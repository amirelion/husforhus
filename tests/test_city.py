# tests/test_city.py
"""pipeline.city and the periods re-export."""
import re
from pathlib import Path

import numpy as np
from pyproj import Transformer

from pipeline import city, periods


def test_identity():
    assert city.SLUG == "stockholm"
    assert city.NAME == "Hus för hus"
    assert city.SUBTITLE == {"en": "Stockholm, building by building", "sv": "Stockholm, hus för hus"}
    assert city.CRS == 3011
    assert city.ORIGIN == (154025.1, 6578886.7)
    assert city.KOMMUN == "0180"
    assert city.WIKIDATA == "Q506250"
    assert city.N_PACKS == 8 and city.SIMPLIFY == 0.25
    # 1200 m, measured 2026-10-15. scripts/compare-tiles.sh rewrites TILE for its side builds and restores it in an EXIT trap;
    # if that trap never runs, this fails instead of the next full build quietly using 1500 m.
    assert city.TILE == 1200.0
    assert set(city.HOME) == {"x", "z", "azimuth", "elevation", "span"}
    assert city.FEATURES == {"quests": False, "layers": False, "energy": False, "lang": True, "search": True, "scenes": True}
    assert "_default" in city.STOREY_M
    assert isinstance(city.TIER1, list)
    assert len(city.SALTSJON) == 3


def test_periods_are_twelve_contiguous_from_1000_to_2100():
    assert len(city.PERIODS) == 12
    assert [p[0] for p in city.PERIODS] == [f"p{i}" for i in range(1, 13)]
    assert city.PERIODS[0][3] == 1000 and city.PERIODS[-1][4] == 2100
    for (_, _, _, _, end, _), (_, _, _, start, _, _) in zip(city.PERIODS, city.PERIODS[1:]):
        assert start == end + 1  # no gap, no overlap
    for key, en, sv, start, end, colour in city.PERIODS:
        assert start <= end and en and sv
        assert len(colour) == 7 and colour.startswith("#")


def test_period_index_boundaries():
    cases = {999: 0, 1000: 0, 1610: 0, 1611: 1, 1865: 3, 1866: 4, 1994: 11, 2026: 11, 2100: 11, 2200: 11}
    for year, idx in cases.items():
        assert city.period_index(year) == idx, year


def test_period_indices_matches_the_scalar_form():
    years = list(range(990, 2210, 7)) + [1000, 1610, 1611, 1865, 1866, 1994, 2100]
    assert city.period_indices(years).tolist() == [city.period_index(y) for y in years]
    assert city.period_indices([1919.4, 1919.6, 1945.4]).tolist() == [5, 6, 7]   # floats are rounded first
    assert city.period_indices([]).tolist() == []


def test_plan2_constants():
    # the estimate tier's tables
    assert len(city.INNER_STADSDELAR) == 21 and "GAMLA STAN" in city.INNER_STADSDELAR
    assert all(n == n.upper() for n in city.INNER_STADSDELAR)
    assert len(city.KATEGORI_GROUPS) == 20 and set(city.KATEGORI_GROUPS.values()) == set(city.GROUP_LABELS)
    assert len(city.GROUP_LABELS) == 7 and city.KATEGORI_GROUPS["Enbostadshus"] == "house"
    assert city.KATEGORI_GROUPS["Kolonistuga"] == "cottage" and city.KATEGORI_GROUPS["Flerbostadshus"] == "apartments"
    # eras are runs of whole periods, contiguous from 1000 to 2100
    starts = {p[3] for p in city.PERIODS}
    assert all(lo in starts for _, lo, _ in city.ERAS)
    assert city.ERAS[0][1] == 1000 and city.ERAS[-1][2] == 2100
    for (_, _, hi), (_, lo, _) in zip(city.ERAS, city.ERAS[1:]):
        assert lo == hi + 1
    assert set(city.ESTIMATE) == {"L", "w_height", "w_area", "w_compact", "group_penalty", "k", "eps", "kvarter_bonus",
                                  "near_m", "late_prod_year", "late_unit_fnr", "never_groups", "estimate_groups",
                                  "min_cell", "min_right", "max_band", "give_period", "band_step", "folds", "seed",
                                  "far_rule", "period_only_stadsdelar"}
    assert city.ESTIMATE["near_m"] == 100.0 and city.ESTIMATE["min_cell"] == 30 and city.ESTIMATE["max_band"] == 15
    assert city.ESTIMATE["far_rule"] == "unknown" and city.ESTIMATE["period_only_stadsdelar"] == set()
    # Decided 2026-10-15 after the independent check: estimate only what the check can vouch for
    assert city.ESTIMATE["estimate_groups"] == {"house"} and city.ESTIMATE["give_period"] is False
    assert city.ESTIMATE["min_right"] == 0.7 and city.ESTIMATE["late_unit_fnr"] == 10_400_000
    assert city.ESTIMATE["estimate_groups"] <= set(city.GROUP_LABELS)


def test_periods_module_reexports_city():
    assert periods.PERIODS is city.PERIODS
    assert periods.period_index is city.period_index


def test_to_local_origin_and_axes():
    x, z = city.to_local(*city.ORIGIN)
    assert np.allclose([x, z], [0.0, 0.0])
    x, z = city.to_local(np.array([154025.1, 154125.1]), np.array([6578986.7, 6578886.7]))
    assert np.allclose(x, [0.0, 100.0])  # x grows east
    assert np.allclose(z, [-100.0, 0.0])  # 100 m north is z = -100 (z points south)
    assert isinstance(x, np.ndarray) and isinstance(z, np.ndarray)


def test_fixture_bbox_covers_gamla_stan():
    minx, miny, maxx, maxy = city.FIXTURE_BBOX
    assert minx < maxx and miny < maxy
    # the WGS84 box 18.062,59.320 - 18.080,59.329 lies inside it
    t = Transformer.from_crs(4326, city.CRS, always_xy=True)
    for lon, lat in [(18.062, 59.320), (18.080, 59.320), (18.062, 59.329), (18.080, 59.329)]:
        e, n = t.transform(lon, lat)
        assert minx <= e <= maxx and miny <= n <= maxy
    # Stortorget (the origin) is inside, in the local frame too
    x, z = city.to_local(np.array([minx, maxx]), np.array([miny, maxy]))
    assert x[0] < 0 < x[1]
    assert z[1] < 0 < z[0]


def test_plan3_terrain_constants():
    # the terrain's settings; relief, fade_m and terrace are product defaults the owner confirms at M4
    t = city.TERRAIN
    assert set(t) == {"cell", "sub", "burn", "water_z", "sea_max", "bridge_m", "lake_offset", "fix_m", "terrace_up",
                      "terrace_max_cut", "buried_max", "ground_min", "datum_max", "relief", "relief_max", "fade_m",
                      "terrace", "chunk", "fixture_margin"}
    assert (t["cell"], t["sub"], t["burn"], t["water_z"]) == (20.0, 4, 2, 0.0)
    assert city.TILE % t["cell"] == 0 and t["chunk"] % city.TILE == 0     # nodes and chunks line up with the tiles
    assert set(t["lake_offset"]) == set(t["fix_m"]) == {"dtm", "contours"}
    # Decided 2026-10-16: the ground at true height by default, and a Hills slider from 0 (flat) to 2.5
    assert (t["relief"], t["fade_m"], t["terrace"]) == (1.0, 400.0, "full")
    assert 0 < t["relief"] <= t["relief_max"] == 2.5
    assert 0 < t["terrace_max_cut"] <= 25.5           # the cut ships as u8 decimetres


def test_plan4a_constants():
    # The box the Wikidata queries use, link templates for the viewer, Floors from OSM, the card's rules
    assert city.BOX_WGS84 == (17.75, 59.22, 18.21, 59.45)
    rq = (Path(city.__file__).with_name("queries") / "wikidata_dated.rq").read_text(encoding="utf-8")
    lon0, lat0, lon1, lat1 = city.BOX_WGS84
    assert f'"Point({lon0} {lat0})"' in rq and f'"Point({lon1} {lat1})"' in rq   # one box everywhere
    assert set(city.LINKS) == {"raa", "wikidata", "wikipedia", "wikipedia_rev"}
    assert "{title}" not in "".join(city.LINKS.values())        # no article title ships (wiki.py: designations)
    assert all(v.startswith("https://") for v in city.LINKS.values())
    assert city.LINKS["raa"].format(id="x") == "https://pub.raa.se/visa/objekt/bebyggelse/x"
    assert city.FLOORS_OSM == {"min_iou": 0.5, "max_levels": 60} and city.OSM_TILES == (4, 4)
    assert city.NO_FLOORS_PURPOSE == {"Religionsutövning"} and city.NO_FLOORS_KATEGORI == {"Vattentorn"}
    assert all(n == n.casefold() for n in city.GENERIC_NAMES) and "bostadshus" in city.GENERIC_NAMES
    generic = re.compile(city.GENERIC_NAME_RE, re.IGNORECASE)
    assert all(generic.match(n) for n in ("Norra flygeln", "_", "X", "Kv. Bacchus", "Kv Svalan", "Kvarteret Svalan"))
    assert not any(generic.match(n) for n in ("Kvarnen", "Kvarnholmen", "Svalan"))     # only a block's own name
    assert city.ARCHITECT_MAX_RARE == 3                       # the rare-architect rule
    assert city.WIKI["thumb_width"] in (250, 330, 500, 960)    # a width Wikimedia serves as standard
    assert city.WIKI["max_m"] == 30.0 and city.WIKI["langs"] == ("sv", "en") and city.WIKI["extract_chars"] == 500
    assert isinstance(city.PHOTO_DENY, set)


def test_plan4b_constants():
    # The stadsdelar as people write them, their everyday names, the neighbours, search, About
    assert len(city.DISTRICT_NAMES) == 117
    for key, name in city.DISTRICT_NAMES.items():
        assert key == key.upper() and name != name.upper()
        assert name.upper() == key or (key, name) == ("ULVSUNDA INDUSTRIOMR", "Ulvsunda industriområde")
    names = {n.casefold() for n in city.DISTRICT_NAMES.values()}
    for alias, keys in city.DISTRICT_ALIASES.items():
        assert keys and all(k in city.DISTRICT_NAMES for k in keys), alias
        assert alias.casefold() not in names, alias          # an alias is another name, never a stadsdel's own
    assert not {o.casefold() for o in city.OUTSIDE} & names
    aliases = {a.casefold() for a in city.DISTRICT_ALIASES}
    for alias, target in city.BUILDING_ALIASES.items():          # another name for a card's own name
        assert alias.strip() == alias and target.strip() == target and alias.casefold() != target.casefold(), alias
        assert alias.casefold() not in names | aliases, alias       # never a stadsdel's name or an everyday one
    assert set(city.SEARCH) == {"addr_max_m", "min_chars", "max_rows", "max_per_kind", "max_edits", "examples"}
    assert city.SEARCH["max_per_kind"] <= city.SEARCH["max_rows"] and city.SEARCH["min_chars"] >= 2
    assert all(isinstance(e, str) and e for e in city.SEARCH["examples"])
    assert city.SNAPSHOT == "2023-01"
    # The launch decisions of 2026-10-17
    assert city.LANG_FROM_BROWSER is True                   # 1: a browser set to Swedish opens in Swedish
    assert len(city.MAKER.split()) == 2                     # 2: the maker, named on About as the GDPR controller
    assert city.CONTACT.endswith("@husforhus.se") and " " not in city.CONTACT   # ... and the project's own address
    assert city.PRIVATE_ADDRESSES is True                   # 3: a private house's address is shown
    assert city.RELEASE_WAITS_FOR == ()                     # ... so the public site waits for nothing
    assert set(city.GROUP_LABELS_SV) == set(city.GROUP_LABELS)
    assert set(city.ERA_LABELS_SV) <= {e[0] for e in city.ERAS}


def test_district_names_cover_the_stadsdelar_file():
    from pipeline.s02_attributes import STADSDELAR, load_districts
    from tests.realdata import ensure_city_data

    ensure_city_data([STADSDELAR], steps="s00_fetch_city")
    assert {k.casefold() for k in city.DISTRICT_NAMES} == load_districts(STADSDELAR)
