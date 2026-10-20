"""The City Museum's building-archaeology register (Stadsmuseet i Stockholm, Stads- och byggnadsarkeologiskt register,
BR; sources.yml stadsmuseet_br): which footprints a record covers, and the facts the pinned card states about them.

The register documents investigations of standing buildings, mostly in Gamla stan and Riddarholmen: where medieval
masonry was found, which parts were dated, and when. It dates parts and investigations, never the house: nothing
here touches a building's year, period or colour. Research: docs/research/2026-10-16-gamla-stan-ages.md §4.

A record (s00_fetch_stadsmuseet: /api/brInvestigations/{id}) has its BR number (`id`, also the WFS layer's
`BRNummer`), the investigation's years (`year_earliest`, `year_latest`: when it was investigated, not built), an
address, a property designation, a free-text description, its categories (ids into /api/brCategories) and whether
Digitala Stadsmuseet holds its report (`digital_archive_link_exists`).

place(): a record goes on the footprints its polygon (sr:v_area_br) covers: a footprint whose area lies at least
COVER inside the polygon, or else, when the polygon marks only the investigated part of one building, the one
footprint that holds at least INSIDE of the polygon. A record its polygon places nowhere falls back to its address in
s02_addresses' table (every footprint one of its "street number" addresses sits on). A polygon that touches
footprints without meeting either share, or an address that names only a street, leaves the record ambiguous;
nothing at all leaves it unplaced. Both go to the review file, never on a card. The property designation is a join
key only (designations(): s99 refuses one in any shipped file); it never reaches a card or web/data.

facts(): the card's entry for a footprint's records, from their structured fields and categories, never their
prose (the descriptions are the museum's text). In our words, on the card (web/archaeology.js):
- "Medieval walls documented here": a record dated 1100-1400-talet (category MEDIEVAL) that is not a tree-ring
  record (category DENDRO dates timber, such as BR 492's medieval cellar ceiling, not walls);
- "Timber dated by tree rings: felled 1676": a DENDRO record whose description gives one felling year, plainly
  (felling_year(): never a span of samples, a lower bound "felled after", or one of several);
- "Investigated 1988, 2003": each record's years;
- a "Report" link per record whose report is in Digitala Stadsmuseet (report_url), and the credit, CREDIT.
"""
import re

import numpy as np
import pandas as pd
import shapely

from .plaques import house_numbers, known_street
from .privacy import normalise, phrases
from .textfold import fold

CREDIT = "Stadsmuseet i Stockholm"
REPORT_URL = "https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/?BR={n}"
REPORT_RE = re.compile(re.escape(REPORT_URL.split("{")[0]) + r"[1-9]\d{0,5}")
MEDIEVAL = "1100-1400-talet"     # the register's category labels (/api/brCategories), matched by label, not id
DENDRO = "Dendrokronologi"
COVER = 0.5      # a footprint at least half inside a record's polygon is one the record covers
INSIDE = 0.5     # a polygon at least half inside one footprint (the investigated part of one building) is on it
TOUCH_M2 = 1.0   # less overlap than this is a shared wall drawn twice, not a candidate
YEAR_MIN = 1900  # the register's investigations run from 1918

# A felling year as the descriptions write it: "fällningsår 1676", "fällningsåren 1642-1645", "fällt efter 1486",
# "fälldes vintern 1596-1597", "fällda 1640". `after`: a lower bound only; `to`: a span.
FELLING = re.compile(r"\bf[äa]ll(?:ningså(?:r|ren|ret)|t|d|da|des|ts)\b\s*(?:(?:år|åren|vintern|sommaren|hösten|"
                     r"våren|ca|omkring|cirka)\s+)*(?P<after>(?:efter|tidigast|före)\s+)?(?:(?:år|vintern)\s+)?"
                     r"(?P<year>1[0-9]{3})(?:\s*[-–/]\s*(?P<to>[0-9]{2,4}))?", re.IGNORECASE)
MORE_YEARS = re.compile(r"\s*(?:,|och|eller|samt|resp\.?|respektive)\s*(?:år\s+)?1[0-9]{3}\b", re.IGNORECASE)
UNSURE = re.compile(r"\s*\(?\s*osäker", re.IGNORECASE)
ADDRESS = re.compile(r"^(?P<street>[^\d]+?)\s+(?P<nums>\d.*)$")


def felling_year(text: str) -> int | None:
    """The one felling year a description states plainly, else None: no felling year, a span ("fällningsåren
    1642-1645", BR 286), a lower bound ("fällt efter 1488") or several (BR 492's twelve samples), or one marked
    uncertain. A tolerance ("1676 (plusminus 10 år)", BR 285) keeps the year."""
    found = []
    for m in FELLING.finditer(str(text or "")):
        rest = text[m.end():]
        plain = not m.group("after") and not m.group("to") and not MORE_YEARS.match(rest) and not UNSURE.match(rest)
        found.append(int(m.group("year")) if plain else None)
    return found[0] if len(found) == 1 else None


def category_labels(categories: list[dict]) -> dict[int, str]:
    """{id: label} from /api/brCategories' list."""
    return {int(c["id"]): str(c["label"]) for c in categories}


def years(rec: dict) -> tuple[int, int] | None:
    """(from, to) of the investigation: year_earliest..year_latest, either standing for both; None without one."""
    a, b = rec.get("year_earliest"), rec.get("year_latest")
    a, b = (a if a is not None else b), (b if b is not None else a)
    if a is None or not (YEAR_MIN <= int(a) <= int(b)):
        return None
    return int(a), int(b)


def report_url(rec: dict) -> str:
    """The record's report in Digitala Stadsmuseet (https, by BR number), or "" when it has none."""
    return REPORT_URL.format(n=int(rec["id"])) if rec.get("digital_archive_link_exists") is True else ""


def facts(recs: list[dict], labels: dict[int, str]) -> dict:
    """The card's `br` entry for one footprint's records: {medieval?, felled?, inv: [{from?, to?, report?}], credit}.
    `labels`: category_labels()."""
    def has(rec, label):
        return any(labels.get(int(c)) == label for c in rec.get("categories") or [])

    medieval = any(has(r, MEDIEVAL) and not has(r, DENDRO) for r in recs)
    felled = sorted({y for r in recs if has(r, DENDRO) and (y := felling_year(r.get("description"))) is not None})
    inv = []
    for r in sorted(recs, key=lambda r: (years(r) or (9999, 9999), int(r["id"]))):
        y, url = years(r), report_url(r)
        inv.append({**({"from": y[0], "to": y[1]} if y else {}), **({"report": url} if url else {})})
    return {**({"medieval": True} if medieval else {}), **({"felled": felled} if felled else {}), "inv": inv,
            "credit": CREDIT}


def parse_address(text: str) -> tuple[list[tuple[str, list[str]]], bool]:
    """([(street, [numbers])], whether a part named only a street): "Stora Nygatan 1, Stora Gråmunkegränd 10",
    "Bollhusgränd 6-8", "Skeppar Olofs Gränd (Slottsbacken)" (a street alone), "Västerlånggatan 33, 35"."""
    out, street_only, last = [], False, None
    for part in re.split(r"[,/;]|\boch\b", re.sub(r"\([^)]*\)", " ", str(text or ""))):
        part = " ".join(part.split())
        if not part:
            continue
        m = ADDRESS.match(part)
        if m:
            last = m.group("street")
            out.append((last, house_numbers(m.group("nums").split())))
        elif part[0].isdigit() and last:
            out.append((last, house_numbers(part.split())))
        else:
            street_only = True
    return out, street_only


def by_address(addrs: list[tuple[str, list[str]]], table: pd.DataFrame, streets: set[str]) -> list[int]:
    """The footprints any of the addresses sits on in s02_addresses' table (gid, street, number), the street as the
    City writes it (plaques.known_street)."""
    if table.empty or not addrs:
        return []
    folded = table.street.map(fold)
    gids = set()
    for street, nums in addrs:
        s = known_street(street, streets)
        if s is not None:
            gids |= set(table.gid[(folded == s) & table.number.isin(nums)].astype(int))
    return sorted(gids)


def polygons(features: list[dict]) -> dict[int, object]:
    """{BR number: its (multi)polygon, the union of its features} from the WFS layer (EPSG:3011)."""
    parts: dict[int, list] = {}
    for f in features:
        n, g = (f.get("properties") or {}).get("BRNummer"), f.get("geometry")
        if n is None or not g:
            continue
        geom = shapely.make_valid(shapely.geometry.shape(g))
        if not geom.is_empty:
            parts.setdefault(int(n), []).append(geom)
    return {n: shapely.union_all(gs) for n, gs in parts.items()}


def covered(poly, b, tree) -> tuple[list[int], bool]:
    """(the footprints `poly` covers: COVER of a footprint inside it, else the one footprint holding INSIDE of it;
    whether it touches any footprint at all). `b`: footprints (gid, geometry); `tree`: shapely.STRtree of b."""
    idx = tree.query(poly, predicate="intersects")
    if not len(idx):
        return [], False
    geoms = b.geometry.to_numpy()[idx]
    inter = shapely.area(shapely.intersection(geoms, poly))
    keep = inter >= TOUCH_M2
    if not keep.any():
        return [], False
    gids = b.gid.to_numpy()[idx]
    share = inter / np.maximum(shapely.area(geoms), 1e-9)
    hits = sorted(int(g) for g in gids[keep & (share >= COVER)])
    if not hits and poly.area > 0:
        inside = inter / poly.area
        best = int(np.argmax(inside))
        if inside[best] >= INSIDE:
            hits = [int(gids[best])]
    return hits, True


def place(recs: list[dict], polys: dict[int, object], b, table: pd.DataFrame) -> list[dict]:
    """Each record as {id, gids, how, why}: how "polygon" or "address" when placed; why "ambiguous: …" or
    "unplaced: …" when not (gids empty). `b`: footprints (gid, geometry, EPSG:3011); `table`: s02_addresses'."""
    tree = shapely.STRtree(b.geometry.to_numpy())
    streets = {fold(s) for s in table.street.unique()} if len(table) else set()
    out = []
    for r in recs:
        n = int(r["id"])
        gids, touched = covered(polys[n], b, tree) if n in polys else ([], False)
        if gids:
            out.append({"id": n, "gids": gids, "how": "polygon", "why": ""})
            continue
        addrs, street_only = parse_address(r.get("address"))
        gids = by_address(addrs, table, streets)
        if gids:
            out.append({"id": n, "gids": gids, "how": "address", "why": ""})
            continue
        why = ("ambiguous: its polygon touches footprints but covers none" if touched
               else "ambiguous: its address names only a street" if street_only and not addrs
               else "unplaced: no polygon" if n not in polys and not addrs
               else "unplaced: on no footprint, by polygon or address")
        out.append({"id": n, "gids": [], "how": "", "why": why})
    return out


def cards(recs: list[dict], placed: list[dict], labels: dict[int, str]) -> dict[int, dict]:
    """{gid: facts()} over the placed records."""
    by_id = {int(r["id"]): r for r in recs}
    on: dict[int, list[dict]] = {}
    for p in placed:
        for g in p["gids"]:
            on.setdefault(int(g), []).append(by_id[p["id"]])
    return {g: facts(rs, labels) for g, rs in sorted(on.items())}


def blocks(found: set[str]) -> set[str]:
    """The kvarter names of normalised designations ("exempel", "tre kronor"), without the shorter forms
    privacy.phrases adds by dropping a first word ("kronor", "större")."""
    bases = {m.group(1) for d in found if (m := re.fullmatch(r"(\D+?) \d+(?::\d+)?[a-z]?", d))}
    return {b for b in bases if not any(o != b and o.endswith(" " + b) for o in bases)}


def designations(recs: list[dict]) -> set[str]:
    """The register's property designations, normalised as s99 compares them (privacy.normalise and phrases): each
    record's own, and the former ones its description names in one of those kvarter ("f d Exempel 3, 4, 5 och 9",
    "Exempel f d 6 och 7" as far as phrases reads them), never an address ("Stora Nygatan 1"). s99 refuses any of them
    in a shipped file."""
    own = set()
    for r in recs:
        d = str(r.get("property_denotation") or "")
        own |= {normalise(d)} | set(phrases(d))
    own = {d for d in own if re.search(r"\d", d)}
    kvarter = blocks(own)
    former = {p for r in recs for p in phrases(r.get("description") or "")
              if (m := re.fullmatch(r"(\D+?) \d+(?::\d+)?[a-z]?", p)) and m.group(1) in kvarter}
    return own | former


def cached_designations(raw=None) -> set[str]:
    """designations() of s00_fetch_stadsmuseet's cache (data/raw/stadsmuseet/investigations.json), or none when this
    machine has no cache: s06_wiki leaves them out of the excerpts and s99 refuses them in any shipped file."""
    import json
    from pathlib import Path
    path = (Path("data") if raw is None else Path(raw)) / "raw" / "stadsmuseet" / "investigations.json"
    if not path.exists():
        return set()
    return designations(json.loads(path.read_text(encoding="utf-8"))["brInvestigations"])
