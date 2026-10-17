"""Floors, Stadsmuseet rating, protection, architects and a safe display name per building (Plan 1, Plan 4a).

floors      OSM building:levels where an OSM building matches the footprint (pipeline/osm_buildings.py: IoU above
            city.FLOORS_OSM's min_iou), fsrc FLOORS_OSM; else round(height / storey height for the KATEGORI), half
            up, clamped to 1..99, fsrc FLOORS_HEIGHT. Both stay as columns of their own (floors_osm, 0 where OSM has
            none; floors_h), so the OSM-derived values can be split off if O1 rules out ODbL for the whole (§6.1).
nofloors    True where the floors come from the height and storeys mean little: a church (RAÄ purpose group in
            city.NO_FLOORS_PURPOSE) or a KATEGORI in city.NO_FLOORS_KATEGORI; the card leaves its floors row out.
rating      klassificering of the linked RAÄ record (years.raa_id): Blått 1, Grönt 2, Gult 3, else 0.
prot        the linked RAÄ record's legal protection (skyddstyp_namn): codes.PROTECTION, else 0; since: the year of
            its decision (beslutsdatum) for a listed building (prot 1 or 2), else 0.
architects  RAÄ upphov entries whose role is exactly "Arkitekt", as "First Surname", deduplicated in order.
            Byggherre (owner) and Byggmästare entries never leave this step. On a private-category house that is
            not curated, a name used on city.ARCHITECT_MAX_RARE buildings or fewer citywide is dropped unless it is
            a firm on the reviewed list pipeline/private_firms.txt (D35 point 2, pipeline/architects.py).
name        the curated landmark name; else RAÄ namn, then alternativnamn, unless it looks like a property
            designation ("Kv Storken 12", "Lilla Sticklinge 1:4"), is a bare stadsdel name ("Sätra") or names only
            the building's kind ("Bostadshus", city.GENERIC_NAMES); else "". A private-category house that is not
            curated keeps a name only when it is on the reviewed list pipeline/private_names.txt (a house name can
            carry its owner's).

Writes data/attributes.parquet (contracts C3, C20), and for the hand checks (internal, git-ignored with data/):
data/review-architects.txt, the rare names on private houses that read as firms and are not on private_firms.txt yet
(hidden until a person has read them), and data/review-names.txt, the private houses' names the list does not hold yet.
"""
import argparse
import os
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

from . import architects as arch
from . import city, osm_buildings, suppress
from .codes import FLOORS_HEIGHT, FLOORS_OSM, PROT_LISTED, PROT_STATE, PROTECTION, RATING
from .s00_fetch_city import OUT as CITY_RAW
from .s00_fetch_osm import fixture_tiles, tiles
from .s00_fetch_raa import LAYER as RAA_LAYER
from .s02_years import BUILDINGS, RAA_GPKG, load_raa
from .yearrules import LATEST_YEAR

YEARS = Path("data/years.parquet")
STADSDELAR = CITY_RAW / "Stadsdelar.zip"      # data/raw/city/Stadsdelar.zip (C3 raw inputs)
OUT = Path("data/attributes.parquet")
PRIVATE_NAMES = Path(__file__).with_name("private_names.txt")
PRIVATE_FIRMS = Path(__file__).with_name("private_firms.txt")
REVIEW_ARCHITECTS = Path("data/review-architects.txt")
REVIEW_NAMES = Path("data/review-names.txt")

# A property designation: "Storken 12", "Kv. Bacchus 6", "Lilla Sticklinge 1:4", "Storken-12", "kv.Storken 12": up to
# four words, then a number or number:number (Plan 1's one-word form missed the multi-word ones, P5).
PROPERTY_DESIGNATION = re.compile(r"^(kv\.?\s*)?[a-zåäöéü][\w.åäöéü-]*(\s+[\w.åäöéü-]+){0,3}\s*[-–]?\s*\d+(:\d+)?$",
                                  re.IGNORECASE)
GENERIC = re.compile(city.GENERIC_NAME_RE, re.IGNORECASE)
# A register's building code in a name ("K0061.006", a state-listed building's numbers; Plan 4b, Task 10): an internal
# id, never shown. Taken out with its brackets and separator; a name of codes alone becomes "".
REGISTER_CODE = re.compile(r"\s*\(?\s*\b[A-Z]\d{4}\.\d{3}\b\s*\)?\s*[,;]?")
EMPTY_BRACKETS = re.compile(r"\(\s*[,;]?\s*\)")
QUOTED = re.compile(r'"([^"]*)"')
SURNAME_FIRST = re.compile(r"[^,]+,(?!\s)[^,]+")   # "Surname,First": one comma with nothing, not even a space, after it
NOT_A_NAME = {"okänd", "osignerad"}            # RAÄ writes "Okänd," (unknown) and "Osignerad," (unsigned)


def storey_height(kategori) -> np.ndarray:
    """Metres per storey for each KATEGORI: city.STOREY_M at call time, "_default" for the rest."""
    table = city.STOREY_M
    return np.array([table.get(c, table["_default"]) for c in kategori], dtype=float)


def floors_from_storey(height, k) -> np.ndarray:
    """The C1 floors rule: clamp(floor(height / k + 0.5), 1, 99), so a half storey rounds up. uint8."""
    return np.clip(np.floor(np.asarray(height, dtype=float) / np.asarray(k, dtype=float) + 0.5), 1, 99).astype(np.uint8)


def floors_from_height(height, kategori) -> np.ndarray:
    return floors_from_storey(height, storey_height(kategori))


def parse_architects(upphov) -> list[str]:
    """'"Surname,First:Role"; ...' -> ["First Surname", ...] for role exactly "Arkitekt".

    Only the compact form "Surname,First" is flipped. A comma followed by a space belongs to a firm name or a
    list ("Hagström & Ekman", "Ancker Gate Lindegren, Arkitekter SAR", "S Ancker, B Gate, S Lindegren"), which is
    kept as written, whitespace-normalised. The placeholders "Okänd," and "Osignerad," are dropped.
    """
    if not isinstance(upphov, str) or not upphov.strip():
        return []
    out: list[str] = []
    for entry in QUOTED.findall(upphov) or upphov.split(";"):
        who, sep, role = entry.strip().rpartition(":")
        if not sep or role.strip() != "Arkitekt":
            continue
        parts = [" ".join(p.split()) for p in who.split(",")]
        flip = SURNAME_FIRST.fullmatch(who) is not None and all(parts)    # tested on the raw text, before the collapse
        name = f"{parts[1]} {parts[0]}" if flip else ", ".join(p for p in parts if p)
        if name and name.casefold() not in NOT_A_NAME and name not in out:
            out.append(name)
    return out


def safe_name(name, districts: set[str]) -> str:
    """name, or "" if it is empty, looks like a property designation, is a bare stadsdel name or names only the
    building's kind (city.GENERIC_NAMES, GENERIC_NAME_RE). A register's building code is taken out first."""
    if not isinstance(name, str):
        return ""
    n = " ".join(EMPTY_BRACKETS.sub("", REGISTER_CODE.sub("", name)).strip(" ,;").split())
    if not n or PROPERTY_DESIGNATION.match(n) or n.casefold() in districts:
        return ""
    if n.casefold() in city.GENERIC_NAMES or GENERIC.match(n):
        return ""
    return n


def load_private_names(path: Path = PRIVATE_NAMES) -> set[str]:
    """The reviewed names a private house may carry: one per line, # starts a comment."""
    if not Path(path).exists():
        return set()
    lines = (line.split("#", 1)[0].strip() for line in Path(path).read_text(encoding="utf-8").splitlines())
    return {" ".join(line.split()) for line in lines if line}


def load_private_firms(path: Path = PRIVATE_FIRMS) -> set[str]:
    """The reviewed firm names a private house may show however rare (D35 point 2): the same form as the names list."""
    return load_private_names(path)


def load_districts(path: Path = STADSDELAR) -> set[str]:
    """Casefolded stadsdel names (NAMN) from Stadsdelar.zip."""
    names = pyogrio.read_dataframe(path, columns=["NAMN"], read_geometry=False).NAMN
    return {str(n).casefold() for n in names if isinstance(n, str)}


def decision_year(value) -> int:
    """The year of RAÄ's beslutsdatum (a date, a timestamp or "YYYY-MM-DD"), or 0. A bare number is no date
    (pd.Timestamp would read 1935 as nanoseconds, 1970), and a year outside 1900..LATEST_YEAR is no decision year."""
    if value is None or isinstance(value, (bool, int, float, np.number)) or value is pd.NaT:
        return 0
    try:
        year = int(pd.Timestamp(value).year)
    except (ValueError, TypeError, OverflowError):
        return 0
    return year if 1900 <= year <= LATEST_YEAR else 0


# The RAÄ fields this step reads (s02_years.RAA_FIELDS loads them). pyogrio skips a missing column without a word, so
# main() checks they are there: a renamed skyddstyp_namn would otherwise give every building prot 0.
RAA_READS = ("namn", "alternativnamn", "klassificering", "upphov", "andamal_huvudgrupp", "skyddstyp_namn",
             "beslutsdatum")


def osm_tiles_needed() -> list[str]:
    """The levels tiles s00_fetch_osm caches: all of city.OSM_TILES, or with HFH_FIXTURE=1 the fixture's own."""
    return [k for k, _ in (fixture_tiles() if os.environ.get("HFH_FIXTURE") == "1" else tiles())]


def missing_osm_tiles(folder: Path) -> list[str]:
    """The needed tiles that are not in folder: a city with some tiles missing would quietly take its floors from
    the height there."""
    return [k for k in osm_tiles_needed() if not (Path(folder) / f"{k}.json").exists()]


def build_attributes(b: pd.DataFrame, years: pd.DataFrame, raa: pd.DataFrame, districts: set[str],
                     levels: pd.Series | None = None, private_names: set[str] = frozenset(),
                     report: dict | None = None, private_firms: set[str] = frozenset(),
                     exclude: set[int] = frozenset()) -> pd.DataFrame:
    """attributes.parquet rows (C3, C20) from buildings (gid, kategori, height), years (gid, raa_id, landmark),
    RAÄ records (raa_id, klassificering, upphov, namn, alternativnamn, skyddstyp_namn, beslutsdatum,
    andamal_huvudgrupp), OSM levels per gid (osm_buildings.match; None: none), the reviewed private-house names and
    the reviewed firm names. `report`, when given, receives "firms" (rare names on private houses that read as firms,
    not on the firms list: hidden until a person has read them) and "names" (private houses' names not on the list),
    for the hand checks. `exclude` (Plan 4b): the takedowns' gids, whose architects do not count towards D35's rule, as
    they do not ship (s99 counts over the shipped cards); main() then blanks those rows (suppress.attributes)."""
    d = b[["gid", "kategori", "height"]].merge(years[["gid", "raa_id", "landmark"]], on="gid", how="left")
    d["raa_id"] = d.raa_id.fillna("")
    d["landmark"] = d.landmark.fillna("")
    cols = ["klassificering", "upphov", "namn", "alternativnamn", "skyddstyp_namn", "beslutsdatum", "andamal_huvudgrupp"]
    raa = raa.reindex(columns=["raa_id", *cols])
    rec = raa[raa.raa_id != ""].drop_duplicates("raa_id").set_index("raa_id")[cols]
    r = rec.reindex(d.raa_id)
    names = [lm or safe_name(n, districts) or safe_name(a, districts)
             for lm, n, a in zip(d.landmark, r.namn, r.alternativnamn)]
    # D18 and D35.2 on a private-category house that is not curated: KATEGORI decides, never the `private` flag
    house = d.kategori.isin(city.PRIVATE_HOUSE_KATEGORI).to_numpy() & (d.landmark == "").to_numpy()
    unlisted = sorted({n for n, h in zip(names, house) if h and n and n not in private_names})
    names = ["" if h and n not in private_names else n for n, h in zip(names, house)]
    building = [rid or f"gid {g}" for rid, g in zip(d.raa_id, d.gid)]     # D35 counts buildings, not footprints
    lists = [[] if g in exclude else parse_architects(u) for g, u in zip(d.gid, r.upphov)]
    architects, firms = arch.apply_rule(lists, house, firms=private_firms, keys=building)
    if report is not None:
        report.update(firms=firms, names=unlisted)
    floors_h = floors_from_height(d.height, d.kategori)
    osm = np.zeros(len(d), dtype=np.uint8)
    if levels is not None and len(levels):
        osm = levels.reindex(d.gid).fillna(0).to_numpy().astype(np.uint8)
    from_osm = osm > 0
    prot = r.skyddstyp_namn.map(PROTECTION).fillna(0).to_numpy().astype(np.uint8)
    listed = np.isin(prot, (PROT_STATE, PROT_LISTED))
    since = np.where(listed, [decision_year(v) for v in r.beslutsdatum], 0).astype(np.int16)
    church = r.andamal_huvudgrupp.isin(city.NO_FLOORS_PURPOSE).to_numpy()
    nofloors = ~from_osm & (church | d.kategori.isin(city.NO_FLOORS_KATEGORI).to_numpy())
    out = pd.DataFrame({
        "gid": d.gid.to_numpy().astype(np.int32),
        "floors": np.where(from_osm, osm, floors_h).astype(np.uint8),
        "fsrc": np.where(from_osm, FLOORS_OSM, FLOORS_HEIGHT).astype(np.uint8),
        "rating": r.klassificering.map(RATING).fillna(0).to_numpy().astype(np.uint8),
        "architects": architects,
        "name": pd.array(names, dtype="str"),
        "floors_h": floors_h,
        "floors_osm": osm,
        "prot": prot,
        "since": since,
        "nofloors": nofloors,
    })
    return out.sort_values("gid").reset_index(drop=True)


def summary(a: pd.DataFrame) -> dict:
    return {
        "buildings": len(a),
        "rating": {k: int((a.rating == v).sum()) for k, v in RATING.items()},
        "with_architects": int((a.architects.map(len) > 0).sum()),
        "named": int((a.name != "").sum()),
        "floors_max": int(a.floors.max()),
        "floors_median": float(a.floors.median()),
        "floors_osm": int((a.fsrc == FLOORS_OSM).sum()),
        "protected": {k: int((a.prot == v).sum()) for k, v in PROTECTION.items()},
        "nofloors": int(a.nofloors.sum()),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s02_attributes", description=__doc__.splitlines()[0])
    ap.add_argument("--buildings", type=Path, default=BUILDINGS)
    ap.add_argument("--years", type=Path, default=YEARS)
    ap.add_argument("--raa", type=Path, default=RAA_GPKG)
    ap.add_argument("--stadsdelar", type=Path, default=STADSDELAR)
    ap.add_argument("--osm-levels", type=Path, default=osm_buildings.LEVELS, help="s00_fetch_osm's levels tiles")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--review-architects", type=Path, default=REVIEW_ARCHITECTS)
    ap.add_argument("--review-names", type=Path, default=REVIEW_NAMES)
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    a = ap.parse_args(argv or [])
    missing = missing_osm_tiles(a.osm_levels)
    if missing:
        raise SystemExit(f"{a.osm_levels} lacks {len(missing)} of {len(osm_tiles_needed())} tiles "
                         f"({', '.join(missing)}): run s00_fetch_osm first")
    fields = set(pyogrio.read_info(a.raa, layer=RAA_LAYER)["fields"])
    lacking = [f for f in RAA_READS if f not in fields]
    if lacking:
        raise SystemExit(f"{a.raa} lacks {', '.join(lacking)}: RAÄ renamed or dropped a field this step reads")
    b = gpd.read_parquet(a.buildings, columns=["gid", "kategori", "height", "geometry"])
    levels = osm_buildings.match(b, osm_buildings.load(a.osm_levels, osm_tiles_needed()))
    report = {}
    hidden = suppress.gids_of(a.buildings, a.suppress)                      # Plan 4b: takedowns
    attrs = build_attributes(b, pd.read_parquet(a.years), load_raa(a.raa), load_districts(a.stadsdelar), levels,
                             load_private_names(), report, load_private_firms(), exclude=hidden)
    attrs = suppress.attributes(attrs, hidden)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    attrs.to_parquet(a.out, index=False)
    for path, lines, what in ((a.review_architects, report["firms"],
                               "rare names on private houses that read as firms, hidden until private_firms.txt has them"),
                              (a.review_names, report["names"], "private houses' names not in private_names.txt")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {what} (hand check; internal)\n" + "".join(f"{x}\n" for x in lines), encoding="utf-8")
        print(f"{len(lines)} {what} -> {path}")
    print(summary(attrs))


if __name__ == "__main__":
    main(sys.argv[1:])
