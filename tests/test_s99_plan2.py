"""s99_validate's year-model rules: the ysrc pairing, year_from bounds, the period of a dated year, the
histogram sum, the accuracy table's shape and tiles against attrs. The `site` fixture and helpers come from
tests/test_s99_validate.py (the tiny city now has an estimate, a private period-only house and a Wikidata year)."""
import gzip
import json

import numpy as np
import pytest

from pipeline import city, codes, io, s03_tiles, s99_validate
from tests import tinycity
from tests.test_s99_validate import check, edit_attrs, site

__all__ = ["site"]   # the fixture, re-exported so pytest finds it here


def test_clean_build_with_plan2_rows_passes(site):
    assert check(site) == []


@pytest.mark.parametrize(("gid", "ysrc", "yflag", "message"), [
    (8, codes.SRC_RAA, codes.ESTIMATE, "yflag does not pair with their ysrc"),        # an estimate from RAÄ
    (9, codes.SRC_ESTIMATE, codes.EXACT, "yflag does not pair with their ysrc"),      # an exact estimate
    (0, codes.SRC_RAA_AREA, codes.EXACT, "yflag does not pair with their ysrc"),      # an exact area year
    (6, codes.SRC_RAA, codes.AREA, "yflag does not pair with their ysrc"),            # an area year from a record
    (7, codes.SRC_RAA, codes.UNKNOWN, "yflag does not pair with their ysrc"),         # unknown with a source
    (3, 9, codes.RANGE, "ysrc outside codes.py"),
])
def test_ysrc_must_pair_with_yflag(site, gid, ysrc, yflag, message):
    edit_attrs(site, lambda a: (a["ysrc"].__setitem__(gid, ysrc), a["yflag"].__setitem__(gid, yflag)))
    errors = [e for e in check(site) if message in e]
    assert len(errors) == 1 and f"gids {gid}" in errors[0]


def test_a_dated_year_from_must_be_at_least_1000(site):
    edit_attrs(site, lambda a: a["year_from"].__setitem__(10, 999))
    assert check(site) == ["attrs: 1 buildings dated with a year_from before 1000 (gids 10)"]


def test_a_dated_non_private_row_must_carry_its_years_period(site):
    # gid 8 is estimated 1952 (p9); a p10 period would contradict the year the shader times it by
    edit_attrs(site, lambda a: a["period"].__setitem__(8, 9))
    assert check(site) == ["attrs: 1 buildings dated and not private whose period is not their year's (gids 8)"]
    # Ruling F14: the private house gid 4 (decade 1960, real year 1968, p10) is clean above only because the rule
    # exempts private rows, which take the period from the real year: its period is not its decade's
    a = np.frombuffer(gzip.decompress((site / "attrs.bin.gz").read_bytes()), dtype=s03_tiles.ATTR_DTYPE)
    assert a["private"][4] == 1 and a["period"][4] != city.period_index(int(a["year"][4]))


def test_histograms_must_add_up_to_the_building_count(site):
    cfg = json.loads((site / "stockholm.json").read_text())
    cfg["unknown"] = 3
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["histograms: histogram + histogramEst + unknown is 12 but stats.buildings is 11"]


def test_accuracy_table_must_be_present_and_well_formed(site):
    cfg = json.loads((site / "stockholm.json").read_text())
    good = cfg["accuracy"]
    del cfg["accuracy"]
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["accuracy: stockholm.json has no accuracy table (run s02_years and s03_tiles)"]
    cfg["accuracy"] = json.loads(json.dumps(good))
    cfg["accuracy"]["cells"][1]["right_period"] = 0.9            # numbers on a cell with 5 test buildings
    cfg["accuracy"]["cells"][0]["status"] = "measured"            # not a status
    cfg["accuracy"]["cells"].append({"group": "work", "n": 40})   # fields missing
    io.write_json(site / "stockholm.json", cfg)
    errors = check(site)
    assert errors == ["accuracy: cells[0] has status 'measured'",
                      "accuracy: cells[1] has 5 test buildings (under 30) but is not 'not measurable'",
                      "accuracy: cells[2] lacks one of ['era', 'group', 'inner', 'n', 'status']"]


def test_the_accuracy_table_must_describe_the_shipped_data(site):
    # s03_tiles copies data/accuracy.json as it finds it, so a table from another s02_years run could ship: result must
    # equal stats.byFlag's ESTIMATE and PERIOD counts, tested the building-level years (exact + range + long)
    cfg = json.loads((site / "stockholm.json").read_text())
    cfg["accuracy"]["result"]["estimate"] = 0
    cfg["accuracy"]["tested"] = 40
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["accuracy: result says 0 estimate and 1 period but stats.byFlag has 1 and 1 (another build's table?)",
                           "accuracy: tested is 40 but the build has 6 building-level years (exact + range + long)"]


def test_the_accuracy_table_carries_only_contract_c10_keys(site):
    cfg = json.loads((site / "stockholm.json").read_text())
    cfg["accuracy"]["diagnostics"] = {"8": 1952}                      # a per-building leak into web data
    cfg["accuracy"]["cells"][0]["stadsdel"] = "Farsta"
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["accuracy: stockholm.json accuracy has keys outside the accuracy table's: ['diagnostics']",
                           "accuracy: cells[0] has keys outside the accuracy table's: ['stadsdel']"]


def test_the_fallback_rows_and_the_area_and_external_entries_carry_only_contract_c10_keys(site):
    # Ruling F15: the key pin covers the fallback rows and the area and external entries too, and an error never
    # prints a planted value (the rule: a key shows only if it looks like an identifier, else `[key #i]`; a
    # status shows only if it is a plain word)
    planted = "Södermalm Norra"                                       # a stadsdel name, as key or as value
    cfg = json.loads((site / "stockholm.json").read_text())
    acc = cfg["accuracy"]
    acc["cells"][0]["status"] = planted
    acc["fallback"][0].update({planted: 1234, "gid": 7})
    acc["fallback"].append(planted)                                   # a row that is no object at all
    acc["area"][planted] = 5678
    acc["external"]["diagnostics"] = {"8": 1952}
    io.write_json(site / "stockholm.json", cfg)
    errors = check(site)
    assert errors == ["accuracy: cells[0] has status [value]",
                      "accuracy: fallback[0] has keys outside the accuracy table's: ['[key #0]', 'gid']",
                      "accuracy: fallback[1] is not an object",
                      "accuracy: area has keys outside the accuracy table's: ['[key #0]']",
                      "accuracy: external has keys outside the accuracy table's: ['diagnostics']"]
    assert not any(planted in e or "1234" in e or "5678" in e for e in errors)


def edit_accuracy(out, fn):
    cfg = json.loads((out / "stockholm.json").read_text())
    fn(cfg["accuracy"])
    io.write_json(out / "stockholm.json", cfg)


def test_num_prints_an_int_or_a_float_and_nothing_else():
    assert [s99_validate.num(x) for x in (6, 0, 0.5, "Södermalm Norra", None, True, [1], {"a": 1})] == \
        ["6", "0", "0.5", "[value]", "[value]", "[value]", "[value]", "[value]"]


def test_a_non_numeric_table_value_is_a_readable_error_and_never_printed(site):
    # fix round 1: tested, result and the counts are printed through num(); a string there used to be echoed, and
    # a string n or min_cell raised a TypeError
    planted = "Södermalm Norra"
    def plant(acc):
        acc["tested"] = planted
        acc["result"]["estimate"] = planted
        acc["min_cell"] = planted
        acc["cells"][0]["n"] = planted
        acc["cells"][1]["n"] = [5]
        acc["fallback"][0]["n"] = None
    edit_accuracy(site, plant)
    errors = check(site)
    assert errors == ["accuracy: min_cell is [value] but the estimator uses 30 (another build's table?)",
                      "accuracy: cells[0] has an n that is not a whole number",
                      "accuracy: cells[1] has an n that is not a whole number",
                      "accuracy: fallback[0] has an n that is not a whole number",
                      "accuracy: result says [value] estimate and 1 period but stats.byFlag has 1 and 1 (another build's table?)",
                      "accuracy: tested is [value] but the build has 6 building-level years (exact + range + long)"]
    assert not any(planted in e for e in errors)


def test_the_table_must_carry_every_contract_c10_key(site):
    # fix round 1: no silent default for a missing key (min_cell used to default to 30), and no comparison against
    # a result or tested that is not there
    def strip(acc):
        for key in ("band_coverage", "min_cell", "area", "external", "result", "tested"):
            del acc[key]
    edit_accuracy(site, strip)
    assert check(site) == ["accuracy: stockholm.json accuracy lacks keys the accuracy table requires: "
                           "['area', 'band_coverage', 'external', 'min_cell', 'result', 'tested']"]


def test_area_external_cells_and_fallback_must_be_the_right_shape(site):
    def bend(acc):
        acc["area"] = []                         # present but not an object
        acc["external"] = {"n_all": 3}           # no status, and none of the other counts
        acc["result"] = [1, 1]
        acc["cells"] = {"0": 1}
        acc["fallback"] = "house"
        acc["by_true_period"] = {"p1": 1}
    edit_accuracy(site, bend)
    assert check(site) == ["accuracy: cells is not a list", "accuracy: fallback is not a list",
                           "accuracy: by_true_period is not a list",
                           "accuracy: area is not an object", "accuracy: external lacks a status",
                           "accuracy: external lacks one of ['before_1990', 'from_1990', 'in_band_estimate', "
                           "'n_estimate', 'n_unknown', 'right_estimate']",
                           "accuracy: result is not an object"]


@pytest.mark.parametrize("number", sorted(s99_validate.CELL_NUMBERS))
def test_a_small_cell_or_fallback_row_carries_no_number_at_all(site, number):
    # fix round 1 (a): "not measurable" under min_cell means none of median_error, right_period, within_one, band
    def add(acc):
        acc["cells"][1][number] = 1
        acc["fallback"].append({"group": "work", "inner": True, "n": 5, "status": "not measurable", number: 1})
    edit_accuracy(site, add)
    errors = check(site)
    assert errors[0] == "accuracy: cells[1] has 5 test buildings (under 30) but is not 'not measurable'"
    if number == "band":                          # a fallback row has no band: its key is outside the accuracy table's as well
        assert errors[1:] == ["accuracy: fallback[1] has 5 test buildings (under 30) but is not 'not measurable'",
                              "accuracy: fallback[1] has keys outside the accuracy table's: ['band']"]
    else:
        assert errors[1:] == ["accuracy: fallback[1] has 5 test buildings (under 30) but is not 'not measurable'"]


def test_a_status_that_is_not_a_string_is_a_readable_error(site):
    # fix round 1: a list or dict used to raise TypeError (unhashable) in the membership test
    def bend(acc):
        acc["cells"][0]["status"] = ["estimate"]
        acc["fallback"][0]["status"] = {"a": 1}
        acc["area"]["status"] = ["measured"]
        acc["external"]["status"] = 7
    edit_accuracy(site, bend)
    assert check(site) == ["accuracy: cells[0] has status [value]", "accuracy: fallback[0] has status [value]",
                           "accuracy: area has status [value]", "accuracy: external has status [value]"]


def test_the_table_must_use_the_estimators_thresholds(site):
    # fix round 1: min_cell, min_right and max_band are pinned to city.ESTIMATE, so a table built with other
    # thresholds cannot pass
    def other(acc):
        acc["min_cell"], acc["min_right"], acc["max_band"] = 10, 0.4, 25
    edit_accuracy(site, other)
    assert check(site) == ["accuracy: min_cell is 10 but the estimator uses 30 (another build's table?)",
                           "accuracy: min_right is 0.4 but the estimator uses 0.7 (another build's table?)",
                           "accuracy: max_band is 25 but the estimator uses 15 (another build's table?)"]


def test_a_place_name_as_a_group_or_an_era_is_a_readable_error_without_the_name(site):
    # fix round 1: the strings of a cell or fallback row are constrained to the estimator's groups and city's eras,
    # so a stadsdel name cannot ride along in them; a fallback row's status is checked too
    planted = "Södermalm Norra"
    def plant(acc):
        acc["cells"][0]["group"] = planted
        acc["cells"][0]["era"] = planted
        acc["cells"][1]["inner"] = "yes"
        acc["fallback"][0]["group"] = planted
        acc["fallback"][0]["status"] = "measured"
    edit_accuracy(site, plant)
    errors = check(site)
    assert errors == ["accuracy: cells[0] has a group outside the estimator's groups",
                      "accuracy: cells[0] has an era outside city.ERAS",
                      "accuracy: cells[1] has an inner that is not true or false",
                      "accuracy: fallback[0] has status 'measured'",
                      "accuracy: fallback[0] has a group outside the estimator's groups"]
    assert not any(planted in e for e in errors)


def test_a_table_with_no_measurable_cell_passes_and_a_large_cell_may_not_read_not_measurable():
    # Review Focus #5: a fixture build (519 buildings) measures nothing, and s99 must accept its table
    by_flag = {"exact": 0, "range": 0, "long": 0, "area": 0, "estimate": 0, "period": 0, "unknown": 11}
    acc = {**tinycity.ACCURACY, "tested": 0, "band_coverage": None, "result": {"estimate": 0, "period": 0, "unknown": 11},
           "cells": [{"group": "house", "era": "1946–1975", "inner": False, "n": 5, "status": "not measurable"}],
           "fallback": [{"group": "house", "inner": False, "n": 5, "status": "not measurable"}]}
    assert s99_validate.check_accuracy({"stats": {"byFlag": by_flag}, "accuracy": acc}) == []
    big = {**acc, "cells": [{"group": "house", "era": "1946–1975", "inner": False, "n": 40, "status": "not measurable"}]}
    assert s99_validate.check_accuracy({"stats": {"byFlag": by_flag}, "accuracy": big}) == \
        ["accuracy: cells[0] has 40 test buildings but reads 'not measurable'"]
    odd = {**acc, "external": {**acc["external"], "status": "estimate"}}
    assert s99_validate.check_accuracy({"stats": {"byFlag": by_flag}, "accuracy": odd}) == ["accuracy: external has status 'estimate'"]


def test_the_external_check_carries_its_counts_per_map_state_and_the_1990_split(site):
    # The accuracy table's external entry is the map's own rule run on the Wikidata/OSM-only buildings: whole-number
    # counts, the same four split at 1990, and "measured" only with at least min_cell "≈ year" buildings (else the
    # page prints the counts, never a percentage). A key, a split key or a value that could be a name is an error.
    def plant(acc):
        ext = acc["external"]
        ext.update(n_all=12, n_estimate=40, right_estimate="Södermalm Norra", n_unknown=2.5)
        ext["before_1990"] = {"n_all": 1, "n_estimate": 1, "right_estimate": 1, "gid": 7}
        ext["from_1990"] = [0]
    edit_accuracy(site, plant)
    errors = check(site)
    assert errors == ["accuracy: external right_estimate is not a whole number",
                      "accuracy: external n_unknown is not a whole number",
                      "accuracy: external.before_1990 lacks one of ['in_band_estimate', 'n_all', 'n_estimate', "
                      "'right_estimate']",
                      "accuracy: external.before_1990 has keys outside the accuracy table's: ['gid']",
                      "accuracy: external.from_1990 is not an object",
                      "accuracy: external has 40 '≈ year' buildings but reads 'not measurable'"]
    assert not any("Södermalm" in e for e in errors)
    edit_accuracy(site, lambda acc: acc["external"].update(
        status="measured", n_all=12, n_estimate=6, right_estimate=1, in_band_estimate=1, n_unknown=6,
        before_1990={"n_all": 2, "n_estimate": 1, "right_estimate": 1, "in_band_estimate": 1},
        from_1990={"n_all": 10, "n_estimate": 5, "right_estimate": 0, "in_band_estimate": 0}))
    assert check(site) == ["accuracy: external reads 'measured' with 6 '≈ year' buildings (under 30)"]
    edit_accuracy(site, lambda acc: acc["external"].update(status="not measurable"))
    assert check(site) == []


def test_an_estimate_cell_must_be_one_the_estimator_could_give(site):
    # A cell reads "estimate" only for a type in city.ESTIMATE's
    # estimate_groups, at least min_right right, with a band within max_band; another build's table, or a hand edit,
    # could otherwise ship and the page would print it. The cells' group is never printed.
    def plant(acc):
        good = acc["cells"][0]
        acc["cells"] += [dict(good, group="apartments"), dict(good, right_period=0.69), dict(good, band=20),
                         dict(good, right_period=0.7, band=15)]       # exactly at both thresholds: fine
    edit_accuracy(site, plant)
    assert check(site) == ["accuracy: cells[2] reads 'estimate' for a type the estimator does not estimate",
                           "accuracy: cells[3] reads 'estimate' with a right_period under min_right 0.7",
                           "accuracy: cells[4] reads 'estimate' with a band over max_band 15"]


def test_the_table_by_true_period_has_one_well_formed_row_per_period(site):
    # The cross-validation counted by the period of the true year (the page shows where it is weak):
    # whole-number counts, a period key from city.PERIODS, no other key.
    def plant(acc):
        rows = acc["by_true_period"]
        rows[0]["period"] = "Södermalm Norra"
        rows[1]["right"] = 0.5
        rows[2]["gid"] = 7
        del rows[3]["right_estimate"]
        rows.append("p13")
    edit_accuracy(site, plant)
    errors = check(site)
    assert errors == ["accuracy: by_true_period[0] has a period outside city.PERIODS",
                      "accuracy: by_true_period[1] right is not a whole number",
                      "accuracy: by_true_period[2] has keys outside the accuracy table's: ['gid']",
                      "accuracy: by_true_period[3] lacks one of ['n', 'n_estimate', 'period', 'right', "
                      "'right_estimate']",
                      "accuracy: by_true_period[12] is not an object"]
    assert not any("Södermalm" in e for e in errors)


def test_a_tile_whose_year_disagrees_with_attrs_fails(site):
    # The shader draws the tile's year, the count works from attrs; they must agree per gid
    cfg = json.loads((site / "stockholm.json").read_text())
    t = cfg["tiles"][0]
    blob = bytearray(gzip.decompress((site / t["pack"]).read_bytes()))
    nB = int(np.frombuffer(blob, "<u4", 1, t["offset"] + 4)[0])
    gid0 = int(np.frombuffer(blob, "<u4", 1, t["offset"] + 28)[0])
    year_at = t["offset"] + 28 + ((4 * nB + 3) // 4) * 4            # the i16 year array follows the padded gids
    blob[year_at:year_at + 2] = np.int16(1800).tobytes()
    io.write_gz(site / t["pack"], bytes(blob))
    errors = check(site)
    assert errors == [f"tiles: {t['file']} year disagrees with attrs for 1 gids (gids {gid0})"]


def test_known_and_estimated_flags_split_the_histograms():
    assert s03_tiles.KNOWN_FLAGS == (codes.EXACT, codes.RANGE, codes.LONG)
    assert s03_tiles.ESTIMATED_FLAGS == (codes.AREA, codes.ESTIMATE, codes.PERIOD)
    assert s03_tiles.SRC_NAMES == ["none", "curated", "raa", "raa_area", "wikidata", "estimate", "raa_old", "osm", "reader"]


# Final review PIPELINE-1: a measurable cell or fallback row carries its numbers, and no number or count is impossible
# (a hand-edited or stale table ships inside stockholm.json; About would print "18 (120%)").

@pytest.mark.parametrize("number", sorted(s99_validate.CELL_NUMBERS))
def test_a_measurable_cell_or_fallback_row_must_carry_its_numbers(site, number):
    def strip(acc):
        del acc["cells"][0][number]                      # n 35, at least min_cell
        acc["fallback"][0].pop(number, None)             # a fallback row has no band
    edit_accuracy(site, strip)
    cell = ("accuracy: cells[0] has 35 test buildings but lacks one of "
            "['band', 'median_error', 'right_period', 'within_one']")
    row = "accuracy: fallback[0] has 35 test buildings but lacks one of ['median_error', 'right_period', 'within_one']"
    assert check(site) == ([cell] if number == "band" else [cell, row])


def test_shares_lie_between_0_and_1_and_a_band_is_above_0(site):
    planted = "Södermalm Norra"
    def bend(acc):
        acc["cells"][0].update(right_period=1.7, within_one=-0.2, band=0)
        acc["cells"].append(dict(acc["cells"][0], right_period=0.8, within_one=planted, band=-5))
        acc["fallback"][0]["right_period"] = 1.01
        acc["band_coverage"] = 3.5
        acc["area"] = {"n": 39, "status": "measured", "median_error": 0.0, "right_period": planted}
    edit_accuracy(site, bend)
    errors = check(site)
    assert errors == ["accuracy: cells[0] right_period is not a share between 0 and 1",
                      "accuracy: cells[0] within_one is not a share between 0 and 1",
                      "accuracy: cells[0] band is not a number above 0",
                      "accuracy: cells[2] within_one is not a share between 0 and 1",
                      "accuracy: cells[2] band is not a number above 0",
                      "accuracy: fallback[0] right_period is not a share between 0 and 1",
                      "accuracy: band_coverage is not a share between 0 and 1",
                      "accuracy: area right_period is not a share between 0 and 1"]
    assert not any(planted in e for e in errors)
    edit_accuracy(site, lambda acc: (acc["cells"][0].update(right_period=1, within_one=0, band=5),
                                     acc["cells"].pop(), acc["fallback"][0].update(right_period=0.0),
                                     acc.update(band_coverage=1.0, area={"n": 39, "status": "measured",
                                                                         "median_error": 0.0, "right_period": 0})))
    assert check(site) == []                             # 0 and 1 are shares


def test_the_counts_by_true_period_are_possible(site):
    def bend(acc):
        rows = acc["by_true_period"]
        rows[1]["right"] = 4                             # n 0
        rows[2].update(n=5, right_estimate=1)            # n_estimate 0
        rows[3]["right_estimate"] = -1
        rows[8]["n_estimate"] = 40                       # p9: n 35
    edit_accuracy(site, bend)
    assert check(site) == ["accuracy: by_true_period[1] has right over n",
                           "accuracy: by_true_period[2] has right_estimate over n_estimate",
                           "accuracy: by_true_period[3] right_estimate is below 0",
                           "accuracy: by_true_period[8] has n_estimate over n"]


@pytest.mark.parametrize("edit", ["cut", "swap", "twice"])
def test_by_true_period_holds_exactly_one_row_per_period_in_order(site, edit):
    def bend(acc):
        rows = acc["by_true_period"]
        if edit == "cut":
            del rows[3:]
        elif edit == "swap":
            rows[0], rows[1] = rows[1], rows[0]
        else:
            rows.append(dict(rows[11]))
    edit_accuracy(site, bend)
    assert check(site) == ["accuracy: by_true_period does not hold one row per period of city.PERIODS, in order"]


def test_the_external_counts_are_possible(site):
    split = {"n_all": 5, "n_estimate": 40, "right_estimate": 25, "in_band_estimate": 20}
    def bend(acc):
        acc["external"].update(status="measured", n_all=10, n_estimate=40, right_estimate=50, in_band_estimate=41,
                               n_unknown=0, before_1990=split,
                               from_1990=dict(split, n_all=6, n_estimate=-1, right_estimate=-2))
    edit_accuracy(site, bend)
    assert check(site) == ["accuracy: external has right_estimate over n_estimate",
                           "accuracy: external has in_band_estimate over n_estimate",
                           "accuracy: external has n_estimate + n_unknown over n_all",
                           "accuracy: external.before_1990 has n_estimate over n_all",
                           "accuracy: external.from_1990 n_estimate is below 0",
                           "accuracy: external.from_1990 right_estimate is below 0",
                           "accuracy: external.from_1990 has in_band_estimate over n_estimate",
                           "accuracy: external n_all is not before_1990's plus from_1990's",
                           "accuracy: external n_estimate is not before_1990's plus from_1990's",
                           "accuracy: external right_estimate is not before_1990's plus from_1990's",
                           "accuracy: external in_band_estimate is not before_1990's plus from_1990's"]
    edit_accuracy(site, lambda acc: acc["external"].update(
        n_all=60, n_estimate=40, right_estimate=30, in_band_estimate=35, n_unknown=19,
        before_1990={"n_all": 50, "n_estimate": 38, "right_estimate": 30, "in_band_estimate": 34},
        from_1990={"n_all": 10, "n_estimate": 2, "right_estimate": 0, "in_band_estimate": 1}))
    assert check(site) == []                             # one PERIOD row: n_estimate + n_unknown under n_all
