"""A tiny COPC file (LAZ 1.4 organised as an octree), written by hand for the laser tests: laspy reads COPC but
cannot write it, and no test may download Lantmäteriet's tiles.

Layout (the COPC 1.0 specification): the 375-byte LAS 1.4 header, the COPC info VLR first and the LASzip VLR, the
point data (an 8-byte chunk-table offset, then one LAZ chunk per octree node, point format 6), the chunk table, and
the hierarchy as an EVLR at the end. The root node (level 0) holds every fourth point and the eight level-1 nodes the
rest, by octant, so a query over one corner reads the root and one child only.
"""
import io
import struct

import lazrs
import laspy
import numpy as np

SCALE = 0.01


def _vlr(user: str, record: int, data: bytes, description: str = "") -> bytes:
    return (struct.pack("<H16sHH32s", 0, user.encode(), record, len(data), description.encode()) + data)


def _evlr(user: str, record: int, data: bytes) -> bytes:
    return struct.pack("<H16sHQ32s", 0, user.encode(), record, len(data), b"") + data


def write_copc(points: dict, center, halfsize: float) -> bytes:
    """The bytes of a COPC file holding `points` ({x, y, z, cls, rn, nr} arrays, in the file's CRS) in an octree of
    root `center` (x, y, z) and `halfsize`."""
    x, y, z = (np.asarray(points[k], dtype=np.float64) for k in ("x", "y", "z"))
    n = len(x)
    cx, cy, cz = center
    hdr = laspy.LasHeader(point_format=6, version="1.4")
    hdr.scales = np.array([SCALE] * 3)
    hdr.offsets = np.array([float(np.floor(cx)), float(np.floor(cy)), 0.0])
    rec = laspy.ScaleAwarePointRecord.zeros(n, header=hdr)
    rec.x, rec.y, rec.z = x, y, z
    rec.classification = np.asarray(points["cls"], dtype=np.uint8)
    rec.return_number = np.asarray(points["rn"], dtype=np.uint8)
    rec.number_of_returns = np.asarray(points["nr"], dtype=np.uint8)
    arr = rec.array

    # Nodes: the root takes every fourth point, the eight children the rest by octant
    idx = np.arange(n)
    nodes = [((0, 0, 0, 0), idx[idx % 4 == 0])]
    rest = idx[idx % 4 != 0]
    ox, oy, oz = (x[rest] >= cx).astype(int), (y[rest] >= cy).astype(int), (z[rest] >= cz).astype(int)
    for kx in (0, 1):
        for ky in (0, 1):
            for kz in (0, 1):
                sel = rest[(ox == kx) & (oy == ky) & (oz == kz)]
                if len(sel):
                    nodes.append(((1, kx, ky, kz), sel))

    vlr = lazrs.LazVlr.new_for_compression(6, 0, True)
    vlrs_len = 2 * 54 + 160 + len(vlr.record_data())
    point_start = 375 + vlrs_len
    buf = io.BytesIO()
    comp = lazrs.LasZipCompressor(buf, vlr)
    entries, at = [], 8
    for key, sel in nodes:
        comp.compress_many(arr[sel].tobytes())
        comp.finish_current_chunk()
        entries.append((key, point_start + at, buf.tell() - at, len(sel)))
        at = buf.tell()
    comp.done()
    point_data = buf.getvalue()

    hierarchy = b"".join(struct.pack("<iiiiQii", *key, off, size, count) for key, off, size, count in entries)
    evlr_start = point_start + len(point_data)
    root_hier_offset = evlr_start + 60
    info = struct.pack("<5d2Q2d11Q", cx, cy, cz, halfsize, halfsize / 64, root_hier_offset, len(hierarchy),
                       0.0, 0.0, *([0] * 11))
    vlrs = _vlr("copc", 1, info, "copc info") + _vlr("laszip encoded", 22204, vlr.record_data())
    assert len(vlrs) == vlrs_len

    mins = [float(v.min()) if n else 0.0 for v in (x, y, z)]
    maxs = [float(v.max()) if n else 0.0 for v in (x, y, z)]
    head = bytearray(375)
    struct.pack_into("<4sHH16sBB32s32sHHHIIBHI5I", head, 0, b"LASF", 0, 16, b"\0" * 16, 1, 4, b"", b"copc_fixture",
                     1, 2026, 375, point_start, 2, 6 | 0x80, 30, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<3d3d6d", head, 131, *hdr.scales, *hdr.offsets, maxs[0], mins[0], maxs[1], mins[1], maxs[2],
                     mins[2])
    struct.pack_into("<QQIQ15Q", head, 227, 0, evlr_start, 1, n, *([0] * 15))
    return bytes(head) + vlrs + point_data + _evlr("copc", 1000, hierarchy)
