"""The committed browser terrain fixture must match what pipeline/terrain.py writes today (web/test/terrain.test.mjs
reads it; Plan 3, Task 7)."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "web" / "test" / "fixtures"


def load_maker():
    spec = importlib.util.spec_from_file_location("make_terrain_fixture", HERE / "make_terrain_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_terrain_fixture_matches_the_pipeline():
    buf, water, expect = load_maker().build()
    hint = "terrain.pack output changed: run `uv run python tests/make_terrain_fixture.py`, then npm run test:web"
    assert (FIXTURES / "terrain_v1.bin").read_bytes() == buf, hint
    assert (FIXTURES / "water_v1.bin").read_bytes() == water, hint
    assert json.loads((FIXTURES / "terrain_v1.expect.json").read_text()) == json.loads(json.dumps(expect)), hint
