"""The permit index's list pages (pipeline/bygglov.py), read from trimmed copies of the app's pages in
tests/fixtures/bygglov/: the markup as Stadsarkivet's search app served it on 2026-10-20, every value made up (no real
property designation is written in a public file)."""
import re
from pathlib import Path

import pytest

from pipeline import bygglov
from pipeline.bygglov import PageError

FIXTURES = Path(__file__).with_name("fixtures") / "bygglov"
# Every kvarter the fixtures name: made up, and checked against the city's kvarter when the fixtures were made.
MADE_UP = {"Provkvarteret", "Testgården", "Exempelbacken", "Påhittet", "Övningen Större", "Låtsashagen",
           "Mönstervägen", "Utkastet", "Attrappen", "Modellbygget", "Fantasin", "Teststugan", "Övningsgården",
           "Återbudet", "Påhittet Mindre (Ka)", "Provstaden Stg", "Exempelstad", "Övningsbacken",
           "Låtsaslunden & Testängen", "Fiktiva Höjden", "Diktade Ängen"}


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_a_full_page_gives_its_ten_cards_as_written():
    total, cards = bygglov.parse_page(page("page_full.html"))
    assert total == 108_078 == bygglov.EXPECTED_TOTAL
    assert [c["id"] for c in cards] == list(range(50_001, 50_011))
    assert cards[0] == {"id": 50_001, "kvarter": "Provkvarteret", "nr": "4", "dnr": "12D/58", "year": "1964",
                        "akt": "90001", "scan": "Prov 1_Page_001.jpg"}
    assert cards[5]["kvarter"] == "Övningen Större"          # both row classes (alternating, nonalternating) are read
    assert all(tuple(c) == bygglov.FIELDS for c in cards)
    bygglov.check_page(5000, total, cards)


def test_the_last_page_holds_eight_cards():
    total, cards = bygglov.parse_page(page("page_last.html"))
    assert [c["id"] for c in cards] == list(range(108_071, 108_079))
    assert cards[-1]["kvarter"] == "Återbudet" and cards[-1]["dnr"] == "271A Brd/60"
    bygglov.check_page(10_807, total, cards)
    assert bygglov.N_PAGES == 10_808 and bygglov.expected_ids(10_807) == list(range(108_071, 108_079))


def test_a_page_past_the_end_has_the_count_and_no_card():
    total, cards = bygglov.parse_page(page("page_past_end.html"))
    assert (total, cards) == (108_078, [])
    with pytest.raises(ValueError, match="outside"):
        bygglov.check_page(10_808, total, cards)


def test_odd_values_are_kept_as_the_archive_wrote_them():
    total, cards = bygglov.parse_page(page("page_odd.html"))
    by_id = {c["id"]: c for c in cards}
    assert list(by_id) == list(range(11, 21))
    bygglov.check_page(1, total, cards)
    assert by_id[12]["dnr"] == ""                                     # an empty case number before its <br/>
    assert by_id[12]["scan"] == "Övningsblad utan ritningar_Page_0001.jpg"   # %c3%96 in the address
    assert (by_id[13]["kvarter"], by_id[13]["nr"], by_id[13]["dnr"], by_id[13]["year"]) == \
        ("Påhittet Mindre (Ka)", "1,3", "IV: 2214/68", "-")
    assert (by_id[14]["kvarter"], by_id[14]["nr"]) == ("Provstaden Stg", "1570")
    assert by_id[15]["nr"] == "2:40"
    assert (by_id[16]["nr"], by_id[16]["dnr"]) == ("3013-3015", "IV:1911/69 IV:2201/69")
    assert by_id[17]["kvarter"] == "Låtsaslunden & Testängen"       # &amp;
    assert (by_id[18]["kvarter"], by_id[18]["nr"]) == ("Fiktiva Höjden", "12")   # &nbsp;, tabs and new lines
    assert "A\u030aterbudet" in page("page_odd.html")                # the fixture writes "A" + a combining ring
    assert by_id[19]["kvarter"] == "\u00c5terbudet"                  # read as one "Å" (escapes: no editor folds them)
    assert by_id[19]["dnr"] == "ÄV 141Brd/41"                        # &#196;
    assert by_id[20]["year"] == ""


def test_the_fixtures_name_only_made_up_kvarter():
    for name in ("page_full.html", "page_last.html", "page_odd.html", "page_past_end.html"):
        _, cards = bygglov.parse_page(page(name))
        assert {c["kvarter"] for c in cards} <= MADE_UP, name


def full_with(old: str, new: str, count: int = 1) -> str:
    s = page("page_full.html")
    assert old in s
    return s.replace(old, new, count)


def test_a_changed_layout_is_refused():
    with pytest.raises(PageError, match="5 cells"):     # a cell gone
        bygglov.parse_page(re.sub(r'<td width="4"><div class="cell-content-wrapper">\s*<span>12D/58 <br/></span>\s*'
                                  r"</div></td>", "", page("page_full.html"), count=1))
    with pytest.raises(PageError, match="Visa"):
        bygglov.parse_page(full_with('href="Visa/50001/50001', 'href="Kort/50001/50001'))
    with pytest.raises(PageError, match="Visa"):
        bygglov.parse_page(full_with('href="Visa/50001/50001', 'href="Visa/50001/50002'))
    with pytest.raises(PageError, match="unknown class"):
        bygglov.parse_page(full_with('<tr class="arende-table-row arende-table-row-alternating">',
                                     '<tr class="arende-table-card">'))
    with pytest.raises(PageError, match="count label"):
        bygglov.parse_page(full_with('id="MainContent_AntalTraffarLabel"', 'id="MainContent_Antal"'))
    with pytest.raises(PageError, match="result table"):
        bygglov.parse_page(full_with('id="MainContent_Register_GridView"', 'id="MainContent_Lista"'))


def test_rows_outside_the_result_table_are_not_cards():
    s = full_with("</body>", '<table><tr class="sidfot"><td>Kontakt</td></tr></table></body>')
    assert len(bygglov.parse_page(s)[1]) == 10


def test_the_count_label_reads_any_thousands_separator_and_may_be_blank():
    assert bygglov.parse_total(full_with(">108 078<", ">108 078<")) == 108_078
    assert bygglov.parse_total(full_with(">108 078<", ">108&nbsp;078<")) == 108_078
    assert bygglov.parse_total(full_with(">108 078<", "><")) is None


def test_check_page_refuses_a_changed_index():
    total, cards = bygglov.parse_page(page("page_full.html"))
    with pytest.raises(PageError, match="it changed"):
        bygglov.check_page(5000, 108_079, cards)
    with pytest.raises(PageError, match="it changed"):
        bygglov.check_page(5000, None, cards)
    with pytest.raises(PageError, match="order changed"):
        bygglov.check_page(5001, total, cards)                    # the ids of another page
    with pytest.raises(PageError, match="order changed"):
        bygglov.check_page(5000, total, cards[:9])                # a card missing
    with pytest.raises(PageError, match="order changed"):
        bygglov.check_page(5000, total, [cards[1], cards[0], *cards[2:]])   # the order changed
    bygglov.check_page(0, 25, [{"id": i} for i in range(1, 11)], expected_total=25)
    bygglov.check_page(2, 25, [{"id": i} for i in range(21, 26)], expected_total=25)


def test_page_url_and_expected_ids():
    assert bygglov.page_url(5000) == "https://sok.stadsarkivet.stockholm.se/Databas/bygglov1875-1980/Sok?sidindex=5000"
    assert bygglov.expected_ids(0) == list(range(1, 11))
    with pytest.raises(ValueError):
        bygglov.expected_ids(-1)


def test_closing_year():
    assert bygglov.closing_year("1934") == 1934
    assert bygglov.closing_year(" 1934 ") == 1934
    assert [bygglov.closing_year(y) for y in ("-", "", "193", "19345", "1934?")] == [None] * 5


def test_stg_is_a_word_of_its_own():
    for kv in ("Bromma Stg", "Hässelby Villastad Stg", "Stg", "STG", "stg", "Hässelby Stg.", "Stg3829"):
        assert bygglov.is_stg(kv), kv
    for kv in ("Västgöten", "Kastgatan", "Provkvarteret", "Stgården", "", "Mästgården"):
        assert not bygglov.is_stg(kv), kv


# ---------- the matcher's side: made-up designations only ----------

def test_closing_years():
    assert bygglov.closing_years("1934") == (1934,)
    assert bygglov.closing_years(" 1884, 1885 ") == (1884, 1885)       # a card closed in two years
    assert [bygglov.closing_years(y) for y in ("-", "", "1934?", "19345", "1884 och 1885")] == [()] * 5


def test_fold_takes_case_accents_and_spaces_but_never_the_swedish_letters():
    assert bygglov.fold("  Exempelkupén \t ") == "EXEMPELKUPEN"
    assert bygglov.fold("EXEMPELKUPÉN") == "EXEMPELKUPEN"
    assert bygglov.fold("Övningsgården") == "ÖVNINGSGÅRDEN"
    assert bygglov.fold("Åttrappen") == "ÅTTRAPPEN"           # a decomposed Å is one Å
    assert bygglov.fold("Låtsashagen Större") == "LÅTSASHAGEN STÖRRE"


def test_kvarter_name_drops_the_parish_and_keeps_mindre_and_storre():
    assert bygglov.kvarter_name("Påhittet Mindre (Ka)") == ("PÅHITTET MINDRE", "KA")
    assert bygglov.kvarter_name("Provgården (He)") == ("PROVGÅRDEN", "HE")
    assert bygglov.kvarter_name("Övningen Större") == ("ÖVNINGEN STÖRRE", "")
    assert bygglov.kvarter_name("Provstaden Stg") == ("PROVSTADEN STG", "")
    assert bygglov.kvarter_name("") == ("", "")


def test_numbers_expands_lists_and_short_ranges_and_keeps_trakt_numbers():
    assert bygglov.numbers("10") == ("10",)
    assert bygglov.numbers("010") == ("10",)
    assert bygglov.numbers("1,3") == bygglov.numbers("1, 3") == ("1", "3")
    assert bygglov.numbers("26+27") == ("26", "27")
    assert bygglov.numbers("3013-3015") == ("3013", "3014", "3015")
    assert bygglov.numbers("4-7, 19-22") == ("4", "5", "6", "7", "19", "20", "21", "22")
    assert bygglov.numbers("2:40") == bygglov.numbers("02:040") == ("2:40",)
    assert bygglov.numbers("1,1") == ("1",)
    assert bygglov.numbers("1-20") == tuple(str(i) for i in range(1, 21))     # MAX_NUMBERS, just
    for nr in ("", " ", "105A", "17AC", "S:47", "1.2", "14 (5)", "5-3", "1-21", "1,", ",".join(map(str, range(21)))):
        assert bygglov.numbers(nr) is None, nr


def test_our_designations():
    assert bygglov.designation("PROVKVARTERET 4") == "PROVKVARTERET 4"
    assert bygglov.designation("Provkvarteret  4 ") == "PROVKVARTERET 4"
    assert bygglov.designation("EXEMPELKUPÉN 2") == "EXEMPELKUPEN 2"
    assert bygglov.designation("PROVBY 5:6") == "PROVBY 5:6"
    for f in ("", None, float("nan"), "TESTGÅRDEN S:51"):                    # nothing, or a joint property
        assert bygglov.designation(f) is None, f
    assert bygglov.split_designation("TESTGÅRDEN 12") == ("TESTGÅRDEN", "12")
    assert bygglov.split_designation("PROVBY 5:6") == ("PROVBY", "5:6")
    assert bygglov.split_designation("PROVGRÄND XV:S PORT 6") == ("PROVGRÄND XV:S PORT", "6")
    assert bygglov.split_designation("PROVBY") is None


def test_opened_reads_the_year_at_the_end_of_the_case_number():
    cases = [("564/1875", 1876, 1875), ("65D2/35", 1937, 1935), ("IV:1800/67", 1969, 1967),
             ("841-2790-81", 1983, 1981), ("Häs 1/10-24", 1925, 1924), ("Spå16/4-37", 1937, 1937),
             ("Bro 16/9 —46", 1947, 1946), ("Bro 15/8 45", 1946, 1945), ("IV:1911/69 IV:2201/68", 1970, 1968),
             ("ÄV 141Brd/41", 1942, 1941),
             ("12/23", 1960, None),          # 37 years before closing: no century fits
             ("527/1902", 1901, None),        # opened after it closed: a misreading
             ("564/1855", 1876, None),        # before OPENED_MIN
             ("12D/58", None, 1958), ("98/85", None, 1885),   # undated cards: the later century up to INDEX_END
             ("", 1934, None), ("Ärende I", 1934, None)]
    for dnr, close, want in cases:
        assert bygglov.opened(dnr, close) == want, (dnr, close)


def test_authority_of_a_case_number():
    cases = {"IV:2214/68": "roman", "ÄI IV:1220/66": "roman", "141Brd/41": "Brd", "ÄV 141Brd/41": "Brd",
             "12Brmd/45": "Brmd", "12D/58": "D", "698D2/36": "D", "Spå16/4-37": "rural", "Häs 1/10-24": "rural",
             "564/1875": "plain", "841-2790-81": "plain", "": "none", " ": "none", "FSK/1920": "other"}
    for dnr, want in cases.items():
        assert bygglov.authority(dnr) == want, dnr
