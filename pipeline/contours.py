"""Heights for the City's 2 m contour lines, the terrain's no-account source (spike 2026-10-15).

The Stadskarta's 0_line.shp holds 28,410 contour lines (GRUPP "Höjdkurva heltäckande", RH 2000) with no height; its
NamnText_point holds 29,685 height labels in the same group (TEXT, whole metres). A line takes the most common label
within LABEL_M of it (40% of the lines, 70% of the length). An unlabelled line takes the median of a linear TIN of
the labelled lines sampled along it, rounded to what its KATEGORI allows: a "10 m" line is a multiple of 10, a "Jämn"
line an even metre that is not. A line outside that TIN, or one no label and no TIN reaches, is dropped. s02_terrain
runs the inference a second time with more known heights in that TIN: the shores at their water levels and
the buildings' measured grounds. From the labelled lines alone, an unlabelled line along a quay under a cliff took the
cliff's height (Söder Mälarstrand 18 m, Slussen and Stadsgården 22 m, where the quays stand at about 2 m), because the
nearest labels were up the cliff and across the water.

The TIN sources (ContourSource) give heights anywhere inside the lines' hull; s02_terrain adds the water's shores at
their levels, as the spike did, so lakes and quays hold their level up to the bank.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.interpolate import LinearNDInterpolator

from . import terrain

LABEL_GRUPP = "Höjdkurva heltäckande"
LABEL_M = 3.0      # a label this close to a line names it
STEP_M = 10.0      # spacing of the points sampled along each line


def densify(geoms, step: float = STEP_M) -> tuple[np.ndarray, np.ndarray]:
    """(points (n, 2), owner index) every `step` metres along each (multi)line, ends included."""
    dense = shapely.segmentize(np.asarray(geoms, dtype=object), step)
    return shapely.get_coordinates(dense, return_index=True)


def allowed(median: np.ndarray, ten: np.ndarray) -> np.ndarray:
    """The nearest height a line may have: a multiple of 10 for a "10 m" line, else an even metre that is not."""
    m = np.asarray(median, dtype=np.float64)
    tens = np.round(m / 10) * 10
    even = np.round(m / 2) * 2
    even = np.where(even % 10 == 0, np.where(m >= even, even + 2, even - 2), even)
    return np.where(np.asarray(ten, dtype=bool), tens, even)


def label_lines(lines: gpd.GeoDataFrame, labels: gpd.GeoDataFrame) -> np.ndarray:
    """Each line's most common label within LABEL_M (NaN where none). lines need `geometry`; labels `geometry`, `h`.
    A tie goes to the lowest height, so the answer never depends on row order."""
    h = np.full(len(lines), np.nan)
    if not len(labels) or not len(lines):
        return h
    j = gpd.sjoin_nearest(labels[["h", "geometry"]], lines[["geometry"]].reset_index(drop=True),
                          max_distance=LABEL_M, how="inner")
    if not len(j):
        return h
    counts = j.groupby(["index_right", "h"]).size().reset_index(name="n")
    best = counts.sort_values(["index_right", "n", "h"], ascending=[True, False, True]).drop_duplicates("index_right")
    h[best.index_right.to_numpy()] = best.h.to_numpy()
    return h


def infer_unlabelled(lines: gpd.GeoDataFrame, h: np.ndarray, known_xy=None,
                     known_z=None) -> tuple[np.ndarray, np.ndarray]:
    """(h, src) with the unlabelled lines filled from a TIN of the labelled ones; src is "label", "inferred" or ""
    (dropped). lines need `geometry` and `ten`. known_xy (n, 2) and known_z (n,), in the lines' CRS, are more points of
    known height for that TIN: s02_terrain hands it the shores at their water levels and the buildings' grounds. A
    point on a labelled line's own vertex (to the centimetre) is left out, so the line's height wins there."""
    h = np.asarray(h, dtype=np.float64).copy()
    src = np.where(np.isfinite(h), "label", "").astype(object)
    known = np.flatnonzero(np.isfinite(h))
    todo = np.flatnonzero(~np.isfinite(h))
    if len(known) < 3 or not len(todo):
        return h, src
    xy, own = densify(lines.geometry.values[known])
    z = h[known][own]
    if known_xy is not None and len(known_xy):
        exy = np.asarray(known_xy, dtype=np.float64).reshape(-1, 2)
        ez = np.asarray(known_z, dtype=np.float64)
        _, inv = np.unique(np.round(np.r_[xy, exy], 2), axis=0, return_inverse=True)
        inv = inv.ravel()
        on_line = np.zeros(inv.max() + 1, dtype=bool)
        on_line[inv[:len(xy)]] = True
        mine = inv[len(xy):]
        keep = np.zeros(len(exy), dtype=bool)
        keep[np.unique(mine, return_index=True)[1]] = True      # the first of the extra points at one place
        keep &= ~on_line[mine]
        xy, z = np.r_[xy, exy[keep]], np.r_[z, ez[keep]]
    tin = LinearNDInterpolator(xy, z)
    uxy, uown = densify(lines.geometry.values[todo])
    v = tin(uxy)
    med = pd.Series(v).groupby(uown).median().reindex(range(len(todo))).to_numpy()
    fill = allowed(med, lines.ten.to_numpy()[todo])
    ok = np.isfinite(med)
    h[todo[ok]] = fill[ok]
    src[todo[ok]] = "inferred"
    return h, src


def read_labelled(stadskarta: Path) -> tuple[gpd.GeoDataFrame, np.ndarray]:
    """The contour lines (EPSG:3011, 2D, column `ten`) and each one's label height (NaN where none), read once so
    s02_terrain can infer the rest twice."""
    lines = gpd.read_file(stadskarta / "0_line.shp")
    if lines.crs is not None and lines.crs.to_epsg() != 3011:
        lines = lines.to_crs(3011)
    lines = gpd.GeoDataFrame({"ten": lines["KATEGORI"].astype(str).str.startswith("10").to_numpy()},
                             geometry=shapely.force_2d(lines.geometry.values), crs=3011)
    labels = gpd.read_file(stadskarta / "NamnText_point.shp")
    labels = labels[labels["GRUPP"] == LABEL_GRUPP]
    if labels.crs is not None and labels.crs.to_epsg() != 3011:
        labels = labels.to_crs(3011)
    labels = gpd.GeoDataFrame({"h": pd.to_numeric(labels["TEXT"], errors="coerce").to_numpy()},
                              geometry=shapely.force_2d(labels.geometry.values), crs=3011).dropna(subset=["h"])
    return lines, label_lines(lines, labels)


def with_heights(lines: gpd.GeoDataFrame, labelled: np.ndarray, known=None) -> gpd.GeoDataFrame:
    """read_labelled's lines with every height inferred (columns h, src, geometry; lines without one left out).
    known: (xy, z) in EPSG:3011, more points of known height for the inference (s02_terrain: the shores at their
    levels, as shore_points gives them, and the buildings' grounds)."""
    h, src = infer_unlabelled(lines, labelled, *(known if known is not None else (None, None)))
    out = gpd.GeoDataFrame({"h": h, "src": src}, geometry=lines.geometry.values, crs=3011)
    return out[np.isfinite(out.h.to_numpy())].reset_index(drop=True)


def load(stadskarta: Path, known=None) -> gpd.GeoDataFrame:
    """The contour lines with heights (EPSG:3011, 2D): columns h, src, geometry. Lines without a height are left
    out. known: as with_heights."""
    return with_heights(*read_labelled(stadskarta), known)


class ContourSource:
    """Heights from contour lines (local frame) as a linear TIN, optionally with extra points (shores at their
    water level). sample() is NaN outside the hull."""
    kind = "contours"

    def __init__(self, lines_local, heights, extra_xy=None, extra_z=None, step: float = STEP_M):
        xy, own = densify(lines_local, step)
        z = np.asarray(heights, dtype=np.float64)[own]
        if extra_xy is not None and len(extra_xy):
            xy = np.r_[xy, np.asarray(extra_xy, dtype=np.float64)]
            z = np.r_[z, np.asarray(extra_z, dtype=np.float64)]
        key = np.round(xy, 2)
        _, first = np.unique(key, axis=0, return_index=True)   # shared vertices would make Qhull complain
        first.sort()
        self.tin = LinearNDInterpolator(xy[first], z[first])

    def sample(self, xz) -> np.ndarray:
        xz = np.asarray(xz, dtype=np.float64).reshape(-1, 2)
        out = np.empty(len(xz))
        for a in range(0, len(xz), 1 << 20):   # in blocks, so memory stays flat on 7 million sub-samples
            out[a:a + (1 << 20)] = self.tin(xz[a:a + (1 << 20)])
        return out


def shore_points(water, levels, step: float = STEP_M) -> tuple[np.ndarray, np.ndarray]:
    """Points every `step` metres along each water polygon's rings, at that polygon's level, in the polygons' own
    coordinates: any CRS (s02_terrain asks for the local frame for the TIN and EPSG:3011 for the inference)."""
    if not len(water):
        return np.zeros((0, 2)), np.zeros(0)
    rings = shapely.boundary(np.asarray(water, dtype=object))
    xy, own = densify(rings, step)
    return xy, np.asarray(levels, dtype=np.float64)[own]


def lines_near(lines: gpd.GeoDataFrame, domain_local, margin: float) -> tuple[np.ndarray, np.ndarray]:
    """(local line geometries, heights) for the lines within `margin` of the domain's box."""
    minx, minz, maxx, maxz = domain_local.bounds
    local = terrain.to_local(lines.geometry.values)
    near = shapely.intersects(local, shapely.box(minx - margin, minz - margin, maxx + margin, maxz + margin))
    return local[near], lines.h.to_numpy()[near]
