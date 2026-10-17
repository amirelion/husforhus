"""OpenStreetMap start_date as a year source (Plan 2 tier `osm`, below Wikidata; docs/research/2026-10-15-data-hunt.md §4).

load(): the cached Overpass result (s00_fetch_osm) -> one row per dated OSM building with a usable date.
parse_date(): the formats mappers use. A plain year, a date (1906-06-10) and a month (2009-04) give that year; a
decade ("1940s") the range 1940–1949; "1865 - 1878" or "2017-2019" a range; "~1920" 1915–1925. A century ("1700s",
"1100s"), "early 1700s", "after 1908", "1635 / 1854" and anything else gives nothing. Years outside 1000..2026 give
nothing. stated_year(): the year the map publishes (D6, shown honestly): the stated year for "~1920", the decade
start for "1940s" (the card prints "1940s"), and RAÄ's completion-year rule only for a real span. match(): the
element's centre inside a footprint, else the nearest within MAX_M; a footprint that receives two OSM buildings
with different dates gets nothing. Names (ODbL) stay internal: only the year ships.
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import lonlat_to_3011, resolve_points
from .s00_fetch_osm import DEST
from .yearrules import FLOOR_YEAR, LATEST_YEAR, display

MAX_M = 15.0
CIRCA = 5                      # "~1920" is shown as the range 1915–1925
DATE_TAGS = ("start_date", "year_of_construction", "construction_date")
YEAR = re.compile(r"^(\d{4})(?:-\d{2}(?:-\d{2})?)?$")       # 1916, 2009-04, 1906-06-10
DECADE = re.compile(r"^(\d{2}[1-9])0s$")                    # 1940s (but not 1900s: a century)
SPAN = re.compile(r"^(\d{4})\s*[-–]\s*(\d{4})$")             # 1865 - 1878, 2017-2019
ABOUT = re.compile(r"^~\s*(\d{4})$")                        # ~1920


def parse_date(s) -> tuple[int, int] | None:
    """(year_from, year_to) for an OSM date tag, or None when it carries no usable year."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    if m := YEAR.match(s):
        y = int(m.group(1))
        lo, hi = y, y
    elif m := DECADE.match(s):
        lo = int(m.group(1)) * 10
        hi = lo + 9
    elif m := SPAN.match(s):
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
    elif m := ABOUT.match(s):
        y = int(m.group(1))
        lo, hi = y - CIRCA, y + CIRCA
    else:
        return None
    if lo < FLOOR_YEAR or hi > LATEST_YEAR:
        return None
    return lo, hi


def stated_year(s, lo: int, hi: int) -> int:
    """The year to publish for a parsed tag (lo, hi): "~1920" gives 1920, "1940s" gives 1940, a real span goes
    through the RAÄ display rule (completion year for 15 years or less, else the start)."""
    s = (s or "").strip()
    if m := ABOUT.match(s):
        return int(m.group(1))
    if DECADE.match(s):
        return lo
    return int(display(np.array([lo]), np.array([hi]))[0][0])


def load(path: Path = DEST) -> pd.DataFrame:
    """osm_id, name, x, y (EPSG:3011), year, year_from, year_to for every OSM building (not a bare building:part)
    with a centre and a usable date tag, in result order."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for e in data.get("elements", []):
        tags = e.get("tags") or {}
        if "building" not in tags:
            continue
        centre = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
        if centre is None:
            continue
        tag = next((tags[t] for t in DATE_TAGS if t in tags), None)
        date = parse_date(tag)
        if date is None:
            continue
        rows.append({"osm_id": f"{e['type']}/{e['id']}", "name": tags.get("name", ""), "lon": float(centre["lon"]),
                     "lat": float(centre["lat"]), "year": stated_year(tag, *date), "year_from": date[0], "year_to": date[1]})
    df = pd.DataFrame(rows, columns=["osm_id", "name", "lon", "lat", "year", "year_from", "year_to"])
    x, y = lonlat_to_3011(df.lon.to_numpy(dtype=float), df.lat.to_numpy(dtype=float))
    df["x"], df["y"] = x, y
    return df[["osm_id", "name", "x", "y", "year", "year_from", "year_to"]]


def match(b, osm: pd.DataFrame, max_dist: float = MAX_M) -> pd.DataFrame:
    """One row per footprint that receives exactly one dated OSM building (or several that agree): year,
    year_from, year_to, osm_id, name; indexed by gid, sorted."""
    cols = ["year", "year_from", "year_to", "osm_id", "name"]
    if osm.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="gid"))
    hit = osm.assign(gid=resolve_points(b, osm.x.to_numpy(), osm.y.to_numpy(), max_dist))
    hit = hit[hit.gid >= 0]
    distinct = hit.drop_duplicates(["gid", "year_from", "year_to"]).groupby("gid").size()
    one = hit[hit.gid.map(distinct) == 1].sort_values(["gid", "osm_id"]).drop_duplicates("gid").set_index("gid")
    one.index.name = "gid"
    return one[cols].sort_index()
