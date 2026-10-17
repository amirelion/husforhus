"""A synthetic town for the terrain steps (Plan 3): raw City files, buildings and attributes on a known hill.

Local frame (x east, z south): the municipality is two stadsdelar over x 0..1000, z 0..800. The ground is a cone,
h = max(1, 30 - 0.05 * distance from (250, 350)), so the east is low. Water: a sea strait along the east edge (x 850
and on, cut off by the boundary at x = 1000) and a lake on the hill (x 200..300, z 300..400). The contours are that
cone's circles every 2 m, half of them labelled. Seven buildings: 0 standing right; 1 whose MARK_Z is 25 m too low (an
LOD1 sheet-line error); 2 across the slope (the terrace cuts under it); 3 a quay house under the sea (MARK_Z -1.1 m, as
four in Stockholm); 4 on a paved strip at a cliff's foot that no contour crosses (MARK_Z 15 m under the contours,
like Söder Mälarstrand); 5 and 6 plain houses.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from pipeline import city, codes

E0, N0 = city.ORIGIN
PEAK = (250.0, 350.0)
SEA_X = 850.0
LAKE = (200.0, 300.0, 300.0, 400.0)


def height(x, z) -> np.ndarray:
    d = np.hypot(np.asarray(x, dtype=float) - PEAK[0], np.asarray(z, dtype=float) - PEAK[1])
    return np.maximum(1.0, 30.0 - 0.05 * d)


def to3011(geom):
    return shapely.transform(geom, lambda c: np.c_[c[:, 0] + E0, N0 - c[:, 1]])


def lbox(x0, z0, x1, z1):
    return shapely.box(x0, z0, x1, z1)


FOOTPRINTS = [lbox(400, 500, 420, 520), lbox(600, 200, 630, 230), lbox(300, 420, 340, 440), lbox(800, 600, 820, 620),
              lbox(500, 330, 520, 350), lbox(150, 600, 165, 615), lbox(650, 500, 665, 515)]


def outline_min(poly) -> float:
    c = shapely.get_coordinates(shapely.segmentize(poly, 1.0))
    return float(height(c[:, 0], c[:, 1]).min())


def buildings() -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """(buildings with gid, kategori, ground = MARK_Z, height, geometry in EPSG:3011; attributes gid, floors)."""
    ground = np.array([outline_min(p) for p in FOOTPRINTS])
    ground[1] -= 25.0                       # the sheet-line error s02_terrain must fix
    ground[3] = -1.1                        # a quay house under the sea: drawn at the 0.3 m floor
    ground[4] -= 15.0                       # the strip at the cliff's foot: real ground, which the contours miss
    n = len(FOOTPRINTS)
    b = gpd.GeoDataFrame({"gid": pd.array(range(n), dtype="int32"), "kategori": ["Flerbostadshus"] * n,
                          "ground": ground.astype("float32"),
                          "height": pd.array([12.0, 35.0, 9.0, 6.0, 12.0, 7.0, 7.0], dtype="float32")},
                         geometry=[to3011(p) for p in FOOTPRINTS], crs=city.CRS)
    a = pd.DataFrame({"gid": pd.array(range(n), dtype="int32"), "floors": pd.array([3, 9, 2, 2, 3, 2, 2], dtype="uint8"),
                      "fsrc": pd.array([codes.FLOORS_HEIGHT] * n, dtype="uint8")})
    return b, a


def write_raw(raw: Path, contours: bool = True) -> None:
    """data/raw/city as s00_fetch_city and s00_fetch_dem leave it: stadsdelar, Vatten_area, 0_line, NamnText_point."""
    (raw / "stadsdelar").mkdir(parents=True, exist_ok=True)
    (raw / "stadskarta").mkdir(parents=True, exist_ok=True)
    halves = [to3011(lbox(0, 0, 500, 800)), to3011(lbox(500, 0, 1000, 800))]
    gpd.GeoDataFrame({"NAMN": ["VÄST", "ÖST"]}, geometry=halves, crs=city.CRS).to_file(raw / "stadsdelar" / "Stadsdel.shp")
    water = [to3011(lbox(SEA_X, -100, 1100, 900)), to3011(lbox(*LAKE))]
    gpd.GeoDataFrame({"GRUPP": ["Sjö", "Sjö"]}, geometry=water, crs=city.CRS).to_file(
        raw / "stadskarta" / "Vatten_area.shp")
    if not contours:
        return
    levels = np.arange(2, 30, 2)
    lines = [to3011(shapely.LineString(shapely.Point(PEAK).buffer((30 - c) / 0.05, quad_segs=32).exterior))
             for c in levels]
    kat = ["10 m" if c % 10 == 0 else "Jämn" for c in levels]
    gpd.GeoDataFrame({"GRUPP": ["Höjdkurva heltäckande"] * len(levels), "KATEGORI": kat}, geometry=lines,
                     crs=city.CRS).to_file(raw / "stadskarta" / "0_line.shp")
    labelled = np.r_[levels[::2], 28]       # every other line and the top one are labelled; the rest are inferred
    pts = [to3011(shapely.Point(PEAK[0] + (30 - c) / 0.05, PEAK[1])) for c in labelled]
    gpd.GeoDataFrame({"GRUPP": ["Höjdkurva heltäckande"] * len(labelled), "TEXT": [str(c) for c in labelled]},
                     geometry=pts, crs=city.CRS).to_file(raw / "stadskarta" / "NamnText_point.shp")


def write_dtm(path: Path, lake_level: float = 27.5, sea_level: float = 0.1) -> None:
    """data/raw/dem/dtm5.tif as s00_fetch_dem writes it: EPSG:3011, 5 m, pixel edges on multiples of 5 m in the
    local frame; the cone, with the lake flat at lake_level and the sea at sea_level."""
    import rasterio
    from rasterio.transform import Affine
    x = np.arange(-500, 1500, 5.0) + 2.5
    z = np.arange(-500, 1300, 5.0) + 2.5
    X, Z = np.meshgrid(x, z)
    h = height(X, Z)
    h[(X >= LAKE[0]) & (X <= LAKE[2]) & (Z >= LAKE[1]) & (Z <= LAKE[3])] = lake_level
    h[X >= SEA_X] = sea_level
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=h.shape[0], width=h.shape[1], count=1, dtype="float32",
                       crs=f"EPSG:{city.CRS}", transform=Affine(5, 0, E0 - 500, 0, -5, N0 + 500),
                       nodata=np.nan) as dst:
        dst.write(h.astype("float32"), 1)


def write_data(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    b, a = buildings()
    b.to_parquet(data / "buildings.parquet")
    a.to_parquet(data / "attributes.parquet")
