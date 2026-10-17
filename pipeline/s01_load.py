"""Load the City LOD1 buildings into data/buildings.parquet (contract C3).

Input: data/raw/city/lod1/<district>/Byggnad.shp (13 MULTIPATCH shapefiles, EPSG:3011) and
data/raw/city/stadsdelar/Stadsdel.shp (117 stadsdelar; their union is the municipality), both from s00_fetch_city.

Footprint: the floor face of each MULTIPATCH, i.e. the union of the faces whose vertices all lie within
FLOOR_TOL of the feature's lowest z. Cleaning runs in this order (counts are printed):
  1. union pieces that share an OID across district files (min MARK_Z, max TAK_Z, TAKMAX_Z, BYGG_H);
  2. drop duplicates: (a) rows with an identical footprint (one per UUID survives; an empty UUID loses to a
     filled one), (b) overlapping rows that share a UUID or where at least one UUID is empty, with IoU >= DUP_IOU,
     or IoU >= DUP_IOU_SAME_HEIGHT and heights within DUP_HEIGHT_TOL (copies that would z-fight); a filled UUID
     beats an empty one, otherwise the lowest OID wins, and rows with two different UUIDs are never merged;
  3. height = TAK_Z - MARK_Z (the roof, never the spire), BYGG_H when that is <= 0;
  4. drop slivers under SLIVER_M2;
  5. keep buildings whose representative point lies in the stadsdelar union;
  6. with HFH_FIXTURE=1, keep only buildings that intersect city.FIXTURE_BBOX;
  7. simplify by city.SIMPLIFY (topology preserved) and normalise the geometry;
  8. gid = rank after a stable sort by (uuid or "", oid, centroid x, centroid y).
prod_year is the year of PROD_DATE, when the City first digitised the object (the earliest over an OID's pieces; 0
when missing). It is an upper bound on the build year and the estimate tier's "probably new" gate (Plan 2); it
never ships. fnr is the LOD1 FNR, the property-unit key (int64, the smallest over an OID's pieces; 0 when missing,
as for the City's unregistered buildings): a high key is a property unit formed late, the estimate tier's second
"probably new" gate (Task 14b). Like FASTIGHET it is internal and never ships (s99 checks). Outside fixture builds,
fewer than city.MIN_BUILDINGS buildings stops the run before anything is written.
"""
import argparse
import os
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

from pipeline import city

LOD1_DIR = Path("data/raw/city/lod1")
STADSDELAR = Path("data/raw/city/stadsdelar/Stadsdel.shp")
OUT = Path("data/buildings.parquet")
COLS = ["GRUPP", "KATEGORI", "OID", "UUID", "FASTIGHET", "FNR", "BYGG_A", "BYGG_H", "MARK_Z", "TAK_Z", "TAKMAX_Z",
        "PROD_DATE"]
FLOOR_TOL = 0.05     # m; the floor face sits at the feature's min z (MARK_Z within ±5 cm)
DUP_IOU = 0.99       # same or empty UUID and at least this overlap: one building stored twice
DUP_IOU_SAME_HEIGHT = 0.95   # ... or at least this overlap when the heights also agree within DUP_HEIGHT_TOL
DUP_HEIGHT_TOL = 0.1         # m; the z attributes have one decimal
SLIVER_M2 = 2.0
SPIRE_TOL = 0.11     # m; the z attributes have one decimal, so 0.1 differences must match
SPIRE_MIN = 3.0      # m; TAKMAX_Z this far above TAK_Z means a spire or tower top


def floor_footprints(geoms) -> np.ndarray:
    """2D footprint per MULTIPATCH feature: union of the parts whose vertices all lie within FLOOR_TOL of min z."""
    geoms = np.asarray(geoms, dtype=object)
    parts, part_of = shapely.get_parts(geoms, return_index=True)
    coords, coord_of = shapely.get_coordinates(parts, include_z=True, return_index=True)
    z = coords[:, 2]
    part_max = np.full(len(parts), -np.inf)
    np.maximum.at(part_max, coord_of, z)
    feat_min = np.full(len(geoms), np.inf)
    np.minimum.at(feat_min, part_of[coord_of], z)
    is_floor = part_max - feat_min[part_of] <= FLOOR_TOL
    floor, owner = shapely.force_2d(parts[is_floor]), part_of[is_floor]
    out = np.empty(len(geoms), dtype=object)
    out[:] = None
    counts = np.bincount(owner, minlength=len(geoms))
    single = counts[owner] == 1
    out[owner[single]] = floor[single]
    for i in np.flatnonzero(counts > 1):
        out[i] = shapely.union_all(floor[owner == i])
    return out


def read_lod1(lod1_dir: Path = LOD1_DIR) -> gpd.GeoDataFrame:
    """All district files, in sorted folder order, as raw LOD1 rows (MultiPolygon Z geometry)."""
    files = sorted(Path(lod1_dir).glob("*/Byggnad.shp"))
    if not files:
        raise SystemExit(f"no Byggnad.shp under {lod1_dir}: run s00_fetch_city first")
    frames = [pyogrio.read_dataframe(f, columns=COLS) for f in files]
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=frames[0].crs)


def prod_years(prod_date) -> np.ndarray:
    """The year in a PROD_DATE column ("20230117", a date, or missing), as int64; 0 when there is none."""
    text = pd.Series(prod_date).astype(str).str.strip().str[:4]
    return pd.to_numeric(text, errors="coerce").fillna(0).astype(np.int64).to_numpy()


def fnr_keys(fnr) -> np.ndarray:
    """The LOD1 FNR column (a float with NaN for unregistered buildings) as int64; 0 when missing."""
    return pd.to_numeric(pd.Series(fnr), errors="coerce").fillna(0).astype(np.int64).to_numpy()


def footprints(raw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Raw LOD1 rows -> one 2D footprint row per feature with lower-case attribute columns."""
    df = pd.DataFrame({
        "uuid": raw["UUID"].fillna("").astype(str).to_numpy(),
        "oid": raw["OID"].astype("int64").to_numpy(),
        "grupp": raw["GRUPP"].fillna("").astype(str).to_numpy(),
        "kategori": raw["KATEGORI"].fillna("").astype(str).to_numpy(),
        "fastighet": raw["FASTIGHET"].fillna("").astype(str).to_numpy(),
        "bygg_h": raw["BYGG_H"].astype(float).to_numpy(),
        "mark_z": raw["MARK_Z"].astype(float).to_numpy(),
        "tak_z": raw["TAK_Z"].astype(float).to_numpy(),
        "takmax_z": raw["TAKMAX_Z"].astype(float).to_numpy(),
        "prod_year": prod_years(raw["PROD_DATE"]),
        "fnr": fnr_keys(raw["FNR"]),
    })
    fp = floor_footprints(raw.geometry.values)
    return gpd.GeoDataFrame(df, geometry=fp, crs=raw.crs if raw.crs is not None else city.CRS)


def union_split_oids(b: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Step 1: one row per OID. Attributes come from the largest piece; heights span all pieces."""
    b = b.assign(_area=b.area).sort_values(["oid", "_area"], ascending=[True, False], kind="mergesort")
    split = b["oid"].duplicated(keep=False)
    if not split.any():
        return b.drop(columns="_area").reset_index(drop=True)
    whole, parts = b[~split], b[split]
    rows = []
    for _, grp in parts.groupby("oid", sort=True):
        row = grp.iloc[0].copy()
        row["mark_z"] = grp["mark_z"].min()
        row["tak_z"] = grp["tak_z"].max()
        row["takmax_z"] = grp["takmax_z"].max()
        row["bygg_h"] = grp["bygg_h"].max()
        dated = grp["prod_year"][grp["prod_year"] > 0]
        row["prod_year"] = int(dated.min()) if len(dated) else 0
        keyed = grp["fnr"][grp["fnr"] > 0]
        row["fnr"] = int(keyed.min()) if len(keyed) else 0
        row["geometry"] = shapely.union_all(grp.geometry.values)
        rows.append(row)
    merged = gpd.GeoDataFrame(rows, geometry="geometry", crs=b.crs)
    out = pd.concat([whole, merged]).sort_values("oid", kind="mergesort")
    return gpd.GeoDataFrame(out.drop(columns="_area"), geometry="geometry", crs=b.crs).reset_index(drop=True)


def drop_identical(b: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Step 2a: rows with the same normalised footprint. One row per UUID survives (lowest OID); a row without
    a UUID is dropped when the same footprint also exists with one."""
    b = b.sort_values("oid", kind="mergesort").reset_index(drop=True)
    key = pd.Series([shapely.to_wkb(g) for g in shapely.normalize(b.geometry.values)], index=b.index)
    has_uuid = b["uuid"] != ""
    same = pd.DataFrame({"k": key, "u": b["uuid"]}).duplicated()
    empty_loses = ~has_uuid & key.isin(set(key[has_uuid]))
    return b[~(same | empty_loses)].reset_index(drop=True)


def drop_near_identical(b: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Step 2b: the same building stored twice with slightly different outlines (an extra collinear vertex,
    millimetre jitter, a trimmed edge). Two overlapping rows are copies when their UUIDs are equal or at least one
    is empty, and IoU >= DUP_IOU, or IoU >= DUP_IOU_SAME_HEIGHT with heights within DUP_HEIGHT_TOL. Rows with two
    different filled UUIDs are never merged. Of each copy pair the row with a filled UUID survives, else the one
    with the lowest OID. Rows are visited in that priority order and a surviving row removes the lower-priority
    copies of itself, so the result does not depend on the input order (OIDs are unique after step 1)."""
    b = b.sort_values("oid", kind="mergesort").reset_index(drop=True)
    geoms = b.geometry.to_numpy()
    uuid = b["uuid"].to_numpy(dtype=object)
    empty = uuid == ""
    height = heights(b)[0]
    area = shapely.area(geoms)
    left, right = shapely.STRtree(geoms).query(geoms, predicate="intersects")
    pair = left < right                                       # each pair once; rows are sorted by OID
    left, right = left[pair], right[pair]
    pair = (uuid[left] == uuid[right]) | empty[left] | empty[right]
    left, right = left[pair], right[pair]
    inter = shapely.area(shapely.intersection(geoms[left], geoms[right]))
    union = area[left] + area[right] - inter
    iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
    same_height = np.abs(height[left] - height[right]) <= DUP_HEIGHT_TOL
    dup = (iou >= DUP_IOU) | ((iou >= DUP_IOU_SAME_HEIGHT) & same_height)
    priority = np.empty(len(b), dtype=np.int64)               # 0 = survives first: filled UUID, then lowest OID
    priority[np.lexsort((b["oid"].to_numpy(), empty))] = np.arange(len(b))
    copies: dict[int, list[int]] = {}
    for i, j in zip(left[dup].tolist(), right[dup].tolist()):
        first, second = (i, j) if priority[i] < priority[j] else (j, i)
        copies.setdefault(first, []).append(second)
    drop = np.zeros(len(b), dtype=bool)
    for i in np.argsort(priority):
        if not drop[i] and i in copies:
            drop[copies[i]] = True
    return b[~drop].reset_index(drop=True)


def heights(b: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Step 3: (height, spire mask). Height is the roof, TAK_Z - MARK_Z, for every building, so spires are already
    left out; BYGG_H only when the roof is not above the ground. The spire mask (BYGG_H measured to TAKMAX_Z, and
    TAKMAX_Z more than SPIRE_MIN above the roof) is only counted in the log."""
    roof = (b["tak_z"] - b["mark_z"]).to_numpy()
    h = np.where(roof > 0, roof, b["bygg_h"].to_numpy())
    to_top = (b["takmax_z"] - b["mark_z"]).to_numpy()
    spire = (np.abs(b["bygg_h"].to_numpy() - to_top) <= SPIRE_TOL) & \
            ((b["takmax_z"] - b["tak_z"]).to_numpy() > SPIRE_MIN)
    return h, spire


def load_boundary(path: Path = STADSDELAR):
    sd = pyogrio.read_dataframe(path)
    if sd.crs is None or sd.crs.to_epsg() != city.CRS:
        sd = sd.to_crs(city.CRS)
    return shapely.union_all(shapely.force_2d(sd.geometry.values))


def clean(raw: gpd.GeoDataFrame, boundary=None, fixture: bool = False, log=print) -> gpd.GeoDataFrame:
    """Raw LOD1 rows -> the C3 buildings frame. boundary=None skips step 5 (used by tests)."""
    b = footprints(raw)
    b = b[~b.geometry.isna() & ~b.geometry.is_empty].reset_index(drop=True)
    log(f"rows in: {len(raw):,} (footprints: {len(b):,})")
    n = len(b)
    b = union_split_oids(b)
    log(f"1 union split OIDs: {len(b):,} (-{n - len(b)})")
    n = len(b)
    b = drop_identical(b)
    log(f"2a drop identical footprints: {len(b):,} (-{n - len(b)})")
    n = len(b)
    b = drop_near_identical(b)
    log(f"2b drop near-identical copies (IoU >= {DUP_IOU}, or >= {DUP_IOU_SAME_HEIGHT} at the same height): "
        f"{len(b):,} (-{n - len(b)})")
    h, spire = heights(b)
    b["height"] = h
    n_bygg = int((b["tak_z"] <= b["mark_z"]).sum())
    log(f"3 heights: {n_bygg} from BYGG_H, {int(spire.sum())} spires left out (roof height)")
    n = len(b)
    b = b[b.area >= SLIVER_M2].reset_index(drop=True)
    log(f"4 drop slivers < {SLIVER_M2} m²: {len(b):,} (-{n - len(b)})")
    if boundary is not None:
        n = len(b)
        pts = b.representative_point()
        b = b[shapely.contains_xy(boundary, pts.x.to_numpy(), pts.y.to_numpy())].reset_index(drop=True)
        log(f"5 inside the stadsdelar: {len(b):,} (-{n - len(b)})")
    if fixture:
        n = len(b)
        b = b[b.intersects(shapely.box(*city.FIXTURE_BBOX))].reset_index(drop=True)
        log(f"6 fixture bbox: {len(b):,} (-{n - len(b)})")
    n_bad = int((b["height"] <= 0).sum())
    if n_bad:
        log(f"dropping {n_bad} buildings with no positive height")
        b = b[b["height"] > 0].reset_index(drop=True)
    geom = shapely.normalize(shapely.simplify(b.geometry.values, city.SIMPLIFY, preserve_topology=True))
    b = b.set_geometry(gpd.GeoSeries(geom, index=b.index, crs=b.crs))
    log(f"7 simplified at {city.SIMPLIFY} m: {int(shapely.get_num_coordinates(geom).sum()):,} vertices")
    c = b.geometry.centroid
    b = b.assign(_cx=c.x.to_numpy(), _cy=c.y.to_numpy())
    b = b.sort_values(["uuid", "oid", "_cx", "_cy"], kind="mergesort").reset_index(drop=True)
    out = gpd.GeoDataFrame({
        "gid": np.arange(len(b), dtype=np.int32),
        "uuid": b["uuid"].astype(str).to_numpy(),
        "oid": b["oid"].astype("int64").to_numpy(),
        "grupp": b["grupp"].astype(str).to_numpy(),
        "kategori": b["kategori"].astype(str).to_numpy(),
        "fastighet": b["fastighet"].astype(str).to_numpy(),
        "height": b["height"].astype("float32").to_numpy(),
        "ground": b["mark_z"].astype("float32").to_numpy(),
        "area": b.area.astype("float32").to_numpy(),
        "prod_year": b["prod_year"].astype("int16").to_numpy(),
        "fnr": b["fnr"].astype("int64").to_numpy(),
    }, geometry=b.geometry.to_numpy(), crs=city.CRS)
    log(f"8 gids: {len(out):,} buildings")
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="LOD1 MULTIPATCH -> data/buildings.parquet")
    ap.add_argument("--lod1", type=Path, default=LOD1_DIR)
    ap.add_argument("--stadsdelar", type=Path, default=STADSDELAR)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--min-buildings", type=int, default=city.MIN_BUILDINGS,
                    help="fail with fewer buildings than this, outside fixture builds (tests pass a small value)")
    args = ap.parse_args([] if argv is None else argv)
    fixture = os.environ.get("HFH_FIXTURE") == "1"
    b = clean(read_lod1(args.lod1), boundary=load_boundary(args.stadsdelar), fixture=fixture)
    if not fixture and len(b) < args.min_buildings:
        raise SystemExit(f"{len(b):,} buildings after cleaning, fewer than the city's {args.min_buildings:,}: "
                         f"a partial LOD1 under {args.lod1}? Rerun s00_fetch_city; {args.out} is unchanged")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    b.to_parquet(args.out, index=False)
    print(f"wrote {args.out} ({len(b):,} buildings{', fixture' if fixture else ''})")


if __name__ == "__main__":
    main(sys.argv[1:])
