"""Year rules (Task 10). Synthetic footprints near Stortorget in EPSG:3011; one test on the real city."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pytest
from pandas.testing import assert_frame_equal
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, box

from pipeline import city, s02_years
from pipeline.codes import (
    AREA,
    ESTIMATE,
    EXACT,
    LONG,
    PERIOD,
    RANGE,
    SRC_CURATED,
    SRC_NONE,
    SRC_RAA,
    SRC_RAA_AREA,
    UNKNOWN,
)
from pipeline.landmarks import LANDMARKS
from tests.realdata import ensure_city_data

X0, Y0 = 154000.0, 6579000.0
TO_WGS84 = Transformer.from_crs(3011, 4326, always_xy=True)


@pytest.fixture(autouse=True)
def pinned_private_house_set(request, monkeypatch):
    """Rule tests pin the D18 set, so they hold whatever Task 9 finalises; the real-data test uses city.py's."""
    if request.node.get_closest_marker("network") is None:
        monkeypatch.setattr(city, "PRIVATE_HOUSE_KATEGORI", {"Enbostadshus", "Kolonistuga"})


def sq(i, size=10.0, dx=0.0, dy=0.0):
    """A size×size square in slot i (slots are 100 m apart)."""
    x, y = X0 + 100.0 * i + dx, Y0 + dy
    return box(x, y, x + size, y + size)


def buildings(*rows):
    """rows: (uuid, kategori, geometry); gid = row order."""
    return gpd.GeoDataFrame(
        {"gid": np.arange(len(rows), dtype="int32"), "uuid": [r[0] for r in rows], "kategori": [r[1] for r in rows]},
        geometry=[r[2] for r in rows], crs=3011)


def rec(raa_id, geom, yfrom, ytom, regid=None, typ="Byggnad", grp="Bostäder"):
    return {"url": s02_years.RAA_URL + raa_id, "registerbyggnad_id": regid, "objekttyp_namn": typ,
            "nybyggnad_tillkomstar_from": yfrom, "nybyggnad_tillkomstar_tom": ytom, "andamal_huvudgrupp": grp,
            "namn": None, "alternativnamn": None, "klassificering": None, "upphov": None,
            "kommunnamn": "Stockholm", "geometry": geom}


def raa(*recs):
    df = gpd.GeoDataFrame(list(recs), geometry="geometry", crs=3011)
    df["raa_id"] = df.url.map(s02_years.raa_id_from_url)
    return df


def no_raa():
    """A RAÄ frame whose only record is far from every test footprint."""
    return raa(rec("nothing", box(X0 + 5000, Y0, X0 + 5010, Y0 + 10), 1900, 1900))


def run(b, r, landmarks=()):
    years, report = s02_years.assign_years(b, r, list(landmarks))
    return years.set_index("gid"), report


def landmark_at(x, y, name="Test", year=1754, year_from=1697, year_to=1754):
    lon, lat = TO_WGS84.transform(x, y)
    return {"name": name, "qid": "Q1", "lat": lat, "lon": lon, "year": year, "year_from": year_from,
            "year_to": year_to, "source": "sv:Test", "checks": ()}


def test_raa_id_comes_from_the_public_url():
    assert s02_years.raa_id_from_url(s02_years.RAA_URL + "669d5919-109c-448e") == "669d5919-109c-448e"
    assert s02_years.raa_id_from_url("https://example.org/x") == ""
    assert s02_years.raa_id_from_url(None) == ""


def test_display_rule():
    year, flag = s02_years.display(np.array([1930, 1930, 1930, 1930]), np.array([1930, 1935, 1945, 1946]))
    assert year.tolist() == [1930, 1935, 1945, 1930]
    assert flag.tolist() == [EXACT, RANGE, RANGE, LONG]


def test_uuid_join_gives_exact_range_and_long():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)))
    r = raa(rec("a", sq(0), 1930, 1930, "u0"), rec("b", sq(1), 1926, 1929, "u1"), rec("c", sq(2), 1880, 1950, "u2"))
    y, _ = run(b, r)
    assert y.year.tolist() == [1930, 1929, 1880]
    assert y.yflag.tolist() == [EXACT, RANGE, LONG]
    assert (y.ysrc == SRC_RAA).all()
    assert y.raa_id.tolist() == ["a", "b", "c"]
    assert y.period.tolist() == [city.period_index(1930), city.period_index(1929), city.period_index(1880)]


def test_missing_tom_becomes_from():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    y, _ = run(b, raa(rec("a", sq(0), 1890, None, "u0")))
    assert (y.year[0], y.year_from[0], y.year_to[0], y.yflag[0]) == (1890, 1890, 1890, EXACT)


def test_inverted_range_is_swapped():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    y, _ = run(b, raa(rec("a", sq(0), 1912, 1908, "u0")))
    assert (y.year_from[0], y.year_to[0], y.year[0], y.yflag[0]) == (1908, 1912, 1912, RANGE)


def test_1065_typo_is_dropped_but_a_medieval_church_is_kept():
    b = buildings(("u0", "Enbostadshus", sq(0)), ("u1", "Ospec. samfundsbyggnad", sq(1)))
    r = raa(rec("typo", sq(0), 1065, 1067, "u0"), rec("church", sq(1), 1140, 1199, "u1", grp="Religionsutövning"))
    y, report = run(b, r)
    assert (y.year[0], y.yflag[0], y.ysrc[0]) == (0, UNKNOWN, SRC_NONE)
    assert y.raa_id[0] == "typo"                      # the record link survives; its year does not
    assert (y.year[1], y.year_from[1], y.yflag[1]) == (1140, 1140, LONG)
    assert [x["raa_id"] for x in report["raa_rejected"]] == ["typo"]
    known = y[y.yflag != UNKNOWN]
    assert (known.year >= 1000).all() and (known.year_from <= known.year_to).all()


def test_a_year_after_2026_is_rejected():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    y, report = run(b, raa(rec("future", sq(0), 1914, 2914, "u0")))
    assert (y.year[0], y.yflag[0]) == (0, UNKNOWN)
    assert [x["raa_id"] for x in report["raa_rejected"]] == ["future"]


def test_an_undated_uuid_joined_record_keeps_the_link_but_gives_no_year():
    # Task 11 reads the rating and architects through raa_id, so a record with no from-year must still link.
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Enbostadshus", sq(2)))
    zone = box(X0 + 90, Y0 - 10, X0 + 130, Y0 + 20)            # dates slot 1 by area
    y, report = run(b, raa(rec("undated", sq(0), None, None, "u0"), rec("also-undated", sq(1), None, None, "u1"),
                           rec("zone", zone, 1900, 1910, typ="Område"), rec("nodate-house", sq(2), None, 1950, "u2")))
    assert (y.year[0], y.year_from[0], y.year_to[0], y.yflag[0], y.ysrc[0], y.period[0]) == (0, 0, 0, UNKNOWN, 0, 0)
    assert y.raa_id[0] == "undated"                            # the link survives; there is no year to take
    assert (y.year[1], y.yflag[1], y.ysrc[1], y.raa_id[1]) == (1910, AREA, SRC_RAA_AREA, "also-undated")
    assert (y.yflag[2], y.private[2], y.raa_id[2]) == (UNKNOWN, False, "nodate-house")   # a tom alone is no date
    assert report["raa_rejected"] == []                        # undated is not "rejected": it was never dated


def test_a_dated_record_supplies_the_link_over_a_larger_undated_one():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)))
    r = raa(rec("undated-big", sq(0), None, None, "u0"),
            rec("dated-small", box(X0, Y0, X0 + 2, Y0 + 10), 1925, 1925, "u0"),
            rec("undated-big-1", sq(1), None, None, "u1"),
            rec("rejected-small", box(X0 + 100, Y0, X0 + 102, Y0 + 10), 1065, 1067, "u1"))
    y, _ = run(b, r)
    assert (y.raa_id[0], y.year[0], y.yflag[0]) == ("dated-small", 1925, EXACT)
    assert (y.raa_id[1], y.year[1], y.yflag[1]) == ("undated-big-1", 0, UNKNOWN)    # no dated record: the best overlap


def test_the_best_undated_record_is_chosen_deterministically():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    recs = [rec("b", sq(0), None, None, "u0"), rec("a", sq(0), None, None, "u0"),
            rec("small", box(X0, Y0, X0 + 2, Y0 + 10), None, None, "u0")]
    first, _ = run(b, raa(*recs))
    second, _ = run(b, raa(*recs[::-1]))
    assert first.raa_id[0] == "a" and (first.year[0], first.yflag[0]) == (0, UNKNOWN)
    assert_frame_equal(first, second)


def test_several_records_on_one_footprint_most_overlap_wins():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    big = box(X0, Y0, X0 + 8, Y0 + 10)               # 80 m² of the footprint
    small = box(X0 + 8, Y0, X0 + 10, Y0 + 10)        # 20 m²
    y, _ = run(b, raa(rec("small", small, 1880, 1882, "u0"), rec("big", big, 1910, 1912, "u0")))
    assert (y.raa_id[0], y.year[0], y.yflag[0]) == ("big", 1912, RANGE)


def test_tied_records_take_the_earliest_year_and_long():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    y, _ = run(b, raa(rec("late", sq(0), 1920, 1925, "u0"), rec("early", sq(0), 1900, 1905, "u0")))
    assert (y.raa_id[0], y.year[0], y.year_from[0], y.year_to[0], y.yflag[0]) == ("early", 1900, 1900, 1925, LONG)


def test_tied_records_that_agree_keep_the_display_rule():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    y, _ = run(b, raa(rec("b", sq(0), 1930, 1932, "u0"), rec("a", sq(0), 1930, 1932, "u0")))
    assert (y.raa_id[0], y.year[0], y.yflag[0]) == ("a", 1932, RANGE)


def test_winner_does_not_depend_on_input_order():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("", "Flerbostadshus", sq(2)))
    recs = [rec("a", sq(0), 1920, 1925, "u0"), rec("b", sq(0), 1900, 1905, "u0"), rec("c", sq(1), 1955, 1957, "u1"),
            rec("d", box(X0, Y0, X0 + 8, Y0 + 10), 1890, 1890, "u1"), rec("e", sq(2), 1961, 1961)]
    first, _ = run(b, raa(*recs))
    second, _ = run(b, raa(*recs[::-1]))
    assert_frame_equal(first, second)


def test_unmatched_polygon_must_cover_half_the_footprint():
    b = buildings(("", "Flerbostadshus", sq(0)), ("", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)))
    r = raa(rec("half", sq(0, size=10, dx=4), 1931, 1931),           # covers 60 m² of 100
            rec("less", sq(1, size=10, dx=6), 1932, 1932),           # covers 40 m²
            rec("own", sq(2), 1900, 1900, "u2"),
            rec("over", sq(2), 1999, 1999))                          # unmatched, covers a dated footprint
    y, _ = run(b, r)
    assert (y.year[0], y.raa_id[0], y.ysrc[0]) == (1931, "half", SRC_RAA)
    assert (y.year[1], y.raa_id[1], y.yflag[1]) == (0, "", UNKNOWN)
    assert (y.year[2], y.raa_id[2]) == (1900, "own")


def test_area_rule_smallest_polygon_wins_and_buildings_beat_areas():
    b = buildings(("", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(0, dx=40)), ("", "Flerbostadshus", sq(3)))
    big = box(X0 - 100, Y0 - 100, X0 + 200, Y0 + 200)
    small = box(X0 - 5, Y0 - 5, X0 + 20, Y0 + 20)
    r = raa(rec("big", big, 1900, 1950, typ="Område"), rec("small", small, 1960, 1964, typ="Område"),
            rec("own", sq(0, dx=40), 1935, 1936, "u1"))
    y, _ = run(b, r)
    assert (y.year[0], y.year_from[0], y.year_to[0], y.yflag[0], y.ysrc[0]) == (1964, 1960, 1964, AREA, SRC_RAA_AREA)
    assert (y.year[1], y.ysrc[1]) == (1936, SRC_RAA)
    assert (y.year[2], y.yflag[2]) == (0, UNKNOWN)


def test_area_with_a_long_span_shows_year_from():
    b = buildings(("", "Flerbostadshus", sq(0)))
    y, _ = run(b, raa(rec("big", box(X0 - 50, Y0 - 50, X0 + 50, Y0 + 50), 1900, 1950, typ="Område")))
    assert (y.year[0], y.yflag[0]) == (1900, AREA)


def test_landmark_wins_over_raa_and_keeps_the_raa_link():
    b = buildings(("u0", "Allmän byggnad", sq(0, size=40)))
    r = raa(rec("wing", sq(0, size=40), 1640, 1742, "u0"))
    y, report = run(b, r, [landmark_at(X0 + 20, Y0 + 20, name="Stockholms slott")])
    assert (y.year[0], y.year_from[0], y.year_to[0]) == (1754, 1697, 1754)
    assert (y.ysrc[0], y.yflag[0], y.landmark[0], y.raa_id[0]) == (SRC_CURATED, RANGE, "Stockholms slott", "wing")
    assert report["landmarks"] == {"Stockholms slott": 0}


def test_landmark_in_a_courtyard_or_within_15_m_resolves_else_is_dropped():
    ring = Polygon(sq(0, size=60).exterior.coords, [sq(0, size=40, dx=10, dy=10).exterior.coords])
    b = buildings(("", "Allmän byggnad", ring), ("", "Allmän byggnad", sq(2)), ("", "Allmän byggnad", sq(4)))
    lms = [landmark_at(X0 + 30, Y0 + 30, name="court", year=1900, year_from=1900, year_to=1900),
           landmark_at(X0 + 200 + 20, Y0 + 5, name="near"),          # 10 m east of slot 2
           landmark_at(X0 + 400 + 40, Y0 + 5, name="far")]           # 30 m east of slot 4
    y, report = run(b, no_raa(), lms)
    assert (y.landmark[0], y.yflag[0]) == ("court", EXACT)
    assert y.landmark[1] == "near"
    assert y.landmark[2] == "" and report["landmarks_dropped"] == ["far"]


def test_private_house_publishes_only_its_decade_and_keeps_its_flag():
    # Review Focus #3 (D18): RAÄ dates house 0 exactly to 1963; only "1960s" may leave this step.
    b = buildings(("u0", "Enbostadshus", sq(0)), ("u1", "Enbostadshus", sq(1)), ("u2", "Enbostadshus", sq(2)),
                  ("", "Kolonistuga", sq(3)), ("u4", "Flerbostadshus", sq(4)))
    r = raa(rec("exact", sq(0), 1963, 1963, "u0"), rec("range", sq(1), 1926, 1929, "u1"),
            rec("long", sq(2), 1884, 1950, "u2"),
            rec("area", box(X0 + 290, Y0 - 10, X0 + 320, Y0 + 20), 1936, 1938, typ="Område"),
            rec("flats", sq(4), 1963, 1963, "u4"))
    y, _ = run(b, r)
    assert y.year.tolist() == [1960, 1920, 1880, 1930, 1963]
    assert y.year_from.tolist() == [1960, 1920, 1880, 1930, 1963]
    assert y.year_to.tolist() == [1969, 1929, 1889, 1939, 1963]
    assert y.yflag.tolist() == [EXACT, RANGE, LONG, AREA, EXACT]      # yflag still says how the year is known
    assert y.ysrc.tolist() == [SRC_RAA, SRC_RAA, SRC_RAA, SRC_RAA_AREA, SRC_RAA]
    assert y.private.tolist() == [True, True, True, True, False]
    assert y.raa_id.tolist() == ["exact", "range", "long", "", "flats"]  # for the rating; never on a card (Task 12)
    assert y.period.tolist() == [city.period_index(v) for v in (1963, 1929, 1884, 1938, 1963)]


def test_private_house_keeps_its_period_across_a_period_boundary():
    b = buildings(("u0", "Enbostadshus", sq(0)))
    y, _ = run(b, raa(rec("house", sq(0), 1967, 1967, "u0")))
    assert (y.year[0], y.year_from[0], y.year_to[0], y.yflag[0], y.private[0]) == (1960, 1960, 1969, EXACT, True)
    assert y.period[0] == city.period_index(1967) != city.period_index(1960)


def test_private_house_without_a_source_stays_unknown():
    b = buildings(("u0", "Enbostadshus", sq(0)))
    y, _ = run(b, no_raa())
    assert (y.year[0], y.year_from[0], y.year_to[0], y.yflag[0], y.period[0]) == (0, 0, 0, UNKNOWN, 0)
    assert not y.private[0]


def test_curated_private_house_keeps_its_exact_year():
    b = buildings(("u0", "Enbostadshus", sq(0)))
    y, _ = run(b, raa(rec("house", sq(0), 1963, 1963, "u0")),
               [landmark_at(X0 + 5, Y0 + 5, name="Villa", year=1905, year_from=1905, year_to=1905)])
    assert (y.year[0], y.yflag[0], y.ysrc[0], y.private[0]) == (1905, EXACT, SRC_CURATED, False)


def test_a_rebuild_never_changes_the_year_or_the_period():
    # Task 11a (§14 of the Gamla stan research): the map shows when the standing building was built; its rebuilds,
    # raised storeys and extensions are a second line on the card, and older cellars leave the build's year as it is.
    # A guard: s02_years reads none of these fields, so it passed before Task 11a's code too.
    b = buildings(("u0", "Allmän byggnad", sq(0, size=40)))
    r = raa(rec("wing", sq(0, size=40), 1640, 1742, "u0"))
    plain = landmark_at(X0 + 20, Y0 + 20, name="Huset", year=1690, year_from=1688, year_to=1690)
    rebuilt = {**plain, "rebuilt": [[1757, "rebuilt"], [1857, "raised"], [1935, "extended"]], "cellars": True,
               "point": {"reason": "a test", "source": "a test"}}
    y0, _ = run(b, r, [plain])
    y1, report = run(b, r, [rebuilt])
    assert_frame_equal(y1, y0)
    assert (y1.year[0], y1.year_from[0], y1.year_to[0], y1.period[0]) == (1690, 1688, 1690, city.period_index(1690))
    assert report["landmarks"] == {"Huset": 0}


def test_output_matches_contract_c3():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    years, _ = s02_years.assign_years(b, raa(rec("a", sq(0), 1930, 1930, "u0")), [])
    assert list(years.columns) == ["gid", "year", "year_from", "year_to", "ysrc", "yflag", "period", "private",
                                   "raa_id", "landmark"]
    assert [str(t) for t in years.dtypes[:8]] == ["int32", "int16", "int16", "int16", "uint8", "uint8", "uint8",
                                                  "bool"]
    assert years.raa_id.tolist() == ["a"] and years.landmark.tolist() == [""]


# --- the RAÄ Stockholm layer mixes Polygon and MultiPolygon (23,497 and 27 records) ----------------------

def two_parts(i, h=2.0):
    """A MultiPolygon: the two 10 m wide, h m deep outer strips of slot i's square (20 m² each at h=2)."""
    x, y = X0 + 100.0 * i, Y0
    return MultiPolygon([box(x, y, x + 10, y + h), box(x, y + 10 - h, x + 10, y + 10)])


def test_multipolygon_records_join_overlap_and_date_areas_like_polygons():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("", "Flerbostadshus", sq(1)), ("", "Flerbostadshus", sq(2)),
                  ("", "Flerbostadshus", sq(3)))
    wide = MultiPolygon([box(X0 + 100, Y0, X0 + 106, Y0 + 10), box(X0 + 106, Y0, X0 + 110, Y0 + 10)])
    r = raa(rec("joined", two_parts(0), 1900, 1902, "u0"),                      # by UUID
            rec("covers", wide, 1950, 1950),                                     # unmatched, covers all of slot 1
            rec("sparse", two_parts(2), 1960, 1960),                             # unmatched, covers 40 m² of 100
            rec("zone", MultiPolygon([box(X0 + 290, Y0 - 5, X0 + 320, Y0 + 15)]), 1930, 1940, typ="Område"))
    y, _ = run(b, r)
    assert (y.year[0], y.raa_id[0], y.yflag[0]) == (1902, "joined", RANGE)
    assert (y.year[1], y.raa_id[1], y.ysrc[1]) == (1950, "covers", SRC_RAA)
    assert (y.year[2], y.yflag[2]) == (0, UNKNOWN)
    assert (y.year[3], y.ysrc[3], y.yflag[3]) == (1940, SRC_RAA_AREA, AREA)


def test_load_raa_reads_both_geometry_types_for_stockholm_only(tmp_path):
    gpkg = tmp_path / "raa.gpkg"
    rows = [rec("poly", sq(0), 1900, 1900, "u0"), rec("multi", two_parts(1), 1910, 1912, "u1"),
            rec("elsewhere", sq(2), 1920, 1920, "u2")]
    rows[2]["kommunnamn"] = "Nacka"
    geoms = gpd.GeoSeries([r.pop("geometry") for r in rows], crs=3011).to_crs(3006)
    # Like the real layer: geometry type "Unknown", Polygon and MultiPolygon side by side.
    pyogrio.write_dataframe(gpd.GeoDataFrame(rows, geometry=geoms, crs=3006), gpkg, layer="raa", driver="GPKG",
                            geometry_type="Unknown", promote_to_multi=False)
    got = s02_years.load_raa(gpkg, "raa")
    assert got.crs.to_epsg() == city.CRS
    assert sorted(got.raa_id) == ["multi", "poly"]
    assert sorted(set(got.geometry.geom_type)) == ["MultiPolygon", "Polygon"]
    assert abs(got.geometry[got.raa_id == "poly"].iloc[0].area - 100.0) < 0.01


def test_load_raa_keeps_border_records_that_name_stockholm_in_a_list(tmp_path):
    # D35's border fix (Plan 4a): RAÄ writes a building on the municipal border as 'Solna;Stockholm'
    gpkg = tmp_path / "raa.gpkg"
    rows = [rec("plain", sq(0), 1900, 1900, "u0"), rec("border", sq(1), 1910, 1910, "u1"),
            rec("nacka", sq(2), 1920, 1920, "u2"), rec("south", sq(3), 1930, 1930, "u3"),
            rec("look-alike", sq(4), 1940, 1940, "u4")]
    for r, k in zip(rows, ["Stockholm", "Solna;Stockholm", "Nacka", "Huddinge; Stockholm", "Stockholmsnäs"]):
        r["kommunnamn"] = k
    geoms = gpd.GeoSeries([r.pop("geometry") for r in rows], crs=3011).to_crs(3006)
    pyogrio.write_dataframe(gpd.GeoDataFrame(rows, geometry=geoms, crs=3006), gpkg, layer="raa", driver="GPKG")
    assert sorted(s02_years.load_raa(gpkg, "raa").raa_id) == ["border", "plain", "south"]
    assert s02_years.in_stockholm(["Stockholm", "Solna;Stockholm", None, "Stockholmsnäs"]).tolist() == [
        True, True, False, False]


def fake_years(ysrc, yflag):
    """years.parquet rows for two footprints: one UNKNOWN, one dated by `ysrc` (with a RAÄ link, so only the
    RAÄ-year guard can fire)."""
    return pd.DataFrame({
        "gid": [0, 1], "year": [0, 1900], "year_from": [0, 1900], "year_to": [0, 1900], "ysrc": [SRC_NONE, ysrc],
        "yflag": [UNKNOWN, yflag], "period": [0, 5], "private": [False, False], "raa_id": ["", "r1"],
        "landmark": ["", ""]})


@pytest.mark.parametrize(("ysrc", "yflag", "fails"), [(SRC_NONE, UNKNOWN, True), (SRC_RAA_AREA, AREA, True),
                                                      (SRC_RAA, EXACT, False)], ids=["unknown", "area-only", "raa"])
def test_main_fails_when_no_building_gets_a_raa_year(tmp_path, monkeypatch, ysrc, yflag, fails):
    # P2: if RAÄ renames its kommunnamn, load_raa finds nothing and every building would ship UNKNOWN
    gpd.GeoDataFrame({"gid": [0, 1], "uuid": ["a", "b"], "kategori": ["", ""], "fnr": [0, 0]}, geometry=[sq(0), sq(1)],
                     crs=city.CRS).to_parquet(tmp_path / "buildings.parquet")
    monkeypatch.setattr(s02_years, "load_raa", lambda *_: None)
    # Plan 2: main also loads the Wikidata and OSM caches and the stadsdelar; they are stubbed here
    for mod in (s02_years.years_wikidata, s02_years.years_osm):
        monkeypatch.setattr(mod, "load", lambda *_: None)
    monkeypatch.setattr(s02_years.est, "stadsdel_of", lambda *_: None)
    for name in ("dated.json", "classes.json", "osm.json"):
        (tmp_path / name).write_text("{}")
    report = {"raa_rejected": [], "landmarks_dropped": [], "landmarks": 0, "review": {}, "accuracy": {}}
    monkeypatch.setattr(s02_years, "assign_years", lambda *_, **__: (fake_years(ysrc, yflag), report))
    args = ["--buildings", str(tmp_path / "buildings.parquet"), "--out", str(tmp_path / "years.parquet"),
            "--raa-old", str(tmp_path / "missing.gpkg"), "--wikidata", str(tmp_path / "dated.json"),
            "--wikidata-classes", str(tmp_path / "classes.json"), "--osm", str(tmp_path / "osm.json"),
            "--accuracy-out", str(tmp_path / "accuracy.json"), "--review-out", str(tmp_path / "review.json"),
            "--landmarks", str(tmp_path / "landmarks.json")]
    (tmp_path / "landmarks.json").write_text("[]")      # Plan 4a: s08_landmarks' verified list
    if fails:
        with pytest.raises(SystemExit, match="no building got a RAÄ year"):
            s02_years.main(args)
    else:
        s02_years.main(args)
    assert (tmp_path / "years.parquet").exists() is not fails


# --- real data ----------------------------------------------------------------------------------------

@pytest.mark.network
def test_real_stockholm_years(tmp_path: Path):
    ensure_city_data([s02_years.RAA_GPKG, s02_years.BUILDINGS, s02_years.years_wikidata.DATED,
                      s02_years.years_wikidata.CLASSES, s02_years.years_osm.DEST, s02_years.LANDMARKS_JSON],
                     buildings=s02_years.BUILDINGS,
                     steps="s00_fetch_city s00_fetch_raa s00_fetch_raa_old s00_fetch_wikidata s00_fetch_osm s01_load "
                           "s08_landmarks")
    out = tmp_path / "years.parquet"
    s02_years.main(["--out", str(out), "--accuracy-out", str(tmp_path / "accuracy.json"),
                    "--review-out", str(tmp_path / "review.json")])
    y = pd.read_parquet(out)
    s = s02_years.summary(y)
    print(s)
    verified = s02_years.load_landmarks()           # Plan 4a: the entries s08_landmarks verified
    assert len(verified) == len(LANDMARKS)
    assert s["curated"] == len(verified)
    assert set(y.landmark[y.landmark != ""]) == {L["name"] for L in verified}
    # Observed on the 77,743-building city (RAÄ rebuilds nightly, so the bounds leave room for drift).
    assert 21_500 <= s["raa"] <= 22_500           # observed 22,049: 22,003 by UUID + 53 by overlap - 7 curated
    # observed 5,878; 6,263 since D35's border fix (Task 2): RAÄ's area record "Skärholmen" ("Huddinge;Stockholm")
    # now dates 386 Stockholm buildings in Skärholmen
    assert 5_500 <= s["raa_area"] <= 6_600
    # Plan 2 (2026-10-15 measurements; the ranges leave room for the new anchors and RAÄ's nightly rebuilds)
    assert 700 <= s["raa_old"] <= 950 or not s02_years.years_raa_old.DEST.exists()   # 818; 0 without the snapshot
    assert 100 <= s["wikidata"] <= 200            # 137
    assert 400 <= s["osm"] <= 650                 # 514
    # Task 14b (houses only, no period on its own, 7 in 10 right, the FNR guard), measured on v20261015-m3b:
    assert 3_800 <= s["estimate"] <= 5_200        # 4,510 (Task 14 built 5,906 and 1,182 period-only)
    assert s["period"] == 0                       # give_period is off: a rule, not a measurement
    assert 15_000 <= s["private"] <= 18_500       # 16,864: 12,204 dated houses + the estimated and newly dated ones
    assert 42_500 <= s["unknown"] <= 45_500       # 43,935 (41,357 in Task 14's build; 49,804 before Plan 2)
    assert (tmp_path / "accuracy.json").exists() and (tmp_path / "review.json").exists()
    bld = pd.read_parquet(s02_years.BUILDINGS, columns=["gid", "uuid", "kategori", "fnr"])
    assert s["buildings"] == len(bld) and set(y.gid) == set(bld.gid)
    estimated = bld.set_index("gid").loc[y.gid[y.yflag == ESTIMATE]]
    assert (estimated.kategori == "Enbostadshus").all()                       # houses only
    assert (estimated.fnr <= city.ESTIMATE["late_unit_fnr"]).all()           # never on a late-formed property unit
    ext = json.loads((tmp_path / "accuracy.json").read_text(encoding="utf-8"))["external"]
    # the map's rule on the Wikidata/OSM-only buildings: 551 of them, 10 shown as "≈ year" (6 right), 219 from 1990 on
    assert 450 <= ext["n_all"] <= 700 and ext["n_all"] == ext["n_estimate"] + ext["n_unknown"]
    assert ext["before_1990"]["n_all"] + ext["from_1990"]["n_all"] == ext["n_all"]
    assert ext["n_estimate"] <= 25 and ext["status"] == ("measured" if ext["n_estimate"] >= 30 else "not measurable")
    assert ext["from_1990"]["n_estimate"] <= 3     # the blind spot stays closed on this sample (m3b: 0; m3's rule: 24)
    known = y[y.yflag != UNKNOWN]
    assert known.year.between(1000, 2026).all()
    assert (known.year_from <= known.year).all() and (known.year <= known.year_to).all()
    assert (y.year[y.yflag == UNKNOWN] == 0).all() and not y.private[y.yflag == UNKNOWN].any()
    p = y[y.private]                               # D18: the decade only, a knowledge flag, the real period
    assert (p.year % 10 == 0).all() and (p.year_from == p.year).all() and (p.year_to == p.year + 9).all()
    assert set(p.yflag) <= {EXACT, RANGE, LONG, AREA, ESTIMATE, PERIOD}   # Plan 2: estimated houses round too
    assert all(city.period_index(d) <= q <= city.period_index(d + 9) for d, q in zip(p.year, p.period))
    palace = y[y.landmark == "Stockholms slott"].iloc[0]
    assert (palace.year, palace.raa_id) == (1754, "669d5919-109c-448e-bb9e-094033371c64")
    linked = set(y.raa_id) - {""}
    assert len(linked) > 20_000
    assert not linked & set(bld.uuid)              # RAÄ's own ids, never the register UUID
    # Every footprint a RAÄ Byggnad record joins by UUID carries a link, dated or not (Task 11 reads its rating).
    records = s02_years.load_raa()
    joined = set(records.registerbyggnad_id[records.objekttyp_namn == "Byggnad"].dropna()) - {""}
    must_link = bld.gid[bld.uuid.isin(joined)]
    assert len(must_link) > 20_000
    assert (y.raa_id[y.gid.isin(must_link)] != "").all()
