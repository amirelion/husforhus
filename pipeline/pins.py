"""The Wikidata pin table, pipeline/wiki_pins.csv: a hand-checked item whose coordinate falls in the wrong footprint
(the house next door) is put on its own, by that footprint's LOD1 UUID (so a row survives renumbered gids).

Both tiers that place an item read it: s06_wiki for the card (its name, photo and article; wiki.pin) and s02_years for
the Wikidata year (years_wikidata.match), so the card and the year never part. Columns: qid, uuid, reason (checked
how, and when; one line, in our own words, no property designation)."""
import re
import sys
from pathlib import Path

import pandas as pd

PATH = Path(__file__).with_name("wiki_pins.csv")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def read(path: Path = PATH) -> pd.DataFrame:
    """The pin table: qid, uuid, reason. Refuses a malformed table or a repeated qid (ValueError)."""
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(t.columns) != ["qid", "uuid", "reason"]:
        raise ValueError(f"{path}: the columns are {list(t.columns)}, not qid, uuid, reason")
    bad = [q for q, u, r in zip(t.qid, t.uuid, t.reason)
           if not re.fullmatch(r"Q\d+", q) or not UUID.fullmatch(u) or not r.strip()]
    if bad or t.qid.duplicated().any():
        raise ValueError(f"{path}: malformed or repeated rows {bad or sorted(set(t.qid[t.qid.duplicated()]))}")
    return t


def pins_of(t: pd.DataFrame, b) -> dict[str, int]:
    """{qid: gid} for the pins whose footprint is in b (gid, uuid). One that is not (a fixture build, or the City
    redrew it) is skipped with a warning, as name_fixes does; one whose uuid is on several footprints (the register
    gives a few buildings two) is refused (ValueError), as cited.rows refuses such a row: which part the item belongs
    on is a hand check, not the last gid's luck."""
    by = b.groupby("uuid").gid.agg(list) if "uuid" in b and len(b) else pd.Series(dtype=object)
    many = [(q, u) for q, u in zip(t.qid, t.uuid) if u in by.index and len(by[u]) > 1]
    if many:
        raise ValueError(f"pins on a uuid with several footprints (pin the item by hand to one part): {many}")
    out = {}
    for q, u in zip(t.qid, t.uuid):
        if u in by.index:
            out[q] = int(by[u][0])
        else:
            print(f"warning: wiki_pins: {q}: its footprint is not among these buildings (a fixture build, or the City "
                  "redrew it?); skipped", file=sys.stderr)
    return out
