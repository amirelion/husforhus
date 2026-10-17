// The terrain (Plan 3, contracts C16 and C18): terrain.bin.gz decoded, the ground's height anywhere, the edge fade and
// the meshes the terrain worker builds. No three.js here apart from what the caller passes in (a triangulator), so
// node --test can run it (web/test/terrain.test.mjs). pipeline/terrain.py is the Python side of every function here.
//
// Local frame: metres from Stortorget, x east, z south. Node (i, j) of the grid sits at (x0 + i*cell, z0 + j*cell);
// cell (i, j) lies between nodes (i, j) and (i+1, j+1). Heights are true metres (RH 2000): what the map draws is
// relief * t - cutK * cut (uRelief and uCutK in the shaders), the same bilinear in every shader and here.
//
// Culling bounds: every chunk (chunkIndices) and every group of shore cells or walls (edgeMesh, wallMesh) carries hMax
// and hMin in true metres: the highest t, and the lowest of t and t - cut, over the grid nodes it covers (a group of
// walls also counts its own water levels). Since 0 <= cutK <= relief and cut >= 0, the drawn height relief * t -
// cutK * cut lies between relief * hMin and relief * hMax, whatever the terrace.

export const MAGIC = 0x31544648; // 'HFT1', little-endian
export const RING_SCALE = 255;
export const CLS = Object.freeze({ OUTSIDE: 0, LAND: 1, EDGE: 2, WATER: 3 });
export const SOURCES = Object.freeze(['', 'contours', 'dtm']);   // the header's source field (pipeline/terrain.py SOURCES)
// A chunk's 40 m level merges a 2 x 2 block only where its middle nodes stay within this many true metres of the
// 40 m quad (in the true heights and in the cut ones): under a pixel at the 4 km switch at the default relief.
export const LOD_TOL = 1.0;

// How long app.js waits for web/terrain-worker.js. A worker that hangs would leave the map with its water but no land:
// after this the terrain counts as failed, and the flat land is fetched instead.
export const WORKER_TIMEOUT_MS = 30_000;
// Posts one message to a worker and resolves with its answer ({ok: true, ...}); rejects on {ok: false, error}, on an
// error event, or with no answer within `ms`. The worker is terminated whichever happens.
export function askWorker(worker, message, transfer = [], ms = WORKER_TIMEOUT_MS) {
  let timer;
  return new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`the terrain worker gave no answer in ${ms / 1000} s`)), ms);
    worker.onmessage = ({ data }) => (data.ok ? resolve(data) : reject(new Error(data.error)));
    worker.onerror = e => reject(new Error(e.message || 'the terrain worker failed'));
    worker.postMessage(message, transfer);
  }).finally(() => {
    clearTimeout(timer);
    worker.terminate();
  });
}
// How long app.js waits for terrain.bin.gz to show a sign of life (its answer, then each chunk of it): a download
// that stalls is stopped after this, the terrain counts as failed and the flat land is fetched instead, as for a
// worker that hangs. A slow download that keeps arriving goes on (the final review's VIEWER-2: below about 0.8 Mbps
// the 785 KB took longer than 30 s in all).
export const FETCH_TIMEOUT_MS = 30_000;
// Starts run(signal, alive) and settles as it does, unless `ms` pass without a sign of life: run calls alive() as it
// makes progress (web/gz.js fetchGz: the answer, each chunk of the body), which starts the clock again. Then the signal
// aborts (a fetch stops downloading) and the promise rejects, naming `what`.
export function withTimeout(run, ms, what) {
  const ctl = new AbortController();
  let timer;
  return new Promise((resolve, reject) => {
    const alive = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        reject(new Error(`${what} stalled: no data for ${ms / 1000} s`));
        ctl.abort();
      }, ms);
    };
    alive();
    run(ctl.signal, alive).then(resolve, reject);
  }).finally(() => clearTimeout(timer));
}

// terrain.bin (pipeline/terrain.py pack): a 64-byte header, then levels, the two byte planes of the predicted heights,
// the cut, the classes, the edge rings and the shore bits, each section padded to 4 bytes.
export function parseTerrain(buf) {
  const v = new DataView(buf);
  const magic = buf.byteLength >= 4 ? v.getUint32(0, true) : null;
  if (magic !== MAGIC) {
    throw new Error(`not a terrain file (${magic === null ? `${buf.byteLength} bytes` : `magic 0x${magic.toString(16)}`})`);
  }
  if (buf.byteLength < 64) throw new Error(`terrain file is ${buf.byteLength} bytes, shorter than its 64-byte header`);
  if (v.getUint32(4, true) !== 1) throw new Error(`terrain version ${v.getUint32(4, true)}, expected 1`);
  const x0 = v.getFloat32(8, true), z0 = v.getFloat32(12, true), cell = v.getFloat32(16, true);
  const nx = v.getUint32(20, true), nz = v.getUint32(24, true), waterZ = v.getFloat32(28, true);
  const nLevels = v.getUint32(32, true), nEdge = v.getUint32(36, true), ringBytes = v.getUint32(40, true);
  const shoreBytes = v.getUint32(44, true), nShore = v.getUint32(48, true);
  const source = SOURCES[v.getUint32(52, true)] || String(v.getUint32(52, true));
  let o = 64;
  const take = (Type, n) => {
    if (o + n * Type.BYTES_PER_ELEMENT > buf.byteLength) throw new Error('terrain file shorter than its header says');
    const a = new Type(buf, o, n);
    o += Math.ceil(n * Type.BYTES_PER_ELEMENT / 4) * 4;
    return a;
  };
  const n = nx * nz;
  const levels = Float32Array.from(take(Int16Array, nLevels), d => d / 10);
  const lo = take(Uint8Array, n), hi = take(Uint8Array, n);
  const cutDm = take(Uint8Array, n);
  const cls = take(Uint8Array, (nx - 1) * (nz - 1));
  const rings = take(Uint8Array, ringBytes);
  const shore = take(Uint8Array, shoreBytes);
  if (o !== buf.byteLength) throw new Error(`terrain file is ${buf.byteLength} bytes, its header says ${o}`);
  // Undo the predictor: h = r + left + up - upleft, wrapped to int16 like the encoder.
  const h = new Float32Array(n), dm = new Int16Array(n);
  for (let j = 0; j < nz; j++) {
    for (let i = 0; i < nx; i++) {
      const k = j * nx + i;
      const left = i ? dm[k - 1] : 0, up = j ? dm[k - nx] : 0, upleft = i && j ? dm[k - nx - 1] : 0;
      dm[k] = (((lo[k] | (hi[k] << 8)) + left + up - upleft) << 16) >> 16;
      h[k] = dm[k] / 10;
    }
  }
  const cut = Float32Array.from(cutDm, d => d / 10);
  return { x0, z0, cell, nx, nz, waterZ, levels, h, cut, cls, rings, nEdge, shore, nShore, source };
}

// How much of the cut the map applies at relief R: all of it ('full', the default: every building stands on its own
// terrace), the part that exaggeration added ('true': a building buried 1 m by the true ground stays buried 1 m), or
// none (the plain terrain).
export const cutFactor = (mode, relief) => (mode === 'none' ? 0 : mode === 'true' ? Math.max(relief - 1, 0) : relief);

// Bilinear on the grid, each of the four nodes clamped on its own (as texelFetch is in the shaders and
// pipeline/terrain.py bilinear): tAt and cutAt in true metres, surfaceAt = R * t - K * cut, what the map draws. It reads
// the interleaved (t, cut) texture data (T.tex, heightTexture's layout), so the page keeps one copy of the grid.
export function makeGround(T) {
  if (!T) return { tAt: () => 0, cutAt: () => 0, surfaceAt: () => 0 };
  const { x0, z0, cell, nx, nz } = T, tex = T.tex ?? heightTexture(T);
  const at = (o, i, j) => tex[2 * (Math.min(nz - 1, Math.max(0, j)) * nx + Math.min(nx - 1, Math.max(0, i))) + o];
  const bil = (o, x, z) => {
    const gx = (x - x0) / cell, gz = (z - z0) / cell, fx = Math.floor(gx), fz = Math.floor(gz), tx = gx - fx, tz = gz - fz;
    const top = at(o, fx, fz) * (1 - tx) + at(o, fx + 1, fz) * tx;
    const bottom = at(o, fx, fz + 1) * (1 - tx) + at(o, fx + 1, fz + 1) * tx;
    return top * (1 - tz) + bottom * tz;
  };
  return { tAt: (x, z) => bil(0, x, z), cutAt: (x, z) => bil(1, x, z), surfaceAt: (x, z, R, K) => R * bil(0, x, z) - K * bil(1, x, z) };
}

// The texture the shaders read heights from: two floats per node, (t, cut), row-major (an RG32F DataTexture).
export function heightTexture(T) {
  const out = new Float32Array(T.nx * T.nz * 2);
  for (let k = 0; k < T.nx * T.nz; k++) { out[2 * k] = T.h[k]; out[2 * k + 1] = T.cut[k]; }
  return out;
}

// The edge fade's width from the M4 review's ?fade=<metres> lever (app.js): a finite number of metres held to
// 0..FADE_MAX_M (0 is a hard edge); anything else (missing, empty, nonsense, Infinity) keeps the build's own width.
export const FADE_MAX_M = 5000;
export function fadeWidth(param, def) {
  const v = param === null || param.trim() === '' ? NaN : Number(param);
  return Number.isFinite(v) ? Math.min(Math.max(v, 0), FADE_MAX_M) : def;
}

// The edge fade (D20, spec §4.7): per node, 255 * smoothstep(0, fadeM, d), d the distance to the nearest node outside
// the domain (a node is inside when any of its four cells is). Two-pass chamfer distance, 1 and √2 cells.
export function fadeField(T, fadeM) {
  const { nx, nz, cell, cls } = T;
  const inside = new Uint8Array(nx * nz);
  for (let j = 0; j < nz - 1; j++) {
    for (let i = 0; i < nx - 1; i++) {
      if (cls[j * (nx - 1) + i] === CLS.OUTSIDE) continue;
      inside[j * nx + i] = inside[j * nx + i + 1] = inside[(j + 1) * nx + i] = inside[(j + 1) * nx + i + 1] = 1;
    }
  }
  const d = new Float32Array(nx * nz);
  for (let k = 0; k < d.length; k++) d[k] = inside[k] ? 1e9 : 0;
  const D = Math.SQRT2;
  const relax = (k, kk, w) => { if (d[kk] + w < d[k]) d[k] = d[kk] + w; };
  for (let j = 0; j < nz; j++) {
    for (let i = 0; i < nx; i++) {
      const k = j * nx + i;
      if (i) relax(k, k - 1, 1);
      if (j) { relax(k, k - nx, 1); if (i) relax(k, k - nx - 1, D); if (i < nx - 1) relax(k, k - nx + 1, D); }
    }
  }
  for (let j = nz - 1; j >= 0; j--) {
    for (let i = nx - 1; i >= 0; i--) {
      const k = j * nx + i;
      if (i < nx - 1) relax(k, k + 1, 1);
      if (j < nz - 1) { relax(k, k + nx, 1); if (i < nx - 1) relax(k, k + nx + 1, D); if (i) relax(k, k + nx - 1, D); }
    }
  }
  const out = new Uint8Array(nx * nz);
  for (let k = 0; k < out.length; k++) {
    const t = Math.min(1, Math.max(0, (d[k] * cell) / Math.max(fadeM, 1e-6)));
    out[k] = Math.round(255 * (fadeM <= 0 ? (inside[k] ? 1 : 0) : t * t * (3 - 2 * t)));
  }
  return out;
}

// The land cells as meshes, one per chunk of `chunkCells` x `chunkCells` cells: every chunk shares one vertex grid of
// (chunkCells + 1)^2 nodes (positions relative to the chunk's corner, so one buffer serves all), and has two index
// lists: LOD0, two triangles per land cell; LOD1, two per 2 x 2 block of land cells that is whole, away from the
// chunk's outer ring of cells (so neighbouring chunks meet along 20 m edges at any level) and flat enough: its five
// middle nodes within `tol` true metres of the 40 m quad, in the true heights and in the cut ones (whatever the relief
// and terrace, the drawn ground then stays within tol x relief of the 20 m grid the buildings stand on). Where a 40 m
// side meets cells drawn at 20 m (land or an edge cell), a gap triangle (A, middle, C), in both windings, closes the
// T-junction. Triangles face up (+y); gap triangles stand on their edge. hMax and hMin bound the chunk's land nodes
// (the module's culling bounds, above).
export function chunkIndices(T, chunkCells, tol = LOD_TOL) {
  checkChunkCells(T, chunkCells);
  const { nx, nz, cls, h, cut } = T;
  const cx = nx - 1, cz = nz - 1, V = chunkCells + 1, out = [];
  const kind = (i, j) => (i >= 0 && j >= 0 && i < cx && j < cz ? cls[j * cx + i] : CLS.OUTSIDE);
  const land = (i, j) => kind(i, j) === CLS.LAND;
  const node = (f, i, j) => f[j * nx + i];
  const t = (i, j) => node(h, i, j), cutT = (i, j) => node(h, i, j) - node(cut, i, j);
  // Within tol of the 40 m quad (a, b, c, d; diagonal b-c, as quad() splits it) at the five middle nodes of field f.
  const within = (f, i, j) => {
    const a = f(i, j), b = f(i + 2, j), c = f(i, j + 2), d = f(i + 2, j + 2);
    return Math.abs(f(i + 1, j) - (a + b) / 2) <= tol && Math.abs(f(i, j + 1) - (a + c) / 2) <= tol
      && Math.abs(f(i + 2, j + 1) - (b + d) / 2) <= tol && Math.abs(f(i + 1, j + 2) - (c + d) / 2) <= tol
      && Math.abs(f(i + 1, j + 1) - (b + c) / 2) <= tol;
  };
  const flat = (i, j) => within(t, i, j) && within(cutT, i, j);
  for (let j0 = 0; j0 < cz; j0 += chunkCells) {
    for (let i0 = 0; i0 < cx; i0 += chunkCells) {
      const i1 = Math.min(i0 + chunkCells, cx), j1 = Math.min(j0 + chunkCells, cz);
      const lod0 = [], lod1 = [];
      const at = (i, j) => (j - j0) * V + (i - i0);
      const quad = (list, i, j, s) => {
        const a = at(i, j), b = a + s, c = a + s * V, d = c + s;
        list.push(a, c, b, b, c, d);
      };
      let hMax = -Infinity, hMin = Infinity, any = false;
      for (let j = j0; j < j1; j++) {
        for (let i = i0; i < i1; i++) {
          if (!land(i, j)) continue;
          any = true;
          quad(lod0, i, j, 1);
          for (const [p, q] of [[i, j], [i + 1, j], [i, j + 1], [i + 1, j + 1]]) {
            hMax = Math.max(hMax, t(p, q));
            hMin = Math.min(hMin, t(p, q), cutT(p, q));
          }
        }
      }
      if (!any) continue;
      // which cells a 40 m quad covers: whole blocks at even offsets, inside the chunk's outer ring, flat enough
      const coarse = new Uint8Array((i1 - i0) * (j1 - j0));
      const isCoarse = (i, j) => i >= i0 && j >= j0 && i < i1 && j < j1 && coarse[(j - j0) * (i1 - i0) + (i - i0)] === 1;
      const blocks = [];
      for (let j = j0 + 2; j + 2 < j1; j += 2) {
        for (let i = i0 + 2; i + 2 < i1; i += 2) {
          if (!(land(i, j) && land(i + 1, j) && land(i, j + 1) && land(i + 1, j + 1)) || !flat(i, j)) continue;
          blocks.push([i, j]);
          for (const [di, dj] of [[0, 0], [1, 0], [0, 1], [1, 1]]) coarse[(j + dj - j0) * (i1 - i0) + (i + di - i0)] = 1;
        }
      }
      for (const [i, j] of blocks) {
        quad(lod1, i, j, 2);
        // each side: (outside cells across it, A, middle, C); a 20 m neighbour (land or edge) needs the gap triangle
        for (const [n1, n2, A, M, C] of [
          [[i, j - 1], [i + 1, j - 1], at(i, j), at(i + 1, j), at(i + 2, j)],
          [[i, j + 2], [i + 1, j + 2], at(i, j + 2), at(i + 1, j + 2), at(i + 2, j + 2)],
          [[i - 1, j], [i - 1, j + 1], at(i, j), at(i, j + 1), at(i, j + 2)],
          [[i + 2, j], [i + 2, j + 1], at(i + 2, j), at(i + 2, j + 1), at(i + 2, j + 2)]]) {
          const fine = [n1, n2].some(([p, q]) => !isCoarse(p, q) && (land(p, q) || kind(p, q) === CLS.EDGE));
          if (fine) lod1.push(A, M, C, A, C, M);
        }
      }
      for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) if (land(i, j) && !isCoarse(i, j)) quad(lod1, i, j, 1);
      out.push({ i0, j0, cells: [i1 - i0, j1 - j0], lod0: Uint16Array.from(lod0), lod1: Uint16Array.from(lod1), hMax, hMin });
    }
  }
  return out;
}

// A chunk's side in cells: a whole number, small enough that its vertex grid fits Uint16 indices ((n + 1)^2 nodes)
// and its corner-relative positions fit Int16 decimetres (n * cell * 10).
function checkChunkCells(T, chunkCells) {
  const n = chunkCells;
  if (!(Number.isInteger(n) && n >= 1 && n * Math.round(T.cell * 10) <= 32767 && (n + 1) ** 2 <= 65536)) {
    throw new Error(`a chunk of ${n} cells of ${T.cell} m: needs a whole number n >= 1 with (n + 1)^2 <= 65536 nodes `
      + 'and n * cell <= 3276.7 m');
  }
}

// The shared vertex grid of chunkIndices: Int16 (x, 0, z) in decimetres from the chunk's corner.
export function chunkVertices(T, chunkCells) {
  checkChunkCells(T, chunkCells);
  const V = chunkCells + 1, pos = new Int16Array(V * V * 3), step = Math.round(T.cell * 10);
  for (let j = 0; j < V; j++) for (let i = 0; i < V; i++) pos.set([i * step, 0, j * step], (j * V + i) * 3);
  return pos;
}

// Orient a triangle list so every triangle faces up (+y): in x, z (z south), that is a negative cross product.
function faceUp(xz, idx, first) {
  for (let k = first; k < idx.length; k += 3) {
    const [a, b, c] = [idx[k], idx[k + 1], idx[k + 2]];
    const cross = (xz[2 * b] - xz[2 * a]) * (xz[2 * c + 1] - xz[2 * a + 1]) - (xz[2 * c] - xz[2 * a]) * (xz[2 * b + 1] - xz[2 * a + 1]);
    if (cross > 0) { idx[k + 1] = c; idx[k + 2] = b; }
  }
}

// Polygons ([[ [x, z], ... ] exterior, ...holes ]) as one triangle list: xz (local metres) and indices facing up.
// triangulate(contour, holes) is three.js ShapeUtils.triangulateShape on arrays of {x, y}. ends, when given, collects
// the index count after each polygon (for groupRanges()). A ring that repeats its first point at its end loses the
// repeat first, as triangulateShape drops it (three.js removeDupEndPts: more than two points, exactly equal): kept in
// xz, it would shift the indices of every later ring of the polygon by one.
const openRing = ring => (ring.length > 2 && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1]
  ? ring.slice(0, -1) : ring);
function polygonsMesh(polys, triangulate, perPoly = () => 0, ends = null) {
  const xz = [], idx = [], extra = [];
  for (let p = 0; p < polys.length; p++) {
    const [outer, ...holes] = polys[p].map(openRing);
    const base = xz.length / 2;
    const toV = ring => ring.map(([x, z]) => ({ x, y: z }));
    for (const ring of [outer, ...holes]) for (const [x, z] of ring) { xz.push(x, z); extra.push(perPoly(p)); }
    const first = idx.length;
    for (const t of triangulate(toV(outer), holes.map(toV))) idx.push(base + t[0], base + t[1], base + t[2]);
    faceUp(xz, idx, first);
    ends?.push(idx.length);
  }
  return { xz: Float32Array.from(xz), idx: Uint32Array.from(idx), extra: Float32Array.from(extra) };
}

// Groups of groupCells x groupCells cells (4800 m in the viewer: two by two chunks), so the shore cells and the quay
// walls cull with the view and the pick pass a group at a time instead of as one city-wide mesh. Items (each with the
// grid cell it belongs to) are ordered by group; each group gets its index range, its box (local metres) and its
// culling bounds hMax and hMin (see the top of the module): over the grid nodes under its box when T is given, and
// over its vertices' own levels when `level` is given (the walls' water).
function groupOf(T, groupCells) {
  const gx = Math.ceil((T.nx - 1) / groupCells);
  return ([i, j]) => Math.floor(j / groupCells) * gx + Math.floor(i / groupCells);
}
function groupRanges(T, keys, ends, xz, idx, level = null) {
  const groups = [];
  let start = 0;
  for (let k = 0; k < keys.length; k++) {
    if (k + 1 < keys.length && keys[k + 1] === keys[k]) continue;
    const end = ends[k];
    if (end > start) {
      let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity, hMax = -Infinity, hMin = Infinity;
      for (let q = start; q < end; q++) {
        const v = idx[q];
        x0 = Math.min(x0, xz[2 * v]); x1 = Math.max(x1, xz[2 * v]); z0 = Math.min(z0, xz[2 * v + 1]); z1 = Math.max(z1, xz[2 * v + 1]);
        if (level) { hMax = Math.max(hMax, level[v]); hMin = Math.min(hMin, level[v]); }
      }
      if (T) {
        const i0 = Math.max(0, Math.floor((x0 - T.x0) / T.cell)), i1 = Math.min(T.nx - 1, Math.ceil((x1 - T.x0) / T.cell));
        const j0 = Math.max(0, Math.floor((z0 - T.z0) / T.cell)), j1 = Math.min(T.nz - 1, Math.ceil((z1 - T.z0) / T.cell));
        for (let j = j0; j <= j1; j++) {
          for (let i = i0; i <= i1; i++) {
            const t = T.h[j * T.nx + i];
            hMax = Math.max(hMax, t);
            hMin = Math.min(hMin, t, t - T.cut[j * T.nx + i]);
          }
        }
      }
      groups.push({ start, count: end - start, box: [x0, z0, x1, z1], hMax, hMin });
    }
    start = end;
  }
  return groups;
}
function byGroup(keys) {
  return keys.map((key, k) => [key, k]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, k]) => k);
}

// The edge cells' land (the exact cut along shores and the domain's edge), from the ring stream: the polygons and,
// for each, its cell [i, j].
export function edgePolygons(T) {
  const { nx, cell, cls, rings, nEdge, x0, z0 } = T;
  const v = new DataView(rings.buffer, rings.byteOffset, rings.byteLength), polys = [], cells = [];
  let o = 0, seen = 0;
  for (let k = 0; k < cls.length && seen < nEdge; k++) {
    if (cls[k] !== CLS.EDGE) continue;
    seen++;
    const i = k % (nx - 1), j = Math.floor(k / (nx - 1)), cx = x0 + i * cell, cz = z0 + j * cell;
    const nPoly = rings[o++];
    for (let p = 0; p < nPoly; p++) {
      const nRing = rings[o++], poly = [];
      for (let r = 0; r < nRing; r++) {
        const nv = v.getUint16(o, true); o += 2;
        const ring = [];
        for (let q = 0; q < nv; q++, o += 2) ring.push([cx + rings[o] / RING_SCALE * cell, cz + rings[o + 1] / RING_SCALE * cell]);
        poly.push(ring);
      }
      polys.push(poly);
      cells.push([i, j]);
    }
  }
  if (o !== rings.length) throw new Error('terrain ring stream disagrees with its cells');
  return { polys, cells };
}

// The edge cells as one triangle list in groups (groupCells: see groupOf; Infinity makes one group).
export function edgeMesh(T, triangulate, groupCells = Infinity) {
  const { polys, cells } = edgePolygons(T);
  const key = groupCells === Infinity ? () => 0 : groupOf(T, groupCells);
  const order = byGroup(cells.map(key)), ends = [];
  const m = polygonsMesh(order.map(k => polys[k]), triangulate, () => 0, ends);
  return { xz: m.xz, idx: m.idx, groups: groupRanges(T, order.map(k => key(cells[k])), ends, m.xz, m.idx) };
}

// water.bin (pipeline/s04_base.py pack): u32 nPoly, nRing, nVert; u32 ringStart[nPoly+1]; u32 vertStart[nRing+1];
// f32 xz[2*nVert]. Returns polygons of rings of [x, z].
export function parsePolygons(buf) {
  const [nPoly, nRing, nVert] = new Uint32Array(buf, 0, 3);
  const ringStart = new Uint32Array(buf, 12, nPoly + 1);
  const vertStart = new Uint32Array(buf, 12 + 4 * (nPoly + 1), nRing + 1);
  const xz = new Float32Array(buf, 12 + 4 * (nPoly + 1) + 4 * (nRing + 1), 2 * nVert);
  const polys = [];
  for (let p = 0; p < nPoly; p++) {
    const poly = [];
    for (let r = ringStart[p]; r < ringStart[p + 1]; r++) {
      const ring = [];
      for (let k = vertStart[r]; k < vertStart[r + 1]; k++) ring.push([xz[2 * k], xz[2 * k + 1]]);
      poly.push(ring);
    }
    polys.push(poly);
  }
  return polys;
}

// The water at its levels: one triangle list, each vertex carrying its polygon's level (true metres).
export function waterMesh(polys, levels, triangulate) {
  const m = polygonsMesh(polys, triangulate, p => levels[p] ?? 0);
  return { xz: m.xz, idx: m.idx, level: m.extra };
}

// Quay walls along every shore segment (the shore bits, one per water vertex in water.bin's order): a quad from the
// terrain's height at the shore down to the water's level. top is 1 for the upper vertices; level per vertex. With T
// and groupCells, the quads are ordered and grouped by the cell under each segment's middle (see edgeMesh). Every
// group has its box and bounds; without T (no ground heights to read) the bounds are its water levels alone.
export function wallMesh(polys, levels, shore, T = null, groupCells = Infinity) {
  const segs = [];
  let k = 0;
  for (let p = 0; p < polys.length; p++) {
    for (const ring of polys[p]) {
      for (let q = 0; q < ring.length; q++, k++) {
        if ((shore[k >> 3] >> (k & 7)) & 1) segs.push([p, ring[q], ring[(q + 1) % ring.length]]);
      }
    }
  }
  const key = !T || groupCells === Infinity ? () => 0 : groupOf(T, groupCells);
  const cellOf = ([, a, b]) => (T ? [Math.floor(((a[0] + b[0]) / 2 - T.x0) / T.cell), Math.floor(((a[1] + b[1]) / 2 - T.z0) / T.cell)] : [0, 0]);
  const keys = segs.map(s => key(cellOf(s))), order = byGroup(keys);
  const xz = [], top = [], level = [], idx = [], ends = [];
  for (const s of order) {
    const [p, [ax, az], [bx, bz]] = segs[s];
    const v = xz.length / 2;
    xz.push(ax, az, bx, bz, bx, bz, ax, az);
    top.push(0, 0, 1, 1);
    level.push(levels[p], levels[p], levels[p], levels[p]);
    idx.push(v, v + 1, v + 2, v, v + 2, v + 3);
    ends.push(idx.length);
  }
  const out = { xz: Float32Array.from(xz), top: Uint8Array.from(top), level: Float32Array.from(level), idx: Uint32Array.from(idx) };
  out.groups = groupRanges(T, order.map(s => keys[s]), ends, out.xz, out.idx, out.level);
  return out;
}

// The level (true metres) of the water at (x, z): the polygon that holds the point (even-odd over its rings), else
// the nearest polygon's (a name on a stream narrower than the water polygons). For the water's names (app.js).
export function levelAt(polys, levels, x, z) {
  let best = -1, bestD = Infinity;
  for (let p = 0; p < polys.length; p++) {
    let inside = false, d = Infinity;
    for (const ring of polys[p]) {
      for (let q = 0, r = ring.length - 1; q < ring.length; r = q++) {
        const [ax, az] = ring[q], [bx, bz] = ring[r];
        if ((az > z) !== (bz > z) && x < ((bx - ax) * (z - az)) / (bz - az) + ax) inside = !inside;
        const ex = bx - ax, ez = bz - az, L = ex * ex + ez * ez;
        const s = L ? Math.min(1, Math.max(0, ((x - ax) * ex + (z - az) * ez) / L)) : 0;
        d = Math.min(d, Math.hypot(x - ax - s * ex, z - az - s * ez));
      }
    }
    if (inside) return levels[p];
    if (d < bestD) { bestD = d; best = p; }
  }
  return best < 0 ? 0 : levels[best];
}
