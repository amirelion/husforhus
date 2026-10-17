"""The committed browser fixture must match what pack_tile writes today (web/test/tile.test.mjs reads it)."""

import gzip
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "web" / "test" / "fixtures"


def load_maker():
    spec = importlib.util.spec_from_file_location("make_tile_fixture", HERE / "make_tile_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_tile_fixture_matches_pack_tile():
    assert (FIXTURES / "tile_v1.bin").read_bytes() == load_maker().build(), (
        "pack_tile output changed: run `uv run python tests/make_tile_fixture.py` and update web/test/tile.test.mjs"
    )


def test_gz_fixture_unpacks_to_the_tile():
    assert gzip.decompress((FIXTURES / "tile_v1.bin.gz").read_bytes()) == (FIXTURES / "tile_v1.bin").read_bytes()
