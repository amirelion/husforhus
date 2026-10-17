// A tile's culling bounds on the terrain (web/bounds.js). Every vertex of the fixture tile is lifted and skirted as the
// vertex shader does it at rest (app.js VERT; terrain-shaders.test.mjs pins those lines), at reliefs up to the most the
// viewer offers, and must lie inside the box and the sphere three.js culls and picks with.
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { BufferAttribute, BufferGeometry, Vector3 } from '../vendor/three.core.js';
import { parse, ATTR_FLOATS } from '../tile.js';
import { liftBounds } from '../bounds.js';

let build;
before(async () => {
  globalThis.self ??= {}; // worker.js sets self.onmessage when it loads
  ({ build } = await import('../worker.js'));
});

const fixture = () => {
  const b = readFileSync(new URL('./fixtures/tile_v1.bin', import.meta.url));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
};

// VERT at rest, positions in decimetres: a vertex rises by its building's ground times the relief r; with the relief
// on, a wall's bottom (y 0) reaches down to the drawn terrain under it (hEff, metres) and 2 m further, plus half of how
// much the drawn ground varies over its cell (hRange, metres).
function lifted(y, groundDm, r, hEff, hRange) {
  const lift = groundDm * r;
  const skirt = y === 0 && r > 0 ? Math.min(hEff * 10 - lift, 0) - 20 - 5 * hRange : 0;
  return y + skirt + lift;
}
// The drawn ground under a wall's corner against the building's own lifted ground, and its cell's range, in metres:
// level with it; 20 m higher (uphill, the cell spanning 30 m); and 30 m lower in a cell spanning 40 m (a steep slope
// at 3x: the box keeps 60 m for the skirts).
const SLOPES = [[0, 0], [20, 30], [-30, 40]];

function outside(m, g, r) {
  const misses = [];
  const p = new Vector3();
  const { center, radius } = g.boundingSphere;
  for (let v = 0; v < m.bld.length; v++) {
    const groundDm = m.attr[m.bld[v] * ATTR_FLOATS + 8];
    for (const [dh, range] of SLOPES) {
      p.set(m.pos[3 * v], lifted(m.pos[3 * v + 1], groundDm, r, groundDm * r / 10 + dh, range), m.pos[3 * v + 2]);
      if (!g.boundingBox.containsPoint(p) || p.distanceTo(center) > radius * (1 + 1e-9)) misses.push(p.toArray());
    }
  }
  return misses;
}

const geometry = m => {
  const g = new BufferGeometry();
  g.setAttribute('position', new BufferAttribute(m.pos, 3));
  return g;
};

test('the lifted buildings and their skirts stay inside the tile\'s box and sphere, at every relief offered', () => {
  const m = build(parse(fixture()));
  assert.ok(m.gMax > 0 && m.gMin < 0, 'the fixture has ground above and below 0');
  for (const reliefMax of [0.5, 1, 2.5, 3]) {
    const g = liftBounds(geometry(m), m, { reliefMax });
    for (const r of [0, reliefMax / 2, reliefMax]) {
      assert.deepEqual(outside(m, g, r), [], `reliefMax ${reliefMax}, relief ${r}`);
    }
    // the highest roof on the highest ground reaches the box's top at the most relief
    assert.ok(g.boundingBox.max.y >= m.gMax * reliefMax + m.top);
  }
  // the Hills slider's every step up to its top, 2.5 (D40): the box made for 2.5 holds each of them
  const g = liftBounds(geometry(m), m, { reliefMax: 2.5 });
  for (const r of [0, 0.5, 1, 1.5, 2, 2.5]) assert.deepEqual(outside(m, g, r), [], `slider at ${r}`);
});

test('without terrain the box still holds the flat tile', () => {
  const m = build(parse(fixture()));
  const g = liftBounds(geometry(m), m, undefined);
  assert.deepEqual(outside(m, g, 0), []);
  assert.equal(g.boundingBox.max.y, m.top);
});
