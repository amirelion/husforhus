"""The City Museum's building-archaeology register on the footprints: data/stadsmuseet.json and
data/review-stadsmuseet.txt, both internal (data/ is never committed).

Reads s00_fetch_stadsmuseet's cache (the records with their categories, the category labels, the polygons),
data/buildings.parquet and s02_addresses' data/addresses.parquet. Each record goes on the footprints its polygon
covers, else on those its address sits on (pipeline/stadsmuseet.py place); a record placed nowhere, or only
ambiguously, is listed in the review file by its BR number and address, never on a card. stadsmuseet.json holds
{"buildings_sha256": the buildings it was placed on, "cards": {gid: the card's `br` entry (stadsmuseet.facts)}};
s03_tiles puts the entry on the card unless the building is `hidden` (a private house), and the viewer shows it on
the pinned card only. No property designation, description or staff name is written; a takedown's building
(suppress.yml) gets nothing.

    uv run python -m pipeline.run s00_fetch_stadsmuseet s02_stadsmuseet s03_tiles s04_base s07_labels s99_validate
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import io, stadsmuseet, suppress
from .s00_fetch_stadsmuseet import AREAS, CATEGORIES, INVESTIGATIONS, read_record, read_records, read_report
from .s02_addresses import OUT as ADDRESSES
from .s02_years import BUILDINGS

OUT = Path("data/stadsmuseet.json")
REVIEW = Path("data/review-stadsmuseet.txt")


def load_records() -> list[dict]:
    """The published records, each with its own answer's categories (records/<n>.json) where it is cached."""
    out = []
    for r in read_records(INVESTIGATIONS):
        if r.get("published") is False:
            continue
        own = read_record(r["id"])
        pages = stadsmuseet.report_pages(read_report(r["id"]), r["id"])
        out.append({**r, "categories": (own or {}).get("categories") or r.get("categories") or [],
                    **({"report_page": pages[0]} if pages else {})})
    return out


def build(recs: list[dict], polys: dict, labels: dict[int, str], b, table: pd.DataFrame,
          taken: set[int] = frozenset()) -> tuple[dict[int, dict], list[str], dict]:
    """({gid: br entry}, the review file's lines, counts)."""
    placed = stadsmuseet.place(recs, polys, b, table)
    by_id = {int(r["id"]): r for r in recs}
    review, n = [], {"records": len(recs), "polygon": 0, "address": 0, "ambiguous": 0, "unplaced": 0, "takedown": 0}
    for p in placed:
        if p["how"]:
            n[p["how"]] += 1
            kept = [g for g in p["gids"] if g not in taken]
            if len(kept) < len(p["gids"]):
                n["takedown"] += 1
            p["gids"] = kept
            continue
        n["ambiguous" if p["why"].startswith("ambiguous") else "unplaced"] += 1
        review.append(f"BR {p['id']}\t{' '.join(str(by_id[p['id']].get('address') or '').split())}\t{p['why']}")
    return stadsmuseet.cards(recs, placed, labels), review, n


def summary(n: dict, buildings: int) -> str:
    placed = n["polygon"] + n["address"]
    return (f"stadsmuseet: {n['records']} records; {placed} placed ({n['polygon']} by polygon, {n['address']} by "
            f"address) on {buildings} buildings, {n['ambiguous']} ambiguous, {n['unplaced']} unplaced"
            + (f", {n['takedown']} with a takedown's building left out" if n["takedown"] else ""))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s02_stadsmuseet", description=__doc__.splitlines()[0])
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    a, _ = ap.parse_known_args(argv or [])
    if not INVESTIGATIONS.exists():
        raise SystemExit(f"{INVESTIGATIONS} is missing: run s00_fetch_stadsmuseet first")
    recs = load_records()
    labels = stadsmuseet.category_labels(json.loads(CATEGORIES.read_text(encoding="utf-8"))["brCategories"])
    polys = stadsmuseet.polygons(json.loads(AREAS.read_text(encoding="utf-8"))["features"])
    b = gpd.read_parquet(BUILDINGS, columns=["gid", "geometry"])
    table = pd.read_parquet(ADDRESSES)
    table = table[~table.withheld] if "withheld" in table else table
    cards, review, n = build(recs, polys, labels, b, table, taken=suppress.gids_of(BUILDINGS, a.suppress))
    io.write_json(OUT, {"buildings_sha256": hashlib.sha256(BUILDINGS.read_bytes()).hexdigest(),
                        "cards": {str(g): c for g, c in cards.items() if c["inv"]}})
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text("# BR number\taddress\twhy it is on no card\n" + "".join(f"{r}\n" for r in review), encoding="utf-8")
    print(summary(n, len(cards)))


if __name__ == "__main__":
    main(sys.argv[1:])
