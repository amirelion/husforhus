// web/terrain.js on the committed synthetic fixture (tests/make_terrain_fixture.py):
// the decoder, the ground sampler against pipeline/terrain.py's own values, the fade, the chunk meshes, the exact cut
// along the shore, the water at its level and the quay walls, and the worker's checks on the two files.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ShapeUtils, Vector2 } from '../vendor/three.core.js';
import {
  CLS, FADE_MAX_M, FETCH_TIMEOUT_MS, LOD_TOL, WORKER_TIMEOUT_MS, askWorker, chunkIndices, chunkVertices, cutFactor,
  edgeMesh, fadeAtGrid, fadeField, fadeWidth, heightTexture, levelAt, makeGround, parsePolygons, parseTerrain, waterMesh, wallMesh,
  withTimeout,
} from '../terrain.js';

const file = name => {
  const b = readFileSync(new URL(`./fixtures/${name}`, import.meta.url));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
};
const expect = JSON.parse(readFileSync(new URL('./fixtures/terrain_v1.expect.json', import.meta.url), 'utf8'));
const T = parseTerrain(file('terrain_v1.bin'));
const water = parsePolygons(file('water_v1.bin'));
const triangulate = (contour, holes) => ShapeUtils.triangulateShape(contour.map(p => new Vector2(p.x, p.y)),
  holes.map(h => h.map(p => new Vector2(p.x, p.y))));

// Area seen from above of a triangle list over xz pairs, and whether every triangle faces up (+y; z points south).
function plan(xz, idx) {
  let area = 0, up = true;
  for (let k = 0; k < idx.length; k += 3) {
    const [a, b, c] = [idx[k], idx[k + 1], idx[k + 2]];
    const cross = (xz[2 * b] - xz[2 * a]) * (xz[2 * c + 1] - xz[2 * a + 1]) - (xz[2 * c] - xz[2 * a]) * (xz[2 * b + 1] - xz[2 * a + 1]);
    area += Math.abs(cross) / 2;
    if (cross > 0) up = false;
  }
  return { area, up };
}

test('the decoder reads the header, the predicted heights, the cut and the sections', () => {
  const g = expect.grid;
  assert.deepEqual([T.x0, T.z0, T.cell, T.nx, T.nz, T.waterZ, T.source], [g.x0, g.z0, g.cell, g.nx, g.nz, 0, 'contours']);
  assert.deepEqual([...T.levels].map(v => +v.toFixed(3)), [expect.level]);
  for (let j = 0; j < T.nz; j++) {
    for (let i = 0; i < T.nx; i++) {
      const x = T.x0 + i * T.cell, z = T.z0 + j * T.cell;
      assert.equal(T.h[j * T.nx + i].toFixed(1), (3 + 0.05 * x - 0.02 * z).toFixed(1), `node ${i},${j}`);
      assert.equal(+T.cut[j * T.nx + i].toFixed(1), x > 40 ? 0.7 : 0);
    }
  }
  const counts = [0, 0, 0, 0];
  for (const c of T.cls) counts[c]++;
  assert.deepEqual(counts, expect.classes);
  assert.equal(T.nEdge, expect.nEdge);
  assert.equal(T.nShore, expect.nShore);
  assert.throws(() => parseTerrain(new ArrayBuffer(64)), /not a terrain file/);
  assert.throws(() => parseTerrain(file('terrain_v1.bin').slice(0, 200)), /shorter/);
  // shorter than the header: the file's own error, never a DataView RangeError
  const own = re => err => !(err instanceof RangeError) && re.test(err.message);
  assert.throws(() => parseTerrain(new ArrayBuffer(0)), own(/not a terrain file \(0 bytes\)/));
  assert.throws(() => parseTerrain(file('terrain_v1.bin').slice(0, 2)), own(/not a terrain file \(2 bytes\)/));
  assert.throws(() => parseTerrain(file('terrain_v1.bin').slice(0, 40)), own(/40 bytes, shorter than its 64-byte header/));
});

test('the ground sampler gives pipeline/terrain.py bilinear values, clamped at the grid edge', () => {
  const ground = makeGround(T);
  // beyond the far corner, and beyond the north edge between two nodes: each node clamped on its own
  for (const [x, z] of [[150, 100], [30, -45], [-50, 5], [95, 70]]) {
    assert.ok(expect.samples.some(s => s.x === x && s.z === z), `sample ${x},${z}`);
  }
  for (const s of expect.samples) {
    assert.ok(Math.abs(ground.tAt(s.x, s.z) - s.t) < 1e-5, `t at ${s.x},${s.z}`);
    assert.ok(Math.abs(ground.cutAt(s.x, s.z) - s.cut) < 1e-5, `cut at ${s.x},${s.z}`);
    const R = 2.5, K = cutFactor('true', R);
    assert.ok(Math.abs(ground.surfaceAt(s.x, s.z, R, K) - (R * s.t - K * s.cut)) < 1e-5);
  }
  assert.equal(makeGround(null).surfaceAt(1, 2, 2.5, 2.5), 0); // before the terrain loads, the ground is flat
  const tex = heightTexture(T);
  assert.equal(tex.length, T.nx * T.nz * 2);
  assert.deepEqual([tex[2 * 7], tex[2 * 7 + 1]], [T.h[7], T.cut[7]]);
});

test('the cut is used fully, for the exaggeration only, or not at all', () => {
  assert.equal(cutFactor('full', 2.5), 2.5);
  assert.equal(cutFactor('true', 2.5), 1.5);
  assert.equal(cutFactor('true', 0.6), 0);   // flatter than true: nothing buried to keep
  assert.equal(cutFactor('none', 2.5), 0);
});

test('the fade read at a point as the shaders read it: between its nodes, clamped at the grid, 1 without one', () => {
  // 3 by 2 nodes, 10 m apart, from (100, 200): a row of 0, 255, 255 over a row of 0, 0, 255
  const grid = { x0: 100, z0: 200, cell: 10, nx: 3, nz: 2 }, fade = Uint8Array.from([0, 255, 255, 0, 0, 255]);
  assert.equal(fadeAtGrid(fade, grid, 110, 200), 1);
  assert.equal(fadeAtGrid(fade, grid, 105, 200), 0.5);
  assert.equal(fadeAtGrid(fade, grid, 110, 205), 0.5);
  assert.equal(fadeAtGrid(fade, grid, 50, 150), 0);                       // past the grid: its edge's value
  assert.equal(fadeAtGrid(fade, grid, 500, 500), 1);
  assert.equal(fadeAtGrid(Uint8Array.from([255]), { x0: 0, z0: 0, cell: 1, nx: 1, nz: 1 }, 5, 5), 1);   // no terrain
  assert.equal(fadeAtGrid(undefined, grid, 105, 200), 1);
});

test('the fade is 0 outside the domain and rises to 255 over fadeM', () => {
  const near = fadeField(T, 400), short = fadeField(T, 10), none = fadeField(T, 0);
  const node = (i, j) => j * T.nx + i;
  assert.equal(near[node(0, 0)], 0);                         // a corner node, outside
  const mid = node(3, 2);                                    // inside the domain, 40 m from its edge
  assert.ok(near[mid] > 0 && near[mid] < 255);
  // 40 m in, at fadeM 400: 255 * smoothstep(0.1) = 7.14; 20 m in: 255 * smoothstep(0.05) = 1.85
  assert.equal(near[mid], 7);
  const rows = [];
  for (let j = 0; j < T.nz; j++) rows.push([...near.subarray(j * T.nx, (j + 1) * T.nx)].join(' '));
  assert.deepEqual(rows, ['0 0 0 0 0 0 0 0', '0 2 2 2 2 2 2 0', '0 2 7 7 7 7 2 0', '0 2 7 7 7 7 2 0', '0 2 2 2 2 2 2 0',
    '0 0 0 0 0 0 0 0']);
  assert.equal(short[mid], 255);
  assert.equal(none[mid], 255);
  assert.equal(none[node(0, 0)], 0);
});

test('chunks cover every land cell; LOD1 covers the same land; triangles face up', () => {
  const land = expect.classes[CLS.LAND];
  for (const size of [2, 3, 120]) {
    const chunks = chunkIndices(T, size);
    const V = size + 1;
    assert.equal(chunks.reduce((n, c) => n + c.lod0.length, 0), land * 6, `size ${size}`);
    for (const c of chunks) {
      assert.ok(Math.max(...c.lod0, ...c.lod1) < V * V);
      assert.ok(c.hMax >= 2 && c.hMax <= 8);
      const verts = chunkVertices(T, size), xz = [];
      for (let k = 0; k < V * V; k++) xz.push(verts[3 * k] / 10, verts[3 * k + 2] / 10);
      const a0 = plan(xz, c.lod0), a1 = plan(xz, c.lod1);
      assert.ok(a0.up && a1.up);
      assert.equal(Math.round(a0.area), Math.round(a1.area));   // LOD1 covers the same land (gap triangles add none)
      // the culling bounds: hMax the highest t of the chunk's land nodes, hMin the lowest of t and t - cut
      const lows = [];
      for (const v of new Set(c.lod0)) {
        const k = (c.j0 + Math.floor(v / V)) * T.nx + c.i0 + (v % V);
        assert.ok(T.h[k] <= c.hMax);
        lows.push(T.h[k], T.h[k] - T.cut[k]);
      }
      assert.equal(c.hMin, Math.min(...lows));
    }
  }
  // a chunk's bounds come from t and from t - cut: a 3 m notch at one node lowers hMin, not hMax
  const notch = chunkIndices(allLand(4, () => 10, (i, j) => (i === 2 && j === 2 ? 3 : 0)), 4)[0];
  assert.deepEqual([notch.hMax, notch.hMin], [10, 7]);
});

// A synthetic all-land grid of n x n cells (20 m), heights f(i, j), no cut: one chunk of n cells.
function allLand(n, f, cutF = () => 0) {
  const nx = n + 1, h = new Float32Array(nx * nx), cut = new Float32Array(nx * nx);
  for (let j = 0; j < nx; j++) for (let i = 0; i < nx; i++) { h[j * nx + i] = f(i, j); cut[j * nx + i] = cutF(i, j); }
  return { x0: 0, z0: 0, cell: 20, nx, nz: nx, h, cut, cls: new Uint8Array(n * n).fill(CLS.LAND) };
}
// LOD1's 40 m quads (two triangles each), its gap triangles, the T-junctions left open and the gaps drawn one way
// only. A 40 m side is open when its middle node is used by a 20 m cell across it, a land cell's triangles or one of
// edgeCells ([i, j] of the cells the shore mesh draws), with no gap triangle (A, middle, C) to close it (R3's node
// test). A gap comes in both windings, (A, M, C) and (A, C, M), so it closes the crack from either side: oneWay counts
// the gaps whose ordered triples show only one.
function lod1Shape(idx, V, edgeCells = []) {
  const rc = v => [v % V, Math.floor(v / V)], tris = [];
  for (let k = 0; k < idx.length; k += 3) tris.push([idx[k], idx[k + 1], idx[k + 2]]);
  const isGap = t => { const p = t.map(rc); return p.every(q => q[0] === p[0][0]) || p.every(q => q[1] === p[0][1]); };
  const key = t => [...t].sort((a, b) => a - b).join(',');
  const turn = t => { const s = t.indexOf(Math.min(...t)); return [t[s], t[(s + 1) % 3], t[(s + 2) % 3]].join(','); };
  const gaps = new Map(), used = new Set();
  for (const t of tris.filter(isGap)) gaps.set(key(t), (gaps.get(key(t)) ?? new Set()).add(turn(t)));
  let coarse = 0, open = 0;
  for (const t of tris) if (!isGap(t)) for (const v of t) used.add(v);
  for (const [i, j] of edgeCells) for (const v of [j * V + i, j * V + i + 1, (j + 1) * V + i, (j + 1) * V + i + 1]) used.add(v);
  for (const t of tris) {
    if (isGap(t)) continue;
    for (const [p, q] of [[t[0], t[1]], [t[1], t[2]], [t[2], t[0]]]) {
      const [a, b] = [rc(p), rc(q)];
      const di = Math.abs(a[0] - b[0]), dj = Math.abs(a[1] - b[1]);
      if (!((di === 2 && dj === 0) || (di === 0 && dj === 2))) continue;
      coarse += 0.25;   // four sides per quad
      const m = (p + q) / 2;
      if (used.has(m) && !gaps.has(key([p, m, q]))) open++;
    }
  }
  const oneWay = [...gaps.values()].filter(w => w.size !== 2).length;
  return { coarse: Math.round(coarse), gaps: gaps.size, open, oneWay };
}

test('LOD1 merges a 2 x 2 block only within LOD_TOL, away from the chunk\'s ring, and closes every T-junction', () => {
  const n = 12, V = n + 1;
  // a plane: every whole block inside the ring merges (rows and columns 2..9: four by four blocks)
  const plane = chunkIndices(allLand(n, (i, j) => 10 + 0.3 * i - 0.2 * j), n)[0];
  assert.deepEqual(lod1Shape(plane.lod1, V), { coarse: 16, gaps: 16, open: 0, oneWay: 0 });
  // one node raised by more than LOD_TOL: node (5, 4) is the middle of a side of blocks (4, 2) and (4, 4), which stay
  // at 20 m, and their neighbours close the T-junctions with them
  const bump = chunkIndices(allLand(n, (i, j) => 10 + 0.3 * i + (i === 5 && j === 4 ? LOD_TOL + 0.2 : 0)), n)[0];
  const b = lod1Shape(bump.lod1, V);
  assert.equal(b.coarse, 14);
  assert.equal(b.open, 0);
  assert.equal(b.oneWay, 0);
  // a bump within LOD_TOL merges; one in the cut alone (a terrace notch) does not
  assert.equal(lod1Shape(chunkIndices(allLand(n, (i, j) => (i === 5 && j === 4 ? 0.9 * LOD_TOL : 0)), n)[0].lod1, V).coarse, 16);
  const notch = allLand(n, () => 10, (i, j) => (i === 5 && j === 4 ? 2 : 0));
  assert.equal(lod1Shape(chunkIndices(notch, n)[0].lod1, V).coarse, 14);
  // the fixture's land cells sit by the shore and the chunk's ring: nothing merges, nothing is left open
  const edges = [];
  T.cls.forEach((c, k) => c === CLS.EDGE && edges.push([k % (T.nx - 1), Math.floor(k / (T.nx - 1))]));
  for (const c of chunkIndices(T, 120)) assert.equal(lod1Shape(c.lod1, 121, edges).open, 0);
});

test('LOD1 tests all five middle nodes against the 40 m quad as it is drawn (diagonal b-c)', () => {
  const n = 12, V = n + 1, up = LOD_TOL + 0.2;
  const coarse = f => lod1Shape(chunkIndices(allLand(n, f), n)[0].lod1, V);
  // (5, 5) is the centre of block (4, 4) alone, whose four merged neighbours each close a side with it: 16 + 4 gaps
  assert.deepEqual(coarse((i, j) => 10 + (i === 5 && j === 5 ? up : 0)), { coarse: 15, gaps: 20, open: 0, oneWay: 0 });
  // (4, 5) is the right middle of block (2, 4) and the left middle of block (4, 4); gaps: 16 - 1 (block (2, 4)'s side
  // on the ring) + 2 (its merged neighbours) + 3 (block (4, 4)'s)
  assert.deepEqual(coarse((i, j) => 10 + (i === 4 && j === 5 ? up : 0)), { coarse: 14, gaps: 20, open: 0, oneWay: 0 });
  // a fold along the line i + j = 10, which is the b-c diagonal of blocks (2, 6), (4, 4) and (6, 2): each of their two
  // 40 m triangles is a plane, so every block merges; tested against (a + d) / 2 instead, those three would not
  assert.equal(coarse((i, j) => 10 * Math.abs(i + j - 10)).coarse, 16);
  // a fold along i = j instead, the a-d diagonal of blocks (2, 2), (4, 4), (6, 6) and (8, 8), bends their 40 m
  // triangles: those four stay at 20 m
  assert.equal(coarse((i, j) => 10 * Math.abs(i - j)).coarse, 12);
});

test('LOD1 closes a T-junction with an edge cell too, with a gap in both windings', () => {
  // cell (4, 1) is an edge cell and (5, 1) water: the only 20 m neighbour across block (4, 2)'s north side is the
  // edge cell, which the shore mesh draws at 20 m
  const n = 12, V = n + 1, g = allLand(n, () => 10);
  g.cls[1 * n + 4] = CLS.EDGE;
  g.cls[1 * n + 5] = CLS.WATER;
  const c = chunkIndices(g, n)[0];
  const s = lod1Shape(c.lod1, V, [[4, 1]]);
  assert.deepEqual(s, { coarse: 16, gaps: 16, open: 0, oneWay: 0 });
  // the gap on that side, both ways round: (A, M, C) and (A, C, M) as ordered triples
  const at = (i, j) => j * V + i, tri = [];
  for (let k = 0; k < c.lod1.length; k += 3) tri.push([...c.lod1.subarray(k, k + 3)].join(','));
  const [A, M, C] = [at(4, 2), at(5, 2), at(6, 2)];
  assert.equal(tri.filter(t => t === [A, M, C].join(',')).length, 1);
  assert.equal(tri.filter(t => t === [A, C, M].join(',')).length, 1);
});

test('land cells and edge cells together are the land, to the ring quantisation', () => {
  const edge = edgeMesh(T, triangulate);
  const { area, up } = plan(edge.xz, edge.idx);
  assert.ok(up);
  const total = area + expect.classes[CLS.LAND] * T.cell * T.cell;
  assert.ok(Math.abs(total - expect.landArea) < 0.002 * expect.landArea, `${total} vs ${expect.landArea}`);
  assert.deepEqual(edge.groups.map(g => [g.start, g.count]), [[0, edge.idx.length]]);
});

// Whether (x, z) lies on a triangle of the list, seen from above (edges included).
function covered(xz, idx, x, z) {
  for (let k = 0; k < idx.length; k += 3) {
    const [a, b, c] = [idx[k], idx[k + 1], idx[k + 2]].map(v => [xz[2 * v], xz[2 * v + 1]]);
    const side = (p, q) => (q[0] - p[0]) * (z - p[1]) - (q[1] - p[1]) * (x - p[0]);
    const d = [side(a, b), side(b, c), side(c, a)];
    if (d.every(e => e >= 0) || d.every(e => e <= 0)) return true;
  }
  return false;
}

test('the edge cells\' land lies where the rings put it, u east and v south in its cell', () => {
  // cell (4, 1) spans x 60..80, z 0..20: the bay's west shore runs from (70, 10) towards (55, 50), so land lies north
  // of z = 10 and west of the shore (x 68.1 at z 15, 67 at z 18), water east of it. A mirrored u or swapped u and v
  // would move the land onto the water at one of these four points.
  const edge = edgeMesh(T, triangulate);
  for (const [x, z] of [[62, 15], [78, 9]]) assert.ok(covered(edge.xz, edge.idx, x, z), `land at ${x},${z}`);
  for (const [x, z] of [[75, 15], [69, 18]]) assert.ok(!covered(edge.xz, edge.idx, x, z), `water at ${x},${z}`);
});

test('a ring that repeats its first point at its end is meshed as the ring', () => {
  // closed rings, as shapely writes them: a 100 m square with a 20 m hole, 9600 m² (13,200 when the hole's indices
  // shift by the outer ring's repeat)
  const sq = (x, z, s) => [[x, z], [x + s, z], [x + s, z + s], [x, z + s], [x, z]];
  const w = waterMesh([[sq(0, 0, 100), sq(40, 40, 20)]], [2], triangulate);
  assert.equal(w.xz.length, 2 * 8);
  const { area, up } = plan(w.xz, w.idx);
  assert.ok(up);
  assert.ok(Math.abs(area - 9600) < 1e-6, `${area}`);
  assert.deepEqual([...w.level], new Array(8).fill(2));
  // an open ring (water.bin's own) is unchanged
  const open = waterMesh([[sq(0, 0, 100).slice(0, 4), sq(40, 40, 20).slice(0, 4)]], [2], triangulate);
  assert.deepEqual([...open.xz], [...w.xz]);
  assert.deepEqual([...open.idx], [...w.idx]);
});

// Groups of cells (two by two chunks in the viewer) split the shore cells and the walls into ranges that cull on their
// own: the ranges cover every index once, in order, each group's box holds its vertices, and its bounds hold the
// ground under them (t, and t - cut: the terrace) and the walls' water.
function checkGroups(mesh) {
  const ground = makeGround(T);
  let next = 0;
  for (const g of mesh.groups) {
    assert.equal(g.start, next);
    next += g.count;
    for (let q = g.start; q < g.start + g.count; q++) {
      const v = mesh.idx[q], x = mesh.xz[2 * v], z = mesh.xz[2 * v + 1];
      assert.ok(x >= g.box[0] && x <= g.box[2] && z >= g.box[1] && z <= g.box[3]);
      const t = ground.tAt(x, z), low = t - ground.cutAt(x, z);
      assert.ok(t <= g.hMax + 1e-5 && low >= g.hMin - 1e-5, `ground ${t}, ${low} at ${x},${z} in ${g.hMin}..${g.hMax}`);
      if (mesh.level) assert.ok(mesh.level[v] >= g.hMin && mesh.level[v] <= g.hMax);
    }
    assert.ok(g.hMax >= 2 && g.hMax <= 8);
    assert.ok(g.hMin < g.hMax);
  }
  assert.equal(next, mesh.idx.length);
  return mesh.groups.length;
}

test('the shore cells and the walls come in groups that cull on their own', () => {
  assert.ok(checkGroups(edgeMesh(T, triangulate, 2)) > 1);
  assert.ok(checkGroups(wallMesh(water, T.levels, T.shore, T, 2)) >= 1);
});

test('a water name takes the level of the water it lies on, or of the nearest water', () => {
  assert.equal(levelAt(water, T.levels, 90, 30), T.levels[0]);   // in the bay
  assert.equal(levelAt(water, T.levels, 10, 30), T.levels[0]);   // on land: the nearest (only) water
  const sq = (x, z) => [[[x, z], [x + 10, z], [x + 10, z + 10], [x, z + 10]]];
  const two = [sq(0, 0), sq(100, 0)];
  assert.equal(levelAt(two, [1, 5], 105, 5), 5);
  assert.equal(levelAt(two, [1, 5], 20, 5), 1);
  assert.equal(levelAt([], [], 0, 0), 0);
});

test('the water mesh is the water at its level; walls stand only along shores', () => {
  const w = waterMesh(water, T.levels, triangulate);
  assert.ok(Math.abs(plan(w.xz, w.idx).area - expect.waterArea) < 1e-3 * expect.waterArea);
  assert.ok([...w.level].every(v => Math.abs(v - expect.level) < 1e-6));
  const walls = wallMesh(water, T.levels, T.shore);
  // without the grid, one group with its box and the bounds of its water levels (no ground heights to read)
  assert.deepEqual(walls.groups, [{ start: 0, count: walls.idx.length, box: [55, 10, 100, 50], hMax: T.levels[0], hMin: T.levels[0] }]);
  const shores = expect.shore.filter(Boolean).length;
  assert.equal(walls.idx.length, 6 * shores);
  assert.equal(walls.xz.length, 8 * shores);
  assert.deepEqual([...walls.top.subarray(0, 4)], [0, 0, 1, 1]);
  // the one segment on the domain's edge (x = 100) has no wall
  for (let k = 0; k < walls.xz.length; k += 8) assert.ok(!(walls.xz[k] === 100 && walls.xz[k + 2] === 100));
});

test('a chunk is a whole number of cells that its Uint16 indices and Int16 decimetres can hold', () => {
  for (const n of [undefined, 0, -2, 2.5, NaN, 164]) {   // 164 cells of 20 m: 32,800 dm, past Int16
    assert.throws(() => chunkIndices(T, n), /a chunk of/, `${n}`);
    assert.throws(() => chunkVertices(T, n), /a chunk of/, `${n}`);
  }
  const v = chunkVertices(T, 163);                        // the largest at 20 m: 32,600 dm
  assert.deepEqual([...v.subarray(-3)], [32600, 0, 32600]);
  const fine = { ...T, cell: 1 };                         // at 1 m the indices bind: 256 x 256 nodes at most
  assert.equal(chunkVertices(fine, 255).length, 3 * 256 * 256);
  assert.throws(() => chunkVertices(fine, 256), /a chunk of 256 cells/);
  assert.equal(chunkIndices(T, 120).length, 1);           // the viewer's 2400 m
});

// water.bin's layout (pipeline/s04_base.py pack) from polygons of rings of [x, z].
function packPolygons(polys) {
  const rings = polys.flat(1), ringStart = [0], vertStart = [0];
  for (const p of polys) ringStart.push(ringStart.at(-1) + p.length);
  for (const r of rings) vertStart.push(vertStart.at(-1) + r.length);
  const head = Uint32Array.from([polys.length, rings.length, vertStart.at(-1), ...ringStart, ...vertStart]);
  const xz = Float32Array.from(rings.flat(2)), out = new Uint8Array(head.byteLength + xz.byteLength);
  out.set(new Uint8Array(head.buffer));
  out.set(new Uint8Array(xz.buffer), head.byteLength);
  return out.buffer;
}

// Every ArrayBuffer a value holds, through its objects and arrays.
function buffersIn(value, out = new Set()) {
  if (ArrayBuffer.isView(value)) out.add(value.buffer);
  else if (value instanceof ArrayBuffer) out.add(value);
  else if (value && typeof value === 'object') for (const v of Object.values(value)) buffersIn(v, out);
  return out;
}

test('the worker builds every mesh from the two files and refuses water that does not match', async () => {
  globalThis.self ??= {}; // terrain-worker.js sets self.onmessage when it loads
  const { buildTerrain, transferables } = await import('../terrain-worker.js');
  const m = buildTerrain(file('terrain_v1.bin'), file('water_v1.bin'), { chunkCells: 120, fadeM: 400 });
  assert.deepEqual(m.grid, { x0: T.x0, z0: T.z0, cell: T.cell, nx: T.nx, nz: T.nz, waterZ: 0 });
  assert.equal(m.source, 'contours');
  assert.deepEqual([...m.levels], [...T.levels]);
  assert.equal(m.tex.length, 2 * T.nx * T.nz);
  assert.ok(!('h' in m) && !('cut' in m));                // the page keeps the texture's copy only
  assert.equal(m.fade.length, T.nx * T.nz);
  assert.equal(m.chunks.length, 1);
  assert.ok(m.edge.idx.length > 0 && m.water.idx.length > 0 && m.walls.idx.length > 0);
  assert.ok(m.edge.groups.length >= 1 && m.walls.groups.length >= 1);
  assert.ok(m.chunks.every(c => c.hMin <= c.hMax) && m.edge.groups.every(g => 'hMin' in g) && m.walls.groups.every(g => 'hMin' in g));
  const buffers = transferables(m);
  assert.equal(new Set(buffers).size, buffers.length);    // each transferred once
  // every buffer in the message is transferred, and nothing else
  assert.deepEqual(new Set(buffers), buffersIn(m));
  const opts = { chunkCells: 120, fadeM: 400 };
  const noWater = new Uint32Array([0, 0, 0, 0, 0]).buffer;  // nPoly 0: one level, no polygon
  assert.throws(() => buildTerrain(file('terrain_v1.bin'), noWater, opts), /1 water levels for 0 water polygons/);
  // the same one polygon with a vertex less: the shore bits were made for other water
  assert.deepEqual(new Uint8Array(packPolygons(water)), new Uint8Array(file('water_v1.bin')));
  const triangle = packPolygons([[water[0][0].slice(0, 3)]]);
  assert.throws(() => buildTerrain(file('terrain_v1.bin'), triangle, opts), /4 shore bits for 3 water vertices/);
  assert.throws(() => buildTerrain(file('terrain_v1.bin').slice(0, 40), file('water_v1.bin'), opts),
    /40 bytes, shorter than its 64-byte header/);
  assert.throws(() => buildTerrain(file('terrain_v1.bin'), file('water_v1.bin'), { fadeM: 400 }),
    /a chunk of undefined cells/);
});

test('?fade= takes a finite width in metres, held to 0..FADE_MAX_M; anything else keeps the build\'s own', () => {
  assert.equal(FADE_MAX_M, 5000);
  for (const [q, want] of [['250', 250], ['0', 0], ['-40', 0], ['12000', 5000], ['1e3', 1000], ['5000', 5000]]) {
    assert.equal(fadeWidth(q, 400), want, q);
  }
  // nonsense was a hard edge (0), and Infinity faded the whole ground
  for (const q of [null, '', ' ', 'abc', 'NaN', 'Infinity', '-Infinity', '12m']) assert.equal(fadeWidth(q, 400), 400, String(q));
});

// A stand-in for a Worker: answer(w) decides what it does with the message it is sent.
function fakeWorker(answer) {
  const w = { terminated: false, sent: null, terminate() { this.terminated = true; } };
  w.postMessage = (msg, transfer) => { w.sent = { msg, transfer }; answer(w); };
  return w;
}

test('askWorker resolves with the worker\'s answer and rejects its error, terminating it either way', async () => {
  assert.equal(WORKER_TIMEOUT_MS, 30_000);
  const ok = fakeWorker(w => setTimeout(() => w.onmessage({ data: { ok: true, grid: 1 } }), 1));
  assert.deepEqual(await askWorker(ok, { a: 1 }, ['t'], 1000), { ok: true, grid: 1 });
  assert.deepEqual(ok.sent, { msg: { a: 1 }, transfer: ['t'] });
  assert.ok(ok.terminated);
  const bad = fakeWorker(w => setTimeout(() => w.onmessage({ data: { ok: false, error: 'not a terrain file' } }), 1));
  await assert.rejects(askWorker(bad, {}, [], 1000), /not a terrain file/);
  assert.ok(bad.terminated);
  const broken = fakeWorker(w => setTimeout(() => w.onerror({ message: 'SyntaxError in terrain-worker.js' }), 1));
  await assert.rejects(askWorker(broken, {}, [], 1000), /SyntaxError in terrain-worker\.js/);
  assert.ok(broken.terminated);
});

test('a terrain worker that never answers is given up on, so the flat land can load instead', async () => {
  const hung = fakeWorker(() => {});
  const t0 = performance.now();
  let guard;
  const stillWaiting = new Promise((_, reject) => { guard = setTimeout(() => reject(new Error('still waiting after 2 s')), 2000); });
  await assert.rejects(Promise.race([askWorker(hung, {}, [], 50), stillWaiting]), /gave no answer in 0\.05 s/);
  clearTimeout(guard);
  assert.ok(performance.now() - t0 >= 45);
  assert.ok(hung.terminated);
});

test('withTimeout settles as its job does, or gives up after its time with no sign of life and aborts the job\'s signal', async () => {
  assert.equal(FETCH_TIMEOUT_MS, 30_000);
  let seen;
  assert.equal(await withTimeout(async signal => { seen = signal; return 7; }, 1000, 'terrain.bin.gz'), 7);
  assert.equal(seen.aborted, false);
  await assert.rejects(withTimeout(async () => { throw new Error('HTTP 404'); }, 1000, 'terrain.bin.gz'), /HTTP 404/);
  // a download that stalls: given up on after `ms`, and its signal aborted so the request stops
  const t0 = performance.now();
  let stalled;
  const never = signal => { stalled = signal; return new Promise(() => {}); };
  let guard;
  const stillWaiting = new Promise((_, reject) => { guard = setTimeout(() => reject(new Error('still waiting after 2 s')), 2000); });
  await assert.rejects(Promise.race([withTimeout(never, 50, 'terrain.bin.gz'), stillWaiting]),
    /terrain\.bin\.gz stalled: no data for 0\.05 s/);
  clearTimeout(guard);
  assert.ok(performance.now() - t0 >= 45);
  assert.equal(stalled.aborted, true);
  // a job that shows life (alive(): a chunk arrived) keeps going past `ms`, and one that stops is given up on `ms`
  // after its last sign
  const slow = async (signal, alive) => {
    for (let k = 0; k < 6; k++) { await new Promise(r => setTimeout(r, 25)); alive(); }
    return 'done';
  };
  assert.equal(await withTimeout(slow, 50, 'terrain.bin.gz'), 'done');   // 150 ms in all, never 50 ms without a chunk
  const t1 = performance.now();
  const stops = async (signal, alive) => {
    await new Promise(r => setTimeout(r, 30)); alive();
    return new Promise(() => {});
  };
  await assert.rejects(withTimeout(stops, 50, 'terrain.bin.gz'), /stalled/);
  assert.ok(performance.now() - t1 >= 75);
});

// The final review's VIEWER-2: below about 0.8 Mbps terrain.bin.gz (785 KB) took more than 30 s while it was still
// arriving, and a total-time limit threw it away. fetchGz reports each chunk of the body, so the limit is on silence.
test('a slow, steady download of terrain.bin.gz goes through; a silent one is given up on', async () => {
  const { fetchGz } = await import('../gz.js');
  const realFetch = globalThis.fetch;
  const body = new Uint8Array(1000).map((_, i) => i % 251);
  // the body in 10 chunks, one every `gap` ms; `after` chunks, then silence when given
  const serve = (gap, after = Infinity) => async (url, { signal } = {}) => {
    let k = 0;
    const stream = new ReadableStream({
      async pull(ctl) {
        if (k >= after) return new Promise(() => {});
        await new Promise((resolve, reject) => {
          const t = setTimeout(resolve, gap);
          signal?.addEventListener('abort', () => { clearTimeout(t); reject(signal.reason); });
        });
        if (k === 10) return ctl.close();
        ctl.enqueue(body.slice(100 * k, 100 * k + 100));
        k++;
      },
    });
    return new Response(stream, { status: 200 });
  };
  try {
    globalThis.fetch = serve(20);   // 220 ms in all, a chunk every 20 ms: well over the 60 ms limit, never silent
    const buf = await withTimeout((signal, alive) => fetchGz('terrain.bin.gz', 2, signal, alive), 60, 'terrain.bin.gz');
    assert.deepEqual(new Uint8Array(buf), body);
    globalThis.fetch = serve(20, 3);   // three chunks, then nothing
    await assert.rejects(withTimeout((signal, alive) => fetchGz('terrain.bin.gz', 2, signal, alive), 60, 'terrain.bin.gz'),
      /terrain\.bin\.gz stalled/);
  } finally {
    globalThis.fetch = realFetch;
  }
});
