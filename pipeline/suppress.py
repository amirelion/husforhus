"""Takedowns (Plan 4b, Task 8; spec §6.3): buildings whose details a person asked us to take off the map.

pipeline/suppress.yml is git-ignored: the list itself says which homes asked, so it never enters the repository (a
public one, once O1 is answered). pipeline/suppress.example.yml shows the form. Each entry names one building by the
City's register UUID or its LOD1 OID (both stay inside the pipeline and survive a gid renumbering), with the date the
request came in:

    - uuid: 2e389b81-54f2-48cc-b4ee-ae1285df2204
      date: 2026-11-02
    - oid: 1004
      date: 2026-11-03

A suppressed building keeps its shape, its height and its stadsdel. Everything else is taken off in the step that
makes it: s02_years draws it as "Year unknown" (no year, source, RAÄ link or landmark), s02_attributes drops its name,
architects, rating and protection, s02_addresses its addresses (on every footprint they landed on), s06_wiki its Wikidata item, photo and excerpt; so the
card, search and About's counts have nothing of it. s99_validate checks every entry against the build, and fails on an
entry that matches no building (a mistyped key would leave a home on the map).
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

from . import codes
from .addresses import sharing

SUPPRESS = Path(__file__).with_name("suppress.yml")
EXAMPLE = Path(__file__).with_name("suppress.example.yml")


def load(path: Path | None = None) -> list[dict]:
    """The entries of suppress.yml (none if the file is missing or empty). An entry needs a uuid or an oid, and a date;
    anything else is an error, so a takedown is never silently ignored."""
    path = SUPPRESS if path is None else Path(path)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except yaml.YAMLError as e:
        # PyYAML's own message quotes the lines around the mistake, which name homes: give only where it is
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ValueError(f"{path}: not valid YAML{where}") from None
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of entries")
    out = []
    for i, e in enumerate(data):
        if not isinstance(e, dict) or not (e.get("uuid") or e.get("oid") is not None):
            raise ValueError(f"{path}: entry {i} names no building (uuid or oid)")
        if not isinstance(e.get("date"), (datetime.date, str)) or not str(e.get("date")).strip():
            raise ValueError(f"{path}: entry {i} has no date")
        if e.get("oid") is not None and not str(e["oid"]).isdigit():
            raise ValueError(f"{path}: entry {i} has an oid that is not a number")
        out.append(e)
    return out


def resolve(b: pd.DataFrame, entries: list[dict]) -> tuple[set[int], list[int]]:
    """(the gids the entries name, the indices of entries that match no building). b: gid with uuid and/or oid. A key
    on several footprints (the register gives a few buildings more than one) takes all of them."""
    uuids, oids = {}, {}
    if "uuid" in b:
        for g, u in zip(b.gid, b.uuid):
            if isinstance(u, str) and u:
                uuids.setdefault(u.casefold(), set()).add(int(g))
    if "oid" in b:
        for g, o in zip(b.gid, b.oid):
            oids.setdefault(int(o), set()).add(int(g))
    gids, missing = set(), []
    for i, e in enumerate(entries):
        hit = uuids.get(str(e["uuid"]).casefold()) if e.get("uuid") else oids.get(int(e["oid"]))
        if hit:
            gids |= hit
        else:
            missing.append(i)
    return gids, missing


def gids_of(buildings: Path, path: Path | None = None) -> set[int]:
    """The suppressed gids of a buildings.parquet; an entry that matches nothing is printed (s99 fails on it)."""
    entries = load(path)
    if not entries:
        return set()
    names = pq.read_schema(buildings).names
    gids, missing = resolve(pd.read_parquet(buildings, columns=[c for c in ("gid", "uuid", "oid") if c in names]), entries)
    if missing:
        print(f"warning: {len(missing)} suppress.yml entries match no building (entries {missing})")
    print(f"suppressed: {len(gids)} buildings")
    return gids


def years(y: pd.DataFrame, gids: set[int]) -> pd.DataFrame:
    """years.parquet rows with the suppressed buildings drawn as "Year unknown": no year, source, RAÄ link or landmark."""
    if not gids:
        return y
    y = y.copy()
    m = y.gid.isin(gids).to_numpy()
    for c in ("year", "year_from", "year_to", "period"):
        y.loc[m, c] = 0
    y.loc[m, "ysrc"] = codes.SRC_NONE
    y.loc[m, "yflag"] = codes.UNKNOWN
    y.loc[m, "private"] = False
    for c in ("raa_id", "landmark"):
        if c in y:
            y.loc[m, c] = ""
    return y


def accuracy(acc: dict, before: pd.DataFrame, after: pd.DataFrame) -> dict:
    """The accuracy table recounted for what ships, as s99 ties it to stats.byFlag: tested (the building-level years)
    and result (estimate, period; a suppressed estimate counts as unknown). Takedowns neither train nor test the
    estimate (s02_years clears their years first and assign_years excludes them, D55); this function only moves an
    estimated takedown from "estimate" to "unknown" in the result counts."""
    known = (codes.EXACT, codes.RANGE, codes.LONG)
    est = (codes.ESTIMATE, codes.PERIOD)
    out = dict(acc)
    out["tested"] = int(after.yflag.isin(known).sum())
    gone = int((before.yflag.isin(est).to_numpy() & ~after.yflag.isin(est).to_numpy()).sum())
    r = dict(acc.get("result") or {})
    r.update(estimate=int((after.yflag == codes.ESTIMATE).sum()), period=int((after.yflag == codes.PERIOD).sum()),
             unknown=int(r.get("unknown", 0)) + gone)
    out["result"] = r
    return out


def attributes(a: pd.DataFrame, gids: set[int]) -> pd.DataFrame:
    """attributes.parquet rows without the suppressed buildings' name, architects, rating and protection."""
    if not gids:
        return a
    a = a.copy()
    m = a.gid.isin(gids).to_numpy()
    a.loc[m, "name"] = ""
    a["architects"] = [[] if hit else arch for hit, arch in zip(m, a.architects)]
    for c in ("rating", "prot", "since"):
        if c in a:
            a.loc[m, c] = 0
    return a


def addresses(on: pd.DataFrame, gids: set[int], also: set[str] = frozenset()) -> pd.DataFrame:
    """addresses.parquet rows with `withheld` set on every row that carries a suppressed building's street and number,
    on whichever footprint it landed, and of every address point beside them (`also`: addresses.near). s03_tiles.load_places leaves them out of the card and search;
    s99 reads them to check that none ships."""
    return on.assign(withheld=sharing(on, gids, also))


def rows(df: pd.DataFrame, gids: set[int]) -> pd.DataFrame:
    """A per-gid table (addresses, wiki) without the suppressed buildings' rows."""
    return df if not gids else df[~df.gid.isin(gids).to_numpy()].reset_index(drop=True)


def keyed(d: dict, gids: set[int]) -> dict:
    """A {gid as str: ...} map (the excerpts) without the suppressed buildings."""
    return d if not gids else {g: v for g, v in d.items() if int(g) not in gids}


def mask(n: int, gids: set[int]) -> np.ndarray:
    m = np.zeros(n, dtype=bool)
    m[[g for g in gids if 0 <= g < n]] = True
    return m
