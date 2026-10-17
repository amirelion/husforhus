import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from pipeline import s00_fetch_city as s00
from pipeline.fetch import zip_members

LAYERS = ["Vatten_area", "Land_area", "TextKurvad_line", "NamnText_point", "AdressText_point", "Vaegutbredning_area"]


def test_lod1_district_names_are_ascii_and_unique():
    safe = list(s00.LOD1_DISTRICTS.values())
    assert len(safe) == 13 and len(set(safe)) == 13
    assert all(s.isascii() and s == s.lower() and " " not in s for s in safe)
    assert s00.safe_name("Enskede-Årsta-Vantör_StadsModell_shp") == "enskede-arsta-vantor"
    assert s00.safe_name("Östermalm_StadsModell_shp") == "ostermalm"
    assert s00.safe_name("Älvsjö Ängby_StadsModell_shp") == "alvsjo-angby"   # a folder the City may add later


def test_stadskarta_members_cover_six_layers():
    assert len(s00.STADSKARTA_MEMBERS) == 30
    for layer in LAYERS:
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            assert f"Stockholm_Utskr-Stadskarta-Standard_shp/{layer}{ext}" in s00.STADSKARTA_MEMBERS


def _cp850_zip(path: Path, members: dict[bytes, bytes]) -> None:
    """Write a zip whose names are raw CP850 bytes without the UTF-8 flag, as the City's zips are."""
    placeholders = {}
    with zipfile.ZipFile(path, "w") as z:
        for i, (raw, data) in enumerate(members.items()):
            ph = (chr(ord("A") + i) * len(raw)).encode()  # ASCII placeholder of the same byte length; one letter
                                                          # per member, so no placeholder contains another
            placeholders[ph] = raw
            z.writestr(ph.decode(), data)
    blob = path.read_bytes()
    for ph, raw in placeholders.items():
        blob = blob.replace(ph, raw)
    path.write_bytes(blob)


def _lod1_members(skip: str = "") -> dict[bytes, bytes]:
    """Byggnad.shp for every district folder but `skip`, as the City names them (CP850)."""
    return {f"{folder}/Byggnad.shp".encode("cp850"): b"shp" for folder in s00.LOD1_DISTRICTS if folder != skip}


def test_extract_lod1_redecodes_names_into_ascii_dirs(tmp_path):
    zp = tmp_path / "lod1.zip"
    _cp850_zip(zp, {
        "Enskede-Årsta-Vantör_StadsModell_shp/Byggnad.dbf".encode("cp850"): b"dbf",
        **_lod1_members(),
        "Södermalm_StadsModell_shp/Byggnad.shp".encode("cp850"): b"shp2",
    })
    with zipfile.ZipFile(zp) as z:
        assert {i.flag_bits & 0x800 for i in z.infolist()} == {0}
        assert "Södermalm_StadsModell_shp/Byggnad.shp" in [s00.decode_name(i) for i in z.infolist()]
    dirs = s00.extract_lod1(zp, tmp_path / "lod1")
    assert sorted(dirs) == sorted(s00.LOD1_DISTRICTS.values())
    assert (tmp_path / "lod1" / "enskede-arsta-vantor" / "Byggnad.dbf").read_bytes() == b"dbf"
    assert (tmp_path / "lod1" / "sodermalm" / "Byggnad.shp").read_bytes() == b"shp2"


def test_extract_lod1_fails_on_a_missing_district_and_extracts_nothing(tmp_path):
    # A republished zip without Södermalm would ship a city ~10k buildings short, with s99 OK
    zp = tmp_path / "lod1.zip"
    _cp850_zip(zp, _lod1_members(skip="Södermalm_StadsModell_shp"))
    with pytest.raises(SystemExit, match="LOD1 districts missing from the zip: sodermalm"):
        s00.extract_lod1(zp, tmp_path / "lod1")
    assert not (tmp_path / "lod1").exists()  # the previous extraction, if any, stays as it was


def test_decode_name_uses_cp850_not_cp437():
    info = zipfile.ZipInfo("x")
    info.filename = "Bjørkhagen_StadsModell_shp/Byggnad.shp".encode("cp850").decode("cp437")   # how zipfile sees it
    info.flag_bits = 0
    assert s00.decode_name(info) == "Bjørkhagen_StadsModell_shp/Byggnad.shp"


@pytest.mark.network
def test_stadskarta_zip_still_has_the_members():
    present = set(zip_members(s00.STADSKARTA_URL))
    assert set(s00.STADSKARTA_MEMBERS) <= present


@pytest.mark.network
def test_main_fetches_city_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s00.main([])
    city = tmp_path / "data/raw/city"
    shps = sorted(p.parent.name for p in (city / "lod1").glob("*/Byggnad.shp"))
    assert shps == sorted(s00.LOD1_DISTRICTS.values())
    assert (city / "stadsdelar/Stadsdel.shp").stat().st_size > 100_000
    for layer in LAYERS:
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            assert (city / "stadskarta" / f"{layer}{ext}").stat().st_size > 0
    manifest = json.loads((tmp_path / "data/raw/MANIFEST.json").read_text())

    def entry(suffix):
        hits = [v for k, v in manifest.items() if k.endswith(suffix)]
        assert len(hits) == 1, suffix
        assert len(hits[0]["sha256"]) == 64
        return hits[0]

    lod1 = entry("city/LOD1_stadsdelsnamnder_SHP.zip")
    assert lod1["sha256"] == hashlib.sha256((city / "LOD1_stadsdelsnamnder_SHP.zip").read_bytes()).hexdigest()
    entry("city/Stadsdelar.zip")
    for m in s00.STADSKARTA_MEMBERS:
        entry("city/stadskarta/" + Path(m).name)
