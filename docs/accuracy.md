# How the years are known, and how good the estimates are (build v20261020-p4q of 2026-10-20)

## In short

This map shows 77,743 buildings in Stockholm. Of them:

- **23,470 (30.2%) have a year from a record**: RAÄ's building registers (RAÄ is Sweden's National Heritage Board), a short hand-checked list of landmarks, Wikidata, OpenStreetMap or a reader's report the map's maker checked.
- **6,263 (8.0%) have the year of their area**: they stand in a district or an estate that RAÄ dates as a whole.
- **4,558 (5.9%) are estimated** from similar dated buildings nearby, shown as an estimated decade ("≈ 1950s"), because every estimated house is a private house, which shows only its decade. Only houses (villa, row, chain) are estimated: for apartment blocks, a new building among older ones too often takes its neighbours' age, and the other types are below 70% right in the test itself.
- **43,452 (55.9%) stay unknown** and are shown as "Year unknown" (pale and hatched in the default look).

How far to trust the estimates: in the test, 82% of the test houses in the cells the map uses were estimated in the right period (6,111 of 7,450), but the test can only use buildings that already have a year, and those are mostly older. A new building among older neighbours is the estimate's blind spot, because it gets its neighbours' age. So the map estimates only houses (villa, row, chain), and none on property units formed late or first mapped by the City in 2008 or later. The independent check further down shows the rule keeping every building from 1990 or later in it off the map, but it is too small to confirm the test's figure.

## Where the years come from

| Source | Buildings | Share |
|---|---:|---:|
| A hand-checked list of landmarks | 72 | 0.1% |
| RAÄ's building register (Bebyggelseregistret) | 22,039 | 28.4% |
| RAÄ's older register file (years the current register dropped) | 809 | 1.0% |
| RAÄ, for a whole area (a district or an estate) | 6,263 | 8.0% |
| Wikidata | 131 | 0.2% |
| OpenStreetMap | 418 | 0.5% |
| A reader's report, checked by the map's maker | 1 | 0.0% |
| Estimated from similar dated buildings nearby | 4,558 | 5.9% |
| No source: the year stays unknown, shown as "Year unknown" | 43,452 | 55.9% |
| **All buildings** | **77,743** | **100.0%** |

A year from a record is shown as the record gives it: an exact year (4,416 buildings), the year a building was finished when the record gives a span of up to 15 years (18,031), or the first year of a longer span (1,023). A private house (a villa, a row or chain house, or an allotment cottage) shows only its decade, never its exact year. Its colour still shows its period, so when a period begins or ends within the decade, the colour narrows the decade to the part inside that period, never to fewer than 4 years.

## What the words mean

- A **period** is one of the map's [12 periods](#the-12-periods) of Stockholm's building history, such as Stenstaden (1866–1889) or Funkis (1930–1945). The map colours each building by its period.
- An estimate is **in the right period** when it falls in the same period as the building's true year, and **within one period** when it falls in that period or the one next to it.
- Every estimate has a **band** of ± years, measured by the test: the range around the estimate that 8 in 10 true years fall inside. The true year is **within the band** when it lies between the estimate minus the band and the estimate plus the band. On the map an estimated house shows only a decade, "≈ 1950s". The decade shown is the decade of the estimated year. With a band of ±5 years, 8 in 10 true years lie within 5 years of that year, so the house can also be from the decade before or after the one shown.
- A *kvarter* is a city block, as named in Stockholm's property register.

## How a house is estimated

For a house with no year, the map looks at the 20 most similar dated buildings nearby: similar in where they stand, how tall they are, how big their footprint is and what kind of building they are, with those in the same city block counting a little extra. It takes their typical year, the closest and most similar weighing most.

To test this, every dated building was estimated as if it had no year, from the others, with whole city blocks left out together, in 5 rounds. The results are grouped into cells by building type, by the era the estimate falls in and by inner or outer city. A cell's band is the ± range that 8 in 10 true years fall inside, rounded up to a multiple of 5 years. Checked on buildings kept out of the band's own calculation, the true year fell inside the band 83% of the time (over every building type's measured cells, not houses alone).

The map shows an estimated decade ("≈ 1950s") only when all of these hold:

- it is of a type the map estimates: houses (villa, row, chain);
- a dated building stands within 100 m;
- the City first mapped it before 2008 (a building first mapped later is probably new);
- its property unit was not formed late (such units are mostly new development); a house with no property-unit key passes this check (estimated houses with no key: 167 of 4,558, all of them first mapped before 2008);
- its cell has at least 30 test buildings, puts at least 70% of them in the right period, and has a band of ±15 years or less.

Every other building stays unknown: the map never shows a period on its own. Buildings the map would never estimate (first mapped in 2008 or later, on a property unit formed late, or allotment cottages) still help estimate the others, but the test does not score them.

**Result:** 4,558 houses are estimated. 82% of the test houses in the cells the map uses were estimated in the right period (6,111 of 7,450), and 96% within one period.

### The houses the map estimates, cell by cell

The era is the era the estimate falls in; the city is the inner city (the central districts) or the outer city. The median error is the typical (median) difference between the estimate and the true year, in years.

| Building type | Estimated era | City | Test buildings | Median error | Right period | Within one period | Band | What the map does |
|---|---|---|---:|---:|---:|---:|---:|---|
| Houses (villa, row, chain) | before 1866 | inner | 6 | – | – | – | – | stays unknown: too few to measure |
| Houses (villa, row, chain) | 1866–1919 | outer | 709 | 1 y | 81% | 94% | ±5 | estimated (decade shown) |
| Houses (villa, row, chain) | 1866–1919 | inner | 1 | – | – | – | – | stays unknown: too few to measure |
| Houses (villa, row, chain) | 1920–1945 | outer | 3,469 | 1 y | 84% | 95% | ±5 | estimated (decade shown) |
| Houses (villa, row, chain) | 1920–1945 | inner | 1 | – | – | – | – | stays unknown: too few to measure |
| Houses (villa, row, chain) | 1946–1975 | outer | 3,272 | 1 y | 80% | 98% | ±5 | estimated (decade shown) |
| Houses (villa, row, chain) | 1976–1993 | outer | 175 | 4 y | 58% | 91% | ±10 | stays unknown: too few right |

### The other building types: measured, not estimated

The same test for every other type. The map leaves all of them unknown.

| Building type | Estimated era | City | Test buildings | Median error | Right period | Within one period | Band | What the map does |
|---|---|---|---:|---:|---:|---:|---:|---|
| Apartment blocks | before 1866 | inner | 120 | 84 y | 25% | 69% | ±145 | stays unknown: type not estimated |
| Apartment blocks | 1866–1919 | outer | 53 | 4 y | 58% | 60% | ±35 | stays unknown: type not estimated |
| Apartment blocks | 1866–1919 | inner | 3,200 | 10 y | 52% | 78% | ±30 | stays unknown: type not estimated |
| Apartment blocks | 1920–1945 | outer | 1,809 | 1 y | 75% | 92% | ±5 | stays unknown: type not estimated |
| Apartment blocks | 1920–1945 | inner | 2,199 | 3 y | 55% | 83% | ±20 | stays unknown: type not estimated |
| Apartment blocks | 1946–1975 | outer | 2,578 | 2 y | 81% | 96% | ±10 | stays unknown: type not estimated |
| Apartment blocks | 1946–1975 | inner | 65 | 7 y | 58% | 83% | ±25 | stays unknown: type not estimated |
| Apartment blocks | 1976–1993 | outer | 91 | 0 y | 88% | 96% | ±5 | stays unknown: type not estimated |
| Apartment blocks | 1994 on | outer | 1 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | before 1866 | inner | 12 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | 1866–1919 | inner | 1 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | 1920–1945 | outer | 9 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | 1946–1975 | outer | 132 | 2 y | 66% | 98% | ±10 | stays unknown: type not estimated |
| Outbuildings | 1946–1975 | inner | 1 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | 1976–1993 | outer | 1 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | before 1866 | inner | 24 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | 1866–1919 | outer | 8 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | 1866–1919 | inner | 104 | 27 y | 27% | 54% | ±115 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1920–1945 | outer | 51 | 19 y | 31% | 57% | ±45 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1920–1945 | inner | 45 | 28 y | 13% | 56% | ±45 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1946–1975 | outer | 152 | 7 y | 53% | 89% | ±15 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1946–1975 | inner | 6 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | 1976–1993 | outer | 11 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | before 1866 | inner | 11 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1866–1919 | outer | 4 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1866–1919 | inner | 31 | 22 y | 42% | 64% | ±115 | stays unknown: type not estimated |
| Unspecified | 1920–1945 | outer | 22 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1920–1945 | inner | 17 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1946–1975 | outer | 31 | 23 y | 39% | 52% | ±50 | stays unknown: type not estimated |
| Unspecified | 1976–1993 | outer | 3 | – | – | – | – | stays unknown: too few to measure |
| Work (office, shop, industry, utility) | before 1866 | inner | 16 | – | – | – | – | stays unknown: too few to measure |
| Work (office, shop, industry, utility) | 1866–1919 | outer | 7 | – | – | – | – | stays unknown: too few to measure |
| Work (office, shop, industry, utility) | 1866–1919 | inner | 80 | 36 y | 21% | 45% | ±80 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1920–1945 | outer | 69 | 30 y | 19% | 45% | ±50 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1920–1945 | inner | 53 | 25 y | 9% | 49% | ±40 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1946–1975 | outer | 434 | 10 y | 41% | 81% | ±25 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1946–1975 | inner | 42 | 10 y | 43% | 76% | ±20 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1976–1993 | outer | 43 | 9 y | 46% | 70% | ±35 | stays unknown: type not estimated |

## Where the test is weak

The cells mix buildings of many ages. Counted by the period each test building was really built in, the estimate is weakest for the oldest and the newest buildings, which the dated buildings include few of. Built 1994 or later: 0% in the right period (70 test buildings).

| Really built | Test buildings | In the right period | Of them in the cells the map uses | In the right period there |
|---|---:|---:|---:|---:|
| Medieval & early Vasa (until 1610) | 12 | 0 of 12 | 1 | 0 of 1 |
| Stormaktstiden (1611–1718) | 108 | 13% | 11 | 0 of 11 |
| Frihetstid & Gustavian (1719–1809) | 132 | 16% | 7 | 0 of 7 |
| Early 1800s (1810–1865) | 160 | 8% | 5 | 0 of 5 |
| Stenstaden (1866–1889) | 879 | 39% | 6 | 2 of 6 |
| Jugend & national romanticism (1890–1919) | 2,796 | 71% | 652 | 87% |
| Swedish Grace (1920–1929) | 1,738 | 63% | 822 | 75% |
| Funkis (1930–1945) | 5,422 | 82% | 2,550 | 90% |
| Folkhem & ABC towns (1946–1964) | 5,121 | 80% | 2,245 | 85% |
| Million Programme & city clearance (1965–1975) | 2,071 | 49% | 1,068 | 67% |
| Postmodern & infill (1976–1993) | 660 | 31% | 71 | 0% |
| Waterfront districts (1994 on) | 70 | 0% | 12 | 0 of 12 |

## The independent check

The test above can only use buildings that already have a year, and most of them are old. So the map's own rule was also run on the 549 buildings that only Wikidata or OpenStreetMap date, as if they had no year, estimating them from the buildings RAÄ and the hand-checked list date and nothing else. They are not a fair sample of the buildings the map estimates: RAÄ dated most of the older buildings, so the ones left to Wikidata and OpenStreetMap are often new, and 219 of the 549 were built in 1990 or later.

Result: the map would show 10 of them as an estimate: 6 in the right period and 7 with the true year inside the band; the other 539 would stay unknown. That is too few for a percentage (the rule needs 30), so the counts stand as they are. The rule leaves a building unknown when it is not of a type the map estimates, stands more than 100 m from a dated building, was first mapped in 2008 or later, stands on a property unit formed late, or falls in a cell that is not good enough.

- Built before 1990: 6 of 10 in the right period, 7 of 10 inside the band.
- Built in 1990 or later: none would show as an estimate (219 buildings).

## How good the area years are

Where a building in a RAÄ-dated area also has a year of its own, the two can be compared: 39 buildings. The area's year was in the right period for 77% of them; the typical (median) difference between the two was 1 years.

## Gamla stan

Gamla stan, the old town, is shown on its own because it is the oldest part of the city and where many visitors look first. Of its 430 buildings, 98 have a year from a record, 0 the year of their area, 0 are estimated and 332 stay unknown.

## Wikidata and OpenStreetMap: the hand-check list

Some years from Wikidata and OpenStreetMap are listed for a hand check:

| Listed for a hand check | Count |
|---|---:|
| Got their year from Wikidata alone | 131 |
| … of them placed on the nearest building (the item's point lies outside every footprint) | 37 |
| A Wikidata year more than 10 years from RAÄ's | 29 |
| A Wikidata year more than 10 years from the area's | 2 |
| A Wikidata year more than 10 years from the hand-checked list | 2 |
| An OpenStreetMap year more than 10 years from RAÄ's | 37 |
| Wikidata items with only a century (not used) | 13 |

## The 12 periods

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

---

Generated by `pipeline/report_accuracy.py` from build v20261020-p4q; do not edit by hand. The first measurements of the method are in [the estimates prototype note](research/2026-10-15-estimates-prototype.md).
