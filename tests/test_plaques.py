"""Samfundet S:t Erik's blue plaques: the list, the texts, placing them (s15_plaques) and s99's check. No network: a
five-plaque list, written as pypdf reads the society's PDF, and footprints around the origin."""
import json

import geopandas as gpd
import pandas as pd
import shapely
from pyproj import Transformer

from pipeline import city, plaques, s03_tiles, s15_plaques, s99_validate
from pipeline.geo import lonlat_to_3011
from pipeline.addresses import assign
from pipeline.sources import check_sources, load_sources

TO_WGS84 = Transformer.from_crs(city.CRS, 4326, always_xy=True)
X0, Y0 = city.ORIGIN

LIST = """Kulturhusskyltar lista
Skyltlista (rev 2026-02-06)
Gamla Stan/Riddarholmen
 Populärnamn Adress, fastighetsbeteckning ID Stockholmskällan År
1.  Börshuset Källargränd 2 (Rådstugan 1) (Skylt saknas) 27666 1995
2.  Den Gyldene Freden Österlånggatan 51 (Argus 6) 27627 1997
6.  Stortorget 18–20 Stortorget 18–20 (Echo 1) 27664 1995
11.  Vindragarlagets hus Stora Hoparegränd 6 (Pollux 11) 27460 1993 (rev 2013)
Kulturhusskyltar lista
Norrmalm
101.  Kvarteret Vätan 22, Katolskt centrum/Otte
Sköld
Regeringsgatan 80, /Snickarbacken 7, (Vätan 22) 30863 2015
Broskyltar
 Populärnamn ID Stockholmskällan Årtal
197.  Vasabron 28351 2007
"""


def post(title, *paras):
    body = "".join(f"<p>{p}</p>\n" for p in paras)
    return (f'<h1 class="post-content"> {title}</h1>\n<div class="post-content section">\n'
            f"<p><strong><em>(texten kommmer från en skylt)</em></strong></p>\n{body}"
            "<p><em>Built in 1720 by a vintner.</em></p>\n<p>&nbsp;</p>\n"
            "<p><strong>Samfundet S:t Eriks kulturhusskyltar<br /></strong>Sedan 1993 har samfundet skyltat.</p>\n"
            "</div>")


def box(gid, x, y, s=10):
    return {"gid": gid, "geometry": shapely.box(X0 + x - s, Y0 + y - s, X0 + x + s, Y0 + y + s)}


def lonlat(x, y):
    return TO_WGS84.transform(X0 + x, Y0 + y)


def test_parse_list_reads_rows_wrapped_rows_and_years():
    rows = plaques.parse_list(LIST)
    assert [(r["n"], r["id"], r["year"], r["missing"]) for r in rows] == [
        (1, 27666, 1995, True), (2, 27627, 1997, False), (6, 27664, 1995, False), (11, 27460, 1993, False),
        (101, 30863, 2015, False), (197, 28351, 2007, False)]
    # the property designations never come along (s99's privacy check), nor the "plaque missing" note
    assert rows[1]["head"] == "Den Gyldene Freden Österlånggatan 51"
    assert rows[0]["head"] == "Börshuset Källargränd 2"
    assert rows[4]["head"] == "Kvarteret Vätan 22, Katolskt centrum/Otte Sköld Regeringsgatan 80, /Snickarbacken 7"
    assert rows[5]["head"] == "Vasabron"


def test_split_address_takes_the_first_street_after_the_name():
    known = {"osterlanggatan", "stortorget", "stora hoparegrand", "regeringsgatan", "snickarbacken"}
    assert plaques.split_address("Den Gyldene Freden Österlånggatan 51", known) == (
        "Den Gyldene Freden", [("Österlånggatan", ["51"])])
    assert plaques.split_address("Stortorget 18–20 Stortorget 18–20", known) == (
        "Stortorget 18–20", [("Stortorget", ["18", "20"])])
    assert plaques.split_address("Vindragarlagets hus Stora Hoparegränd 6", known)[1] == [("Stora Hoparegränd", ["6"])]
    name, addrs = plaques.split_address("Kvarteret Vätan 22, Katolskt centrum/Otte Sköld Regeringsgatan 80, /Snickarbacken 7",
                                        known)
    assert name == "Kvarteret Vätan 22, Katolskt centrum Otte Sköld"
    assert addrs == [("Regeringsgatan", ["80"]), ("Snickarbacken", ["7"])]
    assert plaques.split_address("Vasabron", known) == ("Vasabron", [])
    # without the city's streets: a word that ends like a street
    assert plaques.split_address("Den Gyldene Freden Österlånggatan 51") == ("Den Gyldene Freden", [("Österlånggatan", ["51"])])
    assert plaques.house_numbers(["40", "A,", "B"]) == ["40A", "40B"]
    assert plaques.house_numbers(["30,", "33"]) == ["30", "33"]


def test_text_from_post_keeps_the_swedish_text_only():
    title, text = plaques.text_from_post(post("Den Gyldene Freden, Österlånggatan 51 (Argus 6)",
                                              "Huset byggdes på 1720-talet.", "Källaren har varit stamställe."))
    assert title == "Den Gyldene Freden, Österlånggatan 51 (Argus 6)"
    assert text == "Huset byggdes på 1720-talet.\n\nKällaren har varit stamställe."


def test_cut_leaves_out_owners_and_byggherrar():
    text, cut = plaques.cut("Huset byggdes på 1720-talet. Genom testamentet kom huset 1920 i Svenska Akademiens ägo. "
                            "Taube satt här.")
    assert (text, cut) == ("Huset byggdes på 1720-talet. Taube satt här.", True)
    assert plaques.cut("Bron invigdes 1878.") == ("Bron invigdes 1878.", False)


def fixture():
    """Five plaques: Gyldene Freden and Stortorget by address, Vindragarlaget by its Open Plaques position, Vasabron
    on no footprint (a bridge), Börshuset not on the wall now."""
    rows = [r for r in plaques.parse_list(LIST) if r["id"] != 30863]
    b = gpd.GeoDataFrame([box(0, 0, 0), box(1, 40, 0), box(2, 80, 0), box(3, 120, 0)], crs=city.CRS)
    table = pd.DataFrame({"gid": [0, 1, 1, 3], "street": ["Österlånggatan", "Stortorget", "Stortorget", "Källargränd"],
                          "number": ["51", "18", "20", "2"]})
    lon, lat = lonlat(80, 12)                                                     # 2 m off the facade of gid 2
    lon2, lat2 = lonlat(300, 300)                                                 # the bridge: no footprint near
    op = [{"inscription": "Vindragarlagets hus Byggnaden uppfördes", "address": "Stora Hoparegränd 6",
           "latitude": lat, "longitude": lon},
          {"inscription": "Vasabron Vasabron ritades", "address": "Vasabron", "latitude": lat2, "longitude": lon2}]
    texts = {27627: "Huset byggdes på 1720-talet. Huset kom i Svenska Akademiens ägo.", 27664: "Två hus.",
             27460: "Byggnaden uppfördes 1585.", 28351: "Bron invigdes 1878.", 27666: "Börsen."}
    return rows, texts, table, b, op


def test_place_by_address_then_position_else_unplaced():
    rows, _, table, b, op = fixture()
    placed = {p["id"]: (p["gid"], p["how"]) for p in plaques.place(
        rows, table, b, op, streets={"osterlanggatan", "stortorget", "kallargrand"}, to_xy=lonlat_to_3011, assign=assign)}
    assert placed == {27666: (3, "address"), 27627: (0, "address"), 27664: (1, "address"), 27460: (2, "position"),
                      28351: (-1, "")}


def test_build_writes_placed_plaques_and_reviews_the_rest():
    rows, texts, table, b, op = fixture()
    out, review, n = s15_plaques.build(rows, texts, table, b, op)
    assert n == {"plaques": 5, "address": 2, "name": 0, "position": 1, "unplaced": 1, "missing": 1, "left_out": 0}
    assert [(p["id"], p["gid"], p["how"]) for p in out] == [(27460, 2, "position"), (27627, 0, "address"),
                                                            (27664, 1, "address")]
    freden = next(p for p in out if p["id"] == 27627)
    assert freden["name"] == "Den Gyldene Freden" and freden["year"] == 1997 and freden["cut"] is True
    assert freden["text"] == "Huset byggdes på 1720-talet."                  # the owner sentence left out
    assert freden["credit"] == "Samfundet S:t Erik, CC BY 4.0"
    assert (freden["x"], freden["z"]) == tuple(round(float(v), 1) for v in city.to_local(X0, Y0))
    assert not {"address", "addrs", "owner", "residents"} & set(freden)      # what the list says, nothing about people
    assert sorted(r.split("\t")[0] for r in review) == ["27666", "28351"]
    assert "Skylt saknas" in next(r for r in review if r.startswith("27666"))
    # a takedown's building is left out
    out, _, n = s15_plaques.build(rows, texts, table, b, op, taken={0})
    assert 27627 not in {p["id"] for p in out} and n["left_out"] == 1


def test_s99_checks_plaques(tmp_path):
    rows, texts, table, b, op = fixture()
    out, _, _ = s15_plaques.build(rows, texts, table, b, op)
    (tmp_path / "plaques.json").write_text(json.dumps(out), encoding="utf-8")
    assert s99_validate.check_plaques(tmp_path, 4) == []
    assert s99_validate.check_plaques(tmp_path / "none", 4) == []             # a version without plaques
    bad = [{**out[0], "gid": 9}, {**out[1], "credit": ""}, {**out[2], "text": "Huset ägs av staden."}, out[2]]
    (tmp_path / "plaques.json").write_text(json.dumps(bad), encoding="utf-8")
    errors = s99_validate.check_plaques(tmp_path, 4)
    assert any("gid 9" in e for e in errors) and any("credit" in e for e in errors)
    assert any("owns" in e for e in errors) and any("twice" in e for e in errors)


def test_plaque_sources_are_registered_and_wait_for_the_plaques_switch(monkeypatch):
    sources = load_sources()
    by = {s["id"]: s for s in sources}
    assert check_sources(sources, release=True) == []
    s = by["samfundet_plaques"]
    assert s["licence"] == "CC-BY-4.0" and "Samfundet S:t Erik, CC BY 4.0" in s["attribution"]
    assert s["list_page"].startswith("https://samfundetsterik.se/") and "{id}" in s["texts_url"]
    assert by["openplaques"]["licence"] == "LicenseRef-PublicDomain"
    # About's sources list follows features.plaques (on in city.FEATURES), not the layers switch
    assert city.FEATURES["plaques"] is True
    monkeypatch.setitem(city.FEATURES, "layers", False)
    monkeypatch.setitem(city.FEATURES, "plaques", False)
    assert not {"samfundet_plaques", "openplaques"} & {a["id"] for a in s03_tiles.attribution(sources)}
    monkeypatch.setitem(city.FEATURES, "plaques", True)
    shown = {a["id"]: a for a in s03_tiles.attribution(sources)}
    assert shown["samfundet_plaques"]["credit"] == {"en": "Kulturhusskyltar: Samfundet S:t Erik, CC BY 4.0, processed",
                                                    "sv": "Kulturhusskyltar: Samfundet S:t Erik, CC BY 4.0, bearbetad"}
    assert shown["samfundet_plaques"]["url"].startswith("https://samfundetsterik.se/")
    assert shown["samfundet_plaques"]["licence_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert shown["openplaques"]["url"].startswith("https://openplaques.org/")   # its positions place some plaques
    assert s99_validate.check_attribution({"attribution": list(shown.values())}) == []


def test_clean_name_drops_a_property_designation_from_a_plaque_name():
    d = {"stamtavlan 5", "vätan 22", "argus 6"}
    assert plaques.clean_name("Elefanthuset Stamtavlan 5", d) == "Elefanthuset"
    assert plaques.clean_name("Kvarteret Vätan 22, Katolskt centrum/Otte Sköld", d) == "Katolskt centrum/Otte Sköld"
    assert plaques.clean_name("Den Gyldene Freden", d) == "Den Gyldene Freden"
    assert plaques.clean_name("Stamtavlan 5", d) == ""


def test_build_keeps_one_entry_per_plaque_and_no_designation_in_its_name():
    rows, texts, table, b, op = fixture()
    twice = [*rows, dict(next(r for r in rows if r["id"] == 27627))]
    out, review, _ = s15_plaques.build(twice, texts, table, b, op, designations={"argus 6"})
    assert [p["id"] for p in out].count(27627) == 1
    assert any(r.startswith("27627") and "listed twice" in r for r in review)
    named = [dict(r, name="Den Gyldene Freden Argus 6") if r["id"] == 27627 else r for r in rows]
    out, _, _ = s15_plaques.build(named, texts, table, b, op, designations={"argus 6"})
    assert next(p for p in out if p["id"] == 27627)["name"] == "Den Gyldene Freden"


def test_parse_list_marks_the_bridges_plaques():
    rows = plaques.parse_list(LIST)
    assert [r["id"] for r in rows if r["bridge"]] == [28351]                   # Vasabron, under "Broskyltar"


def test_house_numbers_reads_ranges_and_a_dash_before_a_space():
    assert plaques.house_numbers(["18–24"]) == ["18", "20", "22", "24"]
    assert plaques.house_numbers(["46–108"]) == ["46", "108"]                  # too wide: only its ends
    assert plaques.house_numbers(["25–", "27"]) == ["25", "27"]                # "Nybrogatan 25– 27"
    assert plaques.split_address("Hvita Björn, Nybrogatan 25– 27", {"nybrogatan"}) == (
        "Hvita Björn", [("Nybrogatan", ["25", "27"])])


def test_street_variants_resolve_only_one_known_street():
    streets = {"drottninggatan", "stora nygatan", "lilla nygatan", "sankt eriksgatan", "storgatan"}
    assert plaques.known_street("Drottningg.", streets) == "drottninggatan"
    assert plaques.known_street("Drottninggata", streets) == "drottninggatan"
    assert plaques.known_street("St. Eriksgatan", streets) == "sankt eriksgatan"
    assert plaques.known_street("L. Nygatan", streets) == "lilla nygatan"
    assert plaques.known_street("Nygatan", streets) is None                    # Stora or Lilla: never a guess
    assert plaques.known_street("Storgatan", {"stora storgatan"} | streets) == "storgatan"   # as written wins
    assert plaques.known_street("Okändgatan", streets) is None


def test_a_renamed_street_resolves_to_its_name_today(monkeypatch):
    monkeypatch.setitem(plaques.RENAMED, "gamla vagen", "nya vagen")
    assert plaques.known_street("Gamla vägen", {"nya vagen"}) == "nya vagen"


def test_letter_variants_only_when_they_sit_on_one_footprint():
    table = pd.DataFrame({"gid": [5, 5, 6, 8, 7], "street": ["Sibyllegatan", "Sibyllegatan", "Erstagatan", "Erstagatan",
                                                              "Saltmätargatan"],
                          "number": ["50A", "50B", "1A", "1B", "19"]})
    assert plaques.by_address([("Sibyllegatan", ["50"])], table) == -1         # not as written
    assert plaques.by_address([("Sibyllegatan", ["50"])], table, variants=True) == 5
    assert plaques.by_address([("Erstagatan", ["1"])], table, variants=True) == -1      # 1A and 1B: two footprints
    assert plaques.by_address([("Saltmätargatan", ["19B"])], table, variants=True) == 7  # 19B written as 19


def test_by_name_takes_only_a_unique_card_name():
    cards = {"abf huset": [11], "johannes brandstation": [12], "tullhuset": [1, 2]}
    assert plaques.by_name("Johannes brandstation", cards) == 12
    assert plaques.by_name("ABF–huset Sveavägen", cards, {"sveavagen"}) == 11     # the street off its end
    assert plaques.by_name("Tullhuset", cards) == -1                           # two cards: never a guess
    assert plaques.by_name("Okänt hus", cards) == -1


def test_place_order_keeps_address_and_position_first_and_never_places_a_bridge():
    rows, _, table, b, op = fixture()
    streets = {"osterlanggatan", "stortorget", "kallargrand"}
    # a card named like a plaque never overrides its address or its position
    cards = {"den gyldene freden": [2], "vindragarlagets hus": [0], "vasabron": [3]}
    placed = {p["id"]: (p["gid"], p["how"]) for p in plaques.place(
        rows, table, b, op, streets=streets, to_xy=lonlat_to_3011, assign=assign, cards=cards)}
    assert placed[27627] == (0, "address") and placed[27460] == (2, "position")
    assert placed[28351] == (-1, "")                                          # the bridge, whatever its card or position
    # a position within 25 m of a footprint
    lon, lat = lonlat(80, 32)                                                  # 22 m off gid 2's facade
    near = [dict(op[0], latitude=lat, longitude=lon)]
    got = {p["id"]: p["gid"] for p in plaques.place(rows, table, b, near, streets=streets, to_xy=lonlat_to_3011,
                                                    assign=assign)}
    assert got[27460] == 2
    # by the card's name when neither address nor position places it
    got = {p["id"]: (p["gid"], p["how"]) for p in plaques.place(rows, table, b, [], streets=streets | {"stora hoparegrand"},
                                                                to_xy=lonlat_to_3011, assign=assign, cards=cards)}
    assert got[27460] == (0, "name")


def test_load_cards_leaves_out_private_houses(tmp_path):
    pd.DataFrame({"gid": [0, 1, 2], "kategori": ["Allmän byggnad", "Enbostadshus", "Allmän byggnad"]}
                 ).to_parquet(tmp_path / "b.parquet")
    pd.DataFrame({"gid": [0, 1], "name": ["ABF–huset", "Villa X"]}).to_parquet(tmp_path / "a.parquet")
    pd.DataFrame({"gid": [2], "name": ["Johannes brandstation"]}).to_parquet(tmp_path / "w.parquet")
    assert s15_plaques.load_cards(tmp_path / "b.parquet", tmp_path / "a.parquet", tmp_path / "w.parquet") == {
        "abf huset": [0], "johannes brandstation": [2]}
