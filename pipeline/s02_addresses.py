"""Each footprint's OpenStreetMap addresses and its stadsdel.

Reads data/buildings.parquet, s00_fetch_osm's address tiles (data/raw/osm/addresses/) and Stadsdelar.zip; writes
data/addresses.parquet (gid, street, number, withheld: one row per address on a footprint, pipeline/addresses.py; never
one that reads as a property designation, addresses.without_designations; withheld where a takedown's address sits,
suppress.addresses) and
data/districts.parquet (gid, district: the stadsdel NAMN under the footprint, estimate.stadsdel_of). Both are internal:
s03_tiles puts a footprint's first address and how many it has on its card (not on a private house's while
city.PRIVATE_ADDRESSES is False) and its stadsdel in districts.bin.gz (one byte per building, the display names of
city.DISTRICT_NAMES in stockholm.json), and s14_search builds the search index from them.
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import addresses, suppress
from .estimate import stadsdel_of
from .s02_attributes import STADSDELAR, osm_tiles_needed
from .s02_years import BUILDINGS

OUT = Path("data/addresses.parquet")
DISTRICTS = Path("data/districts.parquet")


def build(b: gpd.GeoDataFrame, points: pd.DataFrame, stadsdelar: Path = STADSDELAR) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """(addresses, districts, addresses left out as designations) for buildings `b` (gid, geometry, fastighet) and
    address points (osm, street, number, x, y)."""
    on, dropped = addresses.without_designations(addresses.on_footprints(points, b), b.fastighet)
    districts = pd.DataFrame({"gid": b.gid.to_numpy().astype("int32"), "district": stadsdel_of(b, stadsdelar)})
    return on, districts.sort_values("gid").reset_index(drop=True), dropped


def summary(points: pd.DataFrame, on: pd.DataFrame, n_buildings: int, dropped: int = 0) -> str:
    hit = on.gid.nunique()
    return (f"addresses: {len(points):,} house numbers, {len(on):,} on footprints; {hit:,} of {n_buildings:,} footprints "
            f"({hit / max(n_buildings, 1):.1%}) have one; {on.street.nunique():,} streets; {dropped} left out as "
            "property designations")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s02_addresses", description=__doc__.splitlines()[0])
    ap.add_argument("--buildings", type=Path, default=BUILDINGS)
    ap.add_argument("--tiles", type=Path, default=addresses.ADDRESSES, help="s00_fetch_osm's address tiles")
    ap.add_argument("--stadsdelar", type=Path, default=STADSDELAR)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--districts", type=Path, default=DISTRICTS)
    ap.add_argument("--suppress", type=Path, default=None, help="takedowns (default pipeline/suppress.yml)")
    a = ap.parse_args(argv or [])
    # every tile of the current grid, and only those: a city with tiles missing would quietly lose its addresses there
    needed = osm_tiles_needed()
    missing = [k for k in needed if not (Path(a.tiles) / f"{k}.json").exists()]
    if len(missing) == len(needed):
        raise SystemExit(f"{a.tiles} holds no tiles: run s00_fetch_osm first")
    if missing:
        raise SystemExit(f"{a.tiles} lacks {len(missing)} of {len(needed)} tiles ({', '.join(missing)}): "
                         "run s00_fetch_osm first")
    b = gpd.read_parquet(a.buildings, columns=["gid", "fastighet", "geometry"])
    points = addresses.load(a.tiles, needed)
    on, districts, dropped = build(b, points, a.stadsdelar)
    taken = suppress.gids_of(a.buildings, a.suppress)                     # a takedown's addresses go
    on = suppress.addresses(on, taken, addresses.near(points, b, taken))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    on.to_parquet(a.out, index=False)
    districts.to_parquet(a.districts, index=False)
    print(summary(points, on[~on.withheld], len(b), dropped))


if __name__ == "__main__":
    main(sys.argv[1:])
