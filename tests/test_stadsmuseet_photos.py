"""The City Museum's archive photos (Task 20): which photos the rules keep (CC BY, exteriors, one footprint by
address, never a private house, a designation or a denied photo), their order and cap, the card's entry and credit,
the file fitted to the site's size, s03_tiles' `arch` and s99's checks. The assets here are trimmed copies of the
archive's answers with made-up ids, addresses ("Exempelgatan") and designations ("Exempel 12")."""
import io
import json

import numpy as np
import pandas as pd
import pytest
import requests
from PIL import Image

from pipeline import s02_stadsmuseet_photos, s03_tiles, s99_validate, stadsmuseet_photos as sp

ARCHIVE = "/fotoweb/archives/5000-Alla-fotografier"
SITE = "https://digitalastadsmuseet.stockholm.se"


def asset(pid, *, title="Exempelgatan 1, fasad mot gatan", year="1925", licence="BY", address="Exempelgatan 1",
          by=("Larsson, Erik",), keywords=("FasaderFacades",), designation=(), rendition=True):
    md = {"5": {"value": title}, "510": {"value": address}, "539": {"value": year}, "590": {"value": licence},
          "80": {"value": list(by)}, "25": {"value": list(keywords)}, "507": {"value": list(designation)},
          "516": {"value": "EXEMPEL"}, "576": {"value": "GAMLA STAN"}}
    href = f"{ARCHIVE}/Fotografier/{pid}.jpg.info"
    cache = f"/fotoweb/cache/v2/a/b/Fotografier/{pid}.jpg"
    prev = [{"href": f"{cache}.s400.jpg", "size": 400, "square": False},             # too small
            {"href": f"{cache}.sq.jpg", "size": 1200, "square": True},              # a square crop
            *([{"href": f"{cache}.s1600.jpg", "size": 1600, "square": False},
               {"href": f"{cache}.s1200.jpg", "size": 1200, "square": False}] if rendition else [])]
    return {"href": href, "metadata": md, "previews": prev}


TABLE = pd.DataFrame({"gid": [1, 2, 3], "street": ["Exempelgatan", "Exempelgatan", "Provgränd"],
                      "number": ["1", "3", "2"]})


def test_item_reads_the_fields_and_its_own_page():
    it = sp.item(asset("SSMF001"))
    assert it["id"] == "SSMF001" and it["page"] == f"{SITE}{ARCHIVE}/Fotografier/SSMF001.jpg.info"
    assert it["year"] == 1925 and it["licence"] == "BY" and it["by"] == ["Larsson, Erik"]
    assert it["rendition"].endswith(".s1200.jpg")      # the 1,200 preview: never a square crop, never the original
    # a document archive's page, or a search address, is not a photo's own page
    assert sp.item({**asset("x"), "href": "/fotoweb/archives/5004-Dokument-och-publikationer/a/b.pdf.info"}) is None
    assert sp.item({**asset("x"), "href": f"{ARCHIVE}/?516=EXEMPEL"}) is None
    # several queries answer the same photo: once each
    assert [i["id"] for i in sp.items([asset("b"), asset("a"), asset("b")])] == ["a", "b"]


@pytest.mark.parametrize("text, year", [("1925", 1925), (" 1850 ", 1850), ("1920-1930", None), ("1920-talet", None),
                                        ("", None), ("1700", None)])
def test_year_of_only_a_single_year(text, year):
    assert sp.year_of(text) == year


def test_exteriors_only():
    assert sp.exterior("Exempelgatan 1, fasad mot gatan")
    assert sp.exterior("Vy över Riddarholmen från Söder")
    for title in ("Interiör, salen i andra våningen", "Portal mot gården", "Källarvalv", "Detalj av fönster",
                  "Takmålning i rummet", "Trapphuset"):
        assert not sp.exterior(title), title
    assert not sp.exterior("Exempelgatan 1", ["InteriörerInteriors"])
    assert sp.exterior("Exempelgatan 1", ["Gator och torgStreets and squares"])


def test_credited_names():
    assert sp.credited(["Larsson, Erik"]) == ["Erik Larsson"]
    assert sp.credited(["Okänd"]) == []
    assert sp.credited(["Larssons, Ateljé", "Larssons Ateljé"]) == ["Larssons Ateljé"]


def test_place_needs_exactly_one_footprint():
    its = sp.items([asset("one"), asset("two", address="Exempelgatan 1, Exempelgatan 3"), asset("none", address="")])
    assert sp.place(its, TABLE) == {"one": 1}


def test_choose_applies_every_rule_oldest_first_and_caps():
    assets = [asset("p1", year="1930"), asset("p2", year=""), asset("p3", year="1880"), asset("p4", year="1905"),
              asset("nc", licence="BY-NC-ND"), asset("in", title="Interiör, salen"),
              asset("ev", title="Exempelgatan 1. Kungen inviger huset."),
              asset("priv", address="Exempelgatan 3"), asset("des", title="Exempel 12 från gatan"),
              asset("deny"), asset("norend", rendition=False), asset("far", address="Ingenstans 9"),
              asset("grp", keywords=("GatorStreets", "GrupporträttGroup portraits")), asset("nokw", keywords=())]
    its = sp.items(assets)
    picks, n = sp.choose(its, sp.place(its, TABLE), private={2}, designations={"exempel 12"},
                         deny={"deny": "not this building"})
    assert [p["id"] for p in picks[1]] == ["p3", "p4", "p1"]          # oldest first, the undated one over the cap
    assert set(picks) == {1}
    assert n == {"unplaced": 1, "licence": 1, "interior or detail": 1, "people or event": 2, "no building keyword": 1,
                 "private house": 1, "designation": 1, "deny list": 1, "no rendition": 1, "over the cap": 1}
    # outside FULL_AREAS a building gets MAX_ELSEWHERE photos: the oldest
    picks, n = sp.choose(its, sp.place(its, TABLE), private={2}, designations={"exempel 12"},
                         deny={"deny": "not this building"}, full={3})
    assert [p["id"] for p in picks[1]] == ["p3"] and n["over the cap"] == 3


@pytest.mark.parametrize("title, keywords", [
    ("Operans balettskola har uppvisning.", ["BarnChildren", "BalettBallet"]),
    ("Beredskapsträff på restaurang.", ["GrupporträttGroup portraits"]),
    ("Myntgatan 5. Civildepartementet.", ["KontorOffices", "PolitikerPoliticians"]),
    ("Stadshusbygget. Portvakt Widmark med sin hund Lord.", ["Offentliga byggnaderPublic buildings"]),
    ("Stadshusbygget. En grupp med Torngrundsarbetare.", ["ByggnadsarbetareConstruction worker"]),
    ("Silverutställning.", ["UtställningarExhibitions"]),
])
def test_people_or_event_by_keywords_too(title, keywords):
    assert sp.people_or_event(title, keywords)


def test_building_view_needs_a_place_keyword():
    for kws in (["FasaderFacades"], ["Gatumiljöer"], ["Offentliga byggnaderPublic buildings"], ["TorgSquares"],
                ["KontorsbyggnaderOffice buildings"], ["Allmänna utsikter"], ["Gårdar (gårdsmiljöer)Yards"]):
        assert sp.building_view(kws) and not sp.people_or_event("Skeppsbron 10.", kws), kws
    for kws in ([], ["Renoveringar"], ["Torghandel"], ["FängelserPrisons"], ["MuseerMuseums"]):
        assert not sp.building_view(kws), kws


def test_read_deny(tmp_path):
    p = tmp_path / "deny.txt"
    p.write_text("# comment\n\nSSMF001\tnot this building\nSSMF002 a courtyard\n", encoding="utf-8")
    assert sp.read_deny(p) == {"SSMF001": "not this building", "SSMF002": "a courtyard"}
    p.write_text("SSMF001\n", encoding="utf-8")
    with pytest.raises(ValueError, match="reason"):
        sp.read_deny(p)
    p.write_text("SSMF001 a\nSSMF001 b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="twice"):
        sp.read_deny(p)
    assert all(sp.read_deny(sp.DENY).values())    # the repo's list parses, each id with its reason


def test_entry_and_its_title():
    it = sp.item(asset("SSMF001", by=("Okänd",)))
    e = sp.entry(it, "0123456789abcdef-800.jpg", 800, 600)
    assert e == {"key": "0123456789abcdef-800.jpg", "w": 800, "h": 600, "y": 1925, "page": it["page"],
                 "t": "Exempelgatan 1, fasad mot gatan"}
    # a title that says who owns the building is left out; no year, no `y`
    owned = sp.item(asset("SSMF002", title="Huset som ägs av familjen", year=""))
    assert "t" not in sp.entry(owned, "k", 1, 1) and "y" not in sp.entry(owned, "k", 1, 1)


def jpeg(w, h, fmt="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 110, 100)).save(buf, fmt)
    return buf.getvalue()


def test_fit_keeps_a_small_jpeg_and_scales_a_large_one():
    small = jpeg(800, 600)
    assert sp.fit(small, max_bytes=10**6) == (small, 800, 600)
    body, w, h = sp.fit(jpeg(2400, 1800), max_bytes=10**6)
    assert (w, h) == (sp.MAX_WIDTH, 900) and Image.open(io.BytesIO(body)).format == "JPEG"
    _, w, _ = sp.fit(jpeg(600, 400, "PNG"), max_bytes=10**6)
    assert w == 600
    assert sp.key_of(small, 800).endswith("-800.jpg") and len(sp.key_of(small, 800)) == 16 + len("-800.jpg")


def test_files_copy_the_fitted_renditions(tmp_path):
    its = sp.items([asset("p1"), asset("gone")])
    picks = {1: its}
    cards, missing = s02_stadsmuseet_photos.files(picks, get=lambda pid, href: jpeg(640, 480) if pid == "p1" else None,
                                                  web=tmp_path)
    assert missing == 1 and [e["id"] for e in cards[1]] == ["p1"]
    assert (tmp_path / cards[1][0]["key"]).is_file()


def test_card_shards_never_put_archive_photos_on_a_hidden_card():
    df = pd.DataFrame({"gid": [0, 1], "name": ["", ""], "architects": [[], []], "raa_id": [None, None],
                       "private": [0, 1], "kategori": ["Allmän byggnad", "Allmän byggnad"], "ysrc": [0, 0]})
    arch = [{"key": "0123456789abcdef-800.jpg", "w": 800, "h": 600, "y": 1925, "page": "p", "id": "dropped"}]
    shards = s03_tiles.card_shards(df, archive={0: arch, 1: arch})
    assert shards[0]["0"]["arch"] == [{"key": "0123456789abcdef-800.jpg", "w": 800, "h": 600, "y": 1925, "page": "p"}]
    assert "arch" not in shards[1].get("1", {})
    assert s03_tiles.photo_gids(shards) == [0]
    assert s03_tiles.used_photos(shards) == ["0123456789abcdef-800.jpg"]


class FakeResponse:
    def __init__(self, body: bytes):
        self.content, self.status_code = body, 200

    def raise_for_status(self):
        pass


def placed(pid, stadsdel, kvarter):
    a = asset(pid)
    a["metadata"]["576"], a["metadata"]["516"] = {"value": stadsdel}, {"value": kvarter}
    return a


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """The archive's answers by query: {(field, value, page): assets}; Gamla stan has two pages, and its first answers
    a Södermalm photo too (a query answers items that do not hold its value)."""
    from pipeline import s00_fetch_stadsmuseet as s00
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    monkeypatch.setattr(s00, "sleep", lambda s: None)
    answers = {("576", "GAMLA STAN", 0): [placed("a1", "GAMLA STAN", "EXEMPEL"), placed("x", "SÖDERMALM", "ANNAT")],
               ("576", "GAMLA STAN", 1): [placed("a2", "GAMLA STAN", "CEPHEUS")],
               ("576", "RIDDARHOLMEN", 0): [placed("a3", "RIDDARHOLMEN", "")],
               ("516", "CEPHEUS", 0): [placed("a2", "GAMLA STAN", "CEPHEUS"), placed("a4", "", "CEPHEUS")],
               ("516", "EXEMPEL", 0): [placed("a1", "GAMLA STAN", "EXEMPEL")],
               ("516", s00.NO_SUCH, 0): []}
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        assert url == s00.PHOTO_ARCHIVE and headers["Accept"] == "application/vnd.fotoware.assetlist+json"
        (field, value), p = next((k, v) for k, v in params.items() if k != "p"), int(params.get("p", 0))
        calls.append((field, value, p))
        last = 1 if (field, value) == ("576", "GAMLA STAN") else 0
        body = {"data": answers.get((field, value, p), []),
                "paging": {"last": f"{url}?{field}=x&p={last}"} if last else {}}
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr(requests, "get", get)
    return s00, answers, calls


def test_fetch_photos_keeps_only_items_that_hold_the_value(archive):
    s00, _, calls = archive
    out = s00.fetch_photos(refresh=False)
    ids = sorted(sp.item(a)["id"] for a in s00.read_photo_assets())
    assert ids == ["a1", "a2", "a3", "a4"]                 # never the Södermalm photo; a4 through its kvarter
    q = {(r["field"], r["value"]): (r["answered"], r["kept"]) for r in out["queries"]}
    assert q[("576", "GAMLA STAN")] == (3, 2) and q[("516", "CEPHEUS")] == (2, 2)
    assert set(s00.read_photo_assets()[0]["metadata"]) <= set(s00.KEEP)
    calls.clear()
    s00.fetch_photos(refresh=False)                        # a second run asks nothing
    assert calls == []


def test_fetch_photos_asks_every_stadsdel_and_the_kvarter_of_gamla_stan_only(archive):
    s00, answers, calls = archive
    answers[("576", "SÖDERMALM", 0)] = [placed("s1", "SÖDERMALM", "ANNAT")]
    s00.fetch_photos(refresh=False, areas=["GAMLA STAN", "RIDDARHOLMEN", "SÖDERMALM"])
    ids = sorted(sp.item(a)["id"] for a in s00.read_photo_assets())
    assert ids == ["a1", "a2", "a3", "a4", "s1"] and ("516", "ANNAT", 0) not in calls


def test_stadsdelar_gamla_stan_first(tmp_path):
    import geopandas as gpd
    from shapely.geometry import Point
    from pipeline import s00_fetch_stadsmuseet as s00
    shp = tmp_path / "Stadsdel.shp"
    gpd.GeoDataFrame({"NAMN": ["ÖSTERMALM", "GAMLA STAN", "AKALLA", "RIDDARHOLMEN"]},
                     geometry=[Point(0, 0)] * 4, crs="EPSG:3011").to_file(shp)
    assert s00.stadsdelar(shp) == ["GAMLA STAN", "RIDDARHOLMEN", "AKALLA", "ÖSTERMALM"]
    assert s00.stadsdelar(tmp_path / "none.shp") == ["GAMLA STAN", "RIDDARHOLMEN"]


def test_fetch_photos_refuses_an_archive_that_does_not_filter(archive):
    s00, answers, _ = archive
    answers[("516", s00.NO_SUCH, 0)] = [placed("a1", "GAMLA STAN", "EXEMPEL")]
    with pytest.raises(SystemExit, match="do not filter"):
        s00.fetch_photos(refresh=False)


def write_cards(out, cards):
    (out / "cards").mkdir(parents=True, exist_ok=True)
    (out / "cards" / "00.json").write_text(json.dumps({str(g): c for g, c in cards.items()}), encoding="utf-8")


def test_s99_checks_the_archive_photos(tmp_path):
    out = tmp_path / "v1"
    photos = tmp_path / "photos"
    photos.mkdir()
    key = "0123456789abcdef-800.jpg"
    (photos / key).write_bytes(jpeg(800, 600))
    page = f"{SITE}{ARCHIVE}/Fotografier/SSMF001.jpg.info"
    good = [{"key": key, "w": 800, "h": 600, "y": 1900, "by": "Erik Larsson", "page": page},
            {"key": key, "w": 800, "h": 600, "page": page}]
    write_cards(out, {0: {"arch": good}})
    (out / "photos.json").write_text(json.dumps([key]), encoding="utf-8")
    assert s99_validate.check_archive_photos(out, np.array([False, False])) == []
    bad = [{"key": key, "w": 800, "h": 600, "page": page}, {"key": "nope.jpg", "w": 0, "h": 600, "y": 1900,
                                                            "page": f"{SITE}{ARCHIVE}/?516=EXEMPEL", "x": 1}]
    write_cards(out, {0: {"arch": good * 2}, 1: {"arch": bad}})
    errors = s99_validate.check_archive_photos(out, np.array([False, True]))
    assert any("private house" in e for e in errors) and any("1 to 3" in e for e in errors)
    assert any("oldest first" in e for e in errors) and any("own .info page" in e for e in errors)
    assert any("fields other" in e for e in errors) and any("width and height" in e for e in errors)
    assert any(f"not in {tmp_path.name}/photos" in e for e in errors) and any("photos.json does not list" in e for e in errors)


def test_a_photo_file_is_a_small_preview_never_an_original(tmp_path, monkeypatch, capsys):
    # The archive's rendition service sent originals of up to 76 MB (2026-10-20): only a preview, by GET, is taken
    import requests

    from pipeline import s00_fetch_stadsmuseet as s00
    monkeypatch.setattr(s00, "_pace", lambda cached: None)
    bodies = {}

    class R:
        def __init__(self, body):
            self.content, self.status_code = body, 200

        def raise_for_status(self):
            pass

    monkeypatch.setattr(requests, "get", lambda url, headers=None, timeout=None: R(bodies[url]))
    ok = "/fotoweb/cache/v2/a/b/Fotografier/OK.jpg.s1200.jpg"
    big = "/fotoweb/cache/v2/a/b/Fotografier/BIG.jpg.s1200.jpg"
    bodies[SITE + ok] = b"\xff\xd8\xff" + b"0" * 1000
    bodies[SITE + big] = b"\xff\xd8\xff" + b"0" * (s00.MAX_FILE + 1)
    assert s00.fetch_rendition("OK", ok, folder=tmp_path) == bodies[SITE + ok]
    assert (tmp_path / "OK.jpg").exists()
    assert s00.fetch_rendition("BIG", big, folder=tmp_path) is None
    assert s00.fetch_rendition("R", f"{ARCHIVE}/Fotografier/R.jpg.info/__renditions/1280", folder=tmp_path) is None
    assert "more than a preview" in capsys.readouterr().err


@pytest.mark.parametrize("title, people", [
    ("Evert Taube hyllas på Gyllene Freden, Österlånggatan 51", True),
    ("Bibelsällskapet i Storkyrkan. På bilden ser vi Pastor Primarius Olle Nystedt", True),
    ("Prinsessan Sibylla eskorterad av General Testrup på väg in i Storkyrkan", True),
    ("Porträtt av Sveabolagets chef Emanuel Högberg", True),
    ("Västerlånggatan 49. Överståthållare Hagander inviger det nya Sparbankskontoret.", True),
    ("Företaget Birke & CO firar 25 års jubileum på Gyllene Freden.", True),
    ("Skeppsbron 24.", False),
    ("Slussplan 5-9. Vy mot kvarteret Achilles", False),
    ("Stora Nygatan 38. Klädesbutik för herrkläder.", False),
    ("Stortorget, västra sidan", False),
])
def test_a_portrait_or_an_event_is_not_a_building_photo(title, people):
    # the owner, 2026-10-20: people and events add atmosphere but take a building photo's place on the card
    assert sp.people_or_event(title) is people
