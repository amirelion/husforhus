"""Archive photos from Digitala Stadsmuseet (archive 5000-Alla-fotografier; sources.yml stadsmuseet_photos) on the
cards: which photos, on which footprint, in which order.

The register does not link these photos, so each keeps its own licence (research:
docs/research/2026-10-19-stadsmuseet-sources.md §5). An item (an entry of the archive's asset list, as
s00_fetch_stadsmuseet caches it) carries its metadata by field number: 5 title, 25 keywords, 80 photographer,
507 property designation, 510 address, 516 kvarter, 539 year, 576 stadsdel, 590 licence.

The rules (choose):
- placed by address (field 510, read as PR 57's register addresses are: stadsmuseet.parse_address and by_address on
  s02_addresses' table) onto exactly one footprint; a photo whose addresses reach two footprints is left out;
- CC BY only (field 590 "BY"): NC and ND photos never ship, as the register's permission does not cover them;
- exteriors only (exterior()): no interior, wall or cellar detail, doorway or fragment, by the title and keywords;
- a building or a street, not people (people_or_event(), building_view()): by the title and the keywords;
- never on a private house (a footprint s03_tiles would hide: marked private, or an uncurated house in
  city.PRIVATE_HOUSE_KATEGORI); never one whose title or photographer names a property designation (the City's,
  the register's or the archive's own field 507); never one in pipeline/stadsmuseet_deny.txt;
- oldest first (by year; a photo without a year after those with one), at most MAX_PER_BUILDING per building in
  FULL_AREAS and MAX_ELSEWHERE on any other.
A photographer "Okänd" (unknown) is allowed: the card credits "Photographer unknown / Fotograf okänd", the museum
being the named holder (the research note's decision 3).

entry(): what a card carries for a picked photo: the file (key, w, h: web/data/photos/<key>, s06_wiki's
content-addressed names), its year, its credited photographers and its own page, the item's .info address
(PHOTO_PAGE), never a search or filter address.
"""
import hashlib
import io as _io
import re
from pathlib import Path

import pandas as pd

from . import city, stadsmuseet
from .privacy import mentions, normalise, owner, phrases
from .textfold import fold

ARCHIVE_ID = "5000-Alla-fotografier"
PHOTO_PAGE = re.compile(re.escape(f"{stadsmuseet.SITE}/fotoweb/archives/{ARCHIVE_ID}/") + r"(?:[A-Za-z0-9_-]+/)*"
                        r"(?P<id>[A-Za-z0-9_-]+)\.(?:jpe?g|tiff?|png)\.info")
# A photo's file: one of the previews the archive keeps ready (a plain GET of a cached JPEG). Its rendition service
# sent the original instead of the size asked for (up to 76 MB, 2026-10-20), so the renditions are never asked for.
PREVIEW = re.compile(r"/fotoweb/cache/v2/[A-Za-z0-9_.~/-]+\.jpg")
PREVIEW_SIZE, PREVIEW_MIN, PREVIEW_MAX = 1200, 800, 1600
DENY = Path(__file__).with_name("stadsmuseet_deny.txt")
LICENCE = "CC BY 4.0"
MAX_PER_BUILDING = 3        # in FULL_AREAS
MAX_ELSEWHERE = 1           # anywhere else: a photo on as many buildings as possible within the host's file limit
FULL_AREAS = ("GAMLA STAN", "RIDDARHOLMEN")
MAX_WIDTH = 1200            # the file's width at most (the archive's sketches are 800-1,280 px; never the original)
YEAR_MIN, YEAR_MAX = 1840, 2026
UNKNOWN = "okänd"

# Exteriors only. A keyword (field 25, the Swedish and English labels run together: "InteriörerInteriors") or a
# title word that marks an interior, a wall or cellar detail, a doorway or a fragment leaves the photo out. Matched
# on folded text (textfold.fold: lower case, no accents) at the start of a word.
NOT_EXTERIOR_KEYWORDS = ("interior", "portal", "portar", "dorr", "plafond", "takmalning", "kallare", "valv",
                         "trapp", "forstug", "kakelugn", "spis", "murverk", "fragment", "detalj", "inredning",
                         "skyddsrum", "verkstad", "butiksinterior", "hantverkare", "vind ", "bjalk", "golv", "vagg",
                         "tak ", "fonster", "beslag", "ornament", "dekor", "stuck", "malning")
NOT_EXTERIOR_TITLE = re.compile(
    r"\b(interior\w*|inre\b|rum(?:met|men)?\b|sal(?:en)?\b|kok(?:et)?\b|forstug\w*|trapp\w*|kallar\w*|kallare\w*|"
    r"valv\w*|portal\w*|port(?:en|ar|arna|omfattning\w*)?\b|dorr\w*|ingang\w*|detalj\w*|fragment\w*|ornament\w*|"
    r"plafond\w*|takmalning\w*|tak(?:et)?\b|bjalk\w*|vind(?:en|svaning\w*)?\b|golv\w*|vagg\w*|vaggmalning\w*|"
    r"mur(?:en|ar|arna|verk\w*|parti\w*|liv\w*)?\b|puts\w*|kakelugn\w*|spis\w*|fonster\w*|beslag\w*|stuck\w*|"
    r"dekor\w*|malning\w*|smide\w*|skylt\w*|verkstad\w*|butik\w*|skyddsrum\w*|grav\w*|sten(?:ar)?\b|"
    r"utgravning\w*|schakt\w*|ritning\w*|planritning\w*|fasadritning\w*|relief\w*|minnestavla\w*|inskription\w*)")


def values(asset: dict, field: str) -> list[str]:
    """A metadata field's values as strings (the archive gives one string or a list)."""
    v = ((asset.get("metadata") or {}).get(field) or {}).get("value")
    return [" ".join(str(x).split()) for x in (v if isinstance(v, list) else [v]) if x not in (None, "")
            and str(x).strip()]


def holds(asset: dict, field: str, value: str) -> bool:
    """Whether the asset's field holds the value (case and spacing aside): the check that a query filtered."""
    want = " ".join(value.split()).casefold()
    return any(v.casefold() == want for v in values(asset, field))


def year_of(text: str) -> int | None:
    """The photo's year from field 539: a single year YEAR_MIN..YEAR_MAX, else None (a span, a decade or no year:
    the card shows none rather than a year the archive does not give)."""
    m = re.fullmatch(r"\s*(1[89]\d\d|20[0-2]\d)\s*", str(text or ""))
    return int(m.group(1)) if m and YEAR_MIN <= int(m.group(1)) <= YEAR_MAX else None


def item(asset: dict) -> dict | None:
    """The fields the rules read from one asset, or None when it has no .info page in the photo archive.
    `rendition`: its preview of about 1,200 px (PREVIEW), or "" when it has none."""
    page = stadsmuseet.SITE + str(asset.get("href") or "")
    m = PHOTO_PAGE.fullmatch(page)
    if not m:
        return None
    prev = [p for p in asset.get("previews") or [] if not p.get("square") and PREVIEW.fullmatch(str(p.get("href") or ""))
            and PREVIEW_MIN <= int(p.get("size") or 0) <= PREVIEW_MAX]
    prev.sort(key=lambda p: abs(int(p["size"]) - PREVIEW_SIZE))   # the 1,200 preview, else the nearest
    first = lambda f: (values(asset, f) or [""])[0]           # noqa: E731
    return {"id": m.group("id"), "page": page, "title": first("5"), "keywords": values(asset, "25"),
            "by": values(asset, "80"), "addresses": values(asset, "510"), "designations": values(asset, "507"),
            "year": year_of(first("539")), "licence": first("590"), "kvarter": values(asset, "516"),
            "stadsdel": values(asset, "576"), "rendition": prev[0]["href"] if prev else ""}


def items(assets: list[dict]) -> list[dict]:
    """item() of each asset once (several queries answer the same photo), sorted by id."""
    out = {}
    for a in assets:
        it = item(a)
        if it and it["id"] not in out:
            out[it["id"]] = it
    return [out[k] for k in sorted(out)]


def cc_by(it: dict) -> bool:
    return it["licence"].strip().upper() in ("BY", "CC BY", "CC BY 4.0")


# A portrait or an event shows people, not the building: on a card it takes a building photo's place (the owner,
# 2026-10-20: "adds atmosphere, but too much"). Matched on the folded title; a view of the street or a shop front stays.
PEOPLE_OR_EVENT = re.compile(
    r"\b(portratt\w*|pa bilden|ser vi\b|hyllas|hyllning\w*|firar|firande|jubile\w*|invig\w*|eskorter\w*|konsert\w*|"
    r"gudstjanst\w*|mottagning\w*|middag\w*|fest(?:en|ligheter\w*)?\b|besok(?:er|et)?\b|prinsess\w*|prins(?:en)?\b|"
    r"kung(?:en)?\b|drottning\w*|biskop\w*|pastor\w*|general\b|overstathallar\w*|foredrag\w*|sammantrade\w*|"
    r"brollop\w*|begravning\w*|intervju\w*|utdelning\w*|prisutdelning\w*|demonstration\w*|tal(?:ar|aren)\b|"
    r"portvakt\w*|med sin(?:a)?\b|med maka\b|med make\b|med fru\b|en grupp\b|grupp med\b)")


# The archive's subject keywords (field 25, the Swedish and English labels run together: "FasaderFacades") decide
# the rest (the owner, 2026-10-20: press photos of people indoors still showed). A photo ships only with a keyword
# that shows a building, a street or a view (BUILDING_KEYWORD), and with none that shows people, an event or a room
# (PEOPLE_KEYWORD); a photo without keywords says nothing about what it shows, so it is left out. Matched on the
# folded keyword from its start.
BUILDING_KEYWORD = re.compile(
    r"(fasad|byggnader|gatumiljo|gator|grander|torg(?!handel)|offentliga byggnader|palats|kyrkor|slott|"
    r"stenhusbebyggelse|trahusbebyggelse|flerbostadshus|kontorsbyggnader|tegelbyggnader|villor|radhus|smahus|"
    r"allmanna utsikter|utsikter|stadsvyer|broar|kajer|kanaler|hamnar|gardar|bakgardar|parker|torn|exterior|hotell|"
    r"banker|bostadshus|hyreshus|kvarter|stadsdelar|stadsmiljo|gatuhorn|gatukorsning)")
PEOPLE_KEYWORD = re.compile(
    r"(portratt|grupportratt|interior|inredning|utstallning|skolutstallning|salar|kok|kontor(?!s)|bibliotek|innertak|"
    r"tak(?=ceilings)|laboratori|skolavslutning|middag|fest|mottagning|folksamling|publik|kungahuset|butiksbitrade|"
    r"kassaapparat|politiker|balett|teater|opera|konsert|militarparad|parad|brandman|brander|strejk|uniform|"
    r"fangelse|sammantrade|mote|kongress|konferens|kurs|undervisning|lektion|bal\b|dans|bankett|servering|"
    r"restauranggaster|pressvisning|vernissage|invigning|jubileum|firande|ceremoni|begravning|brollop|dop\b|"
    r"skolbarn|elever|personal|anstallda|arbetare|hantverkare|yrken|kokspersonal|fabriksarbeterskor|"
    r"byggnadsarbetare|arbetsklader)")


def people_or_event(title: str, keywords: list[str] = ()) -> bool:
    """True when the title (PEOPLE_OR_EVENT) or a keyword (PEOPLE_KEYWORD) says the photo is of people, an event or
    a room, not of the building."""
    return bool(PEOPLE_OR_EVENT.search(fold(title))) or any(PEOPLE_KEYWORD.match(fold(k)) for k in keywords)


def building_view(keywords: list[str]) -> bool:
    """True when a keyword says the photo shows a building, a street or a view (BUILDING_KEYWORD)."""
    return any(BUILDING_KEYWORD.match(fold(k)) for k in keywords)


def exterior(title: str, keywords: list[str] = ()) -> bool:
    """False for an interior, a wall or cellar detail, a doorway or a fragment, by its title or keywords."""
    for k in keywords:
        f = fold(k) + " "
        if any(f.startswith(w) or f" {w}" in f" {f}" for w in NOT_EXTERIOR_KEYWORDS):
            return False
    return not NOT_EXTERIOR_TITLE.search(fold(title))


def credited(names: list[str]) -> list[str]:
    """The photographers as the card credits them: "Okänd" left out (none left: the card says unknown),
    "Last, First" as "First Last", one name given twice ("Larssons, Ateljé" and "Larssons Ateljé") once."""
    out: dict[str, tuple[str, bool]] = {}           # one name's words: (as shown, written with a comma)
    for n in names:
        n = " ".join(n.split()).strip(" ,;")
        if not n or n.casefold() == UNKNOWN:
            continue
        key = " ".join(sorted(re.findall(r"\w+", n.casefold())))
        last, comma, rest = n.partition(",")
        shown = f"{rest.strip()} {last.strip()}" if comma and rest.strip() and "," not in rest else n
        if key not in out or (out[key][1] and not comma):    # the form without a comma wins
            out[key] = (shown, bool(comma))
    return [s for s, _ in out.values()]


def place(its: list[dict], table: pd.DataFrame) -> dict[str, int]:
    """{photo id: gid} for the photos whose addresses (field 510) all lead to exactly one footprint."""
    streets = {fold(s) for s in table.street.unique()} if len(table) else set()
    index = stadsmuseet.address_index(table) if len(table) else {}
    out = {}
    for it in its:
        addrs = [a for text in it["addresses"] for a in stadsmuseet.parse_address(text)[0]]
        gids = stadsmuseet.by_address(addrs, table, streets, index)
        if len(gids) == 1:
            out[it["id"]] = int(gids[0])
    return out


def archive_designations(its: list[dict]) -> set[str]:
    """The property designations the archive's own field 507 names, normalised as privacy compares them."""
    out = set()
    for it in its:
        for d in it["designations"]:
            out |= {normalise(d)} | set(phrases(d))
    return {d for d in out if re.search(r"\d", d)}


def read_deny(path: Path = DENY) -> dict[str, str]:
    """{photo id: reason} from the deny list: one id per line, then its reason; '#' starts a comment. A line without
    a reason, or an id twice, is refused: the list says why each photo is dropped."""
    out = {}
    if not Path(path).exists():
        return out
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid, _, reason = line.partition("\t") if "\t" in line else line.partition(" ")
        pid, reason = pid.strip(), reason.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", pid) or not reason:
            raise ValueError(f"{path}:{i}: a photo id, then its reason")
        if pid in out:
            raise ValueError(f"{path}:{i}: {pid} twice")
        out[pid] = reason
    return out


def private_gids(b: pd.DataFrame, years: pd.DataFrame) -> set[int]:
    """The footprints s03_tiles hides (its `hidden`): marked private, or an uncurated house in
    city.PRIVATE_HOUSE_KATEGORI. `b`: gid, kategori; `years`: gid, ysrc, private."""
    from .codes import SRC_CURATED
    y = years.set_index("gid").reindex(b.gid)
    private = y.private.fillna(0).astype(bool).to_numpy() if "private" in y else False
    house = b.kategori.isin(city.PRIVATE_HOUSE_KATEGORI).to_numpy() & (y.ysrc.to_numpy() != SRC_CURATED)
    return set(b.gid.to_numpy()[private | house].astype(int).tolist())


def order(it: dict) -> tuple:
    """Oldest first; a photo without a year after those with one; then by id."""
    return (it["year"] is None, it["year"] or 0, it["id"])


def choose(its: list[dict], placed: dict[str, int], *, private: set[int] = frozenset(),
           designations: set[str] = frozenset(), deny: dict[str, str] | None = None,
           full: set[int] | None = None) -> tuple[dict[int, list[dict]], dict]:
    """({gid: its photos, oldest first, at most MAX_PER_BUILDING on a building in `full` (the FULL_AREAS
    footprints; None: every building) and MAX_ELSEWHERE on any other}, {why: how many photos were left out})."""
    deny = deny or {}
    n = {"unplaced": 0, "licence": 0, "interior or detail": 0, "people or event": 0, "no building keyword": 0,
         "private house": 0,
         "designation": 0, "deny list": 0,
         "no rendition": 0, "over the cap": 0}
    on: dict[int, list[dict]] = {}
    for it in its:
        g = placed.get(it["id"])
        why = ("unplaced" if g is None else "licence" if not cc_by(it)
               else "interior or detail" if not exterior(it["title"], it["keywords"])
               else "people or event" if people_or_event(it["title"], it["keywords"])
               else "no building keyword" if not building_view(it["keywords"])
               else "private house" if g in private
               else "designation" if any(mentions(s.replace("_", " "), designations) for s in [it["title"], *it["by"]])
               else "deny list" if it["id"] in deny
               else "no rendition" if not it["rendition"] else "")
        if why:
            n[why] += 1
            continue
        on.setdefault(g, []).append(it)
    picks = {}
    for g in sorted(on):
        ps = sorted(on[g], key=order)
        cap = MAX_PER_BUILDING if full is None or g in full else MAX_ELSEWHERE
        n["over the cap"] += max(0, len(ps) - cap)
        picks[g] = ps[:cap]
    return picks, n


def fit(body: bytes, max_width: int = MAX_WIDTH, max_bytes: int | None = None) -> tuple[bytes, int, int] | None:
    """(the file, its width, height): the rendition as it came when it is a JPEG at most max_width wide and
    max_bytes long, else scaled to max_width and saved again as a JPEG; None when even that is over max_bytes."""
    from PIL import Image
    max_bytes = city.WIKI["photo_bytes"] if max_bytes is None else max_bytes
    im = Image.open(_io.BytesIO(body))
    w, h = im.size
    if im.format == "JPEG" and w <= max_width and len(body) <= max_bytes:
        return body, w, h
    if w > max_width:
        im = im.resize((max_width, max(1, round(h * max_width / w))), Image.LANCZOS)
    im = im.convert("L" if im.mode in ("L", "LA", "1", "I", "I;16") else "RGB")
    for quality in (85, 75, 65):
        buf = _io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue(), im.size[0], im.size[1]
    return None


def key_of(body: bytes, width: int) -> str:
    """s06_wiki's content-addressed name: 16 hex digits of the file's sha1, "-", its width, ".jpg"."""
    return f"{hashlib.sha1(body).hexdigest()[:16]}-{int(width)}.jpg"


def entry(it: dict, key: str, w: int, h: int) -> dict:
    """The card's entry for one picked photo: key, w, h, y (when it has a year), by (the credited photographers,
    none when unknown), page (its .info page) and t (its title, unless it says who owns the building)."""
    by = credited(it["by"])
    title = it["title"] if it["title"] and not owner(it["title"]) else ""
    return {"key": key, "w": int(w), "h": int(h), **({"y": it["year"]} if it["year"] else {}),
            **({"by": ", ".join(by)} if by else {}), "page": it["page"], **({"t": title} if title else {})}


def review_html(rows: list[dict]) -> str:
    """data/review-stadsmuseet-photos.html: a contact sheet of every picked photo, by building. Each row: gid,
    address, id, key, year, title, by, page. Each photo gives the line to paste into DENY to drop it."""
    from html import escape as e
    by_gid: dict[int, list[dict]] = {}
    for r in rows:
        by_gid.setdefault(int(r["gid"]), []).append(r)
    parts = []
    for g in sorted(by_gid):
        rs = by_gid[g]
        figs = "".join(
            f'<figure><a href="{e(r["page"])}"><img src="../web/data/photos/{e(r["key"])}" loading="lazy" alt=""></a>'
            f'<figcaption><b>{e(str(r.get("year") or "no year"))}</b> {e(r.get("title") or "")}<br>'
            f'{e(r.get("by") or "photographer unknown")}<br><code>{e(r["id"])}\tnot this building: '
            f'</code></figcaption></figure>' for r in rs)
        parts.append(f'<section><h2>{e(rs[0].get("address") or "")} <small>gid {g}</small></h2>{figs}</section>')
    return ("<!doctype html><meta charset=utf-8><title>Stadsmuseet photos to review</title><style>"
            "body{font:13px system-ui;margin:16px}section{border-top:1px solid #ccc;padding:8px 0}"
            "figure{display:inline-block;width:260px;margin:0 12px 12px 0;vertical-align:top}"
            "img{width:260px;height:200px;object-fit:cover;background:#eee}code{font-size:11px}</style>"
            f"<h1>{len(rows)} Stadsmuseet photos on {len(by_gid)} buildings</h1><p>To drop a photo, paste its "
            "line into pipeline/stadsmuseet_deny.txt with the reason, then run s02_stadsmuseet_photos and s03_tiles "
            "again.</p>" + "".join(parts) + "\n")
