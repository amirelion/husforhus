# pipeline/io.py
"""Writers for web/data (contract C6). Output is byte-for-byte reproducible: gzip with a fixed header, sorted JSON."""
import datetime
import json
import re
import struct
import zlib
from pathlib import Path

WEB_DATA = Path("web/data")
MAX_BYTES = 20 * 1024 * 1024  # Cloudflare static assets: every file ≤ 20 MiB (our cap; the platform allows 25)
# gzip member header: magic, deflate, no flags, mtime 0, XFL 2 (best compression), OS 255 (unknown).
# Python 3.12's gzip.compress copies zlib's OS byte (19 on macOS, 3 on Linux), so we write the header ourselves.
GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"


def gzip_bytes(data: bytes) -> bytes:
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate, default memLevel, as gzip.compress
    body = deflate.compress(data) + deflate.flush()
    return GZIP_HEADER + body + struct.pack("<II", zlib.crc32(data), len(data) & 0xFFFFFFFF)


def _write(path: Path, blob: bytes) -> int:
    if len(blob) > MAX_BYTES:
        raise ValueError(f"{path}: {len(blob):,} bytes is over the 20 MiB per-file cap")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return len(blob)


def write_gz(path: Path, data: bytes) -> int:
    """Gzip data (level 9, mtime 0, fixed header) to path; returns the bytes written."""
    return _write(path, gzip_bytes(data))


def write_json(path: Path, obj) -> int:
    """Compact UTF-8 JSON with sorted keys; NaN and Infinity are refused. Returns the bytes written."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return _write(path, text.encode("utf-8"))


def version_dir(version: str | None = None) -> Path:
    """web/data/<version>/, created if needed. A version is vYYYYMMDD, optionally with -<tag> ([0-9a-z]+) for a
    side build such as v20261014-t1200; the default is today's date as vYYYYMMDD."""
    version = version or datetime.date.today().strftime("v%Y%m%d")
    if not re.fullmatch(r"v\d{8}(-[0-9a-z]+)?", version):
        raise ValueError(f"version must look like vYYYYMMDD or vYYYYMMDD-tag, not {version!r}")
    path = WEB_DATA / version
    path.mkdir(parents=True, exist_ok=True)
    return path
