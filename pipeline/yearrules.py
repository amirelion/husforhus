"""Year rules shared by every year source (split out of s02_years so the source modules can use them
without importing s02_years): the plausible-year bounds, the RAÄ display rule and the RAÄ record cleaner."""
import numpy as np
import pandas as pd

from .codes import EXACT, LONG, RANGE

FLOOR_YEAR = 1000              # nothing older is plausible in Stockholm
LATEST_YEAR = 2026             # s99's upper bound; a later year is a typo
MIN_YEAR = 1250                # older RAÄ years are typos (a house dated 1065–1067) or site origins
OLD_OK = {"Religionsutövning", "Försvarsväsende"}   # medieval churches and defence works may be older
RANGE_MAX = 15                 # longest span still shown as a completion year


def display(year_from, year_to) -> tuple[np.ndarray, np.ndarray]:
    """(year, yflag) for a from–to range: a span of RANGE_MAX years or less shows year_to (completion), EXACT when
    from == to, else RANGE; a longer span shows year_from, flagged LONG."""
    lo, hi = np.asarray(year_from), np.asarray(year_to)
    span = hi - lo
    year = np.where(span <= RANGE_MAX, hi, lo)
    flag = np.where(span > RANGE_MAX, LONG, np.where(span == 0, EXACT, RANGE))
    return year, flag


def clean_years(raa: pd.DataFrame) -> pd.DataFrame:
    """All rows, with integer year_from <= year_to, dated and year_ok.

    dated is False without a from-year; such a record gives no year (0/0) but may still link a footprint
    (the card reads its rating and architects through the link). A missing tom becomes from; an inverted
    pair is swapped. year_ok is False when not dated, outside FLOOR_YEAR..LATEST_YEAR, and below MIN_YEAR
    unless the record is religious or defence (a church may be from the 1100s; a house dated 1065 is a typo).
    """
    f = pd.to_numeric(raa["nybyggnad_tillkomstar_from"], errors="coerce")
    t = pd.to_numeric(raa["nybyggnad_tillkomstar_tom"], errors="coerce").fillna(f)
    out = raa.copy()
    out["dated"] = f.notna().to_numpy()
    f, t = f.fillna(0).astype(int), t.fillna(0).astype(int)
    out["year_from"] = np.where(out.dated, np.minimum(f, t), 0)
    out["year_to"] = np.where(out.dated, np.maximum(f, t), 0)
    old_ok = out["andamal_huvudgrupp"].isin(OLD_OK)
    in_range = (out.year_from >= FLOOR_YEAR) & (out.year_to <= LATEST_YEAR)
    out["year_ok"] = out.dated & in_range & ((out.year_from >= MIN_YEAR) | old_ok)
    return out
