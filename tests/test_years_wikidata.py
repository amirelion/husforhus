"""Wikidata as a year source: the class rules, the year rule and the one-to-one placement, on
hand-written SPARQL results."""
import json
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import Polygon

from pipeline import years_wikidata as wd
from tests import synth

WD = "http://www.wikidata.org/entity/"
TO_WGS84 = Transformer.from_crs(3011, 4326, always_xy=True)
# A small class graph: building Q41176; church Q16970 and palace Q16560 under it; movie theater Q41253 under both
# building and business Q4830453 -> organization Q43229; fountain Q483453 -> work of art Q838948; metro station
# Q928830 -> structure Q811979; a museum building class Q24699794 under building and museum Q33506.
EDGES = [("Q16970", "Q41176"), ("Q16560", "Q41176"), ("Q41253", "Q41176"), ("Q41253", "Q4830453"),
         ("Q4830453", "Q43229"), ("Q483453", "Q838948"), ("Q928830", "Q811979"), ("Q41176", "Q811979"),
         ("Q24699794", "Q41176"), ("Q24699794", "Q33506")]


def lonlat(dx, dz):
    """WGS84 of a local (dx east, dz south) point, like synth.square's centre."""
    from pipeline import city
    return TO_WGS84.transform(city.ORIGIN[0] + dx, city.ORIGIN[1] - dz)


def binding(item, cls, prop, time, precision, dx=0.0, dz=0.0, part=None, circa=None, ended=False, sv=None, en=None,
            svwiki=None, enwiki=None):
    lon, lat = lonlat(dx, dz)
    b = {"item": {"type": "uri", "value": WD + item}, "coord": {"type": "literal", "value": f"Point({lon} {lat})"},
         "prop": {"type": "literal", "value": prop}, "time": {"type": "literal", "value": time},
         "precision": {"type": "literal", "value": str(precision)},
         "calendar": {"type": "uri", "value": WD + "Q1985727"},
         "ended": {"type": "literal", "value": "true" if ended else "false"}}
    if cls:
        b["cls"] = {"type": "uri", "value": WD + cls}
    if part:
        b["part"] = {"type": "uri", "value": WD + part}
    if circa:
        b["circa"] = {"type": "uri", "value": WD + circa}
    for k, v in (("sv", sv), ("en", en)):
        if v:
            b[k] = {"type": "literal", "xml:lang": k, "value": v}
    for k, v in (("svwiki", svwiki), ("enwiki", enwiki)):
        if v:
            b[k] = {"type": "uri", "value": v}
    return b


def write(tmp_path: Path, bindings, edges=EDGES):
    dated = tmp_path / "dated.json"
    dated.write_text(json.dumps({"head": {"vars": ["item"]}, "results": {"bindings": bindings}}), encoding="utf-8")
    classes = tmp_path / "classes.json"
    classes.write_text(json.dumps({"head": {"vars": ["a", "b"]}, "results": {"bindings": [
        {"a": {"type": "uri", "value": WD + a}, "b": {"type": "uri", "value": WD + b}} for a, b in edges]}}), encoding="utf-8")
    return dated, classes


def test_class_rules_keep_buildings_and_drop_organisations_artworks_and_structures(tmp_path):
    dated, classes = write(tmp_path, [
        binding("Q1", "Q16970", "P571", "1306-01-01T00:00:00Z", 9, sv="Storkyrkan"),
        binding("Q2", "Q41253", "P571", "1950-01-01T00:00:00Z", 9, sv="Bion"),            # a cinema: organisation
        binding("Q3", "Q483453", "P571", "1920-01-01T00:00:00Z", 9),                        # a fountain: work of art
        binding("Q4", "Q928830", "P1619", "1950-01-01T00:00:00Z", 9),                       # a metro station
        binding("Q5", "Q16560", "P571", "1650-01-01T00:00:00Z", 9, ended=True),            # a demolished palace
        binding("Q6", "Q24699794", "P571", "1792-01-01T00:00:00Z", 9),                      # a museum class
        binding("Q7", "Q41176", "P571", "1900-01-01T00:00:00Z", 9, svwiki="https://sv.wikipedia.org/wiki/X"),
    ])
    items = wd.load(dated, classes).set_index("qid")
    assert items.dropped.to_dict() == {"Q1": "", "Q2": "organization", "Q3": "work of art", "Q4": "not a building",
                                       "Q5": "demolished or dissolved (P576)", "Q6": "museum", "Q7": ""}
    assert items.name["Q1"] == "Storkyrkan" and items.name["Q3"] == "Q3"
    assert items.article.to_dict() == {q: q == "Q7" for q in items.index}
    assert (items.year_from["Q1"], items.year_to["Q1"], items.precision["Q1"]) == (1306, 1306, 9)


def test_year_rule_precision_values_parts_and_circa(tmp_path):
    dated, classes = write(tmp_path, [
        binding("Q1", "Q41176", "P571", "1640-01-01T00:00:00Z", 8),                                  # a decade
        binding("Q2", "Q41176", "P571", "1300-01-01T00:00:00Z", 7),                                  # a century
        binding("Q3", "Q41176", "P571", "1571-01-01T00:00:00Z", 9),                                  # two values
        binding("Q3", "Q41176", "P571", "1642-01-01T00:00:00Z", 9),
        binding("Q4", "Q41176", "P571", "1986-01-01T00:00:00Z", 9),                                  # P571 beats P1619
        binding("Q4", "Q41176", "P1619", "1989-02-19T00:00:00Z", 11),
        binding("Q5", "Q41176", "P1619", "1990-06-15T00:00:00Z", 11),                                # P1619 alone
        binding("Q6", "Q41176", "P571", "1700-01-01T00:00:00Z", 9, part="Q99"),                     # the part is skipped
        binding("Q6", "Q41176", "P571", "1750-01-01T00:00:00Z", 9),
        binding("Q7", "Q41176", "P571", "1700-01-01T00:00:00Z", 9, part="Q99"),                     # a part alone counts
        binding("Q8", "Q41176", "P571", "1920-01-01T00:00:00Z", 9, circa="Q5727902"),
        binding("Q9", "Q41176", "P571", "0850-01-01T00:00:00Z", 9),                                  # before 1000
        binding("Q10", "Q41176", "P571", "2030-01-01T00:00:00Z", 9),                                 # after 2026
        binding("Q11", "Q41176", "P571", "-0500-01-01T00:00:00Z", 9),                                # BCE
        binding("Q12", "Q41176", "P571", "1640-01-01T00:00:00Z", 8),                                 # decade and a fine value
        binding("Q12", "Q41176", "P571", "1648-01-01T00:00:00Z", 9),
    ])
    it = wd.load(dated, classes).set_index("qid")
    got = {q: (int(r.year_from), int(r.year_to), r.dropped) for q, r in it.iterrows()}
    assert got == {
        "Q1": (1640, 1649, ""), "Q2": (0, 0, "century"), "Q3": (1571, 1642, ""), "Q4": (1986, 1986, ""),
        "Q5": (1990, 1990, ""), "Q6": (1750, 1750, ""), "Q7": (1700, 1700, ""), "Q8": (1915, 1925, ""),
        "Q9": (0, 0, "out of range"), "Q10": (0, 0, "out of range"), "Q11": (0, 0, "out of range"),
        "Q12": (1648, 1648, ""),
    }
    # the published year: a decade its start, a circa the stated year, two distinct values the display rule
    # (71 years apart: the earliest, LONG), a single value itself
    assert {q: int(it.year[q]) for q in ("Q1", "Q3", "Q4", "Q8", "Q12")} == {"Q1": 1640, "Q3": 1571, "Q4": 1986, "Q8": 1920, "Q12": 1648}


def test_match_places_items_inside_in_a_courtyard_or_nearby_and_one_to_one(tmp_path):
    court = Polygon(synth.square(0, 0, size=60).exterior.coords, [synth.square(0, 0, size=40).exterior.coords])
    b = synth.buildings(rows=[{"geometry": court}, {"geometry": synth.square(200, 0)}, {"geometry": synth.square(400, 0)},
                              {"geometry": synth.square(600, 0)}, {"geometry": synth.square(800, 0)}])
    dated, classes = write(tmp_path, [
        binding("Q1", "Q16560", "P571", "1754-01-01T00:00:00Z", 9, dx=0, dz=0),          # the courtyard point
        binding("Q2", "Q41176", "P571", "1900-01-01T00:00:00Z", 9, dx=200, dz=0),        # inside
        binding("Q3", "Q41176", "P571", "1910-01-01T00:00:00Z", 9, dx=400 + 25, dz=0),   # 20 m east of the wall
        binding("Q4", "Q41176", "P571", "1920-01-01T00:00:00Z", 9, dx=600 + 45, dz=0),   # 40 m: too far
        binding("Q5", "Q41176", "P571", "1520-01-01T00:00:00Z", 9, dx=800, dz=0),        # two items on one footprint
        binding("Q6", "Q41176", "P571", "1650-01-01T00:00:00Z", 9, dx=800 + 2, dz=0),
        binding("Q7", "Q483453", "P571", "1930-01-01T00:00:00Z", 9, dx=200 + 2, dz=0),   # a fountain next to Q2's building
    ])
    m = wd.match(b, wd.load(dated, classes))
    assert m.index.tolist() == [0, 1, 2]
    assert m.year_from.tolist() == [1754, 1900, 1910] and m.qid.tolist() == ["Q1", "Q2", "Q3"]
    assert list(m.columns) == ["year", "year_from", "year_to", "qid", "name", "article", "placement"]
    assert m.placement.tolist() == ["courtyard", "inside", "nearest"]


def test_an_item_between_two_footprints_goes_to_the_nearest_then_the_lowest_gid(tmp_path):
    # Review Focus #7: the reverse of two items on one footprint. Footprints A (gid 0) and B (gid 1) are 10 m squares
    # 32 m apart edge to edge; Q1 is 10 m from A's wall and 22 m from B's; Q2 is exactly equidistant (16 m) from
    # footprints C (gid 2) and D (gid 3). Both are "nearest" placements, so the review list says so.
    b = synth.buildings(rows=[{"geometry": synth.square(0, 0)}, {"geometry": synth.square(42, 0)},
                              {"geometry": synth.square(200, 0)}, {"geometry": synth.square(242, 0)}])
    dated, classes = write(tmp_path, [
        binding("Q1", "Q41176", "P571", "1900-01-01T00:00:00Z", 9, dx=15, dz=0),         # 10 m from A, 22 m from B
        binding("Q2", "Q41176", "P571", "1950-01-01T00:00:00Z", 9, dx=221, dz=0),        # 16 m from C and from D
    ])
    m = wd.match(b, wd.load(dated, classes))
    assert m.index.tolist() == [0, 2] and m.qid.tolist() == ["Q1", "Q2"]
    assert m.placement.tolist() == ["nearest", "nearest"]
    assert wd.match(b, wd.load(dated, classes)).equals(m)                               # deterministic


def test_an_empty_result_matches_nothing(tmp_path):
    dated, classes = write(tmp_path, [], edges=[])
    items = wd.load(dated, classes)
    assert items.empty
    assert wd.match(synth.buildings(1), items).empty


@pytest.mark.parametrize(("time", "year"), [("1739-06-02T00:00:00Z", 1739), ("+1739-06-02T00:00:00Z", 1739),
                                            ("-0500-01-01T00:00:00Z", -500), ("12345-01-01T00:00:00Z", 12345)])
def test_year_of_time(time, year):
    assert wd.year_of_time(time) == year
