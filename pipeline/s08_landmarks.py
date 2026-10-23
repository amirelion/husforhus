"""Verify the curated landmark file against its cited articles.

Every entry of pipeline/landmarks.py cites one Wikipedia article ("sv:Title" or "en:Title") and the strings that
article must contain (`checks`: the years it states, a phrase). This step fetches each article's plain text through
the MediaWiki API, one request at a time and PAUSE_S apart, with maxlag=5 (Wikimedia's etiquette for bots: a lagging
server answers "maxlag" instead of adding load), cached in data/raw/wiki/landmarks/ with a MANIFEST entry
(fetch.post_query: the request's hash stands in for an ETag, so a build reads the cache and only --refresh asks
again). An error answer (maxlag, ratelimited) comes with HTTP 200: it is never cached (api_error, fetch.BadAnswer),
so it is asked again after the backoff, and a later build never reads it as the article. The step then writes
data/landmarks.json: the entries whose fields are well formed and whose article holds every check string, each with
the revision it was checked against. s02_years reads that file, so an entry that fails never sets a year. Failures
are reported and dropped, never fatal (spec); an article that cannot be fetched at all, with no cached copy, stops
the step instead, so a network outage cannot quietly empty the curated tier. An entry's rebuild years, and the years
of the other house it names (`also`), are held to its checks too: each must be written in one of them, so the article
is checked for it like any other year.

Comparison: both texts have no-break spaces turned into spaces, runs of whitespace collapsed, and every dash-like
character (hyphen, en and em dash, minus) read as "-", so "1280–1300" in a check matches "1280-1300" in an article.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from pipeline import city
from pipeline.fetch import post_query_retrying
from pipeline.landmarks import LANDMARKS

API = "https://{lang}.wikipedia.org/w/api.php"
RAW = Path("data/raw/wiki/landmarks")
OUT = Path("data/landmarks.json")
LANGS = ("sv", "en")
KEYS = {"name", "qid", "lat", "lon", "year", "year_from", "year_to", "source", "checks"}
# timeline: a positive priority puts the entry's name on the timeline (1 first). rebuilt, cellars, point, also and
# raa: (pipeline/landmarks.py says what each holds).
OPTIONAL = {"timeline", "rebuilt", "cellars", "point", "also", "raa"}
REBUILD_KINDS = ("rebuilt", "raised", "extended")    # ombyggt, påbyggt, tillbyggt (web/i18n card.rebuild.*)
POINT_KEYS = {"reason", "source"}
RAA_KEYS = {"id", "reason"}
RAA_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")     # a record's id, as its public URL ends
RETRIES = 3
BACKOFF_S = (5, 30)              # seconds before the second and the third try (fetch.post_query_retrying)
PAUSE_S = 1.0                    # between two articles sent (cached ones send nothing)
sleep = time.sleep               # module-level so tests can stub the wait
DASHES = re.compile(r"[‐-―−-]")


def norm(s: str) -> str:
    """Text as the checks compare it: spaces for no-break spaces, single spaces, every dash a hyphen."""
    return DASHES.sub("-", " ".join(str(s).replace(" ", " ").split()))


def source_of(entry: dict) -> tuple[str, str]:
    lang, _, title = entry["source"].partition(":")
    return lang, title


def article_path(source: str, raw: Path = RAW) -> Path:
    """The cache file of one cited article: <lang>_<12 hex digits of sha1(source)>.json (titles hold any character)."""
    lang = source.partition(":")[0]
    return raw / f"{lang}_{hashlib.sha1(source.encode('utf-8')).hexdigest()[:12]}.json"


def request(title: str) -> dict:
    """The API request for one article's whole plain text and its latest revision id."""
    return {"action": "query", "format": "json", "formatversion": "2", "prop": "extracts|info", "explaintext": "1",
            "redirects": "1", "maxlag": "5", "titles": title}


def api_error(body: bytes) -> str | None:
    """What is wrong with a MediaWiki answer that came with HTTP 200 (its error code, or not JSON), else None: such an
    answer is never cached (fetch.post_query's check). s06_wiki uses it too."""
    try:
        data = json.loads(body)
    except ValueError:
        return "the API answered something that is not JSON"
    if isinstance(data, dict) and "error" in data:
        return f"the API answered {error_code(data['error'])}"
    return None


def error_code(error) -> str:
    """A MediaWiki error's code: an object's `code`, or the text itself when the error is a plain string."""
    if isinstance(error, dict):
        return str(error.get("code") or "an error")
    return str(error) if error else "an error"


def problems(entry: dict) -> list[str]:
    """What is wrong with an entry's fields (no network): an empty list means it may be checked."""
    out = []
    missing = KEYS - set(entry)
    extra = set(entry) - KEYS - OPTIONAL
    if missing:
        out.append(f"missing {', '.join(sorted(missing))}")
    if extra:
        out.append(f"unknown field {', '.join(sorted(extra))}")
    if missing:
        return out
    if entry["qid"] == "":       # no item: no P625 confirms the point, so it must be a hand-checked one
        if "point" not in entry:
            out.append('an entry without a Wikidata item (qid "") needs a hand-checked point')
    elif not re.fullmatch(r"Q\d+", str(entry["qid"])):
        out.append("qid is not a Wikidata item id")
    lang, title = source_of(entry)
    if lang not in LANGS or not title:
        out.append(f"source must be one of {'/'.join(LANGS)}:<article title>")
    lon0, lat0, lon1, lat1 = city.BOX_WGS84
    if not (lat0 < entry["lat"] < lat1 and lon0 < entry["lon"] < lon1):
        out.append("lat/lon outside the municipality's box")
    if not (1000 <= entry["year_from"] <= entry["year"] <= entry["year_to"] <= 2026):
        out.append("years must satisfy 1000 <= year_from <= year <= year_to <= 2026")
    checks = entry["checks"]
    if not isinstance(checks, (list, tuple)) or not checks or not all(isinstance(c, str) and c.strip() for c in checks):
        out.append("checks must be a non-empty list of strings")
    tl = entry.get("timeline")
    if tl is not None and (not isinstance(tl, int) or isinstance(tl, bool) or tl < 1):
        out.append("timeline must be a positive whole number")
    if "rebuilt" in entry:
        out += rebuild_problems(entry)
    if "cellars" in entry and entry["cellars"] is not True:
        out.append("cellars must be True when given")
    point = entry.get("point")
    if "point" in entry and not (isinstance(point, dict) and set(point) == POINT_KEYS
                                 and all(isinstance(v, str) and v.strip() for v in point.values())):
        out.append("point must be {reason, source}, both non-empty text")
    if "also" in entry:
        out += also_problems(entry)
    rec = entry.get("raa")
    if "raa" in entry and not (isinstance(rec, dict) and set(rec) == RAA_KEYS and isinstance(rec["id"], str)
                               and RAA_ID.fullmatch(rec["id"]) and isinstance(rec["reason"], str)
                               and rec["reason"].strip()):
        out.append("raa must be {id, reason}: a RAÄ record's id and how it was checked")
    return out


def rebuild_problems(entry: dict) -> list[str]:
    """What is wrong with an entry's `rebuilt`: a non-empty list of (year, kind), each year after year_to
    and by 2026, written in one of the checks (alone or inside one, as a whole number), so the article is checked for
    it like the entry's other years; each kind one of REBUILD_KINDS; no (year, kind) twice."""
    rebuilt = entry["rebuilt"]
    pairs = isinstance(rebuilt, (list, tuple)) and rebuilt and all(
        isinstance(r, (list, tuple)) and len(r) == 2 and isinstance(r[0], int) and not isinstance(r[0], bool)
        and isinstance(r[1], str) for r in rebuilt)
    if not pairs:
        return ["rebuilt must be a non-empty list of (year, kind)"]
    out = []
    if len({(year, kind) for year, kind in rebuilt}) < len(rebuilt):
        out.append("rebuilt: a (year, kind) is given twice")
    checks = entry["checks"] if isinstance(entry["checks"], (list, tuple)) else []
    checks = [norm(c) for c in checks if isinstance(c, str)]
    for year, kind in rebuilt:
        if kind not in REBUILD_KINDS:
            out.append(f"rebuilt: a kind must be {', '.join(REBUILD_KINDS[:-1])} or {REBUILD_KINDS[-1]}")
        if not entry["year_to"] < year <= 2026:
            out.append(f"rebuilt: {year} must come after year_to ({entry['year_to']}) and by 2026")
        elif not any(re.search(rf"(?<!\d){year}(?!\d)", c) for c in checks):
            out.append(f"rebuilt: {year} is not one of the checks or inside one")
    return out


def also_problems(entry: dict) -> list[str]:
    """What is wrong with an entry's `also` (another house on the footprint the article dates): a non-empty list of
    (year_from, year_to), each 1000 <= year_from <= year_to <= 2026 and each year written in one of the checks (alone
    or inside one, as a whole number), so the article is checked for it; no span twice. Unlike a rebuild it may come
    before the entry's own years."""
    also = entry["also"]
    spans = isinstance(also, (list, tuple)) and also and all(
        isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(y, int) and not isinstance(y, bool) for y in r)
        for r in also)
    if not spans:
        return ["also must be a non-empty list of (year_from, year_to)"]
    out = []
    if len({tuple(r) for r in also}) < len(also):
        out.append("also: a span is given twice")
    checks = entry["checks"] if isinstance(entry["checks"], (list, tuple)) else []
    checks = [norm(c) for c in checks if isinstance(c, str)]
    for a, z in also:
        if not 1000 <= a <= z <= 2026:
            out.append(f"also: {a}–{z} must satisfy 1000 <= year_from <= year_to <= 2026")
            continue
        for year in dict.fromkeys((a, z)):
            if not any(re.search(rf"(?<!\d){year}(?!\d)", c) for c in checks):
                out.append(f"also: {year} is not one of the checks or inside one")
    return out


def page_of(path: Path) -> dict:
    """The one page of a cached answer: {title, text, rev}; raises ValueError on an API error or a missing page."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "error" in data:
        raise ValueError(f"{path}: the API answered {error_code(data['error'])}")
    pages = data.get("query", {}).get("pages", [])
    if len(pages) != 1 or pages[0].get("missing") or pages[0].get("invalid"):
        raise ValueError(f"{path}: no such article")
    p = pages[0]
    return {"title": p["title"], "text": p.get("extract") or "", "rev": int(p.get("lastrevid") or 0)}


def missing_checks(entry: dict, text: str) -> list[str]:
    t = norm(text)
    return [c for c in entry["checks"] if norm(c) not in t]


def fetch(entry: dict, *, raw: Path = RAW, refresh: bool = False, manifest: Path | None = None) -> Path:
    lang, title = source_of(entry)
    dest = article_path(entry["source"], raw)
    post_query_retrying([API.format(lang=lang)], request(title), dest, retries=RETRIES, backoff_s=BACKOFF_S,
                        sleep=sleep, refresh=refresh, manifest=manifest, check=api_error)
    return dest


def verify(landmarks: list[dict], *, raw: Path = RAW, refresh: bool = False, manifest: Path | None = None,
           get=None) -> tuple[list[dict], list[tuple[str, str]]]:
    """(entries that pass, each with `rev` and the article `title` as fetched; [(name, why)] for the rest).

    `get(entry) -> Path` fetches one article (default: fetch with these arguments, PAUSE_S between two that are
    sent); tests pass a stub. Names and QIDs must be unique: a repeated one fails the later entry (qid "", no item,
    is never a repeat)."""
    sent = []

    def fetch_paced(e):
        if refresh or not article_path(e["source"], raw).exists():
            if sent:
                sleep(PAUSE_S)
            sent.append(e["source"])
        return fetch(e, raw=raw, refresh=refresh, manifest=manifest)
    get = get or fetch_paced
    ok, failed, names, qids = [], [], set(), set()
    for e in landmarks:
        why = problems(e)
        if not why and e["name"] in names:
            why = ["a second entry with this name"]
        if not why and e["qid"] and e["qid"] in qids:
            why = ["a second entry for this Wikidata item"]
        if why:
            failed.append((str(e.get("name", "?")), "; ".join(why)))
            continue
        try:
            page = page_of(get(e))
        except ValueError as err:
            failed.append((e["name"], str(err)))
            continue
        miss = missing_checks(e, page["text"])
        if miss:
            failed.append((e["name"], f"{page['title']} (rev {page['rev']}) lacks {miss}"))
            continue
        names.add(e["name"])
        qids.add(e["qid"])
        ok.append({**e, "checks": list(e["checks"]), "rev": page["rev"], "title": page["title"]})
    return ok, failed


def load(path: Path = OUT) -> list[dict]:
    """The verified entries s08_landmarks wrote, for s02_years and s03_tiles."""
    if not Path(path).exists():
        raise SystemExit(f"{path} is missing: run s08_landmarks first (it verifies pipeline/landmarks.py)")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s08_landmarks", description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="fetch every article again and report what changed")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args([] if argv is None else argv)
    ok, failed = verify(LANDMARKS, refresh=args.refresh)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ok, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    for name, why in failed:
        print(f"landmark dropped: {name}: {why}", file=sys.stderr)
    on_timeline = sum(1 for e in ok if e.get("timeline"))
    print(f"landmarks: {len(ok)} of {len(LANDMARKS)} verified ({on_timeline} on the timeline) -> {args.out}")


if __name__ == "__main__":
    main(sys.argv[1:])
