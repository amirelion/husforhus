"""The City Museum's building-archaeology register (Task 19): s00_fetch_stadsmuseet against a recorded answer (no
network: requests is faked), the felling-year parser on the research note's three samples
(docs/research/2026-10-16-gamla-stan-ages.md §4, by BR number), the card's facts, the placement on footprints, and
s99's checks. The records here are trimmed copies of the register's answers with made-up designations and
addresses ("Exempel 12", "Exempelgatan"): no real property designation is written in a public file."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import requests
import shapely
from shapely.geometry import box, mapping

from pipeline import fetch, s00_fetch_stadsmuseet, s02_stadsmuseet, s03_tiles, s99_validate, stadsmuseet
from pipeline.sources import check_sources, credit, load_sources

API = "https://stadsarkeologisktregister.stockholm.se/api"
WFS = "https://stadsarkeologisktregister.stockholm.se/geoserver/sr/ows"
REPORT = "https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/DOK_1/SSM_DOK_{}.pdf.info"

# The three samples' felling sentences, as the register's descriptions write them (trimmed).
BR285 = ("Bjälktaket gav ett daterbart svar till fällningsår 1676  (plusminus 10 år). Takkonstruktionens delar "
         "daterades till 1686/1687.")
BR286 = "Av sex prover gav tre stycken fällningsåren 1642-1645, två prov gav äldre dateringar."
BR492 = ("Samtliga kunde dateras, med resultaten fällt efter 1486, fällt efter 1487, fällt efter 1464, fällt efter "
         "1488, fällt efter 1475, vintern 1596-1597 för två prov, vintern 1516-1517 (osäker), efter 1575.")

CATEGORIES = {"brCategories": [{"id": 1, "label": "Datering"}, {"id": 15, "label": "Dendrokronologi"},
                               {"id": 26, "label": "Bjälktak"}, {"id": 40, "label": "Källare"},
                               {"id": 49, "label": "1100-1400-talet"}, {"id": 51, "label": "1600-talet"}]}
LABELS = stadsmuseet.category_labels(CATEGORIES["brCategories"])


def rec(n, *, cats=(), desc="", y=(2006, 2006), report=True, address="Exempelgatan 1", designation="Exempel 12"):
    return {"id": n, "published": True, "year_earliest": y[0], "year_latest": y[1], "address": address,
            "property_denotation": designation, "description": desc, "digital_archive_link_exists": report,
            "categories": list(cats), **({"report_page": REPORT.format(n)} if report else {})}


# ---------- the fetch, against a recorded answer ----------

class FakeResponse:
    def __init__(self, body: bytes, status=200):
        self.content, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


RECORDED = {
    f"{API}/brInvestigations": {"brInvestigations": [
        {k: v for k, v in rec(285, desc=BR285).items() if k not in ("categories", "report_page")},
        {k: v for k, v in rec(492, desc=BR492, y=(1988, 1988)).items() if k not in ("categories", "report_page")}]},
    f"{API}/brCategories": CATEGORIES,
    f"{API}/brInvestigations/285": {"brInvestigations": rec(285, cats=[15, 51], desc=BR285)},
    f"{API}/brInvestigations/492": {"brInvestigations": rec(492, cats=[15, 26, 40, 49], desc=BR492, y=(1988, 1988))},
    WFS: {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"BRNummer": 285}, "geometry": mapping(box(0, 0, 10, 10))}]},
}


@pytest.fixture
def register(tmp_path, monkeypatch):
    """The register's recorded answers; every GET is recorded as (url, params, headers)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    monkeypatch.setattr(s00_fetch_stadsmuseet, "sleep", lambda s: None)
    calls, down = [], set()

    def get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        if url in down:
            raise requests.ConnectionError("the register does not answer")
        if url == stadsmuseet.ARCHIVE:     # Digitala Stadsmuseet: the report whose field 688 holds the number
            n = str(params["688"])
            return FakeResponse(json.dumps({"data": [{"href": f"/fotoweb/archives/5004-Dokument-och-publikationer/"
                                                              f"Dokument/DOK_1/SSM_DOK_{n}.pdf.info",
                                                      "metadata": {"688": {"value": [n]}}}]}).encode())
        return FakeResponse(json.dumps(RECORDED[url]).encode())

    monkeypatch.setattr(requests, "get", get)
    return calls, down


def test_fetch_caches_every_answer_with_the_projects_user_agent(register):
    calls, _ = register
    s00_fetch_stadsmuseet.main([])
    urls = [c[0] for c in calls]
    assert urls == [f"{API}/brInvestigations", f"{API}/brCategories", WFS, f"{API}/brInvestigations/285",
                    f"{API}/brInvestigations/492", stadsmuseet.ARCHIVE, stadsmuseet.ARCHIVE]
    reports = [c for c in calls if c[0] == stadsmuseet.ARCHIVE]
    assert [c[1]["688"] for c in reports] == [285, 492]
    assert all(c[2]["Accept"] == "application/vnd.fotoware.assetlist+json" for c in reports)
    assert stadsmuseet.report_pages(s00_fetch_stadsmuseet.read_report(492), 492) == [REPORT.format(492)]
    assert all(c[2]["User-Agent"] == "HusForHus/1.0 (+https://github.com/amirelion/husforhus)" for c in calls)
    wfs = next(c[1] for c in calls if c[0] == WFS)
    assert wfs["typeNames"] == "sr:v_area_br" and wfs["srsName"] == "EPSG:3011" and wfs["request"] == "GetFeature"
    assert len(s00_fetch_stadsmuseet.read_records()) == 2
    assert s00_fetch_stadsmuseet.read_record(492)["categories"] == [15, 26, 40, 49]
    assert str(s00_fetch_stadsmuseet.RAW) == "data/raw/stadsmuseet"
    # a second run asks nothing; --refresh asks again for everything
    calls.clear()
    s00_fetch_stadsmuseet.main([])
    assert calls == []
    s00_fetch_stadsmuseet.main(["--refresh"])
    assert len(calls) == 7


def test_fetch_keeps_the_cache_when_the_register_does_not_answer(register, capsys):
    calls, down = register
    s00_fetch_stadsmuseet.main([])
    down.add(f"{API}/brCategories")
    s00_fetch_stadsmuseet.main(["--refresh"])
    assert "keeping the cached" in capsys.readouterr().err
    assert s00_fetch_stadsmuseet.CATEGORIES.exists()


def test_fetch_refuses_an_answer_without_its_list(register, monkeypatch):
    calls, _ = register
    monkeypatch.setitem(RECORDED, f"{API}/brCategories", {"error": "maintenance"})
    monkeypatch.setattr(fetch, "TIMEOUT", (1, 1))
    with pytest.raises(SystemExit):
        s00_fetch_stadsmuseet.get(f"{API}/brCategories", {}, s00_fetch_stadsmuseet.CATEGORIES, "brCategories", False)
    assert not s00_fetch_stadsmuseet.CATEGORIES.exists()


# ---------- the facts ----------

def test_felling_year_on_the_research_notes_three_samples():
    assert stadsmuseet.felling_year(BR285) == 1676        # a tolerance keeps its year
    assert stadsmuseet.felling_year(BR286) is None        # a span of samples, 1642-1645
    assert stadsmuseet.felling_year(BR492) is None        # several, each "felled after"
    assert stadsmuseet.felling_year("Bjälkarna var fällda 1640.") == 1640
    assert stadsmuseet.felling_year("fällt efter 1488") is None
    assert stadsmuseet.felling_year("fällningsår 1676 (osäker)") is None
    assert stadsmuseet.felling_year("") is None and stadsmuseet.felling_year(None) is None


def test_facts_in_our_words_from_the_fields_and_categories():
    recs = [rec(285, cats=[15, 51], desc=BR285, y=(2006, 2006)),
            rec(492, cats=[15, 26, 40, 49], desc=BR492, y=(1988, 1988)),
            rec(150, cats=[49], y=(1971, 1971), report=False)]
    f = stadsmuseet.facts(recs, LABELS)
    assert f == {"medieval": True, "felled": [1676], "credit": "Stadsmuseet i Stockholm",
                 "inv": [{"from": 1971, "to": 1971}, {"from": 1988, "to": 1988, "report": REPORT.format(492)},
                         {"from": 2006, "to": 2006, "report": REPORT.format(285)}]}
    # a tree-ring record dated 1100-1400-talet dates timber, not walls
    assert "medieval" not in stadsmuseet.facts([recs[1]], LABELS)
    # a dendro category without one plain year states no felling; no years, no years on the card
    f = stadsmuseet.facts([rec(286, cats=[15], desc=BR286, y=(None, None))], LABELS)
    assert "felled" not in f and f["inv"] == [{"report": REPORT.format(286)}]
    # the museum's prose and the designation never reach the entry
    assert "Bjälktaket" not in json.dumps(f) and "Exempel" not in json.dumps(f)


# ---------- the placement ----------

def footprints():
    return gpd.GeoDataFrame({"gid": [0, 1, 2, 3]}, geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10),
                                                             box(30, 0, 40, 10), box(50, 0, 60, 10)], crs=3011)


TABLE = pd.DataFrame({"gid": [3, 2], "street": ["Exempelgatan", "Exempelgatan"], "number": ["3", "5"]})


def test_covered_by_the_share_thresholds():
    b = footprints()
    tree = shapely.STRtree(b.geometry.to_numpy())
    assert stadsmuseet.COVER == 0.5 and stadsmuseet.INSIDE == 0.5
    assert stadsmuseet.covered(box(0, 0, 15, 10), b, tree) == ([0, 1], True)       # gid 1 half inside: covered
    assert stadsmuseet.covered(box(0, 0, 14, 10), b, tree) == ([0], True)          # 40 %: not
    assert stadsmuseet.covered(box(31, 1, 33, 3), b, tree) == ([2], True)          # the investigated part of one
    assert stadsmuseet.covered(box(7, 0, 13, 20), b, tree) == ([], True)           # straddles two, covers none
    assert stadsmuseet.covered(box(100, 100, 110, 110), b, tree) == ([], False)
    assert stadsmuseet.covered(box(9.95, 0, 30.05, 10), b, tree)[0] == [1]          # a shared wall is no overlap


def test_place_by_polygon_then_address_else_ambiguous_or_unplaced():
    recs = [rec(1), rec(2), rec(3, address="Exempelgatan 3"), rec(4, address="Exempelgränd (Slottsbacken)"),
            rec(5, address="Okändgatan 9"), rec(6, address="Exempelgatan 3, 5")]
    polys = {1: box(0, 0, 16, 10), 2: box(7, 0, 13, 20), 5: box(100, 100, 110, 110)}
    placed = {p["id"]: (p["gids"], p["how"], p["why"].split(":")[0]) for p in
              stadsmuseet.place(recs, polys, footprints(), TABLE)}
    assert placed == {1: ([0, 1], "polygon", ""), 2: ([], "", "ambiguous"), 3: ([3], "address", ""),
                      4: ([], "", "ambiguous"), 5: ([], "", "unplaced"), 6: ([2, 3], "address", "")}


def test_build_counts_and_reviews_without_a_designation():
    recs = [rec(1, cats=[49]), rec(2), rec(3, address="Exempelgatan 3"), rec(5, address="Okändgatan 9")]
    polys = {1: box(0, 0, 16, 10), 2: box(7, 0, 13, 20)}
    cards, review, n = s02_stadsmuseet.build(recs, polys, LABELS, footprints(), TABLE)
    assert n == {"records": 4, "polygon": 1, "address": 1, "ambiguous": 1, "unplaced": 1, "takedown": 0}
    assert sorted(cards) == [0, 1, 3] and cards[0]["medieval"] is True
    assert [r.split("\t")[0] for r in review] == ["BR 2", "BR 5"]
    assert not any("Exempel 12" in r for r in review)
    assert "2 placed (1 by polygon, 1 by address) on 3 buildings, 1 ambiguous, 1 unplaced" in s02_stadsmuseet.summary(n, 3)
    cards, _, n = s02_stadsmuseet.build(recs, polys, LABELS, footprints(), TABLE, taken={0})
    assert 0 not in cards and n["takedown"] == 1


def test_designations_are_the_records_own_and_the_former_ones_they_name():
    recs = [rec(1, designation="Exempel 12", desc="Fastigheten f d Exempel 3, 4 och 9 vid Exempelgatan 1."),
            rec(2, designation="Prov 1")]
    d = stadsmuseet.designations(recs)
    assert {"exempel 12", "exempel 3", "prov 1"} <= d
    assert not any(x.startswith("exempelgatan") for x in d)


# ---------- the card and s99 ----------

def write_cards(out, cards):
    (out / "cards").mkdir(parents=True, exist_ok=True)
    (out / "cards" / "00.json").write_text(json.dumps({str(g): c for g, c in cards.items()}), encoding="utf-8")


def test_card_shards_never_put_the_section_on_a_private_house():
    df = pd.DataFrame({"gid": [0, 1], "name": ["", ""], "architects": [[], []], "raa_id": [None, None],
                       "private": [0, 1], "kategori": ["Allmän byggnad", "Allmän byggnad"], "ysrc": [0, 0]})
    br = stadsmuseet.facts([rec(1, cats=[49])], LABELS)
    cards = {int(g): c for shard in s03_tiles.card_shards(df, archaeology={0: br, 1: br}) for g, c in shard.items()}
    assert cards[0]["br"] == br and "br" not in cards.get(1, {})


def test_s99_checks_the_section(tmp_path):
    good = stadsmuseet.facts([rec(492, cats=[15, 49], desc=BR285, y=(1988, 1988))], LABELS)
    write_cards(tmp_path, {0: {"br": good}})
    assert s99_validate.check_archaeology(tmp_path, np.array([False, False])) == []
    write_cards(tmp_path, {0: {"br": good}, 1: {"br": {**good, "note": "x", "credit": "", "felled": [1676, 1600],
                                                        "inv": [{"from": 1800, "to": 1700, "report": "http://x"}]}}})
    errors = s99_validate.check_archaeology(tmp_path, np.array([True, False]))
    assert any("private house" in e for e in errors)
    assert any("fields other" in e for e in errors) and any("credit" in e for e in errors)
    assert any("felled" in e for e in errors) and any("years out of order" in e for e in errors)
    assert any("not an https link" in e for e in errors)


def test_s99_refuses_a_register_designation_in_a_shipped_file(tmp_path):
    raw = tmp_path / "raw" / "stadsmuseet"
    raw.mkdir(parents=True)
    raw.joinpath("investigations.json").write_text(json.dumps({"brInvestigations": [rec(1)]}), encoding="utf-8")
    props = s99_validate.register_designations(tmp_path)
    out = tmp_path / "web"
    write_cards(out, {0: {"name": "Huset i Exempel 12"}})
    assert any("property designation" in e for e in s99_validate.check_privacy(out, set(), props))
    write_cards(out, {0: {"br": stadsmuseet.facts([rec(1)], LABELS)}})
    assert s99_validate.check_privacy(out, set(), props) == []


def test_the_source_is_registered_with_its_permission():
    sources = load_sources()
    assert check_sources(sources, release=True) == []
    s = next(s for s in sources if s["id"] == "stadsmuseet_br")
    assert s["publisher"] == "Stadsmuseet i Stockholm" and s["product"] == "Stads- och byggnadsarkeologiskt register"
    assert s["terms"] == "written permission from Stadsmuseet, 2026-10-19: free use with the source credited"
    assert "@" not in json.dumps(s)
    c = credit(s)
    assert c["en"].startswith("Stads- och byggnadsarkeologiskt register: Stadsmuseet i Stockholm, used with permission")
    assert "används med tillstånd" in c["sv"]


def test_cached_designations_reads_the_fetch_cache_and_none_without_it(tmp_path):
    import json
    assert stadsmuseet.cached_designations(tmp_path) == set()
    raw = tmp_path / "raw" / "stadsmuseet"
    raw.mkdir(parents=True)
    (raw / "investigations.json").write_text(json.dumps({"brInvestigations": [
        {"property_denotation": "Skravelberget större 13", "description": ""}]}), encoding="utf-8")
    assert "skravelberget större 13" in stadsmuseet.cached_designations(tmp_path)


def test_an_excerpt_leaves_out_a_sentence_naming_a_register_designation():
    # A Wikipedia article titled with a designation the City's table does not hold (2026-10-20)
    from pipeline import wiki
    from pipeline.privacy import normalise
    text = ("Skravelberget större 13 är en kulturhistoriskt värdefull kontorsfastighet vid Nybrogatan 7 på Östermalm. "
            "Byggnaden stod färdig år 1911.")
    out = wiki.cut(text, designations={normalise("Skravelberget större 13")})
    assert "Skravelberget" not in out and "1911" in out


def test_report_pages_keep_only_items_whose_field_688_holds_the_number():
    # Digitala Stadsmuseet's answer to ?688=106: the query alone can return unrelated items too
    answer = {"data": [
        {"href": "/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/Medeltidsstaden/SSM_DOK_000252.pdf.info",
         "metadata": {"688": {"value": ["9", "106"]}}},
        {"href": "/fotoweb/archives/5004-Dokument-och-publikationer/Publikationer/SSMB_0013540_01.pdf.info",
         "metadata": {"5": {"value": "Sagerska målet"}}},
        {"href": "/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/X.pdf.info",
         "metadata": {"688": {"value": "1060"}}}]}
    assert stadsmuseet.report_pages(answer, 106) == [
        "https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/Medeltidsstaden/SSM_DOK_000252.pdf.info"]
    assert stadsmuseet.report_pages(None, 106) == [] and stadsmuseet.report_pages({"data": None}, 106) == []


def test_a_record_links_its_report_page_never_the_archives_search_address():
    r = rec(5)
    assert stadsmuseet.report_url(r) == REPORT.format(5)
    assert stadsmuseet.report_url({**r, "report_page": ""}) == ""
    assert stadsmuseet.report_url({**r, "report_page": stadsmuseet.ARCHIVE + "?BR=5"}) == ""
    assert stadsmuseet.report_url({**r, "digital_archive_link_exists": False}) == ""


def test_s99_takes_a_report_pages_file_number_for_what_it_is_but_still_catches_an_fnr_elsewhere(tmp_path):
    # Two report files are named by archive numbers that equal FNR keys by chance (2026-10-20)
    page = stadsmuseet.ARCHIVE + "Dokument/Ritningar/10091955.pdf.info"
    out = tmp_path / "web"
    write_cards(out, {0: {"br": {"inv": [{"from": 1990, "to": 1990, "report": page}], "credit": stadsmuseet.CREDIT}}})
    assert s99_validate.check_privacy(out, set(), set(), {10091955}) == []
    write_cards(out, {0: {"name": "Hus 10091955"}})
    assert any("FNR" in e for e in s99_validate.check_privacy(out, set(), set(), {10091955}))
