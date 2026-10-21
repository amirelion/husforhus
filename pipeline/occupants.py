"""What is inside a carded building (s06_wiki step 4): the public institutions Wikidata places in it, for search.

An occupant is an item whose location (P276) or headquarters location (P159) is the building's item, or one the
building's item names as its occupant (P466), by a statement that has not ended (pipeline/queries/wiki_occupants.rq).
Only public institutions are kept: an item is kept when one of its own classes descends from KEEP and none of its own
classes descends from SKIP (companies, people, works of art) without also descending from KEEP (kept()), and it has a
Swedish or English label (each stands in for the other when one is missing). Its other names (sv/en aliases,
"Nobelmuseet") come along, so search finds an institution by an older name too.

The hand-checked table pipeline/occupant_pins.csv adds what Wikidata does not link, by footprint (read_pins()).
"""
import re
import sys
from pathlib import Path

import pandas as pd

from . import cited, city
from .s00_fetch_wikidata import qid
from .textfold import fold

KEEP = {
    "Q33506",     # museum
    "Q24354",     # theatre (building)
    "Q742421",    # theatre company
    "Q153562",    # opera house
    "Q1060829",   # concert hall
    "Q7075",      # library
    "Q166118",    # archive
    "Q3917681",   # embassy
    "Q7843791",   # diplomatic mission
    "Q327333",    # government agency
    "Q2659904",   # government organisation
    "Q294414",    # public office
    "Q11204",     # legislature
    "Q41487",     # court
    "Q2385804",   # educational institution
    "Q3914",      # school
    "Q3918",      # university
    "Q162633",    # academy
    "Q955824",    # learned society
    "Q3152824",   # cultural institution
    "Q16970",     # church building
    "Q1530022",   # religious organisation
    "Q102496",    # parish
    "Q2061186",   # congregation
}
SKIP = {
    "Q4830453",   # business
    "Q783794",    # company
    "Q6881511",   # enterprise
    "Q5",         # human
    "Q838948",    # work of art
}
QID = re.compile(r"Q\d+")


def kept(classes: set[str], anc: dict[str, set[str]]) -> bool:
    """Whether an item of these (direct, P31) classes is a public institution. Each class is judged by its own
    ancestors: in Wikidata's class graph "library", "academy" and "theatre" also descend from business (Q4830453) or
    enterprise (Q6881511), so one SKIP anywhere in the union dropped Svenska Akademien, Riksbanken and Kungliga Operan
    (2026-10-21). A class that descends from SKIP alone (a bank, a company, a human) still drops the item, whatever
    its other classes are: a company that runs a museum is a company."""
    ups = [anc.get(c, {c}) for c in classes]
    return any(u & KEEP for u in ups) and not any(u & SKIP and not u & KEEP for u in ups)


def occupants_from(rows: list[dict], anc: dict[str, set[str]]) -> dict[str, list[dict]]:
    """{building qid: [{qid, sv, en, alt}, ...]} from the query's rows (b, occ, cls?, sv?, en?, alt?) and the classes'
    ancestors (years_wikidata.ancestors), sorted by occupant qid."""
    seen: dict[tuple[str, str], dict] = {}
    for r in rows:
        b, o = qid(r["b"]), qid(r["occ"])
        if b == o:
            continue
        e = seen.setdefault((b, o), {"cls": set(), "sv": "", "en": "", "alt": set()})
        if r.get("cls"):
            e["cls"].add(qid(r["cls"]))
        for lang in ("sv", "en"):
            if r.get(lang) and not QID.fullmatch(r[lang]):
                e[lang] = e[lang] or r[lang]
        if r.get("alt"):
            e["alt"].add(r["alt"])
    out: dict[str, list[dict]] = {}
    for (b, o), e in sorted(seen.items(), key=lambda kv: (kv[0][0], int(kv[0][1][1:]))):
        sv, en = e["sv"] or e["en"], e["en"] or e["sv"]
        if not sv or not kept(e["cls"], anc):
            continue
        own = {fold(sv), fold(en)}
        alt = sorted({a for a in e["alt"] if len(fold(a)) >= 4 and fold(a) not in own})
        out.setdefault(b, []).append({"qid": o, "sv": sv, "en": en, "alt": alt})
    return out


# The hand-checked table (added 2026-10-21 from the research into the key public sites search could not find,
# docs/research/2026-10-21-missing-landmarks.md): an institution Wikidata does not link to a carded building, placed
# on its footprint by hand. Columns: key (the footprint's LOD1 UUID, or "oid:<n>" for one the City's data gives no
# UUID, as pipeline/cited.py keys a row, so a row survives renumbered gids), qid (the institution's item, may be
# empty), sv, en (empty: the same as sv), alt (other names, ";" between them), source (an https URL: the Wikidata
# item, the institution's own page, or a Swedish or English Wikipedia revision by oldid), note (checked how, and
# when; one line, in our own words, no property designation). s14_search reads it (tests/test_occupants.py).
PINS = Path(__file__).with_name("occupant_pins.csv")
PIN_COLUMNS = ["key", "qid", "sv", "en", "alt", "source", "note"]
KEY = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|oid:[1-9]\d{0,17}")
SOURCE = re.compile(r"https://(?:www\.wikidata\.org/wiki/Q\d+|(?:sv|en)\.wikipedia\.org/w/index\.php\?oldid=\d+"
                    r"|(?!(?:\w+\.)?wiki[pm]edia\.org|www\.wikidata\.org)[\w.-]+\.\w+(?:/\S*)?)")
# Contact details have no place in a table that ships names to search: an e-mail address, or a run of 7+ digits
# that reads as a phone number ("+46 8 123 45 67", "08-123 45 67"; a postcode, "114 60", is five digits and a date,
# "2026-10-21", has its dashes elsewhere)
CONTACT = re.compile(r"\S@\S|\+?\d(?: ?\d){6,}|\b0\d{1,3}-\d{2,3}(?: ?\d{2}){2,}")


def read_pins(path: Path = PINS) -> pd.DataFrame:
    """The table, refused (ValueError) when malformed: a key that is neither a UUID nor oid:<n>, a qid that is not a
    Q-number, an empty Swedish name, a source that is not an https URL of the kinds above, an empty note, a cell
    that holds an e-mail address or a phone number, or one institution twice on a footprint (the same key and
    name, or the same qid)."""
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(t.columns) != PIN_COLUMNS:
        raise ValueError(f"{path}: the columns are {list(t.columns)}, not {', '.join(PIN_COLUMNS)}")
    bad = [f"row {i + 2}" for i, r in t.iterrows()
           if not KEY.fullmatch(r.key) or not (r.qid == "" or QID.fullmatch(r.qid)) or not r.sv.strip()
           or not SOURCE.fullmatch(r.source) or not r.note.strip()
           or any(CONTACT.search(r[c]) for c in ("sv", "en", "alt", "note"))
           or any(not a.strip() for a in r.alt.split(";")) and r.alt != ""]
    names = pd.Series([f"{k}\u0000{fold(s)}" for k, s in zip(t.key, t.sv)])
    twice = sorted(set(t.key[names.duplicated()]) | set(t.qid[(t.qid != "") & t.qid.duplicated()]))
    if bad or twice:
        raise ValueError(f"{path}: malformed rows {bad}" if bad else f"{path}: repeated institutions {twice}")
    return t


def pinned(t: pd.DataFrame, b: pd.DataFrame) -> dict[int, list[dict]]:
    """{gid: [{qid, sv, en, alt}, ...]} for the table's rows on b (gid, uuid, oid, kategori), in the table's order. A
    key on no footprint (a fixture build, or the City redrew it) is skipped with a warning, as wiki_pins are; a key on
    several footprints, an oid key on a footprint the City gives a UUID, or a row on a private house (city.
    PRIVATE_HOUSE_KATEGORI: search would name its home) is refused (ValueError)."""
    where = cited.footprints(t.key, b)
    problems = [p for p in cited.clashes(where, b) if not p.startswith("keys [")]   # several institutions, one house
    kat = dict(zip(b.gid.astype(int), b.kategori)) if "kategori" in b else {}
    problems += [f"{k} is a private house" for k, gids in where.items() for g in gids
                 if kat.get(g) in city.PRIVATE_HOUSE_KATEGORI]
    if problems:
        raise ValueError("; ".join(problems))
    out: dict[int, list[dict]] = {}
    for r in t.itertuples():
        if not where[r.key]:
            print(f"warning: occupant_pins: {r.sv}: its footprint is not among these buildings (a fixture build, or "
                  "the City redrew it?); skipped", file=sys.stderr)
            continue
        own = {fold(r.sv), fold(r.en or r.sv)}
        alt = [a.strip() for a in r.alt.split(";") if a.strip() and fold(a) not in own]
        out.setdefault(where[r.key][0], []).append({"qid": r.qid, "sv": r.sv, "en": r.en or r.sv, "alt": alt})
    return out
