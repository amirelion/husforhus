"""s99_validate's rules for the laser towers: each part on a building that is not a private house, 5..400 m above its
ground, inside its footprint, and Lantmäteriet's laser credited exactly when a tile draws one. The `site` fixture and
helpers come from tests/test_s99_validate.py."""
import json

import pytest

from pipeline import io, s03_tiles
from tests.test_s99_validate import VERSION, check, site
from tests.tinycity import ACCURACY, SOURCES, TERRAIN, ground_rows, local_box, tiny_city

__all__ = ["site"]

LASER = dict(SOURCES[0], id="lm_laser", attribution="Laserdata Nedladdning, skog, © Lantmäteriet, CC BY 4.0 (bearbetad)")
SPIRE = local_box(4, 4, 7, 7)       # inside gid 0, the church (0..10 x 0..10)


def rebuild(site, monkeypatch, parts, sources=(LASER,)):
    """The site rebuilt with these tower parts ({gid: [(height, outline)]}) put straight into the tiles, past
    s03_tiles.tower_parts' own filters, as a broken build would."""
    monkeypatch.setattr(s03_tiles, "tower_parts", lambda df, towers: parts)
    b, y, a = tiny_city()
    s03_tiles.write_outputs(s03_tiles.join(b, y, a, ground_rows(b, a)), site, VERSION, sources=SOURCES + list(sources),
                            accuracy=ACCURACY, terrain=TERRAIN)


def test_a_build_with_a_tower_passes(site, monkeypatch):
    rebuild(site, monkeypatch, {0: [(95.0, SPIRE)]})
    assert check(site, sources=SOURCES + [LASER]) == []


def test_a_tower_on_a_private_house_fails(site, monkeypatch):
    rebuild(site, monkeypatch, {4: [(30.0, local_box(-18, -1598, -12, -1592))], 6: [(9.0, local_box(22, 22, 26, 26))]})
    errors = check(site, sources=SOURCES + [LASER])
    assert errors == ["towers: 2 buildings with a laser part on a private house or no building (gids 4, 6)"]


@pytest.mark.parametrize("height", [4.0, 401.0])
def test_a_tower_out_of_range_fails(site, monkeypatch, height):
    rebuild(site, monkeypatch, {0: [(height, SPIRE)]})
    assert check(site, sources=SOURCES + [LASER]) == ["towers: 1 buildings with a laser part outside 5..400 m (gids 0)"]


def test_a_tower_outside_its_footprint_fails(site, monkeypatch):
    rebuild(site, monkeypatch, {0: [(95.0, local_box(8, 8, 14, 14))]})
    assert check(site, sources=SOURCES + [LASER]) == ["towers: 1 buildings with a laser part outside its footprint (gids 0)"]
    rebuild(site, monkeypatch, {0: [(95.0, local_box(8, 8, 10.1, 10.1))]})       # within the 0.2 m tolerance
    assert check(site, sources=SOURCES + [LASER]) == []


def test_the_laser_credit_follows_the_towers(site, monkeypatch):
    rebuild(site, monkeypatch, {0: [(95.0, SPIRE)]}, sources=())            # drawn, not credited
    assert check(site) == ["attribution: Lantmäteriet's laser data is not credited, but the tiles draw 1 laser tower "
                           "parts"]
    rebuild(site, monkeypatch, {})                                           # none drawn: no credit either
    cfg = json.loads((site / "stockholm.json").read_text())
    assert "lm_laser" not in [a["id"] for a in cfg["attribution"]]
    cfg["attribution"].append({**cfg["attribution"][0], "id": "lm_laser"})
    io.write_json(site / "stockholm.json", cfg)
    assert check(site, sources=SOURCES + [LASER]) == [
        "attribution: Lantmäteriet's laser data is credited, but the tiles draw 0 laser tower parts"]
