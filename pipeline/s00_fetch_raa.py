"""Fetch RAÄ Bebyggelseregistret, Stockholm county: 'Bebyggelse, kulturhistoriskt inventerad' (CC0 1.0).

One GeoPackage (about 21.6 MB, rebuilt nightly) with one table,
kulturhistoriskt_inventerad_bebyggelse_stockholm_polygon (EPSG:3006). s02_years keeps the records whose
kommunnamn names Stockholm, alone or in a border list such as 'Solna;Stockholm' (s02_years.in_stockholm).
"""
import argparse
import sys
from pathlib import Path

from pipeline.fetch import download

URL = ("https://pub.raa.se/nedladdning/datauttag/bebyggelse/kulturhistoriskt_inventerad_bebyggelse/"
       "kulturhistoriskt_inventerad_bebyggelse_stockholm.gpkg")
DEST = Path("data/raw/raa/kulturhistoriskt_inventerad_bebyggelse_stockholm.gpkg")
LAYER = "kulturhistoriskt_inventerad_bebyggelse_stockholm_polygon"


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args([] if argv is None else argv)
    e = download(URL, DEST)
    print(f"RAÄ: {e['bytes']:,} bytes, last modified {e['last_modified']} -> {DEST}")


if __name__ == "__main__":
    main(sys.argv[1:])
