"""The cited years (pipeline/cited.py, pipeline/gamla_stan_years.csv): the table's rules, the year a row publishes
(the period rule decided on 2026-10-20), the s02 tier, the card's `yc` and s99's check_cited."""
import csv
import json
import re

import numpy as np
import pandas as pd
import pytest

from pipeline import cited, city, s02_years, s03_tiles, s14_search, s99_validate
from pipeline.codes import (EXACT, LONG, PERIOD, RANGE, SRC_CITED, SRC_CURATED, SRC_NONE, SRC_OSM, SRC_RAA,
                            SRC_WIKIDATA, UNKNOWN)
from tests import tinycity
from tests.test_s02_tiers import osm, run, wikidata
from tests.test_s02_years import buildings, landmark_at, no_raa, raa, rec, sq, X0, Y0

WP = "https://sv.wikipedia.org/w/index.php?oldid=55051795"
KN = "https://kulturnav.org/74ce2767-f09f-4bdf-b86e-ea22dbd632b6"
DOCS = "https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/"
INVENTORY = DOCS + "Byggnadsinventeringar/10043930.pdf.info"
REPORT = DOCS + "DOK_1/SSM_DOK_000624.pdf.info"
UUID = "2e389b81-54f2-48cc-b4ee-ae1285df2207"
RESULTS = "https://www.norradjurgardsstaden2030.se/resultat/etapp/"          # the City's stage pages (D63)
VAXER = "https://vaxer.stockholm/omraden/stadsutvecklingsomraden/norra-djurgardsstaden/i-hjorthagen/"
SHLIST = "https://www.stadsholmen.se/fastigheter/"     # AB Stadsholmen's property list (D64)


def row(**kw):
    r = {"key": UUID, "year_from": "1640", "year_to": "1649", "circa": "", "kind": "built", "source": "wikipedia_sv",
         "place": WP, "page": "", "quote": "Det uppfördes på 1640-talet", "confidence": "medium",
         "note": "A decade, in our words."}
    return {**r, **kw}


def table(*rows) -> pd.DataFrame:
    return pd.DataFrame([row(**r) for r in rows], columns=cited.COLUMNS, dtype=str)


def write_csv(path, *rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cited.COLUMNS)
        w.writeheader()
        w.writerows(row(**r) for r in rows)
    return path


# ---- the table's rules

def test_a_good_row_of_each_source_passes():
    assert cited.row_errors(row()) == []
    assert cited.row_errors(row(source="kulturnav", place=KN, quote="Uppförande, Utförandeår 1855–1858")) == []
    assert cited.row_errors(row(source="ssm_inventory", place=INVENTORY, page="3", quote="")) == []
    assert cited.row_errors(row(source="ssm_br", place=REPORT, page="1", quote="", kind="period", year_from="1000",
                                year_to="1520")) == []


def stage(**kw):
    """A Hjorthagen block's row: its building stage's move-in years from the City's stage page (D63)."""
    return row(**{"source": "stockholm_stage", "place": RESULTS + "vastra", "quote": "", "year_from": "2014",
                  "year_to": "2017", "confidence": "high", "note": "Västra stage, block Tyresta: move-in 2014–2017.",
                  **kw})


def test_a_stage_row_cites_the_city_s_stage_page_without_a_quote_or_a_page():
    # the stage's results page (Norra 1, Västra, Norra 2) or the City's Hjorthagen page (Brofästet's years)
    for place in (RESULTS + "norra-1", RESULTS + "vastra", RESULTS + "norra-2", VAXER):
        assert cited.row_errors(stage(place=place)) == [] and cited.is_place(place), place
    # the City's text is facts we put in our own words: never a quote, and no page number
    assert cited.row_errors(stage(quote="Färdigställt 2014–2017")) == [
        "quote is required for KulturNav and Wikipedia and empty for the City Museum, AB Stadsholmen and the City's "
        "stage pages"]
    assert cited.row_errors(stage(page="2")) == [
        "page is a page number for a City Museum PDF or an AB Stadsholmen fact sheet only"]
    # only Hjorthagen's stage pages: not another area's page on vaxer.stockholm, nor another site, nor plain http
    for place in ("https://vaxer.stockholm/omraden/stadsutvecklingsomraden/stadsutvecklingsomrade-hammarby-sjostad/",
                  "https://www.norradjurgardsstaden2030.se/resultat/bilaga/2025",
                  "http://www.norradjurgardsstaden2030.se/resultat/etapp/vastra", RESULTS + "vastra?x=1", WP):
        assert cited.row_errors(stage(place=place)) == ["place is not a stockholm_stage page"], place
    # a stage's move-in span is a construction window: the map's year is its last, a span (RANGE)
    assert cited.year_of("built", 2014, 2017) == (2017, RANGE)
    assert cited.SOURCES["stockholm_stage"]["credit"] == "stockholm_stages"


def sheet(**kw):
    """A row from AB Stadsholmen's fact sheet for the footprint's property (D64): the company's property list, the
    sheet's page, no quote."""
    return row(**{"source": "stadsholmen", "place": SHLIST, "page": "7", "quote": "", "kind": "rebuilt",
                  "year_from": "1780", "year_to": "1780", "note": "The sheet: raised by a storey in 1780.", **kw})


def test_a_stadsholmen_row_cites_the_property_list_with_its_page_and_no_quote():
    assert cited.row_errors(sheet()) == [] and cited.is_place(SHLIST)
    # never the sheet's PDF, on either host: its file name is the property designation (D17); nor a property's page
    # (named by it too), another host's list, plain http or a query. Exempel 1 is a made-up property, like the URLs
    for place in ("https://www.stadsholmen.se/app/uploads/2018/09/Exempel1-FAKTABLAD.pdf",
                  "https://stadsholmen.se/app/uploads/2018/09/Exempel1-FAKTABLAD.pdf",
                  "https://www.stadsholmen.se/fastigheter/exempel-1/", "https://stadsholmen.se/fastigheter/",
                  "http://www.stadsholmen.se/fastigheter/", SHLIST + "?omrade=gamla-stan", WP):
        assert cited.row_errors(sheet(place=place)) == [
            "place is not a stadsholmen page (AB Stadsholmen's property list, never a fact sheet's PDF: its file name "
            "is the property designation)"], place
        assert not cited.place_ok("stadsholmen", place), place
    # the sheets' text is never taken (the permission covers the years), and the page the year is on is required
    assert cited.row_errors(sheet(quote="Huset byggdes på 1780")) == [
        "quote is required for KulturNav and Wikipedia and empty for the City Museum, AB Stadsholmen and the City's "
        "stage pages"]
    for page in ("", "p7", "7a"):
        assert cited.row_errors(sheet(page=page)) == [
            "page is a page number for a City Museum PDF or an AB Stadsholmen fact sheet only"], page
    assert cited.SOURCES["stadsholmen"]["credit"] == "stadsholmen_faktablad"


def test_the_harvested_sheets_give_the_properties_they_cover(tmp_path):
    # data/raw/stadsholmen/MANIFEST.json, the research harvest: one entry per PDF; none on this machine is None.
    # Made-up properties, normalised as s99 compares a FASTIGHET
    assert cited.sheet_properties(tmp_path) is None
    f = tmp_path / cited.SHEETS
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"a.pdf": {"fastighet": "EXEMPEL  1"}, "b.pdf": {"fastighet": "Provgården 2"}, "c.pdf": {}}),
                 encoding="utf-8")
    assert cited.sheet_properties(tmp_path) == {"exempel 1", "provgården 2"}


def test_a_wikipedia_link_carries_its_oldid_alone():
    # D49: no article title ships (an article can be named after a property designation)
    titled = "https://sv.wikipedia.org/w/index.php?title=Kvarteret_Thisbe&oldid=55051795"
    assert cited.row_errors(row(place=titled)) == [
        "place is not a wikipedia_sv page (a revision by its oldid alone, no article title)"]
    assert not cited.place_ok("wikipedia_sv", titled) and cited.place_ok("wikipedia_sv", WP)


def test_an_inventory_must_be_one_of_the_cc_by_ones():
    # 10043887 is CC BY-NC-SA (field 590): usable only as a report the register links, never as an inventory
    nc = DOCS + "Byggnadsinventeringar/10043887.pdf.info"
    assert cited.row_errors(row(source="ssm_inventory", place=nc, page="3", quote="")) == [
        "place is not one of the City Museum's CC BY inventories (CC_BY_INVENTORIES)"]
    assert len(cited.CC_BY_INVENTORIES) == 32 and "10043930" in cited.CC_BY_INVENTORIES
    assert cited.row_errors(row(source="ssm_br", place=nc, page="3", quote="")) == []     # s99 checks the register


@pytest.mark.parametrize(("kw", "error"), [
    ({"quote": " ".join(["ord"] * 26)}, "quote is more than 25 words or one line"),
    ({"quote": ""}, "quote is required for KulturNav and Wikipedia and empty for the City Museum"),
    ({"source": "ssm_br", "place": REPORT, "page": "1"}, "quote is required for KulturNav and Wikipedia and empty for "
                                                          "the City Museum"),          # never the museum's text
    ({"page": "3"}, "page is a page number for a City Museum PDF or an AB Stadsholmen fact sheet only"),
    ({"confidence": "low"}, "confidence 'low' (low stays on hold)"),
    ({"kind": "period", "year_from": "1640", "year_to": "1640"}, "a period is a span, not one year"),
    ({"year_from": "999"}, "year_from..year_to is not a span inside 1000..2026"),
    ({"note": ""}, "note must be one line of 1 to 300 characters"),
    ({"key": UUID.upper()}, "key is not a lowercase UUID or oid:<n>"),
    ({"key": "oid:0"}, "key is not a lowercase UUID or oid:<n>"),
    ({"key": "oid:12a"}, "key is not a lowercase UUID or oid:<n>"),
    ({"kind": "rebuild"}, "kind 'rebuild'"),
    # a century or half-century is a period (≈, the 3/4 rule), never a first year shown as exact
    ({"year_from": "1600", "year_to": "1699"}, "a century, a half-century or a span over 100 years is kind period, "
                                               "not built"),
    ({"kind": "rebuilt_from_new", "year_from": "1650", "year_to": "1699"}, "a century, a half-century or a span over "
                                                                          "100 years is kind period, not "
                                                                          "rebuilt_from_new"),
    ({"year_from": "1600", "year_to": "1700"}, "is kind period, not built"),          # KulturNav's "1600–1700"
    ({"year_from": "1580", "year_to": "1690"}, "is kind period, not built"),          # over a century
    # "about" is for one year a source gives so ("omkring 1640"), never a period (approximate already) or a span
    ({"circa": "true"}, "circa is for one year"),
    ({"circa": "true", "kind": "period", "year_from": "1600", "year_to": "1699"}, "circa is for one year"),
    ({"circa": "yes", "year_to": "1640"}, "circa is true or empty"),
])
def test_a_malformed_row_names_its_fault(kw, error):
    assert any(error in e for e in cited.row_errors(row(**kw)))


@pytest.mark.parametrize(("a", "z"), [(1637, 1652), (1697, 1754), (1640, 1649), (1600, 1640), (1610, 1659)])
def test_a_construction_window_off_the_century_bounds_may_be_built(a, z):
    # some houses took decades to build; only a span a source gives as a century or half-century is refused
    assert cited.row_errors(row(year_from=str(a), year_to=str(z))) == []


def test_read_refuses_a_repeated_key_and_other_columns(tmp_path):
    with pytest.raises(ValueError, match="2 primary rows"):
        cited.read(write_csv(tmp_path / "t.csv", {}, {}))
    (tmp_path / "bad.csv").write_text("uuid,year\n", encoding="utf-8")
    with pytest.raises(ValueError, match="the columns are"):
        cited.read(tmp_path / "bad.csv")


def test_a_file_without_the_circa_column_is_read_with_it_empty(tmp_path):
    # the table before 2026-10-20's evening had no circa column
    path = write_csv(tmp_path / "t.csv", {}, {"key": "oid:50489018", "year_from": "1785", "year_to": "1785"})
    old = pd.read_csv(path, dtype=str, keep_default_na=False).drop(columns="circa")
    old.to_csv(path, index=False)
    t = cited.read(path)
    assert list(t.columns) == cited.COLUMNS and list(t.circa) == ["", ""]
    assert cited.row_errors(row(circa="true", year_to="1640")) == []                  # "about 1640"


def test_a_file_headed_uuid_is_read_with_its_first_column_as_key(tmp_path):
    # the table before 2026-10-20: every key a uuid, the column named so
    path = write_csv(tmp_path / "t.csv", {}, {"key": "oid:50489018", "year_from": "1785", "year_to": "1785"})
    text = path.read_text(encoding="utf-8")
    assert text.startswith("key,")
    path.write_text("uuid," + text.removeprefix("key,"), encoding="utf-8")
    t = cited.read(path)
    assert list(t.columns) == cited.COLUMNS and list(t.key) == [UUID, "oid:50489018"]
    assert list(pd.read_csv(cited.PATH, nrows=0).columns) == cited.COLUMNS       # the repo's file is migrated


# ---- two sourced readings are shown, not held (an either pair), and the rebuilds the sources name (decided 2026-10-20)

WP2 = "https://sv.wikipedia.org/w/index.php?oldid=53738008"


def either(a, z, **kw):
    return {"kind": "either", "year_from": str(a), "year_to": str(z), **kw}


def rebuilt(a, z=None, **kw):
    return {"kind": "rebuilt", "year_from": str(a), "year_to": str(z or a), **kw}


def also(a, z=None, **kw):
    return {"kind": "also", "year_from": str(a), "year_to": str(z or a), **kw}


def test_an_either_pair_and_rebuilt_rows_share_a_key(tmp_path):
    t = cited.read(write_csv(
        tmp_path / "t.csv", either(1785, 1785), either(1798, 1798, source="ssm_inventory", place=INVENTORY, page="3",
                                                       quote=""),
        rebuilt(1947, quote="byggdes om 1907 och 1947"), rebuilt(1907, quote="byggdes om 1907 och 1947"),
        {"key": "oid:50489018"}, {"key": "oid:50489018", **rebuilt(1859)},
        # one report, two pages that differ: two readings; and a medieval origin beside the 1600s
        {"key": "oid:7", **either(1000, 1520, source="ssm_br", place=REPORT, page="1", quote="")},
        {"key": "oid:7", **either(1600, 1699, source="ssm_br", place=REPORT, page="12", quote="")}))
    assert len(t) == 8
    f = cited.footprint(cited.by_key(t)[UUID])
    assert (f["kind"], f["year_from"], f["year_to"], f["source"]) == ("either", 1785, 1798,
                                                                      "wikipedia_sv or ssm_inventory")
    assert f["options"] == [{"a": 1785, "z": 1785, "s": "wikipedia_sv", "u": WP},
                            {"a": 1798, "z": 1798, "s": "ssm_inventory", "u": INVENTORY}]
    assert [o["a"] for o in f["rebuilt"]] == [1907, 1947]                       # earliest first
    f = cited.footprint(cited.by_key(t)["oid:50489018"])
    assert (f["kind"], f["year_from"], f["year_to"], f["options"]) == ("built", 1640, 1649, [])
    assert f["rebuilt"] == [{"a": 1859, "z": 1859, "s": "wikipedia_sv", "u": WP}]


@pytest.mark.parametrize(("rows", "error"), [
    ([either(1785, 1785)], "an either is exactly two rows on one key, not 1"),
    ([either(1785, 1785), either(1790, 1790, place=WP2), either(1798, 1798, source="kulturnav", place=KN)],
     "an either is exactly two rows on one key, not 3"),
    ([either(1785, 1785), either(1798, 1798, place=WP2), {}], "no built, rebuilt_from_new or period row beside it"),
    ([{}, {"kind": "period", "year_from": "1600", "year_to": "1699"}], "2 primary rows"),
    ([rebuilt(1907)], "a rebuilt or also row needs its footprint's primary row"),
    ([also(1804)], "a rebuilt or also row needs its footprint's primary row"),
    ([either(1785, 1785), either(1785, 1785, place=WP2)], "the two either rows give the same span"),
    ([either(1785, 1785), either(1798, 1798)], "the two either rows cite the same place"),
    # a rebuild comes after the house it rebuilds: after the primary's last year, not inside its span
    ([{}, rebuilt(1640)], "a rebuilt row starts by the primary's last year (1649)"),
    ([{}, rebuilt(1645)], "a rebuilt row starts by the primary's last year (1649)"),
    ([either(1785, 1785), either(1798, 1798, place=WP2), rebuilt(1790)], "starts by the primary's last year (1798)"),
    ([{}, rebuilt(1700), rebuilt(1700)], "two rebuilt rows give the same span"),
    ([{}, also(1804), also(1804, place=WP2)], "two also rows give the same span"),
])
def test_a_key_s_rows_must_belong_together(tmp_path, rows, error):
    # one primary row or an either pair per footprint, and rebuilt rows beside it: nothing else repeats a key
    with pytest.raises(ValueError, match=re.escape(error)):
        cited.read(write_csv(tmp_path / "t.csv", *rows))


def test_another_house_on_the_footprint_may_be_older_or_younger_than_the_primary(tmp_path):
    # Stortorget 18 and 20 (one footprint): the 1650 house dates it, the 1520s one is its also row; a rebuild after
    t = cited.read(write_csv(tmp_path / "t.csv", {"year_from": "1650", "year_to": "1650"}, also(1520, 1529),
                             also(1804, place=WP2), rebuilt(1905)))
    f = cited.footprint(cited.by_key(t)[UUID])
    assert (f["kind"], f["year_from"], cited.footprint_year(f)) == ("built", 1650, (1650, EXACT))
    assert [(o["a"], o["z"]) for o in f["also"]] == [(1520, 1529), (1804, 1804)]
    assert [(o["a"], o["z"]) for o in f["rebuilt"]] == [(1905, 1905)]


def o_(a, z):
    return {"a": a, "z": z}


@pytest.mark.parametrize(("p", "q", "want"), [
    ((1785, 1785), (1798, 1798), ((1785 + 1798) // 2, PERIOD)),   # both in Frihetstid & Gustavian (1719–1809)
    ((1630, 1639), (1640, 1649), ((1630 + 1649) // 2, PERIOD)),   # the 1630s or the 1640s: Stormaktstiden
    ((1675, 1675), (1680, 1689), ((1675 + 1689) // 2, PERIOD)),   # Slottsbacken 6
    # each reading counts the same, however long its span: a medieval reading (1000–1520, 521 years of FLOOR_YEAR's
    # placeholder) no longer outweighs the other. Medieval or the 1600s: 100% and 11% before 1611, so no colour
    ((1000, 1520), (1600, 1699), (0, UNKNOWN)),
    ((1000, 1520), (1780, 1780), (0, UNKNOWN)),                   # medieval or 1780: the map takes no side
    # Gåsgränd 4: medieval, or the 1500s to the mid-1600s (111 of 150 years before 1611): 87% on average, so
    # "Medieval & early Vasa"; no earlier bound, so it stands on the timeline by the overlap's end, 1610
    ((1000, 1520), (1500, 1649), (1610, PERIOD)),
    ((1580, 1580), (1650, 1659), (0, UNKNOWN)),                   # one reading in each period: no colour
])
def test_an_either_pair_takes_the_period_rule_on_its_two_readings_each_counting_the_same(p, q, want):
    assert cited.year_of("either", min(p[0], q[0]), max(p[1], q[1]), [o_(*p), o_(*q)]) == want
    with pytest.raises(ValueError, match="needs its two readings"):
        cited.year_of("either", min(p[0], q[0]), max(p[1], q[1]))


def test_a_key_is_a_uuid_or_the_oid_of_a_footprint_without_one(capsys):
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("", "Flerbostadshus", sq(1)), ("", "Flerbostadshus", sq(2)))
    b["oid"] = pd.array([5001, 5002, 5003], dtype="int64")
    assert cited.footprints(["u0", "oid:5002", "oid:9999", "u9"], b) == {"u0": [0], "oid:5002": [1], "oid:9999": [],
                                                                         "u9": []}
    assert cited.footprints(["oid:5002"], b.drop(columns="oid")) == {"oid:5002": []}     # a build without oids
    t = table({"key": "oid:5003", "year_from": "1643", "year_to": "1643"}, {"key": "oid:9999"})
    assert cited.missing(t, b) == ["oid:9999"]
    r = cited.rows(t, b)
    assert list(r.index) == [2] and (r.year[2], r.yflag[2]) == (1643, EXACT)
    assert "oid:9999: its footprint is not among these buildings" in capsys.readouterr().err
    b["oid"] = pd.array([5001, 5003, 5003], dtype="int64")
    with pytest.raises(cited.Refused, match="keys on several footprints"):
        cited.rows(t, b)


def test_two_keys_on_one_footprint_and_an_oid_key_beside_a_uuid_are_refused():
    # the second key's row would overwrite the first's year and card without a word (the review of 2026-10-20)
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("", "Flerbostadshus", sq(1)))
    b["oid"] = pd.array([5001, 5002], dtype="int64")
    t = table({"key": "u0", "year_from": "1640", "year_to": "1640"}, {"key": "oid:5001", "year_from": "1700",
                                                                      "year_to": "1700"})
    with pytest.raises(cited.Refused, match=re.escape("keys ['u0', 'oid:5001'] name one footprint (gid 0)")):
        cited.rows(t, b)
    # an oid only for a footprint the City gives no UUID; its own key is the UUID
    with pytest.raises(cited.Refused, match=re.escape("oid:5001 names a footprint the City gives a UUID (u0)")):
        cited.rows(table({"key": "oid:5001"}), b)
    assert cited.clashes(cited.footprints(["u0", "oid:5002"], b), b) == []
    # and the card is left alone: neither key's `yc` (s99 fails the build in any case)
    df = pd.DataFrame({"gid": [0, 1], "uuid": ["u0", ""], "oid": [5001, 5002], "ysrc": [SRC_CITED, SRC_NONE]})
    shards = [{}]
    assert cited.cards(shards, df, t, np.zeros(2, bool)) == 0 and shards == [{}]


def test_the_repo_table_reads_and_holds_the_decided_rows():
    t = cited.read()
    t = t[t.source != "stockholm_stage"]           # Gamla stan and Riddarholmen (Hjorthagen's stages: the next test)
    keys = cited.by_key(t)
    assert (len(t), len(keys)) == (410, 188)
    # Vindragarlagets hus was the wrong house (its record is the next footprint, which RAÄ dates); Mälartorget 15 is
    # held (two building phases on one footprint): docs/research/2026-10-20-gamla-stan-years.md. Held on the review's
    # answers of 2026-10-20 too: Själagårdsgatan 5, Köpmangatan 22, the house behind Kindstugatan 11 and the
    # no-address house at Västerlånggatan (oid 50482216); and Baggensgatan 19, whose report cannot confirm its cellar
    # is medieval. Själagårdsgatan 19, held then, is dated since 2026-10-23 by AB Stadsholmen's sheet (D64)
    assert not t.key.str.startswith(("116f5662", "2f06bb6a", "cc821610", "fa5783d0", "ffd9aa36", "oid:50482216",
                                     "55f7943a")).any()
    assert set(t.source[t.key.str.startswith("4ff97ad1")]) == {"stadsholmen"}
    # a dated medieval cellar is a medieval origin (the review of 2026-10-20: one rule for the cellar-only cards):
    # Skottgränd 1, Skottgränd 7, Stora Nygatan 34 and Österlånggatan 35 ship like Skomakargatan 30, and Funckens
    # Gränd 2's medieval cellar is its origin, its 1627 anchors a rebuild
    for k in ("8abc89ca", "f71eaa09", "8721e9ad", "723eda8a", "2fa43e0f", "f60b0c7d"):
        f = cited.footprint(next(rs for key, rs in keys.items() if key.startswith(k)))
        assert f["kind"] == "period" and f["year_to"] <= 1520 and cited.footprint_year(f)[1] == PERIOD, k
    # Ignatiigränd 2: the museum's medieval walls are its origin; Wikipedia's 1600s and 1906 are rebuilds
    ignatii = cited.footprint(keys["4dc27df6-8423-454a-987f-f283dec6e53d"])
    assert (ignatii["kind"], ignatii["year_from"], ignatii["year_to"]) == ("period", 1000, 1520)
    assert [(o["a"], o["z"]) for o in ignatii["rebuilt"]] == [(1600, 1699), (1906, 1906)]
    # where two sources differ both readings are shown (Gåsgränd 4, Slottsbacken 6, and where AB Stadsholmen's sheet
    # differs from Wikipedia: Munkbrogatan 11, Köpmanbrinken 4, Österlånggatan 34); Stortorget 18 and 20 are two
    # houses on one footprint, not two readings: the card is Schantzska huset's (its name, photo and article), so its
    # 1650 dates it and the 1520s Seyfridtz house is the other house; so too Kammarrätten's house beside the Sparre
    # palace, and the old national archive beside the Stenbock palace
    assert sorted(k[:8] for k, rs in keys.items() if cited.footprint(rs)["kind"] == "either") == [
        "2a22d390", "33154fc2", "36232e6d", "94bb3a36", "f6acf0c5"]
    stortorget = cited.footprint(keys["3b1e01bd-52cb-45e1-8eb0-79f09a1928d4"])
    assert (stortorget["kind"], stortorget["year_from"]) == ("built", 1650)
    assert [(o["a"], o["z"], o["s"]) for o in stortorget["rebuilt"]] == [(1861, 1861, "stadsholmen"),
                                                                          (1904, 1905, "stadsholmen")]
    assert [(o["a"], o["z"]) for o in stortorget["also"]] == [(1520, 1529)]
    sparre = cited.footprint(keys["de5a1bde-c116-48c0-b144-fd1a5c243b8b"])
    assert ([o["a"] for o in sparre["rebuilt"]], [o["a"] for o in sparre["also"]]) == ([1807], [1804])
    stenbock = cited.footprint(keys["d7d96f2a-6194-447d-a066-196367589456"])
    assert [(o["a"], o["z"], o["s"]) for o in stenbock["also"]] == [(1887, 1890, "kulturnav")]
    # no span ships an end year its source does not give: after 1762 is the 1760s, shortly after 1685 the 1680s (one
    # of Köpmanbrinken 4's two readings)
    for k, want in (("a1eba477", (1760, 1769)), ("f6acf0c5", (1680, 1689)), ("eaac7398", (1675, 1699))):
        rs = next(rs for key, rs in keys.items() if key.startswith(k))
        assert want in {(int(r["year_from"]), int(r["year_to"])) for r in rs if r["kind"] not in cited.LATER}, k
    # a source's "about one year" says so on the card
    assert sorted(t.key[t.circa == "true"].str[:8]) == ["0796a12d", "37cdb69f", "43d457bd", "7062f8d2", "71140b72",
                                                        "d6e7c50c", "deff337f", "e816107b", "eaac7398"]
    brandenburgska = t[t.key.str.startswith("e029fefa")].iloc[0]
    assert (brandenburgska.year_from, brandenburgska.year_to, brandenburgska.kind, brandenburgska.place) == (
        "1640", "1649", "built", "https://sv.wikipedia.org/w/index.php?oldid=55051687")
    assert set(t.source) <= set(cited.SOURCES) and not t.place.str.contains("title=").any()
    # Österlånggatan 9 cites the museum's report itself (its summary, p. 12), not the Wikipedia article that quotes it
    osterlanggatan9 = t[t.key.str.startswith("3643fddd")].iloc[0]
    assert (osterlanggatan9.source, osterlanggatan9.page, osterlanggatan9.quote) == ("ssm_br", "12", "")
    assert osterlanggatan9.place.endswith("/Byggnadshistoriska%20rapporter/SSMB_0027901_01.pdf.info")
    # every footprint's period (or either pair) is coloured by one map period but six: Funckens Gränd 1's "the
    # beginning of the 1600s" (1600–1624), and the late 1500s to the mid-1600s at Kindstugatan 3 (1580–1649) straddle
    # 1610/1611, as do two early-1600s houses AB Stadsholmen's sheets date (Järntorgsgatan 4 and the courtyard house at
    # Trädgårdstvärgränd 1); and two either pairs fall in two periods (Munkbrogatan 11, 1778 or 1872; Köpmanbrinken 4,
    # medieval or the 1680s), so they have no colour and their cards give the span or the two readings (s02 lists them,
    # cited_no_period). Österlånggatan 34's 1895 or 1898 lie in one period, which colours it
    fs = {k[:8]: cited.footprint(rs) for k, rs in keys.items()}
    unplaced = [k for k, f in fs.items() if cited.footprint_year(f)[1] == UNKNOWN]
    assert sorted(unplaced) == ["0796a12d", "30f86dd2", "5cb0834f", "94bb3a36", "bcc747db", "f6acf0c5"]
    assert cited.footprint_year(fs["33154fc2"])[1] == PERIOD


def test_the_repo_table_s_hjorthagen_rows_give_each_block_its_stage_s_move_in_years():
    # D63: the City's four finished housing stages in Hjorthagen, one built row per footprint whose block is in one,
    # keyed by uuid, its span the stage's move-in years and its link the stage's page
    t = cited.read()
    h = t[t.source == "stockholm_stage"]
    spans = {RESULTS + "norra-1": ("2012", "2014"), RESULTS + "vastra": ("2014", "2017"),
             RESULTS + "norra-2": ("2016", "2017"), VAXER: ("2018", "2020")}
    assert h.place.value_counts().to_dict() == {RESULTS + "norra-1": 22, VAXER: 18, RESULTS + "vastra": 17,
                                                RESULTS + "norra-2": 15}
    assert all(spans[p] == (a, z) for p, a, z in zip(h.place, h.year_from, h.year_to))
    assert set(h.kind) == {"built"} and not h.quote.any() and not h.page.any() and not h.circa.any()
    assert h.key.str.fullmatch(cited.UUID.pattern).all() and h.key.is_unique and not h.key.isin(t.key[t.source !=
                                                                                                       "stockholm_stage"]).any()
    # Brofästet's block list may be incomplete, so its rows are medium; so are a non-home and Padjelanta (the research
    # spells it Padjelanda)
    assert set(h.confidence[h.place == VAXER]) == {"medium"}
    assert (h.confidence == "medium").sum() == 20
    # the Backåkra house Wikidata dates 2019 keeps its year (inside its stage's span): no row on it
    assert "2ffb531e-914f-4986-aae7-d85b8bf0b809" not in set(h.key)
    # Kvarteret Tyresta (Lövängsgatan 12–14, Slåttervallsgatan 3–5) is in Västra
    tyresta = h[h.key == "089d0de8-13f8-4430-8225-851e33d97c50"].iloc[0]
    assert (tyresta.place, tyresta.year_from, tyresta.year_to) == (RESULTS + "vastra", "2014", "2017")
    assert all(cited.footprint_year(cited.footprint(rs))[1] == RANGE for rs in cited.by_key(h).values())


def test_the_repo_table_s_stadsholmen_rows_link_the_property_list_with_their_page():
    # D64: AB Stadsholmen's fact sheets for Gamla stan, 159 rows on 60 footprints, 27 of them dated by no row before;
    # each links the company's property list, never the sheet's PDF (named by the designation), with the sheet's page
    # and no quote
    t = cited.read()
    sh = t[t.source == "stadsholmen"]
    assert (len(sh), sh.key.nunique()) == (159, 60)
    assert set(sh.place) == {SHLIST} and sh.page.str.fullmatch(r"\d+").all() and not sh.quote.any()
    assert len(set(sh.key) - set(t.key[t.source != "stadsholmen"])) == 27
    assert sh.kind.value_counts().to_dict() == {"rebuilt": 120, "period": 17, "also": 8, "built": 7,
                                                "rebuilt_from_new": 4, "either": 3}
    keys = cited.by_key(t)
    # Suckiska huset (Österlånggatan 37): the sheet's new house of 1662 over medieval cellars, which the block article
    # gives no year of its own (a medieval cellar under a house a source dates as new gives way to it, as at
    # Kindstugatan 3); the article's later facade and its 1960s flats stay
    suckiska = cited.footprint(keys["c7a6716f-fb86-4a5d-a3fd-009c66e90c80"])
    assert (suckiska["kind"], suckiska["year_from"], suckiska["source"]) == ("rebuilt_from_new", 1662, "stadsholmen")
    assert [(o["a"], o["z"], o["s"]) for o in suckiska["rebuilt"]] == [
        (1750, 1799, "wikipedia_sv"), (1959, 1959, "stadsholmen"), (1960, 1970, "wikipedia_sv")]
    # where a sheet dates a medieval cellar and never says the older house went, the house's origin is medieval and
    # its 1600s house a rebuild, as at Funckens gränd 2 (the two joined houses at Järntorget, Göran Hälsinges gränd 5)
    for k, rebuilt in (("40b2eb9f", [(1669, 1671), (1778, 1778)]), ("c22d2284", [(1600, 1699), (1740, 1756)]),
                       ("757a72cf", [(1650, 1699)])):
        f = cited.footprint(next(rs for key, rs in keys.items() if key.startswith(k)))
        assert (f["kind"], f["year_from"], f["year_to"]) == ("period", 1000, 1520), k
        assert [(o["a"], o["z"]) for o in f["rebuilt"]] == rebuilt, k
    # Köpmanbrinken 4: Wikipedia's new house of the 1680s, or the sheet's older house with medieval walls in its own
    # front; Österlånggatan 34: Wikipedia's 1895, or the sheet's 1898
    kopmanbrinken = cited.footprint(keys["f6acf0c5-1b43-4dfd-bc1d-4cdb6cdb9d86"])
    assert [(o["a"], o["z"], o["s"]) for o in kopmanbrinken["options"]] == [(1000, 1520, "stadsholmen"),
                                                                            (1680, 1689, "wikipedia_sv")]
    osterlanggatan34 = cited.footprint(keys["33154fc2-44a8-4d85-8845-75a713ec2d9d"])
    assert [(o["a"], o["s"]) for o in osterlanggatan34["options"]] == [(1895, "wikipedia_sv"), (1898, "stadsholmen")]
    assert [o["a"] for o in osterlanggatan34["rebuilt"]] == [1972]
    # Österlånggatan 10: the sheet's 1632 is the museum card's 1600s rebuild, one row
    osterlanggatan10 = cited.footprint(keys["9ef9f4cb-9454-446b-b631-375b44ea383f"])
    assert [(o["a"], o["z"], o["s"]) for o in osterlanggatan10["rebuilt"]] == [
        (1632, 1632, "stadsholmen"), (1760, 1761, "stadsholmen"), (1970, 1974, "stadsholmen")]
    # a renovation that changes no structure or exterior gets no row: Västerlånggatan 37's 1940s refit, for one, is
    # gone, and Västerlånggatan 77 keeps only its 1850 rebuild of the sheet's
    assert not sh.key.str.startswith("70810a4d").any()
    assert list(sh.year_from[sh.key.str.startswith("1e8a8f4c")]) == ["1850"]
    # Munkbrogatan 11: the sheet's works of 1778, or Wikipedia's 1872; the block's 1971–73 rebuild stays
    munkbrogatan = cited.footprint(keys["94bb3a36-fbb5-44b8-ace1-01af09012e3b"])
    assert [(o["a"], o["s"]) for o in munkbrogatan["options"]] == [(1778, "stadsholmen"), (1872, "wikipedia_sv")]
    assert [(o["a"], o["z"]) for o in munkbrogatan["rebuilt"]] == [(1971, 1973)]
    # Helga Lekamens gränd 5: the 1978 memo's undated later top storey is the sheet's raising of 1758, one row
    helga = cited.footprint(keys["30b313a2-7702-47ef-a1ac-f35ab985fa96"])
    assert [(o["a"], o["z"], o["s"]) for o in helga["rebuilt"]] == [(1758, 1758, "stadsholmen")]
    assert [(o["a"], o["z"]) for o in helga["also"]] == [(1650, 1699)]
    # one row relies on a neighbour's sheet, and its note says so (the place cannot: it is the list)
    neighbour = sh[sh.key.str.startswith("9ef9f4cb") & (sh.year_from == "1970")].iloc[0]
    assert "neighbour's sheet" in neighbour.note


def test_plain_reads_wikitext_as_its_reader_sees_it():
    text = ("'''Huset''' [[uppförande|uppfördes]] på [[1640-talet]]<ref name=\"a\">{{Webbref|url=x}}</ref> av "
            "{{small|{{nowrap|en}}}}murmästaren")
    assert cited.plain(text) == "Huset uppfördes på 1640-talet av murmästaren"


def test_a_quote_the_article_relays_from_another_work_is_found():
    # An article that quotes a report: those words are the report's, not Wikipedia's (2026-10-20, Österlånggatan 9)
    text = ("Huset har ett välvt källarplan.\n\nEnligt [[Stockholms stadsmuseum|stadsmuseets]] rapport från 2009 är "
            "huset ”ett exempel på hur man byggde förr, kanske på 1500-talet”.<ref>Rapport</ref> Fasaden är putsad."
            "\n\nDet kallas ”Gula huset” och byggdes på 1640-talet.")
    assert cited.relayed(text, "ett exempel på hur man byggde förr")
    assert cited.relayed(text, "byggde förr, kanske på 1500-talet”. Fasaden")      # half in the quotation
    assert not cited.relayed(text, "Fasaden är putsad")
    # a quotation wholly inside the row's quote (a house's name in ”…”) is the article's own sentence
    assert not cited.relayed(text, "Det kallas ”Gula huset” och byggdes på 1640-talet.")
    assert not cited.relayed(text, "byggdes på 1640-talet")
    for marks in ('""', "“”", "„“", "»»", "«»"):
        assert cited.relayed(f"Rapporten säger {marks[0]}huset är från 1600-talet{marks[1]}.", "huset är från 1600")


def kn_entry(dataset=cited.KULTURNAV_DATASET, licence=cited.KULTURNAV_CC0, events=(("Uppförande", "1600-Y", "1700-Y"),
                                                                                   ("Annat (105)", "1966-Y", "1968-Y"))):
    """A KulturNav entry's JSON as kulturnav.org/<uuid>.json shapes it, cut to what the network test reads."""
    def span(a, z):
        return [{"value": {"properties": {"timespan.start": [{"value": a}], "timespan.end": [{"value": z}]}}}]
    return {"properties": {
        "entity.dataset": [{"valueType": "ENTITY_REFERENCE", "value": dataset}],
        "superconcept.license": [{"valueType": "ENTITY_REFERENCE", "value": licence}],
        "construction.activity": [{"value": {"caption": {"sv": c}, "properties": {"event.timespan": span(a, z)}}}
                                  for c, a, z in events]}}


def test_a_kulturnav_entry_is_read_for_its_dataset_licence_and_construction_years_alone():
    assert cited.kulturnav_entry(kn_entry()) == {"dataset": cited.KULTURNAV_DATASET, "licence": cited.KULTURNAV_CC0,
                                                 "built": [(1600, 1700)]}      # never the rebuild's 1966–1968
    assert cited.kulturnav_entry(kn_entry(events=[("Uppförande", "1855?-Y", "1858-Y")]))["built"] == [(1855, 1858)]
    other = cited.kulturnav_entry(kn_entry(dataset="00000000-0000-4000-8000-000000000000", licence="x", events=[]))
    assert other == {"dataset": "00000000-0000-4000-8000-000000000000", "licence": "x", "built": []}
    assert kulturnav_faults(row(source="kulturnav", place=KN, year_from="1600", year_to="1699", kind="period",
                                quote="Uppförande, Utförandeår 1600–1700, Uppskattat årtal"), kn_entry()) == []
    # a mistyped row, a quote another event's years would satisfy, an entry of another dataset or licence
    assert kulturnav_faults(row(source="kulturnav", place=KN, year_from="1600", year_to="1689", kind="period",
                                quote="Uppförande, Utförandeår 1600–1700"), kn_entry()) == ["row's years"]
    assert kulturnav_faults(row(source="kulturnav", place=KN, year_from="1966", year_to="1968",
                                quote="Utförandeår 1966–1968"), kn_entry()) == ["quote's years", "row's years"]
    assert kulturnav_faults(row(source="kulturnav", place=KN, year_from="1600", year_to="1699", kind="period",
                                quote="Utförandeår 1600–1700"), kn_entry(licence="x")) == ["dataset or licence"]


def kulturnav_faults(r: dict, entry: dict) -> list[str]:
    """What the network test finds wrong with a KulturNav row against its entry: the entry is not ArkDes' CC0 dataset
    (the credit every KulturNav row carries); the quote's years are not a construction event's; the row's are not
    (KulturNav's "1600–1700" may be read as the 1600s, 1600–1699)."""
    e = cited.kulturnav_entry(entry)
    faults = []
    if (e["dataset"], e["licence"]) != (cited.KULTURNAV_DATASET, cited.KULTURNAV_CC0):
        faults.append("dataset or licence")
    ys = tuple(int(y) for y in re.findall(r"\d{4}", r["quote"]))
    if not any(ys == (f, t) or (f == t and ys == (f,)) for f, t in e["built"]):
        faults.append("quote's years")
    a, z = int(r["year_from"]), int(r["year_to"])
    if not any((a, z) == (f, t) or ((a, z) == (f, t - 1) and t % 100 == 0) for f, t in e["built"]):
        faults.append("row's years")
    return faults


@pytest.mark.network
def test_every_quote_is_in_its_revision_and_every_kulturnav_year_in_its_entry():
    # The repo's table against the live sources: a Wikipedia revision never changes (oldid), a KulturNav entry can.
    # A Wikipedia quote must be the article's own words (not inside quotation marks); a KulturNav row's entry must be
    # ArkDes' CC0 dataset, its construction event's years the quote's and the row's
    import time

    import requests
    from pipeline.fetch import UA
    missing, lagged = [], []
    for k, r in enumerate(cited.read().to_dict("records")):
        if r["source"] not in ("wikipedia_sv", "kulturnav") or (r["source"] == "wikipedia_sv" and lagged):
            continue
        if k:
            time.sleep(1.0)                              # polite pacing
        if r["source"] == "wikipedia_sv":
            oldid = r["place"].rsplit("=", 1)[1]
            for attempt in range(4):
                got = requests.get("https://sv.wikipedia.org/w/api.php", headers=UA, timeout=60, params={
                    "action": "query", "prop": "revisions", "revids": oldid, "rvprop": "content", "rvslots": "main",
                    "format": "json", "formatversion": "2", "maxlag": "5"})
                answer = got.json()
                if (answer.get("error") or {}).get("code") != "maxlag":
                    break
                # a lagging server asks bots to wait (Wikimedia's maxlag etiquette): wait as asked, then longer
                wait = got.headers.get("Retry-After", "5")
                time.sleep(min(float(wait) if wait.isdigit() else 5.0, 30.0) + 10.0 * attempt)
            else:
                lagged.append(oldid)                     # the rest of Wikipedia waits for another run; KulturNav goes on
                continue
            wikitext = answer["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
            if " ".join(r["quote"].split()) not in cited.plain(wikitext):
                missing.append((r["key"][:8], oldid, "not in the revision"))
            elif cited.relayed(wikitext, r["quote"]):
                # inside quotation marks: the article quotes another work (the City Museum's, say); cite that instead
                missing.append((r["key"][:8], oldid, "a quotation the article relays, not Wikipedia's words"))
        else:
            entry = requests.get(r["place"] + ".json", headers=UA, timeout=60).json()
            if faults := kulturnav_faults(r, entry):
                missing.append((r["key"][:8], r["place"], faults))
    assert missing == []
    if lagged:
        pytest.skip(f"Wikipedia's database servers stayed lagged (maxlag) from revision {lagged[0]} on: the KulturNav "
                    "rows and the revisions before it passed; try the rest again later")


# ---- the year a row publishes

@pytest.mark.parametrize(("kind", "a", "z", "want"), [
    ("built", 1640, 1649, (1640, RANGE)),          # a decade: its start, the card reads "1640s"
    ("built", 1855, 1858, (1858, RANGE)),          # a short span: the completion year
    ("built", 1643, 1643, (1643, EXACT)),
    ("built", 1697, 1754, (1697, LONG)),           # a long construction window: the first year (a century is a period)
    ("rebuilt_from_new", 1854, 1854, (1854, EXACT)),
    # periods: the map period holding at least 3/4 of the span, the middle of that overlap
    ("period", 1300, 1399, ((1300 + 1399) // 2, PERIOD)),   # all in "Medieval & early Vasa" (–1610)
    # no earlier bound than FLOOR_YEAR (medieval): it stood by the overlap's end, never at 1260, the midpoint of a
    # placeholder, before the city's church
    ("period", 1000, 1520, (1520, PERIOD)),
    ("period", 1000, 1599, (1599, PERIOD)),
    ("period", 1600, 1699, ((1611 + 1699) // 2, PERIOD)),   # 89 of 100 years in Stormaktstiden (1611–1718)
    ("period", 1600, 1649, ((1611 + 1649) // 2, PERIOD)),   # 39 of 50: 78%
    ("period", 1607, 1622, ((1611 + 1622) // 2, PERIOD)),   # 12 of 16: exactly 3/4
    ("period", 1606, 1622, (0, UNKNOWN)),                   # 12 of 17: no colour, listed for a hand check
    ("period", 1580, 1650, (0, UNKNOWN)),                   # 31 and 40 of 71 years
    ("period", 1600, 1624, (0, UNKNOWN)),                   # "the beginning of the 1600s": 14 of 25 years, 56%
])
def test_year_of(kind, a, z, want):
    assert cited.year_of(kind, a, z) == want
    if want[1] == PERIOD:
        lo, hi = next((f, t) for _, _, _, f, t, _ in city.PERIODS if f <= want[0] <= t)
        assert 4 * (min(z, hi) - max(a, lo) + 1) >= 3 * (z - a + 1)


# ---- the s02 tier

def tier(b, t, r=None, **kw):
    return run(b, no_raa() if r is None else r, cited=cited.rows(t, b), **kw)


def test_a_cited_row_dates_an_unknown_footprint_and_overrides_wikidata_and_osm():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)))
    t = table({"key": "u0"}, {"key": "u1", "year_from": "1600", "year_to": "1699", "kind": "period"},
              {"key": "u2", "year_from": "1643", "year_to": "1643"})
    t.key = ["u0", "u1", "u2"]           # the synthetic footprints' keys (a real row's is a LOD1 UUID)
    y, report = tier(b, t, wikidata=wikidata(("Q0", 0, 1900, 1900, False)), osm=osm(("way/2", 2, 1645, 1645)))
    assert (y.ysrc[0], y.yflag[0], y.year[0], y.year_from[0], y.year_to[0]) == (SRC_CITED, RANGE, 1640, 1640, 1649)
    assert (y.ysrc[1], y.yflag[1], y.year[1], y.period[1]) == (SRC_CITED, PERIOD, 1655, city.period_index(1655))
    assert (y.ysrc[2], y.yflag[2], y.year[2]) == (SRC_CITED, EXACT, 1643)
    assert report["cited"] == 3 and report["cited_skipped"] == []
    # the Wikidata year it replaced lies 250 years off: listed; OSM's 1645 two years from 1643: not
    assert [(e["gid"], e["qid"], e["year_from"], e["winner_from"]) for e in report["review"]["cited_vs_wikidata"]] == [
        (0, "Q0", 1900, 1640)]
    assert report["review"]["cited_vs_osm"] == []


def test_a_raa_or_landmark_date_wins_and_a_disagreement_is_listed():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)))
    t = table({"key": "u0"}, {"key": "u1", "year_from": "1500", "year_to": "1599", "kind": "period"},
              {"key": "u2"})
    t.key = ["u0", "u1", "u2"]
    r = raa(rec("r0", sq(0), 1645, 1645, "u0"), rec("r1", sq(1), 1700, 1720, "u1"))
    y, report = tier(b, t, r, landmarks=[landmark_at(X0 + 205, Y0 + 5)])
    assert list(y.ysrc) == [SRC_RAA, SRC_RAA, SRC_CURATED]
    assert sorted(report["cited_skipped"]) == [0, 1, 2] and report["cited"] == 0
    # RAÄ's 1645 agrees with the 1640s; its 1700–1720 is a century from the 1500s
    assert [(e["gid"], e["year_from"], e["year_to"], e["winner_from"], e["source"]) for e in
            report["review"]["cited_vs_raa"]] == [(1, 1500, 1599, 1700, "wikipedia_sv")]


def test_a_period_no_map_period_holds_three_quarters_of_stays_unknown_and_is_listed():
    b = buildings(("u0", "Enbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)),
                  ("u3", "Flerbostadshus", sq(3)))
    t = table(*({"key": u, "year_from": "1580", "year_to": "1650", "kind": "period"} for u in ("u0", "u1", "u2", "u3")))
    t.key = ["u0", "u1", "u2", "u3"]
    y, report = tier(b, t, raa(rec("r3", sq(3), 1700, 1700, "u3")), wikidata=wikidata(("Q1", 1, 1900, 1900, False)),
                     osm=osm(("way/2", 2, 1890, 1890)))
    # no colour on an undated footprint (and no refusal on the private house: nothing is written there)
    assert (y.ysrc[0], y.yflag[0], y.year[0]) == (SRC_NONE, UNKNOWN, 0)
    # the cited tier outranks Wikidata and OSM: their years go too, so the building is "Year unknown" as About says
    for g in (1, 2):
        assert (y.ysrc[g], y.yflag[g], y.year[g], y.year_from[g], y.year_to[g]) == (SRC_NONE, UNKNOWN, 0, 0, 0)
    assert (y.ysrc[3], y.year[3]) == (SRC_RAA, 1700)                  # RAÄ outranks the cited tier: it stays
    # each listed with the year that was there, so the conflict is in sight
    assert [(e["gid"], e["before_src"], e["before_year"], e["cleared"]) for e in report["review"]["cited_no_period"]] \
        == [(0, "", 0, False), (1, "wikidata", 1900, True), (2, "osm", 1890, True), (3, "raa", 1700, False)]
    assert report["cited"] == 0 and report["review"]["wikidata_gains"] == []


def test_a_cited_period_leaves_a_wikidata_or_osm_year_inside_its_span_and_lists_it():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)), ("u2", "Flerbostadshus", sq(2)),
                  ("u3", "Flerbostadshus", sq(3)))
    t = table(*({"key": u, "year_from": "1600", "year_to": "1699", "kind": "period"} for u in ("u0", "u1", "u2")),
              {"key": "u3", "year_from": "1640", "year_to": "1649"})
    t.key = ["u0", "u1", "u2", "u3"]
    y, report = tier(b, t, wikidata=wikidata(("Q0", 0, 1643, 1643, False), ("Q3", 3, 1643, 1643, False)),
                     osm=osm(("way/1", 1, 1648, 1648), ("way/2", 2, 1595, 1595)))
    # the more precise record agrees with the century: it stays, exact, and the row waits for a look
    assert (y.ysrc[0], y.yflag[0], y.year[0]) == (SRC_WIKIDATA, EXACT, 1643)
    assert (y.ysrc[1], y.yflag[1], y.year[1]) == (SRC_OSM, EXACT, 1648)
    assert [(e["gid"], e["record_src"], e["record_year"], e["year_from"], e["year_to"])
            for e in report["review"]["cited_period_vs_record"]] == [(0, "wikidata", 1643, 1600, 1699),
                                                                     (1, "osm", 1648, 1600, 1699)]
    # OSM's 1595 lies outside the 1600s (by less than DISAGREE_YEARS): the period replaces it, and it is listed, as is
    # every record a cited period replaces; a cited decade over a year inside it replaces it as before
    assert (y.ysrc[2], y.yflag[2]) == (SRC_CITED, PERIOD) and (y.ysrc[3], y.yflag[3], y.year[3]) == (SRC_CITED, RANGE,
                                                                                                    1640)
    assert [(e["gid"], e["osm_id"], e["year_from"]) for e in report["review"]["cited_vs_osm"]] == [(2, "way/2", 1595)]
    assert report["review"]["cited_vs_wikidata"] == [] and report["cited"] == 2


def fake_estimate(monkeypatch, n):
    """est.run, est.features and est.check_external stubbed: the estimate tier runs and dates nothing; returns what
    est.run was given (train, query)."""
    import pipeline.estimate as est
    seen = {}

    def fake_run(f, year, train, query, p=None, stadsdel=None):
        seen.update(train=train.copy(), query=query.copy())
        return (pd.DataFrame({"yflag": [UNKNOWN] * n, "yhat": [0.0] * n, "band": [0] * n}),
                {"result": {"estimate": 0, "period": 0, "unknown": int(query.sum())}})
    monkeypatch.setattr(est, "features", lambda *a, **k: None)
    monkeypatch.setattr(est, "run", fake_run)
    monkeypatch.setattr(est, "check_external", lambda *a, **k: est.no_external())
    return seen


def test_a_listed_period_keeps_its_footprint_from_the_estimate(monkeypatch):
    b = buildings(("u0", "Enbostadshus", sq(0)))
    t = table({"key": "u0", "year_from": "1580", "year_to": "1650", "kind": "period"})
    t.key = ["u0"]
    seen = fake_estimate(monkeypatch, 1)
    s02_years.assign_years(b, no_raa(), [], estimates=True, cited=cited.rows(t, b))
    assert seen["query"].tolist() == [False]


def test_a_cited_period_on_a_private_house_is_refused():
    b = buildings(("u0", "Enbostadshus", sq(0)))
    t = table({"key": "u0", "year_from": "1600", "year_to": "1699", "kind": "period"})
    t.key = ["u0"]
    with pytest.raises(cited.Refused, match="a cited period or either pair on a private house"):
        tier(b, t)


def test_a_cited_year_on_a_private_house_keeps_the_decade_rule():
    b = buildings(("u0", "Enbostadshus", sq(0)))
    t = table({"key": "u0", "year_from": "1643", "year_to": "1643"})
    t.key = ["u0"]
    y, _ = tier(b, t)
    assert (y.ysrc[0], y.year[0], y.year_from[0], y.year_to[0], bool(y.private[0])) == (SRC_CITED, 1640, 1640, 1649,
                                                                                          True)


def test_a_takedown_is_dated_by_no_cited_row():
    b = buildings(("u0", "Flerbostadshus", sq(0)))
    t = table({"key": "u0"})
    t.key = ["u0"]
    y, report = tier(b, t, exclude={0})
    assert (y.ysrc[0], y.yflag[0]) == (SRC_NONE, UNKNOWN) and report["cited"] == 0


def test_a_cited_period_never_trains_the_estimate(monkeypatch):
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)))
    t = table({"key": "u0", "year_from": "1600", "year_to": "1699", "kind": "period"}, {"key": "u1"})
    t.key = ["u0", "u1"]
    seen = fake_estimate(monkeypatch, 2)
    _, report = s02_years.assign_years(b, no_raa(), [], estimates=True, cited=cited.rows(t, b))
    assert seen["train"].tolist() == [False, True]
    # what ships counts the cited period as a period (s99 ties result to stats.byFlag)
    assert report["accuracy"]["result"]["period"] == 1


def test_a_uuid_on_several_footprints_is_refused():
    b = buildings(("u0", "Flerbostadshus", sq(0)), ("u0", "Flerbostadshus", sq(1)))
    t = table({"key": "u0"})
    t.key = ["u0"]
    with pytest.raises(cited.Refused, match="several footprints"):
        cited.rows(t, b)


def test_an_either_pair_dates_its_footprint_by_its_union_and_a_rebuild_never_does():
    b = buildings(*((f"u{i}", "Flerbostadshus", sq(i)) for i in range(4)))
    t = table({"key": "u0", **either(1785, 1785)}, {"key": "u0", **either(1798, 1798, place=WP2)},
              {"key": "u1", **either(1580, 1580)}, {"key": "u1", **either(1650, 1659, place=WP2)},
              {"key": "u2", "year_from": "1798", "year_to": "1798"}, {"key": "u2", **rebuilt(1940, 1949)},
              {"key": "u3", **either(1600, 1699)}, {"key": "u3", **either(1643, 1643, place=WP2)})
    y, report = tier(b, t, wikidata=wikidata(("Q1", 1, 1900, 1900, False), ("Q3", 3, 1650, 1650, False)))
    # the union's period holds 3/4 of it: PERIOD, "≈", the estimate tone, its middle year on the timeline
    assert (y.ysrc[0], y.yflag[0], y.year[0], y.year_from[0], y.year_to[0]) == (SRC_CITED, PERIOD, 1791, 1785, 1798)
    # none does: no colour, the Wikidata year it outranks cleared, listed for a hand check with its kind
    assert (y.ysrc[1], y.yflag[1], y.year[1]) == (SRC_NONE, UNKNOWN, 0)
    assert [(e["gid"], e["kind"], e["year_from"], e["year_to"], e["source"], e["before_src"], e["cleared"])
            for e in report["review"]["cited_no_period"]] == [(1, "either", 1580, 1659, "wikipedia_sv or wikipedia_sv",
                                                               "wikidata", True)]
    # a rebuild of the 1940s changes nothing: the standing house's 1798
    assert (y.ysrc[2], y.yflag[2], y.year[2], y.year_from[2], y.year_to[2]) == (SRC_CITED, EXACT, 1798, 1798, 1798)
    # unlike a period row, an either pair is applied over a Wikidata year inside its union (its two readings are the
    # hand-checked answer), and the year it replaced is listed
    assert (y.ysrc[3], y.yflag[3], y.year_from[3], y.year_to[3]) == (SRC_CITED, PERIOD, 1600, 1699)
    assert report["review"]["cited_period_vs_record"] == []
    assert [(e["gid"], e["qid"]) for e in report["review"]["cited_vs_wikidata"]] == [(3, "Q3")]
    assert report["cited"] == 3


def test_an_either_pair_on_a_private_house_is_refused():
    b = buildings(("u0", "Enbostadshus", sq(0)))
    t = table({"key": "u0", **either(1785, 1785)}, {"key": "u0", **either(1798, 1798, place=WP2)})
    with pytest.raises(cited.Refused, match="a cited period or either pair on a private house"):
        tier(b, t)


def test_an_oid_key_dates_a_footprint_without_a_uuid():
    b = buildings(("", "Flerbostadshus", sq(0)), ("", "Flerbostadshus", sq(1)))
    b["oid"] = pd.array([50489018, 50489019], dtype="int64")
    y, report = tier(b, table({"key": "oid:50489019", "year_from": "1643", "year_to": "1643"}))
    assert (y.ysrc[1], y.yflag[1], y.year[1]) == (SRC_CITED, EXACT, 1643) and y.ysrc[0] == SRC_NONE
    assert report["cited"] == 1


# ---- the card

def test_the_card_carries_the_source_and_page_only_never_on_a_hidden_card():
    df = pd.DataFrame({"gid": [0, 1, 2, 3], "uuid": ["u0", "u1", "u2", "u3"],
                       "ysrc": [SRC_CITED, SRC_CITED, SRC_CITED, SRC_RAA]})
    t = table({"key": "u0"}, {"key": "u1", "kind": "rebuilt_from_new"}, {"key": "u2"}, {"key": "u3"})
    t.key = ["u0", "u1", "u2", "u3"]
    shards = [{} for _ in range(4)]
    n = cited.cards(shards, df, t, np.array([False, False, True, False]))
    assert n == 2
    assert shards[0] == {"0": {"yc": {"s": "wikipedia_sv", "u": WP}}}
    assert shards[1] == {"1": {"yc": {"s": "wikipedia_sv", "u": WP, "k": "rebuilt"}}}
    assert shards[2] == {} and shards[3] == {}                    # a private house, and a RAÄ-dated footprint


def test_s03_reads_no_table_unless_given_one(tmp_path, monkeypatch):
    # a fixture build never reads the repo's table: write_outputs' default is none
    from tests.test_s03_tiles import write
    monkeypatch.setattr(cited, "read", lambda *a, **k: pytest.fail("read the repo's table"))
    write(tmp_path)


def test_the_card_carries_both_readings_the_rebuilds_and_a_span_no_year_ships():
    df = pd.DataFrame({"gid": range(8), "uuid": ["u0", "u1", "u2", "u3", "u4", "", "u6", "u7"], "oid": range(10, 18),
                       "ysrc": [SRC_CITED, SRC_NONE, SRC_CITED, SRC_NONE, SRC_RAA, SRC_CITED, SRC_NONE, SRC_NONE]})
    t = table({"key": "u0", **either(1798, 1798, place=WP2)}, {"key": "u0", **either(1785, 1785)},
              {"key": "u0", **rebuilt(1947)}, {"key": "u0", **rebuilt(1907)},
              {"key": "u1", **either(1580, 1580)}, {"key": "u1", **either(1650, 1659, place=WP2)},
              {"key": "u2", "kind": "rebuilt_from_new", "year_from": "1854", "year_to": "1854"},
              {"key": "u2", **rebuilt(1902)},
              {"key": "u3", "kind": "period", "year_from": "1600", "year_to": "1624"},
              {"key": "u4", "kind": "period", "year_from": "1580", "year_to": "1650"},      # RAÄ dates it
              {"key": "oid:15", "year_from": "1643", "year_to": "1643"},
              {"key": "u6", "year_from": "1643", "year_to": "1643"},                         # ships no cited year
              {"key": "u7", "kind": "period", "year_from": "1600", "year_to": "1624"})       # a takedown
    shards = [{} for _ in range(8)]
    n = cited.cards(shards, df, t, np.zeros(8, bool), withheld={7})
    yc = {int(g): c["yc"] for shard in shards for g, c in shard.items()}
    def o(a, z, u=WP):
        return {"a": a, "z": z, "s": "wikipedia_sv", "u": u}
    assert yc == {
        0: {"e": [o(1785, 1785), o(1798, 1798, WP2)], "r": [o(1907, 1907), o(1947, 1947)]},
        1: {"e": [o(1580, 1580), o(1650, 1659, WP2)]},                  # no colour: the card still gives both
        2: {"s": "wikipedia_sv", "u": WP, "k": "rebuilt", "r": [o(1902, 1902)]},
        3: {"s": "wikipedia_sv", "u": WP, "a": 1600, "z": 1624},       # no colour: the card reads the span here
        5: {"s": "wikipedia_sv", "u": WP}}                              # by its oid
    assert n == 5
    # card_entry: what the card gets for a footprint's rows and the source its year ships with
    rows_u3 = cited.by_key(t)["u3"]
    assert cited.card_entry(rows_u3, SRC_NONE) == yc[3]
    for other in (SRC_RAA, SRC_WIKIDATA, SRC_OSM, SRC_CURATED):
        assert cited.card_entry(rows_u3, other) is None                 # another tier dates it: no cited line
    assert cited.card_entry(cited.by_key(t)["u6"], SRC_NONE) is None


def test_the_card_carries_about_and_the_other_houses():
    t = table({"key": "u0", "year_from": "1640", "year_to": "1640", "circa": "true", "kind": "rebuilt_from_new"},
              {"key": "u0", **rebuilt(1774, circa="true")}, {"key": "u0", **also(1520, 1529, place=WP2)},
              {"key": "u1", **either(1785, 1785, circa="true")}, {"key": "u1", **either(1798, 1798, place=WP2)})
    def o(a, z, u=WP, **kw):
        return {"a": a, "z": z, "s": "wikipedia_sv", "u": u, **kw}
    assert cited.card_entry(cited.by_key(t)["u0"], SRC_CITED) == {
        "s": "wikipedia_sv", "u": WP, "k": "rebuilt", "c": True, "r": [o(1774, 1774, c=True)],
        "o": [o(1520, 1529, WP2)]}
    assert cited.card_entry(cited.by_key(t)["u1"], SRC_CITED) == {"e": [o(1785, 1785, c=True), o(1798, 1798, WP2)]}


# ---- s99: check_cited

# the fixture's source, and the credits the cited sources need (cited.SOURCES' `credit`)
CREDITS = [{**tinycity.SOURCES[0], "id": i}
           for i in ("test-src", "wikipedia", "kulturnav", "stadsmuseet_br", "stadsmuseet_inventories",
                     "stockholm_stages", "stadsholmen_faktablad")]


def cited_site(tmp_path, monkeypatch, r: dict, gid: int = 7, ship: dict | None = None, extra=(),
               key: str | None = None):
    """The tiny city of tests/test_s99_validate.py with footprint `gid` dated by the cited row r (and the `extra` rows
    on its key: an either pair's second, rebuilt rows) as s02 would write it (or as `ship` says, to test a mismatch),
    its card's `yc` from s03; returns (out, csv path). key: the rows' key (default: the footprint's uuid)."""
    from tests.tinycity import ACCURACY, LANDMARKS, TERRAIN, WIKI, ground_rows, tiny_city, write_data
    from tests.test_s99_validate import VERSION
    from pipeline import io, s04_base
    from tests.tinycity import local_box, tiny_terrain
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    write_data(data)
    b, y, a = tiny_city()
    rs = [row(key=key or str(b.uuid[gid]), **x) for x in (r, *extra)]
    f = cited.footprint(rs)
    year, flag = cited.footprint_year(f)
    w = {"year": year, "year_from": f["year_from"], "year_to": f["year_to"], "ysrc": SRC_CITED, "yflag": flag,
         "period": city.period_index(year), "private": False, **(ship or {})}
    before = int(y.yflag[gid])
    for k, v in w.items():
        y.loc[gid, k] = v
    acc = json.loads(json.dumps(ACCURACY))
    for flags, step in ((before, -1), (w["yflag"], 1)):         # the table counts what ships (s99 ties it)
        if flags == PERIOD:
            acc["result"]["period"] += step
        elif flags in (EXACT, RANGE, LONG):
            acc["tested"] += step
    y.to_parquet(data / "years.parquet")
    (data / "accuracy.json").write_text(json.dumps(acc), encoding="utf-8")
    out = tmp_path / "web" / "data" / VERSION
    path = write_csv(tmp_path / "cited.csv", *rs)
    s03_tiles.write_outputs(s03_tiles.join(b, y, a, ground_rows(b, a)), out, VERSION, sources=CREDITS, accuracy=acc,
                            terrain=TERRAIN, wiki=WIKI, landmarks=LANDMARKS, cited=cited.read(path))
    s14_search.write(out, *s14_search.build(s03_tiles.join(b, y, a), s14_search.read_cards(out),
                                            s03_tiles.load_places(data)))
    (tmp_path / "web" / "data" / "photos").mkdir()
    from tests.tinycity import PHOTO_KEY
    (tmp_path / "web" / "data" / "photos" / PHOTO_KEY).write_bytes(b"\xff\xd8 a tiny jpeg")
    io.write_gz(out / "land.bin.gz", s04_base.pack([local_box(-800, -800, 800, 800)]))
    io.write_gz(out / "water.bin.gz", s04_base.pack([local_box(900, -800, 1400, 800)]))
    io.write_gz(out / "terrain.bin.gz", tiny_terrain())
    io.write_json(out / "labels.json", [{"name": "Strömmen", "water": True, "tier": 1, "pts": [[1100, 0, 0, 300, 80]]}])
    io.write_json(out / "ferries.json", {"version": 1, "routes": [
        {"id": "r1", "ref": "82", "name": "Djurgårdsfärjan 82", "kind": "ferry", "ends": ["pier", "pier"],
         "path": [[1000.0, 0.0], [1300.0, 0.0]]}]})
    return out, path


def validate(out, path, **kw):
    kw.setdefault("takedowns", [])
    return s99_validate.validate(out, out.parents[2] / "data", sources=kw.pop("sources", CREDITS), cited_path=path, **kw)


def cited_errors(errors):
    return [e for e in errors if e.startswith("cited:")]


def test_a_cited_decade_ships_with_its_link_and_passes(tmp_path, monkeypatch):
    out, path = cited_site(tmp_path, monkeypatch, {})
    card = json.loads((out / "cards" / "07.json").read_text())["7"]
    assert card["yc"] == {"s": "wikipedia_sv", "u": WP} and "quote" not in json.dumps(card)
    assert validate(out, path) == []


def test_a_stage_row_ships_its_span_with_the_stage_page_and_passes(tmp_path, monkeypatch):
    r = {"source": "stockholm_stage", "place": RESULTS + "norra-2", "quote": "", "year_from": "2016",
         "year_to": "2017", "note": "Norra 2 stage, block Sonfjället: move-in 2016–2017."}
    out, path = cited_site(tmp_path, monkeypatch, r)
    card = json.loads((out / "cards" / "07.json").read_text())["7"]
    assert card["yc"] == {"s": "stockholm_stage", "u": RESULTS + "norra-2"}
    assert validate(out, path) == []
    # its credit, the City's stage pages, must be in sources.yml
    errors = validate(out, path, sources=[s for s in CREDITS if s["id"] != "stockholm_stages"])
    assert "cited: source stockholm_stages is not in sources.yml (its credit would be missing)" in errors


def test_a_cited_period_passes(tmp_path, monkeypatch):
    out, path = cited_site(tmp_path, monkeypatch, {"kind": "period", "year_from": "1600", "year_to": "1699"})
    assert validate(out, path) == []


def test_a_period_without_a_map_period_ships_no_year_of_a_lower_tier(tmp_path, monkeypatch):
    period = {"kind": "period", "year_from": "1580", "year_to": "1650"}
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    out, path = cited_site(tmp_path / "a", monkeypatch, period, ship={"ysrc": SRC_NONE, "yflag": UNKNOWN, "year": 0,
                                                                      "year_from": 0, "year_to": 0, "period": 0})
    assert cited_errors(validate(out, path)) == []
    out, path = cited_site(tmp_path / "b", monkeypatch, period, ship={"ysrc": SRC_WIKIDATA, "yflag": EXACT,
                                                                      "year": 1900, "year_from": 1900, "year_to": 1900,
                                                                      "period": city.period_index(1900)})
    assert cited_errors(validate(out, path)) == [
        "cited: row 1 (gid 7) has no map period, but its footprint ships a year from a tier the cited one outranks "
        "(area, Wikidata, OSM or the estimate): s02 clears it"]


UNKNOWN_SHIP = {"ysrc": SRC_NONE, "yflag": UNKNOWN, "year": 0, "year_from": 0, "year_to": 0, "period": 0}


def card7(out) -> dict:
    return json.loads((out / "cards" / "07.json").read_text())["7"]


def test_a_period_without_a_map_period_still_says_so_on_its_card(tmp_path, monkeypatch):
    from tests.test_s99_validate import edit_card
    out, path = cited_site(tmp_path, monkeypatch, {"kind": "period", "year_from": "1580", "year_to": "1650"},
                           ship=UNKNOWN_SHIP)
    card = card7(out)
    assert card["yc"] == {"s": "wikipedia_sv", "u": WP, "a": 1580, "z": 1650}
    assert validate(out, path) == []
    edit_card(out, 7, {k: v for k, v in card.items() if k != "yc"})
    assert cited_errors(validate(out, path)) == [
        "cited: row 1 (gid 7): its card does not link the row's source and page (`yc`)"]


def test_an_either_pair_ships_with_both_readings_and_its_rebuilds(tmp_path, monkeypatch):
    from tests.test_s99_validate import edit_card
    out, path = cited_site(tmp_path, monkeypatch, either(1785, 1785),
                           extra=[either(1798, 1798, source="ssm_inventory", place=INVENTORY, page="3", quote=""),
                                  rebuilt(1907, quote="byggdes om 1907")])
    card = card7(out)
    assert card["yc"] == {"e": [{"a": 1785, "z": 1785, "s": "wikipedia_sv", "u": WP},
                                {"a": 1798, "z": 1798, "s": "ssm_inventory", "u": INVENTORY}],
                          "r": [{"a": 1907, "z": 1907, "s": "wikipedia_sv", "u": WP}]}
    assert "quote" not in json.dumps(card) and "note" not in json.dumps(card)
    assert validate(out, path) == []
    # the card must carry what the rows give: a rebuild left out fails
    edit_card(out, 7, {**card, "yc": {"e": card["yc"]["e"]}})
    assert cited_errors(validate(out, path)) == [
        "cited: row 1 (gid 7): its card does not link the row's source and page (`yc`)"]


def test_an_either_pair_no_period_holds_stays_unknown_and_its_card_gives_both(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    out, path = cited_site(tmp_path / "a", monkeypatch, either(1580, 1580), extra=[either(1650, 1659, place=WP2)],
                           ship=UNKNOWN_SHIP)
    assert card7(out)["yc"] == {"e": [{"a": 1580, "z": 1580, "s": "wikipedia_sv", "u": WP},
                                      {"a": 1650, "z": 1659, "s": "wikipedia_sv", "u": WP2}]}
    assert validate(out, path) == []
    # shipping a cited year for it is an error, as for a period row
    out, path = cited_site(tmp_path / "b", monkeypatch, either(1580, 1580), extra=[either(1650, 1659, place=WP2)],
                           ship={"ysrc": SRC_CITED, "yflag": PERIOD, "year": 1640, "year_from": 1580, "year_to": 1659,
                                 "period": city.period_index(1640)})
    assert ('cited: row 1 (gid 7) ships a cited year, but no map period holds 3/4 of its span (cited.year_of): it '
            'must stay "Year unknown"') in cited_errors(validate(out, path))


def test_an_oid_key_names_a_footprint_without_a_uuid(tmp_path, monkeypatch, capsys):
    # the tiny city's gid 10 has no uuid (oid 1010)
    out, path = cited_site(tmp_path, monkeypatch, {"year_from": "1643", "year_to": "1643"}, gid=10, key="oid:1010")
    assert json.loads((out / "cards" / "10.json").read_text())["10"]["yc"] == {"s": "wikipedia_sv", "u": WP}
    assert validate(out, path) == []
    # an oid that names no footprint: a warning on a fixture build, an error on a release
    both = write_csv(tmp_path / "both.csv", {"key": "oid:1010", "year_from": "1643", "year_to": "1643"},
                     {"key": "oid:999999"})
    import gzip
    attrs = np.frombuffer(gzip.decompress((out / "attrs.bin.gz").read_bytes()), dtype=s03_tiles.ATTR_DTYPE)
    data = out.parents[2] / "data"
    assert s99_validate.check_cited(attrs, data, sources=CREDITS, path=both) == []
    assert "cited: row 2: its footprint is not among these buildings" in capsys.readouterr().err
    assert s99_validate.check_cited(attrs, data, sources=CREDITS, path=both, release=True) == [
        "cited: row 2: its footprint is not among these buildings (the City redrew it?): find the footprint again or "
        "hold the row"]


def test_the_card_line_s_shape_is_checked():
    def o(a, z, u=WP):
        return {"a": a, "z": z, "s": "wikipedia_sv", "u": u}
    cited_rec, none_rec, raa_rec = ({"ysrc": SRC_CITED, "yflag": PERIOD}, {"ysrc": SRC_NONE, "yflag": UNKNOWN},
                                    {"ysrc": SRC_RAA, "yflag": EXACT})
    line = s99_validate.check_cited_line
    pair = [o(1785, 1785), o(1798, 1798, WP2)]
    assert line("c", {"e": pair, "r": [o(1907, 1907), o(1947, 1947)]}, cited_rec) == []
    assert line("c", {"e": pair}, none_rec) == []                                       # no colour, both readings
    assert line("c", {"s": "wikipedia_sv", "u": WP, "a": 1580, "z": 1650}, none_rec) == []
    not_cited = ["c has `yc` but its year is not a cited record's"]
    assert line("c", {"s": "wikipedia_sv", "u": WP}, none_rec) == not_cited           # nothing to say without a span
    assert line("c", {"e": pair}, raa_rec) == not_cited
    bad_e = ["c has a `yc.e` that is not two readings {a, z, s, u} by year, each a cited source's page"]
    assert line("c", {"e": pair[::-1]}, cited_rec) == bad_e                             # earliest first
    assert line("c", {"e": pair[:1]}, cited_rec) == bad_e
    assert line("c", {"e": [o(1785, 1785), o(1798, 1798, WP.replace("?oldid", "?title=X&oldid"))]}, cited_rec) == bad_e
    assert line("c", {"e": pair, "s": "wikipedia_sv", "u": WP}, cited_rec) == [
        "c has a `yc` with an either pair and a single row's fields"]
    assert line("c", {"s": "wikipedia_sv", "u": WP, "a": 1600, "z": 1699}, cited_rec) == [
        "c has a `yc` span, but its year ships (the card reads that)"]
    assert line("c", {"s": "wikipedia_sv", "u": WP, "a": 1600}, none_rec) == [
        "c has a `yc` span that is not two years a..z"]
    bad_r = ["c has a `yc.r` that is not rebuilds {a, z, s, u} by year, each a cited source's page"]
    assert line("c", {"s": "wikipedia_sv", "u": WP, "r": [o(1907, 1907), o(1880, 1880)]}, cited_rec) == bad_r
    assert line("c", {"s": "wikipedia_sv", "u": WP, "r": []}, cited_rec) == bad_r
    assert line("c", {"s": "wikipedia_sv", "u": WP, "q": 1}, cited_rec) == [
        "c has a `yc` that is not {s, u, k, a, z, e, r, o, c}"]
    # "about" (c) and the other houses (o)
    assert line("c", {"s": "wikipedia_sv", "u": WP, "c": True, "r": [{**o(1774, 1774), "c": True}],
                      "o": [o(1520, 1529)]}, cited_rec) == []
    assert line("c", {"e": pair, "o": [o(1804, 1804)]}, cited_rec) == []
    assert line("c", {"s": "wikipedia_sv", "u": WP, "c": 1}, cited_rec) == ["c has a `yc.c` that is not true"]
    assert line("c", {"s": "wikipedia_sv", "u": WP, "o": [o(1804, 1804), o(1520, 1520)]}, cited_rec) == [
        "c has a `yc.o` that is not other houses {a, z, s, u} by year, each a cited source's page"]
    assert line("c", {"s": "wikipedia_sv", "u": WP, "o": [{**o(1804, 1804), "c": False}]}, cited_rec) == [
        "c has a `yc.o` that is not other houses {a, z, s, u} by year, each a cited source's page"]


def test_two_keys_on_one_footprint_fail_s99_by_name(tmp_path, monkeypatch):
    import gzip
    out, _ = cited_site(tmp_path, monkeypatch, {})
    attrs = np.frombuffer(gzip.decompress((out / "attrs.bin.gz").read_bytes()), dtype=s03_tiles.ATTR_DTYPE)
    data = out.parents[2] / "data"
    b = pd.read_parquet(data / "buildings.parquet", columns=["gid", "uuid"])
    uuid = str(b.uuid[b.gid == 7].iloc[0])
    both = write_csv(tmp_path / "both.csv", {"key": uuid}, {"key": "oid:1007", "year_from": "1700", "year_to": "1700"})
    errors = s99_validate.check_cited(attrs, data, sources=CREDITS, path=both)
    assert f"cited: keys ['{uuid}', 'oid:1007'] name one footprint (gid 7): one key per footprint" in errors
    assert f"cited: oid:1007 names a footprint the City gives a UUID ({uuid}): key the row by that" in errors


def test_a_period_around_a_more_precise_wikidata_year_is_a_warning(tmp_path, monkeypatch, capsys):
    out, path = cited_site(tmp_path, monkeypatch, {"kind": "period", "year_from": "1600", "year_to": "1699"},
                           ship={"ysrc": SRC_WIKIDATA, "yflag": EXACT, "year": 1643, "year_from": 1643,
                                 "year_to": 1643, "period": city.period_index(1643)})
    assert cited_errors(validate(out, path)) == []
    assert "is a period around the footprint's Wikidata or OSM year" in capsys.readouterr().err


def test_a_build_without_the_table_has_a_stray_cited_year(tmp_path, monkeypatch):
    out, _ = cited_site(tmp_path, monkeypatch, {})
    assert cited_errors(validate(out, None)) == ["cited: 1 buildings carry a cited year without a row (gids 7)"]


def test_a_cited_row_that_ships_another_year_fails(tmp_path, monkeypatch):
    out, path = cited_site(tmp_path, monkeypatch, {}, ship={"year": 1641, "period": city.period_index(1641)})
    assert any("does not ship as its row says" in e for e in cited_errors(validate(out, path)))


def test_a_cited_card_without_its_link_fails(tmp_path, monkeypatch):
    from tests.test_s99_validate import edit_card
    out, path = cited_site(tmp_path, monkeypatch, {})
    card = json.loads((out / "cards" / "07.json").read_text())["7"]
    edit_card(out, 7, {k: v for k, v in card.items() if k != "yc"})
    assert cited_errors(validate(out, path)) == [
        "cited: row 1 (gid 7): its card does not link the row's source and page (`yc`)"]


def test_a_title_link_on_a_card_fails(tmp_path, monkeypatch):
    from tests.test_s99_validate import edit_card
    out, path = cited_site(tmp_path, monkeypatch, {})
    card = json.loads((out / "cards" / "07.json").read_text())["7"]
    edit_card(out, 7, {**card, "yc": {"s": "wikipedia_sv", "u": WP.replace("?oldid", "?title=X&oldid")}})
    assert any("not a cited source's page" in e for e in validate(out, path))


def test_a_takedown_on_a_cited_footprint_is_an_error(tmp_path, monkeypatch):
    out, path = cited_site(tmp_path, monkeypatch, {})
    errors = cited_errors(validate(out, path, takedowns=[{"oid": 1007, "date": "2026-11-02"}]))
    assert ("cited: row 1 (gid 7) is on a takedown: delete the row from pipeline/gamla_stan_years.csv "
            "(docs/privacy.md, takedowns)") in errors


def test_a_row_naming_a_designation_in_its_note_or_place_fails(tmp_path, monkeypatch):
    out, path = cited_site(tmp_path, monkeypatch, {"note": "The house on Diana 2, built in the 1640s."})
    assert "cited: row 1 names a property designation in its quote, note or place" in cited_errors(validate(out, path))


def test_a_source_not_in_sources_yml_fails(tmp_path, monkeypatch):
    out, path = cited_site(tmp_path, monkeypatch, {})
    errors = validate(out, path, sources=[s for s in CREDITS if s["id"] != "wikipedia"])
    assert "cited: source wikipedia is not in sources.yml (its credit would be missing)" in errors


def test_a_row_on_no_footprint_is_an_error_only_on_a_release(tmp_path, monkeypatch, capsys):
    import gzip
    out, _ = cited_site(tmp_path, monkeypatch, {}, ship={"ysrc": SRC_NONE, "yflag": UNKNOWN, "year": 0,
                                                          "year_from": 0, "year_to": 0, "period": 0})
    path = write_csv(tmp_path / "gone.csv", {"key": "0e389b81-54f2-48cc-b4ee-ae1285df2299"})
    attrs = np.frombuffer(gzip.decompress((out / "attrs.bin.gz").read_bytes()), dtype=s03_tiles.ATTR_DTYPE)
    data = out.parents[2] / "data"
    assert s99_validate.check_cited(attrs, data, sources=CREDITS, path=path) == []
    assert "its footprint is not among these buildings" in capsys.readouterr().err
    assert s99_validate.check_cited(attrs, data, sources=CREDITS, path=path, release=True) == [
        "cited: row 1: its footprint is not among these buildings (the City redrew it?): find the footprint again or "
        "hold the row"]


def test_a_city_museum_report_must_be_one_the_register_links(tmp_path, monkeypatch):
    out, path = cited_site(tmp_path, monkeypatch, {"source": "ssm_br", "place": REPORT, "page": "1", "quote": ""})
    data = out.parents[2] / "data"
    # without the register's cache: a warning, on a release an error
    assert cited_errors(validate(out, path)) == []
    assert any("cannot check that 1 City Museum reports" in e for e in validate(out, path, release=True))
    reports = data / "raw" / "stadsmuseet" / "reports"
    reports.mkdir(parents=True)
    other = {"data": [{"href": "/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/DOK_1/SSM_DOK_000999.pdf.info",
                       "metadata": {"688": {"value": ["42"]}}}]}
    (reports / "42.json").write_text(json.dumps(other), encoding="utf-8")
    assert cited_errors(validate(out, path)) == [
        "cited: row 1 cites a City Museum document the register does not link (the museum's permission covers the "
        "register's reports only)"]
    linked = {"data": [{"href": REPORT.removeprefix("https://digitalastadsmuseet.stockholm.se"),
                        "metadata": {"688": {"value": ["42"]}}}]}
    (reports / "42.json").write_text(json.dumps(linked), encoding="utf-8")
    assert cited_errors(validate(out, path)) == []


def test_a_stadsholmen_row_links_the_property_list_and_its_property_must_have_a_harvested_sheet(tmp_path, monkeypatch,
                                                                                                capsys):
    r = {"source": "stadsholmen", "place": SHLIST, "page": "6", "quote": "", "note": "The sheet: built in the 1640s."}
    out, path = cited_site(tmp_path, monkeypatch, r, gid=8)
    card = json.loads((out / "cards" / "08.json").read_text())["8"]
    assert card["yc"] == {"s": "stadsholmen", "u": SHLIST}
    # without the harvest: a warning only, since no committed step makes it
    capsys.readouterr()
    assert cited_errors(validate(out, path)) == []
    assert "cannot check that 1 AB Stadsholmen rows are on properties its fact sheets cover" in capsys.readouterr().err
    sheets = out.parents[2] / "data" / cited.SHEETS
    sheets.parent.mkdir(parents=True)
    sheets.write_text(json.dumps({"Diana1-FAKTABLAD.pdf": {"fastighet": "DIANA 1"}}), encoding="utf-8")
    assert cited_errors(validate(out, path)) == [
        "cited: row 1 (gid 8) cites AB Stadsholmen's fact sheet, but its footprint is on no property the harvested "
        "sheets cover (the permission covers Gamla stan's sheets)"]
    sheets.write_text(json.dumps({"Diana2-FAKTABLAD.pdf": {"fastighet": "DIANA 2"}}), encoding="utf-8")
    assert cited_errors(validate(out, path)) == []
    # its credit, AB Stadsholmen / Stadsmuseet, must be in sources.yml
    errors = validate(out, path, sources=[s for s in CREDITS if s["id"] != "stadsholmen_faktablad"])
    assert "cited: source stadsholmen_faktablad is not in sources.yml (its credit would be missing)" in errors


def test_a_fixture_build_never_reads_the_repo_table(tmp_path, monkeypatch):
    # validate's default: no table (s99's main and build_dist's gate pass the repo's); the stray check still runs
    from tests.test_s99_validate import check
    out, _ = cited_site(tmp_path, monkeypatch, {}, ship={"ysrc": SRC_NONE, "yflag": UNKNOWN, "year": 0,
                                                          "year_from": 0, "year_to": 0, "period": 0})
    monkeypatch.setattr(cited, "read", lambda *a, **k: pytest.fail("read the repo's table"))
    assert check(out, sources=CREDITS) == []
