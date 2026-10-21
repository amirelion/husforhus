"""s00_fetch_bygglov: the paced, resumable harvest of the permit index's list pages, against a fake archive (no
network: requests' transport is replaced, and the clock and the waits are fake). The pages it serves are the
fixtures' made-up page moved to the page asked for (tests/fixtures/bygglov/; no real designation). One network test
asks the live archive for robots.txt and one page, only with HFH_STADSARKIVET=1 as well (never in the weekly CI)."""
import email.utils
import hashlib
import http.client
import io
import json
import os
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from requests.cookies import MockRequest, MockResponse

from pipeline import bygglov, fetch
from pipeline import s00_fetch_bygglov as s00

from tests.test_bygglov import FIXTURES

FULL = (FIXTURES / "page_full.html").read_text(encoding="utf-8")
ROBOTS_TXT = (FIXTURES / "robots.txt").read_bytes()
DATA_ROW = re.compile(r'<tr class="arende-table-row arende-table-row-(?:non)?alternating">.*?</tr>', re.S)
UA = "HusForHus/1.0 (+https://github.com/amirelion/husforhus)"


def page_html(p: int, total: int = bygglov.EXPECTED_TOTAL) -> str:
    """The made-up full page moved to page p of an index of `total` cards: its ids 10p+1 onwards, its count `total`,
    and only as many rows as that page holds."""
    def moved(m):
        i = 10 * p + int(m.group(1)) - 50_000
        return f"Visa/{i}/{i}"

    s = re.sub(r"Visa/(\d+)/\1", moved, FULL)
    s = s.replace(">108 078<", f">{total:,}<".replace(",", " "))
    rows = list(DATA_ROW.finditer(s))
    n = len(bygglov.expected_ids(p, total)) if 0 <= p * bygglov.PER_PAGE < total else 0
    return s if n == len(rows) else s[:rows[n].start()] + s[rows[-1].end():]


class Clock:
    """The fake monotonic clock, and a wall clock (UTC) that moves with it from START."""
    START = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)

    def __init__(self):
        self.t, self.sleeps = 1000.0, []

    def __call__(self) -> float:
        return self.t

    def wall(self) -> datetime:
        return self.START + timedelta(seconds=self.t - 1000.0)

    def sleep(self, s: float) -> None:
        assert s >= 0
        self.sleeps.append(s)
        self.t += s


@dataclass
class Call:
    t: float
    url: str
    headers: dict
    timeout: object


class Archive:
    """The fake archive. `script` maps a url to outcomes used one per request: an HTTP status, (status, headers), an
    exception to raise, or a body (str or bytes) sent with 200. Without one, robots.txt or the page asked for."""

    def __init__(self, clock: Clock, total: int = bygglov.EXPECTED_TOTAL):
        self.clock, self.total, self.robots = clock, total, ROBOTS_TXT
        self.calls: list[Call] = []
        self.script: dict[str, list] = {}
        self.latency: dict[str, float] = {}
        self.in_flight = self.max_in_flight = 0

    def respond(self, request, timeout):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            self.calls.append(Call(self.clock(), request.url, dict(request.headers), timeout))
            self.clock.t += self.latency.get(request.url, 0.25)
            todo = self.script.get(request.url)
            outcome = todo.pop(0) if todo else None
            if isinstance(outcome, Exception):
                raise outcome
            status, headers, body = 200, {}, None
            if isinstance(outcome, int):
                status = outcome
            elif isinstance(outcome, tuple):
                status, headers = outcome
            elif isinstance(outcome, (str, bytes)):
                body = outcome.encode("utf-8") if isinstance(outcome, str) else outcome
            if body is None:
                body = self.default(request.url) if status == 200 else b"error"
            r = requests.Response()
            r.status_code, r._content, r._content_consumed = status, body, True
            r.headers = requests.structures.CaseInsensitiveDict(headers)
            r.url, r.request, r.raw = request.url, request, io.BytesIO(b"")
            return r
        finally:
            self.in_flight -= 1

    def default(self, url: str) -> bytes:
        if url == s00.ROBOTS:
            return self.robots
        return page_html(int(parse_qs(urlparse(url).query)["sidindex"][0]), self.total).encode("utf-8")

    def pages_asked(self) -> list[int]:
        return [int(parse_qs(urlparse(c.url).query)["sidindex"][0]) for c in self.calls if "sidindex=" in c.url]


class FakeAdapter(requests.adapters.BaseAdapter):
    def __init__(self, archive: Archive):
        super().__init__()
        self.archive = archive

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        return self.archive.respond(request, timeout)

    def close(self):
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """A fake archive behind a real requests.Session (the step's own headers and cookie policy), a fake clock, a free
    lock port, and data/ under tmp_path."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    clock = Clock()
    monkeypatch.setattr(s00, "clock", clock)
    monkeypatch.setattr(s00, "sleep", clock.sleep)
    monkeypatch.setattr(s00, "wall", clock.wall)
    monkeypatch.setattr(s00, "LOCK_PORT", free_port())
    a = Archive(clock)
    real = s00.new_session

    def session():
        s = real()
        s.mount("https://", FakeAdapter(a))
        s.mount("http://", FakeAdapter(a))
        return s

    monkeypatch.setattr(s00, "new_session", session)
    return a


def small_index(monkeypatch, archive: Archive, total: int = 25) -> None:
    """An index of `total` cards (3 pages for 25), so a test can complete it."""
    monkeypatch.setattr(bygglov, "EXPECTED_TOTAL", total)
    monkeypatch.setattr(bygglov, "N_PAGES", -(-total // bygglov.PER_PAGE))
    archive.total = total


def gaps(calls: list[Call]) -> list[float]:
    return [b.t - a.t for a, b in zip(calls, calls[1:])]


def serve_robots(archive: Archive, monkeypatch, body: bytes) -> None:
    """Serve another robots.txt, as if a person had read it and pinned it (ROBOTS_SHA256)."""
    archive.robots = body
    monkeypatch.setattr(s00, "ROBOTS_SHA256", hashlib.sha256(body).hexdigest())


def http_date(t: datetime) -> str:
    return email.utils.format_datetime(t.astimezone(timezone.utc), usegmt=True)


# ---------- the crawl ----------

def test_a_smoke_run_saves_each_page_after_robots_txt_one_request_at_a_time(archive, capsys):
    start = archive.clock()
    s00.main(["--fetch", "--pages", "5000:5003"])
    assert [c.url for c in archive.calls] == [s00.ROBOTS] + [bygglov.page_url(p) for p in (5000, 5001, 5002)]
    assert archive.calls[0].t - start >= s00.GAP_S                  # a run waits the gap before its first request
    assert min(gaps(archive.calls)) >= s00.GAP_S
    assert archive.max_in_flight == 1
    for c in archive.calls:
        assert c.headers["User-Agent"] == UA == fetch.UA["User-Agent"]
        assert c.headers["Accept-Encoding"] == "gzip"
        assert "Cookie" not in c.headers
        assert c.timeout == s00.TIMEOUT
    doc = json.loads(s00.page_path(5001).read_text(encoding="utf-8"))
    assert set(doc) == {"page", "url", "fetched", "total", "cards"}
    assert (doc["page"], doc["url"], doc["total"]) == (5001, bygglov.page_url(5001), 108_078)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", doc["fetched"])
    assert [c["id"] for c in doc["cards"]] == list(range(50_011, 50_021))
    assert doc["cards"][1]["kvarter"] == "Testgården"                 # å as written, not \u00e5
    assert "Testgården" in s00.page_path(5001).read_text(encoding="utf-8")
    assert s00.saved_pages() == {5000, 5001, 5002}
    assert s00.requests_logged() == 4
    assert not s00.MANIFEST.exists()                                  # written only when every page is saved
    assert "3 pages to fetch (5000 to 5002)" in capsys.readouterr().out


def test_a_rerun_asks_only_for_the_missing_pages_and_a_complete_range_sends_nothing(archive):
    s00.main(["--fetch", "--pages", "5001:5002"])
    archive.calls.clear()
    s00.main(["--fetch", "--pages", "5000:5003"])
    assert archive.pages_asked() == [5000, 5002]
    archive.calls.clear()
    s00.main(["--fetch", "--pages", "5000:5003"])
    assert archive.calls == []                                        # not even robots.txt


def test_limit_caps_the_new_pages_of_a_run(archive):
    s00.main(["--fetch", "--pages", "100:200", "--limit", "2"])
    assert archive.pages_asked() == [100, 101]
    s00.main(["--fetch", "--pages", "100:200", "--limit", "2"])
    assert archive.pages_asked() == [100, 101, 102, 103]


def test_the_gap_is_a_floor(archive):
    for bad in ("1.5", "nan", "inf", "-inf"):
        with pytest.raises(SystemExit, match="floor"):
            s00.main(["--fetch", "--pages", "0:3", f"--gap={bad}"])
    assert archive.calls == []
    s00.main(["--fetch", "--pages", "0:3", "--gap", "2.5"])
    assert min(gaps(archive.calls)) >= 2.5


def test_the_crawler_holds_the_floor_whoever_makes_it(archive):
    assert s00.Crawler(0.0).gap == s00.Crawler(-3).gap == s00.GAP_S
    assert s00.Crawler(2.5).gap == 2.5
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            s00.Crawler(bad)
    c = s00.Crawler(0.0)
    for p in range(3):
        c.get(bygglov.page_url(p))
    assert archive.calls[0].t - 1000.0 >= s00.GAP_S and min(gaps(archive.calls)) >= s00.GAP_S


def test_a_slow_server_rests_at_least_as_long_as_it_worked(archive):
    for p in range(4):
        archive.latency[bygglov.page_url(p)] = 3.0
    s00.main(["--fetch", "--pages", "0:4"])
    pages = archive.calls[1:]
    for a, b in zip(pages, pages[1:]):
        idle = b.t - (a.t + 3.0)                                    # from the end of one answer to the next request
        assert idle >= max(s00.IDLE_MIN_S, 3.0) - 1e-9
    assert min(gaps(archive.calls)) >= s00.GAP_S


def test_the_gap_holds_after_a_backoff_and_a_slow_answer(archive):
    archive.script[bygglov.page_url(1)] = [503]
    archive.latency[bygglov.page_url(2)] = 6.0
    s00.main(["--fetch", "--pages", "0:4"])
    assert archive.pages_asked() == [0, 1, 1, 2, 3]
    assert min(gaps(archive.calls)) >= s00.GAP_S
    assert s00.BACKOFF_S in archive.clock.sleeps and s00.SLOW_PAUSE_S in archive.clock.sleeps


def test_the_pinned_robots_txt_is_the_one_read_on_2026_10_20():
    assert hashlib.sha256(ROBOTS_TXT).hexdigest() == s00.ROBOTS_SHA256
    rules = s00.robots_rules(ROBOTS_TXT.decode("utf-8"), UA)
    assert ("disallow", "/Bildarkiv/") in rules
    assert s00.robots_refuses(rules) is None and s00.robots_delay(rules) == 0


def test_a_changed_robots_txt_stops_the_run_until_a_person_reads_it(archive):
    archive.robots = ROBOTS_TXT + b"\r\n# a line more"
    with pytest.raises(SystemExit, match="changed since 2026-10-20.*ROBOTS_SHA256 to [0-9a-f]{64}"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert [c.url for c in archive.calls] == [s00.ROBOTS]
    assert s00.saved_pages() == set()


@pytest.mark.parametrize("rule", ["/Databas/", "/databas/", "/Databas/*/Sok", "/*?sidindex=", "*.aspx", "/",
                                  "/Databas/bygglov1875-1980/Sok?sidindex=1", "/Databas/bygglov1875-1980/Sok$"])
def test_robots_txt_that_could_disallow_a_list_page_stops_the_run(archive, monkeypatch, rule):
    serve_robots(archive, monkeypatch, ROBOTS_TXT + f"\r\nDisallow: {rule}\r\n".encode())
    with pytest.raises(SystemExit, match="disallows"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert [c.url for c in archive.calls] == [s00.ROBOTS]
    assert s00.saved_pages() == set()


@pytest.mark.parametrize("body", [b"User-agent: HusForHus\nDisallow: /\n", b"User-agent: husforhus/1.0\nDisallow: /\n",
                                  b"\xef\xbb\xbfUser-agent: *\nDisallow: /Databas/\n"])
def test_a_group_for_us_counts_too(archive, monkeypatch, body):
    serve_robots(archive, monkeypatch, body)
    with pytest.raises(SystemExit, match="disallows"):
        s00.main(["--fetch", "--pages", "0:3"])


def test_rules_for_others_or_for_other_paths_do_not_stop_the_run(archive, monkeypatch):
    serve_robots(archive, monkeypatch, ROBOTS_TXT + b"\r\nDisallow: /Bildarkiv/*.jpg\r\n"
                 b"Disallow: /Databas/bygglov1875-1980/Visa/\r\n\r\nUser-agent: Googlebot\r\nDisallow: /\r\n"
                 b"Crawl-delay: 30\r\n")
    s00.main(["--fetch", "--pages", "0:3"])
    assert archive.pages_asked() == [0, 1, 2]
    assert max(gaps(archive.calls)) < 3


@pytest.mark.parametrize("line, at_least", [(b"Crawl-delay: 3", 3), (b"Crawl-delay: 2.5", 2.5),
                                            (b"Request-rate: 1/4", 4), (b"Request-rate: 2/5.5s", 2.75),
                                            (b"Request-rate: 1/1m", 60)])
def test_a_crawl_delay_longer_than_the_gap_is_waited(archive, monkeypatch, line, at_least):
    serve_robots(archive, monkeypatch, b"User-agent: *\nDisallow: /Bildarkiv/\n" + line + b"\n")
    s00.main(["--fetch", "--pages", "0:3"])
    assert min(gaps(archive.calls)[1:]) >= at_least                 # robots.txt itself came at the gap


def test_429_waits_its_retry_after_and_5xx_backs_off_doubling(archive):
    archive.script[bygglov.page_url(0)] = [(429, {"Retry-After": "120"})]
    archive.script[bygglov.page_url(1)] = [500, 502, requests.Timeout("read timed out")]
    s00.main(["--fetch", "--pages", "0:2"])
    assert archive.pages_asked() == [0, 0, 1, 1, 1, 1]
    assert [s for s in archive.clock.sleeps if s >= 60] == [120, 60, 120, 240]
    assert s00.saved_pages() == {0, 1}
    log = s00.LOG.read_text(encoding="utf-8").splitlines()
    assert len(log) == len(archive.calls) == 7
    assert log[1].split("\t")[1:5] == ["429", "0.25s", "5", "120"] and log[1].split("\t")[5] == bygglov.page_url(0)
    assert log[0].split("\t")[4] == "0" and "Timeout" in log[-2]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", log[0].split("\t")[0])


def test_the_log_stamps_each_request_when_it_was_sent(archive):
    archive.latency[bygglov.page_url(0)] = 0.30
    archive.latency[bygglov.page_url(1)] = 0.22
    s00.main(["--fetch", "--pages", "0:3"])
    sent = [datetime.fromisoformat(line.split("\t")[0]) for line in s00.LOG.read_text(encoding="utf-8").splitlines()]
    assert sent[0] == archive.clock.START + timedelta(seconds=archive.calls[0].t - 1000.0)   # not when it answered
    assert min((b - a).total_seconds() for a, b in zip(sent, sent[1:])) >= s00.GAP_S - 0.001   # ms in the log


def test_429s_slow_the_run_down_and_the_third_stops_it(archive, capsys):
    for p in (1, 3, 5):
        archive.script[bygglov.page_url(p)] = [429]
    with pytest.raises(SystemExit, match="slow down 3 times this run.*--gap 12.8") as e:
        s00.main(["--fetch", "--pages", "0:8"])
    assert archive.pages_asked() == [0, 1, 1, 2, 3, 3, 4, 5]
    assert s00.saved_pages() == {0, 1, 2, 3, 4}
    g = gaps(archive.calls)              # robots, 0, 1 (429), 1, 2, 3 (429), 3, 4, 5 (429)
    assert g[1] < 2                      # 0 → 1: the gap the run began with
    assert g[3] >= 3.2 and g[6] >= 6.4 and g[7] >= 6.4
    assert [s for s in archive.clock.sleeps if s >= 60] == [60, 60]
    assert "refused before" in str(e.value)
    assert "6.4 s between requests for the rest of this run" in capsys.readouterr().err


def test_a_503_with_retry_after_slows_the_run_and_one_without_does_not(archive):
    archive.script[bygglov.page_url(1)] = [(503, {"Retry-After": "90"})]
    archive.script[bygglov.page_url(3)] = [503]
    s00.main(["--fetch", "--pages", "0:6"])
    g = gaps(archive.calls)              # robots, 0, 1 (503), 1, 2, 3 (503), 3, 4, 5
    assert g[3] >= 3.2 and g[7] >= 3.2 and g[7] < 6.4
    assert [s for s in archive.clock.sleeps if s >= 60] == [90, 60]


def test_ten_failures_in_one_run_stop_it_though_none_came_twice_in_a_row(archive):
    for p in range(10):
        archive.script[bygglov.page_url(p)] = [500]
    with pytest.raises(SystemExit, match="10 requests failed this run"):
        s00.main(["--fetch", "--pages", "0:12"])
    assert archive.pages_asked() == [p for p in range(9) for _ in (0, 1)] + [9]
    assert s00.saved_pages() == set(range(9))


def test_a_retry_after_longer_than_the_backoff_cap_stops_the_run_with_when_to_resume(archive):
    archive.script[bygglov.page_url(0)] = [(429, {"Retry-After": "3600"})]
    with pytest.raises(SystemExit, match=r"asks us to wait 1 h 00 min \(Retry-After\).*refused before") as e:
        s00.main(["--fetch", "--pages", "0:2"])
    assert archive.pages_asked() == [0]
    assert not [s for s in archive.clock.sleeps if s >= 60]             # never back early, never 30 min
    resume = (archive.calls[-1].t - 1000.0) + 0.25 + 3600
    assert s00.local(archive.clock.START + timedelta(seconds=resume)) in str(e.value)
    archive.clock.t += 3599
    with pytest.raises(SystemExit, match="not crawling before"):
        s00.main(["--fetch", "--pages", "0:2"])
    assert archive.pages_asked() == [0]
    archive.clock.t += 2
    s00.main(["--fetch", "--pages", "0:2"])
    assert s00.saved_pages() == {0, 1}


def test_a_retry_after_is_waited_in_full_and_may_be_a_date(archive):
    archive.script[bygglov.page_url(0)] = [(429, {"Retry-After": "900"})]
    in_20_min = http_date(archive.clock.START + timedelta(minutes=20))
    archive.script[bygglov.page_url(1)] = [(503, {"Retry-After": in_20_min})]
    archive.script[bygglov.page_url(2)] = [(503, {"Retry-After": "soon"})]
    s00.main(["--fetch", "--pages", "0:3"])
    long_waits = [s for s in archive.clock.sleeps if s >= 60]
    assert long_waits[0] == 900 and long_waits[2] == 60
    assert archive.calls[4].t - 1000.0 >= 20 * 60                   # page 1 again, not before the date it named
    assert s00.saved_pages() == {0, 1, 2}


def test_a_retry_after_date_more_than_the_cap_away_stops_the_run(archive):
    archive.script[bygglov.page_url(0)] = [(503, {"Retry-After": http_date(archive.clock.START + timedelta(hours=2))})]
    with pytest.raises(SystemExit, match="asks us to wait 2 h 00 min"):
        s00.main(["--fetch", "--pages", "0:2"])
    assert archive.pages_asked() == [0]


def test_retry_after_reads_seconds_and_dates():
    now = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
    assert s00.parse_retry_after("120", now) == 120 and s00.parse_retry_after(" 3600 ", now) == 3600
    assert s00.parse_retry_after("Tue, 20 Oct 2026 21:00:00 GMT", now) == 3600
    assert s00.parse_retry_after("Tue, 20 Oct 2026 20:00:30 -0000", now) == 30
    assert s00.parse_retry_after("Tue, 20 Oct 2026 19:00:00 GMT", now) == 0       # already past
    for bad in (None, "", "soon", "-5", "1.5", "١٢٠"):
        assert s00.parse_retry_after(bad, now) == 0
    assert s00.parse_retry_after("9" * 30, now) == s00.RETRY_AFTER_CAP_S


def test_five_failures_in_a_row_stop_the_run_and_save_nothing_of_that_page(archive):
    archive.script[bygglov.page_url(1)] = [503, requests.ConnectionError("reset"), 503, 503, 503]
    with pytest.raises(SystemExit, match="5 times in a row.*Look at the archive before running again"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert archive.pages_asked() == [0, 1, 1, 1, 1, 1]
    assert s00.saved_pages() == {0}
    assert [s for s in archive.clock.sleeps if s >= 60] == [60, 120, 240, 480]


def test_a_rerun_soon_after_a_stop_on_failures_sends_nothing(archive):
    archive.script[bygglov.page_url(1)] = [503] * 5
    with pytest.raises(SystemExit, match="5 times in a row"):
        s00.main(["--fetch", "--pages", "0:3"])
    asked = archive.pages_asked()
    archive.clock.t += s00.BACKOFF_MAX_S - 1
    with pytest.raises(SystemExit, match="did not get a 200; not crawling before"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert archive.pages_asked() == asked                              # not even robots.txt
    archive.clock.t += 2
    s00.main(["--fetch", "--pages", "0:3"])
    assert s00.saved_pages() == {0, 1, 2}


def test_a_run_cut_short_while_it_backs_off_holds_the_next_one(archive, monkeypatch):
    archive.script[bygglov.page_url(1)] = [(429, {"Retry-After": "1200"})]

    def interrupted(s):
        if s >= 60:
            raise KeyboardInterrupt
        archive.clock.sleep(s)

    monkeypatch.setattr(s00, "sleep", interrupted)
    with pytest.raises(KeyboardInterrupt):
        s00.main(["--fetch", "--pages", "0:3"])
    monkeypatch.setattr(s00, "sleep", archive.clock.sleep)
    archive.calls.clear()
    archive.clock.t += 1200                                            # the Retry-After, but not BACKOFF_MAX_S
    with pytest.raises(SystemExit, match="not crawling before"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert archive.calls == []


def test_the_hold_reads_the_older_log_lines_too(archive):
    s00.LOG.parent.mkdir(parents=True)
    t = s00.stamp(archive.clock.wall() - timedelta(seconds=60))
    s00.LOG.write_text(f"{t}\t503\t0.25s\t5\t{bygglov.page_url(3)}\n", encoding="utf-8")   # no Retry-After column
    assert s00.held_until() == archive.clock.wall() - timedelta(seconds=60) + timedelta(seconds=0.25 + 1800)
    s00.LOG.write_text(f"{t}\t200\t0.25s\t5\t{bygglov.page_url(3)}\n", encoding="utf-8")
    assert s00.held_until() is None
    s00.LOG.write_text(f"{t}\t-\t60.00s\t0\t0\t{bygglov.page_url(3)}\tReadTimeout: x\n", encoding="utf-8")
    assert s00.held_until() is not None
    s00.LOG.write_text("2026-10-20T17:0", encoding="utf-8")
    with pytest.raises(SystemExit, match="cannot be read"):
        s00.held_until()


@pytest.mark.parametrize("status", [403, 404, 410])
def test_any_other_refusal_stops_at_once(archive, status):
    archive.script[bygglov.page_url(1)] = [status]
    with pytest.raises(SystemExit, match=f"HTTP {status}"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert archive.pages_asked() == [0, 1]
    assert s00.saved_pages() == {0}


def test_a_redirect_is_not_followed(archive):
    archive.script[bygglov.page_url(0)] = [(302, {"Location": "https://sok.stadsarkivet.stockholm.se/Fel"})]
    with pytest.raises(SystemExit, match="HTTP 302"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert [c.url for c in archive.calls] == [s00.ROBOTS, bygglov.page_url(0)]


def test_a_changed_count_stops_the_run_before_the_page_is_saved(archive):
    archive.script[bygglov.page_url(5001)] = [page_html(5001, total=108_079)]
    with pytest.raises(SystemExit, match="page 5001 is not saved.*it changed"):
        s00.main(["--fetch", "--pages", "5000:5003"])
    assert archive.pages_asked() == [5000, 5001]
    assert s00.saved_pages() == {5000}
    assert not list(s00.PAGES.glob("*.part"))


def test_shifted_ids_stop_the_run_before_the_page_is_saved(archive):
    archive.script[bygglov.page_url(5001)] = [page_html(5002)]
    with pytest.raises(SystemExit, match="order changed"):
        s00.main(["--fetch", "--pages", "5000:5003"])
    assert s00.saved_pages() == {5000}


def test_a_changed_layout_or_encoding_stops_the_run(archive):
    archive.script[bygglov.page_url(0)] = [page_html(0).replace("arende-table-row arende-table-row-alternating", "kort",
                                                                1)]
    with pytest.raises(SystemExit, match="page 0 is not saved: .*unknown class"):
        s00.main(["--fetch", "--pages", "0:1"])
    archive.script[bygglov.page_url(0)] = [page_html(0).encode("utf-16")]
    with pytest.raises(SystemExit, match="not saved"):
        s00.main(["--fetch", "--pages", "0:1"])
    assert s00.saved_pages() == set()


def test_only_robots_txt_and_list_pages_are_asked_for(archive):
    s00.main(["--fetch", "--pages", "7:9"])
    for c in archive.calls:
        assert c.url == s00.ROBOTS or c.url.startswith(bygglov.BASE + "?sidindex=")
        assert "/Bildarkiv/" not in c.url and "/Visa/" not in c.url


def test_progress_lines_give_the_pace_and_the_time_left(archive, monkeypatch, capsys):
    monkeypatch.setattr(s00, "PROGRESS_EVERY", 2)
    s00.main(["--fetch", "--pages", "0:5"])
    out = capsys.readouterr().out
    assert re.search(r"2 of 5 pages this run \(page 1\), 2 of 10,808 saved; 1\.\d\d s a page; about \d+ min left", out)
    assert "4 of 5 pages this run" in out
    assert "5 pages fetched this run" in out and "6 requests" in out


# ---------- no crawl without --fetch, one crawl at a time ----------

def test_a_routine_run_reports_the_cache_and_sends_nothing(archive, capsys):
    s00.main([])
    s00.main(["--release", "--version", "v1"])          # pipeline.run passes every step the same arguments
    assert archive.calls == []
    out = capsys.readouterr().out
    assert "0 of 10,808 pages saved" in out and "uv run python -m pipeline.s00_fetch_bygglov --fetch" in out


def test_a_fixture_build_never_fetches(archive, monkeypatch, capsys):
    monkeypatch.setenv("HFH_FIXTURE", "1")
    s00.main(["--fetch", "--pages", "0:3"])
    assert archive.calls == []
    assert "a fixture build never fetches" in capsys.readouterr().out


def test_the_lock_refuses_a_second_crawl_and_is_freed_after(archive):
    held = s00.lock()
    with pytest.raises(SystemExit, match="another crawl"):
        s00.lock()
    with pytest.raises(SystemExit, match="another crawl"):
        s00.main(["--fetch", "--pages", "0:3"])
    assert archive.calls == []
    held.close()
    s00.main(["--fetch", "--pages", "0:1"])
    assert archive.pages_asked() == [0]
    s00.lock().close()                                   # the run let it go


def test_the_session_keeps_no_cookie_and_sends_the_projects_headers():
    s = s00.new_session()
    assert s.headers["User-Agent"] == UA and s.headers["Accept-Encoding"] == "gzip"
    msg = http.client.parse_headers(io.BytesIO(b"Set-Cookie: ASP.NET_SessionId=abc123; path=/; HttpOnly\r\n\r\n"))
    req = requests.Request("GET", bygglov.page_url(0)).prepare()
    s.cookies.extract_cookies(MockResponse(msg), MockRequest(req))
    assert len(s.cookies) == 0
    assert "Cookie" not in s.prepare_request(requests.Request("GET", bygglov.page_url(1))).headers


def test_pages_ranges():
    assert s00.parse_range("5000:5020") == (5000, 5020)
    assert s00.parse_range(":3") == (0, 3)
    assert s00.parse_range("10800:") == (10_800, 10_808)
    for bad in ("5:3", "3:3", "abc", "0:10809", "5000"):
        with pytest.raises(SystemExit):
            s00.parse_range(bad)
    assert s00.ranges([0, 1, 2, 5, 7, 8]) == "0-2, 5, 7-8"
    assert s00.ranges([]) == ""


# ---------- the complete cache, and --check ----------

def test_a_complete_harvest_writes_its_manifest_and_then_sends_nothing(archive, monkeypatch):
    small_index(monkeypatch, archive)
    s00.main(["--fetch"])
    assert archive.pages_asked() == [0, 1, 2]
    assert [c["id"] for c in json.loads(s00.page_path(2).read_text(encoding="utf-8"))["cards"]] == list(range(21, 26))
    m = json.loads(s00.MANIFEST.read_text(encoding="utf-8"))
    assert (m["total"], m["pages"], m["cards"], m["first_id"], m["last_id"]) == (25, 3, 25, 1, 25)
    assert m["requests"] == 4 and m["user_agent"] == UA and m["gap_floor_s"] == s00.GAP_S
    assert m["start"] <= m["end"] and len(m["cards_sha256"]) == 64
    entry = fetch.read_manifest()["bygglov/MANIFEST.json"]
    assert entry["sha256"] == fetch.sha256_file(s00.MANIFEST) and entry["cards_sha256"] == m["cards_sha256"]
    archive.calls.clear()
    s00.main(["--fetch"])
    s00.main([])
    assert archive.calls == []
    assert json.loads(s00.MANIFEST.read_text(encoding="utf-8")) == m


def test_a_routine_run_writes_a_missing_manifest_from_a_complete_cache(archive, monkeypatch):
    small_index(monkeypatch, archive)
    s00.main(["--fetch"])
    s00.MANIFEST.unlink()
    archive.calls.clear()
    s00.main([])
    assert archive.calls == [] and s00.MANIFEST.exists()


def test_a_lost_record_of_the_manifest_is_written_again(archive, monkeypatch, tmp_path):
    small_index(monkeypatch, archive)
    s00.main(["--fetch"])
    m = s00.MANIFEST.read_bytes()
    os.replace(fetch.RAW / "MANIFEST.json", tmp_path / "away.json")      # the cache moved to another checkout
    s00.main([])
    entry = fetch.read_manifest()["bygglov/MANIFEST.json"]
    assert entry["sha256"] == fetch.sha256_file(s00.MANIFEST) and s00.MANIFEST.read_bytes() == m
    assert archive.pages_asked() == [0, 1, 2]


def test_a_crash_between_the_manifest_and_its_record_is_mended(archive, monkeypatch):
    small_index(monkeypatch, archive)
    real = fetch.record

    def crash(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(fetch, "record", crash)
    with pytest.raises(OSError):
        s00.main(["--fetch"])
    assert s00.MANIFEST.exists() and "bygglov/MANIFEST.json" not in fetch.read_manifest()
    monkeypatch.setattr(fetch, "record", real)
    s00.main(["--fetch"])
    assert fetch.read_manifest()["bygglov/MANIFEST.json"]["sha256"] == fetch.sha256_file(s00.MANIFEST)


def test_a_manifest_that_no_longer_matches_the_pages_is_written_again(archive, monkeypatch, capsys):
    small_index(monkeypatch, archive)
    s00.main(["--fetch"])
    old = json.loads(s00.MANIFEST.read_text(encoding="utf-8"))
    doc = json.loads(s00.page_path(1).read_text(encoding="utf-8"))
    doc["cards"][0]["akt"] = "99"
    s00.page_path(1).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    s00.main([])
    new = json.loads(s00.MANIFEST.read_text(encoding="utf-8"))
    assert new["cards_sha256"] == s00.cards_sha256() != old["cards_sha256"]
    assert fetch.read_manifest()["bygglov/MANIFEST.json"]["cards_sha256"] == new["cards_sha256"]
    assert "does not match the saved pages" in capsys.readouterr().out


def test_an_incomplete_cache_has_no_manifest(archive, monkeypatch):
    small_index(monkeypatch, archive)
    s00.main(["--fetch"])
    old = s00.MANIFEST.read_bytes()
    os.replace(s00.page_path(2), s00.RAW / "02.json.away")
    s00.main([])
    assert not s00.MANIFEST.exists() and s00.STALE.read_bytes() == old
    assert "bygglov/MANIFEST.json" not in fetch.read_manifest()
    archive.calls.clear()
    s00.main(["--fetch"])                                              # page 2 again: complete, with a new manifest
    assert archive.pages_asked() == [2]
    assert s00.MANIFEST.exists() and fetch.read_manifest()["bygglov/MANIFEST.json"]["sha256"] == \
        fetch.sha256_file(s00.MANIFEST)


def test_a_new_harvest_moves_an_old_manifest_aside_before_its_first_request(archive, monkeypatch):
    small_index(monkeypatch, archive)
    s00.main(["--fetch"])
    os.replace(s00.PAGES, s00.RAW.parent / "old-pages")
    archive.script[bygglov.page_url(1)] = [403]
    with pytest.raises(SystemExit, match="HTTP 403"):
        s00.main(["--fetch"])                                          # stopped before finish()
    assert not s00.MANIFEST.exists() and s00.STALE.exists()


def test_check_revalidates_the_saved_pages_offline(archive, capsys):
    s00.main(["--fetch", "--pages", "5000:5003"])
    archive.calls.clear()
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        s00.main(["--check"])
    assert e.value.code == s00.INCOMPLETE == 3                        # not finished: never exit 0
    out, err = capsys.readouterr()
    assert "3 of 10,808 pages saved and valid, 30 cards (30 with a closing year, 0 without" in out
    assert "10,805 pages not saved yet: 0-4999, 5003-10807" in out and "not finished" in err
    (s00.PAGES / "05003.json.part").write_text("{", encoding="utf-8")     # a crash's leftover is not a page
    with pytest.raises(SystemExit) as e:
        s00.main(["--check"])
    assert e.value.code == s00.INCOMPLETE
    path = s00.page_path(5001)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["cards"][3]["id"] += 1
    path.write_text(json.dumps(doc), encoding="utf-8")
    s00.page_path(5002).write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"2 saved page\(s\) fail") as e:
        s00.main(["--check"])
    assert "05001.json" in str(e.value) and "05002.json" in str(e.value)
    assert archive.calls == []


def test_check_exits_0_only_for_a_finished_harvest(archive, monkeypatch, capsys):
    small_index(monkeypatch, archive)
    s00.main(["--fetch"])
    s00.main(["--check"])
    assert "finished" in capsys.readouterr().out
    os.replace(s00.MANIFEST, s00.RAW / "aside.json")
    with pytest.raises(SystemExit) as e:
        s00.main(["--check"])
    assert e.value.code == s00.INCOMPLETE and not s00.MANIFEST.exists()   # --check writes nothing
    assert archive.pages_asked() == [0, 1, 2]


def test_check_refuses_a_file_holding_another_page_or_missing_a_field(archive):
    s00.main(["--fetch", "--pages", "0:2"])
    doc = json.loads(s00.page_path(0).read_text(encoding="utf-8"))
    s00.page_path(0).write_text(json.dumps({**doc, "page": 1}), encoding="utf-8")
    doc1 = json.loads(s00.page_path(1).read_text(encoding="utf-8"))
    del doc1["cards"][0]["dnr"]
    s00.page_path(1).write_text(json.dumps(doc1), encoding="utf-8")
    problems, counts = s00.check_cache()
    assert len(problems) == 2 and counts["pages"] == 0
    assert "holds page 1" in problems[0] and "fields" in problems[1]


def test_check_counts_years_stg_and_trakt_cards(archive):
    s00.main(["--fetch", "--pages", "1:2"])
    path = s00.page_path(1)
    odd = bygglov.parse_page((FIXTURES / "page_odd.html").read_text(encoding="utf-8"))[1]
    path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "cards": odd}), encoding="utf-8")
    problems, n = s00.check_cache()
    assert problems == []
    assert (n["cards"], n["dated"], n["undated"], n["stg"], n["trakt"], n["no_dnr"]) == (10, 8, 2, 1, 1, 3)


# ---------- the live archive ----------

@pytest.mark.network
def test_the_live_index_still_reads_as_the_harvest_expects(tmp_path, monkeypatch):
    """Two requests to Stadsarkivet: robots.txt and the first list page. The register is closed, so this is a manual
    check (about once a year), never the weekly network CI: it needs HFH_STADSARKIVET=1 besides --network. The real
    lock, so never beside a crawl."""
    if os.environ.get("HFH_STADSARKIVET") != "1":
        pytest.skip("asks Stadsarkivet: needs HFH_STADSARKIVET=1 as well")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    try:
        s00.lock().close()
    except SystemExit:
        pytest.skip("a crawl of the permit index runs on this machine")
    s00.main(["--fetch", "--pages", "0:1"])
    doc = json.loads(s00.page_path(0).read_text(encoding="utf-8"))
    assert doc["total"] == bygglov.EXPECTED_TOTAL
    assert [c["id"] for c in doc["cards"]] == list(range(1, 11))
    assert s00.requests_logged() == 2
