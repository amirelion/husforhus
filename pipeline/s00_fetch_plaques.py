"""Samfundet S:t Erik's plaque list, the plaque texts and Open Plaques' Stockholm positions (sources.yml
samfundet_plaques and openplaques), cached under data/raw/plaques/.

- list.pdf: the list the society's plaque page links to now (sources.yml list_page; its url when the page names no
  PDF), so a new list is picked up by running this step again. Recorded in data/raw/MANIFEST.json.
- texts/<id>.html: each plaque's Stockholmskällan post (texts_url), where the society publishes the plaque's text.
  A post already cached is kept (--refresh-texts asks again), so a new list fetches only its new plaques.
- openplaques-stockholm.json: Open Plaques' Stockholm area.
One request at a time, with the project's User-Agent (fetch.UA).
"""
import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import pypdf
import requests

from . import fetch, plaques
from .sources import load_sources

RAW = fetch.RAW / "plaques"
LIST = RAW / "list.pdf"
TEXTS = RAW / "texts"
OPENPLAQUES = RAW / "openplaques-stockholm.json"
PAUSE_S = 1.0
PDF_LINK = re.compile(r'href="([^"]+\.pdf)"[^>]*>([^<]*)', re.I)


def source(sid: str) -> dict:
    return next(s for s in load_sources() if s["id"] == sid)


def list_url(page: str, fallback: str) -> str:
    """The plaque list a page links to: the PDF whose link text names the list (förteckning), else the first PDF."""
    links = PDF_LINK.findall(page)
    named = [u for u, text in links if "förteckning" in text.lower() or "lista" in u.lower()]
    return (named or [u for u, _ in links] or [fallback])[0]


def read_list(path: Path = LIST) -> str:
    return "\n".join(p.extract_text() for p in pypdf.PdfReader(path).pages)


def get(url: str) -> requests.Response:
    r = requests.get(url, headers=fetch.UA, timeout=fetch.TIMEOUT)
    r.raise_for_status()
    time.sleep(PAUSE_S)
    return r


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s00_fetch_plaques", description=__doc__.splitlines()[0])
    ap.add_argument("--refresh-texts", action="store_true", help="fetch every plaque's text again")
    a, _ = ap.parse_known_args(argv or [])
    s, op = source("samfundet_plaques"), source("openplaques")
    url = list_url(get(s["list_page"]).text, s["url"])
    url = urljoin(s["list_page"], url)
    fetch.download(url, LIST)
    time.sleep(PAUSE_S)
    fetch.download(op["data_url"], OPENPLAQUES)
    rows = plaques.parse_list(read_list())
    TEXTS.mkdir(parents=True, exist_ok=True)
    new = failed = 0
    for r in rows:
        dest = TEXTS / f"{r['id']}.html"
        if dest.exists() and not a.refresh_texts:
            continue
        try:
            dest.write_text(get(s["texts_url"].format(id=r["id"])).text, encoding="utf-8")
            new += 1
        except requests.RequestException as e:
            failed += 1
            print(f"plaque {r['id']}: no text ({e})", file=sys.stderr)
    print(f"plaques: {url} lists {len(rows)}; {new} texts fetched, {failed} failed, "
          f"{sum((TEXTS / f'{r['id']}.html').exists() for r in rows)} cached")


if __name__ == "__main__":
    main(sys.argv[1:])
