"""What is inside a carded building (pipeline/occupants.py, s06_wiki step 4): public institutions kept, companies and
people left out, each class judged by its own ancestors (a library that Wikidata also files under business is kept),
English and Swedish labels, the cached Wikidata query one batch at a time and only its statements that have not
ended. No network."""
import json
import re

import pandas as pd
import pytest

from pipeline import occupants, s06_wiki

E = "http://www.wikidata.org/entity/"
BORSHUSET, NOBEL, BANK, PERSON, ACADEMY, PAINTING = "Q404416", "Q1144549", "Q900", "Q901", "Q902", "Q903"
# the classes' ancestors (class itself included), as years_wikidata.ancestors gives them
ANC = {"Q207694": {"Q207694", "Q33506"},                      # art museum < museum
       "Q22687": {"Q22687", "Q4830453"},                      # bank < business
       "Q5": {"Q5"}, "Q3305213": {"Q3305213"},                # human; painting
       "Q955824": {"Q955824"},                                # learned society
       "Q1664720": {"Q1664720", "Q2385804", "Q4830453"},      # an institute that Wikidata also files under business
       "Q783794": {"Q783794", "Q4830453"}}                    # company < business


def row(b, occ, cls=None, sv=None, en=None, alt=None):
    r = {"b": E + b, "occ": E + occ}
    r.update({k: v for k, v in (("cls", cls and E + cls), ("sv", sv), ("en", en), ("alt", alt)) if v})
    return r


def test_keeps_public_institutions_with_both_labels_and_their_other_names():
    rows = [row(BORSHUSET, NOBEL, "Q207694", "Nobelprismuseet", "Nobel Prize Museum", "Nobelmuseet"),
            row(BORSHUSET, NOBEL, "Q207694", "Nobelprismuseet", "Nobel Prize Museum", "Nobel Museum"),
            row(BORSHUSET, ACADEMY, "Q955824", "Svenska Akademien", "Swedish Academy"),
            row(BORSHUSET, BANK, "Q22687", "Stockholmsbörsen", "Stockholm Stock Exchange"),
            row(BORSHUSET, PERSON, "Q5", "Någon Person"),
            row(BORSHUSET, PAINTING, "Q3305213", "En tavla"),
            row(BORSHUSET, BORSHUSET, "Q207694", "Börshuset")]                 # the building itself: not inside it
    out = occupants.occupants_from(rows, ANC)
    assert out == {BORSHUSET: [
        {"qid": ACADEMY, "sv": "Svenska Akademien", "en": "Swedish Academy", "alt": []},          # by Q-number
        {"qid": NOBEL, "sv": "Nobelprismuseet", "en": "Nobel Prize Museum", "alt": ["Nobel Museum", "Nobelmuseet"]}]}


def test_each_class_is_judged_by_its_own_ancestors():
    # Wikidata's class graph files library (Q7075) under business too (library < organization < ... < business): the
    # union of the classes' ancestors then always met SKIP, and Svenska Akademiens Nobelbibliotek, Riksbanken and
    # Kungliga Operan were dropped (2026-10-21). A class that descends from SKIP alone still drops the item.
    anc = {**ANC, "Q7075": {"Q7075", "Q43229", "Q4830453"},                 # library < organization < business
           "Q43229": {"Q43229", "Q4830453"}}
    rows = [row("Q1", "Q20", "Q7075", "Nobelbiblioteket"),                        # a library: kept
            row("Q1", "Q21", "Q1664720", "Ett institut"),                          # an institute and a business: kept
            row("Q1", "Q22", "Q22687", "En bank"),                                 # a bank, a business alone: out
            row("Q1", "Q23", "Q207694", "Ett företagsmuseum"),                     # a museum that is a company: out
            row("Q1", "Q23", "Q783794", "Ett företagsmuseum"),
            row("Q1", "Q24", "Q43229", "En organisation")]                        # nothing KEEP names: out
    assert [o["qid"] for o in occupants.occupants_from(rows, anc)["Q1"]] == ["Q20", "Q21"]
    assert occupants.kept({"Q7075"}, anc) and not occupants.kept({"Q207694", "Q783794"}, anc)
    assert not occupants.kept(set(), anc)


def test_one_language_stands_in_for_the_other_and_an_unlabelled_item_is_left_out():
    rows = [row("Q1", "Q10", "Q955824", en="Only English"), row("Q1", "Q11", "Q955824", sv="Bara svenska"),
            row("Q1", "Q12", "Q955824"), row("Q1", "Q13", "Q955824", "Q13")]     # no label, or the bare Q-id
    assert [(o["sv"], o["en"]) for o in occupants.occupants_from(rows, ANC)["Q1"]] == [
        ("Only English", "Only English"), ("Bara svenska", "Bara svenska")]


def test_fetch_asks_wikidata_in_cached_batches_with_the_buildings_items(tmp_path, monkeypatch):
    asked = []

    def ask(endpoints, data, dest, refresh, headers=None):
        asked.append((endpoints, data["query"], dest.name))
        body = {"results": {"bindings": []}}
        if dest.name.startswith("occupants_"):
            body["results"]["bindings"] = [{"b": {"value": E + BORSHUSET}, "occ": {"value": E + NOBEL},
                                            "cls": {"value": E + "Q207694"}, "sv": {"value": "Nobelprismuseet"}}]
        else:
            body["results"]["bindings"] = [{"a": {"value": E + "Q207694"}, "b": {"value": E + "Q33506"}}]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(body))
        return body

    monkeypatch.setattr(s06_wiki, "ask", ask)
    monkeypatch.setattr(s06_wiki, "OCCUPANT_BATCH", 2)
    out = s06_wiki.fetch_occupants(["Q3", BORSHUSET, "Q2", BORSHUSET], refresh=False, raw=tmp_path)
    assert [a[2] for a in asked] == ["occupants_000.json", "occupants_001.json", "occupant_classes.json"]
    assert "VALUES ?b { wd:Q2 wd:Q3 }" in asked[0][1]
    # the links as statements (p:/ps:), so one that has ended (an end time, an end cause, a latest date) is left out
    query = asked[0][1]
    assert all(f"p:{p} ?st . ?st ps:{p}" in query for p in ("P276", "P159", "P466")) and "wdt:P466" not in query
    assert all(f"FILTER NOT EXISTS {{ ?st pq:{p} [] }}" in query for p in ("P582", "P1534", "P1326"))
    assert asked[0][0] == [s06_wiki.WDQS] and "wd:Q207694" in asked[2][1]
    assert out == {BORSHUSET: [{"qid": NOBEL, "sv": "Nobelprismuseet", "en": "Nobelprismuseet", "alt": []}]}


@pytest.mark.parametrize("qids", [[], [""]])
def test_no_carded_items_asks_nothing(tmp_path, monkeypatch, qids):
    monkeypatch.setattr(s06_wiki, "ask", lambda *a, **k: pytest.fail("asked"))
    assert s06_wiki.fetch_occupants(qids, refresh=False, raw=tmp_path) == {}


# The hand-checked table (pipeline/occupant_pins.csv): an institution placed by footprint, card or none.
HEAD = "key,qid,sv,en,alt,source,note\n"
U1, U2 = "2e389b81-54f2-48cc-b4ee-ae1285df2202", "2e389b81-54f2-48cc-b4ee-ae1285df2204"
GOOD = (f"{U1},Q1726607,Historiska museet,Swedish History Museum,Statens historiska museum;Historiska museet,"
        "https://sv.wikipedia.org/w/index.php?oldid=59676070,Checked on the map data 2026-10-21\n"
        f"{U1},,Ekonomiska museet,,,https://www.wikidata.org/wiki/Q1750428,Shares the footprint\n"
        "oid:50330777,Q10655174,Riksdagsbiblioteket,Riksdag Library,,https://www.riksdagen.se/sv/bibliotek/,\"The old "
        "bank palace, since 1996\"\n")


def buildings():
    return pd.DataFrame({"gid": [0, 1, 2], "uuid": [U1, "", U2], "oid": [1, 50330777, 3],
                         "kategori": ["Allmän byggnad", "Allmän byggnad", "Enbostadshus"]})


def test_pins_by_footprint_uuid_or_oid_with_their_names(tmp_path):
    path = tmp_path / "pins.csv"
    path.write_text(HEAD + GOOD, encoding="utf-8")
    out = occupants.pinned(occupants.read_pins(path), buildings())
    assert out == {0: [{"qid": "Q1726607", "sv": "Historiska museet", "en": "Swedish History Museum",
                        "alt": ["Statens historiska museum"]},           # its own name is not another name
                       {"qid": "", "sv": "Ekonomiska museet", "en": "Ekonomiska museet", "alt": []}],
                   1: [{"qid": "Q10655174", "sv": "Riksdagsbiblioteket", "en": "Riksdag Library", "alt": []}]}


@pytest.mark.parametrize("row", [
    "not-a-uuid,,Namn,,,https://www.wikidata.org/wiki/Q1,note",
    f"{U1},1726607,Namn,,,https://www.wikidata.org/wiki/Q1,note",                 # a qid without its Q
    f"{U1},,,English only,,https://www.wikidata.org/wiki/Q1,note",                # no Swedish name
    f"{U1},,Namn,,,http://example.se/,note",                                     # not https
    f"{U1},,Namn,,,https://sv.wikipedia.org/wiki/Historiska_museet,note",         # a live article, not a revision
    f"{U1},,Namn,,,https://www.wikidata.org/wiki/Q1,",                           # no note
    f"{U1},,Namn,,,https://www.wikidata.org/wiki/Q1,ask kontakt@example.org",     # an e-mail address
    f"{U1},,Namn,,,https://www.wikidata.org/wiki/Q1,call 08-123 45 67",          # a phone number
    f"{U1},,Namn,,a;;b,https://www.wikidata.org/wiki/Q1,note",                   # an empty other name
    f"{U1},Q1726607,Historiska Muséet,,,https://www.wikidata.org/wiki/Q1,note",  # the same institution again
])
def test_a_malformed_or_repeated_row_refuses_the_table(tmp_path, row):
    path = tmp_path / "pins.csv"
    path.write_text(HEAD + GOOD + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        occupants.read_pins(path)


def test_a_pin_on_a_private_house_or_an_oid_for_a_footprint_with_a_uuid_is_refused_and_a_lost_one_skipped(tmp_path,
                                                                                                         capsys):
    for key in (U2, "oid:1"):                       # a villa; gid 0's oid while gid 0 has a UUID
        path = tmp_path / "pins.csv"
        path.write_text(HEAD + f"{key},,Namn,,,https://www.wikidata.org/wiki/Q1,note\n", encoding="utf-8")
        with pytest.raises(ValueError):
            occupants.pinned(occupants.read_pins(path), buildings())
    path.write_text(HEAD + "oid:99,,Namn,,,https://www.wikidata.org/wiki/Q1,note\n", encoding="utf-8")
    assert occupants.pinned(occupants.read_pins(path), buildings()) == {}
    assert "not among these buildings" in capsys.readouterr().err


def test_the_shipped_table_reads_and_names_no_property_designation():
    t = occupants.read_pins()
    assert len(t) >= 80 and "Historiska museet" in set(t.sv)
    # a designation reads like "Krubban 1" or "Kvarteret Krubban": a name or another name that ends in a number, or
    # starts with "kvarteret", would be one (s99 checks the built index against the city's own designations); the
    # one name that ends in a number is a museum's own, Magasin III's other spelling
    names = [n for c in ("sv", "en") for n in t[c]] + [a for alt in t.alt for a in alt.split(";") if a]
    assert [n for n in names if re.search(r"\s\d+(?:[:;]\d+)?$", n) or n.casefold().startswith("kvarteret")] == [
        "Magasin 3"]
