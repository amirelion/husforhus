"""Readers' reports the owner accepted (web/admin/, src/admin.js), as data: pipeline/contributions.csv.

scripts/contributions.mjs `pull` writes the table from D1 (it runs `python -m pipeline.contributions resolve` for the
uuid and the photo); the pipeline reads it keyed by uuid, so a row survives renumbered gids. Columns:
  ref                HFH-<n>, the report's reference: the only credit, "a reader's report (HFH-<n>)"
  uuid               the footprint's LOD1 UUID (buildings.parquet)
  kind               year | main_address | name | photo | none
  value              year: 1938 or 1938-1939; main_address: one of the building's addresses; name: up to 120
                     characters; photo: the credit the sender gave under CC BY 4.0; none: empty
  public_note        the owner's one line of evidence, shown on the card (at most 200 characters)
  replaces_register  yes | no: a year replaces a building-level record year only with yes (never a curated one)
  issue_url          the report's GitHub issue, or empty
  photo              photo: the file in web/data/photos/ (named like s06_wiki's: 16 hex of its sha1, its width)

What each kind does:
  year          s02_years: fills a building whose year is unknown, area-based or estimated (the "reader" tier,
                codes.SRC_READER); a record year only with replaces_register yes; refuses a curated or withheld one
  main_address  s03_tiles: the card's first address; refused unless it is among the building's shown addresses
  name          s03_tiles: the card's name; refused on a private house (s03_tiles.hidden)
  photo         s03_tiles: the card's photo, "Photo: <credit>, CC BY 4.0, a reader's photo"; refused on a private house
  none          nothing (accepted without a data change)
No email and no name but a photo's credit: s99_validate refuses email-like or phone-like text in a note or value.
"""
import argparse
import csv
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from . import city, codes
from .yearrules import LATEST_YEAR, display

PATH = Path(__file__).with_name("contributions.csv")
COLUMNS = ["ref", "uuid", "kind", "value", "public_note", "replaces_register", "issue_url", "photo"]
KINDS = ("year", "main_address", "name", "photo", "none")
YEAR = re.compile(r"(\d{4})(?:-(\d{4}))?")
REF = re.compile(r"HFH-\d+")
ISSUE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/issues/\d+")
PHOTO_KEY = re.compile(r"[0-9a-f]{16}-\d+\.(jpg|png|webp)")
EMAIL_LIKE = re.compile(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
PHONE_LIKE = re.compile(r"(?:\+|\b0)\d[\d\s-]{6,}\d")
WEB_PHOTOS = Path("web/data/photos")
LICENCE, LICENCE_URL = "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"


class Refused(ValueError):
    """A row the pipeline will not apply: the message names its ref and why."""


def personal(text: str) -> bool:
    """True where text looks like an email address or a phone number."""
    return bool(EMAIL_LIKE.search(text or "") or PHONE_LIKE.search(text or ""))


def year_span(value: str) -> tuple[int, int]:
    m = YEAR.fullmatch(value or "")
    if not m:
        raise ValueError(f"not a year or a range: {value!r}")
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    if not 1000 <= a <= b <= LATEST_YEAR:
        raise ValueError(f"not a year or a range from 1000 to {LATEST_YEAR}: {value!r}")
    return a, b


def row_errors(r: dict) -> list[str]:
    """What is wrong with one row on its own (the building's checks come where it is applied)."""
    e = []
    if not REF.fullmatch(r["ref"]):
        e.append("ref is not HFH-<n>")
    if not r["uuid"]:
        e.append("no uuid")
    if r["kind"] not in KINDS:
        e.append(f"kind {r['kind']!r}")
    note = r["public_note"]
    if not note.strip() or len(note) > 200 or "\n" in note or "\r" in note:
        e.append("public_note must be one line of 1 to 200 characters")
    if r["replaces_register"] not in ("yes", "no") or (r["replaces_register"] == "yes" and r["kind"] != "year"):
        e.append("replaces_register must be yes (a year only) or no")
    if r["issue_url"] and not ISSUE.fullmatch(r["issue_url"]):
        e.append("issue_url is not a GitHub issue")
    kind, value = r["kind"], r["value"]
    if kind == "year":
        try:
            year_span(value)
        except ValueError as x:
            e.append(str(x))
    elif kind in ("main_address", "photo") and not value.strip():
        e.append(f"a {kind} needs its value")
    elif kind == "name" and (not value.strip() or len(value) > 120 or "\n" in value):
        e.append("a name is 1 to 120 characters on one line")
    elif kind == "none" and value:
        e.append("none has no value")
    if (kind == "photo") != bool(r["photo"]) or (r["photo"] and not PHOTO_KEY.fullmatch(r["photo"])):
        e.append("photo names its file (web/data/photos/) for a photo row only")
    if personal(note) or personal(value):
        e.append("email-like or phone-like text in public_note or value")
    return e


def read(path: Path = PATH) -> pd.DataFrame:
    """The table, every row checked on its own; refuses a malformed one or a repeated ref."""
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(t.columns) != COLUMNS:
        raise ValueError(f"{path}: the columns are {list(t.columns)}, not {', '.join(COLUMNS)}")
    bad = {r["ref"]: e for r in t.to_dict("records") if (e := row_errors(r))}
    if bad:
        raise ValueError(f"{path}: {bad}")
    if t.ref.duplicated().any():
        raise ValueError(f"{path}: repeated refs {sorted(set(t.ref[t.ref.duplicated()]))}")
    return t


def missing(t: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    """The refs whose uuid is on no footprint of b: a fixture build, or a footprint the City has since redrawn."""
    have = set(b.uuid)
    return [ref for ref, u in zip(t.ref, t.uuid) if u not in have]


def present(t: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """t without the rows whose footprint is not in this build, each named in a warning (as name_fixes does): a
    reader's change is never applied to a building it was not about."""
    gone = missing(t, b)
    for ref in gone:
        print(f"warning: contributions: {ref}: its footprint is not among these buildings (a fixture build, or the "
              "City redrew it?); skipped", file=sys.stderr)
    return t[~t.ref.isin(gone)] if gone else t


def gids(t: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    """Each row's gid by its uuid (b: gid, uuid); refuses a uuid on no footprint or on several (present() first drops
    the rows whose footprint is not in the build)."""
    by = b.groupby("uuid").gid.agg(list)
    out = {}
    for ref, u in zip(t.ref, t.uuid):
        found = by.get(u, []) if u else []
        if len(found) != 1:
            raise Refused(f"{ref}: uuid {u} is on {len(found)} footprints, not exactly one")
        out[ref] = int(found[0])
    return pd.Series(out, dtype="int64")


def ref_number(ref: str) -> int:
    return int(ref.split("-")[1])


# ---- s02_years

def reader_years(t: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """The year rows indexed by gid: ref, year_from, year_to, replaces (bool)."""
    y = present(t[t.kind == "year"], b)
    if y.empty:
        return pd.DataFrame(columns=["ref", "year_from", "year_to", "replaces"], index=pd.Index([], name="gid"))
    g = gids(y, b)
    spans = [year_span(v) for v in y.value]
    out = pd.DataFrame({"ref": y.ref.to_numpy(), "year_from": [s[0] for s in spans], "year_to": [s[1] for s in spans],
                        "replaces": (y.replaces_register == "yes").to_numpy()}, index=pd.Index(g[y.ref].to_numpy(), name="gid"))
    if out.index.duplicated().any():
        raise Refused(f"two year rows for one building: {sorted(out.ref[out.index.duplicated(keep=False)])}")
    return out


FILLS = (codes.SRC_NONE, codes.SRC_RAA_AREA, codes.SRC_ESTIMATE)          # unknown, area-based, estimated
REPLACES = (codes.SRC_RAA, codes.SRC_RAA_OLD, codes.SRC_WIKIDATA, codes.SRC_OSM)   # record years: only with "yes"


def apply_years(rows: pd.DataFrame, pos: pd.Series, year, y_from, y_to, ysrc, yflag, gone=()) -> int:
    """Write the reader tier into the arrays (s02_years.assign_years, after every other tier); returns how many."""
    gone = set(int(g) for g in gone)
    for g, r in rows.iterrows():
        if int(g) not in pos.index:
            raise Refused(f"{r.ref}: gid {g} is not among these buildings")
        k = int(pos[int(g)])
        src = int(ysrc[k])
        if int(g) in gone:
            raise Refused(f"{r.ref}: the building is withheld (pipeline/suppress.yml)")
        if src == codes.SRC_CURATED:
            raise Refused(f"{r.ref}: the building has a hand-checked year; change pipeline/landmarks.py instead")
        if src in REPLACES and not r.replaces:
            raise Refused(f"{r.ref}: the building has a record year; set replaces_register to yes to replace it")
        yr, fl = display(np.array([r.year_from]), np.array([r.year_to]))
        year[k], y_from[k], y_to[k], ysrc[k], yflag[k] = int(yr[0]), r.year_from, r.year_to, codes.SRC_READER, int(fl[0])
    return len(rows)


# ---- s03_tiles

def apply_cards(shards: list[dict], df: pd.DataFrame, t: pd.DataFrame, hide: np.ndarray, addresses: dict[int, list[str]],
                photos: Path = WEB_PHOTOS) -> int:
    """The reader rows on the card shards (s03_tiles.card_shards' output), in place; returns the applied rows but
    "none". df: gid, uuid, ysrc. hide: s03_tiles.hidden(df). addresses: gid -> its shown addresses ("Street 12")."""
    n_shards = len(shards)
    t = present(t, df[["gid", "uuid"]])
    g_of = gids(t, df[["gid", "uuid"]])
    ysrc = df.ysrc.to_numpy()
    applied = 0
    for r in t.to_dict("records"):
        g = int(g_of[r["ref"]])
        shard = shards[g % n_shards]
        card = shard.setdefault(str(g), {})
        kind, value = r["kind"], r["value"]
        if kind == "year":
            if ysrc[g] != codes.SRC_READER:
                raise Refused(f"{r['ref']}: s02_years did not apply the year (run s02_years again)")
            if not hide[g]:      # a private house's line names the source only: the note or issue may give the year
                card["yrd"] = {"ref": r["ref"], "note": r["public_note"], **({"url": r["issue_url"]} if r["issue_url"] else {})}
        elif kind == "main_address":
            if value not in addresses.get(g, []):
                raise Refused(f"{r['ref']}: {value!r} is not among the building's addresses")
            card["addr"] = value
        elif kind == "name":
            if hide[g]:
                raise Refused(f"{r['ref']}: a private house's card takes no name from a report")
            card["name"] = value
            card.pop("en", None)
        elif kind == "photo":
            if hide[g]:
                raise Refused(f"{r['ref']}: a private house's card shows no photo")
            path = photos / r["photo"]
            if not path.is_file():
                raise Refused(f"{r['ref']}: {path} is missing (run scripts/contributions.mjs pull)")
            w, h = image_size(path.read_bytes())
            card["photo"] = {"key": r["photo"], "w": w, "h": h, "by": value, "lic": LICENCE, "lu": LICENCE_URL, "rd": r["ref"]}
        if not card:
            shard.pop(str(g))
        applied += kind != "none"
    return applied


# ---- the photo, for `pull`

def image_size(b: bytes) -> tuple[int, int]:
    """(width, height) of a JPEG, PNG or WebP from its header."""
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", b[16:24])
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        c = b[12:16]
        if c == b"VP8X":
            return 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
        if c == b"VP8L":
            v = int.from_bytes(b[21:25], "little")
            return 1 + (v & 0x3FFF), 1 + ((v >> 14) & 0x3FFF)
        if c == b"VP8 ":
            return int.from_bytes(b[26:28], "little") & 0x3FFF, int.from_bytes(b[28:30], "little") & 0x3FFF
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                break
            m, n = b[i + 1], int.from_bytes(b[i + 2:i + 4], "big")
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return w, h
            i += 2 + n
    raise ValueError("not a JPEG, PNG or WebP whose size can be read")


PHOTO_MAX_PX = 1000     # a reader's photo arrives at up to 2048 px; the card shows it at most about 360 px wide, twice


def shrink(data: bytes, max_px: int = PHOTO_MAX_PX, limit: int = city.WIKI["photo_bytes"]) -> bytes:
    """A reader's photo small enough for the site: as it is when within max_px and limit, else re-encoded as a JPEG
    with its longest side at most max_px (a fresh encode carries no metadata), stepping the quality down to fit."""
    w, h = image_size(data)
    if max(w, h) <= max_px and len(data) <= limit:
        return data
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    for q in (85, 78, 70, 62):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= limit:
            break
    return buf.getvalue()


def place_photo(src: Path, web: Path = WEB_PHOTOS) -> str:
    """A report's photo into web/data/photos/ (shrunk first, if it is larger than the site takes) under s06_wiki's kind
    of key: 16 hex of the sha1, "-", its width."""
    data = shrink(Path(src).read_bytes())
    w, _ = image_size(data)
    ext = "png" if data[:4] == b"\x89PNG" else "webp" if data[:4] == b"RIFF" else "jpg"
    key = f"{hashlib.sha1(data).hexdigest()[:16]}-{w}.{ext}"
    web.mkdir(parents=True, exist_ok=True)
    (web / key).write_bytes(data)
    return key


# ---- `pull`: D1 rows -> the CSV

NEAR_M = 10.0   # the card's point is the footprint's centroid, which an L- or U-shaped building can leave


def footprints_at(b: gpd.GeoDataFrame, x: float, z: float) -> list[int]:
    """The gids whose footprint contains the local-frame point (x, z)."""
    e, n = x + city.ORIGIN[0], city.ORIGIN[1] - z
    p = shapely.Point(e, n)
    geoms = b.geometry.values
    return sorted(int(b.gid.iat[j]) for j in shapely.STRtree(geoms).query(p, predicate="within"))


def footprint_for(b: gpd.GeoDataFrame, x: float, z: float) -> list[int]:
    """The footprint a card's point stands for: the one containing it, else every one within NEAR_M (the centroid of
    an L- or U-shaped building can fall outside it). One gid when that is unambiguous."""
    inside = footprints_at(b, x, z)
    if inside:
        return inside
    p = shapely.Point(x + city.ORIGIN[0], city.ORIGIN[1] - z)
    near = shapely.STRtree(b.geometry.values).query(p, predicate="dwithin", distance=NEAR_M)
    return sorted(int(b.gid.iat[j]) for j in near)


def resolve(rows: list[dict], b: gpd.GeoDataFrame, current: str) -> tuple[list[dict], list[str]]:
    """(the rows with their uuid, the refusals) for D1's rows (id, report_id, kind, value, public_note,
    replaces_register, gid, data_version, x, z, issue_url, photo_file). By gid when the row's data_version is the current
    build's, else by the footprint containing its point; refused when gid and point disagree, the point is in no
    footprint, or the footprint has no uuid. b: buildings.parquet (gid, uuid, geometry)."""
    uuid = dict(zip(b.gid.astype(int), b.uuid))
    out, refused = [], []
    for r in rows:
        ref = f"HFH-{int(r['report_id'])}"
        has_point = r.get("x") is not None and r.get("z") is not None
        at = footprint_for(b, float(r["x"]), float(r["z"])) if has_point else None
        if r.get("data_version") == current and r.get("gid") is not None:
            g = int(r["gid"])
            if g not in uuid or (at is not None and g not in at):
                refused.append(f"{ref}: gid {g} and the point ({r.get('x')}, {r.get('z')}) disagree")
                continue
        else:
            if not at or len(at) > 1:
                refused.append(f"{ref}: the point ({r.get('x')}, {r.get('z')}) is in no footprint"
                               + (f", and {len(at)} are within {NEAR_M:g} m" if at else ""))
                continue
            g = at[0]
        if not uuid.get(g):
            refused.append(f"{ref}: gid {g} has no uuid")
            continue
        photo = place_photo(Path(r["photo_file"])) if r["kind"] == "photo" and r.get("photo_file") else ""
        if photo and (WEB_PHOTOS / photo).stat().st_size > city.WIKI["photo_bytes"]:
            refused.append(f"{ref}: the photo is still over {city.WIKI['photo_bytes']:,} bytes after shrinking")
            continue
        row = {"ref": ref, "uuid": uuid[g], "kind": r["kind"], "value": r.get("value") or "",
               "public_note": r["public_note"], "replaces_register": "yes" if r.get("replaces_register") else "no",
               "issue_url": r.get("issue_url") or "", "photo": photo}
        if errors := row_errors(row):
            refused.append(f"{ref}: {'; '.join(errors)}")
            continue
        out.append(row)
    return out, refused


def write(rows: list[dict], path: Path = PATH) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m pipeline.contributions", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="D1 rows (JSON on stdin) -> pipeline/contributions.csv")
    r.add_argument("--buildings", type=Path, default=Path("data/buildings.parquet"))
    r.add_argument("--current", type=Path, default=Path("web/data/current.json"))
    r.add_argument("--out", type=Path, default=PATH)
    sub.add_parser("check", help="read and check pipeline/contributions.csv")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        print(f"{len(read())} rows OK")
        return
    b = gpd.read_parquet(a.buildings, columns=["gid", "uuid", "geometry"])
    current = json.loads(a.current.read_text())["version"] if a.current.exists() else ""
    rows, refused = resolve(json.load(sys.stdin), b, current)
    for x in refused:
        print(f"refused {x}", file=sys.stderr)
    write(rows, a.out)
    print(f"{len(rows)} rows -> {a.out}; {len(refused)} refused")
    if refused:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
