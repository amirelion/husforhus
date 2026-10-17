"""The tower candidates and their cached laser points, shared by s00_fetch_laser (which fetches the points) and
s02_towers (which reads them).

A candidate is a building that is not a private house (the `private` column, and every non-curated building in a
city.PRIVATE_HOUSE_KATEGORI category, as s03_tiles.hidden) and is named on a card (s02_attributes' name, else the
Wikidata name s06_wiki found), or is a church or a water tower (s02_attributes' nofloors: RAÄ purpose group
Religionsutövning or KATEGORI Vattentorn), or has a LOD1 height of city.LASER's min_lod1_m or more, or is on the hand
list city.LASER_TOWERS (matched by its card's name).

The points around a candidate (its footprint's box grown by city.LASER's ring_m) are kept in
data/raw/laser/points/<gid>.npz, never anywhere else: Lantmäteriet's terms say the points may hold personal data, so
only the building parts derived from them leave data/raw (s02_towers' data/towers.parquet), and neither is committed
(data/ is git-ignored). Each file holds x0, y0 (float64, EPSG:3011), x and y (float32, metres from x0, y0), z (float32,
RH 2000), cls, rn and nr (uint8: classification, return number, number of returns).
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from . import city, codes
from .fetch import RAW

LASER = RAW / "laser"
POINTS = LASER / "points"
MANIFEST = LASER / "manifest.json"
DATA = Path("data")
FIELDS = ("x", "y", "z", "cls", "rn", "nr")
REASONS = ("named", "church", "tall", "list")     # a candidate's `why`, comma-separated, in this order


def _text(v) -> str:
    return v if isinstance(v, str) else ""


def hidden(kategori, private, ysrc) -> np.ndarray:
    """Per row, True for a private house: marked private, or a non-curated building in a private-house category (the
    rule s03_tiles.hidden applies to the cards)."""
    return (np.asarray(private, dtype=bool)
            | (pd.Series(kategori).isin(city.PRIVATE_HOUSE_KATEGORI).to_numpy()
               & (np.asarray(ysrc) != codes.SRC_CURATED)))


def card_names(df: pd.DataFrame) -> list[str]:
    """The name a card shows: s02_attributes' name, else the Wikidata name (wname) where the card may carry one."""
    hide = hidden(df.kategori, df.private, df.ysrc)
    wname = df["wname"] if "wname" in df else pd.Series([""] * len(df))
    return [_text(n) or ("" if h else _text(w)) for n, w, h in zip(df["name"], wname, hide, strict=True)]


def hand_list(names: list[str], hand=city.LASER_TOWERS) -> dict[str, list[int]]:
    """Row positions per hand-list entry (its first name), matched by any of the entry's names, casefolded, and by
    the other names city.BUILDING_ALIASES gives them."""
    wanted = {}
    for entry in hand:
        keys = {n.casefold() for n in entry}
        keys |= {v.casefold() for k, v in city.BUILDING_ALIASES.items() if k.casefold() in keys}
        wanted[entry[0]] = keys
    found = {label: [] for label in wanted}
    for i, n in enumerate(names):
        for label, keys in wanted.items():
            if n and n.casefold() in keys:
                found[label].append(i)
    return found


def candidates(b: gpd.GeoDataFrame, y: pd.DataFrame, a: pd.DataFrame, wiki: pd.DataFrame | None = None,
               hand=city.LASER_TOWERS) -> tuple[gpd.GeoDataFrame, list[str]]:
    """(the candidates: gid, name, why, height, ground, geometry (EPSG:3011), sorted by gid; the hand-list entries no
    card name matched). b is buildings.parquet (gid, kategori, height, ground, geometry), y years.parquet (gid,
    private, ysrc), a attributes.parquet (gid, name, nofloors where it has one), wiki s06_wiki's table (gid, name)."""
    df = b[["gid", "kategori", "height", "ground", "geometry"]].merge(
        y[["gid", "private", "ysrc"]], on="gid", validate="one_to_one").merge(
        a[["gid", "name", *(["nofloors"] if "nofloors" in a else [])]], on="gid", validate="one_to_one")
    if wiki is not None and len(wiki):
        w = wiki[["gid", "name"]].rename(columns={"name": "wname"}).astype({"gid": df.gid.dtype})
        df = df.merge(w, on="gid", how="left", validate="one_to_one")
    df = df.sort_values("gid").reset_index(drop=True)
    names = card_names(df)
    hide = hidden(df.kategori, df.private, df.ysrc)
    found = hand_list(names, hand)
    on_list = np.zeros(len(df), dtype=bool)
    for rows in found.values():
        on_list[rows] = True
    why = {"named": np.array([bool(n) for n in names]),
           "church": df["nofloors"].fillna(False).to_numpy(bool) if "nofloors" in df else np.zeros(len(df), bool),
           "tall": df.height.to_numpy(np.float64) >= city.LASER["min_lod1_m"],
           "list": on_list}
    assert tuple(why) == REASONS
    keep = ~hide & np.any(list(why.values()), axis=0)
    out = gpd.GeoDataFrame({
        "gid": df.gid.to_numpy()[keep].astype(np.int64),
        "name": np.array(names, dtype=object)[keep],
        "why": [",".join(k for k, v in why.items() if v[i]) for i in np.flatnonzero(keep)],
        "height": df.height.to_numpy(np.float64)[keep],
        "ground": df.ground.to_numpy(np.float64)[keep],
    }, geometry=df.geometry.values[keep], crs=city.CRS)
    missing = [label for label, rows in found.items() if not any(keep[r] for r in rows)]
    return out, missing


def load_candidates(data: Path = DATA) -> tuple[gpd.GeoDataFrame, list[str]]:
    """candidates() over data/'s tables (wiki.parquet when s06_wiki has run)."""
    for name in ("buildings", "years", "attributes"):
        if not (data / f"{name}.parquet").exists():
            raise SystemExit(f"{data / name}.parquet is missing: run s01_load, s02_years and s02_attributes first")
    b = gpd.read_parquet(data / "buildings.parquet", columns=["gid", "kategori", "height", "ground", "geometry"])
    wiki = pd.read_parquet(data / "wiki.parquet") if (data / "wiki.parquet").exists() else None
    return candidates(b, pd.read_parquet(data / "years.parquet"), pd.read_parquet(data / "attributes.parquet"), wiki)


def query_box(geom, ring: float = city.LASER["ring_m"]) -> tuple[float, float, float, float]:
    """A footprint's box grown by `ring` on every side (EPSG:3011), rounded outward to the decimetre."""
    x0, y0, x1, y1 = shapely.bounds(geom)
    return (float(np.floor((x0 - ring) * 10) / 10), float(np.floor((y0 - ring) * 10) / 10),
            float(np.ceil((x1 + ring) * 10) / 10), float(np.ceil((y1 + ring) * 10) / 10))


def points_path(gid: int, folder: Path = POINTS) -> Path:
    return Path(folder) / f"{int(gid)}.npz"


def save_points(path: Path, pts: dict) -> None:
    """Write one candidate's points (FIELDS; x and y in EPSG:3011) compactly; x0, y0 make float32 offsets exact
    enough (a millimetre within a few kilometres)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x, y = np.asarray(pts["x"], np.float64), np.asarray(pts["y"], np.float64)
    x0, y0 = (float(np.floor(x.min())), float(np.floor(y.min()))) if len(x) else (0.0, 0.0)
    tmp = path.with_name(path.name + ".part.npz")
    np.savez_compressed(tmp, x0=np.float64(x0), y0=np.float64(y0), x=(x - x0).astype(np.float32),
                        y=(y - y0).astype(np.float32), z=np.asarray(pts["z"], np.float32),
                        cls=np.asarray(pts["cls"], np.uint8), rn=np.asarray(pts["rn"], np.uint8),
                        nr=np.asarray(pts["nr"], np.uint8))
    tmp.replace(path)


def load_points(path: Path) -> dict:
    """save_points' file back as {x, y (float64, EPSG:3011), z (float64), cls, rn, nr}."""
    with np.load(path) as f:
        return {"x": f["x"].astype(np.float64) + float(f["x0"]), "y": f["y"].astype(np.float64) + float(f["y0"]),
                "z": f["z"].astype(np.float64), "cls": f["cls"], "rn": f["rn"], "nr": f["nr"]}
