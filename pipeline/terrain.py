"""The terrain grid (spec §4.1 "Terrain (D9)", §3.2 s04_base; Plan 3, contract C15): pure functions shared by
s02_terrain, s04_base and s99_validate, and mirrored in web/terrain.js. No file I/O here.

Everything works in the viewer's local frame (metres from city.ORIGIN, x east, z south). A grid's node (i, j) sits at
(x0 + i*cell, z0 + j*cell), on multiples of cell, so 20 m nodes line up with the 1200 m building tiles. Cell (i, j) is
the square between nodes (i, j) and (i+1, j+1). Heights are true metres in RH 2000; the viewer multiplies them by the
relief (uRelief).

terrain.bin.gz (contract C16; little-endian, every section starts on a 4-byte boundary):
  header (64 bytes) u32 magic 'HFT1', u32 version 1, f32 x0, z0, cell, u32 nx, nz, f32 waterZ, u32 nLevels, nEdge,
                    ringBytes, shoreBytes, nShoreVerts, u32 source (1 the City's contours, 2 Lantmäteriet's model),
                    2 x u32 reserved (0)
  i16 levels_dm[nLevels]   each water polygon's level, in water.bin.gz order
  u8  hLo[nx*nz], hHi[nx*nz]   the heights in decimetres after the 2D predictor h - (left + up - upleft), as the
                               low and high bytes of the int16 residual (row-major, j then i)
  u8  cut[nx*nz]           the terrace cut in decimetres (0..255): how far the viewer may lower each node
  u8  cls[(nx-1)*(nz-1)]   per cell: 0 outside the domain, 1 all land, 2 part land (an edge cell), 3 water in the domain
  u8  rings[ringBytes]     per edge cell, in cls order: u8 nPoly; per polygon u8 nRing; per ring u16 nVert, then nVert
                           x (u8 u, u8 v), cell-local (0 and 255 are the cell's sides); a polygon's first ring is its
                           exterior
  u8  shore[shoreBytes]    one bit per water.bin.gz vertex (bit k & 7 of byte k >> 3): the segment from that vertex
                           to the next in its ring is a shore, where the viewer stands a quay wall
"""
import struct
from dataclasses import asdict, dataclass

import numpy as np
import shapely
from rasterio.features import rasterize
from rasterio.transform import Affine
from scipy import ndimage

from . import city

MAGIC = 0x31544648  # 'HFT1' read as a little-endian u32
VERSION = 1
HEADER = struct.Struct("<2I3f2If5I3I")
assert HEADER.size == 64
RING_SCALE = 255          # cell-local ring coordinates run 0..RING_SCALE across a cell
OUTSIDE, LAND, EDGE, WATER = 0, 1, 2, 3
SOURCES = {"contours": 1, "dtm": 2}   # the header's source field: s99 checks it against stockholm.json
MAX_CUT = 25.5            # metres: the cut ships as u8 decimetres


@dataclass(frozen=True)
class Grid:
    x0: float
    z0: float
    cell: float
    nx: int
    nz: int

    def node_xz(self) -> tuple[np.ndarray, np.ndarray]:
        """Local x and z of every node, each shaped (nz, nx)."""
        return np.meshgrid(self.x0 + np.arange(self.nx) * self.cell, self.z0 + np.arange(self.nz) * self.cell)

    def node_transform(self) -> Affine:
        """Pixels centred on the nodes (rows go south, +z)."""
        return Affine(self.cell, 0, self.x0 - self.cell / 2, 0, self.cell, self.z0 - self.cell / 2)

    def cell_transform(self) -> Affine:
        """Pixels that are the cells, (nz - 1, nx - 1) of them."""
        return Affine(self.cell, 0, self.x0, 0, self.cell, self.z0)

    def sub_transform(self, sub: int) -> Affine:
        """sub x sub pixels per node, covering node ± cell/2."""
        return Affine(self.cell / sub, 0, self.x0 - self.cell / 2, 0, self.cell / sub, self.z0 - self.cell / 2)

    def to_dict(self) -> dict:
        return asdict(self)


def grid_for(bounds, cell: float) -> Grid:
    """The grid over local bounds (minx, minz, maxx, maxz) plus one cell on every side, nodes on multiples of cell."""
    minx, minz, maxx, maxz = bounds
    x0 = float(np.floor(minx / cell) * cell - cell)
    z0 = float(np.floor(minz / cell) * cell - cell)
    nx = int(np.ceil((maxx + cell - x0) / cell)) + 1
    nz = int(np.ceil((maxz + cell - z0) / cell)) + 1
    return Grid(x0, z0, float(cell), nx, nz)


def to_local(geom):
    """An EPSG:3011 geometry in the local frame (x = E - E0, z = -(N - N0)). The z flip mirrors ring orientation,
    which nothing here depends on."""
    e0, n0 = city.ORIGIN
    return shapely.transform(geom, lambda c: np.c_[c[:, 0] - e0, n0 - c[:, 1]])


def burn(geoms, values, shape, transform, *, fill=0, dtype="float32", all_touched=False, smallest_wins=False):
    """rasterio's rasterize with one value per geometry. smallest_wins: where geometries overlap, the smallest value
    stays (they are drawn largest first, and each one overwrites)."""
    pairs = [(g, v) for g, v in zip(geoms, values) if g is not None and not g.is_empty]
    if smallest_wins:
        pairs.sort(key=lambda p: -float(p[1]))
    if not pairs:
        return np.full(shape, fill, dtype=dtype)
    return rasterize(pairs, out_shape=shape, transform=transform, fill=fill, dtype=dtype, all_touched=all_touched)


def node_means(values: np.ndarray, mask: np.ndarray, sub: int) -> tuple[np.ndarray, np.ndarray]:
    """(mean, land): per node, the mean of the finite sub-samples under `mask` in its footprint (NaN where there is
    none), and whether any sub-sample of the footprint is under `mask` at all."""
    nz, nx = values.shape[0] // sub, values.shape[1] // sub
    ok = mask & np.isfinite(values)
    total = np.where(ok, values, 0.0).reshape(nz, sub, nx, sub).sum(axis=(1, 3))
    count = ok.reshape(nz, sub, nx, sub).sum(axis=(1, 3))
    land = mask.reshape(nz, sub, nx, sub).any(axis=(1, 3))
    mean = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    return mean.astype(np.float32), land


def nearest_fill(h: np.ndarray, have: np.ndarray, where: np.ndarray) -> np.ndarray:
    """h with every node in `where` set to the value of the nearest node in `have` (Euclidean, in nodes)."""
    out = h.copy()
    if not have.any() or not where.any():
        return out
    _, (ii, jj) = ndimage.distance_transform_edt(~have, return_indices=True)
    out[where] = h[ii[where], jj[where]]
    return out


def burn_in(h: np.ndarray, land: np.ndarray, rings: int) -> tuple[np.ndarray, np.ndarray]:
    """Land nodes without a value take the nearest valued land node; nodes within `rings` (chessboard) of land that
    are not land take the nearest land node's value, so bilinear sampling keeps bank heights up to the shore.
    Returns (h, burnt) with every other node NaN."""
    h = h.copy()
    valued = land & np.isfinite(h)
    h = nearest_fill(h, valued, land & ~valued)
    d = ndimage.distance_transform_cdt(~land, metric="chessboard") if land.any() else np.full(land.shape, 10 ** 6)
    burnt = ~land & (d <= rings)
    h = nearest_fill(h, land, burnt)
    h[~(land | burnt)] = np.nan
    return h, burnt


def water_systems(water, bridge_m: float) -> np.ndarray:
    """A system id per water polygon: pieces closer than 2 * bridge_m (a bridge, a lock) are one system."""
    if not water:
        return np.zeros(0, dtype=np.int64)
    merged = shapely.union_all([p.buffer(bridge_m) for p in water])
    parts = list(getattr(merged, "geoms", [merged]))
    tree = shapely.STRtree(parts)
    ids = []
    for p in water:
        hit = tree.query(p.representative_point(), predicate="within")
        ids.append(int(hit.min()) if len(hit) else -1)
    return np.array(ids, dtype=np.int64)


def lake_levels(ring_p05: np.ndarray, inner_median: np.ndarray, systems: np.ndarray, *, water_z: float,
                sea_max: float, offset: float) -> np.ndarray:
    """One level per water polygon (spec §3.2's single water level, clarified by Plan 3): every polygon of a system
    whose lowest shore reads under sea_max is the sea or Mälaren, at water_z. Every other polygon keeps its own level
    (never its system's: Flaten would come out 2 m low beside Magelungen): the median of the terrain inside it when the
    source gives one (the laser model's water is flat), else its shore's 5th percentile minus offset; a polygon with
    neither takes its system's lowest shore minus offset. A system with no shore sample at all gives each polygon the
    terrain inside it where there is one, else water_z. A level never goes below water_z."""
    n = len(ring_p05)
    levels = np.full(n, water_z, dtype=np.float64)
    for s in np.unique(systems):
        idx = np.flatnonzero(systems == s)
        shores = ring_p05[idx]
        low = np.nanmin(shores) if np.isfinite(shores).any() else np.nan
        if not np.isfinite(low):
            inner = inner_median[idx]
            levels[idx] = np.where(np.isfinite(inner), inner, water_z)
            continue
        if low < sea_max:
            continue
        for k in idx:
            if np.isfinite(inner_median[k]):
                levels[k] = inner_median[k]
            elif np.isfinite(ring_p05[k]):
                levels[k] = ring_p05[k] - offset
            else:
                levels[k] = low - offset
    return np.maximum(levels, water_z)


def bilinear(grid: Grid, field: np.ndarray, x, z) -> np.ndarray:
    """field (nz, nx) sampled at local (x, z) like the viewer's hEff: node indices clamped to the grid."""
    gx = (np.asarray(x, dtype=np.float64) - grid.x0) / grid.cell
    gz = (np.asarray(z, dtype=np.float64) - grid.z0) / grid.cell
    fx, fz = np.floor(gx), np.floor(gz)
    tx, tz = gx - fx, gz - fz
    i0 = np.clip(fx.astype(np.int64), 0, grid.nx - 1)        # each of the four nodes is clamped on its own,
    j0 = np.clip(fz.astype(np.int64), 0, grid.nz - 1)        # as the shader's texelFetch and web/terrain.js do
    i1 = np.clip(fx.astype(np.int64) + 1, 0, grid.nx - 1)
    j1 = np.clip(fz.astype(np.int64) + 1, 0, grid.nz - 1)
    f = field.astype(np.float64)
    top = f[j0, i0] * (1 - tx) + f[j0, i1] * tx
    bottom = f[j1, i0] * (1 - tx) + f[j1, i1] * tx
    return top * (1 - tz) + bottom * tz


def outline_points(polys, step: float) -> tuple[np.ndarray, np.ndarray]:
    """(points (n, 2), owner) along every ring of each (local) polygon: its vertices and points at most step apart."""
    dense = shapely.segmentize(np.asarray(polys, dtype=object), step)
    coords, owner = shapely.get_coordinates(dense, return_index=True)
    return coords, owner


def outline_min(sample, polys, step: float = 5.0) -> np.ndarray:
    """Per footprint, the lowest terrain along its outline: the LOD1's MARK_Z is that point (spike, 2026-10-15:
    median MARK_Z - outline minimum is about -0.1 m on every slope; against the centroid it drifts with the slope).
    sample(xz) gives heights at local points: s02_terrain passes the source itself (the 5 m model or the TIN), never
    the 20 m grid, whose ±10 m means would misjudge every quay and cliff foot. NaN where the source has no value."""
    pts, owner = outline_points(polys, step)
    vals = np.asarray(sample(pts), dtype=np.float64)
    out = np.full(len(polys), np.inf)
    np.fmin.at(out, owner, vals)
    return np.where(np.isfinite(out), out, np.nan)


def fix_grounds(mark_z, height, tmin, fix_m: float, min_h: float = 2.0, max_h: float = 200.0):
    """(ground, height, fixed). A MARK_Z more than fix_m under the terrain's minimum along the outline is an error
    (most sit on the LOD1's 1 km sheet lines; the spike found 77% of the outliers too low): the ground becomes that
    minimum and the height TAK_Z - ground, so the roof stays where the City measured it. A MARK_Z above the terrain is
    left alone (a deck, a bridge, a yard built up over a slope: its skirts reach down to the ground), and so is a fix
    whose new height would leave min_h..max_h."""
    mark_z = np.asarray(mark_z, dtype=np.float64)
    height = np.asarray(height, dtype=np.float64)
    tmin = np.asarray(tmin, dtype=np.float64)
    roof = mark_z + height
    new_h = roof - tmin
    fixed = np.isfinite(tmin) & (tmin - mark_z > fix_m) & (new_h >= min_h) & (new_h <= max_h)
    return np.where(fixed, tmin, mark_z), np.where(fixed, new_h, height), fixed


def terrace_cut(grid: Grid, h: np.ndarray, polys, ground, up: float, max_cut: float) -> np.ndarray:
    """How far each node may be lowered so no building stands buried: every node of every cell a footprint touches
    is capped at the lowest such building's ground + up, never cut by more than max_cut (the spike's corner terrace).
    Returns the cut in metres, 0 where nothing is capped. A ground that is not finite is refused: it would wipe the
    caps of every cell it touches, its neighbours' included."""
    ground = np.asarray(ground, dtype=np.float64)
    if not np.isfinite(ground).all():
        raise ValueError("building grounds must be finite")
    ny, nx = grid.nz - 1, grid.nx - 1
    caps = burn(polys, ground, (ny, nx), grid.cell_transform(), fill=np.inf, dtype="float64", all_touched=True,
                smallest_wins=True)
    node = np.full((grid.nz, grid.nx), np.inf)
    for dj in (0, 1):
        for di in (0, 1):
            node[dj:dj + ny, di:di + nx] = np.minimum(node[dj:dj + ny, di:di + nx], caps)
    cut = np.where(np.isfinite(node), h - (node + up), 0.0)
    return np.clip(np.nan_to_num(cut, nan=0.0), 0.0, max_cut).astype(np.float32)


def burial(grid: Grid, h: np.ndarray, cut: np.ndarray, polys, ground, relief: float, step: float = 2.0) -> np.ndarray:
    """Per building, how far (scene metres, at `relief` with the full terrace) the drawn ground rises above its drawn
    base at the highest point of its outline: what the terrace could not cut away. s02_terrain counts the buildings
    buried by more than half their height (terrain.json `buried`)."""
    pts, owner = outline_points(polys, step)
    top = np.full(len(polys), -np.inf)
    np.maximum.at(top, owner, bilinear(grid, np.asarray(h, np.float64) - cut, pts[:, 0], pts[:, 1]))
    return relief * (top - np.asarray(ground, dtype=np.float64))


# ---------- the binary file (contract C16) ----------

def predict(h_dm: np.ndarray) -> np.ndarray:
    """The 2D predictor's residual, h - (left + up - upleft), in int16 arithmetic (wrapping)."""
    h = h_dm.astype(np.int32)
    p = np.zeros_like(h)
    p[:, 1:] += h[:, :-1]
    p[1:, :] += h[:-1, :]
    p[1:, 1:] -= h[:-1, :-1]
    return ((h - p) & 0xFFFF).astype(np.uint16).view(np.int16)


def unpredict(res: np.ndarray) -> np.ndarray:
    """Inverse of predict, row by row: h[j][i] = r + h[j][i-1] + h[j-1][i] - h[j-1][i-1], so each row is a running
    sum of r + up - upleft, wrapped to int16 like the encoder (the viewer does the same in one pass)."""
    nz, nx = res.shape
    h = np.zeros((nz, nx), dtype=np.int64)
    r = res.astype(np.int64)
    up = np.zeros(nx, dtype=np.int64)
    for j in range(nz):
        upleft = np.r_[0, up[:-1]]
        row = (np.cumsum(r[j] + up - upleft) + 32768) % 65536 - 32768
        h[j] = row
        up = row
    return h.astype(np.int16)


def quantise_ring(ring_xz: np.ndarray, cx: float, cz: float, cell: float) -> np.ndarray:
    """A ring in cell-local u8 coordinates, consecutive duplicates (and a closing duplicate) dropped."""
    q = np.clip(np.round((ring_xz - (cx, cz)) / cell * RING_SCALE), 0, RING_SCALE).astype(np.uint8)
    keep = np.r_[True, np.any(q[1:] != q[:-1], axis=1)]
    q = q[keep]
    if len(q) > 1 and np.array_equal(q[0], q[-1]):
        q = q[:-1]
    return q


def cell_rings(geom, cx: float, cz: float, cell: float) -> bytes:
    """One edge cell's land, as the ring stream C16 describes. Polygons and rings that collapse below 3 vertices
    when quantised are dropped."""
    polys = []
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        rings = []
        for k, ring in enumerate([p.exterior, *p.interiors]):
            q = quantise_ring(shapely.get_coordinates(ring)[:-1], cx, cz, cell)
            if len(q) >= 3:
                rings.append(q)
            elif k == 0:
                break
        else:
            if rings:
                polys.append(rings)
    out = bytearray([len(polys)])
    for rings in polys:
        out.append(len(rings))
        for q in rings:
            out += struct.pack("<H", len(q)) + q.tobytes()
    return bytes(out)


def _polygonal(g):
    """The polygons of an overlay result (lines and points along a cut are dropped), or None."""
    parts = [p for p in shapely.get_parts(g) if p.geom_type == "Polygon" and p.area > 0]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else shapely.MultiPolygon(parts)


def land_cells(grid: Grid, land) -> tuple[list, dict]:
    """Split local land over the cells by quadtree: (all-land blocks, {(j, i): land in that cell}) where the blocks
    are (j0, i0, j1, i1) ranges wholly covered. Each level clips the previous level's piece, so the work grows
    with the land's vertices times the depth, not with the number of cells."""
    full_blocks, parts = [], {}
    stack = [(0, 0, grid.nz - 1, grid.nx - 1, land)]
    c = grid.cell
    while stack:
        j0, i0, j1, i1, g = stack.pop()
        rect = shapely.box(grid.x0 + i0 * c, grid.z0 + j0 * c, grid.x0 + i1 * c, grid.z0 + j1 * c)
        piece = _polygonal(shapely.intersection(g, rect))
        if piece is None or piece.area < 0.01:
            continue
        if piece.area >= rect.area - 1e-3 * (j1 - j0) * (i1 - i0):
            full_blocks.append((j0, i0, j1, i1))
            continue
        if j1 - j0 == 1 and i1 - i0 == 1:
            parts[(j0, i0)] = piece
            continue
        jm, im = (j0 + j1) // 2, (i0 + i1) // 2
        for a, b, cc, d in ((j0, i0, jm, im), (j0, im, jm, i1), (jm, i0, j1, im), (jm, im, j1, i1)):
            if a < cc and b < d:
                stack.append((a, b, cc, d, piece))
    return full_blocks, parts


def classes_and_rings(grid: Grid, land, domain) -> tuple[np.ndarray, bytes, int]:
    """(cls (nz-1, nx-1) u8, ring stream, number of edge cells) for local land and domain geometries: a cell is all
    land, an edge cell (part land: its land goes into the ring stream, row-major), water in the domain, or outside
    it. An edge cell whose land quantises away is drawn as water."""
    ny, nx = grid.nz - 1, grid.nx - 1
    inside = burn([domain], [1], (ny, nx), grid.cell_transform(), dtype="uint8", all_touched=True).astype(bool)
    cls = np.where(inside, WATER, OUTSIDE).astype(np.uint8)
    blocks, parts = land_cells(grid, land)
    for j0, i0, j1, i1 in blocks:
        cls[j0:j1, i0:i1] = LAND
    stream, n_edge = bytearray(), 0
    for j, i in sorted(parts):
        blob = cell_rings(parts[(j, i)], grid.x0 + i * grid.cell, grid.z0 + j * grid.cell, grid.cell)
        if blob[0] == 0:
            continue
        cls[j, i] = EDGE
        stream += blob
        n_edge += 1
    return cls, bytes(stream), n_edge


def shore_bits(water_rings: list[list[np.ndarray]], domain_boundary, tol: float = 0.05) -> tuple[bytes, int]:
    """(bits, vertex count): per vertex of water.bin.gz's rings (local, in its order), 1 when the segment to the
    next vertex of its ring is a shore, not the domain's edge (where water is cut off and no wall belongs)."""
    mids = []
    for poly in water_rings:
        for ring in poly:
            nxt = np.roll(ring, -1, axis=0)
            mids.append((ring + nxt) / 2)
    if not mids:
        return b"", 0
    m = np.concatenate(mids).astype(np.float64)
    shapely.prepare(domain_boundary)
    on_edge = shapely.dwithin(domain_boundary, shapely.points(m), tol)
    bits = np.packbits(~on_edge, bitorder="little")
    return bits.tobytes(), len(m)


def _pad(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def pack(grid: Grid, h: np.ndarray, cut: np.ndarray, levels, water_z: float, cls: np.ndarray, rings: bytes,
         n_edge: int, shore: bytes, n_shore: int, source: str = "contours") -> bytes:
    """terrain.bin (C16) from heights and cut in metres. Refuses what it cannot store exactly: a height, cut, level
    or water_z that is not finite, a height or level beyond int16 decimetres, a cut outside 0..MAX_CUT."""
    h, cut = np.asarray(h, dtype=np.float64), np.asarray(cut, dtype=np.float64)
    if not (np.isfinite(h).all() and np.isfinite(cut).all()):
        raise ValueError("terrain heights and cut must be finite")
    h_dm = np.round(h * 10)
    if h_dm.min() < -32768 or h_dm.max() > 32767:
        raise ValueError("terrain height beyond int16 decimetres")
    if cut.min() < 0 or cut.max() > MAX_CUT:
        raise ValueError(f"terrace cut outside 0..{MAX_CUT} m (u8 decimetres)")
    lv_m = np.asarray(levels, np.float64)
    if not (np.isfinite(lv_m).all() and np.isfinite(water_z)):
        raise ValueError("water levels must be finite")
    if lv_m.size and np.abs(np.round(lv_m * 10)).max() > 32767:
        raise ValueError("water level beyond int16 decimetres")
    res = predict(h_dm.astype(np.int16)).view(np.uint16)
    cut_dm = np.round(cut * 10).astype(np.uint8)
    lv = np.round(lv_m * 10).astype("<i2")
    head = HEADER.pack(MAGIC, VERSION, grid.x0, grid.z0, grid.cell, grid.nx, grid.nz, water_z, len(lv), n_edge,
                       len(rings), len(shore), n_shore, SOURCES[source], 0, 0)
    return (head + _pad(lv.tobytes()) + _pad((res & 0xFF).astype(np.uint8).tobytes())
            + _pad((res >> 8).astype(np.uint8).tobytes()) + _pad(cut_dm.tobytes())
            + _pad(np.asarray(cls, dtype=np.uint8).tobytes()) + _pad(rings) + _pad(shore))


def unpack(buf: bytes) -> dict:
    """Inverse of pack: the header fields, levels (m), h (m, (nz, nx)), cut (m), cls, rings (bytes), shore (bytes).
    Raises ValueError on a bad magic, version or length."""
    if len(buf) < HEADER.size:
        raise ValueError("terrain file shorter than its header")
    (magic, version, x0, z0, cell, nx, nz, water_z, n_levels, n_edge, ring_bytes, shore_bytes, n_shore, source,
     *_) = HEADER.unpack_from(buf, 0)
    if magic != MAGIC:
        raise ValueError(f"bad terrain magic {magic:#010x}")
    if version != VERSION:
        raise ValueError(f"terrain version {version}, expected {VERSION}")
    o = HEADER.size

    def take(dtype, n):
        nonlocal o
        dt = np.dtype(dtype)
        if o + n * dt.itemsize > len(buf):
            raise ValueError("terrain file shorter than its header says")
        a = np.frombuffer(buf, dtype=dt, count=n, offset=o)
        o += -(-n * dt.itemsize // 4) * 4
        return a

    n = nx * nz
    levels = take("<i2", n_levels).astype(np.float64) / 10
    lo, hi = take("u1", n), take("u1", n)
    res = (lo.astype(np.uint16) | (hi.astype(np.uint16) << 8)).view(np.int16).reshape(nz, nx)
    cut = take("u1", n).reshape(nz, nx).astype(np.float64) / 10
    cls = take("u1", (nx - 1) * (nz - 1)).reshape(nz - 1, nx - 1)
    rings = take("u1", ring_bytes).tobytes()
    shore = take("u1", shore_bytes).tobytes()
    if o != len(buf):
        raise ValueError(f"terrain file is {len(buf)} bytes, its header says {o}")
    names = {v: k for k, v in SOURCES.items()}
    return {"grid": Grid(float(x0), float(z0), float(cell), int(nx), int(nz)), "water_z": float(water_z),
            "levels": levels, "h": unpredict(res).astype(np.float64) / 10, "cut": cut, "cls": cls, "rings": rings,
            "n_edge": int(n_edge), "shore": shore, "n_shore": int(n_shore), "source": names.get(source, str(source))}


def read_rings(stream: bytes, n_edge: int) -> list[list[list[np.ndarray]]]:
    """The ring stream as one list per edge cell of polygons, each a list of (n, 2) u8 rings."""
    out, o = [], 0
    for _ in range(n_edge):
        polys = []
        n_poly = stream[o]
        o += 1
        for _ in range(n_poly):
            rings = []
            n_ring = stream[o]
            o += 1
            for _ in range(n_ring):
                (nv,) = struct.unpack_from("<H", stream, o)
                o += 2
                rings.append(np.frombuffer(stream, np.uint8, 2 * nv, o).reshape(nv, 2))
                o += 2 * nv
            polys.append(rings)
        out.append(polys)
    if o != len(stream):
        raise ValueError("ring stream length disagrees with its cells")
    return out
