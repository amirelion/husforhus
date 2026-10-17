"""The estimate tier (Plan 2, Task 6; Task 14b's safer rule): kNN, the kvarter-held-out accuracy table and the
ESTIMATE/PERIOD/UNKNOWN rule, on a synthetic city of villa blocks whose years are known (tests.synth.villa_blocks)."""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pytest
from shapely.geometry import box

from pipeline import city, estimate
from pipeline.codes import ESTIMATE, PERIOD, UNKNOWN
from tests import synth
from tests.synth import PITCH, STEP, villa_blocks

HOUSE, FLATS = estimate.GROUP_CODE["house"], estimate.GROUP_CODE["apartments"]
# The measured rule, whatever product default the project picks at M3 (Task 14 may set far_rule or period_only_stadsdelar
# in city.ESTIMATE): the synthetic expectations below do not move with it.
P = dict(city.ESTIMATE, far_rule="unknown", period_only_stadsdelar=set())
# The rule as Task 6 measured it, before Task 14b (min_right 0.5, period-only on): the levers still work.
OLD = dict(P, min_right=0.5, give_period=True)
LATE_UNIT = city.ESTIMATE["late_unit_fnr"]


def inside(block, i=0.5, j=0.5):
    """Local (dx, dz) of a point between the houses of block `block`."""
    return block * PITCH + i * STEP, j * STEP


def frame(xy, kvarter) -> pd.DataFrame:
    """A feature frame (estimate.features' columns) of identical houses at the given (x, y) metres in one kvarter."""
    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    return pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1], "logh": np.log(6.0), "loga": np.log(64.0), "compact": 0.785,
                         "group": HOUSE, "inner": False, "kvarter": np.int64(kvarter), "prod_year": 2003,
                         "fnr": np.int64(10_100_000)})


def ring(r, n=20):
    """n points r metres from (0, 0), evenly spaced."""
    a = 2 * np.pi * np.arange(n) / n
    return np.c_[r * np.cos(a), r * np.sin(a)]


def scattered(west, east=None, middle=(1950, 1950, 1950)):
    """villa_blocks with every block's years set by column (0: no year): `west`, `middle` and `east` (default: west).
    Only the west and east columns are tested (the middle one is 105 m from the next block), and every block pair
    split across folds tests one west and one east column, so these two set a cell's error spread and share in the
    right period. Returns (features, years, dated)."""
    b, _, _, _ = villa_blocks()
    east = west if east is None else east
    years = np.tile(np.r_[west, middle, east].astype(np.int64), 10)   # house i * 3 + j is in column i
    return estimate.features(b), years, years > 0


def test_features_groups_kvarter_and_inner():
    b = synth.buildings(rows=[
        {"kategori": "Enbostadshus", "fastighet": "STORKEN 12"}, {"kategori": "Enbostadshus", "fastighet": "STORKEN 13"},
        {"kategori": "Flerbostadshus", "fastighet": "SUNDBY 5:6"}, {"kategori": "Kolonistuga", "fastighet": ""},
        {"kategori": "Something new", "fastighet": "SUNDBY 5:7"},
    ])
    f = estimate.features(b, stadsdel=np.array(["GAMLA STAN", "FARSTA", "FARSTA", "FARSTA", "FARSTA"], dtype=object))
    assert list(f.columns) == ["x", "y", "logh", "loga", "compact", "group", "inner", "kvarter", "prod_year", "fnr"]
    assert f.group.tolist() == [HOUSE, HOUSE, FLATS, estimate.GROUP_CODE["cottage"], estimate.GROUP_CODE["unspecified"]]
    assert f.kvarter[0] == f.kvarter[1] and f.kvarter[2] == f.kvarter[4] != f.kvarter[0]   # kvarter, trakt block
    assert f.kvarter[3] not in (f.kvarter[0], f.kvarter[2])                                 # a grid cell stands in
    assert f.inner.tolist() == [True, False, False, False, False]
    assert (f.prod_year == 2003).all()                   # synth.buildings: first digitised in 2003, before the late gate
    assert f.fnr.tolist() == b.fnr.tolist() and str(f.fnr.dtype) == "int64"    # the property-unit key, carried as is
    assert (estimate.features(b.drop(columns="fnr")).fnr == 0).all()          # no key: 0, never guarded
    assert np.allclose(f.loga, np.log(100.0)) and np.allclose(f.logh, np.log(20.0))


def test_knn_takes_the_neighbours_year_and_the_distance_to_the_nearest():
    b, years, dated, _ = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    f = estimate.features(b)
    yhat, d1 = estimate.knn(f[dated], years[dated], f[~dated])
    assert abs(yhat[0] - 1952) <= 2        # block 3 was built in 1946 + 2 * 3
    assert 5 < d1[0] < 20                  # metres to the nearest house of the block
    none_y, none_d = estimate.knn(f[dated].iloc[:0], years[:0], f[~dated])
    assert np.isnan(none_y[0]) and np.isinf(none_d[0])


def test_cross_validation_measures_the_house_cell():
    b, years, dated, _ = villa_blocks()
    table = estimate.cross_validate(estimate.features(b), years, dated)
    assert set(table) == set(estimate.CV_KEYS)
    assert table["tested"] == 90 and table["held_out"] == "kvarter" and table["folds"] == 5
    cells = {(c["group"], c["era"], c["inner"]): c for c in table["cells"]}
    cell = cells[("house", "1946–1975", False)]
    assert cell["n"] >= 30 and cell["status"] == "estimate" and cell["band"] == 5
    # 2 y: a held-out block's nearest dated houses are the next blocks' (2 y apart). Folds that let a block's own
    # houses train (not whole kvarter) would give 0.
    assert cell["right_period"] == 1.0 and cell["median_error"] == 2 and cell["within_one"] == 1.0
    assert all(c["status"] == "not measurable" and "band" not in c for c in table["cells"] if c["n"] < 30)
    fb = {(r["group"], r["inner"]): r for r in table["fallback"]}
    # Task 14b: the fallback never gives a period on its own any more (give_period=False): it reads what the map does
    assert fb[("house", False)]["status"] == "unknown" and fb[("house", False)]["n"] == cell["n"]
    assert estimate.cross_validate(estimate.features(b), years, dated, OLD)["fallback"][0]["status"] == "period"
    assert 0.0 <= table["band_coverage"] <= 1.0
    # by the period of the true year: every villa is from 1946..1964 (p9), all of them in the "≈ year" cell
    by = {r["period"]: r for r in table["by_true_period"]}
    assert [r["period"] for r in table["by_true_period"]] == [p[0] for p in city.PERIODS]
    assert by["p9"] == {"period": "p9", "n": cell["n"], "right": cell["n"], "n_estimate": cell["n"],
                        "right_estimate": cell["n"]}
    assert all(r["n"] == r["right"] == r["n_estimate"] == r["right_estimate"] == 0 for k, r in by.items() if k != "p9")


def test_the_kvarter_bonus_reranks_only_the_candidates_each_group_tree_returns():
    # The plan's approximation (the full add-on measured 0.1 y of gain): the bonus re-ranks the at most k candidates
    # each group's tree returns. 20 own-kvarter houses at 80 m stay behind 20 kvarter-1 houses at 50 m.
    q = frame([0.0, 0.0], kvarter=2)
    train = pd.concat([frame(ring(50.0), kvarter=1), frame(ring(80.0), kvarter=2)], ignore_index=True)
    years = np.r_[np.full(20, 1950), np.full(20, 1980)]
    for bonus in (0.0, 0.5):
        yhat, d1 = estimate.knn(train, years, q, P, kvarter_bonus=bonus)
        assert yhat[0] == 1950 and np.isclose(d1[0], 50.0)
    # Returned as candidates (k = 40), the same bonus lets them win: the limit is the tree's top k, not the bonus.
    assert estimate.knn(train, years, q, dict(P, k=40), kvarter_bonus=0.5)[0][0] == 1980
    # An own-kvarter house among the group's raw top k (k = 3: two kvarter-1 houses at 50 m, it at 80 m, ten more
    # kvarter-1 houses at 200 m): the bonus takes its distance to 0, first place, and its weight 1 / eps outweighs
    # the other two, so its year becomes the median.
    train = pd.concat([frame(ring(50.0, 2), kvarter=1), frame([80.0, 0.0], kvarter=2), frame(ring(200.0, 10), kvarter=1)],
                      ignore_index=True)
    years = np.r_[1950, 1950, 1980, np.full(10, 1950)]
    k3 = dict(P, k=3)
    assert estimate.knn(train, years, q, k3)[0][0] == 1950
    assert estimate.knn(train, years, q, k3, kvarter_bonus=0.5)[0][0] == 1980


def test_cross_validation_derives_period_and_unknown_from_the_data():
    # Every block mostly 1950 (so every estimate is 1950); the other houses 40 years off, in other periods. Under the
    # levers Task 6 measured (OLD: min_right 0.5, period-only on).
    cases = [([(1950, 1950, 1990)], "period", 0.667, 0),                        # right enough, P80 error 40 y > max_band
             ([(1950, 1990, 1910)], "unknown", 0.333, 40),                      # a third right < min_right
             ([(1950, 1950, 1990), (1950, 1990, 1990)], "period", 0.5, 20)]    # exactly half right: >= min_right
    for columns, status, right, median_error in cases:
        f, years, dated = scattered(*columns)
        table = estimate.cross_validate(f, years, dated, OLD)
        assert [(c["group"], c["era"], c["status"]) for c in table["cells"]] == [("house", "1946–1975", status)]
        cell = table["cells"][0]
        assert cell["n"] >= 30 and cell["right_period"] == right and cell["band"] == 40
        assert cell["median_error"] == median_error
        assert [r["status"] for r in table["fallback"]] == ["unknown" if status == "unknown" else "period"]
        # Task 14b's rule on the same data: no cell gives a period on its own, so every one reads "unknown"
        new = estimate.cross_validate(f, years, dated, P)
        assert [c["status"] for c in new["cells"]] == ["unknown"] and new["cells"][0]["right_period"] == right
        assert [r["status"] for r in new["fallback"]] == ["unknown"]


def test_a_cell_needs_seven_in_ten_right_for_an_estimate():
    # Task 14b: min_right 0.7. Two in three houses of every tested column at 1950, the third at 1945 (Funkis, so in
    # another period but only 5 years off): every estimate is 1950, two thirds are right and the band is 5, so only
    # the share right decides. It was an estimate under 0.5 and is unknown now.
    f, years, dated = scattered((1950, 1950, 1945))
    old, new = (estimate.cross_validate(f, years, dated, p)["cells"][0] for p in (OLD, P))
    assert old["right_period"] == new["right_period"] == 0.667 and new["band"] == 5
    assert (old["status"], new["status"]) == ("estimate", "unknown")


def test_no_dated_building_means_an_empty_table_and_no_estimate():
    b, years, dated, query = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    f = estimate.features(b)
    out, table = estimate.run(f, years, np.zeros(len(b), bool), np.ones(len(b), bool))
    assert table["tested"] == 0 and table["cells"] == [] and table["band_coverage"] is None
    assert (out.yflag == UNKNOWN).all() and out.yhat.isna().all()
    assert table["result"] == {"estimate": 0, "period": 0, "unknown": len(b)}


def test_decide_estimates_near_houses_and_leaves_the_rest_unknown():
    extra = [
        (*inside(3), "Enbostadshus", "KV3 10", 2003),          # a villa among dated villas: ESTIMATE
        (5000.0, 0.0, "Enbostadshus", "FAR 1", 2003),          # 5 km from any dated building: UNKNOWN
        (*inside(3, 1.5, 0.5), "Kolonistuga", "KV3 11", 2003),  # an allotment cottage: never estimated
        (*inside(4), "Enbostadshus", "KV4 10", 2010),           # first digitised in 2010: probably new, UNKNOWN
        (*inside(6), "Flerbostadshus", "KV6 10", 2003),         # no measurable cell or fallback for apartments
        (*inside(3, 2.5, 0.5), "Enbostadshus", "NYKVARTER 1", 2003),   # a kvarter of its own among dated blocks: ESTIMATE
    ]
    b, years, dated, query = villa_blocks(extra)
    f = estimate.features(b)
    assert f.kvarter[len(b) - 1] not in set(f.kvarter[:-1])            # the kvarter bonus has nothing to apply to
    out, table = estimate.run(f, years, dated, query, p=P)
    got = out[query]
    assert got.yflag.tolist() == [ESTIMATE, UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN, ESTIMATE]
    assert got.band.tolist() == [5, 0, 0, 0, 0, 5]
    assert abs(got.yhat.iloc[0] - 1952) <= 2 and got.d1.iloc[1] > 1000 and abs(got.yhat.iloc[5] - 1952) <= 2
    assert table["result"] == {"estimate": 2, "period": 0, "unknown": 4}
    assert (out.yflag[dated] == UNKNOWN).all() and out.yhat[dated].isna().all()   # dated rows are not estimated

    # The period levers: with period-only on, the far one gets its period (far_rule) and the apartment block in a
    # period-only stadsdel its period (not the far one, the cottage or the late one). Task 14b: with give_period=False
    # (the default) neither lever can produce a PERIOD.
    sd = np.array(["TEST"] * len(b), dtype=object)
    for give, far_flags, gamla_flags in ((True, [ESTIMATE, PERIOD, UNKNOWN, UNKNOWN, UNKNOWN, ESTIMATE],
                                          [ESTIMATE, UNKNOWN, UNKNOWN, UNKNOWN, PERIOD, ESTIMATE]),
                                         (False, [ESTIMATE, UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN, ESTIMATE],
                                          [ESTIMATE, UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN, ESTIMATE])):
        lever = dict(P, give_period=give, estimate_groups={"house", "apartments"})
        out, _ = estimate.run(f, years, dated, query, p=dict(lever, far_rule="period"))
        assert out[query].yflag.tolist() == far_flags
        out, _ = estimate.run(f, years, dated, query, p=dict(lever, period_only_stadsdelar={"TEST"}), stadsdel=sd)
        assert out[query].yflag.tolist() == gamla_flags


def test_a_wide_band_or_a_wrong_cell_gives_period_or_unknown():
    b, years, dated, query = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003)])
    f = estimate.features(b)
    table = estimate.cross_validate(f, years, dated, OLD)
    yhat, d1 = estimate.knn(f[dated], years[dated], f[query], OLD)
    cell = next(c for c in table["cells"] if c["status"] == "estimate")
    cell["status"], cell["band"] = "period", 25
    assert estimate.decide(f[query], yhat, d1, table, OLD)[0].tolist() == [PERIOD]
    assert estimate.decide(f[query], yhat, d1, table, P)[0].tolist() == [UNKNOWN]   # Task 14b: never a period alone
    cell["status"] = "unknown"
    assert estimate.decide(f[query], yhat, d1, table, OLD)[0].tolist() == [UNKNOWN]
    cell["status"] = "not measurable"
    assert estimate.decide(f[query], yhat, d1, table, OLD)[0].tolist() == [PERIOD]     # the group x outer fallback
    assert estimate.decide(f[query], yhat, d1, table, P)[0].tolist() == [UNKNOWN]      # ... not without give_period
    table["fallback"] = []
    assert estimate.decide(f[query], yhat, d1, table, OLD)[0].tolist() == [UNKNOWN]


def test_only_houses_are_estimated_and_the_other_types_are_still_measured():
    # Task 14b rule 1: the same villa city built of small apartment blocks. Their cell is measured as well as the
    # houses' (every one right, band 5), but the map leaves the type unknown, and the table says so.
    b, years, dated, query = villa_blocks([(*inside(3), "Flerbostadshus", "KV3 10", 2003)])
    b["kategori"] = "Flerbostadshus"
    f = estimate.features(b)
    out, table = estimate.run(f, years, dated, query, p=P)
    [cell] = table["cells"]
    assert (cell["group"], cell["n"], cell["right_period"], cell["band"]) == ("apartments", 42, 1.0, 5)
    assert cell["status"] == "unknown" and table["fallback"][0]["status"] == "unknown"
    assert out[query].yflag.tolist() == [UNKNOWN] and table["result"] == {"estimate": 0, "period": 0, "unknown": 1}
    assert [r["n_estimate"] for r in table["by_true_period"]] == [0] * len(city.PERIODS)
    out, table = estimate.run(f, years, dated, query, p=dict(P, estimate_groups={"house", "apartments"}))
    assert table["cells"][0]["status"] == "estimate" and out[query].yflag.tolist() == [ESTIMATE]


def test_decide_itself_estimates_only_the_estimate_groups_whatever_the_table_says():
    # Task 14b review (M2 a): decide's own group gate, not only status_of's. A table whose apartment cell reads
    # "estimate" (built with apartments allowed) still gives an apartment block nothing under the default rule, and a
    # far apartment block gets no period from far_rule even with the period levers on.
    b, years, dated, query = villa_blocks([(*inside(3), "Flerbostadshus", "KV3 10", 2003),
                                           (5000.0, 0.0, "Flerbostadshus", "FAR 1", 2003)])
    b["kategori"] = "Flerbostadshus"
    f = estimate.features(b)
    flats = dict(P, estimate_groups={"house", "apartments"})
    table = estimate.cross_validate(f, years, dated, flats)
    assert table["cells"][0]["status"] == "estimate"
    yhat, d1 = estimate.knn(f[dated], years[dated], f[query], P, kvarter_bonus=P["kvarter_bonus"])
    assert estimate.decide(f[query], yhat, d1, table, flats)[0].tolist() == [ESTIMATE, UNKNOWN]
    assert estimate.decide(f[query], yhat, d1, table, P)[0].tolist() == [UNKNOWN, UNKNOWN]
    levers = dict(P, give_period=True, far_rule="period")
    assert estimate.decide(f[query], yhat, d1, table, levers)[0].tolist() == [UNKNOWN, UNKNOWN]
    assert estimate.decide(f[query], yhat, d1, table, dict(levers, estimate_groups={"house", "apartments"}))[0].tolist() \
        == [ESTIMATE, PERIOD]


def test_the_external_check_uses_the_production_kvarter_bonus():
    # Task 14b review (M2 b): check_external runs knn with the kvarter bonus, as the map does. k = 3: two kvarter-1
    # houses at 50 m (1950) and one in the test house's own kvarter at 80 m (1980), ten more kvarter-1 houses at 200
    # m. With the bonus the kvarter-mate wins (1980, the true year, an "estimate" cell); without it, 1950 lands in a
    # cell that reads "unknown".
    k3 = dict(P, k=3)
    train = pd.concat([frame(ring(50.0, 2), kvarter=1), frame([80.0, 0.0], kvarter=2), frame(ring(200.0, 10), kvarter=1)],
                      ignore_index=True)
    f = pd.concat([train, frame([0.0, 0.0], kvarter=2)], ignore_index=True)
    years = np.r_[1950, 1950, 1980, np.full(10, 1950), 1980].astype(float)
    test_row = np.arange(len(f)) == len(f) - 1
    table = {"cells": [{"group": "house", "era": "1976–1993", "inner": False, "n": 40, "status": "estimate", "band": 5},
                       {"group": "house", "era": "1946–1975", "inner": False, "n": 40, "status": "unknown"}],
             "fallback": []}
    ext = estimate.check_external(f, years, ~test_row, test_row, table, k3)
    assert (ext["n_estimate"], ext["right_estimate"], ext["in_band_estimate"], ext["n_unknown"]) == (1, 1, 1, 0)
    assert ext["from_1990"]["n_all"] == 0 and ext["before_1990"]["n_estimate"] == 1


def test_the_external_check_is_measured_by_its_estimates_not_by_its_rows():
    # Task 14b review (M2 d): the status comes from n_estimate. The ring's 20 test houses all sit more than 100 m from
    # the training houses, so none is estimated: 20 rows (over min_cell 5) but 0 estimates reads "not measurable".
    train = frame(ring(30.0), kvarter=1)
    far = frame(ring(400.0), kvarter=2)
    f = pd.concat([train, far], ignore_index=True)
    years = np.r_[np.full(20, 1950), np.full(20, 1950)].astype(float)
    test_rows = np.arange(len(f)) >= 20
    table = {"cells": [{"group": "house", "era": "1946–1975", "inner": False, "n": 40, "status": "estimate", "band": 5}],
             "fallback": []}
    ext = estimate.check_external(f, years, ~test_rows, test_rows, table, dict(P, min_cell=5))
    assert (ext["n_all"], ext["n_estimate"], ext["n_unknown"], ext["status"]) == (20, 0, 20, "not measurable")
    near = estimate.check_external(pd.concat([train, frame(ring(40.0), kvarter=2)], ignore_index=True), years,
                                   ~test_rows, test_rows, table, dict(P, min_cell=5))
    assert (near["n_estimate"], near["status"]) == (20, "measured")


def test_a_house_on_a_late_formed_property_unit_is_not_estimated():
    # Task 14b rule 4 (the FNR guard): a key above late_unit_fnr is a property unit formed late, mostly new
    # development, so the house stays unknown; at the cut, or with no key (0), it is estimated.
    b, years, dated, query = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003, LATE_UNIT + 1),
                                           (*inside(3, 1.5), "Enbostadshus", "KV3 11", 2003, LATE_UNIT),
                                           (*inside(3, 2.5), "Enbostadshus", "KV3 12", 2003, 0)])
    out, table = estimate.run(estimate.features(b), years, dated, query, p=P)
    assert out[query].yflag.tolist() == [UNKNOWN, ESTIMATE, ESTIMATE]
    assert np.isfinite(out[query].yhat).all()                 # estimated, then held back by the rule
    out, _ = estimate.run(estimate.features(b), years, dated, query, p=dict(P, late_unit_fnr=LATE_UNIT + 1))
    assert out[query].yflag.tolist() == [ESTIMATE, ESTIMATE, ESTIMATE]


def test_the_table_scores_only_buildings_the_map_could_estimate_but_all_of_them_train():
    # Task 14b rule 5. Seven blocks' houses are scored (3 or 6 each, 42 in all; the folds hold whole blocks out).
    # Block 1 first digitised in 2010 and block 6 on late-formed units (6 scored each) still train but are not scored:
    # 30 left. Block 2's key is exactly at the cut, so it is still scored.
    b, years, dated, query = villa_blocks([(*inside(1), "Enbostadshus", "KV1 10", 2003)])
    block = b.fastighet.str.extract(r"^KV(\d+) ")[0].astype(float).to_numpy()
    base = estimate.cross_validate(estimate.features(b), years, dated, P)
    b.loc[(block == 1) & dated, "prod_year"] = 2010            # not the query house, which is in kvarter KV1 too
    b.loc[block == 6, "fnr"] = LATE_UNIT + 1
    b.loc[block == 2, "fnr"] = LATE_UNIT
    f = estimate.features(b)
    table = estimate.cross_validate(f, years, dated, P)
    assert table["tested"] == base["tested"] == 90                             # the pool: every dated building
    assert (base["cells"][0]["n"], table["cells"][0]["n"]) == (42, 30)
    assert table["cells"][0]["status"] == "estimate" and table["by_true_period"][8]["n"] == 30
    # block 1 trains: the house among its villas gets block 1's 1948, not its neighbours' 1946 or 1950
    out, _ = estimate.run(f, years, dated, query, p=P)
    assert out[query].yflag.tolist() == [ESTIMATE] and abs(out[query].yhat.iloc[0] - 1948) <= 1
    # dated cottages (a group the map never estimates) are not scored at all: no cottage cell
    b.loc[block == 8, "kategori"] = "Kolonistuga"
    groups = {c["group"] for c in estimate.cross_validate(estimate.features(b), years, dated, P)["cells"]}
    assert "cottage" not in groups
    assert "cottage" in {c["group"] for c in estimate.cross_validate(estimate.features(b), years, dated,
                                                                       dict(P, never_groups=set()))["cells"]}


def test_runs_are_deterministic():
    b, years, dated, query = villa_blocks([(*inside(3), "Enbostadshus", "KV3 10", 2003), (*inside(7), "Enbostadshus", "KV7 10", 2003)])
    f = estimate.features(b)
    a, ta = estimate.run(f, years, dated, query, p=P)
    c, tc = estimate.run(f, years, dated, query, p=P)
    pd.testing.assert_frame_equal(a, c)
    assert ta == tc


def test_group_folds_hold_out_whole_groups_and_balance():
    groups = np.repeat(np.arange(10), [30, 20, 10, 10, 10, 5, 5, 5, 3, 2])
    fold = estimate.group_folds(groups, 5, seed=0)
    assert len(fold) == 100 and set(fold) == set(range(5))
    for g in range(10):
        assert len(set(fold[groups == g])) == 1
    sizes = np.bincount(fold, minlength=5)
    assert sizes.max() <= 30 and sizes.min() >= 10
    assert (estimate.group_folds(groups, 5, seed=0) == fold).all()


def test_era_of_and_band_rounding():
    assert estimate.era_of([1000, 1865, 1866, 1919.4, 1919.6, 1945, 1946, 1975, 1976, 1993, 1994, 2026]).tolist() == \
        [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]   # 1919.6 rounds to 1920
    assert estimate.round_band([0, 1, 5, 5.1, 12, 24.0], city.ESTIMATE).tolist() == [5, 5, 5, 10, 15, 25]


def test_band_rounding_ignores_float_noise_in_the_percentile():
    ae = np.array([0.0] * 27 + [4.0] + [9.0] * 7)          # the 80th percentile is 5, computed as 5.000000000000014
    assert np.percentile(ae, 80) > 5 and pd.Series(ae).quantile(0.8) > 5
    assert estimate.round_band(np.percentile(ae, 80), P) == 5
    assert estimate.round_band(pd.Series(ae).quantile(0.8), P) == 5
    assert estimate.round_band([5.0001], P).tolist() == [10]   # a real excess still rounds up


def test_score_gives_the_median_error_and_the_share_in_the_right_period():
    # 1950 and 1946 share a period, 1975 and 1977 do not (1976 starts one); 1945.75 rounds to 1946 before its period.
    s = estimate.score([1950, 1975, 1900, 1945.75], np.array([1946, 1977, 1900, 1946]))
    assert s == {"median_error": 1.125, "right_period": 0.75}
    assert estimate.score([1946.0], [1946]) == {"median_error": 0.0, "right_period": 1.0}


def test_stadsdel_of_uses_the_polygon_under_the_centroid_else_the_nearest(tmp_path: Path):
    shp = tmp_path / "Stadsdel.shp"
    sd = gpd.GeoDataFrame({"NAMN": ["Gamla stan", "Farsta"]},
                          geometry=[box(154000, 6578800, 154100, 6578900), box(154200, 6578800, 154300, 6578900)], crs=city.CRS)
    pyogrio.write_dataframe(sd, shp)
    b = synth.buildings(rows=[{"geometry": box(154010, 6578810, 154020, 6578820)},
                              {"geometry": box(154290, 6578810, 154299, 6578820)},
                              {"geometry": box(154120, 6578810, 154130, 6578820)}])   # between the two: nearest wins
    assert estimate.stadsdel_of(b, shp).tolist() == ["GAMLA STAN", "FARSTA", "GAMLA STAN"]


@pytest.mark.filterwarnings("ignore:.crs. was not provided")   # the naive file is written so on purpose
def test_stadsdel_of_reads_a_shapefile_without_a_crs_as_epsg_3011_and_reprojects_another(tmp_path: Path):
    b = synth.buildings(rows=[{"geometry": box(154010, 6578810, 154020, 6578820)}])
    naive = tmp_path / "Naive.shp"
    pyogrio.write_dataframe(gpd.GeoDataFrame({"NAMN": ["Farsta"]}, geometry=[box(154000, 6578800, 154100, 6578900)]),
                            naive)
    assert not naive.with_suffix(".prj").exists()
    assert estimate.stadsdel_of(b, naive).tolist() == ["FARSTA"]
    other = tmp_path / "Sweref99tm.shp"
    sd = gpd.GeoDataFrame({"NAMN": ["Farsta"]}, geometry=[box(154000, 6578800, 154100, 6578900)], crs=city.CRS)
    pyogrio.write_dataframe(sd.to_crs(3006), other)
    assert estimate.stadsdel_of(b, other).tolist() == ["FARSTA"]


# Final review PIPELINE-2: the independent check counts "in band" apart from "right", bounds included, and splits at
# 1990 by the true year.

def test_the_external_check_counts_in_band_apart_from_right_and_splits_at_1990():
    # Three clusters 2 km apart, each a ring of 20 training houses 50 m round its test houses, all of one year, so
    # every test house is estimated at its cluster's year (k 20) with the cell's band 5:
    #   1944 (Funkis, p8): truths 1946 and 1949, inside the band (1949 its upper bound) but Folkhem (p9), so not right;
    #                      1939, right and on the band's lower bound.
    #   1950: truth 1960, right (both Folkhem) but 10 years off, outside the band.
    #   1985: truth 1990, right and inside, the first year of the from_1990 half.
    clusters = {(0.0, 0.0): (1944, [1946, 1949, 1939]), (2000.0, 0.0): (1950, [1960]), (4000.0, 0.0): (1985, [1990])}
    train, test, years = [], [], []
    for kv, ((x, y), (year, truths)) in enumerate(clusters.items()):
        train.append(frame(ring(50.0) + (x, y), kvarter=kv))
        test.append(frame(np.tile((x, y), (len(truths), 1)), kvarter=10 + kv))
        years += [year] * 20
    truths = [t for _, ts in clusters.values() for t in ts]
    f = pd.concat(train + test, ignore_index=True)
    years = np.r_[years, truths].astype(float)
    test_rows = np.arange(len(f)) >= 60
    table = {"cells": [{"group": "house", "era": era, "inner": False, "n": 40, "status": "estimate", "band": 5}
                       for era in ("1920–1945", "1946–1975", "1976–1993")], "fallback": []}
    ext = estimate.check_external(f, years, ~test_rows, test_rows, table, P)
    assert (ext["n_all"], ext["n_estimate"], ext["right_estimate"], ext["in_band_estimate"], ext["n_unknown"]) == \
        (5, 5, 3, 4, 0)
    assert ext["before_1990"] == {"n_all": 4, "n_estimate": 4, "right_estimate": 2, "in_band_estimate": 3}
    assert ext["from_1990"] == {"n_all": 1, "n_estimate": 1, "right_estimate": 1, "in_band_estimate": 1}


# Final review PIPELINE-4: every threshold of the estimator at its boundary.

def test_a_cell_exactly_at_min_right_and_max_band_gives_an_estimate():
    assert estimate.status_of("house", 0.7, 15, P) == "estimate"
    assert estimate.status_of("house", 0.699, 15, P) == "unknown"
    assert estimate.status_of("house", 0.7, 20, P) == "unknown"
    # through the cross-validation: one in three tested houses 15 years from the estimate, in the same period
    # (1949 and 1964 are both Folkhem), so the 80th-percentile error is exactly 15
    f, years, dated = scattered((1949, 1949, 1964), middle=(1949, 1949, 1949))
    [cell] = estimate.cross_validate(f, years, dated, P)["cells"]
    assert (cell["right_period"], cell["band"], cell["status"]) == (1.0, 15, "estimate")


def test_a_house_exactly_near_m_from_a_dated_one_is_scored_and_estimated():
    # Two kvarter of 40 houses, 100 m apart (the folds hold each out against the other): every test house is exactly
    # near_m from its nearest training house, so all 80 are scored; a millimetre further and none is.
    def table(gap):
        f = pd.concat([frame(np.zeros((40, 2)), kvarter=1), frame(np.tile((gap, 0.0), (40, 1)), kvarter=2)],
                      ignore_index=True)
        return estimate.cross_validate(f, np.full(80, 1950.0), np.ones(80, bool), P)
    assert P["near_m"] == 100.0
    assert [c["n"] for c in table(100.0)["cells"]] == [80]
    assert table(100.001)["cells"] == []
    one = frame([0.0, 0.0], kvarter=1)
    cells = {"cells": [{"group": "house", "era": "1946–1975", "inner": False, "n": 40, "status": "estimate", "band": 5}],
             "fallback": []}
    assert estimate.decide(one, [1950.0], [100.0], cells, P)[0].tolist() == [ESTIMATE]
    assert estimate.decide(one, [1950.0], [100.001], cells, P)[0].tolist() == [UNKNOWN]


def test_the_new_building_gates_at_their_boundaries():
    # late_prod_year 2008: first digitised in 2008 is gated, in 2007 not (0: unknown, not gated); late_unit_fnr
    # 10,400,000: a key above it is gated, at it not (0: no key, not gated)
    assert (P["late_prod_year"], P["late_unit_fnr"]) == (2008, 10_400_000)
    f = pd.concat([frame([0.0, 0.0], kvarter=1)] * 6, ignore_index=True)
    f["prod_year"] = [2007, 2008, 0, 2003, 2003, 2003]
    f["fnr"] = np.array([10_100_000, 10_100_000, 10_100_000, 10_400_000, 10_400_001, 0], dtype=np.int64)
    assert estimate.gated(f, P).tolist() == [False, True, False, False, True, False]
