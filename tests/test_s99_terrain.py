"""s99_validate's terrain rules (Plan 3, Task 6): terrain.bin.gz against stockholm.json and water.bin.gz, its values,
the 1.5 MB budget, its source against the config, data/terrain.json and the credits, the buildings left buried, the
datum on a DTM build and the tiles' drawn grounds. The `site` fixture and helpers come from tests/test_s99_validate.py;
its tiny terrain is tests/tinycity.py tiny_terrain()."""
import gzip
import json

import numpy as np
import pytest

from pipeline import io, s03_tiles, s99_validate, tiles_decode
from tests.test_s99_validate import VERSION, check, site
from tests.tinycity import ACCURACY, SOURCES, TERRAIN, ground_rows, tiny_city, tiny_terrain

__all__ = ["site"]


def edit_config(out, **terrain_keys):
    cfg = json.loads((out / "stockholm.json").read_text())
    cfg["terrain"] = {**cfg["terrain"], **terrain_keys}
    io.write_json(out / "stockholm.json", cfg)


def edit_record(site, **keys):
    """data/terrain.json, s02_terrain's record (the site's working directory holds data/)."""
    path = site.parents[2] / "data" / "terrain.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), **keys}))


LM = dict(SOURCES[0], id="lm_markhojd", attribution="Markhöjdmodell Nedladdning, © Lantmäteriet, CC BY 4.0 (bearbetad)")


def as_dtm_build(site, datum):
    """The site rebuilt as a consistent DTM build: the file, the record, the config and the credit all say dtm."""
    b, y, a = tiny_city()
    s03_tiles.write_outputs(s03_tiles.join(b, y, a, ground_rows(b, a)), site, VERSION, sources=SOURCES + [LM],
                            accuracy=ACCURACY, terrain={**TERRAIN, "source": "dtm", "datum": datum})
    io.write_gz(site / "terrain.bin.gz", tiny_terrain(source="dtm"))
    edit_record(site, source="dtm", datum=datum)


def test_a_clean_tiny_terrain_passes(site):
    assert check(site) == []


def test_the_header_must_match_stockholm_json(site):
    edit_config(site, cell=25.0, nx=7)
    assert check(site) == ["terrain: terrain.bin.gz's header disagrees with stockholm.json on ['cell', 'nx']"]


@pytest.mark.parametrize(("key", "value"), [("x0", -60.0), ("z0", -20.0), ("cell", 25.0), ("nx", 7), ("nz", 4),
                                            ("waterZ", 0.5)])
def test_every_header_field_must_match_stockholm_json(site, key, value):
    edit_config(site, **{key: value})
    assert check(site) == [f"terrain: terrain.bin.gz's header disagrees with stockholm.json on ['{key}']"]


@pytest.mark.parametrize("water_z", [0.07, 0.86, 0.5, 0.0])
def test_the_headers_float32_water_level_matches_the_config_within_a_centimetre(site, water_z):
    # PIPELINE-6: the header holds water_z as a float32, so 0.07 (Saltsjön's mean, D39) reads 0.07000000029802322
    from pipeline import terrain as T
    grid = T.Grid(TERRAIN["x0"], TERRAIN["z0"], TERRAIN["cell"], TERRAIN["nx"], TERRAIN["nz"])
    h = 1.0 + np.add.outer(np.arange(grid.nz), np.arange(grid.nx)).astype(float)
    cls = np.full((grid.nz - 1, grid.nx - 1), T.LAND, dtype=np.uint8)
    shore = np.packbits(np.ones(4, bool), bitorder="little").tobytes()
    io.write_gz(site / "terrain.bin.gz", T.pack(grid, h, np.zeros_like(h), [max(water_z, 0.0) + 1.0], water_z, cls,
                                                 b"", 0, shore, 4, "contours"))
    edit_config(site, waterZ=water_z)
    assert check(site) == []
    edit_config(site, waterZ=round(water_z + 0.011, 3))     # more than a centimetre off still fails
    assert check(site) == ["terrain: terrain.bin.gz's header disagrees with stockholm.json on ['waterZ']"]


def test_a_burial_count_made_at_another_relief_fails(site):
    # the Hills slider's review (S5): data/terrain.json's buried was counted at its relief_max; the viewer's slider
    # reaches stockholm.json's reliefMax. A record counted at the old 3x (or with no relief at all) is caught.
    edit_record(site, relief_max=3.0)
    msg = ("terrain: data/terrain.json counted its buried buildings at 3x, stockholm.json's slider reaches 2.5x (run "
           "s02_terrain again)")
    assert check(site) == [msg]
    edit_record(site, relief_max=None)
    assert check(site) == [msg.replace("at 3x", "at [value]x")]


STADSKARTA = dict(SOURCES[0], id="city_stadskarta", licence="CC-BY-4.0",
                  licence_url="https://creativecommons.org/licenses/by/4.0/", modified=True, product="Stadskarta",
                  attribution="Stadskarta, © Stockholms stad, Stadsbyggnadskontoret, CC BY 4.0 (bearbetad / modified)")


@pytest.fixture
def release_ready(monkeypatch):
    """Plan 4b: every --release run also needs a maker, a contact and the answers it waits for; these tests check only
    the terrain's rule, so they get placeholders."""
    monkeypatch.setattr(s99_validate.city, "MAKER", "Ann Maker")
    monkeypatch.setattr(s99_validate.city, "CONTACT", "hej@example.org")
    monkeypatch.setattr(s99_validate.city, "RELEASE_WAITS_FOR", ())


NOT_COVERED = ("terrain: a release built from the City's contour lines needs the City's answer to name them: "
               "sources.yml's city_stadskarta does not say covers_contours: true (ask the City, or build from "
               "Lantmäteriet's model, P13)")


@pytest.mark.parametrize(("covers", "errors"), [(False, [NOT_COVERED]), (None, [NOT_COVERED]), ("yes", [NOT_COVERED]),
                                                (True, [])])
def test_a_contour_release_needs_the_citys_answer_to_cover_the_contour_lines(site, covers, errors, release_ready):
    # PRIVACY-3: the O1 that was sent names the Stadskarta's water, land, names and addresses, not the contour lines.
    # Marking city_stadskarta confirmed is not enough for a release built from them: its covers_contours must say so.
    entry = {**STADSKARTA, "status": "confirmed", **({} if covers is None else {"covers_contours": covers})}
    assert check(site, sources=SOURCES + [entry], release=True) == errors
    assert check(site, sources=SOURCES + [entry]) == []                     # a preview build is never held to it
    as_dtm_build(site, -0.1)                                                  # nor is a build from Lantmäteriet's model
    assert check(site, sources=SOURCES + [entry, dict(LM, status="confirmed")], release=True) == []


def test_a_contour_release_without_the_stadskarta_registered_fails(site, release_ready):
    assert check(site, release=True) == [NOT_COVERED]


def test_one_level_per_water_polygon_and_one_shore_bit_per_water_vertex(site):
    io.write_gz(site / "terrain.bin.gz", tiny_terrain(levels=(0.0, 3.0), n_shore=5))
    assert check(site) == ["terrain: 2 water levels for 1 water polygons",
                           "terrain: shore flags for 5 vertices, water.bin.gz has 4"]


@pytest.mark.parametrize(("node", "error"), [
    (300.0, "terrain: heights from 5 to 300 m, outside -10..250 m"),
    (250.0, None),                                                       # the limits themselves are Stockholm heights
    (-10.0, None),
    (-10.1, "terrain: heights from -10.1 to 5 m, outside -10..250 m"),
])
def test_heights_must_be_stockholm_heights(site, node, error):
    h = np.full((TERRAIN["nz"], TERRAIN["nx"]), 5.0)
    h[2, 3] = node
    io.write_gz(site / "terrain.bin.gz", tiny_terrain(h=h))
    assert check(site) == ([error] if error else [])


@pytest.mark.parametrize(("level", "fails"), [
    (40.0, True),    # over every height: the tiny terrain's highest node is 10 m
    (10.0, False),   # at the highest node
    (0.0, False),    # at the sea's level
    (-1.0, True),    # below the sea's
])
def test_a_level_under_the_sea_or_over_every_height_fails(site, level, fails):
    io.write_gz(site / "terrain.bin.gz", tiny_terrain(levels=(level,)))
    assert check(site) == (["terrain: a water level below the sea's or above every height"] if fails else [])


def test_terrain_over_its_budget_fails(site, monkeypatch):
    monkeypatch.setattr(s99_validate, "TERRAIN_BYTES", 40)
    errors = check(site)
    assert len(errors) == 1 and errors[0].startswith("budget: terrain is ") and errors[0].endswith("over 40")


def test_the_terrain_limits_are_the_specs_and_the_budget_itself_passes(site, monkeypatch):
    # spec §4.6: 1.5 MB transferred; heights -10..250 m; a drawn ground at most 200 m up
    assert s99_validate.TERRAIN_BYTES == 1_500_000
    assert (s99_validate.TERRAIN_DM, s99_validate.MAX_GROUND_DM) == ((-100, 2500), 2000)
    size = (site / "terrain.bin.gz").stat().st_size
    monkeypatch.setattr(s99_validate, "TERRAIN_BYTES", size)
    assert check(site) == []
    monkeypatch.setattr(s99_validate, "TERRAIN_BYTES", size - 1)
    assert check(site) == [f"budget: terrain is {size:,} bytes, over {size - 1:,}"]


def test_a_file_that_does_not_decode_or_a_config_without_terrain_fails(site):
    io.write_gz(site / "terrain.bin.gz", b"HFT1 but not really")
    errors = check(site)
    assert len(errors) == 1 and errors[0].startswith("terrain: terrain.bin.gz does not decode")
    io.write_gz(site / "terrain.bin.gz", tiny_terrain())
    cfg = json.loads((site / "stockholm.json").read_text())
    del cfg["terrain"]
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["terrain: stockholm.json has no terrain block (run s02_terrain and s03_tiles)"]


@pytest.mark.parametrize(("source", "datum", "fails"), [
    ("dtm", -0.12, False),       # MARK_Z is the outline minimum: about -0.1 m on every slope (spike, 2026-10-15)
    ("dtm", -0.62, True),        # the same grounds read in RH 00 against an RH 2000 model: 0.52 m lower
    ("dtm", 0.31, True),
    ("dtm", 0.3, False),         # the limit itself passes, either way
    ("dtm", -0.3, False),
    ("contours", -1.83, False),  # a contour build is never held to it (the first draft's fixture read -1.83 m)
])
def test_the_datum_check_applies_to_a_dtm_build(site, source, datum, fails):
    if source == "dtm":
        as_dtm_build(site, datum)
    else:
        edit_config(site, datum=datum)
        edit_record(site, datum=datum)
    errors = check(site)
    assert errors == ([f"terrain: building grounds sit {datum:g} m off the terrain under their outlines (median, "
                       "limit 0.3): a wrong height datum?"] if fails else [])


def test_a_terrain_from_another_source_than_the_config_fails(site):
    # The owner's DTM fetch, then s02_terrain and s04_base without s03_tiles: Lantmäteriet's heights under a config that
    # says contours, uncredited, and with no datum check
    io.write_gz(site / "terrain.bin.gz", tiny_terrain(source="dtm"))
    edit_record(site, source="dtm", datum=-0.1, fixed=12)
    assert check(site) == [
        "terrain: terrain.bin.gz was built from dtm, stockholm.json says contours (run s03_tiles and s04_base together "
        "after s02_terrain)",
        "terrain: stockholm.json's terrain block disagrees with data/terrain.json on ['source', 'fixed'] (run s03_tiles "
        "and s04_base together after s02_terrain)"]


@pytest.mark.parametrize(("key", "value"), [("source", "dtm"), ("datum", 0.05), ("fixed", 3)])
def test_the_record_must_match_stockholm_json_key_by_key(site, key, value):
    # s02_terrain ran again (another datum, more grounds fixed) and s03_tiles did not
    edit_record(site, **{key: value})
    assert check(site) == [f"terrain: stockholm.json's terrain block disagrees with data/terrain.json on ['{key}'] (run "
                           "s03_tiles and s04_base together after s02_terrain)"]


def test_without_data_terrain_json_the_record_checks_are_reported_not_skipped(site):
    record = site.parents[2] / "data" / "terrain.json"
    record.rename(record.with_name("terrain.json.aside"))
    assert check(site) == [f"terrain: cannot check without {record}"]


def test_lantmateriet_is_credited_exactly_when_its_model_was_used(site):
    # a contour build that credits Lantmäteriet's model all the same
    cfg = json.loads((site / "stockholm.json").read_text())
    cfg["attribution"] = cfg["attribution"] + s03_tiles.attribution([LM])
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["attribution: Lantmäteriet's terrain model is credited, but the terrain came from contours"]
    as_dtm_build(site, -0.1)
    assert check(site) == []
    cfg = json.loads((site / "stockholm.json").read_text())
    cfg["attribution"] = [a for a in cfg["attribution"] if a["id"] != "lm_markhojd"]
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["attribution: Lantmäteriet's terrain model is not credited, but the terrain came from dtm"]


NO_COUNT = "terrain: data/terrain.json lacks a whole-number buried count (run s02_terrain again)"


@pytest.mark.parametrize(("buried", "error"), [
    (10, None),                                                          # buried_max itself passes
    (11, "terrain: 11 buildings buried by more than half their height at 2.5x (limit 10): the terrace cannot free them"),
    (True, NO_COUNT),
    (None, NO_COUNT),
    ("absent", NO_COUNT),                                                # a record written before the count existed
])
def test_buildings_the_terrace_cannot_free_fail(site, buried, error):
    if buried == "absent":
        path = site.parents[2] / "data" / "terrain.json"
        path.write_text(json.dumps({k: v for k, v in json.loads(path.read_text()).items() if k != "buried"}))
    else:
        edit_record(site, buried=buried)
    assert check(site) == ([error] if error else [])


def test_a_building_drawn_under_the_water_fails(site):
    # without s02_terrain's floor, gid 3's MARK_Z of -1.1 m would put its walls in the water
    b, y, a = tiny_city()
    s03_tiles.write_outputs(s03_tiles.join(b, y, a), site, VERSION, sources=SOURCES, accuracy=ACCURACY,
                            terrain=TERRAIN)
    assert check(site) == ["tiles: 1 buildings drawn under the water's floor (gids 3)"]


@pytest.mark.parametrize(("gid", "ground", "error"), [
    (7, 200.0, None),                                                    # 200 m itself passes
    (7, 200.1, "tiles: 1 buildings drawn more than 200 m up (gids 7)"),
    (3, 0.2, "tiles: 1 buildings drawn under the water's floor (gids 3)"),   # the clean site draws gid 3 at 0.3 m
])
def test_a_drawn_ground_must_lie_between_the_waters_floor_and_200_m(site, gid, ground, error):
    b, y, a = tiny_city()
    g = ground_rows(b, a)
    g.loc[gid, "ground"] = ground
    s03_tiles.write_outputs(s03_tiles.join(b, y, a, g), site, VERSION, sources=SOURCES, accuracy=ACCURACY,
                            terrain=TERRAIN)
    assert check(site) == ([error] if error else [])


def test_the_tiles_carry_the_grounds_s02_terrain_settled(site):
    cfg = json.loads((site / "stockholm.json").read_text())
    packs = {p: gzip.decompress((site / p).read_bytes()) for p in cfg["packs"]}
    grounds = {}
    for t in cfg["tiles"]:
        tile = tiles_decode.parse(packs[t["pack"]], t["offset"])
        grounds.update(zip(tile["gid"].tolist(), tile["ground"].tolist()))
    assert grounds[3] == 3 and grounds[7] == 736          # 0.3 m floor (dm); Kaknästornet's 73.6 m kept
