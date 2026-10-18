"""Readers' reports as data (pipeline/contributions.py): the table, resolving a report to a footprint, each kind, the
refusals and the privacy check."""
import hashlib
import struct
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from pipeline import codes, contributions as C, s02_years, s03_tiles, s99_validate
from tests import synth
from tests.test_s02_years import buildings as years_buildings
from tests.test_s02_years import no_raa, raa, rec, sq

HEADER = ",".join(C.COLUMNS) + "\n"


def row(**o):
    r = {"ref": "HFH-12", "uuid": "u0", "kind": "year", "value": "1938", "public_note": "The permit is dated 1938.",
         "replaces_register": "no", "issue_url": "", "photo": ""}
    r.update(o)
    return r


def table(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=C.COLUMNS)


def write_csv(tmp_path: Path, *rows) -> Path:
    p = tmp_path / "contributions.csv"
    C.write(list(rows), p)
    return p


def test_the_seeded_table_is_its_header_only():
    assert C.PATH.read_text(encoding="utf-8") == HEADER
    assert C.read().empty


def test_read_refuses_malformed_rows(tmp_path):
    assert len(C.read(write_csv(tmp_path, row(), row(ref="HFH-13", kind="none", value="")))) == 2
    for bad in (row(ref="12"), row(kind="colour"), row(value="38"), row(value="1939-1938"), row(public_note=""),
                row(public_note="x" * 201), row(replaces_register="maybe"), row(kind="name", value="X", replaces_register="yes"),
                row(issue_url="https://example.org/1"), row(kind="name", value="x" * 121), row(kind="none", value="1938"),
                row(kind="photo", value="A. Reader"), row(photo="0123456789abcdef-500.jpg")):
        with pytest.raises(ValueError):
            C.read(write_csv(tmp_path, bad))
    with pytest.raises(ValueError, match="repeated"):
        C.read(write_csv(tmp_path, row(), row()))


@pytest.mark.parametrize("text", ["write to anna@example.org", "call 070-123 45 67", "+46 8 123 456 78"])
def test_no_email_or_phone_like_text_in_a_note_or_value(tmp_path, text):
    assert C.personal(text)
    for bad in (row(public_note=text), row(kind="name", value=text)):
        with pytest.raises(ValueError, match="email-like or phone-like"):
            C.read(write_csv(tmp_path, bad))
    assert not C.personal("Built 1938-1939, see the permit (BN 1938/412).")


# ---- resolving a D1 row to a footprint (pull)

def d1(**o):
    r = {"id": 1, "report_id": 12, "kind": "year", "value": "1938", "public_note": "The permit is dated 1938.",
         "replaces_register": 0, "gid": 1, "data_version": "v20261017", "x": 20.0, "z": 0.0, "issue_url": None}
    r.update(o)
    return r


def test_resolve_by_gid_in_the_current_version_and_by_point_in_another():
    b = synth.buildings(3)                      # 10 m squares centred at x = 0, 20, 40
    rows, refused = C.resolve([d1()], b, "v20261017")
    assert refused == [] and rows[0]["uuid"] == b.uuid[1] and rows[0]["ref"] == "HFH-12"
    rows, refused = C.resolve([d1(gid=0, x=40.0, data_version="v20261001")], b, "v20261017")   # renumbered: the point wins
    assert refused == [] and rows[0]["uuid"] == b.uuid[2]
    rows, _ = C.resolve([d1(x=None, z=None)], b, "v20261017")    # a ?q= link has no point: the gid alone
    assert rows[0]["uuid"] == b.uuid[1]
    assert rows[0]["replaces_register"] == "no" and rows[0]["issue_url"] == "" and rows[0]["photo"] == ""


def test_resolve_refuses_a_gid_and_point_that_disagree_or_a_point_in_no_footprint():
    b = synth.buildings(3)
    _, refused = C.resolve([d1(gid=0)], b, "v20261017")
    assert "disagree" in refused[0]
    _, refused = C.resolve([d1(x=10.0, data_version="v20260101")], b, "v20261017")   # between two squares
    assert "in no footprint" in refused[0]
    _, refused = C.resolve([d1(x=None, z=None, data_version="v20260101")], b, "v20261017")
    assert "in no footprint" in refused[0]
    _, refused = C.resolve([d1(public_note="mail me at a@example.org")], b, "v20261017")
    assert "email-like" in refused[0]


def test_a_point_just_outside_its_building_still_finds_it_but_never_a_guess_between_two():
    b = synth.buildings(3)                      # 10 m squares centred at x = 0, 20, 40
    rows, refused = C.resolve([d1(z=6.0, data_version="v20260101")], b, "v20261017")   # 1 m past gid 1's edge
    assert refused == [] and rows[0]["uuid"] == b.uuid[1]
    rows, refused = C.resolve([d1(z=6.0)], b, "v20261017")                              # same version: gid 1 agrees
    assert refused == [] and rows[0]["uuid"] == b.uuid[1]
    _, refused = C.resolve([d1(z=30.0, data_version="v20260101")], b, "v20261017")     # 25 m off: nothing near
    assert "in no footprint" in refused[0]


def test_a_large_readers_photo_is_shrunk_and_re_encoded_without_its_metadata(tmp_path):
    from io import BytesIO

    from PIL import Image
    rng = np.random.default_rng(1)
    im = Image.fromarray(rng.integers(0, 255, (1600, 2400, 3), dtype=np.uint8))
    exif = Image.Exif()
    exif[0x010F] = "SomeCamera"
    src = tmp_path / "big.jpg"
    im.save(src, "JPEG", quality=95, exif=exif)
    assert src.stat().st_size > C.city.WIKI["photo_bytes"]
    key = C.place_photo(src, tmp_path / "photos")
    out = (tmp_path / "photos" / key).read_bytes()
    assert C.image_size(out) == (1000, 667) and key.endswith("-1000.jpg")
    assert len(out) <= C.city.WIKI["photo_bytes"]
    assert not Image.open(BytesIO(out)).getexif()


def jpeg(w=640, h=480) -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + b"\xff\xdb\x00\x04\x00\x00" + sof + b"\xff\xda\x00\x02\xff\xd9"


def test_a_photo_is_copied_under_s06s_kind_of_key(tmp_path):
    src = tmp_path / "r2.jpg"
    src.write_bytes(jpeg(800, 600))
    assert C.image_size(src.read_bytes()) == (800, 600)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 300, 200)
    assert C.image_size(png) == (300, 200)
    key = C.place_photo(src, tmp_path / "photos")
    assert key == f"{hashlib.sha1(src.read_bytes()).hexdigest()[:16]}-800.jpg"
    assert (tmp_path / "photos" / key).read_bytes() == src.read_bytes()
    assert C.PHOTO_KEY.fullmatch(key)


# ---- year (s02_years)

def reader(b, *rows):
    return C.reader_years(table(*rows), b)


def years_of(b, r, rows, **kw):
    y, report = s02_years.assign_years(b, r, [], estimates=False, reader=reader(b, *rows), **kw)
    return y.set_index("gid"), report


def test_a_reader_year_fills_an_unknown_building_as_its_own_tier():
    b = years_buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)))
    y, report = years_of(b, no_raa(), [row(uuid="u1", value="1938-1939")])
    assert (y.ysrc[1], y.yflag[1], y.year[1], y.year_from[1], y.year_to[1]) == (codes.SRC_READER, codes.RANGE, 1939, 1938, 1939)
    assert y.ysrc[0] == codes.SRC_NONE and report["reader"] == 1
    assert report["accuracy"]["tested"] == 1 and report["accuracy"]["result"]["unknown"] == 1


def test_a_reader_year_fills_an_area_year_and_replaces_a_register_year_only_when_asked():
    area = rec("area", sq(0, size=500, dx=-10, dy=-10), 1880, 1890, typ="Område")
    reg = rec("reg", sq(1), 1900, 1900, regid="u1")
    b = years_buildings(("u0", "Flerbostadshus", sq(0)), ("u1", "Flerbostadshus", sq(1)))
    y, _ = years_of(b, raa(area, reg), [row(uuid="u0")])
    assert (y.ysrc[0], y.year[0], y.yflag[0]) == (codes.SRC_READER, 1938, codes.EXACT)
    with pytest.raises(C.Refused, match="replaces_register"):
        years_of(b, raa(area, reg), [row(uuid="u1")])
    y, _ = years_of(b, raa(area, reg), [row(uuid="u1", replaces_register="yes")])
    assert (y.ysrc[1], y.year[1]) == (codes.SRC_READER, 1938)


def test_a_reader_year_never_replaces_a_curated_one_or_dates_a_takedown():
    b = years_buildings(("u0", "Flerbostadshus", sq(0)))
    with pytest.raises(C.Refused, match="withheld"):
        years_of(b, no_raa(), [row(uuid="u0")], exclude={0})
    rows = reader(b, row(uuid="u0", replaces_register="yes"))
    ysrc = np.array([codes.SRC_CURATED])
    with pytest.raises(C.Refused, match="hand-checked"):
        C.apply_years(rows, pd.Series([0], index=[0]), np.zeros(1), np.zeros(1), np.zeros(1), ysrc, np.zeros(1))


def test_a_private_house_with_a_reader_year_shows_its_decade():
    b = years_buildings(("u0", "Enbostadshus", sq(0)))
    y, _ = years_of(b, no_raa(), [row(uuid="u0", value="1938")])
    assert (y.ysrc[0], y.private[0], y.year[0], y.year_to[0]) == (codes.SRC_READER, True, 1930, 1939)


def test_a_uuid_on_no_footprint_or_on_two_is_refused():
    b = years_buildings(("u0", "Flerbostadshus", sq(0)), ("u0", "Flerbostadshus", sq(1)))
    with pytest.raises(C.Refused, match="2 footprints"):
        reader(b, row(uuid="u0"))
    with pytest.raises(C.Refused, match="0 footprints"):
        reader(b, row(uuid="gone"))


# ---- main_address, name, photo (s03_tiles)

def frame(private=(False, False, False), ysrc=(codes.SRC_NONE,) * 3):
    df = pd.DataFrame({"gid": [0, 1, 2], "uuid": ["u0", "u1", "u2"], "ysrc": list(ysrc),
                       "private": list(private), "kategori": ["Flerbostadshus"] * 3})
    return df, s03_tiles.hidden(df)


def shards_with(cards: dict) -> list[dict]:
    shards = [{} for _ in range(s03_tiles.N_CARD_SHARDS)]
    for g, c in cards.items():
        shards[g % s03_tiles.N_CARD_SHARDS][str(g)] = dict(c)
    return shards


def test_main_address_must_be_one_the_building_has():
    df, hide = frame()
    shards = shards_with({1: {"addr": "Stortorget 2", "addrn": 2}})
    n = C.apply_cards(shards, df, table(row(uuid="u1", kind="main_address", value="Källargränd 1")), hide,
                      {1: ["Stortorget 2", "Källargränd 1"]})
    assert n == 1 and shards[1]["1"] == {"addr": "Källargränd 1", "addrn": 2}
    with pytest.raises(C.Refused, match="not among"):
        C.apply_cards(shards, df, table(row(uuid="u1", kind="main_address", value="Elsewhere 3")), hide, {1: ["Stortorget 2"]})


def test_a_name_but_never_on_a_private_house():
    df, hide = frame(private=(False, True, False))
    shards = shards_with({0: {"name": "Old", "en": "Old EN"}})
    C.apply_cards(shards, df, table(row(uuid="u0", kind="name", value="Börshuset")), hide, {})
    assert shards[0]["0"] == {"name": "Börshuset"}
    with pytest.raises(C.Refused, match="private"):
        C.apply_cards(shards, df, table(row(uuid="u1", kind="name", value="Villa X")), hide, {})


def test_a_photo_credited_as_a_readers_but_never_on_a_private_house(tmp_path):
    df, hide = frame(private=(False, True, False))
    key = C.place_photo(_photo(tmp_path), tmp_path / "photos")
    shards = shards_with({})
    C.apply_cards(shards, df, table(row(uuid="u2", kind="photo", value="A. Reader", photo=key)), hide, {}, tmp_path / "photos")
    assert shards[2]["2"]["photo"] == {"key": key, "w": 640, "h": 480, "by": "A. Reader", "lic": "CC BY 4.0",
                                       "lu": "https://creativecommons.org/licenses/by/4.0/", "rd": "HFH-12"}
    assert set(shards[2]["2"]["photo"]) <= set(s03_tiles.PHOTO_FIELDS)
    with pytest.raises(C.Refused, match="private"):
        C.apply_cards(shards, df, table(row(uuid="u1", kind="photo", value="A. Reader", photo=key)), hide, {}, tmp_path / "photos")


def _photo(tmp_path):
    p = tmp_path / "in.jpg"
    p.write_bytes(jpeg())
    return p


def test_a_reader_year_puts_its_reference_and_note_on_the_card_but_not_on_a_private_houses():
    df, hide = frame(private=(False, True, False), ysrc=(codes.SRC_READER, codes.SRC_READER, codes.SRC_NONE))
    shards = shards_with({})
    url = "https://github.com/amirelion/husforhus/issues/9"
    n = C.apply_cards(shards, df, table(row(uuid="u0", issue_url=url), row(ref="HFH-13", uuid="u1"),
                                        row(ref="HFH-14", uuid="u2", kind="none", value="")), hide, {})
    assert n == 2                                                            # "none" changes nothing
    assert shards[0]["0"] == {"yrd": {"ref": "HFH-12", "note": "The permit is dated 1938.", "url": url}}
    assert "1" not in shards[1] and "2" not in shards[2]
    with pytest.raises(C.Refused, match="s02_years"):
        C.apply_cards(shards_with({}), df, table(row(uuid="u2")), hide, {})


# ---- s99_validate

def test_s99_every_row_resolves_to_exactly_one_footprint(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    synth.buildings(2).to_parquet(data / "buildings.parquet")
    b = gpd.read_parquet(data / "buildings.parquet")
    ok = write_csv(tmp_path, row(uuid=b.uuid[0]))
    assert s99_validate.check_contributions(data, ok) == []
    assert "0 footprints" in s99_validate.check_contributions(data, write_csv(tmp_path, row(uuid="nowhere")))[0]
    assert "email-like" in s99_validate.check_contributions(data, write_csv(tmp_path, row(public_note="x@example.org")))[0]
    assert s99_validate.check_contributions(data, C.PATH) == []


def test_s99_the_cards_reader_line():
    rec_ = {"ysrc": codes.SRC_READER}
    good = {"ref": "HFH-1", "note": "Permit 1938.", "url": "https://github.com/amirelion/husforhus/issues/1"}
    assert s99_validate.check_reader_line("c", good, rec_, False) == []
    assert s99_validate.check_reader_line("c", good, rec_, True)
    assert s99_validate.check_reader_line("c", good, {"ysrc": codes.SRC_RAA}, False)
    assert s99_validate.check_reader_line("c", {**good, "note": "ring 08-123 456 78"}, rec_, False)
    assert s99_validate.check_reader_line("c", {**good, "email": "x"}, rec_, False)
