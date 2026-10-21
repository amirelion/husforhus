"""s99_validate's checks of the building-permit tier (SRC_BYGGLOV, pipeline/years_bygglov.py), in one place so the big
validator only calls them. Tested by tests/test_validate_bygglov.py.

- block(): stockholm.json's accuracy.bygglov, the tier's block as s02_years wrote it: a status of applied, absent or
  off; the settings city.BYGGLOV has (else it is another build's block); and, when applied, counts that add up (the
  target footprints are the skipped ones plus the written ones, the written ones split by what they had before, what
  ships after the readers' reports equals stats.bySrc.bygglov), shares from 0 to 1, cells that are well formed, and
  every cell that dates ("dated") meets min_cell, min_right and min_decade in a group the tier dates. The blind spot
  must be there, and over BLIND_SPOT_MAX (the plan's stop rule) the build fails. A permit year in stats without an
  applied block fails too.
- rows(): the permit-dated rows of attrs.bin: a non-private one inside min_year..max_year with year_from at most
  max_lag before its year_to; a private one a decade that starts in those years' decades. With data/buildings.parquet,
  every one is of a KATEGORI group with a dated cell whose era its year (or decade) reaches.
- cards(): a permit-dated building's card carries nothing of the tier: no cited (`yc`) or reader (`yrd`) line, and no
  string shaped like a case number (diarienummer, "1234/1934").
- files(): no shipped text file holds the archive database's path (bygglov1875-1980): its search page and each card's
  Visa page show the designation, the scan and the exact closing year. About links the app's information page, once.
- release(): a full-city build (city.MIN_BUILDINGS or more) with city.FEATURES bygglov on must have applied the tier:
  without a complete harvest it is absent, and a release would quietly lose its years.

Error lines name the file and a JSON path or a count, never a designation, a case number, a group or an era.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import city, codes
from .years_bygglov import CELL_KEYS, FOOTPRINT_REASONS, MATCH_REASONS, settings

BLIND_SPOT_MAX = 0.05    # the plan's stop rule: at most 5% of the post-1980 record-dated footprints get a permit year
STATUSES = {"applied", "absent", "off"}
CELL_STATUSES = {"dated", "measured only", "not measurable", "fails"}
SETTINGS = ("min_cell", "min_right", "min_decade", "groups", "fill_area", "trains", "max_footprints", "max_year")
APPLIED_KEYS = {"status", *SETTINGS, "target", "written", "skipped", "cells", "test", "blind_spot", "others",
                "written_by_state", "estimate_check", "shipped"}
CELL_NUMBERS = {"median_error", "right_period", "same_decade", "within_1", "within_3", "exact", "late_10",
                "early_10"}
SHARES = CELL_NUMBERS - {"median_error"}
TEST_KEYS = {"n", "used"} | CELL_NUMBERS
CHECK_KEYS = {"n", "status"} | CELL_NUMBERS
STATES = ("unknown", "estimate", "area")
DNR_RE = re.compile(r"\b\d{1,6}\s*/\s*(?:18|19)\d\d\b")   # a case number with its year, as the cards write them
ARCHIVE_PATH = "bygglov1875-1980"


def _whole(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _share(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 1


def _num(x) -> str:
    return str(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else "[value]"


def expected(p: dict | None = None) -> dict:
    """The settings a block of this build must carry (years_bygglov.settings of city.BYGGLOV)."""
    return settings(p)


def _cells(cells, s: dict) -> list[str]:
    errors = []
    if not isinstance(cells, list):
        return ["accuracy: bygglov cells is not a list"]
    groups = set(s.get("groups") or ())
    eras = {e[0] for e in city.ERAS}
    for i, c in enumerate(cells):
        where = f"bygglov cells[{i}]"
        if not isinstance(c, dict) or not ({*CELL_KEYS, "n", "status"} <= set(c)):
            errors.append(f"accuracy: {where} lacks one of {sorted({*CELL_KEYS, 'n', 'status'})}")
            continue
        extra = sorted(set(c) - {*CELL_KEYS, "n", "status"} - CELL_NUMBERS)
        if extra:
            errors.append(f"accuracy: {where} has {len(extra)} keys outside the block's")
        if c["status"] not in CELL_STATUSES:
            errors.append(f"accuracy: {where} has a status outside {sorted(CELL_STATUSES)}")
        if c["era"] not in eras or not isinstance(c["inner"], bool) or c["episodes"] not in (1, 2):
            errors.append(f"accuracy: {where} has an era, inner or episodes outside the tier's")
        if not _whole(c["n"]) or c["n"] < 0:
            errors.append(f"accuracy: {where} has an n that is not a whole number")
            continue
        measurable = c["n"] >= s["min_cell"]
        numbers = CELL_NUMBERS & set(c)
        if measurable != (c["status"] != "not measurable") or (numbers != CELL_NUMBERS if measurable else numbers):
            errors.append(f"accuracy: {where} has {_num(c['n'])} test buildings but its status or numbers say "
                          "otherwise")
        errors += [f"accuracy: {where} {k} is not a share between 0 and 1" for k in SHARES if k in c and not _share(c[k])]
        if c["status"] == "dated" and measurable and CELL_NUMBERS <= set(c):
            if c["group"] not in groups:
                errors.append(f"accuracy: {where} dates a group the tier does not date")
            if _share(c["right_period"]) and c["right_period"] < s["min_right"]:
                errors.append(f"accuracy: {where} dates with a right_period under min_right {_num(s['min_right'])}")
            if _share(c["same_decade"]) and c["same_decade"] < s["min_decade"]:
                errors.append(f"accuracy: {where} dates with a same_decade under min_decade {_num(s['min_decade'])}")
    return errors


def block(cfg: dict) -> list[str]:
    """stockholm.json's accuracy.bygglov (see the module docstring); [] for a build from before the tier, unless its
    stats hold permit years."""
    acc = cfg.get("accuracy") if isinstance(cfg.get("accuracy"), dict) else {}
    by_src = (cfg.get("stats") or {}).get("bySrc") or {}
    n_src = by_src.get("bygglov", 0)
    b = acc.get("bygglov")
    if b is None:
        return [f"accuracy: stats has {_num(n_src)} permit years but the table has no bygglov block"] if n_src else []
    if not isinstance(b, dict) or b.get("status") not in STATUSES:
        return ["accuracy: bygglov is not a block with a status of applied, absent or off"]
    errors = []
    want = expected()
    for k in SETTINGS:
        if b.get(k) != want[k]:
            errors.append(f"accuracy: bygglov {k} is not city.BYGGLOV's (another build's block?)")
    if b["status"] != "applied":
        if n_src:
            errors.append(f"accuracy: stats has {_num(n_src)} permit years but the bygglov block reads not applied")
        extra = sorted(set(b) - {"status", *SETTINGS})
        return errors + ([f"accuracy: bygglov has {len(extra)} keys outside a block that was not applied"]
                         if extra else [])
    missing, extra = sorted(APPLIED_KEYS - set(b)), sorted(set(b) - APPLIED_KEYS)
    if missing:
        errors.append(f"accuracy: bygglov lacks {missing}")
    if extra:
        errors.append(f"accuracy: bygglov has {len(extra)} keys outside the block's")
    if missing:
        return errors
    counts = [b["target"], b["written"], *b["skipped"].values(), *b["written_by_state"].values(),
              b["shipped"].get("n"), b["shipped"].get("exact"), b["shipped"].get("range")] \
        if isinstance(b["skipped"], dict) and isinstance(b["written_by_state"], dict) \
        and isinstance(b["shipped"], dict) else [None]
    if not all(_whole(x) and x >= 0 for x in counts):
        return errors + ["accuracy: bygglov has a count that is not a whole number from 0"]
    if set(b["skipped"]) != {*FOOTPRINT_REASONS, *MATCH_REASONS, "cell"} or set(b["written_by_state"]) != set(STATES):
        errors.append("accuracy: bygglov skipped or written_by_state has keys outside the block's")
    if sum(b["skipped"].values()) + b["written"] != b["target"]:
        errors.append(f"accuracy: bygglov skipped ({_num(sum(b['skipped'].values()))}) and written "
                      f"({_num(b['written'])}) do not add up to target ({_num(b['target'])})")
    if sum(b["written_by_state"].values()) != b["written"]:
        errors.append("accuracy: bygglov written_by_state does not add up to written")
    sh = b["shipped"]
    if sh["n"] != n_src:
        errors.append(f"accuracy: bygglov shipped is {_num(sh['n'])} but stats.bySrc has {_num(n_src)} (another "
                      "build's block?)")
    if sh["n"] > b["written"] or sh["exact"] + sh["range"] != sh["n"]:
        errors.append("accuracy: bygglov shipped is over written, or its exact and range do not add up")
    errors += _cells(b["cells"], b)
    for name, keys in (("test", TEST_KEYS), ("estimate_check", CHECK_KEYS)):
        part = b[name]
        if not isinstance(part, dict) or not _whole(part.get("n")) or set(part) - keys:
            errors.append(f"accuracy: bygglov {name} is not a block of counts and shares")
            continue
        errors += [f"accuracy: bygglov {name} {k} is not a share between 0 and 1" for k in SHARES
                   if k in part and not _share(part[k])]
    if isinstance(b["test"], dict) and _whole(b["test"].get("used")) and _whole(b["test"].get("n")) \
            and b["test"]["used"] > b["test"]["n"]:
        errors.append("accuracy: bygglov test has used over n")
    bs = b["blind_spot"]
    if not (isinstance(bs, dict) and _whole(bs.get("n")) and _whole(bs.get("dated")) and 0 <= bs["dated"] <= bs["n"]):
        errors.append("accuracy: bygglov blind_spot is not a count of n and dated")
    elif bs["n"] >= b["min_cell"] and bs["dated"] > BLIND_SPOT_MAX * bs["n"]:
        errors.append(f"accuracy: bygglov blind spot: {_num(bs['dated'])} of {_num(bs['n'])} buildings from 1981 or "
                      f"later get a permit year, over {BLIND_SPOT_MAX:.0%} (the plan's stop rule)")
    others = b["others"]
    if not isinstance(others, dict) or any(
            not (isinstance(v, dict) and all(_whole(v.get(k)) for k in ("n", "listed", "same_period"))
                 and v["listed"] <= v["n"] and v["same_period"] <= v["n"]) for v in others.values()):
        errors.append("accuracy: bygglov others is not a count per source of n, listed and same_period")
    return errors


def _kategori(n: int, data: Path) -> np.ndarray | None:
    path = data / "buildings.parquet"
    if not path.exists():
        return None
    k = pd.read_parquet(path, columns=["gid", "kategori"]).set_index("gid").kategori
    return k.reindex(np.arange(n), fill_value="").to_numpy(dtype=object)


def rows(a: np.ndarray, cfg: dict, data: Path | None = None, p: dict | None = None) -> list[str]:
    """The permit-dated rows of attrs.bin (see the module docstring). data: the pipeline's data/, for KATEGORI."""
    p = city.BYGGLOV if p is None else p
    on = a["ysrc"] == codes.SRC_BYGGLOV
    if not on.any():
        return []
    errors = []
    year, y_from, y_to = a["year"].astype(int), a["year_from"].astype(int), a["year_to"].astype(int)
    private = a["private"] != 0

    def rule(mask, what):
        if mask.any():
            idx = np.flatnonzero(mask)
            errors.append(f"attrs: {int(mask.sum())} permit-dated buildings {what} (gids "
                          f"{', '.join(map(str, idx[:5]))}{' …' if len(idx) > 5 else ''})")

    lo, hi = p["min_year"], p["max_year"]
    rule(on & ~private & ((y_to < lo) | (y_to > hi) | (year != y_to)),
         f"whose year is not their closing year inside {lo}..{hi}")
    rule(on & ~private & ((y_from > y_to) | (y_to - y_from > p["max_lag"])),
         f"whose opening year is after their closing year or more than {p['max_lag']} years before it")
    rule(on & private & ((year < lo // 10 * 10) | (year > hi // 10 * 10)),
         f"marked private with a decade outside {lo // 10 * 10}..{hi // 10 * 10}")
    kategori = _kategori(len(a), data) if data is not None else None
    cells = ((cfg.get("accuracy") or {}).get("bygglov") or {}).get("cells") or []
    dated = [c for c in cells if isinstance(c, dict) and c.get("status") == "dated"]
    if kategori is None:
        return errors
    eras = {e[0]: (e[1], e[2]) for e in city.ERAS}
    group = np.array([city.KATEGORI_GROUPS.get(k, "unspecified") for k in kategori], dtype=object)
    reach = np.zeros(len(a), bool)
    for c in dated:
        a0, a1 = eras.get(c.get("era"), (0, -1))
        top = np.where(private, year + 9, year)
        reach |= (group == c.get("group")) & (top >= a0) & (year <= a1)
    rule(on & ~reach, "whose type and year fall in no cell that dates")
    return errors


def cards(out: Path, a: np.ndarray, shards) -> list[str]:
    """A permit-dated building's card (see the module docstring); shards: s99_validate.read_shards' (path, shard)."""
    errors = []
    on = a["ysrc"] == codes.SRC_BYGGLOV
    for p, shard in shards:
        for key, card in shard.items():
            if not (key.isascii() and key.isdigit() and int(key) < len(a) and on[int(key)] and isinstance(card, dict)):
                continue
            ref = f"cards: {p.name} gid {int(key)}"
            for f in ("yc", "yrd"):
                if f in card:
                    errors.append(f"{ref} is permit-dated and carries `{f}`")
            if any(isinstance(v, str) and DNR_RE.search(v) for v in _values(card)):
                errors.append(f"{ref} is permit-dated and holds a string shaped like a case number")
    return errors


def _values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _values(v)
    else:
        yield obj


def files(text_files) -> list[str]:
    """text_files: s99_validate.text_files(out)'s (relative path, text) pairs."""
    return [f"privacy: {rel} holds the permit database's path ({ARCHIVE_PATH}): a card's own page shows its "
            "designation and exact year" for rel, text in text_files if ARCHIVE_PATH in text]


def release(cfg: dict, n: int) -> list[str]:
    """A release of a full-city build with the tier's feature on needs it applied (see the module docstring)."""
    if not city.FEATURES.get("bygglov") or n < city.MIN_BUILDINGS:
        return []
    status = (((cfg.get("accuracy") or {}).get("bygglov")) or {}).get("status")
    if status == "applied":
        return []
    return ["release: features.bygglov is on but the permit tier was not applied (no complete harvest in "
            "data/raw/bygglov: run s00_fetch_bygglov, then s02_years)"]
