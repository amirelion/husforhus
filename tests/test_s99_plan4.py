"""s99_validate's card rules: the card's new fields on private houses, the rare-architect rule, photos,
excerpt shards, timeline landmarks and designations inside sentences. The `site` fixture comes from
tests/test_s99_validate.py (the tiny city now has a photo, excerpts and a timeline landmark)."""
import json

import geopandas as gpd
import pandas as pd
import pytest
from pyproj import Transformer

from pipeline import city, codes, io, s99_validate
from tests.test_s99_validate import check, edit_attrs, edit_card, reindex, site
from tests.tinycity import PHOTO_KEY, WIKI

__all__ = ["site"]
PHOTO = dict(WIKI["photos"][PHOTO_KEY])


def test_clean_build_with_plan4_fields_passes(site):
    cards = {}
    for p in sorted((site / "cards").glob("*.json")):
        cards.update(json.loads(p.read_text()))
    assert cards["1"]["photo"]["key"] == PHOTO_KEY and cards["0"]["prot"] == 3
    assert check(site) == []


@pytest.mark.parametrize("field", ["qid", "wp", "photo", "en"])
def test_nothing_that_states_the_year_on_a_private_house(site, field):
    # Gid 4 is a private house; gid 5 an undated Enbostadshus (same rule, from KATEGORI)
    value = {"qid": "Q1", "wp": ["sv"], "photo": PHOTO, "en": "Villa"}[field]
    edit_card(site, 4, {field: value})
    edit_card(site, 5, {field: value})
    assert check(site) == [f"cards: 04.json gid 4 is in a private-house category and carries `{field}`",
                           f"cards: 05.json gid 5 is in a private-house category and carries `{field}`"]


def test_a_private_house_name_must_be_on_the_reviewed_list(site, monkeypatch):
    edit_card(site, 4, {"name": "Villa Andersson"})
    assert check(site) == ["cards: 04.json gid 4 is in a private-house category and carries a name not on the "
                           "reviewed list"]
    monkeypatch.setattr(s99_validate, "load_private_names", lambda: {"Villa Andersson"})
    assert check(site) == []


def test_a_rare_architect_on_a_private_house_fails_and_a_reviewed_firm_or_a_common_name_passes(site, monkeypatch):
    # "Ruth Rare" on 1 card is a person's name a private house may not show; a rare firm shows only from the
    # reviewed list (a name that merely reads as a firm could be a person's); a name on 4 cards (more than
    # city.ARCHITECT_MAX_RARE) shows
    edit_card(site, 4, {"architects": ["Ruth Rare", "Byggare & Son AB", "Carl Common"]})
    for g in (2, 3, 8):
        edit_card(site, g, {"architects": ["Carl Common"]})
    assert check(site) == [f"cards: 04.json gid 4 is in a private-house category and names 2 architect(s) found on "
                           f"{city.ARCHITECT_MAX_RARE} cards or fewer"]
    monkeypatch.setattr(s99_validate, "load_private_firms", lambda: {"Byggare & Son AB"})
    assert check(site) == [f"cards: 04.json gid 4 is in a private-house category and names 1 architect(s) found on "
                           f"{city.ARCHITECT_MAX_RARE} cards or fewer"]
    edit_card(site, 2, {"architects": ["Carl Common", "Ruth Rare"]})
    edit_card(site, 3, {"architects": ["Ruth Rare", "Carl Common"]})
    edit_card(site, 8, {"architects": ["Ruth Rare", "Carl Common"]})
    assert check(site) == []                       # now on 4 cards: no longer rare


def test_a_public_domain_photo_from_sweden_passes(site):
    edit_card(site, 1, {"name": "Kungliga slottet", "qid": "Q750444", "wp": ["sv", "en"],
                        "photo": {**PHOTO, "lic": "Public domain (Sweden)"}})
    reindex(site)                                       # the card no longer has its English label
    assert check(site) == []


@pytest.mark.parametrize(("change", "message"), [
    ({"lic": "CC BY-NC-SA 4.0"}, "whose licence is not CC BY, CC BY-SA, CC0 or public domain"),
    ({"by": " "}, "without its author"),
    ({"page": "https://commons.wikimedia.org/wiki/File:Styckjunkaren_7.jpg"}, "without its Commons page"),
    ({"lic": "CC BY-SA 3.0"}, "has a CC BY-SA 3.0 photo without its title"),
    ({"key": "fedcba9876543210-500.jpg"}, "names a photo that is not in data/photos"),
    ({"thumb": "https://upload.wikimedia.org/x.jpg"}, "has photo fields outside a card's: ['thumb']"),
])
def test_a_photo_needs_its_credit_and_its_file(site, change, message):
    edit_card(site, 1, {"name": "Kungliga slottet", "qid": "Q750444", "wp": ["sv", "en"], "photo": {**PHOTO, **change}})
    errors = check(site)
    assert any(e.startswith("cards: 01.json gid 1 ") and e.endswith(message) for e in errors), errors


def test_a_photo_over_the_size_cap_or_missing_from_photos_json_fails(site, monkeypatch):
    monkeypatch.setitem(city.WIKI, "photo_bytes", 5)
    assert check(site) == ["cards: 01.json gid 1 names a photo over 5 bytes"]
    monkeypatch.setitem(city.WIKI, "photo_bytes", 400_000)
    io.write_json(site / "photos.json", [])
    assert check(site) == ["cards: 01.json gid 1 names a photo photos.json does not list"]


def test_an_excerpt_shard_carries_its_licence_and_only_what_the_card_links(site):
    path = site / "wiki" / "01.json"
    shard = json.loads(path.read_text())
    io.write_json(path, {"items": shard["items"]})
    assert check(site) == ["wiki: 01.json is not {licence: CC BY-SA 4.0, items} (the excerpts' licence, §6.1)"]
    shard["items"]["1"]["de"] = {"t": "Das Schloss.", "r": 5}        # gid 1's card links sv and en only
    shard["items"]["65"] = {"sv": {"t": "", "r": 0}}                 # gid 65 is beyond the city
    io.write_json(path, shard)
    assert check(site) == ["wiki: 01.json gid 1 has an excerpt in a language its card does not link",
                           "wiki: 01.json holds 65, which is not a gid of this shard"]


def test_an_excerpt_on_a_private_house_fails(site):
    io.write_json(site / "wiki" / "04.json", {"licence": "CC BY-SA 4.0", "items": {"4": {"sv": {"t": "Villan.", "r": 9}}}})
    assert check(site) == ["wiki: 04.json gid 4 is in a private-house category and carries an excerpt",
                           "wiki: 04.json gid 4 has an excerpt in a language its card does not link"]


def test_an_excerpt_that_names_an_owner_or_a_byggherre_fails(site):
    # No owner or byggherre names in web data (s06_wiki's cut leaves such sentences out; s99 checks it)
    shard = json.loads((site / "wiki" / "01.json").read_text())
    shard["items"]["1"]["sv"]["t"] = "Slottet ägs av staten och förvaltas av Statens fastighetsverk."
    shard["items"]["1"]["en"]["t"] = "The palace was built for King Frederick I."
    io.write_json(site / "wiki" / "01.json", shard)
    assert check(site) == ["wiki: 01.json gid 1 has an excerpt that says who owns the building or had it built"] * 2


@pytest.mark.parametrize("text", ["Fastighetsägaren är AB Exempel.", "Huset samägs av X och Y.",
                                  "Villan disponeras av familjen X."])
def test_an_excerpt_with_an_owner_in_a_compound_fails(site, text):
    # Such sentences shipped in the build of 2026-10-17 and s99 passed them
    shard = json.loads((site / "wiki" / "01.json").read_text())
    shard["items"]["1"]["sv"]["t"] = f"Slottet är stort. {text}"
    io.write_json(site / "wiki" / "01.json", shard)
    assert check(site) == ["wiki: 01.json gid 1 has an excerpt that says who owns the building or had it built"]


def test_an_item_beside_a_private_house_on_its_property_fails(site):
    # Gid 8's item stands 2 m from gid 9, an uncurated Enbostadshus, once both
    # are on one property; the photo or article may show the house
    data = site.parents[2] / "data"
    lon, lat = Transformer.from_crs(city.CRS, 4326, always_xy=True).transform(city.ORIGIN[0] + 58, city.ORIGIN[1] - 5)
    table = WIKI["table"].assign(lon=[18.07, 18.1, 18.05], lat=[59.33, 59.34, 59.32])
    table = pd.concat([table, table.iloc[[2]].assign(gid=8, qid="Q9", name="", lon=lon, lat=lat)], ignore_index=True)
    table.to_parquet(data / "wiki.parquet")
    edit_card(site, 8, {"qid": "Q9"})
    assert check(site) == []                           # another property: gid 8 is DIANA 2, gid 9 GRIMSTA 1:3
    b = gpd.read_parquet(data / "buildings.parquet")
    b.loc[b.gid == 8, "fastighet"] = "GRIMSTA 1:3"
    b.to_parquet(data / "buildings.parquet")
    errors = check(site)
    assert "cards: gid 8 carries an item within 5 m of a private house on its property" in errors
    edit_card(site, 8, {"en": "The shed"})              # the item's English label alone is the item too
    assert "cards: gid 8 carries an item within 5 m of a private house on its property" in check(site)


def test_floors_credited_to_openstreetmap_are_openstreetmaps(site):
    # A repaired ground's floors were recomputed from its height while the card still
    # said "(OpenStreetMap)"; data/attributes.parquet's floors_osm is what OpenStreetMap gives (0 for gid 0 here)
    edit_attrs(site, lambda a: a["fsrc"].__setitem__(0, codes.FLOORS_OSM))
    assert check(site) == ["attrs: 1 buildings whose floors are credited to OpenStreetMap but differ from its "
                           "building:levels (gids 0)"]


def test_a_timeline_landmark_is_a_curated_year(site):
    cfg = json.loads((site / "stockholm.json").read_text())
    cfg["landmarks"].append({"name": "Tyska kyrkan", "year": 1647, "gid": 0, "x": 5, "z": 5, "timeline": 2})
    cfg["landmarks"].append({"name": "Nowhere", "year": 1900, "gid": 99, "x": 0, "z": 0, "timeline": 2})
    io.write_json(site / "stockholm.json", cfg)
    assert check(site) == ["landmarks: entry 1 is not the curated year of gid 0", "landmarks: entry 2 names no building"]


def test_the_timeline_never_shows_a_private_house(site):
    edit_attrs(site, lambda a: a["private"].__setitem__(1, 1))
    errors = check(site)
    assert "landmarks: entry 0 is a private-category house" in errors


def test_a_designation_inside_a_sentence_is_a_leak(site):
    # Wikipedia names buildings after their property ("Diana 1 är en …"); s06_wiki leaves such sentences out
    shard = json.loads((site / "wiki" / "01.json").read_text())
    shard["items"]["1"]["sv"]["t"] = "Huset i kvarteret Diana 1 byggdes 1754."
    io.write_json(site / "wiki" / "01.json", shard)
    assert check(site) == ["privacy: wiki/01.json $.items.1.sv.t holds a property designation (FASTIGHET)"]


def test_normalise_keeps_a_name_that_starts_with_kv():
    assert s99_validate.normalise("Kv. Diana 1") == s99_validate.normalise("kvarteret Diana 1") == "diana 1"
    assert s99_validate.normalise("Kvarnen 3") == "kvarnen 3"


def test_a_wikidata_item_or_commons_page_whose_number_equals_a_property_unit_key_is_not_a_leak(site):
    # the tiny city's property-unit keys are 10,123,400 + gid; a Swedish Wikidata item can carry the same number
    edit_card(site, 10, {"name": "Schönfeldtska huset", "qid": "Q10123401", "wp": ["sv"],
                         "photo": {**PHOTO, "page": "https://commons.wikimedia.org/w/index.php?curid=10123402"}})
    assert check(site) == []
    edit_card(site, 10, {"name": "Schönfeldtska huset 10123401", "qid": "Q10123401", "wp": ["sv"]})
    reindex(site)                    # search takes the card's name, and the scan finds the key there too
    assert check(site) == ["privacy: cards/10.json $.10.name holds a property-unit key (FNR)",
                           "privacy: search/index.json $.buildings[3][0] holds a property-unit key (FNR)"]


def test_a_photo_key_whose_hex_digits_equal_a_property_unit_key_is_not_a_leak(site):
    # a photo's key is 16 hex digits of its file's sha1: about one build in ten has a digit run equal to some FNR
    key = "10123403abcdef01-500.jpg"
    (site.parent / "photos" / key).write_bytes(b"\xff\xd8 another tiny jpeg")
    io.write_json(site / "photos.json", [PHOTO_KEY, key])
    edit_card(site, 10, {"name": "Schönfeldtska huset", "qid": "Q10000001", "wp": ["sv"], "photo": {**PHOTO, "key": key}})
    assert check(site) == []


# ---------- The rare-architect rule per building, the photo page exactly, excerpts' shape, the licence link ----------

def test_d35_counts_buildings_not_cards(site):
    # four cards, one building: a rare name on one villa drawn in four LOD1 parts is still rare
    import pandas as pd
    data = site.parents[2] / "data"
    for g in (2, 3, 4, 8):
        edit_card(site, g, {"architects": ["Olle Owner"]})
    assert check(site) == []                                  # four records: not rare
    y = pd.read_parquet(data / "years.parquet")
    y.loc[y.gid.isin([2, 3, 4, 8]), "raa_id"] = "one-shared-record"
    y.to_parquet(data / "years.parquet")
    assert check(site) == [f"cards: 04.json gid 4 is in a private-house category and names 1 architect(s) found on "
                           f"{city.ARCHITECT_MAX_RARE} cards or fewer"]


@pytest.mark.parametrize(("change", "message"), [
    ({"page": "https://commons.wikimedia.org/w/index.php?curid=42&title=File:Exempel_7.jpg"},
     "without its Commons page"),
    ({"lu": "javascript:alert(1)"}, "whose licence link is not an https URL"),
])
def test_a_photo_page_is_its_page_id_only_and_the_licence_link_a_url(site, change, message):
    edit_card(site, 1, {"name": "Kungliga slottet", "qid": "Q750444", "wp": ["sv", "en"], "photo": {**PHOTO, **change}})
    errors = check(site)
    assert any(e.startswith("cards: 01.json gid 1 ") and e.endswith(message) for e in errors), errors


def test_a_designation_written_with_underscores_is_a_leak(site):
    shard = json.loads((site / "wiki" / "01.json").read_text())
    shard["items"]["1"]["sv"]["t"] = "Se filen Diana_1.jpg."
    io.write_json(site / "wiki" / "01.json", shard)
    assert check(site) == ["privacy: wiki/01.json $.items.1.sv.t holds a property designation (FASTIGHET)"]


def test_an_excerpt_item_that_is_not_by_language_fails(site):
    shard = json.loads((site / "wiki" / "01.json").read_text())
    shard["items"]["1"] = "Slottet ägs av staten."
    io.write_json(site / "wiki" / "01.json", shard)
    assert check(site) == ["wiki: 01.json gid 1 is not {lang: {t, r}}"]


def card_of(site, gid):
    return json.loads((site / "cards" / f"{gid % 64:02d}.json").read_text())[str(gid)]


def test_a_rebuild_on_a_card_that_is_not_curated_fails(site):
    # Rebuild lines and older cellars are a hand-checked entry's, checked against its article; gid 0 is
    # RAÄ-dated and gid 10 Wikidata-dated
    edit_card(site, 0, {**card_of(site, 0), "rebuilt": [[1700, "rebuilt"]], "also": [[1805, 1818]]})
    edit_card(site, 10, {**card_of(site, 10), "cellars": True})
    assert check(site) == ["cards: 00.json gid 0 is not curated and carries `rebuilt`",
                           "cards: 00.json gid 0 is not curated and carries `also`",
                           "cards: 10.json gid 10 is not curated and carries `cellars`"]


def test_another_house_on_a_curated_card_may_come_before_its_year(site):
    # Historiska museet's 1805–1818 range on its 1939 card (D65): not a rebuild, so no order against the card's year
    edit_card(site, 1, {**card_of(site, 1), "also": [[1700, 1705], [1805, 1818]]})
    assert check(site) == []


def test_a_rebuild_year_before_the_card_year_fails(site):
    palace = card_of(site, 1)                       # curated 1754, made-up rebuilds (tests/tinycity.py)
    assert palace["rebuilt"] == [[1772, "rebuilt"], [1857, "raised"]] and palace["cellars"] is True
    for rebuilt in ([[1754, "rebuilt"], [1857, "raised"]], [[1700, "raised"]], [[2027, "raised"]]):
        edit_card(site, 1, {**palace, "rebuilt": rebuilt})
        assert check(site) == [f"cards: 01.json gid 1 has a rebuild year not after its own year (1754) or after "
                               f"{s99_validate.YEAR_MAX}"], rebuilt


@pytest.mark.parametrize("change, message", [
    ({"rebuilt": [[1857, "facade"]]}, "has a rebuild whose kind is not rebuilt, raised or extended"),
    ({"rebuilt": [[1857]]}, "has `rebuilt` that is not a list of [year, kind] by year"),
    ({"rebuilt": []}, "has `rebuilt` that is not a list of [year, kind] by year"),
    ({"rebuilt": [["1857", "raised"]]}, "has `rebuilt` that is not a list of [year, kind] by year"),
    ({"rebuilt": [[1857, "raised"], [1772, "rebuilt"]]}, "has `rebuilt` that is not a list of [year, kind] by year"),
    ({"cellars": False}, "has `cellars` that is not true"),
    # the other house on a curated footprint (D65): spans by year, inside the years, before or after the card's own
    *[({"also": also}, "has `also` that is not a list of [from, to] by year, inside 1000..2026")
      for also in ([], [[1818, 1805]], [[1805]], [["1805", 1818]], [[1900, 1905], [1805, 1818]], [[1805, 2027]],
                   [[999, 1805]], "1805–1818")],
])
def test_a_rebuild_of_another_kind_or_shape_fails(site, change, message):
    edit_card(site, 1, {**card_of(site, 1), **change})
    assert check(site) == [f"cards: 01.json gid 1 {message}"]


def test_photo_gids_must_match_the_cards_with_a_photo(site):
    # the photo filter's list (s03_tiles.photo_gids): exactly the shown cards with a photo, sorted
    io.write_json(site / "photo-gids.json", [1, 3])
    assert check(site) == ["photos: photo-gids.json lists gid 3, whose card has no photo"]
    io.write_json(site / "photo-gids.json", [])
    assert check(site) == ["photos: photo-gids.json leaves out gid 1, whose card has a photo"]
    io.write_json(site / "photo-gids.json", {"1": 1})
    assert check(site) == ["photos: photo-gids.json is not a sorted list of gids"]
    (site / "photo-gids.json").unlink()
    assert check(site) == ["photos: photo-gids.json is missing (run s03_tiles)"]
