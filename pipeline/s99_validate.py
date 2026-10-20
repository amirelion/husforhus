"""Validate web/data/<version> before it ships (the spec's s99 rules as Plans 1 and 2 implement them).

Fails (exit 1, with a readable list) on:
- plaques (s15_plaques, when plaques.json is there): a plaque on no building of the version, without its credit,
  name, text or position, listed twice, or with a text that names an owner or a byggherre (spec §6.3);
- building archaeology (card `br`, s02_stadsmuseet): on a private house, or not well formed (its own fields, the
  investigations' years, felling years, the credit "Stadsmuseet i Stockholm", a report link that is not https to
  Digitala Stadsmuseet); and, in the privacy check, any of the City Museum register's property designations
  (today's and the former ones it names) in any shipped file, as for FASTIGHET;
- metro (s16_metro, when metro.json is there): a date that does not parse, a segment station not in the stations
  list, a line other than green, red or blue, or a coordinate outside the map;
- stockholm.json naming another version than its folder;
- any file over 20 MiB; first-load or whole-city transferred bytes over budget;
- base: land.bin.gz or water.bin.gz missing, not decoding or without a polygon; labels.json missing or not a
  list with at least one label (s03_tiles never ships alone, and the viewer cannot load such a folder);
- terrain: terrain.bin.gz missing, not decoding, or disagreeing with stockholm.json's terrain
  block (origin, cell, size, water level within WATER_Z_TOL: the header holds it as a float32) or with water.bin.gz (one level per water polygon, one shore bit per water
  vertex); a height outside -10..250 m or a level outside the heights' range; more transferred bytes than the terrain
  budget (1.5 MB); with the DTM as its source, building grounds that sit more than TERRAIN["datum_max"]
  off the terrain under their outlines (median; a wrong vertical datum, RH 00 for RH 2000, moves it by 0.52 m); a
  tile drawing a building under the water's floor (water_z + ground_min) or more than 200 m up; the file's source,
  data/terrain.json (missing, or its source, datum or fixed count) and the credits (lm_markhojd exactly when the source
  is dtm) not all agreeing with stockholm.json; data/terrain.json's buried, the buildings left more than half under at
  relief_max, not a whole number or over TERRAIN["buried_max"] (10), or counted at another relief than the slider's top
  (stockholm.json reliefMax); with --release, a terrain from the City's contour lines while sources.yml's
  city_stadskarta does not say covers_contours: true;
- attrs: a yflag outside codes.py (5 is retired), year 0 without yflag UNKNOWN (or the reverse), a year
  outside 1000..2026, a dated year outside its own year_from..year_to, a dated year_from before 1000, a year_to
  after 2026 (a private house's decade end excepted), height not in (0, 200] m, more than 60 floors, NaN or
  out-of-bounds coordinates, a period outside the period table, a dated non-private row whose period is not its
  year's (private rows take the period from the real year, so only they may differ), a ysrc outside codes.py or one
  that does not pair with the yflag (codes.py: UNKNOWN <-> none, AREA <-> raa_area, ESTIMATE/PERIOD <-> estimate, the
  rest <-> an exact, range or long year), a private house not published as exactly a decade (a private house shows only the decade: no exact year
  for private houses), a private house whose decade and period share fewer than 2 years (the pair would give the
  year away), or a dated, non-curated building in a private-house category that is not marked private (the decade rule
  checked from KATEGORI, not from the flag it is meant to verify);
- histograms: histogram + histogramEst + unknown not adding up to stats.buildings;
- accuracy: the table missing from stockholm.json, an accuracy-table key missing or outside the contract (on the table, a
  cell, a fallback row, a by_true_period row, or the area and external entries and the external entry's 1990
  split), a cell without its group/era/inner/n/status (a fallback row without group/inner/n/status), a status
  outside estimate/period/unknown/not measurable (an area or external one outside not measurable/measured), a
  group or era that is not one of the estimator's (a by_true_period period not one of city.PERIODS), a value of
  the wrong type (the external entry's and by_true_period's counts are whole numbers), numbers of any kind on a
  cell or row with fewer than min_cell test buildings, "not measurable" on one with min_cell or more, or one with
  min_cell or more without all its numbers (a cell's median_error, right_period, within_one and band; a fallback
  row's the same without band), a share (right_period, within_one, band_coverage) outside 0..1, a band of 0 or less,
  an impossible count (below 0, right over n, right_estimate over n_estimate over n in a by_true_period row,
  right_estimate or in_band_estimate over n_estimate, n_estimate + n_unknown over n_all, a 1990 half not adding up
  to the external total), by_true_period not exactly one row per period of city.PERIODS in order, an
  "estimate" cell of a type outside city.ESTIMATE's estimate_groups or under min_right or over max_band, an external
  check that reads "measured" with fewer than min_cell "≈ year" buildings (or the reverse), min_cell/min_right/
  max_band that are not city.ESTIMATE's, or a table that does not describe this build (result's ESTIMATE and
  PERIOD counts against stats.byFlag, tested against the building-level years);
- tiles: gids not exactly 0..n-1 once each; and, last, on a build with no other finding, a tile's year, yflag or
  period disagreeing with attrs for a gid;
- data: data/buildings.parquet not holding exactly this version's gids 0..n-1 (after a fixture build it holds
  519 rows; the KATEGORI and privacy checks below read it by gid, so they would quietly check almost nothing);
- sources missing required fields (with --release: any source still pending-O1);
- privacy: a City/register UUID, a normalised FASTIGHET (a whole value, a part between punctuation, or, since 2026-10-16,
  a phrase inside a sentence: privacy.phrases) or a property-unit key (LOD1 FNR, data/buildings.parquet `fnr`: a digit
  run in a string, a whole number, or a field named fnr) found in any decompressed JSON/text file;
- cards: any field other than a card's, or on a private house or any other non-curated building whose KATEGORI is in
  city.PRIVATE_HOUSE_KATEGORI, dated or not: a RAÄ link, a Wikidata item, an article, a photo or an English
  label, a name that is not on the reviewed list (pipeline/private_names.txt), or an architect's name that appears on
  city.ARCHITECT_MAX_RARE cards or fewer citywide and is not a reviewed firm (pipeline/private_firms.txt; the rare-architect rule, point
  2); a photo whose licence is not CC BY, CC BY-SA, CC0 or public domain, without an author or a Commons page,
  without its title under CC 2.0–3.0, missing from web/data/photos/ or over city.WIKI's photo_bytes, or not listed in
  photos.json, which build_dist ships from; rebuilds or older cellars on a card that is not curated, a
  rebuild of another kind, out of order, or not after the card's own year;
- excerpts (wiki/NN.json): a shard without its CC BY-SA 4.0 licence, a key that is not a gid of its own
  shard, an excerpt on a building whose card may not link an article, one without text or revision, in a language
  the card's `wp` does not list, or one that says who owns the building or had it built (privacy.owner);
- landmarks: a timeline landmark that is not the curated year of a building outside the private-house categories;
- towers (the laser parts s03_tiles draws after a building's footprint): one on a private house (marked private, or a
  non-curated house in a private-house category) or on no building, one outside TOWER_M (5..400 m above its
  building's ground), one reaching more than TOWER_INSIDE_M past its footprint; Lantmäteriet's laser data credited
  when no tile draws a tower, or not credited when one does;
- a card address on a private-category house while city.PRIVATE_ADDRESSES is False; districts.bin.gz not one
  byte per gid within stockholm.json `districts`; search/index.json missing while features.search is on, a building
  entry naming what its card does not, another name (city.BUILDING_ALIASES) pointing at a building whose card does not
  carry its target, a street without its numbers, a street and number that together read as a property designation,
  an address on no building (or on a private house while PRIVATE_ADDRESSES is False); a takedown
  (pipeline/suppress.yml) that matches no building, or a suppressed building that ships a year, a rating, a card, an
  excerpt or a search entry; with --release, an empty city.MAKER or city.CONTACT, or an open decision that the
  public site waits for (city.RELEASE_WAITS_FOR: addresses on private houses).

Error lines name the file and a JSON path, never a leaked value. A JSON key or card field name is printed only if
it looks like an identifier (SAFE_KEY: letters, digits, underscore); anything else is shown as `[key #i]`, so a
UUID or a property designation used as a key stays out of CI logs. The accuracy checks follow the same rule: an
unexpected key goes through `shown`, a status is quoted only if it is a plain word, a number is printed only if it
is one (`num`), and anything else reads `[value]`; a group or era is never printed.
"""
import argparse
import datetime
import gzip
import json
import math
import re
import struct
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import city, codes, contributions, plaques, stadsmuseet, suppress
from .estimate import GROUPS
from .geo import lonlat_to_3011
from .privacy import mentions, normalise, owner, phrases
from .s02_attributes import REGISTER_CODE, load_private_firms, load_private_names
from .s03_tiles import (ATTR_DTYPE, CARD_FIELDS, CURRENT, DTM_SOURCE, LASER_SOURCE, N_CARD_SHARDS, PHOTO_FIELDS, SOURCES,
                       WIKI_LICENCE)
from .s04_base import unpack
from .s08_landmarks import REBUILD_KINDS
from .sources import PROCESSED, check_sources, licence_names, load_sources
from . import terrain
from .tiles_decode import parse
from .tiles_decode import parts as tile_parts
from .wiki import beside_private

DATA = Path("data")
MAX_FILE_BYTES = 20 * 1024 * 1024
FIRST_LOAD_BYTES = 2_500_000
WHOLE_CITY_BYTES = 8_000_000
TERRAIN_BYTES = 1_500_000      # the terrain's download budget
TERRAIN_DM = (-100, 2500)      # a terrain height outside -10..250 m is a broken grid, not Stockholm
WATER_Z_TOL = 0.01             # metres: the header's float32 water level against stockholm.json's
CONTOUR_SOURCE = "city_stadskarta"   # sources.yml: the City's Stadskarta, whose 0_line layer is the contour terrain
MAX_GROUND_DM = 2000           # a building's drawn ground above 200 m
YEAR_MIN, YEAR_MAX = 1000, 2026
MAX_HEIGHT_DM = 2000
MAX_FLOORS = 60
TOWER_M = (5.0, 400.0)         # a laser tower part's height above its building's ground
TOWER_INSIDE_M = 0.2           # ... and how far past its footprint its outline may reach (decimetre vertices)
TOWER_OUTSIDE_M2 = 0.5
MAX_LOCAL_M = 30_000  # the municipality spans about ±16 km around Stortorget
METRO_LINES = {"green", "red", "blue"}  # s16_metro (pipeline/metro.py LINES)
MIN_PRIVATE_OVERLAP = 2  # years a private row's decade must share with its period, or the pair pins the year
YFLAGS = (codes.EXACT, codes.RANGE, codes.LONG, codes.AREA, codes.ESTIMATE, codes.PERIOD, codes.UNKNOWN)
YSRCS = (codes.SRC_NONE, codes.SRC_CURATED, codes.SRC_RAA, codes.SRC_RAA_AREA, codes.SRC_WIKIDATA, codes.SRC_ESTIMATE,
         codes.SRC_RAA_OLD, codes.SRC_OSM, codes.SRC_READER)
# The codes.py pairing: the yflags a source may carry.
PAIRS = {codes.SRC_NONE: (codes.UNKNOWN,), codes.SRC_RAA_AREA: (codes.AREA,),
         codes.SRC_ESTIMATE: (codes.ESTIMATE, codes.PERIOD)}
DATED_FLAGS = (codes.EXACT, codes.RANGE, codes.LONG)
# The accuracy table's keys, a cell's keys and the statuses.
TABLE_KEYS = {"method", "held_out", "folds", "near_m", "min_cell", "min_right", "max_band", "tested", "cells", "fallback",
              "band_coverage", "by_true_period", "area", "external", "result"}
ACCURACY_STATUSES = {"estimate", "period", "unknown", "not measurable"}
SIDE_STATUSES = {"not measurable", "measured"}            # the area and external checks
CELL_KEYS = {"group", "era", "inner", "n", "status"}
CELL_NUMBERS = {"median_error", "right_period", "within_one", "band"}
FALLBACK_KEYS = {"group", "inner", "n", "status", "median_error", "right_period", "within_one"}   # Ruling F15
# The area check (n, status and score()'s numbers) and, since 2026-10-15, the external check: the map's own rule on the
# Wikidata/OSM-only buildings, counted per map state (estimate.check_external) and split at 1990 (SPLIT_KEYS each).
EXTERNAL_COUNTS = ("n_all", "n_estimate", "right_estimate", "in_band_estimate", "n_unknown")
SPLIT_KEYS = {"n_all", "n_estimate", "right_estimate", "in_band_estimate"}
EXTERNAL_SPLITS = ("before_1990", "from_1990")
SIDE_KEYS = {"area": {"n", "status", "median_error", "right_period"},
             "external": {"status", *EXTERNAL_COUNTS, *EXTERNAL_SPLITS}}
BY_PERIOD_KEYS = {"period", "n", "right", "n_estimate", "right_estimate"}   # by_true_period's rows
ROW_KEYS = {"group", "inner", "n", "status"}                       # what a fallback row must carry (cells: CELL_KEYS)
ERA_LABELS = tuple(e[0] for e in city.ERAS)                        # the strings a cell's group and era may take
PERIOD_KEYS = tuple(q[0] for q in city.PERIODS)                    # the strings a by_true_period row's period may take
PINNED = ("min_cell", "min_right", "max_band")                     # the table must use the estimator's thresholds
TEXT_SUFFIXES = (".json", ".txt", ".csv", ".geojson")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SPLIT_RE = re.compile(r"[,;()\[\]/|]")
DIGITS_RE = re.compile(r"\d+")
SAFE_KEY = re.compile(r"[A-Za-z0-9_]{1,32}")  # a UUID has hyphens, a FASTIGHET has a space: neither is printed
SAFE_WORD = re.compile(r"[a-z]{1,16}( [a-z]{1,16})?")  # a status as an error line may quote it: "not measurable"
# What a card's photo may be licensed under and where its page is, and the fields that would state the
# exact year of a house the card shows only by its decade
PHOTO_LICENCE = re.compile(r"CC BY(-SA)? \d\.\d( [A-Z]{2})?|CC0|Public domain( \(Sweden\))?")
OLD_CC = re.compile(r"CC BY(-SA)? [23]\.\d( [A-Z]{2})?")
COMMONS_PAGE = "https://commons.wikimedia.org/w/index.php?curid="
COMMONS_PAGE_ID = re.compile(re.escape(COMMONS_PAGE) + r"\d+")   # the page id alone, as wiki.credit requires
HIDDEN_FIELDS = ("raa", "qid", "wp", "photo", "en")
# A Wikidata item ("Q10123456"), a Commons page id or a photo's key (16 hex digits of the file's sha1, whose digit runs
# can be eight long) is an identifier of its own, whose number can equal a property-unit key (FNR, 10,057,056–
# 10,547,437 on 2026-10-16; Swedish Wikidata items live in that range): the FNR digit test skips a string that is
# exactly one of them, and every other test still applies.
ID_FORMAT = re.compile(r"Q\d+|" + re.escape(COMMONS_PAGE) + r"\d+|[0-9a-f]{16}-\d+\.(?:jpg|png|webp)")


def shown(key: str, i: int, what: str = "key") -> str:
    """A JSON key or field name as it may appear in an error line: itself if identifier-like, else `[key #i]`."""
    return key if SAFE_KEY.fullmatch(key) else f"[{what} #{i}]"


def stray(keys, allowed: set[str]) -> list[str]:
    """The keys outside `allowed`, sorted, each as `shown` prints it (an unexpected key could be anything)."""
    return [shown(k, i) for i, k in enumerate(sorted(set(keys) - allowed))]


def num(x) -> str:
    """A table number as an error line may print it: an int or float as itself, anything else (a string could be
    a place name, a bool or a list is no count) as `[value]`."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return "[value]"
    return str(x) if isinstance(x, int) else f"{x:g}"


def whole(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def share(x) -> bool:
    """A table share (right_period, within_one, band_coverage): a number from 0 to 1."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 1


def quoted(status) -> str:
    """A status value as an error line may quote it: itself if it is a plain lowercase word or two, else `[value]`."""
    return repr(status) if isinstance(status, str) and SAFE_WORD.fullmatch(status) else "[value]"


def privacy_sets(data: Path) -> tuple[set[str], set[str], set[int]]:
    """(UUIDs casefolded, normalised FASTIGHET designations, FNR property-unit keys) of data/buildings.parquet; no
    FNR set from a buildings file written before 2026-10-15 (it has no fnr column, so nothing could ship one). 0 is "no
    key" and never in the set."""
    path = data / "buildings.parquet"
    has_fnr = "fnr" in pq.read_schema(path).names
    b = pd.read_parquet(path, columns=["uuid", "fastighet", *(["fnr"] if has_fnr else [])])
    uuids = {u.casefold() for u in b.uuid.dropna() if u}
    props = {normalise(f) for f in b.fastighet.dropna() if f.strip()} - {""}
    fnrs = {int(v) for v in b.fnr.to_numpy() if v > 0} if has_fnr else set()
    return uuids, props, fnrs


def transferred(path: Path) -> int:
    """Bytes on the wire: .gz files as stored; text compressed by the host (estimated with gzip -9)."""
    raw = path.read_bytes()
    if path.suffix == ".gz":
        return len(raw)
    if path.suffix in TEXT_SUFFIXES:
        return len(gzip.compress(raw, 9, mtime=0))
    return len(raw)


def check_sizes(out: Path, cfg: dict) -> list[str]:
    errors = []
    files = sorted(p for p in out.rglob("*") if p.is_file())
    for p in files:
        if p.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"size: {p.relative_to(out)} is {p.stat().st_size:,} bytes, over {MAX_FILE_BYTES:,}")
    first = [out / f"{city.SLUG}.json", out / "attrs.bin.gz"] + [out / p for p in cfg.get("packs", [])[:1]]
    first_bytes = sum(transferred(p) for p in first if p.exists())
    if first_bytes > FIRST_LOAD_BYTES:
        errors.append(f"budget: first load is {first_bytes:,} bytes, over {FIRST_LOAD_BYTES:,}")
    city_bytes = sum(transferred(p) for p in files)
    if city_bytes > WHOLE_CITY_BYTES:
        errors.append(f"budget: whole city is {city_bytes:,} bytes, over {WHOLE_CITY_BYTES:,}")
    return errors


def check_base(out: Path, cfg: dict) -> list[str]:
    """The folder is the one stockholm.json names, and holds the land, water and labels the viewer loads."""
    errors = []
    if cfg.get("version") != out.name:
        errors.append(f"{city.SLUG}.json: version is {cfg.get('version')} but the folder is {out.name}")
    for name in ("land.bin.gz", "water.bin.gz"):
        if not (out / name).exists():
            errors.append(f"base: {name} is missing (run s04_base)")
            continue
        try:
            polys = unpack(gzip.decompress((out / name).read_bytes()))
        except (OSError, EOFError, ValueError, struct.error) as e:
            errors.append(f"base: {name} does not decode ({e})")
            continue
        if not polys:
            errors.append(f"base: {name} holds no polygon")
    if not (out / "terrain.bin.gz").exists():
        errors.append("base: terrain.bin.gz is missing (run s02_terrain and s04_base)")
    if not (out / "labels.json").exists():
        errors.append("labels: labels.json is missing (run s07_labels)")
    else:
        try:
            labels = json.loads((out / "labels.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append("labels: labels.json is not valid JSON")
        else:
            if not isinstance(labels, list) or not labels:
                errors.append("labels: labels.json is not a list with at least one label")
    return errors


def check_terrain(out: Path, cfg: dict, data: Path = DATA, *, release: bool = False,
                  sources: list[dict] = ()) -> list[str]:
    """terrain.bin.gz against stockholm.json's terrain block and water.bin.gz, its values, the terrain
    budget, the source it says it came from (the file's header, data/terrain.json and the credits must agree with
    stockholm.json), the buildings the terrace could not free and, for a DTM build, the datum. A missing
    terrain.bin.gz is check_base's to report; a missing data/terrain.json is reported here (its checks cannot run).
    A release built from the City's contour lines also needs sources.yml's city_stadskarta to say covers_contours:
    true (the City's licence answer named the Stadskarta's other layers, not the contours)."""
    path, t = out / "terrain.bin.gz", cfg.get("terrain")
    if not path.exists():
        return []
    if not isinstance(t, dict):
        return ["terrain: stockholm.json has no terrain block (run s02_terrain and s03_tiles)"]
    errors = []
    covered = any(s.get("id") == CONTOUR_SOURCE and s.get("covers_contours") is True for s in sources)
    if release and t.get("source") == "contours" and not covered:
        errors.append("terrain: a release built from the City's contour lines needs the City's answer to name them: "
                      f"sources.yml's {CONTOUR_SOURCE} does not say covers_contours: true (ask the City, or build from "
                      "Lantmäteriet's model)")
    if transferred(path) > TERRAIN_BYTES:
        errors.append(f"budget: terrain is {transferred(path):,} bytes, over {TERRAIN_BYTES:,}")
    try:
        d = terrain.unpack(gzip.decompress(path.read_bytes()))
    except (OSError, EOFError, ValueError, struct.error) as e:
        return [*errors, f"terrain: terrain.bin.gz does not decode ({e})"]
    g = d["grid"]
    head = {"x0": g.x0, "z0": g.z0, "cell": g.cell, "nx": g.nx, "nz": g.nz, "waterZ": d["water_z"]}
    # the header holds the water level as a float32 (0.07 reads 0.07000000029802322): within WATER_Z_TOL
    same = {"waterZ": lambda a, b: num(a) != "[value]" and abs(a - b) <= WATER_Z_TOL}
    off = [k for k, v in head.items() if not same.get(k, lambda a, b: a == b)(t.get(k), v)]
    if off:
        errors.append(f"terrain: terrain.bin.gz's header disagrees with stockholm.json on {off}")
    if d["source"] != t.get("source"):
        errors.append(f"terrain: terrain.bin.gz was built from {d['source']}, stockholm.json says {t.get('source')} "
                      "(run s03_tiles and s04_base together after s02_terrain)")
    rec_path = data / "terrain.json"
    if not rec_path.exists():   # the source, datum, fixed and buried checks need s02_terrain's record
        errors.append(f"terrain: cannot check without {rec_path}")
    else:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        off = [k for k in ("source", "datum", "fixed") if rec.get(k) != t.get(k)]
        if off:
            errors.append(f"terrain: stockholm.json's terrain block disagrees with data/terrain.json on {off} (run "
                          "s03_tiles and s04_base together after s02_terrain)")
        if rec.get("relief_max") != t.get("reliefMax"):   # the burial count must be made at the slider's top
            errors.append(f"terrain: data/terrain.json counted its buried buildings at {num(rec.get('relief_max'))}x, "
                          f"stockholm.json's slider reaches {num(t.get('reliefMax'))}x (run s02_terrain again)")
        buried, most = rec.get("buried"), city.TERRAIN["buried_max"]
        if not whole(buried):   # absent, null or true would pass a bare comparison
            errors.append("terrain: data/terrain.json lacks a whole-number buried count (run s02_terrain again)")
        elif buried > most:
            errors.append(f"terrain: {buried} buildings buried by more than half their height at "
                          f"{city.TERRAIN['relief_max']:g}x (limit {most}): the terrace cannot free them")
    credited = DTM_SOURCE in {a.get("id") for a in cfg.get("attribution", [])}
    if credited != (t.get("source") == "dtm"):
        errors.append(f"attribution: Lantmäteriet's terrain model is {'credited' if credited else 'not credited'}, "
                      f"but the terrain came from {t.get('source')}")
    polys = []
    if (out / "water.bin.gz").exists():
        try:
            polys = unpack(gzip.decompress((out / "water.bin.gz").read_bytes()))
        except (OSError, EOFError, ValueError, struct.error):
            polys = []   # check_base reports it
    if polys:   # no water polygon is check_base's to report
        n_verts = sum(len(r) for poly in polys for r in poly)
        if len(d["levels"]) != len(polys):
            errors.append(f"terrain: {len(d['levels'])} water levels for {len(polys)} water polygons")
        if d["n_shore"] != n_verts:
            errors.append(f"terrain: shore flags for {d['n_shore']} vertices, water.bin.gz has {n_verts}")
    h_dm = np.round(d["h"] * 10)
    lo, hi = TERRAIN_DM
    if h_dm.min() < lo or h_dm.max() > hi:
        errors.append(f"terrain: heights from {h_dm.min() / 10:g} to {h_dm.max() / 10:g} m, outside "
                      f"{lo / 10:g}..{hi / 10:g} m")
    if len(d["levels"]) and (d["levels"].min() < d["water_z"] or d["levels"].max() > d["h"].max()):
        errors.append("terrain: a water level below the sea's or above every height")
    datum, kind = t.get("datum"), t.get("source")
    if kind == "dtm" and (not isinstance(datum, (int, float)) or abs(datum) > city.TERRAIN["datum_max"]):
        errors.append(f"terrain: building grounds sit {num(datum)} m off the terrain under their outlines (median, "
                      f"limit {city.TERRAIN['datum_max']:g}): a wrong height datum?")
    return errors


def check_attribution(cfg: dict) -> list[str]:
    """Every source About lists carries its line in English and Swedish, "Dataset: publisher,
    licence", the dataset and the licence the same in both, the licence the entry's own (sources.licence_names), and
    ", processed" / ", bearbetad" in both or in neither."""
    errors = []
    for i, a in enumerate(cfg.get("attribution", [])):
        sid, c = a.get("id", f"#{i}"), a.get("credit")
        # a permission's words differ per language ("used with permission", "används med tillstånd"): the same
        # licence is the same entry of its names in both
        names = {lang: licence_names(a.get("licence"), lang) for lang in PROCESSED}
        found = {lang: re.fullmatch(rf"(?P<dataset>[^:\s][^:]*): [^\s,].*, (?P<licence>{'|'.join(map(re.escape, names[lang]))})"
                                    rf"(?P<p>, {PROCESSED[lang]})?", c[lang])
                 if names[lang] and isinstance(c, dict) and isinstance(c.get(lang), str) else None
                 for lang in PROCESSED}
        if not all(found.values()) or len({(m["dataset"], names[lang].index(m["licence"]), bool(m["p"]))
                                           for lang, m in found.items()}) != 1:
            errors.append(f"attribution: {sid}: its credit must read \"Dataset: publisher, licence\" (plus \", processed\" "
                          f"/ \", bearbetad\") in en and sv, naming {a.get('licence')}: {c!r}")
    return errors


def first_gids(mask: np.ndarray, k: int = 5) -> str:
    idx = np.flatnonzero(mask)
    return ", ".join(map(str, idx[:k])) + (" …" if len(idx) > k else "")


def check_attrs(a: np.ndarray, periods: list[tuple[int, int]] | None = None) -> list[str]:
    """`periods` is the (from, to) range of each period index; default city.PERIODS."""
    periods = [(p[3], p[4]) for p in city.PERIODS] if periods is None else list(periods)
    errors = []

    def rule(mask, what):
        if mask.any():
            errors.append(f"attrs: {int(mask.sum())} buildings {what} (gids {first_gids(mask)})")

    year, flag, period = a["year"].astype(int), a["yflag"], a["period"].astype(int)
    rule(~np.isin(flag, YFLAGS), "with a yflag outside codes.py")
    src = a["ysrc"]
    rule(~np.isin(src, YSRCS), "with a ysrc outside codes.py")
    paired = np.array([int(f) in PAIRS.get(int(s), DATED_FLAGS) for f, s in zip(flag, src)], dtype=bool)
    rule(np.isin(src, YSRCS) & np.isin(flag, YFLAGS) & ~paired, "whose yflag does not pair with their ysrc")
    unknown = flag == codes.UNKNOWN
    rule((year == 0) != unknown, "where year 0 and yflag UNKNOWN disagree")
    in_bounds = (year >= YEAR_MIN) & (year <= YEAR_MAX)
    rule((year != 0) & ~in_bounds, f"with a year outside {YEAR_MIN}..{YEAR_MAX}")
    rule((a["h_dm"] == 0) | (a["h_dm"] > MAX_HEIGHT_DM), f"with a height outside (0, {MAX_HEIGHT_DM / 10:g}] m")
    rule(a["floors"] > MAX_FLOORS, f"with more than {MAX_FLOORS} floors")
    y_from, y_to = a["year_from"].astype(int), a["year_to"].astype(int)
    # a year already reported above (0 on a dated row, or out of bounds) is not reported twice
    rule(~unknown & in_bounds & ((y_from > year) | (year > y_to)),
         "dated with a year outside their own year_from..year_to")
    rule(~unknown & (y_from < YEAR_MIN), f"dated with a year_from before {YEAR_MIN}")
    finite = np.isfinite(a["x"]) & np.isfinite(a["z"])
    far = (np.abs(a["x"]) > MAX_LOCAL_M) | (np.abs(a["z"]) > MAX_LOCAL_M)
    rule(~finite | far, "with NaN or out-of-bounds coordinates")
    bad_period = period >= len(periods)
    rule(bad_period, f"with a period outside the {len(periods)} periods")
    private = a["private"] != 0
    if periods:
        starts = np.array([p[0] for p in periods], dtype=np.int64)
        own = np.maximum(0, np.searchsorted(starts, year, side="right") - 1)
        rule(~unknown & in_bounds & ~private & ~bad_period & (own != period),
             "dated and not private whose period is not their year's")
    # a private house's year_to is its decade end (2020s: 2029), not a year in the future
    rule(~unknown & ~private & (y_to > YEAR_MAX), f"with a year_to after {YEAR_MAX}")
    not_decade = (year == 0) | (year % 10 != 0) | (y_from != year) | (y_to != year + 9)
    rule(private & not_decade, "marked private but not published as exactly a decade (an exact year would leak)")
    if periods:
        # Review Focus #3: a decade plus a period that share one year (or none) would pin the exact year
        bounds = np.array(periods, dtype=np.int64)
        at = np.minimum(period, len(periods) - 1)
        shared = np.minimum(year + 9, bounds[at, 1]) - np.maximum(year, bounds[at, 0]) + 1
        rule(private & ~not_decade & ~bad_period & (shared < MIN_PRIVATE_OVERLAP),
             f"marked private whose decade and period narrow the exact year (fewer than {MIN_PRIVATE_OVERLAP} "
             "years in common)")
    return errors


def check_data(out: Path, data: Path, n: int) -> list[str]:
    """The KATEGORI and privacy checks read data/buildings.parquet by gid, so it must hold exactly this
    version's buildings, gids 0..n-1. An absent file is reported by the privacy check instead."""
    path = data / "buildings.parquet"
    if not path.exists():
        return []
    gids = pd.read_parquet(path, columns=["gid"]).gid.to_numpy()
    fix = "rebuild data/ or validate the matching version"
    if len(gids) != n:
        return [f"data: {path} has {len(gids):,} rows but {out.name} has {n:,} buildings: {fix}"]
    if not np.array_equal(np.sort(gids), np.arange(n)):
        return [f"data: {path} gids are not exactly 0..{n - 1}: {fix}"]
    return []


def building_keys(n: int, data: Path) -> np.ndarray | None:
    """Per gid, the building it belongs to for the rare-architect count: its RAÄ record (data/years.parquet `raa_id`), else the gid
    itself; None when the file is absent. LOD1 often draws one building as several footprints sharing a record, and
    s02_attributes counts a name once per record, so s99 counts the same way."""
    path = data / "years.parquet"
    if not path.exists():
        return None
    rid = pd.read_parquet(path, columns=["gid", "raa_id"]).set_index("gid").raa_id.reindex(np.arange(n))
    return np.array([r if isinstance(r, str) and r else f"gid {g}" for g, r in enumerate(rid)], dtype=object)


def private_category(n: int, data: Path) -> np.ndarray | None:
    """Per gid, True where KATEGORI (data/buildings.parquet, by gid) is in city.PRIVATE_HOUSE_KATEGORI; None when
    the file is absent."""
    path = data / "buildings.parquet"
    if not path.exists():
        return None
    kategori = pd.read_parquet(path, columns=["gid", "kategori"]).set_index("gid").kategori
    return kategori.reindex(np.arange(n), fill_value="").isin(city.PRIVATE_HOUSE_KATEGORI).to_numpy()


def check_private_marked(a: np.ndarray, data: Path) -> list[str]:
    """The decade rule for private houses, checked from KATEGORI rather than from the `private` flag it governs: a dated (yflag not UNKNOWN),
    non-curated building in a private-house category must be marked private, or its exact year would ship."""
    in_set = private_category(len(a), data)
    if in_set is None:  # no KATEGORI by gid; the privacy check already fails the run
        return []
    missed = in_set & (a["ysrc"] != codes.SRC_CURATED) & (a["yflag"] != codes.UNKNOWN) & (a["private"] == 0)
    if not missed.any():
        return []
    return [f"attrs: {int(missed.sum())} private-category buildings not marked private (an exact year would ship) "
            f"(gids {first_gids(missed)})"]


def check_osm_floors(a: np.ndarray, data: Path) -> list[str]:
    """The card credits floors with fsrc FLOORS_OSM to OpenStreetMap ("5 (OpenStreetMap)"), so they must be its
    building:levels (data/attributes.parquet `floors_osm`, by gid): s02_terrain once recomputed them from a repaired
    height. Without the file, or a table without floors_osm, there is nothing to
    compare."""
    path = data / "attributes.parquet"
    if not path.exists() or "floors_osm" not in pq.read_schema(path).names:
        return []
    osm = pd.read_parquet(path, columns=["gid", "floors_osm"]).set_index("gid").floors_osm
    osm = osm.reindex(np.arange(len(a)), fill_value=0).to_numpy().astype(np.int64)
    off = (a["fsrc"] == codes.FLOORS_OSM) & (a["floors"].astype(np.int64) != osm)
    if not off.any():
        return []
    return [f"attrs: {int(off.sum())} buildings whose floors are credited to OpenStreetMap but differ from its "
            f"building:levels (gids {first_gids(off)})"]


def check_histograms(cfg: dict) -> list[str]:
    """Histogram + histogramEst + unknown == stats.buildings."""
    total = sum(sum(v) for h in (cfg.get("histogram", {}), cfg.get("histogramEst", {})) for v in h.values())
    total += int(cfg.get("unknown", 0))
    n = cfg.get("stats", {}).get("buildings")
    if total != n:
        return [f"histograms: histogram + histogramEst + unknown is {total:,} but stats.buildings is {n:,}"]
    return []


def check_row(where: str, row, required: set[str], allowed: set[str], min_cell: int) -> list[str]:
    """One cell or fallback row of the table: an object with its required keys and none outside `allowed`, a status in
    the list, a group (and era) that is one of the estimator's, a true/false inner and a whole-number n; a row under
    min_cell reads "not measurable" with no number at all, one at or over it does not and carries every number
    (`allowed - required`: a cell's CELL_NUMBERS, a fallback row's the same without band); right_period and
    within_one are shares from 0 to 1 and a band is above 0. No value that could be a place name is printed."""
    if not isinstance(row, dict):
        return [f"accuracy: {where} is not an object"]
    if not required <= set(row):
        return [f"accuracy: {where} lacks one of {sorted(required)}"]
    errors, status, n = [], row["status"], row["n"]
    if not (isinstance(status, str) and status in ACCURACY_STATUSES):
        errors.append(f"accuracy: {where} has status {quoted(status)}")
    if not (isinstance(row["group"], str) and row["group"] in GROUPS):
        errors.append(f"accuracy: {where} has a group outside the estimator's groups")
    if "era" in required and not (isinstance(row["era"], str) and row["era"] in ERA_LABELS):
        errors.append(f"accuracy: {where} has an era outside city.ERAS")
    if not isinstance(row["inner"], bool):
        errors.append(f"accuracy: {where} has an inner that is not true or false")
    if not whole(n):
        errors.append(f"accuracy: {where} has an n that is not a whole number")
    else:
        if n < min_cell and (status != "not measurable" or CELL_NUMBERS & set(row)):
            errors.append(f"accuracy: {where} has {num(n)} test buildings (under {num(min_cell)}) "
                          "but is not 'not measurable'")
        if n >= min_cell and status == "not measurable":
            errors.append(f"accuracy: {where} has {num(n)} test buildings but reads 'not measurable'")
        numbers = allowed - required
        if n >= min_cell and status != "not measurable" and not numbers <= set(row):
            errors.append(f"accuracy: {where} has {num(n)} test buildings but lacks one of {sorted(numbers)}")
    errors += check_shares(where, row, ("right_period", "within_one"))
    if "band" in row and not (isinstance(row["band"], (int, float)) and not isinstance(row["band"], bool)
                              and row["band"] > 0):
        errors.append(f"accuracy: {where} band is not a number above 0")
    extra = stray(row, allowed)
    if extra:
        errors.append(f"accuracy: {where} has keys outside the accuracy table's: {extra}")
    return errors


def check_estimate_cell(where: str, row, acc: dict) -> list[str]:
    """A cell that reads "estimate" must be one the estimator could give: a type in
    city.ESTIMATE's estimate_groups, right_period at least min_right, band at most max_band (the table's thresholds,
    pinned to the estimator's above). A malformed cell is check_row's; the group is never printed."""
    if not (isinstance(row, dict) and row.get("status") == "estimate"):
        return []
    errors = []
    if row.get("group") in GROUPS and row["group"] not in city.ESTIMATE["estimate_groups"]:   # else check_row's
        errors.append(f"accuracy: {where} reads 'estimate' for a type the estimator does not estimate")
    min_right = acc["min_right"] if isinstance(acc.get("min_right"), (int, float)) else city.ESTIMATE["min_right"]
    max_band = acc["max_band"] if isinstance(acc.get("max_band"), (int, float)) else city.ESTIMATE["max_band"]
    right, band = row.get("right_period"), row.get("band")
    if isinstance(right, (int, float)) and not isinstance(right, bool) and right < min_right:
        errors.append(f"accuracy: {where} reads 'estimate' with a right_period under min_right {num(min_right)}")
    if isinstance(band, (int, float)) and not isinstance(band, bool) and band > max_band:
        errors.append(f"accuracy: {where} reads 'estimate' with a band over max_band {num(max_band)}")
    return errors


def check_counts(where: str, obj: dict, keys) -> list[str]:
    """The whole-number counts `keys` of an object that has them (a missing one is reported by the caller); only the
    key, one of the contract's own, is printed."""
    return [f"accuracy: {where} {k} is not a whole number" for k in keys if k in obj and not whole(obj[k])]


def check_shares(where: str, obj: dict, keys) -> list[str]:
    """The shares `keys` of an object that has them: each a number from 0 to 1. Only the key is printed."""
    return [f"accuracy: {where} {k} is not a share between 0 and 1" for k in keys if k in obj and not share(obj[k])]


def check_possible(where: str, obj: dict, keys, chains) -> list[str]:
    """Counts that could be real: none of the whole-number `keys` below 0, and along each chain of keys (a, b, ...)
    a <= b <= ... wherever both sides are whole numbers (a count that is not is reported by check_counts). Only the
    keys are printed."""
    errors = [f"accuracy: {where} {k} is below 0" for k in keys if whole(obj.get(k)) and obj[k] < 0]
    for chain in chains:
        for lo, hi in zip(chain, chain[1:]):
            if whole(obj.get(lo)) and whole(obj.get(hi)) and obj[lo] > obj[hi]:
                errors.append(f"accuracy: {where} has {lo} over {hi}")
    return errors


def check_by_period(rows) -> list[str]:
    """by_true_period: a list of objects with exactly BY_PERIOD_KEYS, a period from city.PERIODS and
    whole-number counts that could be real (none below 0, right <= n, right_estimate <= n_estimate <= n), and exactly
    one row per period of city.PERIODS, in order (checked once every row is an object with a known period). No value
    read from a row is printed."""
    if not isinstance(rows, list):
        return ["accuracy: by_true_period is not a list"]
    errors = []
    for i, row in enumerate(rows):
        where = f"by_true_period[{i}]"
        if not isinstance(row, dict):
            errors.append(f"accuracy: {where} is not an object")
            continue
        if not BY_PERIOD_KEYS <= set(row):
            errors.append(f"accuracy: {where} lacks one of {sorted(BY_PERIOD_KEYS)}")
            continue
        if not (isinstance(row["period"], str) and row["period"] in PERIOD_KEYS):
            errors.append(f"accuracy: {where} has a period outside city.PERIODS")
        errors += check_counts(where, row, ("n", "right", "n_estimate", "right_estimate"))
        errors += check_possible(where, row, ("n", "right", "n_estimate", "right_estimate"),
                                 (("right", "n"), ("right_estimate", "n_estimate", "n")))
        extra = stray(row, BY_PERIOD_KEYS)
        if extra:
            errors.append(f"accuracy: {where} has keys outside the accuracy table's: {extra}")
    periods = [row.get("period") if isinstance(row, dict) else None for row in rows]
    if all(isinstance(q, str) and q in PERIOD_KEYS for q in periods) and tuple(periods) != PERIOD_KEYS:
        errors.append("accuracy: by_true_period does not hold one row per period of city.PERIODS, in order")
    return errors


def check_external(s: dict, min_cell: int) -> list[str]:
    """The external entry's own rules, after its status and keys: every count present and a whole number,
    the 1990 split two objects with exactly SPLIT_KEYS, and "measured" exactly when min_cell or more buildings would
    show as "≈ year" (else the page prints counts, never a share). The counts could be real: none below 0,
    right_estimate and in_band_estimate at most n_estimate, n_estimate + n_unknown at most n_all (a PERIOD row is in
    neither), each half of the split the same with n_estimate at most n_all, and the halves adding up to the totals."""
    errors = []
    missing = sorted((SIDE_KEYS["external"] - {"status"}) - set(s))
    if missing:
        errors.append(f"accuracy: external lacks one of {missing}")
    errors += check_counts("external", s, EXTERNAL_COUNTS)
    shown_of = (("right_estimate", "n_estimate"), ("in_band_estimate", "n_estimate"))
    errors += check_possible("external", s, EXTERNAL_COUNTS, shown_of)
    if whole(s.get("n_estimate")) and whole(s.get("n_unknown")) and whole(s.get("n_all")) \
            and s["n_estimate"] + s["n_unknown"] > s["n_all"]:
        errors.append("accuracy: external has n_estimate + n_unknown over n_all")
    for name in EXTERNAL_SPLITS:
        if name not in s:
            continue
        part, where = s[name], f"external.{name}"
        if not isinstance(part, dict):
            errors.append(f"accuracy: {where} is not an object")
            continue
        if not SPLIT_KEYS <= set(part):
            errors.append(f"accuracy: {where} lacks one of {sorted(SPLIT_KEYS)}")
        extra = stray(part, SPLIT_KEYS)
        if extra:
            errors.append(f"accuracy: {where} has keys outside the accuracy table's: {extra}")
        errors += check_counts(where, part, sorted(SPLIT_KEYS))
        errors += check_possible(where, part, EXTERNAL_COUNTS[:4],
                                 (("right_estimate", "n_estimate", "n_all"), ("in_band_estimate", "n_estimate")))
    halves = [s.get(name) for name in EXTERNAL_SPLITS]
    if all(isinstance(h, dict) for h in halves):
        for k in EXTERNAL_COUNTS[:4]:                    # the split keys, in the contract's order
            parts = [h.get(k) for h in halves]
            if all(whole(v) for v in [s.get(k), *parts]) and sum(parts) != s[k]:
                errors.append(f"accuracy: external {k} is not before_1990's plus from_1990's")
    status, n = s.get("status"), s.get("n_estimate")
    if status in SIDE_STATUSES and whole(n):
        if status == "measured" and n < min_cell:
            errors.append(f"accuracy: external reads 'measured' with {num(n)} '≈ year' buildings (under {num(min_cell)})")
        if status == "not measurable" and n >= min_cell:
            errors.append(f"accuracy: external has {num(n)} '≈ year' buildings but reads 'not measurable'")
    return errors


def check_accuracy(cfg: dict) -> list[str]:
    """The accuracy table is present with exactly the contract's keys (on the table, the cells, the fallback
    rows and the area and external entries: a per-building diagnostic or a stadsdel name must not ship), uses the
    estimator's thresholds, every cell and fallback row is well-formed (see check_row: its numbers are present
    exactly when n >= min_cell), every share (right_period, within_one, band_coverage) is from 0 to 1 and every band
    above 0, the counts of by_true_period and the external entry could be real (check_by_period, check_external:
    none below 0, no part over its whole, the 1990 halves adding up, one by_true_period row per period in order),
    and it describes this build: result equals stats.byFlag's ESTIMATE and PERIOD counts and tested the
    building-level years (s03_tiles copies the file as it finds it, so another run's table could otherwise ship).
    Nothing read from the table is printed except through shown, quoted and num, and a value of the wrong type is an
    error line, never an exception."""
    acc = cfg.get("accuracy")
    if not isinstance(acc, dict):
        return ["accuracy: stockholm.json has no accuracy table (run s02_years and s03_tiles)"]
    errors = []
    extra = stray(acc, TABLE_KEYS)
    if extra:
        errors.append(f"accuracy: stockholm.json accuracy has keys outside the accuracy table's: {extra}")
    missing = sorted(TABLE_KEYS - set(acc))
    if missing:
        errors.append(f"accuracy: stockholm.json accuracy lacks keys the accuracy table requires: {missing}")
    for key in PINNED:
        if key in acc and acc[key] != city.ESTIMATE[key]:
            errors.append(f"accuracy: {key} is {num(acc[key])} but the estimator uses {num(city.ESTIMATE[key])} "
                          "(another build's table?)")
    # a missing or bad min_cell is reported above; the rows are then read against the estimator's
    min_cell = acc["min_cell"] if whole(acc.get("min_cell")) else city.ESTIMATE["min_cell"]
    for name, required, allowed in (("cells", CELL_KEYS, CELL_KEYS | CELL_NUMBERS),
                                    ("fallback", ROW_KEYS, FALLBACK_KEYS)):
        rows = acc.get(name, [])
        if not isinstance(rows, list):
            errors.append(f"accuracy: {name} is not a list")
            continue
        for i, row in enumerate(rows):
            errors += check_row(f"{name}[{i}]", row, required, allowed, min_cell)
            if name == "cells":
                errors += check_estimate_cell(f"{name}[{i}]", row, acc)
    if acc.get("band_coverage") is not None and not share(acc["band_coverage"]):   # None: no measurable cell (fixture)
        errors.append("accuracy: band_coverage is not a share between 0 and 1")
    if "by_true_period" in acc:
        errors += check_by_period(acc["by_true_period"])
    for side in ("area", "external"):
        if side not in acc:
            continue
        s = acc[side]
        if not isinstance(s, dict):
            errors.append(f"accuracy: {side} is not an object")
            continue
        if "status" not in s:
            errors.append(f"accuracy: {side} lacks a status")
        elif not (isinstance(s["status"], str) and s["status"] in SIDE_STATUSES):
            errors.append(f"accuracy: {side} has status {quoted(s['status'])}")
        extra = stray(s, SIDE_KEYS[side])
        if extra:
            errors.append(f"accuracy: {side} has keys outside the accuracy table's: {extra}")
        if side == "area":
            errors += check_shares("area", s, ("right_period",))
        if side == "external":
            errors += check_external(s, min_cell)
    f = cfg.get("stats", {}).get("byFlag", {})
    r = acc.get("result")
    if isinstance(r, dict):
        if (r.get("estimate"), r.get("period")) != (f.get("estimate"), f.get("period")):
            errors.append(f"accuracy: result says {num(r.get('estimate'))} estimate and {num(r.get('period'))} period "
                          f"but stats.byFlag has {num(f.get('estimate'))} and {num(f.get('period'))} "
                          "(another build's table?)")
    elif "result" in acc:
        errors.append("accuracy: result is not an object")
    known = sum(int(f.get(k, 0)) for k in ("exact", "range", "long"))
    if "tested" in acc and acc["tested"] != known:
        errors.append(f"accuracy: tested is {num(acc['tested'])} but the build has {num(known)} building-level years "
                      "(exact + range + long)")
    return errors


def decoded_tiles(out: Path, cfg: dict, errors: list[str]):
    """(tile entry, decoded tile) for every tile stockholm.json names; packs or tiles that fail are reported."""
    packs = {}
    for name in cfg.get("packs", []):
        if not (out / name).exists():
            errors.append(f"tiles: pack {name} is missing")
            continue
        packs[name] = gzip.decompress((out / name).read_bytes())
    for t in cfg.get("tiles", []):
        if t["pack"] not in packs:
            continue
        try:
            tile = parse(packs[t["pack"]], t["offset"])
        except (ValueError, IndexError) as e:
            errors.append(f"tiles: {t['file']} does not decode ({e})")
            continue
        yield t, tile


def check_tiles(out: Path, cfg: dict, n: int) -> list[str]:
    errors, seen, low, high = [], [], [], []
    floor_dm = round((city.TERRAIN["water_z"] + city.TERRAIN["ground_min"]) * 10)
    for t, tile in decoded_tiles(out, cfg, errors):
        if tile["end"] != t["offset"] + t["length"] or tile["nB"] != t["n"]:
            errors.append(f"tiles: {t['file']} length or count disagrees with stockholm.json")
        seen.append(tile["gid"])
        low.append(tile["gid"][tile["ground"] < floor_dm])
        high.append(tile["gid"][tile["ground"] > MAX_GROUND_DM])
    for found, what in ((low, "under the water's floor"), (high, f"more than {MAX_GROUND_DM / 10:g} m up")):
        g = np.concatenate(found) if found else np.zeros(0, np.uint32)
        if len(g):
            errors.append(f"tiles: {len(g)} buildings drawn {what} (gids {', '.join(map(str, np.sort(g)[:5]))}"
                          f"{' …' if len(g) > 5 else ''})")
    gids = np.concatenate(seen) if seen else np.zeros(0, np.uint32)
    counts = np.bincount(gids.astype(np.int64), minlength=n) if len(gids) else np.zeros(n, int)
    if len(counts) > n:
        errors.append(f"tiles: {int((counts[n:] > 0).sum())} gids at or above n={n}")
    counts = counts[:n]
    if (counts == 0).any():
        errors.append(f"tiles: {int((counts == 0).sum())} gids missing (gids {first_gids(counts == 0)})")
    if (counts > 1).any():
        errors.append(f"tiles: {int((counts > 1).sum())} gids drawn more than once (gids {first_gids(counts > 1)})")
    return errors


def check_tiles_attrs(out: Path, cfg: dict, a: np.ndarray) -> list[str]:
    """The shader draws a tile's year, yflag and period, the count and the card read attrs; per gid they must
    agree. Runs last, on a build with no other finding (any attrs finding would also show up here)."""
    errors = []
    for t, tile in decoded_tiles(out, cfg, errors):
        g = tile["gid"].astype(np.int64)
        ok = g < len(a)
        for field in ("year", "yflag", "period"):
            off = g[ok][tile[field][ok].astype(np.int64) != a[field][g[ok]].astype(np.int64)]
            if len(off):
                errors.append(f"tiles: {t['file']} {field} disagrees with attrs for {len(off)} gids "
                              f"(gids {', '.join(map(str, off[:5]))}{' …' if len(off) > 5 else ''})")
    return errors


def raa_hidden(a: np.ndarray, data: Path) -> np.ndarray:
    """Per gid, True where the card must not link RAÄ: a row marked private, or any non-curated building
    whose KATEGORI is in city.PRIVATE_HOUSE_KATEGORI, dated or not. KATEGORI is read by gid from
    data/buildings.parquet; without that file only the attrs `private` byte can be checked."""
    hidden = a["private"] != 0
    in_set = private_category(len(a), data)
    if in_set is not None:
        hidden = hidden | (in_set & (a["ysrc"] != codes.SRC_CURATED))
    return hidden


def read_shards(folder: Path) -> list[tuple[Path, dict]]:
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(folder.glob("*.json"))]


def check_photo(out: Path, where: str, photo, used: set[str]) -> list[str]:
    """One card photo: the credit the open licence asks for, the file it names (web/data/photos/<key>)."""
    if not isinstance(photo, dict):
        return [f"cards: {where} has a photo that is not an object"]
    errors = []
    extra = [shown(f, j, "field") for j, f in enumerate(sorted(set(photo) - set(PHOTO_FIELDS)))]
    if extra:
        errors.append(f"cards: {where} has photo fields outside a card's: {extra}")
    lic, key = str(photo.get("lic", "")), str(photo.get("key", ""))
    if not PHOTO_LICENCE.fullmatch(lic):
        errors.append(f"cards: {where} has a photo whose licence is not CC BY, CC BY-SA, CC0 or public domain")
    if not str(photo.get("by", "")).strip():
        errors.append(f"cards: {where} has a photo without its author")
    reader = "rd" in photo          # a reader's photo (pipeline/contributions.py): CC BY 4.0, no Commons page
    if reader and (lic != contributions.LICENCE or not contributions.REF.fullmatch(str(photo["rd"]))
                   or "page" in photo or "title" in photo):
        errors.append(f"cards: {where} has a reader's photo without CC BY 4.0 and its report's reference, or with a page")
    if not reader and not COMMONS_PAGE_ID.fullmatch(str(photo.get("page", ""))):
        errors.append(f"cards: {where} has a photo without its Commons page")
    if photo.get("lu") and not str(photo["lu"]).startswith("https://"):
        errors.append(f"cards: {where} has a photo whose licence link is not an https URL")
    if OLD_CC.fullmatch(lic) and not str(photo.get("title", "")).strip():
        errors.append(f"cards: {where} has a {lic} photo without its title")
    path = out.parent / "photos" / key
    if not re.fullmatch(r"[0-9a-f]{16}-\d+\.(jpg|png|webp)", key) or not path.is_file():
        errors.append(f"cards: {where} names a photo that is not in {out.parent.name}/photos")
    elif path.stat().st_size > city.WIKI["photo_bytes"]:
        errors.append(f"cards: {where} names a photo over {city.WIKI['photo_bytes']:,} bytes")
    if key not in used:
        errors.append(f"cards: {where} names a photo photos.json does not list")
    return errors


def check_cards(out: Path, a: np.ndarray, hidden: np.ndarray, allowed_names: set[str] | None = None,
                allowed_firms: set[str] | None = None, keys: np.ndarray | None = None) -> list[str]:
    """A card's fields; on a hidden card (raa_hidden: a private house, or a non-curated building in a private-house
    category) none of HIDDEN_FIELDS, a name only from the reviewed list, and no architect name that appears on
    city.ARCHITECT_MAX_RARE buildings or fewer unless it is a reviewed firm (the rare-architect rule: counted per building,
    `keys` from building_keys, as s02_attributes counts; a name the rule hid on a house is rare here
    too); each photo as check_photo; `rebuilt` and `cellars` only on a curated card and well formed."""
    allowed_names = load_private_names() if allowed_names is None else allowed_names
    allowed_firms = load_private_firms() if allowed_firms is None else allowed_firms
    errors, n = [], len(a)
    shards = read_shards(out / "cards")
    used_path = out / "photos.json"
    used = set(json.loads(used_path.read_text(encoding="utf-8"))) if used_path.exists() else set()
    owners = {}                  # a name's buildings: keys (building_keys) where given, else one per card
    for _, shard in shards:
        for key, card in shard.items():
            building = keys[int(key)] if keys is not None and key.isascii() and key.isdigit() and int(key) < n else key
            for name in set(card.get("architects", []) if isinstance(card, dict) else []):
                owners.setdefault(name, set()).add(building)
    named = {name: len(b) for name, b in owners.items()}
    for p, shard in shards:
        for i, (key, card) in enumerate(shard.items()):
            is_gid = key.isascii() and key.isdigit()
            ref = f"gid {shown(key, i)}" if is_gid else f"entry {shown(key, i)}"
            extra = [shown(f, j, "field") for j, f in enumerate(sorted(set(card) - set(CARD_FIELDS)))]
            if extra:
                errors.append(f"cards: {p.name} {ref} has fields other than a card's: {extra}")
            if not is_gid:
                errors.append(f"cards: {p.name} holds a non-gid key ({shown(key, i)})")
                continue
            if int(key) >= n or f"{int(key) % N_CARD_SHARDS:02d}.json" != p.name:
                errors.append(f"cards: {p.name} holds {ref}, which belongs elsewhere")
                continue
            if "photo" in card:
                errors += check_photo(out, f"{p.name} {ref}", card["photo"], used)
            errors += check_rebuilds(f"cards: {p.name} {ref}", card, a[int(key)])
            if "yrd" in card:
                errors += check_reader_line(f"cards: {p.name} {ref}", card["yrd"], a[int(key)], hidden[int(key)])
            for field in ("name", "en"):   # a register's building code is an internal id
                if isinstance(card.get(field), str) and REGISTER_CODE.search(card[field]):
                    errors.append(f"cards: {p.name} {ref} {field} carries a register's building code")
            if not hidden[int(key)]:
                continue
            # Each of them can state the exact year; the address too, when city.PRIVATE_ADDRESSES allows it
            for f in HIDDEN_FIELDS + (() if city.PRIVATE_ADDRESSES else ("addr", "addrn")):
                if f in card:
                    what = ("links its RAÄ record" if f == "raa" else f"carries `{f}`"
                            + (" (city.PRIVATE_ADDRESSES is False)" if f in ("addr", "addrn") else ""))
                    errors.append(f"cards: {p.name} {ref} is in a private-house category and {what}")
            if card.get("name") and card["name"] not in allowed_names:
                errors.append(f"cards: {p.name} {ref} is in a private-house category and carries a name not on "
                              "the reviewed list")
            rare = [x for x in card.get("architects", [])
                    if x not in allowed_firms and named.get(x, 0) <= city.ARCHITECT_MAX_RARE]
            if rare:
                errors.append(f"cards: {p.name} {ref} is in a private-house category and names {len(rare)} architect(s) "
                              f"found on {city.ARCHITECT_MAX_RARE} cards or fewer")
    return errors


def check_reader_line(where: str, yrd, rec, hide: bool) -> list[str]:
    """A card's `yrd` (the reader's report its year comes from): only on a reader-dated, non-hidden card; the reference,
    a one-line note with nothing email- or phone-like, an optional GitHub issue."""
    if not isinstance(yrd, dict) or set(yrd) - {"ref", "note", "url"}:
        return [f"{where} has a `yrd` that is not {{ref, note, url}}"]
    errors = []
    if rec["ysrc"] != codes.SRC_READER or hide:
        errors.append(f"{where} has `yrd` but its year is not a reader's, or it is a private house")
    note = str(yrd.get("note", ""))
    if not contributions.REF.fullmatch(str(yrd.get("ref", ""))) or not note or len(note) > 200 or "\n" in note:
        errors.append(f"{where} has a `yrd` without its reference or one-line note")
    if contributions.personal(note):
        errors.append(f"{where} has a reader's note with email-like or phone-like text")
    if "url" in yrd and not contributions.ISSUE.fullmatch(str(yrd["url"])):
        errors.append(f"{where} has a `yrd` link that is not a GitHub issue")
    return errors


def check_contributions(data: Path, path: Path = contributions.PATH) -> list[str]:
    """pipeline/contributions.csv: well formed, nothing email- or phone-like in a note or value (contributions.read),
    and no row's uuid on two footprints of data/buildings.parquet (one on none is a warning: s02/s03 skip it)."""
    if not path.exists():
        return [f"contributions: {path} is missing (seed it with its header)"]
    try:
        t = contributions.read(path)
    except ValueError as e:
        return [f"contributions: {e}"]
    if t.empty:
        return []
    if not (data / "buildings.parquet").exists():   # only a partial data/ (tests): nothing to resolve against
        print(f"s99_validate: warning: contributions: {len(t)} rows not resolved without {data / 'buildings.parquet'}",
              file=sys.stderr)
        return []
    b = pd.read_parquet(data / "buildings.parquet", columns=["gid", "uuid"])
    for ref in contributions.missing(t, b):     # a fixture build, or a redrawn footprint: s02/s03 skipped it too
        print(f"s99_validate: warning: contributions: {ref}: its footprint is not among these buildings", file=sys.stderr)
    t = t[~t.ref.isin(contributions.missing(t, b))]
    errors = []
    for i in range(len(t)):
        try:
            contributions.gids(t.iloc[[i]], b)
        except contributions.Refused as e:
            errors.append(f"contributions: {e}")
    return errors


def check_rebuilds(where: str, card: dict, rec) -> list[str]:
    """A card's `rebuilt` and `cellars`: only on a curated building (s08_landmarks checked them against its
    article); `rebuilt` a non-empty list of [year, kind] by year, each kind one of REBUILD_KINDS and each year after
    the card's own year, by YEAR_MAX (a rebuild never sets the year, §14 of the Gamla stan research); `cellars`
    true."""
    errors = []
    for f in ("rebuilt", "cellars"):
        if f in card and rec["ysrc"] != codes.SRC_CURATED:
            errors.append(f"{where} is not curated and carries `{f}`")
    if errors:
        return errors
    if "cellars" in card and card["cellars"] is not True:
        errors.append(f"{where} has `cellars` that is not true")
    if "rebuilt" not in card:
        return errors
    rebuilt = card["rebuilt"]
    pairs = isinstance(rebuilt, list) and rebuilt and all(
        isinstance(r, list) and len(r) == 2 and whole(r[0]) and isinstance(r[1], str) for r in rebuilt)
    if not pairs or [r[0] for r in rebuilt] != sorted(r[0] for r in rebuilt):
        return [*errors, f"{where} has `rebuilt` that is not a list of [year, kind] by year"]
    if any(kind not in REBUILD_KINDS for _, kind in rebuilt):
        errors.append(f"{where} has a rebuild whose kind is not {', '.join(REBUILD_KINDS[:-1])} or {REBUILD_KINDS[-1]}")
    if any(not int(rec["year"]) < year <= YEAR_MAX for year, _ in rebuilt):
        errors.append(f"{where} has a rebuild year not after its own year ({int(rec['year'])}) or after {YEAR_MAX}")
    return errors


def check_wiki(out: Path, a: np.ndarray, hidden: np.ndarray) -> list[str]:
    """The excerpt shards: their licence, their gids, never on a hidden card, text and revision, a language the
    card lists in `wp`, and no sentence that says who owns the building or had it built (privacy.owner)."""
    errors, n = [], len(a)
    wp = {}
    for _, shard in read_shards(out / "cards"):
        for key, card in shard.items():
            if key.isascii() and key.isdigit():
                wp[int(key)] = set(card.get("wp", []))
    for p, shard in read_shards(out / "wiki"):
        if not isinstance(shard, dict) or shard.get("licence") != WIKI_LICENCE or not isinstance(shard.get("items"), dict):
            errors.append(f"wiki: {p.name} is not {{licence: {WIKI_LICENCE}, items}} (the excerpts' licence, §6.1)")
            continue
        for i, (key, langs) in enumerate(shard["items"].items()):
            if not (key.isascii() and key.isdigit()) or int(key) >= n or f"{int(key) % N_CARD_SHARDS:02d}.json" != p.name:
                errors.append(f"wiki: {p.name} holds {shown(key, i)}, which is not a gid of this shard")
                continue
            g = int(key)
            if not isinstance(langs, dict):
                errors.append(f"wiki: {p.name} gid {g} is not {{lang: {{t, r}}}}")
                continue
            if hidden[g]:
                errors.append(f"wiki: {p.name} gid {g} is in a private-house category and carries an excerpt")
            for lang, e in (langs.items() if isinstance(langs, dict) else []):
                ok = (isinstance(e, dict) and isinstance(e.get("t"), str) and e["t"].strip()
                      and whole(e.get("r")) and e["r"] > 0)
                if not ok:
                    errors.append(f"wiki: {p.name} gid {g} has an excerpt without text or revision")
                if lang not in wp.get(g, set()):
                    errors.append(f"wiki: {p.name} gid {g} has an excerpt in a language its card does not link")
                if ok and owner(e["t"]):
                    errors.append(f"wiki: {p.name} gid {g} has an excerpt that says who owns the building or had it "
                                  "built")
    return errors


def check_photo_gids(out: Path, hidden: np.ndarray) -> list[str]:
    """photo-gids.json (s03_tiles.photo_gids): a sorted list of exactly the gids whose card has a photo. A hidden card
    with a photo is check_cards' error, so it is not counted here."""
    path = out / "photo-gids.json"
    if not path.exists():
        return ["photos: photo-gids.json is missing (run s03_tiles)"]
    listed = json.loads(path.read_text(encoding="utf-8"))
    if not (isinstance(listed, list) and all(whole(g) for g in listed) and listed == sorted(set(listed))):
        return ["photos: photo-gids.json is not a sorted list of gids"]
    n = len(hidden)
    has = {int(k) for _, shard in read_shards(out / "cards") for k, c in shard.items()
           if k.isascii() and k.isdigit() and isinstance(c, dict) and "photo" in c and not (int(k) < n and hidden[int(k)])}
    listed = {int(g) for g in listed}
    return ([f"photos: photo-gids.json lists gid {g}, whose card has no photo" for g in sorted(listed - has)
             if not (g < n and hidden[g])]
            + [f"photos: photo-gids.json leaves out gid {g}, whose card has a photo" for g in sorted(has - listed)])


def check_districts(out: Path, cfg: dict, n: int) -> list[str]:
    """Districts.bin.gz, one byte per gid naming its stadsdel in stockholm.json `districts` (0: none)."""
    names = cfg.get("districts")
    if names is None:
        return []
    path = out / "districts.bin.gz"
    if not path.exists():
        return ["districts: districts.bin.gz is missing (stockholm.json lists districts)"]
    b = np.frombuffer(gzip.decompress(path.read_bytes()), dtype=np.uint8)
    errors = [] if len(b) == n else [f"districts: districts.bin.gz has {len(b)} bytes for {n} buildings"]
    if len(b) and int(b.max()) > len(names):
        errors.append(f"districts: districts.bin.gz names stadsdel {int(b.max())} of {len(names)}")
    return errors


def check_beside_private(out: Path, a: np.ndarray, data: Path) -> list[str]:
    """No card whose footprint is not curated carries an item (`qid`, `wp`, a
    photo, an English label or an excerpt) whose point (data/wiki.parquet lon, lat) lies within city.WIKI private_m of an uncurated
    private-category house on the same property, as s06_wiki leaves such items out (wiki.beside_private). Without
    data/buildings.parquet, or a wiki table without points, there is nothing to check this by."""
    bpath, wpath = data / "buildings.parquet", data / "wiki.parquet"
    if not bpath.exists() or not wpath.exists() or not {"lon", "lat"} <= set(pq.read_schema(wpath).names):
        return []
    carried = set()
    for _, shard in read_shards(out / "cards"):
        carried |= {int(k) for k, c in shard.items() if k.isascii() and k.isdigit() and isinstance(c, dict)
                    and any(f in c for f in ("qid", "wp", "photo", "en"))}
    for _, shard in read_shards(out / "wiki"):
        items = shard.get("items") if isinstance(shard, dict) else None
        carried |= {int(k) for k in (items if isinstance(items, dict) else {}) if k.isascii() and k.isdigit()}
    w = pd.read_parquet(wpath, columns=["gid", "lon", "lat"])
    w = w[w.gid.isin(carried) & (w.gid < len(a))]
    w = w[a["ysrc"][w.gid.to_numpy(dtype=np.int64)] != codes.SRC_CURATED]
    if w.empty:
        return []
    b = gpd.read_parquet(bpath, columns=["gid", "kategori", "fastighet", "geometry"])
    x, y = lonlat_to_3011(w.lon.to_numpy(dtype=float), w.lat.to_numpy(dtype=float))
    near = beside_private(b, np.flatnonzero(a["ysrc"] == codes.SRC_CURATED), w.gid.to_numpy(), x, y)
    return [f"cards: gid {g} carries an item within {city.WIKI['private_m']:g} m of a private house on its property"
            for g in w.gid.to_numpy()[near]]


def addresses_of(data: Path, gids) -> set[tuple[str, str]]:
    """The (street, number) pairs, letter case aside, that sit on `gids` in data/addresses.parquet, withheld rows
    included: what may show on no footprint (addresses.sharing, the final review's F1)."""
    path = data / "addresses.parquet"
    gids = set(int(g) for g in gids)
    if not gids or not path.exists():
        return set()
    names = pq.read_schema(path).names
    p = pd.read_parquet(path, columns=[c for c in ("gid", "street", "number", "withheld") if c in names])
    # s02_addresses' own withheld rows count too: an address beside a takedown that landed on another footprint
    p = p[p.gid.isin(gids) | (p.withheld.to_numpy(bool) if "withheld" in p else False)]
    return {(str(s).casefold(), str(n).casefold()) for s, n in zip(p.street, p.number)}


def shard_pairs(out: Path) -> list[tuple[str, str, str]]:
    """(shard file name, street, number) for every address in search/addr/, misshapen entries skipped."""
    rows = []
    for p, shard in read_shards(out / "search" / "addr"):
        for street, pairs in shard.items() if isinstance(shard, dict) else ():
            rows += [(p.name, street, str(q[0])) for q in (pairs if isinstance(pairs, list) else ())
                     if isinstance(q, list) and q and isinstance(street, str)]
    return rows


def check_search(out: Path, cfg: dict, a: np.ndarray, hidden: np.ndarray,
                 designations: set[str] = frozenset(), data: Path | None = None) -> list[str]:
    """Search/index.json and its address shards, required once config.features.search is on. Every
    building entry names what its card names (so search shows nothing a card does not), every other name
    (`baliases`) is city.BUILDING_ALIASES' and points at the building whose card carries its target name, every gid
    is a building, every street's numbers sit in the shard it names, no street and number together read as a property
    designation of the city's buildings (`designations`: the shards keep the street and the number apart, which the
    privacy scan reads one by one), and a private-category house's address appears only as city.PRIVATE_ADDRESSES
    allows."""
    folder = out / "search"
    if not (folder / "index.json").exists():
        on = (cfg.get("features") or {}).get("search")
        return ["search: search/index.json is missing (run s14_search)"] if on else []
    errors, n = [], len(a)
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict):
        return ["search: search/index.json is not an object"]

    def listed(key: str) -> list:
        value = index.get(key, [])
        if isinstance(value, list):
            return value
        errors.append(f"search: index.json {key} is not a list")
        return []

    names: dict[int, set] = {}
    for _, shard in read_shards(out / "cards"):
        for key, card in shard.items() if isinstance(shard, dict) else ():
            if key.isascii() and key.isdigit() and isinstance(card, dict):
                names[int(key)] = {v for v in (card.get("name"), card.get("en")) if isinstance(v, str) and v}
    for i, b in enumerate(listed("buildings")):
        if not (isinstance(b, list) and len(b) == 4 and isinstance(b[0], str) and isinstance(b[3], str)
                and whole(b[1]) and 0 <= b[1] < n):
            errors.append(f"search: building entry {i} is not [name, gid, stadsdel, English label]")
        elif b[0] not in names.get(b[1], set()) or (b[3] and b[3] not in names.get(b[1], set())):
            errors.append(f"search: building entry {i} (gid {b[1]}) carries a name its card does not")
    for i, b in enumerate(listed("baliases")):
        ok = isinstance(b, list) and len(b) == 2 and isinstance(b[0], str) and whole(b[1]) and 0 <= b[1] < n
        if not ok or city.BUILDING_ALIASES.get(b[0]) not in names.get(b[1], set()):
            errors.append(f"search: other-name entry {i} is not one of city.BUILDING_ALIASES for its building's card name")
    for i, o in enumerate(listed("occupants")):              # what is inside a building: only one a card names
        if not (isinstance(o, list) and len(o) == 4 and isinstance(o[0], str) and isinstance(o[1], str) and o[0]
                and whole(o[2]) and 0 <= o[2] < n and isinstance(o[3], list)):
            errors.append(f"search: occupant entry {i} is not [Swedish name, English name, gid, other names]")
        elif not names.get(o[2]):
            errors.append(f"search: occupant entry {i} (gid {o[2]}) is in a building no card names")
    shards = {}
    for p, s in read_shards(folder / "addr"):
        if isinstance(s, dict):
            shards[p.stem] = s
        else:
            errors.append(f"search: addr/{p.name} is not an object")
    for i, s in enumerate(listed("streets")):
        if not (isinstance(s, list) and len(s) == 4 and isinstance(s[0], str) and s[0] in shards.get(str(s[3]), {})):
            errors.append(f"search: street entry {i} has no numbers in the shard it names")
    taken = None
    for p, shard in sorted(shards.items()):
        for j, (street, pairs) in enumerate(shard.items()):
            if not isinstance(pairs, list):
                errors.append(f"search: addr/{p}.json street {j} is not a list of [number, gid, stadsdel]")
                continue
            if designations and any(isinstance(pair, list) and pair and mentions(f"{street} {pair[0]}", designations)
                                    for pair in pairs):
                errors.append(f"search: addr/{p}.json street {j} holds an address that reads as a property "
                              "designation")
            for g in (pair[1] if isinstance(pair, list) and len(pair) == 3 else None for pair in pairs):
                if not whole(g) or not 0 <= g < n:
                    errors.append(f"search: addr/{p}.json street {j} holds an address on no building")
                elif hidden[g] and not city.PRIVATE_ADDRESSES:
                    errors.append(f"search: addr/{p}.json street {j} holds the address of gid {g}, a private-category "
                                  "house (city.PRIVATE_ADDRESSES is False)")
            # ... and not on a neighbour either, where an entrance node beside the house landed
            if not city.PRIVATE_ADDRESSES and data is not None and taken is None:
                taken = addresses_of(data, np.flatnonzero(hidden))
            if not city.PRIVATE_ADDRESSES and taken and any(
                    isinstance(pair, list) and pair and (street.casefold(), str(pair[0]).casefold()) in taken
                    and not (whole(pair[1]) and pair[1] < n and hidden[pair[1]]) for pair in pairs):
                errors.append(f"search: addr/{p}.json street {j} holds the address of a private-category house "
                              "(city.PRIVATE_ADDRESSES is False)")
    return errors


def check_suppressed(out: Path, a: np.ndarray, data: Path, entries: list[dict]) -> list[str]:
    """Every takedown in pipeline/suppress.yml names a building of this build, and that building
    ships nothing but its shape: "Year unknown" with no rating, an empty card (or none), no excerpt, and nowhere in
    search (a card may keep `nofloors`, a fact about its shape). Error lines name entries by their place in the file
    and buildings by gid, never by their keys."""
    if not entries:
        return []
    path = data / "buildings.parquet"
    if not path.exists():
        return [f"suppress: cannot check {len(entries)} takedowns without {path}"]
    names = pq.read_schema(path).names
    gids, missing = suppress.resolve(pd.read_parquet(path, columns=[c for c in ("gid", "uuid", "oid") if c in names]),
                                     entries)
    errors = [f"suppress: entry {i} matches no building of this build (a mistyped key leaves a home on the map)"
              for i in missing]
    def objects(folder):                      # the shards' objects; a misshapen one is check_cards'/check_search's
        return [s for _, s in read_shards(folder) if isinstance(s, dict)]

    def items(obj):
        return obj.items() if isinstance(obj, dict) else ()

    def lists(obj):
        return obj if isinstance(obj, list) else ()

    cards = {int(k): c for s in objects(out / "cards") for k, c in s.items() if k.isascii() and k.isdigit()}
    wiki = {int(k) for s in objects(out / "wiki") for k, _ in items(s.get("items")) if k.isascii() and k.isdigit()}
    found = set()
    if (out / "search" / "index.json").exists():
        index = json.loads((out / "search" / "index.json").read_text(encoding="utf-8"))
        index = index if isinstance(index, dict) else {}
        found |= {b[1] for b in lists(index.get("buildings")) if isinstance(b, list) and len(b) == 4}
        found |= {b[1] for b in lists(index.get("baliases")) if isinstance(b, list) and len(b) == 2}
        found |= {o[2] for o in lists(index.get("occupants")) if isinstance(o, list) and len(o) == 4}
        for shard in objects(out / "search" / "addr"):
            found |= {p[1] for _, pairs in items(shard) for p in lists(pairs) if isinstance(p, list) and len(p) == 3}
    for g in sorted(gids):
        if g >= len(a):
            continue
        # "Year unknown" in every field, the decade of a private house and its period colour included
        dated = any(int(a[f][g]) != 0 for f in ("year", "year_from", "year_to", "period", "ysrc", "private"))
        if a["yflag"][g] != codes.UNKNOWN or dated or a["rating"][g] != 0:
            errors.append(f"suppress: gid {g} is a takedown but ships a year or a rating")
        if set(cards.get(g) or {}) - {"nofloors"}:    # only the shape's own fact may stay
            errors.append(f"suppress: gid {g} is a takedown but has a card")
        if g in wiki:
            errors.append(f"suppress: gid {g} is a takedown but has an excerpt")
        if g in found:
            errors.append(f"suppress: gid {g} is a takedown but search finds it")
    # its addresses on any footprint: an entrance node beside the house can land on the garage or the neighbour (F1)
    taken = addresses_of(data, gids)
    if taken:
        for g, card in sorted(cards.items()):
            if isinstance(card, dict) and isinstance(card.get("addr"), str) and tuple(
                    card["addr"].casefold().rsplit(" ", 1)) in taken:
                errors.append(f"suppress: gid {g}'s card shows an address of a takedown")
        for name in sorted({f for f, street, num in shard_pairs(out) if (street.casefold(), num.casefold()) in taken}):
            errors.append(f"suppress: search addr/{name} holds an address of a takedown")
    return errors


def check_landmarks(cfg: dict, a: np.ndarray, data: Path) -> list[str]:
    """stockholm.json `landmarks`: each a curated building's own year, never a private-category house."""
    errors, n = [], len(a)
    in_set = private_category(n, data)
    for i, L in enumerate(cfg.get("landmarks", [])):
        g = L.get("gid") if isinstance(L, dict) else None
        if not whole(g) or not 0 <= g < n:
            errors.append(f"landmarks: entry {i} names no building")
            continue
        if a["ysrc"][g] != codes.SRC_CURATED or int(a["year"][g]) != L.get("year"):
            errors.append(f"landmarks: entry {i} is not the curated year of gid {g}")
        if a["private"][g] or (in_set is not None and in_set[g]):
            errors.append(f"landmarks: entry {i} is a private-category house")
    return errors


def _outline(rings):
    """A part's rings (tiles_decode.parts: exteriors, each followed by its holes) as one (Multi)Polygon."""
    import shapely
    polys = []
    for xz, hole in rings:
        if len(xz) < 3:
            continue
        if hole and polys:
            polys[-1][1].append(xz)
        elif not hole:
            polys.append((xz, []))
    return shapely.make_valid(shapely.union_all([shapely.Polygon(e, h) for e, h in polys]))


def check_towers(out: Path, cfg: dict, a: np.ndarray, data: Path) -> list[str]:
    """Laser tower parts (s03_tiles.tower_parts, every part of a building after its first): each on a gid that is not a
    private house (marked private, or a non-curated house in a private-house category), TOWER_M[0]..TOWER_M[1] m above
    its building's ground, and inside its building's footprint (within TOWER_INSIDE_M, for the decimetre vertices);
    Lantmäteriet's laser credited exactly when a tile draws one."""
    errors, scratch, n = [], [], len(a)
    in_set = private_category(n, data)
    hide = a["private"].astype(bool) | ((in_set if in_set is not None else np.zeros(n, bool))
                                        & (a["ysrc"] != codes.SRC_CURATED))
    found, private, height, outside = 0, set(), set(), set()
    for _, tile in decoded_tiles(out, cfg, scratch):        # a tile that does not decode is check_tiles' to report
        for b in np.flatnonzero(np.diff(tile["partStart"].astype(np.int64)) > 1):
            g = int(tile["gid"][b])
            first, *towers = tile_parts(tile, int(b))
            foot = _outline(first[1]).buffer(TOWER_INSIDE_M)
            for h, rings in towers:
                found += 1
                if g >= n or hide[g]:
                    private.add(g)
                if not TOWER_M[0] <= h <= TOWER_M[1]:
                    height.add(g)
                if _outline(rings).difference(foot).area > TOWER_OUTSIDE_M2:
                    outside.add(g)
    for gids, what in ((private, "on a private house or no building"),
                       (height, f"outside {TOWER_M[0]:g}..{TOWER_M[1]:g} m"), (outside, "outside its footprint")):
        if gids:
            g = sorted(gids)
            errors.append(f"towers: {len(g)} buildings with a laser part {what} (gids {', '.join(map(str, g[:5]))}"
                          f"{' …' if len(g) > 5 else ''})")
    credited = LASER_SOURCE in {s.get("id") for s in cfg.get("attribution", [])}
    if credited != bool(found):
        errors.append(f"attribution: Lantmäteriet's laser data is {'credited' if credited else 'not credited'}, but "
                      f"the tiles draw {found} laser tower parts")
    return errors


def strings(obj, path="$", numbers: bool = False):
    """Every string (keys and values) in a JSON value, with its JSON path; with numbers, every whole number too (an
    int, or a float with no fraction; never a bool). A key that is not identifier-like (it could be a UUID or a
    FASTIGHET) appears in the path as `[key #i]`, never as itself."""
    if isinstance(obj, str):
        yield path, obj
    elif numbers and isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if isinstance(obj, int) or obj.is_integer():
            yield path, int(obj)
    elif isinstance(obj, dict):
        for i, (k, v) in enumerate(obj.items()):
            here = f"{path}.{k}" if SAFE_KEY.fullmatch(k) else f"{path}[key #{i}]"
            yield here, k
            yield from strings(v, here, numbers)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from strings(v, f"{path}[{i}]", numbers)


def text_files(out: Path):
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        name = p.name.removesuffix(".gz")
        if not name.endswith(TEXT_SUFFIXES):
            continue
        raw = gzip.decompress(p.read_bytes()) if p.name.endswith(".gz") else p.read_bytes()
        yield p.relative_to(out), raw.decode("utf-8", errors="replace")


def check_privacy(out: Path, uuids: set[str], props: set[str], fnrs: set[int] = frozenset()) -> list[str]:
    """UUIDs, FASTIGHET designations and FNR property-unit keys must not reach web/: a key is caught as a
    digit run in any string, as a whole number anywhere in a JSON file, or as a field named fnr. Error lines carry
    the file and the JSON path, never the value."""
    errors = []
    for rel, text in text_files(out):
        try:
            found = list(strings(json.loads(text), numbers=True))
        except json.JSONDecodeError:
            found = [(f"line {i + 1}", line) for i, line in enumerate(text.splitlines())]
        for path, s in found:
            if isinstance(s, int):
                if s in fnrs:
                    errors.append(f"privacy: {rel} {path} holds a property-unit key (FNR)")
                continue
            if any(u.casefold() in uuids for u in UUID_RE.findall(s)):
                errors.append(f"privacy: {rel} {path} holds a City/register UUID")
            parts = ({normalise(s)} | {normalise(x) for x in SPLIT_RE.split(s)} | set(phrases(s))
                     | set(phrases(s.replace("_", " "))))     # a file name in a URL: "Diana_1.jpg"
            if parts & props:
                errors.append(f"privacy: {rel} {path} holds a property designation (FASTIGHET)")
            if fnrs and not ID_FORMAT.fullmatch(s) and any(int(d) in fnrs for d in DIGITS_RE.findall(s)):
                errors.append(f"privacy: {rel} {path} holds a property-unit key (FNR)")
            if s.casefold() == "fnr" and not path.startswith("line "):
                errors.append(f"privacy: {rel} {path} is a property-unit key field (FNR)")
    return errors


def check_plaques(out: Path, n_buildings: int) -> list[str]:
    """The blue plaques (s15_plaques), when the version has them: each on a real gid, with its id, name, text, the
    credit (plaques.CREDIT: Samfundet S:t Erik, CC BY 4.0) and a finite position; no plaque twice."""
    path = out / "plaques.json"
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["plaques: plaques.json is not JSON"]
    if not isinstance(items, list):
        return ["plaques: plaques.json is not a list"]
    errors, seen = [], set()
    for i, p in enumerate(items):
        pid = p.get("id", f"#{i}") if isinstance(p, dict) else f"#{i}"
        if not isinstance(p, dict):
            errors.append(f"plaques: {pid} is not an object")
            continue
        g = p.get("gid")
        if not isinstance(g, int) or isinstance(g, bool) or not 0 <= g < n_buildings:
            errors.append(f"plaques: {pid} is on gid {g!r}, not a building of this version")
        if p.get("credit") != plaques.CREDIT:
            errors.append(f"plaques: {pid} lacks its credit ({plaques.CREDIT!r})")
        errors += [f"plaques: {pid} has no {k}" for k in ("name", "text") if not str(p.get(k) or "").strip()]
        if not all(isinstance(p.get(k), (int, float)) and math.isfinite(p[k]) for k in ("x", "z")):
            errors.append(f"plaques: {pid} has no position")
        if owner(str(p.get("text") or "")):
            errors.append(f"plaques: {pid} has a text that says who owns the building or had it built (spec §6.3)")
        if pid in seen:
            errors.append(f"plaques: {pid} twice")
        seen.add(pid)
    return errors


BR_KEYS = {"medieval", "felled", "inv", "credit"}
BR_INV_KEYS = {"from", "to", "report"}


def _year(v, lo: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= YEAR_MAX


def check_archaeology(out: Path, hidden: np.ndarray) -> list[str]:
    """The City Museum's building-archaeology section (card `br`, s02_stadsmuseet): never on a hidden card (a private
    house, raa_hidden); only its own fields; `medieval` true when there, `felled` sorted distinct years 1000..2026,
    `inv` a non-empty list of investigations, each with its years from YEAR_MIN (1900) to 2026 in order (or none)
    and a report only as an https link to the record in Digitala Stadsmuseet (stadsmuseet.REPORT_RE); the credit
    stadsmuseet.CREDIT."""
    errors = []
    for p, shard in read_shards(out / "cards"):
        for i, (key, card) in enumerate(shard.items()):
            if not isinstance(card, dict) or "br" not in card or not (key.isascii() and key.isdigit()):
                continue
            ref, br = f"cards: {p.name} gid {shown(key, i)} br", card["br"]
            if int(key) < len(hidden) and hidden[int(key)]:
                errors.append(f"{ref}: building archaeology on a private house")
            if not isinstance(br, dict):
                errors.append(f"{ref} is not an object")
                continue
            extra = [shown(f, j, "field") for j, f in enumerate(sorted(set(br) - BR_KEYS))]
            if extra:
                errors.append(f"{ref} has fields other than its own: {extra}")
            if br.get("credit") != stadsmuseet.CREDIT:
                errors.append(f"{ref} lacks its credit ({stadsmuseet.CREDIT!r})")
            if "medieval" in br and br["medieval"] is not True:
                errors.append(f"{ref} medieval is not true")
            felled = br.get("felled", [])
            if not (isinstance(felled, list) and (felled or "felled" not in br) and all(_year(y, 1000) for y in felled)
                    and felled == sorted(set(felled))):
                errors.append(f"{ref} felled is not a sorted list of distinct years")
            inv = br.get("inv")
            if not isinstance(inv, list) or not inv:
                errors.append(f"{ref} has no investigations")
                continue
            for k, e in enumerate(inv):
                where = f"{ref} inv[{k}]"
                if not isinstance(e, dict) or set(e) - BR_INV_KEYS:
                    errors.append(f"{where} is not an investigation ({sorted(BR_INV_KEYS)})")
                    continue
                if ("from" in e) != ("to" in e) or ("from" in e and not (
                        _year(e["from"], stadsmuseet.YEAR_MIN) and _year(e["to"], stadsmuseet.YEAR_MIN)
                        and e["from"] <= e["to"])):
                    errors.append(f"{where} has years out of order or outside {stadsmuseet.YEAR_MIN}..{YEAR_MAX}")
                if "report" in e and not (isinstance(e["report"], str) and stadsmuseet.REPORT_RE.fullmatch(e["report"])):
                    errors.append(f"{where} report is not an https link to Digitala Stadsmuseet")
    return errors


def register_designations(data: Path) -> set[str]:
    """The City Museum's register's property designations (stadsmuseet.cached_designations): checked like FASTIGHET in
    every shipped file."""
    return stadsmuseet.cached_designations(data)


def check_metro(out: Path) -> list[str]:
    """Tunnelbanan (s16_metro), when the version has it: every date parses, every segment's stations are in the
    stations list, the lines are green, red or blue, and every coordinate is finite and inside the map."""
    path = out / "metro.json"
    if not path.exists():
        return []
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["metro: metro.json is not JSON"]
    if not isinstance(m, dict) or not isinstance(m.get("segments"), list) or not isinstance(m.get("stations"), list):
        return ["metro: metro.json needs a segments list and a stations list"]

    def date_ok(v) -> bool:
        try:
            datetime.date.fromisoformat(v)
            return True
        except (TypeError, ValueError):
            return False

    def inside(x, z) -> bool:
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= MAX_LOCAL_M
                   for v in (x, z))

    errors, names = [], set()
    for i, s in enumerate(m["stations"]):
        name = s.get("name") if isinstance(s, dict) else None
        if not isinstance(name, str) or not name.strip():
            errors.append(f"metro: station #{i} has no name")
            continue
        if name in names:
            errors.append(f"metro: station {name} twice")
        names.add(name)
        if not (s.get("never") and s.get("opened") is None) and not date_ok(s.get("opened")):
            errors.append(f"metro: station {name} has an opening date that does not parse: {s.get('opened')!r}")
        if "closed" in s and not date_ok(s["closed"]):
            errors.append(f"metro: station {name} has a closing date that does not parse: {s['closed']!r}")
        if not s.get("lines") or not set(s["lines"]) <= METRO_LINES:
            errors.append(f"metro: station {name} has lines {s.get('lines')!r}")
        if not inside(s.get("x"), s.get("z")):
            errors.append(f"metro: station {name} is not inside the map")
    for i, g in enumerate(m["segments"]):
        sid = g.get("id", f"#{i}") if isinstance(g, dict) else f"#{i}"
        if not isinstance(g, dict):
            errors.append(f"metro: segment {sid} is not an object")
            continue
        if not date_ok(g.get("opened")):
            errors.append(f"metro: segment {sid} has an opening date that does not parse: {g.get('opened')!r}")
        if "closed" in g and not date_ok(g["closed"]):
            errors.append(f"metro: segment {sid} has a closing date that does not parse: {g['closed']!r}")
        if g.get("line") not in METRO_LINES:
            errors.append(f"metro: segment {sid} has line {g.get('line')!r}")
        missing = [n for n in g.get("stations") or [] if n not in names]
        if missing or len(g.get("stations") or []) < 2:
            errors.append(f"metro: segment {sid} names stations not in the list: {missing or g.get('stations')}")
        track = g.get("track")
        if not isinstance(track, list) or len(track) < 2:
            errors.append(f"metro: segment {sid} has no track")
        elif not all(isinstance(p, list) and len(p) == 2 and inside(*p) for p in track):
            errors.append(f"metro: segment {sid} has track outside the map")
    return errors


def validate(out: Path, data: Path = DATA, *, release: bool = False, sources: list[dict] | None = None,
             takedowns: list[dict] | None = None) -> list[str]:
    out, data = Path(out), Path(data)
    sources = load_sources(SOURCES) if sources is None else sources
    takedowns = suppress.load() if takedowns is None else takedowns
    errors = [f"sources: {e}" for e in check_sources(sources, release=release)]
    if release:
        # A public map names who made it and where to write (GDPR Art. 14; About and the card use both)
        errors += [f"release: city.{k} is empty (decision 2: who made the map and the address for corrections "
                   "and takedowns)" for k in ("MAKER", "CONTACT") if not getattr(city, k)]
        errors += [f"release: waiting for {w} (city.RELEASE_WAITS_FOR)" for w in city.RELEASE_WAITS_FOR]
    cfg_path = out / f"{city.SLUG}.json"
    if not cfg_path.exists():
        return [*errors, f"missing {cfg_path}"]
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    errors += check_sizes(out, cfg)
    errors += check_base(out, cfg)
    errors += check_terrain(out, cfg, data, release=release, sources=sources)
    errors += check_attribution(cfg)
    attrs_path = out / "attrs.bin.gz"
    if not attrs_path.exists():
        return [*errors, f"missing {attrs_path}"]
    a = np.frombuffer(gzip.decompress(attrs_path.read_bytes()), dtype=ATTR_DTYPE)
    if len(a) != cfg["stats"]["buildings"]:
        errors.append(f"attrs: {len(a)} records but stats.buildings is {cfg['stats']['buildings']}")
    periods = [(p["from"], p["to"]) for p in cfg["periods"]] if cfg.get("periods") else None
    errors += check_attrs(a, periods)
    errors += check_histograms(cfg)
    errors += check_accuracy(cfg)
    errors += check_tiles(out, cfg, len(a))
    mismatch = check_data(out, data, len(a))
    if mismatch:  # the checks below would read another build's rows by gid
        return [*errors, *mismatch]
    errors += check_private_marked(a, data)
    errors += check_osm_floors(a, data)
    hidden = raa_hidden(a, data)
    errors += check_cards(out, a, hidden, keys=building_keys(len(a), data))
    errors += check_wiki(out, a, hidden)
    errors += check_photo_gids(out, hidden)
    errors += check_beside_private(out, a, data)
    errors += check_landmarks(cfg, a, data)
    errors += check_towers(out, cfg, a, data)
    errors += check_districts(out, cfg, len(a))
    errors += check_suppressed(out, a, data, takedowns)
    errors += check_contributions(data)
    sets = privacy_sets(data) if (data / "buildings.parquet").exists() else None
    errors += check_search(out, cfg, a, hidden, sets[1] if sets else frozenset(), data)
    errors += check_plaques(out, len(a))
    errors += check_archaeology(out, hidden)
    errors += check_metro(out)
    if sets:
        uuids, props, fnrs = sets
        errors += check_privacy(out, uuids, props | register_designations(data), fnrs)
    else:
        errors.append(f"privacy: cannot check without {data / 'buildings.parquet'}")
    if not errors:
        errors += check_tiles_attrs(out, cfg, a)
    return errors


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s99_validate", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="version to check (default: the one in web/data/current.json)")
    ap.add_argument("--data", default=str(DATA), help="pipeline data directory (for the privacy sets)")
    ap.add_argument("--release", action="store_true", help="also fail on sources still pending-O1")
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    args = ap.parse_args(argv)
    version = args.version or json.loads(CURRENT.read_text())["version"]
    out = CURRENT.parent / version
    takedowns = suppress.load(args.suppress)
    errors = validate(out, Path(args.data), release=args.release, takedowns=takedowns)
    if errors:
        print(f"s99_validate: {len(errors)} problem(s) in {out}:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        raise SystemExit(1)
    # the takedowns it checked: 0 where pipeline/suppress.yml should hold some means the file was lost (docs/privacy.md)
    print(f"s99_validate: {out} OK{' (release)' if args.release else ''}; {len(takedowns)} takedowns checked")


if __name__ == "__main__":
    main(sys.argv[1:])
