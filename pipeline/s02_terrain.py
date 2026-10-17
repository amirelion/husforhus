"""The terrain grid and each building's ground (spec §4.1 "Terrain (D9)", §3.2; Plan 3, contract C15).

Source: Lantmäteriet's 1 m terrain model read down to 5 m (data/raw/dem/dtm5.tif, s00_fetch_dem with the owner's
login), else the City's 2 m contour lines (pipeline/contours.py; no login). `--source` forces one.

1. Domain, land and water: s04_base's own recipe (the municipality, or the fixture box with HFH_FIXTURE=1), so the
   grid, the land and the water polygons agree with what s04_base ships.
2. Grid: every city.TERRAIN["cell"] metres in the local frame; a node is the mean of the source's land sub-samples
   (sub x sub per node); `burn` nodes of water around land take the nearest land node's height.
3. Water levels per water polygon (terrain.lake_levels): the sea and Mälaren at water_z, every lake at its own.
   Nodes in a water polygon and away from land take its level; the rest of the grid water_z. With the contours, the
   unlabelled lines are then inferred again with every shore at its level and the buildings' grounds (step 4's
   outlier test) beside the labels (pipeline/contours.py), so a line along a quay under a cliff takes the quay's
   height, not the cliff's; and the levels are read again from those lines, the ones the TIN is built from, so no
   pond stands above banks the second inference lowered.
4. Buildings: the source's minimum along each outline (tmin), read from the source itself (the 5 m model or the
   TIN), never from the 20 m grid. A MARK_Z more than fix_m under it is replaced (ground = tmin, height = TAK_Z -
   ground, floors again from the height); a MARK_Z above it is kept (decks, bridges). The drawn ground is at least
   water_z + ground_min. The median MARK_Z - tmin is the datum check s99 reads on a DTM build.
   With the contours, the buildings that are not outliers then join the TIN: each MARK_Z at its footprint's
   representative point (the spike's "hybrid"), so paved quays, squares and the strips at a cliff's foot, which no
   contour crosses, come down to the street, and tmin is read again from that TIN.
5. Terrace: the cut that lowers every node of every cell a footprint touches to the drawn ground + terrace_up of the
   lowest building touching that cell (at most terrace_max_cut); the viewer decides how much of it to use
   (city.TERRAIN["terrace"]). `buried` counts the buildings the terrace could not free: the drawn ground more than half
   their height above their base somewhere along the outline, at relief_max (s99 holds it to buried_max, and checks the
   record's relief_max against the slider's). `floating` counts what the cut costs: the buildings whose base stands more
   than FLOAT_M above the cut ground at their outline's highest point (a higher building sharing a cell with a lower
   one stands over the notch; for the project's terrace decision, D41).

Writes data/terrain.npz (grid arrays), data/terrain.json (what s03_tiles copies into stockholm.json, with the hashes of
the buildings.parquet and attributes.parquet it was built from) and data/ground.parquet (gid, ground, height, floors,
ground_src, tmin), all internal.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from . import city, contours, s04_base, terrain
from .codes import FLOORS_OSM
from .fetch import sha256_file
from .s02_attributes import floors_from_height

DATA = Path("data")
DTM = Path("data/raw/dem/dtm5.tif")
CONTOUR_MARGIN_M = 500.0   # contour lines this far outside the domain's box still shape its edge
RING_M = 20.0            # a lake's shore is sampled on the line this far outside it
GROUND_TERRAIN = 1       # ground.parquet ground_src: 0 the LOD1's MARK_Z, 1 the terrain (a fixed outlier)
# The LOD1's sheet-line errors (Task 12 review): every ground m4 had to fix lay on a 1 km map-sheet edge, its MARK_Z
# up to 30 m too low. One that passes the hybrid's fix_m test still pulls a contour TIN down, and a TIN pulled down
# lets a worse one pass (gid 28062, a villa on a 40 m hill, at 9.5 m). A building whose outline lies within
# SHEET_NEAR_M of a sheet edge and whose MARK_Z is more than SHEET_LOW_M under the median MARK_Z of the others within
# NEIGHBOUR_M (under the TIN's own minimum along its outline where there are none) is never a contour TIN's anchor.
# The median counts anchors only, in a second pass (the final review's PIPELINE-2: gid 42975, 11 m too low, had one
# neighbour, gid 5317, itself 39 m too low, and passed).
SHEET_M = 1000.0
SHEET_NEAR_M = 15.0
SHEET_LOW_M = 8.0
NEIGHBOUR_M = 50.0
FLOAT_M = 3.0            # terrain.json `floating`: a base more than this above the cut ground at the outline's top


class DtmSource:
    """Heights from data/raw/dem/dtm5.tif (EPSG:3011, 5 m, NaN outside), sampled bilinearly."""
    kind = "dtm"

    def __init__(self, path: Path = DTM):
        import rasterio
        with rasterio.open(path) as src:
            self.z = src.read(1).astype(np.float64)
            if src.nodata is not None and not np.isnan(src.nodata):
                self.z[self.z == src.nodata] = np.nan
            self.inv = ~src.transform

    def sample(self, xz) -> np.ndarray:
        from scipy import ndimage
        xz = np.asarray(xz, dtype=np.float64).reshape(-1, 2)
        e = xz[:, 0] + city.ORIGIN[0]
        n = city.ORIGIN[1] - xz[:, 1]
        col, row = self.inv @ (e, n)
        return ndimage.map_coordinates(self.z, [row - 0.5, col - 0.5], order=1, mode="constant", cval=np.nan,
                                       prefilter=False)


def choose_source(kind: str, dtm: Path = DTM) -> str:
    if kind == "auto":
        return "dtm" if dtm.exists() else "contours"
    if kind == "dtm" and not dtm.exists():
        raise SystemExit(f"--source dtm: {dtm} is missing (run s00_fetch_dem with LM_USER/LM_PASSWORD set)")
    return kind


def sub_centres(grid: terrain.Grid, sub: int, mask: np.ndarray) -> np.ndarray:
    """Local (x, z) of the sub-samples under `mask`, row-major."""
    s = grid.cell / sub
    jj, ii = np.nonzero(mask)
    return np.c_[grid.x0 - grid.cell / 2 + (ii + 0.5) * s, grid.z0 - grid.cell / 2 + (jj + 0.5) * s]


def ring_samples(source, water_local, land_local, step: float = 10.0) -> np.ndarray:
    """Per water polygon, the 5th percentile of the source on land along the line RING_M outside it (NaN where
    that line has no land)."""
    shapely.prepare(land_local)
    out = np.full(len(water_local), np.nan)
    for k, p in enumerate(water_local):
        line = shapely.boundary(p.buffer(RING_M))
        pts = shapely.get_coordinates(shapely.segmentize(line, step))
        if not len(pts):
            continue
        pts = pts[shapely.contains_xy(land_local, pts[:, 0], pts[:, 1])]
        v = source.sample(pts) if len(pts) else np.zeros(0)
        v = v[np.isfinite(v)]
        if len(v):
            out[k] = np.percentile(v, 5)
    return out


def inner_medians(source, water_local, grid: terrain.Grid, sub: int) -> np.ndarray:
    """Per water polygon, the median of a DTM source inside it shrunk by 5 m (a laser model's water is flat);
    NaN for the contour source, whose TIN means nothing inside a lake, or with fewer than 4 samples."""
    out = np.full(len(water_local), np.nan)
    if source.kind != "dtm":
        return out
    shape = (grid.nz * sub, grid.nx * sub)
    idx = terrain.burn([p.buffer(-5.0) for p in water_local], np.arange(len(water_local)) + 1, shape,
                       grid.sub_transform(sub), fill=0, dtype="int32")
    pts = sub_centres(grid, sub, idx > 0)
    owner = idx[idx > 0] - 1
    v = source.sample(pts)
    ok = np.isfinite(v)
    for k, s in pd.Series(v[ok]).groupby(owner[ok]):
        if len(s) >= 4:
            out[int(k)] = float(s.median())
    return out


def build_grid(source, grid: terrain.Grid, land_local, water_local, levels, cfg) -> tuple[np.ndarray, np.ndarray]:
    """(h (nz, nx) metres, every node filled; use: land and burn-in nodes)."""
    sub = cfg["sub"]
    shape = (grid.nz * sub, grid.nx * sub)
    land_parts = list(shapely.get_parts(land_local))
    land_sub = terrain.burn(land_parts, [1] * len(land_parts), shape, grid.sub_transform(sub),
                            dtype="uint8").astype(bool)
    values = np.full(shape, np.nan, dtype=np.float32)
    pts = sub_centres(grid, sub, land_sub)
    values[land_sub] = source.sample(pts).astype(np.float32)
    mean, land = terrain.node_means(values, land_sub, sub)
    h, burnt = terrain.burn_in(mean, land, cfg["burn"])
    use = land | burnt
    widx = terrain.burn(water_local, np.arange(len(water_local)) + 1, (grid.nz, grid.nx), grid.node_transform(),
                        fill=0, dtype="int32")
    lv = np.r_[cfg["water_z"], np.asarray(levels, dtype=np.float64)]
    h = np.where(use, h, lv[widx]).astype(np.float32)
    if not np.isfinite(h).all():   # a land node the source never reached (outside the TIN's hull)
        h = terrain.nearest_fill(h, np.isfinite(h), ~np.isfinite(h)).astype(np.float32)
    return h, use


def floors_of(b: gpd.GeoDataFrame, attrs: pd.DataFrame) -> np.ndarray:
    """attributes.parquet's floors in b's gid order. A gid it lacks (s01_load ran again since s02_attributes) is
    refused: it would ship 0 floors."""
    floors = attrs.set_index("gid").floors.reindex(b.gid)
    missing = floors.isna().to_numpy()
    if missing.any():
        raise SystemExit(f"attributes.parquet has no floors for {int(missing.sum())} of the buildings (gid "
                         f"{int(b.gid.to_numpy()[missing][0])} first): run s02_attributes first")
    return floors.to_numpy().astype(np.uint8)


def ground_table(b: gpd.GeoDataFrame, attrs: pd.DataFrame, tmin: np.ndarray, kind: str, cfg,
                 low=None) -> pd.DataFrame:
    """ground.parquet's rows: per gid the drawn ground, height, floors, where the ground came from, and tmin (the
    source's minimum along the outline). A sheet-line error (low) is fixed once it lies SHEET_LOW_M under tmin, not
    only fix_m: the TIN it was kept out of judges it, and on a cliff's foot its own outline's minimum is low too."""
    fix = cfg["fix_m"][kind]
    if low is not None:
        fix = np.where(low, min(fix, SHEET_LOW_M), fix)
    ground, height, fixed = terrain.fix_grounds(b.ground.to_numpy(), b.height.to_numpy(), tmin, fix)
    floors = floors_of(b, attrs)
    # only the height rule's floors follow the repaired height: OpenStreetMap's stand, as the card credits them (the
    # final review of Plan 4a)
    if "fsrc" in attrs:
        fixed_h = fixed & (attrs.set_index("gid").fsrc.reindex(b.gid).to_numpy() != FLOORS_OSM)
    else:
        fixed_h = fixed
    if fixed_h.any():
        floors[fixed_h] = floors_from_height(height[fixed_h], b.kategori.to_numpy()[fixed_h])
    drawn = np.maximum(ground, cfg["water_z"] + cfg["ground_min"])
    return pd.DataFrame({
        "gid": b.gid.to_numpy().astype(np.int32),
        "ground": drawn.astype(np.float32),
        "height": height.astype(np.float32),
        "floors": floors,
        "ground_src": np.where(fixed, GROUND_TERRAIN, 0).astype(np.uint8),
        "tmin": tmin.astype(np.float32),
    })


def terraced_nodes(cut: np.ndarray) -> int:
    """The nodes whose cut ships: terrain.bin stores it in whole decimetres (terrain.pack rounds), so a cut under
    about 5 cm reaches no viewer."""
    return int((np.round(np.asarray(cut, dtype=np.float64) * 10) >= 1).sum())


def fixed_report(b: gpd.GeoDataFrame, g: pd.DataFrame, n: int = 20) -> list[str]:
    """The n fixed grounds that moved most: gid, MARK_Z -> ground, height -> height (for the build log)."""
    k = np.flatnonzero(g.ground_src.to_numpy() == GROUND_TERRAIN)
    k = k[np.argsort(-(g.ground.to_numpy()[k] - b.ground.to_numpy()[k]), kind="stable")][:n]
    return [f"  gid {int(b.gid.iloc[i])}: ground {b.ground.iloc[i]:.1f} -> {g.ground.iloc[i]:.1f} m, height "
            f"{b.height.iloc[i]:.1f} -> {g.height.iloc[i]:.1f} m" for i in k]


def sheet_edge_m(geoms) -> np.ndarray:
    """Each outline's distance in metres to the nearest map-sheet edge: a multiple of SHEET_M in E or N (EPSG:3011),
    0 for an outline across one. Exact from the bounds, since the edges are lines along the axes."""
    x0, z0, x1, z1 = shapely.bounds(np.asarray(geoms, dtype=object)).T

    def edge(lo, hi):
        across = np.floor(hi / SHEET_M) >= np.ceil(lo / SHEET_M)
        return np.where(across, 0.0, np.minimum(lo - np.floor(lo / SHEET_M) * SHEET_M,
                                                np.ceil(hi / SHEET_M) * SHEET_M - hi))
    return np.minimum(edge(x0, x1), edge(z0, z1))


def sheet_line_lows(geoms, mark_z, tmin, fix_m: float | None = None) -> np.ndarray:
    """The LOD1's sheet-line errors among outlines in EPSG:3011: within SHEET_NEAR_M of a sheet edge and more than
    SHEET_LOW_M under the median MARK_Z of the other buildings within NEIGHBOUR_M, or under tmin where none is. A quay
    house under a cliff is as far under its neighbours but lies off the sheet edges, so it stays an anchor.
    Two passes: the first takes every neighbour; the second only the anchors among them (within fix_m of tmin, the
    contours' 20 m by default, and not flagged by the first), so one error beside another is not masked by it."""
    geoms = np.asarray(geoms, dtype=object)
    mark_z = np.asarray(mark_z, dtype=np.float64)
    tmin = np.asarray(tmin, dtype=np.float64)
    fix_m = city.TERRAIN["fix_m"]["contours"] if fix_m is None else fix_m
    near = sheet_edge_m(geoms) <= SHEET_NEAR_M
    rep = shapely.point_on_surface(geoms)
    i, j = shapely.STRtree(rep).query(rep, predicate="dwithin", distance=NEIGHBOUR_M)

    def flagged(counts):
        k = (i != j) & counts[j]
        med = pd.Series(mark_z[j[k]]).groupby(i[k]).median().reindex(range(len(geoms))).to_numpy()
        return near & (np.where(np.isfinite(med), med, tmin) - mark_z > SHEET_LOW_M)

    first = flagged(np.ones(len(geoms), dtype=bool))
    return flagged(np.isfinite(tmin) & (np.abs(mark_z - tmin) <= fix_m) & ~first)


def anchors(geoms, mark_z, tmin, fix_m: float, low=None) -> np.ndarray:
    """The buildings whose MARK_Z may join a contour TIN, the inference's or the hybrid's: within fix_m of tmin (the
    TIN's minimum along the outline), and not a sheet-line error (low, else sheet_line_lows). geoms in EPSG:3011."""
    mark_z = np.asarray(mark_z, dtype=np.float64)
    low = sheet_line_lows(geoms, mark_z, tmin, fix_m) if low is None else low
    return np.isfinite(tmin) & (np.abs(mark_z - tmin) <= fix_m) & ~low


def build(raw: Path, b: gpd.GeoDataFrame, attrs: pd.DataFrame, *, kind: str, fixture: bool, cfg=None,
          dtm: Path = DTM, log=print) -> tuple[dict, dict, pd.DataFrame]:
    """(arrays for terrain.npz, the terrain.json record, ground.parquet's frame). raw is data/raw/city."""
    cfg = city.TERRAIN if cfg is None else cfg
    floors_of(b, attrs)   # refuse attributes made for other buildings now, not after the grid
    dom = s04_base.domain(raw, fixture=fixture)
    w = gpd.read_file(s04_base.find(raw, "Vatten_area.shp")).to_crs(city.CRS)
    land, water = s04_base.land_and_water(shapely.force_2d(w.geometry.values), dom)
    dom_l = terrain.to_local(dom)
    land_l = terrain.to_local(shapely.union_all(land)) if land else shapely.Polygon()
    water_l = [terrain.to_local(p) for p in water]
    grid = terrain.grid_for(dom_l.bounds, cfg["cell"])
    if kind == "dtm":
        source = DtmSource(dtm)
    else:
        lines, labelled = contours.read_labelled(raw / "stadskarta")
        geoms, hs = contours.lines_near(contours.with_heights(lines, labelled), dom_l, CONTOUR_MARGIN_M)
        source = contours.ContourSource(geoms, hs)
    log(f"source {kind}; grid {grid.nx} x {grid.nz} nodes of {cfg['cell']:g} m; {len(water_l)} water polygons")
    systems = terrain.water_systems(water_l, cfg["bridge_m"])
    inner = inner_medians(source, water_l, grid, cfg["sub"])

    def levels_on(src):
        return terrain.lake_levels(ring_samples(src, water_l, land_l), inner, systems, water_z=cfg["water_z"],
                                   sea_max=cfg["sea_max"], offset=cfg["lake_offset"][kind])
    levels = levels_on(source)
    polys = terrain.to_local(b.geometry.values)
    mark_z = b.ground.to_numpy(np.float64)
    if kind == "contours":
        # The unlabelled lines again (pipeline/contours.py), now with known heights beside the labels in the inference:
        # every shore at its level, and every building ground the first TIN does not call an outlier (the hybrid's
        # test, below). From the labels alone a line along a quay under a cliff took the cliff's height (Söder
        # Mälarstrand 18 m, Slussen and Stadsgården 22 m, Task 12); the shores alone pulled the lines on the plateau
        # behind the cliff down instead (26-30 m to 8-16 m beside buildings at 33-47 m). Judged on buildings held out
        # of it, the inference with both is off by 1.1 m (median) where the labels alone are off by 1.8 m.
        # never the LOD1's sheet-line errors (sheet_line_lows), here or in the hybrid below
        tmin = terrain.outline_min(source.sample, polys)
        low = sheet_line_lows(b.geometry.values, mark_z, tmin, cfg["fix_m"][kind])
        keep = anchors(b.geometry.values, mark_z, tmin, cfg["fix_m"][kind], low)
        floor = np.maximum(mark_z[keep], cfg["water_z"] + cfg["ground_min"])
        wxy, wz = contours.shore_points(water, levels)
        bxy = shapely.get_coordinates(shapely.point_on_surface(b.geometry.values[keep]))
        geoms, hs = contours.lines_near(contours.with_heights(lines, labelled, (np.r_[wxy, bxy], np.r_[wz, floor])),
                                        dom_l, CONTOUR_MARGIN_M)
        # the levels again, from these lines (the ones the TIN is built from): the second inference may lower a pond's
        # own shore line (pond 41 in Norra Djurgården: 12 m to 6 m), and a level from the first would float above it
        # (the final review's PIPELINE-1). The sea and Mälaren keep water_z: lake_levels snaps them as before.
        levels = levels_on(contours.ContourSource(geoms, hs))
        # the shores at their levels, so lakes and quays keep their level up to the bank
        sxy, sz = contours.shore_points(water_l, levels)
        source = contours.ContourSource(geoms, hs, sxy, sz)
        # the hybrid: every building whose MARK_Z the contour TIN does not call an outlier joins it at its own ground
        # (never under the floor buildings are drawn at, so the four quay houses below the sea dig no pits)
        tmin = terrain.outline_min(source.sample, polys)
        keep = anchors(b.geometry.values, mark_z, tmin, cfg["fix_m"][kind], low)
        rep = shapely.get_coordinates(shapely.point_on_surface(polys[keep]))
        floor = np.maximum(mark_z[keep], cfg["water_z"] + cfg["ground_min"])
        source = contours.ContourSource(geoms, hs, np.r_[sxy, rep], np.r_[sz, floor])
        edge = f" ({int(low.sum()):,} on a sheet edge)" if low.any() else ""
        log(f"hybrid: {int(keep.sum()):,} building grounds join the contours' TIN, {int((~keep).sum()):,} left out{edge}")
    else:
        low = np.zeros(len(b), dtype=bool)
    h, use = build_grid(source, grid, land_l, water_l, levels, cfg)
    tmin = terrain.outline_min(source.sample, polys)
    g = ground_table(b, attrs, tmin, kind, cfg, low)
    cut = terrain.terrace_cut(grid, h, polys, g.ground.to_numpy(), cfg["terrace_up"], cfg["terrace_max_cut"])
    # true metres of cut ground above each base at the outline's highest point: buried (scaled by the relief) where
    # positive, standing over a notch where negative
    rise = terrain.burial(grid, h, cut, polys, g.ground.to_numpy(), 1.0)
    half = 0.5 * g.height.to_numpy()
    buried = int((cfg["relief_max"] * rise > half).sum())
    buried_default = int((cfg["relief"] * rise > half).sum())
    floating = int((-rise > FLOAT_M).sum())
    ok = np.isfinite(tmin)
    datum = float(np.median(mark_z[ok] - tmin[ok])) if ok.any() else 0.0
    fixed = int((g.ground_src == GROUND_TERRAIN).sum())
    raised = int((levels > cfg["water_z"]).sum())
    sea = inner[levels <= cfg["water_z"]]
    sea = float(np.median(sea[np.isfinite(sea)])) if np.isfinite(sea).any() else None
    terraced = terraced_nodes(cut)
    log(f"water: {len(levels) - raised} polygons at {cfg['water_z']:g} m, {raised} lakes above it"
        f"{'' if sea is None else f'; the model reads the sea at {sea:+.2f} m'}; "
        f"{fixed} building grounds fixed from the terrain; datum median {datum:+.2f} m; "
        f"terrace cuts {terraced:,} nodes (max {float(cut.max()) if cut.size else 0:.1f} m), floating {floating:,} "
        f"buildings more than {FLOAT_M:g} m above it; {buried} buildings buried at {cfg['relief_max']:g}x "
        f"({buried_default} at the {cfg['relief']:g}x default)")
    for line in fixed_report(b, g):
        log(line)
    record = {"source": kind, **grid.to_dict(), "water_z": cfg["water_z"], "levels": len(levels),
              "water_area": round(float(sum(p.area for p in water)), 1), "datum": round(datum, 3), "fixed": fixed,
              "lakes": raised, "fixture": fixture, "buried": buried, "relief_max": cfg["relief_max"],
              "floating": floating, "sea": None if sea is None else round(sea, 3)}
    arrays = {"h": h, "cut": cut, "use": use, "levels": levels.astype(np.float32)}
    return arrays, record, g


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s02_terrain", description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=["auto", "dtm", "contours"], default="auto")
    ap.add_argument("--raw", type=Path, default=s04_base.RAW)
    ap.add_argument("--data", type=Path, default=DATA)
    # pipeline.run hands every step the arguments after `--`: a rebuild from here (README, "Terrain") names the version
    # the later steps write; s02_terrain writes data/ only, so it takes the version and ignores it
    ap.add_argument("--version", help="ignored (the version the steps after s02_terrain write)")
    args = ap.parse_args([] if argv is None else argv)
    fixture = os.environ.get("HFH_FIXTURE") == "1"
    kind = choose_source(args.source)
    # hashed before it is read: an s01_load that replaces it in between leaves outputs that s03_tiles and s04_base
    # refuse, never old outputs stamped with the new file's hash
    sha = sha256_file(args.data / "buildings.parquet")
    sha_attrs = sha256_file(args.data / "attributes.parquet")
    b = gpd.read_parquet(args.data / "buildings.parquet", columns=["gid", "kategori", "ground", "height", "geometry"])
    attrs = pd.read_parquet(args.data / "attributes.parquet", columns=["gid", "floors", "fsrc"])
    arrays, record, g = build(args.raw, b, attrs, kind=kind, fixture=fixture)
    record["buildings_sha256"] = sha   # s03_tiles and s04_base check them
    record["attributes_sha256"] = sha_attrs
    np.savez_compressed(args.data / "terrain.npz", **arrays)
    (args.data / "terrain.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    g.to_parquet(args.data / "ground.parquet", index=False)
    print(f"wrote {args.data / 'terrain.npz'}, terrain.json and ground.parquet ({record['source']}, "
          f"{record['nx']} x {record['nz']} nodes)")


if __name__ == "__main__":
    main(sys.argv[1:])
