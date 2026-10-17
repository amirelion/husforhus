"""What is inside a carded building (s06_wiki step 4): the public institutions Wikidata places in it, for search.

An occupant is an item whose location (P276) or headquarters location (P159) is the building's item, or one the
building's item names as its occupant (P466). Only public institutions are kept: an item is kept when one of its
classes descends from KEEP and none from SKIP (companies, people, works of art), and it has a Swedish or English
label (each stands in for the other when one is missing). Its other names (sv/en aliases, "Nobelmuseet") come along,
so search finds an institution by an older name too.
"""
import re

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
        up = set().union(*(anc.get(c, {c}) for c in e["cls"]))
        sv, en = e["sv"] or e["en"], e["en"] or e["sv"]
        if not sv or not up & KEEP or up & SKIP:
            continue
        own = {fold(sv), fold(en)}
        alt = sorted({a for a in e["alt"] if len(fold(a)) >= 4 and fold(a) not in own})
        out.setdefault(b, []).append({"qid": o, "sv": sv, "en": en, "alt": alt})
    return out
