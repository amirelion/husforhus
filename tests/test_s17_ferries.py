"""The boats' step (s17_ferries): ferries.json in a version folder, its check in s99, and its registration. No network:
ferries.fetch is replaced by the hand-made elements of tests/test_ferries.py."""
import json

import pytest
import shapely
from shapely.geometry import box

from pipeline import city, ferries, run, s03_tiles, s17_ferries, s99_validate
from pipeline.sources import check_sources, load_sources
from tests.test_ferries import CHANNEL, CORNER, GROUND, elements, project, write_base

VERSION = "v20261020-t1"
ON = {"features": {"ferries": True}}       # stockholm.json's features, for check_ferries
OFF = {"features": {"ferries": False}}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A version folder with s04_base's water and land, in a working directory of its own (web/data, data/raw)."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "web" / "data" / VERSION
    out.mkdir(parents=True)
    write_base(out, CHANNEL[0], GROUND)
    real = ferries.lines
    monkeypatch.setattr(ferries, "lines", lambda els, project_=None: real(els, project))   # local metres as lon, lat
    return out


def test_writes_ferries_json_into_the_version(folder, monkeypatch, capsys):
    monkeypatch.setattr(ferries, "fetch", lambda refresh=False: elements())
    s17_ferries.main(["--version", VERSION, "--release", "--data", "x"])     # another step's arguments go to every step
    out = json.loads((folder / "ferries.json").read_text(encoding="utf-8"))
    assert out["version"] == 1
    assert [(r["id"], r["kind"], r["ends"]) for r in out["routes"]] == [
        ("r1", "ferry", ["pier", "pier"]), ("r12", "ship", ["pier", "edge"]), ("r10", "ship", ["pier", "edge"])]
    assert "1 city boat routes, 2 ship routes" in capsys.readouterr().out
    assert s99_validate.check_ferries(folder) == [] and s99_validate.check_ferries(folder, ON, release=True) == []


def test_without_overpass_or_a_cache_the_file_has_no_routes(folder, monkeypatch, capsys):
    def down(refresh=False):
        raise SystemExit("data/raw/osm/ferries.json: no endpoint answered and there is no cached result")
    monkeypatch.setattr(ferries, "fetch", down)
    (folder / "ferries.json").write_text('{"version": 1, "routes": [{"id": "r1"}]}', encoding="utf-8")   # stale
    s17_ferries.main(["--version", VERSION])
    assert json.loads((folder / "ferries.json").read_text(encoding="utf-8")) == {"version": 1, "routes": []}
    assert "warning: no ferry routes" in capsys.readouterr().err


@pytest.mark.parametrize("failure", [SystemExit("data/raw/osm/ferries.json: no endpoint answered and there is no "
                                                 "cached result"), json.JSONDecodeError("a cut file", "{", 1)])
def test_a_release_stops_when_the_routes_cannot_be_had(folder, monkeypatch, failure):
    # a public build does not go out quietly without the boats: offline with no cache, or a cache that does not read
    def down(refresh=False):
        raise failure
    monkeypatch.setattr(ferries, "fetch", down)
    with pytest.raises(type(failure)):
        s17_ferries.main(["--version", VERSION, "--release"])
    assert not (folder / "ferries.json").exists()


def test_needs_s04_bases_water(folder, monkeypatch):
    (folder / "water.bin.gz").unlink()
    monkeypatch.setattr(ferries, "fetch", lambda refresh=False: pytest.fail("fetched before checking the base"))
    with pytest.raises(SystemExit, match="run s04_base first"):
        s17_ferries.main(["--version", VERSION])


def test_s99_checks_ferries(folder):
    assert s99_validate.check_ferries(folder) == []                     # a version without the boats
    good = ferries.layer(elements(), *CHANNEL, project)
    (folder / "ferries.json").write_text(json.dumps(good), encoding="utf-8")
    assert s99_validate.check_ferries(folder) == []
    bad = json.loads(json.dumps(good))
    r1, r12, r10 = bad["routes"]
    r1["path"][1] = [0.0, 0.0]                                          # on the bridge, not on water
    r12["kind"], r12["ends"] = "yacht", ["pier"]
    r10["id"], r10["path"] = "r1", [[0.0, 99_000.0], [1.0, 1.0]]
    bad["routes"].append({"id": "relation 5", "name": " ", "ref": None, "kind": "ferry", "ends": ["edge", "edge"],
                          "path": [[500.0, 0.0], [500.0, 0.0]]})
    bad["routes"].append("r6")
    (folder / "ferries.json").write_text(json.dumps(bad), encoding="utf-8")
    errors = s99_validate.check_ferries(folder)
    assert "ferries: route r1 has 1 point(s) off the water" in errors
    assert "ferries: route r12 has kind 'yacht'" in errors
    assert "ferries: route r12 has ends ['pier'], not two of pier and edge" in errors
    assert "ferries: route r1 twice" in errors and "ferries: route r1 has a path outside the map" in errors
    assert "ferries: route #3 has id 'relation 5', not r or w and a number" in errors
    assert "ferries: route #3 has no name or no ref" in errors and "ferries: route #3 has a path of no length" in errors
    assert "ferries: route #4 is not an object" in errors
    assert len(errors) == 9, errors
    names = json.loads(json.dumps(good))
    r1, r12, r10 = names["routes"]
    r1["stops"] = ["Slussen"]
    r12["home"], r12["operator"] = " ", 7
    r10["dests"] = [{"to": "Turku", "via": ["Mariehamn", ""]}]
    (folder / "ferries.json").write_text(json.dumps(names), encoding="utf-8")
    assert s99_validate.check_ferries(folder) == [
        "ferries: route r1 has stops ['Slussen'], not two or more names",
        "ferries: route r12 has home ' ', not a name", "ferries: route r12 has operator 7, not a name",
        "ferries: route r10 has dests [{'to': 'Turku', 'via': ['Mariehamn', '']}], not a list of {to, via} names"]
    r10["dests"] = []
    (folder / "ferries.json").write_text(json.dumps(names), encoding="utf-8")
    assert "ferries: route r10 has dests [], not a list of {to, via} names" in s99_validate.check_ferries(folder)
    (folder / "ferries.json").write_text('{"routes": []}', encoding="utf-8")
    assert s99_validate.check_ferries(folder) == ["ferries: ferries.json needs version 1 and a routes list"]
    (folder / "ferries.json").write_text("{", encoding="utf-8")
    assert s99_validate.check_ferries(folder) == ["ferries: ferries.json is not JSON"]


def test_a_release_needs_the_boats_when_they_are_on(folder):
    # s17_ferries writes no routes when Overpass cannot be reached and nothing is cached; a release with the feature on
    # must not ship that (the viewer would show no boats while About credits them), a preview may
    missing = "ferries: ferries.json is missing while features.ferries is on (run s17_ferries)"
    assert s99_validate.check_ferries(folder, ON, release=True) == [missing]
    assert s99_validate.check_ferries(folder, ON) == s99_validate.check_ferries(folder, OFF, release=True) == []
    (folder / "ferries.json").write_text('{"version": 1, "routes": []}', encoding="utf-8")
    assert s99_validate.check_ferries(folder, ON, release=True) == [
        "ferries: ferries.json has no routes while features.ferries is on (s17_ferries found none, or could not "
        "reach Overpass with nothing cached: run it again)"]
    assert s99_validate.check_ferries(folder, ON) == s99_validate.check_ferries(folder, OFF, release=True) == []


def test_s99_finds_a_segment_off_the_map(tmp_path):
    # every point on the water, but one step across ground off the map, between two waters that touch at a corner
    write_base(tmp_path, CORNER, shapely.union(CORNER, box(0, 500, 500, 1000)))
    across = {"id": "r1", "ref": "", "name": "Cityline", "kind": "ferry", "ends": ["pier", "pier"],
              "path": [[400.0, 300.0], [500.0, 429.2], [569.2, 500.0], [900.0, 700.0]]}
    (tmp_path / "ferries.json").write_text(json.dumps({"version": 1, "routes": [across]}), encoding="utf-8")
    assert s99_validate.check_ferries(tmp_path) == ["ferries: route r1 has 1 segment(s) off the map"]
    across["path"][1:3] = [[500.0, 500.0]]                                # by the corner itself: on the map
    (tmp_path / "ferries.json").write_text(json.dumps({"version": 1, "routes": [across]}), encoding="utf-8")
    assert s99_validate.check_ferries(tmp_path) == []


def test_registered_after_s04_base_with_its_source():
    assert run.STEPS.index("s17_ferries") == run.STEPS.index("s04_base") + 1      # it reads s04_base's water
    sources = load_sources()
    assert check_sources(sources, release=True) == []
    by = {s["id"]: s for s in sources}
    assert by["ferry_routes"]["licence"] == "ODbL-1.0" and by["ferry_routes"]["modified"] is True
    assert by["ferry_routes"]["feature"] == "ferries" and city.FEATURES["ferries"] is True
    assert "ferry_routes" in {a["id"] for a in s03_tiles.attribution(sources)}


def test_a_route_id_is_not_taken_for_a_property_unit_key(tmp_path):
    # OSM relation ids pass through the FNR range (10,057,056-10,547,437): "r10234567" is an identifier of its own,
    # while the same digits anywhere else in the file are still caught
    route = {"id": "r10234567", "ref": "", "name": "Cityline", "kind": "ferry", "ends": ["pier", "pier"],
             "path": [[0.0, 0.0], [1.0, 0.0]]}
    (tmp_path / "ferries.json").write_text(json.dumps({"version": 1, "routes": [route]}), encoding="utf-8")
    assert s99_validate.check_privacy(tmp_path, set(), set(), {10234567}) == []
    route["name"] = "Cityline 10234567"
    (tmp_path / "ferries.json").write_text(json.dumps({"version": 1, "routes": [route]}), encoding="utf-8")
    assert s99_validate.check_privacy(tmp_path, set(), set(), {10234567}) == [
        "privacy: ferries.json $.routes[0].name holds a property-unit key (FNR)"]
