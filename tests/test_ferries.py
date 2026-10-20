"""Ferry routes (pipeline/ferries.py): which boats, their lines, and their paths on a hand-made map's water. No network:
the elements are written here, in Overpass's shape, with local metres for coordinates (see `project`)."""
import json

import numpy as np
import pytest
import shapely
from shapely.geometry import box

from pipeline import city, ferries, io
from pipeline.s00_fetch_osm import overpass_error
from pipeline.s04_base import pack

O_E, O_N = city.ORIGIN


def project(lon, lat):
    """The elements below give local metres as lon (x) and lat (z): this undoes city.to_local."""
    return np.asarray(lon, dtype=float) + O_E, O_N - np.asarray(lat, dtype=float)


def geom(*pts):
    return [None if p is None else {"lon": p[0], "lat": p[1]} for p in pts]


def rel(i, tags, *ways, roles=None):
    """A route relation: a stop node, then its ways (role "" unless `roles` says otherwise)."""
    members = [{"type": "node", "ref": 9000 + i, "role": "stop", "lon": ways[0][0][0], "lat": ways[0][0][1]}]
    members += [{"type": "way", "ref": 100 * i + k, "role": (roles or [""] * len(ways))[k], "geometry": geom(*w)}
                for k, w in enumerate(ways)]
    return {"type": "relation", "id": i, "tags": {"type": "route", "route": "ferry", **tags}, "members": members}


def way(i, tags, *pts):
    return {"type": "way", "id": i, "tags": {"route": "ferry", **tags}, "geometry": geom(*pts)}


def base(water, ground):
    """(water, land) as load_base gives them: land is the map minus the water."""
    land = ground.difference(water)
    shapely.prepare(water)
    shapely.prepare(land)
    return water, land


# A channel across the map (z -100..100), quays at x = -900, a 20 m bridge at x = -10..10, and the map's east edge
# at x = 2000, where the water goes on.
GROUND = box(-1000, -500, 2000, 500)
CHANNEL = base(shapely.union(box(-900, -100, -10, 100), box(10, -100, 2000, 100)), GROUND)

SL82 = {"name": "Djurgårdsfärjan 82: Slussen - Djurgården", "ref": "82", "network": "SL"}
VIKING = {"name": "Viking Line: Stockholm => Mariehamn => Turku", "operator": "Viking Line"}


# ---- which boats ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("tags", "kind", "ref", "name"), [
    (SL82, "ferry", "82", "Djurgårdsfärjan 82"),
    ({"name": "Pendelbåt 84: Ålstäcket => Strömkajen", "network": "SL"}, "ferry", "84", "Pendelbåt 84"),
    ({"name": "Pendelbåt 80X", "network": "SL"}, "ferry", "80X", "Pendelbåt 80X"),
    ({"name": "Båt 89: Klara Mälarstrand - Tappström", "ref": "89", "network": "SL"}, "ferry", "89", "Båt 89"),
    ({"ref": "Cityline", "operator": "Ressel rederi", "network": "Ressel rederi"}, "ferry", "", "Cityline"),
    ({"name": "Sjöstadstrafiken", "ref": "Sjöstadstrafiken", "operator": "Ressel Rederi"}, "ferry", "",
     "Sjöstadstrafiken"),
    ({"name": "Båt: Riddarholmen - Solna Strand", "operator": "E/S Movitz", "network": "E/S Movitz"}, "ferry", "",
     "Riddarholmen - Solna Strand"),
    (VIKING, "ship", "", "Viking Line"),
    ({"name": "Silja Line: Helsinki => Mariehamn => Stockholm", "operator": "Silja Line"}, "ship", "", "Silja Line"),
    ({"name": "Tallink: Tallinn => Mariehamn => Stockholm", "operator": "Tallink"}, "ship", "", "Tallink"),
])
def test_the_chosen_boats(tags, kind, ref, name):
    assert ferries.kind(tags) == kind
    assert ferries.clean_name(tags) == name
    if kind == "ferry":
        assert ferries.line_ref(tags) == ref


@pytest.mark.parametrize("tags", [
    {"name": "Färja 4: Rindö - Vaxholm - Stockholm (Strömkajen)", "ref": "4", "network": "Waxholmsbolaget"},
    {"name": "Färja 82: Stockholm - Vaxholm", "ref": "82", "network": "Waxholmsbolaget"},   # SL's number, not SL's boat
    {"name": "Stora kanalturen till Gustavsberg", "ref": "Grand Canal Cruise", "operator": "Strömma Kanalbolag"},
    {"name": "Djurgården Runt", "ref": "Royal Canal Tour", "operator": "Strömma Kanalbolag"},
    {"name": "Cinderella Stockholm ↔ Sandhamn", "operator": "Strömma Kanalbolag"},
    {"name": "Hop-On Hop-Off", "operator": "Royal Sightseeiing;Stockolm Sightseeing"},
    {"name": "Strömma Kanalbolaget s/s Stockholm"}, {"name": "Ångfartyget Mariefred"},
    {"name": "European route E 20", "ref": "E 20", "network": "e-road", "motor_vehicle": "yes"},
    {"name": "Pendelbåt 83: Nybroplan - Ropsten", "network": "SL"},                          # not one of the lines
    {},
])
def test_every_other_boat_is_left_out(tags):
    assert ferries.kind(tags) is None


@pytest.mark.parametrize(("tags", "line"), [
    (VIKING, "Viking Line"),
    ({"name": "Viking Line Stockholm – Helsinki"}, "Viking Line"),                 # no colon
    ({"name": "M/S Gabriella", "operator": "Viking Line"}, "Viking Line"),         # named after the ship
    ({"name": "Silja Line: Stockholm => Helsinki", "operator": "Tallink Silja"}, "Silja Line"),   # the name first
    ({"name": "Silja Serenade", "operator": "Tallink Silja Oy"}, "Tallink"),
    (SL82, None),
])
def test_a_ship_is_known_by_its_line(tags, line):
    assert ferries.ship_line(tags) == line
    assert ferries.kind(tags) == ("ship" if line else "ferry")


def test_names_lose_their_direction():
    assert ferries.clean_name({"name": "Cinderella Stockholm ↔ Sandhamn"}) == "Cinderella Stockholm – Sandhamn"
    assert ferries.clean_name({"name": "A => B -> C"}) == "A – B – C"
    assert ferries.clean_name({}) == ""
    assert ferries.line_ref({"ref": "Cityline", "name": "Cityline"}) == ""


# ---- lines ---------------------------------------------------------------------------------------------------------

def test_chain_turns_each_way_to_follow_on():
    a, b, c = np.array([[10, 0], [0, 0]]), np.array([[20, 0], [10, 0]]), np.array([[20, 0], [30, 5]])
    assert ferries.chain([a, b, c]).tolist() == [[0, 0], [10, 0], [20, 0], [30, 5]]
    gap = ferries.chain([np.array([[0, 0], [10, 0]]), np.array([[25, 0], [15, 0]])])
    assert gap.tolist() == [[0, 0], [10, 0], [15, 0], [25, 0]]                # a gap is crossed straight
    assert ferries.chain([np.zeros((1, 2))]).shape == (0, 2)


def test_lines_take_the_route_ways_of_the_chosen_relations():
    elements = [
        rel(1, SL82, [(0, 0), (100, 0)], [(150, 0), (100, 0)], [(0, 50), (0, 60)], roles=["", "route", "platform"]),
        rel(2, {"name": "Färja 4: Rindö - Stockholm", "ref": "4", "network": "Waxholmsbolaget"}, [(0, 0), (9, 9)]),
        way(101, {"name": "Djurgårdsfärjan 82", "ref": "82"}, (0, 0), (100, 0)),            # in relation 1
        way(7, {"name": "Sjöstadstrafiken"}, (5, 5), (6, 6), None, (7, 7)),               # in no relation; a null node
        way(8, {"name": "Hop-On Hop-Off"}, (0, 0), (1, 1)),
        rel(3, VIKING, [(0, 0), (500, 0)]),
    ]
    got = {ln["id"]: ln for ln in ferries.lines(elements, project)}
    assert sorted(got) == ["r1", "r3", "w7"]
    assert np.allclose(got["r1"]["coords"], [[0, 0], [100, 0], [150, 0]])      # the platform way is not sailed
    assert (got["r1"]["kind"], got["r1"]["ref"], got["r1"]["name"], got["r1"]["group"]) == \
        ("ferry", "82", "Djurgårdsfärjan 82", "82")
    assert np.allclose(got["w7"]["coords"], [[5, 5], [6, 6], [7, 7]]) and got["w7"]["group"] == "Sjöstadstrafiken"
    assert (got["r3"]["kind"], got["r3"]["ref"], got["r3"]["group"]) == ("ship", "", "Viking Line")


def test_lines_project_wgs84_to_the_local_frame():
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(city.CRS, 4326, always_xy=True).transform(O_E + 100.0, O_N - 50.0)
    (ln,) = ferries.lines([way(5, {"name": "Cityline"}, (lon, lat), (lon, lat + 0.001))])
    assert np.allclose(ln["coords"][0], [100.0, 50.0], atol=0.01)              # x east, z south
    assert ln["coords"][1][1] < 50.0


# ---- on the water --------------------------------------------------------------------------------------------------

def test_a_route_sails_under_a_bridge_from_pier_to_pier():
    water, land = CHANNEL
    w = ferries.on_water(np.array([[-950.0, 0], [1500, 0]]), water, land)
    assert w["ends"] == ["pier", "pier"]                       # it leaves a quay, and ends on water: its own end
    xs = w["coords"][:, 0]
    assert xs[0] == pytest.approx(-900) and xs[-1] == 1500
    assert not ((xs > -10) & (xs < 10)).any()                  # the bridge's land points go; the boat crosses straight
    assert ferries.off_water(w["coords"], water) == 0
    assert w["length"] == pytest.approx(2400)


def test_land_wider_than_a_bridge_ends_the_stretch():
    water, land = base(shapely.union(box(-900, -100, -100, 100), box(100, -100, 2000, 100)), GROUND)
    w = ferries.on_water(np.array([[-950.0, 0], [1500, 0]]), water, land)
    assert w["ends"] == ["pier", "pier"] and w["coords"][0][0] == pytest.approx(100)   # the longer stretch, east


def test_a_lane_that_leaves_the_map_ends_at_its_edge():
    water, land = CHANNEL
    w = ferries.on_water(np.array([[-950.0, 0], [2500, 0]]), water, land)
    assert w["ends"] == ["pier", "edge"]
    assert w["coords"][-1].tolist() == [2000, 0]               # the steps within SNAP_M past the edge are moved onto it
    assert len(w["coords"]) == len(np.unique(w["coords"], axis=0))
    assert ferries.on_water(np.array([[-950.0, 400], [1500, 400]]), water, land) is None   # all on land


def test_a_route_that_ends_off_the_map_ends_at_the_edge():
    water, land = CHANNEL
    w = ferries.on_water(np.array([[0.0, 50], [2100, 50]]), water, land)       # another kommun's pier, 100 m past
    assert w["ends"] == ["pier", "edge"]                       # starts on the bridge (land), ends moved: not a pier


def test_a_lane_just_outside_the_map_is_drawn_along_its_edge():
    water, land = base(box(0, 0, 1000, 100), box(0, 0, 1000, 500))            # off the map below z = 0
    lane = np.array([[50.0, 150], [50, 50], [100, -50], [900, -50], [950, 50], [950, 150]])
    w = ferries.on_water(lane, water, land)
    assert w["ends"] == ["pier", "pier"]
    assert w["coords"][:, 1].min() == pytest.approx(0) and w["coords"][:, 1].max() <= 100
    assert ferries.off_water(w["coords"], water) == 0
    far = lane + [[0, 0], [0, 0], [0, -250], [0, -250], [0, 0], [0, 0]]          # 300 m out: past SNAP_M
    w = ferries.on_water(far, water, land)                     # two stretches, each from a pier to the edge
    assert sorted(w["ends"]) == ["edge", "pier"] and w["coords"][:, 1].min() >= 0


L_WATER = box(0, 0, 1000, 1000).difference(box(500, -1, 1001, 500))           # an L: off the map in the corner


def test_a_lane_moved_onto_the_edge_goes_round_its_corner():
    water, land = base(L_WATER, L_WATER)
    ground = ferries.the_map(water, land)
    w = ferries.on_water(np.array([[400.0, 300], [900, 700]]), water, land, ground)
    c = w["coords"]
    steps = shapely.linestrings(np.stack([c[:-1], c[1:]], axis=1))
    assert shapely.covered_by(steps, ground).all()             # no step across the corner, off the map
    assert np.hypot(*(c - [500, 500]).T).min() < 1             # it goes by the corner
    assert w["ends"] == ["pier", "pier"]


CORNER = shapely.union(box(0, 0, 500, 500), box(500, 500, 1000, 1000))     # two waters that touch at one corner


def test_a_step_off_the_map_with_no_way_round_ends_the_stretch():
    # moved onto the edges of two waters that touch at a corner, two points are a step apart across ground off the
    # map, with no edge between them: the stretch is cut there, at the edge, and the longer piece is kept
    water, land = base(CORNER, shapely.union(CORNER, box(0, 500, 500, 1000)))
    ground = ferries.the_map(water, land)
    w = ferries.on_water(np.array([[400.0, 300], [900, 700]]), water, land, ground)
    assert w["ends"] == ["edge", "pier"] and w["coords"][-1].tolist() == [900, 700]
    assert w["coords"][0][1] == pytest.approx(500)                       # on the second water's edge
    assert ferries.off_map(w["coords"], ground) == 0 and ferries.off_water(w["coords"], water) == 0
    assert len(w["moved"]) == len(w["coords"]) and w["moved"][0] and not w["moved"][-1]


def turns(c):
    """The cosine of each turn along a path."""
    d = np.diff(np.asarray(c, dtype=float), axis=0)
    d /= np.hypot(*d.T)[:, None]
    return (d[:-1] * d[1:]).sum(axis=1)


def test_an_edge_end_stops_where_its_points_on_the_edge_would_turn_back():
    # the lane leaves the map past the water's corner at (1000, 0), then turns back west 100 m outside it, as
    # Pendelbåt 80's does for a pier in Nacka: moved onto the edge, its points would walk 100 m back along it
    water, land = base(box(0, 0, 1000, 100), box(0, 0, 1000, 500))       # off the map below z = 0 and past x = 1000
    lane = np.array([[20.0, 150], [50, 50], [900, 50], [1100, -100], [900, -100]])
    w = ferries.on_water(lane, water, land)
    assert w["ends"] == ["pier", "edge"] and w["coords"][-1].tolist() == [1000, 0]
    assert turns(w["coords"]).min() > 0                                   # no turn of more than a right angle
    w = ferries.on_water(lane[::-1], water, land)                         # the same, from its edge end
    assert w["ends"] == ["edge", "pier"] and w["coords"][0].tolist() == [1000, 0]
    away = np.array([[50.0, 150], [50, 50], [100, -50], [1300, -50]])      # one that never turns back keeps its run
    w = ferries.on_water(away, water, land)
    assert w["ends"] == ["pier", "edge"] and w["coords"][-1].tolist() == [1000, 0]
    assert w["coords"][:, 1].min() == 0 and w["length"] > 1000


def test_simplify_keeps_the_map():
    water, land = base(L_WATER, L_WATER)
    pts = [[450, 200], [500, 500], [800, 550]]
    assert ferries.simplify(pts, tol=1000) == [[450, 200], [800, 550]]
    assert ferries.simplify(pts, tol=1000, ground=ferries.the_map(water, land)) == pts
    line = [[0, 0], [10, 0.01], [20, 0], [30.04, 0.05]]
    assert ferries.simplify(line) == [[0, 0], [30.0, 0.1]]   # within 4 m of the chord; 0.1 m


def test_simplify_takes_points_moved_onto_the_edge_further_on_the_water():
    water = box(0, -10, 200, 100)
    pts, moved = [[0, 0], [100, 30], [200, 0]], [False, True, False]
    assert ferries.simplify(pts) == pts                                   # 30 m off the chord: kept at 4 m
    assert ferries.simplify(pts, moved=moved, wet=ferries.the_water(water)) == [[0, 0], [200, 0]]   # 40 m when moved
    notch = ferries.the_water(water.difference(box(90, -11, 110, 5)))
    assert ferries.simplify(pts, moved=moved, wet=notch) == pts         # unless the chord leaves the water
    wide = [[0, 0], [100, 50], [200, 0]]
    assert ferries.simplify(wide, moved=moved, wet=ferries.the_water(water)) == wide   # 50 m: too far


# ---- one route per line --------------------------------------------------------------------------------------------

def elements():
    return [
        rel(1, SL82, [(-950, 0), (1500, 0)]),
        rel(2, {**SL82, "name": "Djurgårdsfärjan 82: Djurgården - Slussen"}, [(1400, 20), (-950, 20)]),
        rel(10, VIKING, [(-950, -50), (3000, -50)]),
        rel(11, {**VIKING, "name": "Viking Line: Helsinki => Mariehamn => Stockholm"}, [(3000, -60), (-950, -60)]),
        rel(12, {"name": "Silja Line: Stockholm => Turku", "operator": "Silja Line"}, [(500, 150), (500, 90),
                                                                                       (3000, 90)]),
        rel(13, {**VIKING, "name": "Viking Line: Turku => Långnäs => Stockholm"}, [(2500, 50), (1000, 50),
                                                                                    (2500, 60)]),
        rel(20, {"name": "Färja 4: Rindö - Stockholm", "ref": "4", "network": "Waxholmsbolaget"}, [(-950, 0),
                                                                                                    (1500, 0)]),
    ]


def test_one_route_per_line_and_per_ship_terminal():
    water, land = CHANNEL
    out = ferries.layer(elements(), water, land, project)
    assert out["version"] == ferries.VERSION == 1
    routes = out["routes"]
    assert [(r["id"], r["kind"], r["name"]) for r in routes] == [
        ("r1", "ferry", "Djurgårdsfärjan 82"),          # both directions: one route, the longer
        ("r12", "ship", "Silja Line"),                  # another ship line, from its own terminal
        ("r10", "ship", "Viking Line")]                 # two relations from one terminal; r13 never calls at the map
    by = {r["id"]: r for r in routes}
    assert by["r1"]["ref"] == "82" and by["r1"]["ends"] == ["pier", "pier"]
    assert by["r10"]["ref"] == "" and by["r10"]["ends"] == ["pier", "edge"]
    assert by["r10"]["path"][0] == [-900.0, -50.0] and by["r10"]["path"][-1] == [2000.0, -50.0]
    assert by["r12"]["ends"] == ["pier", "edge"] and by["r12"]["path"][0] == [500.0, 100.0]
    assert set(routes[0]) == {"id", "ref", "name", "kind", "ends", "path"}
    assert all(v == round(v, 1) for r in routes for p in r["path"] for v in p)


def test_a_ship_line_has_one_route_per_terminal():
    # a Viking Line relation from another quay, 1.5 km from the first one's: a route of its own
    water, land = CHANNEL
    far = rel(14, {**VIKING, "name": "Viking Line: Stockholm => Helsinki"}, [(600, 150), (600, 90), (3000, 90)])
    vikings = [r for r in ferries.routes([*elements(), far], water, land, project) if r["name"] == "Viking Line"]
    assert [(r["id"], r["ends"], r["path"][0]) for r in vikings] == [
        ("r10", ["pier", "edge"], [-900.0, -50.0]), ("r14", ["pier", "edge"], [600.0, 100.0])]


def test_a_ships_relations_are_one_route_whatever_their_names():
    # OSM names a ship line's relations in more than one way: from one terminal they are one route, named after the line
    water, land = CHANNEL
    rels = [rel(10, VIKING, [(-950, -50), (3000, -50)]),
            rel(15, {"name": "M/S Gabriella", "operator": "Viking Line"}, [(-950, -40), (3000, -40)]),
            rel(16, {"name": "Viking Line Stockholm – Helsinki"}, [(3000, -30), (-950, -30)])]
    (r,) = ferries.routes(rels, water, land, project)
    assert (r["id"], r["name"], r["kind"], r["ref"]) == ("r10", "Viking Line", "ship", "")


def test_a_ships_lane_is_drawn_along_the_edge_from_further_out():
    # 180 m outside the map's water: past SNAP_M for a city boat, within SHIP_SNAP_M for a ship (as Silja Line's and
    # Tallink's lanes down Lilla Värtan)
    assert ferries.SNAP_M < 180 < ferries.SHIP_SNAP_M
    water, land = base(box(0, 0, 1000, 100), box(0, 0, 1000, 500))       # off the map below z = 0
    lane = [(50, 150), (50, 50), (100, -180), (900, -180), (950, 50), (950, 150)]
    ferry, ship = ferries.routes([rel(1, VIKING, lane), rel(2, SL82, lane)], water, land, project)
    assert (ship["kind"], ship["ends"]) == ("ship", ["pier", "pier"])    # along the edge, quay to quay
    assert ferries.length(ship["path"]) > 900 and min(z for _, z in ship["path"]) < 5      # by the edge, z = 0
    assert (ferry["kind"], ferry["ends"]) == ("ferry", ["pier", "edge"])
    assert ferries.length(ferry["path"]) < 300


def test_a_route_is_turned_to_start_at_its_pier():
    water, land = CHANNEL
    (r,) = ferries.routes([rel(11, VIKING, [(3000, -60), (-950, -60)])], water, land, project)
    assert r["ends"] == ["pier", "edge"] and r["path"][0] == [-900.0, -60.0]


def test_no_elements_no_routes():
    assert ferries.layer([], *CHANNEL) == {"version": 1, "routes": []}


# ---- input -------------------------------------------------------------------------------------------------------

def test_the_query_asks_for_ferry_routes_in_the_kommun_with_geometry():
    q = ferries.QUERY.read_text(encoding="utf-8")
    assert f'area["admin_level"="7"]["ref:scb"="{city.KOMMUN}"]->.k;' in q
    assert 'relation["route"="ferry"](area.k)' in q and 'way["route"="ferry"](area.k)' in q
    assert "out body geom;" in q


def test_fetch_goes_through_the_shared_query_policy(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake(endpoints, data, dest, **kw):
        seen.update(endpoints=endpoints, data=data, dest=dest, **kw)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({"elements": [way(1, {"name": "Cityline"}, (0, 0), (1, 1))]}), encoding="utf-8")
        return {}

    monkeypatch.setattr(ferries, "post_query_retrying", fake)
    assert ferries.fetch()[0]["id"] == 1
    assert seen["endpoints"] == ferries.OVERPASS and seen["dest"] == ferries.RAW
    assert seen["data"] == {"data": ferries.QUERY.read_text(encoding="utf-8")}
    assert seen["check"] is overpass_error and seen["retries"] == ferries.RETRIES and seen["refresh"] is False
    assert seen["sleep"] is ferries.sleep


def to_3011(g):
    return shapely.transform(g, lambda c: np.c_[c[:, 0] + O_E, O_N - c[:, 1]])


def write_base(folder, water, ground):
    land = ground.difference(water)
    io.write_gz(folder / "water.bin.gz", pack(shapely.get_parts(to_3011(water))))
    io.write_gz(folder / "land.bin.gz", pack(shapely.get_parts(to_3011(land))))


def test_load_base_reads_s04_bases_files(tmp_path):
    water = CHANNEL[0]
    write_base(tmp_path, water, GROUND)
    w, land = ferries.load_base(tmp_path)
    assert w.area == pytest.approx(water.area, abs=1) and land.area == pytest.approx(GROUND.area - water.area, abs=1)
    assert w.intersects(shapely.Point(500, 0)) and not w.intersects(shapely.Point(0, 0))      # the bridge is land


def test_the_command_line_reads_a_version_folder_and_writes_where_it_is_told(tmp_path, monkeypatch, capsys):
    write_base(tmp_path, CHANNEL[0], GROUND)
    real = ferries.lines
    monkeypatch.setattr(ferries, "lines", lambda els, project_=None: real(els, project))
    monkeypatch.setattr(ferries, "fetch", lambda refresh=False: elements())
    (tmp_path / f"{city.SLUG}.json").write_text(json.dumps({"origin": list(city.ORIGIN)}), encoding="utf-8")
    ferries.main(["--base", str(tmp_path), "--dest", str(tmp_path / "dev" / "ferries.json")])
    printed = capsys.readouterr().out
    assert "Djurgårdsfärjan 82" in printed and "off water: 0" in printed and "3 routes" in printed
    assert len(json.loads((tmp_path / "dev" / "ferries.json").read_text(encoding="utf-8"))["routes"]) == 3
    (tmp_path / f"{city.SLUG}.json").write_text(json.dumps({"origin": [0, 0]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="another frame"):
        ferries.main(["--base", str(tmp_path)])
