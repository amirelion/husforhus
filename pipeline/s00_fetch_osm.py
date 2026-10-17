"""Fetch the OpenStreetMap data the build uses. ODbL.

Dated buildings: one Overpass query, pipeline/queries/osm_dated.overpass: buildings in Stockholms kommun
(area ref:scb 0180) with start_date, year_of_construction or construction_date, as tags plus a centre point (about
1,400 elements), to data/raw/osm/dated.json.

Tiled queries: each query in TILED runs once per tile of city.BOX_WGS84 split into city.OSM_TILES (4 x 4
tiles of about 6.5 km), one request at a time, PAUSE_S apart, into data/raw/osm/<name>/<col>_<row>.json. The public
Overpass servers answer one large request for the whole city slowly and unreliably (a 502, then 52 s, on
2026-10-16), and a tile that fails keeps its cached copy without costing the others. `levels`
(osm_levels.overpass): building ways and multipolygon relations with building:levels, with their geometry, for
Floors (pipeline/osm_buildings.py; about 18 MB for the city); `addresses` (osm_addresses.overpass): every
node, way and relation with addr:street and addr:housenumber, nodes with their position and the others with their
centre, for the card and search (pipeline/addresses.py; about 77,000 elements, about 15 MB). An element crossing a tile
edge comes back in both tiles; the readers deduplicate.

Every result has a MANIFEST entry keyed by its query's sha256. A build reads the cache: nothing is sent unless a file
is missing or --refresh is given. Overpass is tried RETRIES times, waiting BACKOFF_S between tries (30, 60, then
120 s; longer when a 429 says Retry-After), because the public servers shed load for minutes at a time (two tiles
answered 502 twice on 2026-10-16 and came on the next round); the policy lives in fetch.post_query_retrying, shared
with s00_fetch_wikidata. Overpass reports a query that ran out of time or memory with HTTP 200 and a "runtime error"
remark: overpass_error refuses such an answer, so it is retried and never cached as an empty tile (a district would
lose its floors or its addresses until --refresh). When Overpass stays down a cached file is kept with a warning; a
tile with no cache is skipped while the others are fetched, and the step then stops naming the tiles to fetch again.

With HFH_FIXTURE=1 (the CI e2e job, the UI tasks' fixture builds) only the tiles that touch city.FIXTURE_BBOX are
fetched: one or two of the sixteen, not about 50 MB.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from pyproj import Transformer

from pipeline import city
from pipeline.fetch import post_query_retrying

OVERPASS = "https://overpass-api.de/api/interpreter"
QUERIES = Path(__file__).with_name("queries")
QUERY = QUERIES / "osm_dated.overpass"
RAW = Path("data/raw/osm")
DEST = RAW / "dated.json"
TILED = {"levels": QUERIES / "osm_levels.overpass", "addresses": QUERIES / "osm_addresses.overpass"}
RETRIES = 4                    # attempts
BACKOFF_S = (30, 60, 120)      # seconds before the second, third and fourth
PAUSE_S = 1.0                  # between two tile requests (Overpass: one request at a time)
sleep = time.sleep             # module-level so tests can stub the wait


def overpass_error(body: bytes) -> str | None:
    """What is wrong with an Overpass answer that came with HTTP 200, else None: not JSON, no `elements`, or a remark
    that reports an error ("runtime error: Query timed out", "… out of memory")."""
    try:
        data = json.loads(body)
    except ValueError:
        return "Overpass answered something that is not JSON"
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        return "Overpass answered without elements"
    remark = str(data.get("remark") or "")
    return f"Overpass: {remark[:120]}" if "error" in remark.lower() else None


def tiles(box=None, grid=None) -> list[tuple[str, tuple[float, float, float, float]]]:
    """("<col>_<row>", (south, west, north, east)) for every tile of the box, columns west to east, rows south to
    north; edges rounded to 6 decimals, so neighbours share them exactly."""
    lon0, lat0, lon1, lat1 = city.BOX_WGS84 if box is None else box
    nx, ny = city.OSM_TILES if grid is None else grid
    xs = [round(lon0 + (lon1 - lon0) * i / nx, 6) for i in range(nx + 1)]
    ys = [round(lat0 + (lat1 - lat0) * j / ny, 6) for j in range(ny + 1)]
    return [(f"{i}_{j}", (ys[j], xs[i], ys[j + 1], xs[i + 1])) for i in range(nx) for j in range(ny)]


def tile_query(template: str, bbox: tuple[float, float, float, float]) -> str:
    def num(v):                      # the edge as tiles() rounded it (6 decimals), without trailing zeros
        return f"{round(v, 6):.6f}".rstrip("0").rstrip(".")
    s, w, n, e = bbox
    return template.replace("{s}", num(s)).replace("{w}", num(w)).replace("{n}", num(n)).replace("{e}", num(e))


def fixture_tiles() -> list[tuple[str, tuple[float, float, float, float]]]:
    """The tiles that touch city.FIXTURE_BBOX (EPSG:3011, its corners taken to WGS84): what a fixture build needs."""
    to_wgs84 = Transformer.from_crs(city.CRS, 4326, always_xy=True)
    e0, n0, e1, n1 = city.FIXTURE_BBOX
    lons, lats = to_wgs84.transform([e0, e1, e0, e1], [n0, n0, n1, n1])
    w, s, e, n = min(lons), min(lats), max(lons), max(lats)
    return [(k, b) for k, b in tiles() if b[0] <= n and b[2] >= s and b[1] <= e and b[3] >= w]


def fetch_tiled(name: str, template_path: Path, refresh: bool, only=None) -> tuple[int, int]:
    """Every tile of one tiled query (or the `only` ones); returns (tiles, bytes). A tile that cannot be fetched and
    has no cache does not stop the others: the step stops afterwards, naming the tiles to fetch again."""
    template = template_path.read_text(encoding="utf-8")
    todo = tiles() if only is None else only
    total, sent, missing = 0, False, []
    for key, bbox in todo:
        dest = RAW / name / f"{key}.json"
        send = refresh or not dest.exists()      # a cached tile goes out only on --refresh
        if send and sent:
            sleep(PAUSE_S)
        sent = sent or send
        try:
            e = post_query_retrying([OVERPASS], {"data": tile_query(template, bbox)}, dest, retries=RETRIES,
                                    backoff_s=BACKOFF_S, sleep=sleep, refresh=refresh, check=overpass_error)
        except SystemExit as err:
            print(f"warning: {err}", file=sys.stderr)
            missing.append(key)
            continue
        total += e["bytes"]
    if missing:
        raise SystemExit(f"OSM {name}: Overpass did not answer for tile(s) {', '.join(missing)}, which have no cached "
                         f"copy; the other {len(todo) - len(missing)} are saved. Run s00_fetch_osm again later: only "
                         "the missing tiles are asked for.")
    return len(todo), total


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s00_fetch_osm", description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="query Overpass again even when the cache matches")
    args = ap.parse_args([] if argv is None else argv)
    e = post_query_retrying([OVERPASS], {"data": QUERY.read_text(encoding="utf-8")}, DEST, retries=RETRIES,
                            backoff_s=BACKOFF_S, sleep=sleep, refresh=args.refresh, check=overpass_error)
    print(f"OSM: {e['bytes']:,} bytes, retrieved {e['retrieved']} -> {DEST}")
    only = fixture_tiles() if os.environ.get("HFH_FIXTURE") == "1" else None
    for name, path in TILED.items():
        n, size = fetch_tiled(name, path, args.refresh, only)
        print(f"OSM {name}: {n} tiles, {size:,} bytes -> {RAW / name}")


if __name__ == "__main__":
    main(sys.argv[1:])
