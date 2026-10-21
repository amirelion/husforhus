"""pipeline/sources.yml and pipeline/sources.py."""
import copy
from pathlib import Path

import pytest
import yaml

from pipeline.sources import check_sources, credit, load_sources, main

ROOT = Path(__file__).resolve().parents[1]
GOOD = {
    "id": "demo",
    "url": "https://example.org/demo.zip",
    "publisher": "Example",
    "product": "Demo product",
    "dataset": "Demo data",
    "licence": "CC-BY-4.0",
    "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    "attribution": "Demo product, © Example, CC BY 4.0 (modified)",
    "modified": True,
    "status": "confirmed",
}
MARKERS = {"CC-BY-4.0": "CC BY 4.0", "CC-BY-SA-4.0": "CC BY-SA 4.0", "ODbL-1.0": "ODbL", "CC0-1.0": "CC0"}
ATTRIBUTION_LICENCES = ["CC-BY-4.0", "CC-BY-SA-4.0", "ODbL-1.0"]


def with_(**changes):
    """GOOD with changes applied; None removes a field. A new licence brings an attribution that fits it."""
    entry = copy.deepcopy(GOOD)
    if "licence" in changes and "attribution" not in changes:
        entry["attribution"] = f"Demo product, © Example, {MARKERS.get(changes['licence'], 'CC0')} (modified)"
    for key, value in changes.items():
        if value is None:
            entry.pop(key)
        else:
            entry[key] = value
    return entry


def test_repo_sources_file():
    sources = load_sources(ROOT / "pipeline" / "sources.yml")
    ids = [s["id"] for s in sources]
    assert ids == ["city_lod1", "city_stadsdelar", "city_stadskarta", "raa_bebyggelse", "raa_old", "wikidata", "osm",
                   "lm_markhojd", "lm_laser", "wikipedia", "samfundet_plaques", "openplaques", "stadsmuseet_br",
                   "stadsarkivet_bygglov", "stadsmuseet_photos", "kulturnav", "stadsmuseet_inventories", "stockholm_stages",
                   "metro_stations", "metro_track", "ferry_routes"]
    by_id = {s["id"]: s for s in sources}
    # Lantmäteriet's terrain model, CC BY 4.0 with no licence question pending (it never blocks --release)
    # asks for the product name, ©Lantmäteriet, that it was processed and the licence
    lm = by_id["lm_markhojd"]
    assert (lm["licence"], lm["status"], lm["modified"], lm["publisher"]) == ("CC-BY-4.0", "confirmed", True, "Lantmäteriet")
    assert lm["attribution"] == "Markhöjdmodell Nedladdning, © Lantmäteriet, CC BY 4.0 (bearbetad / modified)"
    # the laser points for the towers: CC BY 4.0, processed (only derived building parts ship), its own credit line
    la = by_id["lm_laser"]
    assert (la["licence"], la["status"], la["modified"], la["publisher"]) == ("CC-BY-4.0", "confirmed", True, "Lantmäteriet")
    assert la["url"] == "https://www.lantmateriet.se/sv/geodata/vara-produkter/produktlista/laserdata-nedladdning-skog/"
    assert credit(la) == {"en": "Laserdata Nedladdning, skog: © Lantmäteriet, CC BY 4.0, processed",
                          "sv": "Laserdata Nedladdning, skog: © Lantmäteriet, CC BY 4.0, bearbetad"}
    # The card's excerpts are CC BY-SA 4.0, shortened (modified), credited under each one too
    assert by_id["wikipedia"]["licence"] == "CC-BY-SA-4.0" and by_id["wikipedia"]["modified"] is True
    # The three year sources, their licences and the ODbL attribution the licence requires
    assert {k: by_id[k]["licence"] for k in ("raa_old", "wikidata", "osm")} == {"raa_old": "CC0-1.0", "wikidata": "CC0-1.0", "osm": "ODbL-1.0"}
    assert "© OpenStreetMap contributors" in by_id["osm"]["attribution"]
    city_attribution = {
        "city_lod1": "SBK 3D-Byggnader (LOD1) generaliserade, © Stockholms stad, Stadsbyggnadskontoret, "
                     "CC BY 4.0 (bearbetad / modified)",
        "city_stadsdelar": "Stadsdelar, © Stockholms stad, Stadsbyggnadskontoret, CC BY 4.0 (bearbetad / modified)",
        "city_stadskarta": "Stadskarta, © Stockholms stad, Stadsbyggnadskontoret, CC BY 4.0 (bearbetad / modified)",
    }
    for key, attribution in city_attribution.items():
        s = by_id[key]
        # 2026-10-16: the City confirmed the 3D buildings and the districts; the city map (contour lines included)
        # rests on its product specification's CC BY
        assert s["licence"] == "CC-BY-4.0" and s["status"] == "confirmed" and s["modified"] is True
        assert s["attribution"] == attribution
        assert s["url"].startswith("https://dataportalen.stockholm.se/dataportalen/Data/Stadsbyggnadskontoret/")
    raa = by_id["raa_bebyggelse"]
    assert raa["licence"] == "CC0-1.0" and raa["status"] == "confirmed"
    assert raa["attribution"] == "Riksantikvarieämbetet, Bebyggelseregistret (CC0)"
    assert check_sources(sources, release=False) == []
    # The corner credit names the City, RAÄ, OpenStreetMap (linked to its copyright page, as the OSMF asks)
    # and, on a build whose terrain came from its model, Lantmäteriet (s03_tiles.attribution leaves it out otherwise)
    words = [s["corner"]["en"] for s in sources if "corner" in s]
    assert list(dict.fromkeys(words)) == ["© Stockholms stad", "RAÄ", "© OpenStreetMap contributors", "© Lantmäteriet"]
    assert by_id["osm"]["corner"] == {"en": "© OpenStreetMap contributors", "sv": "© OpenStreetMap-bidragsgivare",
                                      "url": "https://www.openstreetmap.org/copyright"}
    assert "corner" not in by_id["wikidata"] and "corner" not in by_id["wikipedia"]   # credited in About and per text


@pytest.mark.parametrize(("corner", "message"), [
    ("© X", "corner must be a mapping with en and sv"), ({"en": "© X"}, "corner needs its sv words"),
    ({"en": " ", "sv": "© X"}, "corner needs its en words"), ({"en": "X", "sv": "X", "url": "ftp://x"}, "corner url"),
    ({"en": "X", "sv": "X", "link": "https://x"}, "corner has fields other than")])
def test_a_corner_credit_needs_both_languages_and_a_web_url(corner, message):
    errors = check_sources([with_(corner=corner)], release=False)
    assert len(errors) == 1 and message in errors[0]
    assert check_sources([with_(corner={"en": "© X", "sv": "© X", "url": "https://x.org"})], release=False) == []


def test_every_source_has_a_dataset_and_credit_as_has_both_languages():
    # Every credit reads "Dataset: publisher, licence"; where a source prescribes its own words
    # (credit_as) they stand in the publisher's place, in both languages; licence_as (the City's "CC BY") is the
    # licence's own name with or without its version, never another licence's
    assert check_sources([with_(dataset=None)], release=False) == ["demo: missing field 'dataset'"]
    assert check_sources([with_(dataset=" ")], release=False) == ["demo: missing field 'dataset'"]
    for credit_as, message in [("© X", "credit_as must be a mapping with en and sv"),
                               ({"en": "© X"}, "credit_as needs its sv words"),
                               ({"en": "© X", "sv": ""}, "credit_as needs its sv words"),
                               ({"en": "X", "sv": "X", "url": "https://x.org"}, "credit_as has fields other than")]:
        errors = check_sources([with_(credit_as=credit_as)], release=False)
        assert len(errors) == 1 and message in errors[0], (credit_as, errors)
    assert check_sources([with_(credit_as={"en": "© X", "sv": "© X"}, licence_as="CC BY")], release=False) == []
    for licence_as in ("CC BY-SA", "CC", "", 4):
        errors = check_sources([with_(licence_as=licence_as)], release=False)
        assert len(errors) == 1 and "licence_as" in errors[0], (licence_as, errors)
    assert check_sources([with_(licence="CC0-1.0", licence_as="CC0")], release=False) == []

    by_id = {s["id"]: s for s in load_sources(ROOT / "pipeline" / "sources.yml")}
    assert {k: s["dataset"] for k, s in by_id.items()} == {
        "city_lod1": "SBK 3D-Byggnader (LOD1) generaliserade", "city_stadsdelar": "Stadsdelar",
        "city_stadskarta": "Stadskarta", "raa_bebyggelse": "Bebyggelseregistret",
        "raa_old": "Bebyggelseregistret, äldre registret", "wikidata": "Wikidata", "osm": "OpenStreetMap",
        "lm_markhojd": "Markhöjdmodell Nedladdning", "lm_laser": "Laserdata Nedladdning, skog", "wikipedia": "Wikipedia",
        "samfundet_plaques": "Kulturhusskyltar", "openplaques": "Open Plaques",
        "stadsmuseet_br": "Stads- och byggnadsarkeologiskt register", "stadsarkivet_bygglov": "Bygglov 1875–1980",
        "stadsmuseet_photos": "Digitala Stadsmuseet, fotografier",
        "kulturnav": "KulturNav, Byggnader i Sverige", "stadsmuseet_inventories": "Byggnadsinventeringar",
        "stockholm_stages": "Hjorthagens utbyggnadsetapper", "metro_stations": "Tunnelbanestationer", "metro_track": "Tunnelbanans spår", "ferry_routes": "Båtlinjer"}
    assert {k: s["credit_as"]["sv"] for k, s in by_id.items() if "credit_as" in s} == {
        "city_lod1": "© Stockholms stad, Stadsbyggnadskontoret", "city_stadsdelar": "© Stockholms stad, Stadsbyggnadskontoret",
        "city_stadskarta": "© Stockholms stad, Stadsbyggnadskontoret", "wikidata": "Wikidatas bidragsgivare",
        "osm": "© OpenStreetMap-bidragsgivare", "lm_markhojd": "© Lantmäteriet", "lm_laser": "© Lantmäteriet",
        "wikipedia": "Wikipedias bidragsgivare",
        "samfundet_plaques": "Samfundet S:t Erik", "metro_stations": "Wikidata", "metro_track": "© OpenStreetMap-bidragsgivare",
        "ferry_routes": "© OpenStreetMap-bidragsgivare"}
    # the City's own credit (its licence answer, 2026-10-16): "© Stockholms stad, Stadsbyggnadskontoret, CC BY"
    assert {k for k, s in by_id.items() if "licence_as" in s} == {"city_lod1", "city_stadsdelar", "city_stadskarta"}
    # the cited years' two new sources (pipeline/cited.py): KulturNav CC0, the museum's inventories CC BY
    assert credit(by_id["kulturnav"]) == {"en": "KulturNav, Byggnader i Sverige: ArkDes, CC0, processed",
                                          "sv": "KulturNav, Byggnader i Sverige: ArkDes, CC0, bearbetad"}
    # ... "CC BY 4.0", as the museum's photos are credited (Digitala Stadsmuseet's field 590 "BY")
    assert credit(by_id["stadsmuseet_inventories"]) == {
        "en": "Byggnadsinventeringar: Stadsmuseet i Stockholm, CC BY 4.0, processed",
        "sv": "Byggnadsinventeringar: Stadsmuseet i Stockholm, CC BY 4.0, bearbetad"}
    # the City's Hjorthagen stage years (D63): facts read from its pages, nothing of theirs copied
    assert credit(by_id["stockholm_stages"]) == {
        "en": "Hjorthagens utbyggnadsetapper: Stockholms stad, facts only, processed",
        "sv": "Hjorthagens utbyggnadsetapper: Stockholms stad, endast fakta, bearbetad"}


def test_default_path_is_next_to_the_module(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # any working directory
    assert [s["id"] for s in load_sources()] == ["city_lod1", "city_stadsdelar", "city_stadskarta", "raa_bebyggelse",
                                                  "raa_old", "wikidata", "osm", "lm_markhojd", "lm_laser", "wikipedia",
                                                  "samfundet_plaques", "openplaques", "stadsmuseet_br",
                                                  "stadsarkivet_bygglov", "stadsmuseet_photos", "kulturnav", "stadsmuseet_inventories",
                                                  "stockholm_stages", "metro_stations", "metro_track", "ferry_routes"]


def test_release_fails_on_pending_sources():
    pending = with_(status="pending-O1")
    assert check_sources([pending], release=True) == ["demo: status pending-O1 is not allowed in a release"]
    assert check_sources([pending], release=False) == []


def test_release_names_each_pending_source():
    sources = [with_(id="a", status="pending-O1"), with_(id="b"), with_(id="c", status="pending-O1")]
    assert check_sources(sources, release=True) == [
        "a: status pending-O1 is not allowed in a release",
        "c: status pending-O1 is not allowed in a release",
    ]


def test_good_entry_passes_release():
    assert check_sources([GOOD], release=True) == []


@pytest.mark.parametrize("field", ["id", "url", "publisher", "product", "licence", "licence_url", "attribution",
                                   "status"])
def test_required_field_missing(field):
    errors = check_sources([with_(**{field: None})], release=False)
    assert any(f"missing field '{field}'" in e for e in errors), errors


@pytest.mark.parametrize("field", ["url", "publisher", "attribution"])
def test_required_field_empty(field):
    errors = check_sources([with_(**{field: "  "})], release=False)
    assert any(f"missing field '{field}'" in e for e in errors), errors


def test_licence_must_be_allowed_spdx():
    assert check_sources([with_(licence="CC-BY-NC-4.0")], release=False) == [
        "demo: licence 'CC-BY-NC-4.0' is not one of CC-BY-4.0, CC-BY-SA-4.0, CC0-1.0, LicenseRef-Facts, "
        "LicenseRef-Permission, LicenseRef-PublicDomain, ODbL-1.0"]
    for ok in ["CC-BY-4.0", "CC0-1.0", "ODbL-1.0", "CC-BY-SA-4.0"]:
        assert check_sources([with_(licence=ok)], release=False) == []


def test_licence_url_must_be_http():
    assert check_sources([with_(licence_url="creativecommons.org/licenses/by/4.0/")], release=False) == [
        "demo: licence_url must start with http:// or https://"]


@pytest.mark.parametrize("licence", ["CC-BY-4.0", "CC-BY-SA-4.0", "ODbL-1.0"])
def test_attribution_licences_need_modified(licence):
    assert check_sources([with_(licence=licence, modified=None)], release=False) == [
        f"demo: licence {licence} needs 'modified: true' or 'modified: false'"]
    assert check_sources([with_(licence=licence, modified="yes")], release=False) == [
        f"demo: licence {licence} needs 'modified: true' or 'modified: false'"]
    assert check_sources([with_(licence=licence, modified=False)], release=False) == []


def test_cc0_does_not_need_modified():
    assert check_sources([with_(licence="CC0-1.0", modified=None)], release=False) == []


@pytest.mark.parametrize("licence", ATTRIBUTION_LICENCES)
def test_attribution_must_contain_product(licence):
    marker = MARKERS[licence]
    assert check_sources([with_(licence=licence, attribution=f"© Example, {marker} (modified)")], release=False) == [
        "demo: attribution must contain the product name 'Demo product'"]
    assert check_sources([with_(licence=licence, attribution=f"Demo product, © Example, {marker} (modified)")],
                         release=False) == []


@pytest.mark.parametrize("licence", ATTRIBUTION_LICENCES)
def test_attribution_must_contain_licence_marker(licence):
    marker = MARKERS[licence]
    assert check_sources([with_(licence=licence, attribution="Demo product, © Example (modified)")],
                         release=False) == [f"demo: attribution must contain the licence marker '{marker}'"]
    assert check_sources([with_(licence=licence, attribution=f"Demo product, © Example, {marker} (modified)")],
                         release=False) == []


@pytest.mark.parametrize("licence, other", [("CC-BY-4.0", "CC BY-SA 4.0"), ("CC-BY-SA-4.0", "CC BY 4.0"),
                                            ("CC-BY-4.0", "ODbL"), ("ODbL-1.0", "CC BY 4.0")])
def test_attribution_marker_must_match_the_licence(licence, other):
    errors = check_sources([with_(licence=licence, attribution=f"Demo product, © Example, {other} (modified)")],
                           release=False)
    assert errors == [f"demo: attribution must contain the licence marker '{MARKERS[licence]}'"]


@pytest.mark.parametrize("licence", ATTRIBUTION_LICENCES)
def test_attribution_must_say_modified_when_modified(licence):
    marker = MARKERS[licence]
    error = ["demo: attribution must say 'modified' or 'bearbetad' because modified is true"]
    assert check_sources([with_(licence=licence, attribution=f"Demo product, © Example, {marker}")],
                         release=False) == error
    for word in ["modified", "Modified", "MODIFIED", "bearbetad", "Bearbetad"]:
        attribution = f"Demo product, © Example, {marker} ({word})"
        assert check_sources([with_(licence=licence, attribution=attribution)], release=False) == []


@pytest.mark.parametrize("licence", ATTRIBUTION_LICENCES)
def test_attribution_need_not_say_modified_when_unmodified(licence):
    attribution = f"Demo product, © Example, {MARKERS[licence]}"
    assert check_sources([with_(licence=licence, modified=False, attribution=attribution)], release=False) == []


def test_attribution_failures_are_separate_errors():
    assert check_sources([with_(attribution="© Example")], release=False) == [
        "demo: attribution must contain the product name 'Demo product'",
        "demo: attribution must contain the licence marker 'CC BY 4.0'",
        "demo: attribution must say 'modified' or 'bearbetad' because modified is true",
    ]


def test_cc0_attribution_is_free_text():
    assert check_sources([with_(licence="CC0-1.0", modified=None, attribution="Someone")], release=False) == []


def test_blank_attribution_is_only_reported_as_missing():
    assert check_sources([with_(attribution="  ")], release=False) == ["demo: missing field 'attribution'"]


def test_status_must_be_known():
    assert check_sources([with_(status="maybe")], release=False) == [
        "demo: status 'maybe' is not one of confirmed, pending-O1"]


def test_duplicate_ids():
    assert check_sources([GOOD, GOOD], release=False) == ["demo: duplicate id"]


def test_load_rejects_non_list(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text("id: demo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="list of sources"):
        load_sources(p)


def write_register(path, *entries):
    path.write_text(yaml.safe_dump(list(entries), allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(path)


def test_main_exit_codes_on_a_confirmed_register(tmp_path, capsys):
    register = write_register(tmp_path / "sources.yml", with_(id="a"), with_(id="b"))
    assert main(["--sources", register]) == 0
    assert main(["--sources", register, "--release"]) == 0
    assert "2 sources, 0 problems" in capsys.readouterr().out


def test_main_exit_codes_on_a_register_with_a_pending_source(tmp_path, capsys):
    register = write_register(tmp_path / "sources.yml", with_(id="a"), with_(id="b", status="pending-O1"))
    assert main(["--sources", register]) == 0
    assert "2 sources, 0 problems" in capsys.readouterr().out
    assert main(["--sources", register, "--release"]) == 1
    out = capsys.readouterr().out
    assert "b: status pending-O1 is not allowed in a release" in out
    assert "2 sources, 1 problems" in out


def test_main_exits_1_on_an_invalid_register(tmp_path, capsys):
    register = write_register(tmp_path / "sources.yml", with_(licence="CC-BY-NC-4.0"))
    assert main(["--sources", register]) == 1
    assert "demo: licence 'CC-BY-NC-4.0' is not one of" in capsys.readouterr().out


def test_main_defaults_to_the_register_next_to_the_module(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)  # any working directory; without --release the register passes whatever the statuses
    assert main([]) == 0
    assert ", 0 problems" in capsys.readouterr().out


def test_wikipedia_is_credited_like_the_other_sources():
    # The attribution reaches the About page; the pattern "Product, © publisher, licence (modified)"
    w = {s["id"]: s for s in load_sources()}["wikipedia"]
    assert w["attribution"] == "Wikipedia, © Wikipedia contributors, CC BY-SA 4.0 (bearbetad / modified)"


def test_the_permit_index_is_credited_with_permission_and_its_feature():
    # Stadsarkivet's written answer (O6) is the permission: its terms are required, and the credit says "used with
    # permission, processed" in both languages; it waits with city.FEATURES bygglov, and has no corner credit
    s = {x["id"]: x for x in load_sources(ROOT / "pipeline" / "sources.yml")}["stadsarkivet_bygglov"]
    assert check_sources([s], release=True) == []
    assert (s["licence"], s["feature"], s["status"]) == ("LicenseRef-Permission", "bygglov", "confirmed")
    assert "corner" not in s and "bygglov1875-1980" not in s["url"]      # About links the information page only
    assert credit(s) == {"en": "Bygglov 1875–1980: Stockholms stadsarkiv, used with permission, processed",
                         "sv": "Bygglov 1875–1980: Stockholms stadsarkiv, används med tillstånd, bearbetad"}
    assert check_sources([{**s, "terms": ""}], release=False) == [
        "stadsarkivet_bygglov: licence LicenseRef-Permission needs the permission's 'terms'"]
