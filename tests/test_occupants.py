"""What is inside a carded building (pipeline/occupants.py, s06_wiki step 4): public institutions kept, companies and
people left out, English and Swedish labels, the cached Wikidata query one batch at a time. No network."""
import json

import pytest

from pipeline import occupants, s06_wiki

E = "http://www.wikidata.org/entity/"
BORSHUSET, NOBEL, BANK, PERSON, ACADEMY, PAINTING = "Q404416", "Q1144549", "Q900", "Q901", "Q902", "Q903"
# the classes' ancestors (class itself included), as years_wikidata.ancestors gives them
ANC = {"Q207694": {"Q207694", "Q33506"},                      # art museum < museum
       "Q22687": {"Q22687", "Q4830453"},                      # bank < business
       "Q5": {"Q5"}, "Q3305213": {"Q3305213"},                # human; painting
       "Q955824": {"Q955824"},                                # learned society
       "Q1664720": {"Q1664720", "Q2385804", "Q4830453"}}      # an institute that is also a business: left out


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
            row(BORSHUSET, "Q904", "Q1664720", "Ett institut"),
            row(BORSHUSET, BORSHUSET, "Q207694", "Börshuset")]                 # the building itself: not inside it
    out = occupants.occupants_from(rows, ANC)
    assert out == {BORSHUSET: [
        {"qid": ACADEMY, "sv": "Svenska Akademien", "en": "Swedish Academy", "alt": []},          # by Q-number
        {"qid": NOBEL, "sv": "Nobelprismuseet", "en": "Nobel Prize Museum", "alt": ["Nobel Museum", "Nobelmuseet"]}]}


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
    assert "VALUES ?b { wd:Q2 wd:Q3 }" in asked[0][1] and "wdt:P466" in asked[0][1] and "wdt:P159" in asked[0][1]
    assert asked[0][0] == [s06_wiki.WDQS] and "wd:Q207694" in asked[2][1]
    assert out == {BORSHUSET: [{"qid": NOBEL, "sv": "Nobelprismuseet", "en": "Nobelprismuseet", "alt": []}]}


@pytest.mark.parametrize("qids", [[], [""]])
def test_no_carded_items_asks_nothing(tmp_path, monkeypatch, qids):
    monkeypatch.setattr(s06_wiki, "ask", lambda *a, **k: pytest.fail("asked"))
    assert s06_wiki.fetch_occupants(qids, refresh=False, raw=tmp_path) == {}
