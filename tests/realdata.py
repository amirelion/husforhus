"""Shared guard for tests that read the real city's files (Tasks 10, 11).

Those tests only read files: when a pipeline step has not run they skip and name the steps to run, so CI with
HFH_NETWORK=1 never downloads the city inside pytest.
"""
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import pytest

from pipeline import city

STEPS = "s00_fetch_city s00_fetch_raa s01_load"
MIN_BUILDINGS = city.MIN_BUILDINGS   # the real city has 77,743; a fixture build has 519


def ensure_city_data(required: Iterable[Path], *, buildings: Path | None = None, steps: str = STEPS) -> None:
    """Skip unless every path in `required` exists; fail when `buildings` is a fixture build.

    required   the inputs the test reads (a task adds its own to the shared ones)
    buildings  data/buildings.parquet, when the test needs the full city: fewer than MIN_BUILDINGS rows fails
    steps      the steps that write the inputs, named in the skip message
    """
    missing = [p for p in required if not Path(p).exists()]
    if missing:
        pytest.skip(f"needs {', '.join(map(str, missing))}: uv run python -m pipeline.run {steps}")
    if buildings is not None:
        n = len(pd.read_parquet(buildings, columns=["gid"]))
        if n < MIN_BUILDINGS:
            pytest.fail(f"{buildings} holds {n} buildings: a fixture build. Rerun s01_load without HFH_FIXTURE.")
