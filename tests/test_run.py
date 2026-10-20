# tests/test_run.py
"""pipeline.run."""
import subprocess
import sys
import types
from pathlib import Path

import pytest

from pipeline import run

ROOT = Path(__file__).resolve().parents[1]


def test_steps_contract():
    # S08_landmarks verifies the curated list before s02_years reads it (spec order, not number order);
    # s06_wiki needs the years (curated private houses) and feeds s03_tiles' cards. s02_addresses puts the
    # OSM addresses and the stadsdel on each footprint, for the cards; s14_search indexes the version's cards. The blue
    # plaques: s15_plaques needs s02_addresses' table and writes into the version s03_tiles made. The laser points:
    # s00_fetch_laser picks its candidates from the years, attributes and Wikidata names (so after s06_wiki), and
    # s02_towers' parts go into s03_tiles' tiles. metro: s16_metro writes metro.json into the version s03_tiles made.
    # The City Museum's register: fetched with the other sources, placed by s02_stadsmuseet once s02_addresses' table
    # is there (its address fallback), and on s03_tiles' cards; its archive photos likewise (s02_stadsmuseet_photos
    # reads years.parquet for the private houses). The ferries: s17_ferries cuts the routes to the water s04_base wrote
    assert run.STEPS == ["s00_fetch_city", "s00_fetch_raa", "s00_fetch_raa_old", "s00_fetch_wikidata", "s00_fetch_osm",
                         "s00_fetch_dem", "s00_fetch_plaques", "s00_fetch_stadsmuseet", "s01_load", "s08_landmarks",
                         "s02_years", "s02_attributes", "s02_addresses", "s02_stadsmuseet", "s02_stadsmuseet_photos",
                         "s02_terrain", "s06_wiki", "s00_fetch_laser", "s02_towers", "s03_tiles", "s16_metro", "s04_base",
                         "s17_ferries", "s07_labels", "s14_search", "s15_plaques", "s13_quests", "s99_validate"]


def test_list_prints_steps_without_importing_them(capsys):
    before = set(sys.modules)
    assert run.main(["--list"]) == 0
    assert capsys.readouterr().out.split() == run.STEPS
    assert not any(m.startswith("pipeline.s0") or m.startswith("pipeline.s9") for m in set(sys.modules) - before)


def test_unknown_step_exits_2():
    p = subprocess.run(["uv", "run", "python", "-m", "pipeline.run", "nope"], cwd=ROOT, capture_output=True,
                       text=True, timeout=300)
    assert p.returncode == 2
    assert "unknown step: nope" in p.stderr


def fake_steps(monkeypatch, names):
    calls = []
    for name in names:
        mod = types.ModuleType(f"pipeline.{name}")
        mod.main = lambda argv=None, name=name: calls.append((name, argv))
        monkeypatch.setitem(sys.modules, f"pipeline.{name}", mod)
    return calls


def test_named_steps_run_in_declared_order_with_timing(monkeypatch, capsys):
    calls = fake_steps(monkeypatch, ["s00_fetch_city", "s01_load"])
    assert run.main(["s01_load", "s00_fetch_city", "s01_load"]) == 0
    assert calls == [("s00_fetch_city", []), ("s01_load", [])]
    out = capsys.readouterr().out
    assert "s00_fetch_city" in out and " s" in out and "total" in out


def test_all_steps_by_default_and_arguments_after_double_dash(monkeypatch):
    calls = fake_steps(monkeypatch, run.STEPS)
    assert run.main([]) == 0
    assert [c[0] for c in calls] == run.STEPS
    calls.clear()
    assert run.main(["s99_validate", "--", "--release"]) == 0
    assert calls == [("s99_validate", ["--release"])]


def test_missing_step_module_is_reported(monkeypatch, capsys):
    monkeypatch.setattr(run, "STEPS", ["s98_not_written_yet"])
    assert run.main(["s98_not_written_yet"]) == 1
    assert "not implemented yet" in capsys.readouterr().err


def test_step_failure_propagates(monkeypatch):
    mod = types.ModuleType("pipeline.s01_load")

    def boom(argv=None):
        raise RuntimeError("bad data")

    mod.main = boom
    monkeypatch.setitem(sys.modules, "pipeline.s01_load", mod)
    with pytest.raises(RuntimeError, match="bad data"):
        run.main(["s01_load"])
