"""scripts/check_names.py: card names that may sit on the wrong footprint (data/review-names.md)."""
import importlib.util
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from pyproj import Transformer

from pipeline import city

spec = importlib.util.spec_from_file_location("check_names", Path(__file__).parent.parent / "scripts" / "check_names.py")
check_names = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_names)
TO_WGS84 = Transformer.from_crs(city.CRS, 4326, always_xy=True)
X0, Y0 = city.ORIGIN


def lonlat(x, y):
    return TO_WGS84.transform(X0 + x, Y0 + y)


def test_lists_a_far_item_and_a_name_whose_item_stands_in_another_footprint():
    b = gpd.GeoDataFrame({"gid": [0, 1, 2, 3], "kategori": ["Allmän byggnad"] * 3 + ["Enbostadshus"],
                          "geometry": [shapely.box(X0 + x, Y0, X0 + x + 20, Y0 + 20) for x in (0, 45, 400, 3000)]},
                         crs=city.CRS)
    attributes = pd.DataFrame({"gid": [0, 3], "name": ["Globen", "Villa"]})
    dome = lonlat(55, 10)                                                     # inside gid 1
    far = lonlat(200, 10)                                                     # 180 m off gid 2
    wiki = pd.DataFrame({"gid": [1, 2], "qid": ["Q32926", "Q2"], "name": ["Globen", "Hallen"],
                         "lon": [dome[0], far[0]], "lat": [dome[1], far[1]]})
    items = pd.DataFrame({"qid": ["Q32926", "Q2"], "sv": ["Globen", "Hallen"], "en": ["Avicii Arena", ""],
                          "lon": [dome[0], far[0]], "lat": [dome[1], far[1]]})
    c = check_names.cards(b, attributes, wiki)
    assert list(c.gid) == [0, 1, 2]                                           # the private house is not looked at
    rows = check_names.check(b, c, items)
    assert [(r["check"], r["gid"], r["other"]) for r in rows] == [("elsewhere", 0, 1), ("far", 2, "")]
    md = check_names.report(rows, pd.DataFrame({"key": ["0"]}))
    assert "1 far, 1 elsewhere; 1 already in name_fixes.csv" in md
    assert "| elsewhere | 0 | Globen | Q32926 | 35 | 1 | yes |" in md
