"""Ferry routes for the boats (feature 5, docs/superpowers/specs/2026-10-20-fun-effects-design.md §5): which
OpenStreetMap route=ferry lines the map sails, and their paths on the map's own water.

Input: one Overpass query, pipeline/queries/ferry_routes.overpass (route=ferry relations and ways in Stockholms kommun,
with their geometry), cached in data/raw/osm/ferries.json via fetch.post_query_retrying, as metro.py's track.

Which boats (decided 2026-10-20), chosen by their tags (name, ref, operator, network):
  - ferry, the city's own boats: SL's Djurgårdsfärjan 82, Pendelbåt 80, 80X and 84 and Båt 89 (SL_LINES), Ressel's
    Sjöstadstrafiken and Cityline, and E/S Movitz between Riddarholmen and Solna strand (CITY_LINES);
  - ship, the big Baltic ships: Viking Line, Silja Line and Tallink (SHIPS).
Not the archipelago boats (Waxholmsbolaget's "Färja N" lines, Strömma's Sandhamn and Gustavsberg boats), not
sightseeing (Strömma's canal tours, Hop-On Hop-Off, s/s Stockholm, Mariefred) and not the E 20's road ferries.

Each chosen relation (or a chosen way that is in no relation) becomes one line: its route ways chained in member order,
in the local frame (city.to_local, x east, z south). The line is cut to the map's water (water.bin.gz and land.bin.gz,
s04_base; on_water): looked at every STEP_M, a point is on water, on land or off the map; off the map but within SNAP_M
of the water (SHIP_SNAP_M for a ship; the kommun's border runs down Saltsjön and Lilla Värtan, and some lanes run just
past it) it is moved onto the water's edge; stretches of water are joined across land up to BRIDGE_M (a bridge, a lock
gate, a pier the line was drawn onto), never across the map's edge. Each end of a stretch is a "pier" (at land, or the
route's own end) or an "edge" (the lane leaves the map's water). At an edge end the moved points stop where they would
walk back along the edge, and a step between moved points that would leave the map goes along the edge, or, where
there is no such way, ends the stretch. The line keeps its longest stretch with a pier (else its longest). Then one
route per line: a line's directions and variants are one route (the best of their stretches), and the Baltic ships'
relations one route per ship line (SHIPS) and terminal (their pier ends within TERMINAL_M), as they share the lane out
of Stockholm. Paths are simplified to SIMPLIFY_M (their points moved onto the edge to EDGE_SIMPLIFY_M, on the water) and
rounded to 0.1 m; every point lies on the water, and no segment leaves the map (they cross land only under a bridge or
at a pier). The boats are illustration: real routes, not live positions.

What the viewer says about a boat (its tooltip, web/ferries.js boatInfo), with each route, the names as OSM has them:
  - a city boat's name, its title: an SL line's own (Djurgårdsfärjan 82, Pendelbåt 80), a line without a number by the
    one of CITY_LINES its tags name (ferry_name: Movitz, whose OSM name is only its route);
  - a city boat's stops, in order along its path (stops): the chosen relation's stop and platform members that are
    named nodes (the query outputs them), placed along its line (along: OSM lists Båt 89's and Pendelbåt 84's stops
    out of order), a stop and its platform of one name once; else its from, via and to tags; else its name's
    "X: A - B - C". The whole line's, so a boat on a route cut at the map's edge still says where it goes (Tappström);
  - a Baltic ship's home port (home, its terminal's end of the relations: "Stockholm") and destinations (dests, each
    {to, via}: Turku via Mariehamn or Långnäs, Helsinki via Mariehamn) from all the relations of its route, by their
    from, via and to tags, else their names' "Stockholm => Mariehamn => Turku"; the stops' own names there are the
    terminals' ("Viking Line: Stadsgården, Stockholm"), not the ports'. And its operator when OSM has one.

    uv run python -m pipeline.ferries --base web/data/<version>              # print the routes
    uv run python -m pipeline.ferries --base web/data/<version> --dest PATH  # and write them as ferries.json
(the routes come from the cache when it matches the query, else from one Overpass query; --refresh asks again)
"""
import argparse
import gzip
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import shapely
import shapely.ops

from . import city, io
from .fetch import post_query_retrying
from .geo import lonlat_to_3011
from .s00_fetch_osm import overpass_error
from .s04_base import unpack

RAW = Path("data/raw/osm/ferries.json")
QUERY = Path(__file__).with_name("queries") / "ferry_routes.overpass"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
RETRIES = 4                    # as metro.py: Overpass is often busy
BACKOFF_S = (30, 60, 120)
sleep = time.sleep             # module-level so tests can stub the wait
VERSION = 1                    # ferries.json's format (the viewer's web/ferries.js reads it)

SL_LINES = {"80", "80X", "82", "84", "89"}             # SL's boats, by line number (network SL)
CITY_LINES = ("Sjöstadstrafiken", "Cityline", "Movitz")   # named in the name, ref, operator or network
SHIPS = ("Viking Line", "Silja Line", "Tallink")         # named before the name's colon, or in the operator
GENERIC = {"båt", "färja", "pendelbåt", "boat", "ferry"}  # a name head that says nothing ("Båt: Riddarholmen - …")
NOT_ROUTE = ("stop", "platform")                         # member roles (with _entry_only, _exit_only) of no way sailed
STOP_NODES = {"stop_position", "platform", "station"}     # public_transport of a stop node whose role was left empty
                                                         # (Movitz's Riddarholmen, Båt 89's Jungfrusund on 2026-10-20)
STOP_SLACK_M = 100.0           # a stop is looked for on its line after the one before it while it lies at most this much
                               # further from that part than from the whole line (a pier beside the lane; along)
LINE_REF = re.compile(r"\d{1,3}[A-Z]?")
ARROWS = re.compile(r"\s*(?:<=>|<->|=>|->|→|⇒|↔)\s*")
LEGS = re.compile(r"\s*(?:<=>|<->|=>|->|→|⇒|↔)\s*|\s+[-–]\s+")    # between the places of a name ("A - B", "A => B")
PLACE_HYPHEN = re.compile(r"\s+-\s+")                    # a hyphen with spaces round it, between two places

SIMPLIFY_M = 4.0               # as s16_metro
EDGE_SIMPLIFY_M = 40.0         # a path's points moved onto the map's edge are simplified this much, on the water: the
                               # kommun's border is jagged where the lane beside it runs straight
STEP_M = 10.0                  # near the map a line is looked at every STEP_M: on water, on land or off the map
SNAP_M = 150.0                 # a city boat's lane this close outside the map's water is drawn along its edge (the
                               # kommun's border runs down Saltsjön; Pendelbåt 84's and 80X's lanes keep up to 40 m
                               # outside it on 2026-10-20). Onto the edge itself: a line moved some way inside it
                               # zigzags where the lane's own points touch the edge
SHIP_SNAP_M = 250.0            # the same for a Baltic ship, whose lane keeps further out: Viking Line's up to 114 m
                               # outside the map down Saltsjön, Silja Line's and Tallink's 100-215 m for about 2.4 km
                               # down Lilla Värtan (2026-10-20). Not for the city's boats: their lanes that far out are
                               # on the way to a pier in another kommun, and 80, 84 and 89 would only run 100-260 m
                               # further along the border
BRIDGE_M = 60.0                # land this short between two stretches of water is crossed: a bridge the water stops
                               # under, a lock gate, a pier the line was drawn onto at a stop on the way
TERMINAL_M = 500.0             # Baltic ships' pier ends this close are one terminal
DETOUR = 4.0                   # a step off the map goes along the edge when that way is at most this many times longer
ON_WATER_M = 0.5               # a path point counts as on water this close to it (rounding to 0.1 m, float32 water)


# ---- which boats ---------------------------------------------------------------------------------------------------

def _head(name: str) -> str:
    """The part of a PTv2 name before its colon: 'Djurgårdsfärjan 82: Slussen - Djurgården' -> 'Djurgårdsfärjan 82'."""
    return name.partition(":")[0].strip()


def line_ref(tags: dict) -> str:
    """The public line number: the ref when it is one ('82'), else the one in the name's head ('Pendelbåt 80X' ->
    '80X'); '' for a line known by name (Cityline's ref is its name) or a ship."""
    ref = tags.get("ref", "").strip()
    if LINE_REF.fullmatch(ref):
        return ref
    found = [w for w in _head(tags.get("name", "")).split() if LINE_REF.fullmatch(w)]
    return found[-1] if found else ""


def clean_name(tags: dict) -> str:
    """The name without its direction: the head of a PTv2 name ('Viking Line: Stockholm => Mariehamn => Turku' ->
    'Viking Line'), or, when the head is a bare word such as 'Båt', the rest; the ref when there is no name; arrows,
    and a hyphen between two places ('A - B'), become the route line's dashes (web/ferries.js routeLine)."""
    raw = (tags.get("name") or tags.get("ref") or "").strip()
    head, colon, rest = raw.partition(":")
    if colon:
        raw = rest if head.strip().lower() in GENERIC else head
    return PLACE_HYPHEN.sub(" – ", ARROWS.sub(" – ", raw)).strip()


def ferry_name(tags: dict) -> str:
    """A city boat's name, the tooltip's title (web/ferries.js boatTitle): an SL line's from its name ('Djurgårdsfärjan
    82', clean_name); a line without a number by the one of CITY_LINES its tags name, as its name is often only its
    route ('Båt: Riddarholmen - Solna Strand', run by E/S Movitz, is Movitz), which the tooltip says below it."""
    if line_ref(tags):
        return clean_name(tags)
    words = " ".join(tags.get(k, "") for k in ("name", "ref", "operator", "network")).lower()
    return next((c for c in CITY_LINES if c.lower() in words), clean_name(tags))


def ship_line(tags: dict) -> str | None:
    """Which Baltic ship line (SHIPS) a route is: the one its name's head names ('Silja Line: Stockholm => Turku',
    'Viking Line Stockholm – Helsinki'), else its operator's ('M/S Gabriella' run by Viking Line; 'Tallink Silja' is
    Tallink); None for every other boat. The ships are grouped by it, so a relation named another way joins its line."""
    for said in (_head(tags.get("name", "")), tags.get("operator", "")):
        found = next((s for s in SHIPS if s.lower() in said.lower()), None)
        if found:
            return found
    return None


def kind(tags: dict) -> str | None:
    """'ship' for a Baltic ship, 'ferry' for one of the city's boats, None for every other route=ferry."""
    if ship_line(tags):
        return "ship"
    if tags.get("network") == "SL" and line_ref(tags) in SL_LINES:
        return "ferry"
    words = " ".join(tags.get(k, "") for k in ("name", "ref", "operator", "network")).lower()
    if any(c.lower() in words for c in CITY_LINES):
        return "ferry"
    return None


# ---- lines ---------------------------------------------------------------------------------------------------------

def _local(geometry: list, project) -> np.ndarray:
    pts = [p for p in geometry if p]                     # Overpass leaves null for a node it could not place
    if not pts:
        return np.zeros((0, 2))
    e, n = project([p["lon"] for p in pts], [p["lat"] for p in pts])
    x, z = city.to_local(e, n)
    return np.c_[x, z]


def chain(parts: list[np.ndarray]) -> np.ndarray:
    """Ways in member order as one line: each way turned to start where the line so far ends (the first one towards
    the second); a gap between two ways is crossed straight."""
    parts = [p for p in parts if len(p) >= 2]
    if not parts:
        return np.zeros((0, 2))
    first = parts[0]
    if len(parts) > 1:
        ends = (parts[1][0], parts[1][-1])
        if min(math.dist(first[0], e) for e in ends) < min(math.dist(first[-1], e) for e in ends):
            first = first[::-1]
    out, end = [first], first[-1]
    for p in parts[1:]:
        if math.dist(p[-1], end) < math.dist(p[0], end):
            p = p[::-1]
        out.append(p[1:] if math.dist(p[0], end) < 1e-6 else p)
        end = p[-1]
    return np.concatenate(out)


def _stop(member: dict, tags: dict) -> bool:
    """Whether a relation's member is one of its stops: a node in a stop or platform role, or in none when its own tags
    say it is a stop (STOP_NODES, a ferry terminal)."""
    if member["type"] != "node":
        return False
    role = member.get("role", "")
    return role.startswith(NOT_ROUTE) or (role == "" and (tags.get("public_transport") in STOP_NODES
                                                          or tags.get("amenity") == "ferry_terminal"))


def lines(elements: list[dict], project=lonlat_to_3011) -> list[dict]:
    """The chosen routes as lines: {id, kind, ref, name, group, coords (local metres), tags, stops}, in element order.
    `group` is what makes two of them one route (the line, or a ship's line, ship_line, which is also its name; the
    terminal is added later). `stops`: a relation's named stop nodes (_stop) as [(name, (x, z))], in member order; the
    query outputs the nodes with their tags, and a node it did not (an older cache) gives no name."""
    out, in_relation = [], set()
    rels = [e for e in elements if e["type"] == "relation"]
    nodes = {e["id"]: e.get("tags", {}) for e in elements if e["type"] == "node"}
    for r in rels:
        in_relation.update(m["ref"] for m in r.get("members", []) if m["type"] == "way")

    def stops(members):
        found = [(nodes.get(m["ref"], {}).get("name", "").strip(), m) for m in members
                 if _stop(m, nodes.get(m["ref"], {})) and m.get("lat") is not None and m.get("lon") is not None]
        found = [(n, m) for n, m in found if n]
        return [(n, tuple(_local([m], project)[0])) for n, m in found]
    candidates = [(f"r{r['id']}", r.get("tags", {}),
                   [m.get("geometry") or [] for m in r.get("members", [])
                    if m["type"] == "way" and not m.get("role", "").startswith(NOT_ROUTE)],
                   stops(r.get("members", []))) for r in rels]
    candidates += [(f"w{w['id']}", w.get("tags", {}), [w.get("geometry") or []], [])
                   for w in elements if w["type"] == "way" and w["id"] not in in_relation]
    for rid, tags, geoms, named in candidates:
        k = kind(tags)
        if k is None:
            continue
        coords = chain([_local(g, project) for g in geoms])
        if len(coords) < 2:
            continue
        ref, name = ("", ship_line(tags)) if k == "ship" else (line_ref(tags), ferry_name(tags))
        out.append({"id": rid, "kind": k, "ref": ref, "name": name, "group": ref or name, "coords": coords,
                    "tags": tags, "stops": named})
    return out


# ---- what a boat's tooltip says ------------------------------------------------------------------------------------

def _names(value) -> list[str]:
    """A tag's names, trimmed: "A;B" is two."""
    return [n.strip() for n in str(value or "").split(";") if n.strip()]


def places(tags: dict) -> list[str]:
    """A route's places from its tags, in its direction: from, via and to; else its name's "X: A - B - C" (or
    "A - B", "A => B"), the head before a colon left out; [] when that gives fewer than two."""
    if _names(tags.get("from")) and _names(tags.get("to")):
        return _names(tags.get("from")) + _names(tags.get("via")) + _names(tags.get("to"))
    raw = tags.get("name", "")
    _, colon, rest = raw.partition(":")
    parts = [p.strip() for p in LEGS.split(rest if colon else raw) if p.strip()]
    return parts if len(parts) >= 2 else []


def along(line, pts) -> list[float]:
    """Each point's place along a line, metres from its start, in the order given. Each is looked for on the line
    after the point before it, so a loop's last stop lands at its end and a pier called at twice is passed twice; and
    anywhere on the line when it lies more than STOP_SLACK_M further from that part than from the whole line (a
    relation that lists its stops out of order)."""
    ls = shapely.LineString(np.asarray(line, dtype=float))
    out, prev = [], 0.0
    for p in pts:
        pt = shapely.Point(p)
        here = ls.project(pt)
        if ls.length - prev > 1e-6:
            rest = shapely.ops.substring(ls, prev, ls.length)
            if rest.geom_type == "LineString" and rest.distance(pt) <= ls.distance(pt) + STOP_SLACK_M:
                here = prev + rest.project(pt)
        out.append(float(here))
        prev = here
    return out


def stop_names(line, stops: list) -> list[str]:
    """A line's stops [(name, (x, z))] as names in order along it (along; a tie keeps the relation's order), a name
    straight after itself once (a stop and its platform, a stop listed twice). [] for fewer than two."""
    if len(line) < 2 or not stops:
        return []
    at = along(line, [xy for _, xy in stops])
    out = []
    for _, name in sorted(zip(at, (n for n, _ in stops)), key=lambda t: t[0]):
        if not out or out[-1] != name:
            out.append(name)
    return out if len(out) >= 2 else []


def _by_count(names: list[str]) -> list[str]:
    """Distinct names, the most often named first, then the first named."""
    count = {}
    for n in names:
        count[n] = count.get(n, 0) + 1
    return sorted(count, key=lambda n: -count[n])                  # stable: a tie keeps the first named first


def ship_ports(legs: list[tuple[list[str], bool]]) -> tuple[str, list[dict]]:
    """A ship route's home port and its destinations, from its relations' places (places) and, for each, whether its
    terminal in the map is at the relation's start (it leaves from here): home is that end, the destination the other
    and the vias between, from home outwards. ("", []) when no relation names two places. The destinations as {to,
    via}, the most sailed first (_by_count), each with its vias the same way."""
    homes, dests, vias = [], [], {}
    for names, leaves in legs:
        if len(names) < 2:
            continue
        names = names if leaves else names[::-1]
        homes.append(names[0])
        dests.append(names[-1])
        vias.setdefault(names[-1], []).extend(names[1:-1])
    if not dests:
        return "", []
    return _by_count(homes)[0], [{"to": d, "via": _by_count(vias[d])} for d in _by_count(dests)]


def _leaves(line, terminal) -> bool:
    """Whether a relation's terminal in the map is in the first half of its line: the relation leaves from it."""
    ls = shapely.LineString(np.asarray(line, dtype=float))
    return ls.project(shapely.Point(terminal)) <= ls.length / 2


# ---- on the water --------------------------------------------------------------------------------------------------

def load_base(folder: Path) -> tuple:
    """(water, land) of a version folder (s04_base's water.bin.gz and land.bin.gz) as prepared shapely geometries in the
    local frame. Land is the kommun minus the water, so a point on neither is off the map."""
    def polys(name):
        rings = unpack(gzip.decompress((Path(folder) / name).read_bytes()))
        g = shapely.union_all([shapely.Polygon(p[0], p[1:]) for p in rings if len(p[0]) >= 3])
        shapely.prepare(g)
        return g
    return polys("water.bin.gz"), polys("land.bin.gz")


def length(coords) -> float:
    c = np.asarray(coords, dtype=float)
    return float(np.hypot(*np.diff(c, axis=0).T).sum()) if len(c) > 1 else 0.0


def densify(coords: np.ndarray, box: tuple, step: float = STEP_M) -> np.ndarray:
    """A point every `step` metres along the segments that come into `box` (x0, z0, x1, z1); far away (a Baltic
    route's 300 km to Turku) the line keeps its own vertices."""
    out = [coords[:1]]
    x0, z0, x1, z1 = box
    for p, q in zip(coords[:-1], coords[1:]):
        near = min(p[0], q[0]) <= x1 and max(p[0], q[0]) >= x0 and min(p[1], q[1]) <= z1 and max(p[1], q[1]) >= z0
        n = max(1, math.ceil(math.dist(p, q) / step)) if near else 1
        out.append(p + (q - p) * (np.arange(1, n + 1)[:, None] / n))
    return np.concatenate(out)


def the_map(water, land):
    """The map's ground, water and land together (the kommun), grown by ON_WATER_M so that a step along its edge counts
    as on it, and prepared: a path must not leave it."""
    g = shapely.union(water, land).buffer(ON_WATER_M)
    shapely.prepare(g)
    return g


def on_map(p, q, ground) -> bool:
    """True when the straight step p -> q stays on the map (`ground`, the_map)."""
    return bool(shapely.covered_by(shapely.LineString([p, q]), ground))


def steps_on(path, ground) -> np.ndarray:
    """For each step of a path, whether it stays on `ground` (on_map for all of them at once)."""
    c = np.asarray(path, dtype=float)
    if len(c) < 2:
        return np.zeros(0, bool)
    return shapely.covered_by(shapely.linestrings(np.stack([c[:-1], c[1:]], axis=1)), ground)


class Edge:
    """The water's edge as rings with their vertices' positions along them, for going along it (by_the_edge). The
    rings are found at the first step that needs them."""

    def __init__(self, water):
        self.water, self.rings, self.at = water, None, {}

    def between(self, p, q) -> np.ndarray:
        """The edge's vertices from p to q (both on one ring), the shorter way round; none when they are on different
        rings, or the way round is far longer than the step (DETOUR)."""
        if self.rings is None:
            self.rings = [ring for poly in shapely.get_parts(self.water) for ring in (poly.exterior, *poly.interiors)]
            self.tree = shapely.STRtree(self.rings)
        a, b = shapely.Point(p), shapely.Point(q)
        k = int(self.tree.query_nearest(a)[0])
        ring = self.rings[k]
        if ring.distance(a) > ON_WATER_M or ring.distance(b) > ON_WATER_M:
            return np.zeros((0, 2))
        if k not in self.at:
            xy = np.asarray(ring.coords)[:-1]
            self.at[k] = (xy, np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
        xy, pos = self.at[k]
        total, sa, sb = ring.length, ring.project(a), ring.project(b)
        ahead, back = (pos - sa) % total, (sa - pos) % total
        forward = (sb - sa) % total
        if min(forward, total - forward) > DETOUR * math.dist(p, q) + STEP_M:
            return np.zeros((0, 2))
        if forward <= total - forward:
            pick = np.flatnonzero((ahead > 0) & (ahead < forward))
            return xy[pick[np.argsort(ahead[pick])]]
        pick = np.flatnonzero((back > 0) & (back < total - forward))
        return xy[pick[np.argsort(back[pick])]]


def by_the_edge(c: np.ndarray, moved: np.ndarray, ground, edge: Edge) -> list[tuple[np.ndarray, np.ndarray]]:
    """Points moved onto the map's edge either side of one of its corners are a step apart straight across the corner,
    off the map: such a step goes along the edge instead (Edge.between; the edge's vertices count as moved). Where there
    is no such way (the two points are on different rings of the water, or the way round is far longer than the step),
    the stretch is cut there, as where a lane leaves the map. The pieces, each (coords, moved), in order."""
    bad = set(np.flatnonzero(~steps_on(c, ground)).tolist())
    if not bad:
        return [(c, moved)]
    pieces, out, mv = [], [c[0]], [bool(moved[0])]
    for i in range(1, len(c)):
        if i - 1 in bad:
            via = edge.between(c[i - 1], c[i])
            if not len(via):
                pieces.append((np.array(out), np.array(mv)))
                out, mv = [], []
            out += list(via)
            mv += [True] * len(via)
        out.append(c[i])
        mv.append(bool(moved[i]))
    pieces.append((np.array(out), np.array(mv)))
    return pieces


def turns_back(c: np.ndarray, moved: np.ndarray) -> int:
    """The last index of a stretch to keep at its edge end. Points moved onto the edge's nearest spot follow it while
    the lane leaves the map, and walk back along it where the lane then turns away (to a pier in another kommun:
    Pendelbåt 80's in Nacka, E/S Movitz's at Solna strand), so the last run of moved points ends at its first
    step that turns more than a right angle. The last index when it never does, or when no point stayed where it was."""
    n = len(c)
    if n < 3 or not moved[-1] or moved.all():
        return n - 1
    s = n - 1 - int(np.argmin(moved[::-1]))              # the last point not moved
    d = np.diff(c[s:], axis=0)
    back = np.flatnonzero((d[:-1] * d[1:]).sum(axis=1) < 0)
    return s + 1 + int(back[0]) if len(back) else n - 1


def on_water(coords: np.ndarray, water, land, ground=None, snap: float = SNAP_M) -> dict | None:
    """The line's best stretch on the map's water: {coords, ends: [first, last], length, moved (per point: moved onto
    the edge)}, or None when it never meets it. The line is cut into STEP_M steps, and each point is on water, on land
    or off the map (past the kommun's edge). A point off the map within `snap` of the water is moved onto its edge,
    where the kommun's border runs along a lane: at an edge end the moved points stop where they turn back
    (turns_back), and by_the_edge keeps the stretch on the map. Stretches of water are joined across land up to
    BRIDGE_M long. An end is a "pier" where the stretch meets land or the route itself ends on water, an "edge" where it
    goes off the map (a route that ends off the map, at another kommun's pier, ends at the edge too). The best stretch
    is the longest one with a pier, else the longest."""
    ground = the_map(water, land) if ground is None else ground
    x0, z0, x1, z1 = ground.bounds
    m = snap + STEP_M
    c = densify(np.asarray(coords, dtype=float), (x0 - m, z0 - m, x1 + m, z1 + m))
    pts = shapely.points(c)
    wet = shapely.intersects(pts, water)
    dry = ~wet & shapely.intersects(pts, land)
    off = ~wet & ~dry
    moved = np.zeros(len(c), bool)
    near = np.flatnonzero(off)
    near = near[shapely.dwithin(pts[near], water, snap)] if len(near) else near
    if len(near):
        c[near] = shapely.get_coordinates(shapely.shortest_line(pts[near], water)).reshape(-1, 2, 2)[:, 1]
        moved[near], wet[near], off[near] = True, True, False

    runs, i, n = [], 0, len(c)
    while i < n:                                          # [first, last] index of each stretch of water
        if not wet[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and wet[j + 1]:
            j += 1
        runs.append([i, j])
        i = j + 1
    joined = []
    for r in runs:
        if joined and not off[joined[-1][1] + 1:r[0]].any() and length(c[joined[-1][1]:r[0] + 1]) <= BRIDGE_M:
            joined[-1][1] = r[1]
        else:
            joined.append(r)

    def end(k: int, outward: int) -> str:
        beyond = k + outward
        if beyond < 0 or beyond >= n:                     # the route's own end
            return "edge" if moved[k] else "pier"
        return "pier" if dry[beyond] else "edge"
    found, edge = [], Edge(water)
    for a, b in joined:
        sel = wet[a:b + 1]                                # a bridged gap's land points go: the boat crosses straight
        keep, mk = c[a:b + 1][sel], moved[a:b + 1][sel]
        one = np.r_[True, np.hypot(*np.diff(keep, axis=0).T) > 1e-6]      # points moved onto one spot are one
        keep, mk = keep[one], mk[one]
        ends = [end(a, -1), end(b, 1)]
        lo = len(keep) - 1 - turns_back(keep[::-1], mk[::-1]) if ends[0] == "edge" else 0
        hi = turns_back(keep, mk) if ends[1] == "edge" else len(keep) - 1
        pieces = by_the_edge(keep[lo:hi + 1], mk[lo:hi + 1], ground, edge)
        for k, (pc, pm) in enumerate(pieces):
            pe = [ends[0] if k == 0 else "edge", ends[1] if k == len(pieces) - 1 else "edge"]
            if length(pc) > 0:
                found.append({"coords": pc, "ends": pe, "length": length(pc), "moved": pm})
    if not found:
        return None
    return max(found, key=lambda f: ("pier" in f["ends"], f["length"]))


def off_water(path, water, tol: float = ON_WATER_M) -> int:
    """How many points of a path lie more than tol from water."""
    pts = shapely.points(np.asarray(path, dtype=float))
    return int((~shapely.dwithin(pts, water, tol)).sum())


def off_map(path, ground) -> int:
    """How many segments of a path leave the map (`ground`, the_map)."""
    return int((~steps_on(path, ground)).sum())


def _to_chord(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip((pts - a) @ ab / ab.dot(ab), 0.0, 1.0) if ab.any() else np.zeros(len(pts))
    return np.hypot(*(pts - (a + t[:, None] * ab)).T)


def simplify(coords, tol: float = SIMPLIFY_M, ground=None, moved=None, wet=None) -> list[list[float]]:
    """Douglas-Peucker as s16_metro.simplify (the end points and only original vertices kept), in 0.1 m. With `ground`
    (the_map), a chord that would leave the map is split as if it strayed too far, so a path that goes round one of
    the map's corners does not cut across it. With `moved` (per point: moved onto the map's edge, on_water), such a
    point may be EDGE_SIMPLIFY_M off a chord, and a chord past one must keep to the water (`wet`, the_water): the moved
    points follow every corner of the kommun's jagged border, where the lane beside them runs straight."""
    c = np.asarray(coords, dtype=float)
    m = np.zeros(len(c), bool) if moved is None else np.asarray(moved, bool)
    room = np.where(m, EDGE_SIMPLIFY_M, tol)
    keep = np.zeros(len(c), bool)
    keep[[0, -1]] = True
    todo = [(0, len(c) - 1)]
    while todo:
        a, b = todo.pop()
        if b - a < 2:
            continue
        d = _to_chord(c[a + 1:b], c[a], c[b]) / room[a + 1:b]
        k = int(np.argmax(d))
        if (d[k] > 1 or (ground is not None and not on_map(c[a], c[b], ground))
                or (wet is not None and m[a + 1:b].any() and not on_map(c[a], c[b], wet))):
            keep[a + 1 + k] = True
            todo += [(a, a + 1 + k), (a + 1 + k, b)]
    return [[round(float(x), 1), round(float(z), 1)] for x, z in c[keep]]


def the_water(water):
    """The water grown by ON_WATER_M and prepared: where a chord past points moved onto the edge must keep (simplify)."""
    g = shapely.buffer(water, ON_WATER_M)
    shapely.prepare(g)
    return g


# ---- one route per line --------------------------------------------------------------------------------------------

def _terminal(r: dict):
    """A ship's pier end (its terminal in the map), or None when it has none."""
    ends = [pt for pt, e in zip((r["coords"][0], r["coords"][-1]), r["ends"]) if e == "pier"]
    return ends[0] if ends else None


def routes(elements: list[dict], water, land, project=lonlat_to_3011) -> list[dict]:
    """The routes for ferries.json: one per line (ferries) or per ship line and terminal (ships), each the best of its
    relations' stretches on water (on_water's choice, a ship's lane moved onto the edge from up to SHIP_SNAP_M out),
    the path starting at its pier when only one end is a pier. A city boat's route has its best relation's stops in
    the path's direction (stop_names, else places) when it has two; a ship's its home port and destinations from all
    its relations (ship_ports) and its operator, when OSM has them."""
    groups: dict = {}
    ground, wet = the_map(water, land), the_water(water)
    for ln in lines(elements, project):
        w = on_water(ln["coords"], water, land, ground, SHIP_SNAP_M if ln["kind"] == "ship" else SNAP_M)
        if w is None:
            continue
        # the stops along the whole line, before its coords become the stretch on the water (in the same direction)
        r = {**ln, **w, "line": ln["coords"], "names": stop_names(ln["coords"], ln["stops"]) or places(ln["tags"])}
        key = (r["kind"], r["group"])
        if r["kind"] == "ship":
            t = _terminal(r)
            if t is None:                                   # passes the map without calling at it
                continue
            key = key + (next((k[2] for k in groups if k[:2] == key and math.dist(k[2], t) <= TERMINAL_M), tuple(t)),)
        groups.setdefault(key, []).append(r)
    out = []
    for members in groups.values():
        best = max(members, key=lambda r: ("pier" in r["ends"], round(r["length"], 1), -int(r["id"][1:])))
        coords, ends, moved, names = best["coords"], list(best["ends"]), best["moved"], best["names"]
        if ends == ["edge", "pier"]:
            coords, ends, moved, names = coords[::-1], ends[::-1], moved[::-1], names[::-1]
        route = {"id": best["id"], "ref": best["ref"], "name": best["name"], "kind": best["kind"], "ends": ends,
                 "path": simplify(coords, ground=ground, moved=moved, wet=wet)}
        if best["kind"] == "ferry" and names:
            route["stops"] = names
        if best["kind"] == "ship":
            # every relation of the lane, the ports from their tags (their stops are named after the terminals)
            home, dests = ship_ports([(places(r["tags"]), _leaves(r["line"], _terminal(r))) for r in members])
            if dests:
                route.update(home=home, dests=dests)
            operator = next((r["tags"]["operator"].strip() for r in [best, *members]
                             if r["tags"].get("operator", "").strip()), "")
            if operator:
                route["operator"] = operator
        out.append(route)
    return sorted(out, key=lambda r: (r["kind"] != "ferry", r["name"], r["id"]))


def layer(elements: list[dict], water, land, project=lonlat_to_3011) -> dict:
    """ferries.json: {version, routes}."""
    return {"version": VERSION, "routes": routes(elements, water, land, project)}


def fetch(refresh: bool = False) -> list[dict]:
    """The Overpass answer's elements: the cache when it matches the query, else one query (raises SystemExit when
    Overpass cannot be reached and there is no cache)."""
    post_query_retrying(OVERPASS, {"data": QUERY.read_text(encoding="utf-8")}, RAW, retries=RETRIES,
                        backoff_s=BACKOFF_S, sleep=sleep, refresh=refresh, check=overpass_error)
    return json.loads(RAW.read_text(encoding="utf-8"))["elements"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="ferries", description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True, help="a version folder with water.bin.gz and land.bin.gz")
    ap.add_argument("--dest", type=Path, help="write ferries.json here")
    ap.add_argument("--refresh", action="store_true", help="query Overpass again even when the cache matches")
    args = ap.parse_args([] if argv is None else argv)
    cfg = args.base / f"{city.SLUG}.json"
    if cfg.exists() and json.loads(cfg.read_text(encoding="utf-8")).get("origin") != list(city.ORIGIN):
        raise SystemExit(f"{cfg}: its origin is not city.ORIGIN, so its water is in another frame")
    water, land = load_base(args.base)
    out, ground = layer(fetch(refresh=args.refresh), water, land), the_map(water, land)
    for r in out["routes"]:
        print(f"{r['id']:>11} {r['kind']:5} {r['ref'] or '-':>4} {r['name'][:28]:28} {'/'.join(r['ends']):10} "
              f"{len(r['path']):4} pts {length(r['path']):7.0f} m  off water: {off_water(r['path'], water)}  "
              f"off map: {off_map(r['path'], ground)}")
        if r.get("stops"):
            print(f"{'':12}stops: {' - '.join(r['stops'])}")
        for d in r.get("dests", []):
            print(f"{'':12}{r['home']} => {' / '.join(d['via']) or '-'} => {d['to']}"
                  f"{'  (' + r['operator'] + ')' if r.get('operator') else ''}")
    if args.dest:
        io.write_json(args.dest, out)
        print(f"ferries: {len(out['routes'])} routes -> {args.dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
