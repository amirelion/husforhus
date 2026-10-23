"""docs/accuracy.md from the accuracy table: the committed page
explains the table in plain words and is aggregate-only; the names go to the internal page data/review-years.md."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from pipeline import city, report_accuracy, s02_years
from tests.tinycity import ACCURACY, tiny_city

GAINS = [{"gid": 10, "qid": "Q1", "name": "Schönfeldtska huset", "year_from": 1630, "year_to": 1630, "placement": "inside"},
         {"gid": 3, "qid": "Q2", "name": "Typhon 16", "year_from": 1905, "year_to": 1907, "placement": "nearest"},
         {"gid": 9, "qid": "Q3", "name": "Villa Solbacken", "year_from": 1912, "year_to": 1912, "placement": "inside"}]
REVIEW = {"wikidata_gains": GAINS, "wikidata_vs_raa": [{"gid": 0}], "wikidata_century": [{"qid": "Q9"}],
          "wikidata_vs_area": [{"gid": 4}, {"gid": 5}], "wikidata_vs_curated": [],
          "osm_vs_raa": [{"gid": 1, "osm_id": "way/123456"}] * 4}


def split(n_all, n_est, right, band):
    return {"n_all": n_all, "n_estimate": n_est, "right_estimate": right, "in_band_estimate": band}


def accuracy(external=None) -> dict:
    """The tiny table, with a cell of each kind the page explains, the table by true period and an external check."""
    acc = json.loads(json.dumps(ACCURACY))
    acc["cells"] += [
        {"group": "house", "era": "1976–1993", "inner": False, "n": 40, "median_error": 4.0, "right_period": 0.6,
         "within_one": 0.9, "band": 15, "status": "unknown"},                        # too few right
        {"group": "house", "era": "1866–1919", "inner": False, "n": 31, "median_error": 9.0, "right_period": 0.742,
         "within_one": 0.9, "band": 25, "status": "unknown"},                        # band too wide
        {"group": "apartments", "era": "1946–1975", "inner": False, "n": 2909, "median_error": 2.0,
         "right_period": 0.78, "within_one": 0.93, "band": 10, "status": "unknown"},  # a type the map does not estimate
        {"group": "outbuilding", "era": "1946–1975", "inner": False, "n": 126, "median_error": 2.0,
         "right_period": 0.659, "within_one": 0.97, "band": 10, "status": "unknown"},  # ... and too often wrong anyway
    ]
    by = {r["period"]: r for r in acc["by_true_period"]}
    by["p12"].update(n=230, right=23, n_estimate=12, right_estimate=2)
    by["p11"].update(n=40, right=11, n_estimate=0, right_estimate=0)
    acc["external"] = external or {"status": "measured", **split(551, 40, 18, 22), "n_unknown": 511,
                                   "before_1990": split(332, 30, 18, 20), "from_1990": split(219, 10, 0, 2)}
    return acc


def section(md: str, heading: str) -> str:
    """The text of one `## ` section, without its heading."""
    return md.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def page(acc=None, gamla=True):
    _, y, _ = tiny_city()
    return report_accuracy.render(accuracy() if acc is None else acc, y, REVIEW,
                                  y[y.gid.isin([0, 1, 10])] if gamla else None, "2026-10-20", "v20261020-m3b")


def test_the_page_opens_with_a_plain_summary_whose_shares_add_up():
    md = page()
    assert md.startswith("# How the years are known, and how good the estimates are (build v20261020-m3b of 2026-10-20)")
    short = section(md, "In short")
    # the tiny city: 6 with a record, 1 by area, 2 estimated (one a period only), 2 unknown; shares by largest remainder
    assert "**6 (54.5%) have a year from a record**" in short and "**1 (9.1%) have the year of their area**" in short
    assert "**2 (18.2%) are estimated**" in short and "**2 (18.2%) stay unknown**" in short
    assert "Only houses (villa, row, chain) are estimated" in short
    for limit in ("mostly older", "apartment blocks", "property units formed late", "2008"):
        assert limit in short, limit
    # Every estimate is a private house, so the map shows its decade, and the summary says so
    assert 'shown as an estimated decade ("≈ 1950s"), because every estimated house is a private house, which shows ' \
           "only its decade" in short
    # ... and gives one accuracy figure with its n (M1 f): the cells the map uses, from by_true_period's counts
    assert "How far to trust the estimates: in the test, 64% of the test houses in the cells the map uses were " \
           "estimated in the right period (30 of 47), but the test can only use" in short
    # M1 (b): the other types' own reason, from their cells (the outbuildings' 66% is under 70%)
    assert "and the other types are below 70% right in the test itself" in short
    # M1 (a): the check does not "show what the blind spot costs"; it says what it shows and that it is small
    assert "blind spot costs" not in short
    assert ("The independent check further down shows how many buildings from 1990 or later still get an estimate."
            in short)


def test_the_sources_are_named_in_words_and_their_shares_add_up_to_100():
    md = page()
    table = section(md, "Where the years come from")
    shares = [float(s) for s in re.findall(r"\| ([\d.]+)% \|", table)]
    assert len(shares) == 11 and round(sum(shares), 1) == 100.0
    assert "| **All buildings** | **11** | **100.0%** |" in table
    for name in ("RAÄ's building register", "RAÄ's older register file", "Wikidata", "OpenStreetMap",
                 "A hand-checked list of landmarks", "No source: the year stays unknown"):
        assert name in table, name
    # Only the default look (Ärg) hatches "Year unknown" (web/test/themes.test.mjs); the others draw it flat
    assert '| No source: the year stays unknown, shown as "Year unknown" |' in table
    assert ('stay unknown** and are shown as "Year unknown" (pale and hatched in the default look).'
            in section(md, "In short"))
    assert "drawn hatched" not in md
    # no raw field name or developer word anywhere on the page
    for raw in ("raa_area", "raa_old", "ESTIMATE", "PERIOD", "kNN", "80th percentile", "| exact |", "| range |",
                "| long |", "| none |", "| area |", "| estimate |", "| period |", "| unknown |", "`"):
        assert raw not in md.replace("`pipeline/report_accuracy.py`", ""), raw


def test_the_summary_and_the_table_give_one_share_for_one_count():
    # The build of 2026-10-17 showed its 6,263 area-dated buildings as 8.0% in the
    # summary (four groups rounded together) and 8.1% in the table (eight sources rounded together)
    by_src = {"none": 43_453, "curated": 72, "raa": 22_039, "raa_area": 6_263, "wikidata": 131, "estimate": 4_558,
              "raa_old": 809, "osm": 418}
    by_flag = {"exact": 23_469, "range": 0, "long": 0, "area": 6_263, "estimate": 4_558, "period": 0,
               "unknown": 43_453}
    kinds, table = report_accuracy.kind_shares(by_flag, by_src)
    rows = dict(zip([k for k, _ in report_accuracy.SOURCES], table))
    assert kinds == ["30.2%", "8.0%", "5.9%", "55.9%"]                     # the closest rounding of the four
    assert kinds[1] == rows["raa_area"] and kinds[2] == rows["estimate"] and kinds[3] == rows["none"]
    record = sum(float(rows[k][:-1]) for k in ("curated", "raa", "raa_old", "wikidata", "osm"))
    assert round(record, 1) == 30.2 and round(sum(float(x[:-1]) for x in table), 1) == 100.0
    with pytest.raises(ValueError, match="ysrc counts disagree"):
        report_accuracy.kind_shares({**by_flag, "area": 6_262, "unknown": 43_454}, by_src)


def test_a_cited_record_counts_as_a_record_even_with_a_century_only():
    # pipeline/cited.py: a published record checked by hand; a century or a period only is PERIOD, from a record
    from pipeline.codes import EXACT, PERIOD, SRC_CITED
    _, y, _ = tiny_city()
    y.loc[7, ["year", "year_from", "year_to", "ysrc", "yflag"]] = [1655, 1600, 1699, SRC_CITED, PERIOD]
    y.loc[5, ["year", "year_from", "year_to", "ysrc", "yflag"]] = [1643, 1643, 1643, SRC_CITED, EXACT]
    acc = accuracy()
    acc["result"]["period"] = 2
    md = report_accuracy.render(acc, y, REVIEW, y[y.gid.isin([5, 7, 10])], "2026-10-20", "v20261020-m3b")
    short = section(md, "In short")
    # 6 + the two cited; still 2 estimated (the kNN's estimate and its one period-only year), none unknown
    assert "**8 (72.7%) have a year from a record**" in short
    assert ("a published record checked by hand (KulturNav, Swedish Wikipedia, the City Museum, AB Stadsholmen or the "
            "City's stage years)") in short
    assert "(1 of them only to a century or a period, or to two readings where sources differ, shown with ≈)" in short
    assert "**2 (18.2%) are estimated** from similar dated buildings nearby (1 of them with the period only)" in short
    table = section(md, "Where the years come from")
    assert ("| A published record checked by hand (KulturNav, Swedish Wikipedia, the City Museum, AB Stadsholmen, the "
            "City) | 2 | 18.2% |") in table
    assert ("where a published record gives only a century or a period, or two records give different years, the map "
            "shows that period with ≈ (1)") in table
    assert "and 1 get the period only." in md
    assert "Of its 3 buildings, 3 have a year from a record, 0 the year of their area, 0 are estimated" in md
    by_flag, by_src = report_accuracy.counts(y)
    assert report_accuracy.kinds(by_flag, report_accuracy.cited_periods(y)) == (8, 1, 2, 0)


def test_the_terms_and_the_method_are_explained_without_jargon():
    md = page()
    assert "[12 periods](#the-12-periods)" in md and "## The 12 periods" in md
    periods = section(md, "The 12 periods")
    assert "| Medieval & early Vasa | until 1610 |" in periods and "| Waterfront districts | 1994 on |" in periods
    for term in ("**in the right period**", "**within one period**", "**within the band**", "*kvarter*", "city block"):
        assert term in md, term
    how = section(md, "How a house is estimated")
    assert "the 20 most similar dated buildings nearby" in how and "8 in 10 true years fall inside" in how
    assert "at least 70%" in how and "±15 years or less" in how and "at least 30 test buildings" in how
    assert "never shows a period on its own" in how
    # I2: what the map shows, and what the band means for a decade; M1 (c): the coverage is over every type
    assert 'The map shows an estimated decade ("≈ 1950s") only when all of these hold:' in how
    assert "The decade shown is the decade of the estimated year. With a band of ±5 years, 8 in 10 true years lie " \
           "within 5 years of that year, so the house can also be from the decade before or after the one shown." in md
    assert "(over every building type's measured cells, not houses alone)" in how
    assert "≈ year ± band" not in md and "as ≈ year" not in md
    # M1 (e): the median error is defined
    assert "The median error is the typical (median) difference between the estimate and the true year, in years." in md


def test_the_cells_say_what_the_map_does_and_why():
    md = page()
    assert "| Houses (villa, row, chain) | 1946–1975 | outer | 35 | 1 y | 80% | 97% | ±5 | estimated (decade shown) |" in md
    assert "| Houses (villa, row, chain) | 1976–1993 | outer | 40 | 4 y | 60% | 90% | ±15 | stays unknown: too few right |" in md
    assert "| Houses (villa, row, chain) | 1866–1919 | outer | 31 | 9 y | 74% | 90% | ±25 | stays unknown: band too wide |" in md
    assert ("| Apartment blocks | 1946–1975 | outer | 2,909 | 2 y | 78% | 93% | ±10 | stays unknown: type not estimated |"
            in md)
    assert "| Apartment blocks | 1866–1919 | inner | 5 | – | – | – | – | stays unknown: too few to measure |" in md
    # the cells the map uses, weighted by their test buildings: 28 + 2 of 35 + 12 (by_true_period's counts)
    assert "64% of the test houses in the cells the map uses were estimated in the right period (30 of 47)" in md


def test_the_test_by_true_period_shows_where_it_is_weak():
    md = page()
    weak = section(md, "Where the test is weak")
    assert "| Waterfront districts (1994 on) | 230 | 10% | 12 | 2 of 12 |" in weak
    assert "| Postmodern & infill (1976–1993) | 40 | 28% | 0 | – |" in weak
    assert "| Folkhem & ABC towns (1946–1964) | 35 | 80% | 35 | 80% |" in weak
    assert "Built 1994 or later: 10% in the right period (230 test buildings)" in weak
    assert "the estimate is weakest for the oldest and the newest buildings" in weak        # M1 (d)


def test_the_independent_check_says_what_it_measures_who_is_in_it_and_the_1990_split():
    md = page()
    ext = section(md, "The independent check")
    assert "only Wikidata or OpenStreetMap date" in ext and "219 of the 551 were built in 1990 or later" in ext
    assert "the map would show 40 of them as an estimate: 18 (45%) in the right period and 22 (55%) with the true " \
           "year inside the band; the other 511 would stay unknown" in ext
    assert "Built before 1990: 18 of 30 (60%) in the right period, 20 of 30 (67%) inside the band." in ext
    assert "Built in 1990 or later: 0 of 10 in the right period, 2 of 10 inside the band." in ext


def test_an_independent_check_with_too_few_estimates_prints_counts_never_a_percentage():
    few = {"status": "not measurable", **split(551, 6, 3, 4), "n_unknown": 545,
           "before_1990": split(332, 4, 3, 4), "from_1990": split(219, 2, 0, 0)}
    ext = section(page(accuracy(few)), "The independent check")
    assert "the map would show 6 of them as an estimate: 3 in the right period and 4 with the true year inside the " \
           "band" in ext
    assert "too few for a percentage" in ext and "%" not in ext


def test_the_summary_says_when_the_check_kept_every_new_building_off_the_map():
    # M1 (a), m3b's case: no building from 1990 on would be shown, and the check is too small for a percentage
    none_new = {"status": "not measurable", **split(551, 10, 6, 7), "n_unknown": 541,
                "before_1990": split(332, 10, 6, 7), "from_1990": split(219, 0, 0, 0)}
    short = section(page(accuracy(none_new)), "In short")
    assert ("The independent check further down shows the rule keeping every building from 1990 or later in it off "
            "the map, but it is too small to confirm the test's figure." in short)


def test_gamla_stan_and_the_hand_check_list_with_all_six_sizes():
    md = page()
    assert "Of its 3 buildings, 3 have a year from a record, 0 the year of their area, 0 are estimated and 0 stay " \
           "unknown." in section(md, "Gamla stan")
    check = section(md, "Wikidata and OpenStreetMap: the hand-check list")
    for row in ("| Got their year from Wikidata alone | 3 |",
                "| … of them placed on the nearest building (the item's point lies outside every footprint) | 1 |",
                "| A Wikidata year more than 10 years from RAÄ's | 1 |",
                "| A Wikidata year more than 10 years from the area's | 2 |",
                "| A Wikidata year more than 10 years from the hand-checked list | 0 |",
                "| An OpenStreetMap year more than 10 years from RAÄ's | 4 |",
                "| Wikidata items with only a century (not used) | 1 |"):
        assert row in check, row
    assert "review-years" not in md and "internal" not in md and "data/" not in md


def test_the_page_is_aggregate_only():
    # Aggregate-only (the repository goes public): no name, no Wikidata or OSM id, no gid, no per-building
    # year, no property-unit key (FNR) or anything shaped like one (eight digits, with or without separators). The tiny
    # city's gid 9 is a private house; a names page would say 1912, the map says the 1910s.
    md = page()
    for leak in ("Schönfeldtska", "Typhon", "Solbacken", "1630", "1905", "1912", "way/", "123456"):
        assert leak not in md, leak
    assert "gid" not in md.lower() and re.search(r"\bQ\d+\b", md) is None
    assert "fnr" not in md.lower() and re.search(r"\b1\d[ ,.]?\d{3}[ ,.]?\d{3}\b", md.replace("20261020", "")) is None


def test_names_page_lists_the_gains_with_placement_and_the_private_flag():
    _, y, _ = tiny_city()
    names = report_accuracy.names_page(REVIEW, y)
    assert names.startswith("# Wikidata gains for the M3 review (internal")
    assert "| Schönfeldtska huset | Q1 | 1630 | inside |  |" in names
    assert "| Typhon 16 | Q2 | 1905–1907 | nearest |  |" in names
    assert "| Villa Solbacken | Q3 | 1912 | inside | yes |" in names      # gid 9 is the tiny city's private period-only house


def test_main_writes_both_pages(tmp_path):
    _, y, _ = tiny_city()
    y.to_parquet(tmp_path / "years.parquet")
    (tmp_path / "accuracy.json").write_text(json.dumps(accuracy()))
    (tmp_path / "review.json").write_text(json.dumps(REVIEW))
    report_accuracy.main(["--accuracy", str(tmp_path / "accuracy.json"), "--years", str(tmp_path / "years.parquet"),
                          "--review", str(tmp_path / "review.json"), "--buildings", str(tmp_path / "none.parquet"),
                          "--stadsdelar", str(tmp_path / "none.shp"), "--date", "2026-10-20", "--version", "v20261020-m3",
                          "--out", str(tmp_path / "docs" / "accuracy.md"), "--names-out", str(tmp_path / "data" / "review-years.md")])
    md = (tmp_path / "docs" / "accuracy.md").read_text()
    assert "build v20261020-m3 of 2026-10-20" in md and "## Gamla stan" not in md
    assert "## Wikidata and OpenStreetMap: the hand-check list" in md
    assert "Schönfeldtska" not in md and "Schönfeldtska huset" in (tmp_path / "data" / "review-years.md").read_text()
    assert pd.read_parquet(tmp_path / "years.parquet").shape[0] == 11


# Final review PRIVACY-1 (option a): the colour of a private house is its period's, so it can narrow the decade to the
# years the decade shares with that period. The page says so, and how far: never below the narrowest part the rule
# allows (s02_years.MIN_PRIVATE_OVERLAP stays 2; with today's periods the narrowest part is 4 years).
def test_the_page_says_a_private_houses_colour_can_narrow_its_decade_but_never_below_four_years(monkeypatch):
    # the structural minimum against the rule itself, year by year: decade, its period (the decade's middle year's when
    # they would share fewer than MIN_PRIVATE_OVERLAP years) and the years they share
    def shared(y):
        d = y // 10 * 10
        def common(p):
            return min(d + 9, city.PERIODS[p][4]) - max(d, city.PERIODS[p][3]) + 1
        p = city.period_index(y)
        return common(p) if common(p) >= s02_years.MIN_PRIVATE_OVERLAP else common(city.period_index(d + 5))
    assert s02_years.MIN_PRIVATE_OVERLAP == 2
    assert report_accuracy.fewest_private_years() == min(shared(y) for y in range(1000, 2027)) == 4
    sentence = ("A private house (a villa, a row or chain house, or an allotment cottage) shows only its decade, never "
                "its exact year. Its colour still shows its period, so when a period begins or ends within the decade, "
                "the colour narrows the decade to the part inside that period, never to fewer than 4 years.")
    assert sentence in section(page(), "Where the years come from")
    monkeypatch.setattr(report_accuracy, "MIN_PRIVATE_OVERLAP", 5)       # option (b), not taken: 1946 + 1940s -> 6
    assert report_accuracy.fewest_private_years() == 5


# Final review ALIGNMENT-2: the late-unit check cannot test a house with no property-unit key (FNR 0), so it passes;
# the page says so and how many, from data/buildings.parquet (which main already reads for Gamla stan).
def test_the_page_says_a_house_with_no_property_unit_key_passes_the_late_unit_check():
    b, y, _ = tiny_city()
    units = b[["gid", "fnr", "prod_year"]].copy()
    units.loc[units.gid == 8, "fnr"] = 0                                   # the estimate; gid 9 (period only) keeps its key
    def how(units):
        return section(report_accuracy.render(accuracy(), y, REVIEW, None, "2026-10-20", "v20261020-m3b", units=units),
                       "How a house is estimated")
    lead = ("- its property unit was not formed late (such units are mostly new development); a house with no "
            "property-unit key passes this check")
    assert f"{lead} (estimated houses with no key: 1 of 2, all of them first mapped before 2008);" in how(units)
    units.loc[units.gid == 8, "prod_year"] = 0                             # first mapped: not known
    assert f"{lead} (estimated houses with no key: 1 of 2, 0 of them first mapped before 2008);" in how(units)
    assert f"{lead};" in how(None)                                         # no buildings file: no count
    assert "fnr" not in how(units).lower()


def test_main_counts_the_estimated_houses_with_no_property_unit_key(tmp_path):
    b, y, _ = tiny_city()
    b.loc[b.gid == 8, "fnr"] = 0
    b.to_parquet(tmp_path / "buildings.parquet")
    y.to_parquet(tmp_path / "years.parquet")
    (tmp_path / "accuracy.json").write_text(json.dumps(accuracy()))
    report_accuracy.main(["--accuracy", str(tmp_path / "accuracy.json"), "--years", str(tmp_path / "years.parquet"),
                          "--review", str(tmp_path / "none.json"), "--buildings", str(tmp_path / "buildings.parquet"),
                          "--stadsdelar", str(tmp_path / "none.shp"), "--date", "2026-10-20",
                          "--version", "v20261020-m3", "--out", str(tmp_path / "accuracy.md"),
                          "--names-out", str(tmp_path / "names.md")])
    assert "(estimated houses with no key: 1 of 2, all of them first mapped before 2008);" in \
        (tmp_path / "accuracy.md").read_text()


# Final review PRIVACY-3: the committed page names the build it describes in its first line; a rebuild under a new
# name that forgets to regenerate it would ship one build while the page describes another. Skipped without a built
# web/data (CI) and on a fixture build (519 buildings: the page describes the whole city).
def test_the_committed_page_describes_the_build_that_ships():
    current = Path("web/data/current.json")
    if not current.exists():
        pytest.skip("needs web/data/current.json (a built city)")
    version = json.loads(current.read_text(encoding="utf-8"))["version"]
    config = json.loads((current.parent / version / "stockholm.json").read_text(encoding="utf-8"))
    if config["stats"]["buildings"] < city.MIN_BUILDINGS:
        pytest.skip(f"{version} is a fixture build")
    first = report_accuracy.DOC.read_text(encoding="utf-8").splitlines()[0]
    m = re.search(r"\(build (\S+) of \d{4}-\d{2}-\d{2}\)$", first)
    assert m, first
    assert m.group(1) == version, (f"docs/accuracy.md describes {m.group(1)} but web/data/current.json ships "
                                   f"{version}: regenerate it (uv run python -m pipeline.report_accuracy --version "
                                   f"{version})")


def test_the_permit_years_have_their_section_with_the_caveat_and_the_blind_spot_from_the_block():
    from pipeline.codes import EXACT, RANGE, SRC_BYGGLOV
    from tests.test_validate_bygglov import good
    _, y, _ = tiny_city()
    for g, flag in ((7, EXACT), (8, RANGE)):
        y.loc[g, ["year", "year_from", "year_to", "ysrc", "yflag", "private"]] = [1930, 1930, 1939, SRC_BYGGLOV, flag,
                                                                                  True]
    acc = accuracy()
    acc["bygglov"] = good()["accuracy"]["bygglov"]
    acc["bygglov"]["shipped"] = {"n": 2, "exact": 1, "range": 1}
    md = report_accuracy.render(acc, y, REVIEW, None, "2026-10-20", "v20261020-m3b")
    s = section(md, "The building-permit years (Stockholm City Archives)")
    assert s.lstrip().startswith("2 buildings get their year from the City Archives' (Stadsarkivet's) card index")
    assert "the permit year fell in the right period at least 85% of the time and in the same decade at least 70%" in s
    assert "All of them are private houses, so they show only their decade." in s
    # the owner's caveat, in plain words, and the way to report it
    assert ("**It can be wrong.** A house built after 1980 on an older property can sometimes show the earlier house's "
            'permit year. If you see one, please report it with "Something wrong?" on its card.') in s
    assert "**1 (2.5%) would get a permit year**" in s and "Of the 40 buildings from 1981 or later" in s
    assert "| No permit card names the property | 7 |" in s and "| Year unknown | 2 |" in s
    assert "| Houses (villa, row, chain) | 1920–1945 | outer | one | 40 | 95% | 90% | 92% | dates |" in s
    assert "1 more cells have fewer than 30 test buildings (5 in all)" in s
    assert "On the 40 test buildings in the cells the map uses, the permit year fell in the right period for 95%" in s
    assert "partly the files agreeing with themselves" in s
    # a closing year is not an exact year: the record kinds leave the two out and name them on their own
    table = section(md, "Where the years come from")
    assert "| The City Archives' building permits, 1875–1980 (Stadsarkivet) | 2 |" in table
    assert "a building-permit year is the year the property's first permit was closed (2)" in table
    # with another block the numbers follow it: nothing in the section is typed in
    acc["bygglov"]["blind_spot"] = {"n": 30, "dated": 0, "share": 0.0}
    md2 = report_accuracy.render(acc, y, REVIEW, None, "2026-10-20", "v20261020-m3b")
    assert "**0 (0.0%) would get a permit year**" in md2 and "Of the 30 buildings" in md2
    # a build without the tier says so, and one from before it has no section
    acc["bygglov"] = {"status": "absent"}
    assert "The building-permit years are not used" in report_accuracy.render(acc, y, REVIEW, None, "2026-10-20", "v")
    del acc["bygglov"]
    assert "building-permit years" not in page()
