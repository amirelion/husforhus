"""Samfundet S:t Erik's blue plaques on their buildings: web/data/<version>/plaques.json (the viewer's context layers,
behind config.features.layers) and data/review-plaques.txt.

Reads s00_fetch_plaques' cache (the list, the texts, Open Plaques' positions), data/buildings.parquet and
s02_addresses' data/addresses.parquet. Each plaque is placed by its address first (or a variant of it), else by the
one non-private building whose card name is the plaque's name (data/attributes.parquet, data/wiki.parquet), else by
its Open Plaques position (pipeline/plaques.py place). plaques.json holds, per placed plaque, its id (the Stockholmskällan post), the
gid, its name, its Swedish text, the year it was put up, where it sits (x, z, city.to_local) and the credit
(plaques.CREDIT, CC BY 4.0): no address, owner or resident. Left out, and listed in the review file: a plaque not
on the wall now ("Skylt saknas"), one without a text, one on no footprint (a bridge, an area, an address no
footprint has), and one on a takedown's building (suppress.yml). A text loses its sentences that name an owner, a byggherre or a
property designation (plaques.cut; the entry says cut). Rerun s00_fetch_plaques and this step on a new list.

    uv run python -m pipeline.run s00_fetch_plaques s15_plaques s99_validate
"""
import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import city, io, plaques, suppress
from .s02_attributes import OUT as ATTRIBUTES
from .addresses import assign
from .geo import lonlat_to_3011
from .privacy import normalise
from .s00_fetch_plaques import LIST, OPENPLAQUES, TEXTS, read_list
from .s02_addresses import OUT as ADDRESSES
from .s02_years import BUILDINGS
from .s03_tiles import out_dir
from .textfold import fold

REVIEW = Path("data/review-plaques.txt")
WIKI = Path("data/wiki.parquet")


def build(rows: list[dict], texts: dict[int, str], table: pd.DataFrame, b, op: list[dict], *,
          taken: set[int] = frozenset(), designations: set[str] = frozenset(),
          cards: dict[str, list[int]] | None = None) -> tuple[list[dict], list[str], dict]:
    """(plaques.json's entries, the review file's lines, counts). cards: load_cards()'s names."""
    streets = {fold(s) for s in table.street.unique()}
    placed = plaques.place(rows, table, b, op, streets=streets, to_xy=lonlat_to_3011, assign=assign, cards=cards)
    centre = b.set_index("gid").geometry.representative_point() if len(b) else None
    out, review = [], []
    n = {"plaques": len(rows), "address": 0, "name": 0, "position": 0, "unplaced": 0, "missing": 0, "left_out": 0}
    seen = set()
    for p in placed:
        if p["id"] in seen:                     # one plaque on two addresses, or listed twice: the first one stands
            review.append(f"{p['id']}\t{p['n']}\t{p['name']}\t\tlisted twice: kept once")
            continue
        seen.add(p["id"])
        text, shortened = plaques.cut(texts.get(p["id"], ""), designations)
        addr = "; ".join(f"{s} {', '.join(nums)}" for s, nums in p["addrs"]) or "no address in the list"
        why = ("not on the wall now (Skylt saknas)" if p["missing"] else "no text" if not text
               else "a bridge (Broskyltar): on no footprint" if p.get("bridge")
               else "on no footprint" if p["gid"] < 0 else "a takedown's building" if p["gid"] in taken
               else "")
        if why:
            n["missing" if p["missing"] else "unplaced" if p["gid"] < 0 and text else "left_out"] += 1
            review.append(f"{p['id']}\t{p['n']}\t{p['name']}\t{addr}\t{why}")
            continue
        n[p["how"]] += 1
        x, z = city.to_local(centre[p["gid"]].x, centre[p["gid"]].y)
        out.append({"id": p["id"], "gid": p["gid"], "name": plaques.clean_name(p["name"], designations), "text": text, "year": p["year"],
                    "x": round(float(x), 1), "z": round(float(z), 1), "how": p["how"], "credit": plaques.CREDIT,
                    **({"cut": True} if shortened else {})})
    return sorted(out, key=lambda e: e["id"]), review, n


def load_cards(buildings: Path = BUILDINGS, attributes: Path = ATTRIBUTES, wiki: Path = WIKI) -> dict[str, list[int]]:
    """{folded card name: [gid, ...]}: the names the cards carry (s02_attributes' own, s06_wiki's), private houses
    left out (city.PRIVATE_HOUSE_KATEGORI)."""
    b = pd.read_parquet(buildings, columns=["gid", "kategori"])
    private = set(b.gid[b.kategori.isin(city.PRIVATE_HOUSE_KATEGORI)])
    out: dict[str, set[int]] = {}
    for path in (attributes, wiki):
        if path.exists():
            t = pd.read_parquet(path, columns=["gid", "name"])
            for g, nm in zip(t.gid, t.name):
                if isinstance(nm, str) and nm.strip() and int(g) not in private:
                    out.setdefault(fold(nm.replace("–", "-")), set()).add(int(g))
    return {k: sorted(v) for k, v in out.items()}


def summary(n: dict) -> str:
    return (f"plaques: {n['plaques']} in the list; {n['address']} placed by address, {n.get('name', 0)} by a card's "
            f"name, {n['position']} by Open Plaques "
            f"position, {n['unplaced']} unplaced, {n['missing']} not on the wall now, {n['left_out']} left out "
            "(no text, or a takedown)")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s15_plaques", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="version folder (default: the one web/data/current.json names)")
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    a, _ = ap.parse_known_args(argv or [])
    if not LIST.exists():
        raise SystemExit(f"{LIST} is missing: run s00_fetch_plaques first")
    rows = plaques.parse_list(read_list())
    texts = {r["id"]: plaques.text_from_post((TEXTS / f"{r['id']}.html").read_text(encoding="utf-8"))[1]
             for r in rows if (TEXTS / f"{r['id']}.html").exists()}
    b = gpd.read_parquet(BUILDINGS, columns=["gid", "fastighet", "geometry"])
    table = pd.read_parquet(ADDRESSES)
    table = table[~table.withheld] if "withheld" in table else table
    op = json.loads(OPENPLAQUES.read_text(encoding="utf-8")) if OPENPLAQUES.exists() else []
    designations = {normalise(f) for f in b.fastighet if isinstance(f, str) and f.strip()} - {""}
    out, review, n = build(rows, texts, table, b[["gid", "geometry"]], op,
                           taken=suppress.gids_of(BUILDINGS, a.suppress), designations=designations,
                           cards=load_cards())
    io.write_json(out_dir(a.version) / "plaques.json", out)
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text("# id\tlist no.\tname\taddress\twhy it is not on the map\n" + "".join(f"{r}\n" for r in review),
                      encoding="utf-8")
    print(summary(n))


if __name__ == "__main__":
    main(sys.argv[1:])
