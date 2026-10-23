"""s08_landmarks: the curated landmarks checked against their cited articles."""
import json

import pytest
import requests

from pipeline import s08_landmarks as s08
from pipeline.landmarks import LANDMARKS

PALACE = {"name": "Stockholms slott", "qid": "Q750444", "lat": 59.3267, "lon": 18.0717, "year": 1754,
          "year_from": 1697, "year_to": 1754, "source": "sv:Stockholms slott", "checks": ("1697", "1754"),
          "timeline": 1}


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """The pause between two articles and the retries' backoff are recorded or skipped, never waited for."""
    monkeypatch.setattr(s08, "sleep", lambda s: None)


def answer(path, title, text, rev=123):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"batchcomplete": True, "query": {"pages": [
        {"pageid": 1, "ns": 0, "title": title, "extract": text, "lastrevid": rev}]}}), encoding="utf-8")
    return path


def test_norm_reads_every_dash_as_a_hyphen_and_collapses_spaces():
    assert s08.norm("byggt 1697–1754,  klart") == "byggt 1697-1754, klart"
    assert s08.norm("1280—1300 − x") == "1280-1300 - x"


def test_problems_lists_what_is_wrong_with_an_entry():
    assert s08.problems(PALACE) == []
    assert s08.problems({k: v for k, v in PALACE.items() if k != "timeline"}) == []   # the timeline is optional
    assert "missing qid" in s08.problems({k: v for k, v in PALACE.items() if k != "qid"})[0]
    assert s08.problems({**PALACE, "colour": "red"}) == ["unknown field colour"]
    assert s08.problems({**PALACE, "source": "de:Schloss"}) == ["source must be one of sv/en:<article title>"]
    assert s08.problems({**PALACE, "lat": 57.7}) == ["lat/lon outside the municipality's box"]
    assert s08.problems({**PALACE, "year": 1690})[0].startswith("years must")
    assert s08.problems({**PALACE, "checks": ()}) == ["checks must be a non-empty list of strings"]
    assert s08.problems({**PALACE, "timeline": 0}) == ["timeline must be a positive whole number"]
    assert s08.problems({**PALACE, "timeline": True}) == ["timeline must be a positive whole number"]
    assert s08.problems({**PALACE, "qid": "750444"}) == ["qid is not a Wikidata item id"]


def test_problems_accepts_rebuilds_the_checks_hold_and_refuses_the_rest():
    # A rebuild year comes after the build, by 2026, as one of the checks or
    # inside one, so the article is checked for it like the entry's other years
    palace = {**PALACE, "checks": ("1697", "1754", "ombyggdes 1772", "1857"),
              "rebuilt": [(1772, "rebuilt"), (1857, "raised"), (1857, "extended")], "cellars": True}
    assert s08.problems(palace) == []
    assert s08.problems({**palace, "rebuilt": [[1772, "rebuilt"]]}) == []           # as data/landmarks.json holds it
    assert s08.problems({**palace, "rebuilt": [(1935, "raised")]}) == ["rebuilt: 1935 is not one of the checks or "
                                                                       "inside one"]
    assert s08.problems({**palace, "checks": ("1697", "1754", "nr 18575"), "rebuilt": [(1857, "raised")]}) == [
        "rebuilt: 1857 is not one of the checks or inside one"]                       # a whole number, not digits
    assert s08.problems({**palace, "checks": ("1697", "1754", "1700"), "rebuilt": [(1700, "rebuilt")]}) == [
        "rebuilt: 1700 must come after year_to (1754) and by 2026"]
    assert s08.problems({**palace, "checks": ("1697", "1754", "år 21857"), "rebuilt": [(1857, "raised")]}) == [
        "rebuilt: 1857 is not one of the checks or inside one"]
    assert s08.problems({**palace, "checks": ("1697", "1754", "2030"), "rebuilt": [(2030, "raised")]}) == [
        "rebuilt: 2030 must come after year_to (1754) and by 2026"]
    assert s08.problems({**palace, "rebuilt": [(1857, "raised"), (1857, "raised")]}) == [
        "rebuilt: a (year, kind) is given twice"]
    assert s08.problems({**palace, "rebuilt": [("1857", "raised")]}) == ["rebuilt must be a non-empty list of (year, "
                                                                         "kind)"]
    assert s08.problems({**palace, "rebuilt": [(1857, ["raised"])]}) == ["rebuilt must be a non-empty list of (year, "
                                                                           "kind)"]   # reported, never a crash
    assert s08.problems({**palace, "rebuilt": [(True, "raised")]}) == ["rebuilt must be a non-empty list of (year, "
                                                                       "kind)"]
    assert s08.problems({**palace, "rebuilt": [(1772, "facade")]}) == [
        "rebuilt: a kind must be rebuilt, raised or extended"]
    assert s08.problems({**palace, "rebuilt": []}) == ["rebuilt must be a non-empty list of (year, kind)"]
    assert s08.problems({**palace, "rebuilt": [(1772,)]}) == ["rebuilt must be a non-empty list of (year, kind)"]
    assert s08.problems({**palace, "cellars": False}) == ["cellars must be True when given"]
    assert s08.problems({**palace, "cellars": 1}) == ["cellars must be True when given"]


def test_problems_accepts_a_point_with_its_reason_and_source_and_refuses_the_rest():
    # Lat/lon are the item's P625 unless `point` says why not and where the point comes from
    point = {"reason": "P625 marks the gasholder, not the hall the year belongs to", "source": "the research row"}
    assert s08.problems({**PALACE, "point": point}) == []
    bad = "point must be {reason, source}, both non-empty text"
    assert s08.problems({**PALACE, "point": {"source": "a map"}}) == [bad]
    assert s08.problems({**PALACE, "point": {"reason": "why"}}) == [bad]
    assert s08.problems({**PALACE, "point": {"reason": " ", "source": "a map"}}) == [bad]
    assert s08.problems({**PALACE, "point": {**point, "by": "someone"}}) == [bad]
    assert s08.problems({**PALACE, "point": "a map"}) == [bad]


def test_problems_accepts_another_house_the_checks_date_and_refuses_the_rest():
    # Historiska museet (D65): one City outline around the 1930s museum and the 1805–1818 range, which the article dates
    # on its own: each of its years must be in the checks, and unlike a rebuild it may come before the entry's years
    museum = {**PALACE, "name": "Historiska museet", "year": 1939, "year_from": 1934, "year_to": 1939,
              "checks": ("in 1934–39", "built in stages in 1805–1818"), "also": [(1805, 1818)]}
    assert s08.problems(museum) == []
    assert s08.problems({**museum, "also": [[1805, 1818]]}) == []                    # as data/landmarks.json holds it
    assert s08.problems({**museum, "also": [(1805, 1817)]}) == ["also: 1817 is not one of the checks or inside one"]
    assert s08.problems({**museum, "also": [(1818, 1805)]}) == [
        "also: 1818–1805 must satisfy 1000 <= year_from <= year_to <= 2026"]
    assert s08.problems({**museum, "also": [(1805, 1818), (1805, 1818)]}) == ["also: a span is given twice"]
    for bad in ([], [(1805,)], [("1805", 1818)], [(True, 1818)], "1805–1818"):
        assert s08.problems({**museum, "also": bad}) == ["also must be a non-empty list of (year_from, year_to)"]


def test_problems_accepts_a_raa_record_with_its_reason_and_refuses_the_rest():
    # The RAÄ record of the building the year belongs to, where the footprint's UUID joins another house's (D65)
    raa = {"id": "ba990ef4-cd17-490d-98dc-d56c40b58a99", "reason": "covers 70% of the footprint"}
    assert s08.problems({**PALACE, "raa": raa}) == []
    bad = "raa must be {id, reason}: a RAÄ record's id and how it was checked"
    for rec in ({**raa, "id": "BA990EF4-CD17-490D-98DC-D56C40B58A99"}, {**raa, "id": "ba990ef4"}, {**raa, "reason": ""},
                {"id": raa["id"]}, {**raa, "by": "someone"}, raa["id"], {**raa, "id": None}):
        assert s08.problems({**PALACE, "raa": rec}) == [bad], rec


def test_an_entry_without_a_wikidata_item_needs_a_hand_checked_point():
    # Decided 2026-10-17: a Gamla stan house cited to its kvarter article has no item; qid "" says so, and
    # its point, which no P625 can confirm, must say where it comes from
    house = {**PALACE, "name": "Stora Nygatan 38", "qid": "", "source": "sv:Kvarteret Pyramus",
             "point": {"reason": "the building has no Wikidata item", "source": "the research row"}}
    assert s08.problems(house) == []
    assert s08.problems({k: v for k, v in house.items() if k != "point"}) == [
        "an entry without a Wikidata item (qid \"\") needs a hand-checked point"]
    assert s08.problems({**house, "qid": " "}) == ["qid is not a Wikidata item id"]
    assert s08.problems({**house, "qid": None}) == ["qid is not a Wikidata item id"]


def test_two_entries_without_an_item_are_not_one_item_twice(tmp_path):
    point = {"reason": "the building has no Wikidata item", "source": "the research row"}
    a = {**PALACE, "name": "Stora Nygatan 32", "qid": "", "point": point}
    b = {**PALACE, "name": "Stora Nygatan 38", "qid": "", "point": point}
    page = answer(tmp_path / "p.json", "Kvarteret Pyramus", "1697 och 1754")
    ok, failed = s08.verify([a, b, PALACE, {**PALACE, "name": "Slottet"}], get=lambda e: page)
    assert [e["name"] for e in ok] == ["Stora Nygatan 32", "Stora Nygatan 38", "Stockholms slott"]
    assert failed == [("Slottet", "a second entry for this Wikidata item")]


def test_verify_keeps_entries_whose_article_holds_every_check(tmp_path):
    ok_path = answer(tmp_path / "a.json", "Stockholms slott", "Slottet byggdes 1697–1754 efter branden.")
    bad_path = answer(tmp_path / "b.json", "Storkyrkan", "Kyrkan är gammal.", rev=9)
    church = {**PALACE, "name": "Storkyrkan", "qid": "Q1133075", "source": "sv:Storkyrkan", "checks": ("invigdes 1306",),
              "year": 1306, "year_from": 1306, "year_to": 1306}
    paths = {"Stockholms slott": ok_path, "Storkyrkan": bad_path}
    ok, failed = s08.verify([PALACE, church], get=lambda e: paths[e["name"]])
    assert [e["name"] for e in ok] == ["Stockholms slott"]
    assert ok[0]["rev"] == 123 and ok[0]["title"] == "Stockholms slott" and ok[0]["checks"] == ["1697", "1754"]
    assert failed == [("Storkyrkan", "Storkyrkan (rev 9) lacks ['invigdes 1306']")]


def test_verify_drops_a_malformed_entry_a_missing_article_and_a_repeated_name_without_fetching(tmp_path):
    missing = tmp_path / "m.json"
    missing.write_text(json.dumps({"query": {"pages": [{"title": "Nope", "missing": True}]}}), encoding="utf-8")
    good = answer(tmp_path / "g.json", "Stockholms slott", "1697 och 1754")
    asked = []

    def get(e):
        asked.append(e["name"])
        return missing if e["name"] == "Nope" else good

    nope = {**PALACE, "name": "Nope", "qid": "Q1"}
    ok, failed = s08.verify([{**PALACE, "year": 1800}, PALACE, nope, {**PALACE, "qid": "Q2"}], get=get)
    assert [e["name"] for e in ok] == ["Stockholms slott"]
    assert [f[0] for f in failed] == ["Stockholms slott", "Nope", "Stockholms slott"]
    assert "no such article" in failed[1][1] and failed[2][1] == "a second entry with this name"
    assert asked == ["Stockholms slott", "Nope"]          # the malformed and the repeated entry are never fetched


def test_an_api_error_answer_is_a_failure_not_a_crash(tmp_path):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"error": {"code": "maxlag", "info": "lagged"}}), encoding="utf-8")
    ok, failed = s08.verify([PALACE], get=lambda e: p)
    assert ok == [] and "maxlag" in failed[0][1]


def test_fetch_caches_by_request_and_records_the_manifest(tmp_path, monkeypatch):
    calls = []

    class Resp:
        content = json.dumps({"query": {"pages": [{"title": "Stockholms slott", "extract": "1697 1754",
                                                    "lastrevid": 5}]}}).encode()

        def raise_for_status(self):
            pass

    def post(url, data=None, headers=None, timeout=None):
        calls.append((url, data["titles"]))
        return Resp()

    monkeypatch.setattr(requests, "post", post)
    raw = tmp_path / "raw" / "wiki" / "landmarks"
    manifest = tmp_path / "raw" / "MANIFEST.json"
    path = s08.fetch(PALACE, raw=raw, manifest=manifest)
    assert path == s08.article_path(PALACE["source"], raw) and path.name.startswith("sv_")
    assert calls == [("https://sv.wikipedia.org/w/api.php", "Stockholms slott")]
    s08.fetch(PALACE, raw=raw, manifest=manifest)          # cached: nothing is sent
    assert len(calls) == 1
    s08.fetch(PALACE, raw=raw, manifest=manifest, refresh=True)
    assert len(calls) == 2
    entry = json.loads(manifest.read_text())[path.relative_to(tmp_path / "raw").as_posix()]
    assert entry["url"] == "https://sv.wikipedia.org/w/api.php" and entry["query_sha256"]


def test_an_error_answer_is_asked_again_and_never_cached(tmp_path, monkeypatch):
    # MediaWiki answers maxlag or ratelimited with HTTP 200: cached, it would drop the landmark on every later build
    answers = [{"error": {"code": "maxlag", "info": "lagged"}},
               {"query": {"pages": [{"title": "Stockholms slott", "extract": "1697 1754", "lastrevid": 5}]}}]
    sent, waits = [], []

    class Resp:
        def __init__(self, body):
            self.content = json.dumps(body).encode()

        def raise_for_status(self):
            pass

    def post(url, data=None, headers=None, timeout=None):
        sent.append(data)
        return Resp(answers[min(len(sent), len(answers)) - 1])

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(s08, "sleep", waits.append)
    raw, manifest = tmp_path / "raw" / "wiki" / "landmarks", tmp_path / "raw" / "MANIFEST.json"
    path = s08.fetch(PALACE, raw=raw, manifest=manifest)
    assert len(sent) == 2 and waits == [s08.BACKOFF_S[0]] and sent[0]["maxlag"] == "5"
    assert s08.page_of(path)["rev"] == 5                       # the article, not the error, is what the cache holds
    answers[1] = answers[0]                                    # now every answer is an error, and nothing is cached
    other = {**PALACE, "source": "sv:Storkyrkan"}
    with pytest.raises(SystemExit, match="no endpoint answered"):
        s08.fetch(other, raw=raw, manifest=manifest)
    assert not s08.article_path(other["source"], raw).exists()
    assert s08.api_error(b"<html>") and s08.api_error(b'{"query": {}}') is None


def test_articles_go_out_a_pause_apart_and_cached_ones_send_nothing(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    waits, got = [], []
    monkeypatch.setattr(s08, "sleep", waits.append)
    monkeypatch.setattr(s08, "fetch", lambda e, **kw: got.append(e["name"]) or answer(
        s08.article_path(e["source"], raw), e["name"], "1697 1754"))
    three = [{**PALACE, "name": n, "qid": f"Q{i}", "source": f"sv:{n}"} for i, n in enumerate(("A", "B", "C"), 1)]
    s08.verify(three, raw=raw)
    assert got == ["A", "B", "C"] and waits == [s08.PAUSE_S] * 2
    s08.verify(three, raw=raw)                                 # all cached: no pause
    assert waits == [s08.PAUSE_S] * 2


def test_main_writes_the_verified_entries_and_reports_the_rest(tmp_path, monkeypatch, capsys):
    good = answer(tmp_path / "g.json", "Stockholms slott", "1697 1754")
    monkeypatch.setattr(s08, "LANDMARKS", [PALACE, {**PALACE, "name": "Bad", "qid": "Q9", "checks": ("1066",)}])
    monkeypatch.setattr(s08, "fetch", lambda e, **kw: good)
    out = tmp_path / "landmarks.json"
    s08.main(["--out", str(out)])
    got = json.loads(out.read_text(encoding="utf-8"))
    assert [e["name"] for e in got] == ["Stockholms slott"] and got[0]["timeline"] == 1
    io = capsys.readouterr()
    assert "1 of 2 verified (1 on the timeline)" in io.out and "landmark dropped: Bad" in io.err
    assert s08.load(out) == got
    with pytest.raises(SystemExit, match="run s08_landmarks first"):
        s08.load(tmp_path / "none.json")


def test_every_curated_entry_is_well_formed_and_the_timeline_ones_are_not_circa():
    assert all(s08.problems(e) == [] for e in LANDMARKS)
    on = [e for e in LANDMARKS if e.get("timeline")]
    assert len(on) >= 10
    assert "Riddarholmskyrkan" not in {e["name"] for e in on}     # "c. 1292": not an exact year


@pytest.mark.network
def test_real_articles_hold_every_check(tmp_path):
    ok, failed = s08.verify(LANDMARKS, raw=tmp_path / "raw", manifest=tmp_path / "MANIFEST.json")
    assert failed == [] and len(ok) == len(LANDMARKS)


def test_an_error_given_as_plain_text_is_still_an_error():
    # An `error` that is a string, not an object, must not crash the check or the cache reader
    assert s08.api_error(b'{"error": "lagged"}') == "the API answered lagged"
    assert s08.api_error(b'{"error": null}') == "the API answered an error"
