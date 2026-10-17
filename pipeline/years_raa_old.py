"""RAÄ's OLD register file as a year source (the `raa_old` tier, right after `raa`).

The file (s00_fetch_raa_old) holds the old building register's Nybyggnad years for all of Sweden, CC0, published
"during a transition period". About 818 Stockholm footprints that today's RAÄ data no longer dates get a year from
it. load(): Stockholm's Nybyggnad records with the same cleaning as the RAÄ tier (yearrules.clean_years).
match(): joined by fast_byg_uuid == LOD1 UUID; several records on one UUID give the earliest from-year and the
latest to-year. The old record URLs will die, so this tier never sets raa_id: cards link no record for it.
"""
from pathlib import Path

import pandas as pd
import pyogrio

from .s00_fetch_raa_old import DEST, LAYER
from .yearrules import clean_years

FIELDS = ["fast_byg_uuid", "kommun", "byggnadshandelse", "from_ar", "to_ar"]
EVENT = "Nybyggnad"


def load(path: Path = DEST, layer: str = LAYER) -> pd.DataFrame:
    """Stockholm's dated Nybyggnad records: fast_byg_uuid, year_from, year_to (year_ok rows only)."""
    # kommun is space-padded in the file ("Stockholm   ..."), so LIKE, not =.
    old = pyogrio.read_dataframe(path, layer=layer, columns=FIELDS, read_geometry=False, where="kommun LIKE 'Stockholm%'")
    old = old[old.byggnadshandelse.fillna("").str.strip() == EVENT]
    old = old.rename(columns={"from_ar": "nybyggnad_tillkomstar_from", "to_ar": "nybyggnad_tillkomstar_tom"})
    old["andamal_huvudgrupp"] = ""        # no purpose group here: the MIN_YEAR rule applies to every record
    old = clean_years(old)
    old = old[old.year_ok & old.fast_byg_uuid.notna() & (old.fast_byg_uuid != "")]
    return old[["fast_byg_uuid", "year_from", "year_to"]].reset_index(drop=True)


def match(b, old: pd.DataFrame) -> pd.DataFrame:
    """year_from, year_to per gid whose UUID the old register dates; indexed by gid, sorted."""
    cols = ["year_from", "year_to"]
    if old.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="gid"))
    has = b[["gid", "uuid"]][b.uuid != ""]
    m = has.merge(old, left_on="uuid", right_on="fast_byg_uuid", how="inner")
    if m.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="gid"))
    out = m.groupby("gid").agg(year_from=("year_from", "min"), year_to=("year_to", "max"))
    return out[cols].sort_index()
