"""Wikidata building items on footprints, their Commons photos and Wikipedia excerpts (for s06_wiki). Pure functions over the cached answers; s06_wiki fetches them and writes the outputs.

Items: the two saved queries (pipeline/queries/wiki_items.rq, wiki_labels.rq) give every item with a coordinate in
the municipality's box, its P31 classes, P18 images and whether it has a P576 (items_from), then its sv/en labels,
sv/en article titles and sitelink count. building_items keeps an item only under the year tier's class rules
(years_wikidata.classify: a building, P31/P279* Q41176, and not an organisation, museum, gallery, destroyed building
or work of art) and without P576, so a fountain's photo never lands on the building beside it. place() puts each on a
footprint as the year tier does (inside, courtyard, else the nearest within city.WIKI's max_m), and best() keeps one
item per footprint for the card: one with an article first, then the one with most sitelinks, then the lowest Q
number. (The year tier keeps its one-item rule: a footprint that two items reach is dated by neither.)

Photos: credit() turns a Commons page (imageinfo with extmetadata) into the credit the card shows, or refuses it.
Only CC BY, CC BY-SA, CC0 and public-domain files pass; a file with a restriction, or a CC file whose author is
unknown (no one to credit), is refused. The author is the Artist field without its HTML (Commons' "No
machine-readable author provided. X assumed" becomes X), or the file's own Attribution field verbatim when the
licensor set one. CC 2.0–3.0 ask for the work's title too, so those files keep their ObjectName (Commons fills it with
the file name when the uploader gave none, so this is the one place a file name can ship, after the designation check
below; 4.0 does not ask for a title). A file Commons files under "PD Sweden" (a simple photograph from before 1969)
is credited "Public domain (Sweden)": free here, not necessarily in the US. Only Wikimedia's thumbnail is used (the
original can be hundreds of MB): no thumbnail, no photo. art_flag() marks a
file whose title, description or categories suggest that a work of art is the subject, for a look by eye (city.PHOTO_DENY
holds the ones refused).

Excerpts: cut() keeps an intro's first paragraph, in whole sentences up to city.WIKI's extract_chars characters; a
first sentence longer than that is cut at a word and ends with "…". A sentence that says who owns a building or had
it built is left out (privacy.owner), and so is a parenthesis that gives the name's pronunciation in IPA
("Storkyrkan (Swedish: [ˈstûːrˌɕʏrkan], …)", which the site's fonts cannot draw), as Wikipedia's own previews do.
The excerpt is CC BY-SA 4.0 and ships in its own files, credited with its article's revision.

Property designations never ship, and Stockholm's articles are often named after one ("Styckjunkaren 7"):
so no article title or Commons file name ships at all (the card links an article through its Wikidata item and an
excerpt's credit through its revision id; a photo's credit links the file's page by its page id), a sentence that
names a designation of the city's buildings is left out of an excerpt (privacy.mentions), and a photo whose title
names one is refused (CC 2.0–3.0 need the title shown).
"""
import html
import re
from urllib.parse import unquote

import numpy as np
import pandas as pd
import shapely

from . import city
from .geo import lonlat_to_3011, placement, resolve_points
from .privacy import mentions, owner
from .s02_attributes import safe_name
from .years_wikidata import POINT, classify

ENTITY = "http://www.wikidata.org/entity/"
FILEPATH = re.compile(r"(?:^|/)Special:FilePath/(.+)$")
TAG = re.compile(r"<[^>]+>")
ASSUMED = re.compile(r"No machine-readable author provided\.\s*(.+?)\s+assumed", re.IGNORECASE)
UNKNOWN_AUTHOR = re.compile(r"^(unknown|okänd|anonymous|anonym|unknown author|author unknown|n/?a|"
                            r"(okänd|unknown) (fotograf|photographer|upphovsman|konstnär|artist))?\.?$",
                            re.IGNORECASE)
CC = re.compile(r"^cc-by(-sa)?-(\d\.\d)(-[a-z]{2})?$")
ART = re.compile(r"skulptur|sculpt|staty|statue|konstverk|artwork|work of art|relief|mosaik|mosaic|mural|"
                 r"väggmålning|utsmyckning|fontän|fountain|\bbyst\b|\bbust\b|minnesmärke|memorial|installation|"
                 r"graffiti|street art|gatukonst|public art|offentlig konst|FoP-Sweden \(artworks\)", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÅÄÖÉ0-9\"«(])")
# A full stop that ends an initial or an abbreviation, not a sentence ("C. A. Exempel", "Mr. X", "kv. Y"): split
# there and the rest of a name would ship as a sentence of its own.
ABBREV = re.compile(r"(?:^|[\s(])(?:[A-ZÅÄÖÉ]|[Kk]v|[Mm]rs?|[Mm]s|[Dd]r|[Ss]t|[Ss]:t|[Jj]r|[Ss]r|[Pp]rof|ca|c|nr|"
                    r"resp|jfr|kl|f\.d|bl\.a|t\.ex|d\.v\.s|o\.s\.v|m\.fl|m\.m|e\.g|i\.e|vs|no)\.$")
# A parenthesis holding an IPA transcription in square brackets, and footnote marks such as "[1]"
PRONUNCIATION = re.compile(r"\s*\((?=[^()]*[\[/][^\]()/]*[ˈˌːəɕʏʂŋɪʊɡɑɛɔœøæɐ̌̂][^\]()/]*[\]/])[^()]*\)")
FOOTNOTE = re.compile(r"\[(?:\d+|[a-z]|note \d+)\]")     # "[1]", "[a]", "[note 1]"
COMMONS_PAGE = re.compile(r"https://commons\.wikimedia\.org/w/index\.php\?curid=\d+")


def qid(uri: str) -> str:
    return uri[len(ENTITY):] if uri.startswith(ENTITY) else uri.rsplit("/", 1)[-1]


def file_title(uri: str) -> str:
    """A P18 value (…/Special:FilePath/Klara%20Folkskola.jpg) as a Commons file name: "Klara Folkskola.jpg"."""
    m = FILEPATH.search(uri)
    return unquote(m.group(1) if m else uri).replace("_", " ")


def items_from(rows_a: list[dict], rows_b: list[dict]) -> pd.DataFrame:
    """One row per item: qid, lon, lat, classes (a sorted tuple), images (sorted file names), ended, sv, en (labels),
    wp_sv, wp_en (article titles), nsl (sitelinks). rows_*: SPARQL bindings as {variable: value} (s00_fetch_wikidata
    rows()). An item with several coordinates takes the first in sorted order, as the research did."""
    items: dict[str, dict] = {}
    for r in rows_a:
        it = items.setdefault(qid(r["item"]), {"coords": set(), "classes": set(), "images": set(), "ended": False})
        if (m := POINT.search(r.get("coord", ""))):
            it["coords"].add((float(m.group(1)), float(m.group(2))))
        if r.get("cls"):
            it["classes"].add(qid(r["cls"]))
        if r.get("img"):
            it["images"].add(file_title(r["img"]))
        it["ended"] |= r.get("ended") == "true"
    for r in rows_b:
        it = items.get(qid(r["item"]))
        if it is None:
            continue
        for k, key in (("sv", "sv"), ("en", "en"), ("svt", "wp_sv"), ("ent", "wp_en")):
            if r.get(k) and not it.get(key):
                it[key] = r[k]
        it["nsl"] = max(it.get("nsl", 0), int(r.get("nsl", 0) or 0))
    rows = []
    for q, it in sorted(items.items()):
        lon, lat = sorted(it["coords"])[0] if it["coords"] else (np.nan, np.nan)
        rows.append({"qid": q, "lon": lon, "lat": lat, "classes": tuple(sorted(it["classes"])),
                     "images": sorted(it["images"]), "ended": it["ended"], "sv": it.get("sv", ""), "en": it.get("en", ""),
                     "wp_sv": it.get("wp_sv", ""), "wp_en": it.get("wp_en", ""), "nsl": it.get("nsl", 0)})
    cols = ["qid", "lon", "lat", "classes", "images", "ended", "sv", "en", "wp_sv", "wp_en", "nsl"]
    return pd.DataFrame(rows, columns=cols)


def building_items(items: pd.DataFrame, anc: dict) -> pd.DataFrame:
    """The items the card may use: buildings by the year tier's class rules, no P576, with a coordinate; adds x, y
    (EPSG:3011)."""
    keep = [not classify(set(c), anc) and not e for c, e in zip(items.classes, items.ended)] if len(items) else []
    out = items[np.asarray(keep, dtype=bool) & items.lon.notna().to_numpy()].copy() if len(items) else items.copy()
    x, y = lonlat_to_3011(out.lon.to_numpy(dtype=float), out.lat.to_numpy(dtype=float))
    out["x"], out["y"] = x, y
    return out.reset_index(drop=True)


def place(b, items: pd.DataFrame, max_m: float | None = None) -> pd.DataFrame:
    """The items that land on a footprint, with gid and placement (inside, courtyard, nearest)."""
    max_m = city.WIKI["max_m"] if max_m is None else max_m
    if items.empty:
        return items.assign(gid=pd.Series([], dtype="int64"), placement=pd.Series([], dtype=object))
    xs, ys = items.x.to_numpy(), items.y.to_numpy()
    gids = resolve_points(b, xs, ys, max_m)
    out = items.assign(gid=gids, placement=placement(b, gids, xs, ys))
    return out[out.gid >= 0].reset_index(drop=True)


def beside_private(b, curated, gids, xs, ys, metres: float | None = None) -> np.ndarray:
    """Per item, True when its point (xs, ys, EPSG:3011) lies within `metres` (city.WIKI private_m) of a footprint
    in a private-house category that is not curated (`curated`: gids) and stands on the same property (FASTIGHET)
    as the footprint the item landed on (`gids`): the item's photo or article may show the house. The final
    review found one such item, inside an outbuilding that touches a villa."""
    metres = city.WIKI["private_m"] if metres is None else metres
    gids = np.asarray(gids, dtype=np.int64)
    out = np.zeros(len(gids), dtype=bool)
    by = b.set_index("gid")
    prop = by.fastighet.fillna("").astype(str).str.strip()
    house = by.kategori.isin(city.PRIVATE_HOUSE_KATEGORI) & ~by.index.isin(list(curated)) & (prop != "")
    if not house.any() or not len(gids):
        return out
    xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    at = np.flatnonzero(np.isfinite(xs) & np.isfinite(ys))      # a curated landmark's own item has no point here
    tree = shapely.STRtree(by.geometry[house].to_numpy())
    k, j = tree.query(shapely.points(xs[at], ys[at]), predicate="dwithin", distance=metres)
    i = at[k]
    same = prop[house].to_numpy()[j] == prop.reindex(gids, fill_value="").to_numpy()[i]
    out[i[same]] = True
    return out


def best(placed: pd.DataFrame) -> pd.DataFrame:
    """One item per footprint, indexed by gid: an article (sv or en) first, then most sitelinks, then the lowest Q
    number; `items` counts the building items that reached the footprint."""
    if placed.empty:
        return placed.assign(items=pd.Series([], dtype="int64")).set_index("gid")
    p = placed.assign(article=(placed.wp_sv != "") | (placed.wp_en != ""),
                      qnum=placed.qid.str[1:].astype("int64"))
    p = p.sort_values(["gid", "article", "nsl", "qnum"], ascending=[True, False, False, True])
    out = p.groupby("gid").head(1).set_index("gid")
    out["items"] = p.groupby("gid").size()
    return out.drop(columns=["article", "qnum"]).sort_index()


def card_name(label: str, districts: set[str]) -> str:
    """A Wikidata label as a card title and search name: what s02_attributes.safe_name allows, and no digit (a label
    with a number is usually an address or a property designation)."""
    n = safe_name(label, districts)
    return "" if any(ch.isdigit() for ch in n) else n


# ---------- Commons ----------

def pages_by_file(answer: dict) -> dict[str, dict]:
    """Commons query answer -> {file name without "File:": page}, through the answer's `normalized` titles."""
    q = answer.get("query", {})
    back = {n["to"]: n["from"] for n in q.get("normalized", [])}
    out = {}
    for p in q.get("pages", []):
        title = back.get(p.get("title", ""), p.get("title", ""))
        out[title.removeprefix("File:").replace("_", " ")] = p
    return out


def plain(s) -> str:
    return " ".join(html.unescape(TAG.sub(" ", str(s or ""))).split())


def meta_of(page: dict) -> dict:
    info = (page.get("imageinfo") or [{}])[0]
    return {k: v.get("value") for k, v in (info.get("extmetadata") or {}).items()}


def author(meta: dict) -> str:
    """Who the credit names: the file's own Attribution line verbatim when set, else its Artist without HTML."""
    if plain(meta.get("Attribution")):
        return plain(meta.get("Attribution"))
    a = plain(meta.get("Artist"))
    m = ASSUMED.search(a)
    a = m.group(1).strip() if m else a
    return "" if UNKNOWN_AUTHOR.fullmatch(a) else a


def licence(meta: dict) -> tuple[str, str]:
    """(family, short name) of a file's licence: family "cc-by", "cc-by-sa", "cc0" or "pd", or "" when the open-licence rule refuses it
    (NC, ND, GFDL only, anything else)."""
    code = str(meta.get("License") or "").strip().lower()
    short = plain(meta.get("LicenseShortName"))
    if code.startswith("cc0") or short.upper().startswith("CC0"):
        return "cc0", "CC0"
    if code.startswith("pd") or short.lower().startswith(("public domain", "pd")):
        sweden = "PD Sweden" in str(meta.get("Categories") or "").split("|")
        return "pd", "Public domain (Sweden)" if sweden else "Public domain"
    m = CC.match(code)
    if m:
        name = f"CC BY{'-SA' if m.group(1) else ''} {m.group(2)}{(' ' + m.group(3)[1:].upper()) if m.group(3) else ''}"
        return ("cc-by-sa" if m.group(1) else "cc-by"), name
    return "", short


def art_flag(page: dict) -> bool:
    m = meta_of(page)
    text = " ".join([page.get("title", ""), plain(m.get("ImageDescription")), plain(m.get("ObjectName")),
                     str(m.get("Categories") or "")])
    return bool(ART.search(text))


def credit(name: str, page: dict, designations: set[str] = frozenset()) -> tuple[dict | None, str]:
    """(the photo's entry, "") or (None, why it is refused). The entry: key (16 hex digits of the file's sha1, "-", the
    thumbnail width asked for and the thumbnail's extension: a new width is a new file, never the old one under its
    name, which the site serves as immutable), w, h (the thumbnail), by, lic, lu (licence URL), title (CC 2.0–3.0 files), page (the file's
    Commons page by page id), and, internal only, thumb (the URL to fetch, without its query string) and file (the
    Commons name). `designations`: the city's property designations, normalised (privacy.normalise)."""
    if page.get("missing") or not page.get("imageinfo"):
        return None, "missing"
    if name in city.PHOTO_DENY:
        return None, "deny list"
    info = page["imageinfo"][0]
    meta = meta_of(page)
    family, short = licence(meta)
    if not family:
        return None, f"licence {short or '?'}"
    if plain(meta.get("Restrictions")):
        return None, "restrictions"
    who = author(meta)
    if family.startswith("cc-by") and not who:
        return None, "no author"
    thumb = str(info.get("thumburl") or "").split("?", 1)[0]       # never the original, which can be huge
    sha1 = str(info.get("sha1") or "")
    if not thumb or not re.fullmatch(r"[0-9a-f]{40}", sha1):
        return None, "no thumbnail"
    ext = thumb.rsplit(".", 1)[-1].lower()
    ext = "jpg" if ext == "jpeg" else ext
    if ext not in ("jpg", "png", "webp"):
        return None, f"thumbnail type {ext}"
    lu = re.sub(r"^http://creativecommons\.org/", "https://creativecommons.org/", str(meta.get("LicenseUrl") or ""))
    entry = {"key": f"{sha1[:16]}-{city.WIKI['thumb_width']}.{ext}", "w": int(info.get("thumbwidth") or 0),
             "h": int(info.get("thumbheight") or 0), "by": who or "unknown", "lic": short,
             "lu": lu, "page": str(info.get("descriptionshorturl") or ""),
             "thumb": thumb, "file": name}
    if family.startswith("cc-by") and not short.endswith(" 4.0"):      # CC 2.0–3.0 ask for the work's title
        entry["title"] = plain(meta.get("ObjectName")) or name.rsplit(".", 1)[0]
    if not COMMONS_PAGE.fullmatch(entry["page"]):           # the page id alone: a title in the URL could be a name
        return None, "no file page"
    if any(mentions(s.replace("_", " "), designations) for s in (entry.get("title", ""), entry["by"])):
        return None, "designation"                           # "_" too: a file name in a credit, "Storken_7_x.jpg"
    return entry, ""


# ---------- Wikipedia ----------

def extract_pages(answer: dict) -> dict[str, dict]:
    """An extracts answer -> {the title as asked: {text, title, rev}}, through `normalized` and `redirects`."""
    q = answer.get("query", {})
    back: dict[str, str] = {}
    for n in q.get("normalized", []) + q.get("redirects", []):
        back[n["to"]] = back.get(n["from"], n["from"])
    out = {}
    for p in q.get("pages", []):
        if p.get("missing") or p.get("invalid"):
            continue
        out[back.get(p["title"], p["title"])] = {"text": (p.get("extract") or "").strip(), "title": p["title"],
                                                  "rev": int(p.get("lastrevid") or 0)}
    return out


def split_sentences(para: str) -> list[str]:
    """The sentences of a paragraph: split after ".", "!" or "?" before a capital, a digit or a quote, never after an
    initial or an abbreviation (ABBREV)."""
    out, start = [], 0
    for m in SENTENCE.finditer(para):
        if ABBREV.search(para[start:m.start()]):
            continue
        out.append(para[start:m.start()])
        start = m.end()
    out.append(para[start:])
    return out


def cut(text: str, max_chars: int | None = None, designations: set[str] = frozenset()) -> str:
    """The first paragraph, in whole sentences up to max_chars, leaving out every sentence that names one of
    `designations` or says who owns the building or had it built, and the name's pronunciation; a longer first
    sentence is cut at a word, with "…"."""
    max_chars = city.WIKI["extract_chars"] if max_chars is None else max_chars
    para = (text or "").strip().split("\n")[0]
    para = " ".join(FOOTNOTE.sub("", PRONUNCIATION.sub("", para)).split())
    sentences = [s for s in split_sentences(para) if s and not mentions(s, designations) and not owner(s)]
    out = ""
    for s in sentences:
        if len(out) + len(s) + (1 if out else 0) > max_chars:
            break
        out = f"{out} {s}" if out else s
    if not out and sentences:
        out = sentences[0][:max_chars - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return out
