# pipeline/fetch.py
"""Downloads with a manifest, and single members out of remote ZIP files via HTTP range requests.

Every file we fetch is recorded in data/raw/MANIFEST.json, keyed by its path relative to data/raw:
    {url, etag, last_modified, sha256, bytes, retrieved}   (+ member, for a file taken out of a remote zip)
The City's URLs are unversioned and get replaced in place, so the manifest is how a build says what it used.
"""
import hashlib
import json
import os
import struct
import sys
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests

RAW = Path("data/raw")
UA = {"User-Agent": "HusForHus/1.0 (+https://github.com/amirelion/husforhus)"}
TIMEOUT = (30, 300)  # connect, read (seconds)
CHUNK = 1 << 20
EOCD_SEARCH = 66 * 1024  # the end-of-central-directory record sits in the last 22 + 65,535 bytes


# ---------- manifest ----------

def _manifest_path(manifest: Path | None) -> Path:
    return Path(manifest) if manifest is not None else RAW / "MANIFEST.json"


def _key(dest: Path, manifest: Path) -> str:
    try:
        return Path(dest).resolve().relative_to(manifest.parent.resolve()).as_posix()
    except ValueError:
        raise ValueError(f"{dest} is not inside {manifest.parent}") from None


def read_manifest(manifest: Path | None = None) -> dict:
    path = _manifest_path(manifest)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _record(manifest: Path, key: str, entry: dict) -> None:
    data = read_manifest(manifest)
    data[key] = entry
    manifest.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest.with_name(manifest.name + ".part")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, manifest)


def record(dest: Path, entry: dict, manifest: Path | None = None) -> None:
    """Record a file a step made itself (a derived download, such as s00_fetch_dem's resampled terrain) under its
    path relative to data/raw. The entry is the step's; `retrieved` is added."""
    manifest = _manifest_path(manifest)
    _record(manifest, _key(Path(dest), manifest), {**entry, "retrieved": _now()})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _head(url: str, auth=None) -> dict:
    r = requests.head(url, headers=UA, auth=auth, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return {"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"),
            "bytes": int(r.headers["Content-Length"]) if "Content-Length" in r.headers else None}


def _unchanged(dest: Path, old: dict | None, head: dict | None) -> bool:
    """True when dest is the file the manifest describes and the server still has the same version."""
    if not old or not dest.exists() or dest.stat().st_size != old.get("bytes") or sha256_file(dest) != old["sha256"]:
        return False
    if head is None:  # offline: trust the verified local copy
        return True
    if head["etag"]:
        return head["etag"] == old.get("etag")
    return bool(head["last_modified"]) and head["last_modified"] == old.get("last_modified")


def _cached(url, dest, manifest, key, auth):
    """(entry, head): entry is the manifest entry when dest can be reused, else None."""
    old = read_manifest(manifest).get(key)
    try:
        head = _head(url, auth)
    except requests.ConnectionError:
        if _unchanged(dest, old, None):
            print(f"offline: keeping {key} from {old['retrieved']}")
            return old, None
        raise
    return (old if _unchanged(dest, old, head) else None), head


# ---------- whole files ----------

def download(url: str, dest: Path, *, auth=None, manifest: Path | None = None) -> dict:
    """Stream url to dest (atomically), record it in the manifest and return the entry.

    Skips the download when dest matches its manifest entry (size and sha256) and the server's ETag
    (or Last-Modified, if there is no ETag) is unchanged.
    """
    dest, manifest = Path(dest), _manifest_path(manifest)
    key = _key(dest, manifest)
    entry, head = _cached(url, dest, manifest, key, auth)
    if entry is not None:
        return entry
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h, n = hashlib.sha256(), 0
    with requests.get(url, headers=UA, auth=auth, timeout=TIMEOUT, stream=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for block in r.iter_content(CHUNK):
                f.write(block)
                h.update(block)
                n += len(block)
        expected = r.headers.get("Content-Length")
        if expected is not None and int(expected) != n and not r.headers.get("Content-Encoding"):
            raise OSError(f"{url}: got {n:,} bytes, expected {int(expected):,}")
        etag, last_modified = r.headers.get("ETag", head["etag"]), r.headers.get("Last-Modified", head["last_modified"])
    os.replace(tmp, dest)
    entry = {"url": url, "etag": etag, "last_modified": last_modified, "sha256": h.hexdigest(), "bytes": n,
             "retrieved": _now()}
    _record(manifest, key, entry)
    return entry


# ---------- query results (SPARQL, Overpass) ----------

class BadAnswer(requests.RequestException):
    """An answer that came back with HTTP 200 but says the query failed: Overpass's "runtime error" remark, a
    MediaWiki error such as maxlag. post_query never saves or records it, so a later build does not read it
    as the result; post_query_retrying counts it as a failed attempt like a network error."""


def _query_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def query_cached(data: dict, dest: Path, *, manifest: Path | None = None) -> bool:
    """True when post_query would answer from the cache: dest matches its MANIFEST entry (size, sha256) and the entry
    was made by this very query. A caller that paces its requests asks this, not whether dest exists: a query that
    changed (a batch shifted by one more file) is sent again although its file is there."""
    dest, manifest = Path(dest), _manifest_path(manifest)
    old = read_manifest(manifest).get(_key(dest, manifest))
    return bool(old and old.get("query_sha256") == _query_hash(data) and dest.exists()
                and dest.stat().st_size == old.get("bytes") and sha256_file(dest) == old.get("sha256"))


def post_query(url: str, data: dict, dest: Path, *, manifest: Path | None = None, refresh: bool = False,
               headers: dict | None = None, check: Callable[[bytes], str | None] | None = None) -> dict:
    """POST a query (form fields in `data`, such as {"query": sparql}) to url, save the body to dest (atomically)
    and record it in the manifest as {url, query_sha256, sha256, bytes, retrieved, etag: None, last_modified: None}.

    A query endpoint has no ETag, so the query's own hash plays that role: when dest exists, matches its entry
    (size, sha256) and the entry's query_sha256 is this query's, nothing is sent unless refresh is True. A build
    therefore reads the cache; only a missing file or --refresh queries the service.

    check(body), when given, says what is wrong with an answer the service sent with HTTP 200 (or None): such an
    answer raises BadAnswer before anything is written, and the cached file, if any, stays as it was.
    """
    dest, manifest = Path(dest), _manifest_path(manifest)
    key = _key(dest, manifest)
    qhash = _query_hash(data)
    old = read_manifest(manifest).get(key)
    if not refresh and query_cached(data, dest, manifest=manifest):
        return old
    r = requests.post(url, data=data, headers={**UA, **(headers or {})}, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.content
    why = check(body) if check else None
    if why:
        raise BadAnswer(why)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(body)
    os.replace(tmp, dest)
    entry = {"url": url, "query_sha256": qhash, "etag": None, "last_modified": None,
             "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "retrieved": _now()}
    _record(manifest, key, entry)
    return entry


RETRY_AFTER_MAX_S = 600   # a Retry-After longer than this is not waited for in full


def retry_after(error: Exception) -> float:
    """The seconds an error answer (a 429 or 503) asks us to wait (its Retry-After header, in seconds), else 0."""
    response = getattr(error, "response", None)
    value = str((getattr(response, "headers", None) or {}).get("Retry-After", "")).strip()
    return min(float(value), RETRY_AFTER_MAX_S) if value.isascii() and value.isdigit() else 0.0


def post_query_retrying(endpoints: list[str], data: dict, dest: Path, *, retries: int = 2,
                        backoff_s: float | tuple[float, ...] = 5, sleep: Callable[[float], None] = time.sleep,
                        manifest: Path | None = None, refresh: bool = False, headers: dict | None = None,
                        check: Callable[[bytes], str | None] | None = None) -> dict:
    """post_query against each endpoint in turn, with the retry, backoff and keep-the-cache policy every query step
    shares (s00_fetch_wikidata, s00_fetch_osm; Ruling F8).

    A public query service fails often (WDQS answered 502/504 three times in a row in the research; QLever
    rate-limits), and the weekly CI job runs the fetch steps on a cold cache. So:
      - each endpoint in `endpoints` is tried `retries` times, `backoff_s` seconds apart (via `sleep`, which a step
        passes from its own module-level name so tests can stub the wait), before the next endpoint is tried;
        `backoff_s` may also give one wait per retry, the last one repeating (Overpass waits 30, 60, 120 s),
        and a 429 or 503 answer's Retry-After is waited instead when it is longer;
      - only network failures count (requests.RequestException: connection errors, timeouts, cut streams, HTTP
        4xx/5xx, and BadAnswer, an error answer that `check` caught); anything else, such as post_query's ValueError
        for a dest outside the manifest folder, is a bug and propagates;
      - each failure prints "warning: <url> failed (<error>)" to stderr, plus "; retrying in N s" when the same
        endpoint is about to be tried again;
      - when every endpoint has failed and `dest` exists, the cached file is kept with a warning and
        {"url": None, "retrieved": "cached", "bytes": <size>} is returned (not a manifest entry); when there is no
        cached file the call raises SystemExit saying so.
    A cache hit in post_query (file matches the manifest and the query, no refresh) returns before anything is sent,
    so none of this applies to it. Returns post_query's manifest entry on success.
    """
    if not endpoints:
        raise ValueError("post_query_retrying needs at least one endpoint")
    if retries < 1:
        raise ValueError(f"retries must be at least 1, got {retries}")
    dest = Path(dest)
    waits = list(backoff_s) if isinstance(backoff_s, (list, tuple)) else [backoff_s]
    last = None
    for url in endpoints:
        for attempt in range(retries):
            try:
                return post_query(url, data, dest, manifest=manifest, refresh=refresh, headers=headers, check=check)
            except requests.RequestException as e:
                again = attempt + 1 < retries
                wait = max(waits[min(attempt, len(waits) - 1)], retry_after(e))
                print(f"warning: {url} failed ({e}){f'; retrying in {wait:g} s' if again else ''}", file=sys.stderr)
                last = e
                if again:
                    sleep(wait)
    if dest.exists():
        print(f"warning: keeping the cached {dest}", file=sys.stderr)
        return {"url": None, "retrieved": "cached", "bytes": dest.stat().st_size}
    raise SystemExit(f"{dest}: no endpoint answered ({last}) and there is no cached result")


# ---------- ZIP members over HTTP range requests ----------

@dataclass(frozen=True)
class ZipMember:
    name: str
    method: int  # 0 stored, 8 deflate
    flags: int
    crc: int
    csize: int
    usize: int
    offset: int  # of the local file header


def decode_name(raw: bytes, flags: int) -> str:
    """Bit 11 set → UTF-8; otherwise the legacy DOS code page. The City's Windows-made zips use CP850,
    which agrees with Python zipfile's CP437 for Å, Ä, Ö, å, ä and ö."""
    return raw.decode("utf-8" if flags & 0x800 else "cp850")


def read_central_directory(read_range: Callable[[int, int], bytes], size: int) -> list[ZipMember]:
    tail_len = min(size, EOCD_SEARCH)
    tail = read_range(size - tail_len, tail_len)
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or len(tail) - at < 22:
        raise ValueError("no end-of-central-directory record: not a zip file?")
    _, _, _, _, n_entries, cd_size, cd_offset, _ = struct.unpack("<4sHHHHIIH", tail[at:at + 22])
    if n_entries == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise NotImplementedError("ZIP64 archives are not supported")
    cd = read_range(cd_offset, cd_size)
    members, pos = [], 0
    for _ in range(n_entries):
        if cd[pos:pos + 4] != b"PK\x01\x02":
            raise ValueError(f"bad central directory entry at offset {cd_offset + pos}")
        (_, _, _, flags, method, _, _, crc, csize, usize, n_name, n_extra, n_comment, _, _, _,
         offset) = struct.unpack("<4sHHHHHHIIIHHHHHII", cd[pos:pos + 46])
        name = decode_name(cd[pos + 46:pos + 46 + n_name], flags)
        members.append(ZipMember(name, method, flags, crc, csize, usize, offset))
        pos += 46 + n_name + n_extra + n_comment
    return members


def read_member(read_range: Callable[[int, int], bytes], member: ZipMember) -> bytes:
    header = read_range(member.offset, 30)
    if header[:4] != b"PK\x03\x04":
        raise ValueError(f"{member.name}: bad local file header")
    n_name, n_extra = struct.unpack("<HH", header[26:30])
    raw = read_range(member.offset + 30 + n_name + n_extra, member.csize) if member.csize else b""
    if member.method == 0:
        data = raw
    elif member.method == 8:
        inflater = zlib.decompressobj(-15)
        data = inflater.decompress(raw) + inflater.flush()
    else:
        raise NotImplementedError(f"{member.name}: compression method {member.method}")
    if len(data) != member.usize or zlib.crc32(data) != member.crc:
        raise ValueError(f"{member.name}: size or CRC mismatch after reading")
    return data


def http_range_reader(url: str, auth=None) -> Callable[[int, int], bytes]:
    def read_range(start: int, length: int) -> bytes:
        rng = {"Range": f"bytes={start}-{start + length - 1}"}
        with requests.get(url, headers={**UA, **rng}, auth=auth, timeout=TIMEOUT, stream=True) as r:
            if r.status_code != 206:  # a 200 would be the whole file: don't read it
                raise OSError(f"{url}: range request answered {r.status_code}, expected 206")
            data = r.content
        if len(data) != length:
            raise OSError(f"{url}: asked for {length:,} bytes at {start:,}, got {len(data):,}")
        return data
    return read_range


def zip_members(url: str) -> list[str]:
    """Names of the files in a remote zip, read from its central directory only."""
    head = _head(url)
    return [m.name for m in read_central_directory(http_range_reader(url), head["bytes"])]


def fetch_zip_member(url: str, member: str, dest: Path, *, manifest: Path | None = None) -> dict:
    """Range-read one member of a remote zip, inflate it to dest (atomically) and record it in the manifest."""
    dest, manifest = Path(dest), _manifest_path(manifest)
    key = _key(dest, manifest)
    entry, head = _cached(url, dest, manifest, key, None)
    if entry is not None and entry.get("member") == member:
        return entry
    if head is None:
        head = _head(url)
    read_range = http_range_reader(url)
    by_name = {m.name: m for m in read_central_directory(read_range, head["bytes"])}
    if member not in by_name:
        raise KeyError(f"{member!r} is not in {url}")
    data = read_member(read_range, by_name[member])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    entry = {"url": url, "member": member, "etag": head["etag"], "last_modified": head["last_modified"],
             "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "retrieved": _now()}
    _record(manifest, key, entry)
    return entry
