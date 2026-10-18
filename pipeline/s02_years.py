"""Construction year per building.

The first tier that applies wins:
  curated   pipeline/landmarks.py as s08_landmarks verified it (data/landmarks.json), placed by its coordinate
  raa       a RAÄ Byggnad record joined by registerbyggnad_id == LOD1 UUID; RAÄ polygons that join no
            UUID may still date a footprint they cover by at least half
  raa_old   RAÄ's OLD register file (pipeline/years_raa_old.py), joined by UUID: years the 2025 register dropped
  raa_area  the footprint's centroid lies in a dated RAÄ Område polygon (the smallest one wins)
  wikidata  a Wikidata building item placed on exactly one footprint (pipeline/years_wikidata.py)
  osm       an OpenStreetMap building with a start_date placed on exactly one footprint (pipeline/years_osm.py)
  estimate  the kNN estimate from dated neighbours (pipeline/estimate.py): ESTIMATE with a ±band for a house in a
            cell the table vouches for, else the building stays UNKNOWN (year 0; Ärg draws it hatched). PERIOD (the
            period only) comes only with city.ESTIMATE's give_period lever, off since 2026-10-15
  reader    a reader's report the owner accepted (pipeline/contributions.csv, pipeline/contributions.py), written last:
            it fills a building that is unknown, area-dated or estimated, and replaces a record year (raa, raa_old,
            wikidata, osm) only when its row says replaces_register yes; a curated or withheld building refuses it

Display rule for a from–to range (yearrules.display): a span of 15 years or less shows year_to (completion),
flagged EXACT when from == to, else RANGE; a longer span shows year_from, flagged LONG. A Wikidata or OSM tier
brings its own published year (a decade's start, a circa's stated year; years_wikidata, years_osm), and the
display rule then gives only the flag. ESTIMATE rows carry year_from/year_to = year ∓ band (clamped to
1000..2026); PERIOD rows carry the period's first and last year.

Private houses: a dated building whose KATEGORI is in city.PRIVATE_HOUSE_KATEGORI, unless curated, gets
private = True and publishes only its decade: year = decade start, year_from = year, year_to = year + 9. yflag
still says how the year is known, and period comes from the year before rounding, so the map keeps the house's
period colour. When that decade and period share fewer than two years (a 1610 or a 1719), the period is taken
from the decade's middle year instead (1615: Stormaktstiden), so the pair never pins the year (s99 checks it).

raa_id links every footprint a RAÄ Byggnad record joins by UUID, whether or not that record has a usable year,
so s02_attributes can read its rating and architects. The raa_old tier never sets it (its record pages will die).

Outputs: data/years.parquet, data/accuracy.json (the estimate tier's accuracy table, with the
area tier's check, area years against the building-level years in the same polygons, Wikidata and OSM years the
area outranked included, and the external check, estimate.check_external: the map's own rule, trained on curated +
raa + raa_old alone, run on the rows only Wikidata or OSM dated as if they had no year, counted per map state and
split at 1990) and data/review-years.json (the curated review list: Wikidata and OSM years that disagree
with RAÄ by more than DISAGREE_YEARS, century-precision items, every Wikidata gain, each Wikidata entry with its
placement; internal, never shipped). No building with a RAÄ year, or none with a RAÄ link, is always wrong (RAÄ
renamed a field, say), so the step stops before writing.
"""
import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

from . import city
from . import estimate as est
from . import contributions, suppress, years_osm, years_raa_old, years_wikidata
from .codes import (AREA, ESTIMATE, EXACT, LONG, PERIOD, RANGE, SRC_CURATED, SRC_ESTIMATE, SRC_NONE, SRC_OSM, SRC_RAA,
                    SRC_RAA_AREA, SRC_RAA_OLD, SRC_READER, SRC_WIKIDATA, UNKNOWN)
from .geo import LANDMARK_MAX_M, lonlat_to_3011, resolve_points  # noqa: F401  (re-exported for callers and tests)
from .s00_fetch_raa import DEST as RAA_GPKG
from .s00_fetch_raa import LAYER as RAA_LAYER
from .s01_load import STADSDELAR
from .s08_landmarks import OUT as LANDMARKS_JSON
from .s08_landmarks import load as load_landmarks
from .yearrules import FLOOR_YEAR, LATEST_YEAR, MIN_YEAR, OLD_OK, RANGE_MAX, clean_years, display  # noqa: F401

BUILDINGS = Path("data/buildings.parquet")
OUT = Path("data/years.parquet")
ACCURACY = Path("data/accuracy.json")
REVIEW = Path("data/review-years.json")

RAA_URL = "https://pub.raa.se/visa/objekt/bebyggelse/"
RAA_FIELDS = ["namn", "alternativnamn", "objekttyp_namn", "registerbyggnad_id", "klassificering",
              "nybyggnad_tillkomstar_from", "nybyggnad_tillkomstar_tom", "andamal_huvudgrupp", "upphov",
              "kommunnamn", "url", "skyddstyp_namn", "beslutsdatum"]   # the last two: s02_attributes
OVERLAP_MIN = 0.5              # share of a footprint an unmatched RAÄ polygon must cover
TIE_M2 = 1.0                   # overlaps this close to the best one count as a tie
DISAGREE_YEARS = 10            # a Wikidata or OSM year this far outside RAÄ's range goes on the review list
MIN_PRIVATE_OVERLAP = 2        # years a private decade must share with its period (s99's rule)
BUILDING_COLUMNS = ["gid", "uuid", "kategori", "fastighet", "height", "area", "prod_year", "fnr", "geometry"]
PERIOD_FROM = np.array([p[3] for p in city.PERIODS], dtype=np.int64)
PERIOD_TO = np.minimum(np.array([p[4] for p in city.PERIODS], dtype=np.int64), LATEST_YEAR)


def raa_id_from_url(url) -> str:
    """RAÄ's own object id, the last path part of its public record URL; "" for anything else."""
    if isinstance(url, str) and url.startswith(RAA_URL):
        return url[len(RAA_URL):].strip("/")
    return ""


def in_stockholm(kommunnamn) -> np.ndarray:
    """True where a record's kommunnamn names Stockholm, alone or in a ";" list: RAÄ writes a building on the border as
    'Solna;Stockholm' (a border fix: two such records on 2026-10-16)."""
    return np.array([isinstance(k, str) and "Stockholm" in [p.strip() for p in k.split(";")] for k in kommunnamn],
                    dtype=bool)


def load_raa(path: Path = RAA_GPKG, layer: str = RAA_LAYER) -> gpd.GeoDataFrame:
    """Stockholm kommun's RAÄ objects in EPSG:3011, with raa_id, border records ('Solna;Stockholm') included.

    The layer mixes Polygon and MultiPolygon (pyogrio reports its geometry type as "Unknown"); every
    function below works on either.
    """
    raa = pyogrio.read_dataframe(path, layer=layer, columns=RAA_FIELDS, where="kommunnamn LIKE '%Stockholm%'")
    raa = raa[in_stockholm(raa.kommunnamn)].reset_index(drop=True)
    raa = raa.to_crs(city.CRS)
    raa["geometry"] = shapely.make_valid(raa.geometry.values)
    raa["raa_id"] = raa.url.map(raa_id_from_url)
    return raa


def pick(pairs: pd.DataFrame) -> pd.DataFrame:
    """One RAÄ record per gid from candidate pairs (gid, raa_id, year_from, year_to, overlap).

    The record covering most of the footprint wins. Overlaps within TIE_M2 of the best tie; tied
    records with different years give the earliest year_from, the latest year_to and the LONG flag.
    Returns one row per gid: raa_id, year_from, year_to, year, yflag.
    """
    cols = ["raa_id", "year_from", "year_to", "year", "yflag"]
    if pairs.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="gid"))
    best = pairs.groupby("gid").overlap.transform("max")
    tied = pairs[pairs.overlap >= best - TIE_M2].sort_values(["gid", "year_from", "year_to", "raa_id"])
    win = tied.groupby("gid").head(1).set_index("gid")
    latest = tied.groupby("gid").year_to.max().reindex(win.index).to_numpy()
    disagree = (tied.drop_duplicates(["gid", "year_from", "year_to"]).groupby("gid").size() > 1)
    disagree = disagree.reindex(win.index).to_numpy()
    year, flag = display(win.year_from.to_numpy(), win.year_to.to_numpy())
    win["year_to"] = np.where(disagree, latest, win.year_to)
    win["year"] = np.where(disagree, win.year_from, year)
    win["yflag"] = np.where(disagree, LONG, flag)
    return win[cols]


def _overlap(a, b) -> np.ndarray:
    return shapely.area(shapely.intersection(a, b))


def match_raa(b: gpd.GeoDataFrame, recs: gpd.GeoDataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """RAÄ building years per gid, and the linked RAÄ id for every footprint a record joins.

    recs: cleaned Byggnad records (clean_years). Returns (years indexed by gid, raa_id by gid).
    The link comes from the record that gave the year. A footprint whose joined records have rejected or
    missing years keeps the link of the best joined record (most overlap, then the pick() tie-break), not a year.
    """
    b = b[["gid", "uuid", "geometry"]]
    has_uuid = b[b.uuid != ""]
    m = recs.merge(has_uuid.rename(columns={"geometry": "fp"}), left_on="registerbyggnad_id",
                   right_on="uuid", how="inner")
    m["overlap"] = _overlap(m.geometry.values, m.fp.values)
    by_uuid = pick(m[m.year_ok])
    link = pick(m).raa_id                      # best record per footprint, year or not
    link.loc[by_uuid.index] = by_uuid.raa_id

    # RAÄ polygons that join no UUID: date the footprints they cover by at least half.
    unmatched = recs[recs.year_ok & ~recs.registerbyggnad_id.isin(set(has_uuid.uuid))]
    free = b[~b.gid.isin(by_uuid.index)]
    hits = gpd.sjoin(unmatched[["raa_id", "year_from", "year_to", "geometry"]],
                     free.set_geometry("geometry"), predicate="intersects", how="inner")
    if len(hits):
        fp = free.set_index("gid").geometry.reindex(hits.gid).values
        hits["overlap"] = _overlap(hits.geometry.values, fp)
        hits = hits[hits.overlap >= OVERLAP_MIN * shapely.area(fp)]
    by_overlap = pick(pd.DataFrame(hits.drop(columns="geometry")))
    link = pd.concat([link[~link.index.isin(by_overlap.index)], by_overlap.raa_id])
    return pd.concat([by_uuid, by_overlap]).sort_index(), link.sort_index()


def match_areas(b: gpd.GeoDataFrame, areas: gpd.GeoDataFrame) -> pd.DataFrame:
    """Years from dated Område polygons: centroid inside, smallest polygon wins."""
    cols = ["year_from", "year_to", "year", "yflag"]
    pts = gpd.GeoDataFrame({"gid": b.gid.values}, geometry=b.geometry.centroid.values, crs=b.crs)
    a = areas[["raa_id", "year_from", "year_to", "geometry"]].copy()
    a["size"] = a.geometry.area
    hits = gpd.sjoin(pts, a, predicate="within", how="inner")
    if hits.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="gid"))
    win = hits.sort_values(["gid", "size", "raa_id"]).groupby("gid").head(1).set_index("gid")
    win["year"], _ = display(win.year_from.to_numpy(), win.year_to.to_numpy())
    win["yflag"] = AREA
    return win[cols]


def _entries(gids, pos, name_of, years_by_gid, year, y_from, y_to, extra=None):
    """Review-list rows for gids: the source's year span against the row's current (winning) span."""
    out = []
    for g in gids:
        k = pos[g]
        row = {"gid": int(g), "name": name_of(g), "year_from": int(years_by_gid.year_from[g]),
               "year_to": int(years_by_gid.year_to[g]),
               "winner_year": int(year[k]), "winner_from": int(y_from[k]), "winner_to": int(y_to[k])}
        if extra:
            row.update(extra(g))
        out.append(row)
    return out


def disagree(src: pd.DataFrame, y_from, y_to, pos, years: int = DISAGREE_YEARS) -> np.ndarray:
    """gids in src whose [year_from, year_to] lies more than `years` outside the winner's [from, to]."""
    k = pos[src.index].to_numpy()
    lo, hi = src.year_from.to_numpy(), src.year_to.to_numpy()
    out = (hi < y_from[k] - years) | (lo > y_to[k] + years)
    return src.index.to_numpy()[out]


def assign_years(b: gpd.GeoDataFrame, raa: gpd.GeoDataFrame, landmarks: list[dict], *, raa_old=None, wikidata=None,
                 osm=None, stadsdel=None, estimates: bool = True, params: dict | None = None,
                 exclude: set[int] = frozenset(), reader: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """years.parquet rows for buildings b (gid, uuid, kategori, geometry and, for the estimate tier,
    fastighet, height, area, prod_year, fnr; EPSG:3011), plus a report (raa_rejected, landmarks, review, accuracy).

    raa_old, wikidata, osm: the loaded source frames (years_*.load), or None to skip that tier. stadsdel: the
    stadsdel name per building (estimate.stadsdel_of), or None for "all outer city". estimates=False skips the
    estimate tier (the accuracy table is then empty). params: city.ESTIMATE, or a copy with other settings.
    exclude: the takedowns' gids (pipeline/suppress.py). No tier dates them, so their years never train or
    test the estimate tier or the area check: an objection stops that use too (GDPR Art. 21), not only the display.
    reader: contributions.reader_years' rows (gid: ref, year_from, year_to, replaces), applied after every other tier,
    so they neither train nor test the estimate; a row the tier refuses stops the step (contributions.Refused).
    """
    p = city.ESTIMATE if params is None else params
    n = len(b)
    gid = b.gid.to_numpy().astype(np.int64)
    pos = pd.Series(np.arange(n), index=gid)
    year = np.zeros(n, np.int64)
    y_from = np.zeros(n, np.int64)
    y_to = np.zeros(n, np.int64)
    ysrc = np.full(n, SRC_NONE, np.int64)
    yflag = np.full(n, UNKNOWN, np.int64)
    raa_id = np.full(n, "", dtype=object)
    landmark = np.full(n, "", dtype=object)

    recs = clean_years(raa)
    rejected = recs[recs.dated & ~recs.year_ok]        # dated but implausible; undated records were never dated
    report = {"raa_rejected": rejected[["raa_id", "namn", "objekttyp_namn", "andamal_huvudgrupp",
                                        "year_from", "year_to"]].to_dict("records")}

    def write(rows: pd.DataFrame, src: int):
        """Write a tier's rows (indexed by gid): the flag from the display rule on the span, the year from the
        frame's own `year` column when it has one (Wikidata, OSM: a decade's start, a circa's stated year), else
        from the display rule. Later tiers overwrite."""
        if rows.empty:
            return
        i = pos[rows.index].to_numpy()
        yr, fl = display(rows.year_from.to_numpy(), rows.year_to.to_numpy())
        if "year" in rows:
            yr = rows.year.to_numpy().astype(np.int64)
        year[i], y_from[i], y_to[i] = yr, rows.year_from.to_numpy(), rows.year_to.to_numpy()
        ysrc[i], yflag[i] = src, fl

    # Lowest tiers first, so every higher tier overwrites them.
    o = years_osm.match(b, osm) if osm is not None else None
    if o is not None:
        write(o, SRC_OSM)
    w = years_wikidata.match(b, wikidata) if wikidata is not None else None
    if w is not None:
        write(w, SRC_WIKIDATA)

    areas = recs[(recs.objekttyp_namn == "Område") & recs.year_ok]
    a = match_areas(b, gpd.GeoDataFrame(areas, geometry="geometry", crs=raa.crs))
    i = pos[a.index].to_numpy()
    year[i], y_from[i], y_to[i] = a.year, a.year_from, a.year_to
    ysrc[i], yflag[i] = SRC_RAA_AREA, AREA

    old = years_raa_old.match(b, raa_old) if raa_old is not None else None
    if old is not None:
        write(old, SRC_RAA_OLD)

    byggnad = gpd.GeoDataFrame(recs[recs.objekttyp_namn == "Byggnad"], geometry="geometry", crs=raa.crs)
    r, link = match_raa(b, byggnad)
    i = pos[r.index].to_numpy()
    year[i], y_from[i], y_to[i], yflag[i] = r.year, r.year_from, r.year_to, r.yflag
    ysrc[i] = SRC_RAA
    raa_id[pos[link.index].to_numpy()] = link.to_numpy()

    report["landmarks_dropped"], report["landmarks"] = [], {}
    if landmarks:
        xs, ys = lonlat_to_3011([L["lon"] for L in landmarks], [L["lat"] for L in landmarks])
        for L, g in zip(landmarks, resolve_points(b, xs, ys)):
            if g < 0 or landmark[pos[g]]:
                report["landmarks_dropped"].append(L["name"])
                continue
            k = pos[g]
            year[k], y_from[k], y_to[k] = L["year"], L["year_from"], L["year_to"]
            ysrc[k] = SRC_CURATED
            yflag[k] = EXACT if L["year_from"] == L["year_to"] else RANGE
            landmark[k] = L["name"]
            report["landmarks"][L["name"]] = int(g)

    # A takedown is dated by nothing from here on (main() draws it as "Year unknown" afterwards).
    gone_gids = [g for g in exclude if g in pos.index]
    gone = pos[gone_gids].to_numpy()
    year[gone], y_from[gone], y_to[gone], ysrc[gone], yflag[gone] = 0, 0, 0, SRC_NONE, UNKNOWN
    raa_id[gone], landmark[gone] = "", ""

    # The curated review list: a Wikidata or OSM year more than DISAGREE_YEARS outside the winning
    # RAÄ, area or curated span; century-precision Wikidata items; and every Wikidata gain, so the owner can scan them.
    review = {"wikidata_vs_raa": [], "wikidata_vs_area": [], "wikidata_vs_curated": [], "osm_vs_raa": [],
              "wikidata_century": [], "wikidata_gains": []}
    if w is not None and len(w):
        def name_w(g):
            return str(w.name[g])

        def qid_w(g):
            return {"qid": str(w.qid[g]), "article": bool(w.article[g]), "placement": str(w.placement[g])}

        bad = disagree(w, y_from, y_to, pos)
        src_of = ysrc[pos[bad].to_numpy()]
        for key, src in (("wikidata_vs_raa", (SRC_RAA, SRC_RAA_OLD)), ("wikidata_vs_area", (SRC_RAA_AREA,)),
                         ("wikidata_vs_curated", (SRC_CURATED,))):
            review[key] = _entries(bad[np.isin(src_of, src)], pos, name_w, w, year, y_from, y_to, qid_w)
        gains = w.index.to_numpy()[ysrc[pos[w.index].to_numpy()] == SRC_WIKIDATA]
        review["wikidata_gains"] = _entries(gains, pos, name_w, w, year, y_from, y_to, qid_w)
    if wikidata is not None and len(wikidata):
        century = wikidata[wikidata.dropped == "century"]
        review["wikidata_century"] = [{"qid": q, "name": nm, "precision": int(pr)}
                                      for q, nm, pr in zip(century.qid, century.name, century.precision)]
    if o is not None and len(o):
        bad = disagree(o, y_from, y_to, pos)
        bad = bad[np.isin(ysrc[pos[bad].to_numpy()], (SRC_RAA, SRC_RAA_OLD))]
        review["osm_vs_raa"] = _entries(bad, pos, lambda g: str(o.name[g]), o, year, y_from, y_to,
                                        lambda g: {"osm_id": str(o.osm_id[g])})
    report["review"] = review

    # The estimate tier, on everything still without a year. Training and testing use the in-memory exact years
    # (private houses are rounded to their decade only below) of every building-level tier, never area years (they are not
    # building-level anchors).
    train = (ysrc != SRC_NONE) & (ysrc != SRC_RAA_AREA)
    query = ysrc == SRC_NONE
    accuracy = {"method": "knn", "held_out": "kvarter", "folds": p["folds"], "near_m": p["near_m"],
                "min_cell": p["min_cell"], "min_right": p["min_right"], "max_band": p["max_band"],
                "tested": int(train.sum()), "cells": [], "fallback": [], "band_coverage": None, "by_true_period": [],
                "result": {"estimate": 0, "period": 0, "unknown": int(query.sum())}}
    external = est.no_external()
    if estimates:
        f = est.features(b, stadsdel=stadsdel)
        got, accuracy = est.run(f, year, train, query, p=p, stadsdel=stadsdel)
        rows = np.flatnonzero(got.yflag.to_numpy() != UNKNOWN)
        if len(rows):
            yh = np.clip(np.round(got.yhat.to_numpy()[rows]), FLOOR_YEAR, LATEST_YEAR).astype(np.int64)
            fl = got.yflag.to_numpy()[rows]
            bd = got.band.to_numpy()[rows]
            per = city.period_indices(yh)
            is_est = fl == ESTIMATE
            year[rows], ysrc[rows], yflag[rows] = yh, SRC_ESTIMATE, fl
            y_from[rows] = np.where(is_est, np.maximum(FLOOR_YEAR, yh - bd), PERIOD_FROM[per])
            y_to[rows] = np.where(is_est, np.minimum(LATEST_YEAR, yh + bd), PERIOD_TO[per])
        # The independent check: the map's own rule (kvarter bonus, the built table, every gate), trained
        # on curated + raa + raa_old alone, run on the rows only Wikidata or OSM dated (RAÄ never did) as if they had
        # no year, and counted per map state. The years are the in-memory ones, before private houses are rounded to their decade.
        ext = np.isin(ysrc, (SRC_WIKIDATA, SRC_OSM))
        core = np.isin(ysrc, (SRC_CURATED, SRC_RAA, SRC_RAA_OLD))
        external = est.check_external(f, year, core, ext, accuracy, p, stadsdel)
    # The area tier's accuracy: area years against the building-level years inside the same polygons.
    # A building's level year is the winner's when a higher tier won (curated, raa, raa_old), else the Wikidata or
    # OSM year the area tier outranked (Wikidata first): written below the area tier, they never win inside a
    # polygon. The years are unrounded (private houses are rounded below); scored by est.score, like the cells and the external check.
    level = np.where(np.isin(ysrc, (SRC_CURATED, SRC_RAA, SRC_RAA_OLD)), year, 0)
    for t in (w, o):
        if t is not None and len(t):
            k = pos[t.index].to_numpy()
            free = level[k] == 0
            level[k[free]] = t.year.to_numpy(dtype=np.int64)[free]
    level[gone] = 0
    ka = pos[a.index].to_numpy()
    both = level[ka] > 0
    area_acc = {"n": int(both.sum()), "status": "not measurable"}
    if area_acc["n"] >= p["min_cell"]:
        area_acc.update(status="measured", **est.score(a.year.to_numpy(dtype=np.int64)[both], level[ka][both]))
    accuracy["area"] = area_acc
    accuracy["external"] = external
    report["accuracy"] = accuracy

    # The reader tier, last: a checked report on top of what the sources and the estimate gave.
    report["reader"] = 0
    if reader is not None and len(reader):
        report["reader"] = contributions.apply_years(reader, pos, year, y_from, y_to, ysrc, yflag, gone=gone_gids)
        # the table describes what ships (s99 ties tested and result to stats.byFlag), as suppress.accuracy does
        accuracy["tested"] = int(np.isin(yflag, (EXACT, RANGE, LONG)).sum())
        accuracy["result"] = {**accuracy["result"], "estimate": int((yflag == ESTIMATE).sum()),
                              "period": int((yflag == PERIOD).sum()), "unknown": int((yflag == UNKNOWN).sum())}

    # Period from the year before the decade rounding, so the map keeps each house's period colour.
    period = np.where(year > 0, city.period_indices(year), 0)

    # Private houses publish only their decade, unless curated. yflag keeps saying how the year is known.
    private = b.kategori.isin(city.PRIVATE_HOUSE_KATEGORI).to_numpy() & (ysrc != SRC_CURATED) & (yflag != UNKNOWN)
    year[private] = year[private] // 10 * 10
    y_from[private], y_to[private] = year[private], year[private] + 9
    # A decade and a period that share fewer than MIN_PRIVATE_OVERLAP years would pin the year (1610 in p1, 1719
    # in p3): the decade wins and the period is taken from its middle year (1615, 1715: both Stormaktstiden).
    shared = np.minimum(year + 9, PERIOD_TO[period]) - np.maximum(year, PERIOD_FROM[period]) + 1
    narrow = private & (shared < MIN_PRIVATE_OVERLAP)
    period[narrow] = city.period_indices(year[narrow] + 5)

    out = pd.DataFrame({
        "gid": gid.astype(np.int32),
        "year": year.astype(np.int16), "year_from": y_from.astype(np.int16), "year_to": y_to.astype(np.int16),
        "ysrc": ysrc.astype(np.uint8), "yflag": yflag.astype(np.uint8), "period": period.astype(np.uint8),
        "private": private.astype(bool),
        "raa_id": pd.array(raa_id, dtype="str"), "landmark": pd.array(landmark, dtype="str"),
    })
    return out.sort_values("gid").reset_index(drop=True), report


def summary(y: pd.DataFrame) -> dict:
    """Counts for the run log and the real-data test. byFlag is keyed by the yflag value (codes.py)."""
    return {
        "buildings": len(y),
        "curated": int((y.ysrc == SRC_CURATED).sum()),
        "raa": int((y.ysrc == SRC_RAA).sum()),
        "raa_old": int((y.ysrc == SRC_RAA_OLD).sum()),
        "raa_area": int((y.ysrc == SRC_RAA_AREA).sum()),
        "wikidata": int((y.ysrc == SRC_WIKIDATA).sum()),
        "osm": int((y.ysrc == SRC_OSM).sum()),
        "reader": int((y.ysrc == SRC_READER).sum()),
        "estimate": int((y.yflag == ESTIMATE).sum()),
        "period": int((y.yflag == PERIOD).sum()),
        "private": int(y.private.sum()),
        "unknown": int((y.yflag == UNKNOWN).sum()),
        "byFlag": {int(k): int(v) for k, v in y.yflag.value_counts().sort_index().items()},
        "with_raa_id": int((y.raa_id != "").sum()),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s02_years", description=__doc__.splitlines()[0])
    ap.add_argument("--buildings", type=Path, default=BUILDINGS)
    ap.add_argument("--raa", type=Path, default=RAA_GPKG)
    ap.add_argument("--raa-old", type=Path, default=years_raa_old.DEST,
                    help="the OLD register snapshot; skipped if absent")
    ap.add_argument("--wikidata", type=Path, default=years_wikidata.DATED)
    ap.add_argument("--wikidata-classes", type=Path, default=years_wikidata.CLASSES)
    ap.add_argument("--osm", type=Path, default=years_osm.DEST)
    ap.add_argument("--stadsdelar", type=Path, default=STADSDELAR)
    ap.add_argument("--landmarks", type=Path, default=LANDMARKS_JSON, help="the entries s08_landmarks verified")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--accuracy-out", type=Path, default=ACCURACY)
    ap.add_argument("--review-out", type=Path, default=REVIEW)
    ap.add_argument("--no-estimates", action="store_true", help="skip the estimate tier (a quick build)")
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    ap.add_argument("--contributions", type=Path, default=contributions.PATH, help="accepted readers' reports")
    a = ap.parse_args(argv or [])
    b = gpd.read_parquet(a.buildings)
    try:
        reader = contributions.reader_years(contributions.read(a.contributions), b) if a.contributions.exists() else None
    except ValueError as e:
        raise SystemExit(f"contributions: {e}; {a.out} is unchanged")
    if "fnr" not in b.columns and not a.no_estimates:
        # Without the property-unit key the estimate tier's late-unit guard would be off without a word
        raise SystemExit(f"run s01_load first ({a.buildings} has no fnr, the property-unit key the estimate tier's "
                         f"guard needs: it was written before 2026-10-15); {a.out} is unchanged")
    b = b[[c for c in BUILDING_COLUMNS if c in b.columns]]
    for path, step in ((a.wikidata, "s00_fetch_wikidata"), (a.wikidata_classes, "s00_fetch_wikidata"),
                       (a.osm, "s00_fetch_osm")):
        if not path.exists():
            raise SystemExit(f"{path} is missing: run {step} first")
    raa_old = None
    if a.raa_old.exists():
        raa_old = years_raa_old.load(a.raa_old)
    else:
        print(f"warning: {a.raa_old} is missing (s00_fetch_raa_old found no file): no raa_old tier", file=sys.stderr)
    # A takedown is dated by no tier, so it neither trains nor tests the estimate; it is drawn as "Year
    # unknown", and the table counts what ships (pipeline/suppress.py)
    hidden = suppress.gids_of(a.buildings, a.suppress)
    try:
        years, report = assign_years(
            b, load_raa(a.raa), load_landmarks(a.landmarks), raa_old=raa_old,
            wikidata=years_wikidata.load(a.wikidata, a.wikidata_classes),
            osm=years_osm.load(a.osm), stadsdel=est.stadsdel_of(b, a.stadsdelar), estimates=not a.no_estimates,
            exclude=hidden, reader=reader)
    except contributions.Refused as e:
        raise SystemExit(f"contributions: {e}; {a.out} is unchanged")
    if hidden:
        before, years = years, suppress.years(years, hidden)
        report["accuracy"] = suppress.accuracy(report["accuracy"], before, years)
    s = summary(years)
    if s["raa"] == 0:
        raise SystemExit(f"no building got a RAÄ year from {a.raa} (did RAÄ rename kommunnamn 'Stockholm' or "
                         f"registerbyggnad_id?); {a.out} is unchanged")
    if s["with_raa_id"] == 0:
        raise SystemExit(f"no building carries a RAÄ link (did RAÄ change its record URL prefix {RAA_URL}?); "
                         f"{a.out} is unchanged")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    years.to_parquet(a.out, index=False)
    a.accuracy_out.parent.mkdir(parents=True, exist_ok=True)
    a.accuracy_out.write_text(json.dumps(report["accuracy"], indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    a.review_out.parent.mkdir(parents=True, exist_ok=True)
    a.review_out.write_text(json.dumps(report["review"], indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    for r in report["raa_rejected"]:
        print("RAÄ year rejected:", r)
    for name in report["landmarks_dropped"]:
        print("landmark dropped (no footprint within 15 m, or one already taken):", name)
    print("landmarks placed:", report["landmarks"])
    print("review list:", {k: len(v) for k, v in report["review"].items()}, "->", a.review_out)
    print("estimate tier:", report["accuracy"].get("result"), "area tier:", report["accuracy"].get("area"),
          "->", a.accuracy_out)
    print(s)


if __name__ == "__main__":
    main(sys.argv[1:])
