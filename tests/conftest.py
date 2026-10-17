"""Shared pytest setup.

Network tests (marked @pytest.mark.network) are skipped unless pytest gets --network or HFH_NETWORK=1.
`-m network` only selects them: `pytest -m network` reports them as skipped, `pytest --network -m network` runs them.
The City LOD1 zip is downloaded once into data/cache/ (git-ignored; HFH_CACHE overrides the folder) and its
sha256 is recorded in data/cache/MANIFEST.json on the first download; later sessions check the file against it.
City-derived bytes never enter git: the Gamla stan fixture is cut from the zip at test time.
"""
import os
import zipfile
from pathlib import Path

import pandas as pd
import pyogrio
import pytest

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("HFH_CACHE", ROOT / "data" / "cache"))
LOD1_URL = "https://dataportalen.stockholm.se/dataportalen/Data/Stadsbyggnadskontoret/LOD1_stadsdelsnamnder_SHP.zip"


@pytest.fixture(autouse=True)
def _no_real_takedowns(tmp_path_factory, monkeypatch):
    """Pipeline/suppress.yml (git-ignored) may hold real takedowns on a maintainer's machine; no test reads it.
    A test that wants takedowns writes its own file and passes it."""
    from pipeline import suppress

    monkeypatch.setattr(suppress, "SUPPRESS", tmp_path_factory.getbasetemp() / "no-suppress.yml")


def pytest_addoption(parser):
    parser.addoption("--network", action="store_true", default=False,
                     help="run tests marked 'network' (they download real data); same as HFH_NETWORK=1")


def network_enabled(config) -> bool:
    return bool(config.getoption("--network")) or os.environ.get("HFH_NETWORK") == "1"


def pytest_collection_modifyitems(config, items):
    if network_enabled(config):
        return
    skip = pytest.mark.skip(reason="needs --network or HFH_NETWORK=1")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def lod1_zip(request) -> Path:
    """Path to the City LOD1 zip (17.8 MB), downloaded at most once per ETag and verified by sha256."""
    if not network_enabled(request.config):
        pytest.skip("needs --network or HFH_NETWORK=1")
    from pipeline.fetch import download, sha256_file

    dest = CACHE / "LOD1_stadsdelsnamnder_SHP.zip"
    entry = download(LOD1_URL, dest, manifest=CACHE / "MANIFEST.json")
    assert sha256_file(dest) == entry["sha256"], "cached LOD1 zip does not match its recorded sha256"
    return dest


@pytest.fixture(scope="session")
def lod1_dir(lod1_zip) -> Path:
    """The zip extracted once per sha256, with the CP850 folder names decoded (Södermalm, Östermalm, …)."""
    from pipeline.fetch import read_manifest

    sha = read_manifest(CACHE / "MANIFEST.json")[lod1_zip.name]["sha256"]
    target = CACHE / f"lod1-{sha[:12]}"
    done = target / ".extracted"
    if not done.exists():
        with zipfile.ZipFile(lod1_zip, metadata_encoding="cp850") as z:
            z.extractall(target)
        done.write_text(sha, encoding="utf-8")
    return target


@pytest.fixture(scope="session")
def _gamla_stan_lod1(lod1_dir):
    from pipeline import city

    shps = sorted(lod1_dir.glob("*_StadsModell_shp/Byggnad.shp"))
    assert len(shps) == 13, shps
    frames = []
    for shp in shps:
        gdf = pyogrio.read_dataframe(shp, bbox=city.FIXTURE_BBOX)
        gdf.insert(gdf.columns.get_loc("geometry"), "district", shp.parent.name.removesuffix("_StadsModell_shp"))
        if len(gdf):  # empty frames would turn str columns into object and ints into float in concat
            frames.append(gdf)
    gdf = pd.concat(frames, ignore_index=True).set_crs(city.CRS, allow_override=True)
    # whole-file reads give float64 here (every district file has rows without them); a bbox read may not
    return gdf.astype({"KOM_ID": "float64", "FNR": "float64", "HUSNR": "float64"})


@pytest.fixture
def gamla_stan_lod1(_gamla_stan_lod1):
    """Raw LOD1 features (MULTIPATCH read as MultiPolygon Z, all original columns plus `district`, the folder
    name) whose geometry intersects city.FIXTURE_BBOX. A fresh copy per test."""
    return _gamla_stan_lod1.copy()
