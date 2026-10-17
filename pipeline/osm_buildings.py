"""OpenStreetMap buildings with building:levels, matched to LOD1 footprints.

load(): the tiles s00_fetch_osm cached (data/raw/osm/levels/*.json, Overpass JSON with `out geom`): every building way
and multipolygon relation that carries building:levels, as one polygon each in EPSG:3011, deduplicated across tiles
(an element crossing a tile edge comes back in both). A relation's rings are assembled from its member ways (an outer
ring is often several ways). levels(): building:levels as a number ("2,5" reads 2.5), rounded half up as the height
rule rounds; 0, a negative, a non-number or more than city.FLOORS_OSM's max_levels is no value. building:part and
roof:levels are not used (measured: roof levels make agreement with the height rule worse).

match(): a footprint takes the levels of the OSM building whose intersection with it over their union (IoU) is
largest, when that is above city.FLOORS_OSM's min_iou (0.5): the same building drawn twice, not a neighbour. The
OSM-derived floors stay a column of their own in data/attributes.parquet (floors_osm), so that if the City's licence answer rules out
licensing the whole database under the ODbL they can be split off. ODbL: © OpenStreetMap contributors.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from . import city
from .geo import lonlat_to_3011

LEVELS = Path("data/raw/osm/levels")


def levels(value) -> int:
    """building:levels as whole floors (half up), or 0 when it is no usable number."""
    if value is None:
        return 0
    try:
        v = float(str(value).strip().replace(",", "."))
    except ValueError:
        return 0
    if not math.isfinite(v) or v <= 0:
        return 0
    n = int(math.floor(v + 0.5))
    return n if 1 <= n <= city.FLOORS_OSM["max_levels"] else 0


def _ring(points) -> np.ndarray:
    lon = np.array([p["lon"] for p in points], dtype=float)
    lat = np.array([p["lat"] for p in points], dtype=float)
    x, y = lonlat_to_3011(lon, lat)
    return np.c_[x, y]


def _whole(points) -> bool:
    """True when every point has a position: under a bounding box Overpass can give null for the nodes outside it, and
    such a clipped copy is no outline (the whole copy may come from the next tile)."""
    return all(isinstance(p, dict) and "lat" in p and "lon" in p for p in points)


def _polygon(element: dict):
    """The element's footprint in EPSG:3011, or None when it has no usable geometry."""
    if element["type"] == "way":
        pts = element.get("geometry") or []
        if len(pts) < 4 or not _whole(pts):
            return None
        g = shapely.Polygon(_ring(pts))
    elif element["type"] == "relation":
        lines = {"outer": [], "inner": []}
        for m in element.get("members", []):
            if m.get("type") == "way" and m.get("role") in lines and not _whole(m.get("geometry") or []):
                return None
            if m.get("type") == "way" and m.get("role") in lines and len(m.get("geometry") or []) >= 2:
                lines[m["role"]].append(shapely.LineString(_ring(m["geometry"])))
        if not lines["outer"]:
            return None
        outer = shapely.union_all(shapely.get_parts(shapely.polygonize(lines["outer"])))
        if outer.is_empty:
            return None
        g = outer
        if lines["inner"]:
            g = g.difference(shapely.union_all(shapely.get_parts(shapely.polygonize(lines["inner"]))))
    else:
        return None
    g = shapely.make_valid(g)
    g = shapely.union_all([p for p in shapely.get_parts(g) if p.geom_type == "Polygon"]) if not g.is_empty else g
    return None if g.is_empty or g.area <= 0 else g


def load(folder: Path = LEVELS, names: list[str] | None = None) -> pd.DataFrame:
    """osm_id ("way/1", "relation/2"), levels, geometry (EPSG:3011): one row per building with usable levels. With
    `names`, only those tiles ("<col>_<row>", the current grid's): a tile left from another grid is never read (the
    final review)."""
    seen, rows = set(), []
    paths = sorted(Path(folder).glob("*.json")) if names is None else [Path(folder) / f"{k}.json" for k in sorted(names)]
    for path in (p for p in paths if p.exists()):
        for e in json.loads(path.read_text(encoding="utf-8")).get("elements", []):
            key = f"{e.get('type')}/{e.get('id')}"
            tags = e.get("tags") or {}
            if key in seen or "building" not in tags:
                continue
            n = levels(tags.get("building:levels"))
            if not n:
                continue
            g = _polygon(e)
            if g is not None:                    # seen only once whole: a clipped copy never hides the next tile's
                seen.add(key)
                rows.append((key, n, g))
    if not rows:
        return pd.DataFrame({"osm_id": pd.Series([], dtype=str), "levels": pd.Series([], dtype="uint8"),
                             "geometry": pd.Series([], dtype=object)})
    out = pd.DataFrame(rows, columns=["osm_id", "levels", "geometry"])
    out["levels"] = out.levels.astype("uint8")
    return out.sort_values("osm_id").reset_index(drop=True)


def match(b, osm: pd.DataFrame, min_iou: float | None = None) -> pd.Series:
    """Levels per gid (uint8, indexed by gid) for the footprints an OSM building matches at IoU > min_iou; the best
    IoU wins, then the lower osm_id. Footprints without a match are absent."""
    min_iou = city.FLOORS_OSM["min_iou"] if min_iou is None else min_iou
    empty = pd.Series([], dtype="uint8", index=pd.Index([], name="gid"), name="levels")
    if len(osm) == 0 or len(b) == 0:
        return empty
    fp = b.geometry.values
    tree = shapely.STRtree(fp)
    polys = np.asarray(osm.geometry.values, dtype=object)
    i_osm, i_fp = tree.query(polys, predicate="intersects")
    if len(i_osm) == 0:
        return empty
    inter = shapely.area(shapely.intersection(polys[i_osm], fp[i_fp]))
    union = shapely.area(polys[i_osm]) + shapely.area(fp[i_fp]) - inter
    iou = np.where(union > 0, inter / np.where(union > 0, union, 1), 0.0)
    m = pd.DataFrame({"gid": b.gid.to_numpy()[i_fp], "iou": iou, "osm_id": osm.osm_id.to_numpy()[i_osm],
                      "levels": osm.levels.to_numpy()[i_osm]})
    m = m[m.iou > min_iou].sort_values(["gid", "iou", "osm_id"], ascending=[True, False, True])
    best = m.groupby("gid").head(1).set_index("gid")
    return best.levels.astype("uint8").rename("levels")
