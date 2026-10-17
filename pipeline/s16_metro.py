"""Tunnelbanan on the timeline: web/data/<version>/metro.json, in the local frame (city.to_local) like plaques.json.

pipeline/metro.py reads the research CSVs (docs/research/2026-10-16-tunnelbanan-*.csv) and cuts the OSM running track
(data/raw/osm/metro.json, one cached Overpass query) into the 32 dated segments. This step keeps what the viewer needs:
  segments: id, line (green | red | blue), opened (ISO date), closed (when it closed to passengers), stations in order,
            track [[x, z], ...] simplified to SIMPLIFY_M (station to station in a straight line when the track cache
            is missing and Overpass cannot be reached; a warning says so);
  stations: name, lines, opened, closed (when it closed), names (earlier names: name, from, to), wikidata, x, z;
            Kymlinge, which never opened, with opened null and never true.
The provisional stations stay out (no coordinates); their dates are in the card text of their successors' renames.
No images: station art may not be shown (HD 2016-04-04, Ö 849-15; docs/research/2026-10-16-tunnelbanan.md §8).

    uv run python -m pipeline.run s16_metro s99_validate
"""
import argparse
import sys

from shapely.geometry import LineString

from . import city, io, metro
from .s03_tiles import out_dir

SIMPLIFY_M = 4.0


def _local(xy) -> list[float]:
    x, z = city.to_local(xy[0], xy[1])
    return [round(float(x), 1), round(float(z), 1)]


def simplify(coords: list, tol: float = SIMPLIFY_M) -> list[list[float]]:
    if len(coords) < 3:
        return [list(c) for c in coords]
    return [[round(x, 1), round(y, 1)] for x, y in LineString(coords).simplify(tol, preserve_topology=False).coords]


def layer(raw: dict) -> dict:
    """metro.build's output (EPSG:3011) -> metro.json (local frame, the viewer's fields only)."""
    by_name = {s["name"]: s for s in raw["stations"]}
    segments = []
    for g in raw["segments"]:
        pts = (g.get("track") or {}).get("coords") or [by_name[n]["xy"] for n in g["stations"]]
        segments.append({"id": g["id"], "line": g["line"], "opened": g["opening_date"], "stations": g["stations"],
                         "track": simplify([_local(p) for p in pts]),
                         **({"closed": g["closing_date"]} if g.get("closing_date") else {})})
    stations = []
    for s in raw["stations"]:
        x, z = _local(s["xy"])
        e = {"name": s["name"], "lines": s["lines"], "opened": s["opening_date"], "x": x, "z": z,
             "wikidata": s.get("wikidata"),
             "names": [{"name": r["name"], "from": r["from"], "to": r["to"]} for r in s["renames"] if r["to"]]}
        if s.get("closing_date"):
            e["closed"] = s["closing_date"]
        if s["status"] == "never_opened":
            e["never"] = True
        stations.append(e)
    return {"segments": segments, "stations": sorted(stations, key=lambda e: e["name"])}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s16_metro", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="version folder (default: the one web/data/current.json names)")
    a, _ = ap.parse_known_args(argv or [])
    elements = None
    try:
        elements = metro.fetch_track()          # the cache when it is there, else one Overpass query
    except Exception as e:  # noqa: BLE001 - offline: the stations still show, joined by straight lines
        print(f"warning: no metro track ({e}); segments drawn station to station", file=sys.stderr)
    out = layer(metro.build(elements))
    io.write_json(out_dir(a.version) / "metro.json", out)
    print(f"metro: {len(out['stations'])} stations, {len(out['segments'])} segments"
          f"{'' if elements is not None else ' (no track)'}")


if __name__ == "__main__":
    main(sys.argv[1:])
