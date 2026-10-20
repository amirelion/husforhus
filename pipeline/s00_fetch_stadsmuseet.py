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

    uv run python -m pipeline.run s00_fetch_stadsmuseet -- --refresh
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import fetch, stadsmuseet
from .sources import load_sources

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


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s00_fetch_stadsmuseet", description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="ask the register again for every cached file")
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


if __name__ == "__main__":
    main(sys.argv[1:])
