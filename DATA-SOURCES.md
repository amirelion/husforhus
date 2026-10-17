# Data sources

Hus för hus uses only openly licensed data. Every source is credited in one form, whatever its licence:

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
| Wikipedia (Swedish and English) | Wikipedia contributors | CC BY-SA 4.0 | Short excerpts on building cards; the citations behind the curated landmarks | Wikipedia: © Wikipedia contributors, CC BY-SA 4.0, bearbetad / processed |
| Wikimedia Commons photos | Each photographer | Per file (CC BY-SA, CC BY, CC0 or public domain) | One photo on a notable building's card | Each photo is credited on the card with its author and licence |

Notes:

- The Lantmäteriet terrain model is optional. Without a login, the terrain comes from the Stadskarta contour lines, and the Lantmäteriet credit is not shown.
- Only photos under licences that allow reuse are used, and each is credited where it appears.
- Excerpts are cut from the article's introduction and link back to it, so the share-alike terms carry with them.

## Coordinate systems

The City's data uses SWEREF 99 18 00 (EPSG:3011), which the pipeline works in. Lantmäteriet and RAÄ publish in SWEREF 99 TM (EPSG:3006); the pipeline reprojects them.

## Adding a source

A new source needs an entry in `pipeline/sources.yml` with its URL, publisher, licence and an `attribution` line in the form above. See [Contributing](CONTRIBUTING.md).
