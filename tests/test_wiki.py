"""Wikidata items on footprints, Commons credits and Wikipedia excerpts (Plan 4a, Task 6). No network."""
import pytest
from pyproj import Transformer

from pipeline import city, privacy, wiki
from tests import synth

TO_WGS84 = Transformer.from_crs(city.CRS, 4326, always_xy=True)
E = "http://www.wikidata.org/entity/"
BUILDING, MUSEUM, FOUNTAIN, CHURCH = "Q41176", "Q33506", "Q483453", "Q16970"
ANC = {CHURCH: {CHURCH, BUILDING}, BUILDING: {BUILDING}, MUSEUM: {MUSEUM, "Q43229"}, FOUNTAIN: {FOUNTAIN}}


def point(dx, dz):
    lon, lat = TO_WGS84.transform(city.ORIGIN[0] + dx, city.ORIGIN[1] - dz)
    return f"Point({lon} {lat})"


def a_row(q, dx, dz, cls=BUILDING, img=None, ended=False):
    r = {"item": E + q, "coord": point(dx, dz), "cls": E + cls, "ended": "true" if ended else "false"}
    if img:
        r["img"] = "http://commons.wikimedia.org/wiki/Special:FilePath/" + img.replace(" ", "%20")
    return r


def b_row(q, sv="", en="", svt="", ent="", nsl=0):
    r = {"item": E + q, "nsl": str(nsl)}
    r.update({k: v for k, v in (("sv", sv), ("en", en), ("svt", svt), ("ent", ent)) if v})
    return r


def test_file_title_unquotes_a_p18_value():
    assert wiki.file_title("http://commons.wikimedia.org/wiki/Special:FilePath/Klara%20Folkskola.jpg") == "Klara Folkskola.jpg"
    assert wiki.file_title("Special:FilePath/A_b%C3%A5t.JPG") == "A båt.JPG"


def test_items_keep_buildings_only_and_place_the_best_one_per_footprint():
    b = synth.buildings(rows=[{"geometry": synth.square(0, 0, 30)}, {"geometry": synth.square(100, 0, 30)},
                              {"geometry": synth.square(200, 0, 30)}])
    rows_a = [a_row("Q10", 0, 0, CHURCH, img="Kyrka.jpg"), a_row("Q11", 2, 2, BUILDING),     # two items on gid 0
              a_row("Q12", 100, 0, MUSEUM, img="Museum.jpg"),                                # an organisation: never
              a_row("Q13", 118, 0, FOUNTAIN, img="Fontän.jpg"),                              # a fountain beside gid 1
              a_row("Q14", 200, 0, BUILDING, ended=True),                                    # demolished (P576)
              a_row("Q15", 225, 0, BUILDING), a_row("Q16", 400, 0, BUILDING)]               # 10 m off gid 2; far
    rows_b = [b_row("Q10", sv="Kyrkan", svt="Kyrkan (Stockholm)", nsl=3), b_row("Q11", sv="Huset", nsl=9),
              b_row("Q15", sv="Annexet", nsl=1)]
    items = wiki.items_from(rows_a, rows_b)
    assert items.qid.tolist() == ["Q10", "Q11", "Q12", "Q13", "Q14", "Q15", "Q16"]
    assert items.images[0] == ["Kyrka.jpg"] and items.wp_sv[0] == "Kyrkan (Stockholm)" and items.nsl[1] == 9
    kept = wiki.building_items(items, ANC)
    assert kept.qid.tolist() == ["Q10", "Q11", "Q15", "Q16"]
    placed = wiki.place(b, kept)
    assert dict(zip(placed.qid, placed.gid)) == {"Q10": 0, "Q11": 0, "Q15": 2}
    assert dict(zip(placed.qid, placed.placement)) == {"Q10": "inside", "Q11": "inside", "Q15": "nearest"}
    best = wiki.best(placed)
    # gid 0: the item with an article wins over the one with more sitelinks; `items` counts both
    assert best.qid.to_dict() == {0: "Q10", 2: "Q15"} and best["items"].to_dict() == {0: 2, 2: 1}
    assert wiki.best(placed.iloc[:0]).empty


def test_without_an_article_the_most_sitelinks_then_the_lowest_q_number_wins():
    b = synth.buildings(rows=[{"geometry": synth.square(0, 0, 30)}])
    items = wiki.items_from([a_row("Q9", 0, 0), a_row("Q100", 1, 1), a_row("Q7", 2, 2)],
                            [b_row("Q9", nsl=2), b_row("Q100", nsl=5), b_row("Q7", nsl=5)])
    assert wiki.best(wiki.place(b, wiki.building_items(items, ANC))).qid.tolist() == ["Q7"]


@pytest.mark.parametrize(("label", "name"), [("Kyrkan", "Kyrkan"), ("Hornsgatan 12", ""), ("Styckjunkaren 7", ""),
                                             ("Bostadshus", ""), ("Sätra", ""), ("Kv Storken 12", ""), ("", "")])
def test_card_name_takes_a_label_only_when_it_is_a_name(label, name):
    assert wiki.card_name(label, {"sätra"}) == name


def page(sha1="ab" * 20, **meta):
    m = {"License": "cc-by-sa-4.0", "LicenseShortName": "CC BY-SA 4.0", "Artist": '<a href="//x">Ann Foto</a>',
         "LicenseUrl": "https://creativecommons.org/licenses/by-sa/4.0", "ObjectName": "Kyrkan 2012"}
    m.update(meta)
    return {"title": "File:Kyrka.jpg", "imageinfo": [{
        "sha1": sha1, "thumburl": "https://upload.wikimedia.org/x/500px-Kyrka.jpg?utm_source=x", "thumbwidth": 500,
        "thumbheight": 375, "descriptionshorturl": "https://commons.wikimedia.org/w/index.php?curid=42",
        "extmetadata": {k: {"value": v} for k, v in m.items() if v is not None}}]}


def test_credit_for_an_open_licence():
    e, why = wiki.credit("Kyrka.jpg", page())
    assert why == "" and e == {"key": "abababababababab-500.jpg", "w": 500, "h": 375, "by": "Ann Foto",
                               "lic": "CC BY-SA 4.0", "lu": "https://creativecommons.org/licenses/by-sa/4.0",
                               "page": "https://commons.wikimedia.org/w/index.php?curid=42",
                               "thumb": "https://upload.wikimedia.org/x/500px-Kyrka.jpg", "file": "Kyrka.jpg"}
    e, _ = wiki.credit("Kyrka.jpg", page(License="cc-by-3.0", LicenseShortName="CC BY 3.0"))
    assert e["lic"] == "CC BY 3.0" and e["title"] == "Kyrkan 2012"           # CC 2.0–3.0: the work's title too
    e, _ = wiki.credit("Kyrka.jpg", page(License="cc-by-2.5-se", LicenseShortName="CC BY 2.5 se"))
    assert e["lic"] == "CC BY 2.5 SE"


def test_a_photo_key_names_the_thumbnail_width(monkeypatch):
    # the final review of Plan 4a: without the width, a wider thumb_width kept serving the old files, which the site
    # serves as immutable
    monkeypatch.setitem(wiki.city.WIKI, "thumb_width", 800)
    assert wiki.credit("Kyrka.jpg", page())[0]["key"] == "abababababababab-800.jpg"


def test_credit_links_a_creative_commons_licence_over_https():
    # Commons writes some licence links as http:// (28 of the city's photos on 2026-10-16); s99 requires https, and
    # creativecommons.org serves the same page there. Another host is left as written, for s99 to judge.
    e, _ = wiki.credit("Kyrka.jpg", page(License="cc0", LicenseShortName="CC0",
                                         LicenseUrl="http://creativecommons.org/publicdomain/zero/1.0/deed.en"))
    assert e["lu"] == "https://creativecommons.org/publicdomain/zero/1.0/deed.en"
    e, _ = wiki.credit("Kyrka.jpg", page(LicenseUrl="http://example.org/licence"))
    assert e["lu"] == "http://example.org/licence"


@pytest.mark.parametrize(("meta", "lic", "by"), [
    ({"License": "pd", "LicenseShortName": "Public domain", "Artist": ""}, "Public domain", "unknown"),
    ({"License": "pd", "LicenseShortName": "Public domain", "Categories": "Gamla stan|PD Sweden"},
     "Public domain (Sweden)", "Ann Foto"),                       # a simple photograph from before 1969: free here
    ({"License": "cc0", "LicenseShortName": "CC0", "Artist": "Okänd"}, "CC0", "unknown"),
    ({"Artist": "No machine-readable author provided. Holger~commonswiki assumed (based on copyright claims)."},
     "CC BY-SA 4.0", "Holger~commonswiki"),
    ({"Attribution": "Foto: Stadsmuseet / Ann Foto"}, "CC BY-SA 4.0", "Foto: Stadsmuseet / Ann Foto"),
])
def test_credit_names_who_the_licence_asks_for(meta, lic, by):
    e, why = wiki.credit("Kyrka.jpg", page(**meta))
    assert why == "" and (e["lic"], e["by"]) == (lic, by)


@pytest.mark.parametrize(("meta", "why"), [
    ({"License": "cc-by-nc-sa-4.0", "LicenseShortName": "CC BY-NC-SA 4.0"}, "licence CC BY-NC-SA 4.0"),
    ({"License": "cc-by-nd-3.0", "LicenseShortName": "CC BY-ND 3.0"}, "licence CC BY-ND 3.0"),
    ({"License": "gfdl", "LicenseShortName": "GFDL"}, "licence GFDL"),
    ({"Restrictions": "personality"}, "restrictions"),
    ({"Artist": "unknown"}, "no author"),
    ({"License": "cc-by-3.0", "LicenseShortName": "CC BY 3.0", "ObjectName": "Styckjunkaren 7, Stockholm"},
     "designation"),
])
def test_credit_refuses_what_d16_and_the_privacy_rule_refuse(meta, why):
    assert wiki.credit("Kyrka.jpg", page(**meta), {"styckjunkaren 7"}) == (None, why)


def test_credit_refuses_a_missing_file_a_denied_one_and_one_without_a_page(monkeypatch):
    assert wiki.credit("X.jpg", {"title": "File:X.jpg", "missing": True}) == (None, "missing")
    monkeypatch.setattr(city, "PHOTO_DENY", {"Kyrka.jpg"})
    assert wiki.credit("Kyrka.jpg", page()) == (None, "deny list")
    monkeypatch.setattr(city, "PHOTO_DENY", set())
    p = page()
    p["imageinfo"][0]["descriptionshorturl"] = "https://commons.wikimedia.org/wiki/File:Kyrka.jpg"
    assert wiki.credit("Kyrka.jpg", p) == (None, "no file page")       # the file name (often a designation) never ships
    p = page(sha1="nope")
    assert wiki.credit("Kyrka.jpg", p) == (None, "no thumbnail")
    p = page()
    p["imageinfo"][0].pop("thumburl")
    p["imageinfo"][0]["url"] = "https://upload.wikimedia.org/x/Kyrka.jpg"     # the original: maybe hundreds of MB
    assert wiki.credit("Kyrka.jpg", p) == (None, "no thumbnail")


def test_art_flag_reads_title_description_and_categories():
    assert wiki.art_flag(page(Categories="Sculptures in Årsta|Built in 1953"))
    assert wiki.art_flag(page(ImageDescription="Byst av en skådespelerska"))
    assert not wiki.art_flag(page(Categories="Churches in Stockholm|Wiki Loves Monuments 2012 in Sweden"))


def test_pages_by_file_follows_normalised_titles():
    answer = {"query": {"normalized": [{"from": "File:Kyrka_1.jpg", "to": "File:Kyrka 1.jpg"}],
                        "pages": [{"title": "File:Kyrka 1.jpg", "imageinfo": [{}]}, {"title": "File:B.jpg", "missing": True}]}}
    assert set(wiki.pages_by_file(answer)) == {"Kyrka 1.jpg", "B.jpg"}


def test_extract_pages_map_redirects_back_to_the_asked_title():
    answer = {"query": {"normalized": [{"from": "a_b", "to": "A b"}], "redirects": [{"from": "A b", "to": "C"}],
                        "pages": [{"title": "C", "extract": " Text. ", "lastrevid": 7}, {"title": "D", "missing": True}]}}
    assert wiki.extract_pages(answer) == {"a_b": {"text": "Text.", "title": "C", "rev": 7}}


def test_cut_keeps_whole_sentences_of_the_first_paragraph():
    text = "Första meningen är här. Andra meningen kommer sedan! Tredje? Nej.\nAndra stycket."
    assert wiki.cut(text, 59) == "Första meningen är här. Andra meningen kommer sedan!"      # 52 characters
    assert wiki.cut(text, 60) == "Första meningen är här. Andra meningen kommer sedan! Tredje?"   # 60
    assert wiki.cut(text, 500) == "Första meningen är här. Andra meningen kommer sedan! Tredje? Nej."
    long = "Ett " + "mycket " * 100 + "långt slut."
    out = wiki.cut(long, 50)
    assert out.endswith("…") and len(out) <= 50 and not out[:-1].endswith(" ")
    assert wiki.cut("", 50) == "" and wiki.cut("Kort.", 50) == "Kort."


def test_cut_leaves_out_sentences_that_name_a_property_designation():
    d = {privacy.normalise("STYCKJUNKAREN 7")}
    text = ("Styckjunkaren 7 är en kontorsfastighet vid Birger Jarlsgatan 14. Byggnaden stod färdig år 1900. "
            "Den ritades av Ludvig Peterson.")
    assert wiki.cut(text, 500, d) == "Byggnaden stod färdig år 1900. Den ritades av Ludvig Peterson."
    assert wiki.cut("Styckjunkaren 7 är en fastighet.", 500, d) == ""


def test_cut_leaves_out_sentences_that_name_an_owner_or_a_byggherre():
    # spec §6.3: no owner or byggherre names in web data; About says the map never shows who owns or commissioned a
    # building. Whoever the sentence names (a person, a firm, the state), it goes.
    text = ("Hellstrandska huset är ett bostadshus på Södermalm. Byggherre var ingenjör Hellstrand. Huset uppfördes "
            "1903 för kassör Carl Cederborg. Det ägs av AB Stadsholmen. Fasaden är av tegel.")
    assert wiki.cut(text, 500) == "Hellstrandska huset är ett bostadshus på Södermalm. Fasaden är av tegel."
    assert wiki.cut("The palace was built for the merchant Jan Doe. It is owned by the state. It has 600 rooms.",
                    500) == "It has 600 rooms."
    assert wiki.cut("Nobelfesten äger rum i huset. Huset byggdes för att rymma banken.", 500) == (
        "Nobelfesten äger rum i huset. Huset byggdes för att rymma banken.")       # "takes place", "in order to"
    for owner in ("Beställare var läkaren X.", "Fastigheten såldes 2014 till regissören Y.", "Z lät bygga huset.",
                  "Huset ägdes av släkten W.", "Kronan förvärvades av staten 1930."):
        assert privacy.owner(owner), owner


def test_cut_leaves_out_the_pronunciation_and_footnote_marks():
    text = ("Storkyrkan (Swedish: [ˈstûːrˌɕʏrkan], lit. 'The Great Church'), officially Sankt Nikolai kyrka, is the "
            "oldest church in Gamla stan. Södra Bankohuset (Swedish: \"The Southern Bank Building\"[1]) is a building.")
    assert wiki.cut(text, 500) == ("Storkyrkan, officially Sankt Nikolai kyrka, is the oldest church in Gamla stan. "
                                   "Södra Bankohuset (Swedish: \"The Southern Bank Building\") is a building.")


@pytest.mark.parametrize(("text", "found"), [
    ("Styckjunkaren 7 är en fastighet", True), ("i kvarteret Styckjunkaren 7", True), ("Huset Styckjunkaren 7", True),
    ("kv. Styckjunkaren 7", True), ("STYCKJUNKAREN 7", True), ("Styckjunkaren 70", False),
    ("Styckjunkaren 7:1", False), ("Styckjunkaren", False), ("byggt 1907", False), ("", False),
])
def test_privacy_mentions_finds_a_designation_inside_a_sentence(text, found):
    assert privacy.mentions(text, {"styckjunkaren 7"}) is found
    assert privacy.mentions(text, set()) is False


@pytest.mark.parametrize(("text", "found"), [
    ("Styckjunkaren7", True), ("Styckjunkaren7.JPG", True), ("Huset Styckjunkaren7 i snö", True),
    ("Styckjunkaren70", False), ("G4S Styckjunkaren", False),
    ("Styckjunkaren 7b", True), ("Styckjunkaren7b.jpg", True), ("Styckjunkaren 70b", False),
    ("Styckjunkaren6-8", True), ("Styckjunkaren-7", True), ("Styckjunkaren_7", True), ("Styckjunkaren 7:1b", False),
    ("Styckjunkaren 6-8b", True), ("Styckjunkaren 5 & 7b", True),
])
def test_privacy_mentions_finds_a_designation_written_without_its_space(text, found):
    # Commons titles of 2026-10-17 shipped "Bryggaren16", "Överkikaren2" and "Glaucus5b": the number joined to the
    # block name, or a photo's letter after it (Task 13 and its review)
    assert privacy.mentions(text, {"styckjunkaren 7"}) is found


# ---------- Task 6's review: initials, more owner wordings, several numbers, the file page, unknown authors ----------

def test_cut_does_not_split_at_initials_or_abbreviations():
    # split after "C." the owner sentence went and "A. Exempel." shipped as a sentence of its own
    assert wiki.cut("Villan är ett bostadshus. Byggherre var grosshandlare C. A. Exempel. Fasaden är av tegel.",
                    500) == "Villan är ett bostadshus. Fasaden är av tegel."
    assert wiki.cut("The house was built for Mr. John Exempel. It has a tower.", 500) == "It has a tower."
    kv = "Huset ligger i kv. Exemplet. Det byggdes 1900."
    assert wiki.cut(kv, 500) == kv
    assert wiki.cut("Kyrkan byggdes på 1600-talet. Tornet är från 1700-talet.", 500) == (
        "Kyrkan byggdes på 1600-talet. Tornet är från 1700-talet.")


@pytest.mark.parametrize("text", [
    "Huset uppfördes åt grosshandlare Exempel.", "Villan byggdes åt familjen Exempel.",
    "Byggnaden beställdes av bolaget Exempel.", "Huset ritades på uppdrag av X.", "Familjen ägde huset till 1950.",
    "Villan är ägd av X.", "X köpte huset 1920.", "Huset köptes 1990 av X.", "Kommunen förvärvade huset.",
    "Huset tillhör X.", "X lät 1905 uppföra villan.", "It was owned until 1990 by X.", "The city owns it.",
    "X bought the house.", "X had the house built in 1905.", "X commissioned the house.",
    "It was built in 1905 for X.", "It was built by Y for his family.", "It belongs to X.", "It was the home of X.",
])
def test_owner_finds_more_wordings(text):
    assert privacy.owner(text), text


# The final review of Plan 4a: "ägare" inside a compound or in the plural, "samägs", and a family that "disponerar" a
# house; sentences of these shapes shipped in the build of 2026-10-17 (names here are made up)
@pytest.mark.parametrize("text", [
    "En av fastighetsägarna var mångmiljonären X.", "Huset är uppkallat efter en av ägarna, assessorn X.",
    "Bland ägarna fanns X och Y.", "Det uppfördes av byggmästaren och fastighetsägaren X.",
    "Fastighetsägaren är AB Exempel.", "Fastighetsägare är Exempelbolaget.", "Den nya fastighetsägaren X rev huset.",
    "Fastigheten samägs av föreningen X och klubben Y.", "Aktieägarna i X sålde huset.",
    "Efter flera ägarbyten tog X över.", "Huset delägdes av X.", "Villan disponeras av familjen X.",
    "Släkten X har disponerat villan sedan 1900.", "Huset är helägt av X.", "Familjen har ägt huset.",
    # the fix wave's review: the passive and infinitive, "i X:s ägo", and a compound after a "b"
    "Huset har ägts av familjen X sedan 1900.", "Huset kommer att ägas av X.", "Huset är i familjen X:s ägo.",
    "Huset kom i X:s ägo 1920.", "Klubbägaren X byggde om huset.", "Pubägaren X driver krogen.",
])
def test_owner_finds_compounds_plurals_and_a_family_that_has_the_use(text):
    assert privacy.owner(text), text


@pytest.mark.parametrize("text", [
    "Vägarna runt huset breddades.", "Jägarna samlades vid stugan.", "Halvvägs upp ligger kyrkan.",
    "Det sägs att huset är det äldsta.", "Det sades att tornet vägde mycket.", "Huset har sagts vara det äldsta.",
    "Idag disponeras byggnaden av hotellet X.", "Sedan 2010 disponerar varuhuset X tre våningar.",
    "Ett läger byggdes vid sjön.", "Han sägs ha bott här.", "Museet är ett stiftelseägt museum.",
    "Utställningen är privatägd.",
    # the fix wave's review: forms of "säga" inside a word, and "äga rum" in every tense
    "Detta motsägs av senare forskning.", "Det förutsägs bli varmt.", "Han motsägde rapporten.",
    "Invigningen ägde rum 1900.", "Mötet har ägt rum här.", "Konserter ägs rum i salen.", "Bägaren står i museet.",
    "Motorvägarna går förbi.", "Järnvägarna byggdes ut.",
])
def test_owner_leaves_roads_hunters_sayings_and_tenants(text):
    # the review: a hotel, an embassy or a department store "disponerar" a building as its tenant, not its owner
    assert not privacy.owner(text), text


@pytest.mark.parametrize(("text", "found"), [
    ("Styckjunkaren 6 och 7 är två fastigheter", True), ("Styckjunkaren 5–7", True), ("Styckjunkaren 6, 7", True),
    ("Styckjunkaren 6 och 8", False), ("Styckjunkaren 1–5", False),
])
def test_mentions_reads_every_number_after_a_block_name(text, found):
    assert privacy.mentions(text, {"styckjunkaren 7"}) is found


def test_phrases_is_fast_on_long_runs_of_spaces():
    assert privacy.phrases("A" + " " * 100_000 + "1") == ["a 1"]


def test_credit_needs_a_bare_page_id_and_a_known_author(monkeypatch):
    p = page()
    p["imageinfo"][0]["descriptionshorturl"] += "&title=File:Styckjunkaren_7.jpg"
    assert wiki.credit("Kyrka.jpg", p) == (None, "no file page")
    for who in ("Okänd fotograf", "Unknown photographer", "anonym", "Okänd upphovsman"):
        assert wiki.credit("Kyrka.jpg", page(Artist=who)) == (None, "no author"), who
    e, why = wiki.credit("Kyrka.jpg", page(Attribution="Foto: https://x.org/File:Styckjunkaren_7_x.jpg"),
                         {"styckjunkaren 7"})
    assert (e, why) == (None, "designation")


def test_cut_leaves_out_slashed_pronunciations_and_lettered_footnotes():
    assert wiki.cut("Exempelhuset (/ˈɛksɛmpɛl/) is a building.[a] It has a tower.[note 1]", 500) == (
        "Exempelhuset is a building. It has a tower.")
