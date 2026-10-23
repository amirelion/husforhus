"""The search index: what web/search.js looks up.

Writes into the version folder:
- search/index.json, loaded on the search field's first focus: the settings (city.SEARCH), the examples that resolve
  in this build, the stadsdelar (display name, buildings, bounds in the local frame), the everyday district names
  (city.DISTRICT_ALIASES), the neighbouring municipalities (city.OUTSIDE), the streets with an address on a footprint
  (name, buildings, stadsdelar, the shard holding its numbers), the named buildings (name, gid, stadsdel, English
  label), the names people use for the best-known of them (city.BUILDING_ALIASES: "Slottet", "Royal Palace",
  "Stadshuset", each with the gid of the one card carrying its target name), what is inside the buildings
  (`occupants`: Swedish and English name, gid, other names, stadsdel; from s06_wiki's data/occupants.json for a
  footprint whose card carries the building's item, "Nobelprismuseet" in Börshuset, and from the hand-checked table
  pipeline/occupant_pins.csv by footprint, which needs no card at all: "Liljevalchs konsthall") and how many buildings
  have an address
  (the empty field says what share of the city search covers);
- search/addr/<k>.json, loaded when a street is resolved: {street: [[number, gid, stadsdel], ...]}, the stadsdel an
  index into `districts`, k the first character of the street's folded name (pipeline/textfold.py; "_" for anything but
  a-z and 0-9).

Names come only from the version's own cards (cards/NN.json), so search shows no name a card does not, and a
private house's name only as its card does (the reviewed list); an alias only finds a building that a card
already names, and shows that name. Addresses come from s02_addresses
(OpenStreetMap, ODbL); a non-curated private-category house's are left out only when city.PRIVATE_ADDRESSES is False
. Folded names are not stored: the browser folds them on load with the same rules.

    uv run python -m pipeline.run s03_tiles s04_base s07_labels s14_search s99_validate -- --version v20261016

Rebuilding the same version replaces search/: an address shard the new index no longer uses is moved to
temp_trash/<version>/ (git-ignored), never deleted.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import city, io, occupants as occupant_table, suppress
from .addresses import number_key
from .s03_tiles import DATA, N_CARD_SHARDS, load, load_places, out_dir, shown_addresses
from .textfold import fold

SHARD_KEY = re.compile(r"[a-z0-9]")
TRASH = Path("temp_trash")
OCCUPANTS = Path("data/occupants.json")
EXAMPLE = re.compile(r"^(.*\S)\s+(\d+\s*[a-zA-Z]?)$")


def shard_key(street: str) -> str:
    f = fold(street)
    return f[0] if f and SHARD_KEY.fullmatch(f[0]) else "_"


def read_cards(out: Path) -> dict[int, dict]:
    """{gid: card} from the version's 64 card shards (anything that is not a gid's card is s99's to report)."""
    cards = {}
    for k in range(N_CARD_SHARDS):
        path = out / "cards" / f"{k:02d}.json"
        if path.exists():
            cards.update({int(g): c for g, c in json.loads(path.read_text(encoding="utf-8")).items()
                          if g.isascii() and g.isdigit() and isinstance(c, dict)})
    return cards


def bounds(x: np.ndarray, z: np.ndarray) -> list[int]:
    return [int(np.floor(x.min())), int(np.floor(z.min())), int(np.ceil(x.max())), int(np.ceil(z.max()))]


def one_spelling(a: pd.DataFrame) -> pd.DataFrame:
    """The addresses with one spelling per street, letter case aside (OSM writes some as both "... Väg" and "... väg"):
    the most common, on a tie the first sorted. Streets that differ by a diacritic stay apart (final review, F3)."""
    if a.empty:
        return a
    key = a.street.str.casefold()
    counts = a.groupby([key.rename("key"), a.street]).size().reset_index(name="n")
    best = counts.sort_values(["key", "n", "street"], ascending=[True, False, True]).drop_duplicates("key")
    return a.assign(street=key.map(best.set_index("key").street).to_numpy())


def occupant_entries(cards: dict[int, dict], occupants: dict[str, list[dict]],
                     pinned: dict[int, list[dict]] | None = None, district: dict[int, int] | None = None,
                     hidden: set[int] = frozenset()) -> list[list]:
    """[[Swedish name, English name, gid, [other names], stadsdel], ...]: what is inside a building. From s06_wiki's
    occupants.json ({building qid: [{qid, sv, en, alt}]}) for a footprint whose card carries that item, named or not
    (Forum för levande historia's house shows no name); from the hand-checked table (occupants.pinned, {gid: [...]})
    for its footprint, card or none. An institution the table places is not also placed where Wikidata puts it (the
    hand check wins); an occupant that shares the building's own name is the building, not something inside it; one
    name once per footprint; nothing on a takedown (`hidden`). The stadsdel is an index into the index's districts,
    -1 for none, so a row for a footprint without a named card still says where it is."""
    pinned, district = pinned or {}, district or {}
    placed = {o["qid"] for os in pinned.values() for o in os if o["qid"]}
    found: dict[int, list[dict]] = {}
    for g in sorted(cards):
        if cards[g].get("qid"):
            found[g] = [o for o in occupants.get(cards[g]["qid"], []) if o["qid"] not in placed]
    for g, os in pinned.items():
        found.setdefault(g, []).extend(os)
    out = []
    for g in sorted(found):
        if g in hidden:
            continue
        name, seen = fold(cards.get(g, {}).get("name") or ""), set()
        for o in found[g]:
            f = fold(o["sv"])
            if f != name and f not in seen:
                seen.add(f)
                out.append([o["sv"], o["en"], g, list(o.get("alt", [])), district.get(g, -1)])
    return out


def build(df: pd.DataFrame, cards: dict[int, dict], places: dict,
          occupants: dict[str, list[dict]] | None = None, pinned: dict[int, list[dict]] | None = None,
          hidden: set[int] = frozenset()) -> tuple[dict, dict[str, dict]]:
    """(index, {shard key: {street: [[number, gid, stadsdel], ...]}}) for buildings `df` (s03_tiles.load: gid, x, z,
    kategori, private, ysrc), the version's cards, s02_addresses' outputs, s06_wiki's occupants and the hand-checked
    ones (occupants.pinned) less the takedowns' footprints (`hidden`)."""
    dist_of = places["districts"].set_index("gid").district.reindex(df.gid).fillna("").to_numpy(dtype=object)
    keys = sorted({d for d in dist_of if d}, key=lambda d: city.DISTRICT_NAMES.get(d, d))
    di = {d: i for i, d in enumerate(keys)}
    x, z = df.x.to_numpy(float), df.z.to_numpy(float)
    districts = []
    for d in keys:
        m = dist_of == d
        districts.append([city.DISTRICT_NAMES.get(d, d.title()), int(m.sum()), bounds(x[m], z[m])])
    aliases = [[a, sorted(di[k] for k in ks if k in di)] for a, ks in city.DISTRICT_ALIASES.items()]
    aliases = [a for a in aliases if a[1]]

    a = one_spelling(shown_addresses(places["addresses"], df))
    shards: dict[str, dict] = {}
    streets = []
    for street, rows in a.groupby("street", sort=True):
        pairs = sorted({(n, int(g)) for n, g in zip(rows.number, rows.gid)}, key=lambda p: (number_key(p[0]), p[1]))
        k = shard_key(street)
        shards.setdefault(k, {})[street] = [[n, g, di.get(dist_of[g], -1)] for n, g in pairs]
        gids = rows.gid.unique()
        counts = pd.Series(dist_of[gids]).value_counts()
        ds = [di[d] for d, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if d in di]
        streets.append([street, int(len(gids)), ds, k])

    buildings = []
    for g in sorted(cards):
        c = cards[g]
        if c.get("name"):
            buildings.append([c["name"], g, di.get(dist_of[g], -1), c.get("en", "")])
    by_name: dict[str, list[int]] = {}
    for name, g, _, _ in buildings:
        by_name.setdefault(name, []).append(g)
    baliases = sorted([alias, by_name[target][0]] for alias, target in city.BUILDING_ALIASES.items()
                      if len(by_name.get(target, [])) == 1)
    index = {"v": 1, "settings": {k: v for k, v in city.SEARCH.items() if k not in ("examples", "addr_max_m")},
             "districts": districts, "aliases": aliases, "outside": list(city.OUTSIDE), "streets": streets,
             "buildings": buildings, "baliases": baliases, "occupants": occupant_entries(cards, occupants or {}, pinned,
                                           {int(g): di[d] for g, d in enumerate(dist_of) if d in di}, hidden),
             "addressed": int(a.gid.nunique())}
    index["examples"] = [e for e in city.SEARCH["examples"] if resolves(e, index, shards)]
    return index, shards


def resolves(example: str, index: dict, shards: dict[str, dict]) -> bool:
    """An example the empty field suggests must find something exactly: a street and its number, a building, a
    stadsdel or an everyday district name."""
    f = fold(example)
    m = EXAMPLE.match(example)
    if m:
        street = next((s for s in index["streets"] if fold(s[0]) == fold(m.group(1))), None)
        number = re.sub(r"\s+", "", m.group(2)).upper()
        if street and any(p[0] == number for p in shards.get(street[3], {}).get(street[0], [])):
            return True
    names = ([b[0] for b in index["buildings"]] + [d[0] for d in index["districts"]] + [a[0] for a in index["aliases"]]
             + [a[0] for a in index.get("baliases", [])])
    return any(fold(n) == f for n in names)


def write(out: Path, index: dict, shards: dict[str, dict], trash: Path = TRASH) -> dict:
    """Write search/ into `out` (replacing an older one: a shard the new index does not use goes to trash/<version>/,
    never deleted, and never over a copy trashed before: that one keeps its name, the new one gets -1, -2, ...);
    return sizes."""
    folder = out / "search"
    for old in sorted(folder.glob("addr/*.json")):
        if old.stem not in shards:
            dest = base = trash / out.name / "search" / "addr" / old.name
            k = 0
            while dest.exists():
                k += 1
                dest = base.with_name(f"{old.stem}-{k}{old.suffix}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            old.replace(dest)
    raw = io.write_json(folder / "index.json", index)
    gz = len(io.gzip_bytes((folder / "index.json").read_bytes()))
    addr = sum(len(io.gzip_bytes(json.dumps(s, ensure_ascii=False, separators=(",", ":")).encode()))
               for s in shards.values())
    for k, shard in sorted(shards.items()):
        io.write_json(folder / "addr" / f"{k}.json", shard)
    return {"index_raw": raw, "index_gz": gz, "addr_gz": addr}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s14_search", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="version folder to index (default: the one web/data/current.json names)")
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args(argv or [])
    out = out_dir(args.version)
    cards = read_cards(out)
    if not cards:
        raise SystemExit(f"{out / 'cards'} holds no cards: run s03_tiles first")
    df = load(args.data)
    occ = json.loads(OCCUPANTS.read_text(encoding="utf-8")) if OCCUPANTS.exists() else {}
    b = pd.read_parquet(args.data / "buildings.parquet", columns=["gid", "uuid", "oid", "kategori"])
    try:
        pinned = occupant_table.pinned(occupant_table.read_pins(), b)
    except ValueError as e:
        raise SystemExit(f"occupant_pins: {e}; nothing written")
    hidden = suppress.gids_of(args.data / "buildings.parquet")
    index, shards = build(df, cards, load_places(args.data), occ, pinned, hidden)
    s = write(out, index, shards)
    n_addr = sum(len(v) for shard in shards.values() for v in shard.values())
    dropped = [e for e in city.SEARCH["examples"] if e not in index["examples"]]
    missing = sorted(set(city.BUILDING_ALIASES) - {a[0] for a in index["baliases"]})
    print(f"search: {len(index['streets']):,} streets, {n_addr:,} addresses in {len(shards)} shards, "
          f"{len(index['buildings']):,} named buildings ({len(index['baliases'])} other names), "
          f"{len(index['occupants'])} institutions inside buildings ({sum(map(len, pinned.values()))} by hand), "
          f"{len(index['districts'])} stadsdelar; index {s['index_gz'] / 1e3:.0f} KB gz, addresses "
          f"{s['addr_gz'] / 1e3:.0f} KB gz"
          + (f"; examples not in this build: {', '.join(dropped)}" if dropped else "")
          + (f"; other names whose building no card names: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
