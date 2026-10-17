"""Writes the synthetic terrain fixture for the browser tests (web/test/terrain.test.mjs; Plan 3, Task 7).

A made-up 100 x 60 m shore, no City or Lantmäteriet data, so the output is committed:
  domain   local x 0..100, z 0..60 (x east, z south)
  water    one bay: (70, 10) (100, 10) (100, 50) (55, 50), cut off by the domain's east edge, at level 0.4 m
  heights  h = 3 + 0.05 x - 0.02 z metres (stored in decimetres), cut 0.7 m east of x = 40
Writes terrain_v1.bin (C16), water_v1.bin (the s04 polygon format) and terrain_v1.expect.json: sample points with
pipeline/terrain.py's bilinear values, the land and water areas, the class counts and the shore bits, which the
JS tests compare against (parity with the Python port).

Run from the repository root: uv run python tests/make_terrain_fixture.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "test" / "fixtures"
BAY = [(70.0, 10.0), (100.0, 10.0), (100.0, 50.0), (55.0, 50.0)]
LEVEL = 0.4
# (150, 100) lies beyond the grid's far corner and (30, -45) beyond its north edge: the sampler clamps each node
SAMPLES = [(0.0, 0.0), (10.0, 10.0), (33.3, 47.1), (-50.0, 5.0), (95.0, 70.0), (60.0, 20.0), (150.0, 100.0), (30.0, -45.0)]


def pipeline_on_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def build() -> tuple[bytes, bytes, dict]:
    pipeline_on_path()
    import numpy as np
    import shapely

    from pipeline import city, s04_base, terrain

    e0, n0 = city.ORIGIN
    to3011 = lambda g: shapely.transform(g, lambda c: np.c_[c[:, 0] + e0, n0 - c[:, 1]])  # noqa: E731
    domain = shapely.box(0, 0, 100, 60)
    bay = shapely.Polygon(BAY)
    land = domain.difference(bay)
    grid = terrain.grid_for(domain.bounds, 20.0)
    X, Z = grid.node_xz()
    h = np.round((3.0 + 0.05 * X - 0.02 * Z) * 10) / 10
    cut = np.where(X > 40, 0.7, 0.0)
    cls, rings, n_edge = terrain.classes_and_rings(grid, land, domain)
    water_bin = s04_base.pack([to3011(bay)])
    shore, n_shore = terrain.shore_bits(s04_base.unpack(water_bin), shapely.boundary(domain))
    buf = terrain.pack(grid, h, cut, [LEVEL], 0.0, cls, rings, n_edge, shore, n_shore)
    d = terrain.unpack(buf)
    xs, zs = np.array(SAMPLES).T
    expect = {
        "grid": grid.to_dict(), "level": LEVEL, "landArea": land.area, "waterArea": bay.area,
        "classes": np.bincount(cls.ravel(), minlength=4).tolist(), "nEdge": n_edge, "nShore": n_shore,
        "shore": np.unpackbits(np.frombuffer(shore, np.uint8), bitorder="little")[:n_shore].tolist(),
        "samples": [{"x": float(x), "z": float(z), "t": float(t), "cut": float(c)} for x, z, t, c in
                    zip(xs, zs, terrain.bilinear(grid, d["h"], xs, zs), terrain.bilinear(grid, d["cut"], xs, zs))],
    }
    return buf, water_bin, expect


def main() -> None:
    buf, water_bin, expect = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "terrain_v1.bin").write_bytes(buf)
    (OUT / "water_v1.bin").write_bytes(water_bin)
    (OUT / "terrain_v1.expect.json").write_text(json.dumps(expect, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"web/test/fixtures/terrain_v1.bin: {len(buf)} bytes, water_v1.bin: {len(water_bin)} bytes")


if __name__ == "__main__":
    main()
