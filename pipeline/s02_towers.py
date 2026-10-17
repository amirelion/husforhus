"""Towers and spires from the laser points: the parts of a building that rise well above its LOD1 roof.

The LOD1 gives each footprint one flat height, so Stadshuset's tower or Riddarholmskyrkan's spire stands no higher
than the roof beside it. s00_fetch_laser cached Lantmäteriet's points around each candidate (pipeline/laser.py); this
step, which needs no login, reads them and for each candidate:

- ground: the median height of the ground points (class 2) in the RING_M ring around the footprint; with fewer than
  MIN_GROUND of them, the building's own LOD1 ground (buildings.parquet `ground`);
- roof points: the points inside the footprint that are not ground, low noise, water or high noise (classes 2, 7, 9,
  18) and are a single return or the last of several (a tree's first returns are its canopy, not a roof);
- a check: where the median roof point's height above the ground differs from the LOD1 height by more than
  max(MATCH_M, MATCH_SHARE x the LOD1 height), the building changed after the 2021 scan or the footprint does not
  match it, and the building is skipped (listed in the review);
- raised parts: roof points more than max(RAISE_M, RAISE_SHARE x the LOD1 height) above the LOD1 height, grouped on a
  CELL_M grid (cells that touch, diagonals included). A group needs MIN_CLUSTER points; its top is its highest point
  with another point of the group at most STEP_M below it (one stray return is not a spire); its outline is the convex
  hull of its points grown by HULL_BUFFER_M, at least MIN_SIDE_M on each side, cut to the footprint; its height is
  the top above the ground.

Writes data/towers.parquet (gid, part, height_m, n_points, top_z, ground_z, ground_basis, basis "laser", geometry: the
part's outline in EPSG:3011), data/towers.json (the counts and the sha256 of the buildings.parquet it was made from:
s03_tiles draws the parts only for that one) and data/review-towers.md (the 30 largest raises and every skipped
building, for a person to check against known heights before a version ships). Without cached points it says so and
writes nothing. Points never leave data/raw/laser: these outputs hold outlines and heights only.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from scipy import ndimage

from . import city, laser

DATA = Path("data")
OUT = DATA / "towers.parquet"
RECORD = DATA / "towers.json"
REVIEW = DATA / "review-towers.md"
RING_M = city.LASER["ring_m"]
OFF_CLASSES = (2, 7, 9, 18)      # ground, low noise, water, high noise
GROUND_CLASS = 2
MIN_GROUND = 5
MIN_ROOF = 10
MATCH_M, MATCH_SHARE = 4.0, 0.25
RAISE_M, RAISE_SHARE = 6.0, 0.25
CELL_M = 1.5
MIN_CLUSTER = 4
# Outside the hand list a raised part needs this many points: the full run of 2026-10-17 showed 4–20-point parts
# beside tall buildings (a neighbour's facade spilling over the footprint edge) and at building sites (cranes).
MIN_POINTS_UNLISTED = 20
STEP_M = 3.0
HULL_BUFFER_M = 1.0
MIN_SIDE_M = 3.0
MIN_PART_M2 = 1.0
REVIEW_TOP = 30


def ground_of(pts: dict, footprint, fallback: float) -> tuple[float, str]:
    """(ground height, "ring" or "lod1"): the median of the ground points in the ring around the footprint."""
    ring = shapely.difference(shapely.buffer(footprint, RING_M), footprint)
    sel = (pts["cls"] == GROUND_CLASS) & shapely.contains_xy(ring, pts["x"], pts["y"])
    if sel.sum() >= MIN_GROUND:
        return float(np.median(pts["z"][sel])), "ring"
    return float(fallback), "lod1"


def roof_mask(pts: dict, footprint) -> np.ndarray:
    """Points inside the footprint that may be roof: not ground, noise or water; single or last returns only."""
    nr, rn = pts["nr"].astype(int), pts["rn"].astype(int)
    last = (nr <= 1) | (rn == nr)
    return (~np.isin(pts["cls"], OFF_CLASSES)) & last & shapely.contains_xy(footprint, pts["x"], pts["y"])


def clusters(x: np.ndarray, y: np.ndarray, cell: float = CELL_M) -> np.ndarray:
    """A label per point (0, 1, ...): points whose CELL_M cells touch, diagonals included, share a label."""
    if not len(x):
        return np.zeros(0, dtype=int)
    ix = np.floor((x - x.min()) / cell).astype(int)
    iy = np.floor((y - y.min()) / cell).astype(int)
    grid = np.zeros((ix.max() + 1, iy.max() + 1), dtype=bool)
    grid[ix, iy] = True
    labels, _ = ndimage.label(grid, structure=np.ones((3, 3), dtype=int))
    return labels[ix, iy] - 1


def cluster_top(z: np.ndarray, step: float = STEP_M) -> float | None:
    """The highest point with another point at most `step` below it (or level with it); None when there is none."""
    s = np.sort(np.asarray(z, dtype=np.float64))[::-1]
    for i in range(len(s) - 1):
        if s[i] - s[i + 1] <= step:
            return float(s[i])
    return None


def part_shape(x: np.ndarray, y: np.ndarray, footprint):
    """The convex hull of the points grown by HULL_BUFFER_M, at least MIN_SIDE_M by MIN_SIDE_M, cut to the footprint;
    None when less than MIN_PART_M2 of it lies on the footprint."""
    hull = shapely.buffer(shapely.convex_hull(shapely.multipoints(np.c_[x, y])), HULL_BUFFER_M)
    x0, y0, x1, y1 = hull.bounds
    if x1 - x0 < MIN_SIDE_M or y1 - y0 < MIN_SIDE_M:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = max(x1 - x0, MIN_SIDE_M) / 2, max(y1 - y0, MIN_SIDE_M) / 2
        hull = shapely.union(hull, shapely.box(cx - w, cy - h, cx + w, cy + h))
    part = shapely.make_valid(shapely.intersection(hull, footprint))
    polys = [g for g in getattr(part, "geoms", [part]) if isinstance(g, (shapely.Polygon, shapely.MultiPolygon))]
    part = shapely.union_all(polys) if polys else None
    if part is None or part.is_empty or part.area < MIN_PART_M2:
        return None
    return part


def detect(footprint, lod1: float, pts: dict, fallback_ground: float, trusted: bool = False) -> dict:
    """{parts: [{geometry, height_m, n_points, top_z}], skip: reason or None, ground, ground_basis, roof_m, n_roof}.
    `trusted` (a hand-listed landmark, city.LASER_TOWERS) skips the roof check: there the City's footprint can be a low
    base its LOD1 height does not match (Kaknästornet, Globen), and the laser's tower is the point."""
    ground, basis = ground_of(pts, footprint, fallback_ground)
    out = {"parts": [], "skip": None, "ground": ground, "ground_basis": basis, "roof_m": None, "n_roof": 0}
    roof = roof_mask(pts, footprint)
    out["n_roof"] = int(roof.sum())
    if roof.sum() < MIN_ROOF:
        out["skip"] = f"{int(roof.sum())} roof points, fewer than {MIN_ROOF}"
        return out
    rel = pts["z"][roof] - ground
    med = float(np.median(rel))
    out["roof_m"] = med
    if not trusted and abs(med - lod1) > max(MATCH_M, MATCH_SHARE * lod1):
        out["skip"] = (f"roof {med:.1f} m above the ground, the LOD1 says {lod1:.1f} m: changed since the 2021 scan, "
                       "or the footprint does not match")
        return out
    hi = rel > lod1 + max(RAISE_M, RAISE_SHARE * lod1)
    x, y, z = pts["x"][roof][hi], pts["y"][roof][hi], pts["z"][roof][hi]
    labels = clusters(x, y)
    for k in range(labels.max() + 1 if len(labels) else 0):
        sel = labels == k
        if sel.sum() < (MIN_CLUSTER if trusted else max(MIN_CLUSTER, MIN_POINTS_UNLISTED)):
            continue
        top = cluster_top(z[sel])
        if top is None:
            continue
        shape = part_shape(x[sel], y[sel], footprint)
        if shape is None:
            continue
        out["parts"].append({"geometry": shape, "height_m": top - ground, "n_points": int(sel.sum()), "top_z": top})
    out["parts"].sort(key=lambda p: -p["height_m"])
    return out


def build(cands: gpd.GeoDataFrame, folder: Path = laser.POINTS) -> tuple[gpd.GeoDataFrame, list[dict], dict]:
    """(towers rows, per-candidate results with points, counts) for the candidates whose points are cached."""
    rows, results = [], []
    for gid, name, why, h, g, geom in zip(cands.gid, cands.name, cands.why, cands.height, cands.ground, cands.geometry,
                                          strict=True):
        path = laser.points_path(gid, folder)
        if not path.exists():
            continue
        r = detect(geom, float(h), laser.load_points(path), float(g), trusted="list" in str(why).split(","))
        results.append({"gid": int(gid), "name": name, "lod1": float(h), **r})
        for k, p in enumerate(r["parts"]):
            rows.append({"gid": int(gid), "part": k, "height_m": float(p["height_m"]), "n_points": p["n_points"],
                         "top_z": float(p["top_z"]), "ground_z": r["ground"], "ground_basis": r["ground_basis"],
                         "basis": "laser", "geometry": p["geometry"]})
    towers = gpd.GeoDataFrame(rows, columns=["gid", "part", "height_m", "n_points", "top_z", "ground_z", "ground_basis",
                                             "basis", "geometry"], geometry="geometry", crs=city.CRS)
    towers = towers.astype({"gid": "int32", "part": "uint8", "height_m": "float32", "n_points": "int32",
                            "top_z": "float32", "ground_z": "float32"})
    counts = {"candidates": len(cands), "with_points": len(results),
              "raised": len({r["gid"] for r in results if r["parts"]}), "parts": len(towers),
              "skipped": sum(1 for r in results if r["skip"])}
    return towers, results, counts


def review(results: list[dict], missing: list[str], counts: dict) -> str:
    """data/review-towers.md: the REVIEW_TOP largest raises and the skipped buildings with their reasons."""
    def label(r):
        return r["name"] or f"gid {r['gid']}"
    raises = sorted(((r, p) for r in results for p in r["parts"]), key=lambda rp: -(rp[1]["height_m"] - rp[0]["lod1"]))
    lines = ["# Towers from the laser points (s02_towers; internal, a hand check before a version ships)", "",
             f"{counts['candidates']} candidates, {counts['with_points']} with laser points; {counts['raised']} "
             f"buildings raised in {counts['parts']} parts; {counts['skipped']} skipped.", "",
             f"## The {REVIEW_TOP} largest raises", "",
             "| Building | gid | LOD1 height (m) | New height (m) | Raise (m) | Points | Ground |",
             "|---|---|---|---|---|---|---|"]
    for r, p in raises[:REVIEW_TOP]:
        lines.append(f"| {label(r)} | {r['gid']} | {r['lod1']:.1f} | {p['height_m']:.1f} | "
                     f"{p['height_m'] - r['lod1']:.1f} | {p['n_points']} | {r['ground_basis']} |")
    skipped = [r for r in results if r["skip"]]
    lines += ["", f"## Skipped ({len(skipped)})", ""]
    lines += [f"- {label(r)} (gid {r['gid']}, LOD1 {r['lod1']:.1f} m): {r['skip']}" for r in skipped] or ["None."]
    lines += ["", "## Hand-list names no card carries", ""]
    lines += [f"- {m}" for m in missing] or ["None."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s02_towers", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help=argparse.SUPPRESS)   # pipeline.run hands a build's arguments to every step
    ap.parse_args([] if argv is None else argv)
    if not laser.POINTS.exists() or not any(laser.POINTS.glob("*.npz")):
        print(f"s02_towers: no laser points in {laser.POINTS} (s00_fetch_laser needs the owner's login), so no towers")
        return
    cands, missing = laser.load_candidates(DATA)
    towers, results, counts = build(cands)
    towers.to_parquet(OUT, index=False)
    RECORD.write_text(json.dumps({**counts, "buildings_sha256": hashlib.sha256(
        (DATA / "buildings.parquet").read_bytes()).hexdigest()}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    REVIEW.write_text(review(results, missing, counts), encoding="utf-8")
    print(f"s02_towers: {counts['raised']} of {counts['with_points']} buildings with laser points raised, "
          f"{counts['parts']} parts, {counts['skipped']} skipped -> {OUT}; review {REVIEW}")


if __name__ == "__main__":
    main(sys.argv[1:])
