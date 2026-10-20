"""Everything Stockholm-specific that the pipeline and the generated stockholm.json need.

Local frame: metres from ORIGIN (Stortorget), x east, z south, as upstream (three.js, y up).
The tests and web/themes.js quote some of these constants, so change them together.
"""
from bisect import bisect_right

import numpy as np

SLUG = "stockholm"
NAME = "Hus för hus"
SUBTITLE = {"en": "Stockholm, building by building", "sv": "Stockholm, hus för hus"}
CRS = 3011                                   # SWEREF 99 18 00
ORIGIN = (154025.1, 6578886.7)               # Stortorget, EPSG:3011
KOMMUN = "0180"
WIKIDATA = "Q506250"
TILE = 1200.0                                # metres; M2 draw-call rule picked 1200 over 1500
N_PACKS = 8
SIMPLIFY = 0.25                              # metres
# Riddarfjärden panorama, tuned by eye: from the WNW over the water, Stadshuset front left, Riddarholmen
# in the middle, Gamla stan behind it, Södermalm's cliffs on the right. Camera 2,250 m from the target at 17°.
HOME = dict(x=-350.0, z=0.0, azimuth=255.0, elevation=17.0, span=2500.0)
# (key, label_en, label_sv, from, to, colour); colours are the default look, Ärg (web/look.js DEFAULT_LOOK);
# web/themes.js overrides them per look. web/test/look.test.mjs checks that they match.
PERIODS = [
    ("p1",  "Medieval & early Vasa",             "Medeltid och äldre vasatid",            1000, 1610, "#8ed3d0"),
    ("p2",  "Stormaktstiden",                     "Stormaktstiden",                        1611, 1718, "#72c3c1"),
    ("p3",  "Frihetstid & Gustavian",             "Frihetstid och gustaviansk tid",        1719, 1809, "#5ab2b3"),
    ("p4",  "Early 1800s",                        "Tidigt 1800-tal",                       1810, 1865, "#47a0a5"),
    ("p5",  "Stenstaden",                         "Stenstaden",                            1866, 1889, "#3c8e97"),
    ("p6",  "Jugend & national romanticism",      "Jugend och nationalromantik",           1890, 1919, "#387b88"),
    ("p7",  "Swedish Grace",                      "Nordisk klassicism",                    1920, 1929, "#3c6778"),
    ("p8",  "Funkis",                             "Funktionalism",                         1930, 1945, "#465262"),
    ("p9",  "Folkhem & ABC towns",                "Folkhemmet och ABC-städer",             1946, 1964, "#87503d"),
    ("p10", "Million Programme & city clearance", "Miljonprogrammet och citysaneringen",   1965, 1975, "#aa6446"),
    ("p11", "Postmodern & infill",                "Postmodernism",                         1976, 1993, "#cf7b50"),
    ("p12", "Waterfront districts",               "Hammarby sjöstad till Norra Djurgårdsstaden", 1994, 2100, "#e49f75"),
]
# Private houses (they show only the decade, so the exact year can't identify the owners): the dwelling KATEGORI values for small private homes in the LOD1 (2023-01 snapshot, 20 values):
# Enbostadshus 44,238 buildings after cleaning (villas, row and chain houses) and Kolonistuga 3,098 (allotment
# cottages). The LOD1 has no separate småhus, radhus or fritidshus value. Outbuildings (Komplementbyggnad,
# Ospec. byggnad *) are not homes. s02_years sets private = True for a dated, uncurated building in this set and
# publishes only its decade. Finalised with `python -m pipeline.report_kategori`.
PRIVATE_HOUSE_KATEGORI = {"Enbostadshus", "Kolonistuga"}
# Metres per storey k: floors = clamp(floor(height / k + 0.5), 1, 99). Fitted once, offline (2026-10-14,
# `report_kategori --osm`) against 21,573 OSM building:levels matched to LOD1 footprints. Six KATEGORI get their
# own k: the median height per OSM level, moved to the best exact share where that differs (Flerbostadshus
# 3.9 -> 4.0, Allmän byggnad 4.7 -> 4.6). Kontorsbyggnad keeps the researched 4.5 (4.3-4.7 score alike). Every
# other KATEGORI uses _default 4.2, the median for the pooled rest. Industribyggnad 4.2 and _default 4.2 are one
# matched building short of their best grid k (4.3 and 4.1). Exact floors 61.9% -> 63.5%, within one floor
# 91.6% -> 92.2% (placeholders -> these).
STOREY_M = {"Flerbostadshus": 4.0, "Enbostadshus": 3.7, "Kolonistuga": 3.1, "Kontorsbyggnad": 4.5,
            "Allmän byggnad": 4.6, "Industribyggnad": 4.2, "_default": 4.2}
TIER1 = [
    # main streets, all found in the Stadskarta (Västerlånggatan and Österlånggatan only in TextKurvad_line;
    # Kungsgatan, Vasagatan, Hamngatan, Hornsgatan, Fleminggatan, Odengatan, Narvavägen, Regeringsgatan and
    # Kungsholmsgatan only in NamnText_point)
    "Strandvägen", "Sveavägen", "Drottninggatan", "Kungsgatan", "Vasagatan", "Hamngatan", "Birger Jarlsgatan",
    "Götgatan", "Hornsgatan", "Ringvägen", "Sankt Eriksgatan", "Fleminggatan", "Odengatan", "Karlavägen",
    "Valhallavägen", "Norr Mälarstrand", "Söder Mälarstrand", "Skeppsbron", "Västerlånggatan", "Österlånggatan",
    "Folkungagatan", "Hantverkargatan", "Narvavägen", "Regeringsgatan", "Kungsholmsgatan",
    # waters: NamnText_point GRUPP Sjö; Saltsjön is in neither file and is hand-placed from SALTSJON
    "Riddarfjärden", "Mälaren", "Strömmen", "Årstaviken", "Brunnsviken", "Nybroviken", "Klara Sjö",
    "Hammarby Sjö", "Saltsjön", "Lilla Värtan", "Djurgårdsbrunnsviken", "Ladugårdslandsviken",
]
SALTSJON = (2050.0, 600.0, 0.0)               # local (x, z, angle°): open water off Fåfängan, 237 m from any shore
FEATURES = {"quests": True, "layers": False, "energy": False, "lang": True, "search": True, "scenes": True,
            "plaques": True, "metro": True, "walks": True, "ferries": True}   # lang, search, scenes, plaques: on since
# 2026-10-17; metro: s16_metro; ferries: s17_ferries, the boats (decided 2026-10-20), shown while the timeline is at
# today unless the viewer's Boats switch turns them off
# quests and walks: on for everyone since 2026-10-18; the Look panel's "Quests and walks" switch hides their buttons
# Where a walk can start besides the walker's own location (web/app.js, Walks): (en, sv, x, z) in local metres,
# from WGS84 via pyproj (2026-10-18). The first is the default; Stortorget is ORIGIN.
STARTS = [("Stortorget", "Stortorget", 0.0, 0.0), ("Central Station", "Centralstationen", -688.8, -576.4),
          ("Kungsträdgården", "Kungsträdgården", 33.4, -713.0), ("Slussen", "Slussen", 85.0, 621.5),
          ("Medborgarplatsen", "Medborgarplatsen", 160.8, 1203.0), ("Odenplan", "Odenplan", -1201.0, -1990.8)]
FIXTURE_BBOX = (153529.0, 6578318.0, 154556.0, 6579322.0)  # WGS84 18.062,59.320–18.080,59.329 via pyproj, rounded outward
# HFH_FIXTURE=1 makes s01_load keep only buildings whose 2D footprint intersects FIXTURE_BBOX (519 on 2026-10-14);
# tests/conftest.py gamla_stan_lod1 cuts with the same rule.
# The whole city has 77,743 buildings after cleaning (2026-10-15). Fewer than this means a partial input (a LOD1
# district missing, a filter gone wrong): s01_load stops outside fixture builds, and the real-data tests fail.
MIN_BUILDINGS = 70_000

# --- The estimate tier and the accuracy table ---
# Inner city for the accuracy table: the stadsdelar (Stadsdel.shp NAMN, upper case) of the four inner
# stadsdelsområden Norrmalm, Östermalm, Kungsholmen and Södermalm (12,260 buildings on 2026-10-15).
INNER_STADSDELAR = {
    "NORRMALM", "VASASTADEN", "SKEPPSHOLMEN",
    "ÖSTERMALM", "DJURGÅRDEN", "NORRA DJURGÅRDEN", "LADUGÅRDSGÄRDET", "HJORTHAGEN",
    "KUNGSHOLMEN", "MARIEBERG", "FREDHÄLL", "KRISTINEBERG", "STADSHAGEN", "LILLA ESSINGEN", "STORA ESSINGEN",
    "SÖDERMALM", "GAMLA STAN", "RIDDARHOLMEN", "LÅNGHOLMEN", "REIMERSHOLME", "SÖDRA HAMMARBYHAMNEN",
}
# KATEGORI groups: the rows of the accuracy table and the kNN's "same kind of building" test. Every LOD1 KATEGORI
# (the 20 values of report_kategori's report) maps to one group; a value not listed counts as "unspecified".
KATEGORI_GROUPS = {
    "Flerbostadshus": "apartments",
    "Enbostadshus": "house",
    "Kolonistuga": "cottage",
    "Komplementbyggnad": "outbuilding", "Ekonomibyggnad": "outbuilding",
    "Ospec. byggnad Oregistrerad": "unspecified", "Ospec. byggnad Registrerad": "unspecified",
    "Kontorsbyggnad": "work", "Handelsbyggnad": "work", "Hotellbyggnad": "work", "Industribyggnad": "work",
    "Ospec. industribyggnad": "work", "Ospec. verksamhetsbyggnad": "work", "Parkeringshus": "work",
    "Transformator": "work", "Vattentorn": "work",
    "Allmän byggnad": "public", "Idrottsbyggnad": "public", "Vårdbyggnad": "public",
    "Ospec. samfundsbyggnad": "public",
}
GROUP_LABELS = {"apartments": "Apartment blocks", "house": "Houses (villa, row, chain)",
                "cottage": "Allotment cottages", "outbuilding": "Outbuildings", "unspecified": "Unspecified",
                "work": "Work (office, shop, industry, utility)", "public": "Public (school, care, sport, church)"}
# Eras: the accuracy table's columns, each a run of whole periods (p1–p4, p5–p6, p7–p8, p9–p10, p11, p12).
ERAS = [("before 1866", 1000, 1865), ("1866–1919", 1866, 1919), ("1920–1945", 1920, 1945),
        ("1946–1975", 1946, 1975), ("1976–1993", 1976, 1993), ("1994 on", 1994, 2100)]
# The estimate tier (pipeline/estimate.py), as tuned and measured on 2026-10-15. Distances are in units of L.
# Decided 2026-10-15, after the independent check on the Wikidata/OSM-only buildings): the cross-validation measures
# RAÄ-dated, mostly old buildings, while the buildings the map estimates are the ones RAÄ never dated, many of them new
# among older neighbours. So the map estimates only what the checks can vouch for: houses only, no period on its own,
# 7 in 10 right, and no building on a late-formed property unit.
ESTIMATE = dict(
    L=280.0,               # metres per unit of feature distance
    w_height=3.0,          # weight of ln(height)
    w_area=0.5,            # weight of ln(footprint area)
    w_compact=0.0,         # weight of compactness 4*pi*A/P^2 (measured: adds nothing)
    group_penalty=2.0,     # added in quadrature when the KATEGORI group differs (2 units = 560 m)
    k=20,                  # neighbours; the year is their inverse-distance-weighted median
    eps=0.05,              # weight 1 / (distance + eps)
    kvarter_bonus=0.5,     # taken off the distance to candidates in the same kvarter (production only)
    near_m=100.0,          # no estimate when the nearest dated building is further away
    late_prod_year=2008,   # first digitised in the LOD1 this year or later: probably new, no estimate
    late_unit_fnr=10_400_000,   # LOD1 FNR (property-unit key) above this: a unit formed late, mostly new, no estimate
    never_groups={"cottage"},   # no dated example anywhere, so nothing can be measured (and nothing is scored)
    estimate_groups={"house"},  # the only KATEGORI groups given a year; the others are measured but stay unknown
    min_cell=30,           # test buildings a cell needs to be measurable
    min_right=0.7,         # share in the right period a cell needs to give an estimate (was 0.5 before 2026-10-15)
    max_band=15,           # a wider 80th-percentile band: the period only if give_period, else unknown
    give_period=False,     # True lets a right-enough cell with a wide band (and the fallback rows) show the period only
    band_step=5,           # bands round up to this and never go below it
    folds=5, seed=0,       # cross-validation with whole kvarter held out
    far_rule="unknown",    # beyond near_m: "unknown" (option A, measured right) or "period" (option C; needs give_period)
    period_only_stadsdelar=set(),   # e.g. {"GAMLA STAN"}: still-unknown buildings there get the period (needs give_period)
)

# --- Terrain ---
# Heights are metres in RH 2000. Grid nodes sit every `cell` metres on multiples of it in the local frame (so they
# line up with the 1200 m tiles); a node is the mean of its land sub-samples (sub x sub of them), and `burn` nodes of
# water around land take the nearest land height, so bilinear sampling keeps bank heights up to the shore.
TERRAIN = dict(
    cell=20.0, sub=4, burn=2,
    water_z=0.0,           # the sea and Mälaren, one level: Saltsjön's 2026 mean is +0.07 m, Mälaren +0.86
    sea_max=3.0,           # a water system whose lowest shore reads under this is the sea or Mälaren
    bridge_m=30.0,         # water pieces closer than twice this (a bridge, a lock) are one system
    lake_offset={"dtm": 0.3, "contours": 1.0},   # a lake with no flat laser surface: its shore's 5th percentile minus this
    fix_m={"dtm": 5.0, "contours": 20.0},        # MARK_Z this far under the terrain along its outline is an error
    terrace_up=0.3,        # the terrain under a footprint may be cut to the building's drawn ground plus this ...
    terrace_max_cut=20.0,  # ... by at most this (the quays at the foot of Söder's cliffs need 15-20 m; u8 dm holds 25.5)
    buried_max=10,         # s99: at most this many buildings buried by more than half their height at relief_max
    ground_min=0.3,        # a building is drawn at least this far above water_z (four quay buildings sit below 0)
    datum_max=0.3,         # s99: |median(MARK_Z - terrain minimum along the outline)| must stay under this
    relief=1.0,            # the default: the ground at true height (decided 2026-10-16; 2-3x had been the first plan)
    relief_max=2.5,        # the top of the Look panel's Hills slider (0 to this); the viewer's culling bounds assume it
    fade_m=400.0,          # the edge fade: ground and water fade into the sky over this
    terrace="full",        # how the viewer uses the cut: "full", "true" (the true burial at any relief) or "none"
    chunk=2400.0,          # metres per terrain mesh (two by two building tiles: 63 hold land, not 207)
    fixture_margin=2000.0,  # HFH_FIXTURE=1: land, water and terrain only within FIXTURE_BBOX grown by this
)

# --- Timeline landmarks, Floors from OpenStreetMap, the building card ---
# The municipality's WGS84 box (lon0, lat0, lon1, lat1): the Wikidata queries' wikibase:box and the Overpass tiles.
BOX_WGS84 = (17.75, 59.22, 18.21, 59.45)
# Link templates (the viewer holds no Stockholm literals; s03_tiles copies them into stockholm.json `links`).
# {id}: RAÄ's own record id; {qid}: a Wikidata item; {lang}: a Wikipedia language; {rev}: the revision an excerpt was
# taken from. No article title or file name ships (they are often property designations, wiki.py): an article is
# reached through its Wikidata item, an excerpt's credit through its revision id.
LINKS = {
    "raa": "https://pub.raa.se/visa/objekt/bebyggelse/{id}",
    "wikidata": "https://www.wikidata.org/wiki/{qid}",
    "wikipedia": "https://www.wikidata.org/wiki/Special:GoToLinkedPage/{lang}wiki/{qid}",
    "wikipedia_rev": "https://{lang}.wikipedia.org/w/index.php?oldid={rev}",
}
# Floors from OSM building:levels (spec s02_attributes): a footprint takes the levels of the OSM building (a way or a
# multipolygon relation, never a building:part) whose intersection with it over their union is above min_iou; roof
# levels are not added (measured: agreement with the height rule drops from 63.6% to 61.4% exact). s00_fetch_osm
# splits BOX_WGS84 into tiles (columns, rows) of Overpass requests.
FLOORS_OSM = dict(min_iou=0.5, max_levels=60)
OSM_TILES = (4, 4)
# The card leaves out its floors row where floors come only from the height and storeys mean little: churches (RAÄ
# purpose group) and water towers.
NO_FLOORS_PURPOSE = {"Religionsutövning"}
NO_FLOORS_KATEGORI = {"Vattentorn"}
# RAÄ `namn` values that name a building's kind, not the building: never a card title, never searchable (casefolded
# whole-name matches, plus a wing named only by its side, and a block's name, "Kv. Bacchus" or "Kvarteret Svalan":
# block names stay out of v1, roadmap question 6).
GENERIC_NAMES = {
    "administrationsbyggnad", "administrationsbyggnaden", "bisättningsbyggnad", "bostadshus", "båthall", "flygelbyggnad",
    "församlimgshem", "församlingshem", "församlingshus", "förråd", "förrådsbyggnad", "gravkapell", "gravkor",
    "gymnastikbyggnad", "gårdshus", "gårdshuset", "huvudbyggnad", "huvudbyggnaden", "institutionsbyggnad",
    "kemibyggnaden", "köksbyggnad", "köksbyggnaden", "laboratoriebyggnaden", "laboratorium", "lusthus", "lusthuset",
    "omformarstation", "orangeri", "orangeriet", "paviljong", "porthus", "portvakthuset", "portvaktsbyggnaden",
    "redskapsbod", "ridhus", "ridhuset", "skjutbanelokal", "slottet", "slottsflygel", "slöjdbyggnad", "smedjan",
    "spruthus", "stall", "stallbyggnader", "stallet", "stationsbyggnad", "terminalbyggnad", "uthus", "uthuslänga",
    "utsiktstorn", "vagnshus", "vagnslider", "vaktbyggnaden", "vattentorn", "vattentornet", "vedbod",
}
GENERIC_NAME_RE = r"^((norra|södra|östra|västra) flygeln|_+|.|kv(arteret)?\b.*)$"
# On a private-category house that is not curated, an architect's name shows only when it appears
# on more than this many buildings citywide, or when it is a firm, an office or a cooperative a person has confirmed
# (pipeline/private_firms.txt; pipeline/architects.py only proposes them).
ARCHITECT_MAX_RARE = 3
# s06_wiki: Wikidata building items (years_wikidata's class rules) placed within max_m of a footprint, the
# best item per footprint for the card (an article first, then the most sitelinks). Photos: Commons thumbnails at
# thumb_width px (a width Wikimedia serves as standard), copied to the site, at most photo_bytes each. Excerpts: the
# intro's first paragraph, whole sentences up to extract_chars characters.
# private_m: an item whose point lies this close to an uncurated private house on the same property is left out (decided 2026-10-17): its photo or article may show the house
WIKI = dict(max_m=30.0, thumb_width=500, photo_bytes=400_000, extract_chars=500, langs=("sv", "en"), private_m=5.0)
# Commons files never shown although Wikidata gives them to a building: a work of art as the main subject (public art,
# NJA 2016), checked by eye from s06_wiki's art-flag list, and a photo that shows something other
# than the footprint it lands on (a building since replaced, a neighbour, a view, a boat, animals), checked by eye from
# its "nearest" list. Read 2026-10-17: 6 art flags and 218 nearest-footprint photos.
PHOTO_DENY: set[str] = {
    # a work of art as the main subject
    "Farsta torg NK 1962.JPG",                                   # the square's fountain, the store behind it
    "Katarina västra vårdgymnasiums gymnastikhall 2012a 01.jpg",  # the gable's relief; the hall, not these flats
    # not the footprint's building: one since replaced, a neighbour, or no building at all
    "Allotment hut in red 1920s.JPG",                 # Skansen's allotment hut, 26 m from the footprint
    "Brunkebergsverket 1896h.jpg",                    # the 1890s works, on a 1935 building
    "Djurgården, Östermalm, Stockholm, Sweden - panoramio (106).jpg",  # the view from a terrace
    "Flora, Midsommarkransen april 2021b.jpg",        # a block of flats, on a transformer station
    "Gyllenborgska malmgården, ritning.jpg",          # a drawing of the malmgård, on an 1888 block
    "Hammarbyverket 2008.jpg",                        # the power station, on a small building 21 m away
    "Kammeckerska kvarnen och malmgården.JPG",        # a painting of the mill, on an 1891 block
    "Kungsholms tull 1910.jpg",                       # the old toll house, on a 1939 block
    "Kvarnen Starckan 1890.jpg",                      # the windmill, on a 1925 block
    "Pratts Birger Jarlsgatan.jpg",                   # the petrol station, on a 1928 block
    "Rescue Pantamera 02.JPG",                        # a rescue boat
    "Skansen 2019 13 56 55 010000.jpeg",              # a well
    "Skansen 2019 13 57 15 137000.jpeg",              # a rock with grinding grooves
    "Skansen 2019 14 05 45 951000.jpeg",              # a garden plot
    "Skansenakv lemurer.jpg",                         # lemurs and children
    "Stativet och Tumstocken 1964b.jpg",              # the old wooden houses, on a 1973 block
    "Stora barnhuset 1784.jpg",                       # an 18th-century view, on an 1888 block
    "Strato Södermalm (2023).jpg",                    # a tower not yet built (a rendering), on an office building
    "Tofslärkan 11, Tyrgatan 9, sept 2022.jpg",       # a large brick house, on a 3 m building 18 m away
    "Älvsjö gård 2015c.jpg",                          # the manor, on an industrial building 24 m away
    "Östra kanslihuset.jpg",                          # Östra kanslihuset, on Västra kanslihuset
    # a CC 2.0–3.0 title (which the credit must show) naming a block of the city and a number it no longer uses: an
    # earlier property designation, which privacy.mentions cannot know
    "Brunkhalsen 5.JPG", "Isafjord 1 Mars 2013 01.jpg", "Lustgården 14 febr 2014a.jpg", "Minan 5 & 6.JPG",
    "Riddaren 17-DSC 5326-1.jpg", "Wahrenberg 10.JPG",
}

# --- Search, the language, About, privacy, credits ---
# The 117 stadsdelar as people write them: Stadsdel.shp's NAMN is upper case and cuts one name short ("ULVSUNDA
# INDUSTRIOMR"). Checked against Wikidata's labels (116 of 117 matched, 2026-10-16); the card and search show these.
DISTRICT_NAMES = {
    "ABRAHAMSBERG": "Abrahamsberg", "AKALLA": "Akalla", "ALVIK": "Alvik", "ASPUDDEN": "Aspudden",
    "BAGARMOSSEN": "Bagarmossen", "BANDHAGEN": "Bandhagen", "BECKOMBERGA": "Beckomberga", "BJÖRKHAGEN": "Björkhagen",
    "BLACKEBERG": "Blackeberg", "BREDÄNG": "Bredäng", "BROMMA KYRKA": "Bromma kyrka", "BROMSTEN": "Bromsten",
    "BÄLLSTA": "Bällsta", "DJURGÅRDEN": "Djurgården", "ENEBY": "Eneby", "ENSKEDE GÅRD": "Enskede gård",
    "ENSKEDEDALEN": "Enskededalen", "ENSKEDEFÄLTET": "Enskedefältet", "FAGERSJÖ": "Fagersjö", "FARSTA": "Farsta",
    "FARSTA STRAND": "Farsta strand", "FARSTANÄSET": "Farstanäset", "FLATEN": "Flaten", "FLYSTA": "Flysta",
    "FREDHÄLL": "Fredhäll", "FRUÄNGEN": "Fruängen", "GAMLA ENSKEDE": "Gamla Enskede", "GAMLA STAN": "Gamla stan",
    "GRIMSTA": "Grimsta", "GRÖNDAL": "Gröndal", "GUBBÄNGEN": "Gubbängen", "HAGSÄTRA": "Hagsätra",
    "HAMMARBYHÖJDEN": "Hammarbyhöjden", "HANSTA": "Hansta", "HERRÄNGEN": "Herrängen", "HJORTHAGEN": "Hjorthagen",
    "HUSBY": "Husby", "HÄGERSTEN": "Hägersten", "HÄGERSTENSÅSEN": "Hägerstensåsen", "HÄSSELBY GÅRD": "Hässelby gård",
    "HÄSSELBY STRAND": "Hässelby strand", "HÄSSELBY VILLASTAD": "Hässelby villastad", "HÖGDALEN": "Högdalen",
    "HÖGLANDET": "Höglandet", "HÖKARÄNGEN": "Hökarängen", "JOHANNESHOV": "Johanneshov", "KISTA": "Kista",
    "KRISTINEBERG": "Kristineberg", "KUNGSHOLMEN": "Kungsholmen", "KÄLVESTA": "Kälvesta", "KÄRRTORP": "Kärrtorp",
    "LADUGÅRDSGÄRDET": "Ladugårdsgärdet", "LARSBODA": "Larsboda", "LILJEHOLMEN": "Liljeholmen",
    "LILLA ESSINGEN": "Lilla Essingen", "LISEBERG": "Liseberg", "LUNDA": "Lunda", "LÅNGBRO": "Långbro",
    "LÅNGHOLMEN": "Långholmen", "LÅNGSJÖ": "Långsjö", "MARIEBERG": "Marieberg", "MARIEHÄLL": "Mariehäll",
    "MIDSOMMARKRANSEN": "Midsommarkransen", "MÄLARHÖJDEN": "Mälarhöjden", "NOCKEBY": "Nockeby",
    "NOCKEBYHOV": "Nockebyhov", "NORRA DJURGÅRDEN": "Norra Djurgården", "NORRA ÄNGBY": "Norra Ängby",
    "NORRMALM": "Norrmalm", "NÄLSTA": "Nälsta", "OLOVSLUND": "Olovslund", "ORHEM": "Orhem",
    "REIMERSHOLME": "Reimersholme", "RIDDARHOLMEN": "Riddarholmen", "RIKSBY": "Riksby", "RINKEBY": "Rinkeby",
    "RÅCKSTA": "Råcksta", "RÅGSVED": "Rågsved", "SKARPNÄCKS GÅRD": "Skarpnäcks gård", "SKEPPSHOLMEN": "Skeppsholmen",
    "SKRUBBA": "Skrubba", "SKÄRHOLMEN": "Skärholmen", "SKÖNDAL": "Sköndal", "SMEDSLÄTTEN": "Smedslätten",
    "SOLBERGA": "Solberga", "SOLHEM": "Solhem", "STADSHAGEN": "Stadshagen", "STORA ESSINGEN": "Stora Essingen",
    "STORA MOSSEN": "Stora mossen", "STUREBY": "Stureby", "SUNDBY": "Sundby", "SVEDMYRA": "Svedmyra",
    "SÄTRA": "Sätra", "SÖDERMALM": "Södermalm", "SÖDRA HAMMARBYHAMNEN": "Södra Hammarbyhamnen",
    "SÖDRA ÄNGBY": "Södra Ängby", "TALLKROGEN": "Tallkrogen", "TENSTA": "Tensta", "TRANEBERG": "Traneberg",
    "ULVSUNDA": "Ulvsunda", "ULVSUNDA INDUSTRIOMR": "Ulvsunda industriområde", "VASASTADEN": "Vasastaden",
    "VINSTA": "Vinsta", "VÄLLINGBY": "Vällingby", "VÄSTBERGA": "Västberga", "VÄSTERTORP": "Västertorp",
    "VÅRBERG": "Vårberg", "ÄLVSJÖ": "Älvsjö", "ÄPPELVIKEN": "Äppelviken", "ÅKESHOV": "Åkeshov",
    "ÅKESLUND": "Åkeslund", "ÅLSTEN": "Ålsten", "ÅRSTA": "Årsta", "ÖRBY": "Örby", "ÖRBY SLOTT": "Örby slott",
    "ÖSTBERGA": "Östberga", "ÖSTERMALM": "Östermalm",
}
# Everyday and English names search knows, each pointing at the stadsdelar it means (r4-ux-copy.md §3.2; hand-written,
# never imported from Wikidata's aliases, which are noisy). An island that is a stadsdel needs no entry.
DISTRICT_ALIASES = {
    "Vasastan": ("VASASTADEN",), "Söder": ("SÖDERMALM",), "Gärdet": ("LADUGÅRDSGÄRDET",), "City": ("NORRMALM",),
    "Old Town": ("GAMLA STAN",), "Stadsholmen": ("GAMLA STAN",), "Hammarby sjöstad": ("SÖDRA HAMMARBYHAMNEN",),
    "Liljeholmskajen": ("LILJEHOLMEN",), "Kastellholmen": ("SKEPPSHOLMEN",), "Beckholmen": ("DJURGÅRDEN",),
    "Essingeöarna": ("STORA ESSINGEN", "LILLA ESSINGEN"),
}
# The names people search the best-known buildings by, each pointing at the name the building's card carries (the
# version's own cards, s14_search; a target no card carries in a build is left out of its index). Hand-written and
# short: the city's landmarks only, never a private house. "Slottet" finds the palace, not every "… slott". Since 2026-10-16
# curated the church as "Klara kyrka", so its formal name, Sankta Clara kyrka, points there (decided 2026-10-17).
BUILDING_ALIASES = {
    "Kungliga slottet": "Stockholms slott", "Slottet": "Stockholms slott", "Royal Palace": "Stockholms slott",
    "Stadshuset": "Stockholms stadshus", "City Hall": "Stockholms stadshus",
    "Riksdagen": "Riksdagshuset i Stockholm", "Riksdagshuset": "Riksdagshuset i Stockholm",
    "Parliament": "Riksdagshuset i Stockholm",
    "Operan": "Kungliga Operan", "Royal Opera": "Kungliga Operan",
    "Dramaten": "Kungliga Dramatiska teatern (Dramaten)",
    "Konserthuset": "Stockholms konserthus", "Stadsbiblioteket": "Stockholms stadsbibliotek",
    "Centralen": "Stockholms centralstation", "Centralstationen": "Stockholms centralstation",
    "Stadion": "Stockholms Stadion", "Ericsson Globe": "Avicii Arena", "Globe Arena": "Avicii Arena", "Globen": "Avicii Arena",
    "Rådhuset": "Stockholms rådhus", "Polishuset": "Stockholms polishus", "Stadsteatern": "Stockholms stadsteater",
    "NK": "Nordiska Kompaniet", "Börsen": "Börshuset", "Nobelprismuseet": "Börshuset", "Nobel Prize Museum": "Börshuset",
    "Vasa": "Vasamuseet", "Nationalmuseet": "Nationalmuseum", "National Museum": "Nationalmuseum",
    "Natural History Museum": "Naturhistoriska riksmuseet", "Nordic Museum": "Nordiska museet",
    "Hallwylska museet": "Hallwylska palatset", "Hallwyl Museum": "Hallwylska palatset",
    "Prins Eugens Waldemarsudde": "Waldemarsudde", "Kaknäs Tower": "Kaknästornet",
    "Domkyrkan": "Storkyrkan", "Stockholm Cathedral": "Storkyrkan", "Sankt Nikolai kyrka": "Storkyrkan",
    "Sankta Clara kyrka": "Klara kyrka", "Maritime Museum": "Sjöhistoriska Museet", "Observatory": "Observatoriet",
}
# Municipalities around Stockholm: a search for one says the map covers Stockholms kommun only.
OUTSIDE = ("Botkyrka", "Danderyd", "Ekerö", "Haninge", "Huddinge", "Järfälla", "Lidingö", "Nacka", "Sollentuna", "Solna",
           "Sundbyberg", "Södertälje", "Tyresö", "Täby", "Upplands Väsby", "Vallentuna", "Vaxholm", "Värmdö", "Österåker")
# Search (pipeline/s14_search.py writes these into search/index.json for web/search.js): an OSM address belongs to the
# footprint it lies in (the smallest), else to the nearest within addr_max_m; a query needs min_chars; the list shows
# max_rows, max_per_kind of one kind; a near miss is a street name within max_edits edits; the empty field suggests the
# examples that resolve in the build.
SEARCH = dict(addr_max_m=10.0, min_chars=2, max_rows=8, max_per_kind=4, max_edits=2,
              examples=("Hornsgatan 30", "Engelbrektskyrkan", "Gamla stan", "Vällingby"))
# Towers and spires from Lantmäteriet's laser points (s00_fetch_laser, s02_towers). The LOD1 gives each footprint one
# flat height, so a tower is as low as its roof. The laser is read around these buildings: every non-private building
# named on a card, every church (s02_attributes' nofloors) and every one whose LOD1 height reaches min_lod1_m, plus this
# hand list, matched by the card's name (casefolded; each entry's first name is how the review page writes it, the
# others are the names a card may carry). Each footprint's box grows by ring_m on every side: the ground around it.
# Not Globen: the dome is its own footprint, already 71 m in LOD1 (checked against the laser on 2026-10-17); the
# name Globen RAÄ gives the entrance building beside it is dropped (pipeline/name_fixes.csv); search finds the dome,
# Avicii Arena, as Globen (BUILDING_ALIASES).
LASER = dict(ring_m=15.0, min_lod1_m=25.0, budget_bytes=500_000_000)
LASER_TOWERS = (
    ("Kaknästornet",), ("Stadshuset", "Stockholms stadshus"), ("Riddarholmskyrkan",),
    ("Storkyrkan", "Stockholms domkyrka", "Sankt Nikolai kyrka"), ("Tyska kyrkan", "Sankta Gertruds kyrka"),
    ("Engelbrektskyrkan",), ("Katarina kyrka",), ("Hedvig Eleonora kyrka", "Hedvig Eleonora"), ("Oscarskyrkan",),
    ("Klara kyrka", "Sankta Clara kyrka"), ("Johannes kyrka", "Sankt Johannes kyrka", "S:t Johannes kyrka"),
    ("Adolf Fredriks kyrka",), ("Gustav Vasa kyrka",), ("Sofia kyrka",), ("Högalidskyrkan",), ("Kungsholms kyrka",),
    ("Skatteskrapan",), ("Wenner-Gren Center",),
)
# Decided 2026-10-17: shown. True shows a private house's street address on its card and lets
# search find it by that address (an address names no one, and the card still gives only the decade); False would
# leave both out for every non-curated private-category house, wherever the address landed (s03_tiles.shown_addresses).
# s99 checks both.
PRIVATE_ADDRESSES = True
# The LOD1 model's snapshot (About: buildings finished after about 2022 are missing).
SNAPSHOT = "2023-01"
# About and the privacy section (answered 2026-10-17): who made the map (named only there, as the
# GDPR controller) and where to write (a forwarding address on the project's domain). Empty, About would name no one,
# the card would have no "Something wrong?" line, and s99 --release fails (a public site needs both, GDPR Art. 14).
MAKER = "Amir Elion"
CONTACT = "hej@husforhus.se"
# What a public release still waits for: open decisions that the locked preview can carry but the public site cannot
# (s99_validate --release fails while this lists anything; remove an entry once it is answered).
RELEASE_WAITS_FOR = ()
# Which language a first visit opens in (answered 2026-10-17): True opens a browser set to Swedish
# in Swedish; ?lang= and the switch's saved choice still come first. False would keep English first.
LANG_FROM_BROWSER = True
# The accuracy table's rows and columns in Swedish, for About (GROUP_LABELS and ERAS are the English).
GROUP_LABELS_SV = {"apartments": "Flerbostadshus", "house": "Småhus (villor, rad- och kedjehus)", "cottage": "Kolonistugor",
                   "outbuilding": "Uthus", "unspecified": "Ospecificerade",
                   "work": "Verksamheter (kontor, handel, industri, teknik)", "public": "Offentliga byggnader (skola, vård, idrott, kyrka)"}
ERA_LABELS_SV = {"before 1866": "före 1866", "1994 on": "1994 och senare"}

_PERIOD_STARTS = [p[3] for p in PERIODS]


def period_index(year: int) -> int:
    """0-based index into PERIODS; years before 1000 → 0, after 2100 → the last period. Scalar; for arrays use
    np.maximum(0, np.searchsorted([p[3] for p in PERIODS], years, side="right") - 1)."""
    return max(0, bisect_right(_PERIOD_STARTS, int(year)) - 1)


def period_indices(years) -> np.ndarray:
    """period_index for an array of years (floats are rounded): the vector form the docstring above describes."""
    y = np.round(np.asarray(years, dtype=float)).astype(np.int64)
    return np.maximum(0, np.searchsorted(_PERIOD_STARTS, y, side="right") - 1)


def to_local(e, n) -> tuple[np.ndarray, np.ndarray]:
    """EPSG:3011 easting/northing → local (x, z) in metres. Vectorised; scalars give 0-d arrays."""
    x = np.asarray(e, dtype=np.float64) - ORIGIN[0]
    z = -(np.asarray(n, dtype=np.float64) - ORIGIN[1])
    return x, z
