"""The year tiers inside s02_years: the order, the new sources, the estimate tier, the decade rule for
estimates, the narrow-decade rule and the review list. Synthetic footprints like tests/test_s02_years.py."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from pipeline import city, s02_years, s03_tiles, s99_validate
from pipeline.codes import (AREA, ESTIMATE, EXACT, LONG, PERIOD, RANGE, SRC_CURATED, SRC_ESTIMATE, SRC_NONE, SRC_OSM,
                            SRC_RAA, SRC_RAA_AREA, SRC_RAA_OLD, SRC_WIKIDATA, UNKNOWN)
from pipeline.yearrules import display
from tests.synth import PITCH, STEP, villa_blocks
from tests.test_s02_years import X0, Y0, buildings, landmark_at, no_raa, raa, rec, sq

# The measured rule, whatever product default the project picks at M3 (tests/test_estimate.py says the same).
P = dict(city.ESTIMATE, far_rule="unknown", period_only_stadsdelar=set())
# The independent check with nothing to check (no Wikidata or OSM row, or estimates off): the accuracy table's shape.
SPLIT0 = {"n_all": 0, "n_estimate": 0, "right_estimate": 0, "in_band_estimate": 0}
NO_EXTERNAL = {"status": "not measurable", "n_all": 0, "n_estimate": 0, "right_estimate": 0, "in_band_estimate": 0,
               "n_unknown": 0, "before_1990": SPLIT0, "from_1990": SPLIT0}


@pytest.fixture(autouse=True)
def pinned_private_house_set(monkeypatch):
    monkeypatch.setattr(city, "PRIVATE_HOUSE_KATEGORI", {"Enbostadshus", "Kolonistuga"})


def xy(i, dx=5.0, dy=5.0):
    """EPSG:3011 point inside slot i's square."""
    return X0 + 100.0 * i + dx, Y0 + dy


def inside(block, i=0.5, j=0.5):
    """Local (dx, dz) of a point between the houses of villa_blocks' block `block`."""
    return block * PITCH + i * STEP, j * STEP


def raa_recs(b, years, skip=None):
    """RAÄ records dating every footprint of b that has a year (by UUID, from == to), except the rows `skip` marks."""
    skip = np.zeros(len(b), dtype=bool) if skip is None else np.asarray(skip, dtype=bool)
    return [rec(f"r{g}", geom, int(yr), int(yr), uuid)
            for g, (geom, yr, uuid, s) in enumerate(zip(b.geometry, years, b.uuid, skip)) if yr and not s]


def shown(f, t, year=None):
    """The published year of a source span: the given one (a decade's start, a circa's stated year), else display()."""
    return year if year is not None else int(display(np.array([f]), np.array([t]))[0][0])


def wikidata(*items):
    """items: (qid, slot, year_from, year_to, article[, year]). A frame like years_wikidata.load()."""
    rows = [{"qid": q, "name": f"Item {q}", "x": xy(i)[0], "y": xy(i)[1], "year": shown(f, t, *rest), "year_from": f,
             "year_to": t, "precision": 9, "article": art, "dropped": ""} for q, i, f, t, art, *rest in items]
    return pd.DataFrame(rows, columns=["qid", "name", "x", "y", "year", "year_from", "year_to", "precision", "article",
                                       "dropped"])


def osm(*items):
    """items: (osm_id, slot, year_from, year_to[, year])."""
    rows = [{"osm_id": o, "name": "", "x": xy(i)[0], "y": xy(i)[1], "year": shown(f, t, *rest), "year_from": f,
             "year_to": t} for o, i, f, t, *rest in items]
    return pd.DataFrame(rows, columns=["osm_id", "name", "x", "y", "year", "year_from", "year_to"])


def attrs_of(row) -> np.ndarray:
    """One attrs.bin record (s03_tiles.ATTR_DTYPE) from a years.parquet row, for s99_validate.check_attrs."""
    a = np.zeros(1, dtype=s03_tiles.ATTR_DTYPE)
    for k in ("year", "year_from", "year_to", "yflag", "ysrc", "period", "private"):
        a[k] = row[k]
    a["h_dm"], a["floors"] = 60, 2
    return a


def raa_old(*items):
    """items: (uuid, year_from, year_to)."""
    return pd.DataFrame([{"fast_byg_uuid": u, "year_from": f, "year_to": t} for u, f, t in items],
                        columns=["fast_byg_uuid", "year_from", "year_to"])


def run(b, r, landmarks=(), **sources):
    years, report = s02_years.assign_years(b, r, list(landmarks), estimates=False, **sources)
    return years.set_index("gid"), report


@pytest.fixture
def main_args(tmp_path, monkeypatch):
    """main()'s setup on villa_blocks(extra): buildings.parquet written, RAÄ dating every block house, empty Wikidata
    and OSM caches (the files exist, their loaders are stubbed), no old-register snapshot, no verified landmark,
    every building in FARSTA.
    Call it with the extra rows; it returns (recs, args), where args(tag) names the inputs and the outputs
    years{tag}.parquet, accuracy{tag}.json and review{tag}.json in tmp_path."""
    def setup(extra):
        b, years, _, _ = villa_blocks(extra)
        b.to_parquet(tmp_path / "buildings.parquet")
        recs = raa_recs(b, years)
        monkeypatch.setattr(s02_years, "load_raa", lambda *_: raa(*recs))
        monkeypatch.setattr(s02_years.years_wikidata, "load", lambda *_: wikidata())
        monkeypatch.setattr(s02_years.years_osm, "load", lambda *_: osm())
        monkeypatch.setattr(s02_years.est, "stadsdel_of", lambda *_: np.array(["FARSTA"] * len(b), dtype=object))
        for name in ("dated.json", "classes.json", "osm.json"):
            (tmp_path / name).write_text("{}")
        (tmp_path / "landmarks.json").write_text("[]")      # s08_landmarks' verified list, empty here

        def args(tag=""):
            return ["--buildings", str(tmp_path / "buildings.parquet"), "--raa-old", str(tmp_path / "missing.gpkg"),
                    "--wikidata", str(tmp_path / "dated.json"), "--wikidata-classes", str(tmp_path / "classes.json"),
                    "--osm", str(tmp_path / "osm.json"), "--out", str(tmp_path / f"years{tag}.parquet"),
                    "--accuracy-out", str(tmp_path / f"accuracy{tag}.json"),
                    "--review-out", str(tmp_path / f"review{tag}.json"),
                    "--landmarks", str(tmp_path / "landmarks.json")]
        return recs, args
    return setup


def test_tier_order_follows_the_spec():
    # slot: 0 RAÄ + Wikidata + OSM; 1 old register + area; 2 area + Wikidata; 3 Wikidata + OSM; 4 OSM alone;
    # 5 old register alone; 6 curated + Wikidata; 7 nothing
    b = buildings(*[(f"u{i}", "Flerbostadshus", sq(i)) for i in range(8)])

    def zone(i):
        return rec(f"zone{i}", sq(i, size=30, dx=-10, dy=-10), 1960, 1964, typ="Område")

    r = raa(rec("a", sq(0), 1930, 1930, "u0"), zone(1), zone(2))
    y, _ = run(b, r, [landmark_at(*xy(6), name="Slottet")],
               raa_old=raa_old(("u1", 1902, 1905), ("u5", 1978, 1978)),
               wikidata=wikidata(("Q0", 0, 1700, 1700, False), ("Q2", 2, 1995, 1995, False),
                                 ("Q3", 3, 1630, 1630, True), ("Q6", 6, 1900, 1900, False)),
               osm=osm(("way/0", 0, 1800, 1800), ("way/3", 3, 1850, 1850), ("way/4", 4, 1916, 1916)))
    assert y.ysrc.tolist() == [SRC_RAA, SRC_RAA_OLD, SRC_RAA_AREA, SRC_WIKIDATA, SRC_OSM, SRC_RAA_OLD, SRC_CURATED,
                               SRC_NONE]
    assert y.year.tolist() == [1930, 1905, 1964, 1630, 1916, 1978, 1754, 0]
    assert y.yflag.tolist() == [EXACT, RANGE, AREA, EXACT, EXACT, EXACT, RANGE, UNKNOWN]
    assert y.raa_id.tolist() == ["a", "", "", "", "", "", "", ""]          # the old register never links a record
    assert y.period.tolist() == [city.period_index(v) if v else 0
                                 for v in (1930, 1905, 1964, 1630, 1916, 1978, 1754, 0)]


def test_wikidata_and_osm_publish_the_stated_year_and_spans_follow_the_display_rule():
    # Shown honestly: a Wikidata decade publishes 1640 (the card prints "1640s", the timeline draws it at 1640),
    # an OSM "~1920" the year the mapper wrote; only a real span takes RAÄ's completion-year rule. The yflag still
    # comes from the span (a decade is RANGE), so year_from <= year <= year_to holds for s99.
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)),
                  ("u3", "Flerbostadshus", sq(3)))
    y, _ = run(b, no_raa(), wikidata=wikidata(("Q0", 0, 1640, 1649, False, 1640), ("Q1", 1, 1571, 1642, False)),
               osm=osm(("way/2", 2, 1915, 1925, 1920), ("way/3", 3, 1865, 1878)))
    assert (y.year[0], y.year_from[0], y.year_to[0], y.yflag[0]) == (1640, 1640, 1649, RANGE)   # a decade
    assert (y.year[1], y.yflag[1]) == (1571, LONG)                                                # two values far apart
    assert (y.year[2], y.year_from[2], y.year_to[2], y.yflag[2]) == (1920, 1915, 1925, RANGE)   # "~1920"
    assert (y.year[3], y.yflag[3]) == (1878, RANGE)                             # a real span: its completion year
    assert y.period.tolist() == [city.period_index(v) for v in (1640, 1571, 1920, 1878)]


def test_a_pinned_wikidata_item_dates_the_footprint_its_card_goes_to():
    # pipeline/wiki_pins.csv: the item whose point falls in the house next door dates its own house, as s06 puts the
    # card's item there; the house next door is dated by nothing
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)))
    items = wikidata(("Q0", 0, 1643, 1643, False))
    y, _ = run(b, no_raa(), wikidata=items)
    assert (y.ysrc[0], y.ysrc[1]) == (SRC_WIKIDATA, SRC_NONE)
    y, report = run(b, no_raa(), wikidata=items, wiki_pins={"Q0": 1})
    assert (y.ysrc[0], y.ysrc[1], y.year[1]) == (SRC_NONE, SRC_WIKIDATA, 1643)
    assert [(e["gid"], e["placement"]) for e in report["review"]["wikidata_gains"]] == [(1, "pinned")]


def test_a_private_house_dated_by_wikidata_or_osm_publishes_its_decade_only():
    # The decade rule: the Wikipedia-article exception is not implemented yet; every non-curated private house rounds.
    b = buildings(("u0", "Enbostadshus", sq(0)), ("u1", "Enbostadshus", sq(1)), ("u2", "Enbostadshus", sq(2)))
    y, _ = run(b, no_raa(), wikidata=wikidata(("Q0", 0, 1912, 1912, True)), osm=osm(("way/1", 1, 1967, 1967)),
               raa_old=raa_old(("u2", 1955, 1955)))
    assert y.year.tolist() == [1910, 1960, 1950] and y.year_to.tolist() == [1919, 1969, 1959]
    assert y.private.tolist() == [True, True, True]
    assert y.period.tolist() == [city.period_index(1912), city.period_index(1967), city.period_index(1955)]


def test_a_narrow_decade_takes_its_period_from_the_decades_middle_year():
    # Review Focus #2: a private house RAÄ dates to 1610 (p1 ends 1610) or 1719 (p3 starts 1719) would be pinned by
    # its decade and period together; the decade wins and the period is the one of 1615 or 1715 (Stormaktstiden).
    b = buildings(("u0", "Enbostadshus", sq(0)), ("u1", "Enbostadshus", sq(1)), ("u2", "Enbostadshus", sq(2)))
    y, _ = run(b, raa(rec("a", sq(0), 1610, 1610, "u0"), rec("b", sq(1), 1719, 1719, "u1"),
                      rec("c", sq(2), 1611, 1611, "u2")))
    assert y.year.tolist() == [1610, 1710, 1610]
    assert y.period.tolist() == [1, 1, 1]        # Stormaktstiden: the period of the decade's middle year
    assert city.period_index(1610) == 0 and city.period_index(1719) == 2   # what the real years would have given
    for d, q in zip(y.year, y.period):
        lo, hi = city.PERIODS[q][3], city.PERIODS[q][4]
        assert min(d + 9, hi) - max(d, lo) + 1 >= s02_years.MIN_PRIVATE_OVERLAP


def test_review_list_names_disagreements_centuries_and_gains():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)),
                  ("u3", "Flerbostadshus", sq(3)), ("u4", "Flerbostadshus", sq(4)),
                  ("u5", "Allmän byggnad", sq(5, size=40)))
    zone = rec("zone", sq(4, size=30, dx=-10, dy=-10), 1966, 1971, typ="Område")
    r = raa(rec("a", sq(0), 1345, 1354, "u0"), rec("b", sq(1), 1906, 1907, "u1"), rec("c", sq(2), 1920, 1925, "u2"),
            zone, rec("palace", sq(5, size=40), 1640, 1742, "u5"))
    wd = wikidata(("Q0", 0, 1625, 1625, True), ("Q1", 1, 1912, 1912, False), ("Q3", 3, 1880, 1880, False),
                  ("Q4", 4, 1995, 1995, False), ("Q5", 5, 1571, 1571, False))
    wd = pd.concat([wd, pd.DataFrame([{"qid": "Q9", "name": "Storkyrkan", "x": np.nan, "y": np.nan, "year_from": 0,
                                       "year_to": 0, "precision": 7, "article": True, "dropped": "century"}])])
    y, report = run(b, r, [landmark_at(*xy(5, 20, 20), name="Tyska kyrkan", year=1642, year_from=1638, year_to=1642)],
                    wikidata=wd, osm=osm(("way/2", 2, 1986, 1986), ("way/1", 1, 1909, 1909)))
    rv = report["review"]
    assert [(e["gid"], e["qid"], e["year_from"], e["winner_from"], e["winner_to"]) for e in rv["wikidata_vs_raa"]] == \
        [(0, "Q0", 1625, 1345, 1354)]                              # Q1 is within 10 years of 1906–1907: no entry
    assert [(e["gid"], e["qid"], e["year_from"]) for e in rv["wikidata_vs_area"]] == [(4, "Q4", 1995)]
    assert [(e["gid"], e["qid"], e["winner_year"]) for e in rv["wikidata_vs_curated"]] == [(5, "Q5", 1642)]
    assert [(e["gid"], e["osm_id"], e["year_from"]) for e in rv["osm_vs_raa"]] == [(2, "way/2", 1986)]
    assert rv["wikidata_century"] == [{"qid": "Q9", "name": "Storkyrkan", "precision": 7}]
    assert [(e["gid"], e["qid"], e["article"], e["placement"]) for e in rv["wikidata_gains"]] == \
        [(3, "Q3", False, "inside")]
    assert all(set(e) >= {"gid", "name", "year_from", "year_to", "winner_year", "winner_from", "winner_to"}
               for key in ("wikidata_vs_raa", "osm_vs_raa") for e in rv[key])
    # Review Focus #7: every Wikidata entry says how its item was placed, so a nearest-only gain can be weighed
    assert all(e["placement"] in ("inside", "courtyard", "nearest")
               for key in ("wikidata_vs_raa", "wikidata_vs_area", "wikidata_vs_curated", "wikidata_gains")
               for e in rv[key])
    assert y.ysrc[3] == SRC_WIKIDATA


def test_estimates_fill_near_houses_with_a_decade_and_the_rule_leaves_the_rest_unknown():
    # Villa blocks dated by RAÄ (exact years, in slot-free coordinates), plus undated buildings among them.
    b, years, _, _ = villa_blocks([
        (*inside(3), "Enbostadshus", "KV3 10", 2003),            # ESTIMATE, published as a decade
        (*inside(3, 1.5), "Flerbostadshus", "KV3 11", 2003),      # no measurable cell for apartments: UNKNOWN
        (5000.0, 0.0, "Enbostadshus", "FAR 1", 2003),             # far: UNKNOWN
        (*inside(5), "Kolonistuga", "KV5 10", 2003),              # a cottage: UNKNOWN
        (*inside(3, 2.5, 0.5), "Enbostadshus", "NYKVARTER 1", 2003),   # a kvarter of its own among the blocks: ESTIMATE
    ])
    y, report = s02_years.assign_years(b, raa(*raa_recs(b, years)), [], params=P)
    y = y.set_index("gid")
    q = y.loc[90:]
    assert q.yflag.tolist() == [ESTIMATE, UNKNOWN, UNKNOWN, UNKNOWN, ESTIMATE]
    assert q.ysrc.tolist() == [SRC_ESTIMATE, SRC_NONE, SRC_NONE, SRC_NONE, SRC_ESTIMATE]
    assert (q.year[90], q.year_from[90], q.year_to[90], q.private[90]) == (1950, 1950, 1959, True)   # 1952 ±5: 1950s
    assert (q.year[94], q.year_from[94], q.year_to[94], q.private[94]) == (1950, 1950, 1959, True)   # no kvarter bonus
    assert q.period[90] == q.period[94] == city.period_index(1952)
    assert (y.loc[:89].ysrc == SRC_RAA).all() and (y.loc[:89].private).all()      # the dated villas are untouched
    acc = report["accuracy"]
    assert acc["result"] == {"estimate": 2, "period": 0, "unknown": 3} and acc["tested"] == 90
    assert acc["area"] == {"n": 0, "status": "not measurable"}
    assert acc["external"] == NO_EXTERNAL                                   # no Wikidata or OSM row to score on
    cell = next(c for c in acc["cells"] if c["status"] == "estimate")
    # trained and scored on the exact years of the (private) villas, never on their published decades: blocks two
    # years apart give a held-out error of 2, where the decade starts would give 0 or 10
    assert cell["group"] == "house" and cell["median_error"] == 2


def test_a_small_city_measures_nothing_and_estimates_nothing():
    # Review Focus #5 (a fixture build): three dated blocks are 27 test buildings, fewer than min_cell in every cell
    # and in every fallback row, so nothing is estimated, not even a period through a fallback row.
    b, years, _, _ = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    few = b.fastighet.str.match(r"KV[012] ").to_numpy()
    y, report = s02_years.assign_years(b, raa(*raa_recs(b, years, skip=~few)), [], params=P)
    acc = report["accuracy"]
    assert acc["tested"] == 27
    assert acc["cells"] and all(c["n"] < 30 and c["status"] == "not measurable" for c in acc["cells"])
    assert acc["fallback"] and all(r["n"] < 30 and r["status"] == "not measurable" for r in acc["fallback"])
    assert acc["result"] == {"estimate": 0, "period": 0, "unknown": 64}       # blocks 3..9 and the extra house
    assert set(y.ysrc) == {SRC_RAA, SRC_NONE} and (y.yflag[y.ysrc == SRC_NONE] == UNKNOWN).all()


def osm_block(b, years, block, year=None):
    """An OSM frame dating every house of villa_blocks' block `block` (its own years, or `year`) on its centroid."""
    rows = b.fastighet.str.startswith(f"KV{block} ").to_numpy()
    c = b[rows].geometry.centroid
    yr = years[rows] if year is None else np.full(rows.sum(), year)
    return rows, pd.DataFrame({"osm_id": [f"way/{g}" for g in b[rows].gid], "name": "", "x": c.x.to_numpy(),
                               "y": c.y.to_numpy(), "year": yr, "year_from": yr, "year_to": yr})


def wikidata_block(b, years, block, year=None):
    """osm_block's houses dated by Wikidata items on their centroids instead."""
    rows, o = osm_block(b, years, block, year)
    return rows, pd.DataFrame({"qid": [f"Q{g}" for g in b[rows].gid], "name": "", "x": o.x, "y": o.y, "year": o.year,
                               "year_from": o.year_from, "year_to": o.year_to, "precision": 9, "article": False,
                               "dropped": ""})


# Final review PIPELINE-2: the external tests run on a block dated by Wikidata as well as by OSM, so a Wikidata row
# leaking into the check's training set (core) fails them as an OSM row does.
EXTERNAL_SOURCES = {"osm": (osm_block, SRC_OSM), "wikidata": (wikidata_block, SRC_WIKIDATA)}


@pytest.mark.parametrize("source", sorted(EXTERNAL_SOURCES))
def test_the_external_check_runs_the_maps_rule_on_the_wikidata_and_osm_rows_alone(source):
    # The independent check: trained on curated + raa + raa_old alone, the map's own rule (kvarter bonus,
    # the cells, every gate) run on the rows Wikidata or OSM dated, as if they had no year, and counted per map state.
    # Block 4's nine houses are dated by OSM (or Wikidata) instead of RAÄ: six are within 100 m of a RAÄ-dated house
    # and become "≈ year" (right period, true year within the ±5 band), the middle column (105 m away) stays unknown.
    # Six is under min_cell, so the check reads "not measurable" and keeps its counts; with min_cell lowered it is
    # measured.
    block_of, src = EXTERNAL_SOURCES[source]
    b, years, _, _ = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    block4, o = block_of(b, years, 4)
    recs = raa_recs(b, years, skip=block4)
    y, report = s02_years.assign_years(b, raa(*recs), [], **{source: o}, params=P)
    assert (y.set_index("gid").loc[b[block4].gid].ysrc == src).all()
    old = {"n_all": 9, "n_estimate": 6, "right_estimate": 6, "in_band_estimate": 6}
    assert report["accuracy"]["external"] == {"status": "not measurable", **old, "n_unknown": 3,
                                              "before_1990": old, "from_1990": SPLIT0}
    _, report = s02_years.assign_years(b, raa(*recs), [], **{source: o}, params=dict(P, min_cell=5))
    assert report["accuracy"]["external"] == {"status": "measured", **old, "n_unknown": 3,
                                              "before_1990": old, "from_1990": SPLIT0}
    # 9 rows reach min_cell 7, but 6 estimates do not: the status follows the estimates (review M2 d)
    _, report = s02_years.assign_years(b, raa(*recs), [], **{source: o}, params=dict(P, min_cell=7))
    assert report["accuracy"]["external"]["status"] == "not measurable"


@pytest.mark.parametrize("source", sorted(EXTERNAL_SOURCES))
def test_the_external_check_shows_the_blind_spot_and_the_guard(source):
    # A block OSM (or Wikidata) dates to 2005 among villas from 1946..1964: the map's rule gives it its neighbours' age
    # (wrong period, far outside the band), counted under from_1990. Two of its houses stand on late-formed property
    # units, so the guard leaves them unknown although they are within 100 m.
    block_of, _ = EXTERNAL_SOURCES[source]
    b, years, _, _ = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    block4, o = block_of(b, years, 4, year=2005)
    b.loc[b.fastighet.isin(["KV4 1", "KV4 2"]), "fnr"] = city.ESTIMATE["late_unit_fnr"] + 1     # the west column
    _, report = s02_years.assign_years(b, raa(*raa_recs(b, years, skip=block4)), [], **{source: o}, params=P)
    new = {"n_all": 9, "n_estimate": 4, "right_estimate": 0, "in_band_estimate": 0}
    assert report["accuracy"]["external"] == {"status": "not measurable", **new, "n_unknown": 5,
                                              "before_1990": SPLIT0, "from_1990": new}


def test_the_area_check_scores_area_years_against_the_building_years_in_the_polygon():
    # The area tier's accuracy. One Område 1900–1910 (area year 1910) over slots 0..3 and building 5:
    # slot 0 RAÄ 1905; slot 1 a private house RAÄ dates to 1917 (published as the 1910s, scored on 1917); slot 2
    # Wikidata 1930 and OSM 1909 and slot 3 OSM 1911, both outranked by the area but still building-level years
    # (Wikidata before OSM); building 5 the area alone. Errors 5, 7, 20 and 1; 1930 lies in another period. Slot 4,
    # outside the polygon, does not count.
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Enbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)),
                  ("u3", "Flerbostadshus", sq(3)), ("u4", "Flerbostadshus", sq(4)),
                  ("u5", "Flerbostadshus", sq(2, dx=40)))
    r = raa(rec("zone", sq(0, size=330, dx=-10, dy=-10), 1900, 1910, typ="Område"), rec("a", sq(0), 1905, 1905, "u0"),
            rec("b", sq(1), 1917, 1917, "u1"), rec("e", sq(4), 1800, 1800, "u4"))
    sources = dict(wikidata=wikidata(("Q2", 2, 1930, 1930, False)),
                   osm=osm(("way/2", 2, 1909, 1909), ("way/3", 3, 1911, 1911)))
    y, report = run(b, r, **sources)
    assert y.ysrc.tolist() == [SRC_RAA, SRC_RAA, SRC_RAA_AREA, SRC_RAA_AREA, SRC_RAA, SRC_RAA_AREA]
    assert y.year[1] == 1910                                               # published as the 1910s
    assert report["accuracy"]["area"] == {"n": 4, "status": "not measurable"}
    _, report = run(b, r, params=dict(P, min_cell=4), **sources)
    assert report["accuracy"]["area"] == {"n": 4, "status": "measured", "median_error": 6.0, "right_period": 0.75}
    # Final review PIPELINE-3: an old-register year is a building-level year too. Building 5, dated 1912 by the old
    # register, now counts (error 2, the same period): errors 5, 7, 20, 1 and 2.
    y, report = run(b, r, params=dict(P, min_cell=4), raa_old=raa_old(("u5", 1912, 1912)), **sources)
    assert y.ysrc[5] == SRC_RAA_OLD
    assert report["accuracy"]["area"] == {"n": 5, "status": "measured", "median_error": 5.0, "right_period": 0.8}


def test_area_years_never_train_the_estimator():
    # Final review PIPELINE-3 (the kNN trains on building-level years only): blocks 8 and 9 lose their RAÄ
    # records, then a dated Område covers them. Their 18 area years must not join the training pool: tested, the
    # cells and the estimate of the house in block 3 are those of the run without the Område.
    b, years, _, _ = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    late = b.fastighet.str.match(r"KV[89] ").to_numpy()
    recs = raa_recs(b, years, skip=late)
    zone = rec("zone", b[late].geometry.union_all().envelope.buffer(5.0), 1960, 1964, typ="Område")
    y0, base = s02_years.assign_years(b, raa(*recs), [], params=P)
    y, report = s02_years.assign_years(b, raa(*recs, zone), [], params=P)
    y0, y = y0.set_index("gid"), y.set_index("gid")
    assert (y.ysrc[b[late].gid] == SRC_RAA_AREA).all() and not (y0.ysrc[b[late].gid] == SRC_RAA_AREA).any()
    acc, acc0 = report["accuracy"], base["accuracy"]
    assert acc["tested"] == acc0["tested"] == 72
    assert [(c["era"], c["n"]) for c in acc["cells"]] == [(c["era"], c["n"]) for c in acc0["cells"]]
    assert (y.yflag[90], y.year[90]) == (y0.yflag[90], y0.year[90]) == (ESTIMATE, 1950)


def test_a_non_private_estimate_and_a_period_row_carry_their_ranges():
    # A city of small apartment blocks, with the levers turned off by default on 2026-10-15 (apartments estimated, a
    # period on its own when the band is too wide), so the row shapes stay pinned.
    b, years, _, _ = villa_blocks([(*inside(3), "Flerbostadshus", "KV3 10", 2003)])
    b.loc[b.kategori == "Enbostadshus", "kategori"] = "Flerbostadshus"     # a city of small apartment blocks
    recs = raa_recs(b, years)
    lever = dict(P, estimate_groups={"apartments"}, give_period=True)
    y, report = s02_years.assign_years(b, raa(*recs), [], params=P)
    assert y.set_index("gid").loc[90].yflag == UNKNOWN                        # the default: apartments not estimated
    y, report = s02_years.assign_years(b, raa(*recs), [], params=lever)
    row = y.set_index("gid").loc[90]
    assert (row.yflag, row.ysrc, row.private) == (ESTIMATE, SRC_ESTIMATE, False)
    assert 1950 <= row.year <= 1954 and (row.year_from, row.year_to) == (row.year - 5, row.year + 5)
    assert row.period == city.period_index(row.year)
    # the same city with the cell forced to PERIOD: the row keeps the estimate as its year and the period's span
    y, report = s02_years.assign_years(b, raa(*recs), [], params=dict(lever, max_band=1))
    row = y.set_index("gid").loc[90]
    assert (row.yflag, row.ysrc) == (PERIOD, SRC_ESTIMATE)
    assert 1950 <= row.year <= 1954 and (row.year_from, row.year_to) == (1946, 1964)      # p9 Folkhem & ABC towns
    assert report["accuracy"]["result"] == {"estimate": 0, "period": 1, "unknown": 0}


def test_an_estimate_at_the_latest_year_keeps_its_band_inside_the_bounds():
    # Review Focus #6: blocks built 2008..2026, so the estimate near block 9 is about 2025 and its ±5 band would
    # cross 2026. year_to is capped at 2026, year_from keeps the full width (the card reads "±5" from the larger
    # side), the period is p12 and s99's rules accept the row; forced to PERIOD, the span is 1994–2026.
    b, years, _, _ = villa_blocks([(*inside(9), "Flerbostadshus", "KV9 10", 2003)], base_year=2008)
    b.loc[b.kategori == "Enbostadshus", "kategori"] = "Flerbostadshus"
    recs = raa_recs(b, years)
    lever = dict(P, estimate_groups={"apartments"}, give_period=True)      # the defaults would leave it unknown
    y, _ = s02_years.assign_years(b, raa(*recs), [], params=lever)
    row = y.set_index("gid").loc[90]
    assert (row.yflag, row.ysrc) == (ESTIMATE, SRC_ESTIMATE)
    assert 2022 <= row.year <= 2026 and row.year_to == 2026 and row.year_from == row.year - 5
    assert row.period == city.period_index(int(row.year)) == 11                           # p12, "1994 on"
    assert s99_validate.check_attrs(attrs_of(row)) == []
    y, _ = s02_years.assign_years(b, raa(*recs), [], params=dict(lever, max_band=1))
    row = y.set_index("gid").loc[90]
    assert (row.yflag, row.year_from, row.year_to) == (PERIOD, 1994, 2026) and 2022 <= row.year <= 2026
    assert s99_validate.check_attrs(attrs_of(row)) == []


def test_a_private_period_row_publishes_its_decade_and_the_estimates_period():
    b, years, _, _ = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    y, _ = s02_years.assign_years(b, raa(*raa_recs(b, years)), [], params=dict(P, max_band=1, give_period=True))
    row = y.set_index("gid").loc[90]
    assert (row.yflag, row.private, row.year, row.year_from, row.year_to) == (PERIOD, True, 1950, 1950, 1959)
    assert row.period == city.period_index(1952)


def test_estimates_off_leaves_an_empty_table_that_still_describes_the_data():
    b = buildings(("u0", "Enbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)))
    y, report = run(b, raa(rec("a", sq(1), 1930, 1930, "u1")))
    assert y.yflag.tolist() == [UNKNOWN, EXACT]
    acc = report["accuracy"]
    # s99 checks tested (the building-level years) and result against stats.byFlag, --no-estimates builds included
    assert acc["cells"] == [] and acc["tested"] == 1 and acc["result"] == {"estimate": 0, "period": 0, "unknown": 1}
    assert acc["area"] == {"n": 0, "status": "not measurable"} and acc["external"] == NO_EXTERNAL
    assert set(report["review"]) == {"wikidata_vs_raa", "wikidata_vs_area", "wikidata_vs_curated", "osm_vs_raa",
                                     "wikidata_century", "wikidata_gains", "cited_vs_raa", "cited_vs_wikidata",
                                     "cited_vs_osm", "cited_no_period", "cited_period_vs_record"}


def test_summary_counts_every_tier():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)))
    y, _ = run(b, no_raa(), wikidata=wikidata(("Q0", 0, 1700, 1700, False)), osm=osm(("way/1", 1, 1800, 1800)))
    s = s02_years.summary(y.reset_index())
    assert set(s) == {"buildings", "curated", "cited", "raa", "raa_old", "raa_area", "wikidata", "osm", "reader", "estimate",
                      "period", "private", "unknown", "byFlag", "with_raa_id"}
    assert (s["wikidata"], s["osm"], s["unknown"], s["estimate"], s["period"]) == (1, 1, 1, 0, 0)


def test_main_writes_years_accuracy_and_review_and_guards_the_raa_link(tmp_path, monkeypatch, capsys, main_args):
    recs, args = main_args([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    s02_years.main(args())
    assert "no raa_old tier" in capsys.readouterr().err      # Review Focus #4: no snapshot, no tier, no stop
    y = pd.read_parquet(tmp_path / "years.parquet")
    assert y.yflag.tolist()[-1] == ESTIMATE and (y.raa_id != "").sum() == 90
    acc = json.loads((tmp_path / "accuracy.json").read_text())
    assert acc["result"] == {"estimate": 1, "period": 0, "unknown": 0} and acc["area"]["status"] == "not measurable"
    assert acc["external"] == NO_EXTERNAL
    assert json.loads((tmp_path / "review.json").read_text())["wikidata_gains"] == []
    # every RAÄ link gone (a changed URL prefix) stops the step before writing
    moved = [dict(x, url="https://other/" + x["url"].rsplit("/", 1)[-1]) for x in recs]
    monkeypatch.setattr(s02_years, "load_raa", lambda *_: raa(*moved))
    (tmp_path / "years.parquet").unlink()
    with pytest.raises(SystemExit, match="RAÄ link"):
        s02_years.main(args())
    assert not (tmp_path / "years.parquet").exists()
    # a missing Wikidata cache names the step to run
    nope = args()
    nope[nope.index("--wikidata") + 1] = str(tmp_path / "nope.json")
    with pytest.raises(SystemExit, match="s00_fetch_wikidata"):
        s02_years.main(nope)


def test_main_reads_the_property_unit_key_and_stops_without_it(tmp_path, monkeypatch, main_args):
    # Main loads fnr with the other building columns (s02_years.BUILDING_COLUMNS), so the
    # guard holds through the real entry point: the house on a late-formed unit stays unknown, its neighbour block's
    # house is estimated. A buildings.parquet written before 2026-10-15 (no fnr) would switch the guard off without a
    # word, so main stops and names the step to run.
    late = city.ESTIMATE["late_unit_fnr"] + 1
    _, args = main_args([(*inside(3), "Enbostadshus", "KV3 10", 2003, late), (*inside(7), "Enbostadshus", "KV7 10", 2003)])
    s02_years.main(args())
    y = pd.read_parquet(tmp_path / "years.parquet")
    assert y.yflag.tolist()[-2:] == [UNKNOWN, ESTIMATE]
    b = gpd.read_parquet(tmp_path / "buildings.parquet")
    b.drop(columns="fnr").to_parquet(tmp_path / "buildings.parquet")
    (tmp_path / "years.parquet").rename(tmp_path / "years-before.parquet")
    with pytest.raises(SystemExit, match=r"run s01_load first \(.*buildings.parquet has no fnr"):
        s02_years.main(args())
    assert not (tmp_path / "years.parquet").exists()


def test_two_main_runs_write_identical_years_and_accuracy(tmp_path, main_args):
    # The golden check for s02_years (Global Constraints, Output files): the kNN, the folds, the review list and the
    # table are deterministic. A real-data check repeats it across processes under two PYTHONHASHSEED values.
    _, args = main_args([(*inside(3), "Enbostadshus", "KV3 10", 2003), (*inside(7), "Enbostadshus", "KV7 10", 2003)])

    def run_once(tag):
        s02_years.main(args(tag))
        return [(tmp_path / f"{stem}{tag}.{ext}").read_bytes()
                for stem, ext in (("years", "parquet"), ("accuracy", "json"), ("review", "json"))]

    a, b = run_once("-a"), run_once("-b")
    ya, yb = pd.read_parquet(tmp_path / "years-a.parquet"), pd.read_parquet(tmp_path / "years-b.parquet")
    pd.testing.assert_frame_equal(ya, yb)
    assert a == b                                     # years.parquet, accuracy.json and review.json, byte for byte
    assert (ya.yflag == ESTIMATE).sum() == 2


def test_a_takedown_neither_trains_nor_tests_the_estimate():
    # A takedown (GDPR Art. 21: an objection stops the use, not only the display): a dated villa taken down is no anchor
    # for its neighbours' estimates and no test house; the run equals the one where RAÄ never dated it
    b, years, _, _ = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    gone = int(b.gid[b.fastighet == "KV3 1"].iloc[0])                     # a dated villa beside the estimated house
    never = (b.gid == gone).to_numpy()
    y0, base = s02_years.assign_years(b, raa(*raa_recs(b, years, skip=never)), [], params=P)
    y, report = s02_years.assign_years(b, raa(*raa_recs(b, years)), [], params=P, exclude={gone})
    pd.testing.assert_frame_equal(y, y0)                                   # every building, the estimates too
    assert report["accuracy"] == base["accuracy"]                          # tested, the cells, the checks
    full, _ = s02_years.assign_years(b, raa(*raa_recs(b, years)), [], params=P)
    assert full.set_index("gid").ysrc[gone] == SRC_RAA                     # without the takedown it is RAÄ-dated


def test_main_draws_a_takedown_as_unknown_and_counts_what_ships(tmp_path, main_args, capsys):
    # The estimated house (the last row) is taken down: "Year unknown", and the accuracy table's result and
    # tested follow, so s99 still finds the table describing the build
    _, args = main_args([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    uuid = gpd.read_parquet(tmp_path / "buildings.parquet").uuid.iloc[-1]
    (tmp_path / "suppress.yml").write_text(f"- uuid: {uuid}\n  date: 2026-11-02\n")
    s02_years.main(args() + ["--suppress", str(tmp_path / "suppress.yml")])
    y = pd.read_parquet(tmp_path / "years.parquet")
    assert (y.yflag.iloc[-1], y.year.iloc[-1], y.raa_id.iloc[-1]) == (UNKNOWN, 0, "")
    acc = json.loads((tmp_path / "accuracy.json").read_text())
    assert acc["result"] == {"estimate": 0, "period": 0, "unknown": 1}
    assert acc["tested"] == int(y.yflag.isin([EXACT, RANGE, LONG]).sum())
    assert "suppressed: 1 buildings" in capsys.readouterr().out
