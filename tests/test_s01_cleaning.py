"""Review Focus #1: empty UUIDs, duplicated UUIDs and OIDs split across district files.

No building may be drawn twice, no slivers may survive, and gids must not depend on input order.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pytest
import shapely
from shapely.geometry import MultiPolygon, Polygon

from pipeline import city
from pipeline import s01_load as s01
from tests.synth import lod1_frame, prism

X, Y = 154000.0, 6578900.0   # Gamla stan, EPSG:3011


def row(geometry, **attrs):
    return {"geometry": geometry, **attrs}


def run(rows, **kw):
    return s01.clean(lod1_frame(rows), log=lambda *_: None, **kw)


def test_footprint_is_the_floor_face_in_2d():
    b = run([row(prism(X, Y, X + 10, Y + 20, 5.0, 15.0))])
    g = b.geometry.iloc[0]
    assert not g.has_z
    assert g.area == pytest.approx(200.0)
    assert b["area"].iloc[0] == pytest.approx(200.0)


def test_c3_columns_and_dtypes():
    b = run([row(prism(X, Y, X + 10, Y + 10, 2.0, 12.0)),
             row(prism(X + 20, Y, X + 30, Y + 10, 3.0, 9.0), UUID=None, FASTIGHET=None)])
    assert list(b.columns) == ["gid", "uuid", "oid", "grupp", "kategori", "fastighet", "height", "ground", "area",
                               "prod_year", "fnr", "geometry"]
    assert str(b["gid"].dtype) == "int32" and str(b["oid"].dtype) == "int64" and str(b["prod_year"].dtype) == "int16"
    assert b["prod_year"].tolist() == [2023, 2023]      # synth.lod1_raw's PROD_DATE "20230117"
    # The property-unit key (LOD1 FNR, internal), 0 for the unregistered building that has none
    assert str(b["fnr"].dtype) == "int64" and b["fnr"].tolist() == [0, 10_000_000]
    assert all(str(b[c].dtype) == "float32" for c in ("height", "ground", "area"))
    assert b.crs.to_epsg() == city.CRS
    assert b["gid"].tolist() == [0, 1]
    assert b["uuid"].tolist()[0] == ""            # empty UUIDs become "" and sort first
    assert (b["height"] > 0).all()


def test_prod_years_reads_the_year_of_a_prod_date_and_gives_zero_when_missing():
    got = s01.prod_years(["20230117", " 19871231 ", "2008", "", None, float("nan"), "None", "garbage"])
    assert got.tolist() == [2023, 1987, 2008, 0, 0, 0, 0, 0] and str(got.dtype) == "int64"
    assert s01.prod_years(pd.to_datetime(["2023-01-17", None])).tolist() == [2023, 0]     # real dates work too
    assert s01.prod_years([]).tolist() == []


def test_prod_year_of_a_split_oid_is_its_earliest_dated_piece():
    def halves(x, oid, uuid, d1, d2):
        return [row(prism(x, Y, x + 10, Y + 10, 5.0, 15.0), OID=oid, UUID=uuid, PROD_DATE=d1),
                row(prism(x + 10, Y, x + 20, Y + 10, 5.0, 15.0), OID=oid, UUID=uuid, PROD_DATE=d2)]
    b = run(halves(X, 7, "u-7", "20190305", "20080101")       # two dates: the earlier one
            + halves(X + 100, 8, "u-8", None, "20150601")     # a missing date never wins
            + halves(X + 200, 9, "u-9", None, None)           # none at all: 0
            + [row(prism(X + 300, Y, X + 310, Y + 10, 5.0, 15.0), OID=10, UUID="u-10", PROD_DATE="19991231")])
    assert b.set_index("oid")["prod_year"].to_dict() == {7: 2008, 8: 2015, 9: 0, 10: 1999}


def test_fnr_of_a_split_oid_is_its_smallest_registered_key():
    # like prod_year: a missing key (NaN) never wins, none at all gives 0 (the City's pieces of one OID carry the
    # same FNR in the 2026 data; the rule only has to be deterministic)
    def halves(x, oid, f1, f2):
        return [row(prism(x, Y, x + 10, Y + 10, 5.0, 15.0), OID=oid, UUID=f"u-{oid}", FNR=f1),
                row(prism(x + 10, Y, x + 20, Y + 10, 5.0, 15.0), OID=oid, UUID=f"u-{oid}", FNR=f2)]
    b = run(halves(X, 7, 10_450_000.0, 10_120_000.0) + halves(X + 100, 8, None, 10_500_000.0)
            + halves(X + 200, 9, None, None))
    assert b.set_index("oid")["fnr"].to_dict() == {7: 10_120_000, 8: 10_500_000, 9: 0}


def test_oid_split_across_districts_is_unioned():
    # one building cut by a district border: a 0.5 m² sliver in one file, the rest in the other
    b = run([row(prism(X, Y, X + 0.5, Y + 1, 4.3, 28.7), OID=50471681, UUID="u-split", TAKMAX_Z=28.7),
             row(prism(X + 0.5, Y, X + 20.5, Y + 12, 3.7, 30.1), OID=50471681, UUID="u-split", TAKMAX_Z=32.3)])
    assert len(b) == 1
    one = b.iloc[0]
    assert one.geometry.geom_type == "Polygon"
    assert one["area"] == pytest.approx(240.5)
    assert one["ground"] == pytest.approx(3.7)                 # min MARK_Z
    assert one["height"] == pytest.approx(30.1 - 3.7, abs=1e-4)  # max TAK_Z - min MARK_Z


def test_identical_footprints_are_drawn_once():
    sq = (X, Y, X + 10, Y + 10, 15.2, 22.4)
    b = run([row(prism(*sq), OID=50363471, UUID="u-dup"),
             row(prism(*sq), OID=50321776, UUID="u-dup"),         # same UUID, same polygon
             row(prism(X + 30, Y, X + 40, Y + 10, 1, 9), OID=1, UUID="u-filled"),
             row(prism(X + 30, Y, X + 40, Y + 10, 1, 9), OID=2, UUID=None),   # copy without UUID
             row(prism(X + 60, Y, X + 70, Y + 10, 1, 9), OID=3, UUID=None),
             row(prism(X + 60, Y, X + 70, Y + 10, 1, 9), OID=4, UUID=None)])  # two empty copies
    assert len(b) == 3
    assert sorted(b["oid"]) == [1, 3, 50321776]                # lowest OID wins; filled UUID beats empty


def test_same_uuid_near_identical_polygon_is_drawn_once():
    # the same 10 x 10 m house, once with an extra collinear vertex and 1 mm of jitter
    a = prism(X, Y, X + 10, Y + 10, 40.4, 50.4)
    floor = Polygon([(X, Y, 40.4), (X + 5, Y + 0.001, 40.4), (X + 10, Y, 40.4), (X + 10, Y + 10, 40.4),
                     (X, Y + 10, 40.4)])
    b_geom = MultiPolygon([floor, *list(a.geoms)[1:]])
    b = run([row(a, OID=50507893, UUID="u-near"), row(b_geom, OID=50507894, UUID="u-near")])
    assert b["oid"].tolist() == [50507893]


def jittered(x0, y0, x1, y1, z0, z1):
    """The same block as prism(), but the floor has an extra collinear vertex lifted 1 mm (IoU 0.99995)."""
    mid = (x0 + x1) / 2
    floor = Polygon([(x0, y0, z0), (mid, y0 + 0.001, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)])
    return MultiPolygon([floor, *list(prism(x0, y0, x1, y1, z0, z1).geoms)[1:]])


def test_empty_uuid_copy_of_a_filled_building_is_drawn_once():
    # the filled original has the HIGHER oid: a filled UUID beats a lower OID
    b = run([row(jittered(X, Y, X + 10, Y + 10, 1, 9), OID=50406245, UUID=None),
             row(prism(X, Y, X + 10, Y + 10, 1, 9), OID=50406246, UUID="u-orig")])
    assert b["oid"].tolist() == [50406246]
    assert b["uuid"].tolist() == ["u-orig"]


def test_two_empty_uuid_copies_keep_the_lowest_oid():
    b = run([row(jittered(X, Y, X + 10, Y + 10, 1, 9), OID=62649682, UUID=None),
             row(prism(X, Y, X + 10, Y + 10, 1, 9), OID=62649675, UUID=None)])
    assert b["oid"].tolist() == [62649675]


def _nested_pair(width_b, z1_b, uuid_a="u-a", uuid_b=None):
    """A 10 x 10 m block and a 10 x width_b block on top of it (IoU = width_b / 10), roofs at 9 and z1_b."""
    return [row(prism(X, Y, X + 10, Y + 10, 1, 9), OID=1, UUID=uuid_a),
            row(prism(X, Y, X + 10, Y + width_b, 1, z1_b), OID=2, UUID=uuid_b)]


def test_overlap_of_096_and_equal_height_with_an_empty_uuid_is_merged():
    b = run(_nested_pair(9.6, 9.0))
    assert b["oid"].tolist() == [1]                       # the filled one survives


def test_overlap_of_096_and_equal_height_keeps_the_filled_uuid_even_when_it_is_the_smaller_one():
    b = run(_nested_pair(9.6, 9.0, uuid_a=None, uuid_b="u-b"))
    assert b["oid"].tolist() == [2]


def test_overlap_of_096_with_heights_3_m_apart_keeps_both():
    b = run(_nested_pair(9.6, 12.0))                      # heights 8.0 and 11.0
    assert sorted(b["oid"]) == [1, 2]


def test_overlap_below_095_keeps_both_even_at_equal_height():
    b = run(_nested_pair(9.4, 9.0))                       # IoU 0.94
    assert sorted(b["oid"]) == [1, 2]


def test_overlap_of_095_with_heights_within_a_decimetre_merges_but_not_beyond():
    assert run(_nested_pair(9.6, 9.1))["oid"].tolist() == [1]          # heights 8.0 / 8.1
    assert sorted(run(_nested_pair(9.6, 9.2))["oid"]) == [1, 2]        # heights 8.0 / 8.2


def test_two_different_filled_uuids_are_never_merged():
    b = run(_nested_pair(9.95, 9.0, uuid_a="u-a", uuid_b="u-b"))        # IoU 0.995, equal height
    assert sorted(b["oid"]) == [1, 2]
    b = run([row(jittered(X, Y, X + 10, Y + 10, 1, 9), OID=1, UUID="u-a"),
             row(prism(X, Y, X + 10, Y + 10, 1, 9), OID=2, UUID="u-b")])
    assert b["oid"].tolist() == [1, 2]


def test_empty_uuid_copy_next_to_two_filled_neighbours_is_dropped_and_both_neighbours_stay():
    b = run([row(prism(X, Y, X + 10, Y + 10, 1, 9), OID=7, UUID="u-a"),
             row(jittered(X, Y, X + 10, Y + 10, 1, 9), OID=8, UUID="u-b"),
             row(jittered(X, Y, X + 10, Y + 10, 1, 9), OID=3, UUID=None)])
    assert sorted(b["oid"]) == [7, 8]


def _near_duplicate_rows():
    rows = []
    for k in range(4):
        x = X + 100 * k
        rows += [row(prism(x, Y, x + 10, Y + 10, 1, 9), OID=100 + 10 * k + 5, UUID=None),
                 row(jittered(x, Y, x + 10, Y + 10, 1, 9), OID=100 + 10 * k + 1, UUID=None if k % 2 else f"u{k}"),
                 row(prism(x, Y, x + 10, Y + 9.6, 1, 9), OID=100 + 10 * k + 3, UUID=None)]
    rows += [row(prism(X + 500, Y, X + 510, Y + 10, 1, 9), OID=900, UUID="u-a"),
             row(prism(X + 500, Y, X + 510, Y + 9.95, 1, 9), OID=901, UUID="u-b"),
             row(jittered(X + 500, Y, X + 510, Y + 10, 1, 9), OID=902, UUID=None)]
    return rows


def test_near_duplicate_rule_does_not_depend_on_input_order():
    raw = lod1_frame(_near_duplicate_rows())
    a = s01.clean(raw, log=lambda *_: None)
    # one survivor per block of three (the filled UUID, else the lowest OID); u-a and u-b both stay, 902 goes
    assert sorted(a["oid"]) == [101, 111, 121, 131, 900, 901]
    for seed in range(8):
        b = s01.clean(raw.sample(frac=1.0, random_state=seed).reset_index(drop=True), log=lambda *_: None)
        assert b[["gid", "uuid", "oid"]].equals(a[["gid", "uuid", "oid"]])
        assert np.array_equal(shapely.to_wkb(b.geometry.values), shapely.to_wkb(a.geometry.values))


def test_same_uuid_separate_footprints_are_kept():
    b = run([row(prism(X, Y, X + 10, Y + 10, 18.4, 30.4), OID=50506839, UUID="u-two"),
             row(prism(X + 20, Y, X + 30, Y + 10, 18.0, 22.8), OID=50506840, UUID="u-two")])
    assert b["oid"].tolist() == [50506839, 50506840]
    assert b["height"].tolist() == pytest.approx([12.0, 4.8], abs=1e-4)


def test_slivers_under_two_square_metres_are_dropped():
    b = run([row(prism(X, Y, X + 1, Y + 1, 0, 3), OID=1),            # 1 m²
             row(prism(X + 5, Y, X + 7, Y + 1.5, 0, 3), OID=2)])     # 3 m²
    assert b["oid"].tolist() == [2]


def test_height_is_the_roof_not_the_spire():
    # Riddarholmskyrkan: BYGG_H and the MULTIPATCH reach the spire top (TAKMAX_Z); the height stops at the roof
    church = [row(prism(X, Y, X + 30, Y + 52, 7.7, 97.4), MARK_Z=7.7, TAK_Z=22.8, TAKMAX_Z=97.4, BYGG_H=89.7)]
    assert run(church)["height"].iloc[0] == pytest.approx(15.1, abs=1e-4)
    _, spire = s01.heights(s01.footprints(lod1_frame(church)))
    assert spire.tolist() == [True]


def test_roof_below_ground_falls_back_to_bygg_h():
    # GRIMSTA 1:2 (Parkeringshus): TAK_Z 27.5 < MARK_Z 29.2, BYGG_H 1.7
    b = run([row(prism(X, Y, X + 20, Y + 30, 29.2, 30.9), MARK_Z=29.2, TAK_Z=27.5, TAKMAX_Z=27.5, BYGG_H=1.7)])
    assert b["height"].iloc[0] == pytest.approx(1.7, abs=1e-4)


def test_boundary_keeps_buildings_whose_point_is_inside():
    boundary = shapely.box(X - 100, Y - 100, X + 50, Y + 50)
    b = run([row(prism(X, Y, X + 10, Y + 10, 0, 6), OID=1),
             row(prism(X + 45, Y, X + 65, Y + 10, 0, 6), OID=2),     # point at X+55: outside
             row(prism(X + 500, Y, X + 510, Y + 10, 0, 6), OID=3)], boundary=boundary)
    assert b["oid"].tolist() == [1]


def test_fixture_mode_keeps_only_the_fixture_bbox():
    x0, y0, x1, y1 = city.FIXTURE_BBOX
    b = run([row(prism(x0 + 10, y0 + 10, x0 + 20, y0 + 20, 0, 6), OID=1),
             row(prism(x1 + 100, y1, x1 + 110, y1 + 10, 0, 6), OID=2)], fixture=True)
    assert b["oid"].tolist() == [1]


def _messy_rows():
    rows = []
    for i in range(24):
        x = X + (i % 6) * 15
        y = Y + (i // 6) * 15
        rows.append(row(prism(x, y, x + 8, y + 9, 1.0 + i / 10, 12.0 + i), OID=60_000_000 + i,
                        UUID=None if i % 5 == 0 else f"u{i % 7:03d}"))
    rows.append(row(prism(X + 200, Y, X + 200.5, Y + 1, 2, 9), OID=70_000_000, UUID="u-split"))
    rows.append(row(prism(X + 200.5, Y, X + 210, Y + 10, 1, 12), OID=70_000_000, UUID="u-split"))
    rows.append(row(prism(X + 300, Y, X + 310, Y + 10, 1, 12), OID=70_000_001, UUID="u-dup"))
    rows.append(row(prism(X + 300, Y, X + 310, Y + 10, 1, 12), OID=70_000_002, UUID="u-dup"))
    rows.append(row(prism(X + 400, Y, X + 401, Y + 1, 1, 3), OID=70_000_003, UUID=None))
    return rows


def test_gids_do_not_depend_on_input_order():
    raw = lod1_frame(_messy_rows())
    a = s01.clean(raw, log=lambda *_: None)
    for seed in (1, 2, 3):
        shuffled = raw.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        b = s01.clean(shuffled, log=lambda *_: None)
        assert b[["gid", "uuid", "oid"]].equals(a[["gid", "uuid", "oid"]])
        assert np.array_equal(shapely.to_wkb(b.geometry.values), shapely.to_wkb(a.geometry.values))
    assert len(a) == 26                     # 24 + 1 union + 1 of the duplicate pair; the 1 m² sliver is gone
    assert a["gid"].tolist() == list(range(26))
    assert not a["oid"].duplicated().any()


def main_args(tmp_path) -> list[str]:
    """Two district files and a stadsdelar boundary; s01.main on them keeps one building."""
    lod1 = tmp_path / "lod1"
    districts = {"norrmalm": [row(prism(X, Y, X + 0.5, Y + 1, 4.3, 28.7), OID=9, UUID="s")],
                 "ostermalm": [row(prism(X + 0.5, Y, X + 20.5, Y + 12, 3.7, 30.1), OID=9, UUID="s"),
                               row(prism(X + 900, Y, X + 910, Y + 10, 0, 6), OID=10)]}
    for name, rows in districts.items():
        (lod1 / name).mkdir(parents=True)
        pyogrio.write_dataframe(lod1_frame(rows), lod1 / name / "Byggnad.shp", layer_options={"SHPT": "MULTIPATCH"})
    sd = tmp_path / "Stadsdel.shp"
    gpd.GeoDataFrame({"NAMN": ["GAMLA STAN"]}, geometry=[shapely.box(X - 50, Y - 50, X + 100, Y + 100)],
                     crs=3011).to_file(sd)
    return ["--lod1", str(lod1), "--stadsdelar", str(sd), "--out", str(tmp_path / "buildings.parquet")]


def test_main_fails_below_the_city_floor_without_writing(tmp_path, monkeypatch):
    # A partial LOD1 (a district missing, a filter gone wrong) must not become data/buildings.parquet
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    with pytest.raises(SystemExit, match="1 buildings after cleaning, fewer than the city's 70,000"):
        s01.main(main_args(tmp_path))
    assert not (tmp_path / "buildings.parquet").exists()


def test_the_fixture_build_has_no_floor(tmp_path, monkeypatch):
    monkeypatch.setenv("HFH_FIXTURE", "1")
    s01.main(main_args(tmp_path))
    assert len(gpd.read_parquet(tmp_path / "buildings.parquet")) == 1


def test_main_reads_multipatch_files_and_writes_parquet(tmp_path, monkeypatch):
    out = tmp_path / "buildings.parquet"
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    s01.main([*main_args(tmp_path), "--min-buildings", "1"])
    b = gpd.read_parquet(out)
    assert b["oid"].tolist() == [9]          # the split pieces became one; OID 10 lies outside the stadsdelar
    assert b["area"].iloc[0] == pytest.approx(240.5)
