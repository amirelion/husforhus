"""Repository hygiene: Task 1 (toolchain, reference/ move, licence, ignores)."""
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

AMSTERDAM_MODULES = [
    "curated.py", "facts.py", "i18n_nl.py", "layers.py", "monuments.py", "periods.py", "quests.py",
    "s00_fetch_energy.py", "s00_fetch_layers.py", "s00_fetch_water.py", "s01_load.py", "s02_attributes.py",
    "s03_tiles.py", "s04_water.py", "s05_layers.py", "s06_wiki.py", "s07_labels.py", "s08_curated.py",
    "s09_residents.py", "s10_commons.py", "s11_facts.py", "s12_archive.py", "s13_quests.py",
]


def test_pipeline_package_imports():
    import pipeline

    assert Path(pipeline.__file__).name == "__init__.py"


@pytest.mark.skipif(not (ROOT / "reference").is_dir(), reason="reference/ is not part of the public export")
def test_amsterdam_modules_live_in_reference():
    ref = ROOT / "reference" / "amsterdam" / "pipeline"
    missing = [m for m in AMSTERDAM_MODULES if not (ref / m).is_file()]
    assert missing == []
    assert (ROOT / "reference" / "amsterdam" / "web" / "logo.js").is_file()
    assert (ROOT / "reference" / "amsterdam" / "CONTRIBUTING.md").is_file()
    for script in ["promo-video.mjs", "thumbnail.mjs"]:  # Amsterdam promo tools (stop-token's playwright, ffmpeg)
        assert (ROOT / "reference" / "amsterdam" / "scripts" / script).is_file(), script
        assert not (ROOT / "scripts" / script).exists(), script
    assert not (ROOT / "web" / "logo.js").exists()
    assert "logo.js" not in (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    readme = (ROOT / "reference" / "README.md").read_text(encoding="utf-8")
    assert "MIT" in readme and "alexbarakov" in readme


def test_pyproject():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "husforhus-pipeline"
    assert data["project"]["requires-python"] == ">=3.12"
    assert any(d.startswith("pyyaml") for d in data["project"]["dependencies"])
    dev = data["dependency-groups"]["dev"]
    assert any(d.startswith("pytest") for d in dev) and any(d.startswith("ruff") for d in dev)
    assert data["tool"]["ruff"]["line-length"] == 120
    assert "reference" in data["tool"]["ruff"]["extend-exclude"]
    assert data["tool"]["ruff"]["lint"]["select"] == ["E4", "E7", "E9", "F"]
    assert any(m.startswith("network") for m in data["tool"]["pytest"]["ini_options"]["markers"])


def test_licence_keeps_upstream_copyright():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Copyright (c) 2026 alexbarakov" in text
    assert "Copyright (c) 2026 Amir Elion and contributors" in text


def test_gitignore_and_nvmrc():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    for entry in ["data/", "web/data/", "temp_trash/", "node_modules/", "test-results/", "playwright-report/",
                  ".DS_Store", "pipeline/suppress.yml"]:
        assert entry in ignored, entry
    assert ".env" in ignored or ".env*" in ignored
    assert (ROOT / ".nvmrc").read_text(encoding="utf-8").strip() == "22"


def test_one_canonical_address():
    # www.husforhus.se serves the same page; search engines are pointed at the bare domain
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://husforhus.se/">' in html
    assert '<meta property="og:url" content="https://husforhus.se/">' in html
