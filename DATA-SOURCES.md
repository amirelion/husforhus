# Data sources

Hus för hus uses only openly licensed data, and one register used with its publisher's written permission. Every source is credited in one form, whatever its licence:

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
| Wikipedia (Swedish and English) | Wikipedia contributors | CC BY-SA 4.0 | Short excerpts on building cards; the citations behind the curated landmarks | Wikipedia: © Wikipedia contributors, CC BY-SA 4.0, bearbetad / processed |
| Stads- och byggnadsarkeologiskt register, with its reports in Digitala Stadsmuseet | Stadsmuseet i Stockholm | Written permission from Stadsmuseet, 2026-10-19: free use with the source credited | The "Building archaeology" section on a pinned card in Gamla stan and on Riddarholmen: medieval walls, timber dated by tree rings, the investigations' years and their reports | Stads- och byggnadsarkeologiskt register: Stadsmuseet i Stockholm, används med tillstånd / used with permission, bearbetad / processed |
| Wikimedia Commons photos | Each photographer | Per file (CC BY-SA, CC BY, CC0 or public domain) | One photo on a notable building's card | Each photo is credited on the card with its author and licence |

Notes:

- The Lantmäteriet terrain model is optional. Without a login, the terrain comes from the Stadskarta contour lines, and the Lantmäteriet credit is not shown.
- The laser points are optional too. They are read only around landmarks, churches and tall buildings, never around private houses, and stay on the build machine: Lantmäteriet's terms note that the points may contain personal data, so only the derived tower outlines and heights are published. Without them, or when a build draws no tower, their credit is not shown.
- Only photos under licences that allow reuse are used, and each is credited where it appears.
- Excerpts are cut from the article's introduction and link back to it, so the share-alike terms carry with them.
- The City Museum's building-archaeology register is used with its written permission, not an open licence. The card states the register's facts in the map's own words, from its structured fields, and links each report; it never copies the museum's descriptions or shows a property designation. The register dates building parts and investigations, not the house, so it never changes a building's year or colour. In Swedish: Stadsmuseets byggnadsarkeologiska register används med museets skriftliga tillstånd. Kortet återger registrets uppgifter med egna ord och länkar till rapporterna; det ändrar aldrig husets byggår eller färg.

## Coordinate systems

The City's data uses SWEREF 99 18 00 (EPSG:3011), which the pipeline works in. Lantmäteriet and RAÄ publish in SWEREF 99 TM (EPSG:3006); the pipeline reprojects them.

## Adding a source

A new source needs an entry in `pipeline/sources.yml` with its URL, publisher, licence and an `attribution` line in the form above. See [Contributing](CONTRIBUTING.md).
