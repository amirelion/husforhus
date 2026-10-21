"""The building-permit tier's matcher (pipeline/years_bygglov.py) on tiny synthetic cards and buildings. Every kvarter
here is made up (no real designation is written in a public file)."""
import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from pipeline import city
from pipeline import years_bygglov as yb
from tests import synth

P = city.BYGGLOV
OPEN = {**P, "block_years": None, "block_uncarded": None}     # the block check off, for the tests of everything else


def cards(*rows) -> pd.DataFrame:
    """A cards table (yb.CARD_COLUMNS) from (kvarter, nr, dnr, year) rows; ids from 1, akt numbers 900 + id."""
    return pd.DataFrame([{"id": i, "kvarter": k, "nr": nr, "dnr": dnr, "year": y, "akt": str(900 + i), "page": 0}
                         for i, (k, nr, dnr, y) in enumerate(rows, 1)], columns=yb.CARD_COLUMNS)


def props(*rows, p=P) -> pd.DataFrame:
    return yb.properties(yb.keys(cards(*rows)), p)


def town(rows, district="TESTDALEN") -> tuple[pd.DataFrame, np.ndarray]:
    b = synth.buildings(rows=[{"kategori": "Enbostadshus", **r} for r in rows])
    return b, np.array([r.get("district", district) for r in rows], dtype=object)


# ---------- cards ----------

def harvest(tmp_path, pages: dict, total=None) -> tuple:
    folder = tmp_path / "pages"
    folder.mkdir()
    n = 0
    for p, rows in pages.items():
        doc = {"page": p, "cards": [{"id": i, "kvarter": k, "nr": nr, "dnr": "", "year": y, "akt": "", "scan": ""}
                                    for i, k, nr, y in rows]}
        (folder / f"{p:05d}.json").write_text(json.dumps(doc), encoding="utf-8")
        n += len(rows)
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"cards": n if total is None else total, "cards_sha256": "f1"}), encoding="utf-8")
    return folder, manifest


def test_cards_are_built_once_from_a_complete_harvest_and_read_back(tmp_path):
    folder, manifest = harvest(tmp_path, {1: [(11, "Testgården", "4", "1934"), (12, "Provby", "5:6", "-")],
                                          0: [(1, "Provkvarteret", "1,3", "1928")]})
    out = tmp_path / "bygglov" / "cards.parquet"
    c = yb.cards(out, folder, manifest)
    assert c.id.tolist() == [1, 11, 12] and c.page.tolist() == [0, 1, 1]
    assert list(c.columns) == yb.CARD_COLUMNS and c.nr.tolist() == ["1,3", "4", "5:6"]
    assert pq.read_schema(out).metadata[yb.FINGERPRINT] == b"f1"
    for f in folder.iterdir():                     # the table is read back: the pages are not needed again
        f.unlink()
    assert yb.cards(out, folder, manifest).id.tolist() == [1, 11, 12]
    manifest.write_text(json.dumps({"cards": 0, "cards_sha256": "f2"}), encoding="utf-8")
    assert yb.cards(out, folder, manifest).empty                         # a new fingerprint: built again


def test_no_complete_harvest_gives_no_cards(tmp_path):
    folder, manifest = harvest(tmp_path, {0: [(1, "Testgården", "4", "1934")]})
    assert yb.cards(tmp_path / "c.parquet", folder, tmp_path / "missing.json") is None
    manifest.write_text(json.dumps({"cards": 1}), encoding="utf-8")       # no fingerprint: not complete
    assert yb.cards(tmp_path / "c.parquet", folder, manifest) is None
    other = tmp_path / "other"
    other.mkdir()
    folder2, manifest2 = harvest(other, {0: [(1, "Testgården", "4", "1934")]}, total=2)
    with pytest.raises(ValueError, match="manifest"):
        yb.cards(tmp_path / "c.parquet", folder2, manifest2)


# ---------- keys and properties ----------

def test_keys_name_properties_and_say_why_a_card_names_none():
    k = yb.keys(cards(("Testgården", "4", "12D/58", "1960"), ("Provstaden Stg", "1570", "", "1925"),
                      ("", "4", "", "1930"), ("Testgården", "105A", "", "1930"), ("Provgården (He)", "1", "", "1930"),
                      ("Provgården (Kf)", "2", "", "1931"), ("Testbacken", "1", "", "1930"),
                      ("Testbacken (Kf)", "2", "", "1930"), ("Låtsashagen (Ka)", "1,3", "", "1884, 1885"),
                      ("Exempelkupen", "2", "", "-")))
    assert k.groupby("id").reason.first().tolist() == ["", "stg", "no_kvarter", "no_number", "parish", "parish",
                                                       "parish", "parish", "", ""]
    named = k[k.reason == ""]
    assert named.key.tolist() == ["TESTGÅRDEN 4", "LÅTSASHAGEN 1", "LÅTSASHAGEN 3", "EXEMPELKUPEN 2"]
    assert named.close.tolist() == [1960, 1884, 1884, 0] and named.opened.tolist() == [1958, 0, 0, 0]
    assert named.authority.tolist()[0] == "D" and (k[k.reason != ""].key == "").all()


def test_the_year_is_the_earliest_closing_year_and_year_from_its_opening_year():
    pr = props(("Testgården", "4", "IV:1208/64", "1968"), ("Testgården", "4", "3873Brd/54", "1959"),
               ("Testgården", "4", "252Brd/61", "1965"), ("Testgården", "5", "12/1905", "1934"),
               ("Testgården", "6", "", "1934"), ("Testgården", "6", "", "1936"))
    assert pr.year.to_dict() == {"TESTGÅRDEN 4": 1959, "TESTGÅRDEN 5": 1934, "TESTGÅRDEN 6": 1934}
    assert pr.year_from["TESTGÅRDEN 4"] == 1954                    # opened 5 years before: within max_lag
    assert pr.year_from["TESTGÅRDEN 5"] == 1934                    # opened 29 years before: the closing year
    assert pr.n_cards.to_dict() == {"TESTGÅRDEN 4": 3, "TESTGÅRDEN 5": 1, "TESTGÅRDEN 6": 2}
    assert pr.episodes.to_dict() == {"TESTGÅRDEN 4": 2, "TESTGÅRDEN 5": 1, "TESTGÅRDEN 6": 1}
    assert pr.gap["TESTGÅRDEN 4"] == 6 and pr.close_last["TESTGÅRDEN 4"] == 1968   # the second episode: 1965
    assert (pr.reason == "").all()


def test_undated_cards_and_years_out_of_bounds():
    rows = [("Provby", "1", "", "1930"), ("Provby", "1", "", "-"), ("Provby", "2", "", "-"), ("Provby", "2", "", ""),
            ("Provby", "3", "", "1999"), ("Provby", "4", "", "1999"), ("Provby", "4", "", "1931")]
    skip = props(*rows, p={**P, "undated": "skip"})
    assert skip.reason.to_dict() == {"PROVBY 1": "undated_card", "PROVBY 2": "undated_only",
                                     "PROVBY 3": "undated_only", "PROVBY 4": "undated_card"}
    assert (skip.year == 0).all()
    ignore = props(*rows, p={**P, "undated": "ignore"})
    assert ignore.reason.to_dict() == {"PROVBY 1": "", "PROVBY 2": "undated_only", "PROVBY 3": "undated_only",
                                       "PROVBY 4": ""}
    assert ignore.year["PROVBY 1"] == 1930 and ignore.year["PROVBY 4"] == 1931    # 1999 is past max_year
    with pytest.raises(ValueError, match="year_rule"):
        props(*rows, p={**P, "year_rule": "latest_close"})


# ---------- footprints ----------

def test_only_the_one_main_building_of_a_small_property_may_get_its_year():
    estate = ["Enbostadshus"] + ["Komplementbyggnad"] * 6          # one house and six outbuildings
    b, sd = town([{"fastighet": "TESTGÅRDEN 1"}, {"fastighet": "TESTGÅRDEN 1", "kategori": "Komplementbyggnad"},
                  {"fastighet": "TESTGÅRDEN 2"}, {"fastighet": "TESTGÅRDEN 2"},
                  {"fastighet": "TESTGÅRDEN 3"}, {"fastighet": "TESTGÅRDEN 3", "kategori": "Kolonistuga"},
                  *[{"fastighet": "TESTGÅRDEN 4", "kategori": k} for k in estate],
                  {"fastighet": ""}, {"fastighet": "TESTGÅRDEN S:5"}, {"fastighet": "PROVBY 5:6", "prod_year": 2008},
                  {"fastighet": "PROVBY 5:7", "fnr": 10_400_001}, {"fastighet": "PROVBY 5:8", "district": "GAMLA STAN"},
                  {"fastighet": "PROVBY 5:9", "prod_year": 0, "fnr": 0}])
    f = yb.footprints(b, sd, exclude={b.gid.iloc[-1]})
    assert f.reason.tolist() == ["", "not_main", "several_main", "several_main", "several_main", "several_main",
                                 "estate", *["not_main"] * 6, "no_designation", "joint_property", "late_prod",
                                 "late_unit", "skip_stadsdel", "takedown"]
    assert f.n_fp.tolist()[:2] == [2, 2] and f.n_main.tolist()[:2] == [1, 1]
    assert f.key.tolist()[-6:] == ["", "", "PROVBY 5:6", "PROVBY 5:7", "PROVBY 5:8", "PROVBY 5:9"]
    assert set(f.reason) - {""} <= set(yb.FOOTPRINT_REASONS)
    g = yb.footprints(b, sd)
    assert g.reason.iloc[-1] == ""                  # prod_year 0 and fnr 0 are unknown, not late


# ---------- match ----------

def test_the_villa_gets_the_year_and_its_garage_does_not():
    b, sd = town([{"fastighet": "TESTGÅRDEN 1"}, {"fastighet": "TESTGÅRDEN 1", "kategori": "Komplementbyggnad"},
                  {"fastighet": "TESTGÅRDEN 3"}, {"fastighet": "TESTGÅRDEN 7"}, {"fastighet": "EXEMPELKUPÉN 2"},
                  {"fastighet": "PROVSTADEN STG 1570"}])
    pr = props(("Testgården", "1,3", "12/30", "1931"), ("Exempelkupen", "2", "", "1952"),
               ("Provstaden Stg", "1570", "", "1925"), p=OPEN)
    m = yb.match(yb.footprints(b, sd, p=OPEN), pr, OPEN)
    assert m.reason.tolist() == ["", "not_main", "", "no_card", "", "no_card"]
    assert m.year.tolist() == [1931, 0, 1931, 0, 1952, 0]          # "1,3" dates both; É folds; Stg never matches
    assert m.year_from.tolist()[0] == 1930 and m.n_cards.tolist() == [1, 0, 1, 0, 1, 0]
    assert set(m.reason) - {""} <= set(yb.FOOTPRINT_REASONS + yb.MATCH_REASONS)


def test_the_block_check():
    rows = [{"fastighet": f"PROVBY {i}"} for i in range(1, 7)] + [{"fastighet": "TESTBACKEN 1"}]
    b, sd = town(rows)
    years = ["1930", "1931", "1932", "1960", "1933", "1931"]
    pr = props(*[("Provby", str(i), "", y) for i, y in enumerate(years, 1)], ("Testbacken", "1", "", "1975"))
    m = yb.match(yb.footprints(b, sd), pr)
    assert m.reason.tolist() == ["", "", "", "block_disagrees", "", "", ""]   # the 1960 card against the others' 1931
    assert m.block_median.tolist()[3] == 1931 and np.isnan(m.block_median.iloc[6])   # alone in its block: no check
    # Two of the block's six properties without a card: a third of it (over block_uncarded)
    pr2 = props(*[("Provby", str(i), "", y) for i, y in enumerate(years[:4], 1)])
    m2 = yb.match(yb.footprints(b, sd), pr2)
    assert m2.reason.tolist()[:6] == ["block_uncarded"] * 3 + ["block_disagrees", "no_card", "no_card"]
    assert m2.block_uncarded.tolist()[0] == pytest.approx(1 / 3)
    off = yb.match(yb.footprints(b, sd), pr2, OPEN)
    assert off.reason.tolist()[:6] == ["", "", "", "", "no_card", "no_card"]


def test_block_of_a_designation():
    assert yb.block("TESTGÅRDEN 12") == "TESTGÅRDEN"
    assert yb.block("PROVBY 5:6") == "PROVBY 5"
    assert yb.block("") == yb.block("PROVBY") == ""


# ---------- the gate ----------

def test_score_counts_the_shares():
    s = yb.score([1934, 1939, 1920, 1960], [1934, 1941, 1934, 1945])
    assert s["same_decade"] == 0.25 and s["within_3"] == 0.5 and s["exact"] == 0.25
    assert s["late_10"] == 0.25 and s["early_10"] == 0.25 and s["right_period"] == 0.5


def test_a_cell_writes_only_when_it_measures_right():
    rng = np.random.default_rng(0)
    truth = rng.integers(1925, 1929, 40)
    t = pd.DataFrame({"truth": np.r_[truth, truth, truth[:20], truth],
                      "pred": np.r_[truth, truth - 40, truth[:20], truth],
                      "group": ["house"] * 100 + ["apartments"] * 40,
                      "inner": [False] * 40 + [True] * 40 + [False] * 20 + [False] * 40,
                      "era": ["1920–1945"] * 140, "episodes": [1] * 40 + [1] * 40 + [2] * 20 + [1] * 40})
    cl = {(c["group"], c["inner"], c["episodes"]): c["status"] for c in yb.cells(t)}
    assert cl == {("house", False, 1): "dated", ("house", True, 1): "fails", ("house", False, 2): "not measurable",
                  ("apartments", False, 1): "measured only"}
    assert yb.cell_status(30, 0.85, 0.70) == "dated"
    assert yb.cell_status(29, 1.0, 1.0) == "not measurable"
    assert yb.cell_status(30, 0.849, 1.0) == yb.cell_status(30, 1.0, 0.699) == "fails"
    assert yb.cell_status(30, 1.0, 1.0, group="work") == "measured only"
    assert list(yb.era([1866, 1919, 1920, 1975, 1976])) == ["1866–1919", "1866–1919", "1920–1945", "1946–1975",
                                                             "1976–1993"]


# ---------- the tier ----------

def gate_town():
    """Six houses whose permit year is their record year, one built in 1985 on an older property (a predecessor's
    card), three record-dated 1990 whose 1950 cards are all wrong, and the footprints the tier may fill: an unknown
    house in the good cell, an apartment block, a house of the bad cell and a house no card names."""
    rows = [{"fastighet": f"TESTGÅRDEN {i}"} for i in range(1, 9)] + [
        {"fastighet": "TESTGÅRDEN 9", "kategori": "Flerbostadshus"}, {"fastighet": "TESTGÅRDEN 10"}] + [
        {"fastighet": f"PROVBY {i}"} for i in range(1, 5)]
    b, _ = town(rows)
    c = [("Testgården", str(i), "", str(1931 + i)) for i in range(1, 7)] + [
        ("Testgården", "7", "", "1933"), ("Testgården", "8", "", "1934"), ("Testgården", "9", "", "1934")] + [
        ("Provby", str(i), "", "1950") for i in range(1, 4)] + [("Provby", "4", "", "1951")]
    truth = np.array([1932, 1933, 1934, 1935, 1936, 1937, 1985, 0, 0, 0, 1990, 1990, 1990, 0])
    return b, props(*c, p=OPEN), truth


def test_the_tier_dates_only_in_a_cell_measured_right_against_the_record_years():
    b, pr, truth = gate_town()
    m, measured, checks = yb.tier(b, pr, None, truth, p={**OPEN, "min_cell": 3})
    status = {(c["group"], c["era"]): c["status"] for c in measured}
    # 6 of the 7 houses of 1920-1945 right (86%, over min_right 85%): it dates; the 1946-1975 houses all wrong: fails
    assert status == {("house", "1920–1945"): "dated", ("house", "1946–1975"): "fails"}
    assert m.ok.tolist() == [True] * 8 + [False] * 6
    assert m.cell.tolist()[7:] == ["dated", "no test building", "", "fails", "fails", "fails", "fails"]
    assert m.reason.tolist()[9] == "no_card" and m.year.tolist()[7] == 1934
    assert checks["test"]["n"] == 10 and checks["test"]["used"] == 7 and checks["test"]["right_period"] == 0.857
    # the blind spot: the four from 1981 on; the 1985 house is in a dated cell and gets its predecessor's year
    assert checks["blind_spot"] == {"n": 4, "dated": 1, "share": 0.25}
    # a cell under min_cell writes nothing, whatever its share
    m30, measured30, _ = yb.tier(b, pr, None, truth, p=OPEN)
    assert not m30.ok.any() and {c["status"] for c in measured30} == {"not measurable"}


def test_every_footprint_the_tier_may_fill_is_written_or_skipped_once():
    b, pr, truth = gate_town()
    m, _, _ = yb.tier(b, pr, None, truth, exclude={int(b.gid.iloc[-1])}, p={**OPEN, "min_cell": 3})
    target = truth == 0
    written = target & m.ok.to_numpy()
    s = yb.skipped(m, target, written)
    assert int(written.sum()) == 1 and sum(s.values()) + 1 == int(target.sum())
    assert {k: v for k, v in s.items() if v} == {"takedown": 1, "no_card": 1, "cell": 1}
    assert list(s) == [*yb.FOOTPRINT_REASONS, *yb.MATCH_REASONS, "cell"]


def test_the_estimate_is_scored_against_the_permit_years_only_with_enough_houses():
    assert yb.estimate_check([1950.4], [1952], 30) == {"n": 1, "status": "not measurable"}
    got = yb.estimate_check([1950.4, 1961.0, 1935.2], [1952, 1952, 1935], 3)
    assert got["status"] == "measured" and got["n"] == 3 and got["same_decade"] == 0.667
    assert yb.not_run("absent") == {"status": "absent", **yb.settings()}
    assert yb.settings()["trains"] is False and yb.settings()["groups"] == ["house"]
