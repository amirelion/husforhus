"""RAÄ's OLD register file as a year source: Stockholm's Nybyggnad records joined by UUID."""
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry import Point

from pipeline import years_raa_old as old
from pipeline.codes import EXACT, LONG
from pipeline.yearrules import display
from tests import synth


def write(tmp_path: Path, rows) -> Path:
    """A point layer shaped like byggnader_sverige_point: kommun is space-padded, years are strings."""
    path = tmp_path / "byggnader_sverige.gpkg"
    df = gpd.GeoDataFrame([{"fast_byg_uuid": u, "kommun": f"{k:<33}", "byggnadshandelse": ev, "from_ar": f, "to_ar": t}
                           for u, k, ev, f, t in rows], geometry=[Point(674000 + i, 6580000) for i in range(len(rows))],
                          crs=3006)
    pyogrio.write_dataframe(df, path, layer=old.LAYER, driver="GPKG")
    return path


def test_load_keeps_stockholm_nybyggnad_records_with_plausible_years(tmp_path):
    path = write(tmp_path, [
        ("u1", "Stockholm", "Nybyggnad", "1961", "1961"),
        ("u2", "Stockholm", "Nybyggnad", "1902", "1910"),
        ("u3", "Stockholm", "Ombyggnad", "1950", "1950"),       # not a construction event
        ("u4", "Göteborg", "Nybyggnad", "1930", "1930"),        # another kommun
        ("u5", "Stockholm", "Nybyggnad", "1067", "1067"),       # the typo rule (MIN_YEAR)
        ("u6", "Stockholm", "Nybyggnad", None, "1950"),         # no from-year: undated
        ("", "Stockholm", "Nybyggnad", "1950", "1950"),         # no UUID: cannot join
    ])
    got = old.load(path)
    assert list(got.columns) == ["fast_byg_uuid", "year_from", "year_to"]
    assert got.fast_byg_uuid.tolist() == ["u1", "u2"]
    assert got.year_from.tolist() == [1961, 1902] and got.year_to.tolist() == [1961, 1910]


def test_match_joins_by_uuid_and_merges_duplicates(tmp_path):
    b = synth.buildings(rows=[{"uuid": "u1"}, {"uuid": "u2"}, {"uuid": ""}, {"uuid": "u9"}])
    path = write(tmp_path, [
        ("u1", "Stockholm", "Nybyggnad", "1961", "1961"),
        ("u2", "Stockholm", "Nybyggnad", "1902", "1905"),
        ("u2", "Stockholm", "Nybyggnad", "1930", "1931"),       # a second record on the same UUID
        ("u7", "Stockholm", "Nybyggnad", "1950", "1950"),       # no footprint
    ])
    m = old.match(b, old.load(path))
    assert m.index.tolist() == [0, 1]
    assert m.year_from.tolist() == [1961, 1902] and m.year_to.tolist() == [1961, 1931]
    year, flag = display(m.year_from.to_numpy(), m.year_to.to_numpy())
    assert year.tolist() == [1961, 1902] and flag.tolist() == [EXACT, LONG]
    assert old.match(b, old.load(path).iloc[:0]).empty
