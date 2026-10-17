"""Takedowns (Plan 4b, Task 8): pipeline/suppress.py, the steps that apply it and s99's check."""
import datetime
import gzip
import json

import numpy as np
import pandas as pd
import pytest

from pipeline import codes, io, s03_tiles, s99_validate, suppress
from tests.test_s99_validate import check, edit_attrs, edit_card, reindex, site
from tests.tinycity import tiny_city

__all__ = ["site"]


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_load_reads_entries_and_refuses_a_takedown_it_cannot_apply(tmp_path):
    assert suppress.load(tmp_path / "none.yml") == []
    assert suppress.load(write(tmp_path / "empty.yml", "# nothing yet\n")) == []
    got = suppress.load(write(tmp_path / "a.yml", "- uuid: AB-1\n  date: 2026-11-02\n- oid: 1004\n  date: '2026-11-03'\n"))
    assert got == [{"uuid": "AB-1", "date": datetime.date(2026, 11, 2)}, {"oid": 1004, "date": "2026-11-03"}]
    for bad, msg in (("- date: 2026-11-02\n", "names no building"), ("- uuid: x\n", "no date"),
                     ("- oid: abc\n  date: 2026-11-02\n", "not a number"), ("uuid: x\n", "a list")):
        with pytest.raises(ValueError, match=msg):
            suppress.load(write(tmp_path / "bad.yml", bad))
    assert len(suppress.load(suppress.EXAMPLE)) == 2                     # the committed example parses


def test_resolve_by_uuid_in_any_case_or_by_oid_and_names_the_entries_that_match_nothing():
    b = pd.DataFrame({"gid": [0, 1, 2], "uuid": ["aa-1", "", "cc-3"], "oid": [1000, 1001, 1002]})
    gids, missing = suppress.resolve(b, [{"uuid": "AA-1"}, {"oid": 1001}, {"uuid": "zz"}, {"oid": 99}])
    assert gids == {0, 1} and missing == [2, 3]


def test_a_key_on_several_footprints_takes_them_all():
    # Task 8 review: the register gives a few buildings (a villa among them) one UUID on two footprints
    b = pd.DataFrame({"gid": [0, 1, 2, 3], "uuid": ["aa-1", "AA-1", "cc-3", "dd-4"], "oid": [1000, 1001, 1001, 1003]})
    assert suppress.resolve(b, [{"uuid": "aa-1"}]) == ({0, 1}, [])
    assert suppress.resolve(b, [{"oid": 1001}]) == ({1, 2}, [])


def test_a_file_that_is_not_yaml_is_refused_without_quoting_it(tmp_path):
    # Task 8 review: PyYAML's message quotes the lines around the mistake, and the list names homes
    bad = write(tmp_path / "bad.yml", "- uuid: 2e389b81-secret-key\n  date: 2026-11-02\n - oid: [\n")
    with pytest.raises(ValueError, match=r"not valid YAML at line \d+, column \d+$") as e:
        suppress.load(bad)
    assert "secret" not in str(e.value) and e.value.__cause__ is None


def test_a_takedown_keeps_the_shape_and_takes_the_rest():
    b, y, a = tiny_city()
    hidden = {0, 4}
    y2 = suppress.years(y, hidden)
    assert y2.yflag[0] == y2.yflag[4] == codes.UNKNOWN and y2.ysrc[0] == codes.SRC_NONE
    assert (y2.year[0], y2.raa_id[0], y2.private[4], y2.year[1]) == (0, "", False, y.year[1])
    a2 = suppress.attributes(a, hidden)
    assert (a2.name[0], a2.architects[0], a2.rating[0], a2.prot[0]) == ("", [], 0, 0)
    assert a2.floors[0] == a.floors[0] and a2.name[1] == a.name[1]           # the shape's floors stay; others untouched
    assert suppress.rows(pd.DataFrame({"gid": [0, 1, 4]}), hidden).gid.tolist() == [1]
    assert suppress.keyed({"0": 1, "1": 2}, hidden) == {"1": 2}
    assert suppress.years(y, set()) is y


def test_the_accuracy_table_counts_what_ships():
    before = pd.DataFrame({"yflag": [codes.EXACT, codes.EXACT, codes.ESTIMATE, codes.UNKNOWN]})
    after = pd.DataFrame({"yflag": [codes.EXACT, codes.UNKNOWN, codes.UNKNOWN, codes.UNKNOWN]})
    acc = suppress.accuracy({"tested": 2, "result": {"estimate": 1, "period": 0, "unknown": 1}}, before, after)
    assert acc == {"tested": 1, "result": {"estimate": 0, "period": 0, "unknown": 2}}


def test_s99_checks_every_takedown_against_the_build(site):
    # gid 0 (Tyska kyrkan) as built: dated, rated, named, in search; a takedown for it must clear all of that
    entry = {"uuid": "2E389B81-54F2-48CC-B4EE-AE1285DF2200", "date": "2026-11-02"}
    assert check(site, takedowns=[entry]) == ["suppress: gid 0 is a takedown but ships a year or a rating",
                                              "suppress: gid 0 is a takedown but has a card",
                                              "suppress: gid 0 is a takedown but search finds it"]
    assert check(site, takedowns=[{"oid": 99999, "date": "2026-11-02"}]) == [
        "suppress: entry 0 matches no building of this build (a mistyped key leaves a home on the map)"]


def rebuild_with(site, hidden):
    """The steps' own functions on the tiny city, as a rebuild from s02_years would run them with these takedowns."""
    from tests.tinycity import ACCURACY, LANDMARKS, SOURCES, TERRAIN, WIKI, ground_rows

    b, y, a = tiny_city()
    y = suppress.years(y, hidden)
    acc = suppress.accuracy(ACCURACY, tiny_city()[1], y)
    data = site.parents[2] / "data"
    suppress.addresses(pd.read_parquet(data / "addresses.parquet"), hidden).to_parquet(data / "addresses.parquet")
    places = s03_tiles.load_places(data)                                 # s02_addresses' withheld rows left out
    wiki = dict(WIKI, table=suppress.rows(WIKI["table"], hidden), extracts=suppress.keyed(WIKI["extracts"], hidden))
    s03_tiles.write_outputs(s03_tiles.join(b, y, suppress.attributes(a, hidden), ground_rows(b, a)), site, site.name,
                            sources=SOURCES, accuracy=acc, terrain=TERRAIN, wiki=wiki, landmarks=LANDMARKS,
                            places=places)
    y.to_parquet(site.parents[2] / "data" / "years.parquet")
    suppress.attributes(a, hidden).to_parquet(site.parents[2] / "data" / "attributes.parquet")
    reindex(site)


def test_a_rebuild_with_the_takedown_passes(site):
    rebuild_with(site, {0})
    assert check(site, takedowns=[{"oid": 1000, "date": "2026-11-02"}]) == []


TAKEN = [{"oid": 1000, "date": "2026-11-02"}]          # gid 0
SHIPS = "suppress: gid 0 is a takedown but ships a year or a rating"


@pytest.mark.parametrize(("field", "value"), [("year_from", 1640), ("year_to", 1649), ("period", 2), ("ysrc", 2),
                                              ("private", 1)])
def test_s99_finds_any_part_of_a_takedown_s_year(site, field, value):
    # Task 8 review: "Year unknown" in yflag and year alone is not enough; a decade's ends or its period colour is a
    # year too
    rebuild_with(site, {0})
    edit_attrs(site, lambda a: a[field].__setitem__(0, value))
    assert SHIPS in check(site, takedowns=TAKEN)


def test_s99_finds_a_takedown_behind_another_name_and_reports_a_misshapen_index(site):
    rebuild_with(site, {0})
    path = site / "search" / "index.json"
    index = json.loads(path.read_text())
    io.write_json(path, dict(index, baliases=index["baliases"] + [["Kyrkan", 0]]))
    assert "suppress: gid 0 is a takedown but search finds it" in check(site, takedowns=TAKEN)
    # a misshapen index or shard is reported by the search check, never raised here
    for broken in ([], {"buildings": 5, "baliases": "x"}):
        io.write_json(path, broken)
        assert check(site, takedowns=TAKEN)
    # ... and so is a misshapen card or excerpt shard (check_suppressed alone: the card check has its own rules)
    io.write_json(path, index)
    io.write_json(site / "wiki" / "00.json", {"items": ["0"]})
    io.write_json(sorted((site / "cards").glob("*.json"))[1], [1, 2])
    a = np.frombuffer(gzip.decompress((site / "attrs.bin.gz").read_bytes()), dtype=s03_tiles.ATTR_DTYPE)
    assert s99_validate.check_suppressed(site, a, site.parents[2] / "data", TAKEN) == []


def test_s99_main_checks_the_list_it_is_given(site, monkeypatch, capsys, tmp_path):
    from tests.tinycity import SOURCES
    rebuild_with(site, {0})
    monkeypatch.setattr(s99_validate, "CURRENT", site.parent / "current.json")
    monkeypatch.setattr(s99_validate, "load_sources", lambda path: SOURCES)
    taken = write(tmp_path / "taken.yml", "- oid: 1000\n  date: 2026-11-02\n")
    s99_validate.main(["--data", str(site.parents[2] / "data"), "--suppress", str(taken)])
    assert "OK; 1 takedowns checked" in capsys.readouterr().out
    with pytest.raises(SystemExit):                     # the same build, checked against a key it did not take down
        s99_validate.main(["--data", str(site.parents[2] / "data"),
                           "--suppress", str(write(tmp_path / "other.yml", "- oid: 1001\n  date: 2026-11-02\n"))])


def test_release_needs_a_maker_a_contact_and_the_open_decisions(site, monkeypatch):
    monkeypatch.setattr(s99_validate.city, "MAKER", "")
    monkeypatch.setattr(s99_validate.city, "RELEASE_WAITS_FOR",
                        ("decision 3 (Plan 4b): addresses on private houses, city.PRIVATE_ADDRESSES",))
    errors = check(site, release=True)
    assert ("release: city.MAKER is empty (decision 2: who made the map and the address for corrections and "
            "takedowns)") in errors
    monkeypatch.setattr(s99_validate.city, "MAKER", "Ann Maker")
    monkeypatch.setattr(s99_validate.city, "CONTACT", "hej@example.org")
    # an open decision: the locked preview carries it, the public site waits for the answer
    assert [e for e in check(site, release=True) if e.startswith("release:")] == [
        "release: waiting for decision 3 (Plan 4b): addresses on private houses, city.PRIVATE_ADDRESSES "
        "(city.RELEASE_WAITS_FOR)"]
    monkeypatch.setattr(s99_validate.city, "RELEASE_WAITS_FOR", ())
    assert not [e for e in check(site, release=True) if e.startswith("release:")]


def test_s99_finds_a_takedown_s_address_on_another_footprint(site):
    # final review F1: gid 4's address (Grimstagatan 5) also landed on gid 3; the rebuild withholds it there too
    rebuild_with(site, {4})
    taken = [{"oid": 1004, "date": "2026-11-02"}]
    assert check(site, takedowns=taken) == []
    io.write_json(site / "search" / "addr" / "g.json", {"Grimstagatan": [["5", 3, 4]]})
    edit_card(site, 3, {"addr": "grimstagatan 5"})
    errors = check(site, takedowns=taken)
    assert "suppress: search addr/g.json holds an address of a takedown" in errors
    assert "suppress: gid 3's card shows an address of a takedown" in errors


def test_each_version_keeps_its_gid_keys(tmp_path):
    # final review F8: a gid belongs to one data version; the takedown routine looks its uuid and oid up in that
    # version's own key file, which a later load (or a fixture build) never overwrites
    b, _, _ = tiny_city()
    b.to_parquet(tmp_path / "buildings.parquet")
    path = s03_tiles.keep_keys(tmp_path / "buildings.parquet", tmp_path / "keys", "v20261017-x")
    assert path == tmp_path / "keys" / "v20261017-x.parquet"
    keys = pd.read_parquet(path)
    assert list(keys.columns) == ["gid", "uuid", "oid"] and keys.oid.tolist() == b.oid.tolist()
    assert suppress.resolve(keys, [{"oid": 1004, "date": "2026-11-02"}]) == ({4}, [])


def test_s99_counts_a_withheld_row_as_a_takedown_s_address(site):
    # fix-wave review: s02_addresses withholds an address beside a takedown that landed elsewhere; s99 holds every
    # shipped card and shard to those rows too
    rebuild_with(site, {0})
    data = site.parents[2] / "data"
    a = pd.read_parquet(data / "addresses.parquet")
    a.assign(withheld=a.gid == 3).to_parquet(data / "addresses.parquet")       # Hornsgatan 30 and 32: withheld
    assert "suppress: search addr/h.json holds an address of a takedown" in check(site, takedowns=TAKEN)
