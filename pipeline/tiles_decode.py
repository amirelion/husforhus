"""Python port of the worker's tile parser, for tests and s99_validate.

Mirrors `parse()` in web/tile.js (upstream kept it in web/worker.js): every section starts on a 4-byte boundary.
"""
import struct

import numpy as np

MAGIC = 0x31484648  # 'HFH1' read as a little-endian u32
HEADER = struct.Struct("<5I2f")  # magic, nB, nP, nR, nV, originX, originZ (28 bytes)


def parse(buf: bytes | memoryview, offset: int = 0) -> dict:
    """Decode one tile starting at `offset`. Arrays are read-only views into `buf`."""
    magic, nB, nP, nR, nV, ox, oz = HEADER.unpack_from(buf, offset)
    if magic != MAGIC:
        raise ValueError(f"bad tile magic {magic:#010x} at offset {offset}")
    o = offset + HEADER.size

    def take(dtype: str, n: int) -> np.ndarray:
        nonlocal o
        dt = np.dtype(dtype)
        a = np.frombuffer(buf, dtype=dt, count=n, offset=o)
        o += -(-n * dt.itemsize // 4) * 4
        return a

    t = {"nB": nB, "nP": nP, "nR": nR, "nV": nV, "origin": (ox, oz)}
    t["gid"] = take("<u4", nB)
    t["year"] = take("<i2", nB)
    t["yflag"] = take("u1", nB)
    t["period"] = take("u1", nB)
    t["floors"] = take("u1", nB)
    t["ground"] = take("<i2", nB)
    t["lay0"] = take("<u4", nB)
    t["lay1"] = take("<u4", nB)
    t["partStart"] = take("<u4", nB + 1)
    t["height"] = take("<f4", nP)
    t["ringStart"] = take("<u4", nP + 1)
    t["vertStart"] = take("<u4", nR + 1)
    t["hole"] = take("u1", nR)
    t["xz"] = take("<i2", 2 * nV).reshape(-1, 2)
    t["end"] = o
    return t


def rings(t: dict, b: int) -> list[tuple[np.ndarray, int]]:
    """Rings of building index `b` (not gid) in local metres (x east, z south), with their hole flag: every part's."""
    out = []
    ox, oz = t["origin"]
    for p in range(t["partStart"][b], t["partStart"][b + 1]):
        for r in range(t["ringStart"][p], t["ringStart"][p + 1]):
            s, e = t["vertStart"][r], t["vertStart"][r + 1]
            xz = t["xz"][s:e].astype(np.float64) / 10.0 + (ox, oz)
            out.append((xz, int(t["hole"][r])))
    return out


def parts(t: dict, b: int) -> list[tuple[float, list[tuple[np.ndarray, int]]]]:
    """(height in metres, rings in local metres with their hole flag) for each part of building index `b`: the
    footprint first, then any laser tower parts (s03_tiles.tower_parts)."""
    out = []
    ox, oz = t["origin"]
    for p in range(t["partStart"][b], t["partStart"][b + 1]):
        rs = []
        for r in range(t["ringStart"][p], t["ringStart"][p + 1]):
            s, e = t["vertStart"][r], t["vertStart"][r + 1]
            rs.append((t["xz"][s:e].astype(np.float64) / 10.0 + (ox, oz), int(t["hole"][r])))
        out.append((float(t["height"][p]), rs))
    return out
