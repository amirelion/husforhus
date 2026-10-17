"""Point helpers shared by the year sources (Plan 2 moved them out of s02_years, which re-exports them):
WGS84 -> EPSG:3011, and placing a point on a LOD1 footprint."""
import numpy as np
import shapely
from pyproj import Transformer

from . import city

LANDMARK_MAX_M = 15.0          # a landmark point may sit this far outside its footprint

_TO_3011 = Transformer.from_crs(4326, city.CRS, always_xy=True)


def lonlat_to_3011(lon, lat) -> tuple[np.ndarray, np.ndarray]:
    x, y = _TO_3011.transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    return np.asarray(x), np.asarray(y)


def _filled(g):
    if g.geom_type == "Polygon":
        return shapely.Polygon(g.exterior)
    return shapely.MultiPolygon([shapely.Polygon(p.exterior) for p in g.geoms])


def resolve_points(b, xs, ys, max_dist: float = LANDMARK_MAX_M) -> np.ndarray:
    """gid for each EPSG:3011 point, or -1.

    Order: a footprint containing the point; else one whose outer ring contains it (a courtyard,
    as at Stockholms slott); else the nearest footprint within max_dist. Several candidates at one
    step: the smallest footprint, then the lowest gid. In the nearest step distances are compared to the
    millimetre, then by gid: a point that is equidistant up to floating-point noise (a WGS84 round trip
    leaves ~1e-10 m) goes to the lowest gid, not to whichever side the noise favours.
    """
    geoms = b.geometry.values
    gids = b.gid.to_numpy()
    tree = shapely.STRtree(geoms)
    out = np.full(len(xs), -1, dtype=np.int64)
    for i, (x, y) in enumerate(zip(xs, ys)):
        p = shapely.Point(x, y)
        cand = tree.query(p)
        inside = sorted((j for j in cand if geoms[j].contains(p)), key=lambda j: (geoms[j].area, gids[j]))
        if not inside:
            inside = sorted((j for j in cand if _filled(geoms[j]).contains(p)),
                            key=lambda j: (geoms[j].area, gids[j]))
        if inside:
            out[i] = gids[inside[0]]
            continue
        j = tree.query(p, predicate="dwithin", distance=max_dist)
        if len(j):
            d = np.round(shapely.distance(geoms[j], p), 3)
            out[i] = gids[j[np.lexsort((gids[j], d))][0]]
    return out


def placement(b, gids, xs, ys) -> np.ndarray:
    """How each resolved point (resolve_points' gid per point) sits on its footprint: "inside" it, in a "courtyard"
    (inside the outer ring only) or "nearest" (outside, within the distance resolve_points allowed); "" for -1.
    The review list carries it (Plan 2): nearest-only placements are the least sure."""
    geoms = b.set_index("gid").geometry
    out = np.full(len(xs), "", dtype=object)
    for i, (g, x, y) in enumerate(zip(gids, xs, ys)):
        if g < 0:
            continue
        fp, p = geoms[g], shapely.Point(x, y)
        out[i] = "inside" if fp.contains(p) else ("courtyard" if _filled(fp).contains(p) else "nearest")
    return out
