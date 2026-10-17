"""pipeline/terrain.py: the grid, the water levels, the ground fix, the terrace and the
terrain.bin layout, on small synthetic inputs."""
import struct

import numpy as np
import pytest
import shapely

from pipeline import city, terrain


def test_grid_nodes_sit_on_multiples_of_the_cell_and_cover_the_box_plus_one_cell():
    g = terrain.grid_for((-17_623.0, -12_834.0, 7_392.0, 10_897.0), 20.0)   # the municipality's local box
    assert (g.x0, g.z0) == (-17_660.0, -12_860.0)                           # the spike's grid, 2026-10-15
    assert (g.nx, g.nz) == (1255, 1190)
    assert g.x0 % 20 == 0 and g.z0 % 20 == 0
    assert g.x0 + (g.nx - 1) * g.cell >= 7_392.0 + 20 and g.z0 + (g.nz - 1) * g.cell >= 10_897.0 + 20
    assert city.TILE % g.cell == 0                                           # nodes line up with the 1200 m tiles


def test_node_means_average_only_the_land_sub_samples():
    v = np.arange(16, dtype=np.float32).reshape(4, 4)        # one node, 4 x 4 sub-samples
    land = np.zeros((4, 4), bool)
    land[:, :2] = True                                         # the west half is land
    mean, is_land = terrain.node_means(v, land, 4)
    assert mean[0, 0] == pytest.approx(np.mean(v[:, :2])) and is_land[0, 0]
    mean, is_land = terrain.node_means(v, np.zeros((4, 4), bool), 4)
    assert np.isnan(mean[0, 0]) and not is_land[0, 0]


def test_burn_in_carries_bank_heights_two_nodes_out_and_no_further():
    h = np.full((1, 6), np.nan, np.float32)
    land = np.array([[True, True, False, False, False, False]])
    h[0, :2] = [5.0, 7.0]
    out, burnt = terrain.burn_in(h, land, 2)
    assert out[0, :4].tolist() == [5.0, 7.0, 7.0, 7.0]          # the bank height reaches the shore
    assert burnt[0].tolist() == [False, False, True, True, False, False]
    assert np.isnan(out[0, 4:]).all()


def test_a_land_node_the_source_missed_takes_its_nearest_land_value():
    h = np.array([[3.0, np.nan, np.nan]], np.float32)
    out, _ = terrain.burn_in(h, np.array([[True, True, False]]), 1)
    assert out[0].tolist() == [3.0, 3.0, 3.0]


def test_water_systems_join_pieces_across_a_bridge_only():
    a, b, c = shapely.box(0, 0, 100, 10), shapely.box(140, 0, 200, 10), shapely.box(400, 0, 500, 10)
    s = terrain.water_systems([a, b, c], bridge_m=30.0)   # a and b are 40 m apart (a bridge), c is 200 m off
    assert s[0] == s[1] != s[2]


def test_lake_levels_snap_the_sea_and_keep_every_lake_at_its_own():
    kw = dict(water_z=0.0, sea_max=3.0, offset=1.0)
    nan = np.nan
    # 0, 1: the sea in two pieces (one shore reads 5 m on a paved quay: its system's lowest shore decides)
    # 2, 3: two lakes joined by a stream (Magelungen and Flaten): each keeps its own level, never the system's
    # 4: a lake whose own shore has no land sample takes its system's lowest shore
    ring = np.array([1.2, 5.0, 22.0, 24.0, nan])
    inner = np.full(5, nan)
    systems = np.array([0, 0, 1, 1, 1])
    lv = terrain.lake_levels(ring, inner, systems, **kw)
    assert lv.tolist() == [0.0, 0.0, 21.0, 23.0, 21.0]
    # a laser model's flat water wins over the shore when there is one
    inner[3] = 22.6
    assert terrain.lake_levels(ring, inner, systems, **kw)[3] == pytest.approx(22.6)
    # never below the sea
    assert terrain.lake_levels(np.array([3.5]), np.array([nan]), np.array([0]), **kw).tolist() == [2.5]
    assert terrain.lake_levels(np.array([3.2]), np.array([-4.0]), np.array([0]), **kw).tolist() == [0.0]
    # a system with no shore sample at all: each piece takes the terrain inside it where the source has one (floored
    # at the sea), else the sea; never 0 m for a lake the laser model saw at 12.5 m
    none = np.full(3, nan)
    assert terrain.lake_levels(none, np.array([12.5, nan, -2.0]), np.zeros(3, int), **kw).tolist() == [12.5, 0.0, 0.0]


def test_bilinear_matches_the_viewer_and_clamps_at_the_edge():
    g = terrain.Grid(0.0, 0.0, 20.0, 3, 2)
    h = np.array([[0.0, 10.0, 20.0], [4.0, 14.0, 24.0]])
    assert terrain.bilinear(g, h, 10.0, 10.0) == pytest.approx(7.0)
    assert terrain.bilinear(g, h, 40.0, 20.0) == pytest.approx(24.0)
    assert terrain.bilinear(g, h, 500.0, -50.0) == pytest.approx(20.0)   # clamped to the corner node


def test_outline_min_is_the_lowest_ground_along_the_outline_from_the_source_itself():
    rises = lambda p: 0.1 * p[:, 0]                 # noqa: E731 (rises 1 m per 10 m eastwards)
    poly = shapely.box(50, 50, 90, 70)
    assert terrain.outline_min(rises, [poly])[0] == pytest.approx(5.0)
    # a source with no value along an outline (outside the TIN) gives NaN, never a minimum of nothing
    assert np.isnan(terrain.outline_min(lambda p: np.full(len(p), np.nan), [poly])[0])


def test_fix_grounds_replaces_a_ground_too_low_and_keeps_the_roof():
    ground, height, fixed = terrain.fix_grounds(
        mark_z=[11.2, 30.0, 30.0, 30.0, 30.0], height=[56.9, 10.0, 10.0, 10.0, 10.0],
        tmin=[52.0, 31.0, 50.0, 12.0, np.nan], fix_m=5.0)
    # gid 0 is the spike's worst case (Mälarhöjden: 11.2 m on ground of about 52); 1 is within 5 m; 2 would leave a
    # roof under the ground (height -10 m): kept; 3 stands 18 m above the terrain (a deck, a bridge): kept, its
    # skirts reach down; 4 has no terrain under it
    assert fixed.tolist() == [True, False, False, False, False]
    assert ground.tolist() == [52.0, 30.0, 30.0, 30.0, 30.0]
    assert height[0] == pytest.approx(16.1) and height.tolist()[1:] == [10.0] * 4


def test_burial_is_how_far_the_drawn_ground_rises_above_the_base():
    g = terrain.Grid(0.0, 0.0, 20.0, 6, 6)
    X, Z = g.node_xz()
    h = 0.2 * X
    poly = shapely.box(25, 25, 55, 35)                  # its outline's highest drawn ground: x 55, 11 m
    assert terrain.burial(g, h, np.zeros_like(h), [poly], [6.0], relief=3.0)[0] == pytest.approx(3 * (11 - 6))
    cut = terrain.terrace_cut(g, h, [poly], [6.0], up=0.3, max_cut=20.0)
    assert terrain.burial(g, h, cut, [poly], [6.0], relief=3.0)[0] == pytest.approx(3 * 0.3)


def test_terrace_cuts_every_node_of_the_cells_a_footprint_touches():
    g = terrain.Grid(0.0, 0.0, 20.0, 6, 6)
    X, Z = g.node_xz()
    h = 0.2 * X                                         # 4 m per cell eastwards
    poly = shapely.box(25, 25, 55, 35)                  # touches cells i 1..2, j 1
    cut = terrain.terrace_cut(g, h, [poly], [6.0], up=0.3, max_cut=8.0)
    capped = cut > 0
    # the nodes of cells (1..2, 1): i 1..3, j 1..2; only those above 6.3 m (x >= 40) are cut
    assert np.argwhere(capped).tolist() == [[1, 2], [1, 3], [2, 2], [2, 3]]
    assert cut[1, 2] == pytest.approx(8.0 - 6.3) and cut[1, 3] == pytest.approx(min(12.0 - 6.3, 8.0))
    # the lower building wins where two touch the same cell; nothing is cut away from footprints
    cut2 = terrain.terrace_cut(g, h, [poly, shapely.box(45, 22, 50, 28)], [6.0, 2.0], up=0.3, max_cut=8.0)
    assert cut2[1, 2] == pytest.approx(8.0 - 2.3)
    assert cut2[4:, :].max() == 0
    # ... in either order (not just the last one drawn)
    assert terrain.terrace_cut(g, h, [shapely.box(45, 22, 50, 28), poly], [2.0, 6.0], up=0.3,
                               max_cut=8.0)[1, 2] == pytest.approx(8.0 - 2.3)
    # and no node is cut by more than max_cut
    assert terrain.terrace_cut(g, h, [poly], [6.0], up=0.3, max_cut=2.0).max() == pytest.approx(2.0)


def test_terrace_refuses_a_ground_that_is_not_finite():
    # one NaN ground would wipe the caps of every cell it touches, and its neighbours' with them
    g = terrain.Grid(0.0, 0.0, 20.0, 6, 6)
    X, Z = g.node_xz()
    with pytest.raises(ValueError, match="grounds must be finite"):
        terrain.terrace_cut(g, 0.2 * X, [shapely.box(25, 25, 55, 35), shapely.box(45, 22, 50, 28)], [6.0, np.nan],
                            up=0.3, max_cut=8.0)


def test_the_predictor_round_trips_every_int16():
    rng = np.random.default_rng(3)
    h = rng.integers(-32768, 32767, size=(9, 11)).astype(np.int16)
    assert np.array_equal(terrain.unpredict(terrain.predict(h)), h)
    smooth = (100 + np.add.outer(np.arange(40), np.arange(50)) * 7).astype(np.int16)
    assert np.count_nonzero(terrain.predict(smooth)) == 40 + 50 - 1   # a plane leaves only the first row and column


def land_with_bay():
    """Land over x 0..100, z 0..60 with a bay cut out of its east side, in a domain of the same box."""
    domain = shapely.box(0, 0, 100, 60)
    land = domain.difference(shapely.Polygon([(70, 10), (100, 10), (100, 50), (55, 50)]))
    return domain, land


def test_classes_and_rings_cover_the_land_exactly():
    domain, land = land_with_bay()
    g = terrain.grid_for(domain.bounds, 20.0)            # x0 = z0 = -20, 8 x 6 nodes
    cls, stream, n_edge = terrain.classes_and_rings(g, land, domain)
    assert cls.shape == (g.nz - 1, g.nx - 1)
    assert n_edge == int((cls == terrain.EDGE).sum()) > 0
    area = (cls == terrain.LAND).sum() * g.cell ** 2
    cells = list(zip(*np.nonzero(cls == terrain.EDGE)))
    for (j, i), polys in zip(cells, terrain.read_rings(stream, n_edge)):
        for rings in polys:
            pts = [r.astype(float) / terrain.RING_SCALE * g.cell + (g.x0 + i * g.cell, g.z0 + j * g.cell) for r in rings]
            area += shapely.Polygon(pts[0], pts[1:]).area
    assert area == pytest.approx(land.area, rel=1e-3)   # R3: the edge rings plus the land cells are the land
    # the cells beyond the domain are outside; the bay's cells are water in the domain
    assert cls[0, 0] == terrain.OUTSIDE and cls[2, 5] in (terrain.WATER, terrain.EDGE)


def test_a_cell_corner_quantises_exactly_so_neighbours_meet():
    q = terrain.quantise_ring(np.array([[20.0, 40.0], [40.0, 40.0], [40.0, 60.0]]), 20.0, 40.0, 20.0)
    assert q.tolist() == [[0, 0], [255, 0], [255, 255]]


def test_shore_bits_leave_out_the_edges_on_the_domain_boundary():
    domain = shapely.box(0, 0, 100, 100)
    strait = np.array([[80.0, 0.0], [100.0, 0.0], [100.0, 100.0], [80.0, 100.0]])   # cut off by the boundary at x = 100
    bits, n = terrain.shore_bits([[strait]], shapely.boundary(domain))
    assert n == 4
    flags = np.unpackbits(np.frombuffer(bits, np.uint8), bitorder="little")[:n].tolist()
    # segments: (80,0)-(100,0) on the boundary, (100,0)-(100,100) on it, (100,100)-(80,100) on it, (80,100)-(80,0) shore
    assert flags == [0, 0, 0, 1]


def test_pack_and_unpack_round_trip_the_c16_layout():
    domain, land = land_with_bay()
    g = terrain.grid_for(domain.bounds, 20.0)
    X, Z = g.node_xz()
    h = 3.0 + 0.05 * X - 0.02 * Z
    cut = np.where(X > 40, 0.7, 0.0)
    cls, stream, n_edge = terrain.classes_and_rings(g, land, domain)
    shore, n_shore = terrain.shore_bits([[np.array([[70.0, 10.0], [100.0, 10.0], [100.0, 50.0], [55.0, 50.0]])]],
                                        shapely.boundary(domain))
    buf = terrain.pack(g, h, cut, [0.0], 0.0, cls, stream, n_edge, shore, n_shore)
    assert struct.unpack_from("<I", buf, 0)[0] == terrain.MAGIC and len(buf) % 4 == 0
    d = terrain.unpack(buf)
    assert d["grid"] == g and d["water_z"] == 0.0 and d["levels"].tolist() == [0.0]
    assert np.abs(d["h"] - h).max() <= 0.05 + 1e-9                     # decimetres
    assert np.array_equal(d["cut"], np.round(cut * 10) / 10)
    assert np.array_equal(d["cls"], cls) and d["rings"] == stream and d["shore"] == shore and d["n_shore"] == 4
    assert d["source"] == "contours"
    assert terrain.unpack(terrain.pack(g, h, cut, [0.0], 0.0, cls, stream, n_edge, shore, n_shore, "dtm"))["source"] == "dtm"
    with pytest.raises(ValueError, match="magic"):
        terrain.unpack(b"\0" * 64)
    with pytest.raises(ValueError, match="bytes"):
        terrain.unpack(buf + b"\0\0\0\0")
    # what u8 decimetres and int16 decimetres cannot hold is refused, never clipped or written as garbage
    with pytest.raises(ValueError, match="finite"):
        terrain.pack(g, np.where(X > 50, np.nan, h), cut, [0.0], 0.0, cls, stream, n_edge, shore, n_shore)
    with pytest.raises(ValueError, match="cut outside"):
        terrain.pack(g, h, np.where(X > 50, 25.6, 0.0), [0.0], 0.0, cls, stream, n_edge, shore, n_shore)
    with pytest.raises(ValueError, match="cut outside"):
        terrain.pack(g, h, np.where(X > 50, -0.1, 0.0), [0.0], 0.0, cls, stream, n_edge, shore, n_shore)
    with pytest.raises(ValueError, match="terrain height beyond int16"):     # 32767.5 dm rounds to 32768
        terrain.pack(g, np.where(X > 50, 3276.75, h), cut, [0.0], 0.0, cls, stream, n_edge, shore, n_shore)
    # a level that is not finite would ship as 0 m (the sea), and 4000 m would wrap around: both are refused
    for levels, water_z, match in (([np.nan], 0.0, "water levels must be finite"),
                                   ([0.0], np.nan, "water levels must be finite"),
                                   ([4000.0], 0.0, "water level beyond int16")):
        with pytest.raises(ValueError, match=match):
            terrain.pack(g, h, cut, levels, water_z, cls, stream, n_edge, shore, n_shore)


def test_pack_rounds_the_cut_to_decimetres_and_keeps_the_ceiling():
    domain, land = land_with_bay()
    g = terrain.grid_for(domain.bounds, 20.0)
    X, Z = g.node_xz()
    cls, stream, n_edge = terrain.classes_and_rings(g, land, domain)
    cut = np.where(X > 40, 0.69, np.where(X < 0, 25.5, 0.0))   # 6.9 dm rounds to 7 (truncating would give 6)
    d = terrain.unpack(terrain.pack(g, np.zeros_like(X), cut, [], 0.0, cls, stream, n_edge, b"", 0))
    assert set(np.unique(d["cut"]).tolist()) == {0.0, 0.7, 25.5}
    assert np.array_equal(d["cut"], np.round(cut * 10) / 10)


def test_the_header_is_c16_field_by_field_on_a_grid_that_is_not_square():
    g = terrain.Grid(-17_660.0, -12_860.0, 20.0, 4, 3)   # x0 != z0 and nx != nz, so no swap goes unseen
    h = np.arange(12, dtype=np.float64).reshape(3, 4) - 5.5
    cut = np.arange(12, dtype=np.float64).reshape(3, 4) / 10
    cls = np.array([[0, 1, 2], [3, 1, 0]], np.uint8)
    buf = terrain.pack(g, h, cut, [21.4], 0.0, cls, b"", 0, b"", 0, "dtm")
    # magic, version, x0, z0, cell, nx, nz, waterZ, nLevels, nEdge, ringBytes, shoreBytes, nShoreVerts, source, 2 x 0
    assert struct.unpack_from("<2I3f2If5I3I", buf) == (terrain.MAGIC, 1, -17_660.0, -12_860.0, 20.0, 4, 3, 0.0, 1, 0,
                                                       0, 0, 0, 2, 0, 0)
    assert buf[:4] == b"HFT1"
    # levels (2 bytes, padded to 4), hLo, hHi, cut (12 each), cls (6, padded to 8): 64 + 4 + 36 + 8
    assert len(buf) == 112
    assert struct.unpack_from("<h", buf, 64)[0] == 214
    d = terrain.unpack(buf)
    assert d["h"].shape == (3, 4) and np.array_equal(d["h"], h)
    assert np.array_equal(d["cut"], cut) and np.array_equal(d["cls"], cls)
    assert d["levels"].tolist() == [21.4]
