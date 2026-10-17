"""s02_terrain on the synthetic town (tests/terrain_town.py): the grid from contours or from a DTM,
the water levels, the fixed ground, the hybrid TIN, the terrace and the files it writes. Then s04_base on the same
town."""
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import shapely

from pipeline import city, codes, contours, s02_terrain, s04_base, terrain
from pipeline.s02_attributes import floors_from_height
from tests import synth
from tests import terrain_town as town


@pytest.fixture
def made(tmp_path, monkeypatch):
    """The town's raw files and data/, with the working directory there, as the runner sees it."""
    monkeypatch.chdir(tmp_path)
    town.write_raw(tmp_path / "data" / "raw" / "city")
    town.write_data(tmp_path / "data")
    return tmp_path


def run(made, *args):
    s02_terrain.main(list(args))
    with np.load(made / "data" / "terrain.npz") as z:
        arrays = {k: z[k] for k in z.files}
    record = json.loads((made / "data" / "terrain.json").read_text())
    return arrays, record, pd.read_parquet(made / "data" / "ground.parquet")


def test_choose_source_prefers_the_dtm_and_never_invents_one(tmp_path):
    assert s02_terrain.choose_source("auto", tmp_path / "dtm5.tif") == "contours"
    (tmp_path / "dtm5.tif").write_bytes(b"x")
    assert s02_terrain.choose_source("auto", tmp_path / "dtm5.tif") == "dtm"
    assert s02_terrain.choose_source("contours", tmp_path / "dtm5.tif") == "contours"
    with pytest.raises(SystemExit, match="s00_fetch_dem"):
        s02_terrain.choose_source("dtm", tmp_path / "missing.tif")


def nodes_under(grid, poly):
    """The grid nodes of every cell the (local) footprint touches: what the terrace may cut."""
    X, Z = grid.node_xz()
    x0, z0, x1, z1 = poly.bounds
    return (X >= np.floor(x0 / grid.cell) * grid.cell) & (X <= np.ceil(x1 / grid.cell) * grid.cell) & \
        (Z >= np.floor(z0 / grid.cell) * grid.cell) & (Z <= np.ceil(z1 / grid.cell) * grid.cell)


def test_contour_build_gives_the_hill_the_sea_the_lake_and_fixes_the_outlier(made):
    arrays, record, g = run(made, "--source", "contours")
    grid = terrain.Grid(record["x0"], record["z0"], record["cell"], record["nx"], record["nz"])
    assert (record["source"], record["cell"], record["fixture"]) == ("contours", 20.0, False)
    assert (grid.x0, grid.z0) == (-20.0, -20.0) and (grid.nx, grid.nz) == (53, 43)
    assert arrays["h"].shape == (grid.nz, grid.nx) and np.isfinite(arrays["h"]).all()
    # land nodes follow the cone the contours were drawn from (beside the lake the shore, at the lake's level,
    # pulls the TIN down, as a real bank does; around gid 4 its own ground does, below)
    X, Z = grid.node_xz()
    near_lake = (X > 140) & (X < 360) & (Z > 240) & (Z < 460)
    near_strip = (X > 440) & (X < 580) & (Z > 270) & (Z < 410)
    land = arrays["use"] & (X > 40) & (X < 800) & (Z > 40) & (Z < 760) & ~near_lake & ~near_strip
    assert np.abs(arrays["h"][land] - town.height(X[land], Z[land])).max() < 1.0
    # the strait is the sea (its shores read about 1 m), the lake keeps its own level a metre under its shore
    sea, lake = arrays["levels"].tolist()
    assert sea == 0.0 and 23.0 < lake < 27.0 and record["lakes"] == 1 and record["sea"] is None
    # far from land, the grid holds each water's level (the camera's floor over water)
    assert arrays["h"][grid.nz // 2, grid.nx - 3] == pytest.approx(0.0)
    # gid 1's MARK_Z is 25 m too low: its ground comes from the terrain and its roof stays where it was
    b, _ = town.buildings()
    assert g.gid.tolist() == list(range(7)) and g.ground_src.tolist() == [0, 1, 0, 0, 0, 0, 0] and record["fixed"] == 1
    roof = float(b.ground[1] + b.height[1])
    assert g.ground[1] == pytest.approx(town.outline_min(town.FOOTPRINTS[1]), abs=1.0)
    assert g.ground[1] + g.height[1] == pytest.approx(roof, abs=1e-3)
    assert g.floors[1] == 3                              # 35 m became about 10 m: floors follow (k = 4.0)
    assert g.ground[0] == pytest.approx(b.ground[0]) and g.floors.tolist()[::2] == [3, 2, 3, 2]
    # the terrace cuts nodes under gid 2 (across the slope) down to its ground + 0.3 m
    assert arrays["cut"].max() > 0.5 and arrays["cut"].max() <= city.TERRAIN["terrace_max_cut"]
    assert abs(record["datum"]) < 0.5
    # gid 3, the quay house under the sea, is drawn at the 0.3 m floor, and the terrace cuts no node of its cells
    # below that floor + terrace_up (it never digs a pit under the sea)
    t = city.TERRAIN
    assert g.ground[3] == pytest.approx(t["water_z"] + t["ground_min"])
    under = nodes_under(grid, town.FOOTPRINTS[3]) & (arrays["cut"] > 0)
    assert under.any() and (arrays["h"] - arrays["cut"])[under].min() >= t["water_z"] + t["ground_min"] + t["terrace_up"] - 1e-4


def test_the_hybrid_tin_brings_a_strip_at_a_cliffs_foot_down_and_nothing_stays_buried(made):
    # gid 4 stands on a paved strip 15 m under the contours (no contour crosses it, as along Söder Mälarstrand): its
    # MARK_Z joins the TIN, so the ground around it comes down, it is not "fixed", and the terrace frees it
    arrays, record, g = run(made, "--source", "contours")
    grid = terrain.Grid(record["x0"], record["z0"], record["cell"], record["nx"], record["nz"])
    b, _ = town.buildings()
    under = nodes_under(grid, town.FOOTPRINTS[4])
    X, Z = grid.node_xz()
    assert (arrays["h"][under] - town.height(X[under], Z[under])).min() < -5
    assert g.ground_src[4] == 0 and g.ground[4] == pytest.approx(b.ground[4])
    assert record["buried"] == 0
    # with the old 8 m cap on the cut it would stay buried (more than half its height at the relief's maximum)
    a, rec, _ = s02_terrain.build(Path("data/raw/city"), b, town.buildings()[1], kind="contours", fixture=False,
                                  cfg={**city.TERRAIN, "terrace_max_cut": 8.0}, log=lambda *_: None)
    assert rec["buried"] == 1


def frame(footprints, ground, height):
    """buildings and attributes for local footprints (gids 0..n-1), as s01_load and s02_attributes leave them."""
    import geopandas as gpd
    n = len(footprints)
    b = gpd.GeoDataFrame({"gid": pd.array(range(n), dtype="int32"), "kategori": ["Flerbostadshus"] * n,
                          "ground": np.asarray(ground, "float32"), "height": np.asarray(height, "float32")},
                         geometry=[town.to3011(p) for p in footprints], crs=city.CRS)
    return b, pd.DataFrame({"gid": pd.array(range(n), dtype="int32"), "floors": pd.array([3] * n, dtype="uint8"),
                            "fsrc": pd.array([codes.FLOORS_HEIGHT] * n, dtype="uint8")})


def town_plus(footprint, ground, height):
    """The town's seven buildings and one more (gid 7)."""
    b, a = town.buildings()
    return frame([*town.FOOTPRINTS, footprint], [*b.ground, ground], [*b.height, height])


def build_logged(b, a, kind="contours", **kw):
    lines = []
    arrays, rec, g = s02_terrain.build(Path("data/raw/city"), b, a, kind=kind, fixture=False, log=lines.append, **kw)
    return arrays, rec, g, [s for s in lines if s.startswith("hybrid:")]


class CliffDtm:
    """A 5 m model stand-in: the town's cone, the strait at 0 m, and for z 360..480 a 60 m cliff (x 700..840, 61 m)
    behind a 10 m quay strip at 1 m (x 840..850). A 20 m node over the cliff's foot is half cliff, half quay."""
    kind = "dtm"

    def __init__(self, path=None):
        pass

    def sample(self, xz):
        x, z = np.asarray(xz, dtype=np.float64).reshape(-1, 2).T
        band = (z > 360) & (z < 480)
        h = np.where(band & (x >= 700) & (x < 840), 61.0, town.height(x, z))
        h = np.where(band & (x >= 840), 1.0, h)
        return np.where(x >= town.SEA_X, 0.0, h)


def test_a_quay_house_under_a_cliff_is_judged_on_the_source_never_on_the_grid(made, monkeypatch):
    # its MARK_Z is the model's own minimum along its outline: right, so not fixed. The 20 m grid's nodes there mean
    # the cliff and the quay, so judged on the grid it would sit some 30 m under the terrain and be "fixed" up there.
    monkeypatch.setattr(s02_terrain, "DtmSource", CliffDtm)
    quay = town.lbox(842, 400, 848, 420)
    b, a = frame([quay], [1.0], [40.0])
    arrays, record, g, _ = build_logged(b, a, kind="dtm")
    assert record["source"] == "dtm" and g.ground_src.tolist() == [0] and record["fixed"] == 0
    assert g.tmin[0] == pytest.approx(1.0) and g.ground[0] == pytest.approx(1.0) and g.height[0] == pytest.approx(40.0)
    grid = terrain.Grid(record["x0"], record["z0"], record["cell"], record["nx"], record["nz"])
    on_grid = terrain.outline_min(lambda xz: terrain.bilinear(grid, arrays["h"], *np.asarray(xz).T),
                                  terrain.to_local(b.geometry.values))
    assert on_grid[0] - 1.0 > 4 * city.TERRAIN["fix_m"]["dtm"]   # the scenario tells the two apart


def test_a_mark_z_above_the_terrain_stays_out_of_the_tin_and_is_kept(made):
    # gid 7, a deck 25 m above the cone: an outlier the other way. It keeps its MARK_Z (only a MARK_Z too low is
    # fixed) and stays out of the TIN, which would otherwise stand a 25 m spike on the hill around it
    foot = town.lbox(350, 600, 365, 615)
    mark = town.outline_min(foot) + 25.0
    b, a = town_plus(foot, mark, 6.0)
    arrays, record, g, hybrid = build_logged(b, a)
    assert hybrid == ["hybrid: 6 building grounds join the contours' TIN, 2 left out"]    # gids 1 and 7
    assert g.ground_src[7] == 0 and g.ground[7] == pytest.approx(mark) and g.height[7] == pytest.approx(6.0)
    assert g.tmin[7] == pytest.approx(town.outline_min(foot), abs=0.5)
    grid = terrain.Grid(record["x0"], record["z0"], record["cell"], record["nx"], record["nz"])
    X, Z = grid.node_xz()
    near = (np.abs(X - 357.5) <= 40) & (np.abs(Z - 607.5) <= 40)
    assert np.abs(arrays["h"][near] - town.height(X[near], Z[near])).max() < 1.0


def test_grounds_are_judged_on_the_hybrid_tin_not_on_the_contours_alone(made):
    # three houses in a row on a paved strip north of the hill, about 19, 21.5 and 19 m under the contours. The
    # contours alone call the middle one an outlier (more than 20 m), so it stays out of the TIN; its neighbours join
    # it and bring the strip down, and on that TIN the middle one is about 13 m under: not fixed, its MARK_Z kept.
    # Judged on the contours alone it would be raised 21.5 m and lose 21.5 m of its height.
    row = [town.lbox(228, 215, 241, 230), town.lbox(244, 215, 257, 230), town.lbox(260, 215, 273, 230)]
    mark = np.array([town.outline_min(p) for p in row]) - [19.0, 21.5, 19.0]
    b, a = frame(row, mark, [30.0] * 3)
    _, record, g, hybrid = build_logged(b, a)
    assert hybrid == ["hybrid: 2 building grounds join the contours' TIN, 1 left out"]
    assert g.ground_src.tolist() == [0, 0, 0] and record["fixed"] == 0
    assert g.ground.to_numpy() == pytest.approx(mark) and g.height.tolist() == [30.0] * 3
    assert g.tmin[1] - mark[1] < city.TERRAIN["fix_m"]["contours"] - 3


def test_the_unlabelled_contours_are_inferred_again_with_the_shores_and_the_buildings_grounds(made, monkeypatch):
    # From the labels alone, the lines along Söder's quays took the cliff's height (18-22 m). The lake levels
    # come from that first inference; then the unlabelled lines are inferred again knowing every shore at its level
    # and every building ground the first TIN does not call an outlier, and the TIN is built from those heights.
    calls = []
    real = contours.infer_unlabelled

    def spy(*args):
        known = args[2:] if len(args) > 2 and args[2] is not None else None
        calls.append(None if known is None else (np.asarray(known[0]), np.asarray(known[1])))
        return real(*args)

    monkeypatch.setattr(contours, "infer_unlabelled", spy)
    b, a = town.buildings()
    arrays, _, _ = s02_terrain.build(Path("data/raw/city"), b, a, kind="contours", fixture=False, log=lambda *_: None)
    assert len(calls) == 2 and calls[0] is None
    xy, z = calls[1]
    # the buildings' grounds at their representative points: the outlier gid 1 (25 m too low) left out, and the quay
    # house gid 3 too, which lies outside the labelled lines' hull (no first TIN to judge it on)
    reps = shapely.get_coordinates(shapely.point_on_surface(b.geometry.values))
    at = [np.flatnonzero(np.hypot(*(xy - r).T) < 1e-6) for r in reps]
    assert [len(k) for k in at] == [1, 0, 1, 0, 1, 1, 1]
    for g in (0, 2, 4, 5, 6):
        assert z[at[g][0]] == pytest.approx(max(float(b.ground[g]), 0.3))
    # the rest are the shores (in EPSG:3011, like the lines) at their levels: the sea at 0 m, the lake at its own
    shore = np.ones(len(z), dtype=bool)
    shore[np.concatenate(at)] = False
    assert np.unique(z[shore]) == pytest.approx(np.unique(arrays["levels"]), abs=1e-4)
    for ring in (town.to3011(town.lbox(*town.LAKE)).boundary, town.to3011(town.lbox(town.SEA_X, 0, 1000, 800)).boundary):
        assert np.min(np.hypot(*(xy[shore] - np.array(ring.coords[0])).T)) < 1e-6


def test_the_second_inference_knows_the_grounds_anchors_keeps(made, monkeypatch):
    # The buildings whose grounds the second inference knows are anchors()'s, so the LOD1's
    # sheet-line errors stay out of it. With anchors() told to drop gid 5 too, its ground leaves the inference.
    calls, kept = [], []
    real_infer, real_anchors = contours.infer_unlabelled, s02_terrain.anchors

    def spy(*args):
        calls.append(args[2] if len(args) > 2 and args[2] is not None else None)
        return real_infer(*args)

    def without_5(geoms, *args, **kw):
        keep = real_anchors(geoms, *args, **kw)
        keep[5] = False
        kept.append(keep.copy())
        return keep

    monkeypatch.setattr(contours, "infer_unlabelled", spy)
    monkeypatch.setattr(s02_terrain, "anchors", without_5)
    b, a = town.buildings()
    s02_terrain.build(Path("data/raw/city"), b, a, kind="contours", fixture=False, log=lambda *_: None)
    reps = shapely.get_coordinates(shapely.point_on_surface(b.geometry.values))
    at = [int((np.hypot(*(calls[1] - r).T) < 1e-6).sum()) for r in reps]
    assert kept and at == kept[0].astype(int).tolist() == [1, 0, 1, 0, 1, 0, 1]


def test_the_lake_levels_come_from_the_lines_the_tin_is_built_from(made, monkeypatch):
    # The final review's PIPELINE-1: the levels came from the first inference's lines while the TIN was built from the
    # second's. On the city the second inference re-heighted pond 41's own shore line from 12 to 6 m, and the pond
    # stood 2.1 m above every bank. Here the second inference moves the unlabelled lines 4 m down (the 24 m circle,
    # 20 m beyond the lake's shore ring, among them), so the lake's shore reads lower on the lines the TIN uses.
    real = contours.infer_unlabelled

    def lower(lines, h, *known):
        out, src = real(lines, h)                 # the same lines whatever the known points, so the runs compare
        return np.where(src == "inferred", out - 4.0, out), src

    def second_lower(lines, h, *known):
        return lower(lines, h) if known and known[0] is not None else real(lines, h)

    b, a = town.buildings()

    def levels(infer):
        monkeypatch.setattr(contours, "infer_unlabelled", infer)
        arrays, _, _ = s02_terrain.build(Path("data/raw/city"), b, a, kind="contours", fixture=False,
                                         log=lambda *_: None)
        return arrays["levels"].tolist()

    plain, moved, both = levels(real), levels(second_lower), levels(lower)
    assert both[1] < plain[1] - 0.5               # the move reaches the lake's shore ring
    # the levels follow the lines the TIN is built from: the second inference's, as when both inferences give them
    assert moved == both and moved[0] == plain[0] == 0.0


# The LOD1's sheet-line errors: buildings on the 1 km sheet edges whose MARK_Z is up to 20 m too low
# pass the hybrid's 20 m test, and as anchors they pulled unlabelled lines down (pits in Vasastan and on Södermalm; gid
# 28062, a villa on a 40 m hill, kept at 9.5 m). A sheet town in EPSG:3011 round the edge E = 154000 on a 35 m hill.
E0, N0 = 154000.0, 6578445.0


def house(e, n=N0, w=10.0):
    return shapely.box(e - w / 2, n - 5, e + w / 2, n + 5)


def sheet_town():
    """(outlines, MARK_Z, tmin): six houses on the hill, the fourth straddling the sheet edge 17 m too low (it passes
    the 20 m test); a quay house 400 m from any edge, 27 m under its neighbours on the cliff top; and a lone house on
    the edge N = 6580000 with no neighbour, 25 m under the first TIN."""
    geoms = [house(E0 - 55), house(E0 - 35), house(E0 - 15), house(E0), house(E0 + 15), house(E0 + 35),
             house(E0 + 400), house(E0 + 420), house(E0 + 440), house(156505.0, 6580000.0)]
    mark_z = np.array([35.0, 35.5, 34.5, 18.0, 35.0, 36.0, 3.0, 30.0, 30.5, 5.0])
    tmin = np.array([35.0, 35.0, 35.0, 35.0, 35.0, 35.0, 15.0, 30.0, 30.0, 30.0])
    return np.array(geoms, dtype=object), mark_z, tmin


def test_sheet_line_lows_are_the_lod1s_edge_errors_not_the_quays():
    geoms, mark_z, tmin = sheet_town()
    assert s02_terrain.sheet_edge_m(geoms)[[0, 3, 4, 6]] == pytest.approx([50.0, 0.0, 10.0, 395.0])
    low = s02_terrain.sheet_line_lows(geoms, mark_z, tmin)
    # the house on the edge 17 m under its neighbours, and the lone one 25 m under the TIN; never the quay house
    # (far from an edge) nor the house 10 m from the edge at its neighbours' height
    assert np.flatnonzero(low).tolist() == [3, 9]
    keep = s02_terrain.anchors(geoms, mark_z, tmin, city.TERRAIN["fix_m"]["contours"])
    assert np.flatnonzero(~keep).tolist() == [3, 9]


def test_a_sheet_line_error_beside_another_is_not_masked_by_it():
    # The final review's PIPELINE-2 (gid 42975): a house straddling the sheet edge 11 m too low whose only neighbour
    # within 50 m is another sheet-line error, 39 m too low. Their median is that neighbour's 1.5 m, so the first house
    # passed as an anchor and dug a 9 m crater, and two houses beside it were "fixed" into it. A second pass takes the
    # median over anchors only (within fix_m of tmin and not flagged by the first pass), and where none is left the
    # TIN's own minimum along the outline: both are flagged. The houses around, 70 to 150 m off, stand at 40 m.
    geoms = np.array([house(E0, N0 + 20, 8), house(E0 + 12, N0 + 20, 8), house(E0 - 90, N0 + 100),
                      house(E0 + 100, N0 + 120), house(E0 + 60, N0 + 160)], dtype=object)
    mark_z = np.array([29.0, 1.5, 40.0, 40.5, 39.6])
    tmin = np.array([40.3, 40.0, 40.0, 40.4, 39.8])
    assert s02_terrain.sheet_edge_m(geoms)[:2].tolist() == [0.0, 8.0]
    assert np.flatnonzero(s02_terrain.sheet_line_lows(geoms, mark_z, tmin)).tolist() == [0, 1]
    assert np.flatnonzero(s02_terrain.anchors(geoms, mark_z, tmin, 20.0)).tolist() == [2, 3, 4]


def test_a_sheet_line_error_does_not_move_an_unlabelled_line():
    # labelled lines at 20, 30, 40 and 50 m across the hill, a short unlabelled one (true 36 m) passing the houses,
    # 15 m from the low one
    import geopandas as gpd
    ns = [N0 - 145, N0 - 45, N0 + 55, N0 + 155, N0 + 15]
    lines = gpd.GeoDataFrame({"ten": [True, True, True, True, False]},
                             geometry=[shapely.LineString([(E0 - 300, n), (E0 + 300, n)]) for n in ns[:4]]
                             + [shapely.LineString([(E0 - 20, ns[4]), (E0 + 20, ns[4])])], crs=3011)
    h = np.array([20.0, 30.0, 40.0, 50.0, np.nan])
    geoms, mark_z, tmin = sheet_town()
    hill = np.arange(6)
    rep = shapely.get_coordinates(shapely.point_on_surface(geoms[hill]))

    def line(mask):
        return contours.with_heights(lines, h, (rep[mask], mark_z[hill][mask])).h.iloc[4]

    keep = s02_terrain.anchors(geoms, mark_z, tmin, city.TERRAIN["fix_m"]["contours"])[hill]
    everyone = np.ones(6, dtype=bool)
    without = everyone.copy()
    without[3] = False
    assert line(everyone) < line(without)            # the low house as an anchor pulls the line down ...
    assert line(keep) == line(without) == 36.0       # ... and anchors() leaves it out


def test_a_sheet_line_error_is_kept_out_of_the_tins_and_fixed_from_8_m(made, monkeypatch):
    # a sheet edge across the town (E = 154500 is x = 474.9) and a house straddling it on the hill, 12 m too low: it
    # passes the 20 m test, but as a sheet-line error it joins neither TIN, and 12 m under the TIN it is fixed
    monkeypatch.setattr(s02_terrain, "SHEET_M", 500.0)
    fp = town.lbox(470, 600, 480, 610)
    true = town.outline_min(fp)
    b, a = town_plus(fp, true - 12.0, 20.0)
    _, _, g, hybrid = build_logged(b, a)
    assert hybrid == ["hybrid: 6 building grounds join the contours' TIN, 2 left out (1 on a sheet edge)"]
    assert g.ground_src[7] == 1 and g.ground[7] == pytest.approx(true, abs=0.5)
    assert g.height[7] == pytest.approx(20.0 - (g.ground[7] - (true - 12.0)), abs=1e-3)   # the roof stays
    # off the sheet edge, the same house is a plain building 12 m under the contours: kept and not fixed (fix_m 20)
    monkeypatch.setattr(s02_terrain, "SHEET_M", 1000.0)
    _, _, g, hybrid = build_logged(b, a)
    assert g.ground_src[7] == 0 and hybrid == ["hybrid: 7 building grounds join the contours' TIN, 1 left out"]


def test_the_record_counts_the_buildings_the_full_terrace_leaves_floating(made):
    # The final review's PIPELINE-3: the terrace caps every node of every cell a footprint touches at the lowest such
    # building's ground + 0.3 m, so a higher building sharing a cell with a lower one stands over the notch. Two
    # houses in one 20 m cell on the hill's slope, the second on a strip 10 m lower: the first floats about 10 m above
    # the ground at its outline's highest point. s02_terrain counts the buildings more than FLOAT_M (3 m) above it.
    high, low = town.lbox(402, 562, 410, 570), town.lbox(412, 562, 418, 570)
    b, a = frame([high, low], [town.outline_min(high), town.outline_min(low) - 10.0], [9.0, 9.0])
    lines = []
    _, record, g = s02_terrain.build(Path("data/raw/city"), b, a, kind="contours", fixture=False, log=lines.append)
    assert s02_terrain.FLOAT_M == 3.0 and record["floating"] == 1 and g.ground_src.tolist() == [0, 0]
    assert "terrace cuts " in lines[2] and ", floating 1 buildings more than 3 m above it;" in lines[2]
    # alone, the high house stands on its own cut: nothing floats
    b, a = frame([high], [town.outline_min(high)], [9.0])
    assert s02_terrain.build(Path("data/raw/city"), b, a, kind="contours", fixture=False,
                             log=lambda *_: None)[1]["floating"] == 0


def test_the_record_names_the_relief_its_burial_count_was_made_at(made):
    # the Hills slider's review (S5): buried is counted at relief_max, and s99 compares the two, so a count made at
    # another relief (the 3x before the slider) is caught; the log names the default's count as well
    lines = []
    b, a = town.buildings()
    _, record, _ = s02_terrain.build(Path("data/raw/city"), b, a, kind="contours", fixture=False, log=lines.append)
    assert record["relief_max"] == city.TERRAIN["relief_max"] == 2.5
    assert lines[2].endswith(f"{record['buried']} buildings buried at 2.5x (0 at the 1x default)")


def test_the_record_carries_the_hashes_of_the_buildings_and_attributes_it_read(made):
    import hashlib
    _, record, _ = run(made, "--source", "contours")
    for name in ("buildings", "attributes"):
        assert record[f"{name}_sha256"] == hashlib.sha256((made / "data" / f"{name}.parquet").read_bytes()).hexdigest()


def test_nodes_inside_a_lake_away_from_land_hold_its_level():
    # PIPELINE-7 (S9): the camera's floor and target and the water names read these nodes. A 200 m lake
    # in flat land at 20 m: nodes more than `burn` rings from land take the lake's level, never the sea's.
    class Flat:
        kind = "contours"

        def sample(self, xz):
            return np.full(len(np.asarray(xz).reshape(-1, 2)), 20.0)

    grid = terrain.grid_for((0.0, 0.0, 400.0, 400.0), 20.0)
    lake = shapely.box(100, 100, 300, 300)
    land = shapely.box(0, 0, 400, 400).difference(lake)
    h, use = s02_terrain.build_grid(Flat(), grid, land, [lake], [12.5], city.TERRAIN)
    X, Z = grid.node_xz()
    inner = (X >= 160) & (X <= 240) & (Z >= 160) & (Z <= 240)
    assert inner.sum() == 25 and not use[inner].any() and (h[inner] == 12.5).all()
    assert (h[use] == 20.0).all()


def test_the_dtm_is_sampled_at_its_pixel_centres(tmp_path):
    # PIPELINE-7 (S11): rasterio's inverse transform puts a pixel's centre at .5; without the half-pixel offset the
    # whole model would shift 2.5 m. A 5 m model whose pixel (r, c) holds 100 r + c reads exactly that at its centre.
    import rasterio
    from rasterio.transform import Affine
    e0, n0 = city.ORIGIN
    z = np.add.outer(100.0 * np.arange(8), np.arange(8)).astype("float32")
    path = tmp_path / "dtm5.tif"
    with rasterio.open(path, "w", driver="GTiff", height=8, width=8, count=1, dtype="float32", crs=f"EPSG:{city.CRS}",
                       transform=Affine(5, 0, e0 - 20, 0, -5, n0 + 20), nodata=np.nan) as dst:
        dst.write(z, 1)
    src = s02_terrain.DtmSource(path)
    r, c = np.array([2, 3, 5, 6]), np.array([4, 1, 5, 2])
    centres = np.c_[-20 + 5 * c + 2.5, -20 + 5 * r + 2.5]          # local x = E - E0, z = N0 - N
    assert src.sample(centres).tolist() == (100.0 * r + c).tolist()
    # halfway between two pixels, the mean of the two
    assert src.sample(np.array([[-20 + 5 * 4 + 5.0, -20 + 5 * 2 + 2.5]]))[0] == pytest.approx(204.5)


def test_a_lakes_shore_reads_the_5th_percentile_of_the_land_along_its_ring():
    # PIPELINE-7 (S5): the level of a lake without a flat laser surface is its shore ring's 5th percentile minus the
    # offset. A source that rises eastwards: along the ring 20 m outside a 100 m lake x runs 80..220, so
    # the 5th percentile reads 80 to 86, where the median would read 150.
    class East:
        kind = "contours"

        def sample(self, xz):
            return np.asarray(xz, dtype=np.float64).reshape(-1, 2)[:, 0]

    lake = shapely.box(100, 100, 200, 200)
    land = shapely.box(-500, -500, 800, 800).difference(lake)
    p5 = s02_terrain.ring_samples(East(), [lake], land)[0]
    assert 80.0 <= p5 < 86.0


def test_the_datum_is_mark_z_minus_the_model(made, monkeypatch):
    # PIPELINE-7 (S8): a model reading 0.4 m above the grounds' own heights gives a datum of -0.4 m (MARK_Z - model),
    # the sign s99 and the terrain's About note read
    class Raised(CliffDtm):
        def sample(self, xz):
            x, z = np.asarray(xz, dtype=np.float64).reshape(-1, 2).T
            return np.where(x >= town.SEA_X, 0.0, town.height(x, z)) + 0.4

    monkeypatch.setattr(s02_terrain, "DtmSource", Raised)
    b, a = town.buildings()
    _, record, _ = s02_terrain.build(Path("data/raw/city"), b, a, kind="dtm", fixture=False, log=lambda *_: None)
    assert record["datum"] == pytest.approx(-0.4, abs=0.02)


def test_attributes_for_other_buildings_are_refused(made):
    # a gid attributes.parquet lacks (s01_load ran again since s02_attributes) would ship 0 floors: refused, before
    # anything is built or written
    a = pd.read_parquet(made / "data" / "attributes.parquet")
    a[a.gid != 5].to_parquet(made / "data" / "attributes.parquet")
    with pytest.raises(SystemExit, match=r"no floors for 1 of the buildings \(gid 5 first\): run s02_attributes first"):
        s02_terrain.main(["--source", "contours"])
    assert not (made / "data" / "terrain.json").exists()


def test_the_hash_is_of_the_buildings_it_read(made, monkeypatch):
    # an s01_load that replaces buildings.parquet while s02_terrain runs: the record keeps the hash of the file it
    # read, so s03_tiles and s04_base refuse its outputs instead of shipping them as the new buildings' terrain
    import hashlib

    from pipeline import s03_tiles
    path = made / "data" / "buildings.parquet"
    first = path.read_bytes()
    real = s02_terrain.gpd.read_parquet

    def read_then_reload(p, *args, **kw):
        out = real(p, *args, **kw)
        if Path(p).name == "buildings.parquet":
            b, _ = town.buildings()
            b.assign(height=b.height + 1).to_parquet(path)       # s01_load writes newer buildings
        return out

    monkeypatch.setattr(s02_terrain.gpd, "read_parquet", read_then_reload)
    _, record, _ = run(made, "--source", "contours")
    now = hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["buildings_sha256"] == hashlib.sha256(first).hexdigest() != now
    with pytest.raises(SystemExit, match="run s02_terrain again"):
        s03_tiles.check_built_from(record, made / "data")


def test_the_runner_can_hand_s02_terrain_a_version_with_the_steps_after_it(made):
    # the README's rebuild after a DTM fetch is one line, `pipeline.run s02_terrain s03_tiles ... -- --version <v>`,
    # and the runner hands every step the same arguments: s02_terrain takes --version and ignores it (it writes data/)
    _, record, _ = run(made, "--source", "contours", "--version", "v20990101-dtm")
    assert record["source"] == "contours"


def test_a_second_run_gives_the_same_terrain(made):
    # s02_terrain is deterministic: the same raw files give the same arrays, record and ground.parquet bytes
    a1, r1, _ = run(made, "--source", "contours")
    g1 = (made / "data" / "ground.parquet").read_bytes()
    a2, r2, _ = run(made, "--source", "contours")
    assert r1 == r2 and (made / "data" / "ground.parquet").read_bytes() == g1
    assert a1.keys() == a2.keys() and all(np.array_equal(a1[k], a2[k]) for k in a1)


def test_dtm_build_takes_the_flat_lake_and_the_sea_from_the_model(made):
    town.write_dtm(made / "data" / "raw" / "dem" / "dtm5.tif", lake_level=27.5, sea_level=0.1)
    arrays, record, g = run(made)                       # auto: the DTM is there
    assert record["source"] == "dtm"
    assert arrays["levels"].tolist() == [0.0, pytest.approx(27.5)]
    assert record["sea"] == pytest.approx(0.1)          # the model's own sea: a second reading of the datum
    grid = terrain.Grid(record["x0"], record["z0"], record["cell"], record["nx"], record["nz"])
    X, Z = grid.node_xz()
    land = arrays["use"] & (X > 40) & (X < 800) & (Z > 40) & (Z < 760) & ~((X > 180) & (X < 320) & (Z > 280) & (Z < 420))
    assert np.abs(arrays["h"][land] - town.height(X[land], Z[land])).max() < 0.3
    # 25 m too low is over the DTM's 5 m threshold too; gid 4, 15 m under the model, would get a roof under the
    # ground, so it keeps its MARK_Z and the terrace cuts the slope behind it (more than the old 8 m cap allowed)
    assert g.ground_src.tolist() == [0, 1, 0, 0, 0, 0, 0] and record["buried"] == 0
    assert arrays["cut"][nodes_under(grid, town.FOOTPRINTS[4])].max() > 8.0
    assert abs(record["datum"]) < 0.1                    # MARK_Z is the outline minimum by construction


def test_fixture_builds_grid_only_around_the_fixture_box(made, monkeypatch):
    # HFH_FIXTURE=1 cuts the domain to city.FIXTURE_BBOX plus the margin; the town lies far from Gamla stan, so the
    # cut leaves nothing to grid. Moving the box over the town shows the grid shrink to it.
    e0, n0 = city.ORIGIN
    monkeypatch.setattr(city, "FIXTURE_BBOX", (e0 + 0, n0 - 400, e0 + 300, n0 - 0))
    monkeypatch.setattr(city, "TERRAIN", {**city.TERRAIN, "fixture_margin": 100.0})
    monkeypatch.setenv("HFH_FIXTURE", "1")
    arrays, record, _ = run(made, "--source", "contours")
    assert record["fixture"] is True and record["nx"] < 53 and record["nz"] <= 43
    # s04_base cuts its land and water to the same domain: the lake alone (the strait lies outside the box), one level
    # per water polygon it ships
    (made / "web" / "data").mkdir(parents=True)
    (made / "web" / "data" / "current.json").write_text('{"version":"v20990101"}')
    s04_base.main([])
    out = made / "web" / "data" / "v20990101"
    water = s04_base.unpack(gzip.decompress((out / "water.bin.gz").read_bytes()))
    d = terrain.unpack(gzip.decompress((out / "terrain.bin.gz").read_bytes()))
    assert len(arrays["levels"]) == len(d["levels"]) == len(water) == 1
    assert (d["grid"].nx, d["grid"].nz) == (record["nx"], record["nz"])


def test_s04_base_writes_terrain_that_matches_the_grid_and_the_water(made):
    run(made, "--source", "contours")
    (made / "web" / "data").mkdir(parents=True)
    (made / "web" / "data" / "current.json").write_text('{"version":"v20990101"}')
    s04_base.main([])
    out = made / "web" / "data" / "v20990101"
    d = terrain.unpack(gzip.decompress((out / "terrain.bin.gz").read_bytes()))
    water = s04_base.unpack(gzip.decompress((out / "water.bin.gz").read_bytes()))
    record = json.loads((made / "data" / "terrain.json").read_text())
    assert (d["grid"].nx, d["grid"].nz, d["grid"].x0) == (record["nx"], record["nz"], record["x0"])
    assert len(d["levels"]) == len(water) == 2
    assert d["n_shore"] == sum(len(r) for poly in water for r in poly)
    # the strait's edge along the municipality's boundary (x = 1000) is no shore: no quay wall stands in the sea
    bits = np.unpackbits(np.frombuffer(d["shore"], np.uint8), bitorder="little")[:d["n_shore"]]
    k, flags = 0, []
    for poly in water:
        for ring in poly:
            nxt = np.roll(ring, -1, axis=0)
            on_edge = (np.abs(ring[:, 0] - 1000) < 0.01) & (np.abs(nxt[:, 0] - 1000) < 0.01)
            flags.append((bits[k:k + len(ring)].astype(bool), on_edge))
            k += len(ring)
    assert all((f[e] == 0).all() for f, e in flags) and any(e.any() for _, e in flags)
    # the lake's 4 sides and the strait's west side; its north, east and south sides lie on the boundary
    assert sum(int(f.sum()) for f, _ in flags) == 5
    assert (d["cls"] == terrain.EDGE).sum() == d["n_edge"] > 0


def test_the_log_counts_the_terraced_nodes_that_ship(made, monkeypatch, capsys):
    # terrain.bin stores the cut in whole decimetres, so a node cut by under about 5 cm ships uncut: the log counts
    # the nodes that ship (on the whole city's contour build of 2026-10-16, 184,580 of the 189,822 cut at all)
    real = terrain.terrace_cut

    def with_hairs(*args, **kw):
        cut = real(*args, **kw)
        cut[0, :10] += 0.02                     # ten nodes on the grid's outer row, cut by 2 cm
        return cut

    monkeypatch.setattr(terrain, "terrace_cut", with_hairs)
    arrays, _, _ = run(made, "--source", "contours")
    (made / "web" / "data").mkdir(parents=True)
    (made / "web" / "data" / "current.json").write_text('{"version":"v20990101"}')
    s04_base.main([])
    d = terrain.unpack(gzip.decompress((made / "web" / "data" / "v20990101" / "terrain.bin.gz").read_bytes()))
    shipped = int((d["cut"] > 0).sum())
    assert int((arrays["cut"] > 0).sum()) == shipped + 10 and s02_terrain.terraced_nodes(arrays["cut"]) == shipped
    assert f"terrace cuts {shipped:,} nodes (max " in capsys.readouterr().out
    assert s02_terrain.terraced_nodes(np.array([0.0, 0.01, 0.04, 0.06, 0.15, 20.0])) == 3


REAL = Path("data/terrain.json")


@pytest.mark.network
def test_real_stockholm_terrain():
    # After `uv run python -m pipeline.run s02_terrain` on the whole city. The ranges hold for both sources:
    # the contour stand-in (v20261016-m4e) gave 79 sea pieces, 91 lakes, 37 fixed grounds, a datum of +0.14 m, 3
    # buildings buried at 2.5x and 1,412 standing more than 3 m over the terrace's cut.
    if not REAL.exists():
        pytest.skip("data/terrain.json is missing: run s02_terrain")
    rec = json.loads(REAL.read_text())
    if rec["fixture"]:
        pytest.skip("data/ holds a fixture build")
    assert (rec["nx"], rec["nz"], rec["x0"], rec["z0"]) == (1255, 1190, -17660.0, -12860.0)
    assert rec["levels"] == 170 and 80 <= rec["lakes"] <= 100
    assert abs(rec["datum"]) <= city.TERRAIN["datum_max"] and rec["buried"] <= city.TERRAIN["buried_max"]
    assert rec["relief_max"] == city.TERRAIN["relief_max"] and isinstance(rec["floating"], int)
    # a few tens of grounds on the LOD1's sheet lines. More than 100 on Lantmäteriet's model is a finding to
    # investigate (the log lists the 20 that moved most), never a reason to widen this range.
    assert 5 <= rec["fixed"] <= 100
    g = pd.read_parquet(Path("data/ground.parquet"))
    assert len(g) >= city.MIN_BUILDINGS and g.ground.min() >= 0.3 - 1e-6
    assert g.height.min() > 0 and g.height.max() <= 200


def test_a_repaired_ground_keeps_the_floors_openstreetmap_gives():
    # S02_terrain recomputed every repaired ground's floors from its new height, and the
    # card still labelled them "(OpenStreetMap)"; only floors from the height rule follow the height
    b = synth.buildings(rows=[
        {"geometry": synth.square(0, 0, 20), "kategori": "Flerbostadshus", "ground": 0.0, "height": 30.0},
        {"geometry": synth.square(50, 0, 20), "kategori": "Flerbostadshus", "ground": 0.0, "height": 30.0}])
    attrs = pd.DataFrame({"gid": pd.array([0, 1], dtype="int32"), "floors": pd.array([3, 9], dtype="uint8"),
                          "fsrc": pd.array([codes.FLOORS_OSM, codes.FLOORS_HEIGHT], dtype="uint8")})
    g = s02_terrain.ground_table(b, attrs, np.array([25.0, 25.0]), "contours", city.TERRAIN)
    assert g.ground_src.tolist() == [s02_terrain.GROUND_TERRAIN] * 2
    assert g.floors[0] == 3                                       # OpenStreetMap's, as the card says
    assert g.floors[1] == floors_from_height(g.height.to_numpy()[1:], np.array(["Flerbostadshus"]))[0] != 9

