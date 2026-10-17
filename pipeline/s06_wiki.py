"""Wikidata items, Commons photos and Wikipedia excerpts for the building card (spec §3.2 s06_wiki; Plan 4a, Task 7).

Fetches, each cached under data/raw/ with a MANIFEST entry (fetch.post_query: a build reads the cache, --refresh asks
again), one request at a time and PAUSE_S apart, the MediaWiki ones with maxlag=5; an error answer (maxlag,
ratelimited, an answer that is not JSON) comes with HTTP 200, so it is retried and never cached (s08_landmarks.api_error):
  1. Wikidata (WDQS): the two saved queries pipeline/queries/wiki_items.rq and wiki_labels.rq, then the subclass
     graph of every P31 class they use (pipeline/queries/wikidata_classes.rq, QLever first, WDQS as fallback), into
     data/raw/wiki/items.json, labels.json, classes.json.
  2. Commons: imageinfo and licence metadata of the photo of each placed item, 50 files per request
     (data/raw/commons/meta_NNN.json); then each accepted photo's thumbnail at city.WIKI's thumb_width, once, into
     data/raw/commons/thumbs/<key> (content-addressed by the file's sha1, so nothing is fetched twice), PAUSE_S apart.
  3. Wikipedia: the intro of each placed item's sv and en article, 20 per request (data/raw/wiki/extracts/).
The photo: an item in the curated pick table pipeline/photo_picks.csv (qid, commons_file, decision; D19's later change of
2026-10-16, derived from docs/research/2026-10-16-landmark-photos.csv) takes its pick instead of its Wikidata image
(P18), "none" no photo at all; any other item keeps its first P18. A pick goes through the same checks as a P18 file
(wiki.credit: D16's licences and author, city.PHOTO_DENY, the designation rule for CC 2.0–3.0 titles; the thumbnail)
and must be at least city.WIKI's thumb_width wide; one that fails gives no photo, never the P18 it replaced.
Only footprints that are not private houses are looked up: an uncurated house in city.PRIVATE_HOUSE_KATEGORI gets no
Wikidata or Wikipedia content at all (D18 with D34: a Wikidata item, an article or a photo page states the exact year
the card withholds); a curated one does. A curated landmark's card takes its own, hand-checked Wikidata item
(landmarks.py `qid`), whatever the class rules or the items around it say: the palace's footprint also holds the Royal
Chapel's item, which has an article too.

Writes (internal, git-ignored with data/): data/wiki.parquet (gid, qid, name, name_en, langs, photo, placement,
items, and for the landmark candidates wp_sv, wp_en, label, lon, lat: one row per footprint with a building item), data/photos.json ({key: the photo's credit}), data/extracts.json
({gid: {lang: {t, r}}}: the excerpt and its revision) and data/review-photos.txt (photos whose file looks like a
work of art, photos placed only as the nearest footprint: for a look by eye before they ship, city.PHOTO_DENY; and
every pick with a decision beyond "pick", the ones marked for the spot-check listed again; and each photo refused for
a property designation in its title, with its item).
Copies each accepted thumbnail to web/data/photos/<key>, outside the data versions: the same photo serves every
version, and s03_tiles' cards name it by key.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from . import city, suppress, wiki
from .codes import SRC_CURATED
from .fetch import UA, TIMEOUT, post_query_retrying, query_cached, retry_after
from .privacy import normalise
from .s00_fetch_wikidata import ACCEPT, QLEVER, QUERY_CLASSES, WDQS, qid, rows
from .s02_attributes import STADSDELAR, YEARS, load_districts
from .s02_years import BUILDINGS
from .s08_landmarks import OUT as LANDMARKS_JSON
from .s08_landmarks import api_error
from .s08_landmarks import load as load_landmarks
from .years_wikidata import ancestors

QUERIES = Path(__file__).with_name("queries")
QUERY_ITEMS = QUERIES / "wiki_items.rq"
QUERY_LABELS = QUERIES / "wiki_labels.rq"
RAW = Path("data/raw/wiki")
COMMONS = Path("data/raw/commons")
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://{lang}.wikipedia.org/w/api.php"
PICKS = Path(__file__).with_name("photo_picks.csv")
TABLE = Path("data/wiki.parquet")
PHOTOS = Path("data/photos.json")
EXTRACTS = Path("data/extracts.json")
REVIEW = Path("data/review-photos.txt")
WEB_PHOTOS = Path("web/data/photos")
FILES_PER_REQUEST = 50
TITLES_PER_REQUEST = 20
RETRIES = 3
BACKOFF_S = (5, 30)
OLD_KEY = re.compile(r"-500(\.\w+)$")
PAUSE_S = 1.0                   # between two requests sent (a cached answer sends nothing)
sleep = time.sleep
_sent: list[str] = []           # the requests this run has sent so far, for the pause


def ask(endpoints: list[str], data: dict, dest: Path, refresh: bool, headers: dict | None = None) -> dict:
    """One cached request (fetch.post_query_retrying), PAUSE_S after the previous one sent, then its JSON. An error
    answer is retried and never cached; when every try fails, the cached answer is kept or the step stops."""
    if refresh or not query_cached(data, dest):     # what post_query will really send (a shifted batch too)
        if _sent:
            sleep(PAUSE_S)
        _sent.append(str(dest))
    post_query_retrying(endpoints, data, dest, retries=RETRIES, backoff_s=BACKOFF_S, sleep=sleep, refresh=refresh,
                        headers=headers, check=api_error)
    return json.loads(Path(dest).read_text(encoding="utf-8"))


def fetch_items(refresh: bool, raw: Path = RAW) -> tuple[pd.DataFrame, dict]:
    """(every item in the box, the ancestors of its classes)."""
    ask([WDQS], {"query": QUERY_ITEMS.read_text(encoding="utf-8")}, raw / "items.json", refresh, ACCEPT)
    ask([WDQS], {"query": QUERY_LABELS.read_text(encoding="utf-8")}, raw / "labels.json", refresh, ACCEPT)
    items = wiki.items_from(rows(raw / "items.json"), rows(raw / "labels.json"))
    classes = sorted({c for cs in items.classes for c in cs})
    q = QUERY_CLASSES.read_text(encoding="utf-8").replace("__CLASSES__", " ".join(f"wd:{c}" for c in classes))
    ask([QLEVER, WDQS], {"query": q}, raw / "classes.json", refresh, ACCEPT)
    return items, ancestors([(qid(r["a"]), qid(r["b"])) for r in rows(raw / "classes.json")])


def chunks(values: list, n: int) -> list[list]:
    return [values[i:i + n] for i in range(0, len(values), n)]


def fetch_commons(files: list[str], refresh: bool, folder: Path = COMMONS) -> dict[str, dict]:
    """{file name: Commons page} for the files, 50 per cached request."""
    pages = {}
    for k, part in enumerate(chunks(sorted(set(files)), FILES_PER_REQUEST)):
        data = {"action": "query", "format": "json", "formatversion": "2", "prop": "imageinfo",
                "iiprop": "url|size|mime|sha1|extmetadata", "iiurlwidth": str(city.WIKI["thumb_width"]),
                "iiextmetadatalanguage": "en", "maxlag": "5", "titles": "|".join("File:" + f for f in part)}
        pages.update(wiki.pages_by_file(ask([COMMONS_API], data, folder / f"meta_{k:03d}.json", refresh)))
    return pages


def fetch_extracts(titles: list[str], lang: str, refresh: bool, folder: Path = RAW / "extracts") -> dict[str, dict]:
    """{title: {text, title, rev}} of the articles' intros, 20 per cached request."""
    out = {}
    for k, part in enumerate(chunks(sorted(set(titles)), TITLES_PER_REQUEST)):
        data = {"action": "query", "format": "json", "formatversion": "2", "prop": "extracts|info", "exintro": "1",
                "explaintext": "1", "exlimit": str(TITLES_PER_REQUEST), "redirects": "1", "maxlag": "5",
                "titles": "|".join(part)}
        out.update(wiki.extract_pages(ask([WIKIPEDIA_API.format(lang=lang)], data,
                                          folder / f"{lang}_{k:03d}.json", refresh)))
    return out


def get(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    kind = str((r.headers or {}).get("Content-Type", ""))
    if not kind.startswith("image/"):          # an error page with HTTP 200 would be cached as the photo for good
        raise requests.RequestException(f"{url} answered {kind or 'no Content-Type'}, not an image")
    return r.content


def get_retrying(url: str) -> bytes:
    """get(), asked again after a 429 or 503 (RETRIES tries, BACKOFF_S apart, or the answer's Retry-After when
    longer): Wikimedia rate-limits thumbnails, and a dropped one would leave its building without a photo."""
    for attempt in range(RETRIES):
        try:
            return get(url)
        except requests.RequestException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt + 1 == RETRIES or status not in (429, 503):
                raise
            wait = max(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)], retry_after(e))
            print(f"warning: {url} answered {status}; retrying in {wait:g} s", file=sys.stderr)
            sleep(wait)


def fetch_thumbs(photos: dict[str, dict], folder: Path = COMMONS / "thumbs", web: Path = WEB_PHOTOS) -> list[str]:
    """Each photo's thumbnail fetched once into folder and copied to web; returns the keys that failed or came back
    over city.WIKI's photo_bytes (those photos are left out)."""
    folder.mkdir(parents=True, exist_ok=True)
    web.mkdir(parents=True, exist_ok=True)
    bad = []
    for key, p in sorted(photos.items()):
        dest = folder / key
        old = folder / OLD_KEY.sub(r"\1", key)   # cached before 2026-10-17 without the width: 500 px, the only one asked
        if not dest.exists() and old != dest and old.exists():
            old.replace(dest)
        if not dest.exists():
            if _sent:                          # a pause after any request this run sent, Commons' API ones too
                sleep(PAUSE_S)
            _sent.append(p["thumb"])
            try:
                body = get_retrying(p["thumb"])
            except requests.RequestException as e:
                print(f"warning: {p['thumb']} failed ({e}); the photo is left out", file=sys.stderr)
                bad.append(key)
                continue
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(body)
            tmp.replace(dest)
        size = dest.stat().st_size
        if size > city.WIKI["photo_bytes"] or size == 0:
            bad.append(key)
            continue
        out = web / key
        if not out.exists() or out.stat().st_size != size:
            out.write_bytes(dest.read_bytes())
    return bad


def read_picks(path: Path = PICKS) -> pd.DataFrame:
    """The pick table: qid, commons_file (a Commons file name as Commons writes it, spaces and no "File:", or
    "none"), decision (how it was decided: "pick", "alternative" or "none", then "; " and the flag and the reason;
    "none" exactly when the file is). Refuses a malformed table: a pick Commons could not find fails quietly."""
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(t.columns) != ["qid", "commons_file", "decision"]:
        raise ValueError(f"{path}: the columns are {list(t.columns)}, not qid, commons_file, decision")
    bad = [q for q, f, d in zip(t.qid, t.commons_file, t.decision)
           if not re.fullmatch(r"Q\d+", q) or not f.strip() or f.lower().startswith("file:") or "_" in f
           or (f.lower() == "none") != d.startswith("none") or (f.lower() == "none" and f != "none")
           or d.split(";")[0] not in ("pick", "alternative", "none")]
    if bad or t.qid.duplicated().any():
        raise ValueError(f"{path}: malformed or repeated rows {bad or sorted(set(t.qid[t.qid.duplicated()]))}")
    return t


def picks_of(t: pd.DataFrame) -> dict[str, str]:
    """{qid: the picked file, or "" for no photo}."""
    return {q: "" if f == "none" else f for q, f in zip(t.qid, t.commons_file)}


def select(b: gpd.GeoDataFrame, years: pd.DataFrame, items: pd.DataFrame, anc: dict,
           landmarks: list[dict] = ()) -> pd.DataFrame:
    """The best building item per footprint, private houses left out unless curated (D18, D34); a curated landmark's
    footprint (years.parquet `landmark`) takes its own item, placement "curated"."""
    best = wiki.best(wiki.place(b, wiki.building_items(items, anc)))
    qid_of = {L["name"]: L["qid"] for L in landmarks if L["qid"]}     # an entry without an item keeps the rules' one
    by_qid = items.set_index("qid")
    named = years[years.landmark != ""] if "landmark" in years else pd.DataFrame({"gid": [], "landmark": []})
    own = [(int(g), qid_of[n]) for g, n in zip(named.gid, named.landmark) if qid_of.get(n) in by_qid.index]
    for n in sorted({n for n in named.landmark if n in qid_of and qid_of[n] not in by_qid.index}):
        print(f"warning: landmark {n}'s item {qid_of[n]} is not among the items in the box; its card takes the "
              "item the rules choose", file=sys.stderr)
    if own:
        rows = by_qid.loc[[q for _, q in own]].reset_index()
        rows.index = pd.Index([g for g, _ in own], name="gid")
        rows = rows.assign(placement="curated", items=best["items"].reindex(rows.index).fillna(1).astype("int64"),
                           x=np.nan, y=np.nan)
        best = pd.concat([best.drop(index=rows.index, errors="ignore"), rows[best.columns]]).sort_index()
    kat = b.set_index("gid").kategori.reindex(best.index)
    curated = years.set_index("gid").ysrc.reindex(best.index) == SRC_CURATED
    house = kat.isin(city.PRIVATE_HOUSE_KATEGORI) & ~curated
    cur_gids = years.gid[years.ysrc == SRC_CURATED]
    beside = wiki.beside_private(b, cur_gids, best.index, best.x, best.y) & ~curated.to_numpy()
    for g, q in zip(best.index[beside & ~house.to_numpy()], best.qid[beside & ~house.to_numpy()]):
        print(f"wiki: item {q} on gid {g} is left out: it stands beside a private house on the same property",
              file=sys.stderr)
    return best[~house.to_numpy() & ~beside]


def build(b, years, districts, items, anc, *, commons, extracts, thumbs, landmarks=(), picks=None) -> dict:
    """The outputs from the selected items. commons(files) -> pages, extracts(titles, lang) -> {title: page},
    thumbs(photos) -> keys left out: the fetchers (tests pass stubs). landmarks: s08_landmarks' verified entries.
    picks: {qid: file, or "" for no photo} (picks_of), in place of the item's P18."""
    picks = picks or {}
    best = select(b, years, items, anc, landmarks)
    designations = {normalise(f) for f in b.fastighet if isinstance(f, str) and f.strip()} - {""}
    first, picked = {}, set()
    for g, r in best.iterrows():
        if r.qid in picks:
            picked.add(g)
            if picks[r.qid]:
                first[g] = picks[r.qid]
        elif r.images:
            first[g] = r.images[0]
    pages = commons(sorted(set(first.values()))) if first else {}
    photos, photo_of, flagged, refused, refused_picks, designated = {}, {}, [], {}, {}, []

    def refuse(g, why):
        refused[why] = refused.get(why, 0) + 1
        if g in picked:
            refused_picks[why] = refused_picks.get(why, 0) + 1

    for g, name in first.items():
        page = pages.get(name, {"missing": True})
        entry, why = wiki.credit(name, page, designations)
        if entry is None:
            refuse(g, why)
            if why == "designation":
                designated.append((name, best.qid[g]))
            continue
        if g in picked and int(page["imageinfo"][0].get("width") or 0) < city.WIKI["thumb_width"]:
            refuse(g, "narrow")                      # D19: a file under the thumbnail's width only through another pick
            continue
        if wiki.art_flag(page):
            flagged.append(name)
        photos[entry["key"]] = entry
        photo_of[g] = entry["key"]
    for key in thumbs(photos):
        photos.pop(key, None)
        for g in [g for g, k in photo_of.items() if k == key]:
            refuse(g, "thumbnail")
    photo_of = {g: k for g, k in photo_of.items() if k in photos}
    texts = {}
    for lang in city.WIKI["langs"]:
        col = f"wp_{lang}"
        titles = {g: t for g, t in best[col].items() if t}
        pages_l = extracts(sorted(set(titles.values())), lang) if titles else {}
        for g, t in titles.items():
            p = pages_l.get(t)
            text = wiki.cut(p["text"], designations=designations) if p else ""
            if text:
                texts.setdefault(int(g), {})[lang] = {"t": text, "r": p["rev"]}
    table = pd.DataFrame({
        "gid": best.index.to_numpy().astype("int32"),
        "qid": best.qid.to_numpy(),
        "name": [wiki.card_name(x, districts) for x in best.sv],
        "name_en": [wiki.card_name(x, districts) for x in best.en],
        "langs": [",".join(lang for lang in city.WIKI["langs"] if r[f"wp_{lang}"]) for _, r in best.iterrows()],
        "photo": [photo_of.get(g, "") for g in best.index],
        "placement": best.placement.to_numpy(),
        "items": best["items"].to_numpy().astype("int32"),
        # internal only (the landmark candidates list, Task 12): the article titles and the item's own label and point
        "wp_sv": best.wp_sv.to_numpy(), "wp_en": best.wp_en.to_numpy(), "label": best.sv.to_numpy(),
        "lon": best.lon.to_numpy(dtype=float), "lat": best.lat.to_numpy(dtype=float),
    })
    nearest = sorted(first[g] for g in photo_of if best.placement[g] == "nearest")
    return {"table": table, "photos": {k: {f: v for f, v in e.items() if f not in ("thumb", "file")}
                                       for k, e in sorted(photos.items())},
            "extracts": {str(g): texts[g] for g in sorted(texts)}, "flagged": sorted(flagged), "nearest": nearest,
            "refused": refused, "designation": sorted(designated), "p18": sum(g not in picked for g in photo_of),
            "picks": {"used": sum(g in picked for g in photo_of), "none": sum(g not in first for g in picked),
                      "refused": refused_picks, "unplaced": sorted(set(picks) - set(best.qid))}}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s06_wiki", description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="ask Wikidata, Commons and Wikipedia again")
    ap.add_argument("--buildings", type=Path, default=BUILDINGS)
    ap.add_argument("--years", type=Path, default=YEARS)
    ap.add_argument("--stadsdelar", type=Path, default=STADSDELAR)
    ap.add_argument("--landmarks", type=Path, default=LANDMARKS_JSON)
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    args = ap.parse_args([] if argv is None else argv)
    b = gpd.read_parquet(args.buildings, columns=["gid", "kategori", "fastighet", "geometry"])
    years = pd.read_parquet(args.years, columns=["gid", "ysrc", "landmark"])
    picks = read_picks(PICKS)
    items, anc = fetch_items(args.refresh)
    out = build(b, years, load_districts(args.stadsdelar), items, anc,
                commons=lambda files: fetch_commons(files, args.refresh),
                extracts=lambda titles, lang: fetch_extracts(titles, lang, args.refresh),
                thumbs=fetch_thumbs, landmarks=load_landmarks(args.landmarks), picks=picks_of(picks))
    hidden = suppress.gids_of(args.buildings, args.suppress)       # Plan 4b: a takedown's item, photo and excerpt go
    out["table"], out["extracts"] = suppress.rows(out["table"], hidden), suppress.keyed(out["extracts"], hidden)
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    out["table"].to_parquet(TABLE, index=False)
    PHOTOS.write_text(json.dumps(out["photos"], indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    EXTRACTS.write_text(json.dumps(out["extracts"], indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")
    REVIEW.write_text("# photos whose file looks like a work of art (look at each; refuse one in city.PHOTO_DENY)\n"
                      + "".join(f"art: {n}\n" for n in out["flagged"])
                      + "# photos placed only as the nearest footprint (check it shows this building)\n"
                      + "".join(f"nearest: {n}\n" for n in out["nearest"])
                      + "# curated picks decided by D19's rules (pipeline/photo_picks.csv: qid, file, decision)\n"
                      + "".join(f"pick: {q} {f}: {d}\n" for q, f, d in zip(picks.qid, picks.commons_file, picks.decision)
                                if d != "pick")
                      + "# picks to look at on the preview (low confidence, or a decision that was not clear-cut)\n"
                      + "".join(f"spot-check: {q} {f}\n" for q, f, d in zip(picks.qid, picks.commons_file, picks.decision)
                                if "spot-check" in d)
                      + "# photos refused for a property designation in their title (file, item)\n"
                      + "".join(f"designation: {n} ({q})\n" for n, q in out["designation"]), encoding="utf-8")
    t = out["table"]
    print(f"wiki: {len(t)} footprints with a building item, {int((t.photo != '').sum())} photos "
          f"({out['refused']} refused, {len(out['flagged'])} to look at; {out['p18']} from Wikidata), "
          f"{sum('sv' in v for v in out['extracts'].values())} sv and "
          f"{sum('en' in v for v in out['extracts'].values())} en excerpts -> {TABLE}, {PHOTOS}, {EXTRACTS}")
    p = out["picks"]
    print(f"picks: {p['used']} used, {p['none']} none, {sum(p['refused'].values())} refused ({p['refused']}), "
          f"{len(p['unplaced'])} for items on no card (yet)")


if __name__ == "__main__":
    main(sys.argv[1:])
