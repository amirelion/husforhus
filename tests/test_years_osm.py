"""OpenStreetMap start_date as a year source (Plan 2, Task 4): the date formats, the loader and the placement."""
import json
from pathlib import Path

import pytest
from pyproj import Transformer

from pipeline import city
from pipeline import years_osm as osm
from tests import synth

TO_WGS84 = Transformer.from_crs(3011, 4326, always_xy=True)


@pytest.mark.parametrize(("tag", "expected"), [
    ("1916", (1916, 1916)), (" 1916 ", (1916, 1916)), ("1906-06-10", (1906, 1906)), ("2009-04", (2009, 2009)),
    ("1940s", (1940, 1949)), ("1630s", (1630, 1639)), ("1865 - 1878", (1865, 1878)), ("2017-2019", (2017, 2019)),
    ("1660 - 1669", (1660, 1669)), ("1878 - 1865", (1865, 1878)), ("~1920", (1915, 1925)), ("~ 2019", (2014, 2024)),
    ("1700s", None), ("1100s", None), ("early 1700s", None), ("after 1908", None), ("before 1914", None),
    ("1635 / 1854", None), ("C19", None), ("", None), (None, None), ("0999", None), ("2027", None), ("~2025", None),
])
def test_parse_date(tag, expected):
    assert osm.parse_date(tag) == expected


def element(kind, oid, dx, dz, tags):
    lon, lat = TO_WGS84.transform(city.ORIGIN[0] + dx, city.ORIGIN[1] - dz)
    return {"type": kind, "id": oid, "center": {"lat": lat, "lon": lon}, "tags": tags}


def write(tmp_path: Path, elements):
    path = tmp_path / "dated.json"
    path.write_text(json.dumps({"version": 0.6, "elements": elements}), encoding="utf-8")
    return path


def test_load_keeps_dated_buildings_only(tmp_path):
    path = write(tmp_path, [
        element("way", 1, 0, 0, {"building": "yes", "start_date": "1916", "name": "PUB"}),
        element("way", 2, 20, 0, {"building": "yes", "year_of_construction": "1950s"}),
        element("relation", 3, 40, 0, {"building": "yes", "start_date": "early 1700s"}),      # no usable year
        element("way", 4, 60, 0, {"building:part": "yes", "start_date": "1930"}),             # a part, not a building
        {"type": "way", "id": 5, "tags": {"building": "yes", "start_date": "1930"}},         # no centre
        element("node", 6, 80, 0, {"building": "yes", "construction_date": "2010-05-01"}),
        element("way", 7, 100, 0, {"building": "yes", "start_date": "~1920"}),                # circa: the stated year
        element("way", 8, 120, 0, {"building": "yes", "start_date": "1865 - 1878"}),          # a span: the display rule
    ])
    got = osm.load(path)
    assert list(got.columns) == ["osm_id", "name", "x", "y", "year", "year_from", "year_to"]
    assert got.osm_id.tolist() == ["way/1", "way/2", "node/6", "way/7", "way/8"]
    assert got.name.tolist() == ["PUB", "", "", "", ""]
    assert got.year_from.tolist() == [1916, 1950, 2010, 1915, 1865] and got.year_to.tolist() == [1916, 1959, 2010, 1925, 1878]
    # D6, shown honestly: a decade publishes its start (the card prints "1950s"), "~1920" the year the mapper wrote,
    # a real span the completion year (13 years: RAÄ's rule), never the end of a decade or of a circa range
    assert got.year.tolist() == [1916, 1950, 2010, 1920, 1878]
    assert abs(got.x[0] - city.ORIGIN[0]) < 0.01 and abs(got.y[0] - city.ORIGIN[1]) < 0.01


def test_match_places_centres_within_15_m_one_to_one(tmp_path):
    b = synth.buildings(rows=[{"geometry": synth.square(0, 0)}, {"geometry": synth.square(100, 0)},
                              {"geometry": synth.square(200, 0)}, {"geometry": synth.square(300, 0)}])
    path = write(tmp_path, [
        element("way", 1, 0, 0, {"building": "yes", "start_date": "1916"}),             # inside
        element("way", 2, 100 + 15, 0, {"building": "yes", "start_date": "1920"}),      # 10 m from the wall
        element("way", 3, 200 + 25, 0, {"building": "yes", "start_date": "1930"}),      # 20 m: too far
        element("way", 4, 300, 0, {"building": "yes", "start_date": "1940"}),           # two buildings, two dates
        element("way", 5, 300 + 2, 0, {"building": "yes", "start_date": "1950"}),
        element("way", 6, 0 + 2, 0, {"building": "yes", "start_date": "1916"}),         # the same date twice is fine
    ])
    m = osm.match(b, osm.load(path))
    assert m.index.tolist() == [0, 1]
    assert list(m.columns) == ["year", "year_from", "year_to", "osm_id", "name"]
    assert m.year.tolist() == [1916, 1920] and m.year_from.tolist() == [1916, 1920] and m.osm_id.tolist() == ["way/1", "way/2"]
    assert osm.match(b, osm.load(path).iloc[:0]).empty
