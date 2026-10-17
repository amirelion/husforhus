"""Writes the synthetic tile fixture for the browser decoder tests (web/test/tile.test.mjs, decode.test.mjs).

Three made-up buildings, no City data, so the output is committed:
  gid 7      10 x 10 m square,               12.5 m, 1924 RANGE,     period 6 (p7),  3 floors, ground  77 dm
  gid 42     20 x 20 m with an 8 x 8 m yard,  21.0 m, 1650 LONG,      period 1 (p2),  6 floors, ground 123 dm
  gid 70000  right triangle, 6 m legs,         3.0 m, year 0 UNKNOWN, period 0,       1 floor,  ground -11 dm

Run from the repository root: uv run python tests/make_tile_fixture.py
"""

import sys
from pathlib import Path

from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "test" / "fixtures"
TILE_ORIGIN = (-3000.0, 1500.0)  # tile tx=-2, tz=1 at 1500 m; local metres, x east, z south


def pipeline_on_path() -> None:
    """Lets `uv run python tests/make_tile_fixture.py` import pipeline.* from the repository root."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def build() -> bytes:
    """The fixture tile, written by the pipeline's own pack_tile."""
    pipeline_on_path()
    from pipeline.city import ORIGIN
    from pipeline.codes import LONG, RANGE, UNKNOWN
    from pipeline.s03_tiles import pack_tile

    def world(ring):
        """Tile-relative metres (x east, z south) -> EPSG:3011 (E, N)."""
        return [(ORIGIN[0] + TILE_ORIGIN[0] + x, ORIGIN[1] - (TILE_ORIGIN[1] + z)) for x, z in ring]

    square = Polygon(world([(5, 5), (15, 5), (15, 15), (5, 15)]))
    yard = Polygon(world([(30, 30), (50, 30), (50, 50), (30, 50)]), [world([(36, 36), (44, 36), (44, 44), (36, 44)])])
    triangle = Polygon(world([(60, 10), (66, 10), (60, 16)]))
    # Row keys as pack_tile reads them; it writes lay0/lay1 as zeros.
    rows = [
        {"gid": 7, "year": 1924, "yflag": RANGE, "period": 6, "floors": 3, "ground_dm": 77, "height": 12.5,
         "geometry": square},
        {"gid": 42, "year": 1650, "yflag": LONG, "period": 1, "floors": 6, "ground_dm": 123, "height": 21.0,
         "geometry": yard},
        {"gid": 70000, "year": 0, "yflag": UNKNOWN, "period": 0, "floors": 1, "ground_dm": -11, "height": 3.0,
         "geometry": triangle},
    ]
    return pack_tile(TILE_ORIGIN, rows)


def main() -> None:
    pipeline_on_path()
    from pipeline.io import write_gz

    data = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tile_v1.bin").write_bytes(data)
    write_gz(OUT / "tile_v1.bin.gz", data)
    print(f"web/test/fixtures/tile_v1.bin: {len(data)} bytes")


if __name__ == "__main__":
    main()
