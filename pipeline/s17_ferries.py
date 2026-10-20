"""Boats on the water (feature 5): web/data/<version>/ferries.json, in the local frame (city.to_local) like metro.json.

pipeline/ferries.py picks the routes from OpenStreetMap (data/raw/osm/ferries.json, one cached Overpass query): the
city's boats and the Baltic ships chosen on 2026-10-20, each cut to the map's water, which s04_base wrote into the
same version folder (water.bin.gz, land.bin.gz), so this step runs after s04_base. ferries.json, version 1:
  routes: id ("r" + the OSM relation id, or "w" + a way id), ref (the public line number, or ""), name (without its
          direction), kind ("ferry": the city's boats; "ship": the Baltic ships), ends (per end of the path: "pier", a
          terminal in the map, or "edge", where the lane leaves the map's water), path [[x, z], ...] (one line on the
          water that never leaves the map, simplified to 4 m, or 40 m where it is drawn along the map's edge, in
          0.1 m). One route per line, and per ship line and terminal for the ships.
The boats are illustration: real routes, not live positions. When Overpass cannot be reached and nothing is cached (or
the cache does not read), a warning says so and the file has no routes, so a preview or fixture build goes on without
boats (the viewer then draws none, as without the file); with --release the step stops instead, and s99_validate's
release check fails on a version whose ferries.json is missing or has no routes while features.ferries is on.

    uv run python -m pipeline.run s17_ferries s99_validate
"""
import argparse
import sys

from . import ferries, io
from .s03_tiles import out_dir


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s17_ferries", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="version folder (default: the one web/data/current.json names)")
    ap.add_argument("--release", action="store_true", help="a public build: stop when the routes cannot be had")
    a, _ = ap.parse_known_args(argv or [])
    out = out_dir(a.version)
    if not (out / "water.bin.gz").exists() or not (out / "land.bin.gz").exists():
        raise SystemExit(f"{out}: water.bin.gz or land.bin.gz is missing: run s04_base first")
    water, land = ferries.load_base(out)
    try:
        elements = ferries.fetch()              # the cache when it is there, else one Overpass query
    except (Exception, SystemExit) as e:  # noqa: BLE001 - offline with no cache: a preview without boats
        if a.release:
            raise
        print(f"warning: no ferry routes ({e}); ferries.json lists none", file=sys.stderr)
        elements = []
    layer = ferries.layer(elements, water, land)
    io.write_json(out / "ferries.json", layer)
    kinds = [r["kind"] for r in layer["routes"]]
    print(f"ferries: {kinds.count('ferry')} city boat routes, {kinds.count('ship')} ship routes")


if __name__ == "__main__":
    main(sys.argv[1:])
