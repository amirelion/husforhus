# tests/test_fetch.py
"""pipeline.fetch (contract C6): manifest-recording downloads and ZIP members over HTTP range requests."""
import hashlib
import io
import json
import re
import zipfile

import pytest
import requests

from pipeline import fetch

CP850_NAME = "Öster/Vatten_area.dbf"
DBF = b"dbf bytes " * 500
SHP = b"\x00\x00\x27\x0a" + bytes(range(256)) * 40


def make_zip() -> bytes:
    """A zip like the City's: one member with a CP850 (not UTF-8) name, stored and deflated members."""
    placeholder = "X" + CP850_NAME[1:]  # same byte length as the CP850 encoding of the real name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo(placeholder), DBF, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("Öster/Vatten_area.prj"), b"PROJCS[...]", compress_type=zipfile.ZIP_STORED)
        z.writestr(zipfile.ZipInfo("Vatten_area.shp"), SHP, compress_type=zipfile.ZIP_DEFLATED)
    data = buf.getvalue().replace(placeholder.encode("ascii"), CP850_NAME.encode("cp850"))
    assert data.count(CP850_NAME.encode("cp850")) == 2  # local header + central directory
    return data


ZIP = make_zip()


def reader(blob: bytes, log: list | None = None):
    def read_range(start: int, length: int) -> bytes:
        if log is not None:
            log.append((start, length))
        assert 0 <= start and start + length <= len(blob)
        return blob[start:start + length]
    return read_range


def test_central_directory_names_and_methods():
    members = fetch.read_central_directory(reader(ZIP), len(ZIP))
    assert [m.name for m in members] == [CP850_NAME, "Öster/Vatten_area.prj", "Vatten_area.shp"]
    assert [m.method for m in members] == [8, 0, 8]
    assert members[0].flags & 0x800 == 0  # legacy code page, like the City's zips
    assert members[1].flags & 0x800  # Python wrote this one as UTF-8


def test_cp850_matches_zipfile_cp437_for_swedish_letters():
    assert zipfile.ZipFile(io.BytesIO(ZIP)).namelist()[0] == CP850_NAME
    assert fetch.decode_name("ÅÄÖåäö".encode("cp850"), 0) == "ÅÄÖåäö"
    assert fetch.decode_name("Älvsjö".encode("utf-8"), 0x800) == "Älvsjö"


def test_read_member_deflated_and_stored():
    members = {m.name: m for m in fetch.read_central_directory(reader(ZIP), len(ZIP))}
    assert fetch.read_member(reader(ZIP), members[CP850_NAME]) == DBF
    assert fetch.read_member(reader(ZIP), members["Öster/Vatten_area.prj"]) == b"PROJCS[...]"
    assert fetch.read_member(reader(ZIP), members["Vatten_area.shp"]) == SHP


def test_reads_only_the_tail_and_the_directory():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("big.bin", bytes(1_000_000), compress_type=zipfile.ZIP_STORED)
        z.writestr("small.txt", b"hi")
    blob, log = buf.getvalue(), []
    members = fetch.read_central_directory(reader(blob, log), len(blob))
    assert [m.name for m in members] == ["big.bin", "small.txt"]
    assert len(log) == 2 and sum(n for _, n in log) < 70_000  # the 66 KB tail, then the directory


def test_crc_mismatch_is_an_error():
    members = fetch.read_central_directory(reader(ZIP), len(ZIP))
    bad = fetch.ZipMember(**{**members[1].__dict__, "crc": members[1].crc ^ 1})
    with pytest.raises(ValueError, match="CRC"):
        fetch.read_member(reader(ZIP), bad)


def test_not_a_zip():
    with pytest.raises(ValueError, match="end-of-central-directory"):
        fetch.read_central_directory(reader(b"not a zip at all" * 10), 160)


# ---------- a fake HTTP server, so nothing touches the network ----------

class FakeResponse:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self.content, self.headers = status, body, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeServer:
    def __init__(self, files: dict[str, bytes], etag='"v1"'):
        self.files, self.etag, self.gets, self.heads, self.offline = files, etag, [], [], False

    def headers(self, url):
        return {"ETag": self.etag, "Last-Modified": "Wed, 18 Feb 2026 18:01:05 GMT",
                "Content-Length": str(len(self.files[url]))}

    def head(self, url, **kw):
        if self.offline:
            raise requests.ConnectionError("offline")
        self.heads.append(url)
        return FakeResponse(200, b"", self.headers(url))

    def get(self, url, headers=None, **kw):
        if self.offline:
            raise requests.ConnectionError("offline")
        body = self.files[url]
        rng = (headers or {}).get("Range")
        self.gets.append((url, rng))
        if rng:
            a, b = (int(v) for v in rng.removeprefix("bytes=").split("-"))
            return FakeResponse(206, body[a:b + 1], {**self.headers(url), "Content-Length": str(b + 1 - a)})
        return FakeResponse(200, body, self.headers(url))


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = FakeServer({"https://example.org/a.zip": ZIP, "https://example.org/b.bin": b"hello world" * 1000})
    monkeypatch.setattr(fetch.requests, "head", srv.head)
    monkeypatch.setattr(fetch.requests, "get", srv.get)
    monkeypatch.setattr(fetch, "RAW", tmp_path / "raw")
    return srv


def test_download_records_manifest(server, tmp_path):
    dest = tmp_path / "raw" / "city" / "b.bin"
    entry = fetch.download("https://example.org/b.bin", dest)
    body = server.files["https://example.org/b.bin"]
    assert dest.read_bytes() == body
    assert entry["sha256"] == hashlib.sha256(body).hexdigest() and entry["bytes"] == len(body)
    assert entry["etag"] == '"v1"' and entry["url"] == "https://example.org/b.bin"
    assert entry["retrieved"].endswith("Z")
    manifest = json.loads((tmp_path / "raw" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest == {"city/b.bin": entry}
    assert not list(dest.parent.glob("*.part"))


def test_download_skips_when_etag_unchanged(server, tmp_path):
    dest = tmp_path / "raw" / "b.bin"
    first = fetch.download("https://example.org/b.bin", dest)
    n_gets = len(server.gets)
    assert fetch.download("https://example.org/b.bin", dest) == first
    assert len(server.gets) == n_gets  # HEAD only
    server.etag = '"v2"'
    assert fetch.download("https://example.org/b.bin", dest)["etag"] == '"v2"'
    assert len(server.gets) == n_gets + 1


def test_download_repairs_a_corrupted_file(server, tmp_path):
    dest = tmp_path / "raw" / "b.bin"
    fetch.download("https://example.org/b.bin", dest)
    dest.write_bytes(b"truncated")
    fetch.download("https://example.org/b.bin", dest)
    assert dest.read_bytes() == server.files["https://example.org/b.bin"]


def test_download_offline_keeps_verified_copy(server, tmp_path, capsys):
    dest = tmp_path / "raw" / "b.bin"
    first = fetch.download("https://example.org/b.bin", dest)
    server.offline = True
    assert fetch.download("https://example.org/b.bin", dest) == first
    assert "offline" in capsys.readouterr().out
    with pytest.raises(requests.ConnectionError):
        fetch.download("https://example.org/b.bin", tmp_path / "raw" / "other.bin")


def test_download_refuses_paths_outside_the_manifest_folder(server, tmp_path):
    with pytest.raises(ValueError, match="not inside"):
        fetch.download("https://example.org/b.bin", tmp_path / "elsewhere" / "b.bin")


def test_download_with_own_manifest(server, tmp_path):
    cache = tmp_path / "cache"
    entry = fetch.download("https://example.org/b.bin", cache / "b.bin", manifest=cache / "MANIFEST.json")
    assert json.loads((cache / "MANIFEST.json").read_text(encoding="utf-8")) == {"b.bin": entry}


def test_record_keeps_a_derived_file_under_its_path_with_the_time_it_was_made(tmp_path):
    # Plan 3 (s00_fetch_dem): a file a step made itself, recorded beside the downloads
    manifest = tmp_path / "raw" / "MANIFEST.json"
    dest = tmp_path / "raw" / "dem" / "dtm5.tif"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"tif")
    manifest.write_text(json.dumps({"city/a.zip": {"url": "https://example.org/a.zip"}}), encoding="utf-8")
    entry = {"url": "https://example.org/search", "sha256": fetch.sha256_file(dest), "bytes": 3, "items": [{"id": "a"}]}
    fetch.record(dest, entry, manifest=manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert sorted(data) == ["city/a.zip", "dem/dtm5.tif"]          # the other entries stay
    got = data["dem/dtm5.tif"]
    assert {k: v for k, v in got.items() if k != "retrieved"} == entry and "retrieved" not in entry
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", got["retrieved"])
    with pytest.raises(ValueError, match="not inside"):
        fetch.record(tmp_path / "elsewhere.tif", entry, manifest=manifest)


def test_zip_members_over_range_requests(server):
    assert fetch.zip_members("https://example.org/a.zip") == [CP850_NAME, "Öster/Vatten_area.prj",
                                                              "Vatten_area.shp"]
    assert all(rng for _, rng in server.gets)  # never a whole-file GET


def test_fetch_zip_member(server, tmp_path):
    dest = tmp_path / "raw" / "stadskarta" / "Vatten_area.dbf"
    entry = fetch.fetch_zip_member("https://example.org/a.zip", CP850_NAME, dest)
    assert dest.read_bytes() == DBF
    assert entry["member"] == CP850_NAME and entry["sha256"] == hashlib.sha256(DBF).hexdigest()
    assert fetch.read_manifest()["stadskarta/Vatten_area.dbf"] == entry
    n_gets = len(server.gets)
    assert fetch.fetch_zip_member("https://example.org/a.zip", CP850_NAME, dest) == entry
    assert len(server.gets) == n_gets  # unchanged ETag: nothing re-read
    with pytest.raises(KeyError, match="not in"):
        fetch.fetch_zip_member("https://example.org/a.zip", "Nope.shp", tmp_path / "raw" / "nope.shp")


def test_range_reader_refuses_a_full_response(monkeypatch):
    monkeypatch.setattr(fetch.requests, "get", lambda url, **kw: FakeResponse(200, b"whole file"))
    with pytest.raises(OSError, match="expected 206"):
        fetch.http_range_reader("https://example.org/a.zip")(0, 4)
