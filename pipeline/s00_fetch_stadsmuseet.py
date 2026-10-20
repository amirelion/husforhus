"""The City Museum's building-archaeology register (sources.yml stadsmuseet_br), cached under data/raw/stadsmuseet/
(git-ignored, like all of data/: never committed).

- investigations.json: /api/brInvestigations, every BR record (its BR number, years, address, designation, report);
- categories.json: /api/brCategories, the labels of the categories (Datering 1100-1400-talet, Dendrokronologi …);
- records/<n>.json: /api/brInvestigations/<n>, each record's own answer, the only one that lists its categories;
- areas.geojson: the WFS layer sr:v_area_br in EPSG:3011, each record's polygon by BRNummer;
- reports/<n>.json: Digitala Stadsmuseet's answer to ?688=<n> (field 688 is the BR number), for each record that has
  a report: s02 takes the report's own page from it (stadsmuseet.report_pages), REPORT_PAUSE_S apart.

Every request goes with the project's User-Agent (fetch.UA) through fetch.get_query_retrying: the retry, backoff
and keep-the-cache policy of the query steps (a cached answer is kept, with a warning, when the register does not
answer). A cached file is used as it is; --refresh asks the register again for all of them. A record not cached yet
(a new one in the list) is always fetched, PAUSE_S apart.

The archive photos (sources.yml stadsmuseet_photos; s02_stadsmuseet_photos picks them), from Digitala Stadsmuseet's
FotoWeb API (archive 5000-Alla-fotografier, Accept ASSETLIST), PHOTO_PAUSE_S apart:
- photos/<field>-<value>/NNN.json: every page of the queries on field 576 (stadsdel) for STADSDELAR, then on field
  516 (kvarter) for each kvarter those photos name (photos of the area whose stadsdel field is empty);
- photo-assets.json: the photos those pages hold, once each, with only the fields stadsmuseet_photos reads. A query
  answers items that do not hold its value too (the register's report lookups found that for field 688), so an item
  is kept only when its field holds the value asked for;
- before trusting any query, check_filters(): a known kvarter (PROBE) must answer only its own photos, on fewer pages
  than its stadsdel, and a made-up one (NO_SUCH) nothing, as the archive's web page ignores a filter it does not know
  (?BR=12 showed its first page);
- renditions/<id>.jpg: the file of a picked photo (fetch_rendition, called by s02_stadsmuseet_photos): the preview
  the archive keeps ready at about 1,200 px (a GET of /fotoweb/cache/…jpg), never the original.
--no-photos leaves the photos out (the register alone, as before).

    uv run python -m pipeline.run s00_fetch_stadsmuseet -- --refresh
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

from . import fetch, stadsmuseet
from .sources import load_sources
from .stadsmuseet import SITE
from .textfold import fold

RAW = fetch.RAW / "stadsmuseet"
INVESTIGATIONS = RAW / "investigations.json"
CATEGORIES = RAW / "categories.json"
RECORDS = RAW / "records"
AREAS = RAW / "areas.geojson"
REPORTS = RAW / "reports"
ASSETLIST = {"Accept": "application/vnd.fotoware.assetlist+json"}   # the archive's anonymous JSON answer
REPORT_PAUSE_S = 1.0
LAYER = "sr:v_area_br"
PAUSE_S = 0.5
sleep = time.sleep      # tests stub the waits

PHOTO_ARCHIVE = f"{SITE}/fotoweb/archives/5000-Alla-fotografier/"
PHOTO_PAGES = RAW / "photos"
PHOTO_ASSETS = RAW / "photo-assets.json"
RENDITIONS = RAW / "renditions"
PHOTO_PAUSE_S = 1.0
STADSDEL, KVARTER = "576", "516"
STADSDELAR = ("GAMLA STAN", "RIDDARHOLMEN")
PROBE = "CEPHEUS"                     # a Gamla stan kvarter with about 300 photos
NO_SUCH = "HUSFORHUS INGET KVARTER"
KEEP = ("5", "25", "80", "507", "510", "516", "539", "576", "590")   # the fields stadsmuseet_photos reads
MAX_FILE = 2_000_000                  # a preview is a few hundred KB; anything near an original is refused
_sent: list[str] = []                 # the photo requests this run sent (the pause goes between them)


def source() -> dict:
    return next(s for s in load_sources() if s["id"] == "stadsmuseet_br")


def answer_with(key: str):
    """A check for fetch.get_query: an answer that is not JSON holding `key` is a failed attempt, never saved."""
    def check(body: bytes) -> str | None:
        try:
            data = json.loads(body)
        except ValueError:
            return f"not JSON (no {key})"
        # a list, or one record's object (/api/brInvestigations/<n>)
        ok = isinstance(data, dict) and isinstance(data.get(key), (list, dict))
        return None if ok else f"no {key} in the answer"
    return check


def read_records(path: Path = INVESTIGATIONS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["brInvestigations"]


def read_record(n: int, folder: Path = RECORDS) -> dict | None:
    path = folder / f"{int(n)}.json"
    return json.loads(path.read_text(encoding="utf-8"))["brInvestigations"] if path.exists() else None


def get(url: str, params: dict, dest: Path, key: str, refresh: bool, headers: dict | None = None) -> dict:
    return fetch.get_query_retrying([url], params, dest, refresh=refresh, sleep=sleep, check=answer_with(key),
                                    headers=headers)


def read_report(n: int, folder: Path = REPORTS) -> dict | None:
    path = folder / f"{int(n)}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _pace(cached: bool) -> None:
    """PHOTO_PAUSE_S between the archive requests this run sends; a cached answer sends none."""
    if not cached:
        if _sent:
            sleep(PHOTO_PAUSE_S)
        _sent.append("x")


def page_path(field: str, value: str, p: int, folder: Path = PHOTO_PAGES) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", fold(value)).strip("-")
    return folder / f"{field}-{slug}" / f"{p:03d}.json"


def last_page(answer: dict) -> int:
    """The last page's number from an asset list's paging (`last`: "…&p=217"; none or no p: one page)."""
    m = re.search(r"[?&]p=(\d+)", str((answer.get("paging") or {}).get("last") or ""))
    return int(m.group(1)) if m else 0


def asset_page(field: str, value: str, p: int, refresh: bool) -> dict:
    """One page of the archive's answer to ?<field>=<value>, cached."""
    params = {field: value, **({"p": str(p)} if p else {})}
    dest = page_path(field, value, p)
    _pace(not refresh and fetch.query_cached({"GET": PHOTO_ARCHIVE, **params}, dest))
    fetch.get_query_retrying([PHOTO_ARCHIVE], params, dest, refresh=refresh, sleep=sleep, headers=ASSETLIST,
                             check=answer_with("data"))
    return json.loads(dest.read_text(encoding="utf-8"))


def query_assets(field: str, value: str, refresh: bool) -> tuple[list[dict], int]:
    """(the assets of every page whose field holds the value, how many the pages held in all)."""
    from .stadsmuseet_photos import holds
    first = asset_page(field, value, 0, refresh)
    pages = [first] + [asset_page(field, value, p, refresh) for p in range(1, last_page(first) + 1)]
    data = [a for page in pages for a in page.get("data") or []]
    return [a for a in data if holds(a, field, value)], len(data)


def check_filters(refresh: bool) -> None:
    """Refuse the archive's queries unless they filter: the PROBE kvarter's first page holds only its own photos and
    it has fewer pages than its stadsdel; NO_SUCH answers no photo at all."""
    from .stadsmuseet_photos import holds
    probe = asset_page(KVARTER, PROBE, 0, refresh)
    own = [a for a in probe.get("data") or [] if holds(a, KVARTER, PROBE)]
    whole = asset_page(STADSDEL, STADSDELAR[0], 0, refresh)
    none = asset_page(KVARTER, NO_SUCH, 0, refresh)
    why = ("the known kvarter answered no photo" if not own
           else "the known kvarter answered photos of other kvarter" if len(own) < len(probe["data"])
           else "the known kvarter has as many pages as its stadsdel" if last_page(probe) >= last_page(whole)
           else "a made-up kvarter answered photos" if none.get("data") else "")
    if why:
        raise SystemExit(f"s00_fetch_stadsmuseet: the photo archive's queries do not filter ({why}); "
                         "nothing is trusted")


def slim(asset: dict) -> dict:
    """The asset as photo-assets.json keeps it: its .info address, the fields stadsmuseet_photos reads, its
    previews (the ready JPEGs the file is taken from)."""
    md = asset.get("metadata") or {}
    return {"href": asset.get("href"), "metadata": {k: md[k] for k in KEEP if k in md},
            "previews": [{k: p.get(k) for k in ("href", "size", "width", "height", "square")}
                         for p in asset.get("previews") or [] if not p.get("square")]}


def fetch_photos(refresh: bool) -> dict:
    """Harvest the area's photo metadata into photo-assets.json; {queries, assets} (the counts)."""
    from .stadsmuseet_photos import values
    check_filters(refresh)
    assets, queries = {}, []

    def ask(field, value):
        kept, held = query_assets(field, value, refresh)
        queries.append({"field": field, "value": value, "answered": held, "kept": len(kept)})
        for a in kept:
            assets.setdefault(a["href"], slim(a))
        return kept

    named = {}
    for s in STADSDELAR:
        for a in ask(STADSDEL, s):
            for k in values(a, KVARTER):
                named.setdefault(k.casefold(), k.upper())
    for k in sorted(named.values()):
        ask(KVARTER, k)
    out = {"queries": queries, "assets": [assets[h] for h in sorted(assets)]}
    PHOTO_ASSETS.parent.mkdir(parents=True, exist_ok=True)
    PHOTO_ASSETS.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def read_photo_assets(path: Path = PHOTO_ASSETS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["assets"] if path.exists() else []


def fetch_rendition(photo_id: str, href: str, refresh: bool = False, folder: Path = RENDITIONS) -> bytes | None:
    """A picked photo's file (renditions/<id>.jpg, cached): its preview `href` (/fotoweb/cache/…jpg, about 1,200 px),
    fetched with a GET. None, with a warning, when the archive does not give a JPEG of at most MAX_FILE bytes: never an
    original (the rendition service sent originals of up to 76 MB, 2026-10-20)."""
    from .stadsmuseet_photos import PREVIEW
    dest = folder / f"{photo_id}.jpg"
    if dest.exists() and not refresh:
        return dest.read_bytes()
    try:
        if not PREVIEW.fullmatch(href or ""):
            raise requests.RequestException("not a preview address")
        _pace(False)
        t = requests.get(SITE + href, headers=fetch.UA, timeout=fetch.TIMEOUT)
        t.raise_for_status()
        if t.content[:3] != b"\xff\xd8\xff":
            raise requests.RequestException("not a JPEG")
        if len(t.content) > MAX_FILE:
            raise requests.RequestException(f"{len(t.content):,} bytes, more than a preview")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        tmp.write_bytes(t.content)
        tmp.replace(dest)
        return t.content
    except requests.RequestException as e:
        print(f"warning: the file of {photo_id} failed ({e}); the photo is left out", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s00_fetch_stadsmuseet", description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="ask the register again for every cached file")
    ap.add_argument("--no-photos", action="store_true", help="leave the archive photos out")
    a, _ = ap.parse_known_args(argv or [])
    s = source()
    api = s["api_url"].rstrip("/")
    get(f"{api}/brInvestigations", {}, INVESTIGATIONS, "brInvestigations", a.refresh)
    get(f"{api}/brCategories", {}, CATEGORIES, "brCategories", a.refresh)
    get(s["wfs_url"], {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": LAYER,
                       "outputFormat": "application/json", "srsName": "EPSG:3011"}, AREAS, "features", a.refresh)
    recs = read_records()
    new = 0
    for r in recs:
        dest = RECORDS / f"{int(r['id'])}.json"
        if dest.exists() and not a.refresh:
            continue
        get(f"{api}/brInvestigations/{int(r['id'])}", {}, dest, "brInvestigations", a.refresh)
        new += 1
        sleep(PAUSE_S)
    linked = [r for r in recs if r.get("digital_archive_link_exists") is True]
    for r in linked:
        dest = REPORTS / f"{int(r['id'])}.json"
        if dest.exists() and not a.refresh:
            continue
        get(stadsmuseet.ARCHIVE, {"688": int(r["id"])}, dest, "data", a.refresh, headers=ASSETLIST)
        sleep(REPORT_PAUSE_S)
    found = sum(bool(stadsmuseet.report_pages(read_report(r["id"]), r["id"])) for r in linked)
    print(f"stadsmuseet: reports found in Digitala Stadsmuseet for {found} of the {len(linked)} records that link one")
    n_areas = len(json.loads(AREAS.read_text(encoding="utf-8"))["features"])
    print(f"stadsmuseet: {len(recs)} records ({new} fetched now, "
          f"{sum((RECORDS / f'{int(r['id'])}.json').exists() for r in recs)} cached), {n_areas} polygons → {RAW}")
    if not a.no_photos:
        p = fetch_photos(a.refresh)
        print(f"stadsmuseet photos: {len(p['assets'])} photos from {len(p['queries'])} queries "
              f"({sum(q['answered'] - q['kept'] for q in p['queries'])} answers that do not hold their value left out)"
              f" → {PHOTO_ASSETS}")


if __name__ == "__main__":
    main(sys.argv[1:])
