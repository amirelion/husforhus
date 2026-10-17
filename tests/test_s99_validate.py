import gzip
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from pipeline import city, codes, io, s03_tiles, s04_base, s14_search, s99_validate
from tests.tinycity import (ACCURACY, LANDMARKS, PHOTO_KEY, SOURCES, TERRAIN, WIKI, ground_rows, local_box, tiny_city,
                            tiny_terrain, write_data)

VERSION = "v20990101"


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A clean tiny build: data/ parquet files and web/data/<VERSION>/ written by s03's writers (with the grounds
    s02_terrain settles), plus the land, water, terrain and labels that s04_base and s07_labels add (C7: s03_tiles
    never ships alone), and the photo s06_wiki would have copied to web/data/photos/ (Plan 4a)."""
    monkeypatch.chdir(tmp_path)
    write_data(tmp_path / "data")
    out = tmp_path / "web" / "data" / VERSION
    b, y, a = tiny_city()
    s03_tiles.write_outputs(s03_tiles.join(b, y, a, ground_rows(b, a)), out, VERSION, sources=SOURCES,
                            accuracy=ACCURACY, terrain=TERRAIN, wiki=WIKI, landmarks=LANDMARKS)
    # Plan 4b: the search index s14_search adds
    s14_search.write(out, *s14_search.build(s03_tiles.join(*tiny_city()), s14_search.read_cards(out),
                                            s03_tiles.load_places(tmp_path / "data")))
    (tmp_path / "web" / "data" / "photos").mkdir()
    (tmp_path / "web" / "data" / "photos" / PHOTO_KEY).write_bytes(b"\xff\xd8 a tiny jpeg")   # s06_wiki's copy
    io.write_gz(out / "land.bin.gz", s04_base.pack([local_box(-800, -800, 800, 800)]))
    io.write_gz(out / "water.bin.gz", s04_base.pack([local_box(900, -800, 1400, 800)]))
    io.write_gz(out / "terrain.bin.gz", tiny_terrain())
    strommen = {"name": "Strömmen", "water": True, "tier": 1, "pts": [[1100, 0, 0, 300, 80]]}
    io.write_json(out / "labels.json", [strommen])
    io.write_json(tmp_path / "web" / "data" / "current.json", {"version": VERSION})
    return out


def check(out, **kw):
    kw.setdefault("takedowns", [])                     # Plan 4b: a test's own takedowns, never pipeline/suppress.yml
    return s99_validate.validate(out, out.parents[2] / "data", sources=kw.pop("sources", SOURCES), **kw)


def edit_attrs(out, fn):
    a = np.frombuffer(gzip.decompress((out / "attrs.bin.gz").read_bytes()), dtype=s03_tiles.ATTR_DTYPE).copy()
    fn(a)
    io.write_gz(out / "attrs.bin.gz", a.tobytes())


def edit_card(out, gid, card):
    path = out / "cards" / f"{gid % 64:02d}.json"
    shard = json.loads(path.read_text())
    shard[str(gid)] = card
    io.write_json(path, shard)


def reindex(out):
    """Plan 4b: s14_search runs after s03_tiles; a test whose edited cards drop a name the index has calls this to get
    the index a build would write (from the data/ files as the test left them; s03_tiles.load would also insist on a
    terrain built from them, which search does not read)."""
    if (out / "search" / "index.json").exists():
        data = out.parents[2] / "data"
        df = s03_tiles.join(gpd.read_parquet(data / "buildings.parquet"), pd.read_parquet(data / "years.parquet"),
                            pd.read_parquet(data / "attributes.parquet"))
        s14_search.write(out, *s14_search.build(df, s14_search.read_cards(out), s03_tiles.load_places(data)))


def test_clean_build_passes(site):
    assert check(site) == []


def test_file_size_and_budgets(site, monkeypatch):
    monkeypatch.setattr(s99_validate, "MAX_FILE_BYTES", 20_000)
    monkeypatch.setattr(s99_validate, "FIRST_LOAD_BYTES", 500)
    monkeypatch.setattr(s99_validate, "WHOLE_CITY_BYTES", 2_000)
    errors = check(site)
    assert not any(e.startswith("size:") for e in errors)
    assert any("first load" in e for e in errors)
    assert any("whole city" in e for e in errors)
    monkeypatch.setattr(s99_validate, "MAX_FILE_BYTES", 1_000)
    assert any(e.startswith("size: stockholm.json is") for e in check(site))


@pytest.mark.parametrize(("field", "gid", "value", "message"), [
    ("year", 0, 0, "year 0 and yflag UNKNOWN disagree"),
    ("year", 5, 1900, "year 0 and yflag UNKNOWN disagree"),
    ("year", 3, 999, "year outside 1000..2026"),
    ("year", 3, 2027, "year outside 1000..2026"),
    ("h_dm", 2, 0, "height outside (0, 200] m"),
    ("h_dm", 2, 2001, "height outside (0, 200] m"),
    ("floors", 7, 61, "more than 60 floors"),
    ("x", 5, float("nan"), "NaN or out-of-bounds coordinates"),
    ("z", 5, float("nan"), "NaN or out-of-bounds coordinates"),
    ("x", 2, float("inf"), "NaN or out-of-bounds coordinates"),
    ("x", 2, -30_001.0, "NaN or out-of-bounds coordinates"),
    ("z", 2, 30_001.0, "NaN or out-of-bounds coordinates"),
    ("yflag", 3, 5, "yflag outside contract C2"),  # 5 was DECADE, now retired
    ("period", 3, len(city.PERIODS), f"period outside the {len(city.PERIODS)} periods"),
])
def test_attribute_rules(site, field, gid, value, message):
    edit_attrs(site, lambda a: a[field].__setitem__(gid, value))
    errors = check(site)
    assert len(errors) == 1 and message in errors[0] and f"gids {gid}" in errors[0]


@pytest.mark.parametrize(("gid", "field", "value"), [
    (3, "year_from", 1930),  # RANGE 1927..1929 shown as 1929: a from-year after the year
    (3, "year_to", 1928),    # ... or a to-year before it
    (2, "year", 1701),       # LONG 1625..1700: a year after its own range
])
def test_a_dated_year_must_lie_in_its_own_range(site, gid, field, value):
    # P6: dated rows need year_from <= year <= year_to
    edit_attrs(site, lambda a: a[field].__setitem__(gid, value))
    assert check(site) == [f"attrs: 1 buildings dated with a year outside their own year_from..year_to (gids {gid})"]


def test_a_dated_range_must_not_end_in_the_future(site):
    # P6: LONG 1625..1700 ending in 2029
    edit_attrs(site, lambda a: a["year_to"].__setitem__(2, 2029))
    assert check(site) == ["attrs: 1 buildings with a year_to after 2026 (gids 2)"]


def test_a_private_decade_may_end_after_the_latest_year():
    # D18: a private house of the 2020s publishes 2020..2029; its decade end is not a year in the future
    assert s99_validate.check_attrs(private_row(2020, len(city.PERIODS) - 1)) == []


def test_coordinates_exactly_at_the_limit_pass(site):
    edit_attrs(site, lambda a: (a["x"].__setitem__(2, 30_000.0), a["z"].__setitem__(2, -30_000.0)))
    assert check(site) == []


def test_exact_year_leaking_for_a_private_house(site):
    # Review Focus #3: RAÄ dates the private house (gid 4) exactly to 1968; only "1960s" may ship
    def leak(a):
        a["year"][4], a["year_from"][4], a["year_to"][4] = 1968, 1968, 1968
    edit_attrs(site, leak)
    errors = check(site)
    assert len(errors) == 1
    assert errors[0].startswith("attrs: 1 buildings marked private but not published as exactly a decade")
    assert errors[0].endswith("(gids 4)")


def test_private_decade_and_period_must_not_narrow_the_year(site):
    # Task 10 review: a decade whose only overlap with the row's period is one year gives the year away.
    # Decade 1610..1619 with p1 (1000..1610) can only be 1610; the row is still "exactly a decade" on its own.
    def narrow(a):
        a["year"][4], a["year_from"][4], a["year_to"][4], a["period"][4] = 1610, 1610, 1619, 0
    edit_attrs(site, narrow)
    errors = check(site)
    assert len(errors) == 1
    assert errors[0].startswith("attrs: 1 buildings marked private whose decade and period narrow the exact year")
    assert errors[0].endswith("(gids 4)")


def test_a_private_decade_that_misses_its_period_entirely_fails(site):
    # decade 1960..1969 against p3 (1719..1809): no overlap, so the row contradicts itself
    edit_attrs(site, lambda a: a["period"].__setitem__(4, 2))
    errors = check(site)
    assert len(errors) == 1 and "narrow the exact year" in errors[0] and errors[0].endswith("(gids 4)")


def private_row(year=1610, period=0):
    a = np.zeros(1, dtype=s03_tiles.ATTR_DTYPE)
    a["h_dm"], a["floors"], a["yflag"], a["ysrc"], a["private"] = 50, 2, codes.EXACT, codes.SRC_RAA, 1
    a["year"], a["year_from"], a["year_to"], a["period"] = year, year, year + 9, period
    return a


@pytest.mark.parametrize(("period_to", "narrowed"), [(1609, True), (1610, True), (1611, False), (1700, False)])
def test_overlap_of_two_years_is_the_threshold(period_to, narrowed):
    # decade 1610..1619 against a period 1000..period_to: 0 or 1 shared years narrow, 2 or more do not
    errors = s99_validate.check_attrs(private_row(), periods=[(1000, period_to)])
    assert bool(errors) is narrowed


def test_a_period_that_shares_most_of_the_decade_does_not_narrow():
    periods = [(0, 0)] * 8 + [(1946, 1964), (1965, 1975)]  # index 8 is p9, which shares 1960..1964 with the decade
    assert s99_validate.check_attrs(private_row(1960, 8), periods=periods) == []


@pytest.mark.parametrize("exact_year", [True, False], ids=["exact-year", "decade-kept"])
@pytest.mark.parametrize("gid", [4, 6])
def test_a_dated_private_category_house_not_marked_private_fails(site, gid, exact_year):
    # D18 checked from KATEGORI, not from the `private` byte it governs: with the byte cleared the decade rule
    # (which only looks at private rows) cannot see the problem, and an exact year would ship.
    def unmark(a):
        a["private"][gid] = 0
        if exact_year:
            a["year"][gid] = a["year_from"][gid] = a["year_to"][gid] = a["year"][gid] + 8
    edit_attrs(site, unmark)
    expected = [f"attrs: 1 private-category buildings not marked private (an exact year would ship) (gids {gid})"]
    if gid == 4 and not exact_year:   # Plan 2: a non-private row must carry its year's period; 1960 is not p10's
        expected.insert(0, "attrs: 1 buildings dated and not private whose period is not their year's (gids 4)")
    assert check(site) == expected


def test_the_private_mark_is_not_required_for_undated_or_curated_houses_in_a_private_category(site):
    # gid 5 is an undated Enbostadshus (clean build passes with private 0); gid 1 is curated, so it may keep its year
    data = site.parents[2] / "data"
    b = gpd.read_parquet(data / "buildings.parquet")
    b.loc[b.gid == 1, "kategori"] = "Kolonistuga"
    b.to_parquet(data / "buildings.parquet")
    # Plan 4a: no attrs rule fires; only the timeline, which s03_tiles built before the change, now names a
    # private-category house (D18: a curated house shows its year on its card, never on the timeline)
    assert check(site) == ["landmarks: entry 0 is a private-category house (D18)"]


def test_tiles_must_hold_every_gid_exactly_once(site):
    cfg = json.loads((site / "stockholm.json").read_text())
    t = cfg["tiles"][0]
    blob = bytearray(gzip.decompress((site / t["pack"]).read_bytes()))
    first, second = np.frombuffer(blob, "<u4", 2, t["offset"] + 28)
    blob[t["offset"] + 28:t["offset"] + 32] = np.uint32(second).tobytes()  # gid `first` → a copy of `second`
    io.write_gz(site / t["pack"], bytes(blob))
    errors = check(site)
    assert errors == [f"tiles: 1 gids missing (gids {first})", f"tiles: 1 gids drawn more than once (gids {second})"]


def test_a_missing_attrs_file_is_a_readable_error(site):
    (site / "attrs.bin.gz").rename(site / "attrs.bin.gz.aside")
    assert check(site) == [f"missing {site / 'attrs.bin.gz'}"]


def test_a_folder_without_land_water_or_labels_fails(site):
    # P1 (C7): s03_tiles alone writes a folder the viewer cannot load (loadBase/loadLabels fail)
    for name in ("land.bin.gz", "water.bin.gz", "terrain.bin.gz", "labels.json"):
        (site / name).rename(site / f"{name}.aside")
    assert check(site) == ["base: land.bin.gz is missing (run s04_base)",
                           "base: water.bin.gz is missing (run s04_base)",
                           "base: terrain.bin.gz is missing (run s02_terrain and s04_base)",
                           "labels: labels.json is missing (run s07_labels)"]


@pytest.mark.parametrize("name", ["land.bin.gz", "water.bin.gz"])
def test_land_or_water_without_a_polygon_fails(site, name):
    # P1: Vatten_area with nothing inside the boundary packs an empty list, and s04_base still exits 0
    io.write_gz(site / name, s04_base.pack([]))
    assert check(site) == [f"base: {name} holds no polygon"]


def test_land_that_does_not_decode_fails(site):
    io.write_gz(site / "land.bin.gz", b"\x05\x00\x00\x00")
    errors = check(site)
    assert len(errors) == 1 and errors[0].startswith("base: land.bin.gz does not decode")


@pytest.mark.parametrize("labels", [[], {"name": "Strömmen"}], ids=["empty", "not-a-list"])
def test_labels_must_be_a_list_with_at_least_one_label(site, labels):
    io.write_json(site / "labels.json", labels)
    assert check(site) == ["labels: labels.json is not a list with at least one label"]


def test_labels_that_are_not_json_fail(site):
    (site / "labels.json").write_text("[{", encoding="utf-8")
    assert check(site) == ["labels: labels.json is not valid JSON"]


def test_stockholm_json_must_name_its_own_folder(site):
    # P1: a config copied from another version would point the viewer at that version's numbers
    cfg = json.loads((site / "stockholm.json").read_text())
    io.write_json(site / "stockholm.json", dict(cfg, version="v20990102"))
    assert check(site) == [f"stockholm.json: version is v20990102 but the folder is {VERSION}"]


def test_buildings_parquet_from_another_build_fails(site):
    # P3: after the fixture build data/ holds 519 rows while the city version has 77,743; the KATEGORI and leak
    # checks would read another build's rows by gid and see almost nothing
    data = site.parents[2] / "data"
    b = gpd.read_parquet(data / "buildings.parquet")
    b.iloc[:3].to_parquet(data / "buildings.parquet")
    assert check(site) == [f"data: {data / 'buildings.parquet'} has 3 rows but {VERSION} has 11 buildings: rebuild "
                           "data/ or validate the matching version"]


def test_buildings_parquet_with_other_gids_fails(site):
    data = site.parents[2] / "data"
    b = gpd.read_parquet(data / "buildings.parquet")
    b["gid"] = b.gid + 1
    b.to_parquet(data / "buildings.parquet")
    assert check(site) == [f"data: {data / 'buildings.parquet'} gids are not exactly 0..10: rebuild data/ or validate "
                           "the matching version"]


def test_sources_pending_fail_only_a_release(site, monkeypatch):
    # the site's terrain is a contour build: its release also needs the Stadskarta to cover the contour lines (PRIVACY-3)
    from tests.test_s99_terrain import STADSKARTA
    pending = [dict(SOURCES[0], status="pending-O1"), dict(STADSKARTA, status="confirmed", covers_contours=True)]
    assert check(site, sources=pending) == []
    monkeypatch.setattr(city, "MAKER", "A maker")         # Plan 4b: a release also needs these (tests/test_suppress.py)
    monkeypatch.setattr(city, "CONTACT", "hej@example.org")
    monkeypatch.setattr(city, "RELEASE_WAITS_FOR", ())     # ... and the answers to the decisions it waits for
    errors = check(site, sources=pending, release=True)
    assert len(errors) == 1 and errors[0].startswith("sources:") and "pending-O1" in errors[0]


def test_uuid_in_a_card_fails(site):
    edit_card(site, 3, {"name": "Spaden", "raa": "2E389B81-54F2-48CC-B4EE-AE1285DF2203"})
    errors = check(site)
    assert errors == ["privacy: cards/03.json $.3.raa holds a City/register UUID"]


def test_property_designation_in_a_card_or_label_fails(site):
    edit_card(site, 2, {"name": "Kv. Gråmunkeholmen  3"})
    io.write_json(site / "labels.json", [{"name": "Diana 1", "water": False, "tier": 2, "pts": []}])
    errors = check(site)
    assert errors == ["privacy: cards/02.json $.2.name holds a property designation (FASTIGHET)",
                      "privacy: labels.json $[0].name holds a property designation (FASTIGHET)"]


def test_a_property_unit_key_in_any_json_fails_as_text_or_as_a_number(site):
    # Task 14b: the LOD1 FNR (data/buildings.parquet `fnr`) is internal like FASTIGHET. gid 3's key is 10123403: in a
    # card name, as a number in a label, or as a field called fnr, it fails, and the error never prints the value.
    edit_card(site, 3, {"name": "Spaden 10123403"})
    io.write_json(site / "labels.json", [{"name": "Strand", "water": False, "tier": 2, "pts": [[10123405, 0, 0, 1, 1]]},
                                         {"name": "Kaj", "water": False, "tier": 2, "pts": [], "FNR": 1}])
    errors = check(site)
    assert errors == ["privacy: cards/03.json $.3.name holds a property-unit key (FNR)",
                      "privacy: labels.json $[0].pts[0][0] holds a property-unit key (FNR)",
                      "privacy: labels.json $[1].FNR is a property-unit key field (FNR)"]
    assert not any("10123403" in e or "10123405" in e for e in errors)


def test_without_an_fnr_column_the_other_privacy_checks_still_run(site):
    # a data/ built before Task 14b has no fnr column (and nothing could have shipped one); 0 is "no key", never a leak
    data = site.parents[2] / "data"
    b = gpd.read_parquet(data / "buildings.parquet")
    b.drop(columns="fnr").to_parquet(data / "buildings.parquet")
    edit_card(site, 2, {"name": "Diana 1"})
    assert check(site) == ["privacy: cards/02.json $.2.name holds a property designation (FASTIGHET)"]
    assert 0 not in s99_validate.privacy_sets(data)[2] and s99_validate.privacy_sets(data)[2] == set()


def test_a_designation_inside_a_longer_string_fails_by_segment(site):
    io.write_json(site / "labels.json", [{"name": "Gamla stan (Diana 1) / Norr", "water": False, "tier": 2, "pts": []}])
    assert check(site) == ["privacy: labels.json $[0].name holds a property designation (FASTIGHET)"]


def test_a_card_name_with_a_register_code_fails(site):
    # Plan 4b, Task 10: a register's building code is an internal id (s02_attributes.REGISTER_CODE takes it out)
    edit_card(site, 2, {"name": "K0061.006, K0061.005"})
    assert check(site) == ["cards: 02.json gid 2 name carries a register's building code"]
    edit_card(site, 2, {"name": "Kanslikasern", "en": "Barracks (K0061.001)"})
    assert check(site) == ["cards: 02.json gid 2 en carries a register's building code"]


def test_safe_names_that_resemble_designations_pass(site):
    io.write_json(site / "labels.json", [
        {"name": "Tre Kronor", "water": False, "tier": 2, "pts": [[0, 0, 0, 50, 10]]},
        {"name": "Dianavägen 1", "water": False, "tier": 2, "pts": []},
    ])
    assert check(site) == []


def test_normalise_strips_kv_and_collapses_spaces():
    assert s99_validate.normalise("Kv.  GRÅMUNKEHOLMEN   3") == "gråmunkeholmen 3"
    assert s99_validate.normalise("KV Diana 1") == "diana 1"
    assert s99_validate.normalise("Kvarnen 1") == "kvarnen 1"


LEAKS = {  # real tinycity values: gid 3's UUID, in two cases, and two FASTIGHET designations
    "uuid": "2e389b81-54f2-48cc-b4ee-ae1285df2203",
    "uuid-upper": "2E389B81-54F2-48CC-B4EE-AE1285DF2203",
    "fastighet": "TRE KRONOR 1",
    "fastighet-kv": "Kv. Diana 1",
}


@pytest.mark.parametrize("leak", LEAKS.values(), ids=LEAKS.keys())
def test_a_leaked_value_used_as_a_json_key_is_never_printed(site, leak):
    # Finding 1: if a shard were keyed by UUID, the log would carry every UUID. Keys that are not identifiers show
    # as [key #i], in the card checks and in the privacy paths alike.
    io.write_json(site / "cards" / "03.json", {leak: {"name": "Spaden"}})
    io.write_json(site / "labels.json", [{"name": "Strand", "water": False, "tier": 2, "pts": [], leak: 1}])
    errors = check(site)
    assert errors, "the run must still fail"
    assert not any(leak.casefold() in e.casefold() for e in errors)
    assert errors[0] == "cards: 03.json holds a non-gid key ([key #0])"
    kind = "a City/register UUID" if "-" in leak else "a property designation (FASTIGHET)"
    assert errors[1:] == [f"privacy: cards/03.json $[key #0] holds {kind}", f"privacy: labels.json $[0][key #0] holds {kind}"]


@pytest.mark.parametrize("leak", [LEAKS["uuid"], LEAKS["fastighet"]], ids=["uuid", "fastighet"])
def test_a_leaked_value_used_as_a_card_field_name_is_never_printed(site, leak):
    io.write_json(site / "cards" / "03.json", {"3": {"name": "Spaden", leak: 1}})
    errors = check(site)
    assert errors[0] == "cards: 03.json gid 3 has fields other than C21's: ['[field #0]']"
    assert len(errors) == 2 and errors[1].startswith("privacy: cards/03.json $.3[key #")
    assert not any(leak.casefold() in e.casefold() for e in errors)


def test_a_non_gid_key_that_is_an_identifier_is_named(site):
    io.write_json(site / "cards" / "03.json", {"spaden": {"name": "Spaden"}})
    assert check(site) == ["cards: 03.json holds a non-gid key (spaden)"]


def test_a_gid_in_the_wrong_shard_is_reported(site):
    io.write_json(site / "cards" / "03.json", {"4": {"name": "Spaden"}})
    assert check(site) == ["cards: 03.json holds gid 4, which belongs elsewhere"]


def test_cards_hold_only_safe_fields(site):
    edit_card(site, 3, {"raa": "012a1a82-9a9c-4bf7-b88f-2480c9221516", "year": 1929})
    assert check(site) == ["cards: 03.json gid 3 has fields other than C21's: ['year']"]


def test_raa_link_on_a_private_house_fails(site):
    # Review Focus #3: RAÄ's page for gid 4 shows the exact year, so its card must not link it
    edit_card(site, 4, {"raa": "012a1a82-9a9c-4bf7-b88f-2480c9221516"})
    assert check(site) == ["cards: 04.json gid 4 is in a private-house category and links its RAÄ record"]


def test_raa_link_on_an_undated_house_in_a_private_category_fails(site):
    # D18: gid 5 is an undated Enbostadshus (not private) whose raa_id survived; its card must not link it either
    edit_card(site, 5, {"raa": "3f8f590d-6bd1-4b31-85ee-2306fb98332a"})
    assert check(site) == ["cards: 05.json gid 5 is in a private-house category and links its RAÄ record"]


def test_every_undated_house_in_a_private_category_is_checked_not_just_one(site):
    # the real data has several such houses, not one: gid 7 becomes a second undated Kolonistuga
    data = site.parents[2] / "data"
    b = gpd.read_parquet(data / "buildings.parquet")
    b.loc[b.gid == 7, "kategori"] = "Kolonistuga"
    b.to_parquet(data / "buildings.parquet")
    edit_card(site, 5, {"raa": "3f8f590d-6bd1-4b31-85ee-2306fb98332a"})
    edit_card(site, 7, {"name": "Kaknästornet", "raa": "0b3c1f6e-2d4a-4e57-9a31-5c8e7b2f1a90"})
    reindex(site)                                       # Plan 4b: the card no longer has its English label
    assert check(site) == ["cards: 05.json gid 5 is in a private-house category and links its RAÄ record",
                           "cards: 07.json gid 7 is in a private-house category and links its RAÄ record",
                           "cards: 07.json gid 7 is in a private-house category and carries a name not on the reviewed "
                           "list"]


def test_a_curated_building_in_a_private_category_may_link_raa(site):
    data = site.parents[2] / "data"
    b = gpd.read_parquet(data / "buildings.parquet")
    b.loc[b.gid == 1, "kategori"] = "Enbostadshus"  # gid 1 is curated (ysrc SRC_CURATED)
    b.to_parquet(data / "buildings.parquet")
    edit_card(site, 1, {"name": "Kungliga slottet", "raa": "011ae7cb-9b96-42ac-b8b0-17b5a281b98a", "qid": "Q750444",
                        "wp": ["sv", "en"]})
    reindex(site)                                       # Plan 4b: the card no longer has its English label
    # the card may link everything (D34: a curated house gets the full card); its timeline entry may not stay (D18)
    assert check(site) == ["landmarks: entry 0 is a private-category house (D18)"]


def test_without_buildings_parquet_only_the_private_byte_is_checked(site):
    data = site.parents[2] / "data"
    (data / "buildings.parquet").rename(data / "buildings.parquet.aside")  # no KATEGORI by gid now
    edit_card(site, 4, {"raa": "012a1a82-9a9c-4bf7-b88f-2480c9221516"})
    edit_card(site, 5, {"raa": "3f8f590d-6bd1-4b31-85ee-2306fb98332a"})
    errors = check(site)
    assert errors[0] == "cards: 04.json gid 4 is in a private-house category and links its RAÄ record"
    assert len(errors) == 2 and errors[1].startswith("privacy: cannot check without")


def test_main_exits_1_with_a_readable_list(site, capsys):
    s99_validate.main(["--data", "data"])
    assert "OK" in capsys.readouterr().out
    edit_card(site, 3, {"name": "Diana 1"})
    with pytest.raises(SystemExit) as exc:
        s99_validate.main([])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "1 problem(s)" in err and "  - privacy: cards/03.json $.3.name" in err


def test_an_attribution_without_its_d44_lines_fails(site):
    # Plan 4b, Task 9 (D44): About lists every source as "Dataset: publisher, licence" (plus ", processed" /
    # ", bearbetad"), in both languages, with the licence the entry names
    cfg = json.loads((site / "stockholm.json").read_text())
    entry = cfg["attribution"][0]
    assert entry["credit"] == {"en": "Test data: Test, CC0", "sv": "Test data: Test, CC0"}
    bad = [None, "Test data: Test, CC0", {"en": "Test data: Test, CC0"}, {"en": "Test data: Test, CC0", "sv": ""},
           {"en": "Test, CC0", "sv": "Test, CC0"},                                                  # no dataset
           {"en": "Test data: Test", "sv": "Test data: Test"},                                      # no licence
           {"en": "Test data: Test, CC BY 4.0", "sv": "Test data: Test, CC BY 4.0"},                # another licence
           {"en": "Test data: Test, CC0, processed", "sv": "Test data: Test, CC0"},                 # processed in one
           {"en": "Test data: Test, CC0, bearbetad", "sv": "Test data: Test, CC0, bearbetad"},      # the wrong word
           {"en": "Test data: Test, CC0", "sv": "Andra data: Test, CC0"},                           # another dataset
           {"en": " :  , CC0", "sv": " :  , CC0"},                                                  # blank words
           {"en": "Test data: , , CC0", "sv": "Test data: , , CC0"}]                                # no publisher
    for credit in bad:
        changed = {k: v for k, v in entry.items() if k != "credit"} | ({} if credit is None else {"credit": credit})
        io.write_json(site / "stockholm.json", dict(cfg, attribution=[changed]))
        errors = check(site)
        assert len(errors) == 1 and errors[0].startswith("attribution: test-src: ") and "D44" in errors[0], (credit, errors)
    for credit in ({"en": "Test data: Test, CC0, processed", "sv": "Test data: Test, CC0, bearbetad"},
                   {"en": "Bebyggelseregistret, äldre registret: Riksantikvarieämbetet, CC0",
                    "sv": "Bebyggelseregistret, äldre registret: Riksantikvarieämbetet, CC0"}):
        io.write_json(site / "stockholm.json", dict(cfg, attribution=[dict(entry, credit=credit)]))
        assert check(site) == []
    # the City's "CC BY" (licence_as) on a CC BY 4.0 entry; never on a CC BY-SA one
    city_line = "Stadsdelar: © Stockholms stad, Stadsbyggnadskontoret, CC BY, processed"
    cc_by = dict(entry, licence="CC-BY-4.0", credit={"en": city_line, "sv": city_line.replace("processed", "bearbetad")})
    io.write_json(site / "stockholm.json", dict(cfg, attribution=[cc_by]))
    assert check(site) == []
    io.write_json(site / "stockholm.json", dict(cfg, attribution=[dict(cc_by, licence="CC-BY-SA-4.0")]))
    assert len(check(site)) == 1
