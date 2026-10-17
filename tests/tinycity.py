"""A tiny synthetic city in contract C3 shape, shared by the s03 and s99 tests."""
from pathlib import Path

import hashlib
import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon, box

from pipeline import city, codes, terrain

# A tiny accuracy table in contract C10 shape: one measurable cell, one not, the fallback row, the table by the true
# year's period, the area and external checks. It describes the tiny city (s99 cross-checks it against stats.byFlag):
# tested 6 = the EXACT/RANGE/LONG rows, result = its one ESTIMATE, one PERIOD and two UNKNOWN rows (a build with the
# period-only lever on: Task 14b's default never gives one). The cells' numbers are made up.
_SPLIT0 = {"n_all": 0, "n_estimate": 0, "right_estimate": 0, "in_band_estimate": 0}
ACCURACY = {
    "method": "knn", "held_out": "kvarter", "folds": 5, "near_m": 100.0, "min_cell": 30, "min_right": 0.7, "max_band": 15,
    "tested": 6,
    "cells": [{"group": "house", "era": "1946–1975", "inner": False, "n": 35, "median_error": 1.0, "right_period": 0.8,
               "within_one": 0.97, "band": 5, "status": "estimate"},
              {"group": "apartments", "era": "1866–1919", "inner": True, "n": 5, "status": "not measurable"}],
    "fallback": [{"group": "house", "inner": False, "n": 35, "median_error": 1.0, "right_period": 0.8, "within_one": 0.97,
                  "status": "period"}],
    "band_coverage": 0.83,
    "by_true_period": [{"period": p[0], "n": 35 if p[0] == "p9" else 0, "right": 28 if p[0] == "p9" else 0,
                        "n_estimate": 35 if p[0] == "p9" else 0, "right_estimate": 28 if p[0] == "p9" else 0}
                       for p in city.PERIODS],
    "area": {"n": 0, "status": "not measurable"},
    "external": {"status": "not measurable", "n_all": 0, "n_estimate": 0, "right_estimate": 0, "in_band_estimate": 0,
                 "n_unknown": 0, "before_1990": _SPLIT0, "from_1990": _SPLIT0},
    "result": {"estimate": 1, "period": 1, "unknown": 2},
}

# s02_terrain's record for the tiny city (contract C15): a 6 x 5 node grid around the origin, built from contours,
# with the one water polygon of the s99 site fixture (tests/test_s99_validate.py).
TERRAIN = {"source": "contours", "x0": -40.0, "z0": -40.0, "cell": 20.0, "nx": 6, "nz": 5, "water_z": 0.0,
           "levels": 1, "water_area": 800000.0, "datum": -0.1, "fixed": 0, "lakes": 0, "fixture": False, "buried": 0,
           "relief_max": city.TERRAIN["relief_max"], "floating": 0, "sea": None}

# Plan 4a: s06_wiki's outputs for the tiny city (C21). gid 1 is the curated palace (a photo, sv and en excerpts),
# gid 10 a Wikidata-named house of flats, gid 7 the tower (an English label only). The excerpt and the photo credit
# are made up; the key is a photo file that the s99 tests write under web/data/photos/.
PHOTO_KEY = "0123456789abcdef-500.jpg"
WIKI = {
    "table": pd.DataFrame({"gid": pd.array([1, 7, 10], dtype="int32"), "qid": ["Q750444", "Q1721899", "Q10000001"],
                           "name": ["Stockholms slott", "Kaknästornet", "Schönfeldtska huset"],
                           "name_en": ["Stockholm Palace", "Kaknäs Tower", ""], "langs": ["sv,en", "sv", "sv"],
                           "photo": [PHOTO_KEY, "", ""], "placement": ["courtyard", "inside", "inside"],
                           "items": pd.array([1, 1, 2], dtype="int32")}),
    "photos": {PHOTO_KEY: {"key": PHOTO_KEY, "w": 500, "h": 375, "by": "Ann Foto", "lic": "CC BY-SA 4.0",
                           "lu": "https://creativecommons.org/licenses/by-sa/4.0",
                           "page": "https://commons.wikimedia.org/w/index.php?curid=42"}},
    "extracts": {"1": {"sv": {"t": "Slottet byggdes 1697–1754 efter branden.", "r": 59239449},
                       "en": {"t": "The palace was built from 1697 to 1754.", "r": 1250000000}},
                 "10": {"sv": {"t": "Ett hus i Gamla stan.", "r": 59000001}}},
}
# Plan 4a: s08_landmarks' verified entries for the tiny city: the palace is placed (years.landmark) and on the
# timeline; the second entry was not placed in this city. Task 11a: the palace carries made-up rebuilds and older
# cellars, so its card has a rebuild line.
LANDMARKS = [
    {"name": "Kungliga slottet", "qid": "Q750444", "lat": 59.3267, "lon": 18.0717, "year": 1754, "year_from": 1697,
     "year_to": 1754, "source": "sv:Stockholms slott", "checks": ["1697", "1754", "1772", "1857"], "timeline": 1,
     "rebuilt": [[1772, "rebuilt"], [1857, "raised"]], "cellars": True, "rev": 1, "title": "Stockholms slott"},
    {"name": "Storkyrkan", "qid": "Q1133075", "lat": 59.3258, "lon": 18.0706, "year": 1306, "year_from": 1306,
     "year_to": 1306, "source": "sv:Storkyrkan", "checks": ["invigdes 1306"], "timeline": 1, "rev": 2,
     "title": "Storkyrkan"},
]

# Plan 4b: s02_addresses' outputs for the tiny city (C26). gid 3 has two addresses on one street, gid 4 (a private
# house) one, the palace one; the others none. Every building lies in a stadsdel.
ADDRESSES = pd.DataFrame({"gid": pd.array([1, 3, 3, 4, 10], dtype="int32"),
                          "street": ["Slottsbacken", "Hornsgatan", "Hornsgatan", "Grimstagatan", "Västerlånggatan"],
                          "number": ["1", "30", "32", "5", "68"]})
DISTRICTS = pd.DataFrame({"gid": pd.array(range(11), dtype="int32"),
                          "district": ["GAMLA STAN", "GAMLA STAN", "RIDDARHOLMEN", "SÖDERMALM", "GRIMSTA", "SÖDERMALM",
                                       "GAMLA STAN", "LADUGÅRDSGÄRDET", "GAMLA STAN", "GRIMSTA", "GAMLA STAN"]})

SOURCES = [{
    "id": "test-src", "url": "https://example.org/data", "publisher": "Test", "product": "Test product", "dataset": "Test data",
    "licence": "CC0-1.0", "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "attribution": "Test data (CC0)", "modified": False, "status": "confirmed",
}]


def local_box(x0, z0, x1, z1):
    """A rectangle given in local metres (x east, z south), returned in EPSG:3011."""
    e0, e1 = city.ORIGIN[0] + x0, city.ORIGIN[0] + x1
    n0, n1 = city.ORIGIN[1] - z1, city.ORIGIN[1] - z0
    return box(e0, n0, e1, n1)


def tiny_city():
    """Eleven buildings over five 1200 m tiles (city.TILE, D24): a hole, a MultiPolygon, three private houses, two
    unknown years (one of them an Enbostadshus that keeps a RAÄ id), and Plan 2's rows: a kNN estimate (gid 8), a
    private period-only house (gid 9) and a Wikidata year (gid 10)."""
    courtyard = Polygon(local_box(100, 200, 140, 240).exterior.coords, [local_box(110, 210, 130, 230).exterior.coords])
    geoms = [
        local_box(0, 0, 10, 10),
        courtyard,
        MultiPolygon([local_box(-300, 40, -290, 50), local_box(-280, 40, -270, 52)]),
        local_box(1600, 10, 1625, 30),
        local_box(-20, -1600, -8, -1590),
        local_box(3100, 3100, 3130, 3140),
        local_box(20, 20, 32, 31),
        local_box(-700, 700, -650, 760),
        local_box(40, 0, 50, 10),
        local_box(60, 0, 72, 11),
        local_box(200, 100, 230, 130),
    ]
    n = len(geoms)
    b = gpd.GeoDataFrame({
        "gid": pd.array(range(n), dtype="int32"),
        "uuid": [f"2e389b81-54f2-48cc-b4ee-ae1285df22{i:02d}" for i in range(n - 1)] + [""],
        "oid": pd.array([1000 + i for i in range(n)], dtype="int64"),
        "grupp": ["Bostadsbyggnad"] * n,
        "kategori": ["Flerbostadshus", "Flerbostadshus", "Allmän byggnad", "Flerbostadshus", "Enbostadshus",
                     "Enbostadshus", "Kolonistuga", "Flerbostadshus", "Flerbostadshus", "Enbostadshus", "Flerbostadshus"],
        "fastighet": ["DIANA 1", "TRE KRONOR 1", "GRÅMUNKEHOLMEN 3", "SPADEN 12", "GRIMSTA 1:2", "BASTIONEN 4",
                      "KOLONI 7", "", "DIANA 2", "GRIMSTA 1:3", "CEPHEUS 5"],
        "height": pd.array([26.7, 18.0, 39.1, 12.5, 6.3, 21.0, 3.1, 149.8, 15.0, 5.5, 22.0], dtype="float32"),
        "ground": pd.array([3.1, 4.0, 7.7, -1.1, 29.2, 12.0, 15.5, 73.6, 2.0, 30.0, 5.0], dtype="float32"),
        "prod_year": pd.array([2003] * n, dtype="int16"),
        "fnr": pd.array([10_123_400 + i for i in range(n - 1)] + [0], dtype="int64"),   # internal: never shipped
    }, geometry=geoms, crs=city.CRS)
    b["area"] = b.geometry.area.astype("float32")
    E, R, L, A, U = codes.EXACT, codes.RANGE, codes.LONG, codes.AREA, codes.UNKNOWN
    p = city.period_index
    # year, from, to, ysrc, yflag, period, private, raa_id. Private houses (D18) publish only their decade; their
    # period comes from the real year: gid 4 is RAÄ-dated exactly 1968 (p10), gid 6 area-dated 1936 (p8).
    # gid 5 is an undated Enbostadshus: Task 10 rejected its RAÄ year but kept the raa_id (as for 3f8f590d-…).
    # Plan 2: gid 8 is estimated 1952 ±5 (ESTIMATE); gid 9 a private house whose cell gives the period only, the
    # estimate 1936 rounded to its decade (PERIOD); gid 10 is dated 1630 by Wikidata.
    rows = [
        (1647, 1647, 1647, codes.SRC_RAA, E, p(1647), False, "00b0d09f-630d-44fb-ad4e-df8117fdc62b"),
        (1754, 1754, 1754, codes.SRC_CURATED, E, p(1754), False, ""),
        (1625, 1625, 1700, codes.SRC_RAA, L, p(1625), False, "011ae7cb-9b96-42ac-b8b0-17b5a281b98a"),
        (1929, 1927, 1929, codes.SRC_RAA, R, p(1929), False, ""),
        (1960, 1960, 1969, codes.SRC_RAA, E, p(1968), True, "012a1a82-9a9c-4bf7-b88f-2480c9221516"),
        (0, 0, 0, codes.SRC_NONE, U, 0, False, "3f8f590d-6bd1-4b31-85ee-2306fb98332a"),
        (1930, 1930, 1939, codes.SRC_RAA_AREA, A, p(1936), True, ""),
        (0, 0, 0, codes.SRC_NONE, U, 0, False, ""),
        (1952, 1947, 1957, codes.SRC_ESTIMATE, codes.ESTIMATE, p(1952), False, ""),
        (1930, 1930, 1939, codes.SRC_ESTIMATE, codes.PERIOD, p(1936), True, ""),
        (1630, 1630, 1630, codes.SRC_WIKIDATA, E, p(1630), False, ""),
    ]
    y = pd.DataFrame(rows, columns=["year", "year_from", "year_to", "ysrc", "yflag", "period", "private", "raa_id"])
    y.insert(0, "gid", pd.array(range(n), dtype="int32"))
    y = y.astype({"year": "int16", "year_from": "int16", "year_to": "int16", "ysrc": "uint8", "yflag": "uint8",
                  "period": "uint8", "private": "bool"})
    y["landmark"] = ["", "Kungliga slottet", "", "", "", "", "", "", "", "", ""]
    a = pd.DataFrame({
        "gid": pd.array(range(n), dtype="int32"),
        "floors": pd.array([6, 4, 7, 3, 2, 5, 1, 40, 4, 2, 5], dtype="uint8"),
        "fsrc": pd.array([codes.FLOORS_HEIGHT] * n, dtype="uint8"),
        "rating": pd.array([1, 1, 2, 0, 0, 0, 0, 3, 0, 0, 0], dtype="uint8"),
        "architects": [["Nicodemus Tessin d.y."], [], [], ["Sigurd Lewerentz", "Ivar Tengbom"], [], [], [], [], [], [], []],
        "name": ["Tyska kyrkan", "Kungliga slottet", "", "", "", "", "", "Kaknästornet", "", "", "Schönfeldtska huset"],
        # Plan 4a (C20): the height rule's floors, no OSM floors here, the palace state-listed in 1935, the church
        # under church heritage law and without a floors row
        "floors_h": pd.array([6, 4, 7, 3, 2, 5, 1, 40, 4, 2, 5], dtype="uint8"),
        "floors_osm": pd.array([0] * n, dtype="uint8"),
        "prot": pd.array([3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype="uint8"),
        "since": pd.array([0, 1935, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype="int16"),
        "nofloors": [True] + [False] * (n - 1),
    })
    return b, y, a


def ground_rows(b: gpd.GeoDataFrame, a: pd.DataFrame) -> pd.DataFrame:
    """ground.parquet (C15) for the tiny city: nothing fixed, so the LOD1's ground and height and the floors stand;
    gid 3's ground (-1.1 m) is drawn at the 0.3 m floor (TERRAIN["ground_min"])."""
    return pd.DataFrame({"gid": b.gid.to_numpy().astype("int32"),
                         "ground": b.ground.clip(lower=0.3).to_numpy().astype("float32"),
                         "height": b.height.to_numpy().astype("float32"), "floors": a.floors.to_numpy(),
                         "ground_src": pd.array([0] * len(b), dtype="uint8"),
                         "tmin": b.ground.to_numpy().astype("float32")})


def write_data(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    b, y, a = tiny_city()
    b.to_parquet(data / "buildings.parquet")
    y.to_parquet(data / "years.parquet")
    a.to_parquet(data / "attributes.parquet")
    (data / "accuracy.json").write_text(json.dumps(ACCURACY, indent=1, sort_keys=True), encoding="utf-8")
    record = {**TERRAIN, **{f"{name}_sha256": hashlib.sha256((data / f"{name}.parquet").read_bytes()).hexdigest()
                            for name in ("buildings", "attributes")}}
    (data / "terrain.json").write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    ground_rows(b, a).to_parquet(data / "ground.parquet", index=False)
    WIKI["table"].to_parquet(data / "wiki.parquet")
    (data / "photos.json").write_text(json.dumps(WIKI["photos"]), encoding="utf-8")
    (data / "extracts.json").write_text(json.dumps(WIKI["extracts"]), encoding="utf-8")
    (data / "landmarks.json").write_text(json.dumps(LANDMARKS), encoding="utf-8")
    ADDRESSES.to_parquet(data / "addresses.parquet")
    DISTRICTS.to_parquet(data / "districts.parquet")


def tiny_terrain(levels=(0.0,), n_shore: int = 4, h=None, source: str = "contours") -> bytes:
    """terrain.bin (C16) matching TERRAIN: a gentle slope from 1 m to 9 m, all land, no edge cells; one level per
    water polygon and one shore bit per water vertex of the s99 site fixture (one 4-vertex polygon)."""
    g = terrain.Grid(TERRAIN["x0"], TERRAIN["z0"], TERRAIN["cell"], TERRAIN["nx"], TERRAIN["nz"])
    if h is None:
        h = 1.0 + np.add.outer(np.arange(g.nz), np.arange(g.nx)).astype(float)
    cls = np.full((g.nz - 1, g.nx - 1), terrain.LAND, dtype=np.uint8)
    shore = np.packbits(np.ones(n_shore, bool), bitorder="little").tobytes()
    return terrain.pack(g, h, np.zeros_like(h), list(levels), TERRAIN["water_z"], cls, b"", 0, shore, n_shore, source)
