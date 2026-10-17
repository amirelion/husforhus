"""Year, source and floors codes. Mirrored in web/codes.js;
web/test/codes.test.mjs checks the mirror both ways."""

# yflag: how the year is known. Value 5 is retired: it was DECADE; private houses now carry the separate `private` flag.
EXACT, RANGE, LONG, AREA, ESTIMATE, PERIOD, UNKNOWN = 0, 1, 2, 3, 4, 6, 7
# With ysrc SRC_CURATED, RANGE means "construction period": year is the curated completion year, whatever the span.
# ESTIMATE: year is the kNN estimate, year_from/year_to = year -/+ the cell's band, clamped to 1000..2026.
# PERIOD: the cell's band is wider than +-15 years, so only the period is shown. year is still the estimate (the
# timeline needs one); year_from/year_to are the period's first and last year (the last capped at 2026).
# Private houses keep their yflag (EXACT, RANGE, LONG, AREA, ESTIMATE or PERIOD) and set years.parquet
# `private` = True; their published year is the decade start, year_from = year, year_to = year + 9.

# ysrc: where it came from. Pairs with yflag (s99 checks it): SRC_NONE <-> UNKNOWN; SRC_RAA_AREA <-> AREA;
# SRC_ESTIMATE <-> ESTIMATE or PERIOD; every other source <-> EXACT, RANGE or LONG.
SRC_NONE, SRC_CURATED, SRC_RAA, SRC_RAA_AREA, SRC_WIKIDATA, SRC_ESTIMATE = 0, 1, 2, 3, 4, 5
SRC_RAA_OLD, SRC_OSM = 6, 7
# fsrc: floors source.
FLOORS_OSM, FLOORS_HEIGHT = 0, 1
# rating (Stadsmuseet klassificering): 0 none, 1 Blått, 2 Grönt, 3 Gult
RATING = {"Blått": 1, "Grönt": 2, "Gult": 3}
# prot: legal protection from RAÄ's skyddstyp_namn (the card's "Protected" row). "Identifierat
# kulturvärde" (an identified value, no legal force) is no protection and reads 0.
PROT_NONE, PROT_STATE, PROT_LISTED, PROT_CHURCH = 0, 1, 2, 3
PROTECTION = {"Statligt byggnadsminne": PROT_STATE, "Byggnadsminne": PROT_LISTED, "Kyrkligt kulturminne": PROT_CHURCH}
