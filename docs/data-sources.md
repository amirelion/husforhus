# Data sources catalogue

This file lists every open source we plan to use or have ruled out. Status meanings:
- **verified**: re-fetched by an independent fact-checker on 2026-10-14
- **docs**: read from official documentation only
- **to confirm**: needs written confirmation before the repo goes public

Only openly licensed data goes into `web/data/`. Raw downloads live in `data/`, which is git-ignored.

Coordinate systems: the City of Stockholm uses **SWEREF 99 18 00 (EPSG:3011)**. Lantmäteriet and RAÄ use **SWEREF 99 TM (EPSG:3006)**. The terrain model uses EPSG:5845 (SWEREF 99 TM + RH 2000).

## Buildings: footprint, height, type

| Source | Publisher | Licence | Access | Key fields | Size | Status | Role |
|---|---|---|---|---|---|---|---|
| **SBK 3D-Byggnader (LOD1) generaliserade** | Stockholms stad (SBK) | Unclear: product spec says CC BY; metadata states none; WMS says "all rights reserved" | Direct download, no login: `dataportalen.stockholm.se/dataportalen/Data/Stadsbyggnadskontoret/LOD1_stadsdelsnamnder_SHP.zip` (17.8 MB, 2025-11-14) | `UUID, FASTIGHET, HUSNR, GRUPP, KATEGORI, BYGG_A, BYGG_H, MARK_Z, TAK_Z, TAKMIN_Z, TAKMAX_Z, PROD_DATE, MOD_DATE` | 77,769 buildings, 13 MULTIPATCH shapefiles, EPSG:3011 | verified, **licence to confirm** | **Primary geometry + height** |
| OSM buildings and `building:part` | OpenStreetMap | ODbL | Geofabrik extract / Overpass | `building:levels, height, roof:shape, start_date, wikidata, name` | 82,024 buildings in the kommun; 3,229 building parts | verified | Floors; landmark roof shapes; keep as a separate ODbL join file |
| Byggnad Nedladdning, vektor | Lantmäteriet | CC BY 4.0 + personal-data terms (purpose review, GDPR controller) | Geotorget account + application; STAC `byggnader/0180` (13.4 MB) | `objektidentitet, objekttyp, andamal1-5, husnummer, huvudbyggnad`. No height, no year | ~all buildings ≥15 m² | verified (401 without auth) | Fallback only |
| Overture buildings | Overture Maps | ODbL | S3 / DuckDB | Mostly OSM + 10,886 Microsoft ML footprints | 92,872 | verified | Not needed |

Gotchas in the city LOD1 data:
- 58 churches and towers are extruded to spire height across their whole footprint (Riddarholmskyrkan reaches 89.7 m over 1,570 m²). Clamp these to `TAK_Z` and add spires from OSM `building:part`.
- 4,010 rows (5.2%) have no UUID.
- The snapshot is dated 2023-01-17, so buildings completed after about 2022 are missing.
- File names inside the zip are CP437-encoded. Extract with Python and re-decode them.

## Construction year

| Source | Licence | Coverage in Stockholm | Join | Status | Role |
|---|---|---|---|---|---|
| **RAÄ "Bebyggelse, kulturhistoriskt inventerad"** (Bebyggelseregistret) | **CC0 1.0** | 23,524 objects; 28.4% of LOD1 buildings by count, 42% by area, 36% including district polygons | `registerbyggnad_id` = LOD1 `UUID` (98.8% match) | verified | **Primary year source.** Gives `nybyggnad_tillkomstar_from` / `_tom` |
| **RAÄ OLD register file** `byggnader_sverige.gpkg` (catalogue entry 207, "transition period") | **CC0 1.0** | Research (2026-10-15): 29,182 Stockholm points, 23,847 with a Nybyggnad year; 818 undated buildings gain a year. Build v20261015-m3b: 809 buildings take their year from it (the tier's winners) | `fast_byg_uuid` = LOD1 `UUID` | verified (2026-10-15) | **Year tier `raa_old`** (Plan 2, after `raa`); snapshot kept, the file may disappear |
| Wikidata P571 / P1619 | CC0 | Research (2026-10-15): 760 dated building items in the kommun; 386 placed one-to-one, 137 of them undated before. Build v20261015-m3b: 133 buildings take their year from it (the tier's winners) | coordinates on footprints (inside, courtyard, nearest within 30 m) | verified | **Year tier `wikidata`** (Plan 2, below `raa_area`); the RAÄ cross-check feeds the curated review list; landmarks |
| Curated landmark overrides | own, cited to Wikipedia/Wikidata | ~200 planned | manual | — | Always wins (e.g. Royal Palace 1754, not RAÄ's 1170) |
| OSM `start_date` (also `year_of_construction`, `construction_date`) | ODbL | Research (2026-10-15): 1,367 dated buildings; 514 undated before, 256 of them after 1990. Build v20261015-m3b: 418 buildings take their year from it (the tier's winners) | centre on a footprint, else nearest within 15 m | verified | **Year tier `osm`** (Plan 2, below `wikidata`); within 10 years of RAÄ 88% of the time |
| SCB `BostadsbyggnadAlder3` (residential build year by DeSO) | CC0 | 569 DeSO areas, residential only | DeSO polygons | verified | **Not used in v1.** Old-building years mix in tax-register data (spec review data-F1) |
| Lantmäteriet `nybyggnadsår` (Fastighetsinformation / Byggnad Direkt) | CC BY 4.0 + purpose review + GDPR | most residential buildings | `objektidentitet` (= UUID, inferred) | verified gated | Only if an application is approved. Not v1 |
| Lantmäteriet "Ortofoto historiska Visning" (1949–2005) | CC0 | whole city, 0.5–1 m | visual | verified (401 without account) | Later: bracket estimated years |
| GHS-OBAT / GHS-AGE | unverified | epochs since 1980 only | Overture id | docs | Weak prior, probably skip |

## Floors

| Source | Coverage | Rule |
|---|---|---|
| OSM `building:levels` | 19,328 footprints (24.9%) matched at IoU > 0.5; inner city 59.5%, outer 18.4% (build of 2026-10-17; the earlier 29.5% / 72% counted OSM buildings, not our footprints) | rounded half up, `floors_src = osm`; roof levels not added (they lower agreement with the height rule); D46 |
| `BYGG_H / k` | everything else | k ≈ 4.0 m (Flerbostadshus 4.1–4.2, Kontor 4.5, Kolonistuga 3.0). Amsterdam's 3.2 m is wrong here: 17–22% exact vs 50% |

## Energy

None. Boverket's register API is restricted to companies under agreement (BankID, 1,500 calls/day). The law (SFS 2006:1592 §16) limits bulk release to statistics, research, follow-up and supervision. **No Energy mode in v1.**

## Terrain

| Source | Licence | Access | Notes |
|---|---|---|---|
| LOD1 `MARK_Z` per building | as LOD1 | included | Enough for building bases |
| Lantmäteriet Markhöjdmodell Nedladdning 1 m (STAC `dtm-cog`) | CC BY 4.0, no purpose review | the owner's free Geotorget account (downloads answer 401 without it; the catalogue is open) | 10 tiles over the kommun, 2.76 GB on the server; read at 5 m from the COGs' overviews if the files carry them (if not, the step stops rather than stream about 0.8 GB, unless the owner allows it with `--full-res`), only in the 1 km blocks that meet the kommun plus 500 m, into `data/raw/dem/dtm5.tif` (`s00_fetch_dem`), never downloaded whole. **Terrain source (D37)** once the login exists |
| Stockholms stad Stadskarta, 2 m contours (`0_line`, "Höjdkurva heltäckande") | as the Stadskarta (CC BY 4.0, pending O1; named in the O1 addendum) | none: the same zip as the other Stadskarta layers | 28,410 lines, 29.6 MB compressed; heights from 29,685 labels in `NamnText_point` (40% of the lines labelled; the rest inferred from them, the shores at their water levels and the buildings' `MARK_Z`), joined in one TIN with the shores and the buildings' `MARK_Z`. **Terrain source until the login exists (D37)** |
| Lantmäteriet Markhöjdmodell grid 50+ | CC0 | the same account | Not a fallback: same login, 1980s data, 2.5 m error |

## Base map: water, streets, districts, boundary

| Layer | Source | Licence | Status |
|---|---|---|---|
| Water / land | City Stadskarta `Vatten_area`, `Land_area` (range-read from the 108 MB zip) | CC BY per spec, **to confirm** | verified |
| Street-name labels | Stadskarta `TextKurvad_line` (3,199 curved name lines) + `NamnText_point` | same | verified |
| Districts | `Stadsdelar.zip` (117 stadsdelar; their union = municipality boundary) | city, unstated | verified |
| Fallbacks | Lantmäteriet Marktäcke (CC BY 4.0), Topografi 50 (CC0, no street names), Kommun/Län/Rike (CC BY 4.0), OSM (ODbL), Trafikverket NVDB (CC0) | — | verified |

## Addresses and search (Plan 4b, D52)

| Source | Licence | Coverage | Use |
|---|---|---|---|
| OSM `addr:street` + `addr:housenumber` (Overpass, 16 tiles of the municipality's box, about 35 MB, `data/raw/osm/addresses/`) | ODbL 1.0, inside the ODbL-as-a-whole database (D17) | 128,217 house numbers in the box; 75,534 on a footprint (inside it, else within 10 m); 51,746 of 77,743 footprints (66.6%) have one; 3,577 streets (the build of 2026-10-17) | the card's address line and search; "12-14" and "3;5" give each end or item; 12 that read as property designations are left out |
| City `AdressText_point` | CC BY, as the Stadskarta (`confirmed`, 2026-10-16) | 32,923 points, house numbers only | not used: paired with the nearest street label they agree with OSM 31% of the time (the spec's bar was 95%) |
| Stadsdelar (`NAMN`) | as above | 117 stadsdelar | the card's stadsdel and search, written as people write them (`city.DISTRICT_NAMES`, checked against Wikidata's labels: 116 of 117) |

## History and context layers

| Source | Licence | What it gives | Status |
|---|---|---|---|
| RAÄ Bebyggelseregistret (same file as years) | CC0 | Stadsmuseet classification (Blått 1,259 / Grönt 8,531 / Gult 12,759), protection type (233 statligt byggnadsminne, 182 byggnadsminne, 104 kyrkligt kulturminne), architects (`upphov`, 22,135), facade material, building purpose (industry 506, faith 201) | verified |
| RAÄ byggnadsminnen protection zones | CC0 | 291 polygons in the county | verified |
| Riksintresse kulturmiljövård (Länsstyrelsen ShapeExport zip) | CC BY 4.0 | K115 Stockholms innerstad, Vällingby, Skogskyrkogården, Gamla Enskede… | verified |
| UNESCO (Skogskyrkogården) | no conditions | 1 site | docs |
| Wikidata | CC0 | 2,232 buildings, 864 with architect; 750 streets (434 with "named after"); 103 churches; 69 demolished buildings; 19 Nobel laureates | verified |
| Swedish Wikipedia | CC BY-SA | story text, residents (text mining), fires (40 articles), walls and tolls, malmgårdar, Norrmalmsregleringen | verified |
| Stockholmskällan (incl. Samfundet S:t Erik blue-plaque texts) | per item; the site default is non-commercial. A post's CC BY label covers its photograph, not the plaque text (data-layers note §1.6) | plaque texts sv/en with property name; no API | verified; texts wait for O4 |
| Stadsmuseet, Stads- och byggnadsarkeologiskt register (BR), and its reports in Digitala Stadsmuseet | written permission from Stadsmuseet, 2026-10-19: free use with the source credited | ~250 properties in Gamla stan and Riddarholmen: investigations' years, categories (medieval masonry, dendro), polygons (WFS sr:v_area_br, EPSG:3011), report links; the pinned card's "Building archaeology" (s02_stadsmuseet) | in use |
| SKBL (Svenskt kvinnobiografiskt lexikon) | CC BY | ~2,000 women's biographies, JSON with geocoded places | fact-checker find, not yet examined |

## Boats (ferry routes)

| Source | Licence | Coverage | Use |
|---|---|---|---|
| OSM `route=ferry` relations and ways in the kommun (Overpass, `pipeline/queries/ferry_routes.overpass`, cached in `data/raw/osm/ferries.json`, 2.1 MB) | ODbL 1.0, `sources.yml` `ferry_routes` | 138 relations and 95 ways on 2026-10-20, 11 routes kept: SL's 80, 80X, 82, 84 and 89, Sjöstadstrafiken and Cityline, E/S Movitz (Riddarholmen–Solna strand); Viking Line from Stadsgården, Silja Line and Tallink from Värtahamnen | `s17_ferries` writes `ferries.json`: each route cut to the map's water (`s04_base`), one per line and one per ship operator and terminal (`pipeline/ferries.py`). The boats are illustration, real routes and not live positions. Left out: Waxholmsbolaget's archipelago lines, Strömma's and the other sightseeing boats, the E 20's road ferries |

The kommun's border runs down Saltsjön and Lilla Värtan, so most lanes leave the map's water soon. A city boat's lane up to 150 m outside it, and a Baltic ship's up to 250 m, is drawn along its edge: Viking Line's keeps to Saltsjön's south side, up to 114 m outside the kommun, which gives Viking Line about 4.3 km from Stadsgården; Silja Line's and Tallink's run 100–215 m outside it down Lilla Värtan, which gives them about 2.9 km from Värtahamnen, to where the lane bears away from the kommun's water. Where a lane drawn along the edge turns away to a pier in another kommun (Pendelbåt 80 in Nacka, E/S Movitz at Solna strand), the route ends where its points along the edge would turn back, so the boat does not double back along the border. The paths stay on the map's water and never cross off the map; the stretches along the edge are simplified to 40 m, as the border is jagged where the lanes run straight.

## Photos

| Source | Licence | Access | Status |
|---|---|---|---|
| **Digitala Stadsmuseet** (FotoWeb API, anonymous) | per photo, field 590: 76% CC BY, 21% CC BY-NC-ND | `digitalastadsmuseet.stockholm.se/fotoweb/archives/5000-Alla-fotografier/` + `Accept: application/vnd.fotoware.assetlist+json`; previews up to 2400 px; no CORS | in use (Task 20) in Gamla stan and on Riddarholmen: s00_fetch_stadsmuseet harvests fields 576 (stadsdel) and 516 (kvarter), keeping only items whose field holds the value asked for and refusing the archive when a known kvarter or a made-up one shows it does not filter; s02_stadsmuseet_photos keeps CC BY exteriors placed by address (510) on one footprint, never a private house, at most three per building, oldest first; the rendition copied to the site (1,200 px at most); `sources.yml` `stadsmuseet_photos`, a deny list in `pipeline/stadsmuseet_deny.txt` |
| Wikimedia Commons | per file: CC BY-SA 82%, PD 11%, CC BY 5%, CC0 1.4% of the 1,037 files on placed items (2026-10-16) | Wikidata P18 of the card's item, `imageinfo` + `extmetadata`; the 500 px thumbnail copied to the site (D48) | in use (Plan 4a): 893 photos in the build of 2026-10-17, P18 or a curated pick (D19), 29 files refused by eye (`city.PHOTO_DENY`) |
| Wikipedia (sv, en) | CC BY-SA 4.0 | intro extracts through the MediaWiki API; `sources.yml` `wikipedia` | in use (Plan 4a): 891 sv and 119 en excerpts in the build of 2026-10-17, sentences naming a property designation, an owner or a byggherre left out (D49) |
| K-samsök / Europeana / DigitaltMuseum | per record | secondary, noisy for Stockholm | verified |

Credit rule from Stadsmuseet: show the photographer's name and "Stadsmuseet i Stockholm" next to every image.

## Ruled out (not open, or not appropriate)

| Source | Why |
|---|---|
| City WMS of Stadsmuseet's classification | "All rights reserved". Use RAÄ's CC0 copy instead |
| City detailed plans / q-märkning | internal to SBK; the Lantmäteriet product is paid |
| City LOD2, point clouds, height grid | paid under the city's tariff |
| City orthophotos 1995→ | no licence stated; WMS "all rights reserved" |
| Boverket energy declarations | restricted by law and agreement |
| Taxering Direkt / Nedladdning (`värdeår`) | paid + legal review |
| Rotemansarkivet | private individuals, no licence |
| *Stockholms gatunamn* book | copyright. Use Wikidata P138 instead |
| Samfundet S:t Erik plaque PDF | no licence; the texts wait for O4 (Stockholmskällan's CC BY covers photos only) |
| GlobalBuildingAtlas | CC BY-NC |
| Paris site code | all rights reserved (ideas only) |
| Images of in-copyright public art | NJA 2016 Supreme Court ruling (Ö 849-15) |
