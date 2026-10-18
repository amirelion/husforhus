"""Card names that may sit on the wrong footprint: data/review-names.md, for a look by eye. Changes nothing.

Lists the named buildings that are not private houses (city.PRIVATE_HOUSE_KATEGORI) where
- far: the card's Wikidata item has its coordinates (P625) more than FAR_M from the footprint; or
- elsewhere: the card's name is the label of a Wikidata item whose P625 lies inside another footprint and more than
  NEAR_M (and at most NAMESAKE_M) from this one: the name suggests that other building (the arena beside the dome, the hall beside the
  station). The card's name is s02_attributes' own (RAÄ, the curated landmarks) else s06_wiki's.
A row already in pipeline/name_fixes.csv says so. A confirmed one goes into that table (move or drop), which
s03_tiles applies; nothing here edits a name.

Reads data/buildings.parquet, data/attributes.parquet, data/wiki.parquet and s06_wiki's cached items
(data/raw/wiki/items.json, labels.json); run it after a full build:

    uv run python scripts/check_names.py
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import city, name_fixes  # noqa: E402
from pipeline.geo import lonlat_to_3011  # noqa: E402
from pipeline.textfold import fold  # noqa: E402

FAR_M = 60.0
NEAR_M = 10.0
NAMESAKE_M = 500.0     # an item of the same name farther off is a namesake elsewhere in the city, not this building
OUT = Path("data/review-names.md")


def points(lon, lat) -> gpd.GeoSeries:
    x, y = lonlat_to_3011(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    return gpd.GeoSeries(shapely.points(x, y), crs=city.CRS)


def cards(b: gpd.GeoDataFrame, attributes: pd.DataFrame, wiki: pd.DataFrame) -> pd.DataFrame:
    """gid, name, source, qid, lon, lat of each named non-private building."""
    w = wiki.set_index("gid")
    a = attributes.set_index("gid").name.fillna("").astype(str) if len(attributes) else pd.Series(dtype=str)
    rows = []
    for g in b.gid[~b.kategori.isin(city.PRIVATE_HOUSE_KATEGORI)]:
        own = a.get(g, "")
        wn = str(w.name.get(g, "") or "") if g in w.index else ""
        name = own or wn
        if not name:
            continue
        rows.append({"gid": int(g), "name": name, "source": "attributes" if own else "wikidata",
                     "qid": str(w.qid.get(g, "")) if g in w.index else "",
                     "lon": float(w.lon.get(g, np.nan)) if g in w.index else np.nan,
                     "lat": float(w.lat.get(g, np.nan)) if g in w.index else np.nan})
    return pd.DataFrame(rows, columns=["gid", "name", "source", "qid", "lon", "lat"])


def check(b: gpd.GeoDataFrame, c: pd.DataFrame, items: pd.DataFrame) -> list[dict]:
    """The suspect cards: {gid, name, qid, check, metres, other}. items: qid, sv, en, lon, lat."""
    geom = b.set_index("gid").geometry
    out = []
    has = c.dropna(subset=["lon", "lat"])
    if len(has):
        d = geom.loc[has.gid].distance(points(has.lon, has.lat).set_axis(has.gid), align=False)
        for (_, r), m in zip(has.iterrows(), d.to_numpy()):
            if m > FAR_M:
                out.append({**r[["gid", "name", "qid"]].to_dict(), "check": "far", "metres": round(float(m)),
                            "other": ""})
    it = items.dropna(subset=["lon", "lat"])
    pts = gpd.GeoDataFrame({"qid": it.qid.to_numpy()}, geometry=points(it.lon, it.lat).to_numpy(), crs=city.CRS)
    inside = gpd.sjoin(pts, b[["gid", "geometry"]], predicate="within").drop_duplicates("qid").set_index("qid").gid
    by_label: dict[str, list[str]] = {}
    for q, sv, en in zip(it.qid, it.sv, it.en):
        for lab in {fold(x) for x in (sv, en) if isinstance(x, str) and x}:
            by_label.setdefault(lab, []).append(q)
    where = dict(zip(pts.qid, pts.geometry))
    for _, r in c.iterrows():
        for q in by_label.get(fold(r["name"]), []):
            other = inside.get(q)
            if other is None or int(other) == r["gid"]:
                continue
            m = geom[r["gid"]].distance(where[q])
            if NEAR_M < m <= NAMESAKE_M:
                out.append({"gid": r["gid"], "name": r["name"], "qid": q, "check": "elsewhere", "metres": round(m),
                            "other": int(other)})
    return sorted(out, key=lambda e: (e["check"], -e["metres"], e["gid"]))


def report(rows: list[dict], fixes: pd.DataFrame) -> str:
    fixed = set(fixes.key)
    lines = ["# Card names that may be on the wrong footprint", "",
             f"Written by scripts/check_names.py. far: the card's Wikidata item (P625) is more than {FAR_M:.0f} m from "
             "the footprint. elsewhere: the name is the label of an item whose P625 lies inside another footprint "
             f"(more than {NEAR_M:.0f} m and at most {NAMESAKE_M:.0f} m from this one). Look at each on the map; a confirmed one goes into "
             "pipeline/name_fixes.csv.", "",
             f"{sum(r['check'] == 'far' for r in rows)} far, {sum(r['check'] == 'elsewhere' for r in rows)} elsewhere; "
             f"{sum(str(r['gid']) in fixed or r['qid'] in fixed for r in rows)} already in name_fixes.csv.", "",
             "| check | gid | name | item | metres | item inside gid | in name_fixes |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        done = "yes" if str(r["gid"]) in fixed or r["qid"] in fixed else ""
        lines.append(f"| {r['check']} | {r['gid']} | {r['name'].replace('|', '/')} | {r['qid']} | {r['metres']} | "
                     f"{r['other']} | {done} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="check_names", description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    from pipeline.s06_wiki import fetch_items

    b = gpd.read_parquet(a.data / "buildings.parquet", columns=["gid", "kategori", "geometry"])
    attributes = pd.read_parquet(a.data / "attributes.parquet", columns=["gid", "name"])
    wiki = pd.read_parquet(a.data / "wiki.parquet", columns=["gid", "qid", "name", "lon", "lat"])
    items, _ = fetch_items(False)
    rows = check(b, cards(b, attributes, wiki), items[["qid", "sv", "en", "lon", "lat"]])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(report(rows, name_fixes.read()), encoding="utf-8")
    print(f"check_names: {len(rows)} to look at -> {a.out}")


if __name__ == "__main__":
    main(sys.argv[1:])
