"""Wikidata as a year source (the year model's fourth tier).

load(): the cached results of s00_fetch_wikidata -> one row per item that is a building (P31/P279* Q41176) and not
an organisation, museum, art museum, art gallery or destroyed building, has no P576 and is not directly typed as a
work of art, with one year rule applied to its best-rank P571 (else P1619) statements:
  - a statement with "applies to part" (P518) is skipped when the item has one without;
  - precision 9 or finer (year, month, day): the calendar year; several distinct values give from = earliest and
    to = latest;
  - precision 8 (decade): from = the decade start, to = start + 9 (RANGE; year = the decade start, so the card
    prints "1640s" and the timeline draws the house at 1640);
  - precision 7 or coarser (a century): dropped, with the reason "century" for the review list;
  - "circa" (P1480 = Q5727902): year = the stated year, from/to = that year -/+ CIRCA;
  - a year below 1000 or after 2026: dropped ("out of range").
  year, for a span of distinct values, follows yearrules.display (the completion year for 15 years or less).
Items that fail the class rules or the year rule are kept in the frame with `dropped` set, so the review list can
name them; `kept` rows have dropped == "". The box query's points are not clipped to the municipality: a point
only matters when it lands on one of our footprints (match()).

match(): resolve_points with MAX_M, so a point inside a footprint, inside its outer ring (a courtyard) or within
30 m of one dates it (the nearest, then the lowest gid, when several are within reach); a footprint that receives
two kept items gets nothing (LOD1 sometimes merges neighbours). `placement` (geo.placement) says which of the
three it was, for the review list. Labels (CC0) and article links stay internal: the review list uses them, the
web data gets only the year.

DATED and CLASSES, qid() and rows() belong to s00_fetch_wikidata and are imported from there, not copied.
"""
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import lonlat_to_3011, placement, resolve_points
from .s00_fetch_wikidata import CLASSES, DATED, qid, rows
from .yearrules import FLOOR_YEAR, LATEST_YEAR, display

MAX_M = 30.0
CIRCA = 5
KEEP = {"Q41176"}                                                      # building
EXCLUDE = {"Q43229": "organization", "Q33506": "museum", "Q207694": "art museum", "Q1007870": "art gallery",
           "Q19860854": "destroyed building"}
ARTWORK_P31 = {"Q860861", "Q179700", "Q483453", "Q557141", "Q219423", "Q4989906", "Q5003624"}   # direct P31 only
CIRCA_QID = "Q5727902"
PRECISION_DECADE, PRECISION_YEAR = 8, 9
POINT = re.compile(r"Point\(([-0-9.eE]+) ([-0-9.eE]+)\)")
TIME = re.compile(r"^([+-]?)(\d+)-")


def year_of_time(t: str) -> int:
    m = TIME.match(t)
    y = int(m.group(2))
    return -y if m.group(1) == "-" else y


def ancestors(edges) -> dict[str, set[str]]:
    """Every class's set of ancestors (the class itself included) from (class, direct superclass) pairs."""
    up = defaultdict(set)
    for a, b in edges:
        up[a].add(b)
    memo = {}

    def anc(c):
        if c in memo:
            return memo[c]
        seen, stack = {c}, [c]
        while stack:
            x = stack.pop()
            for y in up.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        memo[c] = seen
        return seen

    return {c: anc(c) for c in set(up) | {b for _, b in edges}}


def classify(classes: set[str], anc: dict[str, set[str]]) -> str:
    """"" when the item is a kept building, else why it is dropped."""
    up = set()
    for c in classes:
        up |= anc.get(c, {c})
    if classes & ARTWORK_P31:
        return "work of art"
    for root, why in EXCLUDE.items():
        if root in up:
            return why
    if not (up & KEEP):
        return "not a building"
    return ""


def year_of(statements: list[dict]) -> tuple[int, int, int, int, str]:
    """(year, year_from, year_to, precision, dropped) from an item's statements ({prop, time, precision, part,
    circa}). year is what the map publishes: the decade start for a decade, the stated year for a circa, else the
    display rule on the span of distinct values."""
    for prop in ("P571", "P1619"):
        s = [st for st in statements if st["prop"] == prop]
        if not s:
            continue
        whole = [st for st in s if not st.get("part")]
        s = whole or s
        fine = [st for st in s if int(st["precision"]) >= PRECISION_YEAR]
        s = fine or s
        precision = max(int(st["precision"]) for st in s)
        if precision < PRECISION_DECADE:
            return 0, 0, 0, precision, "century"
        years = sorted({year_of_time(st["time"]) for st in s})
        lo, hi = years[0], years[-1]
        if precision == PRECISION_DECADE:
            lo, hi = lo // 10 * 10, hi // 10 * 10 + 9
            year = lo
        else:
            year = int(display(np.array([lo]), np.array([hi]))[0][0])     # before any circa widening
        if any(st.get("circa") == CIRCA_QID for st in s):
            lo, hi = lo - CIRCA, hi + CIRCA
        if lo < FLOOR_YEAR or hi > LATEST_YEAR:
            return 0, 0, 0, precision, "out of range"
        return year, lo, hi, precision, ""
    return 0, 0, 0, 0, "no date"


def load(dated: Path = DATED, classes: Path = CLASSES) -> pd.DataFrame:
    """One row per item of the dated query: qid, name, x, y, year, year_from, year_to, precision, article, dropped."""
    binds = rows(dated)
    anc = ancestors([(qid(r["a"]), qid(r["b"])) for r in rows(classes)])
    items: dict[str, dict] = {}
    for r in binds:
        q = qid(r["item"])
        it = items.setdefault(q, {"qid": q, "classes": set(), "statements": {}, "ended": False, "coord": None,
                                  "sv": "", "en": "", "article": False})
        if "cls" in r:
            it["classes"].add(qid(r["cls"]))
        key = (r["prop"], r["time"], r["precision"], r.get("part", ""), r.get("circa", ""))
        it["statements"][key] = {"prop": r["prop"], "time": r["time"], "precision": r["precision"],
                                 "part": qid(r["part"]) if r.get("part") else "",
                                 "circa": qid(r["circa"]) if r.get("circa") else ""}
        it["ended"] |= r.get("ended") == "true"
        if it["coord"] is None and (m := POINT.search(r.get("coord", ""))):
            it["coord"] = (float(m.group(1)), float(m.group(2)))
        it["sv"] = it["sv"] or r.get("sv", "")
        it["en"] = it["en"] or r.get("en", "")
        it["article"] |= bool(r.get("svwiki") or r.get("enwiki"))
    out = []
    for it in items.values():
        dropped = classify(it["classes"], anc)
        if not dropped and it["ended"]:
            dropped = "demolished or dissolved (P576)"
        year, lo, hi, precision, why = year_of(list(it["statements"].values()))
        dropped = dropped or why
        if it["coord"] is None:
            dropped = dropped or "no coordinate"
        lon, lat = it["coord"] or (np.nan, np.nan)
        out.append({"qid": it["qid"], "name": it["sv"] or it["en"] or it["qid"], "lon": lon, "lat": lat, "year": year,
                    "year_from": lo, "year_to": hi, "precision": precision, "article": bool(it["article"]),
                    "dropped": dropped})
    df = pd.DataFrame(out, columns=["qid", "name", "lon", "lat", "year", "year_from", "year_to", "precision", "article", "dropped"])
    x, y = lonlat_to_3011(df.lon.to_numpy(dtype=float), df.lat.to_numpy(dtype=float))
    df["x"], df["y"] = x, y
    return df[["qid", "name", "x", "y", "year", "year_from", "year_to", "precision", "article", "dropped"]].sort_values("qid").reset_index(drop=True)


def match(b, items: pd.DataFrame, max_dist: float = MAX_M) -> pd.DataFrame:
    """One row per footprint that receives exactly one kept item: year, year_from, year_to, qid, name, article,
    placement; indexed by gid, sorted."""
    cols = ["year", "year_from", "year_to", "qid", "name", "article", "placement"]
    kept = items[(items.dropped == "") & items.x.notna()] if len(items) else items
    if kept.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="gid"))
    xs, ys = kept.x.to_numpy(), kept.y.to_numpy()
    gids = resolve_points(b, xs, ys, max_dist)
    hit = kept.assign(gid=gids, placement=placement(b, gids, xs, ys))
    hit = hit[hit.gid >= 0]
    counts = hit.groupby("gid").size()
    one = hit[hit.gid.map(counts) == 1].set_index("gid")
    one.index.name = "gid"
    return one[cols].sort_index()
