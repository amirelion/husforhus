# tests/test_geo.py
"""pipeline.geo: placing a point on a LOD1 footprint (moved out of s02_years)."""
import numpy as np
import pytest
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, box

from pipeline import city, geo, s02_years
from tests import synth

X0, Y0 = city.ORIGIN


def fp(*boxes, first_gid=0):
    """Footprints from (minx, miny, maxx, maxy) boxes in absolute EPSG:3011 coordinates, gids first_gid, +1, …"""
    return synth.buildings(rows=[{"gid": first_gid + i, "geometry": box(*bx)} for i, bx in enumerate(boxes)])


def test_s02_years_still_re_exports_the_helpers():
    assert s02_years.resolve_points is geo.resolve_points
    assert s02_years.lonlat_to_3011 is geo.lonlat_to_3011
    assert s02_years.LANDMARK_MAX_M == geo.LANDMARK_MAX_M == 15.0


def test_lonlat_to_3011_puts_stortorget_at_the_origin():
    x, y = geo.lonlat_to_3011([18.0709], [59.3253])
    assert x[0] == pytest.approx(X0, abs=60) and y[0] == pytest.approx(Y0, abs=60)


def test_a_point_inside_wins_and_the_smallest_footprint_beats_the_larger_one():
    big, small = (X0, Y0, X0 + 100, Y0 + 100), (X0 + 40, Y0 + 40, X0 + 50, Y0 + 50)
    b = fp(big, small)                                   # gid 0 is the big one
    got = geo.resolve_points(b, [X0 + 45, X0 + 10], [Y0 + 45, Y0 + 10])
    assert got.tolist() == [1, 0]                        # in both -> the smaller; only in the big -> the big


def test_a_courtyard_point_resolves_to_the_ring_and_a_far_point_to_minus_one():
    ring = Polygon(box(X0, Y0, X0 + 100, Y0 + 100).exterior.coords, [box(X0 + 30, Y0 + 30, X0 + 70, Y0 + 70).exterior.coords])
    b = synth.buildings(rows=[{"geometry": ring}])
    got = geo.resolve_points(b, [X0 + 50, X0 + 500], [Y0 + 50, Y0 + 500])
    assert got.tolist() == [0, -1]


def test_the_nearest_footprint_within_max_dist_else_minus_one():
    b = fp((X0, Y0, X0 + 10, Y0 + 10))
    xs, ys = [X0 + 10 + 14.0, X0 + 10 + 16.0], [Y0 + 5, Y0 + 5]
    assert geo.resolve_points(b, xs, ys).tolist() == [0, -1]                 # 14 m in, 16 m out of the 15 m default
    assert geo.resolve_points(b, xs, ys, max_dist=20.0).tolist() == [0, 0]


def test_a_tie_in_distance_goes_to_the_lowest_gid():
    b = fp((X0, Y0, X0 + 10, Y0 + 10), (X0 + 20, Y0, X0 + 30, Y0 + 10), first_gid=2)
    assert geo.resolve_points(b, [X0 + 15], [Y0 + 5]).tolist() == [2]
    assert geo.resolve_points(b.iloc[::-1], [X0 + 15], [Y0 + 5]).tolist() == [2]   # not the row order


@pytest.mark.parametrize("noise", [1e-10, -1e-10])
def test_equidistant_up_to_floating_point_noise_still_goes_to_the_lowest_gid(noise):
    # Ruling F1. gid 2 and gid 3 are 5 m either side of the point, give or take what a WGS84 round trip leaves. The raw
    # distances differ by ~2e-10 m, so a tie-break on them would hand the point to whichever side the noise favoured;
    # distances are compared to the millimetre, then by gid.
    lo, hi = (X0, Y0, X0 + 10, Y0 + 10), (X0 + 20, Y0, X0 + 30, Y0 + 10)
    b = fp(lo, hi, first_gid=2)
    px, py = X0 + 15 + noise, Y0 + 5
    p = shapely.Point(px, py)
    d_lo, d_hi = shapely.distance(b.geometry.iloc[0], p), shapely.distance(b.geometry.iloc[1], p)
    assert d_lo != d_hi and abs(d_lo - d_hi) < 1e-8                          # the setup: a tie only up to noise
    assert geo.resolve_points(b, [px], [py]).tolist() == [2]


def test_a_tie_that_survives_a_wgs84_round_trip_goes_to_the_lowest_gid():
    b = fp((X0, Y0, X0 + 10, Y0 + 10), (X0 + 20, Y0, X0 + 30, Y0 + 10), first_gid=2)
    back = Transformer.from_crs(city.CRS, 4326, always_xy=True)
    lon, lat = back.transform(X0 + 15, Y0 + 5)
    x, y = geo.lonlat_to_3011([lon], [lat])
    assert geo.resolve_points(b, x, y).tolist() == [2]


def test_a_real_difference_of_a_few_millimetres_still_decides():
    b = fp((X0, Y0, X0 + 10, Y0 + 10), (X0 + 20, Y0, X0 + 30, Y0 + 10), first_gid=2)
    assert geo.resolve_points(b, [X0 + 15.002], [Y0 + 5]).tolist() == [3]    # 2 mm nearer to gid 3


def test_resolve_points_with_no_points_or_no_candidates():
    b = fp((X0, Y0, X0 + 10, Y0 + 10))
    assert geo.resolve_points(b, [], []).tolist() == []
    assert geo.resolve_points(b, [X0 + 1000], [Y0 + 1000]).tolist() == [-1]


def test_placement_names_inside_courtyard_nearest_and_unresolved():
    ring = Polygon(box(X0, Y0, X0 + 100, Y0 + 100).exterior.coords, [box(X0 + 30, Y0 + 30, X0 + 70, Y0 + 70).exterior.coords])
    b = synth.buildings(rows=[{"geometry": ring}, {"geometry": box(X0 + 200, Y0, X0 + 210, Y0 + 10)}])
    xs, ys = [X0 + 10, X0 + 50, X0 + 205 + 8, X0 + 900], [Y0 + 10, Y0 + 50, Y0 + 5, Y0 + 900]
    gids = geo.resolve_points(b, xs, ys)
    assert gids.tolist() == [0, 0, 1, -1]
    assert geo.placement(b, gids, xs, ys).tolist() == ["inside", "courtyard", "nearest", ""]
    assert isinstance(geo.placement(b, gids, xs, ys), np.ndarray)
