"""The real-data fixtures and remote sources (network)."""
import numpy as np
import pytest
import requests
import shapely

from pipeline import city
from pipeline.fetch import UA, fetch_zip_member, http_range_reader, read_central_directory, zip_members
from pipeline.sources import load_sources
from tests import synth

pytestmark = pytest.mark.network
URL = {s["id"]: s["url"] for s in load_sources()}


def test_lod1_zip_folders_decode_as_cp850(lod1_dir):
    names = sorted(p.name for p in lod1_dir.glob("*_StadsModell_shp"))
    assert "Södermalm_StadsModell_shp" in names and "Östermalm_StadsModell_shp" in names
    assert "Enskede-Årsta-Vantör_StadsModell_shp" in names and "Hägersten-Älvsjö_StadsModell_shp" in names


def test_gamla_stan_fixture(gamla_stan_lod1):
    gdf = gamla_stan_lod1
    assert 480 <= len(gdf) <= 560  # 519 on 2026-10-14: 430 Gamla stan, 12 Riddarholmen, 59 Södermalm, 18 Norrmalm
    assert list(gdf.columns) == [*synth.LOD1_COLUMNS, "district", "geometry"]
    assert gdf.crs.to_epsg() == city.CRS
    assert set(gdf.geometry.geom_type) == {"MultiPolygon"} and gdf.geometry.has_z.all()
    minx, miny, maxx, maxy = gdf.total_bounds
    assert minx < city.FIXTURE_BBOX[2] and maxx > city.FIXTURE_BBOX[0]
    assert miny < city.FIXTURE_BBOX[3] and maxy > city.FIXTURE_BBOX[1]
    tallest = gdf.loc[gdf.BYGG_H.idxmax()]
    assert tallest.BYGG_H == pytest.approx(89.7) and tallest.KATEGORI == "Ospec. samfundsbyggnad"  # Riddarholmskyrkan
    assert gdf.UUID.isna().sum() > 0  # buildings without a register UUID exist even here


def test_fixture_is_a_fresh_copy(gamla_stan_lod1, _gamla_stan_lod1):
    gamla_stan_lod1["BYGG_H"] = 0.0
    assert _gamla_stan_lod1.BYGG_H.max() > 0


def test_sources_are_reachable():
    for sid, url in URL.items():
        r = requests.head(url, headers=UA, timeout=60, allow_redirects=True)
        assert r.status_code == 200, sid
        # a size only for a data file: the others are web pages (Wikidata's front page shrank to 43 KB, 2026-10-19)
        if url.lower().endswith((".zip", ".gpkg", ".pdf")):
            assert int(r.headers["Content-Length"]) > 100_000, sid


def test_stadskarta_members_by_range_request(tmp_path):
    url = URL["city_stadskarta"]
    names = zip_members(url)
    folder = "Stockholm_Utskr-Stadskarta-Standard_shp/"
    for layer in ["Vatten_area", "Land_area", "TextKurvad_line", "NamnText_point", "AdressText_point",
                  "Vaegutbredning_area"]:
        assert f"{folder}{layer}.shp" in names and f"{folder}{layer}.dbf" in names
    entry = fetch_zip_member(url, f"{folder}Vatten_area.prj", tmp_path / "Vatten_area.prj",
                             manifest=tmp_path / "MANIFEST.json")
    assert 'AUTHORITY["EPSG",3011]' in (tmp_path / "Vatten_area.prj").read_text(encoding="utf-8")
    assert entry["member"] == f"{folder}Vatten_area.prj" and entry["etag"]


def test_lod1_member_names_over_http_are_cp850():
    url = URL["city_lod1"]
    size = int(requests.head(url, headers=UA, timeout=60).headers["Content-Length"])
    members = read_central_directory(http_range_reader(url), size)
    shps = [m.name for m in members if m.name.endswith("/Byggnad.shp")]
    assert len(shps) == 13 and "Östermalm_StadsModell_shp/Byggnad.shp" in shps
    assert all(m.flags & 0x800 == 0 for m in members)  # no UTF-8 flag: the legacy code page


def test_synthetic_lod1_has_the_real_columns_and_dtypes(gamla_stan_lod1):
    fake = synth.lod1_raw([{"footprint": synth.square(0, 0)}])
    assert list(fake.columns) == list(gamla_stan_lod1.columns)
    assert fake.dtypes.astype(str).to_dict() == gamla_stan_lod1.dtypes.astype(str).to_dict()
    real = gamla_stan_lod1.geometry.iloc[0]
    zs = [shapely.get_coordinates(p, include_z=True)[:, 2] for p in real.geoms]
    assert np.ptp(zs[0]) < 1e-6 and np.ptp(zs[-1]) < 1e-6  # first part is the floor, last the roof
    assert zs[0][0] < zs[-1][0]
