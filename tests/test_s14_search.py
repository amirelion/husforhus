"""The search index: built from the version's own cards and s02_addresses, on the tiny city."""
import json

import pandas as pd
import pytest

from pipeline import city, s03_tiles, s14_search
from tests.test_s03_tiles import PLACES, write as write_version
from tests.tinycity import tiny_city


@pytest.fixture
def built(tmp_path):
    write_version(tmp_path)
    b, y, a = tiny_city()
    df = s03_tiles.join(b, y, a)
    return tmp_path, df, s14_search.read_cards(tmp_path)


def test_index_holds_districts_streets_and_the_cards_names(built):
    out, df, cards = built
    index, shards = s14_search.build(df, cards, PLACES)
    names = [d[0] for d in index["districts"]]
    assert names == ["Gamla stan", "Grimsta", "Ladugårdsgärdet", "Riddarholmen", "Södermalm"]   # display names, sorted
    gamla = index["districts"][0]
    assert gamla[1] == 5 and gamla[2][0] <= df.x[0] <= gamla[2][2]                    # buildings, local bounds
    assert ["Gärdet", [2]] in index["aliases"] and ["Old Town", [0]] in index["aliases"]
    assert not any(a[0] == "Vasastan" for a in index["aliases"])          # no Vasastaden in the tiny city: dropped
    assert index["streets"] == [["Grimstagatan", 1, [1], "g"], ["Hornsgatan", 1, [4], "h"],
                                ["Slottsbacken", 1, [0], "s"], ["Västerlånggatan", 1, [0], "v"]]
    assert shards["h"] == {"Hornsgatan": [["30", 3, 4], ["32", 3, 4]]}                 # number, gid, stadsdel
    # names only from the cards: the palace's RAÄ name, the tower with its English label; a private house none
    assert index["buildings"] == [["Tyska kyrkan", 0, 0, ""], ["Kungliga slottet", 1, 0, "Stockholm Palace"],
                                  ["Kaknästornet", 7, 2, "Kaknäs Tower"], ["Schönfeldtska huset", 10, 0, ""]]
    assert index["outside"] == list(city.OUTSIDE) and index["settings"]["max_rows"] == 8
    assert index["addressed"] == 4                                        # gids 1, 3, 4 and 10


def test_other_names_point_at_the_one_card_that_carries_their_target(built, monkeypatch):
    # city.BUILDING_ALIASES: the names people type ("Slottet", "Royal Palace"), each finding a building only through
    # a name its card already carries; a target no card (or more than one) carries is left out
    out, df, cards = built
    monkeypatch.setattr(city, "BUILDING_ALIASES", {"Slottet": "Kungliga slottet", "Royal Palace": "Kungliga slottet",
                                                   "TV-tornet": "Kaknästornet", "Nowhere": "Stockholms slott"})
    index, _ = s14_search.build(df, cards, PLACES)
    assert index["baliases"] == [["Royal Palace", 1], ["Slottet", 1], ["TV-tornet", 7]]
    assert s14_search.resolves("Royal Palace", index, {}) and not s14_search.resolves("Nowhere", index, {})


def test_examples_are_only_the_ones_that_resolve(built, monkeypatch):
    out, df, cards = built
    monkeypatch.setitem(city.SEARCH, "examples", ("Hornsgatan 30", "Hornsgatan 31", "Kungliga slottet", "Old Town",
                                                 "Vällingby", "hornsgatan 32"))
    index, _ = s14_search.build(df, cards, PLACES)
    assert index["examples"] == ["Hornsgatan 30", "Kungliga slottet", "Old Town", "hornsgatan 32"]


def test_a_private_house_address_follows_decision_3(built, monkeypatch):
    out, df, cards = built
    _, shards = s14_search.build(df, cards, PLACES)
    assert shards["g"] == {"Grimstagatan": [["5", 4, 1]]}                     # gid 4: a private house, shown for now
    monkeypatch.setattr(city, "PRIVATE_ADDRESSES", False)                   # if the answer is no
    index, shards = s14_search.build(df, cards, PLACES)
    assert "g" not in shards and "Grimstagatan" not in [s[0] for s in index["streets"]] and index["addressed"] == 3


def test_a_private_house_address_goes_from_its_neighbour_too(built, monkeypatch):
    # final review F1: the house's address also landed on gid 3 (an entrance node nearest the next footprint)
    out, df, cards = built
    places = dict(PLACES, addresses=pd.concat([PLACES["addresses"], pd.DataFrame(
        {"gid": pd.array([3], dtype="int32"), "street": ["Grimstagatan"], "number": ["5"]})], ignore_index=True))
    monkeypatch.setattr(city, "PRIVATE_ADDRESSES", False)
    index, shards = s14_search.build(df, cards, places)
    assert "g" not in shards and index["addressed"] == 3
    card = s03_tiles.with_places(df, places).set_index("gid")
    assert (card.addr[3], card.addrn[3]) == ("Hornsgatan 30", 2)         # gid 3 keeps only its own two


def test_a_withheld_address_is_in_no_shard(built):
    out, df, cards = built
    places = dict(PLACES, addresses=PLACES["addresses"].assign(withheld=lambda a: a.street == "Hornsgatan"))
    index, shards = s14_search.build(df, cards, places)
    assert "h" not in shards and index["addressed"] == 3
    assert s03_tiles.with_places(df, places).set_index("gid").addr[3] == ""


def test_shard_key_folds_the_first_letter():
    assert [s14_search.shard_key(s) for s in ("Hornsgatan", "Åsögatan", "S:t Eriksgatan", "1:a Långgatan", "´Ö")] == \
        ["h", "a", "s", "1", "o"]


def test_main_writes_search_into_the_version(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    from tests.tinycity import write_data
    write_data(tmp_path / "data")
    out = tmp_path / "web" / "data" / "v20261016"
    write_version(out)
    (out / "search" / "addr").mkdir(parents=True)
    (out / "search" / "addr" / "q.json").write_text("{}")                  # a stale shard from an earlier run goes ...
    s14_search.main(["--version", "v20261016"])
    assert sorted(p.name for p in (out / "search" / "addr").iterdir()) == ["g.json", "h.json", "s.json", "v.json"]
    assert (tmp_path / "temp_trash" / "v20261016" / "search" / "addr" / "q.json").exists()   # ... to temp_trash
    index = json.loads((out / "search" / "index.json").read_text())
    assert len(index["streets"]) == 4 and index["v"] == 1
    assert "search: 4 streets, 5 addresses in 4 shards, 4 named buildings" in capsys.readouterr().out


def test_main_needs_the_cards(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "web" / "data" / "v20261016").mkdir(parents=True)
    with pytest.raises(SystemExit, match="run s03_tiles first"):
        s14_search.main(["--version", "v20261016"])


@pytest.mark.network
def test_the_names_people_type_find_their_building_in_the_real_build():
    # r4-ux-copy.md §3.2: the first searches on a map that opens on the palace and City Hall. Runs on the version
    # web/data/current.json names once the city is built (s14_search), and says so otherwise.
    if not s03_tiles.CURRENT.exists():
        pytest.skip(f"{s03_tiles.CURRENT} is missing: build the city")
    out = s03_tiles.CURRENT.parent / json.loads(s03_tiles.CURRENT.read_text())["version"]
    if not (out / "search" / "index.json").exists():
        pytest.skip(f"{out} has no search index: run s14_search")
    index = json.loads((out / "search" / "index.json").read_text())
    if index["addressed"] < 40_000:
        pytest.skip(f"{out} is not the whole city")
    for name in ("Stadshuset", "City Hall", "Kungliga slottet", "Slottet", "Royal Palace", "Riksdagen", "Operan",
                 "Vasamuseet", "Avicii Arena", "Engelbrektskyrkan", "Söder", "Gamla stan", "Vällingby"):
        assert s14_search.resolves(name, index, {}), name
    assert len(index["baliases"]) >= len(city.BUILDING_ALIASES) - 3          # a renamed card loses at most a few



def test_resolves_without_the_shard_and_with_a_name_that_ends_in_a_number():
    # A street whose shard is not at hand does not resolve (no KeyError), and a building whose name
    # ends in a number is still found by its name
    index = {"streets": [["Hornsgatan", 1, [0], "h"]], "buildings": [["Kvarteret Hus 7", 0, 0, ""]],
             "districts": [], "aliases": []}
    assert not s14_search.resolves("Hornsgatan 30", index, {})
    assert s14_search.resolves("Kvarteret Hus 7", index, {})
    assert s14_search.resolves("Hornsgatan 30", index, {"h": {"Hornsgatan": [["30", 0, 0]]}})


def test_a_shard_trashed_twice_keeps_both_copies(tmp_path):
    # never delete: a second stale q.json under the same version must not overwrite the first one in temp_trash
    out, trash = tmp_path / "web" / "data" / "v1", tmp_path / "temp_trash"
    for text in ('{"first": []}', '{"second": []}'):
        (out / "search" / "addr").mkdir(parents=True, exist_ok=True)
        (out / "search" / "addr" / "q.json").write_text(text)
        s14_search.write(out, {"v": 1}, {}, trash=trash)
    kept = sorted(p.read_text() for p in (trash / "v1" / "search" / "addr").iterdir())
    assert kept == ['{"first": []}', '{"second": []}']


def test_a_street_spelt_in_two_cases_is_one_street(built):
    # final review F3: OSM writes some streets as both "... Väg" and "... väg"; one row, one spelling (the most
    # common, on a tie the first sorted), so no false "isn't in our list" from the other half
    out, df, cards = built
    extra = pd.DataFrame({"gid": pd.array([3, 5, 5], dtype="int32"), "street": ["hornsgatan"] * 3,
                          "number": ["34", "36", "38"]})
    places = dict(PLACES, addresses=pd.concat([PLACES["addresses"], extra], ignore_index=True))
    index, shards = s14_search.build(df, cards, places)
    assert [s[0] for s in index["streets"] if s[0].casefold() == "hornsgatan"] == ["hornsgatan"]
    assert [p[0] for p in shards["h"]["hornsgatan"]] == ["30", "32", "34", "36", "38"]
    tie = pd.DataFrame({"gid": pd.array([4], dtype="int32"), "street": ["grimstagatan"], "number": ["7"]})
    places = dict(PLACES, addresses=pd.concat([PLACES["addresses"], tie], ignore_index=True))
    _, shards = s14_search.build(df, cards, places)
    assert shards["g"] == {"Grimstagatan": [["5", 4, 1], ["7", 4, 1]]}
    # diacritics are another street: Vasterlanggatan stays apart from Västerlånggatan
    other = pd.DataFrame({"gid": pd.array([10], dtype="int32"), "street": ["Vasterlanggatan"], "number": ["1"]})
    index, _ = s14_search.build(df, cards, dict(PLACES, addresses=pd.concat([PLACES["addresses"], other])))
    assert {"Vasterlanggatan", "Västerlånggatan"} <= {s[0] for s in index["streets"]}


def test_occupants_are_listed_only_for_buildings_a_card_names_and_carries(built):
    # Börshuset (its card carries Q404416) holds the Nobel Prize Museum; an item on no card, a card without an item
    # and an occupant that is the building itself under its own name add nothing
    out, df, cards = built
    cards = {**cards, 0: {**cards[0], "name": "Börshuset", "en": "Stock Exchange Building", "qid": "Q404416"}}
    occ = {"Q404416": [{"qid": "Q1144549", "sv": "Nobelprismuseet", "en": "Nobel Prize Museum", "alt": ["Nobelmuseet"]},
                       {"qid": "Q9", "sv": "Börshuset", "en": "Börshuset", "alt": []}],
           "Q999": [{"qid": "Q8", "sv": "Ingenstans", "en": "Nowhere", "alt": []}]}
    index, _ = s14_search.build(df, cards, PLACES, occ)
    assert index["occupants"] == [["Nobelprismuseet", "Nobel Prize Museum", 0, ["Nobelmuseet"], 0]]   # in Gamla stan
    assert s14_search.build(df, cards, PLACES)[0]["occupants"] == []


HISTORISKA = {"qid": "Q1726607", "sv": "Historiska museet", "en": "Swedish History Museum",
              "alt": ["Statens historiska museum"]}


def test_a_hand_checked_occupant_needs_no_card_and_carries_its_stadsdel(built):
    # pipeline/occupant_pins.csv by footprint: gid 2 is a made-up footprint whose card has neither a name nor an item,
    # yet search finds the museum there, in Riddarholmen (stadsdel 3)
    out, df, cards = built
    index, _ = s14_search.build(df, cards, PLACES, {}, {2: [HISTORISKA]})
    assert index["occupants"] == [["Historiska museet", "Swedish History Museum", 2, ["Statens historiska museum"], 3]]
    assert s14_search.build(df, cards, PLACES, {}, {2: [HISTORISKA]}, hidden={2})[0]["occupants"] == []  # a takedown


def test_the_hand_check_wins_over_wikidata_and_an_unnamed_carded_house_keeps_its_occupants(built):
    out, df, cards = built
    cards = {**cards, 3: {**cards[3], "qid": "Q10585474"}}            # a card with an item but no name (Milon 11)
    occ = {"Q750444": [{"qid": "Q1726607", "sv": "Historiska museet", "en": "Historiska museet", "alt": []},
                       {"qid": "Q10671642", "sv": "Slottskyrkan", "en": "Royal Chapel", "alt": []}],
           "Q10585474": [{"qid": "Q1439258", "sv": "Forum för levande historia", "en": "Living History Forum",
                          "alt": []}]}
    pinned = {2: [HISTORISKA], 1: [{"qid": "", "sv": "Slottskyrkan", "en": "Royal Chapel", "alt": []}]}
    index, _ = s14_search.build(df, cards, PLACES, occ, pinned)
    assert [(o[0], o[2]) for o in index["occupants"]] == [
        ("Slottskyrkan", 1),                       # once: Wikidata's and the table's, the same name on one footprint
        ("Historiska museet", 2),                  # the table's footprint, not where Wikidata put the item
        ("Forum för levande historia", 3)]
