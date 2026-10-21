"""Render the year model's accuracy page and the M3 review material.

    uv run python -m pipeline.report_accuracy [--out docs/accuracy.md] [--names-out data/review-years.md]

Reads data/accuracy.json and data/years.parquet (and data/review-years.json, data/buildings.parquet and the
Stadsdelar for the Gamla stan section). docs/accuracy.md (committed, read by the public) explains in plain words how
the map knows each building's year: a short summary with the honest limits, where the years come from (shares by
largest remainder, so they add up to 100%), what the terms mean, how a house is estimated and when the map shows an
estimate (from city.ESTIMATE and the table), the table cell by cell, the test by the period of the true year, the
independent check per map state with its 1990 split, the area check, the building-permit years (accuracy.json's
bygglov block: the rule, why footprints get none, the cells, the test, the blind spot with its plain caveat that a
house built after 1980 can show an older house's permit year, the estimate against the permit years and the other
sources), Gamla stan, the hand-check list's sizes and the 12 periods; it says how far a private house's period colour narrows its decade (fewest_private_years) and how
many estimated houses have no property-unit key, so the late-unit check passes them (no_key, from
data/buildings.parquet). It is aggregate-only: no building name, Wikidata or OSM id, gid, UUID, property designation or
property-unit key (FNR), no per-building year, and no stadsdel name but Gamla stan (the repository goes public at
M11; about 35 Wikidata labels look like addresses or designations; a private house's exact year never leaves data/,
the decade rule for private houses). The Wikidata gains by name go to data/review-years.md, internal (data/ is git-ignored), for the owner's M3 review.
"""
import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq

from . import city
from .codes import ESTIMATE, EXACT, PERIOD, RANGE, SRC_BYGGLOV, SRC_CITED
from .estimate import stadsdel_of
from .s01_load import STADSDELAR
from .s02_years import ACCURACY, BUILDINGS, MIN_PRIVATE_OVERLAP, OUT as YEARS, REVIEW
from .s03_tiles import CURRENT, FLAG_NAMES, SRC_NAMES

DOC = Path("docs/accuracy.md")
NAMES = Path("data/review-years.md")
GAMLA_STAN = "GAMLA STAN"
# Where the years come from, in tier order, in words (the source names of SRC_NAMES never appear on the page).
SOURCES = [("curated", "A hand-checked list of landmarks"),
           ("cited", "A published record checked by hand (KulturNav, Swedish Wikipedia, the City Museum, the City)"),
           ("raa", "RAÄ's building register (Bebyggelseregistret)"),
           ("raa_old", "RAÄ's older register file (years the current register dropped)"),
           ("bygglov", "The City Archives' building permits, 1875–1980 (Stadsarkivet)"),
           ("raa_area", "RAÄ, for a whole area (a district or an estate)"),
           ("wikidata", "Wikidata"),
           ("osm", "OpenStreetMap"),
           ("reader", "A reader's report, checked by the map's maker"),
           ("estimate", "Estimated from similar dated buildings nearby"),
           ("none", 'No source: the year stays unknown, shown as "Year unknown"')]
# The hand-check list (data/review-years.json): its six sizes, in words.
REVIEW_ROWS = [("wikidata_gains", "Got their year from Wikidata alone"),
               ("wikidata_vs_raa", "A Wikidata year more than 10 years from RAÄ's"),
               ("wikidata_vs_area", "A Wikidata year more than 10 years from the area's"),
               ("wikidata_vs_curated", "A Wikidata year more than 10 years from the hand-checked list"),
               ("osm_vs_raa", "An OpenStreetMap year more than 10 years from RAÄ's"),
               ("wikidata_century", "Wikidata items with only a century (not used)"),
               ("bygglov_vs_wikidata", "A Wikidata year more than 10 years from the permit year (Wikidata's kept)"),
               ("bygglov_vs_osm", "An OpenStreetMap year more than 10 years from the permit year (OpenStreetMap's kept)")]


def pct(v) -> str:
    return "–" if v is None else f"{100 * v:.0f}%"


def apportion(counts: list[int], units: int) -> list[int] | None:
    """`units` split in proportion to the counts by largest remainder, so the parts add up to exactly `units`; ties go
    to the earlier count. None for no counts."""
    total = sum(counts)
    if total == 0:
        return None
    scaled = [c * units for c in counts]
    floor = [v // total for v in scaled]
    order = sorted(range(len(counts)), key=lambda i: (-(scaled[i] % total), i))
    for i in order[:units - sum(floor)]:
        floor[i] += 1
    return floor


def share_units(counts: list[int], decimals: int = 1) -> list[int] | None:
    """Each count's share of their total in units of 10**-decimals percent, adding up to exactly 100% (apportion)."""
    return apportion(counts, 100 * 10 ** decimals)


def shares(counts: list[int], decimals: int = 1) -> list[str]:
    """Each count's share of their total, as share_units rounds it, written "8.1%"."""
    units = share_units(counts, decimals)
    return ["–"] * len(counts) if units is None else [f"{v / 10 ** decimals:.{decimals}f}%" for v in units]


# The summary's four kinds as the table's sources (codes.py pairs each yflag with its ysrc; a cited record's century
# or period is PERIOD but from a record, cited_periods)
KIND_SOURCES = [("curated", "cited", "raa", "raa_old", "bygglov", "wikidata", "osm", "reader"), ("raa_area",),
                ("estimate",), ("none",)]


def kind_shares(by_flag: dict, by_src: dict, cited_period: int = 0) -> tuple[list[str], list[str]]:
    """(the four kinds' shares, the sources' shares): the kinds rounded together, then each kind's share split among
    its sources, so a kind and its sources never disagree (a review found one count at 8.0% and
    8.1%) and the summary, the figure people quote, is the closest rounding. cited_period: cited_periods(y)."""
    src = [by_src.get(key, 0) for key, _ in SOURCES]
    kind_counts = list(kinds(by_flag, cited_period))
    if [sum(by_src.get(k, 0) for k in ks) for ks in KIND_SOURCES] != kind_counts:
        raise ValueError("the yflag counts and the ysrc counts disagree: rebuild the years")
    units = share_units(kind_counts)
    if units is None:
        return ["–"] * 4, ["–"] * len(src)
    at = {}
    for ks, u in zip(KIND_SOURCES, units):
        at.update(zip(ks, apportion([by_src.get(k, 0) for k in ks], u) or [0] * len(ks)))
    def tenths(v):
        return f"{v / 10:.1f}%"
    return [tenths(u) for u in units], [tenths(at[key]) for key, _ in SOURCES]


def k_of_n(k: int, n: int, min_cell: int) -> str:
    """'k of n', with the share only when n is large enough for one (min_cell or more)."""
    return f"{k:,} of {n:,} ({100 * k / n:.0f}%)" if n >= min_cell else f"{k:,} of {n:,}"


def counts(y: pd.DataFrame) -> tuple[dict, dict]:
    by_flag = {name: int((y.yflag == code).sum()) for code, name in FLAG_NAMES.items()}
    by_src = {name: int((y.ysrc == i).sum()) for i, name in enumerate(SRC_NAMES)}
    return by_flag, by_src


def cited_periods(y: pd.DataFrame) -> int:
    """How many buildings carry a cited record's century or period (pipeline/cited.py: ysrc cited, yflag PERIOD):
    from a record, though PERIOD like the estimate's period-only years."""
    return int(((y.ysrc == SRC_CITED) & (y.yflag == PERIOD)).sum()) if "ysrc" in y else 0


def kinds(by_flag: dict, cited_period: int = 0) -> tuple[int, int, int, int]:
    """(from a record, by area, estimated, unknown): the four ways the map knows a year. cited_period: the PERIOD
    rows that come from a cited record (cited_periods), counted as from a record."""
    return (by_flag["exact"] + by_flag["range"] + by_flag["long"] + cited_period, by_flag["area"],
            by_flag["estimate"] + by_flag["period"] - cited_period, by_flag["unknown"])


def permit_flags(y: pd.DataFrame) -> tuple[int, int]:
    """(EXACT, RANGE) counts of the permit-dated rows: a closing year with no opening year (EXACT) is not an exact
    construction year, so the page counts them on their own."""
    if "ysrc" not in y:
        return 0, 0
    on = y.ysrc == SRC_BYGGLOV
    return int((on & (y.yflag == EXACT)).sum()), int((on & (y.yflag == RANGE)).sum())


# Why a footprint the permit tier may fill got no year (accuracy.json bygglov skipped), in words, in the rules' order.
PERMIT_SKIPS = [("takedown", "Taken off the map at its owner's request"),
                ("no_designation", "No property designation"),
                ("joint_property", "A joint property"),
                ("not_main", "Not a main building (an outbuilding, a garage, a shed, a substation)"),
                ("several_main", "Two or more main buildings on the property"),
                ("estate", "More than {max_footprints} footprints on the property (an estate)"),
                ("skip_stadsdel", "In Gamla stan or on Riddarholmen (every building there is older than the index)"),
                ("late_prod", "First mapped by the City in {late} or later"),
                ("late_unit", "On a property unit formed late"),
                ("no_card", "No permit card names the property"),
                ("undated_only", "Only cards without a closing year"),
                ("undated_card", "A card without a closing year beside the others (the first case may be undated)"),
                ("block_disagrees", "Its first permit is more than 10 years from the rest of its block's"),
                ("block_uncarded", "Many properties in its block have no card (rebuilt or renumbered after the index)"),
                ("cell", "A kind of building where the permit years did not measure right")]
PERMIT_STATUS = {"dated": "dates", "measured only": "not used: type not dated", "fails": "not used: too few right",
                 "not measurable": "not used: too few to measure"}


def permit_section(bg: dict | None, y: pd.DataFrame, p: dict | None = None) -> list[str]:
    """The building-permit years' section from accuracy.json's bygglov block, in plain words; [] for a build from
    before the tier. Aggregate only, every number from the block or y."""
    if not bg:
        return []
    lines = ["## The building-permit years (Stockholm City Archives)", ""]
    if bg.get("status") != "applied":
        why = ("switched off" if bg.get("status") == "off" else
               "not used: the build had no complete copy of the City Archives' permit index")
        return lines + [f"The building-permit years are {why}, so no building gets one.", ""]
    p = city.ESTIMATE if p is None else p
    on = y.ysrc == SRC_BYGGLOV
    n, private = int(on.sum()), int((on & y.private.astype(bool)).sum()) if "private" in y else 0
    lines += [f"{n:,} buildings get their year from the City Archives' (Stadsarkivet's) card index of building permits, "
              "1875–1980. The year is the year the property's first building permit was closed. The map puts it "
              f"only on a property's one main building, on a property with at most {bg['max_footprints']} footprints. "
              f"It uses it only in kinds of building where, among at least {bg['min_cell']} test buildings, the permit "
              f"year fell in the right period at least {100 * bg['min_right']:.0f}% of the time and in the same decade "
              f"at least {100 * bg['min_decade']:.0f}%. It never replaces a year from another record."
              + ("" if not private else " All of them are private houses, so they show only their decade."
                 if private == n else f" {private:,} of them are private houses, so they show only their decade."), "",
              "**It can be wrong.** A house built after 1980 on an older property can sometimes show the earlier "
              "house's permit year. If you see one, please report it with \"Something wrong?\" on its card.", ""]
    state = bg["written_by_state"]
    lines += ["| What the footprint had before | Footprints dated |", "|---|---:|",
              f"| Year unknown | {state['unknown']:,} |", f"| An estimate (\"≈\") | {state['estimate']:,} |",
              *([f"| Its area's year | {state['area']:,} |"] if bg["fill_area"] or state["area"] else []),
              f"| **All** | **{bg['written']:,}** |", "",
              f"The tier could fill {bg['target']:,} footprints. Why the others got no permit year:", "",
              "| Why no permit year | Footprints |", "|---|---:|"]
    words = {"max_footprints": bg["max_footprints"], "late": p["late_prod_year"]}
    for key, text in PERMIT_SKIPS:
        if bg["skipped"].get(key):
            lines.append(f"| {text.format(**words)} | {bg['skipped'][key]:,} |")
    lines += ["", "### The test, cell by cell", "",
              "Each test building has a year from a building record (RAÄ, RAÄ's older register, the hand-checked "
              "landmarks or a published record checked by hand) and gets its permit year by the same rules. The cells "
              "split them by building type, inner or outer city, the era of the permit year, and whether the "
              "property's cards make one case or several (\"episodes\": cards more than five years after the first "
              "start another).", "",
              "| Building type | Era of the permit year | City | Episodes | Test buildings | Right period | Same decade "
              "| Within ±3 years | What the map does |", "|---|---|---|---|---:|---:|---:|---:|---|"]
    small = [c for c in bg["cells"] if c["status"] == "not measurable"]
    for c in bg["cells"]:
        if c["status"] == "not measurable":
            continue
        label = city.GROUP_LABELS.get(c["group"], c["group"])
        where = "inner" if c["inner"] else "outer"
        ep = "one" if c["episodes"] == 1 else "two or more"
        nums = f"{pct(c['right_period'])} | {pct(c['same_decade'])} | {pct(c['within_3'])}"
        lines.append(f"| {label} | {c['era']} | {where} | {ep} | {c['n']:,} | {nums} | {PERMIT_STATUS[c['status']]} |")
    t = bg["test"]
    lines += [""]
    if small:
        lines += [f"{len(small):,} more cells have fewer than {bg['min_cell']} test buildings "
                  f"({sum(c['n'] for c in small):,} in all), too few to measure: they date nothing.", ""]
    if t.get("used"):
        lines.append(f"On the {t['used']:,} test buildings in the cells the map uses, the permit year fell in the right "
                     f"period for {pct(t['right_period'])} and in the same decade for {pct(t['same_decade'])}; it was "
                     f"the record's year exactly for {pct(t['exact'])}.")
    else:
        lines.append("No cell passes the rule, so no building gets a permit year.")
    bs = bg["blind_spot"]
    share = f" ({100 * bs['dated'] / bs['n']:.1f}%)" if bs["n"] else ""
    lines += ["", "### The blind spot", "",
              "Most test buildings are old. A building from 1981 or later stands on a property whose permit cards are "
              "all older, so any permit year it gets is wrong: it is the earlier house's. Of the "
              f"{bs['n']:,} buildings from 1981 or later that have a record year and pass the footprint rules, "
              f"**{bs['dated']:,}{share} would get a permit year**. The build fails its checks when this is over 5%. "
              "Readers can correct such a house with \"Something wrong?\".", ""]
    ec = bg["estimate_check"]
    lines += ["### The estimate against the permit years", ""]
    if ec.get("status") == "measured":
        lines.append(f"On {ec['n']:,} of the permit-dated footprints the estimate tier would have given an estimate. "
                     "Run there as if they had no year, its estimate fell in the permit year's period for "
                     f"{pct(ec['right_period'])} and in its decade for {pct(ec['same_decade'])} (a typical difference "
                     f"of {ec['median_error']:.0f} years). These are the houses the estimate tier actually estimates, "
                     "so this is a check of both on the same houses, outside the record-dated ones.")
    else:
        lines.append(f"Only {ec.get('n', 0):,} permit-dated footprints would have had an estimate, too few to compare.")
    lines += ["", "### Against the other sources", ""]
    for key, name in (("wikidata", "Wikidata"), ("osm", "OpenStreetMap")):
        o = bg.get("others", {}).get(key)
        if o and o["n"]:
            lines.append(f"- {name} dates {o['n']:,} footprint{'s' if o['n'] != 1 else ''} the permit years would "
                         f"also date, and keeps its year there: {o['same_period']:,} of {o['n']:,} share the period, and "
                         f"{o['listed']:,} lie{'s' if o['listed'] == 1 else ''} more than 10 years apart (listed for a "
                         "hand check).")
        else:
            lines.append(f"- {name} dates no footprint the permit years would also date.")
    lines += ["", "**Why the test may flatter it.** RAÄ very likely read many of its house years from these same "
              "permit files, so a permit year agreeing with RAÄ is partly the files agreeing with themselves. The "
              "blind spot and the estimate check do not depend on RAÄ, which is why they are shown.", ""]
    return lines


def period_years(i: int) -> str:
    """A period's years in words: "until 1610", "1611–1718", ..., "1994 on"."""
    _, _, _, lo, hi, _ = city.PERIODS[i]
    if i == 0:
        return f"until {hi}"
    return f"{lo} on" if i == len(city.PERIODS) - 1 else f"{lo}–{hi}"


def group_words(groups) -> str:
    """Building types in words, from city.GROUP_LABELS ("houses (villa, row, chain)")."""
    words = [city.GROUP_LABELS.get(g, g) for g in sorted(groups)]
    words = [w[0].lower() + w[1:] for w in words]
    return " and ".join(words) if words else "no building"


def fewest_private_years() -> int:
    """The fewest years a private house's period colour can narrow its decade to (final review PRIVACY-1). Where a
    period starts inside a decade, the decade splits in two parts; a part under MIN_PRIVATE_OVERLAP years is never
    shown, because s02_years then takes the period of the decade's middle year. With today's periods: 4 (a 1940s
    house in Folkhem's colour, 1946–1949)."""
    parts = [k for lo in (q[3] for q in city.PERIODS[1:]) if lo % 10 for k in (lo % 10, 10 - lo % 10)]
    return min((k for k in parts if k >= MIN_PRIVATE_OVERLAP), default=10)


def no_key(y: pd.DataFrame, units: pd.DataFrame | None, late: int, noun: str = "houses") -> str:
    """The late-unit check's gap in words (final review ALIGNMENT-2): a house with no property-unit key (FNR 0) passes
    it, and how many estimated buildings have none, with how many of them the City first mapped before `late` (the
    check before it), when units (data/buildings.parquet's gid, fnr and prod_year) is given. Counts only: no key, no
    building."""
    text = "; a house with no property-unit key passes this check"
    if units is None:
        return text
    est = y.gid[y.yflag.isin([ESTIMATE, PERIOD])]
    u = units.set_index("gid").reindex(est)
    none = u[u.fnr.fillna(0) == 0]
    if len(none) == 0:
        return text + f" (every estimated {noun.removesuffix('s')} has a key)"
    before = int(((none.prod_year > 0) & (none.prod_year < late)).sum())
    mapped = "all of them" if before == len(none) else f"{before:,} of them"
    return text + f" (estimated {noun} with no key: {len(none):,} of {len(est):,}, {mapped} first mapped before {late})"


def decade_only(p: dict) -> bool:
    """True when every type the map estimates is a private-house category: then every estimate is published as
    its decade, "≈ 1950s" on the card, and the band is what the test measures, never what the map shows."""
    private = {city.KATEGORI_GROUPS.get(k, "unspecified") for k in city.PRIVATE_HOUSE_KATEGORI}
    return bool(p["estimate_groups"]) and set(p["estimate_groups"]) <= private


def what_the_map_does(c: dict, acc: dict, p: dict) -> str:
    """A cell's status in words, with the reason when the map leaves its buildings unknown."""
    if c["status"] == "estimate":
        return "estimated (decade shown)" if decade_only(p) else "≈ year ± band"
    if c["status"] == "period":
        return "period only"
    if c["status"] == "not measurable":
        return "stays unknown: too few to measure"
    if c["group"] not in p["estimate_groups"]:
        return "stays unknown: type not estimated"
    if c["right_period"] < acc["min_right"]:
        return "stays unknown: too few right"
    return "stays unknown: band too wide"


def cell_rows(cells: list[dict], acc: dict, p: dict) -> list[str]:
    rows = ["| Building type | Estimated era | City | Test buildings | Median error | Right period | Within one period "
            "| Band | What the map does |", "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for c in cells:
        label = city.GROUP_LABELS.get(c["group"], c["group"])
        where = "inner" if c["inner"] else "outer"
        if c["status"] == "not measurable":
            rows.append(f"| {label} | {c['era']} | {where} | {c['n']:,} | – | – | – | – | {what_the_map_does(c, acc, p)} |")
        else:
            rows.append(f"| {label} | {c['era']} | {where} | {c['n']:,} | {c['median_error']:.0f} y | "
                        f"{pct(c['right_period'])} | {pct(c['within_one'])} | ±{c['band']} | {what_the_map_does(c, acc, p)} |")
    return rows


def decade_band(used: list[dict]) -> str:
    """What the band means when the map shows a decade (decade_only): the decade is the estimated year's, and the
    house can be from the next decade over."""
    bands = sorted({c["band"] for c in used})
    width = f"±{bands[0]}" if len(bands) == 1 else f"±{bands[0]} to ±{bands[-1]}"
    within = f"{bands[0]}" if len(bands) == 1 else f"{bands[0]} to {bands[-1]}"
    return (f"On the map an estimated house shows only a decade, \"≈ 1950s\". The decade shown is the decade of the "
            f"estimated year. With a band of {width} years, 8 in 10 true years lie within {within} years of that year, "
            "so the house can also be from the decade before or after the one shown.")


def render(acc: dict, y: pd.DataFrame, review: dict | None, gamla: pd.DataFrame | None, date: str, version: str,
           p: dict | None = None, units: pd.DataFrame | None = None) -> str:
    """The committed page: plain words for the public, aggregate-only (tests/test_report_accuracy.py pins that
    nothing per building is in it). p: the estimator's settings (city.ESTIMATE) the rule is explained from. units:
    data/buildings.parquet's gid, fnr and prod_year, for the count of estimated houses with no property-unit key
    (no_key); None states the rule without a count."""
    p = city.ESTIMATE if p is None else p
    by_flag, by_src = counts(y)
    cp = cited_periods(y)
    n = len(y)
    min_cell = acc["min_cell"]
    rec, area, est, unk = kinds(by_flag, cp)
    (s_rec, s_area, s_est, s_unk), src_shares = kind_shares(by_flag, by_src, cp)
    houses = group_words(p["estimate_groups"])
    noun = "houses" if set(p["estimate_groups"]) == {"house"} else "buildings"
    late = p["late_prod_year"]
    only_period = by_flag["period"] - cp          # the estimate's period-only years, not a record's
    decades = decade_only(p)
    cells = acc.get("cells", [])
    used = [c for c in cells if c["status"] == "estimate"]
    by_period = acc.get("by_true_period", [])
    n_used, right_used = sum(r["n_estimate"] for r in by_period), sum(r["right_estimate"] for r in by_period)
    ext = acc.get("external", {})
    # Why the other types are not estimated: apartment blocks for the blind spot; the rest too, when every one of their
    # measured cells is under min_right in the test itself (M1 b).
    rest = [c for c in cells if c["group"] not in p["estimate_groups"] | {"apartments"} and c["status"] != "not measurable"]
    rest_wrong = bool(rest) and max(c["right_period"] for c in rest) < acc["min_right"]
    figure = (f"in the test, {100 * right_used / n_used:.0f}% of the test {noun} in the cells the map uses were "
              f"estimated in the right period ({right_used:,} of {n_used:,}), but " if n_used else "")
    after = ext.get("from_1990", {})
    if ext.get("n_all") and after.get("n_all") and not after.get("n_estimate"):
        check = ("The independent check further down shows the rule keeping every building from 1990 or later in it "
                 "off the map")
    else:
        check = "The independent check further down shows how many buildings from 1990 or later still get an estimate"
    check += ", but it is too small to confirm the test's figure." if ext.get("status") != "measured" else "."
    lines = [f"# How the years are known, and how good the estimates are (build {version} of {date})", "",
             "## In short", "",
             f"This map shows {n:,} buildings in Stockholm. Of them:", "",
             f"- **{rec:,} ({s_rec}) have a year from a record**: RAÄ's building registers (RAÄ is Sweden's National "
             "Heritage Board), a short hand-checked list of landmarks, a published record checked by hand (KulturNav, "
             "Swedish Wikipedia, the City Museum or the City's stage years), the City Archives' building permits, "
             "Wikidata, OpenStreetMap or a reader's report the map's maker checked"
             + (f" ({cp:,} of them only to a century or a period, or to two readings where sources differ, shown "
                "with ≈)" if cp else "") + ".",
             f"- **{area:,} ({s_area}) have the year of their area**: they stand in a district or an estate that RAÄ "
             "dates as a whole.",
             f"- **{est:,} ({s_est}) are estimated** from similar dated buildings nearby"
             + (f" ({only_period:,} of them with the period only)" if only_period else "")
             + (', shown as an estimated decade ("≈ 1950s"), because every estimated house is a private house, which '
                "shows only its decade" if decades else "")
             + f". Only {houses} are estimated: for apartment blocks, a new building among older ones too often takes "
             "its neighbours' age"
             + (f", and the other types are below {100 * acc['min_right']:.0f}% right in the test itself"
                if rest_wrong else "") + ".",
             f'- **{unk:,} ({s_unk}) stay unknown** and are shown as "Year unknown" '
             "(pale and hatched in the default look).", "",
             f"How far to trust the estimates: {figure}the test can only use buildings that already have a year, "
             "and those are mostly older. A new building among older neighbours is the estimate's blind spot, because "
             f"it gets its neighbours' age. So the map estimates only {houses}, and none on property units formed late "
             f"or first mapped by the City in {late} or later. {check}", ""]

    lines += ["## Where the years come from", "", "| Source | Buildings | Share |", "|---|---:|---:|"]
    src_counts = [by_src[key] for key, _ in SOURCES]
    for (_, words), k, share in zip(SOURCES, src_counts, src_shares):
        lines.append(f"| {words} | {k:,} | {share} |")
    permit_exact, permit_range = permit_flags(y)
    lines += [f"| **All buildings** | **{n:,}** | **{'100.0%' if n else '–'}** |", "",
              f"A year from a record is shown as the record gives it: an exact year "
              f"({by_flag['exact'] - permit_exact:,} buildings), the year a building was finished when the record gives "
              f"a span of up to 15 years ({by_flag['range'] - permit_range:,}), or the first year of a longer span "
              f"({by_flag['long']:,})"
              + (f"; a building-permit year is the year the property's first permit was closed "
                 f"({permit_exact + permit_range:,})" if permit_exact + permit_range else "")
              + (f"; where a published record gives only a century or a period, or two records give different years, "
                 f"the map shows that period with ≈ ({cp:,}), when one of its 12 periods holds at least three quarters "
                 "of it (of the span between them, for two records)" if cp else "")
              + ". A private house (a villa, a row or chain "
              "house, or an allotment cottage) shows only its decade, never its exact year. Its colour still shows "
              "its period, so when a period begins or ends within the decade, the colour narrows the decade to the "
              f"part inside that period, never to fewer than {fewest_private_years()} years.", ""]

    lines += ["## What the words mean", "",
              "- A **period** is one of the map's [12 periods](#the-12-periods) of Stockholm's building history, such "
              "as Stenstaden (1866–1889) or Funkis (1930–1945). The map colours each building by its period.",
              "- An estimate is **in the right period** when it falls in the same period as the building's true year, "
              "and **within one period** when it falls in that period or the one next to it.",
              "- Every estimate has a **band** of ± years, measured by the test: the range around the estimate that 8 "
              "in 10 true years fall inside. The true year is **within the band** when it lies between the estimate "
              "minus the band and the estimate plus the band."
              + (" " + decade_band(used) if decades and used else ""),
              "- A *kvarter* is a city block, as named in Stockholm's property register.", ""]

    shown = [c for c in cells if c["group"] in p["estimate_groups"]]
    other = [c for c in cells if c["group"] not in p["estimate_groups"]]
    n_cells = sum(c["n"] for c in used)
    one = sum(c["within_one"] * c["n"] for c in used) / n_cells if n_cells else None
    never = group_words(p["never_groups"])
    lines += ["## How a house is estimated", "",
              f"For a house with no year, the map looks at the {p['k']} most similar dated buildings nearby: similar "
              "in where they stand, how tall they are, how big their footprint is and what kind of building they "
              "are, with those in the same city block counting a little extra. It takes their typical year, the "
              "closest and most similar weighing most.", "",
              "To test this, every dated building was estimated as if it had no year, from the others, with whole "
              f"city blocks left out together, in {acc['folds']} rounds. The results are grouped into cells by "
              "building type, by the era the estimate falls in and by inner or outer city. A cell's band is the ± "
              f"range that 8 in 10 true years fall inside, rounded up to a multiple of {p['band_step']} years. "
              "Checked on buildings kept out of the band's own calculation, the true year fell inside the band "
              f"{pct(acc.get('band_coverage'))} of the time (over every building type's measured cells, not houses "
              "alone).", "",
              ('The map shows an estimated decade ("≈ 1950s") only when all of these hold:' if decades
               else "The map shows \"≈ year ± band\" only when all of these hold:"), "",
              f"- it is of a type the map estimates: {houses};",
              f"- a dated building stands within {acc['near_m']:g} m;",
              f"- the City first mapped it before {late} (a building first mapped later is probably new);",
              "- its property unit was not formed late (such units are mostly new development)"
              + no_key(y, units, late, noun) + ";",
              f"- its cell has at least {min_cell} test buildings, puts at least {100 * acc['min_right']:.0f}% of them "
              f"in the right period, and has a band of ±{acc['max_band']} years or less.", "",
              ("Every other building stays unknown: the map never shows a period on its own. " if not p["give_period"]
               else "A cell that is right often enough but has a wider band shows the period only. ")
              + f"Buildings the map would never estimate (first mapped in {late} or later, on a property unit formed "
              f"late, or {never}) still help estimate the others, but the test does not score them.", ""]
    result = f"**Result:** {by_flag['estimate']:,} {noun} are estimated"
    result += f" and {only_period:,} get the period only." if only_period else "."
    if n_used:
        result += (f" {100 * right_used / n_used:.0f}% of the test {noun} in the cells the map uses were estimated "
                   f"in the right period ({right_used:,} of {n_used:,}), and {pct(one)} within one period.")
    else:
        result += " No cell passes the rule."
    lines += [result, "",
              f"### The {noun} the map estimates, cell by cell", "",
              "The era is the era the estimate falls in; the city is the inner city (the central districts) or the "
              "outer city. The median error is the typical (median) difference between the estimate and the true "
              "year, in years.", "", *cell_rows(shown, acc, p), "",
              "### The other building types: measured, not estimated", "",
              "The same test for every other type. The map leaves all of them unknown.", "", *cell_rows(other, acc, p),
              ""]

    lines += ["## Where the test is weak", ""]
    if by_period:
        last = len(city.PERIODS) - 1
        newest = by_period[last]
        lead = ("The cells mix buildings of many ages. Counted by the period each test building was really built "
                "in, the estimate is weakest for the oldest and the newest buildings, which the dated buildings "
                "include few of.")
        if newest["n"]:
            right_new = (pct(newest["right"] / newest["n"]) + f" in the right period ({newest['n']:,} test buildings)"
                         if newest["n"] >= min_cell else f"{newest['right']:,} of {newest['n']:,} in the right period")
            lead += f" Built {city.PERIODS[last][3]} or later: {right_new}."
        lines += [lead, "",
                  "| Really built | Test buildings | In the right period | Of them in the cells the map uses | "
                  "In the right period there |", "|---|---:|---:|---:|---:|"]

        def cell(k, m):
            return "–" if m == 0 else (pct(k / m) if m >= min_cell else f"{k:,} of {m:,}")

        for i, r in enumerate(by_period):
            label = f"{city.PERIODS[i][1]} ({period_years(i)})"
            lines.append(f"| {label} | {r['n']:,} | {cell(r['right'], r['n'])} | {r['n_estimate']:,} | "
                         f"{cell(r['right_estimate'], r['n_estimate'])} |")
    else:
        lines.append("Nothing was tested in this build.")
    lines.append("")

    lines += ["## The independent check", ""]
    if ext.get("n_all"):
        before, after_ = ext["before_1990"], ext["from_1990"]
        measured = ext.get("status") == "measured"

        def k(v, m):
            return f"{v:,} ({100 * v / m:.0f}%)" if measured and m else f"{v:,}"

        n_est = ext["n_estimate"]
        n_period = ext["n_all"] - n_est - ext["n_unknown"]
        lines += ["The test above can only use buildings that already have a year, and most of them are old. So the "
                  f"map's own rule was also run on the {ext['n_all']:,} buildings that only Wikidata or OpenStreetMap "
                  "date, as if they had no year, estimating them from the buildings RAÄ and the hand-checked list "
                  "date and nothing else. They are not a fair sample of the buildings the map estimates: RAÄ dated "
                  "most of the older buildings, so the ones left to Wikidata and OpenStreetMap are often new, and "
                  f"{after_['n_all']:,} of the {ext['n_all']:,} were built in 1990 or later.", "",
                  f"Result: the map would show {n_est:,} of them as an estimate: {k(ext['right_estimate'], n_est)} in "
                  f"the right period and {k(ext['in_band_estimate'], n_est)} with the true year inside the band"
                  + (f"; {n_period:,} would show the period only" if n_period else "")
                  + f"; the other {ext['n_unknown']:,} would stay unknown."
                  + ("" if measured else f" That is too few for a percentage (the rule needs {min_cell}), so the "
                     "counts stand as they are.")
                  + " The rule leaves a building unknown when it is not of a type the map estimates, stands more "
                  f"than {acc['near_m']:g} m from a dated building, was first mapped in {late} or later, stands on a "
                  "property unit formed late, or falls in a cell that is not good enough.", ""]
        for words, part in (("Built before 1990", before), ("Built in 1990 or later", after_)):
            if part["n_estimate"]:
                lines.append(f"- {words}: {k_of_n(part['right_estimate'], part['n_estimate'], min_cell)} in the right "
                             f"period, {k_of_n(part['in_band_estimate'], part['n_estimate'], min_cell)} inside the band.")
            else:
                lines.append(f"- {words}: none would show as an estimate ({part['n_all']:,} buildings).")
    else:
        lines.append("No building is dated by Wikidata or OpenStreetMap alone in this build, so there is nothing to "
                     "check.")
    lines.append("")

    area_acc = acc.get("area", {})
    lines += ["## How good the area years are", ""]
    if area_acc.get("status") == "measured":
        lines.append(f"Where a building in a RAÄ-dated area also has a year of its own, the two can be compared: "
                     f"{area_acc['n']:,} buildings. The area's year was in the right period for "
                     f"{pct(area_acc['right_period'])} of them; the typical (median) difference between the two was "
                     f"{area_acc['median_error']:.0f} years.")
    else:
        lines.append(f"Only {area_acc.get('n', 0):,} buildings in a RAÄ-dated area also have a year of their own, too "
                     f"few to measure (the rule needs {min_cell}).")
    lines.append("")
    lines += permit_section(acc.get("bygglov"), y, p)

    if gamla is not None:
        g_rec, g_area, g_est, g_unk = kinds(counts(gamla)[0], cited_periods(gamla))
        lines += ["## Gamla stan", "",
                  "Gamla stan, the old town, is shown on its own because it is the oldest part of the city and where "
                  f"many visitors look first. Of its {len(gamla):,} buildings, {g_rec:,} have a year from a record, "
                  f"{g_area:,} the year of their area, {g_est:,} are estimated and {g_unk:,} stay unknown.", ""]

    if review:
        gains = review.get("wikidata_gains", [])
        nearest = sum(1 for e in gains if e.get("placement") == "nearest")
        lines += ["## Wikidata and OpenStreetMap: the hand-check list", "",
                  "Some years from Wikidata and OpenStreetMap are listed for a hand check:", "",
                  "| Listed for a hand check | Count |", "|---|---:|"]
        for key, words in REVIEW_ROWS:
            lines.append(f"| {words} | {len(review.get(key, [])):,} |")
            if key == "wikidata_gains":
                lines.append(f"| … of them placed on the nearest building (the item's point lies outside every "
                             f"footprint) | {nearest:,} |")
        lines.append("")

    lines += ["## The 12 periods", "", "| Period | Years |", "|---|---|"]
    lines += [f"| {q[1]} | {period_years(i)} |" for i, q in enumerate(city.PERIODS)]
    lines += ["", "---", "",
              f"Generated by `pipeline/report_accuracy.py` from build {version}; do not edit by hand. The first "
              "measurements of the method are in "
              "[the estimates prototype note](research/2026-10-15-estimates-prototype.md)."]
    return "\n".join(lines) + "\n"


def names_page(review: dict | None, y: pd.DataFrame) -> str:
    """The Wikidata gains by name for the M3 review: internal (data/review-years.md), never committed or shipped."""
    gains = (review or {}).get("wikidata_gains", [])
    private = set(y.gid[y.private.astype(bool)]) if "private" in y else set()
    lines = ["# Wikidata gains for the M3 review (internal: names and ids; never commit or ship this file)", "",
             "| Building | Wikidata | Year | Placement | Private house |", "|---|---|---:|---|---|"]
    for e in sorted(gains, key=lambda e: (e["year_from"], e.get("qid", ""))):
        span = f"{e['year_from']}" + ("" if e["year_to"] == e["year_from"] else f"–{e['year_to']}")
        lines.append(f"| {e.get('name', '')} | {e.get('qid', '')} | {span} | {e.get('placement', '')} | "
                     f"{'yes' if e.get('gid') in private else ''} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="report_accuracy", description=__doc__.splitlines()[0])
    ap.add_argument("--accuracy", type=Path, default=ACCURACY)
    ap.add_argument("--years", type=Path, default=YEARS)
    ap.add_argument("--review", type=Path, default=REVIEW)
    ap.add_argument("--buildings", type=Path, default=BUILDINGS)
    ap.add_argument("--stadsdelar", type=Path, default=STADSDELAR)
    ap.add_argument("--date", default=None, help="the build date shown in the title (default: today)")
    ap.add_argument("--version", default=None, help="the data version the page describes (default: web/data/current.json)")
    ap.add_argument("--out", type=Path, default=DOC)
    ap.add_argument("--names-out", type=Path, default=NAMES, help="the internal page with the gains by name")
    a = ap.parse_args([] if argv is None else argv)
    acc = json.loads(a.accuracy.read_text(encoding="utf-8"))
    y = pd.read_parquet(a.years, columns=["gid", "yflag", "ysrc", "private"])
    review = json.loads(a.review.read_text(encoding="utf-8")) if a.review.exists() else None
    gamla = units = None
    if a.buildings.exists() and a.stadsdelar.exists():
        b = gpd.read_parquet(a.buildings, columns=["gid", "geometry"])
        sd = stadsdel_of(b, a.stadsdelar)
        gamla = y[y.gid.isin(b.gid[sd == GAMLA_STAN])]
    if a.buildings.exists() and {"fnr", "prod_year"} <= set(pq.read_schema(a.buildings).names):   # fnr: since 2026-10-15
        units = pd.read_parquet(a.buildings, columns=["gid", "fnr", "prod_year"])
    date = a.date or pd.Timestamp.today().strftime("%Y-%m-%d")
    version = a.version or (json.loads(CURRENT.read_text(encoding="utf-8"))["version"] if CURRENT.exists() else "unversioned")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(acc, y, review, gamla, date, version, units=units), encoding="utf-8")
    a.names_out.parent.mkdir(parents=True, exist_ok=True)
    a.names_out.write_text(names_page(review, y), encoding="utf-8")
    gains = len((review or {}).get("wikidata_gains", []))
    print(f"wrote {a.out} ({len(y):,} buildings, {acc['result']}) and {a.names_out} ({gains} gains by name, internal)")


if __name__ == "__main__":
    main(sys.argv[1:])
