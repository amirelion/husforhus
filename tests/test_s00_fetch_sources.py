"""The year-source fetch steps: post_query's cache, the shared retry helper, the Wikidata step with its
endpoint fallback and refresh diff; Tasks 3 and 4 add the RAÄ OLD snapshot and the OSM step. Nothing touches the
network: requests is faked."""
import hashlib
import json

import pytest
import requests

from pipeline import fetch, s00_fetch_osm, s00_fetch_raa_old, s00_fetch_wikidata


class FakeResponse:
    def __init__(self, body: bytes, status=200):
        self.content, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


def sparql_json(bindings):
    return json.dumps({"head": {"vars": []}, "results": {"bindings": bindings}}).encode()


def item(q, time="1900-01-01T00:00:00Z", cls="Q41176"):
    wd = "http://www.wikidata.org/entity/"
    return {"item": {"type": "uri", "value": wd + q}, "cls": {"type": "uri", "value": wd + cls},
            "prop": {"type": "literal", "value": "P571"}, "time": {"type": "literal", "value": time},
            "precision": {"type": "literal", "value": "9"}, "ended": {"type": "literal", "value": "false"},
            "coord": {"type": "literal", "value": "Point(18.07 59.32)"}}


@pytest.fixture
def raw(tmp_path, monkeypatch):
    """Every step writes under tmp_path/data/raw with its own manifest."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    return tmp_path / "data" / "raw"


def fake_post(monkeypatch, answers):
    """answers: url -> bytes, a FakeResponse, or an exception to raise. Records every call."""
    calls = []

    def post(url, data=None, headers=None, timeout=None):
        calls.append((url, data))
        a = answers[url]
        if isinstance(a, Exception):
            raise a
        return a if isinstance(a, FakeResponse) else FakeResponse(a)

    monkeypatch.setattr(requests, "post", post)
    return calls


def scripted_post(monkeypatch, script):
    """script: url -> list of outcomes, consumed one per call (bytes, or an exception to raise). Records every call."""
    calls = []

    def post(url, data=None, headers=None, timeout=None):
        calls.append(url)
        outcome = script[url].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    monkeypatch.setattr(requests, "post", post)
    return calls


def test_post_query_caches_by_query_hash_and_refreshes_on_demand(raw, monkeypatch):
    calls = fake_post(monkeypatch, {"https://example.org/sparql": b'{"ok":1}'})
    dest = raw / "x" / "r.json"
    e = fetch.post_query("https://example.org/sparql", {"query": "SELECT 1"}, dest)
    assert dest.read_bytes() == b'{"ok":1}' and len(calls) == 1
    assert calls[0] == ("https://example.org/sparql", {"query": "SELECT 1"})
    qhash = hashlib.sha256(json.dumps({"query": "SELECT 1"}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert e["query_sha256"] == qhash and e["bytes"] == 8 and e["etag"] is None and e["last_modified"] is None
    assert fetch.read_manifest()["x/r.json"] == e
    assert fetch.post_query("https://example.org/sparql", {"query": "SELECT 1"}, dest) == e and len(calls) == 1
    fetch.post_query("https://example.org/sparql", {"query": "SELECT 2"}, dest)        # another query: sent
    assert len(calls) == 2
    fetch.post_query("https://example.org/sparql", {"query": "SELECT 2"}, dest, refresh=True)
    assert len(calls) == 3
    dest.write_bytes(b"corrupt")                                                       # a changed file: sent again
    fetch.post_query("https://example.org/sparql", {"query": "SELECT 2"}, dest)
    assert len(calls) == 4 and dest.read_bytes() == b'{"ok":1}'


def test_post_query_refuses_a_dest_outside_the_manifest_folder(raw, monkeypatch):
    fake_post(monkeypatch, {"https://example.org/sparql": b"{}"})
    with pytest.raises(ValueError, match="not inside"):
        fetch.post_query("https://example.org/sparql", {"query": "q"}, raw.parent.parent / "elsewhere.json")


A, B = "https://a.example/q", "https://b.example/q"


def retrying(dest, endpoints=(A, B), **kw):
    """post_query_retrying with a recording sleep; returns (entry, the list of waits)."""
    waits: list[float] = []
    kw.setdefault("retries", 2)
    kw.setdefault("backoff_s", 7)
    entry = fetch.post_query_retrying(list(endpoints), {"query": "q"}, dest, sleep=waits.append, **kw)
    return entry, waits


def test_post_query_retrying_returns_the_first_answer_without_waiting(raw, monkeypatch, capsys):
    calls = scripted_post(monkeypatch, {A: [b"1"], B: [b"2"]})
    dest = raw / "x" / "r.json"
    entry, waits = retrying(dest)
    assert calls == [A] and waits == [] and entry["url"] == A and dest.read_bytes() == b"1"
    assert capsys.readouterr().err == ""
    entry, waits = retrying(dest)                                   # a cache hit sends nothing, so no endpoint is tried
    assert calls == [A] and waits == [] and entry["url"] == A


def test_post_query_retrying_retries_an_endpoint_after_the_backoff(raw, monkeypatch, capsys):
    calls = scripted_post(monkeypatch, {A: [requests.ConnectionError("reset"), b"ok"], B: []})
    dest = raw / "x" / "r.json"
    entry, waits = retrying(dest)
    assert calls == [A, A] and waits == [7] and entry["url"] == A and dest.read_bytes() == b"ok"
    err = capsys.readouterr().err
    assert f"{A} failed (reset); retrying in 7 s" in err


def test_post_query_retrying_falls_to_the_next_endpoint_after_the_retries(raw, monkeypatch, capsys):
    calls = scripted_post(monkeypatch, {A: [requests.Timeout("slow"), requests.ConnectionError("down")], B: [b"b"]})
    dest = raw / "x" / "r.json"
    entry, waits = retrying(dest, retries=2)
    assert calls == [A, A, B] and waits == [7] and entry["url"] == B and dest.read_bytes() == b"b"
    err = capsys.readouterr().err
    assert err.count("retrying") == 1 and "down)" in err            # the last attempt of an endpoint does not say retrying


def test_post_query_retrying_counts_an_http_error_as_a_failure(raw, monkeypatch):
    calls = fake_post(monkeypatch, {A: FakeResponse(b"", 502), B: b"b"})
    entry, waits = retrying(raw / "x" / "r.json", retries=1)
    assert [u for u, _ in calls] == [A, B] and waits == [] and entry["url"] == B


def test_post_query_retrying_keeps_the_cache_when_every_endpoint_fails(raw, monkeypatch, capsys):
    dest = raw / "x" / "r.json"
    dest.parent.mkdir()
    dest.write_bytes(b"old")
    calls = scripted_post(monkeypatch, {A: [requests.ConnectionError("x")] * 2, B: [requests.ConnectionError("y")] * 2})
    entry, waits = retrying(dest, refresh=True)                     # refresh forces the query; the cache survives its failure
    assert calls == [A, A, B, B] and waits == [7, 7] and dest.read_bytes() == b"old"
    assert entry["url"] is None and entry["retrieved"] == "cached" and entry["bytes"] == 3
    assert f"keeping the cached {dest}" in capsys.readouterr().err


def test_post_query_retrying_stops_when_every_endpoint_fails_and_nothing_is_cached(raw, monkeypatch):
    scripted_post(monkeypatch, {A: [requests.ConnectionError("x")] * 2, B: [requests.ConnectionError("last words")] * 2})
    dest = raw / "x" / "r.json"
    with pytest.raises(SystemExit, match=r"no endpoint answered \(last words\) and there is no cached result") as e:
        retrying(dest)
    assert str(dest) in str(e.value) and not dest.exists()


def test_post_query_retrying_does_not_swallow_bugs(raw, monkeypatch):
    fake_post(monkeypatch, {A: b"{}"})
    with pytest.raises(ValueError, match="not inside"):             # only network errors are retried
        retrying(raw.parent.parent / "elsewhere.json", endpoints=(A,))
    with pytest.raises(ValueError, match="at least one endpoint"):
        retrying(raw / "x.json", endpoints=())
    with pytest.raises(ValueError, match="retries"):
        retrying(raw / "x.json", retries=0)


def test_an_answer_the_check_refuses_is_never_saved_and_counts_as_a_failed_attempt(raw, monkeypatch, capsys):
    # Overpass and MediaWiki answer some failures with HTTP 200 and an error in the body; cached, it would
    # stand in for the result on every later build (a district without floors, a landmark dropped)
    bad = b'{"error": {"code": "maxlag"}}'
    check = lambda body: "maxlag" if b"error" in body else None      # noqa: E731
    calls = scripted_post(monkeypatch, {A: [bad, b'{"ok": 1}']})
    dest = raw / "x" / "r.json"
    entry, waits = retrying(dest, endpoints=(A,), check=check)
    assert calls == [A, A] and waits == [7] and dest.read_bytes() == b'{"ok": 1}' and entry["url"] == A
    assert f"{A} failed (maxlag); retrying in 7 s" in capsys.readouterr().err
    scripted_post(monkeypatch, {A: [bad, bad]})
    other = raw / "x" / "s.json"
    with pytest.raises(SystemExit, match="no endpoint answered"):
        retrying(other, endpoints=(A,), check=check)
    assert not other.exists() and "x/s.json" not in fetch.read_manifest()     # nothing of the error answer is kept
    dest_before = dest.read_bytes()
    scripted_post(monkeypatch, {A: [bad, bad]})
    entry, _ = retrying(dest, endpoints=(A,), check=check, refresh=True)      # a refresh that fails keeps the cache
    assert dest.read_bytes() == dest_before and entry["retrieved"] == "cached"


def test_retries_wait_per_attempt_and_a_longer_retry_after_wins(raw, monkeypatch):
    class Busy(FakeResponse):
        def __init__(self, after):
            super().__init__(b"", 429)
            self.headers = {"Retry-After": after}
    calls = []

    def post(url, data=None, headers=None, timeout=None):
        calls.append(url)
        return [Busy("90"), FakeResponse(b"", 504), Busy("soon"), FakeResponse(b"ok")][len(calls) - 1]
    monkeypatch.setattr(requests, "post", post)
    entry, waits = retrying(raw / "x" / "r.json", endpoints=(A,), retries=4, backoff_s=(30, 60, 120))
    assert waits == [90, 60, 120] and entry["url"] == A          # Retry-After 90 beats 30; "soon" is no number
    assert fetch.retry_after(requests.HTTPError("x", response=Busy("100000"))) == fetch.RETRY_AFTER_MAX_S


def test_wikidata_step_runs_both_queries_once_and_falls_back_for_the_class_graph(raw, monkeypatch, capsys):
    dated = sparql_json([item("Q1"), item("Q2", cls="Q16970")])
    edges = sparql_json([{"a": {"type": "uri", "value": "http://www.wikidata.org/entity/Q16970"},
                          "b": {"type": "uri", "value": "http://www.wikidata.org/entity/Q41176"}}])
    calls = fake_post(monkeypatch, {s00_fetch_wikidata.WDQS: None, s00_fetch_wikidata.QLEVER: requests.ConnectionError("429")})
    # WDQS answers the dated query, then the class query after QLever fails: route by the query text
    answers = {s00_fetch_wikidata.WDQS: {"dated": dated, "classes": edges}}

    def post(url, data=None, headers=None, timeout=None):
        calls.append((url, data))
        if url == s00_fetch_wikidata.QLEVER:
            raise requests.ConnectionError("429 Too Many Requests")
        return FakeResponse(answers[url]["classes" if "P279" in data["query"] else "dated"])

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(s00_fetch_wikidata, "sleep", lambda s: None)      # the retry's backoff, not waited for here
    monkeypatch.setattr(s00_fetch_wikidata, "RAW", raw / "wikidata")
    monkeypatch.setattr(s00_fetch_wikidata, "DATED", raw / "wikidata" / "dated.json")
    monkeypatch.setattr(s00_fetch_wikidata, "CLASSES", raw / "wikidata" / "classes.json")
    s00_fetch_wikidata.main([])
    # the dated query on WDQS; the class graph: QLever twice (one retry), then WDQS
    assert [u for u, _ in calls] == [s00_fetch_wikidata.WDQS, s00_fetch_wikidata.QLEVER, s00_fetch_wikidata.QLEVER,
                                     s00_fetch_wikidata.WDQS]
    assert "VALUES ?cls { wd:Q16970 wd:Q41176 }" in calls[3][1]["query"]        # the classes of the dated result
    assert (raw / "wikidata" / "dated.json").read_bytes() == dated
    assert (raw / "wikidata" / "classes.json").read_bytes() == edges
    m = fetch.read_manifest()
    assert set(m) == {"wikidata/dated.json", "wikidata/classes.json"} and m["wikidata/dated.json"]["url"] == s00_fetch_wikidata.WDQS
    assert "2 dated items" in capsys.readouterr().out
    # a second run reads the cache: nothing is sent
    s00_fetch_wikidata.main([])
    assert len(calls) == 4
    # --refresh queries again and reports the change
    answers[s00_fetch_wikidata.WDQS]["dated"] = sparql_json([item("Q1", time="1905-01-01T00:00:00Z"), item("Q3")])
    s00_fetch_wikidata.main(["--refresh"])
    out = capsys.readouterr().out
    assert len(calls) == 8 and "1 items added, 1 removed, 1 with other dates" in out
    assert "added: Q3" in out and "removed: Q2" in out and "changed: Q1" in out


def test_wikidata_step_keeps_the_cache_when_every_endpoint_fails_and_stops_without_one(raw, monkeypatch, capsys):
    monkeypatch.setattr(s00_fetch_wikidata, "sleep", lambda s: None)
    monkeypatch.setattr(s00_fetch_wikidata, "RAW", raw / "wikidata")
    monkeypatch.setattr(s00_fetch_wikidata, "DATED", raw / "wikidata" / "dated.json")
    monkeypatch.setattr(s00_fetch_wikidata, "CLASSES", raw / "wikidata" / "classes.json")
    calls = fake_post(monkeypatch, {s00_fetch_wikidata.WDQS: requests.ConnectionError("down"),
                                    s00_fetch_wikidata.QLEVER: requests.ConnectionError("down")})
    with pytest.raises(SystemExit, match="no cached result"):
        s00_fetch_wikidata.main([])
    assert len(calls) == 2                                                  # WDQS tried twice for the dated query
    assert "retrying" in capsys.readouterr().err
    (raw / "wikidata").mkdir()
    (raw / "wikidata" / "dated.json").write_bytes(sparql_json([item("Q1")]))
    (raw / "wikidata" / "classes.json").write_bytes(sparql_json([]))
    s00_fetch_wikidata.main([])
    assert "keeping the cached" in capsys.readouterr().err


def test_raa_old_step_keeps_a_snapshot_when_the_file_is_gone(raw, monkeypatch, capsys):
    monkeypatch.setattr(s00_fetch_raa_old, "DEST", raw / "raa" / "byggnader_sverige.gpkg")

    def gone(url, dest, **kw):
        raise requests.HTTPError("404 Not Found")

    monkeypatch.setattr(s00_fetch_raa_old, "download", gone)
    s00_fetch_raa_old.main([])
    assert "no snapshot" in capsys.readouterr().err
    (raw / "raa").mkdir()
    (raw / "raa" / "byggnader_sverige.gpkg").write_bytes(b"GPKG")
    s00_fetch_raa_old.main([])
    assert "keeping the snapshot" in capsys.readouterr().err
    assert (raw / "raa" / "byggnader_sverige.gpkg").read_bytes() == b"GPKG"

    def ok(url, dest, **kw):
        return {"bytes": 4, "last_modified": "today"}

    monkeypatch.setattr(s00_fetch_raa_old, "download", ok)
    s00_fetch_raa_old.main([])
    assert "4 bytes" in capsys.readouterr().out


def test_osm_step_caches_and_keeps_the_cache_on_failure(raw, monkeypatch, capsys):
    monkeypatch.setattr(s00_fetch_osm, "DEST", raw / "osm" / "dated.json")
    monkeypatch.setattr(s00_fetch_osm, "TILED", {})                     # the tiled queries have their own test
    waits: list[float] = []
    monkeypatch.setattr(s00_fetch_osm, "sleep", waits.append)            # the retry's backoff, recorded not waited for
    calls = fake_post(monkeypatch, {s00_fetch_osm.OVERPASS: b'{"elements": []}'})
    s00_fetch_osm.main([])
    assert calls[0][1] == {"data": s00_fetch_osm.QUERY.read_text(encoding="utf-8")}
    assert (raw / "osm" / "dated.json").read_bytes() == b'{"elements": []}'
    s00_fetch_osm.main([])
    assert len(calls) == 1
    calls = fake_post(monkeypatch, {s00_fetch_osm.OVERPASS: requests.ConnectionError("down")})
    s00_fetch_osm.main(["--refresh"])
    retries = s00_fetch_osm.RETRIES
    assert len(calls) == retries and "keeping the cached" in capsys.readouterr().err       # the retries, then the cache
    assert waits == list(s00_fetch_osm.BACKOFF_S)[:retries - 1]                    # the step's own backoff and sleep
    (raw / "osm" / "dated.json").unlink()
    with pytest.raises(SystemExit, match="no cached"):
        s00_fetch_osm.main([])


def test_osm_tiles_cover_the_box_edge_to_edge():
    t = s00_fetch_osm.tiles((17.75, 59.22, 18.21, 59.45), (4, 4))
    assert len(t) == 16 and t[0] == ("0_0", (59.22, 17.75, 59.2775, 17.865)) and t[-1][0] == "3_3"
    assert t[-1][1][2:] == (59.45, 18.21)
    south_west = dict(t)
    assert south_west["0_1"][0] == south_west["0_0"][2]                  # rows share their edge exactly
    assert south_west["1_0"][1] == south_west["0_0"][3]                  # and so do columns
    q = s00_fetch_osm.tile_query("[bbox:{s},{w},{n},{e}];", t[0][1])
    assert q == "[bbox:59.22,17.75,59.2775,17.865];"


def test_osm_tiled_query_one_file_per_tile_one_request_at_a_time(raw, monkeypatch, capsys):
    monkeypatch.setattr(s00_fetch_osm, "DEST", raw / "osm" / "dated.json")
    monkeypatch.setattr(s00_fetch_osm, "RAW", raw / "osm")
    monkeypatch.setattr(s00_fetch_osm.city, "OSM_TILES", (2, 1))
    waits: list[float] = []
    monkeypatch.setattr(s00_fetch_osm, "sleep", waits.append)
    calls = fake_post(monkeypatch, {s00_fetch_osm.OVERPASS: b'{"elements": []}'})
    s00_fetch_osm.main([])
    levels = [c[1]["data"] for c in calls[1:3]]
    assert all("building:levels" in q and "[bbox:59.22," in q for q in levels)
    addresses = [c[1]["data"] for c in calls[3:]]                        # the address tiles the same way
    assert len(calls) == 5 and all('["addr:housenumber"]' in q and "[bbox:59.22," in q for q in addresses)
    for name in ("levels", "addresses"):
        assert sorted(p.name for p in (raw / "osm" / name).iterdir()) == ["0_0.json", "1_0.json"]
    assert waits == [s00_fetch_osm.PAUSE_S] * 2                          # a pause between two tiles of one query
    out = capsys.readouterr().out
    assert "OSM levels: 2 tiles" in out and "OSM addresses: 2 tiles" in out
    s00_fetch_osm.main([])                                               # every tile cached: nothing is sent
    assert len(calls) == 5 and waits == [s00_fetch_osm.PAUSE_S] * 2
    manifest = json.loads((raw / "MANIFEST.json").read_text())
    assert {"osm/levels/0_0.json", "osm/levels/1_0.json", "osm/addresses/1_0.json", "osm/dated.json"} <= set(manifest)


def test_an_overpass_error_remark_is_never_cached_and_a_missing_tile_does_not_stop_the_others(raw, monkeypatch, capsys):
    # Overpass answers a query that ran out of time with HTTP 200, no elements and a remark; cached, a district would
    # lose its floors until --refresh. The tile is asked again, the others are fetched, and the step names the gap.
    monkeypatch.setattr(s00_fetch_osm, "DEST", raw / "osm" / "dated.json")
    monkeypatch.setattr(s00_fetch_osm, "RAW", raw / "osm")
    monkeypatch.setattr(s00_fetch_osm, "TILED", {"levels": s00_fetch_osm.TILED["levels"]})
    monkeypatch.setattr(s00_fetch_osm.city, "OSM_TILES", (2, 1))
    waits: list[float] = []
    monkeypatch.setattr(s00_fetch_osm, "sleep", waits.append)
    timeout = b'{"elements": [], "remark": "runtime error: Query timed out in \\"query\\" at line 4 after 181 seconds."}'
    calls = []

    def post(url, data=None, headers=None, timeout_=None, **kw):
        calls.append(data["data"])
        first_tile = "17.75," in data["data"] and "building:levels" in data["data"]
        return FakeResponse(timeout if first_tile else b'{"elements": []}')
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(SystemExit, match=r"tile\(s\) 0_0, which have no cached copy; the other 1 are saved"):
        s00_fetch_osm.main([])
    assert sorted(p.name for p in (raw / "osm" / "levels").iterdir()) == ["1_0.json"]   # the error answer is not kept
    assert waits.count(30) == 1 and waits.count(120) == 1                     # the tile's four tries, then the pause
    assert "runtime error: Query timed out" in capsys.readouterr().err
    assert s00_fetch_osm.overpass_error(b'{"elements": [], "remark": "runtime error: out of memory"}')
    assert s00_fetch_osm.overpass_error(b"<?xml version='1.0'?><osm/>") and s00_fetch_osm.overpass_error(b"{}")
    assert s00_fetch_osm.overpass_error(b'{"elements": [], "remark": "note: 3 areas"}') is None


def test_a_fixture_build_fetches_only_the_tiles_that_touch_its_box(raw, monkeypatch, capsys):
    monkeypatch.setenv("HFH_FIXTURE", "1")
    monkeypatch.setattr(s00_fetch_osm, "DEST", raw / "osm" / "dated.json")
    monkeypatch.setattr(s00_fetch_osm, "RAW", raw / "osm")
    monkeypatch.setattr(s00_fetch_osm, "TILED", {"levels": s00_fetch_osm.TILED["levels"]})
    monkeypatch.setattr(s00_fetch_osm, "sleep", lambda s: None)
    calls = fake_post(monkeypatch, {s00_fetch_osm.OVERPASS: b'{"elements": []}'})
    s00_fetch_osm.main([])
    assert len(calls) == 2 and [p.name for p in (raw / "osm" / "levels").iterdir()] == ["2_1.json"]   # Gamla stan's
    assert "OSM levels: 1 tiles" in capsys.readouterr().out


def test_retry_after_reads_only_ascii_digits():
    # "²".isdigit() is true but float("²") raises, which would escape the retry loop
    class Busy(FakeResponse):
        def __init__(self, after):
            super().__init__(b"", 429)
            self.headers = {"Retry-After": after}
    assert fetch.retry_after(requests.HTTPError("x", response=Busy("²"))) == 0.0
    assert fetch.retry_after(requests.HTTPError("x", response=Busy(" 12 "))) == 12.0


def test_tile_query_writes_the_edges_tiles_gives_it():
    # `:g` keeps six significant digits, so 17.982345 would have been sent as 17.9823
    assert s00_fetch_osm.tile_query("{s},{w},{n},{e}", (59.335, 17.982345, 59.4, 18.0)) == "59.335,17.982345,59.4,18"
