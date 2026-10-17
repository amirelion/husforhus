import json

import pyogrio
import pytest

from pipeline import s00_fetch_raa as raa


def test_source_constants():
    assert raa.URL.startswith("https://pub.raa.se/nedladdning/datauttag/bebyggelse/")
    assert raa.URL.endswith("/kulturhistoriskt_inventerad_bebyggelse_stockholm.gpkg")
    assert raa.DEST.as_posix() == "data/raw/raa/kulturhistoriskt_inventerad_bebyggelse_stockholm.gpkg"
    assert raa.LAYER == "kulturhistoriskt_inventerad_bebyggelse_stockholm_polygon"


@pytest.mark.network
def test_main_downloads_the_county_geopackage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raa.main([])
    gpkg = tmp_path / raa.DEST
    assert raa.LAYER in [name for name, _ in pyogrio.list_layers(gpkg)]
    info = pyogrio.read_info(gpkg, layer=raa.LAYER)
    assert info["crs"] == "EPSG:3006"
    df = pyogrio.read_dataframe(gpkg, layer=raa.LAYER, columns=["kommunnamn"], read_geometry=False,
                                where="kommunnamn = 'Stockholm'")
    assert len(df) > 20_000                      # 23,524 on 2026-10-14 (28,058 rows in the county)
    manifest = json.loads((tmp_path / "data/raw/MANIFEST.json").read_text())
    [e] = [v for k, v in manifest.items() if k.endswith("raa/kulturhistoriskt_inventerad_bebyggelse_stockholm.gpkg")]
    assert len(e["sha256"]) == 64 and e["bytes"] == gpkg.stat().st_size
