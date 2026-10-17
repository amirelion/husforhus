"""Laser points around the tower candidates, from Lantmäteriet's Laserdata Nedladdning, skog (CC BY 4.0, sources.yml
lm_laser), for s02_towers.

The candidates are pipeline/laser.py's: buildings that are not private houses and are named on a card, are churches or
water towers, are at least city.LASER's min_lod1_m tall in the LOD1, or are on the hand list city.LASER_TOWERS. Each
needs the points in its footprint's box grown by city.LASER's ring_m (the ring gives the ground around it).

The catalogue (STAC, collection dsm-skoglig-copc, EPSG:5845: SWEREF 99 TM with RH 2000 heights) is searched
anonymously over the candidates' box. Every tile it lists must be an https URL on lantmateriet.se or one of its
subdomains, or the step stops before reading any. A candidate reads the smallest tiles that cover its box (the 2.5 km
"y" tiles, else the 5 or 10 km "m" ones), the newest where two of one size overlap.

The tiles are COPC files (LAZ organised as an octree), read with laspy's CopcReader through RangeFile: HTTP range
requests on one requests.Session, one at a time, with Basic auth sent only to Lantmäteriet's https hosts (a redirect is
followed by hand; to any other host it goes without the login, to a non-https URL not at all), and the ranges already
read kept in an LRU cache (CACHE_BYTES, more than a 2.5 km tile), so a query reads only the octree nodes it needs and
no node twice. The login comes only from LM_USER and LM_PASSWORD in the process's environment, as s00_fetch_dem's
does: the step never reads a .env file (the owner runs `uv run --env-file .env python -m pipeline.s00_fetch_laser` in
their own terminal), never prints the login, and never sends it anywhere else. Agents never run it with credentials.

Before reading any point the step reads each tile's header and octree hierarchy (a few hundred kB a tile), adds up the
nodes the candidates need and prints that estimate; above city.LASER's budget_bytes (the project's 500 MB rule) it
stops unless --full. Each candidate's points go to data/raw/laser/points/<gid>.npz (pipeline/laser.py: x, y in EPSG:3011
from EPSG:3006, z in RH 2000, classification, return number, number of returns), and data/raw/laser/manifest.json lists
the tiles (id, URL, checksum, date) and, per candidate, its box, its tiles and its file's sha256. A candidate whose
box, tiles and file are unchanged is not read again. Points stay there: Lantmäteriet's terms say they may hold personal
data, so nothing of them is committed or published, only the building parts s02_towers derives.

Without credentials the step says so and succeeds (CI never needs a login): s02_towers uses what is cached. A refused
login (401), a tile that cannot be read or a catalogue that does not answer is a warning, never a stop.
"""
import argparse
import io
import json
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import requests

from . import city, laser
from .fetch import TIMEOUT, UA, sha256_file
from .s00_fetch_dem import credentials, lantmateriet_url, not_fetched
from .s00_fetch_dem import UNAUTHORIZED as DEM_UNAUTHORIZED

STAC_SEARCH = "https://api.lantmateriet.se/stac-hojd/v1/search"
COLLECTION = "dsm-skoglig-copc"
CACHE_BYTES = 256 * 1024 * 1024   # the range cache; a 2.5 km tile is about 80-110 MB, so no node of it is read twice
MAX_REDIRECTS = 5
UNAUTHORIZED = ("401: the login is wrong, or the Geotorget order for Laserdata Nedladdning, skog is not active yet")
CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+|\*)")


class RangeRefused(requests.RequestException):
    """The server answered a range request with something else than the bytes asked for (a whole file, another
    range, a redirect off https): the step reads no further rather than stream what it did not ask for."""


class RangeFile(io.RawIOBase):
    """A read-only, seekable file object over one https URL on Lantmäteriet's hosts, for laspy.CopcReader.

    Every read is an HTTP range request (`Range: bytes=a-b`, expecting 206), made one at a time on `session`. Basic
    `auth` is sent only while the URL is on Lantmäteriet's https hosts: redirects are followed by hand, without the
    login to any other host and not at all to a URL that is not https. Bytes already read stay in an LRU cache of
    whole ranges (`cache_bytes` in all), and a read fetches only the parts of its range the cache lacks.
    `fetched` and `requests` count what went over the wire."""

    def __init__(self, url: str, session: requests.Session, auth=None, cache_bytes: int = CACHE_BYTES):
        super().__init__()
        if not lantmateriet_url(url):
            raise ValueError("RangeFile reads only https URLs on lantmateriet.se or its subdomains")
        self.url, self.session, self.auth, self.cache_bytes = url, session, auth, int(cache_bytes)
        self.pos, self.size = 0, None
        self.fetched = self.requests = 0
        self._cache: OrderedDict[int, bytes] = OrderedDict()   # start -> bytes, least recently used first
        self._cached = 0

    # --- the file-object protocol laspy uses: read, seek, tell (and readinto, readable, seekable, close) ---
    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            pos = offset
        elif whence == io.SEEK_CUR:
            pos = self.pos + offset
        elif whence == io.SEEK_END:
            if self.size is None:
                self._fetch(0, 1)                      # one byte, for the size in Content-Range
            pos = self.size + offset
        else:
            raise ValueError(f"bad whence {whence}")
        if pos < 0:
            raise ValueError("negative seek position")
        self.pos = int(pos)
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            if self.size is None:
                self._fetch(0, 1)
            n = max(0, self.size - self.pos)
        if n == 0:
            return b""
        data = self._read_range(self.pos, self.pos + int(n))
        self.pos += len(data)
        return data

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)

    def clear(self) -> None:
        """Forget the cached ranges (between tiles)."""
        self._cache.clear()
        self._cached = 0

    # --- the cache ---
    def _read_range(self, a: int, b: int) -> bytes:
        if self.size is not None:
            b = min(b, self.size)
        if b <= a:
            return b""
        out = bytearray(b - a)
        have = []
        for start in list(self._cache):
            data = self._cache[start]
            lo, hi = max(a, start), min(b, start + len(data))
            if lo < hi:
                out[lo - a:hi - a] = data[lo - start:hi - start]
                have.append((lo, hi))
                self._cache.move_to_end(start)
        end = b
        for g0, g1 in _gaps(a, b, have):
            data = self._fetch(g0, g1)
            out[g0 - a:g0 - a + len(data)] = data
            if len(data) < g1 - g0:                    # the end of the file
                end = g0 + len(data)
                break
        return bytes(out[:end - a])

    def _remember(self, start: int, data: bytes) -> None:
        if not data or len(data) > self.cache_bytes:
            return
        old = self._cache.pop(start, None)
        self._cached -= len(old) if old else 0
        self._cache[start] = data
        self._cached += len(data)
        while self._cached > self.cache_bytes:
            _, dropped = self._cache.popitem(last=False)
            self._cached -= len(dropped)

    # --- the wire ---
    def _fetch(self, a: int, b: int) -> bytes:
        """Bytes a..b-1 in one range request (fewer at the end of the file), remembered in the cache."""
        url = self.url
        for _ in range(MAX_REDIRECTS + 1):
            auth = self.auth if lantmateriet_url(url) else None
            r = self.session.get(url, headers={**UA, "Range": f"bytes={a}-{b - 1}"}, auth=auth, timeout=TIMEOUT,
                                 allow_redirects=False, stream=True)
            self.requests += 1
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                nxt = urljoin(url, r.headers["Location"])
                r.close()
                if not nxt.startswith("https://"):
                    raise RangeRefused("a range request was redirected off https")
                url = nxt
                continue
            break
        else:
            raise RangeRefused(f"more than {MAX_REDIRECTS} redirects")
        with r:
            if r.status_code == 416:                   # wholly past the end
                return b""
            if r.status_code != 206:
                r.raise_for_status()                   # 401 and the other errors, as requests words them
                raise RangeRefused(f"the server answered a range request with {r.status_code}, not 206: refusing to "
                                   "stream more than was asked for")
            m = CONTENT_RANGE.fullmatch(r.headers.get("Content-Range", "").strip())
            if not m or int(m.group(1)) != a:
                raise RangeRefused("the server sent another byte range than the one asked for")
            if m.group(3) != "*":
                self.size = int(m.group(3))
            want = int(m.group(2)) - a + 1
            data = bytearray()
            for chunk in r.iter_content(1 << 16):
                data += chunk
                if len(data) >= want:
                    break
        data = bytes(data[:want])
        self.fetched += len(data)
        self._remember(a, data)
        return data


def _gaps(a: int, b: int, have: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The parts of [a, b) that none of the `have` intervals covers."""
    out, at = [], a
    for lo, hi in sorted(have):
        if lo > at:
            out.append((at, lo))
        at = max(at, hi)
    if at < b:
        out.append((at, b))
    return out


# --- the catalogue ---

def stac_items(box_wgs84, post=requests.post) -> list[dict]:
    """The dsm-skoglig-copc tiles over a WGS84 box: [{id, href, checksum, datetime, bbox (EPSG:3006), size}], sorted
    by id. The search is anonymous; a listed tile anywhere but on Lantmäteriet's https hosts stops the step."""
    r = post(STAC_SEARCH, json={"collections": [COLLECTION], "bbox": [round(v, 6) for v in box_wgs84], "limit": 1000},
             headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if any(link.get("rel") == "next" for link in body.get("links", [])):
        raise SystemExit("the laser catalogue returned more than one page; raise the limit")
    items = []
    for f in body.get("features", []):
        a = f["assets"]["data"]
        if not lantmateriet_url(a.get("href")):
            raise SystemExit(f"laser tile {f.get('id')} lists {a.get('href')!r}, outside Lantmäteriet's https hosts: "
                             "the login is never sent there, so no tile is read")
        props = f.get("properties", {})
        items.append({"id": f["id"], "href": a["href"], "checksum": a.get("file:checksum"),
                      "datetime": props.get("datetime") or "", "updated": props.get("updated") or "",
                      "bbox": [float(v) for v in (a.get("proj:bbox") or props["proj:bbox"])],
                      "size": a.get("file:size")})
    return sorted(items, key=lambda i: i["id"])


def _overlaps(b, box) -> bool:
    return b[0] < box[2] and b[2] > box[0] and b[1] < box[3] and b[3] > box[1]


def tiles_for(box3006, items: list[dict]) -> list[dict]:
    """The tiles a box reads: of the smallest size whose tiles cover it (2.5 km before 5 and 10 km), newest first, a
    tile left out where newer ones of its size already cover it. A box no size covers (the edge of the survey) reads
    the smallest size that meets it."""
    import shapely
    want = shapely.box(*box3006)
    hits = [i for i in items if _overlaps(i["bbox"], box3006)]
    choice = []
    for size in sorted({round(i["bbox"][2] - i["bbox"][0]) for i in hits}):
        group = sorted((i for i in hits if round(i["bbox"][2] - i["bbox"][0]) == size),
                       key=lambda i: (i["datetime"], i["updated"], i["id"]), reverse=True)
        chosen, cover = [], shapely.Polygon()
        for i in group:
            b = shapely.box(*i["bbox"]).intersection(want)
            if not shapely.covers(cover, b):
                chosen.append(i)
                cover = cover.union(shapely.box(*i["bbox"]))
        if shapely.covers(cover, want):
            return sorted(chosen, key=lambda i: i["id"])
        choice = choice or sorted(chosen, key=lambda i: i["id"])
    return choice


def box_3006(box3011) -> tuple[float, float, float, float]:
    """A box in EPSG:3011 as a box in EPSG:3006 (SWEREF 99 TM, the tiles' horizontal CRS) that holds it."""
    from pyproj import Transformer
    return tuple(Transformer.from_crs(city.CRS, 3006, always_xy=True).transform_bounds(*box3011, densify_pts=21))


def wgs84_box(boxes3011) -> tuple[float, float, float, float]:
    from pyproj import Transformer
    b = np.asarray(boxes3011, dtype=np.float64)
    return Transformer.from_crs(city.CRS, 4326, always_xy=True).transform_bounds(
        b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max(), densify_pts=21)


# --- reading ---

def _bounds(reader, box3006):
    from laspy.copc import Bounds
    return Bounds(np.array(box3006[:2], dtype=np.float64), np.array(box3006[2:], dtype=np.float64)).ensure_3d(
        reader.header.mins, reader.header.maxs)


def node_bytes(reader, boxes3006) -> dict[int, int]:
    """{offset: bytes} of the octree nodes holding points in any of the boxes (laspy.copc.load_octree_for_query, the
    function CopcReader.query itself calls; it reads the hierarchy pages it needs, nothing else)."""
    from laspy.copc import load_octree_for_query
    need = {}
    for box in boxes3006:
        for node in load_octree_for_query(reader.source, reader.copc_info, reader.root_page,
                                          query_bounds=_bounds(reader, box)):
            if node.point_count > 0:
                need[node.offset] = node.byte_size
    return need


def read_box(reader, box3006, box3011) -> dict:
    """The points in box3011 (EPSG:3011), queried from the tile over box3006: {x, y (EPSG:3011), z, cls, rn, nr}."""
    from pyproj import Transformer
    rec = reader.query(bounds=_bounds(reader, box3006))
    ex, ny = np.asarray(rec.x, np.float64), np.asarray(rec.y, np.float64)
    x, y = Transformer.from_crs(3006, city.CRS, always_xy=True).transform(ex, ny)
    x, y = np.asarray(x), np.asarray(y)
    keep = (x >= box3011[0]) & (x <= box3011[2]) & (y >= box3011[1]) & (y <= box3011[3])
    return {"x": x[keep], "y": y[keep], "z": np.asarray(rec.z, np.float64)[keep],
            "cls": np.asarray(rec.classification, np.uint8)[keep], "rn": np.asarray(rec.return_number, np.uint8)[keep],
            "nr": np.asarray(rec.number_of_returns, np.uint8)[keep]}


def _join(parts: list[dict]) -> dict:
    return {k: np.concatenate([p[k] for p in parts]) if parts else np.zeros(0) for k in laser.FIELDS}


class OverBudget(Exception):
    def __init__(self, nbytes: int):
        super().__init__(f"{nbytes:,} bytes")
        self.bytes = int(nbytes)


def read_manifest(path: Path = laser.MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_manifest(m: dict, path: Path = laser.MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(m, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def plan(cands, items: list[dict]) -> list[dict]:
    """Per candidate: {gid, box (EPSG:3011), box3006, tiles: [item]}."""
    out = []
    for gid, geom in zip(cands.gid, cands.geometry, strict=True):
        box = laser.query_box(geom)
        b6 = box_3006(box)
        out.append({"gid": int(gid), "box": list(box), "box3006": b6, "tiles": tiles_for(b6, items)})
    return out


def up_to_date(job: dict, manifest: dict, folder: Path = laser.POINTS) -> bool:
    """True when the candidate's file exists, matches its manifest entry and was read over the same box from the
    same tiles (ids and checksums)."""
    e = manifest.get("points", {}).get(str(job["gid"]))
    path = laser.points_path(job["gid"], folder)
    return bool(e and path.exists() and e.get("box") == job["box"]
                and e.get("tiles") == [[t["id"], t["checksum"]] for t in job["tiles"]]
                and e.get("sha256") == sha256_file(path))


def fetch_points(jobs: list[dict], creds, *, full: bool = False, session: requests.Session | None = None,
                 budget: int = city.LASER["budget_bytes"], folder: Path = laser.POINTS,
                 manifest_path: Path = laser.MANIFEST, log=print) -> dict:
    """Read the points of `jobs` (plan()'s, the up-to-date ones already left out) and write them. The tiles'
    headers and hierarchies come first: the estimate (those bytes plus every node the boxes need, each once) is
    logged, and over `budget` OverBudget is raised before any point is read, unless `full`. Returns a summary."""
    from laspy import CopcReader
    if session is None:
        session = requests.Session()
        session.trust_env = False        # no ~/.netrc login and no proxy from the environment: only `creds`
    tiles = {t["id"]: t for j in jobs for t in j["tiles"]}
    by_tile = {tid: [j for j in jobs if any(t["id"] == tid for t in j["tiles"])] for tid in sorted(tiles)}
    readers, need = {}, {}
    try:
        for tid, js in by_tile.items():
            f = RangeFile(tiles[tid]["href"], session, auth=tuple(creds))
            readers[tid] = (f, CopcReader(f, close_fd=False))
            need[tid] = node_bytes(readers[tid][1], [j["box3006"] for j in js])
        head = sum(f.fetched for f, _ in readers.values())
        est = head + sum(sum(n.values()) for n in need.values())
        log(f"laser: {len(jobs)} candidates over {len(tiles)} tiles: about {est / 1e6:.1f} MB to read "
            f"({head / 1e6:.1f} MB of headers and hierarchy read already)")
        if est > budget and not full:
            raise OverBudget(est)
        manifest = read_manifest(manifest_path)
        manifest.update(collection=COLLECTION, stac=STAC_SEARCH)
        mt = manifest.setdefault("tiles", {})
        mp = manifest.setdefault("points", {})
        parts = {j["gid"]: [] for j in jobs}
        left = {j["gid"]: len(j["tiles"]) for j in jobs}
        jobs_by_gid = {j["gid"]: j for j in jobs}
        written = 0
        for tid, js in by_tile.items():
            f, reader = readers[tid]
            for j in sorted(js, key=lambda j: (j["box"][1], j["box"][0])):
                parts[j["gid"]].append(read_box(reader, j["box3006"], j["box"]))
                left[j["gid"]] -= 1
                if left[j["gid"]] == 0:
                    pts = _join(parts.pop(j["gid"]))
                    path = laser.points_path(j["gid"], folder)
                    laser.save_points(path, pts)
                    job = jobs_by_gid[j["gid"]]
                    mp[str(j["gid"])] = {"box": job["box"], "tiles": [[t["id"], t["checksum"]] for t in job["tiles"]],
                                         "n": int(len(pts["z"])), "sha256": sha256_file(path)}
                    written += 1
            t = tiles[tid]
            mt[tid] = {"href": t["href"], "checksum": t["checksum"], "datetime": t["datetime"], "size": t["size"]}
            f.clear()
            write_manifest(manifest, manifest_path)
        total = sum(f.fetched for f, _ in readers.values())
        reqs = sum(f.requests for f, _ in readers.values())
        log(f"laser: {written} candidates written to {folder} ({total / 1e6:.1f} MB in {reqs} range requests)")
        return {"written": written, "bytes": total, "requests": reqs, "estimate": est}
    finally:
        for f, _ in readers.values():
            f.close()


def masked(e: BaseException, creds) -> str:
    """Why the points were not fetched, on one line, never quoting the login (s00_fetch_dem.not_fetched)."""
    text = not_fetched(e, creds)
    return UNAUTHORIZED if text == DEM_UNAUTHORIZED else text


def main(argv: list[str] | None = None) -> None:
    from laspy.errors import LaspyException
    ap = argparse.ArgumentParser(prog="s00_fetch_laser", description=__doc__.splitlines()[0])
    ap.add_argument("--full", action="store_true",
                    help=f"read even when the estimate is over {city.LASER['budget_bytes'] / 1e6:.0f} MB (it is printed "
                         "first)")
    ap.add_argument("--only", metavar="REASONS",
                    help="only the candidates chosen for one of these comma-separated reasons: named, church, tall, list "
                         "(for a small first read, such as --only list)")
    ap.add_argument("--version", help=argparse.SUPPRESS)   # pipeline.run hands a build's arguments to every step
    args = ap.parse_args([] if argv is None else argv)
    only = set(args.only.split(",")) if args.only else None
    if only and not only <= set(laser.REASONS):
        ap.error(f"--only takes {', '.join(laser.REASONS)}")
    creds = credentials()
    if creds is None:
        n = len(list(laser.POINTS.glob("*.npz"))) if laser.POINTS.exists() else 0
        print(f"laser: no LM_USER/LM_PASSWORD in the environment, so no points are fetched; s02_towers uses the "
              f"{n} cached candidates")
        return
    cands, missing = laser.load_candidates()
    if missing:
        print(f"laser: no card carries these hand-list names: {', '.join(missing)}")
    if only:
        cands = cands[[bool(only & set(w.split(","))) for w in cands.why]]
    try:
        items = stac_items(wgs84_box([laser.query_box(g) for g in cands.geometry]))
        jobs = plan(cands, items)
        manifest = read_manifest()
        todo = [j for j in jobs if j["tiles"] and not up_to_date(j, manifest)]
        outside = sum(1 for j in jobs if not j["tiles"])
        print(f"laser: {len(cands)} candidates, {len(jobs) - len(todo) - outside} up to date, {outside} outside the "
              f"survey, {len(todo)} to read")
        if todo:
            fetch_points(todo, creds, full=args.full)
    except OverBudget as e:
        raise SystemExit(f"laser: the estimate, {e.bytes / 1e6:.0f} MB, is over the "
                         f"{city.LASER['budget_bytes'] / 1e6:.0f} MB rule. Run again with --full to accept it.") from None
    except (requests.RequestException, LaspyException, OSError) as e:
        print(f"warning: laser points not fetched ({masked(e, creds)}); s02_towers uses what is cached",
              file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
