"""Harvest Stadsarkivet's card index to the building-permit files 1875-1980, page by page, into data/raw/bygglov/.

The index is Stockholm City Archives' search app "Bygglov 1875–1980". The cache is git-ignored, like all of data/:
never committed. On 2026-10-20 Stadsarkivet allowed us to use and spread the app's information freely, fetched from
its database: there is no file to download. The cache lands under the folder the step runs from (fetch.RAW is
relative), and a git worktree's data/ goes with the worktree: run the crawl where the builds will read it.

- pages/NNNNN.json: one list page of the app (sidindex NNNNN, 0 to 10807): its cards as bygglov.parse_page reads them
  (id, kvarter, nr, dnr, year, akt, scan, as the archive wrote them), the count the page showed, its address and when
  it was fetched. A page is written (to a .part file, then renamed) only after it passes its checks, so a crash never
  leaves half a page;
- requests.log: one line for every request this step sent, tab-separated: when it was sent (UTC, to the millisecond),
  the status ("-" for no answer), the seconds the answer took, its bytes, the Retry-After it asked for (in seconds, 0
  without one), the address and the error;
- MANIFEST.json: written once every page is saved and checked: the total, the pages, the first and last card id, the
  first and last fetch time, the requests sent, the User-Agent, the gap floor and a sha256 of the cards. It is
  recorded in data/raw/MANIFEST.json too (fetch.record). A run finds a missing record and writes it again, and writes
  MANIFEST.json again when it no longer matches the pages. While pages are missing there is no complete harvest: a
  MANIFEST.json left from an earlier one is moved aside (MANIFEST.stale.json) and its record dropped.

The crawl is slow on purpose (10,808 requests, about 4.8 h at GAP_S) and runs only with --fetch: a routine build
(pipeline.run with no arguments, the CI's fixture build) reports the cache and sends nothing, and HFH_FIXTURE=1 never
fetches. Its rules:
- one request at a time, at least GAP_S (1.6 s) start to start, and after each answer at least as long again as the
  answer took (IDLE_MIN_S at the least) before the next request, so a slow server rests at least as long as it works
  for us. --gap may make the gap longer, never shorter. The floor holds across restarts: a run holds a lock
  (LOCK_PORT on 127.0.0.1, released by the system when the run ends however it ends) for as long as it runs, so a
  second crawl on this machine (another worktree too) is refused, and it waits the gap before its first request;
- the project's User-Agent (fetch.UA), gzip, no cookies kept, no redirect followed;
- robots.txt is read first (one request). The step stops when it is not the file read on 2026-10-20 (ROBOTS_SHA256):
  a person reads the new one first. It also stops when a Disallow rule for us or for * could match a list page
  (wildcards and case taken at their widest), and waits the longest Crawl-delay or Request-rate there (decimals too)
  when that is longer than the gap. The card scans under /Bildarkiv/ are never asked for, nor are the cards' own
  pages;
- a 429, a 5xx, a timeout or a lost connection backs off BACKOFF_S, doubling each time up to BACKOFF_MAX_S, or for
  the Retry-After the answer asks for (seconds or a date) when that is longer. A Retry-After longer than BACKOFF_MAX_S
  stops the step. A 429, or a 5xx with a Retry-After, also doubles the gap for the rest of the run (up to GAP_MAX_S).
  The step stops after MAX_FAILS failures in a row on one address, after MAX_SLOWDOWNS 429s (or 5xx with a
  Retry-After) in one run, or after MAX_RUN_FAILS failures of any kind in one run; any other answer than 200 (a 3xx,
  a 403, a 404) stops it at once;
- after such a stop, or a run cut short while it backed off, a rerun is refused for a while: when the last request in
  requests.log did not get a 200, the step does not start before that answer's time plus BACKOFF_MAX_S, or plus its
  Retry-After when longer. A person looks at the archive in between;
- an answer slower than SLOW_S adds SLOW_PAUSE_S before the next request;
- the step stops when a page's count is not bygglov.EXPECTED_TOTAL or its ids are not the expected ten (10p+1 to
  10p+10): the index changed, and a half-changed harvest must not mix. That page is not saved. Harvesting again is a
  person's decision: move the whole data/raw/bygglov/ folder to temp_trash/ first.

A rerun asks only for the pages not saved yet, in order; a complete cache sends nothing. A progress line every
PROGRESS_EVERY pages gives the pace and the time left. --check reads the saved pages again, offline: it stops (exit 1)
on any that fails the checks, and exits INCOMPLETE (3) while the harvest is not finished (pages missing, or no
MANIFEST.json matching them and recorded), so exit 0 means a finished harvest.

    uv run python -m pipeline.s00_fetch_bygglov --fetch                     # the whole index, resumable
    uv run python -m pipeline.s00_fetch_bygglov --fetch --pages 5000:5020   # pages 5000 to 5019 only
    uv run python -m pipeline.s00_fetch_bygglov --fetch --limit 100         # at most 100 new pages
    uv run python -m pipeline.s00_fetch_bygglov --check                     # re-validate the saved pages, offline
"""
import argparse
import email.utils
import hashlib
import http.cookiejar
import json
import math
import os
import re
import socket
import sys
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

import requests

from . import bygglov, fetch

RAW = fetch.RAW / "bygglov"
PAGES = RAW / "pages"
LOG = RAW / "requests.log"
MANIFEST = RAW / "MANIFEST.json"
STALE = RAW / "MANIFEST.stale.json"
ROBOTS = "https://sok.stadsarkivet.stockholm.se/robots.txt"
ROBOTS_SHA256 = "b1338aaf7eb88b33ccf6e541e4aa8e93be3bce3ee2d7e44bf3e9f386dd33d902"   # as read on 2026-10-20
LIST_PATH = urlsplit(bygglov.BASE).path + "?sidindex="                                   # every list page's start
HEADERS = {**fetch.UA, "Accept-Encoding": "gzip", "Accept-Language": "sv,en;q=0.8"}
GAP_S = 1.6                # start to start, the floor: --gap may only make it longer
GAP_MAX_S = 30.0           # the most a 429 doubles the gap to
IDLE_MIN_S = 1.0           # the least time from the end of one answer to the next request
TIMEOUT = (30, 60)         # connect, read (seconds); the server answers a page in 0.2-0.4 s
BACKOFF_S = 60             # the first wait after a 429, a 5xx or no answer; doubled for each failure in a row
BACKOFF_MAX_S = 1800       # also the least a rerun waits after a stop on a failure
MAX_FAILS = 5              # failures in a row on one address before the step stops
MAX_SLOWDOWNS = 3          # 429s (or 5xx with a Retry-After) in one run before the step stops
MAX_RUN_FAILS = 10         # failures of any kind in one run before the step stops
RETRY_AFTER_CAP_S = 366 * 86_400   # a longer Retry-After is read as this (it stops the step either way)
SLOW_S, SLOW_PAUSE_S = 5.0, 10.0
PROGRESS_EVERY = 100
LOCK_PORT = 41_874         # one crawl per machine: the run binds this port on 127.0.0.1
INCOMPLETE = 3             # --check's exit status while the harvest is not finished
PAGE_FILE = re.compile(r"(\d{5})\.json")
sleep = time.sleep         # module-level, so tests stub the waits and the clocks
clock = time.monotonic


def wall() -> datetime:
    """The time now, in UTC (the log's and the hold's clock; `clock` paces the requests)."""
    return datetime.now(timezone.utc)


def stamp(t: datetime, ms: bool = False) -> str:
    """t in UTC, to the second (to the millisecond with `ms`, as requests.log writes it)."""
    t = t.astimezone(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + (f".{t.microsecond // 1000:03d}" if ms else "") + "Z"


def utc_now(ms: bool = False) -> str:
    return stamp(wall(), ms)


def local(t: datetime) -> str:
    """t as a person here reads it: the date and the minute, in local time."""
    return t.astimezone().strftime("%Y-%m-%d %H:%M") + " local time"


def page_path(p: int, folder: Path | None = None) -> Path:
    return (PAGES if folder is None else folder) / f"{int(p):05d}.json"


def saved_pages(folder: Path | None = None) -> set[int]:
    """The pages whose file is in the cache (a .part file is not a page)."""
    folder = PAGES if folder is None else folder
    return {int(m.group(1)) for f in folder.glob("*.json") if (m := PAGE_FILE.fullmatch(f.name))} \
        if folder.is_dir() else set()


def new_session() -> requests.Session:
    """One connection, kept alive between requests, with the project's headers; it keeps no cookie the server sets."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
    return s


def lock(port: int | None = None) -> socket.socket:
    """Bind LOCK_PORT on 127.0.0.1 for as long as the crawl runs: a second crawl on this machine finds it taken and
    stops. The system frees the port when the process ends, even after a crash, so there is no stale lock file."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT if port is None else port))
    except OSError:
        s.close()
        raise SystemExit(f"s00_fetch_bygglov: another crawl of the permit index runs on this machine (port "
                         f"{LOCK_PORT if port is None else port} on 127.0.0.1 is taken); one at a time") from None
    return s


def parse_retry_after(value: str | None, now: datetime | None = None) -> float:
    """The seconds a Retry-After header asks for: a number of seconds, or an HTTP date (RFC 9110) less the time now,
    rounded up, and at most RETRY_AFTER_CAP_S. 0 without one, for a date already past, and for a value that is
    neither."""
    value = str(value or "").strip()
    if value.isascii() and value.isdigit():
        return float(min(int(value), RETRY_AFTER_CAP_S))
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return 0.0
    if when.tzinfo is None:                       # "-0000": UTC, says RFC 5322
        when = when.replace(tzinfo=timezone.utc)
    seconds = math.ceil((when - (wall() if now is None else now)).total_seconds())
    return float(min(max(0, seconds), RETRY_AFTER_CAP_S))


@dataclass
class Answer:
    status: int | None     # None: no answer (a timeout, a lost connection)
    body: bytes
    seconds: float
    retry_after: float     # what a Retry-After header asked for, in seconds (0 without one)
    error: str = ""
    sent: datetime | None = None


def hold_end(sent: datetime, seconds: float, retry_after: float) -> datetime:
    """The earliest time a rerun may start after a failed answer: BACKOFF_MAX_S after it, or its Retry-After."""
    return sent + timedelta(seconds=seconds + max(BACKOFF_MAX_S, retry_after))


class Crawler:
    """Sends the step's requests: one at a time, `gap` seconds start to start (the first one `gap` seconds after the
    crawler is made), each logged, with the back-off and stop rules of the module docstring."""

    def __init__(self, gap: float, log: Path | None = None):
        gap = float(gap)
        if not math.isfinite(gap):
            raise ValueError(f"gap {gap}: not a number of seconds")
        self.gap, self.log = max(gap, GAP_S), LOG if log is None else log
        self.session = new_session()
        self.last = self.ready = clock()
        self.sent = self.failures = self.slowdowns = 0
        self.slowed = False

    def _wait(self) -> None:
        while (since := clock() - self.last) < self.gap or clock() < self.ready:
            sleep(max(self.gap - since, self.ready - clock(), 0.001))
        self.last = clock()

    def _send(self, url: str) -> Answer:
        self._wait()
        sent, t0 = wall(), clock()
        try:
            r = self.session.get(url, timeout=TIMEOUT, allow_redirects=False)
            body = r.content
        except requests.RequestException as e:
            a = Answer(None, b"", clock() - t0, 0.0, f"{type(e).__name__}: {e}", sent)
        else:
            a = Answer(r.status_code, body, clock() - t0, parse_retry_after(r.headers.get("Retry-After")), "", sent)
        self.ready = clock() + max(IDLE_MIN_S, a.seconds)
        self.sent += 1
        self.log.parent.mkdir(parents=True, exist_ok=True)
        line = [stamp(sent, ms=True), str(a.status or "-"), f"{a.seconds:.2f}s", str(len(a.body)),
                f"{a.retry_after:.0f}", url, a.error]
        with open(self.log, "a", encoding="utf-8") as f:
            f.write("\t".join(line).rstrip("\t") + "\n")
        return a

    def _stop(self, a: Answer, why: str) -> NoReturn:
        until = hold_end(a.sent or wall(), a.seconds, a.retry_after)
        raise SystemExit(f"s00_fetch_bygglov: {why}; stopping. The saved pages are kept. Look at the archive before "
                         f"running again: a rerun is refused before {local(until)}"
                         + (f"; this run had slowed to {self.gap:g} s between requests, and --gap {self.gap:g} starts "
                            "a rerun there" if self.slowed else ""))

    def get(self, url: str) -> Answer:
        """A 200 answer to url, after backing off from failures; SystemExit when a stop rule of the module docstring
        applies."""
        fails = 0
        while True:
            a = self._send(url)
            if a.status == 200:
                if a.seconds > SLOW_S:
                    print(f"bygglov: {url} took {a.seconds:.1f} s; pausing {SLOW_PAUSE_S:g} s", flush=True)
                    sleep(SLOW_PAUSE_S)
                return a
            if a.status is not None and a.status != 429 and a.status < 500:
                self._stop(a, f"{url} answered HTTP {a.status}")
            fails += 1
            self.failures += 1
            why = a.error or f"HTTP {a.status}"
            if a.status == 429 or (a.status is not None and a.retry_after > 0):
                self.slowdowns += 1
                slower = max(self.gap, min(self.gap * 2, GAP_MAX_S))
                if slower > self.gap:
                    self.gap, self.slowed = slower, True
                    print(f"warning: the archive asks us to slow down ({why}); {self.gap:g} s between requests for "
                          "the rest of this run", file=sys.stderr, flush=True)
            if a.retry_after > BACKOFF_MAX_S:
                self._stop(a, f"{url} answered {why} and asks us to wait {_hm(a.retry_after)} (Retry-After)")
            if fails >= MAX_FAILS:
                self._stop(a, f"{url} failed {fails} times in a row ({why})")
            if self.slowdowns >= MAX_SLOWDOWNS:
                self._stop(a, f"the archive asked us to slow down {self.slowdowns} times this run (last: {url}, {why})")
            if self.failures >= MAX_RUN_FAILS:
                self._stop(a, f"{self.failures} requests failed this run (last: {url}, {why})")
            wait = max(min(BACKOFF_S * 2 ** (fails - 1), BACKOFF_MAX_S), a.retry_after)
            print(f"warning: {url} failed ({why}); waiting {wait:g} s", file=sys.stderr, flush=True)
            sleep(wait)


def held_until(log: Path | None = None) -> datetime | None:
    """When the last request in requests.log did not get a 200 (a stop on a failure, or a run cut short while it
    backed off): the time before which the step does not start again, if that is still to come. Else None."""
    log = LOG if log is None else log
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    if not lines:
        return None
    f = lines[-1].split("\t")
    try:
        if f[1] == "200":
            return None
        sent = datetime.fromisoformat(f[0])
        seconds = float(f[2].removesuffix("s"))
        retry = float(f[4]) if len(f) > 4 and re.fullmatch(r"\d+(?:\.\d+)?", f[4]) else 0.0   # older lines: none
    except (IndexError, ValueError):
        raise SystemExit(f"s00_fetch_bygglov: the last line of {log} cannot be read ({lines[-1][:120]!r}); look at "
                         "it before crawling") from None
    until = hold_end(sent, seconds, retry)
    return until if until > wall() else None


# ---------- robots.txt ----------

def robots_rules(text: str, ua: str) -> list[tuple[str, str]]:
    """The (field, value) rules of the robots.txt groups that apply to us: those whose User-agent is part of our
    product token (as urllib.robotparser matches) or holds it, and the * group, all of them (stricter than one)."""
    token = ua.split("/")[0].strip().lower()
    groups, agents, rules = [], [], []
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (s.strip() for s in line.split(":", 1))
        if field.lower() == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        else:
            rules.append((field.lower(), value))
    groups.append((agents, rules))
    return [r for names, rules in groups if any(n == "*" or (n and (n in token or token in n)) for n in names)
            for r in rules]


def robots_refuses(rules: list[tuple[str, str]]) -> str | None:
    """The first Disallow rule that could match a list page, else None. A rule matches as a prefix, in any case (the
    server is IIS, which ignores case); with a wildcard only the part before the first * counts, so /Databas/*/Sok and
    /*?sidindex= refuse, while /Bildarkiv/*.jpg does not."""
    target = LIST_PATH.lower()
    for field, value in rules:
        if field != "disallow" or not value:
            continue
        head = value.split("*", 1)[0] if "*" in value else value.removesuffix("$")
        head = head.lower()
        if target.startswith(head) or head.startswith(target):
            return value
    return None


def robots_delay(rules: list[tuple[str, str]]) -> float:
    """The longest wait between requests the rules ask for, in seconds: Crawl-delay (decimals too) and Request-rate
    (n/t, t in seconds or with s, m or h)."""
    asked = 0.0
    for field, value in rules:
        if field == "crawl-delay" and (m := re.match(r"\d*\.?\d+", value)):
            asked = max(asked, float(m.group()))
        elif field == "request-rate" and (m := re.match(r"(\d+)\s*/\s*(\d*\.?\d+)\s*([smh]?)\b", value, re.I)):
            n, t = int(m.group(1)), float(m.group(2)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(3).lower()]
            asked = max(asked, t / n if n else 0.0)
    return asked


def read_robots(c: Crawler) -> None:
    """Read robots.txt (one request) and apply its rules (the module docstring)."""
    a = c.get(ROBOTS)
    sha = hashlib.sha256(a.body).hexdigest()
    if sha != ROBOTS_SHA256:
        raise SystemExit(f"s00_fetch_bygglov: {ROBOTS} changed since 2026-10-20; not crawling. Read it before "
                         f"crawling: if it still allows the list at this pace, set ROBOTS_SHA256 to {sha}")
    text = a.body.decode("utf-8", "replace")
    ua = fetch.UA["User-Agent"]
    rules = robots_rules(text, ua)
    rp = urllib.robotparser.RobotFileParser(ROBOTS)
    rp.parse(text.splitlines())
    rule = robots_refuses(rules) or (None if rp.can_fetch(ua, bygglov.page_url(0)) else "(urllib.robotparser)")
    if rule:
        raise SystemExit(f"s00_fetch_bygglov: {ROBOTS} disallows {bygglov.BASE} (Disallow: {rule}); not crawling")
    asked = robots_delay(rules)
    if asked > c.gap:
        print(f"bygglov: robots.txt asks for {asked:g} s between requests; waiting that long", flush=True)
        c.gap = asked


# ---------- the crawl ----------

def save_page(p: int, doc: dict, folder: Path | None = None) -> Path:
    """Write the page's file atomically: a .part file, flushed to disk, then renamed."""
    path = page_path(p, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def fetch_page(c: Crawler, p: int) -> dict:
    """Ask for page p, check it and save it; SystemExit (nothing saved) when it fails a check."""
    url = bygglov.page_url(p)
    a = c.get(url)
    fetched = utc_now()
    try:
        total, cards = bygglov.parse_page(a.body.decode("utf-8"))
        bygglov.check_page(p, total, cards, bygglov.EXPECTED_TOTAL)
    except (UnicodeDecodeError, bygglov.PageError) as e:
        raise SystemExit(f"s00_fetch_bygglov: page {p} is not saved: {e}. Stopping; the pages saved before it are "
                         "kept") from None
    doc = {"page": p, "url": url, "fetched": fetched, "total": total, "cards": cards}
    save_page(p, doc)
    return doc


def _hm(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def crawl(todo: list[int], gap: float) -> int:
    """Fetch the pages in `todo`, in order; returns the requests sent."""
    held = lock()
    try:
        until = held_until()
        if until:
            raise SystemExit(f"s00_fetch_bygglov: the last request in {LOG} did not get a 200; not crawling before "
                             f"{local(until)}. Look at the archive in between")
        c = Crawler(gap)
        read_robots(c)
        t0 = clock()
        for i, p in enumerate(todo, 1):
            fetch_page(c, p)
            if i % PROGRESS_EVERY == 0 and i < len(todo):
                per = (clock() - t0) / i
                left = per * (len(todo) - i)
                done_at = (datetime.now() + timedelta(seconds=left)).strftime("%H:%M")
                print(f"bygglov: {i:,} of {len(todo):,} pages this run (page {p}), {len(saved_pages()):,} of "
                      f"{bygglov.N_PAGES:,} saved; {per:.2f} s a page; about {_hm(left)} left (done about "
                      f"{done_at})", flush=True)
        n = len(todo)
        if n:
            per = (clock() - t0) / n
            print(f"bygglov: {n:,} pages fetched this run in {_hm(clock() - t0)} ({per:.2f} s a page), "
                  f"{c.sent:,} requests", flush=True)
        return c.sent
    finally:
        held.close()


# ---------- the saved pages, offline ----------

def check_cache(folder: Path | None = None) -> tuple[list[str], dict]:
    """(problems, counts) of the saved pages, read again from disk: each file must hold its own page number, the
    expected count and exactly the expected ids, with every card field. Sends nothing."""
    folder = PAGES if folder is None else folder
    problems = []
    counts = {"pages": 0, "cards": 0, "first_id": None, "last_id": None, "dated": 0, "undated": 0, "other_year": 0,
              "stg": 0, "trakt": 0, "no_dnr": 0, "first_fetched": None, "last_fetched": None}
    for p in sorted(saved_pages(folder)):
        path = page_path(p, folder)
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("page") != p:
                raise bygglov.PageError(f"the file holds page {doc.get('page')}")
            cards = doc["cards"]
            for card in cards:
                if set(card) != set(bygglov.FIELDS) or not isinstance(card["id"], int) or \
                        not all(isinstance(card[k], str) for k in bygglov.FIELDS[1:]):
                    raise bygglov.PageError(f"card {card.get('id')} does not have the fields {bygglov.FIELDS}")
            bygglov.check_page(p, doc["total"], cards, bygglov.EXPECTED_TOTAL)
        except (ValueError, KeyError, TypeError) as e:     # PageError is a ValueError, as is a JSONDecodeError
            problems.append(f"{path}: {e}")
            continue
        counts["pages"] += 1
        counts["cards"] += len(cards)
        counts["first_id"] = counts["first_id"] or cards[0]["id"]
        counts["last_id"] = cards[-1]["id"] if cards else counts["last_id"]
        for card in cards:
            y = card["year"].strip()
            counts["dated" if bygglov.closing_year(y) else "undated" if y in ("-", "") else "other_year"] += 1
            counts["stg"] += bygglov.is_stg(card["kvarter"])
            counts["trakt"] += ":" in card["nr"]
            counts["no_dnr"] += not card["dnr"]
        f = doc.get("fetched")
        counts["first_fetched"] = min(filter(None, [counts["first_fetched"], f]), default=None)
        counts["last_fetched"] = max(filter(None, [counts["last_fetched"], f]), default=None)
    return problems, counts


def ranges(pages: list[int]) -> str:
    """'0-4, 7, 9-10' for [0, 1, 2, 3, 4, 7, 9, 10]."""
    out, start = [], None
    for i, p in enumerate(pages):
        if start is None:
            start = p
        if i + 1 == len(pages) or pages[i + 1] != p + 1:
            out.append(f"{start}" if start == p else f"{start}-{p}")
            start = None
    return ", ".join(out)


def missing_pages(folder: Path | None = None) -> list[int]:
    have = saved_pages(folder)
    return [p for p in range(bygglov.N_PAGES) if p not in have]


def requests_logged(log: Path | None = None) -> int:
    log = LOG if log is None else log
    return sum(1 for _ in open(log, encoding="utf-8")) if log.exists() else 0


def cards_sha256(folder: Path | None = None) -> str:
    """A fingerprint of the harvest's content: every card, in id order, without the fetch times."""
    h = hashlib.sha256()
    for p in sorted(saved_pages(folder)):
        for card in json.loads(page_path(p, folder).read_text(encoding="utf-8"))["cards"]:
            h.update((json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    return h.hexdigest()


def read_own_manifest() -> dict:
    """MANIFEST.json, or {} when it is missing or unreadable."""
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recorded() -> bool:
    """True when data/raw/MANIFEST.json records MANIFEST.json as it is."""
    entry = fetch.read_manifest().get(MANIFEST.relative_to(fetch.RAW).as_posix()) or {}
    return MANIFEST.exists() and entry.get("sha256") == fetch.sha256_file(MANIFEST)


def record_manifest(entry: dict) -> None:
    fetch.record(MANIFEST, {"url": bygglov.BASE, "pages": entry.get("pages"), "total": entry.get("total"),
                            "cards_sha256": entry.get("cards_sha256"), "sha256": fetch.sha256_file(MANIFEST),
                            "bytes": MANIFEST.stat().st_size, "etag": None, "last_modified": None})


def write_manifest(counts: dict) -> dict:
    """MANIFEST.json for a complete, checked cache, also recorded in data/raw/MANIFEST.json."""
    entry = {"source": "Stockholms stadsarkiv, Bygglov 1875-1980 (the search app's list)", "url": bygglov.BASE,
             "total": bygglov.EXPECTED_TOTAL, "pages": counts["pages"], "cards": counts["cards"],
             "first_id": counts["first_id"], "last_id": counts["last_id"],
             "start": counts["first_fetched"], "end": counts["last_fetched"], "requests": requests_logged(),
             "user_agent": fetch.UA["User-Agent"], "gap_floor_s": GAP_S, "cards_sha256": cards_sha256(),
             "written": utc_now()}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_name(MANIFEST.name + ".part")
    tmp.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, MANIFEST)
    record_manifest(entry)
    return entry


def retire_manifest() -> None:
    """While pages are missing there is no complete harvest: move a MANIFEST.json left from an earlier one aside
    (MANIFEST.stale.json, in place of an older one) and drop its record from data/raw/MANIFEST.json, so nothing
    takes the cache for complete."""
    if MANIFEST.exists():
        os.replace(MANIFEST, STALE)
        print(f"bygglov: pages are missing, so the cache is no longer complete: {MANIFEST} moved to {STALE.name}")
    if fetch.unrecord(MANIFEST):
        print(f"bygglov: its record in {fetch.RAW / 'MANIFEST.json'} is dropped")


def finish(rewrite: bool) -> None:
    """Once every page is saved: check them all and write MANIFEST.json when `rewrite`, when it is missing, or when
    it no longer matches the pages; record it again when data/raw/MANIFEST.json lacks it. While pages are missing:
    retire_manifest."""
    if missing_pages():
        retire_manifest()
        return
    if MANIFEST.exists() and not rewrite:
        m = read_own_manifest()
        if m.get("cards_sha256") == cards_sha256():
            if not recorded():
                record_manifest(m)
                print(f"bygglov: {MANIFEST} recorded in {fetch.RAW / 'MANIFEST.json'} again")
            return
        print(f"bygglov: {MANIFEST} does not match the saved pages; writing it again")
    problems, counts = check_cache()
    if problems:
        raise SystemExit("s00_fetch_bygglov: every page is saved but some fail their checks; no MANIFEST.json:\n  "
                         + "\n  ".join(problems[:20]))
    e = write_manifest(counts)
    print(f"bygglov: complete: {e['cards']:,} cards on {e['pages']:,} pages, {e['requests']:,} requests "
          f"({e['start']} to {e['end']}) → {MANIFEST}")


def report_check() -> None:
    """--check: offline. Exit 1 when a saved page fails its checks, INCOMPLETE while the harvest is not finished."""
    problems, n = check_cache()
    miss = missing_pages()
    print(f"bygglov --check: {n['pages']:,} of {bygglov.N_PAGES:,} pages saved and valid, {n['cards']:,} cards "
          f"({n['dated']:,} with a closing year, {n['undated']:,} without, {n['other_year']:,} other; {n['stg']:,} Stg "
          f"cards, {n['trakt']:,} N:M numbers, {n['no_dnr']:,} without a case number)"
          + (f"; ids {n['first_id']} to {n['last_id']}, fetched {n['first_fetched']} to {n['last_fetched']}"
             if n["pages"] else ""))
    if miss:
        shown = ranges(miss)
        shown = shown if len(shown) < 300 else shown[:300] + "…"
        print(f"bygglov --check: {len(miss):,} pages not saved yet: {shown}")
    if problems:
        raise SystemExit(f"bygglov --check: {len(problems)} saved page(s) fail their checks:\n  "
                         + "\n  ".join(problems[:50]))
    if miss:
        print(f"bygglov --check: not finished: {len(miss):,} pages to fetch", file=sys.stderr)
        raise SystemExit(INCOMPLETE)
    if read_own_manifest().get("cards_sha256") != cards_sha256() or not recorded():
        print(f"bygglov --check: every page is saved and valid, but {MANIFEST} is missing, does not match them or is "
              "not recorded: a run without --check writes it", file=sys.stderr)
        raise SystemExit(INCOMPLETE)
    print(f"bygglov --check: finished: {MANIFEST} matches the pages and is recorded")


def parse_range(text: str) -> tuple[int, int]:
    """'a:b' → (a, b), pages a to b - 1 as in a Python slice; either end may be left out."""
    m = re.fullmatch(r"\s*(\d*)\s*:\s*(\d*)\s*", text or "")
    if not m:
        raise SystemExit(f"--pages wants a:b (such as 5000:5020), not {text!r}")
    a = int(m.group(1)) if m.group(1) else 0
    b = int(m.group(2)) if m.group(2) else bygglov.N_PAGES
    if not 0 <= a < b <= bygglov.N_PAGES:
        raise SystemExit(f"--pages {text}: wants 0 <= a < b <= {bygglov.N_PAGES}")
    return a, b


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s00_fetch_bygglov", description=__doc__.splitlines()[0], allow_abbrev=False)
    ap.add_argument("--fetch", action="store_true", help="ask the archive for the pages not saved yet (slow)")
    ap.add_argument("--pages", metavar="A:B", help="only pages A to B-1 (such as 5000:5020)")
    ap.add_argument("--limit", type=int, metavar="N", help="at most N new pages this run")
    ap.add_argument("--gap", type=float, default=GAP_S, help=f"seconds start to start (at least {GAP_S:g})")
    ap.add_argument("--check", action="store_true", help="re-validate the saved pages, offline, and stop")
    a, _ = ap.parse_known_args([] if argv is None else argv)   # pipeline.run passes every step the same arguments
    if not (math.isfinite(a.gap) and a.gap >= GAP_S):
        raise SystemExit(f"--gap {a.gap:g}: wants a number of seconds of at least {GAP_S:g}, the floor")
    if a.limit is not None and a.limit < 1:
        raise SystemExit("--limit wants a number of pages, at least 1")
    if a.check:
        report_check()
        return
    lo, hi = parse_range(a.pages) if a.pages else (0, bygglov.N_PAGES)
    have = saved_pages()
    if missing_pages():
        retire_manifest()
    todo = [p for p in range(lo, hi) if p not in have][:a.limit]
    if not a.fetch or os.environ.get("HFH_FIXTURE") == "1":
        why = "a fixture build never fetches" if a.fetch else "nothing is fetched without --fetch"
        print(f"bygglov: {len(have):,} of {bygglov.N_PAGES:,} pages saved in {PAGES}; {why}"
              + (": uv run python -m pipeline.s00_fetch_bygglov --fetch" if len(have) < bygglov.N_PAGES else ""))
        finish(rewrite=False)
        return
    if not todo:
        print(f"bygglov: pages {lo} to {hi - 1} are all saved; nothing to fetch")
    else:
        print(f"bygglov: {len(todo):,} pages to fetch ({todo[0]} to {todo[-1]}), {a.gap:g} s apart: about "
              f"{_hm(len(todo) * a.gap)}, into {PAGES.resolve()}", flush=True)
        crawl(todo, a.gap)
    finish(rewrite=bool(todo))


if __name__ == "__main__":
    main(sys.argv[1:])
