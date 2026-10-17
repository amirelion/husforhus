import gzip
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon, box

from pipeline import city, s04_base, terrain

E0, N0 = city.ORIGIN


def test_pack_unpack_round_trip():
    outer = box(E0, N0, E0 + 100, N0 + 50)
    with_hole = Polygon(outer.exterior.coords, [box(E0 + 10, N0 + 10, E0 + 20, N0 + 20).exterior.coords])
    island = box(E0 - 300, N0 - 300, E0 - 250, N0 - 280)
    polys = s04_base.unpack(s04_base.pack([with_hole, island]))
    assert [len(p) for p in polys] == [2, 1]
    for got, poly in zip(polys, [with_hole, island], strict=True):
        for xz, ring in zip(got, [poly.exterior, *poly.interiors], strict=True):
            c = shapely.get_coordinates(ring)[:-1]
            x, z = city.to_local(c[:, 0], c[:, 1])
            assert np.allclose(xz, np.c_[x, z], atol=0.01)
    # local frame: z points south, so a polygon north of the origin has negative z
    assert polys[0][0][:, 1].max() <= 0 and polys[1][0][:, 1].min() >= 280 - 0.01


def wavy(t):
    """A 3 m sine with a 40 m wavelength: enough for the 1 m simplification to move a line, unlike a box's sides."""
    return 3.0 * np.sin(2 * np.pi * np.asarray(t, dtype=float) / 40.0)


def test_land_and_water_split_the_municipality():
    # the town's north edge and the strait's west bank are curved (coordinates on a 1 cm grid), so simplifying moves
    # them; the strait crosses the town's north and south edges and is clipped there
    xs = np.arange(0, 1001.0)
    town = Polygon(np.round(np.r_[[[E0, N0], [E0 + 1000, N0]], np.c_[E0 + xs, N0 + 1000 + wavy(xs)][::-1]], 2))
    ns = np.arange(-500, 1501.0)
    strait = Polygon(np.round(np.r_[[[E0 + 600, N0 - 500], [E0 + 600, N0 + 1500]],
                                    np.c_[E0 + 400 + wavy(ns), N0 + ns][::-1]], 2))
    pond = box(E0 + 100, N0 + 100, E0 + 104, N0 + 102)    # 8 m²: dropped
    land, water = s04_base.land_and_water([strait, pond], town)
    # land is the domain minus that same water: they share every edge, no gap and no overlap. Clipping first and
    # simplifying land and water apart (the first recipe) leaves about 930 m² of gaps and overlaps and 22 m² of overlap
    assert shapely.union_all(land + water).symmetric_difference(town).area < 1e-3
    assert sum(shapely.intersection(lp, wp).area for lp in land for wp in water) < 1e-6
    # simplified before the clip, the water follows the domain's curved edge exactly (the first recipe left 42 m² of
    # it outside the town)
    assert water[0].difference(town).area < 1e-3
    # the sines span whole wavelengths, so the strait keeps about 200,000 m² and the land about 800,000 m²
    assert len(water) == 1 and abs(water[0].area - 200_000) < 5
    assert len(land) == 2 and abs(sum(p.area for p in land) - 800_000) < 50
    assert all(town.buffer(0.01).contains(p) for p in land + water)


def test_main_writes_land_and_water_into_the_current_version(tmp_path, monkeypatch):
    raw = tmp_path / "data" / "raw" / "city"
    (raw / "stadsdelar").mkdir(parents=True)
    (raw / "stadskarta").mkdir(parents=True)
    halves = [box(E0, N0, E0 + 500, N0 + 1000), box(E0 + 500, N0, E0 + 1000, N0 + 1000)]
    gpd.GeoDataFrame({"NAMN": ["VÄST", "ÖST"]}, geometry=halves, crs=city.CRS).to_file(
        raw / "stadsdelar" / "Stadsdel.shp")
    gpd.GeoDataFrame({"GRUPP": ["Sjö"]}, geometry=[box(E0 + 400, N0, E0 + 600, N0 + 1000)],
                     crs=city.CRS).to_file(raw / "stadskarta" / "Vatten_area.shp")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "web" / "data").mkdir(parents=True)
    (tmp_path / "web" / "data" / "current.json").write_text('{"version":"v20990101"}')
    # s02_terrain's outputs for this town: a flat grid at 2 m, the strait at the sea's level
    land_p, water_p = s04_base.land_and_water([box(E0 + 400, N0, E0 + 600, N0 + 1000)], box(E0, N0, E0 + 1000, N0 + 1000))
    grid = terrain.grid_for(terrain.to_local(box(E0, N0, E0 + 1000, N0 + 1000)).bounds, 20.0)
    np.savez(tmp_path / "data" / "terrain.npz", h=np.full((grid.nz, grid.nx), 2.0, np.float32),
             cut=np.zeros((grid.nz, grid.nx), np.float32), levels=np.zeros(len(water_p), np.float32))
    (tmp_path / "data" / "buildings.parquet").write_bytes(b"the buildings s02_terrain read")
    (tmp_path / "data" / "attributes.parquet").write_bytes(b"the attributes s02_terrain read")
    record = {"source": "contours", **grid.to_dict(), "water_z": 0.0, "water_area": sum(p.area for p in water_p),
              "buildings_sha256": hashlib.sha256(b"the buildings s02_terrain read").hexdigest(),
              "attributes_sha256": hashlib.sha256(b"the attributes s02_terrain read").hexdigest()}
    (tmp_path / "data" / "terrain.json").write_text(json.dumps(record))
    s04_base.main([])
    out = tmp_path / "web" / "data" / "v20990101"
    water = s04_base.unpack(gzip.decompress((out / "water.bin.gz").read_bytes()))
    land = s04_base.unpack(gzip.decompress((out / "land.bin.gz").read_bytes()))
    assert len(water) == 1 and len(land) == 2
    t = terrain.unpack(gzip.decompress((out / "terrain.bin.gz").read_bytes()))
    assert t["grid"] == grid and t["levels"].tolist() == [0.0] and t["n_shore"] == 4
    # two shore sides (the strait's banks), two on the town's edge
    assert np.unpackbits(np.frombuffer(t["shore"], np.uint8), bitorder="little")[:4].sum() == 2
    assert t["source"] == "contours"
    # every refusal comes before the first write: the version folder keeps its files, bytes and times
    shipped = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()}
    # a pond added to the Stadskarta since s02_terrain ran: its levels belong to other water, refused
    vatten = raw / "stadskarta" / "Vatten_area.shp"
    strait_and_pond = [box(E0 + 400, N0, E0 + 600, N0 + 1000), box(E0 + 100, N0 + 100, E0 + 150, N0 + 150)]
    gpd.GeoDataFrame({"GRUPP": ["Sjö", "Sjö"]}, geometry=strait_and_pond, crs=city.CRS).to_file(vatten)
    with pytest.raises(SystemExit, match="other water polygons"):
        s04_base.main([])
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()} == shipped
    # the same number of water polygons, but the strait drawn 20 m wider: its area alone tells them apart (PIPELINE-7)
    gpd.GeoDataFrame({"GRUPP": ["Sjö"]}, geometry=[box(E0 + 400, N0, E0 + 620, N0 + 1000)], crs=city.CRS).to_file(vatten)
    with pytest.raises(SystemExit, match="other water polygons"):
        s04_base.main([])
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()} == shipped
    gpd.GeoDataFrame({"GRUPP": ["Sjö"]}, geometry=strait_and_pond[:1], crs=city.CRS).to_file(vatten)
    # a terrain built for other buildings (s01_load ran again since) is refused, never shipped
    (tmp_path / "data" / "buildings.parquet").write_bytes(b"buildings loaded again")
    with pytest.raises(SystemExit, match="buildings.parquet: run s02_terrain again"):
        s04_base.main([])
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()} == shipped
    # nor does a refused build into a new version leave a folder behind
    with pytest.raises(SystemExit, match="buildings.parquet: run s02_terrain again"):
        s04_base.main(["--version", "v20990102"])
    assert not (tmp_path / "web" / "data" / "v20990102").exists()


REAL = Path("data/raw/city/stadskarta/Vatten_area.shp")


@pytest.mark.skipif(not REAL.exists(), reason="needs s00_fetch_city output in data/raw/city")
def test_real_stockholm_land_and_water():
    land, water = s04_base.land_and_water(
        shapely.force_2d(gpd.read_file(REAL).geometry.values), s04_base.boundary())
    assert abs(sum(p.area for p in water) / 1e6 - 27.9) < 0.3
    assert abs(sum(p.area for p in land) / 1e6 - 187.9) < 1.0
    assert len(gzip.compress(s04_base.pack(water), 9)) < 200_000
    assert len(gzip.compress(s04_base.pack(land), 9)) < 200_000
