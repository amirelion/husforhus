"""OSM building:levels and their match to footprints. No network: Overpass answers are written here."""
import json

import pytest
import shapely
from pyproj import Transformer

from pipeline import city, osm_buildings as ob
from tests import synth

TO_WGS84 = Transformer.from_crs(city.CRS, 4326, always_xy=True)


def latlon(coords):
    return [{"lat": lat, "lon": lon} for lon, lat in (TO_WGS84.transform(x, y) for x, y in coords)]


def way(i, poly, levels="3", **tags):
    return {"type": "way", "id": i, "tags": {"building": "yes", "building:levels": levels, **tags},
            "geometry": latlon(poly.exterior.coords)}


def write(folder, name, elements):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps({"elements": elements}), encoding="utf-8")


@pytest.mark.parametrize(("raw", "n"), [("3", 3), ("2.5", 3), ("2,4", 2), ("0", 0), ("-1", 0), ("tre", 0),
                                        ("61", 0), ("60", 60), (None, 0), (" 4 ", 4), ("nan", 0)])
def test_levels_reads_a_number_half_up_or_gives_nothing(raw, n):
    assert ob.levels(raw) == n


def test_load_dedupes_across_tiles_and_assembles_a_relation_from_split_ways(tmp_path):
    a = synth.square(0, 0, 20)
    ring = list(synth.square(100, 0, 30).exterior.coords)        # one outer ring drawn as two ways
    hole = synth.square(100, 0, 10)
    rel = {"type": "relation", "id": 7, "tags": {"building": "yes", "building:levels": "5", "type": "multipolygon"},
           "members": [{"type": "way", "ref": 1, "role": "outer", "geometry": latlon(ring[:3])},
                       {"type": "way", "ref": 2, "role": "outer", "geometry": latlon(ring[2:])},
                       {"type": "way", "ref": 3, "role": "inner", "geometry": latlon(hole.exterior.coords)}]}
    write(tmp_path, "0_0.json", [way(1, a), rel, way(2, synth.square(200, 0), levels="nej")])
    write(tmp_path, "1_0.json", [way(1, a)])                       # the same way again, from the next tile
    got = ob.load(tmp_path)
    assert got.osm_id.tolist() == ["relation/7", "way/1"] and got.levels.tolist() == [5, 3]
    r = got.geometry[0]
    assert abs(r.area - (900 - 100)) < 1.0                          # the hole is cut out
    assert abs(got.geometry[1].area - 400) < 1.0
    assert ob.load(tmp_path / "none").empty


def test_load_reads_only_the_tiles_it_is_given(tmp_path):
    # Tiles left from a larger grid ("0_3" of 4 x 4 after a 3 x 3) were read too, and a
    # stale copy of a building beat a fresh one in sorted file order
    write(tmp_path, "0_3.json", [way(1, synth.square(0, 0, 20), levels="9"), way(5, synth.square(300, 0))])
    write(tmp_path, "1_0.json", [way(1, synth.square(0, 0, 20), levels="4")])
    got = ob.load(tmp_path, ["0_0", "1_0"])
    assert got.osm_id.tolist() == ["way/1"] and got.levels.tolist() == [4]


def test_match_takes_the_same_building_not_a_neighbour(tmp_path):
    b = synth.buildings(rows=[{"geometry": synth.square(0, 0, 20)}, {"geometry": synth.square(40, 0, 20)},
                              {"geometry": synth.square(80, 0, 20)}])
    write(tmp_path, "t.json", [
        way(1, synth.square(1, 0, 20), levels="6"),                # gid 0: almost the same outline (IoU 0.9)
        way(2, synth.square(40, 0, 40), levels="9"),               # gid 1 inside a much larger outline (IoU 0.25)
        way(3, synth.square(86, 0, 20), levels="2"),               # gid 2: shifted 6 m (IoU 0.54)
        way(4, synth.square(80, 0, 21), levels="4"),               # gid 2 again, a better match (IoU 0.91)
    ])
    osm = ob.load(tmp_path)
    got = ob.match(b, osm)
    assert got.to_dict() == {0: 6, 2: 4}
    assert ob.match(b, osm, min_iou=0.2).to_dict() == {0: 6, 1: 9, 2: 4}
    assert ob.match(b, osm.iloc[:0]).empty and str(ob.match(b, osm).dtype) == "uint8"


def test_a_way_with_too_few_points_or_no_geometry_is_skipped(tmp_path):
    bad = {"type": "way", "id": 9, "tags": {"building": "yes", "building:levels": "3"}, "geometry": latlon(
        [(city.ORIGIN[0], city.ORIGIN[1]), (city.ORIGIN[0] + 1, city.ORIGIN[1]), (city.ORIGIN[0], city.ORIGIN[1])])}
    rel = {"type": "relation", "id": 8, "tags": {"building": "yes", "building:levels": "3"}}   # `out tags` had no members
    write(tmp_path, "t.json", [bad, rel])
    assert ob.load(tmp_path).empty


def test_bowtie_outline_is_repaired_not_dropped(tmp_path):
    x, y = city.ORIGIN
    bowtie = shapely.Polygon([(x, y), (x + 10, y + 10), (x + 10, y), (x, y + 10), (x, y)])
    write(tmp_path, "t.json", [{"type": "way", "id": 5, "tags": {"building": "yes", "building:levels": "2"},
                                "geometry": latlon(bowtie.exterior.coords)}])
    got = ob.load(tmp_path)
    assert len(got) == 1 and got.geometry[0].is_valid and abs(got.geometry[0].area - 50) < 0.5


def test_a_clipped_copy_never_hides_the_whole_one_from_the_next_tile(tmp_path):
    # `out geom` under a bounding box can give null points for the nodes outside it. Such a copy is
    # no outline (no crash), and the element is not marked as seen, so a whole copy from another tile still counts.
    a = synth.square(0, 0, 20)
    clipped = way(1, a)
    clipped["geometry"] = clipped["geometry"][:2] + [None, None] + clipped["geometry"][4:]
    write(tmp_path, "0_0.json", [clipped])
    assert ob.load(tmp_path).empty
    write(tmp_path, "1_0.json", [way(1, a)])
    got = ob.load(tmp_path)
    assert got.osm_id.tolist() == ["way/1"] and abs(got.geometry[0].area - 400) < 1.0
