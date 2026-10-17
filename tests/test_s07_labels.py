import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Point, box

from pipeline import city, s07_labels

E0, N0 = city.ORIGIN


def kurvad(rows):
    """rows: (name, LineString); GRUPP Gatunamn."""
    return gpd.GeoDataFrame({"GRUPP": ["Gatunamn"] * len(rows), "KOMPONENT": ["tSGata"] * len(rows),
                             "NAMN": [r[0] for r in rows]}, geometry=[r[1] for r in rows], crs=city.CRS)


def namn(rows):
    """rows: (grupp, name, text, E, N, TEXT_ANGLE, TEXT_SIZE, TEXTJUST)."""
    return gpd.GeoDataFrame({
        "GRUPP": [r[0] for r in rows], "NAMN": [r[1] for r in rows], "TEXT": [r[2] for r in rows],
        "TEXT_ANGLE": [r[5] for r in rows], "TEXT_SIZE": [r[6] for r in rows], "TEXTJUST": [r[7] for r in rows],
    }, geometry=[Point(r[3], r[4]) for r in rows], crs=city.CRS)


def test_tier1_list_is_final():
    assert len(city.TIER1) == len(set(city.TIER1)) == 37
    assert {"Riddarfjärden", "Strömmen", "Saltsjön", "Strandvägen", "Västerlånggatan"} <= set(city.TIER1)
    assert city.SALTSJON == (2050.0, 600.0, 0.0)  # open water off Fåfängan, 237 m from any shore or boundary


def test_angles_follow_the_viewer_convention():
    # map angles: counter-clockwise from east, north up; local: from +x towards +z (south), upright
    assert s07_labels.map_angle_to_local(0.0) == 0.0
    assert s07_labels.map_angle_to_local(180.0) == 0.0
    assert s07_labels.map_angle_to_local(-30.0) == 30.0       # ESE on the map runs towards +z
    assert s07_labels.map_angle_to_local(30.0) == -30.0
    assert s07_labels.map_angle_to_local(90.0) == -90.0       # north-south text stays upright
    assert s07_labels.map_angle_to_local(-90.0) == -90.0


def test_east_west_street_gets_angle_zero_either_way():
    for coords in ([(E0, N0), (E0 + 150, N0)], [(E0 + 150, N0), (E0, N0)]):
        e, n, ang, length = s07_labels.line_placement(LineString(coords), 10.0)
        assert ang == 0.0 and length == pytest.approx(150.0)
        assert e == pytest.approx(E0 + 75)
    e, n, ang, length = s07_labels.line_placement(LineString([(E0, N0), (E0 + 150, N0)]), 10.0)
    assert n == pytest.approx(N0 + 10.0 * s07_labels.BASELINE_UP)  # lifted off the baseline, to the north


def test_point_anchor_moves_to_the_text_centre():
    # left-bottom justified (2), horizontal, size 10, 5 characters
    e, n, _, length = s07_labels.point_placement(E0, N0, 0.0, 10.0, "Abcde", 2)
    assert length == pytest.approx(s07_labels.K_TEXT * 10 * 5)
    assert e == pytest.approx(E0 + length / 2) and n == pytest.approx(N0 + 10 * s07_labels.BASELINE_UP)
    # centre-centre (7) stays put; right-top (12) moves left and down
    assert s07_labels.point_placement(E0, N0, 0.0, 10.0, "Abcde", 7)[:2] == (E0, N0)
    e, n, *_ = s07_labels.point_placement(E0, N0, 0.0, 10.0, "Abcde", 12)
    assert e == pytest.approx(E0 - length / 2) and n == pytest.approx(N0 - 5.0)


def test_width_from_the_road_polygon_under_the_label():
    road = box(E0, N0, E0 + 100, N0 + 20)
    w = s07_labels.road_width(np.array([E0 + 50, E0 + 500]), np.array([N0 + 10, N0]), [road])
    assert w[0] == pytest.approx(2 * 2000 / 240) and np.isnan(w[1])


def test_merge_keeps_placements_350m_apart_longest_first():
    cands = [
        {"name": "Gata", "water": False, "e": E0, "n": N0, "ang": 0.0, "len": 100.0, "width": 10.0},
        {"name": "Gata", "water": False, "e": E0 + 200, "n": N0, "ang": 0.0, "len": 150.0, "width": 10.0},
        {"name": "Gata", "water": False, "e": E0 + 600, "n": N0, "ang": 0.0, "len": 120.0, "width": np.nan},
        {"name": "Viken", "water": True, "e": E0, "n": N0 - 900, "ang": 0.0, "len": 300.0, "width": np.nan},
        {"name": "Viken", "water": False, "e": E0, "n": N0 - 2000, "ang": 0.0, "len": 90.0, "width": 8.0},
    ]
    labels = s07_labels.merge(cands, tier1=["Viken"])
    assert labels == [
        {"name": "Gata", "water": False, "tier": 2,
         "pts": [[200.0, 0.0, 0.0, 150, 10.0], [600.0, 0.0, 0.0, 120, 12.0]]},
        {"name": "Viken", "water": True, "tier": 1,
         "pts": [[0.0, 900.0, 0.0, 300, 80.0], [0.0, 2000.0, 0.0, 90, 8.0]]},
    ]


def test_tier1_must_resolve_and_saltsjon_is_hand_placed():
    k = kurvad([("Storgatan", LineString([(E0, N0), (E0 + 150, N0)]))])
    p = namn([("Sjö", "Riddarfjärden", "Riddarfjärden", E0 - 1700, N0 - 60, 0.0, 23.0, 7),
              ("Kvarter", "Diana", "DIANA", E0, N0, 0.0, 8.0, 7)])
    labels = s07_labels.build(k, p, [], None, ["Storgatan", "Riddarfjärden", "Saltsjön"])
    by = {lab["name"]: lab for lab in labels}
    assert set(by) == {"Storgatan", "Riddarfjärden", "Saltsjön"}  # GRUPP Kvarter is not a label source
    x, z, ang = city.SALTSJON
    assert by["Saltsjön"]["water"] and by["Saltsjön"]["tier"] == 1
    assert by["Saltsjön"]["pts"][0][:3] == [x, z, ang]
    assert by["Riddarfjärden"]["water"] and by["Riddarfjärden"]["pts"][0][4] == 80.0
    assert by["Storgatan"]["pts"][0][4] == s07_labels.WIDTH[1]
    for lab in labels:
        assert set(lab) == {"name", "water", "tier", "pts"}
        assert all(len(pt) == 5 for pt in lab["pts"])
    with pytest.raises(SystemExit, match="Ingenstansgatan"):
        s07_labels.build(k, p, [], None, ["Storgatan", "Ingenstansgatan"])


def test_labels_outside_the_municipality_are_dropped():
    k = kurvad([("Inne", LineString([(E0, N0), (E0 + 150, N0)])),
                ("Ute", LineString([(E0 + 5000, N0), (E0 + 5150, N0)]))])
    area = box(E0 - 1000, N0 - 1000, E0 + 1000, N0 + 1000)
    names = {c["name"] for c in s07_labels.placements(k, namn([]), [], area)}
    assert names == {"Inne"}


def test_main_writes_labels_json(tmp_path, monkeypatch):
    raw = tmp_path / "data" / "raw" / "city"
    (raw / "stadskarta").mkdir(parents=True)
    (raw / "stadsdelar").mkdir(parents=True)
    gpd.GeoDataFrame({"NAMN": ["GAMLA STAN"]}, geometry=[box(E0 - 3000, N0 - 3000, E0 + 3000, N0 + 3000)],
                     crs=city.CRS).to_file(raw / "stadsdelar" / "Stadsdel.shp")
    kurvad([("Västerlånggatan", LineString([(E0, N0), (E0 + 40, N0 - 150)]))]).to_file(
        raw / "stadskarta" / "TextKurvad_line.shp")
    namn([("Gatunamn", "Hornsgatan", "Hornsgatan", E0 - 900, N0 - 800, 13.8, 11.0, 2)]).to_file(
        raw / "stadskarta" / "NamnText_point.shp")
    gpd.GeoDataFrame({"GRUPP": ["Vägutbredning"]}, geometry=[box(E0 - 950, N0 - 830, E0 - 750, N0 - 760)],
                     crs=city.CRS).to_file(raw / "stadskarta" / "Vaegutbredning_area.shp")
    monkeypatch.setattr(city, "TIER1", ["Västerlånggatan", "Hornsgatan", "Saltsjön"])
    monkeypatch.chdir(tmp_path)
    (tmp_path / "web" / "data").mkdir(parents=True)
    (tmp_path / "web" / "data" / "current.json").write_text('{"version":"v20990101"}')
    s07_labels.main([])
    labels = json.loads((tmp_path / "web" / "data" / "v20990101" / "labels.json").read_text())
    assert [lab["name"] for lab in labels] == ["Hornsgatan", "Saltsjön", "Västerlånggatan"]
    assert labels[0]["pts"][0][2] == -13.8 and labels[0]["pts"][0][4] == pytest.approx(2 * 14000 / 540, abs=0.1)


REAL = Path("data/raw/city/stadskarta/NamnText_point.shp")


@pytest.mark.skipif(not REAL.exists(), reason="needs s00_fetch_city output in data/raw/city")
def test_every_real_tier1_name_resolves():
    roads = shapely.make_valid(s07_labels.read("Vaegutbredning_area").geometry.values)
    labels = s07_labels.build(s07_labels.read("TextKurvad_line"), s07_labels.read("NamnText_point"),
                              roads, s07_labels.boundary(), city.TIER1)
    by = {lab["name"]: lab for lab in labels}
    assert all(by[name]["pts"] and by[name]["tier"] == 1 for name in city.TIER1)
    assert by["Saltsjön"]["water"] and by["Riddarfjärden"]["water"] and not by["Hornsgatan"]["water"]
    assert len(labels) > 4000
