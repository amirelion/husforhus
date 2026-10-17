// The worker's mesh builder (web/worker.js build), run in node on decoded tiles (contract C4).
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, ATTR_FLOATS } from '../tile.js';

let build;
before(async () => {
  globalThis.self ??= {}; // worker.js sets self.onmessage when it loads
  ({ build } = await import('../worker.js'));
});

const fixture = () => {
  const b = readFileSync(new URL('./fixtures/tile_v1.bin', import.meta.url));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
};

// Area of the mesh seen from above, in dm². Walls are vertical and add nothing, so this is the roof area.
function plan(m) {
  let a = 0;
  for (let k = 0; k < m.idx.length; k += 3) {
    const [p, q, r] = [m.idx[k], m.idx[k + 1], m.idx[k + 2]].map(i => [m.pos[3 * i], m.pos[3 * i + 2]]);
    a += Math.abs((q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1])) / 2;
  }
  return a;
}

test('the fixture tile builds walls and roofs', () => {
  const m = build(parse(fixture()));
  // 15 edges: 4 wall vertices and 6 indices each. Roofs: 4 + 8 + 3 vertices, 2 + 8 + 1 triangles.
  assert.equal(m.bld.length, 15 * 4 + 15);
  assert.equal(m.idx.length, 15 * 6 + 11 * 3);
  assert.equal(plan(m), 10000 + 40000 - 6400 + 1800);
  assert.deepEqual([...m.attr.subarray(0, 4)], [1924, 6 + 16 * 1, 3, 7]);
  // Plan 3: three texels per building (app.js VERT reads the ground from the third), the third [ground dm, 0, 0, 0]
  assert.equal(ATTR_FLOATS, 3 * 4);
  assert.equal(m.attr.length, 3 * ATTR_FLOATS);
  const at = (b, k) => m.attr[b * ATTR_FLOATS + k];
  assert.deepEqual([at(1, 1), at(2, 1)], [1 + 16 * 2, 0 + 16 * 7]);
  assert.deepEqual([at(0, 8), at(1, 8), at(2, 8)], [77, 123, -11]);
  assert.deepEqual([at(0, 9), at(0, 10), at(0, 11)], [0, 0, 0]);
  // the tile's lowest and highest ground and its tallest roof, in decimetres, for the culling box
  assert.deepEqual([m.gMin, m.gMax, m.top], [-11, 123, 210]);
});

test('an empty tile builds nothing and a flat culling range', () => {
  const none = T => new T(0);
  const t = {
    nB: 0, origin: [0, 0], gid: none(Uint32Array), year: none(Int16Array), yflag: none(Uint8Array),
    period: none(Uint8Array), floors: none(Uint8Array), ground: none(Int16Array), lay0: none(Uint32Array),
    lay1: none(Uint32Array), partStart: Uint32Array.of(0), height: none(Float32Array), ringStart: Uint32Array.of(0),
    vertStart: Uint32Array.of(0), hole: none(Uint8Array), xz: none(Int16Array),
  };
  const m = build(t);
  assert.deepEqual([m.pos.length, m.bld.length, m.idx.length, m.attr.length], [0, 0, 0, 0]);
  // not Infinity and -Infinity: app.js boxes the tile with them (web/bounds.js)
  assert.deepEqual([m.gMin, m.gMax, m.top], [0, 0, 0]);
});

test('a MultiPolygon part gets one roof per exterior ring', () => {
  // One building, one part, three rings: square A, square B, and a yard in B (hole = 1 follows its exterior).
  const rings = [
    [[0, 0], [100, 0], [100, 100], [0, 100]],
    [[200, 0], [400, 0], [400, 200], [200, 200]],
    [[260, 60], [340, 60], [340, 140], [260, 140]],
  ];
  const one = (T, v) => T.of(v);
  const t = {
    nB: 1, origin: [0, 0], gid: one(Uint32Array, 5), year: one(Int16Array, 1900), yflag: one(Uint8Array, 0),
    period: one(Uint8Array, 5), floors: one(Uint8Array, 2), ground: one(Int16Array, 0),
    lay0: one(Uint32Array, 0), lay1: one(Uint32Array, 0), partStart: Uint32Array.of(0, 1),
    height: one(Float32Array, 10), ringStart: Uint32Array.of(0, 3), vertStart: Uint32Array.of(0, 4, 8, 12),
    hole: Uint8Array.of(0, 0, 1), xz: Int16Array.from(rings.flat(2)),
  };
  const m = build(t);
  assert.equal(plan(m), 100 * 100 + 200 * 200 - 80 * 80);
  assert.equal(m.idx.length, 12 * 6 + (2 + 8) * 3);
});
