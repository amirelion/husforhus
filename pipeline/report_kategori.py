"""Report the LOD1 building types: GRUPP x KATEGORI counts and storey-height hints.

    uv run python -m pipeline.report_kategori                       # from data/buildings.parquet
    uv run python -m pipeline.report_kategori --osm levels.json     # also fit metres per storey against OSM

The table shows, per KATEGORI, the count, median and p90 height, median footprint, the metres per storey k that
city.STOREY_M gives it, the floors that k implies (C1: floors = clamp(floor(height / k + 0.5), 1, 99), the rule
s02_attributes ships), and whether the category is a private house (city.PRIVATE_HOUSE_KATEGORI, D18).

--osm takes an Overpass JSON export with `out tags center` of buildings that carry building:levels, e.g.
    [out:json][timeout:240];area(3600398021)->.a;
    (way["building"]["building:levels"](area.a);relation["building"]["building:levels"](area.a););out tags center qt;
Each OSM centre is matched to the footprint that contains it. This is a one-off, offline calibration of a few
constants; no OSM value enters data/ or web/.
"""
import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

from pipeline import city, s02_attributes

BUILDINGS = Path("data/buildings.parquet")
MIN_FIT = 200   # matched OSM buildings a KATEGORI needs before it gets its own k
K_GRID = np.round(np.arange(3.0, 5.01, 0.1), 1)


def storey_k(kategori: pd.Series) -> pd.Series:
    return pd.Series(s02_attributes.storey_height(kategori), index=kategori.index, name=kategori.name)


def floors(height: pd.Series, k: pd.Series) -> np.ndarray:
    """The C1 floors rule, delegated to s02_attributes so the report and the shipped floors cannot drift."""
    return s02_attributes.floors_from_storey(height, k).astype(int)


def kategori_table(b: pd.DataFrame) -> pd.DataFrame:
    b = b.assign(k=storey_k(b["kategori"]))
    b = b.assign(floors=floors(b["height"], b["k"]))
    t = b.groupby(["grupp", "kategori"], sort=False).agg(
        n=("height", "size"), h_med=("height", "median"), h_p90=("height", lambda s: s.quantile(0.9)),
        area_med=("area", "median"), k=("k", "first"), floors_med=("floors", "median"),
        floors_max=("floors", "max")).reset_index()
    t["share"] = t["n"] / t["n"].sum()
    t["private"] = t["kategori"].isin(city.PRIVATE_HOUSE_KATEGORI)
    cols = ["grupp", "kategori", "n", "share", "h_med", "h_p90", "area_med", "k", "floors_med", "floors_max",
            "private"]
    return t[cols].sort_values(["n", "kategori"], ascending=[False, True]).reset_index(drop=True)


def read_overpass(path: Path) -> pd.DataFrame:
    """Overpass JSON -> x, y (EPSG:3011) and levels for every element with a numeric building:levels."""
    rows = []
    for e in json.loads(Path(path).read_text())["elements"]:
        c, t = e.get("center"), e.get("tags", {})
        try:
            levels = float(t["building:levels"].replace(",", "."))
        except (KeyError, ValueError):
            continue
        if c and 1 <= levels <= 60:
            rows.append((c["lon"], c["lat"], levels))
    o = pd.DataFrame(rows, columns=["lon", "lat", "levels"])
    x, y = Transformer.from_crs(4326, city.CRS, always_xy=True).transform(o["lon"].to_numpy(), o["lat"].to_numpy())
    return pd.DataFrame({"x": x, "y": y, "levels": o["levels"].to_numpy()})


def best_k(height: pd.Series, levels: pd.Series) -> tuple[float, float]:
    """The k on K_GRID with the highest share of exact floor counts (ties: the smallest k), and that share."""
    shares = [float((floors(height, pd.Series(k, index=height.index)) == levels.to_numpy()).mean()) for k in K_GRID]
    i = int(np.argmax(shares))
    return float(K_GRID[i]), round(shares[i], 3)


def storey_fit(b: gpd.GeoDataFrame, osm: pd.DataFrame) -> pd.DataFrame:
    """Per KATEGORI: matched OSM buildings, median height per level, exact / ±1 floor shares at the current k,
    and the best k on K_GRID (only for categories with at least MIN_FIT matches; '(rest)' pools the others)."""
    pts = gpd.GeoDataFrame(osm, geometry=gpd.points_from_xy(osm["x"], osm["y"]), crs=city.CRS)
    j = gpd.sjoin(pts, b[["kategori", "height", "geometry"]], predicate="within", how="inner")
    j = j[~j.index.duplicated()]
    j = j.assign(k=storey_k(j["kategori"]))
    j = j.assign(f=floors(j["height"], j["k"]), ratio=j["height"] / j["levels"])
    big = j.groupby("kategori")["levels"].transform("size") >= MIN_FIT
    groups = [(kat, g) for kat, g in j[big].groupby("kategori")] + [("(rest)", j[~big]), ("(all)", j)]
    rows = []
    for kat, g in groups:
        if g.empty:
            continue
        k_best, exact_best = best_k(g["height"], g["levels"]) if kat != "(all)" else (None, None)
        rows.append({"kategori": kat, "n": len(g), "h_per_level": round(float(g["ratio"].median()), 2),
                     "k": g["k"].iloc[0] if kat not in ("(rest)", "(all)") else None,
                     "exact": round(float((g["f"] == g["levels"]).mean()), 3),
                     "within1": round(float(((g["f"] - g["levels"]).abs() <= 1).mean()), 3),
                     "k_best": k_best, "exact_best": exact_best})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="GRUPP x KATEGORI counts and storey-height hints")
    ap.add_argument("--buildings", type=Path, default=BUILDINGS)
    ap.add_argument("--osm", type=Path, help="Overpass JSON with building:levels (optional, offline calibration)")
    args = ap.parse_args([] if argv is None else argv)
    b = gpd.read_parquet(args.buildings)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)
    t = kategori_table(b)
    print(t.to_string(formatters={"share": "{:.1%}".format, "h_med": "{:.1f}".format, "h_p90": "{:.1f}".format,
                                  "area_med": "{:.0f}".format}))
    print(f"\n{len(b):,} buildings, {t['kategori'].nunique()} KATEGORI values; private houses "
          f"{int(t.loc[t['private'], 'n'].sum()):,} ({t.loc[t['private'], 'share'].sum():.1%})")
    unknown = sorted(set(city.STOREY_M) - {"_default"} - set(t["kategori"]))
    missing = sorted(set(city.PRIVATE_HOUSE_KATEGORI) - set(t["kategori"]))
    if unknown or missing:
        print("WARNING: not in the data:", ", ".join(unknown + missing))
    if args.osm:
        print("\nMetres per storey against OSM building:levels:")
        print(storey_fit(b, read_overpass(args.osm)).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
