import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon

from pipeline import city, codes, s03_tiles, tiles_decode
from tests.tinycity import local_box


def test_magic_spells_hfh1():
    assert tiles_decode.MAGIC == 0x31484648
    assert tiles_decode.MAGIC.to_bytes(4, "little") == b"HFH1"


def round_trip_rows():
    courtyard = Polygon(local_box(100, 200, 140, 240).exterior.coords,
                        [local_box(110, 210, 130, 230).exterior.coords])
    pair = MultiPolygon([local_box(-300, 40, -290, 50), local_box(-280, 40, -270, 52)])
    return [
        {"gid": 7, "year": 1647, "yflag": codes.EXACT, "period": 1, "floors": 6, "ground_dm": 31,
         "height": 26.7, "geometry": local_box(0, 0, 10, 10)},
        {"gid": 3, "year": 0, "yflag": codes.UNKNOWN, "period": 0, "floors": 4, "ground_dm": -11,
         "height": 18.25, "geometry": courtyard},
        {"gid": 12, "year": 1950, "yflag": codes.AREA, "period": 8, "floors": 2, "ground_dm": 736,
         "height": 6.3, "geometry": pair},
    ]


def test_pack_tile_round_trips_through_the_decoder():
    origin = (-1500.0, 0.0)
    rows = round_trip_rows()
    buf = s03_tiles.pack_tile(origin, rows)
    t = tiles_decode.parse(buf)
    assert t["end"] == len(buf) and len(buf) % 4 == 0
    assert (t["nB"], t["nP"], t["nR"], t["nV"]) == (3, 3, 5, 20)
    assert t["origin"] == origin
    assert t["gid"].tolist() == [7, 3, 12]
    assert t["year"].tolist() == [1647, 0, 1950]
    assert t["yflag"].tolist() == [codes.EXACT, codes.UNKNOWN, codes.AREA]
    assert t["period"].tolist() == [1, 0, 8]
    assert t["floors"].tolist() == [6, 4, 2]
    assert t["ground"].tolist() == [31, -11, 736]
    assert t["lay0"].tolist() == [0, 0, 0] and t["lay1"].tolist() == [0, 0, 0]
    assert t["partStart"].tolist() == [0, 1, 2, 3]  # one part per building
    assert np.allclose(t["height"], [26.7, 18.25, 6.3], atol=1e-5)
    assert t["ringStart"].tolist() == [0, 1, 3, 5]
    assert t["hole"].tolist() == [0, 0, 1, 0, 0]   # square; courtyard + hole; two exteriors of a MultiPolygon
    assert t["vertStart"].tolist() == [0, 4, 8, 12, 16, 20]
    for b, row in enumerate(rows):
        expected = list(s03_tiles.rings_of(row["geometry"]))
        got = tiles_decode.rings(t, b)
        assert [h for _, h in got] == [h for _, h in expected]
        for (xz, _), (en, _) in zip(got, expected, strict=True):
            x, z = city.to_local(en[:, 0], en[:, 1])
            assert np.abs(xz - np.c_[x, z]).max() <= 0.05  # decimetre rounding


def test_two_tiles_back_to_back_decode_by_offset():
    rows = round_trip_rows()
    a = s03_tiles.pack_tile((-1500.0, 0.0), rows[:1])
    b = s03_tiles.pack_tile((-1500.0, 0.0), rows[1:])
    t = tiles_decode.parse(a + b, len(a))
    assert t["gid"].tolist() == [3, 12] and t["end"] == len(a) + len(b)


def test_pack_tile_refuses_vertices_beyond_i16():
    far = {"gid": 0, "year": 0, "yflag": codes.UNKNOWN, "period": 0, "floors": 1, "ground_dm": 0,
           "height": 3.0, "geometry": local_box(4000, 0, 4010, 10)}
    with pytest.raises(ValueError, match="i16"):
        s03_tiles.pack_tile((0.0, 0.0), [far])


def test_wrong_magic_is_rejected():
    buf = bytearray(s03_tiles.pack_tile((0.0, 0.0), round_trip_rows()[:1]))
    buf[0:4] = b"ABB3"
    with pytest.raises(ValueError, match="magic"):
        tiles_decode.parse(bytes(buf))
