"""Snapshot RAÄ's OLD building-register file (CC0).

catalog.raa.se entry 207, "OLD Bebyggelse, kulturhistoriskt inventerad": one GeoPackage for all of Sweden
(about 76 MB, 99,329 points, layer byggnader_sverige_point) with the old register's Nybyggnad years, published only
"during a transition period". It dates about 818 Stockholm buildings that today's RAÄ data no longer does. The
file can disappear without notice, so a snapshot kept in data/raw/raa/ is the source of record: when the download
fails (a 404, a refused connection) and a snapshot exists, the step keeps it with a warning; without a snapshot it
warns too and s02_years runs without the raa_old tier.
"""
import argparse
import sys
from pathlib import Path

import requests

from pipeline.fetch import download

URL = "https://pub.raa.se/nedladdning/datauttag/bebyggelse/byggnader_kulthist_inv/byggnader_sverige.gpkg"
DEST = Path("data/raw/raa/byggnader_sverige.gpkg")
LAYER = "byggnader_sverige_point"


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(prog="s00_fetch_raa_old", description=__doc__.splitlines()[0]).parse_args([] if argv is None else argv)
    try:
        e = download(URL, DEST)
    except requests.RequestException as err:
        if DEST.exists():
            print(f"warning: {URL} failed ({err}); keeping the snapshot {DEST} (RAÄ publishes this file during a "
                  "transition period only)", file=sys.stderr)
        else:
            print(f"warning: {URL} failed ({err}) and there is no snapshot: s02_years runs without the raa_old tier",
                  file=sys.stderr)
        return
    print(f"RAÄ OLD register: {e['bytes']:,} bytes, last modified {e['last_modified']} -> {DEST}")


if __name__ == "__main__":
    main(sys.argv[1:])
