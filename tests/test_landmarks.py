"""The curated landmark seed (Task 10)."""
import re

import pytest
import requests

from pipeline import s08_landmarks
from pipeline.fetch import UA
from pipeline.landmarks import LANDMARKS

KEYS = {"name", "qid", "lat", "lon", "year", "year_from", "year_to", "source", "checks"}
OPTIONAL = {"timeline", "rebuilt", "cellars", "point"}     # Plan 4a: Task 10's priority, Task 11a's three
REQUIRED = {"Riddarholmskyrkan", "Storkyrkan", "Riddarhuset", "Stockholms slott", "Stockholms stadshus",
            "Stockholms stadsbibliotek", "Kaknästornet", "Avicii Arena"}


def test_every_entry_is_complete_and_consistent():
    assert s08_landmarks.OPTIONAL == OPTIONAL
    for L in LANDMARKS:
        assert KEYS <= set(L) <= KEYS | OPTIONAL, L["name"]
        if "point" in L:      # a hand-checked point says why it is not the item's P625, and where it comes from
            assert set(L["point"]) == {"reason", "source"}, L["name"]
            assert all(isinstance(v, str) and v.strip() for v in L["point"].values()), L["name"]
        # a Wikidata item, or "" for a building that has none (Task 12): then its point is hand-checked
        assert re.fullmatch(r"Q\d+", L["qid"]) or (L["qid"] == "" and "point" in L), L["name"]
        assert re.fullmatch(r"(sv|en):.+", L["source"]), L["name"]
        assert 1000 <= L["year_from"] <= L["year"] <= L["year_to"] <= 2026, L["name"]
        assert 59.2 < L["lat"] < 59.45 and 17.75 < L["lon"] < 18.25, L["name"]
        assert L["checks"] and all(isinstance(c, str) and c for c in L["checks"]), L["name"]


def test_names_and_items_are_unique_and_the_seed_is_complete():
    assert len({L["name"] for L in LANDMARKS}) == len(LANDMARKS)
    items = [L["qid"] for L in LANDMARKS if L["qid"]]
    assert len(set(items)) == len(items)
    assert REQUIRED <= {L["name"] for L in LANDMARKS}


@pytest.mark.network
def test_coordinates_are_the_wikidata_p625():
    ids, entities = [L["qid"] for L in LANDMARKS if L["qid"]], {}
    for i in range(0, len(ids), 50):         # the API takes at most 50 ids a request; one request at a time
        r = requests.get("https://www.wikidata.org/w/api.php", headers=UA, timeout=60, params={
            "action": "wbgetentities", "ids": "|".join(ids[i:i + 50]), "props": "claims", "format": "json"})
        r.raise_for_status()
        entities.update(r.json()["entities"])
    for L in LANDMARKS:
        if not L["qid"]:      # Task 12: no item, so no P625 to hold the point to (the offline test wants its `point`)
            continue
        claims = entities[L["qid"]]["claims"]
        p31 = {c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get("P31", [])}
        assert "Q4167410" not in p31, f'{L["name"]}: {L["qid"]} is a disambiguation page'
        if "point" in L:      # Task 11a: a hand-checked point, not the P625; s02_years still places it within 15 m
            assert L["point"]["reason"].strip() and L["point"]["source"].strip(), L["name"]
            continue
        coord = claims["P625"][0]["mainsnak"]["datavalue"]["value"]
        assert abs(coord["latitude"] - L["lat"]) < 1e-6, L["name"]
        assert abs(coord["longitude"] - L["lon"]) < 1e-6, L["name"]
