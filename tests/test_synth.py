"""tests/synth.py builds inputs shaped like the buildings frame and like the raw City LOD1."""
import numpy as np
import pandas as pd
import pytest
import shapely

from pipeline import city, codes
from tests import synth


def test_square_is_centred_in_the_local_frame():
    sq = synth.square(100.0, -50.0, size=8.0)
    x, z = city.to_local(sq.centroid.x, sq.centroid.y)
    assert np.allclose([x, z], [100.0, -50.0]) and sq.area == pytest.approx(64.0)
    assert sq.exterior.is_ccw


def test_buildings_match_c3(tmp_path):
    b = synth.buildings(3)
    assert list(b.columns) == ["gid", "uuid", "oid", "grupp", "kategori", "fastighet", "height", "ground", "area",
                               "prod_year", "fnr", "geometry"]
    assert b.gid.tolist() == [0, 1, 2] and str(b.gid.dtype) == "int32" and str(b.oid.dtype) == "int64"
    # An early-formed property unit by default, below city.ESTIMATE's late_unit_fnr
    assert str(b.fnr.dtype) == "int64" and b.fnr.tolist() == [10_100_000, 10_100_001, 10_100_002]
    assert {str(b[c].dtype) for c in ["height", "ground", "area"]} == {"float32"}
    assert b.crs.to_epsg() == 3011 and b["area"].tolist() == [100.0, 100.0, 100.0]  # b.area is shapely's
    b2 = synth.buildings(rows=[{"uuid": "", "area": 1.5},
                               {"kategori": "Enbostadshus", "geometry": synth.square(0, 50, 20)}])
    assert b2.uuid.tolist()[0] == "" and b2["area"].tolist() == [1.5, 400.0]
    b.to_parquet(tmp_path / "b.parquet")
    back = pd.read_parquet(tmp_path / "b.parquet")
    assert str(back.gid.dtype) == "int32" and str(back.height.dtype) == "float32"


def test_years_match_c3():
    y = synth.years([0, 1, 2], year=[1650, 1931, 0], yflag=[codes.EXACT, codes.RANGE, codes.UNKNOWN],
                    year_from=[1650, 1929, 0], ysrc=[codes.SRC_CURATED, codes.SRC_RAA, codes.SRC_NONE])
    assert list(y.columns) == ["gid", "year", "year_from", "year_to", "ysrc", "yflag", "period", "private", "raa_id",
                               "landmark"]
    assert y.period.tolist() == [1, 7, 0] and y.year_to.tolist() == [1650, 1931, 0]
    assert [str(y[c].dtype) for c in ["year", "year_from", "year_to"]] == ["int16"] * 3
    assert [str(y[c].dtype) for c in ["ysrc", "yflag", "period"]] == ["uint8"] * 3
    assert str(y.private.dtype) == "bool" and y.private.tolist() == [False] * 3
    # a private house: decade published, period from the real year (1967 is p10, 1960 would be p9)
    p = synth.years([7], year=1960, year_to=1969, period=city.period_index(1967), yflag=codes.EXACT,
                    ysrc=codes.SRC_RAA, private=True)
    assert p.iloc[0].tolist()[:8] == [7, 1960, 1960, 1969, codes.SRC_RAA, codes.EXACT, 9, True]
    with pytest.raises(TypeError, match="unknown years columns"):
        synth.years([0], decade=1950)
    with pytest.raises(ValueError, match="expected 2 values"):
        synth.years([0, 1], year=[1900])


def test_attributes_match_c3(tmp_path):
    a = synth.attributes([0, 1], floors=[5, 2], architects=[["Ivar Tengbom"], []], rating=[codes.RATING["Blått"], 0])
    assert list(a.columns) == ["gid", "floors", "fsrc", "rating", "architects", "name"]
    assert a.architects.tolist() == [["Ivar Tengbom"], []] and a.fsrc.tolist() == [codes.FLOORS_HEIGHT] * 2
    a.to_parquet(tmp_path / "a.parquet")
    assert [list(v) for v in pd.read_parquet(tmp_path / "a.parquet").architects] == [["Ivar Tengbom"], []]


def test_lod1_raw_looks_like_the_city_multipatch():
    raw = synth.lod1_raw([
        {"footprint": synth.square(0, 0)},
        {"footprint": synth.square(30, 0), "UUID": None},
        {"footprint": synth.square(60, 0, 30), "MARK_Z": 7.7, "TAK_Z": 22.8, "TAKMAX_Z": 97.4, "BYGG_H": 89.7},
    ])
    assert list(raw.columns) == [*synth.LOD1_COLUMNS, "district", "geometry"]
    assert raw.UUID.isna().tolist() == [False, True, False]
    assert raw.FASTIGHET.isna().tolist() == [False, True, False] and raw.FNR.isna().tolist() == [False, True, False]
    assert {str(raw[c].dtype) for c in ["KOM_ID", "FNR", "HUSNR"]} == {"float64"} and str(raw.OID.dtype) == "int64"
    g = raw.geometry.iloc[0]
    assert g.geom_type == "MultiPolygon" and g.has_z and len(g.geoms) == 6  # bottom, 4 walls, top
    z = [shapely.get_coordinates(p, include_z=True)[:, 2] for p in g.geoms]
    assert np.allclose(z[0], 5.0) and np.allclose(z[-1], 20.0) and raw.BYGG_H.iloc[0] == 15.0
    spire = raw.geometry.iloc[2]
    assert shapely.get_coordinates(spire, include_z=True)[:, 2].max() == pytest.approx(97.4)


def test_prism_and_lod1_frame_keep_the_given_geometry():
    x, y = city.ORIGIN
    g = synth.prism(x, y, x + 10, y + 20, 5.0, 15.0)
    assert g.geom_type == "MultiPolygon" and len(g.geoms) == 6
    raw = synth.lod1_frame([{"geometry": g}, {"geometry": g, "UUID": None, "OID": 7, "TAK_Z": 12.0}])
    assert list(raw.columns) == [*synth.LOD1_COLUMNS, "district", "geometry"]
    assert raw.MARK_Z.tolist() == [5.0, 5.0] and raw.TAK_Z.tolist() == [15.0, 12.0]
    assert raw.BYGG_H.tolist() == [10.0, 7.0] and raw.OID.tolist() == [50_000_000, 7]
    assert raw.UUID.isna().tolist() == [False, True]
    assert shapely.get_coordinates(raw.geometry.iloc[1], include_z=True)[:, 2].max() == 15.0  # never rebuilt
