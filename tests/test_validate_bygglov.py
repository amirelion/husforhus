"""s99's checks of the building-permit tier (pipeline/validate_bygglov.py): the accuracy block, the rows, the cards, the
shipped files and the release gate. Synthetic values only."""
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import city, codes, s03_tiles
from pipeline import validate_bygglov as vb
from pipeline.years_bygglov import FOOTPRINT_REASONS, MATCH_REASONS

NUMBERS = {"median_error": 0.0, "right_period": 0.95, "same_decade": 0.9, "within_1": 0.9, "within_3": 0.92,
           "exact": 0.8, "late_10": 0.0, "early_10": 0.01}


def good() -> dict:
    """stockholm.json's stats and accuracy with an applied block whose counts add up."""
    skipped = dict.fromkeys([*FOOTPRINT_REASONS, *MATCH_REASONS, "cell"], 0)
    skipped["no_card"] = 7
    block = {"status": "applied", **vb.expected(), "target": 10, "written": 3, "skipped": skipped,
             "cells": [{"group": "house", "inner": False, "era": "1920–1945", "episodes": 1, "n": 40,
                        "status": "dated", **NUMBERS},
                       {"group": "apartments", "inner": True, "era": "1946–1975", "episodes": 2, "n": 5,
                        "status": "not measurable"}],
             "test": {"n": 50, "used": 40, **NUMBERS}, "blind_spot": {"n": 40, "dated": 1, "share": 0.025},
             "others": {"osm": {"n": 2, "listed": 1, "same_period": 1}},
             "written_by_state": {"unknown": 2, "estimate": 1, "area": 0},
             "estimate_check": {"n": 1, "status": "not measurable"}, "shipped": {"n": 3, "exact": 1, "range": 2}}
    return {"stats": {"bySrc": {"bygglov": 3}}, "accuracy": {"bygglov": block}}


def edit(cfg, f):
    out = copy.deepcopy(cfg)
    f(out["accuracy"]["bygglov"])
    return out


def test_a_block_that_adds_up_passes_and_one_from_before_the_tier_too():
    assert vb.block(good()) == []
    assert vb.block({"stats": {"bySrc": {}}, "accuracy": {}}) == []
    assert vb.block({"stats": {"bySrc": {"bygglov": 3}}, "accuracy": {}}) == [
        "accuracy: stats has 3 permit years but the table has no bygglov block"]
    absent = {"stats": {"bySrc": {"bygglov": 0}}, "accuracy": {"bygglov": {"status": "absent", **vb.expected()}}}
    assert vb.block(absent) == []


@pytest.mark.parametrize(("change", "message"), [
    (lambda b: b["blind_spot"].update(dated=3), "3 of 40 buildings from 1981 or later get a permit year, over 5%"),
    (lambda b: b["cells"][0].update(right_period=0.8), "dates with a right_period under min_right 0.85"),
    (lambda b: b["cells"][0].update(same_decade=0.6), "dates with a same_decade under min_decade 0.7"),
    (lambda b: b["cells"][0].update(group="apartments"), "dates a group the tier does not date"),
    (lambda b: b["cells"][1].update(right_period=0.5), "status or numbers say otherwise"),
    (lambda b: b["shipped"].update(n=2, exact=0), "shipped is 2 but stats.bySrc has 3"),
    (lambda b: b["skipped"].update(no_card=6), "do not add up to target"),
    (lambda b: b["written_by_state"].update(area=1), "written_by_state does not add up to written"),
    (lambda b: b.update(min_right=0.5), "min_right is not city.BYGGLOV's"),
    (lambda b: b.update(status="maybe"), "a status of applied, absent or off"),
    (lambda b: b["test"].update(used=60), "test has used over n"),
    (lambda b: b["others"]["osm"].update(listed=3), "others is not a count per source"),
])
def test_a_block_that_does_not_add_up_fails(change, message):
    errors = vb.block(edit(good(), change))
    assert any(message in e for e in errors), errors


def test_an_unknown_key_is_counted_never_printed():
    errors = vb.block(edit(good(), lambda b: b.update({"TESTGÅRDEN 4": 1934})))
    assert errors == ["accuracy: bygglov has 1 keys outside the block's"]
    off = {"stats": {"bySrc": {"bygglov": 2}}, "accuracy": {"bygglov": {"status": "off", **vb.expected()}}}
    assert vb.block(off) == ["accuracy: stats has 2 permit years but the bygglov block reads not applied"]


def attrs(*rows) -> np.ndarray:
    """attrs.bin records (year, year_from, year_to, private) with ysrc SRC_BYGGLOV."""
    a = np.zeros(len(rows), dtype=s03_tiles.ATTR_DTYPE)
    for i, (y, f, t, p) in enumerate(rows):
        a[i]["year"], a[i]["year_from"], a[i]["year_to"], a[i]["private"] = y, f, t, p
        a[i]["ysrc"], a[i]["yflag"] = codes.SRC_BYGGLOV, codes.EXACT if f == t else codes.RANGE
    return a


def test_a_permit_year_is_a_closing_year_inside_the_index_and_a_cell_that_dates(tmp_path):
    ok = attrs((1934, 1931, 1934, 0), (1930, 1930, 1939, 1))
    assert vb.rows(ok, good()) == []
    assert vb.rows(attrs((1990, 1990, 1990, 0)), good()) == [
        "attrs: 1 permit-dated buildings whose year is not their closing year inside 1873..1985 (gids 0)"]
    assert "more than 10 years before it" in vb.rows(attrs((1934, 1920, 1934, 0)), good())[0]
    assert "a decade outside 1870..1980" in vb.rows(attrs((1990, 1990, 1999, 1)), good())[0]
    # with KATEGORI: the house's group and its decade reach the dated cell; an apartment block's does not
    pd.DataFrame({"gid": [0, 1], "kategori": ["Enbostadshus", "Flerbostadshus"]}).to_parquet(tmp_path / "buildings.parquet")
    two = attrs((1930, 1930, 1939, 1), (1934, 1934, 1934, 0))
    assert vb.rows(two, good(), tmp_path) == [
        "attrs: 1 permit-dated buildings whose type and year fall in no cell that dates (gids 1)"]
    # a 1940s house decade reaches the 1920-1945 cell (1940-1945); a 1950s one does not
    pd.DataFrame({"gid": [0], "kategori": ["Enbostadshus"]}).to_parquet(tmp_path / "buildings.parquet")
    assert vb.rows(attrs((1940, 1940, 1949, 1)), good(), tmp_path) == []
    assert vb.rows(attrs((1950, 1950, 1959, 1)), good(), tmp_path) != []


def test_a_permit_dated_card_carries_nothing_of_the_tier():
    a = attrs((1930, 1930, 1939, 1), (1934, 1934, 1934, 0))
    a[1]["ysrc"] = codes.SRC_RAA                    # gid 1 is RAÄ's: its card is not this check's
    shard = {"0": {"name": "Villa Provgården"}, "1": {"yc": {"s": "kulturnav"}}}
    assert vb.cards(Path("."), a, [(Path("00.json"), shard)]) == []
    for card, what in (({"yc": {"s": "kulturnav"}}, "carries `yc`"), ({"yrd": {"ref": "#1"}}, "carries `yrd`"),
                       ({"name": "Akt 2286/1934"}, "holds a string shaped like a case number")):
        errors = vb.cards(Path("."), a, [(Path("00.json"), {"0": card})])
        assert errors == [f"cards: 00.json gid 0 is permit-dated and {what}"], errors


def test_no_shipped_file_holds_the_permit_databases_path():
    files = [(Path("stockholm.json"), '{"url": "https://sok.stadsarkivet.stockholm.se/?id=4243&template=view_post"}'),
             (Path("cards/00.json"), '{"0": {"u": "https://sok.stadsarkivet.stockholm.se/Databas/bygglov1875-1980/Visa/12"}}')]
    assert vb.files(files) == ["privacy: cards/00.json holds the permit database's path (bygglov1875-1980): a card's "
                               "own page shows its designation and exact year"]


def test_a_full_city_release_needs_the_tier_applied(monkeypatch):
    absent = {"accuracy": {"bygglov": {"status": "absent"}}}
    assert vb.release(absent, city.MIN_BUILDINGS)[0].startswith("release: features.bygglov is on but the permit tier")
    assert vb.release(absent, 519) == []                       # a fixture build
    assert vb.release(good(), city.MIN_BUILDINGS) == []
    assert vb.release({"accuracy": {}}, city.MIN_BUILDINGS) != []  # a table from before the tier
    monkeypatch.setitem(city.FEATURES, "bygglov", False)
    assert vb.release(absent, city.MIN_BUILDINGS) == []
