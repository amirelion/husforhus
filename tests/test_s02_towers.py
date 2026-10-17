"""s02_towers on synthetic point sets: a church with a spire, a house under a tree, a building that changed since the
scan, stray returns, and the step's files."""
import json

import geopandas as gpd
import numpy as np
import pytest
import shapely

from pipeline import laser, s02_towers as st
from tests.tinycity import write_data

GROUND = 10.0


def grid(x0, y0, x1, y1, step=0.85):
    xs, ys = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
    return xs.ravel(), ys.ravel()


def pts(*parts):
    """Concatenate point groups given as (x, y, z, cls, rn, nr) with scalars broadcast."""
    out = {k: [] for k in laser.FIELDS}
    for x, y, z, cls, rn, nr in parts:
        n = len(x)
        for k, v in zip(laser.FIELDS, (x, y, z, cls, rn, nr), strict=True):
            out[k].append(np.broadcast_to(np.asarray(v, dtype=np.float64), (n,)))
    out = {k: np.concatenate(v) for k, v in out.items()}
    for k in ("cls", "rn", "nr"):
        out[k] = out[k].astype(np.uint8)
    return out


def site(fp, roof_m, ground=GROUND):
    """Ground points (class 2) in the 15 m ring and single-return roof points over the whole footprint."""
    x0, y0, x1, y1 = fp.bounds
    gx, gy = grid(x0 - 15, y0 - 15, x1 + 15, y1 + 15, 1.0)
    out = ~shapely.contains_xy(fp, gx, gy)
    rx, ry = grid(x0, y0, x1, y1)
    return [(gx[out], gy[out], ground, 2, 1, 1), (rx, ry, ground + roof_m, 1, 1, 1)]


def test_a_church_with_a_narrow_spire_gets_one_part_at_the_spires_height():
    fp = shapely.box(0, 0, 20, 40)
    rng = np.random.default_rng(1)
    n = 30
    sx, sy = rng.uniform(9, 11.5, n), rng.uniform(33, 35.5, n)       # a spire 2.5 m wide near one end
    sz = GROUND + np.linspace(25, 90, n)                            # about 2.2 m between returns up to the tip
    r = st.detect(fp, 15.0, pts(*site(fp, 15.0), (sx, sy, sz, 1, 1, 1)), fallback_ground=0.0)
    assert r["skip"] is None and r["ground_basis"] == "ring" and r["ground"] == pytest.approx(GROUND)
    assert len(r["parts"]) == 1
    p = r["parts"][0]
    assert p["height_m"] == pytest.approx(90.0) and p["top_z"] == pytest.approx(GROUND + 90)
    g = p["geometry"]
    assert shapely.covers(fp, g) and 9 <= g.area <= 30                # at least 3 x 3 m, not the whole church
    assert g.centroid.distance(shapely.Point(10.25, 34.25)) < 1.5
    # points the spire's height above the ground: the points inside the 15 m LOD1 roof are not a part
    assert p["n_points"] == int(((sz - GROUND) > 15 + 6).sum())


def test_a_house_under_a_tree_gets_nothing():
    fp = shapely.box(0, 0, 10, 10)
    tx, ty = grid(2, 2, 9, 9, 0.6)
    canopy = (tx, ty, GROUND + 16 + (tx % 1), 1, 1, 2)          # the tree's first returns, well above the roof
    through = (tx, ty, GROUND + 6.2, 1, 2, 2)                    # its last returns reach the roof
    r = st.detect(fp, 6.0, pts(*site(fp, 6.0), canopy, through), fallback_ground=0.0)
    assert r["skip"] is None and r["parts"] == []


def test_a_building_whose_roof_differs_from_the_lod1_is_skipped():
    fp = shapely.box(0, 0, 30, 30)
    r = st.detect(fp, 30.0, pts(*site(fp, 12.0)), fallback_ground=0.0)
    assert r["parts"] == [] and "changed since the 2021 scan" in r["skip"]
    assert r["roof_m"] == pytest.approx(12.0)
    # within max(4 m, 25 %) it is the same building
    assert st.detect(fp, 30.0, pts(*site(fp, 24.0)), fallback_ground=0.0)["skip"] is None


def test_one_stray_high_point_is_not_a_spire():
    fp = shapely.box(0, 0, 20, 20)
    stray = (np.array([10.0]), np.array([10.0]), GROUND + 60, 1, 1, 1)
    r = st.detect(fp, 12.0, pts(*site(fp, 12.0), stray), fallback_ground=0.0)
    assert r["skip"] is None and r["parts"] == []
    # nor four returns stacked more than 3 m apart (a bird, a wire, a crane's hook): no top
    birds = (np.full(4, 10.0), np.full(4, 10.0) + np.arange(4) * 0.3, GROUND + np.array([40, 45, 50, 55.0]), 1, 1, 1)
    assert st.detect(fp, 12.0, pts(*site(fp, 12.0), birds), fallback_ground=0.0)["parts"] == []
    # high noise (class 18) is never a roof point
    noise = (np.full(10, 10.0), np.linspace(5, 6, 10), GROUND + np.linspace(40, 49, 10), 18, 1, 1)
    assert st.detect(fp, 12.0, pts(*site(fp, 12.0), noise), fallback_ground=0.0)["parts"] == []


def test_without_ground_points_the_lod1_ground_stands_in():
    fp = shapely.box(0, 0, 20, 20)
    rx, ry = grid(0, 0, 20, 20)
    r = st.detect(fp, 12.0, pts((rx, ry, 5.0 + 12.0, 1, 1, 1)), fallback_ground=5.0)
    assert (r["ground"], r["ground_basis"], r["skip"]) == (5.0, "lod1", None)
    assert "fewer than" in st.detect(fp, 12.0, pts((rx[:3], ry[:3], 17.0, 1, 1, 1)), 5.0)["skip"]


def test_helpers():
    assert st.cluster_top(np.array([10.0, 30.0, 12.0, 11.0])) == 12.0
    assert st.cluster_top(np.array([10.0, 20.0])) is None
    lab = st.clusters(np.array([0.0, 1.0, 2.2, 10.0]), np.array([0.0, 1.4, 2.9, 10.0]))
    assert lab[0] == lab[1] == lab[2] != lab[3]                       # diagonal cells touch


def test_the_step_writes_parts_for_candidates_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_data(tmp_path / "data")
    st.main([])                                                         # no points cached: nothing, no failure
    assert not (tmp_path / "data" / "towers.parquet").exists()
    b = gpd.read_parquet(tmp_path / "data" / "buildings.parquet")
    folder = tmp_path / laser.POINTS
    for gid in (0, 4):              # gid 0 is the church (Tyska kyrkan, 26.7 m); gid 4 a private house
        fp = b.geometry[gid]
        h, g = float(b.height[gid]), float(b.ground[gid])
        c = fp.centroid
        n = 20
        spire = (np.full(n, c.x) + np.linspace(-1, 1, n), np.full(n, c.y), g + np.linspace(h + 12, h + 50, n), 1, 1, 1)
        laser.save_points(laser.points_path(gid, folder), pts(*site(fp, h, g), spire))
    st.main(["--version", "v20991231"])
    t = gpd.read_parquet(tmp_path / "data" / "towers.parquet")
    assert t.gid.tolist() == [0] and t.part.tolist() == [0] and t.basis.tolist() == ["laser"]
    assert float(t.height_m[0]) == pytest.approx(26.7 + 50, abs=0.01) and t.crs.to_epsg() == 3011
    rec = json.loads((tmp_path / "data" / "towers.json").read_text())
    assert rec["parts"] == 1 and rec["raised"] == 1 and len(rec["buildings_sha256"]) == 64
    md = (tmp_path / "data" / "review-towers.md").read_text()
    assert "| Tyska kyrkan | 0 | 26.7 | 76.7 |" in md
    assert "Kaknästornet" not in md.split("## Hand-list")[1]           # it is in the tiny city


def test_a_hand_listed_landmark_skips_the_roof_check():
    # Kaknästornet and Globen: the City's footprint is a low base the LOD1 height does not match, but the hand list
    # says the laser's tower is what matters there
    fp = shapely.box(0, 0, 20, 20)
    sx, sy = np.meshgrid(np.arange(8, 12, 1.0), np.arange(8, 12, 1.0))
    shaft = (sx.ravel(), sy.ravel(), np.full(sx.size, 150.0), 1, 1, 1)
    base = pts(*site(fp, 7.0), shaft)
    assert st.detect(fp, 13.0, base, fallback_ground=0.0)["skip"] is not None
    r = st.detect(fp, 13.0, base, fallback_ground=0.0, trusted=True)
    assert r["skip"] is None and len(r["parts"]) == 1 and r["parts"][0]["top_z"] == 150.0
    assert r["parts"][0]["height_m"] == pytest.approx(150.0 - r["ground"])
