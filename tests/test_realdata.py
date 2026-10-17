"""The shared real-data guard (tests/realdata.py)."""
import pandas as pd
import pytest

from tests.realdata import MIN_BUILDINGS, ensure_city_data


def test_skips_naming_the_steps_when_an_input_is_missing(tmp_path):
    with pytest.raises(pytest.skip.Exception, match="s00_fetch_city s00_fetch_raa s01_load") as e:
        ensure_city_data([tmp_path / "nope.gpkg"])
    assert "nope.gpkg" in str(e.value)


def test_a_task_can_name_its_own_steps(tmp_path):
    with pytest.raises(pytest.skip.Exception, match="s02_years"):
        ensure_city_data([tmp_path / "years.parquet"], steps="s02_years")


def test_a_fixture_build_fails_and_a_full_one_passes(tmp_path):
    fixture = tmp_path / "buildings.parquet"
    pd.DataFrame({"gid": range(519)}).to_parquet(fixture)
    with pytest.raises(pytest.fail.Exception, match="fixture build"):
        ensure_city_data([fixture], buildings=fixture)
    full = tmp_path / "full.parquet"
    pd.DataFrame({"gid": range(MIN_BUILDINGS)}).to_parquet(full)
    ensure_city_data([full], buildings=full)
    ensure_city_data([fixture])                    # without `buildings` only existence is checked
