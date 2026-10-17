"""OpenStreetMap addresses on LOD1 footprints (OSM is the only address source).

load(): addr:street + addr:housenumber from the tiles s00_fetch_osm cached (data/raw/osm/addresses/*.json, Overpass
JSON: nodes with their position, ways and relations with their centre), one row per element, deduplicated across
tiles (an element on a tile edge comes back in both), in EPSG:3011. numbers(): a house number as the card and search
write it: "12" stays, "12a" and "12 A" read "12A", a range or list ("12-14", "3;5", "3, 5") gives each end or item,
and anything else ("1 tr", "Gård") gives nothing. assign(): an address belongs to the footprint it lies in (the
smallest, when footprints overlap), else to the nearest footprint within max_m (city.SEARCH addr_max_m, 10 m), else
to none. without_designations(): an address whose text is, or contains, a property designation of the city's buildings
is left out, as s99 would refuse it ("Skansbacken 1" is a street address and also a kvarter's property: 12 of 75,545 on
2026-10-16; pipeline/privacy.py). ODbL: © OpenStreetMap contributors; inside the ODbL-as-a-whole building database.
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from . import city
from .geo import lonlat_to_3011
from .privacy import mentions, normalise

ADDRESSES = Path("data/raw/osm/addresses")
NUMBER = re.compile(r"(\d{1,4})\s*([a-zA-Z])?")
LIST = re.compile(r"\s*[;,]\s*|\s*[-–]\s*")


def numbers(raw) -> list[str]:
    """House numbers in one addr:housenumber value, as "12" or "12A", in the order written."""
    out = []
    for part in LIST.split(str(raw or "").strip()):
        m = NUMBER.fullmatch(part.strip())
        if m and int(m.group(1)) > 0:
            n = str(int(m.group(1))) + (m.group(2) or "").upper()
            if n not in out:
                out.append(n)
    return out


def number_key(n: str) -> tuple[int, str]:
    """Sort key: 2 < 10 < 10A < 10B < 12."""
    m = NUMBER.fullmatch(n)
    return (int(m.group(1)), m.group(2) or "") if m else (0, n)


def load(folder: Path = ADDRESSES, names: list[str] | None = None) -> pd.DataFrame:
    """osm ("node/1"), street, number, x, y (EPSG:3011): one row per house number of every element. With `names`, only
    those tiles ("<col>_<row>", the current grid's), as osm_buildings.load: a tile left from another grid is never read."""
    seen, rows = set(), []
    paths = sorted(Path(folder).glob("*.json")) if names is None else [Path(folder) / f"{k}.json" for k in sorted(names)]
    for path in (p for p in paths if p.exists()):
        for e in json.loads(path.read_text(encoding="utf-8")).get("elements", []):
            key = f"{e.get('type')}/{e.get('id')}"
            tags = e.get("tags") or {}
            street = " ".join(str(tags.get("addr:street", "")).split())
            at = e if e.get("type") == "node" else e.get("center") or {}
            if key in seen or not street or "lat" not in at or "lon" not in at:
                continue
            seen.add(key)
            for n in numbers(tags.get("addr:housenumber")):
                rows.append((key, street, n, float(at["lon"]), float(at["lat"])))
    out = pd.DataFrame(rows, columns=["osm", "street", "number", "lon", "lat"])
    x, y = lonlat_to_3011(out.lon.to_numpy(float), out.lat.to_numpy(float))
    return out.assign(x=x, y=y).drop(columns=["lon", "lat"])


def assign(points: pd.DataFrame, b, max_m: float | None = None) -> np.ndarray:
    """The gid of the footprint each point (x, y) lies in (the smallest, if several), else of the nearest within max_m,
    else -1."""
    max_m = city.SEARCH["addr_max_m"] if max_m is None else max_m
    gid = np.full(len(points), -1, dtype=np.int64)
    if len(points) == 0 or len(b) == 0:
        return gid
    fp = b.geometry.values
    gids = b.gid.to_numpy()
    tree = shapely.STRtree(fp)
    pts = shapely.points(points.x.to_numpy(float), points.y.to_numpy(float))
    i_pt, i_fp = tree.query(pts, predicate="within")
    order = np.lexsort((gids[i_fp], shapely.area(fp[i_fp]), i_pt))   # per point, the smallest footprint first
    first = order[np.unique(i_pt[order], return_index=True)[1]]
    gid[i_pt[first]] = gids[i_fp[first]]
    miss = np.flatnonzero(gid < 0)
    if len(miss):
        i_pt, i_fp = tree.query_nearest(pts[miss], max_distance=max_m, all_matches=False)
        gid[miss[i_pt]] = gids[i_fp]
    return gid


def on_footprints(points: pd.DataFrame, b, max_m: float | None = None) -> pd.DataFrame:
    """gid, street, number for every address that lands on a footprint, one row per (gid, street, number), sorted."""
    out = points.assign(gid=assign(points, b, max_m))
    out = out[out.gid >= 0][["gid", "street", "number"]].drop_duplicates()
    out["key"] = [number_key(n) for n in out.number]
    out = out.sort_values(["gid", "street", "key"]).drop(columns="key").reset_index(drop=True)
    return out.astype({"gid": "int32"})


def without_designations(on: pd.DataFrame, fastighet) -> tuple[pd.DataFrame, int]:
    """(the addresses whose "street number" neither is nor contains a property designation from `fastighet`, how many
    were left out)."""
    designations = {normalise(f) for f in fastighet if isinstance(f, str) and f.strip()} - {""}
    text = on.street + " " + on.number
    bad = np.array([normalise(t) in designations or mentions(t, designations) for t in text], dtype=bool)
    return on[~bad].reset_index(drop=True), int(bad.sum())


def key(street, number) -> pd.Series:
    """A (street, number) pair, letter case aside."""
    return pd.Series(street).str.casefold().to_numpy(object) + "\0" + pd.Series(number).str.casefold().to_numpy(object)


def sharing(on: pd.DataFrame, gids: set[int], also: set[str] = frozenset()) -> np.ndarray:
    """Per row, True where its street and number (letter case aside) also sit on one of `gids`, or are in `also`
    (near(): the addresses beside them). An address belongs to a house, not to the footprint its node landed on: an
    entrance node beside the house can lie nearest its garage or a neighbour, so a house's addresses are withheld
    wherever they landed."""
    if (not gids and not also) or on.empty:
        return np.zeros(len(on), dtype=bool)
    k = pd.Series(key(on.street, on.number))
    return k.isin(set(k[on.gid.isin(gids).to_numpy()]) | set(also)).to_numpy()


def near(points: pd.DataFrame, b, gids: set[int], max_m: float | None = None) -> set[str]:
    """The keys of the address points within max_m (city.SEARCH addr_max_m) of the footprints `gids`, wherever they
    were assigned: a house whose only address node lies outside it, nearest its garage, still owns that address."""
    max_m = city.SEARCH["addr_max_m"] if max_m is None else max_m
    fp = b.geometry.values[b.gid.isin(gids).to_numpy()]
    if not len(fp) or points.empty:
        return set()
    pts = shapely.points(points.x.to_numpy(float), points.y.to_numpy(float))
    i_pt, _ = shapely.STRtree(fp).query(pts, predicate="dwithin", distance=max_m)
    hit = points.iloc[np.unique(i_pt)]
    return set(key(hit.street, hit.number))
