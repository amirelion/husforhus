"""The building-permit tier inside s02_years.assign_years: what it fills and never touches, the review list, the
decade rule, takedowns, readers' reports, the estimate's check against it, and the accuracy block s99 reads. Synthetic
footprints and cards: every kvarter is made up (no real designation is written in a public file)."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from pipeline import city, s02_years, s99_validate, validate_bygglov
from pipeline import years_bygglov as yb
from pipeline.codes import (AREA, ESTIMATE, EXACT, RANGE, SRC_BYGGLOV, SRC_CURATED, SRC_ESTIMATE, SRC_NONE, SRC_OSM,
                            SRC_RAA, SRC_RAA_AREA, SRC_READER, SRC_WIKIDATA, UNKNOWN)
from tests import synth
from tests.test_s02_tiers import P, attrs_of, osm, raa_recs, wikidata, xy
from tests.test_s02_years import landmark_at, raa, rec, sq

# the measured rule with cells small enough for a dozen footprints, and the block check off
BP = {**city.BYGGLOV, "min_cell": 3, "block_years": None, "block_uncarded": None}


@pytest.fixture(autouse=True)
def pinned_private_house_set(monkeypatch):
    monkeypatch.setattr(city, "PRIVATE_HOUSE_KATEGORI", {"Enbostadshus", "Kolonistuga"})


def permits(*rows) -> pd.DataFrame:
    """years_bygglov.properties of cards (kvarter, nr, dnr, closing year)."""
    c = pd.DataFrame([{"id": i, "kvarter": k, "nr": nr, "dnr": dnr, "year": y, "akt": str(900 + i), "page": 0}
                      for i, (k, nr, dnr, y) in enumerate(rows, 1)], columns=yb.CARD_COLUMNS)
    return yb.properties(yb.keys(c), BP)


def town():
    """Slots 0-5: houses RAÄ dates 1932-1937, their cards the same year (the test). 6: an unknown house with a card.
    7: an unknown apartment block with one. 8: Wikidata says 1990, the card 1933. 9: OSM says 1931, the card 1935.
    10: a landmark (1934) with a card. 11: a takedown with a card. 12: area-dated with a card. 13: an unknown house a
    reader dates. 14: an unknown house with no card."""
    kinds = ["Enbostadshus"] * 7 + ["Flerbostadshus"] + ["Enbostadshus"] * 7
    b = gpd.GeoDataFrame({"gid": np.arange(15, dtype="int32"), "uuid": [f"u{i}" for i in range(15)],
                          "kategori": kinds, "fastighet": [f"TESTGÅRDEN {i + 1}" for i in range(15)]},
                         geometry=[sq(i) for i in range(15)], crs=3011)
    recs = [rec(f"r{i}", sq(i), 1932 + i, 1932 + i, f"u{i}") for i in range(6)]
    recs.append(rec("zone", sq(12, size=30, dx=-10, dy=-10), 1960, 1964, typ="Område"))
    cards = [("Testgården", str(i + 1), "", str(1932 + i)) for i in range(6)] + [
        ("Testgården", "7", "12/1931", "1934"), ("Testgården", "8", "", "1936"), ("Testgården", "9", "", "1933"),
        ("Testgården", "10", "", "1935"), ("Testgården", "11", "", "1934"), ("Testgården", "12", "", "1934"),
        ("Testgården", "13", "", "1934"), ("Testgården", "14", "", "1934")]
    return b, raa(*recs), permits(*cards)


def run(**kw):
    b, r, pr = town()
    args = dict(estimates=False, wikidata=wikidata(("Q8", 8, 1990, 1990, False)), osm=osm(("way/9", 9, 1931, 1931)),
                exclude={11}, bygglov=pr, bygglov_params=BP)
    args.update(kw)
    years, report = s02_years.assign_years(b, r, [landmark_at(*xy(10), name="Provhuset", year=1934, year_from=1934,
                                                              year_to=1934)], **args)
    return years.set_index("gid"), report


def test_it_fills_only_unknown_footprints_in_a_cell_measured_right():
    y, report = run()
    assert y.ysrc.tolist() == [SRC_RAA] * 6 + [SRC_BYGGLOV, SRC_NONE, SRC_WIKIDATA, SRC_OSM, SRC_CURATED, SRC_NONE,
                                               SRC_RAA_AREA, SRC_BYGGLOV, SRC_NONE]
    # a private house shows its decade; the period comes from the closing year; the opening year never ships
    assert (y.year[6], y.year_from[6], y.year_to[6], y.private[6]) == (1930, 1930, 1939, True)
    assert y.yflag[6] == RANGE and y.period[6] == city.period_index(1934)
    assert y.year[10] == 1934 and y.yflag[12] == AREA and y.yflag[11] == UNKNOWN and y.yflag[7] == UNKNOWN
    bg = report["accuracy"]["bygglov"]
    assert bg["status"] == "applied" and bg["written"] == 2 and bg["shipped"] == {"n": 2, "exact": 1, "range": 1}
    assert sum(bg["skipped"].values()) + bg["written"] == bg["target"]
    assert {k: v for k, v in bg["skipped"].items() if v} == {"takedown": 1, "no_card": 1, "cell": 1}
    assert bg["written_by_state"] == {"unknown": 2, "estimate": 0, "area": 0}
    # Wikidata's 1990 stays, and is listed against the permit year; OSM's 1931 stays, in the same period
    assert [e["gid"] for e in report["review"]["bygglov_vs_wikidata"]] == [8]
    assert report["review"]["bygglov_vs_osm"] == []
    assert bg["others"] == {"wikidata": {"n": 1, "listed": 1, "same_period": 0},
                            "osm": {"n": 1, "listed": 0, "same_period": 1}}
    assert s02_years.summary(y.reset_index())["bygglov"] == 2
    # what ships passes s99's row checks; a permit year is never LONG
    for g in (6, 13):
        assert s99_validate.check_attrs(attrs_of(y.loc[g])) == []


def test_an_area_year_stays_unless_fill_area_and_a_reader_replaces_a_permit_year_without_the_flag():
    y, _ = run(bygglov_params={**BP, "fill_area": True})
    assert y.ysrc[12] == SRC_BYGGLOV
    reader = pd.DataFrame({"ref": ["#7"], "year_from": [1996], "year_to": [1996], "replaces": [False]},
                          index=pd.Index([13], name="gid"))
    y, report = run(reader=reader)
    assert (y.ysrc[13], y.year[13]) == (SRC_READER, 1990)
    assert report["accuracy"]["bygglov"]["written"] == 2 and report["accuracy"]["bygglov"]["shipped"]["n"] == 1


def test_without_the_cards_the_tier_is_absent_and_writes_nothing():
    y, report = run(bygglov="absent")
    assert SRC_BYGGLOV not in set(y.ysrc) and report["accuracy"]["bygglov"] == yb.not_run("absent", BP)
    y, report = run(bygglov=None)
    assert report["accuracy"]["bygglov"]["status"] == "off"


def test_the_estimate_never_writes_over_a_permit_year_nor_trains_on_it_and_is_scored_against_it():
    # villa_blocks: 90 houses RAÄ dates 1946-1964 in 10 blocks; 10 more in the blocks, unknown, each with a card
    extra = [(blk * synth.PITCH + 0.5 * synth.STEP, 0.5 * synth.STEP, "Enbostadshus", f"KV{blk} 50", 2003)
             for blk in range(10)]
    b, years, _, _ = synth.villa_blocks(extra)
    cards = [(f"KV{blk}", str(n), "", str(1946 + 2 * blk)) for blk in range(10) for n in range(1, 10)]
    cards += [(f"KV{blk}", "50", "", str(1947 + 2 * blk)) for blk in range(10)]
    pr = yb.properties(yb.keys(pd.DataFrame([{"id": i, "kvarter": k, "nr": nr, "dnr": d, "year": yr, "akt": "",
                                              "page": 0} for i, (k, nr, d, yr) in enumerate(cards, 1)],
                                            columns=yb.CARD_COLUMNS)), BP)
    stadsdel = np.array(["FARSTA"] * len(b), dtype=object)
    common = dict(params=P, stadsdel=stadsdel, bygglov_params={**BP, "min_cell": 30})
    with_permits, report = s02_years.assign_years(b, raa(*raa_recs(b, years)), [], bygglov=pr, **common)
    without, report0 = s02_years.assign_years(b, raa(*raa_recs(b, years)), [], **common)
    new = with_permits.ysrc.to_numpy() == SRC_BYGGLOV
    assert new.sum() == 10 and (without.ysrc.to_numpy()[new] == SRC_ESTIMATE).all()
    # the cross-validation is the same with or without them: they neither train nor test it
    acc, acc0 = report["accuracy"], report0["accuracy"]
    assert acc["cells"] == acc0["cells"] and acc["tested"] == acc0["tested"] == 90
    # the check: the estimates the permit-dated houses would have had, against their permit years
    assert acc["bygglov"]["estimate_check"] == {"n": 10, "status": "not measurable"}      # under min_cell
    # with min_cell 10 the ten are scored: each estimate against its house's permit year
    _, scored = s02_years.assign_years(b, raa(*raa_recs(b, years)), [], bygglov=pr,
                                       **{**common, "bygglov_params": {**BP, "min_cell": 10}})
    check = scored["accuracy"]["bygglov"]["estimate_check"]
    assert check["n"] == 10 and check["status"] == "measured" and 0 <= check["right_period"] <= 1
    assert acc["bygglov"]["written_by_state"] == {"unknown": 0, "estimate": 10, "area": 0}
    # the table counts what ships, as s99 ties it to stats.byFlag
    assert acc["result"]["estimate"] == int((with_permits.yflag == ESTIMATE).sum()) == 0
    assert acc["result"]["unknown"] == int((with_permits.yflag == UNKNOWN).sum())


def test_s99_reads_the_block_s02_years_writes(monkeypatch):
    y, report = run()
    cfg = {"stats": {"bySrc": {"bygglov": int((y.ysrc == SRC_BYGGLOV).sum())}},
           "accuracy": {"bygglov": report["accuracy"]["bygglov"]}}
    # this test's levers (min_cell 3, no block check) are not city.BYGGLOV's: s99 says so, and is quiet with them
    assert validate_bygglov.block(cfg) == [f"accuracy: bygglov {k} is not city.BYGGLOV's (another build's block?)"
                                           for k in ("min_cell",)]
    monkeypatch.setattr(city, "BYGGLOV", BP)
    assert validate_bygglov.block(cfg) == []
    assert EXACT in set(y.yflag[y.ysrc == SRC_BYGGLOV])
