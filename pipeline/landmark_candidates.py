"""The curated list's candidates, for whoever grows pipeline/landmarks.py.

    uv run python -m pipeline.landmark_candidates          # writes data/landmark-candidates.md (internal)

Reads s06_wiki's table (the building items on footprints that are not private houses, with their articles), the years
(data/years.parquet) and the review list (data/review-years.json: Wikidata years against RAÄ's, the area's and the
Wikidata gains), and lists, per period, the footprints whose building has a Swedish or English article and is not
curated or cited (pipeline/cited.py) yet: first those still "Year unknown" (the curated tier's best targets), then those whose Wikidata year
disagrees with the winning one, then the rest; Gamla stan first within each group, then by name. Each row gives what an
entry needs to start from: the item, its point, the article to read and quote, and the year the map shows today.
The file names buildings, so it stays in data/ (git-ignored), like the review list.
"""
import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import city
from .codes import SRC_CITED, SRC_CURATED
from .estimate import stadsdel_of
from .s01_load import STADSDELAR
from .s03_tiles import SRC_NAMES     # every ysrc's name, the reader's and the cited records' too


def candidates(wiki: pd.DataFrame, years: pd.DataFrame, review: dict, stadsdel: pd.Series) -> pd.DataFrame:
    """One row per candidate footprint with an article: gid, qid, label, article, lon, lat, year, source, period (the
    map's), stadsdel, group (unknown, disagrees, dated), sorted as the module docstring says."""
    w = wiki[(wiki.wp_sv != "") | (wiki.wp_en != "")].merge(years[["gid", "year", "ysrc", "period"]], on="gid")
    w = w[~w.ysrc.isin((SRC_CURATED, SRC_CITED))]        # checked by hand already: a landmark, or a cited record
    disagree = {e["gid"] for k in ("wikidata_vs_raa", "wikidata_vs_area") for e in review.get(k, [])}
    out = pd.DataFrame({
        "gid": w.gid.astype(int), "qid": w.qid, "label": w.label,
        "article": [f"sv:{s}" if s else f"en:{e}" for s, e in zip(w.wp_sv, w.wp_en)],
        "lon": w.lon.round(6), "lat": w.lat.round(6), "year": w.year.astype(int),
        "source": [SRC_NAMES[int(s)] for s in w.ysrc], "period": w.period.astype(int),
        "stadsdel": stadsdel.reindex(w.gid).fillna("").to_numpy(),
    })
    out["group"] = ["unknown" if s == "none" else "disagrees" if g in disagree else "dated"
                    for s, g in zip(out.source, out.gid)]
    order = {"unknown": 0, "disagrees": 1, "dated": 2}
    out = out.assign(_g=out.group.map(order), _old=(out.stadsdel != "GAMLA STAN").astype(int))
    return out.sort_values(["_g", "period", "_old", "label"]).drop(columns=["_g", "_old"]).reset_index(drop=True)


def render(c: pd.DataFrame) -> str:
    lines = ["# Landmark candidates (internal: names buildings; data/ is git-ignored)", "",
             "Unknown first, then Wikidata disagreeing with the map's year, then the rest; Gamla stan first.", ""]
    for group in ("unknown", "disagrees", "dated"):
        g = c[c.group == group]
        lines += [f"## {group} ({len(g)})", "",
                  "| period | label | qid | article | lon | lat | map year | source | stadsdel |",
                  "|---|---|---|---|---|---|---|---|---|"]
        lines += [f"| p{r.period + 1} | {r.label} | {r.qid} | {r.article} | {r.lon} | {r.lat} | {r.year or ''} | "
                  f"{r.source} | {r.stadsdel} |" for r in g.itertuples()]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="landmark_candidates", description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data/landmark-candidates.md"))
    args = ap.parse_args(argv or [])
    wiki = pd.read_parquet("data/wiki.parquet")
    years = pd.read_parquet("data/years.parquet")
    review = json.loads(Path("data/review-years.json").read_text(encoding="utf-8"))
    b = gpd.read_parquet("data/buildings.parquet", columns=["gid", "geometry"])
    stadsdel = pd.Series(stadsdel_of(b, STADSDELAR), index=b.gid)
    c = candidates(wiki, years, review, stadsdel)
    args.out.write_text(render(c), encoding="utf-8")
    groups = {k: int(v) for k, v in c.group.value_counts().items()}
    print(f"{len(c)} candidates ({groups}) -> {args.out}; periods: "
          + ", ".join(f"{p[0]} {int((c.period == i).sum())}" for i, p in enumerate(city.PERIODS)))


if __name__ == "__main__":
    main(sys.argv[1:])
