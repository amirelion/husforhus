"""Tunnelbanan as a dated layer (roadmap item 16, D35 point 1): stations and segments from the research CSVs, plus
OSM running track cut into the dated segments.

Inputs (docs/research/2026-10-16-tunnelbanan*): the stations CSV (100 open stations, Kymlinge which never opened, and
6 provisional or moved predecessors) and the segments CSV (32 openings, 1950-10-01 to 1994-08-15). Play shows each
station from its `opening_date` (the inauguration, note §3) at today's point; the provisional rows are kept apart, as
data for the card text only (note §9 no. 4).

Track (note §7.1): one Overpass query, pipeline/queries/metro_track.overpass, cached in data/raw/osm/metro.json via
fetch.post_query_retrying. The cut builds a graph from running track (railway=subway with no service tag) plus
service=crossover ways, and joins each pair of neighbouring stations by the shortest path, where:
  - any vertex within SNAP_M of the station point can be an end, and that distance is added to the path;
  - a way named after another line costs OTHER_LINE_FACTOR times its length;
  - service=siding is allowed only for the segments in SIDING_OK (the Hallonbergen–Rinkeby tunnel, tagged siding today).
Long ways cross station points, so the path is cut at the snap vertex, not by whole ways.

Output: data/metro.json (git-ignored), coordinates in EPSG:3011 like the other steps (geo.lonlat_to_3011).
    uv run python -m pipeline.metro            # stations + segments, track from the cache if present
    uv run python -m pipeline.metro --track    # also query Overpass when the track cache is missing
"""
import argparse
import csv
import datetime as dt
import heapq
import json
import math
import re
import sys
import time
from pathlib import Path

from pipeline.fetch import post_query_retrying
from pipeline.geo import lonlat_to_3011

RESEARCH = Path("docs/research")
STATIONS_CSV = RESEARCH / "2026-10-16-tunnelbanan-stations.csv"
SEGMENTS_CSV = RESEARCH / "2026-10-16-tunnelbanan-segments.csv"
DEST = Path("data/metro.json")
TRACK_RAW = Path("data/raw/osm/metro.json")
QUERY = Path(__file__).with_name("queries") / "metro_track.overpass"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
RETRIES = 2
BACKOFF_S = 5
sleep = time.sleep             # module-level so tests can stub the wait

LINES = {"Grön": "green", "Röd": "red", "Blå": "blue"}   # our own colour keys, not SL's styling
SNAP_M = 150.0
OTHER_LINE_FACTOR = 5.0
SIDING_OK = {"S26"}
DATE = re.compile(r"\d{4}-\d\d-\d\d")


def parse_date(s: str | None) -> str | None:
    """'1950-10-01' -> '1950-10-01' (validated), '' -> None; anything else raises ValueError."""
    s = (s or "").strip()
    if not s:
        return None
    return dt.date.fromisoformat(s).isoformat()


def _line_keys(s: str) -> list[str]:
    return [LINES[p.strip()] for p in s.split(";") if p.strip()]


def _line_dates(s: str) -> dict[str, str]:
    """'Grön 1952-10-26; Blå 1975-08-31' -> {'green': '1952-10-26', 'blue': '1975-08-31'}."""
    out = {}
    for part in filter(None, (p.strip() for p in s.split(";"))):
        line, date = part.rsplit(" ", 1)
        out[LINES[line]] = parse_date(date)
    return out


_SPAN = re.compile(r"^(?P<name>.+?) (?:\((?P<note>.*?) ?(?P<a>\d{4}-\d\d-\d\d) – (?P<b>\d{4}-\d\d-\d\d)\)"
                   r"|(?P<a2>\d{4}-\d\d-\d\d) – (?P<b2>\d{4}-\d\d-\d\d)|from (?P<f>\d{4}-\d\d-\d\d))$")


def parse_names(s: str) -> list[dict]:
    """name_history -> [{'name', 'from', 'to', 'note'?}]; 'X since opening' or a bare name -> [] (no rename).
    'Kungsgatan 1952-10-26 – 1957-11-23; Hötorget from 1957-11-24' gives two entries, the last with to=None."""
    s = s.strip()
    if not s or s.endswith(" since opening") or ";" not in s:
        return []
    out = []
    for part in (p.strip() for p in s.split(";")):
        m = _SPAN.match(part)
        if not m:
            raise ValueError(f"unreadable name_history part: {part!r}")
        e = {"name": m["name"], "from": parse_date(m["a"] or m["a2"] or m["f"]), "to": parse_date(m["b"] or m["b2"])}
        if m["note"]:
            e["note"] = m["note"]
        out.append(e)
    return out


def _xy(lon: float, lat: float) -> list[float]:
    x, y = lonlat_to_3011([lon], [lat])
    return [round(float(x[0]), 1), round(float(y[0]), 1)]


def load_stations(path: Path = STATIONS_CSV) -> tuple[list[dict], list[dict]]:
    """(stations, provisional). stations: the open ones and Kymlinge (opening_date None); provisional: the replaced
    predecessors, no coordinates, kept for card text only."""
    stations, provisional = [], []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            s = {"name": r["name_sv"], "lines": _line_keys(r["lines"]), "status": r["status"],
                 "opening_date": parse_date(r["opening_date"]), "closing_date": parse_date(r["closing_date"]),
                 "line_opening_dates": _line_dates(r["line_opening_dates"]),
                 "renames": parse_names(r["name_history"]),
                 "inside_stockholms_kommun": r["inside_stockholms_kommun"] == "yes",
                 "segment": r["opened_by_segment"] or None, "confidence": r["confidence"]}
            if r["status"] == "replaced":
                s["successor_date"] = parse_date(r["closing_date"])
                provisional.append(s)
                continue
            if r["status"] not in ("open", "never_opened"):
                raise ValueError(f"{r['name_sv']}: unknown status {r['status']!r}")
            lon, lat = float(r["lon"]), float(r["lat"])
            s.update(lon=lon, lat=lat, xy=_xy(lon, lat), wikidata=r["wikidata_qid"] or None)
            stations.append(s)
    return stations, provisional


def load_segments(path: Path = SEGMENTS_CSV) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return [{"id": r["segment_id"], "line": LINES[r["line"]], "opening_date": parse_date(r["opening_date"]),
                 "closing_date": parse_date(r["passenger_closing_date"]),
                 "stations": [s.strip() for s in r["stations_in_order"].split(";")],
                 "osm_track_km": float(r["osm_track_km"]) if r["osm_track_km"] else None}
                for r in csv.DictReader(f)]


def open_on(item: dict, date: str) -> bool:
    """Open to passengers on `date` (ISO): opened on or before it, and not closed on or before it."""
    o, c = item.get("opening_date"), item.get("closing_date")
    return o is not None and o <= date and (c is None or date < c)


# ---- track --------------------------------------------------------------------------------------------------------

def _kind(tags: dict, segment_id: str) -> bool:
    if tags.get("railway") != "subway":
        return False
    svc = tags.get("service")
    return svc is None or svc == "crossover" or (svc == "siding" and segment_id in SIDING_OK)


def build_graph(elements: list[dict], segment_id: str = "", project=lonlat_to_3011) -> tuple[dict, dict]:
    """Overpass JSON elements (ways with node lists, plus their nodes) -> (xy by node id, adjacency
    {node: [(neighbour, length_m, cost)]}) over the ways usable for `segment_id`."""
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in elements if e["type"] == "node"}
    ids = list(nodes)
    xs, ys = project([nodes[i][0] for i in ids], [nodes[i][1] for i in ids])
    xy = {i: (float(x), float(y)) for i, x, y in zip(ids, xs, ys)}
    ways = [e for e in elements if e["type"] == "way" and _kind(e.get("tags", {}), segment_id)]
    graph: dict = {}
    for w in ways:
        for a, b in zip(w["nodes"], w["nodes"][1:]):
            d = math.dist(xy[a], xy[b])
            graph.setdefault(a, []).append((b, d, d))
            graph.setdefault(b, []).append((a, d, d))
    return xy, graph


def _penalised(elements, xy, graph, line: str):
    """Re-weight edges of ways whose name names another line (e.g. 'Gröna linjen' when cutting red track)."""
    others = [sv for sv, key in LINES.items() if key != line]
    bad = set()
    for w in (e for e in elements if e["type"] == "way"):
        name = w.get("tags", {}).get("name", "")
        if any(o in name for o in others):
            bad.update(zip(w["nodes"], w["nodes"][1:]))
    return {a: [(b, d, d * OTHER_LINE_FACTOR if (a, b) in bad or (b, a) in bad else c) for b, d, c in nbrs]
            for a, nbrs in graph.items()}


def shortest(xy, graph, start: tuple, end: tuple, snap_m: float = SNAP_M) -> tuple[list, float]:
    """Shortest path between two points: any vertex within snap_m of a point is a possible end, with that distance
    added. Returns (vertex ids in order, length in metres including the snap legs); ([], inf) when none."""
    def near(p):
        return [(n, math.dist(p, q)) for n, q in xy.items() if n in graph and math.dist(p, q) <= snap_m]
    ends = dict(near(end))
    seq = iter(range(1 << 62))             # tie-breaker: never compare vertex ids of mixed types
    heap = [(d, next(seq), d, n, None) for n, d in near(start)]
    heapq.heapify(heap)
    prev, done = {}, set()
    while heap:
        cost, _, length, n, p = heapq.heappop(heap)
        if n in done:
            continue
        done.add(n)
        prev[n] = p
        if n in ends:              # the snap leg is a terminal cost: only accept once it would be popped too
            heapq.heappush(heap, (cost + ends[n], next(seq), length + ends[n], ("end", n), n))
            del ends[n]
            continue
        if isinstance(n, tuple):
            path, v = [], n[1]
            while v is not None:
                path.append(v)
                v = prev[v]
            return path[::-1], length
        for m, d, c in graph.get(n, ()):
            if m not in done:
                heapq.heappush(heap, (cost + c, next(seq), length + d, m, n))
    return [], math.inf


def cut_segment(elements: list[dict], segment: dict, station_xy: dict, project=lonlat_to_3011) -> dict:
    """One segment's track: {'coords': [[x, y], ...] in EPSG:3011, 'length_m'}; raises when a pair has no path."""
    xy, graph = build_graph(elements, segment["id"], project)
    graph = _penalised(elements, xy, graph, segment["line"])
    coords, total = [], 0.0
    for a, b in zip(segment["stations"], segment["stations"][1:]):
        path, length = shortest(xy, graph, station_xy[a], station_xy[b])
        if not path:
            raise ValueError(f"{segment['id']}: no track between {a} and {b}")
        pts = [list(station_xy[a])] + [list(xy[n]) for n in path] + [list(station_xy[b])]
        coords.extend(pts if not coords else pts[1:])
        total += length
    return {"coords": [[round(x, 1), round(y, 1)] for x, y in coords], "length_m": round(total, 1)}


def fetch_track(refresh: bool = False) -> list[dict]:
    post_query_retrying(OVERPASS, {"data": QUERY.read_text(encoding="utf-8")}, TRACK_RAW, retries=RETRIES,
                        backoff_s=BACKOFF_S, sleep=sleep, refresh=refresh)
    return json.loads(TRACK_RAW.read_text(encoding="utf-8"))["elements"]


# ---- build --------------------------------------------------------------------------------------------------------

def build(elements: list[dict] | None = None) -> dict:
    stations, provisional = load_stations()
    segments = load_segments()
    by_name = {s["name"]: s for s in stations}
    missing = sorted({n for g in segments for n in g["stations"]} - set(by_name))
    if missing:
        raise ValueError(f"segment stations not in the stations table: {missing}")
    if elements is not None:
        station_xy = {n: tuple(s["xy"]) for n, s in by_name.items()}
        for g in segments:
            g["track"] = cut_segment(elements, g, station_xy)
    return {"crs": "EPSG:3011", "stations": stations, "provisional": provisional, "segments": segments}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="metro", description=__doc__.splitlines()[0])
    ap.add_argument("--track", action="store_true", help="query Overpass for the track when the cache is missing")
    ap.add_argument("--refresh", action="store_true", help="query Overpass again even when the cache matches")
    args = ap.parse_args([] if argv is None else argv)
    elements = None
    if args.track or args.refresh:
        elements = fetch_track(refresh=args.refresh)
    elif TRACK_RAW.exists():
        elements = json.loads(TRACK_RAW.read_text(encoding="utf-8"))["elements"]
    else:
        print(f"warning: no track cache at {TRACK_RAW}; writing stations and segments without track "
              "(run with --track)", file=sys.stderr)
    layer = build(elements)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(layer, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"metro: {len(layer['stations'])} stations, {len(layer['segments'])} segments -> {DEST}")


if __name__ == "__main__":
    main(sys.argv[1:])
