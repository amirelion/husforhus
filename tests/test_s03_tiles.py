import gzip
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from pipeline import city, codes, s03_tiles, tiles_decode
from pipeline.sources import load_sources
from tests.tinycity import (ACCURACY, ADDRESSES, DISTRICTS, LANDMARKS, PHOTO_KEY, SOURCES, TERRAIN, WIKI, ground_rows,
                            tiny_city, write_data)

PLACES = {"addresses": ADDRESSES, "districts": DISTRICTS}

VERSION = "v20261014"


def test_attr_record_is_24_bytes_in_contract_order():
    dt = s03_tiles.ATTR_DTYPE
    assert dt.itemsize == 24
    offsets = {name: dt.fields[name][1] for name in dt.names}
    assert offsets == {"h_dm": 0, "fsrc": 2, "yflag": 3, "year": 4, "year_from": 6, "year_to": 8, "ysrc": 10,
                       "rating": 11, "x": 12, "z": 16, "floors": 20, "period": 21, "private": 22, "pad": 23}


def test_packs_split_centre_out_by_building_count():
    tiles = [{"n": 10, "data": bytes([k]) * 4} for k in range(16)]
    packs = s03_tiles.assign_packs(tiles, 8)
    assert len(packs) == 8 and [t["pack"] for t in tiles[:3]] == ["pack0.bin.gz", "pack0.bin.gz", "pack1.bin.gz"]
    assert [(t["offset"], t["length"]) for t in tiles[:2]] == [(0, 4), (4, 4)]
    dense = [{"n": n, "data": b"\0" * 4} for n in (70, 10, 10, 10)]  # a dense centre tile fills its own pack
    assert len(s03_tiles.assign_packs(dense, 8)) == 4
    assert [t["pack"] for t in dense] == [f"pack{k}.bin.gz" for k in range(4)]


def test_retired_yflag_5_is_refused():
    b, y, a = tiny_city()
    y.loc[3, "yflag"] = 5  # was DECADE; private houses now carry the `private` column instead
    with pytest.raises(ValueError, match="yflag"):
        s03_tiles.join(b, y, a)


def test_private_houses_bin_inside_their_decade():
    assert s03_tiles.stable_hash(4) == int(hashlib.md5(b"4").hexdigest()[:8], 16)
    assert (s03_tiles.stable_hash(4) % 10, s03_tiles.stable_hash(6) % 10) == (7, 0)
    df = pd.DataFrame({"gid": [4, 6, 4], "year": [1960, 1930, 2020], "yflag": [codes.EXACT] * 3,
                       "period": [9, 7, 11], "private": [True, True, True]})
    # A private house bins at min(year + stable_hash(gid) % 10, 2026), never after s99's latest year
    assert s03_tiles.LATEST_YEAR == 2026
    assert s03_tiles.histogram_years(df).tolist() == [1967, 1930, 2026]  # 2020 + 7 is capped
    df["private"] = False
    assert s03_tiles.histogram_years(df).tolist() == [1960, 1930, 2020]


def write(out):
    b, y, a = tiny_city()
    return s03_tiles.write_outputs(s03_tiles.join(b, y, a), out, VERSION, sources=SOURCES, accuracy=ACCURACY,
                                   terrain=TERRAIN, wiki=WIKI, landmarks=LANDMARKS, places=PLACES)


def test_pack_offsets_reconstruct_every_tile(tmp_path):
    write(tmp_path)
    cfg = json.loads((tmp_path / "stockholm.json").read_text())
    assert cfg["packs"] == [f"pack{k}.bin.gz" for k in range(len(cfg["packs"]))]
    assert 1 <= len(cfg["packs"]) <= city.N_PACKS
    packs = {p: gzip.decompress((tmp_path / p).read_bytes()) for p in cfg["packs"]}
    seen = []
    for t in cfg["tiles"]:
        tile = tiles_decode.parse(packs[t["pack"]], t["offset"])
        assert tile["end"] == t["offset"] + t["length"]
        assert t["bytes"] == t["length"] and tile["nB"] == t["n"]
        assert tile["origin"] == (t["tx"] * cfg["tileSize"], t["tz"] * cfg["tileSize"])
        seen += tile["gid"].tolist()
    assert sorted(seen) == list(range(11))
    for p, blob in packs.items():
        assert sum(t["length"] for t in cfg["tiles"] if t["pack"] == p) == len(blob)
    dists = [t["dist"] for t in cfg["tiles"]]
    assert dists == sorted(dists)


def test_attrs_hold_one_record_per_gid(tmp_path):
    write(tmp_path)
    a = np.frombuffer(gzip.decompress((tmp_path / "attrs.bin.gz").read_bytes()), dtype=s03_tiles.ATTR_DTYPE)
    assert len(a) == 11
    assert a["h_dm"].tolist() == [267, 180, 391, 125, 63, 210, 31, 1498, 150, 55, 220]
    assert a["yflag"].tolist() == [codes.EXACT, codes.EXACT, codes.LONG, codes.RANGE, codes.EXACT,
                                   codes.UNKNOWN, codes.AREA, codes.UNKNOWN, codes.ESTIMATE, codes.PERIOD, codes.EXACT]
    assert a["ysrc"].tolist() == [codes.SRC_RAA, codes.SRC_CURATED, codes.SRC_RAA, codes.SRC_RAA, codes.SRC_RAA,
                                  codes.SRC_NONE, codes.SRC_RAA_AREA, codes.SRC_NONE, codes.SRC_ESTIMATE,
                                  codes.SRC_ESTIMATE, codes.SRC_WIKIDATA]
    assert a["private"].tolist() == [0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0]
    # The estimate's ±5 band ships as year_from/year_to; the private period-only house ships its decade
    assert (a["year"][8], a["year_from"][8], a["year_to"][8]) == (1952, 1947, 1957)
    assert (a["year"][9], a["year_from"][9], a["year_to"][9], a["period"][9]) == (1930, 1930, 1939, city.period_index(1936))
    # The private house RAÄ dates to 1968 ships as the 1960s, but keeps its period colour (p10, not p9)
    assert (a["year"][4], a["year_from"][4], a["year_to"][4]) == (1960, 1960, 1969)
    assert a["period"][4] == city.period_index(1968) != city.period_index(1960)
    assert a["rating"].tolist() == [1, 1, 2, 0, 0, 0, 0, 3, 0, 0, 0]
    assert abs(a["x"][0] - 5.0) < 0.01 and abs(a["z"][0] - 5.0) < 0.01


def test_cards_hold_only_safe_fields(tmp_path):
    write(tmp_path)
    shards = sorted((tmp_path / "cards").glob("*.json"))
    assert [p.name for p in shards] == [f"{k:02d}.json" for k in range(64)]
    cards = {}
    for p in shards:
        cards.update(json.loads(p.read_text()))
    photo = {k: v for k, v in WIKI["photos"][PHOTO_KEY].items()}
    # The first address and how many there are (the stadsdel ships in districts.bin.gz, below)
    assert cards == {
        "0": {"name": "Tyska kyrkan", "architects": ["Nicodemus Tessin d.y."],
              "raa": "00b0d09f-630d-44fb-ad4e-df8117fdc62b", "prot": 3, "nofloors": True},
        # The RAÄ name wins over the Wikidata label; the English label shows since it differs; the
        # curated palace's rebuilds and cellars from its verified entry
        "1": {"name": "Kungliga slottet", "en": "Stockholm Palace", "prot": 1, "since": 1935, "qid": "Q750444",
              "wp": ["sv", "en"], "photo": photo, "rebuilt": [[1772, "rebuilt"], [1857, "raised"]], "cellars": True,
              "addr": "Slottsbacken 1"},
        "2": {"raa": "011ae7cb-9b96-42ac-b8b0-17b5a281b98a"},
        "3": {"architects": ["Sigurd Lewerentz", "Ivar Tengbom"], "addr": "Hornsgatan 30", "addrn": 2},
        "4": {"addr": "Grimstagatan 5"},
        "7": {"name": "Kaknästornet", "en": "Kaknäs Tower", "qid": "Q1721899", "wp": ["sv"]},
        "10": {"name": "Schönfeldtska huset", "qid": "Q10000001", "wp": ["sv"], "addr": "Västerlånggatan 68"},
    }
    assert json.loads((tmp_path / "photos.json").read_text()) == [PHOTO_KEY]
    wiki = {}
    for k in range(64):
        shard = json.loads((tmp_path / "wiki" / f"{k:02d}.json").read_text())
        assert shard["licence"] == "CC BY-SA 4.0"          # the excerpts' own licence travels with them (§6.1)
        wiki.update(shard["items"])
    assert wiki == WIKI["extracts"]
    # gid 4 is a private house: years.parquet links its RAÄ record, but RAÄ's page shows the exact year; its
    # address shows while city.PRIVATE_ADDRESSES allows it
    assert json.loads((tmp_path / "cards" / "04.json").read_text()) == {"4": {"addr": "Grimstagatan 5"}}
    # gid 5 is an undated Enbostadshus with a raa_id: not private, but its category never links RAÄ either
    assert json.loads((tmp_path / "cards" / "05.json").read_text()) == {}
    # One byte per gid, 1 + the stadsdel's place in stockholm.json `districts`
    cfg = json.loads((tmp_path / "stockholm.json").read_text())
    assert cfg["districts"] == ["Gamla stan", "Grimsta", "Ladugårdsgärdet", "Riddarholmen", "Södermalm"]
    codes_ = gzip.decompress((tmp_path / "districts.bin.gz").read_bytes())
    assert [cfg["districts"][c - 1] for c in codes_] == ["Gamla stan", "Gamla stan", "Riddarholmen", "Södermalm",
                                                         "Grimsta", "Södermalm", "Gamla stan", "Ladugårdsgärdet",
                                                         "Gamla stan", "Grimsta", "Gamla stan"]


def test_places_give_the_first_address_its_count_and_the_district(monkeypatch):
    df = pd.DataFrame({"gid": [0, 1, 2]})
    places = {"addresses": pd.DataFrame({"gid": [1, 1, 2], "street": ["Götgatan", "Götgatan", "Hornsgatan"],
                                         "number": ["7", "9", "30A"]}),
              "districts": pd.DataFrame({"gid": [0, 1, 2], "district": ["ULVSUNDA INDUSTRIOMR", "SÖDERMALM", "NYTT OMR"]})}
    got = s03_tiles.with_places(df, places)
    assert got.addr.tolist() == ["", "Götgatan 7", "Hornsgatan 30A"] and got.addrn.tolist() == [0, 2, 1]
    # the display name from city.DISTRICT_NAMES; a NAMN the table does not know is title-cased rather than shouted
    assert got.dist.tolist() == ["Ulvsunda industriområde", "Södermalm", "Nytt Omr"]
    assert s03_tiles.with_places(df, s03_tiles.no_places()).addr.tolist() == ["", "", ""]


def test_a_private_house_keeps_its_address_unless_decision_3_says_no(monkeypatch):
    # gid 2: an undated villa (not `private`, its KATEGORI hides it); gid 3: a curated villa
    df = pd.DataFrame({"gid": [0, 1, 2, 3], "name": ["", "", "", ""], "architects": [[], [], [], []],
                       "raa_id": [""] * 4, "private": [True, False, False, False],
                       "kategori": ["Enbostadshus", "Flerbostadshus", "Enbostadshus", "Enbostadshus"],
                       "ysrc": [codes.SRC_RAA, codes.SRC_RAA, codes.SRC_NONE, codes.SRC_CURATED],
                       "addr": ["Grimstagatan 5", "Hornsgatan 30", "Grimstagatan 7", "Villagatan 1"],
                       "addrn": [1, 3, 1, 1], "dist": ["Grimsta", "Södermalm", "Grimsta", "Bromma"]})
    cards = {g: c for shard in s03_tiles.card_shards(df) for g, c in shard.items()}
    assert cards == {"0": {"addr": "Grimstagatan 5"}, "1": {"addr": "Hornsgatan 30", "addrn": 3},
                     "2": {"addr": "Grimstagatan 7"}, "3": {"addr": "Villagatan 1"}}
    monkeypatch.setattr(city, "PRIVATE_ADDRESSES", False)                                # if the answer is no
    cards = {g: c for shard in s03_tiles.card_shards(df) for g, c in shard.items()}
    assert cards == {"1": {"addr": "Hornsgatan 30", "addrn": 3}, "3": {"addr": "Villagatan 1"}}


def test_district_codes_fit_a_byte():
    names, b = s03_tiles.district_codes(pd.DataFrame({"dist": ["Södermalm", "", "Gamla stan", "Södermalm"]}))
    assert names == ["Gamla stan", "Södermalm"] and b.tolist() == [2, 0, 1, 2] and b.dtype == np.uint8
    with pytest.raises(ValueError, match="do not fit one byte"):
        s03_tiles.district_codes(pd.DataFrame({"dist": [f"D{i}" for i in range(256)]}))


def test_no_raa_link_in_the_private_house_categories_unless_curated():
    # No card links RAÄ for a building whose kategori is in city.PRIVATE_HOUSE_KATEGORI, dated or not,
    # unless it is curated. Other categories keep their link.
    df = pd.DataFrame({
        "gid": [0, 1, 2, 3, 4],
        "name": ["", "", "", "Villa Exempel", ""],
        "architects": [[], [], [], [], []],
        "raa_id": ["r0", "r1", "r2", "r3", "r4"],
        "private": [False, True, False, False, False],
        "kategori": ["Enbostadshus", "Enbostadshus", "Kolonistuga", "Enbostadshus", "Flerbostadshus"],
        "ysrc": [codes.SRC_NONE, codes.SRC_RAA, codes.SRC_NONE, codes.SRC_CURATED, codes.SRC_NONE],
    })
    cards = {gid: card for shard in s03_tiles.card_shards(df) for gid, card in shard.items()}
    # 0: undated house (UNKNOWN) with a raa_id; 1: private house; 2: undated colony cottage; 3: curated house
    assert cards == {"3": {"name": "Villa Exempel", "raa": "r3"}, "4": {"raa": "r4"}}


def test_nothing_that_states_the_year_reaches_a_private_house_card():
    # Neither a Wikidata item, an article, a photo, an English label, a Wikidata name nor an
    # excerpt on a non-curated private-category house, dated or not, even if s06_wiki had sent one
    df = pd.DataFrame({
        "gid": [0, 1, 2], "name": ["", "", ""], "architects": [[], [], []], "raa_id": ["", "", ""],
        "private": [True, False, False], "kategori": ["Enbostadshus", "Kolonistuga", "Enbostadshus"],
        "ysrc": [codes.SRC_RAA, codes.SRC_NONE, codes.SRC_CURATED], "qid": ["Q1", "Q2", "Q3"],
        "wname": ["Villa A", "Stuga B", "Villa C"], "wname_en": ["A", "B", "C"], "langs": ["sv", "sv", "sv"],
        "photo": [PHOTO_KEY] * 3, "prot": [0, 0, 2], "since": [0, 0, 1990], "nofloors": [False] * 3})
    cards = {g: c for shard in s03_tiles.card_shards(df, WIKI["photos"]) for g, c in shard.items()}
    assert set(cards) == {"2"}                                # the curated house gets its full card
    assert set(cards["2"]) == {"name", "en", "qid", "wp", "photo", "prot", "since"}
    extracts = {"0": {"sv": {"t": "x", "r": 1}}, "1": {"sv": {"t": "y", "r": 1}}, "2": {"sv": {"t": "z", "r": 1}}}
    items = {g: v for shard in s03_tiles.wiki_shards(df, extracts) for g, v in shard["items"].items()}
    assert set(items) == {"2"}


def test_rebuilds_and_cellars_reach_only_a_curated_card():
    # A verified entry's rebuilds (by year) and its older cellars go on the card of the building it dates;
    # a name that is not curated there (gid 1), an entry without them (gid 2) and an unplaced one (D) give nothing
    df = pd.DataFrame({
        "gid": [0, 1, 2, 3], "name": ["", "", "", ""], "architects": [[], [], [], []], "raa_id": ["", "", "", ""],
        "private": [False] * 4, "kategori": ["Allmän byggnad"] * 4,
        "ysrc": [codes.SRC_CURATED, codes.SRC_RAA, codes.SRC_CURATED, codes.SRC_RAA], "landmark": ["A", "B", "C", ""]})
    marks = [{"name": "A", "rebuilt": [[1857, "raised"], [1757, "rebuilt"]], "cellars": True},
             {"name": "B", "rebuilt": [[1935, "extended"]], "cellars": True}, {"name": "C"},
             {"name": "D", "rebuilt": [[1900, "rebuilt"]]}]
    cards = {g: c for shard in s03_tiles.card_shards(df, {}, marks) for g, c in shard.items()}
    assert cards == {"0": {"rebuilt": [[1757, "rebuilt"], [1857, "raised"]], "cellars": True}}
    assert {"rebuilt", "cellars"} <= set(s03_tiles.CARD_FIELDS)
    assert s03_tiles.card_shards(df) == s03_tiles.card_shards(df, {}, [])     # no entries, no rebuild lines
    assert not any(s03_tiles.card_shards(df))


def test_the_timeline_takes_placed_verified_landmarks_with_a_priority_never_a_house():
    df = pd.DataFrame({"gid": [0, 1, 2], "landmark": ["A", "B", "C"], "year": [1754, 1306, 1950],
                       "x": [1.04, 2.0, 3.0], "z": [-4.06, 5.0, 6.0],
                       "kategori": ["Allmän byggnad", "Allmän byggnad", "Enbostadshus"]})
    marks = [{"name": "A", "timeline": 2}, {"name": "B", "timeline": 1}, {"name": "C", "timeline": 1},
             {"name": "D", "timeline": 1}, {"name": "A2"}]
    assert s03_tiles.timeline_landmarks(df, marks) == [
        {"name": "B", "year": 1306, "gid": 1, "x": 2.0, "z": 5.0, "timeline": 1},
        {"name": "A", "year": 1754, "gid": 0, "x": 1.0, "z": -4.1, "timeline": 2}]


def test_config_follows_contract_c5(tmp_path):
    write(tmp_path)
    cfg = json.loads((tmp_path / "stockholm.json").read_text())
    assert set(cfg) == {"city", "name", "subtitle", "version", "tileSize", "origin", "crs", "home", "periods",
                        "yearMin", "yearMax", "histogram", "histogramEst", "unknown", "attrStride", "tiles",
                        "packs", "stats", "features", "attribution", "accuracy", "terrain", "links", "landmarks",
                        "districts", "langFromBrowser", "about", "accuracyLabels"}
    # About's own numbers, counted over what ships, and who made the map
    assert cfg["about"] == {"privateCategory": 4, "privateDated": 3, "ratings": [2, 1, 1], "protected": 2,
                            "withArchitect": 2, "addressed": 4, "gamla": {"n": 5, "dated": 3},
                            "fewestPrivateYears": 4, "lateYear": 2008, "nearM": 100, "rareArchitect": 3,
                            "snapshot": "2023-01",
                            "maker": city.MAKER, "contact": city.CONTACT, "privateAddresses": city.PRIVATE_ADDRESSES}
    assert cfg["accuracyLabels"]["sv"]["groups"]["house"] == "Småhus (villor, rad- och kedjehus)"
    assert cfg["accuracyLabels"]["en"]["groups"] == city.GROUP_LABELS
    assert cfg["langFromBrowser"] is city.LANG_FROM_BROWSER
    assert cfg["links"] == city.LINKS
    # the palace (gid 1, curated 1754) is the one placed timeline landmark of the tiny city
    assert cfg["landmarks"] == [{"name": "Kungliga slottet", "year": 1754, "gid": 1, "x": 120.0, "z": 220.0,
                                 "timeline": 1}]
    assert (cfg["city"], cfg["name"], cfg["version"], cfg["crs"]) == ("stockholm", "Hus för hus", VERSION, 3011)
    assert cfg["subtitle"] == city.SUBTITLE and cfg["home"] == city.HOME and cfg["features"] == city.FEATURES
    assert cfg["origin"] == list(city.ORIGIN) and cfg["tileSize"] == city.TILE and cfg["attrStride"] == 24
    assert cfg["periods"][0] == {"key": "p1", "label": "Medieval & early Vasa",
                                 "label_sv": "Medeltid och äldre vasatid", "from": 1000, "to": 1610,
                                 "color": "#8ed3d0"}  # Ärg p1, the default look
    assert len(cfg["periods"]) == len(city.PERIODS)
    assert set(cfg["tiles"][0]) == {"file", "tx", "tz", "n", "bytes", "dist", "pack", "offset", "length"}

    def one(year):
        v = [0] * len(city.PERIODS)
        v[city.period_index(year)] = 1
        return v

    # EXACT/RANGE/LONG by year: the private EXACT house (gid 4, 1960s) sits at 1960 + 7 with its p10 colour, and
    # the Wikidata year (gid 10) is a known year like RAÄ's
    assert cfg["histogram"] == {"1625": one(1625), "1630": one(1630), "1647": one(1647), "1754": one(1754),
                                "1929": one(1929), "1967": one(1968)}
    # AREA/ESTIMATE/PERIOD: the private area-dated colony cottage (gid 6, 1930s) at 1930 + 0, the estimate (gid 8)
    # at its year, the private period-only house (gid 9, 1930s) at 1930 + 6 with its p8 colour
    assert cfg["histogramEst"] == {"1930": one(1936), "1936": one(1936), "1952": one(1952)} and cfg["unknown"] == 2
    assert (cfg["yearMin"], cfg["yearMax"]) == (1625, 1967)
    assert cfg["stats"] == {
        "buildings": 11,
        "byFlag": {"exact": 4, "range": 1, "long": 1, "area": 1, "estimate": 1, "period": 1, "unknown": 2},
        "bySrc": {"none": 2, "curated": 1, "raa": 4, "raa_area": 1, "wikidata": 1, "estimate": 2, "raa_old": 0, "osm": 0},
        "floorsOsm": 0, "floorsHeight": 11, "privateHouses": 3,
        "photos": 1, "extracts": {"sv": 2, "en": 1},
    }
    assert cfg["accuracy"] == ACCURACY
    # The grid as s02_terrain built it, and the viewer's defaults from city.TERRAIN
    assert cfg["terrain"] == {"file": "terrain.bin.gz", "source": "contours", "x0": -40.0, "z0": -40.0, "cell": 20.0,
                              "nx": 6, "nz": 5, "waterZ": 0.0, "datum": -0.1, "fixed": 0, "relief": 1.0,
                              "reliefMax": 2.5, "fadeM": 400.0, "terrace": "full", "chunk": 2400.0}
    assert cfg["attribution"] == [{"id": "test-src", "text": "Test data (CC0)", "url": "https://example.org/data",
                                   "licence": "CC0-1.0",
                                   "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                                   "credit": {"en": "Test data: Test, CC0", "sv": "Test data: Test, CC0"}}]   # the standard credit line
    assert json.loads((tmp_path / "layers.json").read_text()) == []


def test_two_runs_write_identical_bytes(tmp_path):
    write(tmp_path / "a")
    write(tmp_path / "b")
    files = sorted(p.relative_to(tmp_path / "a") for p in (tmp_path / "a").rglob("*") if p.is_file())
    n_packs = len(json.loads((tmp_path / "a" / "stockholm.json").read_text())["packs"])
    # packs, attrs, 64 card shards, 64 excerpt shards, photos.json, layers.json, stockholm.json
    assert len(files) == n_packs + 1 + 64 + 64 + 5                 # districts.bin.gz, photo-gids.json
    for f in files:
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f


def test_main_writes_version_dir_and_current_json(tmp_path, monkeypatch):
    write_data(tmp_path / "data")
    monkeypatch.chdir(tmp_path)
    s03_tiles.main(["--version", "v20990101"])
    out = tmp_path / "web" / "data" / "v20990101"
    assert (out / "stockholm.json").exists() and (out / "attrs.bin.gz").exists() and (out / "pack0.bin.gz").exists()
    assert json.loads((tmp_path / "web" / "data" / "current.json").read_text()) == {"version": "v20990101"}
    assert s03_tiles.out_dir() == s03_tiles.CURRENT.parent / "v20990101"
    s03_tiles.main(["--version", "v20990101-t1200", "--tile", "1200"])  # a side build for the tile-size comparison
    side = json.loads((tmp_path / "web" / "data" / "v20990101-t1200" / "stockholm.json").read_text())
    assert (side["version"], side["tileSize"]) == ("v20990101-t1200", 1200.0)
    assert s03_tiles.out_dir() == s03_tiles.CURRENT.parent / "v20990101-t1200"


def test_ground_parquet_replaces_ground_height_and_floors():
    # S02_terrain settles each building's ground on the terrain (a MARK_Z on a 1 km sheet line is replaced,
    # its height and floors follow); s03 ships those, not buildings.parquet's
    b, y, a = tiny_city()
    g = ground_rows(b, a)
    g.loc[7, ["ground", "height", "floors"]] = [52.0, 21.6, 6]
    df = s03_tiles.join(b, y, a, g)
    assert (df.ground[7], df.height[7], df.floors[7]) == (52.0, pytest.approx(21.6), 6)
    assert df.ground[3] == pytest.approx(0.3)                      # drawn at the floor, never under the water
    assert df.height[3] == pytest.approx(12.5) and df.floors[3] == 3
    with pytest.raises(ValueError, match="ground"):
        s03_tiles.join(b, y, a, g.iloc[:-1])


def test_load_needs_s02_terrain(tmp_path):
    write_data(tmp_path)
    (tmp_path / "ground.parquet").rename(tmp_path / "ground.parquet.aside")
    with pytest.raises(SystemExit, match="ground.parquet is missing: run s02_terrain"):
        s03_tiles.load(tmp_path)
    (tmp_path / "ground.parquet.aside").rename(tmp_path / "ground.parquet")
    (tmp_path / "terrain.json").rename(tmp_path / "terrain.json.aside")
    with pytest.raises(SystemExit, match="terrain.json is missing: run s02_terrain"):
        s03_tiles.load(tmp_path)


def test_load_refuses_a_terrain_built_for_other_buildings(tmp_path):
    # s01_load ran again after s02_terrain: the grounds, heights, floors and cuts belong to other buildings
    write_data(tmp_path)
    df = s03_tiles.load(tmp_path)
    # load ships ground.parquet's grounds: gid 3's MARK_Z of -1.1 m is drawn at the 0.3 m floor
    assert len(df) == len(tiny_city()[0]) and df.ground[3] == pytest.approx(0.3)
    record = json.loads((tmp_path / "terrain.json").read_text())
    (tmp_path / "terrain.json").write_text(json.dumps({**record, "buildings_sha256": "0" * 64}))
    with pytest.raises(SystemExit, match="built from another .*buildings.parquet: run s02_terrain again"):
        s03_tiles.load(tmp_path)


def test_load_refuses_a_terrain_built_from_other_attributes(tmp_path):
    # The final review's PIPELINE-5: ground.parquet carries the floors s02_attributes gave (s03_tiles ships them), so
    # s02_attributes run again without s02_terrain would ship the old floors. terrain.json records attributes.parquet's
    # sha256 too, and a record without it (an older s02_terrain) is refused as well.
    write_data(tmp_path)
    record = json.loads((tmp_path / "terrain.json").read_text())
    assert len(record["attributes_sha256"]) == 64
    a = pd.read_parquet(tmp_path / "attributes.parquet")
    a.assign(floors=a.floors + 1).to_parquet(tmp_path / "attributes.parquet")       # s02_attributes ran again
    with pytest.raises(SystemExit, match="built from another .*attributes.parquet: run s02_terrain again"):
        s03_tiles.load(tmp_path)
    del record["attributes_sha256"]
    (tmp_path / "terrain.json").write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="attributes.parquet: run s02_terrain again"):
        s03_tiles.check_built_from(record, tmp_path)


def test_lantmateriet_is_credited_only_when_its_terrain_was_used(tmp_path):
    lm = dict(SOURCES[0], id="lm_markhojd", attribution="Markhöjdmodell Nedladdning")
    ids = lambda kind: [a["id"] for a in s03_tiles.attribution(SOURCES + [lm], kind)]   # noqa: E731
    assert ids("dtm") == ["test-src", "lm_markhojd"]
    assert ids("contours") == ["test-src"]
    # and stockholm.json follows the record's source: a contour build never credits Lantmäteriet's model
    b, y, a = tiny_city()
    for kind in ("contours", "dtm"):
        s03_tiles.write_outputs(s03_tiles.join(b, y, a, ground_rows(b, a)), tmp_path / kind, VERSION,
                                sources=SOURCES + [lm], accuracy=ACCURACY, terrain={**TERRAIN, "source": kind},
                                wiki=s03_tiles.no_wiki(), landmarks=[],
                                places=s03_tiles.no_places())                # no card content needed here
        cfg = json.loads((tmp_path / kind / "stockholm.json").read_text())
        assert ([c["id"] for c in cfg["attribution"]], cfg["terrain"]["source"]) == (ids(kind), kind)


def test_attribution_carries_the_corner_credit_where_a_source_has_one():
    src = dict(SOURCES[0], corner={"en": "© Test", "sv": "© Test"})
    assert s03_tiles.attribution([src, SOURCES[0]]) == [
        {"id": "test-src", "text": "Test data (CC0)", "url": "https://example.org/data", "licence": "CC0-1.0",
         "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/", "corner": {"en": "© Test", "sv": "© Test"},
         "credit": {"en": "Test data: Test, CC0", "sv": "Test data: Test, CC0"}},
        {"id": "test-src", "text": "Test data (CC0)", "url": "https://example.org/data", "licence": "CC0-1.0",
         "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
         "credit": {"en": "Test data: Test, CC0", "sv": "Test data: Test, CC0"}}]


def test_attribution_credits_each_source_in_the_d44_form():
    # The standard credit line (2026-10-16): "Dataset: publisher, licence", plus ", processed" / ", bearbetad" where the map changes the
    # data (CC0 included); a source's own words stand in the publisher's place; the City's lines are its own
    lines = {a["id"]: (a["credit"]["en"], a["credit"]["sv"])
             for a in s03_tiles.attribution(load_sources(), terrain_source="dtm")}
    both = lambda line: (f"{line}, processed", f"{line}, bearbetad")   # noqa: E731
    assert lines == {
        "city_lod1": both("SBK 3D-Byggnader (LOD1) generaliserade: © Stockholms stad, Stadsbyggnadskontoret, CC BY"),
        "city_stadsdelar": both("Stadsdelar: © Stockholms stad, Stadsbyggnadskontoret, CC BY"),
        "city_stadskarta": both("Stadskarta: © Stockholms stad, Stadsbyggnadskontoret, CC BY"),
        "raa_bebyggelse": both("Bebyggelseregistret: Riksantikvarieämbetet, CC0"),
        "raa_old": both("Bebyggelseregistret, äldre registret: Riksantikvarieämbetet, CC0"),
        "wikidata": ("Wikidata: Wikidata contributors, CC0, processed", "Wikidata: Wikidatas bidragsgivare, CC0, bearbetad"),
        "osm": ("OpenStreetMap: © OpenStreetMap contributors, ODbL, processed",
                "OpenStreetMap: © OpenStreetMap-bidragsgivare, ODbL, bearbetad"),
        "lm_markhojd": both("Markhöjdmodell Nedladdning: © Lantmäteriet, CC BY 4.0"),
        "wikipedia": ("Wikipedia: Wikipedia contributors, CC BY-SA 4.0, processed",
                      "Wikipedia: Wikipedias bidragsgivare, CC BY-SA 4.0, bearbetad")}
    # an unmodified source has no "processed"
    assert s03_tiles.attribution(SOURCES)[0]["credit"] == {"en": "Test data: Test, CC0", "sv": "Test data: Test, CC0"}


def test_photo_gids_lists_the_cards_with_a_photo(tmp_path):
    # the photo filter (web/photos.js): the gids whose card shows a photo, sorted, nothing else
    write(tmp_path)
    assert json.loads((tmp_path / "photo-gids.json").read_text()) == [1]
    cards = [{"1": {"photo": {"key": "a"}}, "65": {"name": "x"}}, {"2": {"photo": {"key": "b"}}}]
    assert s03_tiles.photo_gids(cards) == [1, 2]
