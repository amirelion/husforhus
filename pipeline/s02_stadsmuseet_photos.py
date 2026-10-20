"""Archive photos from Digitala Stadsmuseet on the footprints (pipeline/stadsmuseet_photos.py has the rules):
data/stadsmuseet-photos.json, data/review-stadsmuseet-photos.html (both internal: data/ is never committed) and the
picked files in web/data/photos/.

Reads s00_fetch_stadsmuseet's photo-assets.json, data/buildings.parquet, data/years.parquet (which houses are
private) and s02_addresses' data/addresses.parquet and data/districts.parquet (which buildings are in
stadsmuseet_photos.FULL_AREAS). Each picked photo's rendition is fetched once
(s00_fetch_stadsmuseet.fetch_rendition, cached under data/raw/stadsmuseet/renditions/), fitted to
stadsmuseet_photos.MAX_WIDTH and city.WIKI's photo_bytes, and copied to web/data/photos/<key> under s06_wiki's
content-addressed names, so a card asks no other host for it. stadsmuseet-photos.json holds {"buildings_sha256": the
buildings it was placed on, "cards": {gid: the card's `arch` list (stadsmuseet_photos.entry), oldest first}};
s03_tiles puts it on the card unless the building is `hidden`. A takedown's building (suppress.yml) gets none.

    uv run python -m pipeline.run s00_fetch_stadsmuseet s02_stadsmuseet_photos s03_tiles s04_base s07_labels s99_validate
"""
import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

from . import io, stadsmuseet, stadsmuseet_photos as sp, suppress
from .privacy import normalise
from .s00_fetch_stadsmuseet import PHOTO_ASSETS, fetch_rendition, read_photo_assets
from .s02_addresses import DISTRICTS, OUT as ADDRESSES
from .s02_years import BUILDINGS

OUT = Path("data/stadsmuseet-photos.json")
REVIEW = Path("data/review-stadsmuseet-photos.html")
YEARS = Path("data/years.parquet")
WEB_PHOTOS = Path("web/data/photos")


def files(picks: dict[int, list[dict]], get=fetch_rendition, web: Path = WEB_PHOTOS) -> tuple[dict[int, list[dict]], int]:
    """({gid: card entries}, how many picked photos gave no file): each pick's rendition fitted and copied to web."""
    web.mkdir(parents=True, exist_ok=True)
    cards, missing = {}, 0
    for g, its in sorted(picks.items()):
        for it in its:
            body = get(it["id"], it["rendition"])
            fitted = sp.fit(body) if body else None
            if fitted is None:
                missing += 1
                continue
            data, w, h = fitted
            key = sp.key_of(data, w)
            out = web / key
            if not out.exists() or out.stat().st_size != len(data):
                out.write_bytes(data)
            cards.setdefault(g, []).append({**sp.entry(it, key, w, h), "id": it["id"]})
    return cards, missing


def summary(n: dict, cards: dict, missing: int) -> str:
    left = ", ".join(f"{v} {k}" for k, v in n.items() if v)
    return (f"stadsmuseet photos: {sum(map(len, cards.values()))} photos on {len(cards)} buildings"
            f" (left out: {left or 'none'}{f', {missing} without a file' if missing else ''})")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s02_stadsmuseet_photos", description=__doc__.splitlines()[0])
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    a, _ = ap.parse_known_args(argv or [])
    if not PHOTO_ASSETS.exists():
        raise SystemExit(f"{PHOTO_ASSETS} is missing: run s00_fetch_stadsmuseet first")
    its = sp.items(read_photo_assets())
    b = pd.read_parquet(BUILDINGS, columns=["gid", "kategori", "fastighet"])
    years = pd.read_parquet(YEARS)
    table = pd.read_parquet(ADDRESSES)
    table = table[~table.withheld] if "withheld" in table else table
    designations = ({normalise(f) for f in b.fastighet if isinstance(f, str) and f.strip()}
                    | stadsmuseet.cached_designations() | sp.archive_designations(its)) - {""}
    taken = suppress.gids_of(BUILDINGS, a.suppress)
    # Any building in the city a harvested photo's address leads to (the owner, 2026-10-20: as many buildings with a
    # photo as possible); the harvest itself decides which areas are asked for.
    placed = sp.place(its, table)
    d = pd.read_parquet(DISTRICTS)
    full = set(d.gid[d.district.isin(sp.FULL_AREAS)].astype(int))
    picks, n = sp.choose(its, placed, private=sp.private_gids(b, years) | set(taken),
                         designations=designations, deny=sp.read_deny(), full=full)
    cards, missing = files(picks)
    first = table.sort_values(["gid", "street", "number"]).groupby("gid").first()
    rows = [{"gid": g, "address": f"{first.street[g]} {first.number[g]}" if g in first.index else "",
             "year": e.get("y"), "title": e.get("t"), **e} for g, es in cards.items() for e in es]
    io.write_json(OUT, {"buildings_sha256": hashlib.sha256(BUILDINGS.read_bytes()).hexdigest(),
                        "cards": {str(g): [{k: v for k, v in e.items() if k != "id"} for e in es]
                                  for g, es in cards.items()}})
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(sp.review_html(rows), encoding="utf-8")
    print(summary(n, cards, missing) + f" → {OUT}, {REVIEW}")


if __name__ == "__main__":
    main(sys.argv[1:])
