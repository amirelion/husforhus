"""Fetch the City of Stockholm open data into data/raw/city/.

- LOD1 3D buildings (13 old stadsdelsnämnd folders, MULTIPATCH shapefiles), extracted to
  data/raw/city/lod1/<ascii district>/Byggnad.* with re-decoded, ASCII-safe folder names.
- Stadsdelar (117 districts; their union is the municipality).
- Six Stadskarta layers, range-read from the 107.8 MB zip without downloading it whole.
Every file is recorded in data/raw/MANIFEST.json by pipeline.fetch.
"""
import argparse
import sys
import unicodedata
import zipfile
from pathlib import Path

from pipeline.fetch import download, fetch_zip_member, zip_members

BASE = "https://dataportalen.stockholm.se/dataportalen/Data/Stadsbyggnadskontoret/"
LOD1_URL = BASE + "LOD1_stadsdelsnamnder_SHP.zip"
STADSDELAR_URL = BASE + "Stadsdelar.zip"
STADSKARTA_URL = BASE + "Stadskarta_hela_Stockholm.zip"
OUT = Path("data/raw/city")

# The 13 folders in LOD1_stadsdelsnamnder_SHP.zip (the old stadsdelsnämnder), as listed on 2026-10-14,
# mapped to ASCII-safe directory names under data/raw/city/lod1/.
LOD1_DISTRICTS = {
    "Bromma_StadsModell_shp": "bromma",
    "Enskede-Årsta-Vantör_StadsModell_shp": "enskede-arsta-vantor",
    "Farsta_StadsModell_shp": "farsta",
    "Hägersten-Älvsjö_StadsModell_shp": "hagersten-alvsjo",
    "Hässelby-Vällingby_StadsModell_shp": "hasselby-vallingby",
    "Kungsholmen_StadsModell_shp": "kungsholmen",
    "Norrmalm_StadsModell_shp": "norrmalm",
    "Rinkeby-Kista_StadsModell_shp": "rinkeby-kista",
    "Skarpnäck_StadsModell_shp": "skarpnack",
    "Skärholmen_StadsModell_shp": "skarholmen",
    "Spånga-Tensta_StadsModell_shp": "spanga-tensta",
    "Södermalm_StadsModell_shp": "sodermalm",
    "Östermalm_StadsModell_shp": "ostermalm",
}

# Exact member paths in Stadskarta_hela_Stockholm.zip (central directory read 2026-10-14: 152 entries,
# Last-Modified 2026-02-18). All five sidecar files exist for each of the six layers.
STADSKARTA_MEMBERS = [
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vatten_area.shp",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vatten_area.shx",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vatten_area.dbf",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vatten_area.prj",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vatten_area.cpg",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Land_area.shp",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Land_area.shx",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Land_area.dbf",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Land_area.prj",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Land_area.cpg",
    "Stockholm_Utskr-Stadskarta-Standard_shp/TextKurvad_line.shp",
    "Stockholm_Utskr-Stadskarta-Standard_shp/TextKurvad_line.shx",
    "Stockholm_Utskr-Stadskarta-Standard_shp/TextKurvad_line.dbf",
    "Stockholm_Utskr-Stadskarta-Standard_shp/TextKurvad_line.prj",
    "Stockholm_Utskr-Stadskarta-Standard_shp/TextKurvad_line.cpg",
    "Stockholm_Utskr-Stadskarta-Standard_shp/NamnText_point.shp",
    "Stockholm_Utskr-Stadskarta-Standard_shp/NamnText_point.shx",
    "Stockholm_Utskr-Stadskarta-Standard_shp/NamnText_point.dbf",
    "Stockholm_Utskr-Stadskarta-Standard_shp/NamnText_point.prj",
    "Stockholm_Utskr-Stadskarta-Standard_shp/NamnText_point.cpg",
    "Stockholm_Utskr-Stadskarta-Standard_shp/AdressText_point.shp",
    "Stockholm_Utskr-Stadskarta-Standard_shp/AdressText_point.shx",
    "Stockholm_Utskr-Stadskarta-Standard_shp/AdressText_point.dbf",
    "Stockholm_Utskr-Stadskarta-Standard_shp/AdressText_point.prj",
    "Stockholm_Utskr-Stadskarta-Standard_shp/AdressText_point.cpg",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vaegutbredning_area.shp",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vaegutbredning_area.shx",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vaegutbredning_area.dbf",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vaegutbredning_area.prj",
    "Stockholm_Utskr-Stadskarta-Standard_shp/Vaegutbredning_area.cpg",
]
REQUIRED_EXT = (".shp", ".shx", ".dbf")


def decode_name(info: zipfile.ZipInfo) -> str:
    """Member name as the City wrote it: CP850 bytes in a zip without the UTF-8 flag.

    Python decodes such names as CP437; re-encode and decode as CP850. For å, ä, ö, Å, Ä, Ö the two
    code pages agree; others differ (CP850 0x9B is ø, CP437 0x9B is ¢).
    """
    if info.flag_bits & 0x800:
        return info.filename
    return info.filename.encode("cp437").decode("cp850")


def safe_name(folder: str) -> str:
    """'Enskede-Årsta-Vantör_StadsModell_shp' -> 'enskede-arsta-vantor'."""
    if folder in LOD1_DISTRICTS:
        return LOD1_DISTRICTS[folder]
    stem = folder.removesuffix("_StadsModell_shp")
    ascii_ = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    return "".join(c if c.isalnum() or c == "-" else "-" for c in ascii_.lower()).strip("-")


def extract_lod1(zip_path: Path, out_dir: Path) -> dict[str, Path]:
    """Extract every <folder>/Byggnad.* to out_dir/<safe_name(folder)>/. Returns {safe name: dir}.

    A district missing from the zip stops the run before anything is written: the city would ship partial,
    and the previous extraction stays as it was."""
    with zipfile.ZipFile(zip_path) as z:
        members = []
        for info in z.infolist():
            if info.is_dir():
                continue
            folder, _, base = decode_name(info).rpartition("/")
            if folder and base.startswith("Byggnad."):
                members.append((info, safe_name(folder), base))
        found = {d for _, d, _ in members}
        unknown = sorted(found - set(LOD1_DISTRICTS.values()))
        missing = sorted(set(LOD1_DISTRICTS.values()) - found)
        if unknown:
            print("warning: LOD1 folders not in LOD1_DISTRICTS:", ", ".join(unknown))
        if missing:
            raise SystemExit("LOD1 districts missing from the zip: " + ", ".join(missing))
        dirs: dict[str, Path] = {}
        for info, safe, base in members:
            d = out_dir / safe
            d.mkdir(parents=True, exist_ok=True)
            (d / base).write_bytes(z.read(info))
            dirs[d.name] = d
    return dirs


def extract_flat(zip_path: Path, out_dir: Path) -> list[Path]:
    """Extract a zip whose members sit at the top level (Stadsdelar.zip) into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            p = out_dir / Path(decode_name(info)).name
            p.write_bytes(z.read(info))
            paths.append(p)
    return paths


def fetch_stadskarta(out_dir: Path) -> list[Path]:
    present = set(zip_members(STADSKARTA_URL))
    missing = [m for m in STADSKARTA_MEMBERS if m not in present]
    hard = [m for m in missing if m.endswith(REQUIRED_EXT)]
    if hard:
        raise SystemExit("Stadskarta zip is missing required members: " + ", ".join(hard))
    for m in missing:
        print("note: optional Stadskarta member not in the zip:", m)
    paths = []
    for m in STADSKARTA_MEMBERS:
        if m in missing:
            continue
        dest = out_dir / Path(m).name
        fetch_zip_member(STADSKARTA_URL, m, dest)
        paths.append(dest)
    return paths


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-stadskarta", action="store_true", help="only LOD1 and Stadsdelar")
    args = ap.parse_args([] if argv is None else argv)

    lod1_zip = OUT / "LOD1_stadsdelsnamnder_SHP.zip"
    e = download(LOD1_URL, lod1_zip)
    dirs = extract_lod1(lod1_zip, OUT / "lod1")
    print(f"LOD1: {e['bytes']:,} bytes, {len(dirs)} districts -> {OUT / 'lod1'}")

    sd_zip = OUT / "Stadsdelar.zip"
    e = download(STADSDELAR_URL, sd_zip)
    extract_flat(sd_zip, OUT / "stadsdelar")
    print(f"Stadsdelar: {e['bytes']:,} bytes -> {OUT / 'stadsdelar'}")

    if not args.skip_stadskarta:
        paths = fetch_stadskarta(OUT / "stadskarta")
        total = sum(p.stat().st_size for p in paths)
        print(f"Stadskarta: {len(paths)} files, {total:,} bytes -> {OUT / 'stadskarta'}")


if __name__ == "__main__":
    main(sys.argv[1:])
