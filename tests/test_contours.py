"""pipeline/contours.py: heights for the City's contour lines and the TIN source."""
import geopandas as gpd
import numpy as np
import pytest
import shapely

from pipeline import contours
from tests import terrain_town as town


def test_allowed_heights_follow_the_line_kind():
    med = np.array([19.0, 21.0, 9.9, 10.2, 12.8, 14.9])
    ten = np.array([True, True, False, False, False, False])
    # "10 m" lines: the nearest multiple of 10; "Jämn": the nearest even metre that is not one (10 -> 8 or 12)
    assert contours.allowed(med, ten).tolist() == [20.0, 20.0, 8.0, 12.0, 12.0, 14.0]


def circles(levels):
    return gpd.GeoDataFrame({"ten": [c % 10 == 0 for c in levels]},
                            geometry=[shapely.LineString(shapely.Point(0, 0).buffer(100 - 4 * c, quad_segs=16).exterior)
                                      for c in levels],
                            crs=3011)


def test_label_lines_takes_the_most_common_label_within_3_m():
    lines = circles([2, 4, 6])
    labels = gpd.GeoDataFrame({"h": [2.0, 2.0, 4.0, 6.0]},
                              geometry=[shapely.Point(92, 0), shapely.Point(0, 93.5), shapely.Point(85, 0),
                                        shapely.Point(0, 50)], crs=3011)
    # line 0 (r 92): two labels "2"; line 1 (r 84): "4" 1 m off; line 2 (r 76): the "6" sits 26 m away, too far
    h = contours.label_lines(lines, labels)
    assert h[:2].tolist() == [2.0, 4.0] and np.isnan(h[2])


def test_a_tied_label_goes_to_the_lowest_height_whatever_the_row_order():
    lines = circles([2, 4])
    one = [shapely.Point(92, 0), shapely.Point(0, -92)]           # a "4" and a "2", both on line 0 (r 92)
    for h in ([4.0, 2.0], [2.0, 4.0]):
        labels = gpd.GeoDataFrame({"h": h}, geometry=one, crs=3011)
        assert contours.label_lines(lines, labels)[0] == 2.0


def test_an_unlabelled_line_takes_the_median_along_it_not_the_mean():
    # a flat 10 m TIN with one known point of 400 m at the end of a 41-point unlabelled "10 m" line: the median stays
    # 10; a mean would read (40 x 10 + 400) / 41 = 19.5, rounded to 20
    lines = gpd.GeoDataFrame({"ten": [True] * 4},
                             geometry=[shapely.LineString([(-300, y), (300, y)]) for y in (-50, 50, 150)]
                             + [shapely.LineString([(-200, 0), (200, 0)])], crs=3011)
    out, src = contours.infer_unlabelled(lines, np.array([10.0, 10.0, 10.0, np.nan]), np.array([[200.0, 0.0]]),
                                         np.array([400.0]))
    assert (out[3], src[3]) == (10.0, "inferred")


def test_unlabelled_lines_are_inferred_from_the_labelled_ones_and_rounded():
    lines = circles([2, 4, 6, 8, 10])
    h = np.array([2.0, np.nan, 6.0, np.nan, 10.0])
    out, src = contours.infer_unlabelled(lines, h)
    assert out.tolist() == [2.0, 4.0, 6.0, 8.0, 10.0]
    assert src.tolist() == ["label", "inferred", "label", "inferred", "label"]
    # a line outside every labelled line's hull is dropped (no height)
    far = gpd.GeoDataFrame({"ten": [False] * 4}, geometry=[*circles([2, 4, 6]).geometry,
                                                          shapely.LineString([(500, 500), (520, 500)])], crs=3011)
    out, src = contours.infer_unlabelled(far, np.array([2.0, 4.0, 6.0, np.nan]))
    assert np.isnan(out[3]) and src[3] == ""


# A quay under a cliff (Söder Mälarstrand, Slussen and Stadsgården). A strait of sea (x 10..190) between two
# hills; on the west a long unlabelled line runs along the quay at the water (x = 5), the labelled lines climb the
# cliff behind it (20, 30 and 40 m at x = -30, -40, -50), and one more unlabelled line lies between the first two. The
# far shore has labelled lines too, so the quay line lies inside the labelled lines' hull, as in the city.
QUAY_SEA = shapely.box(10, -500, 190, 700)


def quay_town():
    xs = [5, -30, -35, -40, -50, 210, 230]
    h = np.array([np.nan, 20.0, np.nan, 30.0, 40.0, 20.0, 30.0])
    lines = gpd.GeoDataFrame({"ten": [False, True, False, True, True, True, True]},
                             geometry=[shapely.LineString([(x, -400), (x, 600)]) for x in xs], crs=3011)
    return lines, h


def test_a_quay_line_takes_the_waters_height_once_the_inference_knows_the_shores():
    lines, h = quay_town()
    # from the labelled lines alone, the quay line takes the cliff's height (22 m: 20 rounded to a "Jämn" line)
    alone, _ = contours.infer_unlabelled(lines, h)
    assert alone[0] == 22.0
    # with the shore at the sea's level in the inference, it takes about the water's (5 m inland of a 0 m shore and
    # 35 m from the 20 m line: 2.5, an even metre: 2)
    xy, z = contours.shore_points([QUAY_SEA], [0.0])
    out, src = contours.infer_unlabelled(lines, h, xy, z)
    assert out[0] == 2.0 and src[0] == "inferred"
    # the line up the cliff, away from the water, keeps its height; the labelled lines keep theirs
    assert out[2] == alone[2] == 24.0
    assert out[[1, 3, 4, 5, 6]].tolist() == h[[1, 3, 4, 5, 6]].tolist()


def test_a_known_point_on_a_labelled_lines_vertex_is_left_out():
    # a known point on the 20 m line's own vertex (to the centimetre: 4 mm off) at 100 m is left out, so the line's
    # height wins there; kept, it would raise a 4 mm spike that a tiny unlabelled line beside it (true 22 m) reads
    lines, h = quay_town()
    lines = gpd.GeoDataFrame({"ten": [*lines.ten, False]},
                             geometry=[*lines.geometry, shapely.LineString([(-32, -1), (-32, 1)])], crs=3011)
    h = np.r_[h, np.nan]
    xy, z = contours.shore_points([QUAY_SEA], [0.0])
    out, _ = contours.infer_unlabelled(lines, h, xy, z)
    clash, _ = contours.infer_unlabelled(lines, h, np.r_[xy, [[-30.004, 0.0]]], np.r_[z, [100.0]])
    assert out[-1] == 22.0 and clash.tolist() == out.tolist()
    # a point 4 dm off the vertex is a point of its own, and is kept
    apart, _ = contours.infer_unlabelled(lines, h, np.r_[xy, [[-30.003, 0.4]]], np.r_[z, [100.0]])
    assert apart[-1] > 22.0


def test_load_hands_the_shores_to_the_inference(tmp_path):
    town.write_raw(tmp_path)
    lines, labelled = contours.read_labelled(tmp_path / "stadskarta")
    plain = contours.with_heights(lines, labelled)
    assert plain.h.tolist() == contours.load(tmp_path / "stadskarta").h.tolist()
    # a shore at 100 m between the 2 m line and the (unlabelled) 4 m one: the 4 m line is pulled up towards it
    ring = town.to3011(shapely.Point(town.PEAK)).buffer((30 - 2) / 0.05 - 20)
    shores = contours.shore_points([ring], [100.0])
    lifted = contours.with_heights(lines, labelled, shores)
    assert lifted.h.max() > plain.h.max()
    assert contours.load(tmp_path / "stadskarta", shores).h.tolist() == lifted.h.tolist()


def test_load_reads_the_town_with_heights_on_every_line(tmp_path):
    town.write_raw(tmp_path)
    lines = contours.load(tmp_path / "stadskarta")
    assert len(lines) == 14 and lines.crs.to_epsg() == 3011
    assert sorted(lines.h.tolist()) == list(range(2, 30, 2))       # half labelled, half inferred
    assert set(lines.src) == {"label", "inferred"}


def test_the_tin_follows_the_cone_and_holds_the_shores():
    raw_lines = [shapely.Point(town.PEAK).buffer((30 - c) / 0.05, quad_segs=32).exterior for c in range(2, 30, 2)]
    src = contours.ContourSource(raw_lines, list(range(2, 30, 2)))
    pts = np.array([[town.PEAK[0] + 150, town.PEAK[1]], [town.PEAK[0], town.PEAK[1] - 300]])
    assert src.sample(pts) == pytest.approx(town.height(pts[:, 0], pts[:, 1]), abs=0.3)
    assert np.isnan(src.sample(np.array([[5000.0, 5000.0]]))[0])
    lake = shapely.box(*town.LAKE)
    xy, z = contours.shore_points([lake], [24.5])
    with_shore = contours.ContourSource(raw_lines, list(range(2, 30, 2)), xy, z)
    assert with_shore.sample(np.array([[200.0, 350.0]]))[0] == pytest.approx(24.5)
