"""The estimate tier of the year model (spec §3.3, D6): kNN years from dated neighbours, the accuracy table and the
rule that decides ESTIMATE, PERIOD or UNKNOWN. Measured in docs/research/2026-10-15-estimates-prototype.md.

Feature space (city.ESTIMATE): centroid x and y over L; w_height * ln(height); w_area * ln(area); w_compact *
compactness; a penalty added in quadrature when the KATEGORI group differs; and, in production only, kvarter_bonus
taken off the distance to candidates in the building's own kvarter (from FASTIGHET, as integer codes that never
ship). The search is per KATEGORI group: each group's k-d tree returns its k nearest (at most k per group), and the
bonus only re-ranks those candidates, so a kvarter-mate outside its group's raw top k is never reached (the plan's
approximation: the full add-on measured 0.1 y of gain and is not implemented). The year is the weighted median
(weights 1 / (distance + eps)) of the k best candidates' years; d1 is the plain distance in metres to the nearest
training centroid.

Accuracy: folds-fold cross-validation with whole kvarter held out, on every building with a building-level year.
Every one of them trains, but only the test buildings the map could estimate are scored (Task 14b, "measure what
the map estimates"): a building in never_groups, first digitised in late_prod_year or later, or on a late-formed
property unit (fnr above late_unit_fnr) is a neighbour for the others and never counts in a cell, a fallback row,
the band coverage or by_true_period (gated). A cell is KATEGORI group x era of the *estimated* year x inner/outer
city, over scored test buildings within near_m of a training building. Fewer than min_cell test buildings: "not
measurable". The band is the cell's 80th percentile of absolute error, rounded up to band_step and never below it.
band_coverage: bands from all folds but one, tested on that one (the share of true years inside the band).
median_error and right_period come from score(), the one place they are computed: the cells, the fallback rows and
s02_years' area check all use it. by_true_period counts the scored test buildings by the period of their true year
(n, right) and, of them, those whose cell gives an estimate (n_estimate, right_estimate), so the table shows where it
is weak (the newest buildings). A cell's status says what the map does with it (status_of): "estimate" only for a
group in estimate_groups with right_period >= min_right and band <= max_band; a right-enough cell with a wider band
(and a right-enough fallback row) is "period" only when give_period is on; everything else measurable is "unknown".

Rule for a building without a year (decide): UNKNOWN when its group is not in estimate_groups, it is gated (above),
or the nearest dated building is beyond near_m (far_rule "period" gives it the estimate's period instead, with
give_period on). Else by its cell: "estimate" gives ESTIMATE with the cell's band, "period" gives PERIOD (with
give_period on), "unknown" gives UNKNOWN; not measurable falls back to the group x inner/outer row, PERIOD when
that row reads "period" (with give_period on), else UNKNOWN. period_only_stadsdelar: still-unknown buildings in
those stadsdelar get PERIOD when they pass the gates above (with give_period on); an M3 review lever, off by
default. With Task 14b's defaults (estimate_groups {"house"}, give_period False) the rule gives houses ESTIMATE or
UNKNOWN and every other building UNKNOWN.

The independent check (check_external, C10's external entry): the map's own rule (kvarter bonus, decide with the
built table) on buildings that only Wikidata or OpenStreetMap date, trained on the curated and RAÄ-dated buildings
alone, counted per map state and split at SPLIT_YEAR.
"""
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from scipy.spatial import cKDTree

from . import city
from .codes import ESTIMATE, PERIOD, UNKNOWN
from .s01_load import STADSDELAR
from .yearrules import FLOOR_YEAR, LATEST_YEAR

GROUPS = sorted(set(city.KATEGORI_GROUPS.values()))   # alphabetical, so the integer codes are stable
GROUP_CODE = {g: i for i, g in enumerate(GROUPS)}
ERA_STARTS = np.array([e[1] for e in city.ERAS])
KV = re.compile(r"^(.*?)\s+(\d+)$")             # "STORKEN 12"  -> kvarter STORKEN
TRAKT = re.compile(r"^(.*?)\s+(\d+):(\d+)$")    # "SUNDBY 5:6"  -> trakt block SUNDBY 5
GRID_M = 250.0                                  # a building without a designation: its 250 m grid cell stands in
PERIOD_KEYS = [q[0] for q in city.PERIODS]
SPLIT_YEAR = 1990                               # the external check counts true years before it and from it apart
# The keys of the table cross_validate returns: C10's accuracy table without "area", "external" and "result" (added by
# run and s02_years). Not s99_validate.TABLE_KEYS, which is C10's whole set of 15.
CV_KEYS = ("method", "held_out", "folds", "near_m", "min_cell", "min_right", "max_band", "tested", "cells",
           "fallback", "band_coverage", "by_true_period")
SPLIT_KEYS = ("n_all", "n_estimate", "right_estimate", "in_band_estimate")   # C10's external split at SPLIT_YEAR


def era_of(years) -> np.ndarray:
    """0-based index into city.ERAS for an array of (possibly fractional) years."""
    y = np.round(np.asarray(years, dtype=float))
    return np.maximum(0, np.searchsorted(ERA_STARTS, y, side="right") - 1)


def round_band(v, p) -> np.ndarray:
    """Bands rounded up to a multiple of band_step, never below it. The quotient is rounded to 6 decimals before the
    ceiling, so float noise in a percentile (5.000000000000014 for a true 5) does not add a step."""
    step = p["band_step"]
    return np.maximum(step, step * np.ceil(np.round(np.asarray(v, dtype=float) / step, 6)))


def score(pred, truth) -> dict:
    """The accuracy numbers of estimated years `pred` against known years `truth` (equal-length arrays, at least one
    row): {"median_error": the median absolute error in years, "right_period": the share whose estimate falls in the
    true year's period (city.period_indices, which rounds first), to 3 decimals}. The one scoring rule of the table:
    the cells and fallback rows here, and s02_years' area and external checks (Task 7), merge this dict as it is."""
    pred, truth = np.asarray(pred, dtype=float), np.asarray(truth, dtype=float)
    right = city.period_indices(pred) == city.period_indices(truth)
    return {"median_error": float(np.median(np.abs(pred - truth))), "right_period": round(float(right.mean()), 3)}


def stadsdel_of(b, path=STADSDELAR) -> np.ndarray:
    """The stadsdel (Stadsdel.shp NAMN, upper case) under each building's centroid; the nearest one when the
    centroid falls on a boundary or in water. A file without a CRS is taken to be in EPSG:3011, as the City's is."""
    sd = pyogrio.read_dataframe(path, columns=["NAMN"])
    if sd.crs is None:
        sd = sd.set_crs(city.CRS)
    elif sd.crs.to_epsg() != city.CRS:
        sd = sd.to_crs(city.CRS)
    sd = sd[["NAMN", "geometry"]]
    pts = gpd.GeoDataFrame({"i": np.arange(len(b))}, geometry=b.geometry.centroid.values, crs=city.CRS)
    hit = gpd.sjoin(pts, sd, predicate="within", how="left").drop_duplicates("i").set_index("i")
    names = hit.NAMN.reindex(np.arange(len(b))).fillna("").to_numpy(dtype=object)
    miss = np.flatnonzero(names == "")
    if len(miss):
        near = gpd.sjoin_nearest(pts.iloc[miss], sd, how="left").drop_duplicates("i").set_index("i")
        names[miss] = near.NAMN.reindex(miss).fillna("").to_numpy()
    return np.array([str(n).strip().upper() for n in names], dtype=object)


def kvarter_codes(fastighet, x, y) -> np.ndarray:
    """Integer kvarter codes from FASTIGHET: "NAME N" -> the kvarter NAME; "NAME N:M" -> the trakt block NAME N;
    no designation -> the 250 m grid cell. No designation string leaves this function."""
    keys = []
    for f, xx, yy in zip(fastighet, x, y):
        f = (f or "").strip()
        m = TRAKT.match(f)
        if m:
            keys.append(f"T|{m.group(1)}|{m.group(2)}")
            continue
        m = KV.match(f)
        if m:
            keys.append(f"K|{m.group(1)}")
            continue
        keys.append(f"G|{int(xx // GRID_M)}|{int(yy // GRID_M)}")
    return pd.factorize(pd.Series(keys, dtype=object))[0].astype(np.int64)


def features(b, inner=None, stadsdel=None) -> pd.DataFrame:
    """One row per building: x, y, logh, loga, compact, group (code into GROUPS), inner, kvarter, prod_year, fnr.
    Missing columns get defaults (height 10 m, area from the geometry, no designation, prod_year 0, fnr 0).
    inner: a bool per building, else from stadsdel (in city.INNER_STADSDELAR), else all outer."""
    geom = b.geometry.values
    c = shapely.centroid(geom)
    x, y = shapely.get_x(c), shapely.get_y(c)
    area = b["area"].to_numpy(dtype=float) if "area" in b else shapely.area(geom)
    height = b["height"].to_numpy(dtype=float) if "height" in b else np.full(len(b), 10.0)
    perim = shapely.length(geom)
    compact = 4 * np.pi * area / np.maximum(perim, 1e-6) ** 2
    fastighet = b["fastighet"].fillna("").to_numpy(dtype=object) if "fastighet" in b else np.full(len(b), "", dtype=object)
    prod_year = b["prod_year"].to_numpy(dtype=np.int64) if "prod_year" in b else np.zeros(len(b), np.int64)
    fnr = b["fnr"].to_numpy(dtype=np.int64) if "fnr" in b else np.zeros(len(b), np.int64)
    group = np.array([GROUP_CODE[city.KATEGORI_GROUPS.get(k, "unspecified")] for k in b.kategori], dtype=np.int64)
    if inner is None:
        inner = np.isin(stadsdel, list(city.INNER_STADSDELAR)) if stadsdel is not None else np.zeros(len(b), bool)
    return pd.DataFrame({
        "x": x, "y": y, "logh": np.log(np.maximum(height, 0.5)), "loga": np.log(np.maximum(area, 1.0)),
        "compact": compact, "group": group, "inner": np.asarray(inner, dtype=bool),
        "kvarter": kvarter_codes(fastighet, x, y), "prod_year": prod_year, "fnr": fnr,
    })


def _space(f, p) -> np.ndarray:
    return np.c_[f.x.to_numpy() / p["L"], f.y.to_numpy() / p["L"], p["w_height"] * f.logh.to_numpy(),
                 p["w_area"] * f.loga.to_numpy(), p["w_compact"] * f.compact.to_numpy()]


def wmedian(vals, w) -> np.ndarray:
    """Row-wise weighted median of vals (n, k) with weights w (n, k); ties keep the input order."""
    o = np.argsort(vals, axis=1, kind="stable")
    v = np.take_along_axis(vals, o, 1)
    ww = np.take_along_axis(w, o, 1)
    c = np.cumsum(ww, 1)
    half = c[:, -1:] / 2.0
    idx = (c < half).sum(1)
    return v[np.arange(len(v)), np.minimum(idx, v.shape[1] - 1)]


def knn(train, years, query, p=None, kvarter_bonus: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """(estimated year, metres to the nearest training centroid) for every row of query.

    train, query: feature frames (features()). years: one year per training row. One k-d tree per KATEGORI group
    over the training rows; every query row asks each tree for its k nearest (the candidates, at most k per group),
    the group penalty is added where the group differs, and the k best candidates win. Without a bonus this is the
    exact k nearest in the feature space. kvarter_bonus > 0 takes that much off the distance to the candidates in the
    query row's own kvarter, re-ranking the candidates only: a kvarter-mate outside its group tree's k nearest is not
    reached (the plan's approximation; see the module docstring).
    """
    p = city.ESTIMATE if p is None else p
    k = p["k"]
    n = len(query)
    if len(train) == 0 or n == 0:
        return np.full(n, np.nan), np.full(n, np.inf)
    Xtr, Xq = _space(train, p), _space(query, p)
    gtr, gq = train.group.to_numpy(), query.group.to_numpy()
    y = np.asarray(years, dtype=float)
    D, nbr = [], []
    for g in np.unique(gtr):
        idx = np.flatnonzero(gtr == g)
        kk = min(k, len(idx))
        d, i = cKDTree(Xtr[idx]).query(Xq, k=kk)
        d, i = d.reshape(n, -1), idx[i.reshape(n, -1)]
        pen = np.where(gq == g, 0.0, p["group_penalty"])[:, None]
        D.append(np.sqrt(d ** 2 + pen ** 2))
        nbr.append(i)
    D, nbr = np.hstack(D), np.hstack(nbr)
    if kvarter_bonus > 0:
        same = train.kvarter.to_numpy()[nbr] == query.kvarter.to_numpy()[:, None]
        D = np.where(same, np.maximum(D - kvarter_bonus, 0.0), D)
    o = np.argsort(D, axis=1, kind="stable")[:, :k]
    D, nbr = np.take_along_axis(D, o, 1), np.take_along_axis(nbr, o, 1)
    yhat = wmedian(y[nbr], 1.0 / (D + p["eps"]))
    d1, _ = cKDTree(np.c_[train.x.to_numpy(), train.y.to_numpy()]).query(np.c_[query.x.to_numpy(), query.y.to_numpy()], k=1)
    return yhat, np.asarray(d1, dtype=float).reshape(n)


def group_folds(groups, n: int, seed: int) -> np.ndarray:
    """Fold number per row; whole groups go to one fold, folds balanced by row count (greedy on shuffled groups,
    largest first). The same groups and seed always give the same folds."""
    rng = np.random.default_rng(seed)
    g = pd.Series(np.asarray(groups))
    sizes = g.value_counts()
    order = sizes.index.to_numpy().copy()
    rng.shuffle(order)
    order = sorted(order, key=lambda key: -sizes[key])
    load = np.zeros(n)
    fold_of = {}
    for key in order:
        i = int(np.argmin(load))
        fold_of[key] = i
        load[i] += sizes[key]
    return g.map(fold_of).to_numpy(dtype=np.int64)


def gated(f: pd.DataFrame, p) -> np.ndarray:
    """Per row of f, True where the map never estimates the building whatever its cell says, so the table never
    scores it (it still trains): a group in never_groups, first digitised in late_prod_year or later (0: unknown, not
    gated), or on a property unit formed late (fnr above late_unit_fnr; 0: no key, not gated)."""
    never = np.isin(f.group.to_numpy(), [GROUP_CODE[g] for g in p["never_groups"]])
    prod = f.prod_year.to_numpy()
    fnr = f["fnr"].to_numpy() if "fnr" in f else np.zeros(len(f), np.int64)
    return never | ((prod > 0) & (prod >= p["late_prod_year"])) | (fnr > p["late_unit_fnr"])


def status_of(group: str, right: float, band, p) -> str:
    """What the map does with a measurable cell (band: its band) or fallback row (band None): "estimate" for a group
    in estimate_groups at least min_right right with a band within max_band; "period" for such a group right
    enough but wider (or a fallback row) when give_period is on; else "unknown". The table's statuses say what the
    map does (Task 14b), from the right_period it reports (3 decimals), so its numbers and statuses always agree."""
    if group not in p["estimate_groups"] or right < p["min_right"]:
        return "unknown"
    if band is not None and band <= p["max_band"]:
        return "estimate"
    return "period" if p["give_period"] else "unknown"


def _cells(t: pd.DataFrame, p) -> tuple[list[dict], list[dict]]:
    """The cells (group x era x inner) and the fallback rows (group x inner) of the table from the scored test rows
    t (yhat, year, ae, adj per row). A measurable cell or row gets score()'s numbers and status_of's status."""
    cells, fallback = [], []
    for (g, e, inn), grp in t.groupby(["group", "era", "inner"], sort=True):
        cell = {"group": GROUPS[int(g)], "era": city.ERAS[int(e)][0], "inner": bool(inn), "n": int(len(grp))}
        if len(grp) >= p["min_cell"]:
            s = score(grp.yhat, grp.year)
            band = int(round_band(np.percentile(grp.ae, 80), p))
            cell.update(s, within_one=round(float(grp.adj.mean()), 3), band=band,
                        status=status_of(cell["group"], s["right_period"], band, p))
        else:
            cell["status"] = "not measurable"
        cells.append(cell)
    for (g, inn), grp in t.groupby(["group", "inner"], sort=True):
        row = {"group": GROUPS[int(g)], "inner": bool(inn), "n": int(len(grp))}
        if len(grp) >= p["min_cell"]:
            s = score(grp.yhat, grp.year)
            row.update(s, within_one=round(float(grp.adj.mean()), 3),
                       status=status_of(row["group"], s["right_period"], None, p))
        else:
            row["status"] = "not measurable"
        fallback.append(row)
    return cells, fallback


def _by_true_period(t: pd.DataFrame, cells: list[dict]) -> list[dict]:
    """One row per period of city.PERIODS: the scored test rows t whose true year is in it (n, and how many were
    estimated in the right period), and of them the ones whose cell gives an estimate (n_estimate, right_estimate)."""
    status = {(c["group"], c["era"], c["inner"]): c["status"] for c in cells}
    shown = np.array([status.get((GROUPS[int(g)], city.ERAS[int(e)][0], bool(i))) == "estimate"
                      for g, e, i in zip(t.group, t.era, t.inner)], dtype=bool)
    true = city.period_indices(t.year.to_numpy())
    right = city.period_indices(t.yhat.to_numpy()) == true
    rows = []
    for i, key in enumerate(PERIOD_KEYS):
        m = true == i
        rows.append({"period": key, "n": int(m.sum()), "right": int((m & right).sum()),
                     "n_estimate": int((m & shown).sum()), "right_estimate": int((m & shown & right).sum())})
    return rows


def cross_validate(f: pd.DataFrame, years, dated, p=None) -> dict:
    """The accuracy table (contract C10) from the rows marked dated, their years and the feature frame: the CV_KEYS,
    that is C10's table without "result" (run adds it), "area" and "external" (s02_years adds both, Task 7). Every
    dated row trains; the gated ones are not scored (see the module docstring)."""
    p = city.ESTIMATE if p is None else p
    years = np.asarray(years, dtype=float)
    dated = np.asarray(dated, dtype=bool)
    pool = f[dated].reset_index(drop=True)
    ypool = years[dated]
    table = {"method": "knn", "held_out": "kvarter", "folds": p["folds"], "near_m": p["near_m"],
             "min_cell": p["min_cell"], "min_right": p["min_right"], "max_band": p["max_band"],
             "tested": int(len(pool)), "cells": [], "fallback": [], "band_coverage": None, "by_true_period": []}
    if len(pool) == 0:
        return table
    fold = group_folds(pool.kvarter.to_numpy(), p["folds"], p["seed"])
    yhat = np.full(len(pool), np.nan)
    d1 = np.full(len(pool), np.inf)
    for j in range(p["folds"]):
        te = fold == j
        if not te.any() or te.all():
            continue
        yhat[te], d1[te] = knn(pool[~te], ypool[~te], pool[te], p)
    ok = np.isfinite(yhat) & (d1 <= p["near_m"]) & ~gated(pool, p)
    if not ok.any():
        return table
    ph, pt = city.period_indices(yhat[ok]), city.period_indices(ypool[ok])
    t = pd.DataFrame({"group": pool.group.to_numpy()[ok], "era": era_of(yhat[ok]), "inner": pool.inner.to_numpy()[ok],
                      "yhat": yhat[ok], "year": ypool[ok], "ae": np.abs(yhat[ok] - ypool[ok]),
                      "adj": np.abs(ph - pt) <= 1, "fold": fold[ok]})
    table["cells"], table["fallback"] = _cells(t, p)
    table["by_true_period"] = _by_true_period(t, table["cells"])
    cov = []
    for j in range(p["folds"]):
        trn, tst = t[t.fold != j], t[t.fold == j]
        if trn.empty or tst.empty:
            continue
        g = trn.groupby(["group", "era", "inner"]).ae
        bands = pd.DataFrame({"n": g.size(), "p80": g.quantile(0.8)})
        bands = bands[bands.n >= p["min_cell"]]
        if bands.empty:
            continue
        band = np.array([bands.p80.get(key, np.nan) for key in zip(tst.group, tst.era, tst.inner)])
        has = ~np.isnan(band)
        if has.any():
            cov.append(float((tst.ae.to_numpy()[has] <= round_band(band[has], p)).mean()))
    table["band_coverage"] = round(float(np.mean(cov)), 3) if cov else None
    return table


def decide(f: pd.DataFrame, yhat, d1, table: dict, p=None, stadsdel=None) -> tuple[np.ndarray, np.ndarray]:
    """(yflag, band) per row of f: ESTIMATE, PERIOD or UNKNOWN by the rule in the module docstring. Rows whose yhat
    is NaN (no training data) stay UNKNOWN. Without give_period no row gets PERIOD, whatever the table, far_rule or
    period_only_stadsdelar say."""
    p = city.ESTIMATE if p is None else p
    cells = {(c["group"], c["era"], c["inner"]): c for c in table.get("cells", [])}
    fallback = {(r["group"], r["inner"]): r for r in table.get("fallback", [])}
    yhat, d1 = np.asarray(yhat, dtype=float), np.asarray(d1, dtype=float)
    n = len(f)
    flag = np.full(n, UNKNOWN, dtype=np.int64)
    band = np.zeros(n, dtype=np.int64)
    group, inner = f.group.to_numpy(), f.inner.to_numpy()
    era = era_of(np.where(np.isfinite(yhat), yhat, 1000))
    skip = gated(f, p) | ~np.isin(group, [GROUP_CODE[g] for g in p["estimate_groups"]])
    give = bool(p["give_period"])
    for i in range(n):
        if not np.isfinite(yhat[i]) or skip[i]:
            continue
        g = GROUPS[int(group[i])]
        if d1[i] > p["near_m"]:
            if p["far_rule"] == "period" and give:
                flag[i] = PERIOD
            continue
        c = cells.get((g, city.ERAS[int(era[i])][0], bool(inner[i])))
        if c is not None and c["status"] != "not measurable":
            if c["status"] == "estimate":
                flag[i], band[i] = ESTIMATE, c["band"]
            elif c["status"] == "period" and give:
                flag[i] = PERIOD
            continue
        r = fallback.get((g, bool(inner[i])))
        if r is not None and r["status"] == "period" and give:
            flag[i] = PERIOD
    if stadsdel is not None and p["period_only_stadsdelar"] and give:
        force = ((flag == UNKNOWN) & np.isin(np.asarray(stadsdel, dtype=object), list(p["period_only_stadsdelar"]))
                 & np.isfinite(yhat) & (d1 <= p["near_m"]) & ~skip)
        flag[force] = PERIOD
    return flag, band


def run(f: pd.DataFrame, years, dated, query, p=None, stadsdel=None) -> tuple[pd.DataFrame, dict]:
    """Cross-validate on the dated rows, estimate the query rows and decide their flags.

    years: the in-memory building-level year per row (0 where there is none); dated: rows that train (and are
    tested); query: rows that still need a year. Returns (frame indexed like f with yhat, d1, yflag, band, NaN
    and UNKNOWN outside query; the accuracy table with 'result' added)."""
    p = city.ESTIMATE if p is None else p
    dated, query = np.asarray(dated, dtype=bool), np.asarray(query, dtype=bool)
    table = cross_validate(f, years, dated, p)
    out = pd.DataFrame({"yhat": np.full(len(f), np.nan), "d1": np.full(len(f), np.inf),
                        "yflag": np.full(len(f), UNKNOWN, dtype=np.int64), "band": np.zeros(len(f), dtype=np.int64)},
                       index=f.index)
    if query.any() and dated.any():
        yhat, d1 = knn(f[dated], np.asarray(years, dtype=float)[dated], f[query], p, kvarter_bonus=p["kvarter_bonus"])
        flag, band = decide(f[query], yhat, d1, table, p, None if stadsdel is None else np.asarray(stadsdel)[query])
        out.loc[query, "yhat"], out.loc[query, "d1"] = yhat, d1
        out.loc[query, "yflag"], out.loc[query, "band"] = flag, band
    flags = out.yflag.to_numpy()[query]
    table["result"] = {"estimate": int((flags == ESTIMATE).sum()), "period": int((flags == PERIOD).sum()),
                       "unknown": int((flags == UNKNOWN).sum())}
    return out, table


def no_external() -> dict:
    """C10's external entry when there is nothing to check (no Wikidata or OSM row, or the estimate tier is off)."""
    zero = dict.fromkeys(SPLIT_KEYS, 0)
    return {"status": "not measurable", **zero, "n_unknown": 0, "before_1990": dict(zero), "from_1990": dict(zero)}


def check_external(f: pd.DataFrame, years, train, test, table: dict, p=None, stadsdel=None) -> dict:
    """The independent check (C10's external entry): the map's own rule run on the `test` rows as if they had no
    year, trained on the `train` rows alone: knn with the production kvarter bonus, then decide with the built
    `table` and every gate. s02_years passes the curated + raa + raa_old rows as train and the rows only Wikidata or
    OpenStreetMap date as test.

    Counted per map state: n_all (test rows), n_estimate (rows the map would estimate), right_estimate (of those, the
    estimated year, rounded to a whole year before any D18 decade rounding, in the true year's period),
    in_band_estimate (of those, the true year within the estimated year ± the cell's band, clamped to 1000..2026 as
    s02_years clamps a non-private estimate's range; a private house publishes its decade instead, so this is the
    band the test measures, not a range the map shows), n_unknown; and the four counts split at SPLIT_YEAR into
    before_1990 and from_1990 by the true year. status is "measured" only with min_cell or more estimated rows (never
    from n_all), else "not measurable" (the page then prints the counts, never a share)."""
    p = city.ESTIMATE if p is None else p
    train, test = np.asarray(train, dtype=bool), np.asarray(test, dtype=bool)
    years = np.asarray(years, dtype=float)
    out = no_external()
    if not test.any():
        return out
    yhat, d1 = knn(f[train], years[train], f[test], p, kvarter_bonus=p["kvarter_bonus"])
    flag, band = decide(f[test], yhat, d1, table, p, None if stadsdel is None else np.asarray(stadsdel)[test])
    truth = years[test]
    shown = flag == ESTIMATE
    yh = np.clip(np.round(np.where(shown, yhat, truth)), FLOOR_YEAR, LATEST_YEAR)
    right = shown & (city.period_indices(yh) == city.period_indices(truth))
    inside = shown & (np.maximum(FLOOR_YEAR, yh - band) <= truth) & (truth <= np.minimum(LATEST_YEAR, yh + band))

    def counts(m) -> dict:
        return {"n_all": int(m.sum()), "n_estimate": int((m & shown).sum()), "right_estimate": int((m & right).sum()),
                "in_band_estimate": int((m & inside).sum())}

    out.update(counts(np.ones(len(truth), dtype=bool)), n_unknown=int((flag == UNKNOWN).sum()),
               before_1990=counts(truth < SPLIT_YEAR), from_1990=counts(truth >= SPLIT_YEAR))
    out["status"] = "measured" if out["n_estimate"] >= p["min_cell"] else "not measurable"
    return out
