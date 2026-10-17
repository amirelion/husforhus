"""Land, water and terrain from the Stadskarta and s02_terrain, clipped to the municipality, in the local frame.

Adapted from upstream reference/amsterdam/pipeline/s04_water.py (alexbarakov/amsterdam-by-building, MIT).
water = Vatten_area; land = the domain (the union of the 117 stadsdelar, or the fixture box with HFH_FIXTURE=1)
minus that same water, so land and water share every edge. Water levels: one for the sea and Mälaren, its own for
each lake (data/terrain.npz, s02_terrain).

water.bin.gz / land.bin.gz (gzip of, little-endian):
  u32 nPoly, nRing, nVert; u32 ringStart[nPoly+1]; u32 vertStart[nRing+1]; f32 xz[2*nVert]
The first ring of each polygon is its exterior, the rest are holes. xz are local metres (x east, z south).
terrain.bin.gz (pipeline/terrain.py): the grid from data/terrain.npz, the cells' classes, the land of
the edge cells and which water edges are shores.
"""
import argparse
import json
import os
import struct
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

from . import city, io, terrain
from .s03_tiles import check_built_from, out_dir

RAW = Path("data/raw/city")
DATA = Path("data")
MIN_AREA = 30.0   # m²; smaller slivers are dropped
SIMPLIFY = 1.0    # m
PRECISION = 0.01  # m; land, water and the domain on one 1 cm grid, so a sliver thinner than that between them collapses


def find(raw: Path, name: str) -> Path:
    hits = sorted(raw.rglob(name))
    if not hits:
        raise FileNotFoundError(f"{name} not found under {raw}; run s00_fetch_city first")
    return hits[0]


def boundary(raw: Path = RAW):
    """The municipality: the union of the 117 stadsdelar (Stadsdel.shp), in EPSG:3011, 2D."""
    d = gpd.read_file(find(raw, "Stadsdel.shp")).to_crs(city.CRS)
    return shapely.make_valid(shapely.force_2d(d.union_all()))


def domain(raw: Path = RAW, fixture: bool = False):
    """What land, water and terrain cover (EPSG:3011): the municipality, or with HFH_FIXTURE=1 only its part within
    city.FIXTURE_BBOX grown by TERRAIN["fixture_margin"] (a fixture build then grids a few km, not the city)."""
    city_geom = boundary(raw)
    if not fixture:
        return city_geom
    e0, n0, e1, n1 = city.FIXTURE_BBOX
    m = city.TERRAIN["fixture_margin"]
    return shapely.make_valid(city_geom.intersection(shapely.box(e0 - m, n0 - m, e1 + m, n1 + m)))


def polygons(geom) -> list:
    return [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]


def land_and_water(water_geoms, city_geom) -> tuple[list, list]:
    """Upstream recipe, with one change: make_valid, union, close 0.5 m gaps, simplify 1 m, then clip to
    the domain and drop pieces under 30 m². Simplifying before the clip keeps the domain's own edge exact, and land is
    the domain minus that same water, so land and water share every edge (no slivers or overlaps along the shores, and
    the terrain's shore walls meet the water exactly). All three are snapped to PRECISION, which also closes the
    sub-millimetre gap the buffer round trip leaves where water meets the domain's edge. Dropped ponds become land."""
    city_geom = shapely.set_precision(city_geom, PRECISION)
    water = shapely.make_valid(shapely.union_all(shapely.make_valid(np.asarray(water_geoms))))
    water = shapely.make_valid(water.buffer(0.5).buffer(-0.5).simplify(SIMPLIFY)).intersection(city_geom)
    water = [p for p in polygons(shapely.set_precision(water, PRECISION)) if p.area >= MIN_AREA]
    land = city_geom.difference(shapely.union_all(water)) if water else city_geom
    land = [p for p in polygons(shapely.set_precision(land, PRECISION)) if p.area >= MIN_AREA]
    return land, water


def pack(geoms) -> bytes:
    """Polygons (EPSG:3011) → the upstream polygon format in local metres."""
    ring_start, vert_start, verts = [0], [0], []
    for poly in geoms:
        for ring in [poly.exterior, *poly.interiors]:
            c = shapely.get_coordinates(ring)[:-1]
            if len(c) < 3:
                continue
            x, z = city.to_local(c[:, 0], c[:, 1])
            verts.append(np.c_[x, z].astype("<f4"))
            vert_start.append(vert_start[-1] + len(c))
        ring_start.append(len(vert_start) - 1)
    V = np.concatenate(verts) if verts else np.zeros((0, 2), "<f4")
    return (struct.pack("<3I", len(ring_start) - 1, len(vert_start) - 1, len(V))
            + np.array(ring_start, "<u4").tobytes() + np.array(vert_start, "<u4").tobytes() + V.tobytes())


def unpack(buf: bytes) -> list[list[np.ndarray]]:
    """Inverse of pack: per polygon, its rings as (n, 2) arrays of local x, z."""
    n_poly, n_ring, n_vert = struct.unpack_from("<3I", buf, 0)
    o = 12
    ring_start = np.frombuffer(buf, "<u4", n_poly + 1, o)
    o += 4 * (n_poly + 1)
    vert_start = np.frombuffer(buf, "<u4", n_ring + 1, o)
    o += 4 * (n_ring + 1)
    xz = np.frombuffer(buf, "<f4", 2 * n_vert, o).reshape(-1, 2)
    return [[xz[vert_start[r]:vert_start[r + 1]] for r in range(ring_start[p], ring_start[p + 1])]
            for p in range(n_poly)]


def load_terrain(data: Path = DATA) -> tuple[dict, dict]:
    """(arrays, record) written by s02_terrain: data/terrain.npz and data/terrain.json."""
    npz, rec = data / "terrain.npz", data / "terrain.json"
    if not npz.exists() or not rec.exists():
        raise SystemExit(f"{npz} or {rec} is missing: run s02_terrain")
    with np.load(npz) as z:
        arrays = {k: z[k] for k in z.files}
    record = json.loads(rec.read_text(encoding="utf-8"))
    check_built_from(record, data)
    return arrays, record


def terrain_bytes(arrays: dict, record: dict, land, water, dom) -> bytes:
    """terrain.bin for the land and water polygons s04 ships (EPSG:3011) and s02_terrain's grid."""
    grid = terrain.Grid(record["x0"], record["z0"], record["cell"], record["nx"], record["nz"])
    if len(arrays["levels"]) != len(water) or abs(sum(p.area for p in water) - record["water_area"]) > 1.0:
        raise SystemExit("data/terrain.npz was built from other water polygons: run s02_terrain again")
    land_l = terrain.to_local(shapely.union_all(land)) if land else shapely.Polygon()
    cls, rings, n_edge = terrain.classes_and_rings(grid, land_l, terrain.to_local(dom))
    shore, n_shore = terrain.shore_bits(unpack(pack(water)), terrain.to_local(shapely.boundary(dom)))
    return terrain.pack(grid, arrays["h"], arrays["cut"], arrays["levels"], record["water_z"], cls, rings, n_edge,
                        shore, n_shore, record["source"])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s04_base", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="output version (default: the one in web/data/current.json)")
    args = ap.parse_args(argv)
    dom = domain(fixture=os.environ.get("HFH_FIXTURE") == "1")
    w = gpd.read_file(find(RAW, "Vatten_area.shp")).to_crs(city.CRS)
    land, water = land_and_water(shapely.force_2d(w.geometry.values), dom)
    # every check first (a terrain built for other buildings or other water is refused), so a refusal writes nothing
    # and leaves the version folder as it was
    arrays, record = load_terrain()
    terrain_bin = terrain_bytes(arrays, record, land, water, dom)
    out = out_dir(args.version)
    n_water = io.write_gz(out / "water.bin.gz", pack(water))
    n_land = io.write_gz(out / "land.bin.gz", pack(land))
    n_terrain = io.write_gz(out / "terrain.bin.gz", terrain_bin)
    print(f"water {len(water)} polygons, {sum(p.area for p in water) / 1e6:.1f} km², {n_water / 1e3:.0f} KB gz; "
          f"land {len(land)} polygons, {sum(p.area for p in land) / 1e6:.1f} km², {n_land / 1e3:.0f} KB gz; "
          f"terrain ({record['source']}) {n_terrain / 1e3:.0f} KB gz → {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
