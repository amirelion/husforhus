"""Cited building years: pipeline/gamla_stan_years.csv, each row with its source and the place in it.

Hand-checked, like the landmarks (docs/research/2026-10-20-gamla-stan-years.md; the rules in
docs/research/2026-10-16-gamla-stan-ages.md §13 and §14), but no landmark: s02_years writes them as codes.SRC_CITED,
and private houses keep their decade-only rule. Keyed by footprint, so a row survives renumbered gids. Columns:
  key         the footprint: its LOD1 UUID (buildings.parquet `uuid`), or "oid:<n>" for one the City's data gives no
              UUID (its LOD1 object id, buildings.parquet `oid`, only where its `uuid` is empty); either way it must
              name exactly one footprint, and two keys never name the same one (rows refuses both). A file whose first
              column is still headed `uuid` (before 2026-10-20) is read as `key`
  year_from   first year the source gives, 1000..2026
  year_to     last year; a decade is a span ("built in the 1640s": 1640, 1649), a century too, and so are the parts of
              one the card names (web/card.js when): its beginning (1600-1624), its middle (1640-1660), its end
              (1675-1699), "the late 1630s or the early 1640s" (1635-1644) and "1500 to the mid-1600s" (1500-1649)
  circa       "true" where the source says "about" one year ("omkring 1640": 1640, 1640, true), so the card says "about
              1640"; empty otherwise (a file without the column, from before 2026-10-20's evening, is read with it
              empty). Never on a period (approximate already) or a span
  kind        built | rebuilt_from_new | period | either | rebuilt | also
              built: the standing house was built then; rebuilt_from_new: a new house replaced an older one then;
              period: the source gives only a century, a half-century or a period for the standing house (yflag PERIOD).
              A built span on century or half-century bounds (1600-1699, 1650-1699), or one over BUILT_MAX years, is
              refused: that is a period, which gets "≈" and the 3/4 rule, not a first year shown as exact.
              either: two sources differ and both readings are shown ("Built in 1785 or 1798 (sources differ)",
              decided 2026-10-20): exactly two either rows on one key, each with its own source, its own span (a
              year, a decade, a span or a period) and its own place or page. The footprint is PERIOD where one map
              period holds 3/4 of the two readings, each counting the same however long its span (year_of), else it
              has no colour; the card shows both readings either way, each linked to its source (card_entry).
              rebuilt: a later rebuild, extension, raised storey or new facade of the house, beside the footprint's
              primary row (one built, rebuilt_from_new or period row, or an either pair): the card adds "Rebuilt or
              extended 1780" linked to its source; it never sets the year or the colour. Any span (a year, a decade,
              "in the 1600s") starting after the primary's last year; several make "Rebuilt or extended 1780 and
              1906".
              also: another house on the footprint that a source dates on its own (two houses the City's data draws as
              one: Stortorget 18 and 20, the Sparre palace and Kammarrätten's house), beside the primary row: the
              card adds "Also part of this building: a house built 1804", linked to its source; it never sets the year
              or the colour, and its span may come before the primary's or after it.
              One key carries one primary row, or an either pair, and any number of rebuilt and also rows; nothing
              else repeats a key (read refuses it)
  source      one of SOURCES
  place       the record's own page: a Wikipedia revision by its id alone (https://sv.wikipedia.org/w/index.php?oldid=N;
              no article title, D49), a KulturNav entry, or a City Museum document in Digitala Stadsmuseet: one of the
              CC BY inventories (CC_BY_INVENTORIES) or a report the museum's register links (s99 checks that)
  page        the page of a City Museum PDF the year is on; empty for the other sources
  quote       the source's words, at most QUOTE_WORDS words, without a property designation (s99 checks it): a short
              quotation from Wikipedia (CC BY-SA 4.0) or KulturNav (CC0), linked to its revision or entry by `place`;
              required for those two, empty for the City Museum's (its text never enters git: decided 2026-10-20).
              Wikipedia's own words only: a sentence the article quotes from someone else (inside quotation marks,
              relayed()) is not Wikipedia's text; cite the work it quotes instead (the network test refuses one)
  confidence  high | medium (low stays on hold, in the research note)
  note        one line for the reviewer, in our own words: why this year, what else the sources say

Nothing but each row's `source`, `place`, whether it says "about" and, for an either, rebuilt or also row (or a period
the map cannot colour), its years reaches the web (the card's `yc`, card_entry); the quote and the note stay in the
repo.

The year a footprint publishes (year_of): a decade shows its start (like a Wikidata decade, so the card reads
"1640s"); another built span follows yearrules.display (a completion year up to RANGE_MAX years, else the first year,
LONG). A period row is PERIOD when one map period (city.PERIODS) holds at least PERIOD_SHARE of its span (decided
2026-10-20), an either pair when one holds that share of its two readings, each counting the same (a medieval reading
from FLOOR_YEAR would otherwise outweigh any other by its length alone): the map colours it with that period and the
card says "≈" (web/card.js). Its `year` places it on the timeline (the period colour needs one too): the middle of the
overlap with that period (a house of the 1600s in 1655), but the overlap's end where the span starts at FLOOR_YEAR,
which says only that no earlier bound is known (a medieval house, 1000-1520, stood by 1520; the midpoint, 1260, would
raise the medieval town before its church). A span no map period holds that much of ("1580–1650" straddles 1610/1611
with 31 and 40 years) gets no colour: year_of gives UNKNOWN, and s02_years clears what a lower tier (RAÄ's area,
Wikidata, OSM) wrote on the footprint, keeps the estimate off it and lists it (review-years.json `cited_no_period`), so
the building is drawn uncoloured; its card still gives what the record says (card_entry's `a`, `z`, or the either's
two readings). A period row on a footprint a Wikidata or OSM year dates inside the row's span is not applied: the
record is the more precise (`cited_period_vs_record`; an either pair is applied: its two readings are the hand-checked
answer).
"""
import re
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

from . import city, codes
from .ssm_archive import ARCHIVE, REPORT_RE
from .yearrules import FLOOR_YEAR, LATEST_YEAR, display

PATH = Path(__file__).with_name("gamla_stan_years.csv")
COLUMNS = ["key", "year_from", "year_to", "circa", "kind", "source", "place", "page", "quote", "confidence", "note"]
LEGACY_KEY = "uuid"     # the first column's name before 2026-10-20, when every key was a uuid: read() renames it
PRIMARY = ("built", "rebuilt_from_new", "period")    # one such row alone dates its footprint
LATER = ("rebuilt", "also")                          # rows beside the primary that never date the footprint
KINDS = PRIMARY + ("either",) + LATER
CIRCA = ("", "true")
CONFIDENCE = ("high", "medium")
QUOTE_WORDS = 25
NOTE_MAX = 300
PERIOD_SHARE = (3, 4)   # a period row is coloured by the map period that holds at least 3/4 of its span
BUILT_MAX = 100         # a built span longer than this is a period (a construction window can run 50+ years: 1697-1754)
YEAR = re.compile(r"\d{4}")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OID = re.compile(r"oid:([1-9]\d{0,17})")     # a footprint the City's data gives no UUID: its LOD1 object id
# The City Museum's building inventories whose own licence (Digitala Stadsmuseet's field 590) is CC BY: the 32 read
# from the archive on 2026-10-20 (docs/research/2026-10-20-gamla-stan-years.md). Eight more in the same folder are
# CC BY-NC-SA (10043887, 10043897, 10043899, 10043902, 10043903, 10043920, 10043921, 10043932): a row may cite one of
# those only as a report the register links (ssm_br, the museum's permission of 2026-10-19), never as an inventory.
CC_BY_INVENTORIES = frozenset({
    "10043888", "10043895", "10043925", "10043928", "10043929", "10043930", "10043933", "10043934", "10043935",
    "10043936", "10043937", "10043938", "10043939", "10043940", "10043941", "10043943", "10043944", "10043945",
    "10043946", "10043947", "10043948", "10043950", "10043951", "10043953", "10043954", "10043955", "10043957",
    "10043958", "10043959", "10043960", "10043961", "10043962"})
INVENTORY = re.compile(re.escape(ARCHIVE) + r"Dokument/Byggnadsinventeringar/(\d+)\.pdf\.info")
# Each source: the page a row cites (fullmatch), its sources.yml entry (the credit), whether a page number is needed
# and whether a quote is.
SOURCES = {
    "kulturnav": {"place": re.compile(r"https://kulturnav\.org/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"),
                  "credit": "kulturnav", "page": False, "quote": True},
    "wikipedia_sv": {"place": re.compile(r"https://sv\.wikipedia\.org/w/index\.php\?oldid=\d+"),
                     "credit": "wikipedia", "page": False, "quote": True},
    "ssm_inventory": {"place": INVENTORY, "credit": "stadsmuseet_inventories", "page": True, "quote": False},
    "ssm_br": {"place": REPORT_RE, "credit": "stadsmuseet_br", "page": True, "quote": False},
}
PERIOD_BOUNDS = [(p[3], min(p[4], LATEST_YEAR)) for p in city.PERIODS]


class Refused(ValueError):
    """A row the pipeline will not apply where it stands: the message names it and why."""


def place_ok(source: str, place: str) -> bool:
    """True where `place` is a page a row of `source` may cite: its source's form, and for an inventory one of the
    CC BY ones (CC_BY_INVENTORIES)."""
    src = SOURCES.get(source)
    m = src["place"].fullmatch(place or "") if src else None
    return bool(m) and (source != "ssm_inventory" or m.group(1) in CC_BY_INVENTORIES)


def is_place(s: str) -> bool:
    """True where s is a page one of the sources' rows may cite (s99's privacy check: such a link's digits are no FNR)."""
    return any(place_ok(name, s) for name in SOURCES)


def century_like(year_from: int, year_to: int) -> bool:
    """True for a span a source gives as a century or half-century (both ends on a 50-year boundary: 1600-1699,
    1650-1699, KulturNav's 1600-1700) or longer than BUILT_MAX years: a period, never a construction window."""
    n = year_to - year_from + 1
    return n > BUILT_MAX or (n >= 50 and year_from % 50 == 0 and year_to % 50 in (0, 49))


def row_errors(r: dict) -> list[str]:
    """What is wrong with one row on its own (the rows of one key together: key_errors; the footprint's checks come
    where it is applied)."""
    e = []
    if not (UUID.fullmatch(r["key"]) or OID.fullmatch(r["key"])):
        e.append("key is not a lowercase UUID or oid:<n>")
    if not (YEAR.fullmatch(r["year_from"]) and YEAR.fullmatch(r["year_to"])
            and FLOOR_YEAR <= int(r["year_from"]) <= int(r["year_to"]) <= LATEST_YEAR):
        e.append(f"year_from..year_to is not a span inside {FLOOR_YEAR}..{LATEST_YEAR}")
    elif r["kind"] == "period" and r["year_from"] == r["year_to"]:
        e.append("a period is a span, not one year")
    elif r["kind"] in ("built", "rebuilt_from_new") and century_like(int(r["year_from"]), int(r["year_to"])):
        e.append(f"a century, a half-century or a span over {BUILT_MAX} years is kind period, not {r['kind']}")
    elif r.get("circa", "") and (r["kind"] == "period" or r["year_from"] != r["year_to"]):
        e.append('circa is for one year a source gives as "about" ("omkring 1640"), never a period or a span')
    if r.get("circa", "") not in CIRCA:
        e.append("circa is true or empty")
    if r["kind"] not in KINDS:
        e.append(f"kind {r['kind']!r}")
    src = SOURCES.get(r["source"])
    if src is None:
        e.append(f"source {r['source']!r}")
    else:
        if not src["place"].fullmatch(r["place"]):
            e.append(f"place is not a {r['source']} page"
                     + (" (a revision by its oldid alone, no article title)" if r["source"] == "wikipedia_sv" else ""))
        elif not place_ok(r["source"], r["place"]):
            e.append("place is not one of the City Museum's CC BY inventories (CC_BY_INVENTORIES)")
        if src["page"] != bool(r["page"]) or (r["page"] and not r["page"].isdigit()):
            e.append("page is a page number for a City Museum PDF only")
        if src["quote"] != bool(r["quote"].strip()):
            e.append("quote is required for KulturNav and Wikipedia and empty for the City Museum")
    if len(r["quote"].split()) > QUOTE_WORDS or "\n" in r["quote"]:
        e.append(f"quote is more than {QUOTE_WORDS} words or one line")
    if r["confidence"] not in CONFIDENCE:
        e.append(f"confidence {r['confidence']!r} (low stays on hold)")
    if not r["note"].strip() or len(r["note"]) > NOTE_MAX or "\n" in r["note"]:
        e.append(f"note must be one line of 1 to {NOTE_MAX} characters")
    return e


def key_errors(rs: list[dict]) -> list[str]:
    """What is wrong with the rows of one key together (each well formed on its own): one primary row (built,
    rebuilt_from_new or period) or an either pair, exactly two either rows with two different spans from two different
    places (or pages), and rebuilt and also rows only beside a primary, a rebuilt one after the primary's last year,
    none repeated."""
    kinds = [r["kind"] for r in rs]
    n_primary, n_either = sum(k in PRIMARY for k in kinds), kinds.count("either")
    e = []
    if n_either and n_either != 2:
        e.append(f"an either is exactly two rows on one key, not {n_either}")
    if n_either and n_primary:
        e.append("an either pair is the footprint's primary row: no built, rebuilt_from_new or period row beside it")
    if n_primary > 1:
        e.append(f"{n_primary} primary rows (built, rebuilt_from_new or period) on one key: a footprint has one, or an "
                 "either pair where two sources differ (another house on it is an also row)")
    if not n_primary and not n_either:
        e.append("a rebuilt or also row needs its footprint's primary row (built, rebuilt_from_new, period or an "
                 "either pair)")
    if e:
        return e
    either = [r for r in rs if r["kind"] == "either"]
    if either:
        (a, b) = either
        if (a["year_from"], a["year_to"]) == (b["year_from"], b["year_to"]):
            e.append("the two either rows give the same span: one row says it")
        if (a["place"], a["page"]) == (b["place"], b["page"]):
            e.append("the two either rows cite the same place: an either is two sources that differ")
    last = max(int(r["year_to"]) for r in rs if r["kind"] not in LATER)
    for kind in LATER:
        spans = [(int(r["year_from"]), int(r["year_to"])) for r in rs if r["kind"] == kind]
        if kind == "rebuilt" and any(a <= last for a, _ in spans):
            e.append(f"a rebuilt row starts by the primary's last year ({last}): a rebuild comes after the house it "
                     "rebuilds (another house on the footprint is an also row)")
        if len(set(spans)) < len(spans):
            e.append(f"two {kind} rows give the same span")
    return e


def read(path: Path = PATH) -> pd.DataFrame:
    """The table, every row checked on its own (row_errors) and every key's rows together (key_errors). A file whose
    first column is headed `uuid` (LEGACY_KEY) is read with it as `key`, and one without `circa` with that empty."""
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(t.columns[:1]) == [LEGACY_KEY]:
        t = t.rename(columns={LEGACY_KEY: "key"})
    if "circa" not in t.columns and list(t.columns) == [c for c in COLUMNS if c != "circa"]:
        t.insert(COLUMNS.index("circa"), "circa", "")
    if list(t.columns) != COLUMNS:
        raise ValueError(f"{path}: the columns are {list(t.columns)}, not {', '.join(COLUMNS)}")
    bad = {f"row {i + 1} ({r['key']})": e for i, r in enumerate(t.to_dict("records")) if (e := row_errors(r))}
    if bad:
        raise ValueError(f"{path}: {bad}")
    bad = {k: e for k, rs in by_key(t).items() if (e := key_errors(rs))}
    if bad:
        raise ValueError(f"{path}: {bad}")
    return t


def empty() -> pd.DataFrame:
    """A table without rows: what a build given no table (a fixture's) works with."""
    return pd.DataFrame({c: pd.Series([], dtype=str) for c in COLUMNS})


def by_key(t: pd.DataFrame) -> dict[str, list[dict]]:
    """t's rows by key, in the table's order, each row a dict with its 0-based position in t as `_i`."""
    out: dict[str, list[dict]] = {}
    for i, r in enumerate(t.to_dict("records")):
        out.setdefault(r["key"], []).append({**r, "_i": i})
    return out


def footprint(rs: list[dict]) -> dict:
    """One key's rows as the footprint takes them: {kind, year_from, year_to, circa, source, place, options, rebuilt,
    also}. kind is the primary row's, or "either"; the span is the primary's, or the either pair's union; circa whether
    the primary says "about" (an either's readings carry their own); source and place are the primary's, or the pair's
    joined with " or " and " " (the review lists'); options: an either pair's two readings, rebuilt: the rebuilt rows
    and also: the also rows, each as {a, z, s, u} (and c: True where it says "about"), earliest first."""
    def reading(r):
        o = {"a": int(r["year_from"]), "z": int(r["year_to"]), "s": r["source"], "u": r["place"]}
        return {**o, "c": True} if r.get("circa") == "true" else o

    def order(rows):
        return sorted((reading(r) for r in rows), key=lambda o: (o["a"], o["z"], o["s"], o["u"]))

    either = order(r for r in rs if r["kind"] == "either")
    rebuilt = order(r for r in rs if r["kind"] == "rebuilt")
    also = order(r for r in rs if r["kind"] == "also")
    if either:
        return {"kind": "either", "year_from": min(o["a"] for o in either), "year_to": max(o["z"] for o in either),
                "circa": False, "source": " or ".join(o["s"] for o in either),
                "place": " ".join(o["u"] for o in either), "options": either, "rebuilt": rebuilt, "also": also}
    p = next(r for r in rs if r["kind"] in PRIMARY)
    return {"kind": p["kind"], "year_from": int(p["year_from"]), "year_to": int(p["year_to"]),
            "circa": p.get("circa") == "true", "source": p["source"], "place": p["place"], "options": [],
            "rebuilt": rebuilt, "also": also}


def _period(spans: list[tuple[int, int]]) -> tuple[int, int] | None:
    """The bounds of the map period that holds PERIOD_SHARE of the spans, each span counting the same however long it
    is (for one span: of its years); None where none does."""
    num, den = PERIOD_SHARE
    for a, b in PERIOD_BOUNDS:
        held = sum(Fraction(max(0, min(z, b) - max(f, a) + 1), z - f + 1) for f, z in spans)
        if den * held >= num * len(spans):
            return a, b
    return None


def year_of(kind: str, year_from: int, year_to: int, options: list[dict] | None = None) -> tuple[int, int]:
    """(year, yflag) a footprint publishes (the module docstring); (0, UNKNOWN) for a period, or an either pair, no map
    period holds PERIOD_SHARE of. An either pair's span is its union, and `options` its two readings ({a, z} each),
    each counting the same: a medieval reading (from FLOOR_YEAR) cannot outweigh the other by its length."""
    if kind in ("period", "either"):
        if kind == "either" and not options:
            raise ValueError("an either pair's year needs its two readings (options)")
        p = _period([(year_from, year_to)] if kind == "period" else [(o["a"], o["z"]) for o in options])
        if p is None:
            return 0, codes.UNKNOWN
        lo, hi = max(year_from, p[0]), min(year_to, p[1])
        # no earlier bound than FLOOR_YEAR: the house stood by the overlap's end; else the overlap's middle
        return (hi if year_from == FLOOR_YEAR else (lo + hi) // 2), codes.PERIOD
    if year_from % 10 == 0 and year_to == year_from + 9:
        return year_from, codes.RANGE
    y, f = display(np.array([year_from]), np.array([year_to]))
    return int(y[0]), int(f[0])


def footprint_year(f: dict) -> tuple[int, int]:
    """year_of for a footprint() (its kind, its span and an either pair's two readings)."""
    return year_of(f["kind"], f["year_from"], f["year_to"], f["options"])


def footprints(keys, b: pd.DataFrame) -> dict[str, list[int]]:
    """Each key: the gids of b it names, a uuid by b.uuid and "oid:<n>" by b.oid (none where b has no oid column)."""
    have = b.uuid.fillna("").astype(str)
    by_uuid = b.gid[have != ""].groupby(have[have != ""]).agg(list)
    by_oid = b.gid.groupby(b.oid.astype("int64")).agg(list) if "oid" in b else pd.Series(dtype=object)
    out = {}
    for k in dict.fromkeys(keys):
        m = OID.fullmatch(k)
        found = by_oid.get(int(m.group(1)), []) if m else by_uuid.get(k, [])
        out[k] = [int(g) for g in found]
    return out


def missing(t: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    """The keys of t on no footprint of b: a fixture build, or a footprint the City has since redrawn."""
    return [k for k, gids in footprints(t.key, b).items() if not gids]


def clashes(where: dict[str, list[int]], b: pd.DataFrame) -> list[str]:
    """What is wrong with the keys' footprints (footprints()) together: a key on several footprints, two keys on one
    footprint (the second would overwrite the first, its card twice), and an "oid:<n>" key on a footprint the City
    gives a UUID (its key is the UUID: an oid is only for a footprint without one)."""
    out = [f"keys on several footprints: {k}" for k, gids in where.items() if len(gids) > 1]
    on: dict[int, list[str]] = {}
    for k, gids in where.items():
        for g in gids:
            on.setdefault(g, []).append(k)
    out += [f"keys {ks} name one footprint (gid {g}): one key per footprint" for g, ks in on.items() if len(ks) > 1]
    uuid_of = dict(zip(b.gid.astype(int), b.uuid.fillna("").astype(str)))
    out += [f"{k} names a footprint the City gives a UUID ({uuid_of[g]}): key the row by that"
            for k, gids in where.items() if OID.fullmatch(k) for g in gids if uuid_of.get(g)]
    return out


def rows(t: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """One row per footprint the table dates on this build, indexed by gid: year, year_from, year_to, yflag, kind,
    source, place (footprint(): an either pair as one row, its union span; rebuilt and also rows never set the year). A
    period or an either pair no map period holds enough of has yflag UNKNOWN: s02_years lists it and leaves the
    footprint as it was. A key on no footprint is skipped with a warning; one on several footprints, two keys on one,
    and an oid key on a footprint with a UUID are refused (Refused, clashes)."""
    cols = ["year", "year_from", "year_to", "yflag", "kind", "source", "place"]
    where = footprints(t.key, b)
    for k in sorted(k for k, gids in where.items() if not gids):
        print(f"warning: cited: {k}: its footprint is not among these buildings (a fixture build, or the City redrew "
              "it?); skipped", file=sys.stderr)
    if bad := clashes(where, b):
        raise Refused("; ".join(bad))
    out = []
    for k, rs in by_key(t).items():
        if not where[k]:
            continue
        f = footprint(rs)
        y, fl = footprint_year(f)
        out.append({"gid": where[k][0], "year": y, "year_from": f["year_from"], "year_to": f["year_to"], "yflag": fl,
                    "kind": f["kind"], "source": f["source"], "place": f["place"]})
    if not out:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="gid"))
    return pd.DataFrame(out).set_index("gid")[cols]


def _words(wikitext: str) -> str:
    """Wikitext without references, templates, link targets and bold or italic marks; line breaks kept."""
    t = re.sub(r"<ref[^>]*/>", "", wikitext)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    for _ in range(3):                                   # nested templates, innermost first
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    return t.replace("'''", "").replace("''", "")


def plain(wikitext: str) -> str:
    """A revision's wikitext as its reader sees the words, for checking a row's quote (the network test in
    tests/test_cited.py does): references and templates out, a link as its shown text, no bold or italic marks, one
    space between words."""
    return " ".join(_words(wikitext).split())


QUOTE_MARKS = "\"”“„«»"
QUOTED = re.compile(f"([{QUOTE_MARKS}])([^{QUOTE_MARKS}]+)([{QUOTE_MARKS}])")


def relayed(wikitext: str, quote: str) -> bool:
    """True when a row's quote is, in the revision, inside a quotation (”…”, “…”, „…“, »…», «…», "…"): words the
    article quotes from another work (a museum report, say), not Wikipedia's own, so not its CC BY-SA text. Read per
    paragraph, as plain() reads the words; a quotation wholly inside the row's quote (a house name in ”…”) is fine."""
    q = " ".join(quote.split())
    for para in re.split(r"\n\s*\n", _words(wikitext)):
        p = " ".join(para.split())
        s = p.find(q)
        while s >= 0:
            e = s + len(q)
            for m in QUOTED.finditer(p):
                if s < m.end(2) and e > m.start(2) and not (s <= m.start() and m.end() <= e):
                    return True
            s = p.find(q, s + 1)
    return False


# KulturNav's "Byggnader i Sverige" (ArkDes), the one KulturNav dataset sources.yml credits, and its licence, CC0 1.0
KULTURNAV_DATASET = "1f23ddae-5579-4e3e-bf59-a29524e4f926"
KULTURNAV_CC0 = "c223fa3f-84eb-4c42-ac63-e544ebf4c609"
KN_YEAR = re.compile(r"\s*(\d{4})")


def kulturnav_entry(entry: dict) -> dict:
    """What the network test checks in a KulturNav entry (the JSON at kulturnav.org/<uuid>.json): {dataset, licence,
    built}: the ids of its dataset and licence (a row is credited as ArkDes' CC0 "Byggnader i Sverige", so both must be
    those), and the (from, to) years of each construction event, the one captioned "Uppförande" (a timespan "1600-Y" or
    "1600?-Y" is read as 1600); never another event's years (a rebuild's)."""
    props = entry.get("properties") or {}

    def ref(key):
        v = (props.get(key) or [{}])[0].get("value")
        return v if isinstance(v, str) else ""

    built = []
    for act in props.get("construction.activity") or []:
        v = act.get("value") if isinstance(act.get("value"), dict) else {}
        if (v.get("caption") or {}).get("sv") != "Uppförande":
            continue
        span = ((v.get("properties") or {}).get("event.timespan") or [{}])[0].get("value") or {}
        ends = [((span.get("properties") or {}).get(k) or [{}])[0].get("value") for k in ("timespan.start",
                                                                                             "timespan.end")]
        years = [KN_YEAR.match(e) if isinstance(e, str) else None for e in ends]
        if all(years):
            built.append((int(years[0].group(1)), int(years[1].group(1))))
    return {"dataset": ref("entity.dataset"), "licence": ref("superconcept.license"), "built": built}


# ---- s03_tiles

def card_entry(rs: list[dict], ysrc: int) -> dict | None:
    """A footprint's card `yc` from its rows (one key's) and the source its year ships with (ysrc); None where the card
    gets none. Never a quote or a note. The footprint ships a cited year (ysrc SRC_CITED), or none at all because its
    period or either pair has no map period (year_of: UNKNOWN; the card still says what the records give):
      a primary row: {s: source, u: place, k: "rebuilt" for rebuilt_from_new, c: True where it says "about"}, with
                     a, z (its span) where no year ships (the card cannot read the span from the building)
      an either pair: {e: [{a, z, s, u}, {a, z, s, u}]}, earliest first
      either way, the rebuilt rows, r: [{a, z, s, u}, ...], and the also rows (another house on the footprint), o:
      [{a, z, s, u}, ...], earliest first; a reading that says "about" carries c: True
    A footprint another tier dates (RAÄ, a landmark, a more precise Wikidata or OSM year, a reader) gets none."""
    f = footprint(rs)
    shipped = ysrc == codes.SRC_CITED
    unplaced = footprint_year(f)[1] == codes.UNKNOWN
    if not (shipped or (unplaced and ysrc == codes.SRC_NONE)):
        return None
    if f["kind"] == "either":
        yc = {"e": f["options"]}
    else:
        yc = {"s": f["source"], "u": f["place"]}
        if f["kind"] == "rebuilt_from_new":
            yc["k"] = "rebuilt"
        if f["circa"]:
            yc["c"] = True
        if not shipped:
            yc["a"], yc["z"] = f["year_from"], f["year_to"]
    if f["rebuilt"]:
        yc["r"] = f["rebuilt"]
    if f["also"]:
        yc["o"] = f["also"]
    return yc


def cards(shards: list[dict], df: pd.DataFrame, t: pd.DataFrame, hide: np.ndarray, withheld=frozenset()) -> int:
    """The card's `yc` (card_entry) on each cited footprint that is not hidden, in place (s03_tiles.card_shards'
    output; df: gid, uuid, oid, ysrc); returns how many. A private house gets none: its record would state the year the
    card shows only as its decade; nor does a takedown (`withheld`: its gids; s99 refuses a row on one anyway)."""
    where = footprints(t.key, df)
    shared = {g for g, n in Counter(g for gids in where.values() for g in gids).items() if n > 1}
    pos = pd.Series(np.arange(len(df)), index=df.gid.to_numpy())
    n = 0
    for k, rs in by_key(t).items():
        if len(where[k]) != 1 or where[k][0] in shared:      # refused by rows (clashes): no card either
            continue
        g = where[k][0]
        i = int(pos[g])
        if hide[i] or g in withheld:
            continue
        yc = card_entry(rs, int(df.ysrc.iat[i]))
        if yc is None:
            continue
        shards[g % len(shards)].setdefault(str(g), {})["yc"] = yc
        n += 1
    return n
