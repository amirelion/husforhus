# tests/test_io.py
"""pipeline.io: deterministic gzip and JSON writers, versioned output folders."""
import datetime
import gzip
import json
import os
import re

import pytest

from pipeline import io

FIXED_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"  # magic, deflate, no flags, mtime 0, XFL 2, OS unknown


def test_write_gz_is_deterministic(tmp_path):
    data = bytes(range(256)) * 1000
    a, b = tmp_path / "a.bin.gz", tmp_path / "sub" / "b.bin.gz"
    n = io.write_gz(a, data)
    io.write_gz(b, data)
    assert n == a.stat().st_size
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes()[:10] == FIXED_HEADER  # mtime field is zero and no OS byte from the build machine
    assert gzip.decompress(a.read_bytes()) == data


def test_write_gz_matches_python_gzip_apart_from_os_byte(tmp_path):
    data = b"Hus f\xc3\xb6r hus " * 999
    p = tmp_path / "x.gz"
    io.write_gz(p, data)
    ours, ref = p.read_bytes(), gzip.compress(data, 9, mtime=0)
    assert ours[:9] == ref[:9] and ours[10:] == ref[10:]


def test_write_gz_refuses_files_over_the_cap(tmp_path, monkeypatch):
    assert io.MAX_BYTES == 20 * 1024 * 1024
    monkeypatch.setattr(io, "MAX_BYTES", 100)
    with pytest.raises(ValueError, match="over the 20 MiB"):
        io.write_gz(tmp_path / "big.bin.gz", os.urandom(1000))
    assert not (tmp_path / "big.bin.gz").exists()


def test_write_json_sorted_compact_utf8(tmp_path):
    p = tmp_path / "x.json"
    n = io.write_json(p, {"b": 1, "a": {"ö": [1, 2.5], "c": None}, "name": "Hus för hus"})
    text = p.read_bytes().decode("utf-8")
    assert text == '{"a":{"c":null,"ö":[1,2.5]},"b":1,"name":"Hus för hus"}'
    assert n == len(text.encode("utf-8"))
    assert json.loads(text)["name"] == "Hus för hus"


def test_write_json_rejects_nan(tmp_path):
    with pytest.raises(ValueError):
        io.write_json(tmp_path / "x.json", {"x": float("nan")})


def test_version_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(io, "WEB_DATA", tmp_path / "web" / "data")
    d = io.version_dir("v20261014")
    assert d == tmp_path / "web" / "data" / "v20261014" and d.is_dir()
    today = io.version_dir()
    assert re.fullmatch(r"v\d{8}", today.name) and today.is_dir()
    assert today.name == datetime.date.today().strftime("v%Y%m%d")
    assert io.version_dir("v20261014-t1200").name == "v20261014-t1200"  # a side build (a tile comparison)
    for bad in ["2026-10-14", "v2026101", "v20261014-", "v20261014-T1200", "v20261014_t1200"]:
        with pytest.raises(ValueError):
            io.version_dir(bad)
