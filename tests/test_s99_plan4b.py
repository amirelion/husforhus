"""s99_validate's Plan 4b rules: the card's address and district (Task 2), the search index (Task 3). The `site`
fixture comes from tests/test_s99_validate.py (the tiny city now has addresses, districts and a search index)."""
import json

import pandas as pd

from pipeline import city, io
from tests.test_s99_validate import check, edit_card, reindex, site
from tests.tinycity import ADDRESSES

__all__ = ["site"]


def cards(site):
    out = {}
    for p in sorted((site / "cards").glob("*.json")):
        out.update(json.loads(p.read_text()))
    return out


def test_a_clean_build_has_addresses_and_districts(site):
    c = cards(site)
    assert c["3"]["addr"] == "Hornsgatan 30" and c["3"]["addrn"] == 2 and "dist" not in c["3"]
    assert check(site) == []


def test_the_district_bytes_match_the_buildings_and_the_names(site):
    io.write_gz(site / "districts.bin.gz", bytes([1, 2, 9]))
    assert check(site) == ["districts: districts.bin.gz has 3 bytes for 11 buildings",
                           "districts: districts.bin.gz names stadsdel 9 of 5"]
    (site / "districts.bin.gz").rename(site / "districts.moved")
    assert check(site) == ["districts: districts.bin.gz is missing (stockholm.json lists districts)"]


def test_a_private_house_address_follows_decision_3(site, monkeypatch):
    # gid 4 is a private house with an address: shown while city.PRIVATE_ADDRESSES says so, a leak if the answer is no
    assert "addr" in cards(site)["4"]
    monkeypatch.setattr(city, "PRIVATE_ADDRESSES", False)
    assert check(site) == ["cards: 04.json gid 4 is in a private-house category and carries `addr` "
                           "(city.PRIVATE_ADDRESSES is False)",
                           "search: addr/g.json street 0 holds the address of gid 4, a private-category house "
                           "(city.PRIVATE_ADDRESSES is False)"]
    edit_card(site, 4, {})                              # edit_card replaces the whole card
    reindex(site)                                       # what s14_search writes then: no address for gid 4
    assert check(site) == []


def test_search_names_only_what_the_cards_name(site):
    index = json.loads((site / "search" / "index.json").read_text())
    assert [b[0] for b in index["buildings"]] == ["Tyska kyrkan", "Kungliga slottet", "Kaknästornet",
                                                  "Schönfeldtska huset"]
    index["buildings"].append(["Villa Andersson", 4, 1, ""])              # a name gid 4's card does not carry
    index["buildings"].append(["Kaknästornet", 7, 2, "Kaknäs TV Tower"])   # an English label its card does not carry
    index["buildings"].append(["X", 99, 0, ""])
    io.write_json(site / "search" / "index.json", index)
    assert check(site) == ["search: building entry 4 (gid 4) carries a name its card does not",
                           "search: building entry 5 (gid 7) carries a name its card does not",
                           "search: building entry 6 is not [name, gid, stadsdel, English label]"]


def test_search_streets_and_addresses_must_add_up(site, monkeypatch):
    index = json.loads((site / "search" / "index.json").read_text())
    index["streets"].append(["Götgatan", 1, [0], "g"])
    io.write_json(site / "search" / "index.json", index)
    io.write_json(site / "search" / "addr" / "h.json", {"Hornsgatan": [["30", 3, 4], ["32", 11, 4]]})
    assert check(site) == ["search: street entry 4 has no numbers in the shard it names",
                           "search: addr/h.json street 0 holds an address on no building"]
    io.write_json(site / "search" / "addr" / "h.json", {"Hornsgatan": [["30", 3, 4], ["32", 3, 4]]})
    index["streets"].pop()
    io.write_json(site / "search" / "index.json", index)
    monkeypatch.setattr(city, "PRIVATE_ADDRESSES", False)                 # gid 4's address is then a leak, twice
    assert check(site) == ["cards: 04.json gid 4 is in a private-house category and carries `addr` "
                           "(city.PRIVATE_ADDRESSES is False)",
                           "search: addr/g.json street 0 holds the address of gid 4, a private-category house "
                           "(city.PRIVATE_ADDRESSES is False)"]
    monkeypatch.setattr(city, "PRIVATE_ADDRESSES", True)
    # a street and a number that together read as a property designation ("Diana 1": the street shares the block's
    # name); the shard keeps them apart, so the privacy scan could not see it
    io.write_json(site / "search" / "addr" / "d.json", {"Diana": [["1", 3, 4]]})
    index["streets"].append(["Diana", 1, [4], "d"])
    io.write_json(site / "search" / "index.json", index)
    assert check(site) == ["search: addr/d.json street 0 holds an address that reads as a property designation"]


def test_other_names_must_be_the_reviewed_ones_for_the_cards_building(site, monkeypatch):
    index = json.loads((site / "search" / "index.json").read_text())
    monkeypatch.setattr(city, "BUILDING_ALIASES", {"Slottet": "Kungliga slottet"})
    index["baliases"] = [["Slottet", 1], ["Slottet", 0], ["Villa Andersson", 4]]
    io.write_json(site / "search" / "index.json", index)
    assert check(site) == [f"search: other-name entry {i} is not one of city.BUILDING_ALIASES for its building's card "
                           "name" for i in (1, 2)]


def test_search_is_required_once_the_feature_is_on(site):
    for p in sorted((site / "search").rglob("*.json")):
        p.rename(p.with_suffix(".moved"))
    cfg = json.loads((site / "stockholm.json").read_text())
    cfg["features"]["search"] = False
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == []                                              # no index is fine while search is off
    cfg["features"]["search"] = True
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["search: search/index.json is missing (run s14_search)"]


def test_a_misshapen_search_index_is_reported_not_raised(site):
    # s99 reports what is wrong with valid JSON of the wrong shape, as it does for cards (Task 3's review)
    index = json.loads((site / "search" / "index.json").read_text())

    def run(edit, shard=None):
        changed = json.loads(json.dumps(index))
        replaced = edit(changed)
        changed = changed if replaced is None else replaced
        io.write_json(site / "search" / "index.json", changed)
        io.write_json(site / "search" / "addr" / "h.json", shard if shard is not None
                      else {"Hornsgatan": [["30", 3, 4], ["32", 3, 4]]})
        return check(site)

    assert run(lambda i: []) == ["search: search/index.json is not an object"]
    assert run(lambda i: i.update(buildings="x")) == ["search: index.json buildings is not a list"]
    assert run(lambda i: i["buildings"].append([["x"], 1, 0, ""])) == \
        ["search: building entry 4 is not [name, gid, stadsdel, English label]"]
    assert run(lambda i: i["buildings"].append(["Kungliga slottet", 1, 0, ["x"]])) == \
        ["search: building entry 4 is not [name, gid, stadsdel, English label]"]
    assert run(lambda i: i.update(baliases=[[["Slottet"], 1]])) == \
        ["search: other-name entry 0 is not one of city.BUILDING_ALIASES for its building's card name"]
    assert run(lambda i: i["streets"].append([["Hornsgatan"], 1, [4], "h"])) == \
        ["search: street entry 4 has no numbers in the shard it names"]
    assert run(lambda i: None, shard=[]) == ["search: addr/h.json is not an object",
                                             "search: street entry 1 has no numbers in the shard it names"]
    assert run(lambda i: None, shard={"Hornsgatan": 5}) == \
        ["search: addr/h.json street 0 is not a list of [number, gid, stadsdel]"]
    assert run(lambda i: None) == []
    edit_card(site, 1, {"name": ["Kungliga slottet"], "en": {"x": 1}})      # a misshapen card: check_cards' to report
    assert not any(e.startswith("search:") and "card does not" not in e for e in check(site))


def test_a_private_house_address_on_its_neighbour_is_a_leak(site, monkeypatch):
    # final review F1: Grimstagatan 5 is gid 4's (a private house); with the switch off it may not show on gid 3 either
    data = site.parents[2] / "data"
    extra = pd.DataFrame({"gid": pd.array([3], dtype="int32"), "street": ["Grimstagatan"], "number": ["5"]})
    pd.concat([ADDRESSES, extra], ignore_index=True).to_parquet(data / "addresses.parquet")
    io.write_json(site / "search" / "addr" / "g.json", {"Grimstagatan": [["5", 3, 4]]})
    assert check(site) == []
    monkeypatch.setattr(city, "PRIVATE_ADDRESSES", False)
    assert ("search: addr/g.json street 0 holds the address of a private-category house (city.PRIVATE_ADDRESSES is "
            "False)") in check(site)
