# How the years are known, and how good the estimates are (build v20261021-fx5 of 2026-10-21)

## In short

This map shows 77,743 buildings in Stockholm. Of them:

- **34,877 (44.9%) have a year from a record**: RAÄ's building registers (RAÄ is Sweden's National Heritage Board), a short hand-checked list of landmarks, a published record checked by hand (KulturNav, Swedish Wikipedia, the City Museum or the City's stage years), the City Archives' building permits, Wikidata, OpenStreetMap or a reader's report the map's maker checked (113 of them only to a century or a period, or to two readings where sources differ, shown with ≈).
- **6,263 (8.0%) have the year of their area**: they stand in a district or an estate that RAÄ dates as a whole.
- **1,571 (2.0%) are estimated** from similar dated buildings nearby, shown as an estimated decade ("≈ 1950s"), because every estimated house is a private house, which shows only its decade. Only houses (villa, row, chain) are estimated: for apartment blocks, a new building among older ones too often takes its neighbours' age, and the other types are below 70% right in the test itself.
- **35,032 (45.1%) stay unknown** and are shown as "Year unknown" (pale and hatched in the default look).

How far to trust the estimates: in the test, 82% of the test houses in the cells the map uses were estimated in the right period (6,043 of 7,373), but the test can only use buildings that already have a year, and those are mostly older. A new building among older neighbours is the estimate's blind spot, because it gets its neighbours' age. So the map estimates only houses (villa, row, chain), and none on property units formed late or first mapped by the City in 2008 or later. The independent check further down shows the rule keeping every building from 1990 or later in it off the map, but it is too small to confirm the test's figure.

## Where the years come from

| Source | Buildings | Share |
|---|---:|---:|
| A hand-checked list of landmarks | 72 | 0.1% |
| A published record checked by hand (KulturNav, Swedish Wikipedia, the City Museum, the City) | 231 | 0.3% |
| RAÄ's building register (Bebyggelseregistret) | 22,039 | 28.4% |
| RAÄ's older register file (years the current register dropped) | 809 | 1.0% |
| The City Archives' building permits, 1875–1980 (Stadsarkivet) | 11,175 | 14.4% |
| RAÄ, for a whole area (a district or an estate) | 6,263 | 8.0% |
| Wikidata | 131 | 0.2% |
| OpenStreetMap | 418 | 0.5% |
| A reader's report, checked by the map's maker | 2 | 0.0% |
| Estimated from similar dated buildings nearby | 1,571 | 2.0% |
| No source: the year stays unknown, shown as "Year unknown" | 35,032 | 45.1% |
| **All buildings** | **77,743** | **100.0%** |

A year from a record is shown as the record gives it: an exact year (4,439 buildings), the year a building was finished when the record gives a span of up to 15 years (18,125), or the first year of a longer span (1,025); a building-permit year is the year the property's first permit was closed (11,175); where a published record gives only a century or a period, or two records give different years, the map shows that period with ≈ (113), when one of its 12 periods holds at least three quarters of it (of the span between them, for two records). A private house (a villa, a row or chain house, or an allotment cottage) shows only its decade, never its exact year. Its colour still shows its period, so when a period begins or ends within the decade, the colour narrows the decade to the part inside that period, never to fewer than 4 years.

## What the words mean

- A **period** is one of the map's [12 periods](#the-12-periods) of Stockholm's building history, such as Stenstaden (1866–1889) or Funkis (1930–1945). The map colours each building by its period.
- An estimate is **in the right period** when it falls in the same period as the building's true year, and **within one period** when it falls in that period or the one next to it.
- Every estimate has a **band** of ± years, measured by the test: the range around the estimate that 8 in 10 true years fall inside. The true year is **within the band** when it lies between the estimate minus the band and the estimate plus the band. On the map an estimated house shows only a decade, "≈ 1950s". The decade shown is the decade of the estimated year. With a band of ±5 years, 8 in 10 true years lie within 5 years of that year, so the house can also be from the decade before or after the one shown.
- A *kvarter* is a city block, as named in Stockholm's property register.

## How a house is estimated

For a house with no year, the map looks at the 20 most similar dated buildings nearby: similar in where they stand, how tall they are, how big their footprint is and what kind of building they are, with those in the same city block counting a little extra. It takes their typical year, the closest and most similar weighing most.

To test this, every dated building was estimated as if it had no year, from the others, with whole city blocks left out together, in 5 rounds. The results are grouped into cells by building type, by the era the estimate falls in and by inner or outer city. A cell's band is the ± range that 8 in 10 true years fall inside, rounded up to a multiple of 5 years. Checked on buildings kept out of the band's own calculation, the true year fell inside the band 82% of the time (over every building type's measured cells, not houses alone).

The map shows an estimated decade ("≈ 1950s") only when all of these hold:

- it is of a type the map estimates: houses (villa, row, chain);
- a dated building stands within 100 m;
- the City first mapped it before 2008 (a building first mapped later is probably new);
- its property unit was not formed late (such units are mostly new development); a house with no property-unit key passes this check (estimated houses with no key: 167 of 1,684, all of them first mapped before 2008);
- its cell has at least 30 test buildings, puts at least 70% of them in the right period, and has a band of ±15 years or less.

Every other building stays unknown: the map never shows a period on its own. Buildings the map would never estimate (first mapped in 2008 or later, on a property unit formed late, or allotment cottages) still help estimate the others, but the test does not score them.

**Result:** 1,571 houses are estimated. 82% of the test houses in the cells the map uses were estimated in the right period (6,043 of 7,373), and 96% within one period.

### The houses the map estimates, cell by cell

The era is the era the estimate falls in; the city is the inner city (the central districts) or the outer city. The median error is the typical (median) difference between the estimate and the true year, in years.

| Building type | Estimated era | City | Test buildings | Median error | Right period | Within one period | Band | What the map does |
|---|---|---|---:|---:|---:|---:|---:|---|
| Houses (villa, row, chain) | before 1866 | inner | 7 | – | – | – | – | stays unknown: too few to measure |
| Houses (villa, row, chain) | 1866–1919 | outer | 716 | 1 y | 81% | 94% | ±5 | estimated (decade shown) |
| Houses (villa, row, chain) | 1920–1945 | outer | 3,450 | 1 y | 84% | 96% | ±5 | estimated (decade shown) |
| Houses (villa, row, chain) | 1920–1945 | inner | 1 | – | – | – | – | stays unknown: too few to measure |
| Houses (villa, row, chain) | 1946–1975 | outer | 3,207 | 1 y | 80% | 98% | ±5 | estimated (decade shown) |
| Houses (villa, row, chain) | 1976–1993 | outer | 172 | 6 y | 55% | 89% | ±10 | stays unknown: too few right |

### The other building types: measured, not estimated

The same test for every other type. The map leaves all of them unknown.

| Building type | Estimated era | City | Test buildings | Median error | Right period | Within one period | Band | What the map does |
|---|---|---|---:|---:|---:|---:|---:|---|
| Apartment blocks | before 1866 | inner | 150 | 91 y | 29% | 70% | ±155 | stays unknown: type not estimated |
| Apartment blocks | 1866–1919 | outer | 58 | 4 y | 66% | 69% | ±30 | stays unknown: type not estimated |
| Apartment blocks | 1866–1919 | inner | 3,192 | 9 y | 54% | 79% | ±30 | stays unknown: type not estimated |
| Apartment blocks | 1920–1945 | outer | 1,765 | 1 y | 77% | 93% | ±5 | stays unknown: type not estimated |
| Apartment blocks | 1920–1945 | inner | 2,199 | 3 y | 55% | 83% | ±25 | stays unknown: type not estimated |
| Apartment blocks | 1946–1975 | outer | 2,634 | 2 y | 81% | 96% | ±5 | stays unknown: type not estimated |
| Apartment blocks | 1946–1975 | inner | 73 | 9 y | 52% | 81% | ±25 | stays unknown: type not estimated |
| Apartment blocks | 1976–1993 | outer | 101 | 0 y | 69% | 80% | ±20 | stays unknown: type not estimated |
| Outbuildings | before 1866 | inner | 11 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | 1866–1919 | inner | 3 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | 1920–1945 | outer | 8 | – | – | – | – | stays unknown: too few to measure |
| Outbuildings | 1946–1975 | outer | 133 | 3 y | 62% | 97% | ±10 | stays unknown: type not estimated |
| Outbuildings | 1976–1993 | outer | 1 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | before 1866 | inner | 21 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | 1866–1919 | outer | 6 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | 1866–1919 | inner | 104 | 28 y | 29% | 50% | ±130 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1920–1945 | outer | 45 | 16 y | 27% | 58% | ±45 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1920–1945 | inner | 49 | 25 y | 16% | 43% | ±45 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1946–1975 | outer | 164 | 8 y | 52% | 84% | ±20 | stays unknown: type not estimated |
| Public (school, care, sport, church) | 1946–1975 | inner | 6 | – | – | – | – | stays unknown: too few to measure |
| Public (school, care, sport, church) | 1976–1993 | outer | 12 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | before 1866 | inner | 14 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1866–1919 | outer | 4 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1866–1919 | inner | 27 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1920–1945 | outer | 25 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1920–1945 | inner | 17 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1946–1975 | outer | 28 | – | – | – | – | stays unknown: too few to measure |
| Unspecified | 1976–1993 | outer | 1 | – | – | – | – | stays unknown: too few to measure |
| Work (office, shop, industry, utility) | before 1866 | inner | 16 | – | – | – | – | stays unknown: too few to measure |
| Work (office, shop, industry, utility) | 1866–1919 | outer | 6 | – | – | – | – | stays unknown: too few to measure |
| Work (office, shop, industry, utility) | 1866–1919 | inner | 71 | 39 y | 24% | 49% | ±80 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1920–1945 | outer | 63 | 29 y | 14% | 44% | ±55 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1920–1945 | inner | 62 | 23 y | 14% | 52% | ±45 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1946–1975 | outer | 440 | 9 y | 42% | 81% | ±25 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1946–1975 | inner | 40 | 7 y | 52% | 82% | ±15 | stays unknown: type not estimated |
| Work (office, shop, industry, utility) | 1976–1993 | outer | 39 | 6 y | 59% | 80% | ±25 | stays unknown: type not estimated |

## Where the test is weak

The cells mix buildings of many ages. Counted by the period each test building was really built in, the estimate is weakest for the oldest and the newest buildings, which the dated buildings include few of. Built 1994 or later: 0% in the right period (67 test buildings).

| Really built | Test buildings | In the right period | Of them in the cells the map uses | In the right period there |
|---|---:|---:|---:|---:|
| Medieval & early Vasa (until 1610) | 13 | 0 of 13 | 1 | 0 of 1 |
| Stormaktstiden (1611–1718) | 133 | 22% | 11 | 0 of 11 |
| Frihetstid & Gustavian (1719–1809) | 138 | 14% | 7 | 0 of 7 |
| Early 1800s (1810–1865) | 156 | 7% | 5 | 0 of 5 |
| Stenstaden (1866–1889) | 891 | 40% | 6 | 1 of 6 |
| Jugend & national romanticism (1890–1919) | 2,782 | 73% | 653 | 89% |
| Swedish Grace (1920–1929) | 1,733 | 62% | 825 | 73% |
| Funkis (1930–1945) | 5,430 | 82% | 2,539 | 91% |
| Folkhem & ABC towns (1946–1964) | 5,105 | 80% | 2,211 | 85% |
| Million Programme & city clearance (1965–1975) | 2,040 | 49% | 1,033 | 66% |
| Postmodern & infill (1976–1993) | 653 | 29% | 70 | 0% |
| Waterfront districts (1994 on) | 67 | 0% | 12 | 0 of 12 |

## The independent check

The test above can only use buildings that already have a year, and most of them are old. So the map's own rule was also run on the 549 buildings that only Wikidata or OpenStreetMap date, as if they had no year, estimating them from the buildings RAÄ and the hand-checked list date and nothing else. They are not a fair sample of the buildings the map estimates: RAÄ dated most of the older buildings, so the ones left to Wikidata and OpenStreetMap are often new, and 219 of the 549 were built in 1990 or later.

Result: the map would show 10 of them as an estimate: 6 in the right period and 7 with the true year inside the band; the other 539 would stay unknown. That is too few for a percentage (the rule needs 30), so the counts stand as they are. The rule leaves a building unknown when it is not of a type the map estimates, stands more than 100 m from a dated building, was first mapped in 2008 or later, stands on a property unit formed late, or falls in a cell that is not good enough.

- Built before 1990: 6 of 10 in the right period, 7 of 10 inside the band.
- Built in 1990 or later: none would show as an estimate (219 buildings).

## How good the area years are

Where a building in a RAÄ-dated area also has a year of its own, the two can be compared: 39 buildings. The area's year was in the right period for 77% of them; the typical (median) difference between the two was 1 years.

## The building-permit years (Stockholm City Archives)

11,175 buildings get their year from the City Archives' (Stadsarkivet's) card index of building permits, 1875–1980. The year is the year the property's first building permit was closed. The map puts it only on a property's one main building, on a property with at most 6 footprints. It uses it only in kinds of building where, among at least 30 test buildings, the permit year fell in the right period at least 85% of the time and in the same decade at least 70%. It never replaces a year from another record. All of them are private houses, so they show only their decade.

**It can be wrong.** A house built after 1980 on an older property can sometimes show the earlier house's permit year. If you see one, please report it with "Something wrong?" on its card.

| What the footprint had before | Footprints dated |
|---|---:|
| Year unknown | 8,188 |
| An estimate ("≈") | 2,987 |
| **All** | **11,175** |

The tier could fill 47,778 footprints. Why the others got no permit year:

| Why no permit year | Footprints |
|---|---:|
| No property designation | 3,763 |
| A joint property | 15 |
| Not a main building (an outbuilding, a garage, a shed, a substation) | 2,946 |
| Two or more main buildings on the property | 9,342 |
| More than 6 footprints on the property (an estate) | 2 |
| In Gamla stan or on Riddarholmen (every building there is older than the index) | 120 |
| First mapped by the City in 2008 or later | 1,703 |
| On a property unit formed late | 1,996 |
| No permit card names the property | 7,911 |
| Only cards without a closing year | 504 |
| A card without a closing year beside the others (the first case may be undated) | 691 |
| Its first permit is more than 10 years from the rest of its block's | 4,344 |
| Many properties in its block have no card (rebuilt or renumbered after the index) | 2,660 |
| A kind of building where the permit years did not measure right | 606 |

### The test, cell by cell

Each test building has a year from a building record (RAÄ, RAÄ's older register, the hand-checked landmarks or a published record checked by hand) and gets its permit year by the same rules. The cells split them by building type, inner or outer city, the era of the permit year, and whether the property's cards make one case or several ("episodes": cards more than five years after the first start another).

| Building type | Era of the permit year | City | Episodes | Test buildings | Right period | Same decade | Within ±3 years | What the map does |
|---|---|---|---|---:|---:|---:|---:|---|
| Apartment blocks | 1920–1945 | outer | one | 770 | 99% | 99% | 99% | not used: type not dated |
| Apartment blocks | 1920–1945 | outer | two or more | 228 | 93% | 94% | 94% | not used: type not dated |
| Apartment blocks | 1946–1975 | outer | one | 541 | 81% | 86% | 85% | not used: too few right |
| Apartment blocks | 1946–1975 | outer | two or more | 132 | 80% | 82% | 79% | not used: too few right |
| Apartment blocks | 1866–1919 | inner | one | 50 | 96% | 96% | 96% | not used: type not dated |
| Apartment blocks | 1866–1919 | inner | two or more | 1,088 | 83% | 79% | 81% | not used: too few right |
| Apartment blocks | 1920–1945 | inner | one | 685 | 99% | 94% | 98% | not used: type not dated |
| Apartment blocks | 1920–1945 | inner | two or more | 681 | 97% | 95% | 96% | not used: type not dated |
| Apartment blocks | 1946–1975 | inner | one | 32 | 44% | 62% | 41% | not used: too few right |
| Houses (villa, row, chain) | 1866–1919 | outer | one | 101 | 99% | 98% | 98% | dates |
| Houses (villa, row, chain) | 1866–1919 | outer | two or more | 249 | 98% | 98% | 98% | dates |
| Houses (villa, row, chain) | 1920–1945 | outer | one | 1,575 | 99% | 99% | 99% | dates |
| Houses (villa, row, chain) | 1920–1945 | outer | two or more | 1,468 | 95% | 95% | 95% | dates |
| Houses (villa, row, chain) | 1946–1975 | outer | one | 1,711 | 92% | 91% | 91% | dates |
| Houses (villa, row, chain) | 1946–1975 | outer | two or more | 541 | 93% | 93% | 91% | dates |
| Houses (villa, row, chain) | 1976–1993 | outer | one | 42 | 26% | 74% | 26% | not used: too few right |
| Work (office, shop, industry, utility) | 1946–1975 | outer | one | 66 | 86% | 77% | 80% | not used: type not dated |
| Work (office, shop, industry, utility) | 1946–1975 | outer | two or more | 44 | 77% | 61% | 61% | not used: too few right |

23 more cells have fewer than 30 test buildings (151 in all), too few to measure: they date nothing.

On the 5,645 test buildings in the cells the map uses, the permit year fell in the right period for 95% and in the same decade for 95%; it was the record's year exactly for 86%.

### The blind spot

Most test buildings are old. A building from 1981 or later stands on a property whose permit cards are all older, so any permit year it gets is wrong: it is the earlier house's. Of the 321 buildings from 1981 or later that have a record year and pass the footprint rules, **13 (4.0%) would get a permit year**. The build fails its checks when this is over 5%. Readers can correct such a house with "Something wrong?".

### The estimate against the permit years

On 2,987 of the permit-dated footprints the estimate tier would have given an estimate. Run there as if they had no year, its estimate fell in the permit year's period for 77% and in its decade for 70% (a typical difference of 2 years). These are the houses the estimate tier actually estimates, so this is a check of both on the same houses, outside the record-dated ones.

### Against the other sources

- Wikidata dates 1 footprint the permit years would also date, and keeps its year there: 1 of 1 share the period, and 0 lie more than 10 years apart (listed for a hand check).
- OpenStreetMap dates 27 footprints the permit years would also date, and keeps its year there: 26 of 27 share the period, and 1 lies more than 10 years apart (listed for a hand check).

**Why the test may flatter it.** RAÄ very likely read many of its house years from these same permit files, so a permit year agreeing with RAÄ is partly the files agreeing with themselves. The blind spot and the estimate check do not depend on RAÄ, which is why they are shown.

## Gamla stan

Gamla stan, the old town, is shown on its own because it is the oldest part of the city and where many visitors look first. Of its 430 buildings, 255 have a year from a record, 0 the year of their area, 0 are estimated and 175 stay unknown.

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
| A Wikidata year more than 10 years from the permit year (Wikidata's kept) | 0 |
| An OpenStreetMap year more than 10 years from the permit year (OpenStreetMap's kept) | 1 |

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

Generated by `pipeline/report_accuracy.py` from build v20261021-fx5; do not edit by hand. The first measurements of the method are in [the estimates prototype note](research/2026-10-15-estimates-prototype.md).
