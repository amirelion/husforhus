"""Tunnelbanan layer: the research CSVs as a dated layer, and the track cut."""
import math

import pytest
from pyproj import Transformer

from pipeline import metro

TO_WGS84 = Transformer.from_crs(3011, 4326, always_xy=True)
X0, Y0 = 154000.0, 6580000.0          # a point in central Stockholm, EPSG:3011


@pytest.fixture(scope="module")
def layer():
    return metro.build()


def test_dates_parse(layer):
    for s in layer["stations"] + layer["provisional"]:
        for d in (s["opening_date"], s["closing_date"], *s["line_opening_dates"].values()):
            assert d is None or metro.DATE.fullmatch(d)
    for g in layer["segments"]:
        assert metro.DATE.fullmatch(g["opening_date"])
    with pytest.raises(ValueError):
        metro.parse_date("1950-13-01")


def test_every_segment_station_exists(layer):
    names = {s["name"] for s in layer["stations"]}
    assert len(layer["segments"]) == 32
    for g in layer["segments"]:
        assert len(g["stations"]) >= 2 and set(g["stations"]) <= names, g["id"]
        assert g["line"] in {"green", "red", "blue"}


def test_station_dates(layer):
    by = {s["name"]: s for s in layer["stations"]}
    assert by["Medborgarplatsen"]["opening_date"] == "1950-10-01"
    assert by["Kymlinge"]["opening_date"] is None and not metro.open_on(by["Kymlinge"], "2026-10-16")
    assert by["T-Centralen"]["line_opening_dates"] == {"green": "1957-11-24", "red": "1964-04-05",
                                                       "blue": "1975-08-31"}
    assert by["Hötorget"]["renames"][0] == {"name": "Kungsgatan", "from": "1952-10-26", "to": "1957-11-23"}
    assert by["Skanstull"]["renames"][0]["note"] == "tram stop"
    assert [r["name"] for r in by["Globen"]["renames"]] == ["Slakthuset", "Isstadion", "Globen"]


def test_provisional_kept_apart(layer):
    assert len(layer["provisional"]) == 6
    assert all("xy" not in p for p in layer["provisional"])
    assert all(s["status"] != "replaced" for s in layer["stations"])


def test_hallonbergen_rinkeby_closure(layer):
    s26 = next(g for g in layer["segments"] if g["id"] == "S26")
    assert s26["stations"] == ["Hallonbergen", "Rinkeby"] and s26["closing_date"] == "1985-08-19"
    assert metro.open_on(s26, "1985-08-18") and not metro.open_on(s26, "1985-08-19")


def test_kommun_counts(layer):
    opened = [s for s in layer["stations"] if s["status"] == "open"]
    assert len(opened) == 100
    assert sum(s["inside_stockholms_kommun"] for s in opened) == 82
    assert sum(not s["inside_stockholms_kommun"] for s in opened) == 18


def test_projected(layer):
    for s in layer["stations"]:
        x, y = s["xy"]
        assert 130_000 < x < 180_000 and 6_550_000 < y < 6_610_000, s["name"]


# ---- the cut, on a hand-made graph ---------------------------------------------------------------------------------

def node(i, dx, dy):
    lon, lat = TO_WGS84.transform(X0 + dx, Y0 + dy)
    return {"type": "node", "id": i, "lon": lon, "lat": lat}


def way(i, nodes, **tags):
    return {"type": "way", "id": i, "nodes": nodes, "tags": {"railway": "subway", **tags}}


FIXTURE = [
    node(1, 0, 10), node(2, 500, 60), node(3, 1000, 10), node(4, 1000, 800), node(5, 1000, 400), node(6, 500, 10),
    way(10, [1, 2, 3], name="Röda linjen"),            # 1004.99 m
    way(11, [1, 6, 3], name="Gröna linjen"),           # 1000 m, but named for another line when cutting red
    way(12, [3, 5, 4]),                                # 790 m
    way(13, [1, 4], service="yard"),                   # a shortcut that is not running track
]
STATIONS = {"A": (X0, Y0), "B": (X0 + 1000, Y0), "C": (X0 + 1000, Y0 + 800)}


def test_cut_order_and_length():
    seg = {"id": "SX", "line": "red", "stations": ["A", "B", "C"]}
    t = metro.cut_segment(FIXTURE, seg, STATIONS)
    expect = 10 + 2 * math.hypot(500, 50) + 10 + 10 + 790
    assert t["length_m"] == pytest.approx(expect, abs=0.5)
    ys = [round(y - Y0) for _, y in t["coords"]]
    xs = [round(x - X0) for x, _ in t["coords"]]
    assert list(zip(xs, ys)) == [(0, 0), (0, 10), (500, 60), (1000, 10), (1000, 0),
                                 (1000, 10), (1000, 400), (1000, 800), (1000, 800)]


def test_cut_prefers_own_line_and_skips_yard():
    seg = {"id": "SX", "line": "green", "stations": ["A", "B"]}
    t = metro.cut_segment(FIXTURE, seg, STATIONS)
    assert t["length_m"] == pytest.approx(1020, abs=0.5)
    seg = {"id": "SX", "line": "green", "stations": ["A", "C"]}
    assert metro.cut_segment(FIXTURE, seg, STATIONS)["length_m"] == pytest.approx(10 + 1000 + 790, abs=0.5)


def test_siding_only_where_allowed():
    track = [node(1, 0, 0), node(2, 1000, 0), way(20, [1, 2], service="siding")]
    st = {"A": (X0, Y0), "B": (X0 + 1000, Y0)}
    with pytest.raises(ValueError):
        metro.cut_segment(track, {"id": "S25", "line": "blue", "stations": ["A", "B"]}, st)
    assert metro.cut_segment(track, {"id": "S26", "line": "blue", "stations": ["A", "B"]}, st)["length_m"] == \
        pytest.approx(1000, abs=0.5)
