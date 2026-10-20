# How the years work

Every building on the map is coloured by the year it was built. No single dataset dates all of Stockholm, so each building takes its year from the best source that has one, a few houses are estimated, and the rest are honestly marked "Year unknown". This page explains the rules. The measured numbers for the current build are on the site, in the [About panel's accuracy section](https://husforhus.se/#about/accuracy), and `uv run python -m pipeline.report_accuracy` writes the full report for a build of your own; the figures below come from the build of October 2026 and change a little with each build.

## The year tiers

A building can be dated by several sources. The pipeline (`s02_years`) takes the first one in this order:

| Tier | Source | What it is |
|---|---|---|
| 1. Curated | A hand-checked list of landmarks (`pipeline/landmarks.py`) | Notable buildings whose year we state ourselves, each tied to a Wikipedia article that is checked automatically before every build. |
| 2. RAÄ | The National Heritage Board's building register (Bebyggelseregistret) | The main source: a surveyed construction year or span for about 22,000 buildings. |
| 3. RAÄ, older file | An older release of the same register | Years the current register no longer carries, for about 800 buildings. |
| 4. Cited record | Published records checked by hand (`pipeline/gamla_stan_years.csv`): KulturNav, Swedish Wikipedia, the City Museum's building inventories and the reports its register links | A year, a decade, or the century or period the record gives, in its own words ("about 1640", "the late 1600s", "medieval origin"); where two records differ, the card shows both ("Built in 1785 or 1798 (sources differ)"), each linked, and the building gets a period's colour only where that period holds three quarters of the two readings, each counting the same; a pinned card adds the rebuilds and extensions the records name, and any other house the footprint holds ("Also part of this building: a house built 1804"); so far about 160 buildings, in Gamla stan and on Riddarholmen. Each is matched to its footprint by hand, and the card links the record. It gives way to the curated list and RAÄ, and replaces an area, Wikidata or OpenStreetMap year, except that a century or period never replaces a Wikidata or OpenStreetMap year that falls inside it. |
| 5. RAÄ, area | The same register, for a whole district or estate | Buildings inside an area that RAÄ dates as a whole take the area's year. |
| 6. Wikidata | The "inception" or "opening" date of a building item | Matched to a footprint by the item's coordinates, or by a hand-checked pin where the coordinates fall in the house next door. |
| 7. OpenStreetMap | The `start_date` tag and its variants | Matched to a footprint by position. |
| 8. Estimate | Similar dated buildings nearby | Houses only, and only where the method is measured to work. See below. |
| — | None | "Year unknown". |

The curated list comes first because a register can date the *site* rather than the building standing today: RAÄ dates the Royal Palace (Stockholms slott) to the 1100s, while the palace you see was completed in 1754.

Roughly: 30% of buildings have a year from a record (tiers 1–4, 6, 7), 8% the year of their area, 6% are estimated, and about 56% stay unknown.

### Which year, when the record gives a span

A record may give one year or a span of construction years. The map shows the exact year when there is one, the last year of the span when the span is 15 years or shorter (roughly, when the building was finished), and the first year of a longer span.

A record checked by hand may give only a century or a period ("built in the 1600s", "medieval"). The map then shows that period with "≈", in the muted colour of the estimates, but only when one of the twelve periods below holds at least three quarters of the record's span: "the 1600s" is 89% Stormaktstiden, while "the beginning of the 1600s" straddles the 1610/1611 boundary, so that building gets no colour, and its card gives what the record says. A medieval cellar under a house counts as a medieval origin, shown with the later rebuilds the records name. On the timeline such a building appears in the middle of that period's part of the span (a house of the 1600s in 1655); a medieval one, whose record gives no earliest year, appears in 1520, by when it stood.

## The twelve periods

Colours follow twelve periods of Stockholm's building history:

| Period | Years |
|---|---|
| Medieval & early Vasa | until 1610 |
| Stormaktstiden | 1611–1718 |
| Frihetstid & Gustavian | 1719–1809 |
| Early 1800s | 1810–1865 |
| Stenstaden | 1866–1889 |
| Jugend & national romanticism | 1890–1919 |
| Swedish Grace | 1920–1929 |
| Funkis | 1930–1945 |
| Folkhem & ABC towns | 1946–1964 |
| Million Programme & city clearance | 1965–1975 |
| Postmodern & infill | 1976–1993 |
| Waterfront districts | 1994 on |

## Estimates

For a house with no year, the pipeline looks at the 20 most similar dated buildings nearby (similar in position, height, footprint and building type, with the same city block counting a little extra) and takes their typical year, weighting the closest and most similar most. This is a nearest-neighbours method; its settings are in `pipeline/city.py` (`ESTIMATE`).

### How it is tested

Every dated building is estimated as if it had no year, from the others, with whole city blocks held out together so a building never learns from its own block. The results are grouped into *cells* by building type, era and inner or outer city. For each cell the test measures how often the estimate lands in the right period and the *band*: the ± range around the estimate that 8 in 10 true years fall inside.

### When the map shows an estimate

Only when all of these hold:

- the building is a house (villa, row or chain house);
- a dated building stands within 100 m;
- the City first mapped it before 2008, and its property unit was not formed late (both are signs of new development);
- its cell has at least 30 test buildings, at least 70% of them in the right period, and a band of ±15 years or less.

Everything else stays unknown. The map never paints a period it cannot back with a year, or with a published record's century or span that one period holds at least three quarters of.

### Why so strict

The test can only use buildings that already have a year, and those are mostly older. The undated buildings are by construction the ones the heritage register skipped, and many of them are new. A new building among old neighbours gets its neighbours' age: an early version of the map showed parts of a 2000s waterfront district as 1930s functionalism. Apartment blocks and other types were too often wrong, so only houses, where the method measured about 80% in the right period, are estimated.

An independent check runs the same rule on buildings dated only by Wikidata or OpenStreetMap, using RAÄ and the curated list alone. It is small, but it confirms that the rule keeps buildings from 1990 or later off the map as estimates.

### How estimates look

Estimated years, area years and a record's century or period are drawn in a duller, darker version of their period's colour, and the card shows "≈" before the decade, the century or the period. A switch in the legend hides them all.

## Private houses show only a decade

Villas, row and chain houses and allotment cottages are people's homes. For these the card shows only the decade (for example "1950s", or "≈ 1950s" when estimated), never an exact year, even when a record has one. The colour still shows the period; when a period starts or ends inside the decade, the card narrows the decade to the part inside that period.

The same reasoning removes anything else on the card that could reveal the exact year or point at the owners: a private house gets no Wikidata item, Wikipedia link, excerpt or photo, its name appears only if a person has checked it, and an architect named on only a few buildings citywide is left off. A notable house can still get its full card by joining the curated landmark list, where a person has checked it by hand.

A private house's street address is shown on its card and search finds it, because an address names no one and the card still gives only the decade. Owners are never shown. See [Privacy](PRIVACY.md).

## Buildings taken off the map

Anyone can ask for a building's details to be taken off the map, without giving a reason (see [Privacy](PRIVACY.md)). Such a building keeps its shape, its height and its district, and is drawn as "Year unknown". Its year and source, name, architects, heritage rating, protection, addresses, Wikidata item, photo and excerpt are removed when the data is next rebuilt, so neither its card nor search shows them. The list of these buildings is kept out of the repository, because it would itself say which homes asked.

## Buildings with no year

They stand on the map at "Today", so the opening view shows the whole city, and drop out when you look at the past. A switch in the legend's "Year unknown" row shows or hides them at every year.
