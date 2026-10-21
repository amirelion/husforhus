"""Stockholm City Archives' card index to the building-permit files 1875-1980: reading the list pages of its search
app "Bygglov 1875–1980" (Stadsarkivet). Pure functions, no I/O: s00_fetch_bygglov fetches the pages and saves what
parse_page reads.

A list page shows how many cards the search found (the unfiltered list finds all of them, EXPECTED_TOTAL) and
PER_PAGE cards. The list is sorted by card id, so page p (the app's `sidindex`, from 0) holds the ids 10p+1 to 10p+10,
and the last page fewer. Each card is a table row of six cells: a link to the card's own page (Visa/<id>/<id>) around
a thumbnail of its scan, then Kvarter, Fastighetsnummer, Diarienummer, Avslutningsår and Aktnummer. parse_page keeps
these values as the archive wrote them (markup and entities taken out, white space collapsed, Unicode in NFC): a
kvarter in mixed case with its suffixes ("Provgården Mindre (Ka)"), numbers such as "1,3", "3013-3015" or "2:40", an
empty case number, the year "-" for a card without one. Turning them into our designations is the matcher's work.

The designations are internal research data, a join key only: never committed, never shipped.

The matcher's side (pipeline/years_bygglov.py uses these):
- fold(): one spelling for both sides: upper case, É folded to E (the index writes a kvarter's "é" as "e" where our
  register keeps the "É"; Å, Ä and Ö are never folded), white space collapsed, Unicode NFC;
- kvarter_name(): a card's kvarter folded, with its trailing parenthesis dropped ("Provgården Mindre (Ka)": a parish,
  which tells two blocks of one name apart). MINDRE and STÖRRE are kept, because our register writes them too;
- numbers(): the property numbers a card's Fastighetsnummer names ("1,3", "26+27", "3013-3015", a trakt's "2:40"),
  or None when it names no whole property;
- designation() and split_designation(): our side (buildings.fastighet), folded, a joint property ("S:5") refused;
- closing_years(), opened() and authority(): a card's closing years, the year its case was opened (read from the end
  of the case number) and the office its case number belongs to (for the report).
"""
import html
import re
import unicodedata
from urllib.parse import unquote

BASE = "https://sok.stadsarkivet.stockholm.se/Databas/bygglov1875-1980/Sok"
EXPECTED_TOTAL = 108_078       # the cards in the index on 2026-10-20; the register (1875-1980) is closed
PER_PAGE = 10                  # fixed: no address of the app gives more rows
N_PAGES = -(-EXPECTED_TOTAL // PER_PAGE)   # 10,808: sidindex 0 to 10807
FIELDS = ("id", "kvarter", "nr", "dnr", "year", "akt", "scan")

_COUNT = re.compile(r'<span\b[^>]*\bid="MainContent_AntalTraffarLabel"[^>]*>([^<]*)<', re.I)
_GRID = re.compile(r'<table\b[^>]*\bid="MainContent_Register_GridView"', re.I)
_TABLE = re.compile(r"<(/?)table\b", re.I)
_TR = re.compile(r"<tr\b([^>]*)>(.*?)</tr\s*>", re.S | re.I)
_CLASS = re.compile(r'\bclass\s*=\s*"([^"]*)"', re.I)
_TD = re.compile(r"<td\b[^>]*>(.*?)</td\s*>", re.S | re.I)
_VISA = re.compile(r'href\s*=\s*"Visa/(\d+)/(\d+)', re.I)
_IMG = re.compile(r'<img\b[^>]*\bsrc\s*=\s*"([^"]*)"', re.I)
_TAG = re.compile(r"<[^>]*>")
_SKIP_ROWS = {"arende-table-pager", "arende-table-header"}
_STG = re.compile(r"(?<![^\W\d_])stg(?![^\W\d_])", re.I)   # "Stg" between non-letters: never "Västgöten"
_YEAR = re.compile(r"\d{4}")
_YEARS = re.compile(r"\d{4}(?:\s*,\s*\d{4})*")              # "1884, 1885": a card closed in two years
_PARISH = re.compile(r"\s*\(([^()]*)\)$")                   # "Provgården Mindre (Ka)", "Testbacken (He)"
_ACUTE = str.maketrans({"É": "E"})
_NUMBER = re.compile(r"\d+")
_TRAKT = re.compile(r"(\d+):(\d+)")                         # "2:40"
_SPAN = re.compile(r"(\d+)-(\d+)")                          # "3013-3015"
_JOINT = re.compile(r"\bS:\d+$")                            # our "TESTGÅRDEN S:51": a joint property
_OURS = re.compile(r"^(.*\S)\s+(\d+(?::\d+)?)$")            # "TESTGÅRDEN 12", "PROVBY 5:6", "PROVGRÄND XV:S 6"
MAX_NUMBERS = 20               # a card naming more properties than this is no one house's
# A case number ends in the year it was opened: "564/1875", "65D2/35", "IV:1800/67", "841-2790-81", and the rural
# municipalities' day/month-year "Häs 1/10-24", "Spå16/4-37", "Bro 16/9 —46", "Bro 15/8 45". "/10" there is a month,
# so a year is followed by a space, the end or punctuation, never by "-" or "/". A field may hold two case numbers.
_DNR_YEAR = re.compile(r"(?:[/\-–—]\s*|\s)(\d{4}|\d{2})(?=\s|$|[.,;)])")
OPENED_MIN = 1860              # an opening year before this is a misreading
TWO_DIGIT_BACK = 30            # a two-digit year takes the century that puts it 0 to this many years before closing
INDEX_END = 1980               # the register's last year: on an undated card a two-digit year is at most this
# The office a case number belongs to, from its letters (the report's breakdown only; misread variants included). The
# first group that holds one of its letter groups wins ("roman": the first one only); digits only are "plain", an empty
# case number "none". An "Ä I" or "Ä II" before the number is no office.
AUTHORITIES = (
    ("roman", {"iv", "v", "iii", "ii", "i", "vi", "tv", "rv", "it", "r"}),     # "IV:2214/68", the 1960s-70s form
    ("Brmd", {"brmd", "bimd", "ermd", "brind", "blind", "brmc", "bmd", "btmd", "rmd", "md"}),
    ("Brd", {"brd", "rd", "nd", "btd", "brc", "br"}),
    ("D", {"d", "dn"}),
    ("rural", {"spå", "spd", "spånga", "häs", "hässelby", "bro", "sol", "solhem", "lan", "fly", "hud", "bk"}),
)
_LETTERS = re.compile(r"[^\W\d_]+")
_PREFIX = {"ä", "äi", "äii"}


class PageError(ValueError):
    """A list page that is not laid out as the harvest expects, or does not hold the cards it should: the app or the
    index changed, and nothing from the page is kept."""


def clean(cell: str) -> str:
    """A cell's text: tags out (a <br/> becomes a space), entities unescaped, white space (non-breaking spaces too)
    collapsed to single spaces and trimmed, in Unicode NFC (an "Å" written as "A" plus a combining ring is "Å")."""
    text = html.unescape(_TAG.sub(" ", cell))
    return unicodedata.normalize("NFC", " ".join(text.split()))


def parse_total(page: str) -> int | None:
    """The count label's number ("108 078" → 108078); None when the label is there without a number."""
    m = _COUNT.search(page)
    if not m:
        raise PageError("no count label (MainContent_AntalTraffarLabel)")
    digits = re.sub(r"\D", "", html.unescape(m.group(1)))
    return int(digits) if digits else None


def _grid(page: str) -> str:
    """The result table's markup, up to its own </table> (the pager rows nest a table of their own)."""
    start = _GRID.search(page)
    if not start:
        raise PageError("no result table (MainContent_Register_GridView)")
    depth = 0
    for t in _TABLE.finditer(page, start.start()):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return page[start.start():t.end()]
    raise PageError("the result table is not closed")


def _card(cells: list[str]) -> dict:
    link = _VISA.findall(cells[0])
    if len(link) != 1 or link[0][0] != link[0][1]:
        raise PageError(f"a row without one Visa/<id>/<id> link: {link}")
    img = _IMG.search(cells[0])
    scan = unquote(html.unescape(img.group(1)).rsplit("/", 1)[-1]) if img else ""
    kvarter, nr, dnr, year, akt = (clean(c) for c in cells[1:])
    return {"id": int(link[0][1]), "kvarter": kvarter, "nr": nr, "dnr": dnr, "year": year, "akt": akt,
            "scan": unicodedata.normalize("NFC", scan)}


def parse_page(page: str) -> tuple[int | None, list[dict]]:
    """(the count label's number, the cards in page order) of one list page; each card has FIELDS.

    Refused with PageError: a page without the count label or the result table; a row of an unknown class; a card
    row without exactly six cells or one Visa/<id>/<id> link. The "no hits" row (arende-table-row-empty), the pager
    rows and the header row hold no card. The scan is the thumbnail's file name only: s00_fetch_bygglov never asks for
    it (robots.txt disallows /Bildarkiv/)."""
    total = parse_total(page)
    cards = []
    for m in _TR.finditer(_grid(page)):
        c = _CLASS.search(m.group(1))
        classes = set(c.group(1).split()) if c else set()
        if not classes or classes & _SKIP_ROWS or classes == {"arende-table-row-empty"}:
            continue
        if "arende-table-row" not in classes:
            raise PageError(f"a table row of an unknown class: {' '.join(sorted(classes))}")
        cells = _TD.findall(m.group(2))
        if len(cells) != 6:
            raise PageError(f"a card row with {len(cells)} cells, not 6")
        cards.append(_card(cells))
    return total, cards


def expected_ids(p: int, total: int = EXPECTED_TOTAL) -> list[int]:
    """The card ids page p holds when the index has `total` cards: 10p+1 to 10p+10, the last page fewer."""
    n_pages = -(-total // PER_PAGE)
    if not 0 <= p < n_pages:
        raise ValueError(f"page {p} is outside 0..{n_pages - 1}")
    return list(range(p * PER_PAGE + 1, min((p + 1) * PER_PAGE, total) + 1))


def check_page(p: int, total: int | None, cards: list[dict], expected_total: int = EXPECTED_TOTAL) -> None:
    """Raise PageError unless the page says the index holds expected_total cards and holds exactly the ids
    expected_ids(p): anything else means the index or its order changed since the harvest began, and a half-changed
    harvest must not mix."""
    if total != expected_total:
        raise PageError(f"page {p}: the index holds {total} cards, not {expected_total}: it changed")
    ids = [c["id"] for c in cards]
    want = expected_ids(p, expected_total)
    if ids != want:
        shown = f"{ids[:3]}{'…' if len(ids) > 3 else ''}"
        raise PageError(f"page {p}: ids {shown} ({len(ids)}), not {want[0]}–{want[-1]} ({len(want)}): the index "
                        "or its order changed")


def page_url(p: int) -> str:
    return f"{BASE}?sidindex={int(p)}"


def closing_year(year: str) -> int | None:
    """The card's Avslutningsår as a number; None for "-", an empty cell or anything but four digits."""
    return int(year) if _YEAR.fullmatch(year.strip()) else None


def is_stg(kvarter: str) -> bool:
    """True for an old stadsäga number's card ("Bromma Stg", "Hässelby Villastad Stg", a plain "Stg"): "Stg" as a
    word of its own, in any case. The app's own search matches substrings, which also finds "Västgöten"."""
    return bool(_STG.search(kvarter))


def closing_years(year: str) -> tuple[int, ...]:
    """Every closing year a card's Avslutningsår gives: one ("1934"), or two for a card closed in two years ("1884,
    1885"); () for "-", an empty cell or anything else."""
    year = year.strip()
    return tuple(int(y) for y in _YEAR.findall(year)) if _YEARS.fullmatch(year) else ()


def fold(text: str) -> str:
    """One spelling for both sides of the match: Unicode NFC, upper case, É folded to E (never Å, Ä or Ö), white
    space collapsed and trimmed."""
    return " ".join(unicodedata.normalize("NFC", text).upper().translate(_ACUTE).split())


def kvarter_name(kvarter: str) -> tuple[str, str]:
    """(the card's kvarter folded, its trailing parenthesis folded or ""): "Provgården Mindre (Ka)" gives
    ("PROVGÅRDEN MINDRE", "KA"). The parenthesis names a parish, which tells two blocks of one name apart, so the
    matcher refuses a name the index writes with more than one (years_bygglov)."""
    k = " ".join(unicodedata.normalize("NFC", kvarter).split())
    m = _PARISH.search(k)
    return fold(k[:m.start()] if m else k), fold(m.group(1)) if m else ""


def numbers(nr: str) -> tuple[str, ...] | None:
    """The property numbers a card's Fastighetsnummer names, as our register writes them (no leading zeros): "10";
    a list "1,3", "1, 3" or "26+27"; a range "3013-3015" (or "4-7, 19-22"), expanded; a trakt number "2:40" as it is.
    None when it names no whole property: an empty cell, a letter ("105A", or "S:47", a joint property), "1.2",
    "14 (5)", a range that runs backwards, or more than MAX_NUMBERS numbers in all."""
    parts = [p.strip() for p in re.split(r"[,+]", nr)]
    if not nr.strip() or not all(parts):
        return None
    out: list[str] = []
    for p in parts:
        if _NUMBER.fullmatch(p):
            out.append(str(int(p)))
        elif m := _TRAKT.fullmatch(p):
            out.append(f"{int(m.group(1))}:{int(m.group(2))}")
        elif m := _SPAN.fullmatch(p):
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi <= lo or hi - lo + 1 > MAX_NUMBERS:
                return None
            out.extend(str(i) for i in range(lo, hi + 1))
        else:
            return None
        if len(out) > MAX_NUMBERS:
            return None
    return tuple(dict.fromkeys(out))


def designation(fastighet) -> str | None:
    """Our side of the key: buildings.fastighet folded; None when it is empty or a joint property ("TESTGÅRDEN
    S:51"), which no card names."""
    f = fold(fastighet) if isinstance(fastighet, str) else ""
    return f if f and not _JOINT.search(f) else None


def split_designation(key: str) -> tuple[str, str] | None:
    """(kvarter, number) of a folded designation: "TESTGÅRDEN 12" gives ("TESTGÅRDEN", "12"), "PROVBY 5:6" gives
    ("PROVBY", "5:6"); None when it does not end in a number."""
    m = _OURS.match(key)
    return (m.group(1), m.group(2)) if m else None


def opened(dnr: str, close: int | None = None) -> int | None:
    """The year a card's case was opened, read from the end of its case number (the earliest when the field holds
    two), or None. A four-digit year counts from OPENED_MIN up to the closing year. A two-digit year takes the
    century that puts it 0 to TWO_DIGIT_BACK years before the closing year; on an undated card (close None), the
    later century that keeps it at INDEX_END or before."""
    years = []
    for m in _DNR_YEAR.finditer(" " + (dnr or "")):
        v = m.group(1)
        if len(v) == 4:
            if OPENED_MIN <= int(v) <= (close or INDEX_END):
                years.append(int(v))
            continue
        if close:
            fit = [c + int(v) for c in (1900, 1800) if 0 <= close - (c + int(v)) <= TWO_DIGIT_BACK]
        else:
            fit = [c + int(v) for c in (1900, 1800) if c + int(v) <= INDEX_END]
        years.extend(y for y in fit[:1] if y >= OPENED_MIN)
    return min(years) if years else None


def authority(dnr: str) -> str:
    """The office a case number belongs to, from its letters (AUTHORITIES): "roman" for the 1960s-70s form
    ("IV:2214/68"), "Brmd", "Brd", "D", "rural" (the suburbs' own offices before they joined the city: "Spå16/4-37",
    "Häs 1/10-24"), "plain" for digits only ("564/1875"), "none" for an empty one, else "other"."""
    if not dnr.strip():
        return "none"
    letters = [t for t in (t.lower() for t in _LETTERS.findall(dnr)) if t not in _PREFIX]
    if not letters:
        return "plain"
    for name, tokens in AUTHORITIES:
        if (letters[0] in tokens) if name == "roman" else any(t in tokens for t in letters):
            return name
    return "other"
