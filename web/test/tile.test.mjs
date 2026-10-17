// Decoder tests for tile v1 and attrs. The fixture comes from tests/make_tile_fixture.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, readAttrs, MAGIC, ATTR_STRIDE } from '../tile.js';

const fixture = name => {
  const b = readFileSync(new URL(`./fixtures/${name}`, import.meta.url));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
};

// Shoelace area in dm², orientation ignored, and the ring's vertex set, so the test does not depend on the
// writer's ring orientation or start vertex.
function ring(t, r) {
  const pts = [];
  for (let v = t.vertStart[r]; v < t.vertStart[r + 1]; v++) pts.push([t.xz[2 * v], t.xz[2 * v + 1]]);
  let a = 0;
  pts.forEach(([x, z], i) => { const [x2, z2] = pts[(i + 1) % pts.length]; a += x * z2 - x2 * z; });
  return { area: Math.abs(a) / 2, set: pts.map(p => p.join(',')).sort() };
}

test('parse reads the synthetic v1 tile', () => {
  const t = parse(fixture('tile_v1.bin'));
  assert.equal(MAGIC, 0x31484648);
  assert.deepEqual([t.nB, t.nP, t.nR, t.nV], [3, 3, 4, 15]);
  assert.deepEqual(t.origin, [-3000, 1500]);
  assert.deepEqual([...t.gid], [7, 42, 70000]);
  assert.deepEqual([...t.year], [1924, 1650, 0]);
  assert.deepEqual([...t.yflag], [1, 2, 7]);
  assert.deepEqual([...t.period], [6, 1, 0]);
  assert.deepEqual([...t.floors], [3, 6, 1]);
  assert.deepEqual([...t.ground], [77, 123, -11]);
  assert.deepEqual([...t.lay0, ...t.lay1], [0, 0, 0, 0, 0, 0]);
  assert.deepEqual([...t.partStart], [0, 1, 2, 3]);
  assert.deepEqual([...t.height], [12.5, 21, 3]);
  assert.deepEqual([...t.ringStart], [0, 1, 3, 4]);
  assert.deepEqual([...t.vertStart], [0, 4, 8, 12, 15]);
  assert.deepEqual([...t.hole], [0, 0, 1, 0]);
});

test('ring geometry survives in decimetres from the tile origin', () => {
  const t = parse(fixture('tile_v1.bin'));
  const rings = [0, 1, 2, 3].map(r => ring(t, r));
  assert.deepEqual(rings.map(r => r.area), [10000, 40000, 6400, 1800]);
  assert.deepEqual(rings[0].set, ['150,150', '150,50', '50,150', '50,50']);
  assert.deepEqual(rings[2].set, ['360,360', '360,440', '440,360', '440,440']);
  assert.deepEqual(rings[3].set, ['600,100', '600,160', '660,100']);
});

test('parse rejects a buffer that is not a v1 tile', () => {
  const bad = fixture('tile_v1.bin');
  new DataView(bad).setUint32(0, 0x33424241, true); // upstream 'ABB3'
  assert.throws(() => parse(bad), /not a v1 tile/);
  const short = fixture('tile_v1.bin').slice(0, 216);
  assert.throws(() => parse(short), /RangeError|layout says|out of bounds|Invalid/);
});

test('readAttrs decodes one 24-byte record', () => {
  const v = new DataView(new ArrayBuffer(ATTR_STRIDE * 2));
  const o = ATTR_STRIDE;
  v.setUint16(o, 215, true); v.setUint8(o + 2, 1); v.setUint8(o + 3, 1);
  v.setInt16(o + 4, 1927, true); v.setInt16(o + 6, 1924, true); v.setInt16(o + 8, 1927, true);
  v.setUint8(o + 10, 2); v.setUint8(o + 11, 1);
  v.setFloat32(o + 12, -352.5, true); v.setFloat32(o + 16, 48.25, true);
  v.setUint8(o + 20, 5); v.setUint8(o + 21, 6); v.setUint8(o + 22, 1);
  assert.deepEqual(readAttrs(v, 1), {
    gid: 1, height: 21.5, fsrc: 1, yflag: 1, year: 1927, yearFrom: 1924, yearTo: 1927,
    ysrc: 2, rating: 1, x: -352.5, z: 48.25, floors: 5, period: 6, private: 1,
  });
});
