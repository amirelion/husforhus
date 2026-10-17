"""s00_fetch_laser: the range file object, the catalogue, the tile choice, the candidates and the fetch, all against
fakes. Nothing here touches the network or a real login: the COPC tiles are written by tests/copc_fixture.py and
served by a fake requests.Session."""
import builtins
import io
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import requests
from pyproj import Transformer
from shapely.geometry import box

from pipeline import city, laser, s00_fetch_laser as fl
from pipeline.fetch import UA
from tests.copc_fixture import write_copc
from tests.tinycity import local_box, tiny_city

USER = "user@example.org"
PASSWORD = "pw-never-printed-9Z"
HREF = "https://dl1.lantmateriet.se/hojd/data/pointcloud/sls/21c031/y21c031-65800_6725_25.copc.laz"


class Response:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def iter_content(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for url", response=self)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Session:
    """Serves files by URL with range requests; records (url, range, auth) for every call. `redirect` maps a URL to
    the Location it answers with; `full` URLs answer 200 with the whole file (a server that ignores Range)."""

    def __init__(self, files, redirect=None, full=(), status=None):
        self.files, self.redirect, self.full, self.status = files, redirect or {}, set(full), status or {}
        self.calls = []

    def get(self, url, headers=None, auth=None, timeout=None, allow_redirects=True, stream=False):
        assert allow_redirects is False and stream is True and headers["User-Agent"] == UA["User-Agent"]
        rng = headers.get("Range")
        self.calls.append((url, rng, auth))
        if url in self.redirect:
            return Response(302, headers={"Location": self.redirect[url]})
        if url in self.status:
            return Response(self.status[url])
        data = self.files[url]
        if url in self.full:
            return Response(200, data)
        a, b = (int(v) for v in rng.removeprefix("bytes=").split("-"))
        if a >= len(data):
            return Response(416)
        b = min(b, len(data) - 1)
        return Response(206, data[a:b + 1], {"Content-Range": f"bytes {a}-{b}/{len(data)}"})


def test_range_file_reads_seeks_and_caches():
    data = bytes(range(256)) * 40
    s = Session({HREF: data})
    f = fl.RangeFile(HREF, s, auth=(USER, PASSWORD))
    assert f.read(10) == data[:10] and f.tell() == 10
    f.seek(100)
    assert f.read(50) == data[100:150]
    n = len(s.calls)
    f.seek(105)
    assert f.read(20) == data[105:125] and len(s.calls) == n          # inside a cached range: no request
    f.seek(140)
    assert f.read(30) == data[140:170]
    assert s.calls[-1][1] == "bytes=150-169"                          # only the part the cache lacks
    f.seek(-6, io.SEEK_END)
    assert f.read() == data[-6:]
    assert f.read(5) == b"" and f.seek(len(data) + 10) and f.read(4) == b""
    assert f.fetched == sum(int(r.split("-")[1]) - int(r.split("=")[1].split("-")[0]) + 1 for _, r, _ in s.calls
                            if int(r.split("=")[1].split("-")[0]) < len(data)) and f.requests == len(s.calls)
    buf = bytearray(8)
    f.seek(0)
    assert f.readinto(memoryview(buf)) == 8 and bytes(buf) == data[:8]


def test_range_file_evicts_the_least_recently_used_ranges():
    data = bytes(1000)
    s = Session({HREF: data})
    f = fl.RangeFile(HREF, s, cache_bytes=250)
    for start in (0, 200, 400):
        f.seek(start)
        f.read(100)
    n = len(s.calls)
    f.seek(0)
    f.read(100)                     # evicted: read again
    assert len(s.calls) == n + 1
    f.seek(400)
    f.read(100)                     # still cached
    assert len(s.calls) == n + 1


def test_the_login_goes_only_to_lantmateriets_https_hosts():
    data = b"x" * 100
    other = "https://bucket.example-cdn.net/signed/tile.copc.laz?X-Amz-Signature=abc"
    s = Session({other: data}, redirect={HREF: other})
    f = fl.RangeFile(HREF, s, auth=(USER, PASSWORD))
    assert f.read(10) == b"x" * 10
    assert s.calls == [(HREF, "bytes=0-9", (USER, PASSWORD)), (other, "bytes=0-9", None)]
    # a redirect to plain http is not followed at all
    s = Session({}, redirect={HREF: "http://dl1.lantmateriet.se/plain.copc.laz"})
    with pytest.raises(fl.RangeRefused, match="off https"):
        fl.RangeFile(HREF, s, auth=(USER, PASSWORD)).read(10)
    # and a file object is never opened on another host
    for url in ("https://dl1.lantmateriet.se.example.org/x.laz", "http://dl1.lantmateriet.se/x.laz",
                "https://user:pw@dl1.lantmateriet.se/x.laz", "https://example.org/x.laz"):
        with pytest.raises(ValueError, match="only https URLs on lantmateriet.se"):
            fl.RangeFile(url, Session({}), auth=(USER, PASSWORD))


def test_a_server_that_ignores_the_range_or_refuses_the_login_stops_the_read():
    with pytest.raises(fl.RangeRefused, match="200, not 206"):
        fl.RangeFile(HREF, Session({HREF: b"y" * 50}, full={HREF})).read(10)
    with pytest.raises(requests.HTTPError) as e:
        fl.RangeFile(HREF, Session({}, status={HREF: 401}), auth=(USER, PASSWORD)).read(10)
    assert fl.masked(e.value, (USER, PASSWORD)) == fl.UNAUTHORIZED


# --- the catalogue and the tile choice ---

def feature(fid, href, bbox, when="2021-03-23T00:00:00Z"):
    return {"id": fid, "properties": {"datetime": when, "updated": "2026-10-14T00:00:00Z", "proj:bbox": bbox},
            "assets": {"data": {"href": href, "file:checksum": f"1220{fid}", "file:size": 1000, "proj:bbox": bbox}}}


def test_stac_search_is_anonymous_and_refuses_tiles_off_lantmateriet():
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return Response(200)

    body = {"features": [feature("a", HREF, [672500, 6580000, 675000, 6582500])], "links": []}
    Response.json = lambda self: body
    try:
        items = fl.stac_items((18.0, 59.3, 18.1, 59.4), post=post)
        assert items[0]["href"] == HREF and items[0]["bbox"] == [672500, 6580000, 675000, 6582500]
        assert calls[0][1]["collections"] == ["dsm-skoglig-copc"] and calls[0][2] == UA
        body["features"].append(feature("b", "https://evil.example.org/b.copc.laz", [0, 0, 1, 1]))
        with pytest.raises(SystemExit, match="outside Lantmäteriet's https hosts"):
            fl.stac_items((18.0, 59.3, 18.1, 59.4), post=post)
        body["links"] = [{"rel": "next"}]
        with pytest.raises(SystemExit, match="more than one page"):
            fl.stac_items((18.0, 59.3, 18.1, 59.4), post=post)
    finally:
        del Response.json


def item(fid, bbox, when="2021-03-23"):
    return {"id": fid, "href": HREF, "checksum": fid, "datetime": when, "updated": "", "bbox": bbox, "size": 1}


def test_tiles_for_prefers_the_small_tiles_and_the_newest():
    big = item("m10", [670000, 6580000, 680000, 6590000])
    y1 = item("y1", [672500, 6580000, 675000, 6582500])
    y2 = item("y2", [675000, 6580000, 677500, 6582500])
    old = item("y1old", [672500, 6580000, 675000, 6582500], "2020-03-31")
    items = [big, y1, y2, old]
    assert fl.tiles_for((673000, 6581000, 673100, 6581100), items) == [y1]                  # 2.5 km, the newest
    assert fl.tiles_for((674950, 6581000, 675050, 6581100), items) == [y1, y2]              # across two
    assert fl.tiles_for((677400, 6581000, 677600, 6581100), items) == [big]                 # no 2.5 km cover
    assert fl.tiles_for((690000, 6581000, 690100, 6581100), items) == []


# --- the candidates ---

def test_candidates_leave_out_private_houses():
    b, y, a = tiny_city()
    a = a.copy()
    # a private house named on its card and on the hand list, and a tall private house: never a candidate
    a.loc[4, "name"] = "Engelbrektskyrkan"
    b = b.copy()
    b.loc[6, "height"] = 40.0
    cands, missing = laser.candidates(b, y, a)
    hide = laser.hidden(b.kategori, y.private, y.ysrc)
    assert not set(cands.gid) & set(np.flatnonzero(hide).tolist())
    assert 4 not in set(cands.gid) and 6 not in set(cands.gid)
    why = dict(zip(cands.gid, cands.why))
    assert why[0] == "named,church,tall,list" and why[7] == "named,tall,list" and why[10] == "named"
    assert why[2] == "tall" and 1 in why                                # 39.1 m; the palace is named
    assert 3 not in why and 8 not in why                                # unnamed, low, not a church
    assert "Engelbrektskyrkan" in missing and "Kaknästornet" not in missing
    # a Wikidata name counts only where the card may carry it
    wiki = pd.DataFrame({"gid": [3, 9], "name": ["Hornshuset", "Villa X"]})
    cands, _ = laser.candidates(b, y, a, wiki)
    assert 3 in set(cands.gid) and 9 not in set(cands.gid)


def test_hand_list_matches_card_names_and_aliases():
    names = ["Stockholms stadshus", "", "Sankta Gertruds kyrka", "storkyrkan", "Katarina kyrka"]
    found = laser.hand_list(names)
    assert found["Stadshuset"] == [0] and found["Tyska kyrkan"] == [2] and found["Storkyrkan"] == [3]
    assert found["Katarina kyrka"] == [4] and found["Kaknästornet"] == []


def test_points_round_trip(tmp_path):
    pts = {"x": np.array([154025.123, 154030.5]), "y": np.array([6578886.7, 6578900.25]), "z": np.array([12.5, 80.0]),
           "cls": np.array([1, 2]), "rn": np.array([1, 1]), "nr": np.array([1, 2])}
    laser.save_points(tmp_path / "1.npz", pts)
    back = laser.load_points(tmp_path / "1.npz")
    assert np.allclose(back["x"], pts["x"], atol=1e-3) and np.allclose(back["y"], pts["y"], atol=1e-3)
    assert back["cls"].tolist() == [1, 2] and back["nr"].tolist() == [1, 2]


# --- the fetch over a fake tile ---

TO_3006 = Transformer.from_crs(city.CRS, 3006, always_xy=True)


def tile_over(boxes3011, n_per_box=300, seed=4):
    """A COPC tile (EPSG:3006) whose points lie in the given EPSG:3011 boxes, and its catalogue item."""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for x0, y0, x1, y1 in boxes3011:
        xs.append(rng.uniform(x0, x1, n_per_box))
        ys.append(rng.uniform(y0, y1, n_per_box))
    ex, ny = TO_3006.transform(np.concatenate(xs), np.concatenate(ys))
    n = len(ex)
    pts = {"x": ex, "y": ny, "z": rng.uniform(5, 60, n), "cls": np.where(np.arange(n) % 3 == 0, 2, 1),
           "rn": np.ones(n), "nr": np.ones(n)}
    cx, cy = float(np.floor((ex.min() + ex.max()) / 2)), float(np.floor((ny.min() + ny.max()) / 2))
    data = write_copc(pts, (cx, cy, 30.0), 1000.0)
    bbox = [cx - 1000, cy - 1000, cx + 1000, cy + 1000]
    return data, {"id": "21c031-y1", "href": HREF, "checksum": "1220aa", "datetime": "2021-03-23", "updated": "",
                  "bbox": bbox, "size": len(data)}, pts


def cand_frame(geoms):
    return gpd.GeoDataFrame({"gid": list(range(len(geoms)))}, geometry=geoms, crs=city.CRS)


def test_fetch_reads_only_the_nodes_it_needs_and_caches_points_in_the_city_crs(tmp_path):
    near = local_box(0, 0, 20, 20)                     # two candidates far apart in one tile
    far = local_box(1500, 1500, 1520, 1520)
    boxes = [laser.query_box(g) for g in (near, far)]
    data, it, pts = tile_over(boxes)
    s = Session({HREF: data})
    jobs = fl.plan(cand_frame([near]), [it])
    assert [t["id"] for t in jobs[0]["tiles"]] == ["21c031-y1"]
    logs = []
    out = fl.fetch_points(jobs, (USER, PASSWORD), session=s, folder=tmp_path / "points",
                          manifest_path=tmp_path / "manifest.json", log=logs.append)
    assert out["written"] == 1 and out["bytes"] < len(data)           # not the whole tile
    assert "about" in logs[0] and "MB to read" in logs[0]
    assert all(auth == (USER, PASSWORD) for _, _, auth in s.calls)
    got = laser.load_points(tmp_path / "points" / "0.npz")
    x0, y0, x1, y1 = boxes[0]
    assert len(got["z"]) == 300 and (got["x"] >= x0).all() and (got["x"] <= x1).all()
    assert (got["y"] >= y0).all() and (got["y"] <= y1).all()
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert m["points"]["0"]["n"] == 300 and m["points"]["0"]["tiles"] == [["21c031-y1", "1220aa"]]
    assert m["tiles"]["21c031-y1"]["href"] == HREF
    assert fl.up_to_date(jobs[0], m, tmp_path / "points")
    text = json.dumps(m) + "".join(logs)
    assert PASSWORD not in text and USER not in text


def test_a_candidate_across_two_tiles_reads_both(tmp_path):
    g = local_box(0, 0, 20, 20)
    box = laser.query_box(g)
    data, it, pts = tile_over([box], n_per_box=400)
    split = float(np.median(pts["x"]))                 # the tile edge, in EPSG:3006, through the candidate's box
    files, items = {}, []
    for k, sel in enumerate((pts["x"] < split, pts["x"] >= split)):
        href = HREF.replace(".copc.laz", f"-{k}.copc.laz")
        part = {f: np.asarray(v)[sel] for f, v in pts.items()}
        cx, cy = float(np.floor(part["x"].mean())), float(np.floor(part["y"].mean()))
        files[href] = write_copc(part, (cx, cy, 30.0), 500.0)
        x0, x1 = (split - 2500, split) if k == 0 else (split, split + 2500)
        items.append({"id": f"y{k}", "href": href, "checksum": f"c{k}", "datetime": "2021-03-23", "updated": "",
                      "bbox": [x0, it["bbox"][1], x1, it["bbox"][3]], "size": len(files[href])})
    s = Session(files)
    jobs = fl.plan(cand_frame([g]), items)
    assert [t["id"] for t in jobs[0]["tiles"]] == ["y0", "y1"]
    fl.fetch_points(jobs, (USER, PASSWORD), session=s, folder=tmp_path / "p", manifest_path=tmp_path / "m.json",
                    log=lambda _: None)
    assert len(laser.load_points(tmp_path / "p" / "0.npz")["z"]) == 400
    assert json.loads((tmp_path / "m.json").read_text())["points"]["0"]["tiles"] == [["y0", "c0"], ["y1", "c1"]]


def test_over_the_budget_nothing_is_read_without_full(tmp_path):
    g = local_box(0, 0, 20, 20)
    data, it, _ = tile_over([laser.query_box(g)])
    s = Session({HREF: data})
    jobs = fl.plan(cand_frame([g]), [it])
    with pytest.raises(fl.OverBudget):
        fl.fetch_points(jobs, (USER, PASSWORD), session=s, budget=1000, folder=tmp_path / "p",
                        manifest_path=tmp_path / "m.json", log=lambda _: None)
    assert not (tmp_path / "p").exists()
    out = fl.fetch_points(jobs, (USER, PASSWORD), session=s, budget=1000, full=True, folder=tmp_path / "p",
                          manifest_path=tmp_path / "m.json", log=lambda _: None)
    assert out["written"] == 1


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    monkeypatch.delenv("LM_USER", raising=False)
    monkeypatch.delenv("LM_PASSWORD", raising=False)
    return tmp_path


def test_without_a_login_the_step_says_so_and_succeeds_and_never_reads_dotenv(raw, monkeypatch, capsys):
    (raw / ".env").write_text(f"LM_USER={USER}\nLM_PASSWORD={PASSWORD}\n")
    real_open = builtins.open

    def guarded(file, *a, **k):
        if str(file).endswith(".env"):
            raise AssertionError(f"s00_fetch_laser opened {file}")
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", guarded)
    monkeypatch.setattr(io, "open", guarded)
    monkeypatch.setattr(fl, "stac_items", lambda *a, **k: pytest.fail("no catalogue search without a login"))
    fl.main([])
    fl.main(["--version", "v20991231"])                   # pipeline.run hands the build's version to every step
    out = capsys.readouterr()
    assert "no LM_USER/LM_PASSWORD in the environment" in out.out
    assert PASSWORD not in out.out + out.err and USER not in out.out + out.err


def test_a_refused_login_is_a_warning_that_never_quotes_it(raw, monkeypatch, capsys):
    monkeypatch.setenv("LM_USER", USER)
    monkeypatch.setenv("LM_PASSWORD", PASSWORD)
    g = local_box(0, 0, 20, 20)
    data, it, _ = tile_over([laser.query_box(g)])
    monkeypatch.setattr(laser, "load_candidates", lambda: (cand_frame([g]), []))
    monkeypatch.setattr(fl, "stac_items", lambda *a, **k: [it])

    def refused(url, **kw):
        raise requests.HTTPError(f"401 Client Error for url {url} ({USER}:{PASSWORD})", response=Response(401))

    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kw: refused(url, **kw))
    fl.main([])
    out = capsys.readouterr()
    assert fl.UNAUTHORIZED in out.err
    assert PASSWORD not in out.out + out.err and USER not in out.out + out.err


def test_only_narrows_the_candidates_by_reason(raw, monkeypatch, capsys):
    monkeypatch.setenv("LM_USER", USER)
    monkeypatch.setenv("LM_PASSWORD", PASSWORD)
    c = cand_frame([local_box(0, 0, 20, 20), local_box(100, 0, 120, 20), local_box(200, 0, 220, 20)])
    c["why"] = ["named,list", "tall", "church"]
    monkeypatch.setattr(laser, "load_candidates", lambda: (c, []))
    monkeypatch.setattr(fl, "stac_items", lambda *a, **k: [])
    seen = []
    monkeypatch.setattr(fl, "plan", lambda cands, items: seen.append(cands.gid.tolist()) or [])
    fl.main(["--only", "list"])
    fl.main(["--only", "tall,church"])
    fl.main([])
    assert seen == [[0], [1, 2], [0, 1, 2]]
    with pytest.raises(SystemExit):
        fl.main(["--only", "pretty"])


def test_the_step_is_registered_after_the_tables_it_reads():
    from pipeline import run
    steps = run.STEPS
    assert steps.index("s02_attributes") < steps.index("s06_wiki") < steps.index("s00_fetch_laser")
    assert steps.index("s00_fetch_laser") < steps.index("s02_towers") < steps.index("s03_tiles")


def test_geometry_helpers():
    b = laser.query_box(box(100.04, 200.0, 110.0, 210.01), ring=15)
    assert b == (85.0, 185.0, 125.0, 225.1)
