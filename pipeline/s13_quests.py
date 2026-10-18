"""Resolve every quest step (pipeline/quests.py) to its building and check it: web/data/<version>/quests.json.

A step is dropped, and its quest with it, when: its landmark has no building in this build (the fixture holds only
Gamla stan and Riddarholmen); its article lacks a checked string; a year step's year is not the map's year for the
building (data/years.parquet, within one year). Problems are printed and never fatal, as in upstream's s13_quests.
The articles are s08_landmarks' cache (data/raw/wiki/landmarks/); one not cited by a landmark is fetched the same way.
The output keeps gids (Stockholm's integer ids) where upstream kept BAG ids, and each step's sources as article URLs.

    uv run python -m pipeline.run s13_quests
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from . import io
from .quests import QUESTS
from .s03_tiles import out_dir
from .s08_landmarks import RAW, article_path, fetch, norm, page_of

YEARS = Path("data/years.parquet")


def source_url(source: str) -> str:
    lang, _, title = source.partition(":")
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def article_text(source: str, raw: Path = RAW) -> str:
    path = article_path(source, raw)
    if not path.exists():
        fetch({"source": source}, raw=raw)
    return page_of(path)["text"]


def build(quests: list[dict], years: pd.DataFrame, text=article_text) -> tuple[list[dict], list[str]]:
    """(quests.json's entries, problems). years: gid, year, landmark (data/years.parquet)."""
    by_name = years[years.landmark.fillna("") != ""].groupby("landmark")
    out, problems = [], []
    for q in quests:
        steps = []
        for i, s in enumerate(q["steps"]):
            here = f'{q["id"]} {i + 1}'
            kind, _, ref = s["at"].partition(":")
            if kind != "lm":
                raise ValueError(f"{here}: unknown place {s['at']!r}")
            rows = by_name.get_group(ref) if ref in by_name.groups else years.iloc[0:0]
            if rows.empty:
                problems.append(f"{here}: no building for landmark {ref!r} in this build")
                continue
            missing = [(src, c) for src, cs in s["checks"] for c in cs if norm(c) not in norm(text(src))]
            if missing:
                problems.append(f"{here}: not in the article: {missing}")
                continue
            if s["kind"] == "year" and not (rows.year - s["year"]).abs().le(1).any():
                problems.append(f"{here}: {s['year']} is not the map's year ({sorted(set(rows.year))})")
                continue
            step = {k: v for k, v in s.items() if k not in ("checks", "at") and v is not None}
            step["gids"] = sorted(int(g) for g in rows.gid)
            step["sources"] = sorted({source_url(src) for src, _ in s["checks"]})
            steps.append(step)
        if len(steps) == len(q["steps"]):
            out.append({**q, "steps": steps})
        else:
            problems.append(f'{q["id"]}: left out ({len(q["steps"]) - len(steps)} step(s) failed)')
    return out, problems


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s13_quests", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="version folder (default: the one web/data/current.json names)")
    a, _ = ap.parse_known_args(argv or [])
    if not YEARS.exists():
        raise SystemExit(f"{YEARS} is missing: run s02_years first")
    out, problems = build(QUESTS, pd.read_parquet(YEARS, columns=["gid", "year", "landmark"]))
    io.write_json(out_dir(a.version) / "quests.json", out)
    for p in problems:
        print(f"s13_quests: {p}")
    print(f"s13_quests: {len(out)} of {len(QUESTS)} quests, {sum(len(q['steps']) for q in out)} steps")


if __name__ == "__main__":
    main(sys.argv[1:])
