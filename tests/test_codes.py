# tests/test_codes.py
"""pipeline.codes."""
from pipeline import codes


def test_yflag_codes():
    assert (codes.EXACT, codes.RANGE, codes.LONG, codes.AREA, codes.ESTIMATE, codes.PERIOD, codes.UNKNOWN) == (
        0, 1, 2, 3, 4, 6, 7)
    assert not hasattr(codes, "DECADE")  # 5 is retired; private houses use the years.parquet `private` column


def test_ysrc():
    assert (codes.SRC_NONE, codes.SRC_CURATED, codes.SRC_RAA, codes.SRC_RAA_AREA, codes.SRC_WIKIDATA,
            codes.SRC_ESTIMATE) == (0, 1, 2, 3, 4, 5)
    assert (codes.SRC_RAA_OLD, codes.SRC_OSM) == (6, 7)   # the old register and OpenStreetMap tiers


def test_fsrc_and_rating():
    assert (codes.FLOORS_OSM, codes.FLOORS_HEIGHT) == (0, 1)
    assert codes.RATING == {"Blått": 1, "Grönt": 2, "Gult": 3}


def test_protection_codes():
    # RAÄ's skyddstyp as the card's "Protected" row; an identified value with no legal force is none
    assert (codes.PROT_NONE, codes.PROT_STATE, codes.PROT_LISTED, codes.PROT_CHURCH) == (0, 1, 2, 3)
    assert codes.PROTECTION == {"Statligt byggnadsminne": 1, "Byggnadsminne": 2, "Kyrkligt kulturminne": 3}
    assert "Identifierat kulturvärde" not in codes.PROTECTION
