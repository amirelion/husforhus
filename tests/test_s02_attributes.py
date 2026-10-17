"""Floors, rating, architects and safe names."""
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline import city, report_kategori, s02_attributes, s02_years
from pipeline.codes import FLOORS_HEIGHT, FLOORS_OSM, PROT_CHURCH, PROT_LISTED, PROT_STATE
from tests.realdata import ensure_city_data

REAL_UPPHOV = ('"Peterson,Ludvig:Arkitekt"; "Kumlien,Axel:Arkitekt"; "Palme,Johan Henrik:Byggherre"; '
               '"Schonberg,Johan Peter:Byggmästare"; "Zettervall,Helgo:Arkitekt"')
DISTRICTS = {"sätra", "gamla stan"}
STOREY_M = {"Flerbostadshus": 4.1, "Kontorsbyggnad": 4.5, "Allmän byggnad": 5.1, "Kolonistuga": 3.0, "_default": 3.6}


@pytest.fixture(autouse=True)
def pinned_storey_heights(request, monkeypatch):
    """Rule tests pin STOREY_M to placeholder values, so they hold whatever city.py settles on."""
    if request.node.get_closest_marker("network") is None:
        monkeypatch.setattr(city, "STOREY_M", STOREY_M)


def test_floors_from_height_by_kategori():
    height = [12.3, 25.5, 2.9, 9.0, 7.1, 0.5, 500.0]
    kategori = ["Flerbostadshus", "Allmän byggnad", "Kolonistuga", "Enbostadshus", "Komplementbyggnad",
                "Enbostadshus", "Flerbostadshus"]
    floors = s02_attributes.floors_from_height(height, kategori)
    assert floors.dtype == np.uint8
    # 12.3/4.1 = 3; 25.5/5.1 = 5; 2.9/3.0 -> 1; 9.0/3.6 = 2.5 rounds half up to 3; 7.1/3.6 -> 2;
    # 0.5 m clamps to 1; 500 m clamps to 99
    assert floors.tolist() == [3, 5, 1, 3, 2, 1, 99]


def test_floors_round_half_up_on_float32_heights(monkeypatch):
    """buildings.parquet stores height as float32; ties (x.5 storeys) round up, never to even."""
    monkeypatch.setitem(city.STOREY_M, "Flerbostadshus", 4.0)
    height = np.array([10.0, 14.0, 6.0], dtype=np.float32)        # 2.5, 3.5, 1.5 storeys
    kategori = ["Flerbostadshus"] * 3
    assert s02_attributes.floors_from_height(height, kategori).tolist() == [3, 4, 2]
    # report_kategori's floors table shares the rule: one source of truth.
    k = report_kategori.storey_k(pd.Series(kategori))
    assert report_kategori.floors(pd.Series(height), k).tolist() == [3, 4, 2]
    assert s02_attributes.floors_from_storey(height, k).tolist() == [3, 4, 2]


def test_report_kategori_follows_floors_from_height(monkeypatch):
    """The KATEGORI report and s02_attributes give the same floors for every height and storey height."""
    monkeypatch.setitem(city.STOREY_M, "Flerbostadshus", 4.0)
    rng = np.random.default_rng(7)
    height = rng.uniform(0.2, 140.0, 500).astype(np.float32)
    kategori = rng.choice(["Flerbostadshus", "Allmän byggnad", "Kolonistuga", "Okänd typ"], 500)
    report = report_kategori.floors(pd.Series(height), report_kategori.storey_k(pd.Series(kategori)))
    assert report.tolist() == s02_attributes.floors_from_height(height, kategori).tolist()


def test_upphov_keeps_only_architects_in_order():
    assert s02_attributes.parse_architects(REAL_UPPHOV) == ["Ludvig Peterson", "Axel Kumlien", "Helgo Zettervall"]


@pytest.mark.parametrize(("upphov", "expected"), [
    ('"Westman,Carl:Arkitekt"; "Westman,Carl:Arkitekt"', ["Carl Westman"]),
    ('"Hagström & Ekman:Arkitekt"; "AB Svenska Bostäder:Byggherre"', ["Hagström & Ekman"]),
    ('"S Ancker, B Gate, S Lindegren:Arkitekt"', ["S Ancker, B Gate, S Lindegren"]),
    ('"Nils G:son Friberg Ernst Haverman arkitekter SAR:Arkitekt"',
     ["Nils G:son Friberg Ernst Haverman arkitekter SAR"]),
    ('"Martinsson,Gunnar:Landskapsarkitekt"; "Kempe,H.:Inredningsarkitekt"', []),
    ('"Johansson; Isidor:Byggherre"; "Lewerentz,Sigurd:Arkitekt"', ["Sigurd Lewerentz"]),
    ('"Okänd,:Arkitekt"; "Osignerad,:Arkitekt"; "Åbergh,Gösta:Arkitekt"', ["Gösta Åbergh"]),
    # Only the compact "Surname,First" (one comma, nothing after it) is flipped; a comma followed by a space
    # belongs to a firm name or a two-person list and stays as written.
    ('"Engström,Edvin:Arkitekt"', ["Edvin Engström"]),
    ('"Ancker Gate Lindegren, Arkitekter SAR:Arkitekt"', ["Ancker Gate Lindegren, Arkitekter SAR"]),
    ('"AB Stockholms spårvägar, ban- och byggnadsavdelningen:Arkitekt"',
     ["AB Stockholms spårvägar, ban- och byggnadsavdelningen"]),
    ('"Arndt, Malmquist & Skoogh Arkitektkontor AB:Arkitekt"', ["Arndt, Malmquist & Skoogh Arkitektkontor AB"]),
    ('"G Wejke, K Ödeen Arkitekter SAR:Arkitekt"', ["G Wejke, K Ödeen Arkitekter SAR"]),
    ('"ETH Maskin AB, Värnamo:Arkitekt"', ["ETH Maskin AB, Värnamo"]),
    ('"Tore Forsman, Ulf Snellman  Arkitekter SAR:Arkitekt"', ["Tore Forsman, Ulf Snellman Arkitekter SAR"]),
    ('"Ancker Gate, Arkitekter SAR:Arkitekt"', ["Ancker Gate, Arkitekter SAR"]),
    ('"Åbergh ,  Gösta:Arkitekt"', ["Åbergh, Gösta"]),
    ('"Palme,Johan Henrik:Byggherre"', []),
    ("", []),
    (None, []),
    (float("nan"), []),
])
def test_upphov_edge_cases(upphov, expected):
    assert s02_attributes.parse_architects(upphov) == expected


@pytest.mark.parametrize(("name", "expected"), [
    ("Kv Storken 12", ""),
    ("Kv. Bacchus 6", ""),
    ("kv konsthallen 14", ""),
    ("Cepheus 25", ""),
    ("Brunkhuvudet 4:2", ""),
    ("Sätra", ""),
    ("SÄTRA", ""),
    ("Stockholms stadsbibliotek", "Stockholms stadsbibliotek"),
    ("Vagnhall nr 1 (Dubbelhallen)", "Vagnhall nr 1 (Dubbelhallen)"),
    ("  Palmeska   huset ", "Palmeska huset"),
    ("", ""),
    (None, ""),
    # Multi-word designations, "kv." without a space, a dash; names that only say what kind of building
    ("Lilla Sticklinge 1:4", ""),
    ("Norra Djurgården 1:48", ""),
    ("kv.Storken 12", ""),
    ("Storken-12", ""),
    ("Storken – 12", ""),
    ("Bostadshus", ""),
    ("STALL", ""),
    ("Norra flygeln", ""),
    ("_", ""),
    ("Tyska kyrkan", "Tyska kyrkan"),
    ("Södra flygeln vid slottet", "Södra flygeln vid slottet"),
    ("Kv. Bacchus", ""),                     # a block's name (2 in RAÄ's names today): block names stay out of v1
    ("Kvarteret Svalan", ""),
    ("Kvarnen", "Kvarnen"),
    # A name that is only a register's building codes (a state-listed building's numbers)
    ("K0061.006, K0061.005, K0061.004", ""),
    ("K0061.003", ""),
    ("Kanslikasern (K0061.001)", "Kanslikasern"),
    ("Militärrestaurangen  (K0061.003) ", "Militärrestaurangen"),
    ("K0062.008; Vagnshuset", "Vagnshuset"),
    ("Granhammars herrgård (K0101.722 )", "Granhammars herrgård"),
])
def test_safe_name(name, expected):
    assert s02_attributes.safe_name(name, DISTRICTS) == expected


def test_build_attributes_joins_through_raa_id():
    b = pd.DataFrame({"gid": [0, 1, 2, 3, 4, 5], "kategori": ["Flerbostadshus"] * 6,
                      "height": [12.3, 8.2, 8.2, 8.2, 8.2, 8.2]})
    years = pd.DataFrame({"gid": [0, 1, 2, 3, 4, 5], "raa_id": ["a", "b", "c", "d", "", "f"],
                          "landmark": ["", "", "", "Stockholms stadsbibliotek", "", ""]})
    raa = pd.DataFrame({
        "raa_id": ["a", "b", "c", "d", "f"],
        "klassificering": ["Blått", "Grönt", "Gult", "Blått", "Rött"],
        "upphov": [REAL_UPPHOV, None, '"Asplund,Gunnar:Arkitekt"', '"Asplund,Gunnar:Arkitekt"', ""],
        "namn": ["Palmeska huset", "Kv Storken 12", "Sätra", "Stadsbiblioteket", None],
        "alternativnamn": [None, "Gamla Kungshuset", None, None, None],
    })
    a = s02_attributes.build_attributes(b, years, raa, DISTRICTS).set_index("gid")
    assert a.rating.tolist() == [1, 2, 3, 1, 0, 0]
    assert a.architects[0] == ["Ludvig Peterson", "Axel Kumlien", "Helgo Zettervall"]
    assert a.architects[1] == [] and a.architects[4] == []
    assert a.name.tolist() == ["Palmeska huset", "Gamla Kungshuset", "", "Stockholms stadsbibliotek", "", ""]
    assert a.floors.tolist() == [3, 2, 2, 2, 2, 2]
    assert (a.fsrc == FLOORS_HEIGHT).all()


def test_output_matches_contract_c3():
    b = pd.DataFrame({"gid": [0], "kategori": ["Kolonistuga"], "height": [3.0]})
    years = pd.DataFrame({"gid": [0], "raa_id": [""], "landmark": [""]})
    raa = pd.DataFrame({"raa_id": ["x"], "klassificering": [None], "upphov": [None], "namn": [None],
                        "alternativnamn": [None]})
    a = s02_attributes.build_attributes(b, years, raa, set())
    # The attributes frame: the OSM and height floors kept apart, protection, its year, the floors-row rule
    assert list(a.columns) == ["gid", "floors", "fsrc", "rating", "architects", "name", "floors_h", "floors_osm",
                               "prot", "since", "nofloors"]
    assert [str(t) for t in a.dtypes[:4]] == ["int32", "uint8", "uint8", "uint8"]
    assert [str(t) for t in a.dtypes[6:]] == ["uint8", "uint8", "uint8", "int16", "bool"]
    assert a.architects.tolist() == [[]] and a.name.tolist() == [""]
    assert (a.floors_osm.tolist(), a.prot.tolist(), a.since.tolist(), a.nofloors.tolist()) == ([0], [0], [0], [False])


def test_floors_come_from_osm_where_matched_and_stay_separable():
    b = pd.DataFrame({"gid": [0, 1, 2, 3], "kategori": ["Flerbostadshus", "Flerbostadshus", "Allmän byggnad",
                                                        "Vattentorn"], "height": [20.5, 20.5, 25.5, 30.0]})
    years = pd.DataFrame({"gid": [0, 1, 2, 3], "raa_id": ["", "", "k", ""], "landmark": ["", "", "", ""]})
    raa = pd.DataFrame({"raa_id": ["k"], "klassificering": [None], "upphov": [None], "namn": [None],
                        "alternativnamn": [None], "andamal_huvudgrupp": ["Religionsutövning"],
                        "skyddstyp_namn": ["Kyrkligt kulturminne"], "beslutsdatum": [None]})
    levels = pd.Series([7, 4], index=pd.Index([1, 2], name="gid"), dtype="uint8")
    a = s02_attributes.build_attributes(b, years, raa, set(), levels).set_index("gid")
    assert a.floors_h.tolist() == [5, 5, 5, 8]                    # 20.5/4.1, 25.5/5.1, 30/3.6 (the pinned table)
    assert a.floors_osm.tolist() == [0, 7, 4, 0]
    assert a.floors.tolist() == [5, 7, 4, 8]
    assert a.fsrc.tolist() == [FLOORS_HEIGHT, FLOORS_OSM, FLOORS_OSM, FLOORS_HEIGHT]
    # a church whose floors OSM gives keeps its row; a water tower with floors from its height does not
    assert a.nofloors.tolist() == [False, False, False, True]
    assert a.prot.tolist() == [0, 0, PROT_CHURCH, 0]


@pytest.mark.parametrize(("skydd", "date", "prot", "since"), [
    ("Statligt byggnadsminne", "1935-05-17", PROT_STATE, 1935),
    ("Byggnadsminne", pd.Timestamp("1978-01-02"), PROT_LISTED, 1978),
    ("Byggnadsminne", None, PROT_LISTED, 0),                       # listed, no decision date: no "since"
    ("Kyrkligt kulturminne", "1990-01-01", PROT_CHURCH, 0),        # church heritage carries no decision year
    ("Identifierat kulturvärde", "2001-01-01", 0, 0),              # no legal force: no protection row
    (None, None, 0, 0),
])
def test_protection_and_the_year_it_was_decided(skydd, date, prot, since):
    b = pd.DataFrame({"gid": [0], "kategori": ["Flerbostadshus"], "height": [10.0]})
    years = pd.DataFrame({"gid": [0], "raa_id": ["r"], "landmark": [""]})
    raa = pd.DataFrame({"raa_id": ["r"], "klassificering": [None], "upphov": [None], "namn": [None],
                        "alternativnamn": [None], "andamal_huvudgrupp": ["Bostäder"], "skyddstyp_namn": [skydd],
                        "beslutsdatum": [date]})
    a = s02_attributes.build_attributes(b, years, raa, set())
    assert (int(a.prot[0]), int(a.since[0])) == (prot, since)


def test_main_needs_the_osm_levels_tiles(tmp_path):
    with pytest.raises(SystemExit, match="run s00_fetch_osm first"):
        s02_attributes.main(["--osm-levels", str(tmp_path / "none")])


def test_load_districts_reads_the_zip(tmp_path: Path):
    gdf = gpd.GeoDataFrame({"NAMN": ["SÄTRA", "GAMLA STAN"], "KATEGORI": ["Stadsdel", "Stadsdel"]},
                           geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=3011)
    gdf.to_file(tmp_path / "Stadsdel.shp", engine="pyogrio")
    with zipfile.ZipFile(tmp_path / "Stadsdelar.zip", "w") as z:
        for f in tmp_path.glob("Stadsdel.*"):
            z.write(f, f.name)
    assert s02_attributes.load_districts(tmp_path / "Stadsdelar.zip") == {"sätra", "gamla stan"}


@pytest.mark.network
def test_real_stockholm_attributes(tmp_path: Path):
    ensure_city_data([s02_years.RAA_GPKG, s02_years.BUILDINGS, s02_attributes.STADSDELAR,
                      s02_years.years_wikidata.DATED, s02_years.years_wikidata.CLASSES, s02_years.years_osm.DEST,
                      s02_years.LANDMARKS_JSON, s02_attributes.osm_buildings.LEVELS / "0_0.json"],
                     buildings=s02_years.BUILDINGS,
                     steps="s00_fetch_city s00_fetch_raa s00_fetch_raa_old s00_fetch_wikidata s00_fetch_osm s01_load "
                           "s08_landmarks")
    years = tmp_path / "years.parquet"
    out = tmp_path / "attributes.parquet"
    s02_years.main(["--out", str(years), "--accuracy-out", str(tmp_path / "accuracy.json"),
                    "--review-out", str(tmp_path / "review.json")])
    s02_attributes.main(["--years", str(years), "--out", str(out)])
    a = pd.read_parquet(out)
    # 2026-10-16 measurements: OSM levels on about a quarter of the city, protection from RAÄ
    assert 18_500 <= int((a.fsrc == FLOORS_OSM).sum()) <= 21_500     # 19,136 ways (relations add a few hundred)
    assert ((a.fsrc == FLOORS_OSM) == (a.floors_osm > 0)).all()
    assert (a.floors[a.fsrc == FLOORS_HEIGHT] == a.floors_h[a.fsrc == FLOORS_HEIGHT]).all()
    assert 300 <= int(a.prot.isin([PROT_STATE, PROT_LISTED]).sum()) <= 500   # listed buildings joined by raa_id
    assert (a.since[a.since > 0] >= 1900).all() and (a.since <= 2026).all()
    s = s02_attributes.summary(a)
    print(s)
    assert 1_100 <= s["rating"]["Blått"] <= 1_250       # observed 1,155
    assert 7_900 <= s["rating"]["Grönt"] <= 8_500       # observed 8,216
    assert 11_800 <= s["rating"]["Gult"] <= 12_600      # observed 12,216
    assert 19_000 <= s["with_architects"] <= 20_500     # observed 19,861
    assert 480 <= s["named"] <= 620                     # 539 after the 2026-10-16 rules (690 before: kinds, houses)
    pc = pd.read_parquet(s02_years.BUILDINGS, columns=["kategori"]).kategori.isin(city.PRIVATE_HOUSE_KATEGORI)
    allowed = s02_attributes.load_private_names()
    assert set(a.name[pc.to_numpy() & (a.name != "").to_numpy()]) <= allowed | {L["name"] for L in s02_years.load_landmarks()}
    counted = s02_attributes.arch.counts(a.architects)   # after the rule: a hidden name can only have lost buildings
    firms = s02_attributes.load_private_firms()
    assert not any(n not in firms and counted[n] <= city.ARCHITECT_MAX_RARE
                   for names in a.architects[pc.to_numpy()] for n in names)
    assert 1 <= a.floors.min() and a.floors.max() <= 60  # observed max 36 (OSM)
    names = a.name[a.name != ""]
    # Curated names are hand-checked and may be a street address ("Stora Nygatan 5", the curated Gamla stan houses),
    # which has a designation's shape; the check against the city's own designations below still covers them.
    curated = {L["name"] for L in s02_years.load_landmarks()}
    assert not names[~names.isin(curated)].str.match(s02_attributes.PROPERTY_DESIGNATION).any()
    districts = s02_attributes.load_districts()
    assert not names.str.casefold().isin(districts).any()
    fastighet = {f.casefold() for f in pd.read_parquet(s02_years.BUILDINGS, columns=["fastighet"]).fastighet if f}
    assert not {n.casefold() for n in names} & fastighet
    assert "Stockholms slott" in set(names)
    architects = {n for lst in a.architects for n in lst}
    assert not any(n.startswith("Arkitekter SAR") for n in architects)      # "Firm, Arkitekter SAR" is not flipped
    assert "Ancker Gate Lindegren, Arkitekter SAR" in architects             # observed on 217 buildings
    assert "Edvin Engström" in architects                                    # the compact "Engström,Edvin" is


def house_case():
    """Four buildings sharing names and architects: gid 0 and 1 private-category houses (gid 1 curated), gid 2 a block
    of flats, gid 3 an allotment cottage."""
    b = pd.DataFrame({"gid": [0, 1, 2, 3], "kategori": ["Enbostadshus", "Enbostadshus", "Flerbostadshus", "Kolonistuga"],
                      "height": [7.0, 7.0, 20.0, 3.0]})
    years = pd.DataFrame({"gid": [0, 1, 2, 3], "raa_id": ["a", "b", "c", "d"], "landmark": ["", "Villa Kurt", "", ""]})
    upphov = '"Rare,Ruth:Arkitekt"; "Byggare & Son:Arkitekt"; "Common,Carl:Arkitekt"'
    raa = pd.DataFrame({"raa_id": ["a", "b", "c", "d"], "klassificering": [None] * 4,
                        "upphov": [upphov, upphov, '"Common,Carl:Arkitekt"; "Common,Carl:Arkitekt"', '"Common,Carl:Arkitekt"'],
                        "namn": ["Sagatun", "Villa Kurt", "Bostadshus", "Villa Andersson"], "alternativnamn": [None] * 4})
    return b, years, raa


def test_private_houses_keep_common_names_and_reviewed_firms_only(monkeypatch):
    # "Ruth Rare" and "Byggare & Son" are on 2 buildings (gid 0 and 1), "Carl Common" on 4: with the rule
    # at 3 both rare names hide on the private house until a person has put the firm on private_firms.txt
    b, years, raa = house_case()
    report = {}
    a = s02_attributes.build_attributes(b, years, raa, set(), report=report).set_index("gid")
    assert a.architects[0] == ["Carl Common"]                           # private, not curated: the rare names go
    assert a.architects[1] == ["Ruth Rare", "Byggare & Son", "Carl Common"]   # curated: the rule does not apply
    assert a.architects[2] == ["Carl Common"] and a.architects[3] == ["Carl Common"]
    assert report["firms"] == ["Byggare & Son"]                         # it reads as a firm: for the hand check
    report = {}
    a = s02_attributes.build_attributes(b, years, raa, set(), report=report, private_firms={"Byggare & Son"})
    assert a.set_index("gid").architects[0] == ["Byggare & Son", "Carl Common"] and report["firms"] == []
    monkeypatch.setattr(city, "ARCHITECT_MAX_RARE", 1)
    assert s02_attributes.build_attributes(b, years, raa, set()).architects[0] == ["Ruth Rare", "Byggare & Son",
                                                                                   "Carl Common"]


def test_a_private_house_keeps_a_name_only_from_the_reviewed_list():
    b, years, raa = house_case()
    report = {}
    a = s02_attributes.build_attributes(b, years, raa, set(), report=report).set_index("gid")
    # the curated house keeps its landmark name; the flats' "Bostadshus" names a kind; the houses' names wait
    assert a.name.tolist() == ["", "Villa Kurt", "", ""]
    assert report["names"] == ["Sagatun", "Villa Andersson"]
    a = s02_attributes.build_attributes(b, years, raa, set(), private_names={"Sagatun"}).set_index("gid")
    assert a.name.tolist() == ["Sagatun", "Villa Kurt", "", ""]


def test_load_private_names_reads_one_name_per_line(tmp_path):
    p = tmp_path / "names.txt"
    p.write_text("# reviewed\nSagatun\n  Ektorpet   # a croft\n\n", encoding="utf-8")
    assert s02_attributes.load_private_names(p) == {"Sagatun", "Ektorpet"}
    assert s02_attributes.load_private_names(tmp_path / "none.txt") == set()
    assert s02_attributes.load_private_names() == set()     # the committed lists start empty until confirmed
    assert s02_attributes.load_private_firms() == set()     # (proposals go to data/review-*-proposed.txt)


@pytest.mark.parametrize(("value", "year"), [(1935, 0), (1935.0, 0), (True, 0), ("0001-01-01", 0), ("2999-01-01", 0),
                                             ("1935-05-17", 1935), (pd.Timestamp("2026-01-02"), 2026)])
def test_decision_year_reads_only_a_date_in_range(value, year):
    # Pd.Timestamp(1935) is 1970 (nanoseconds); a year outside 1900..2026 is no decision year
    assert s02_attributes.decision_year(value) == year


def test_main_needs_every_osm_levels_tile(tmp_path, monkeypatch):
    # One tile is not the city; a run with some tiles missing would quietly fall back to the height
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    (tmp_path / "0_0.json").write_text('{"elements": []}')
    with pytest.raises(SystemExit, match=r"lacks 15 of 16 tiles \(0_1, .*\): run s00_fetch_osm first"):
        s02_attributes.main(["--osm-levels", str(tmp_path)])


def test_main_reads_only_the_current_grids_osm_tiles(tmp_path, monkeypatch):
    # A tile left from another grid must not set floors (osm_buildings.load's names)
    monkeypatch.delenv("HFH_FIXTURE", raising=False)
    monkeypatch.setattr(s02_attributes, "missing_osm_tiles", lambda folder: [])
    monkeypatch.setattr(s02_attributes.pyogrio, "read_info", lambda path, layer=None: {"fields": s02_attributes.RAA_READS})
    monkeypatch.setattr(s02_attributes.gpd, "read_parquet", lambda path, columns=None: None)
    asked = []

    def load(folder, names=None):
        asked.append(names)
        raise SystemExit("loaded")
    monkeypatch.setattr(s02_attributes.osm_buildings, "load", load)
    with pytest.raises(SystemExit, match="loaded"):
        s02_attributes.main(["--osm-levels", str(tmp_path)])
    assert asked == [s02_attributes.osm_tiles_needed()] and len(asked[0]) == 16


def test_main_stops_when_raa_lacks_a_field_this_step_reads(tmp_path, monkeypatch):
    # Pyogrio skips a missing column without a word, so a renamed skyddstyp_namn would quietly give
    # every building prot 0; the step stops instead
    monkeypatch.setattr(s02_attributes, "missing_osm_tiles", lambda folder: [])
    gpkg = tmp_path / "raa.gpkg"
    rows = gpd.GeoDataFrame({"namn": ["x"], "klassificering": [None], "upphov": [None], "alternativnamn": [None],
                             "andamal_huvudgrupp": ["Bostäder"], "beslutsdatum": [None]},
                            geometry=[box(0, 0, 1, 1)], crs=3006)
    rows.to_file(gpkg, layer=s02_attributes.RAA_LAYER, driver="GPKG")
    with pytest.raises(SystemExit, match="lacks skyddstyp_namn"):
        s02_attributes.main(["--raa", str(gpkg), "--osm-levels", str(tmp_path)])


def test_the_rare_rule_counts_raa_records_not_footprints():
    # One villa in four LOD1 footprints, all linked to one RAÄ record, is one building
    b = pd.DataFrame({"gid": [0, 1, 2, 3], "kategori": ["Enbostadshus"] * 4, "height": [7.0] * 4})
    years = pd.DataFrame({"gid": [0, 1, 2, 3], "raa_id": ["a"] * 4, "landmark": [""] * 4})
    raa = pd.DataFrame({"raa_id": ["a"], "klassificering": [None], "upphov": ['"Owner,Olle:Arkitekt"'],
                        "namn": [None], "alternativnamn": [None]})
    assert s02_attributes.build_attributes(b, years, raa, set()).architects.tolist() == [[], [], [], []]
