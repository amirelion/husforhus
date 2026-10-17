"""OSM addresses on footprints, and each footprint's stadsdel. No network: Overpass answers are
written here."""
import json

import geopandas as gpd
import pandas as pd
import pytest
import shapely
from pyproj import Transformer

from pipeline import addresses, city, s02_addresses, s03_tiles
from tests import synth

TO_WGS84 = Transformer.from_crs(city.CRS, 4326, always_xy=True)
X0, Y0 = city.ORIGIN                                    # Stortorget: inside GAMLA STAN in the fixture stadsdelar


def at(x, y):
    lon, lat = TO_WGS84.transform(X0 + x, Y0 + y)
    return {"lat": lat, "lon": lon}


def node(i, x, y, street="Hornsgatan", number="30", **tags):
    return {"type": "node", "id": i, **at(x, y), "tags": {"addr:street": street, "addr:housenumber": number, **tags}}


def way(i, x, y, street="Hornsgatan", number="30"):
    return {"type": "way", "id": i, "center": at(x, y), "tags": {"addr:street": street, "addr:housenumber": number}}


def write(folder, name, elements):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps({"elements": elements}), encoding="utf-8")


def buildings(*polys):
    return gpd.GeoDataFrame({"gid": range(len(polys)), "fastighet": ["DIANA 1"] * len(polys)}, geometry=list(polys),
                            crs=city.CRS)


@pytest.mark.parametrize(("raw", "want"), [
    ("30", ["30"]), ("30a", ["30A"]), ("30 A", ["30A"]), ("012", ["12"]), ("12-14", ["12", "14"]),
    ("12–14", ["12", "14"]), ("3;5", ["3", "5"]), ("3, 5", ["3", "5"]), ("3;3", ["3"]), ("1 tr", []),
    ("Gård", []), ("", []), (None, []), ("0", []), ("12B-12C", ["12B", "12C"])])
def test_numbers_reads_numbers_letters_ranges_and_lists(raw, want):
    assert addresses.numbers(raw) == want


def test_number_key_sorts_as_people_count():
    assert sorted(["12", "2", "10B", "10", "10A"], key=addresses.number_key) == ["2", "10", "10A", "10B", "12"]


def test_load_dedupes_across_tiles_and_takes_nodes_ways_and_relations(tmp_path):
    write(tmp_path, "0_0.json", [node(1, 5, 5), way(2, 50, 5, number="12-14"),
                                 {"type": "relation", "id": 3, "center": at(90, 5),
                                  "tags": {"addr:street": "Götgatan", "addr:housenumber": "7"}},
                                 node(4, 0, 0, street=" ", number="9"), {"type": "way", "id": 5, "tags": {}}])
    write(tmp_path, "1_0.json", [node(1, 5, 5)])
    got = addresses.load(tmp_path)
    assert got[["osm", "street", "number"]].values.tolist() == [
        ["node/1", "Hornsgatan", "30"], ["way/2", "Hornsgatan", "12"], ["way/2", "Hornsgatan", "14"],
        ["relation/3", "Götgatan", "7"]]
    assert abs(got.x.iat[0] - (X0 + 5)) < 0.01 and abs(got.y.iat[0] - (Y0 + 5)) < 0.01
    assert addresses.load(tmp_path / "none").empty
    # with `names`, only the current grid's tiles: one left from another grid is never read
    write(tmp_path, "9_9.json", [node(6, 5, 5, street="Götgatan", number="1")])
    assert addresses.load(tmp_path, ["1_0", "0_1"]).osm.tolist() == ["node/1"]


def test_assign_inside_the_smallest_else_nearest_within_ten_metres():
    # synth.square(dx, dz, size) is centred dx east and dz south of the origin
    big, small, far = synth.square(0, 0, 40), synth.square(5, 5, 6), synth.square(200, 0, 10)
    b = buildings(big, small, far).assign(gid=[7, 8, 9])
    pts = pd.DataFrame({"x": [X0 + 6, X0 + 15, X0 + 213, X0 + 225, X0 + 500],
                        "y": [Y0 - 6, Y0 + 15, Y0, Y0, Y0 + 500]})
    assert addresses.assign(pts, b).tolist() == [8, 7, 9, -1, -1]       # 8 m off is in, 20 m off is not
    assert addresses.assign(pts, b, max_m=25).tolist() == [8, 7, 9, 9, -1]
    assert addresses.assign(pts.iloc[:0], b).tolist() == []
    # the smallest wins whatever the gids' order: here it has the lowest gid
    assert addresses.assign(pts.iloc[:1], b.assign(gid=[9, 1, 5])).tolist() == [1]
    assert addresses.assign(pts.iloc[:1], b.assign(gid=[1, 9, 5])).tolist() == [9]


def test_on_footprints_one_row_per_address_sorted():
    b = buildings(synth.square(0, 0, 40))
    pts = pd.DataFrame({"osm": ["n/1", "n/2", "n/3", "n/4"], "street": ["B", "A", "A", "A"],
                        "number": ["1", "10", "2", "2"], "x": [X0 + 5, X0 + 6, X0 + 7, X0 + 8],
                        "y": [Y0 + 5, Y0 + 6, Y0 + 7, Y0 + 8]})
    got = addresses.on_footprints(pts, b)
    assert got.values.tolist() == [[0, "A", "2"], [0, "A", "10"], [0, "B", "1"]]
    assert str(got.gid.dtype) == "int32"


def test_main_writes_addresses_and_districts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    monkeypatch.setattr(city, "OSM_TILES", (1, 1))                 # one tile, 0_0, is the whole grid here
    buildings(synth.square(0, 0, 20), synth.square(100, 0, 20)).to_parquet("buildings.parquet")
    write(tmp_path / "tiles", "0_0.json", [node(1, 3, 3), node(2, 103, 3, street="Götgatan", number="7"),
                                           node(3, 400, 3, number="1")])
    write(tmp_path / "tiles", "3_3.json", [node(9, 3, 3, street="Götgatan", number="99")])   # another grid's
    sd = gpd.GeoDataFrame({"NAMN": ["GAMLA STAN", "SÖDERMALM"], "KATEGORI": ["Stadsdel"] * 2},
                          geometry=[shapely.box(X0 - 60, Y0 - 60, X0 + 50, Y0 + 60),
                                    shapely.box(X0 + 50, Y0 - 60, X0 + 200, Y0 + 60)], crs=city.CRS)
    sd.to_file(tmp_path / "Stadsdel.shp")
    s02_addresses.main(["--buildings", "buildings.parquet", "--tiles", "tiles", "--stadsdelar", "Stadsdel.shp",
                        "--out", "addresses.parquet", "--districts", "districts.parquet"])
    got = pd.read_parquet("addresses.parquet")
    assert got.values.tolist() == [[0, "Hornsgatan", "30", False], [1, "Götgatan", "7", False]]
    assert pd.read_parquet("districts.parquet").values.tolist() == [[0, "GAMLA STAN"], [1, "SÖDERMALM"]]
    assert ("3 house numbers, 2 on footprints; 2 of 2 footprints (100.0%) have one; 2 streets; 0 left out as property "
            "designations") in capsys.readouterr().out


def test_an_address_that_reads_as_a_property_designation_is_left_out():
    # "Skansbacken 1" is a street address and a kvarter's property; "Långa Raden 2" holds the designation "Raden 2"
    on = pd.DataFrame({"gid": [0, 1, 2, 3], "street": ["Skansbacken", "Långa Raden", "Hornsgatan", "Kv. Diana"],
                       "number": ["1", "2", "30", "4"]})
    kept, dropped = addresses.without_designations(on, ["SKANSBACKEN 1", "RADEN 2", "DIANA 4", None, " "])
    assert kept.values.tolist() == [[2, "Hornsgatan", "30"]] and dropped == 3


def test_main_stops_without_tiles(tmp_path):
    with pytest.raises(SystemExit, match="run s00_fetch_osm first"):
        s02_addresses.main(["--tiles", str(tmp_path)])


def test_main_stops_when_a_tile_is_missing(tmp_path, monkeypatch):
    # one tile is not the city: a run with some missing would quietly lose the addresses there
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    write(tmp_path, "0_0.json", [])
    with pytest.raises(SystemExit, match=r"lacks 15 of 16 tiles \(0_1, .*\): run s00_fetch_osm first"):
        s02_addresses.main(["--tiles", str(tmp_path)])


def test_main_leaves_out_a_takedown_s_addresses(tmp_path, monkeypatch, capsys):
    # The takedown list (here its own file) removes a building's addresses; its stadsdel stays
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    monkeypatch.setattr(city, "OSM_TILES", (1, 1))                 # one tile, 0_0, is the whole grid here
    b = buildings(synth.square(0, 0, 20), synth.square(100, 0, 20)).assign(uuid=["u-0", "u-1"])
    b.to_parquet("buildings.parquet")
    write(tmp_path / "tiles", "0_0.json", [node(1, 3, 3), node(2, 103, 3, street="Götgatan", number="7")])
    sd = gpd.GeoDataFrame({"NAMN": ["SÖDERMALM"], "KATEGORI": ["Stadsdel"]},
                          geometry=[shapely.box(X0 - 60, Y0 - 60, X0 + 200, Y0 + 60)], crs=city.CRS)
    sd.to_file(tmp_path / "Stadsdel.shp")
    (tmp_path / "suppress.yml").write_text("- uuid: U-1\n  date: 2026-11-02\n")
    s02_addresses.main(["--buildings", "buildings.parquet", "--tiles", "tiles", "--stadsdelar", "Stadsdel.shp",
                        "--out", "addresses.parquet", "--districts", "districts.parquet",
                        "--suppress", "suppress.yml"])
    assert s03_tiles.load_places(tmp_path)["addresses"].gid.tolist() == [0]
    assert pd.read_parquet("districts.parquet").district.tolist() == ["SÖDERMALM", "SÖDERMALM"]


def test_a_takedown_s_address_goes_from_every_footprint_it_landed_on(tmp_path, monkeypatch):
    # final review F1: the house's own node lies in it, a second element with the same address (an entrance node
    # beside the house) lies nearest its garage; both go, and so does the same address written in another case
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    monkeypatch.setattr(city, "OSM_TILES", (1, 1))
    b = buildings(synth.square(0, 0, 20), synth.square(20, 0, 6), synth.square(100, 0, 20), synth.square(140, 0, 20))
    b.assign(uuid=["u-house", "u-garage", "u-2", "u-3"]).to_parquet("buildings.parquet")
    write(tmp_path / "tiles", "0_0.json", [node(1, 3, 3, street="Ekvägen", number="4"),
                                           node(2, 14, 0, street="Ekvägen", number="4", entrance="main"),
                                           node(3, 103, 3, street="Götgatan", number="7"),
                                           node(4, 143, 3, street="EKVÄGEN", number="4")])
    sd = gpd.GeoDataFrame({"NAMN": ["SÖDERMALM"], "KATEGORI": ["Stadsdel"]},
                          geometry=[shapely.box(X0 - 60, Y0 - 60, X0 + 200, Y0 + 60)], crs=city.CRS)
    sd.to_file(tmp_path / "Stadsdel.shp")
    (tmp_path / "suppress.yml").write_text("- uuid: u-house\n  date: 2026-11-02\n")
    s02_addresses.main(["--buildings", "buildings.parquet", "--tiles", "tiles", "--stadsdelar", "Stadsdel.shp",
                        "--out", "addresses.parquet", "--districts", "districts.parquet",
                        "--suppress", "suppress.yml"])
    got = pd.read_parquet("addresses.parquet")
    assert got[["gid", "withheld"]].values.tolist() == [[0, True], [1, True], [2, False], [3, True]]
    assert s03_tiles.load_places(tmp_path)["addresses"].values.tolist() == [[2, "Götgatan", "7"]]


def test_sharing_matches_street_and_number_in_any_case():
    on = pd.DataFrame({"gid": [0, 1, 2, 3], "street": ["Ekvägen", "ekvägen", "Ekvägen", "Ekvagen"],
                       "number": ["4a", "4A", "6", "4A"]})
    assert addresses.sharing(on, {0}).tolist() == [True, True, False, False]   # diacritics are another street
    assert addresses.sharing(on, set()).tolist() == [False] * 4


def test_a_takedown_without_an_address_of_its_own_still_takes_the_one_beside_it(tmp_path, monkeypatch):
    # fix-wave review: the villa's only address node lies outside it, nearest its garage; it is the villa's all the
    # same (within addr_max_m of it), so it goes from the garage too
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    monkeypatch.setattr(city, "OSM_TILES", (1, 1))
    b = buildings(synth.square(0, 0, 20), synth.square(20, 0, 6), synth.square(100, 0, 20))
    b.assign(uuid=["u-house", "u-garage", "u-2"]).to_parquet("buildings.parquet")
    write(tmp_path / "tiles", "0_0.json", [node(1, 14, 0, street="Ekvägen", number="4"),
                                           node(2, 103, 3, street="Götgatan", number="7")])
    sd = gpd.GeoDataFrame({"NAMN": ["SÖDERMALM"], "KATEGORI": ["Stadsdel"]},
                          geometry=[shapely.box(X0 - 60, Y0 - 60, X0 + 200, Y0 + 60)], crs=city.CRS)
    sd.to_file(tmp_path / "Stadsdel.shp")
    (tmp_path / "suppress.yml").write_text("- uuid: u-house\n  date: 2026-11-02\n")
    s02_addresses.main(["--buildings", "buildings.parquet", "--tiles", "tiles", "--stadsdelar", "Stadsdel.shp",
                        "--out", "addresses.parquet", "--districts", "districts.parquet",
                        "--suppress", "suppress.yml"])
    assert pd.read_parquet("addresses.parquet")[["gid", "withheld"]].values.tolist() == [[1, True], [2, False]]
