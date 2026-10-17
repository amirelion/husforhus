"""Pack buildings into tile v1 binaries, packs, hot attributes, card shards, excerpt shards and stockholm.json.

Adapted from upstream reference/amsterdam/pipeline/s03_tiles.py
(alexbarakov/amsterdam-by-building, MIT, Copyright (c) 2026 alexbarakov): pad4, rings_of, pack_tile and the
centre-out packs keep upstream's shape. The layout is 'HFH1' (web/tiles.js reads it).

Local frame: metres from Stortorget, x east, z south (three.js, y up). Tile layout (little-endian, every
section 4-byte aligned):
  header  u32 magic, nB, nP, nR, nV; f32 originX, originZ                                   (28 bytes)
  B       u32 gid[nB]; i16 year[nB]; u8 yflag[nB]; u8 period[nB]; u8 floors[nB]; i16 ground[nB] (dm);
          u32 lay0[nB]; u32 lay1[nB] (zeros in v1); u32 partStart[nB+1]
  P       f32 height[nP]; u32 ringStart[nP+1]
  R       u32 vertStart[nR+1]; u8 hole[nR]
  V       i16 xz[2*nV], decimetres from the tile origin
One part per building in v1. s01_load has already simplified footprints at city.SIMPLIFY.

A card also carries the English label, protection and the year it was decided, the Wikidata
item, the languages with an article, the photo's credit and whether to leave the floors row out (s02_attributes,
s06_wiki); a curated card also its rebuilds and older cellars (s08_landmarks' entries); Wikipedia excerpts
go to their own shards wiki/NN.json (CC BY-SA 4.0), and photos.json lists the photos this version uses
(scripts/build_dist.py ships them from web/data/photos/); photo-gids.json the sorted gids whose card has a photo
(the legend's "Highlight buildings with a photo" switch). No private house that is not curated carries a RAÄ link, a
Wikidata item, an article, a photo or an excerpt. stockholm.json gains the link templates (city.LINKS) and
the timeline's landmarks.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely

from . import city, codes, io
from .addresses import sharing
from .sources import credit, load_sources
from .tiles_decode import MAGIC

DATA = Path("data")
SOURCES = Path(__file__).with_name("sources.yml")
CURRENT = Path("web/data/current.json")
N_CARD_SHARDS = 64
MAX_TILE_BUILDINGS = 65535  # the worker indexes buildings in a tile with a Uint16 attribute
LATEST_YEAR = 2026          # the cap on histogram years (s99's YEAR_MAX): no bin lies after it

# One fixed 24-byte record per gid.
ATTR_DTYPE = np.dtype([
    ("h_dm", "<u2"), ("fsrc", "u1"), ("yflag", "u1"),
    ("year", "<i2"), ("year_from", "<i2"), ("year_to", "<i2"),
    ("ysrc", "u1"), ("rating", "u1"),
    ("x", "<f4"), ("z", "<f4"),
    ("floors", "u1"), ("period", "u1"), ("private", "u1"), ("pad", "u1"),
])
assert ATTR_DTYPE.itemsize == 24

# stats.byFlag names by yflag code; 5 (once DECADE) is retired and refused.
FLAG_NAMES = {codes.EXACT: "exact", codes.RANGE: "range", codes.LONG: "long", codes.AREA: "area",
              codes.ESTIMATE: "estimate", codes.PERIOD: "period", codes.UNKNOWN: "unknown"}
SRC_NAMES = ["none", "curated", "raa", "raa_area", "wikidata", "estimate", "raa_old", "osm"]  # index = codes ysrc
# histogram holds the building-level years; histogramEst the area and kNN years (PERIOD rows are kNN products too).
KNOWN_FLAGS = (codes.EXACT, codes.RANGE, codes.LONG)
ESTIMATED_FLAGS = (codes.AREA, codes.ESTIMATE, codes.PERIOD)
CARD_FIELDS = ("name", "en", "architects", "raa", "prot", "since", "qid", "wp", "photo", "nofloors", "rebuilt",
               "cellars", "addr", "addrn")
PHOTO_FIELDS = ("key", "w", "h", "by", "lic", "lu", "page", "title")
WIKI_LICENCE = "CC BY-SA 4.0"


def pad4(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def rings_of(geom):
    """(coords in EPSG:3011 without the closing vertex, hole flag) for every ring of a (Multi)Polygon."""
    for poly in getattr(geom, "geoms", [geom]):
        if poly.is_empty:
            continue
        yield shapely.get_coordinates(poly.exterior)[:-1], 0
        for hole in poly.interiors:
            yield shapely.get_coordinates(hole)[:-1], 1


def pack_tile(origin, rows) -> bytes:
    """One tile. `origin` is the tile corner (x, z) in local metres. Each row is a dict with
    gid, year, yflag, period, floors, ground_dm, height (m) and geometry (EPSG:3011 Polygon/MultiPolygon)."""
    ox, oz = float(origin[0]), float(origin[1])
    gid, year, yflag, period, floors, ground, part_start = [], [], [], [], [], [], [0]
    heights, ring_start, vert_start, holes, verts = [], [0], [0], [], []
    for b in rows:
        gid.append(b["gid"])
        year.append(b["year"])
        yflag.append(b["yflag"])
        period.append(b["period"])
        floors.append(b["floors"])
        ground.append(b["ground_dm"])
        heights.append(b["height"])
        for ring, hole in rings_of(b["geometry"]):
            if len(ring) < 3:
                continue
            x, z = city.to_local(ring[:, 0], ring[:, 1])
            loc = np.round(np.c_[x - ox, z - oz] * 10.0)
            if loc.min() < -32768 or loc.max() > 32767:
                raise ValueError(f"gid {b['gid']}: vertex beyond i16 decimetres from tile origin {origin}")
            verts.append(loc.astype("<i2"))
            holes.append(hole)
            vert_start.append(vert_start[-1] + len(ring))
        ring_start.append(len(holes))
        part_start.append(len(heights))
    nB, nP, nR = len(gid), len(heights), len(holes)
    V = np.concatenate(verts) if verts else np.zeros((0, 2), "<i2")
    out = struct.pack("<5I2f", MAGIC, nB, nP, nR, len(V), ox, oz)
    out += pad4(np.array(gid, "<u4").tobytes())
    out += pad4(np.array(year, "<i2").tobytes())
    out += pad4(np.array(yflag, "u1").tobytes())
    out += pad4(np.array(period, "u1").tobytes())
    out += pad4(np.array(floors, "u1").tobytes())
    out += pad4(np.array(ground, "<i2").tobytes())
    out += np.zeros(nB, "<u4").tobytes() + np.zeros(nB, "<u4").tobytes()  # lay0, lay1: no layers in v1
    out += pad4(np.array(part_start, "<u4").tobytes())
    out += pad4(np.array(heights, "<f4").tobytes())
    out += pad4(np.array(ring_start, "<u4").tobytes())
    out += pad4(np.array(vert_start, "<u4").tobytes())
    out += pad4(np.array(holes, "u1").tobytes())
    out += pad4(V.astype("<i2").tobytes())
    return out


def load(data: Path = DATA) -> pd.DataFrame:
    """buildings ⋈ years ⋈ attributes on gid, sorted by gid, gids exactly 0..n-1, with the ground,
    height and floors s02_terrain settled (data/ground.parquet)."""
    b = gpd.read_parquet(data / "buildings.parquet")
    y = pd.read_parquet(data / "years.parquet")
    a = pd.read_parquet(data / "attributes.parquet")
    path = data / "ground.parquet"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run s02_terrain (it settles each building's ground on the terrain)")
    check_built_from(load_terrain(data), data)
    return join(b, y, a, pd.read_parquet(path, columns=["gid", "ground", "height", "floors"]))


def load_terrain(data: Path = DATA) -> dict:
    """s02_terrain's record (data/terrain.json): the grid, its source and the datum check."""
    path = data / "terrain.json"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run s02_terrain")
    return json.loads(path.read_text(encoding="utf-8"))


def check_built_from(record: dict, data: Path = DATA) -> None:
    """s02_terrain's outputs belong to the buildings and attributes they were made from (it records the sha256 of
    data/buildings.parquet and data/attributes.parquet): after a later s01_load they would ship old grounds, heights,
    floors and terrace cuts, and after a later s02_attributes old floors (ground.parquet carries them). s03_tiles and
    s04_base refuse them."""
    for name in ("buildings", "attributes"):
        path = data / f"{name}.parquet"
        if record.get(f"{name}_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            raise SystemExit(f"{data / 'terrain.json'} was built from another {path}: run s02_terrain again")


def load_wiki(data: Path = DATA) -> dict:
    """s06_wiki's outputs: {"table": wiki.parquet, "photos": photos.json, "extracts": extracts.json}."""
    path = data / "wiki.parquet"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run s06_wiki")
    return {"table": pd.read_parquet(path),
            "photos": json.loads((data / "photos.json").read_text(encoding="utf-8")),
            "extracts": json.loads((data / "extracts.json").read_text(encoding="utf-8"))}


def load_landmarks(data: Path = DATA) -> list[dict]:
    """The entries s08_landmarks verified (data/landmarks.json)."""
    path = data / "landmarks.json"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run s08_landmarks")
    return json.loads(path.read_text(encoding="utf-8"))


def load_places(data: Path = DATA) -> dict:
    """s02_addresses' outputs: {"addresses": addresses.parquet without its withheld rows, "districts":
    districts.parquet}."""
    for name in ("addresses.parquet", "districts.parquet"):
        if not (data / name).exists():
            raise SystemExit(f"{data / name} is missing: run s02_addresses")
    a = pd.read_parquet(data / "addresses.parquet")
    if "withheld" in a:
        a = a[~a.withheld.to_numpy(bool)].drop(columns="withheld").reset_index(drop=True)
    return {"addresses": a,
            "districts": pd.read_parquet(data / "districts.parquet")}


def shown_addresses(a: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """The addresses that ship, for the card and search alike: none a takedown withheld (s02_addresses), and while
    city.PRIVATE_ADDRESSES is False none whose street and number also sit on a `hidden` house, on any footprint
    (addresses.sharing: the final review's F1)."""
    keep = ~a.withheld.to_numpy(bool) if "withheld" in a else np.ones(len(a), dtype=bool)
    if not city.PRIVATE_ADDRESSES:
        keep &= ~sharing(a, set(df.gid.to_numpy()[hidden(df)].tolist()))
    return a[keep].drop(columns="withheld", errors="ignore").reset_index(drop=True)


def no_places() -> dict:
    return {"addresses": pd.DataFrame({"gid": pd.Series([], dtype="int32"), "street": pd.Series([], dtype=str),
                                       "number": pd.Series([], dtype=str)}),
            "districts": pd.DataFrame({"gid": pd.Series([], dtype="int32"), "district": pd.Series([], dtype=str)})}


def with_places(df: pd.DataFrame, places: dict) -> pd.DataFrame:
    """df with addr (a footprint's first address, "Hornsgatan 30", in s02_addresses' order: street, then number),
    addrn (how many it has) and dist (its stadsdel as people write it, city.DISTRICT_NAMES); "" and 0 where none.
    The stadsdel ships in districts.bin.gz (district_codes), not on the card: 77,743 names would add 300 KB of cards."""
    a = shown_addresses(places["addresses"], df)
    first = a.groupby("gid", sort=False).agg(street=("street", "first"), number=("number", "first"),
                                              n=("number", "size"))
    out = df.copy()
    gid = out.gid.astype("int64")
    out["addr"] = gid.map((first.street + " " + first.number).rename(index=int)).fillna("").astype(str)
    out["addrn"] = gid.map(first.n.rename(index=int)).fillna(0).astype(int)
    names = places["districts"].assign(gid=lambda d: d.gid.astype("int64")).set_index("gid").district
    out["dist"] = [city.DISTRICT_NAMES.get(n, n.title()) if isinstance(n, str) and n else ""
                   for n in gid.map(names)]
    return out


def district_codes(df: pd.DataFrame) -> tuple[list[str], np.ndarray]:
    """(the stadsdelar's display names, sorted; one byte per gid: 1 + its stadsdel's place in that list, 0 for none):
    districts.bin.gz and stockholm.json `districts`."""
    names = sorted({d for d in df.dist if d})
    code = {d: i + 1 for i, d in enumerate(names)}
    if len(names) > 255:
        raise ValueError(f"{len(names)} stadsdelar do not fit one byte each")
    return names, np.array([code.get(d, 0) for d in df.dist], dtype=np.uint8)


def no_wiki() -> dict:
    return {"table": pd.DataFrame(columns=["gid", "qid", "name", "name_en", "langs", "photo"]), "photos": {},
            "extracts": {}}


def load_accuracy(data: Path = DATA) -> dict:
    """The estimate tier's accuracy table, written by s02_years next to years.parquet."""
    path = data / "accuracy.json"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run s02_years (it writes the accuracy table with years.parquet)")
    return json.loads(path.read_text(encoding="utf-8"))


def join(b: gpd.GeoDataFrame, y: pd.DataFrame, a: pd.DataFrame, g: pd.DataFrame | None = None) -> gpd.GeoDataFrame:
    """g (ground.parquet: gid, ground, height, floors) replaces those three columns when given."""
    if g is not None:
        if len(g) != len(b):
            raise ValueError(f"row counts differ: buildings {len(b)}, ground {len(g)} (run s02_terrain again)")
        b = b.drop(columns=["ground", "height"]).merge(g[["gid", "ground", "height"]], on="gid", validate="one_to_one")
        a = a.drop(columns=["floors"]).merge(g[["gid", "floors"]], on="gid", validate="one_to_one")
    df = b.merge(y, on="gid", validate="one_to_one").merge(a, on="gid", validate="one_to_one")
    if not (len(df) == len(b) == len(y) == len(a)):
        raise ValueError(f"row counts differ: buildings {len(b)}, years {len(y)}, attributes {len(a)}")
    df = df.sort_values("gid").reset_index(drop=True)
    if not np.array_equal(df.gid.to_numpy(), np.arange(len(df))):
        raise ValueError("gids are not exactly 0..n-1")
    bad = ~df.yflag.isin(list(FLAG_NAMES))
    if bad.any():
        raise ValueError(f"{int(bad.sum())} rows have a yflag outside codes.py (gid {int(df.gid[bad].iat[0])})")
    c = shapely.centroid(df.geometry.values)
    df["x"], df["z"] = city.to_local(shapely.get_x(c), shapely.get_y(c))
    return df


def build_tiles(df: pd.DataFrame, tile: float) -> list[dict]:
    """Tiles by centroid, sorted centre-out by the distance of the tile centre from the origin."""
    tx = np.floor(df.x.to_numpy() / tile).astype(int)
    tz = np.floor(df.z.to_numpy() / tile).astype(int)
    ground = np.round(df.ground.to_numpy(np.float64) * 10).astype(int)
    tiles = []
    for (a, b), idx in pd.Series(np.arange(len(df))).groupby([tx, tz]):
        idx = np.sort(idx.to_numpy())
        if len(idx) > MAX_TILE_BUILDINGS:
            raise ValueError(f"tile {a}_{b} holds {len(idx)} buildings; the worker allows {MAX_TILE_BUILDINGS}")
        origin = (a * tile, b * tile)
        rows = [{"gid": int(df.gid.iat[i]), "year": int(df.year.iat[i]), "yflag": int(df.yflag.iat[i]),
                 "period": int(df.period.iat[i]), "floors": int(df.floors.iat[i]), "ground_dm": int(ground[i]),
                 "height": float(df.height.iat[i]), "geometry": df.geometry.iat[i]} for i in idx]
        data = pack_tile(origin, rows)
        dist = round(float(np.hypot(origin[0] + tile / 2, origin[1] + tile / 2)))
        tiles.append({"file": f"{a}_{b}.bin", "tx": int(a), "tz": int(b), "n": len(rows), "bytes": len(data),
                      "dist": dist, "data": data})
    tiles.sort(key=lambda t: (t["dist"], t["tx"], t["tz"]))
    return tiles


def assign_packs(tiles: list[dict], n_packs: int) -> list[bytes]:
    """Split the centre-out tile list into up to n_packs packs with about equal building counts. Sets
    pack/offset/length on each tile (offsets into the decompressed pack) and returns the raw packs."""
    n = np.array([t["n"] for t in tiles])
    start = np.cumsum(n) - n
    k = np.minimum(start * n_packs // max(int(n.sum()), 1), n_packs - 1)
    _, k = np.unique(k, return_inverse=True)  # renumber so pack names stay contiguous
    packs = [bytearray() for _ in range(int(k.max()) + 1 if len(k) else 0)]
    for t, kk in zip(tiles, k, strict=True):
        t.update(pack=f"pack{kk}.bin.gz", offset=len(packs[kk]), length=len(t["data"]))
        packs[kk] += t["data"]
    return [bytes(p) for p in packs]


def attrs_array(df: pd.DataFrame) -> np.ndarray:
    a = np.zeros(len(df), dtype=ATTR_DTYPE)
    a["h_dm"] = np.clip(np.round(df.height.to_numpy(np.float64) * 10), 0, 65535)
    a["fsrc"] = df.fsrc
    a["yflag"] = df.yflag
    a["year"] = df.year
    a["year_from"] = df.year_from
    a["year_to"] = df.year_to
    a["ysrc"] = df.ysrc
    a["rating"] = df.rating
    a["x"] = df.x
    a["z"] = df.z
    a["floors"] = df.floors
    a["period"] = df.period
    a["private"] = df.private
    return a


def hidden(df: pd.DataFrame) -> np.ndarray:
    """Per row, True where the card links nothing that could give the exact year: a row marked private, or
    any non-curated building whose `kategori` is in city.PRIVATE_HOUSE_KATEGORI, dated or not. RAÄ's page, a Wikidata
    item, an article, an excerpt or a photo page would state the year that a private house shows only as its decade."""
    return df.private.to_numpy(bool) | (df.kategori.isin(city.PRIVATE_HOUSE_KATEGORI).to_numpy()
                                        & (df.ysrc.to_numpy() != codes.SRC_CURATED))


def _text(v) -> str:
    return v if isinstance(v, str) else ""


def card_shards(df: pd.DataFrame, photos: dict | None = None, landmarks: list[dict] | None = None) -> list[dict]:
    """64 shards keyed by gid % 64; each holds {gid: card} with only CARD_FIELDS. `df` may carry s06_wiki's columns
    (qid, wname, wname_en, langs, photo), s02_attributes' (prot, since, nofloors) and with_places' (addr, addrn);
    `photos` maps a photo key to its credit (s06_wiki's photos.json). On a `hidden` row: no raa, qid, wp, photo or
    English label, and no address when city.PRIVATE_ADDRESSES is False. `landmarks` are s08_landmarks' entries: a
    curated row (years.parquet `landmark`) takes its entry's `rebuilt`, by year, and `cellars`; no other
    row does."""
    photos = photos or {}
    shards = [{} for _ in range(N_CARD_SHARDS)]
    hide = hidden(df)
    entries = {L["name"]: L for L in landmarks or ()}
    curated = (df.ysrc.to_numpy() == codes.SRC_CURATED) if "ysrc" in df else np.zeros(len(df), bool)
    marks = df.landmark.to_numpy() if "landmark" in df else np.full(len(df), "", dtype=object)
    col = {c: (df[c].to_numpy() if c in df else np.full(len(df), None, dtype=object))
           for c in ("qid", "wname", "wname_en", "langs", "photo", "prot", "since", "nofloors", "addr", "addrn")}
    for i, (gid, name, arch, raa) in enumerate(zip(df.gid, df["name"], df.architects, df.raa_id, strict=True)):
        card = {}
        name = _text(name) or ("" if hide[i] else _text(col["wname"][i]))
        if name:
            card["name"] = name
        en = "" if hide[i] else _text(col["wname_en"][i])
        if en and en.casefold() != name.casefold():
            card["en"] = en
        arch = [str(s) for s in (arch if arch is not None else []) if s]
        if arch:
            card["architects"] = arch
        if isinstance(raa, str) and raa and not hide[i]:
            card["raa"] = raa
        if col["prot"][i]:
            card["prot"] = int(col["prot"][i])
            if col["since"][i]:
                card["since"] = int(col["since"][i])
        if not hide[i] and _text(col["qid"][i]):
            card["qid"] = col["qid"][i]
            langs = [lang for lang in _text(col["langs"][i]).split(",") if lang]
            if langs:
                card["wp"] = langs
            key = _text(col["photo"][i])
            if key and key in photos:
                card["photo"] = {k: photos[key][k] for k in PHOTO_FIELDS if k in photos[key]}
        if col["nofloors"][i]:
            card["nofloors"] = True
        entry = entries.get(marks[i]) if curated[i] and _text(marks[i]) else None
        if entry and entry.get("rebuilt"):
            card["rebuilt"] = sorted([int(y), str(k)] for y, k in entry["rebuilt"])
        if entry and entry.get("cellars") is True:
            card["cellars"] = True
        # The first address (and how many there are); a private house's too, unless city.PRIVATE_ADDRESSES
        # says otherwise (city.PRIVATE_ADDRESSES)
        addr = _text(col["addr"][i])
        if addr and (city.PRIVATE_ADDRESSES or not hide[i]):
            card["addr"] = addr
            if col["addrn"][i] and int(col["addrn"][i]) > 1:
                card["addrn"] = int(col["addrn"][i])
        if card:
            shards[int(gid) % N_CARD_SHARDS][str(int(gid))] = card
    return shards


def wiki_shards(df: pd.DataFrame, extracts: dict) -> list[dict]:
    """64 shards keyed by gid % 64, {"licence": "CC BY-SA 4.0", "items": {gid: {lang: {t, r}}}}: the excerpts, in
    files of their own, never for a `hidden` row."""
    shards = [{"licence": WIKI_LICENCE, "items": {}} for _ in range(N_CARD_SHARDS)]
    ok = dict(zip(df.gid.astype(int), ~hidden(df)))
    for g, langs in sorted(extracts.items(), key=lambda kv: int(kv[0])):
        if ok.get(int(g)):
            shards[int(g) % N_CARD_SHARDS]["items"][str(int(g))] = langs
    return shards


def timeline_landmarks(df: pd.DataFrame, landmarks: list[dict]) -> list[dict]:
    """The verified landmarks with a timeline priority, as placed (years.parquet `landmark`): name, year, gid, x, z
    and the priority; never a private-category house, sorted by year then name."""
    placed = {n: i for i, n in enumerate(df.landmark) if isinstance(n, str) and n}
    private = df.kategori.isin(city.PRIVATE_HOUSE_KATEGORI).to_numpy()
    out = []
    for L in landmarks:
        i = placed.get(L["name"])
        if not L.get("timeline") or i is None or private[i]:
            continue
        out.append({"name": L["name"], "year": int(df.year.iat[i]), "gid": int(df.gid.iat[i]),
                    "x": round(float(df.x.iat[i]), 1), "z": round(float(df.z.iat[i]), 1), "timeline": int(L["timeline"])})
    return sorted(out, key=lambda e: (e["year"], e["name"]))


def with_wiki(df: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """df with s06_wiki's columns (qid, wname, wname_en, langs, photo), "" where a footprint has no item."""
    t = table[["gid", "qid", "name", "name_en", "langs", "photo"]].rename(columns={"name": "wname", "name_en": "wname_en"})
    out = df.merge(t.astype({"gid": "int64"}), on="gid", how="left", validate="one_to_one")
    for c in ("qid", "wname", "wname_en", "langs", "photo"):
        out[c] = out[c].fillna("").astype(str)
    return out


RECORD_SRCS = (codes.SRC_CURATED, codes.SRC_RAA, codes.SRC_RAA_OLD, codes.SRC_WIKIDATA, codes.SRC_OSM)


def about_stats(df: pd.DataFrame, cards: list[dict]) -> dict:
    """stockholm.json `about`: the numbers web/about.js writes into About that `stats` and
    `accuracy` do not hold already, counted over what ships (the cards), and who made the map. Counts only: no
    building, name or address."""
    from .report_accuracy import fewest_private_years

    shipped = [c for shard in cards for c in shard.values()]
    gamla = (df.dist == city.DISTRICT_NAMES["GAMLA STAN"]).to_numpy() if "dist" in df else np.zeros(len(df), bool)
    record = df.ysrc.isin(RECORD_SRCS).to_numpy()
    return {
        "privateCategory": int(df.kategori.isin(city.PRIVATE_HOUSE_KATEGORI).sum()),
        "privateDated": int(df.private.sum()),
        "ratings": [int((df.rating == r).sum()) for r in (1, 2, 3)],
        "protected": int(sum(1 for c in shipped if c.get("prot"))),
        "withArchitect": int(sum(1 for c in shipped if c.get("architects"))),
        "addressed": int(sum(1 for c in shipped if c.get("addr"))),
        "gamla": {"n": int(gamla.sum()), "dated": int((gamla & record).sum())},
        "fewestPrivateYears": fewest_private_years(),
        "lateYear": int(city.ESTIMATE["late_prod_year"]),
        "nearM": int(city.ESTIMATE["near_m"]),
        "rareArchitect": int(city.ARCHITECT_MAX_RARE),
        "snapshot": city.SNAPSHOT,
        "maker": city.MAKER,
        "contact": city.CONTACT,
        "privateAddresses": bool(city.PRIVATE_ADDRESSES),
    }


def stable_hash(gid: int) -> int:
    """The first 8 hex digits of md5(str(gid)) as an integer: the same on every machine and every run."""
    return int(hashlib.md5(str(int(gid)).encode()).hexdigest()[:8], 16)


def histogram_years(df: pd.DataFrame) -> np.ndarray:
    """The year each building counts under in the histograms. Private houses publish only their decade start,
    so they are spread over the decade by a stable hash of the gid (no spike every ten years), capped at 2026:
    min(year + stable_hash(gid) % 10, 2026). That is an aggregate only; no per-building year is implied."""
    year = df.year.to_numpy(np.int64).copy()
    private = df.private.to_numpy(bool)
    spread = np.array([stable_hash(g) % 10 for g in df.gid[private]], dtype=np.int64)
    year[private] = np.minimum(year[private] + spread, LATEST_YEAR)
    return year


def histograms(df: pd.DataFrame) -> tuple[dict, dict]:
    """histogram counts EXACT/RANGE/LONG, histogramEst AREA/ESTIMATE/PERIOD: {year: [n per period]}."""
    n = len(city.PERIODS)
    years = histogram_years(df)

    def hist(mask):
        out = {}
        for y, p in zip(years[mask], df.period.to_numpy()[mask], strict=True):
            out.setdefault(str(int(y)), [0] * n)[int(p)] += 1
        return out

    dated = df.year.to_numpy() > 0
    return hist(dated & df.yflag.isin(KNOWN_FLAGS).to_numpy()), hist(dated & df.yflag.isin(ESTIMATED_FLAGS).to_numpy())


DTM_SOURCE = "lm_markhojd"   # sources.yml: Lantmäteriet's terrain model, credited only when the build used it


def attribution(sources: list[dict], terrain_source: str = "dtm") -> list[dict]:
    """CC BY attribution needs the licence name and a link to it, next to the source. Lantmäteriet's terrain is
    credited only when the terrain came from it (a contour build uses the Stadskarta, credited already). It adds
    the source's words in the map's corner credit where it has them (sources.yml corner), and the standard credit line ("Dataset: publisher, licence"), which About
    lists: `credit`, {en, sv}, "Dataset: publisher, licence" plus ", processed" / ", bearbetad" (sources.credit)."""
    return [{"id": s["id"], "text": s["attribution"], "url": s["url"], "licence": s["licence"],
             "licence_url": s["licence_url"], **({"corner": s["corner"]} if s.get("corner") else {}),
             "credit": credit(s)}
            for s in sources if (s["id"] != DTM_SOURCE or terrain_source == "dtm")
            and city.FEATURES.get(s.get("feature"), True)]   # a source of a switched-off feature waits


def terrain_config(record: dict) -> dict:
    """stockholm.json's `terrain`: the grid as s02_terrain built it and the viewer's defaults."""
    t = city.TERRAIN
    return {"file": "terrain.bin.gz", "source": record["source"], "x0": record["x0"], "z0": record["z0"],
            "cell": record["cell"], "nx": record["nx"], "nz": record["nz"], "waterZ": record["water_z"],
            "datum": record["datum"], "fixed": record["fixed"], "relief": t["relief"], "reliefMax": t["relief_max"],
            "fadeM": t["fade_m"], "terrace": t["terrace"], "chunk": t["chunk"]}


def make_config(df, tiles, packs, version, tile, sources, accuracy, terrain, landmarks=(), wiki_stats=None) -> dict:
    hist, hist_est = histograms(df)
    dated = df.year.to_numpy() > 0
    years = np.concatenate([df.year.to_numpy(np.int64)[dated], histogram_years(df)[dated]])
    flags = np.bincount(df.yflag.to_numpy(int), minlength=max(FLAG_NAMES) + 1)
    srcs = np.bincount(df.ysrc.to_numpy(int), minlength=len(SRC_NAMES))
    return {
        "city": city.SLUG, "name": city.NAME, "subtitle": city.SUBTITLE, "version": version, "tileSize": tile,
        "origin": list(city.ORIGIN), "crs": city.CRS, "home": city.HOME,
        "periods": [{"key": k, "label": en, "label_sv": sv, "from": a, "to": b, "color": col}
                    for k, en, sv, a, b, col in city.PERIODS],
        "yearMin": int(years.min()) if len(years) else city.PERIODS[0][3],
        "yearMax": int(years.max()) if len(years) else LATEST_YEAR,
        "histogram": hist, "histogramEst": hist_est, "unknown": int(flags[codes.UNKNOWN]),
        "attrStride": ATTR_DTYPE.itemsize,
        "tiles": [{k: v for k, v in t.items() if k != "data"} for t in tiles],
        "packs": [f"pack{k}.bin.gz" for k in range(len(packs))],
        "stats": {
            "buildings": len(df),
            "byFlag": {name: int(flags[code]) for code, name in FLAG_NAMES.items()},
            "bySrc": {name: int(srcs[i]) for i, name in enumerate(SRC_NAMES)},
            "floorsOsm": int((df.fsrc == codes.FLOORS_OSM).sum()),
            "floorsHeight": int((df.fsrc == codes.FLOORS_HEIGHT).sum()),
            "privateHouses": int(df.private.sum()),
            **(wiki_stats or {"photos": 0, "extracts": {"sv": 0, "en": 0}}),
        },
        "features": city.FEATURES,
        "langFromBrowser": city.LANG_FROM_BROWSER,
        "attribution": attribution(sources, terrain["source"]),
        "accuracy": accuracy,
        "terrain": terrain_config(terrain),
        "links": city.LINKS,
        "landmarks": list(landmarks),
    }


def photo_gids(cards: list[dict]) -> list[int]:
    """The sorted gids whose card carries a photo, from the card shards."""
    return sorted(int(g) for shard in cards for g, c in shard.items() if "photo" in c)


def write_outputs(df: pd.DataFrame, out: Path, version: str, *, tile: float = city.TILE,
                  n_packs: int = city.N_PACKS, sources: list[dict] | None = None, accuracy: dict | None = None,
                  terrain: dict | None = None, wiki: dict | None = None, landmarks: list[dict] | None = None,
                  places: dict | None = None) -> dict:
    """Write packs, attrs, cards, excerpt shards, photos.json, layers.json and stockholm.json into `out`; return a size
    summary. wiki: load_wiki()'s shape (default: read from data/); landmarks: s08_landmarks' entries (likewise);
    places: load_places()'s shape (likewise)."""
    out = Path(out)
    sources = load_sources(SOURCES) if sources is None else sources
    accuracy = load_accuracy() if accuracy is None else accuracy
    terrain = load_terrain() if terrain is None else terrain
    wiki = load_wiki() if wiki is None else wiki
    landmarks = load_landmarks() if landmarks is None else landmarks
    places = load_places() if places is None else places
    df = with_places(with_wiki(df, wiki["table"]), places)
    tiles = build_tiles(df, tile)
    packs = assign_packs(tiles, n_packs)
    gz = [io.write_gz(out / f"pack{k}.bin.gz", p) for k, p in enumerate(packs)]
    attrs = attrs_array(df)
    attrs_gz = io.write_gz(out / "attrs.bin.gz", attrs.tobytes())
    cards = card_shards(df, wiki["photos"], landmarks)
    for k, shard in enumerate(cards):
        io.write_json(out / "cards" / f"{k:02d}.json", shard)
    texts = wiki_shards(df, wiki["extracts"])
    for k, shard in enumerate(texts):
        io.write_json(out / "wiki" / f"{k:02d}.json", shard)
    names, dist_bytes = district_codes(df)
    io.write_gz(out / "districts.bin.gz", dist_bytes.tobytes())
    used = sorted({c["photo"]["key"] for shard in cards for c in shard.values() if "photo" in c})
    io.write_json(out / "photos.json", used)
    io.write_json(out / "photo-gids.json", photo_gids(cards))
    io.write_json(out / "layers.json", [])
    excerpts = [v for shard in texts for v in shard["items"].values()]
    wiki_stats = {"photos": len(used), "extracts": {lang: sum(lang in v for v in excerpts) for lang in city.WIKI["langs"]}}
    config = make_config(df, tiles, packs, version, tile, sources, accuracy, terrain, timeline_landmarks(df, landmarks),
                         wiki_stats)
    config["districts"] = names
    config["about"] = about_stats(df, cards)
    # the accuracy table's rows and columns in each language (About): the groups by key, the eras by their English
    config["accuracyLabels"] = {"en": {"groups": city.GROUP_LABELS, "eras": {}},
                                "sv": {"groups": city.GROUP_LABELS_SV, "eras": city.ERA_LABELS_SV}}
    io.write_json(out / f"{city.SLUG}.json", config)
    config_gz = len(io.gzip_bytes((out / f"{city.SLUG}.json").read_bytes()))  # size estimate only, not written
    return {"tiles": len(tiles), "buildings": len(df), "max_tile": max(t["n"] for t in tiles),
            "packs_raw": sum(map(len, packs)), "packs_gz": sum(gz), "pack0_gz": gz[0],
            "attrs_raw": attrs.nbytes, "attrs_gz": attrs_gz, "config_gz": config_gz,
            "first_load": config_gz + attrs_gz + gz[0]}


def out_dir(version: str | None = None) -> Path:
    """web/data/<version>/ for steps after s03: the given version, else the one current.json names."""
    if version is None and CURRENT.exists():
        version = json.loads(CURRENT.read_text())["version"]
    return io.version_dir(version)


def keep_keys(buildings: Path, folder: Path, version: str) -> Path:
    """folder/<version>.parquet: gid, uuid, oid of the buildings this version was made from. A gid belongs to one
    version; the takedown routine (docs/privacy.md) reads a reported gid's keys here, as data/buildings.parquet is
    overwritten by every load, a fixture build's included (final review, F8). Git-ignored, like all of data/."""
    names = pq.read_schema(buildings).names
    keys = pd.read_parquet(buildings, columns=[c for c in ("gid", "uuid", "oid") if c in names])
    folder.mkdir(parents=True, exist_ok=True)
    keys.to_parquet(folder / f"{version}.parquet", index=False)
    return folder / f"{version}.parquet"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s03_tiles", description=__doc__.splitlines()[0])
    ap.add_argument("--version", help="output version vYYYYMMDD or vYYYYMMDD-tag (default: today)")
    ap.add_argument("--tile", type=float, default=city.TILE, help="tile size in metres")
    args = ap.parse_args(argv)
    out = io.version_dir(args.version)
    version = out.name
    s = write_outputs(load(), out, version, tile=args.tile)
    io.write_json(CURRENT, {"version": version})
    keep_keys(DATA / "buildings.parquet", DATA / "keys", version)
    mb = 1e6
    print(f"{s['buildings']} buildings in {s['tiles']} tiles of {args.tile:g} m (max {s['max_tile']} per tile); "
          f"packs {s['packs_raw'] / mb:.2f} MB raw, {s['packs_gz'] / mb:.2f} MB gz; "
          f"attrs {s['attrs_raw'] / mb:.2f} MB raw, {s['attrs_gz'] / mb:.2f} MB gz; "
          f"first load {s['first_load'] / mb:.2f} MB → {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
