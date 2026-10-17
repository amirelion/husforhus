"""Tiny synthetic inputs shaped like the real ones, for unit tests that must not touch the network.

    from tests import synth            # the repo root is on sys.path through pytest's pythonpath = ["."]
    b = synth.buildings(3)             # data/buildings.parquet
    y = synth.years(b.gid, year=[1650, 1931, 0], yflag=[EXACT, RANGE, UNKNOWN])
    a = synth.attributes(b.gid, floors=[5, 4, 2])
    raw = synth.lod1_raw([{"footprint": synth.square(0, 0)}, {"footprint": synth.square(30, 0), "UUID": None}])
    raw = synth.lod1_frame([{"geometry": synth.prism(x0, y0, x0 + 10, y0 + 20, 5.0, 15.0), "OID": 7}])

All geometry is EPSG:3011. square() takes offsets in metres from city.ORIGIN (Stortorget; dx east, dz south);
prism() takes absolute coordinates.
"""
from collections.abc import Iterable, Sequence

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon

from pipeline import city, codes

PITCH, STEP = 120.0, 15.0   # villa_blocks: blocks 120 m apart, houses 15 m apart (the next block's nearest house is 90 m away)
LOD1_COLUMNS = ["GRUPP", "KATEGORI", "KOMPONENT", "OID", "KOM_ID", "HUSNR", "UUID", "BYGG_A", "BYGG_H", "MARK_Z",
                "FNR", "FASTIGHET", "TAKMIN_Z", "TAK_Z", "TAKMAX_Z", "PROD_DATE", "MOD_DATE"]


def square(dx: float, dz: float, size: float = 10.0) -> Polygon:
    """An axis-aligned square footprint (CCW) whose centre is (dx, dz) in the local frame: dx east, dz south."""
    e, n = city.ORIGIN[0] + dx, city.ORIGIN[1] - dz
    h = size / 2
    return shapely.box(e - h, n - h, e + h, n + h)


def _column(value, n: int) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return [value] * n
    values = list(value)
    if len(values) != n:
        raise ValueError(f"expected {n} values, got {len(values)}")
    return values


def buildings(n: int = 3, *, rows: Sequence[dict] | None = None) -> gpd.GeoDataFrame:
    """data/buildings.parquet. Default: n Flerbostadshus, 10 m squares, 20 m apart, east of the origin,
    20 m tall on ground 5 m, first digitised in 2003, on early-formed property units (fnr 10,100,000 + i, below
    city.ESTIMATE's late_unit_fnr). `rows` (length n) holds per-building overrides, including 'geometry'."""
    rows = list(rows) if rows is not None else [{} for _ in range(n)]
    n = len(rows)
    records = []
    for i, over in enumerate(rows):
        r = {"gid": i, "uuid": f"00000000-0000-4000-8000-{i:012d}", "oid": 1_000_000 + i,
             "grupp": "Bostadsbyggnad", "kategori": "Flerbostadshus", "fastighet": f"SYNTES {i + 1}",
             "height": 20.0, "ground": 5.0, "prod_year": 2003, "fnr": 10_100_000 + i, "geometry": square(20.0 * i, 0.0)}
        r.update(over)
        r.setdefault("area", r["geometry"].area)
        records.append(r)
    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=city.CRS)
    return gdf.astype({"gid": "int32", "uuid": "str", "oid": "int64", "grupp": "str", "kategori": "str",
                       "fastighet": "str", "height": "float32", "ground": "float32", "area": "float32",
                       "prod_year": "int16", "fnr": "int64"})[
        ["gid", "uuid", "oid", "grupp", "kategori", "fastighet", "height", "ground", "area", "prod_year", "fnr",
         "geometry"]]


def villa_blocks(extra=(), base_year: int = 1946) -> tuple[gpd.GeoDataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """A synthetic city for the estimate tier: 10 villa blocks in a row along x (PITCH apart), 9 Enbostadshus each
    (STEP apart, 8 m squares, 6 m tall), block b built in base_year + 2 * b (1946..1964 by default: one period),
    each block its own kvarter (KV<b>), first digitised in 2003. `extra` adds undated buildings as (dx, dz, kategori,
    fastighet, prod_year[, fnr]) after them (fnr: synth.buildings' default unless given). Returns (buildings, years
    with 0 for the undated, dated mask, query mask)."""
    rows, years, prod = [], [], []
    for b in range(10):
        for i in range(3):
            for j in range(3):
                rows.append({"geometry": square(b * PITCH + i * STEP, j * STEP, size=8.0), "kategori": "Enbostadshus",
                             "fastighet": f"KV{b} {i * 3 + j + 1}", "height": 6.0})
                years.append(base_year + 2 * b)
                prod.append(2003)
    for dx, dz, kategori, fastighet, prod_year, *fnr in extra:
        rows.append({"geometry": square(dx, dz, size=8.0), "kategori": kategori, "fastighet": fastighet, "height": 6.0,
                     **({"fnr": fnr[0]} if fnr else {})})
        years.append(0)
        prod.append(prod_year)
    b = buildings(rows=[dict(r, prod_year=py) for r, py in zip(rows, prod)])
    years = np.array(years, dtype=np.int64)
    return b, years, years > 0, years == 0


def years(gids, **columns) -> pd.DataFrame:
    """data/years.parquet. Defaults: year 0, yflag UNKNOWN, ysrc SRC_NONE, private False. year_from/year_to
    default to year, period to city.period_index(year). Each keyword is a scalar or one value per gid.
    A private house is given as published: year = decade start, year_to = year + 9, private=True, and
    period from the real year (pass it explicitly)."""
    gids = list(gids)
    n = len(gids)
    year = _column(columns.pop("year", 0), n)
    df = pd.DataFrame({
        "gid": gids,
        "year": year,
        "year_from": _column(columns.pop("year_from", year), n),
        "year_to": _column(columns.pop("year_to", year), n),
        "ysrc": _column(columns.pop("ysrc", codes.SRC_NONE), n),
        "yflag": _column(columns.pop("yflag", codes.UNKNOWN), n),
        "period": _column(columns.pop("period", [city.period_index(y) for y in year]), n),
        "private": _column(columns.pop("private", False), n),
        "raa_id": _column(columns.pop("raa_id", ""), n),
        "landmark": _column(columns.pop("landmark", ""), n),
    })
    if columns:
        raise TypeError(f"unknown years columns: {sorted(columns)}")
    return df.astype({"gid": "int32", "year": "int16", "year_from": "int16", "year_to": "int16", "ysrc": "uint8",
                      "yflag": "uint8", "period": "uint8", "private": "bool", "raa_id": "str", "landmark": "str"})


def attributes(gids, **columns) -> pd.DataFrame:
    """data/attributes.parquet. Defaults: floors 0, fsrc FLOORS_HEIGHT, rating 0, architects [], name ""."""
    gids = list(gids)
    n = len(gids)
    architects = columns.pop("architects", None)
    df = pd.DataFrame({
        "gid": gids,
        "floors": _column(columns.pop("floors", 0), n),
        "fsrc": _column(columns.pop("fsrc", codes.FLOORS_HEIGHT), n),
        "rating": _column(columns.pop("rating", 0), n),
        "architects": [list(a) for a in architects] if architects is not None else [[] for _ in range(n)],
        "name": _column(columns.pop("name", ""), n),
    })
    if columns:
        raise TypeError(f"unknown attributes columns: {sorted(columns)}")
    return df.astype({"gid": "int32", "floors": "uint8", "fsrc": "uint8", "rating": "uint8", "name": "str"})


def lod1_prism(footprint: Polygon, ground: float, roof: float) -> MultiPolygon:
    """A building the way pyogrio reads the City's MULTIPATCH: bottom face at `ground` (first part, CCW),
    one vertical quad per edge, top face at `roof` (last part, CW)."""
    ring = np.asarray(shapely.get_coordinates(shapely.orient_polygons(footprint).exterior))
    bottom = Polygon(np.c_[ring, np.full(len(ring), ground)])
    walls = [Polygon([(*a, ground), (*a, roof), (*b, roof), (*b, ground), (*a, ground)])
             for a, b in zip(ring[:-1], ring[1:])]
    top = Polygon(np.c_[ring[::-1], np.full(len(ring), roof)])
    return MultiPolygon([bottom, *walls, top])


def lod1_raw(rows: Sequence[dict]) -> gpd.GeoDataFrame:
    """Raw City LOD1 rows (the 17 shapefile columns + `district`), as the gamla_stan_lod1 fixture returns them.
    Each row needs 'footprint' (a Polygon) and may give 'height' (default 15 m above MARK_Z) or override any
    column. "UUID": None makes an unregistered building: UUID, FASTIGHET, FNR, HUSNR and KOM_ID missing (NaN),
    as in the City's 4,010 such rows. BYGG_H defaults to TAK_Z - MARK_Z. As in the real data, the prism runs
    from MARK_Z to MARK_Z + BYGG_H, so a spire case sets TAKMAX_Z and BYGG_H = TAKMAX_Z - MARK_Z."""
    records = []
    for i, over in enumerate(rows):
        over = dict(over)
        footprint = over.pop("footprint")
        mark = over.get("MARK_Z", 5.0)
        tak = over.get("TAK_Z", mark + over.pop("height", 15.0))
        registered = over.get("UUID", "") is not None
        r = {"GRUPP": "Bostadsbyggnad", "KATEGORI": "Flerbostadshus", "KOMPONENT": "byS", "OID": 50_000_000 + i,
             "KOM_ID": 1000.0 + i if registered else None, "HUSNR": 1.0 if registered else None,
             "UUID": f"10000000-0000-4000-8000-{i:012d}", "BYGG_A": round(footprint.area, 1),
             "BYGG_H": round(tak - mark, 1), "MARK_Z": mark,
             "FNR": 10_000_000.0 + i if registered else None,
             "FASTIGHET": f"SYNTES {i + 1}" if registered else None, "TAKMIN_Z": tak, "TAK_Z": tak,
             "TAKMAX_Z": tak, "PROD_DATE": "20230117", "MOD_DATE": "20230117", "district": "Södermalm"}
        r.update(over)
        r["geometry"] = lod1_prism(footprint, r["MARK_Z"], r["MARK_Z"] + r["BYGG_H"])
        records.append(r)
    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=city.CRS)
    return gdf.astype({"GRUPP": "str", "KATEGORI": "str", "KOMPONENT": "str", "OID": "int64", "KOM_ID": "float64",
                       "HUSNR": "float64", "UUID": "str", "BYGG_A": "float64", "BYGG_H": "float64",
                       "MARK_Z": "float64", "FNR": "float64", "FASTIGHET": "str", "TAKMIN_Z": "float64",
                       "TAK_Z": "float64", "TAKMAX_Z": "float64", "PROD_DATE": "str", "MOD_DATE": "str",
                       "district": "str"})[[*LOD1_COLUMNS, "district", "geometry"]]


def prism(x0: float, y0: float, x1: float, y1: float, z0: float, z1: float) -> MultiPolygon:
    """An axis-aligned LOD1 block in absolute EPSG:3011 metres, shaped like a pyogrio-read MULTIPATCH:
    floor at z0 first, four walls, roof at z1 last."""
    return lod1_prism(shapely.box(x0, y0, x1, y1), z0, z1)


def lod1_frame(rows: Sequence[dict]) -> gpd.GeoDataFrame:
    """Raw LOD1 rows from ready-made MULTIPATCH geometries (e.g. prism()). Each row needs 'geometry' and may
    override any LOD1 column. MARK_Z/TAK_Z default to the lowest/highest z (one decimal), TAKMIN_Z/TAKMAX_Z to
    TAK_Z, BYGG_H to TAK_Z - MARK_Z. The given geometry is kept unchanged. Columns and dtypes are lod1_raw's."""
    plain, geoms = [], []
    for over in rows:
        over = dict(over)
        geom = over.pop("geometry")
        z = shapely.get_coordinates(geom, include_z=True)[:, 2]
        over.setdefault("MARK_Z", round(float(z.min()), 1))
        over.setdefault("TAK_Z", round(float(z.max()), 1))
        over.setdefault("TAKMIN_Z", over["TAK_Z"])
        over.setdefault("TAKMAX_Z", over["TAK_Z"])
        over.setdefault("BYGG_H", round(over["TAK_Z"] - over["MARK_Z"], 1))
        plain.append({**over, "footprint": shapely.force_2d(geom.geoms[0])})
        geoms.append(geom)
    raw = lod1_raw(plain)
    raw["geometry"] = gpd.GeoSeries(geoms, index=raw.index, crs=city.CRS)
    return raw
