"""Card names on the wrong footprint: the hand-checked table pipeline/name_fixes.csv, applied by s03_tiles.

Each row: key (a gid, or a Wikidata id "Q…" for the footprint whose card item it is), action, target, reason.
- move: the footprint's card name (its own name, else its Wikidata name) goes to the target gid's card, replacing
  the name there; the source keeps no name. Its Wikidata item, photo and excerpt stay where they are.
- drop: the footprint's card shows no name.
A row is added only after checking it on the map data (scripts/check_names.py lists candidates in
data/review-names.md); nothing is changed automatically. A row whose key or target is not among the footprints (a
fixture build, renumbered gids) is skipped with a warning. A move needs a name on the source footprint.
"""
import re
import sys
from pathlib import Path

import pandas as pd

PATH = Path(__file__).with_name("name_fixes.csv")
COLUMNS = ["key", "action", "target", "reason"]
NAME_COLS = ("name", "wname", "wname_en")


def read(path: Path = PATH) -> pd.DataFrame:
    """The table; refuses a malformed one (unknown action, a move without a target gid, no reason, a repeated key)."""
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(t.columns) != COLUMNS:
        raise ValueError(f"{path}: the columns are {list(t.columns)}, not {', '.join(COLUMNS)}")
    bad = [k for k, a, g, r in zip(t.key, t.action, t.target, t.reason)
           if not re.fullmatch(r"\d+|Q\d+", k) or a not in ("move", "drop") or not r.strip()
           or (a == "move") != bool(re.fullmatch(r"\d+", g)) or (a == "drop" and g)]
    if bad or t.key.duplicated().any():
        raise ValueError(f"{path}: malformed or repeated rows {bad or sorted(set(t.key[t.key.duplicated()]))}")
    return t


def apply(df: pd.DataFrame, fixes: pd.DataFrame) -> pd.DataFrame:
    """df (gid, qid, name, wname, wname_en) with the fixes applied."""
    if fixes.empty:
        return df
    df = df.copy()
    pos = {int(g): i for i, g in enumerate(df.gid)}
    for k, action, target in zip(fixes.key, fixes.action, fixes.target):
        rows = [pos[int(k)]] if k.isdigit() and int(k) in pos else list((df.qid == k).to_numpy().nonzero()[0])
        if len(rows) != 1 or (action == "move" and int(target) not in pos):
            print(f"warning: name_fixes: {k} {action} {target}: not among these footprints (a fixture build, or "
                  "renumbered gids?); skipped", file=sys.stderr)
            continue
        i = df.index[rows[0]]
        if action == "move":
            name = str(df.at[i, "name"] or df.at[i, "wname"] or "")
            if not name:
                raise SystemExit(f"name_fixes: {k} has no name to move")
            df.at[df.index[pos[int(target)]], "name"] = name
        for c in NAME_COLS:
            if c in df:
                df.at[i, c] = ""
    return df
