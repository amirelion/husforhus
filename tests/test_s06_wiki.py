"""s06_wiki: items to footprints, photos and excerpts, private houses left out. No network."""
import json

import pandas as pd
import pytest
import requests

from pipeline import codes, s06_wiki, wiki
from tests import synth
from tests.test_wiki import ANC, BUILDING, CHURCH, a_row, b_row, page


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """The pauses between requests and the retries' backoff are not waited for; each test starts a fresh run."""
    monkeypatch.setattr(s06_wiki, "sleep", lambda s: None)
    monkeypatch.setattr(s06_wiki, "_sent", [])
    monkeypatch.setattr(s06_wiki, "fetch_occupants", lambda qids, refresh: {})   # tests/test_occupants.py's


def town():
    """gid 0 a church with an item, a photo and articles; gid 1 a private house with an item and a photo; gid 2 a
    curated private house with an item; gid 3 a block of flats whose article title is its property designation."""
    b = synth.buildings(rows=[
        {"geometry": synth.square(0, 0, 30), "kategori": "Allmän byggnad", "fastighet": "KYRKAN 1"},
        {"geometry": synth.square(100, 0, 20), "kategori": "Enbostadshus", "fastighet": "VILLAN 2"},
        {"geometry": synth.square(200, 0, 20), "kategori": "Enbostadshus", "fastighet": "SLOTTET 3"},
        {"geometry": synth.square(300, 0, 30), "kategori": "Flerbostadshus", "fastighet": "STYCKJUNKAREN 7"}])
    years = pd.DataFrame({"gid": [0, 1, 2, 3], "ysrc": [codes.SRC_RAA, codes.SRC_RAA, codes.SRC_CURATED, codes.SRC_RAA]})
    items = wiki.items_from(
        [a_row("Q1", 0, 0, CHURCH, img="Kyrka.jpg"), a_row("Q2", 100, 0, BUILDING, img="Villa.jpg"),
         a_row("Q3", 200, 0, BUILDING, img="Slott.jpg"), a_row("Q4", 300, 0, BUILDING)],
        [b_row("Q1", sv="Kyrkan", en="The Church", svt="Kyrkan", ent="The Church", nsl=4),
         b_row("Q2", sv="Villa Andersson", svt="Villa Andersson", nsl=1),
         b_row("Q3", sv="Lilla slottet", svt="Lilla slottet", nsl=2),
         b_row("Q4", sv="Styckjunkaren 7", svt="Styckjunkaren 7", nsl=1)])
    return b, years, items


def stubs(asked):
    def commons(files):
        asked["files"] = files
        return {f: page(sha1=f"{i:02x}" * 20) for i, f in enumerate(files)}

    def extracts(titles, lang):
        asked.setdefault("titles", {})[lang] = titles
        text = {"Kyrkan": "Kyrkan byggdes 1906. Den ritades av en arkitekt.", "The Church": "The church was built in 1906.",
                "Lilla slottet": "Ett litet slott.", "Styckjunkaren 7": "Styckjunkaren 7 är ett hus vid en gata."}
        return {t: {"text": text[t], "title": t, "rev": 100 + len(t)} for t in titles}

    return commons, extracts, (lambda photos: [])


def test_build_leaves_private_houses_out_and_keeps_titles_and_designations_internal():
    b, years, items = town()
    asked = {}
    commons, extracts, thumbs = stubs(asked)
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts, thumbs=thumbs)
    t = out["table"].set_index("gid")
    assert t.index.tolist() == [0, 2, 3]                     # gid 1, an uncurated private house, gets nothing
    assert asked["files"] == ["Kyrka.jpg", "Slott.jpg"]      # ... not even a request for its photo
    assert t.qid.to_dict() == {0: "Q1", 2: "Q3", 3: "Q4"}
    assert t.name.to_dict() == {0: "Kyrkan", 2: "Lilla slottet", 3: ""}       # a designation is no name
    assert t.name_en.to_dict() == {0: "The Church", 2: "", 3: ""}
    assert t.langs.to_dict() == {0: "sv,en", 2: "sv", 3: "sv"}
    assert t.photo[0] and t.photo[2] and t.photo[3] == ""
    assert set(out["photos"]) == {t.photo[0], t.photo[2]}
    assert set(out["photos"][t.photo[0]]) == {"key", "w", "h", "by", "lic", "lu", "page"}   # no thumb URL, no file name
    # the flats' only sentence names its designation: no excerpt; titles never leave data/raw
    assert out["extracts"] == {"0": {"sv": {"t": "Kyrkan byggdes 1906. Den ritades av en arkitekt.", "r": 106},
                                     "en": {"t": "The church was built in 1906.", "r": 110}},
                               "2": {"sv": {"t": "Ett litet slott.", "r": 113}}}
    assert "Styckjunkaren 7" not in json.dumps({**out["photos"], **out["extracts"]})


def test_an_item_beside_a_private_house_on_its_property_is_left_out():
    # An item placed inside a 3.5 m outbuilding that touches an uncurated Enbostadshus
    # on the same property shipped the house's photo and article on the outbuilding's card
    b, years, items = town()
    extra = synth.buildings(rows=[
        {"geometry": synth.square(113, 0, 6), "kategori": "Komplementbyggnad", "fastighet": "VILLAN 2"},     # gid 4
        {"geometry": synth.square(213, 0, 6), "kategori": "Komplementbyggnad", "fastighet": "SLOTTET 3"},    # gid 5
        {"geometry": synth.square(87, 0, 6), "kategori": "Komplementbyggnad", "fastighet": "GRANNEN 9"},     # gid 6
        {"geometry": synth.square(130, 0, 10), "kategori": "Komplementbyggnad", "fastighet": "VILLAN 2"}])   # gid 7
    b = pd.concat([b, extra.assign(gid=extra.gid + 4)], ignore_index=True)
    years = pd.concat([years, pd.DataFrame({"gid": [4, 5, 6, 7], "ysrc": [codes.SRC_RAA] * 4})], ignore_index=True)
    more = wiki.items_from(
        [a_row("Q6", 112, 0, img="Bod.jpg"), a_row("Q7", 212, 0, img="Slottsbod.jpg"), a_row("Q8", 88, 0),
         a_row("Q9", 132, 0)],
        [b_row(q, sv=f"Hus {q}", nsl=1) for q in ("Q6", "Q7", "Q8", "Q9")])
    items = pd.concat([items, more], ignore_index=True)
    best = s06_wiki.select(b, years, items, ANC)
    # gid 4: its item 2 m from the house on its property; gid 5: beside a curated house; gid 6: another property;
    # gid 7: on the property, 22 m from the house
    assert best.index.tolist() == [0, 2, 3, 5, 6, 7]


def test_a_curated_landmark_takes_its_own_item_whatever_else_stands_on_it():
    # the palace's footprint (gid 0 here) also holds the chapel's item, with an article and more sitelinks
    b, years, items = town()
    chapel = wiki.items_from([a_row("Q5", 1, 1, CHURCH, img="Kapell.jpg")],
                             [b_row("Q5", sv="Slottskyrkan", en="Royal Chapel", svt="Slottskyrkan", nsl=40)])
    palace = wiki.items_from([a_row("Q750444", 3, 3, "Q16560")], [b_row("Q750444", sv="Stockholms slott",
                                                                            en="Stockholm Palace", svt="Stockholms slott",
                                                                            nsl=60)])
    items = pd.concat([items, chapel, palace], ignore_index=True)
    commons, extracts, thumbs = stubs({})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=lambda t, lang: {}, thumbs=thumbs)
    assert out["table"].set_index("gid").qid[0] == "Q5"           # by the rules: the chapel (the palace is no Q41176)
    years = years.assign(landmark=["Stockholms slott", "", "", ""])
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=lambda t, lang: {}, thumbs=thumbs,
                         landmarks=[{"name": "Stockholms slott", "qid": "Q750444"}])
    t = out["table"].set_index("gid")
    assert (t.qid[0], t.name_en[0], t.placement[0]) == ("Q750444", "Stockholm Palace", "curated")


def test_a_curated_landmark_without_an_item_keeps_the_item_the_rules_choose_and_no_warning(capsys):
    # A Gamla stan house curated with qid "" has no item of its own to take, so its footprint keeps what the
    # rules place there (as before it was curated), and that is not worth a warning
    b, years, items = town()
    commons, extracts, thumbs = stubs({})
    before = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=lambda t, lang: {}, thumbs=thumbs)
    capsys.readouterr()
    years = years.assign(landmark=["Stora Nygatan 38", "", "", ""])
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=lambda t, lang: {}, thumbs=thumbs,
                         landmarks=[{"name": "Stora Nygatan 38", "qid": ""}])
    assert out["table"].qid.tolist() == before["table"].qid.tolist()
    assert out["table"].placement.tolist() == before["table"].placement.tolist()
    assert "warning" not in capsys.readouterr().err


def test_a_photo_that_fails_to_download_is_left_out():
    b, years, items = town()
    commons, extracts, _ = stubs({})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts,
                         thumbs=lambda photos: [sorted(photos)[0]])
    assert len(out["photos"]) == 1 and out["refused"] == {"thumbnail": 1}
    assert set(out["table"].photo) - {""} == set(out["photos"])


class Resp:
    def __init__(self, body, status=200):
        self.content, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_fetch_commons_and_extracts_ask_in_cached_batches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    def post(url, data=None, headers=None, timeout=None):
        calls.append((url, data["titles"]))
        if "commons" in url:
            return Resp(json.dumps({"query": {"pages": [{"title": t, "missing": True}
                                                        for t in data["titles"].split("|")]}}).encode())
        return Resp(json.dumps({"query": {"pages": [{"title": t, "extract": "X.", "lastrevid": 1}
                                                    for t in data["titles"].split("|")]}}).encode())

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(s06_wiki, "FILES_PER_REQUEST", 2)
    pages = s06_wiki.fetch_commons(["b.jpg", "a.jpg", "c.jpg", "a.jpg"], False, tmp_path / "data/raw/commons")
    assert [c[1] for c in calls] == ["File:a.jpg|File:b.jpg", "File:c.jpg"] and set(pages) == {"a.jpg", "b.jpg", "c.jpg"}
    s06_wiki.fetch_commons(["a.jpg", "b.jpg", "c.jpg"], False, tmp_path / "data/raw/commons")
    assert len(calls) == 2                                   # cached
    got = s06_wiki.fetch_extracts(["Kyrkan"], "sv", False, tmp_path / "data/raw/wiki/extracts")
    assert calls[-1] == ("https://sv.wikipedia.org/w/api.php", "Kyrkan") and got["Kyrkan"]["rev"] == 1


def test_an_api_error_answer_is_asked_again_never_cached_and_requests_go_a_pause_apart(tmp_path, monkeypatch, capsys):
    # MediaWiki answers maxlag or ratelimited with HTTP 200: cached, it would stop every later build until --refresh
    monkeypatch.chdir(tmp_path)
    waits, sent = [], []
    monkeypatch.setattr(s06_wiki, "sleep", waits.append)
    monkeypatch.setattr(s06_wiki, "_sent", [])
    good = json.dumps({"query": {"pages": [{"title": "File:a.jpg", "missing": True}]}}).encode()
    answers = [b'{"error": {"code": "maxlag"}}', good]

    def post(url, data=None, headers=None, timeout=None):
        sent.append(data)
        return Resp(answers[min(len(sent), len(answers)) - 1])
    monkeypatch.setattr(requests, "post", post)
    s06_wiki.fetch_commons(["a.jpg"], False, tmp_path / "data/raw/commons")
    assert len(sent) == 2 and waits == [s06_wiki.BACKOFF_S[0]] and sent[0]["maxlag"] == "5"
    assert json.loads((tmp_path / "data/raw/commons/meta_000.json").read_text()) == json.loads(good)
    assert "failed (the API answered maxlag)" in capsys.readouterr().err
    s06_wiki.fetch_extracts(["Kyrkan"], "sv", False, tmp_path / "data/raw/wiki/extracts")
    assert waits[-1] == s06_wiki.PAUSE_S and sent[-1]["maxlag"] == "5"          # the next request, a pause later
    answers[1] = answers[0]
    with pytest.raises(SystemExit, match="no endpoint answered"):
        s06_wiki.fetch_extracts(["Storkyrkan"], "en", False, tmp_path / "data/raw/wiki/extracts")
    assert not (tmp_path / "data/raw/wiki/extracts/en_000.json").exists()       # nothing of the error is kept


def test_fetch_thumbs_downloads_once_copies_to_web_and_drops_what_is_too_big(tmp_path, monkeypatch):
    got, waits = [], []
    monkeypatch.setattr(s06_wiki, "sleep", waits.append)

    def fake_get(url):
        got.append(url)
        if url.endswith("big.jpg"):
            return b"x" * (s06_wiki.city.WIKI["photo_bytes"] + 1)
        if url.endswith("gone.jpg"):
            raise requests.HTTPError("404")
        return b"jpeg"

    monkeypatch.setattr(s06_wiki, "get", fake_get)
    photos = {"a.jpg": {"thumb": "https://u/a.jpg"}, "b.jpg": {"thumb": "https://u/big.jpg"},
              "c.jpg": {"thumb": "https://u/gone.jpg"}}
    bad = s06_wiki.fetch_thumbs(photos, tmp_path / "thumbs", tmp_path / "web")
    assert sorted(bad) == ["b.jpg", "c.jpg"] and len(got) == 3 and waits == [1.0, 1.0]
    assert (tmp_path / "web" / "a.jpg").read_bytes() == b"jpeg" and not (tmp_path / "web" / "b.jpg").exists()
    assert s06_wiki.fetch_thumbs({"a.jpg": photos["a.jpg"]}, tmp_path / "thumbs", tmp_path / "web") == []
    assert len(got) == 3                                     # already on disk: not fetched again


def test_a_thumbnail_cached_before_its_key_named_the_width_is_kept(tmp_path, monkeypatch):
    # cached before 2026-10-17 as <sha1>.<ext>, at 500 px, the only width ever asked; moved, not fetched again
    monkeypatch.setattr(s06_wiki, "get", lambda url: pytest.fail("fetched again"))
    (tmp_path / "thumbs").mkdir()
    (tmp_path / "thumbs" / "abababababababab.jpg").write_bytes(b"jpeg")
    assert s06_wiki.fetch_thumbs({"abababababababab-500.jpg": {"thumb": "https://u/a.jpg"}}, tmp_path / "thumbs",
                                 tmp_path / "web") == []
    assert (tmp_path / "web" / "abababababababab-500.jpg").read_bytes() == b"jpeg"
    assert not (tmp_path / "thumbs" / "abababababababab.jpg").exists()


def test_main_writes_the_internal_files_and_the_review_list(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    b, years, items = town()
    (tmp_path / "data").mkdir()
    b.to_parquet(tmp_path / "data" / "buildings.parquet")
    years.assign(year=0, landmark="").to_parquet(tmp_path / "data" / "years.parquet")
    (tmp_path / "data" / "landmarks.json").write_text("[]")
    commons, extracts, thumbs = stubs({})
    monkeypatch.setattr(s06_wiki, "fetch_items", lambda refresh: (items, ANC))
    monkeypatch.setattr(s06_wiki, "fetch_commons", lambda files, refresh: commons(files))
    monkeypatch.setattr(s06_wiki, "fetch_extracts", lambda titles, lang, refresh: extracts(titles, lang))
    monkeypatch.setattr(s06_wiki, "fetch_thumbs", thumbs)
    monkeypatch.setattr(s06_wiki, "load_districts", lambda path: set())
    s06_wiki.main([])
    t = pd.read_parquet(tmp_path / "data" / "wiki.parquet")
    assert list(t.columns) == ["gid", "qid", "name", "name_en", "langs", "photo", "placement", "items", "wp_sv", "wp_en",
                               "label", "lon", "lat"]
    assert len(json.loads((tmp_path / "data" / "photos.json").read_text())) == 2
    assert set(json.loads((tmp_path / "data" / "extracts.json").read_text())) == {"0", "2"}
    assert (tmp_path / "data" / "review-photos.txt").read_text().startswith("# photos whose file looks like a work")
    assert "3 footprints with a building item, 2 photos" in capsys.readouterr().out


def test_main_leaves_out_a_takedown(tmp_path, monkeypatch, capsys):
    # A building in the takedown list (pipeline/suppress.yml, here its own file) gets no item, photo or excerpt
    monkeypatch.chdir(tmp_path)
    b, years, items = town()
    (tmp_path / "data").mkdir()
    b.to_parquet(tmp_path / "data" / "buildings.parquet")
    years.assign(year=0, landmark="").to_parquet(tmp_path / "data" / "years.parquet")
    (tmp_path / "data" / "landmarks.json").write_text("[]")
    (tmp_path / "suppress.yml").write_text(f"- oid: {int(b.oid[0])}\n  date: 2026-11-02\n")
    commons, extracts, thumbs = stubs({})
    monkeypatch.setattr(s06_wiki, "fetch_items", lambda refresh: (items, ANC))
    monkeypatch.setattr(s06_wiki, "fetch_commons", lambda files, refresh: commons(files))
    monkeypatch.setattr(s06_wiki, "fetch_extracts", lambda titles, lang, refresh: extracts(titles, lang))
    monkeypatch.setattr(s06_wiki, "fetch_thumbs", thumbs)
    monkeypatch.setattr(s06_wiki, "load_districts", lambda path: set())
    s06_wiki.main(["--suppress", str(tmp_path / "suppress.yml")])
    assert 0 not in pd.read_parquet(tmp_path / "data" / "wiki.parquet").gid.tolist()
    assert set(json.loads((tmp_path / "data" / "extracts.json").read_text())) == {"2"}
    assert "suppressed: 1 buildings" in capsys.readouterr().out


# ---------- Pacing by what is sent, thumbnail retries, a real image, a missing landmark ----------

def test_a_shifted_batch_is_sent_a_pause_after_the_last(tmp_path, monkeypatch):
    # batches are named by position: one more file shifts every later batch's query, and those go out again
    monkeypatch.chdir(tmp_path)
    waits, sent = [], []
    monkeypatch.setattr(s06_wiki, "sleep", waits.append)
    monkeypatch.setattr(s06_wiki, "FILES_PER_REQUEST", 1)

    def post(url, data=None, headers=None, timeout=None):
        sent.append(data["titles"])
        return Resp(json.dumps({"query": {"pages": [{"title": data["titles"], "missing": True}]}}).encode())
    monkeypatch.setattr(requests, "post", post)
    s06_wiki.fetch_commons(["b.jpg", "c.jpg"], False, tmp_path / "data/raw/commons")
    assert len(sent) == 2 and waits == [s06_wiki.PAUSE_S]
    monkeypatch.setattr(s06_wiki, "_sent", [])                      # a later run
    s06_wiki.fetch_commons(["a.jpg", "b.jpg", "c.jpg"], False, tmp_path / "data/raw/commons")
    assert len(sent) == 5 and waits == [s06_wiki.PAUSE_S] * 3       # three batches changed: each a pause apart


def test_a_rate_limited_thumbnail_is_asked_again_after_its_retry_after(tmp_path, monkeypatch):
    waits, tries = [], []
    monkeypatch.setattr(s06_wiki, "sleep", waits.append)
    monkeypatch.setattr(s06_wiki, "_sent", ["meta_000.json"])      # the Commons request just before

    class Busy:
        status_code, headers = 429, {"Retry-After": "40"}

    def fake_get(url):
        tries.append(url)
        if len(tries) == 1:
            raise requests.HTTPError("429", response=Busy())
        return b"jpeg"
    monkeypatch.setattr(s06_wiki, "get", fake_get)
    bad = s06_wiki.fetch_thumbs({"a.jpg": {"thumb": "https://u/a.jpg"}}, tmp_path / "thumbs", tmp_path / "web")
    assert bad == [] and len(tries) == 2 and waits == [s06_wiki.PAUSE_S, 40]
    assert (tmp_path / "web" / "a.jpg").read_bytes() == b"jpeg"


def test_get_refuses_an_answer_that_is_not_an_image(monkeypatch):
    class Page:
        status_code, headers, content = 200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>"

        def raise_for_status(self):
            pass
    monkeypatch.setattr(requests, "get", lambda url, headers=None, timeout=None: Page())
    with pytest.raises(requests.RequestException, match="not an image"):
        s06_wiki.get("https://u/a.jpg")


def test_a_landmark_whose_item_is_missing_is_reported(capsys):
    b, years, items = town()
    years = years.assign(landmark=["Stockholms slott", "", "", ""])
    s06_wiki.select(b, years, items, ANC, [{"name": "Stockholms slott", "qid": "Q750444"}])
    assert "Stockholms slott's item Q750444 is not among the items" in capsys.readouterr().err


# ---------- Curated photo picks (added 2026-10-16) ----------

def wide(sha1, width=4000, **meta):
    """A Commons page as stubs() gives it, with the original's width (imageinfo `width`, from iiprop `size`)."""
    p = page(sha1=sha1, **meta)
    p["imageinfo"][0]["width"] = width
    return p


def pick_stubs(asked, pages):
    """stubs(), with the Commons answer for each file from `pages` ({file: page}, the rest an open-licence page)."""
    commons, extracts, thumbs = stubs(asked)

    def commons_picks(files):
        asked["files"] = files
        return {f: pages.get(f) or wide(f"{i:02x}" * 20) for i, f in enumerate(files)}
    return commons_picks, extracts, thumbs


def test_a_pick_replaces_the_wikidata_image():
    b, years, items = town()
    asked = {}
    commons, extracts, thumbs = pick_stubs(asked, {"Kyrkan 2020.jpg": wide("cd" * 20)})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts, thumbs=thumbs,
                         picks={"Q1": "Kyrkan 2020.jpg"})
    t = out["table"].set_index("gid")
    assert asked["files"] == ["Kyrkan 2020.jpg", "Slott.jpg"]           # Q1's P18, Kyrka.jpg, is not even asked for
    assert t.photo[0] == "cdcdcdcdcdcdcdcd-500.jpg" and t.photo[0] in out["photos"]
    assert out["picks"] == {"used": 1, "none": 0, "refused": {}, "unplaced": []}


def test_a_pick_of_none_shows_no_photo():
    b, years, items = town()
    asked = {}
    commons, extracts, thumbs = pick_stubs(asked, {})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts, thumbs=thumbs,
                         picks={"Q1": ""})
    t = out["table"].set_index("gid")
    assert asked["files"] == ["Slott.jpg"] and t.photo[0] == ""
    assert out["picks"]["none"] == 1 and out["picks"]["used"] == 0


def test_a_pick_that_fails_a_check_gives_no_photo_never_the_wikidata_image():
    b, years, items = town()
    asked = {}
    refused = {"Kyrka NC.jpg": wide("cd" * 20, License="cc-by-nc-sa-4.0", LicenseShortName="CC BY-NC-SA 4.0"),
               "Slott liten.jpg": wide("ef" * 20, width=499)}            # narrower than the 500 px thumbnail
    commons, extracts, thumbs = pick_stubs(asked, refused)
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts, thumbs=thumbs,
                         picks={"Q1": "Kyrka NC.jpg", "Q3": "Slott liten.jpg"})
    t = out["table"].set_index("gid")
    assert asked["files"] == ["Kyrka NC.jpg", "Slott liten.jpg"]          # neither P18 is asked for
    assert t.photo[0] == "" and t.photo[2] == "" and out["photos"] == {}
    assert out["picks"]["refused"] == {"licence CC BY-NC-SA 4.0": 1, "narrow": 1}
    assert out["refused"] == {"licence CC BY-NC-SA 4.0": 1, "narrow": 1}


def test_a_pick_goes_through_the_deny_list_and_the_designation_rule(monkeypatch):
    b, years, items = town()
    monkeypatch.setattr(s06_wiki.city, "PHOTO_DENY", {"Kyrka staty.jpg"})
    title = wide("ef" * 20, License="cc-by-sa-3.0", LicenseShortName="CC BY-SA 3.0", ObjectName="Slottet 3, 2012")
    commons, extracts, thumbs = pick_stubs({}, {"Slottet 3, 2012.jpg": title})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts, thumbs=thumbs,
                         picks={"Q1": "Kyrka staty.jpg", "Q3": "Slottet 3, 2012.jpg"})
    assert set(out["table"].photo) == {""}
    assert out["picks"]["refused"] == {"deny list": 1, "designation": 1}


def test_a_pick_whose_thumbnail_fails_is_left_out_like_any_photo():
    b, years, items = town()
    commons, extracts, _ = pick_stubs({}, {"Kyrkan 2020.jpg": wide("cd" * 20)})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts,
                         thumbs=lambda photos: ["cdcdcdcdcdcdcdcd-500.jpg"], picks={"Q1": "Kyrkan 2020.jpg"})
    assert out["table"].set_index("gid").photo[0] == ""
    assert out["picks"]["used"] == 0 and out["picks"]["refused"] == {"thumbnail": 1}


def test_an_unpicked_item_keeps_its_wikidata_image_and_an_unplaced_pick_is_reported():
    b, years, items = town()
    asked = {}
    commons, extracts, thumbs = pick_stubs(asked, {})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts, thumbs=thumbs,
                         picks={"Q1": "", "Q2": "Villa 2020.jpg", "Q99": "Annat.jpg"})
    t = out["table"].set_index("gid")
    assert asked["files"] == ["Slott.jpg"] and t.photo[2] != ""          # Q3 is not in the table: its P18
    assert out["picks"]["unplaced"] == ["Q2", "Q99"]       # Q2 stands on an uncurated private house: no card at all
    assert out["p18"] == 1


def test_read_picks_reads_none_as_no_photo_and_refuses_a_malformed_table(tmp_path):
    f = tmp_path / "picks.csv"
    f.write_text("qid,commons_file,decision\nQ1,Kyrkan 2020.jpg,pick\nQ2,none,none; none_found\n", encoding="utf-8")
    t = s06_wiki.read_picks(f)
    assert s06_wiki.picks_of(t) == {"Q1": "Kyrkan 2020.jpg", "Q2": ""}
    for bad in ("Q1,Kyrkan.jpg,pick\nQ1,Kyrka.jpg,pick\n",            # a qid twice
                "Q1,File:Kyrkan.jpg,pick\n",                          # a file with its namespace
                "Q1,file:Kyrkan.jpg,pick\n",                          # ... in any case
                "Q1,Kyrkan_2020.jpg,pick\n",                          # an underscore (a URL's), which Commons reads as a space
                "Q1,Kyrkan.jpg,\n",                                   # no decision
                "Q1,Kyrkan.jpg,kept\n",                               # a decision that is no pick, alternative or none
                "Q1,Kyrkan.jpg,none; none_found\n",                   # none with a file
                "Q1,none,pick\n", "Q1,None,none\n",                   # a pick without one; "none" in another case
                "X1,Kyrkan.jpg,pick\n"):                              # not a qid
        f.write_text("qid,commons_file,decision\n" + bad, encoding="utf-8")
        with pytest.raises(ValueError):
            s06_wiki.read_picks(f)


def test_main_lists_the_decided_picks_and_the_spot_check_in_the_review(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    b, years, items = town()
    (tmp_path / "data").mkdir()
    b.to_parquet(tmp_path / "data" / "buildings.parquet")
    years.assign(year=0, landmark="").to_parquet(tmp_path / "data" / "years.parquet")
    (tmp_path / "data" / "landmarks.json").write_text("[]")
    (tmp_path / "picks.csv").write_text(
        "qid,commons_file,decision\nQ1,Kyrkan 2020.jpg,pick; low confidence: a rear facade (spot-check)\n"
        "Q3,none,none; which_building: the point may be on the other wing\nQ4,Hus.jpg,pick\n", encoding="utf-8")
    commons, extracts, thumbs = pick_stubs({}, {})
    monkeypatch.setattr(s06_wiki, "PICKS", tmp_path / "picks.csv")
    monkeypatch.setattr(s06_wiki, "fetch_items", lambda refresh: (items, ANC))
    monkeypatch.setattr(s06_wiki, "fetch_commons", lambda files, refresh: commons(files))
    monkeypatch.setattr(s06_wiki, "fetch_extracts", lambda titles, lang, refresh: extracts(titles, lang))
    monkeypatch.setattr(s06_wiki, "fetch_thumbs", thumbs)
    monkeypatch.setattr(s06_wiki, "load_districts", lambda path: set())
    s06_wiki.main([])
    review = (tmp_path / "data" / "review-photos.txt").read_text()
    assert "pick: Q1 Kyrkan 2020.jpg: pick; low confidence: a rear facade (spot-check)\n" in review
    assert "pick: Q3 none: none; which_building: the point may be on the other wing\n" in review
    assert "Q4" not in review                                # a plain pick needs no look
    assert "spot-check: Q1 Kyrkan 2020.jpg\n" in review
    assert "picks: 2 used, 1 none, 0 refused" in capsys.readouterr().out


def test_the_committed_pick_table_follows_the_research():
    # every pick is the research's file or one of its alternatives, or none; every flagged row has its decision
    import csv
    research = {r["qid"]: r for r in csv.DictReader(open("docs/research/2026-10-16-landmark-photos.csv",
                                                         encoding="utf-8"))}
    t = s06_wiki.read_picks(s06_wiki.PICKS)
    assert set(t.qid) == set(research)
    for q, f, d in zip(t.qid, t.commons_file, t.decision):
        r = research[q]
        alts = [a.strip().removeprefix("File:") for a in r["alternatives"].split("|") if a.strip()]
        assert d.split(";")[0] in ("pick", "alternative", "none"), (q, d)
        if d.startswith("pick"):
            assert f == r["commons_file"].removeprefix("File:"), q
        elif d.startswith("alternative"):
            assert f in alts, q
        else:
            assert f == "none", q
        if r["flags"] or r["confidence"] == "low":
            assert d != "pick", (q, "a flagged row records its decision")


# ---------- Follow-ups (2026-10-17): the photos refused for a property designation, listed for review ----------

def test_build_names_each_photo_refused_for_a_designation_with_its_item():
    b, years, items = town()
    title = wide("ef" * 20, License="cc-by-sa-3.0", LicenseShortName="CC BY-SA 3.0", ObjectName="Slottet 3, 2012")
    commons, extracts, thumbs = pick_stubs({}, {"Slott.jpg": title})
    out = s06_wiki.build(b, years, set(), items, ANC, commons=commons, extracts=extracts, thumbs=thumbs)
    assert out["refused"] == {"designation": 1}
    assert out["designation"] == [("Slott.jpg", "Q3")]


def test_main_lists_the_designation_refusals_in_the_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b, years, items = town()
    (tmp_path / "data").mkdir()
    b.to_parquet(tmp_path / "data" / "buildings.parquet")
    years.assign(year=0, landmark="").to_parquet(tmp_path / "data" / "years.parquet")
    (tmp_path / "data" / "landmarks.json").write_text("[]")
    (tmp_path / "picks.csv").write_text("qid,commons_file,decision\n", encoding="utf-8")
    title = wide("ef" * 20, License="cc-by-sa-3.0", LicenseShortName="CC BY-SA 3.0", ObjectName="Slottet 3, 2012")
    commons, extracts, thumbs = pick_stubs({}, {"Slott.jpg": title})
    monkeypatch.setattr(s06_wiki, "PICKS", tmp_path / "picks.csv")
    monkeypatch.setattr(s06_wiki, "fetch_items", lambda refresh: (items, ANC))
    monkeypatch.setattr(s06_wiki, "fetch_commons", lambda files, refresh: commons(files))
    monkeypatch.setattr(s06_wiki, "fetch_extracts", lambda titles, lang, refresh: extracts(titles, lang))
    monkeypatch.setattr(s06_wiki, "fetch_thumbs", thumbs)
    monkeypatch.setattr(s06_wiki, "load_districts", lambda path: set())
    s06_wiki.main([])
    review = (tmp_path / "data" / "review-photos.txt").read_text()
    assert "# photos refused for a property designation in their title (file, item)\n" in review
    assert "designation: Slott.jpg (Q3)\n" in review


def test_the_five_held_photos_follow_the_which_building_note():
    # Two picks kept, one alternative, two without a photo
    t = s06_wiki.read_picks(s06_wiki.PICKS).set_index("qid")
    assert t.commons_file["Q537"] == "Prins Eugens Waldemarsudde 02.jpg"
    assert t.commons_file["Q10613664"] == "Oxenstiernska malm 2009e.jpg"
    assert t.commons_file["Q10716820"] == "Strandvägen 55.JPG" and t.decision["Q10716820"].startswith("alternative")
    assert t.commons_file["Q3652398"] == "none" and t.commons_file["Q255031"] == "none"
    assert all("which-building-photos" in t.decision[q] for q in ("Q537", "Q10613664", "Q10716820", "Q3652398",
                                                                   "Q255031"))
