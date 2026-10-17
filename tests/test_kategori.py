import json
import math

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
import shapely
from pyproj import Transformer

from pipeline import city
from pipeline import report_kategori as rk

X, Y = 154000.0, 6578900.0


def frame():
    return gpd.GeoDataFrame({
        "grupp": ["Bostadsbyggnad", "Bostadsbyggnad", "Bostadsbyggnad", "Övrig byggnad", "Servicebyggnad"],
        "kategori": ["Flerbostadshus", "Flerbostadshus", "Enbostadshus", "Kolonistuga", "Vattentorn"],
        "height": [16.0, 24.4, 6.5, 3.1, 30.0],
        "area": [400.0, 600.0, 90.0, 30.0, 1500.0],
    }, geometry=[shapely.box(X + 20 * i, Y, X + 20 * i + 10, Y + 10) for i in range(5)], crs=city.CRS)


def test_kategori_table_counts_types_and_floor_hints():
    t = rk.kategori_table(frame()).set_index("kategori")
    assert t.loc["Flerbostadshus", "n"] == 2
    assert t.loc["Flerbostadshus", "grupp"] == "Bostadsbyggnad"
    assert t["share"].sum() == pytest.approx(1.0)
    assert t.loc["Flerbostadshus", "k"] == city.STOREY_M["Flerbostadshus"]
    assert t.loc["Vattentorn", "k"] == city.STOREY_M["_default"]           # no own k: falls back
    assert t.loc["Flerbostadshus", "floors_max"] == math.floor(24.4 / city.STOREY_M["Flerbostadshus"] + 0.5)
    assert t.loc["Kolonistuga", "floors_med"] == 1
    assert bool(t.loc["Enbostadshus", "private"]) and not bool(t.loc["Flerbostadshus", "private"])


def test_storey_fit_matches_osm_centres_to_footprints(tmp_path):
    osm = tmp_path / "levels.json"
    t = Transformer.from_crs(city.CRS, 4326, always_xy=True)
    lon0, lat0 = t.transform(X + 5, Y + 5)        # inside footprint 0 (16 m Flerbostadshus)
    lon1, lat1 = t.transform(X + 25, Y + 5)       # inside footprint 1 (24.4 m Flerbostadshus)
    lon9, lat9 = t.transform(X - 500, Y)          # no footprint

    def way(i, lon, lat, levels):
        return {"type": "way", "id": i, "center": {"lon": lon, "lat": lat},
                "tags": {"building": "yes", "building:levels": levels}}

    osm.write_text(json.dumps({"elements": [way(1, lon0, lat0, "4"), way(2, lon1, lat1, "6"),
                                            way(3, lon9, lat9, "3"), way(4, lon0, lat0, "x")]}))
    o = rk.read_overpass(osm)
    assert len(o) == 3
    fit = rk.storey_fit(frame(), o).set_index("kategori")
    assert fit.loc["(all)", "n"] == 2
    assert fit.loc["(all)", "exact"] == 1.0          # 16 m / 4 levels and 24.4 m / 6 levels at k = 4.0 (or 4.1)
    assert fit.loc["(rest)", "k_best"] == pytest.approx(3.8)   # smallest grid k with 16/k -> 4 and 24.4/k -> 6


def test_private_house_and_storey_constants_are_final():
    assert city.PRIVATE_HOUSE_KATEGORI == {"Enbostadshus", "Kolonistuga"}
    assert city.STOREY_M == {"Flerbostadshus": 4.0, "Enbostadshus": 3.7, "Kolonistuga": 3.1, "Kontorsbyggnad": 4.5,
                             "Allmän byggnad": 4.6, "Industribyggnad": 4.2, "_default": 4.2}


@pytest.mark.network
def test_kategori_constants_match_the_real_lod1_values(lod1_dir):
    shps = sorted(lod1_dir.glob("*_StadsModell_shp/Byggnad.shp"))
    assert len(shps) == 13
    kats = pd.concat([pyogrio.read_dataframe(shp, columns=["KATEGORI"], read_geometry=False)["KATEGORI"]
                      for shp in shps])
    counts = kats.value_counts()
    assert len(counts) == 20      # 2023-01 snapshot; a new value must be classified (private? own k?) first
    assert city.PRIVATE_HOUSE_KATEGORI <= set(counts.index)
    assert set(city.STOREY_M) - {"_default"} <= set(counts.index)   # no typos in the keys
    assert "_default" in city.STOREY_M
    assert all(city.STOREY_M.get(k, city.STOREY_M["_default"]) > 0 for k in counts.index)
