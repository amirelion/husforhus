# Data sources

Hus för hus uses only openly licensed data, and two registers used with their publishers' written permission. Every source is credited in one form, whatever its licence:

> **Dataset: publisher, licence**, plus "processed" (Swedish: "bearbetad") when the map changes the data.

Where a source prescribes its own wording, that wording goes inside the same pattern, such as "© Lantmäteriet" or "© OpenStreetMap contributors". Every source below is processed: footprints are simplified, years are chosen between sources, heights are fixed to the terrain, and so on.

The machine-readable list is [`pipeline/sources.yml`](pipeline/sources.yml). Its `attribution` lines are what the map shows, and `s99_validate` fails a build whose sources lack a licence or a credit.

## Datasets

| Dataset | Publisher | Licence | Used for | Credit |
|---|---|---|---|---|
| SBK 3D-Byggnader (LOD1) generaliserade | Stockholms stad, Stadsbyggnadskontoret | CC BY 4.0 | Building footprints, heights, building types | SBK 3D-Byggnader (LOD1) generaliserade: © Stockholms stad, Stadsbyggnadskontoret, CC BY 4.0, bearbetad / processed |
| Stadsdelar | Stockholms stad, Stadsbyggnadskontoret | CC BY 4.0 | The 117 districts and the municipal boundary | Stadsdelar: © Stockholms stad, Stadsbyggnadskontoret, CC BY 4.0, bearbetad / processed |
| Stadskarta | Stockholms stad, Stadsbyggnadskontoret | CC BY 4.0 | Water, land, street names, 2 m contour lines | Stadskarta: © Stockholms stad, Stadsbyggnadskontoret, CC BY 4.0, bearbetad / processed |
| Bebyggelseregistret (Bebyggelse, kulturhistoriskt inventerad) | Riksantikvarieämbetet | CC0 1.0 | Construction years, area years, heritage rating, protection, architects | Bebyggelseregistret: Riksantikvarieämbetet, CC0, bearbetad / processed |
| Bebyggelseregistret, older register file | Riksantikvarieämbetet | CC0 1.0 | Years the current register dropped | Bebyggelseregistret, older file: Riksantikvarieämbetet, CC0, bearbetad / processed |
| Wikidata | Wikidata contributors | CC0 1.0 | Years, building names, photo and article links | Wikidata: Wikidata contributors, CC0, bearbetad / processed |
| OpenStreetMap | OpenStreetMap contributors | ODbL 1.0 | Years, floor counts | OpenStreetMap: © OpenStreetMap contributors, ODbL, bearbetad / processed |
| Markhöjdmodell Nedladdning (1 m terrain model) | Lantmäteriet | CC BY 4.0 | Terrain, when the build has a login for it | Markhöjdmodell Nedladdning: © Lantmäteriet, CC BY 4.0, bearbetad / processed |
| Laserdata Nedladdning, skog (laser point cloud) | Lantmäteriet | CC BY 4.0 | Towers and spires that rise above a building's flat LOD1 roof, when the build has a login for it | Laserdata Nedladdning, skog: © Lantmäteriet, CC BY 4.0, bearbetad / processed |
| Wikipedia (Swedish and English) | Wikipedia contributors | CC BY-SA 4.0 | Short excerpts on building cards; the citations behind the curated landmarks; construction years cited by hand, mostly in Gamla stan, each card linking the article's revision | Wikipedia: © Wikipedia contributors, CC BY-SA 4.0, bearbetad / processed |
| KulturNav, Byggnader i Sverige | ArkDes | CC0 1.0 | Construction years cited by hand, mostly in Gamla stan, each card linking the entry | KulturNav, Byggnader i Sverige: ArkDes, CC0, bearbetad / processed |
| Byggnadsinventeringar (building inventories) in Digitala Stadsmuseet | Stadsmuseet i Stockholm | CC BY 4.0, per document: only those marked CC BY are used | Construction years read from an inventory and cited by hand, each card linking the document | Byggnadsinventeringar: Stadsmuseet i Stockholm, CC BY 4.0, bearbetad / processed |
| Hjorthagen's building stages (Stockholm växer, Norra Djurgårdsstaden 2030) | Stockholms stad | Facts only: the stages' move-in years and their blocks, in our own words | The years of the newer blocks in Hjorthagen, each card linking its stage's page | Hjorthagens utbyggnadsetapper: Stockholms stad, endast fakta, bearbetad / facts only, processed |
| Stads- och byggnadsarkeologiskt register, with its reports in Digitala Stadsmuseet | Stadsmuseet i Stockholm | Written permission from Stadsmuseet, 2026-10-19: free use with the source credited | The "Building archaeology" section on a pinned card in Gamla stan and on Riddarholmen: medieval walls, timber dated by tree rings, the investigations' years and their reports; construction years cited by hand from the reports it links | Stads- och byggnadsarkeologiskt register: Stadsmuseet i Stockholm, används med tillstånd / used with permission, bearbetad / processed |
| Bygglov 1875–1980 (the card index to the City's building-permit files) | Stockholms stadsarkiv | Written answer from Stockholms stadsarkiv, 2026-10-20: the data may be used and spread freely | The year a property's first building permit was closed, on the property's one main building, where it measured right (mostly houses in the suburbs, which show only their decade) | Bygglov 1875–1980: Stockholms stadsarkiv, används med tillstånd / used with permission, bearbetad / processed |
| Wikimedia Commons photos | Each photographer | Per file (CC BY-SA, CC BY, CC0 or public domain) | One photo on a notable building's card | Each photo is credited on the card with its author and licence |

Notes:

- The Lantmäteriet terrain model is optional. Without a login, the terrain comes from the Stadskarta contour lines, and the Lantmäteriet credit is not shown.
- The laser points are optional too. They are read only around landmarks, churches and tall buildings, never around private houses, and stay on the build machine: Lantmäteriet's terms note that the points may contain personal data, so only the derived tower outlines and heights are published. Without them, or when a build draws no tower, their credit is not shown.
- Only photos under licences that allow reuse are used, and each is credited where it appears.
- Excerpts are cut from the article's introduction and link back to it, so the share-alike terms carry with them.
- The construction years cited by hand are listed in [`pipeline/gamla_stan_years.csv`](pipeline/gamla_stan_years.csv), one row per building with its source and the page it cites (two rows where two sources give different years, and one more for each later rebuild a source names). So that each year can be checked, a row from Wikipedia or KulturNav keeps a short quotation of the sentence or entry it relies on (at most 25 words), linked to that revision or entry. A Wikipedia quotation is the article's own words, never a passage the article quotes from another work: where an article quotes a museum report, the row cites the report. Those quotations are Wikipedia's (CC BY-SA 4.0) or KulturNav's (CC0), not covered by this repository's MIT licence. They never reach the map: the card names the source and links it. A row from the City Museum keeps only the document, the page and our own one-line reason, never the museum's text. Where a source gives only a century or a period, the card shows it with "≈" in the colour of the map period that holds at least three quarters of it. Where two sources differ, the card shows both readings, each linked to its source, and a rebuild a source names is shown beside the year, never in its place. The same file holds the newer blocks in Hjorthagen: there the year is the move-in years the City gives for the building stage the block is part of ("Built 2014–2017"), because no source dates the single buildings.
- The building-permit years come from the City Archives' card index, harvested once from its search app. Only one year per building ships. The property designations, case numbers and card ids are used to match the cards and are never published, and nothing links a building to its card. A house built after 1980 on an older property can sometimes show the earlier house's permit year; "Something wrong?" on its card reports it.
- The City Museum's building-archaeology register is used with its written permission, not an open licence. The card states the register's facts in the map's own words, from its structured fields, and links each report; it never copies the museum's descriptions or shows a property designation. The register's records date building parts and investigations, not the house, so they never set a building's year or colour. A report the register links can: where we have read the report and cite it by hand (the table above), the building gets the period the report gives, shown with "≈", and the card links the report. In Swedish: Stadsmuseets byggnadsarkeologiska register används med museets skriftliga tillstånd. Kortet återger registrets uppgifter med egna ord och länkar till rapporterna. Registrets poster sätter aldrig husets byggår eller färg; en rapport som registret länkar kan göra det, där vi har läst rapporten och citerar den för hand, och då visas perioden med "≈" och kortet länkar till rapporten.

## Coordinate systems

The City's data uses SWEREF 99 18 00 (EPSG:3011), which the pipeline works in. Lantmäteriet and RAÄ publish in SWEREF 99 TM (EPSG:3006); the pipeline reprojects them.

## Adding a source

A new source needs an entry in `pipeline/sources.yml` with its URL, publisher, licence and an `attribution` line in the form above. See [Contributing](CONTRIBUTING.md).
