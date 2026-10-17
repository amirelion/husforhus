"""Fetch the Wikidata year sources.

Two saved queries in pipeline/queries/:
  wikidata_dated.rq     every item with a coordinate in the municipality's WGS84 box that has an inception (P571)
                        or opening (P1619): best-rank statements with precision, calendar and the P518/P1480
                        qualifiers, P576, labels and sv/en article links. WDQS, about 25 s.
  wikidata_classes.rq   the upward subclass (P279) graph of every P31 class the first result uses. QLever first
                        (1.5 s); WDQS times out on it and is the fallback.
Results go to data/raw/wikidata/dated.json and classes.json with MANIFEST entries (the query's sha256 stands in
for an ETag). A build reads the cache: nothing is sent unless a file is missing or --refresh is given, which also
prints what changed (items added, removed, with other dates). Refresh before a milestone review, not nightly.
Each endpoint is tried RETRIES times, BACKOFF_S apart (WDQS answered 502/504 three times in a row during the
research, and the weekly CI job runs this step on a cold cache); the policy lives in fetch.post_query_retrying,
shared with s00_fetch_osm. Query errors keep the cached files (with a warning) when they exist, and stop the step
when they do not.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from pipeline.fetch import post_query_retrying

WDQS = "https://query.wikidata.org/sparql"
QLEVER = "https://qlever.dev/api/wikidata"
ACCEPT = {"Accept": "application/sparql-results+json"}
QUERIES = Path(__file__).with_name("queries")
QUERY_DATED = QUERIES / "wikidata_dated.rq"
QUERY_CLASSES = QUERIES / "wikidata_classes.rq"
RAW = Path("data/raw/wikidata")
DATED = RAW / "dated.json"
CLASSES = RAW / "classes.json"
RETRIES = 2                    # attempts per endpoint
BACKOFF_S = 5                  # seconds between them
sleep = time.sleep             # module-level so tests can stub the wait


def qid(uri: str) -> str:
    """The Q-id at the end of a Wikidata entity URI."""
    return uri.rsplit("/", 1)[-1]


def rows(path: Path) -> list[dict]:
    """SPARQL JSON bindings as plain {variable: value} dicts (years_wikidata imports this and qid from here)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [{k: v["value"] for k, v in b.items()} for b in data["results"]["bindings"]]


def sparql(query: str, dest: Path, endpoints: list[str], refresh: bool) -> dict:
    """The query against each endpoint in turn (fetch.post_query_retrying with this step's RETRIES, BACKOFF_S and
    sleep); on failure everywhere an existing dest is kept with a warning."""
    return post_query_retrying(endpoints, {"query": query}, dest, retries=RETRIES, backoff_s=BACKOFF_S,
                               sleep=sleep, refresh=refresh, headers=ACCEPT)


def items_of(path: Path) -> dict[str, set[tuple[str, str]]]:
    """qid -> its (prop, time) pairs, from a cached dated.json; {} when the file is missing."""
    if not path.exists():
        return {}
    out: dict[str, set[tuple[str, str]]] = {}
    for r in rows(path):
        out.setdefault(qid(r["item"]), set()).add((r["prop"], r["time"]))
    return out


def classes_of(path: Path) -> list[str]:
    return sorted({qid(r["cls"]) for r in rows(path) if "cls" in r})


def diff(before: dict, after: dict) -> dict:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(q for q in set(before) & set(after) if before[q] != after[q])
    return {"added": added, "removed": removed, "changed": changed}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s00_fetch_wikidata", description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="query again even when the cache matches, and print a diff")
    args = ap.parse_args([] if argv is None else argv)
    before = items_of(DATED) if args.refresh else {}
    e1 = sparql(QUERY_DATED.read_text(encoding="utf-8"), DATED, [WDQS], args.refresh)
    classes = classes_of(DATED)
    q2 = QUERY_CLASSES.read_text(encoding="utf-8").replace("__CLASSES__", " ".join(f"wd:{c}" for c in classes))
    e2 = sparql(q2, CLASSES, [QLEVER, WDQS], args.refresh)
    after = items_of(DATED)
    print(f"Wikidata: {len(after):,} dated items ({e1['bytes']:,} bytes, {e1['retrieved']}); "
          f"{len(classes):,} classes, graph {e2['bytes']:,} bytes ({e2['retrieved']}) -> {RAW}")
    if args.refresh:
        d = diff(before, after)
        print(f"refresh: {len(d['added'])} items added, {len(d['removed'])} removed, {len(d['changed'])} with other dates")
        for key in ("added", "removed", "changed"):
            if d[key]:
                print(f"  {key}: {' '.join(d[key][:20])}{' …' if len(d[key]) > 20 else ''}")


if __name__ == "__main__":
    main(sys.argv[1:])
