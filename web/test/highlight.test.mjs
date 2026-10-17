// The search pick's outline (web/highlight.js; a look change decided 2026-10-17): two pulses, then steady; quads for
// line segments; a building's triangles out of its tile.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pulseWidth, quads, trianglesOf, BASE_PX, SWELL_PX } from '../highlight.js';

test('the outline swells twice through the arrival and rests at its base width', () => {
  assert.equal(pulseWidth(0), BASE_PX);
  assert.equal(pulseWidth(1), BASE_PX);
  assert.equal(pulseWidth(2), BASE_PX);
  assert.ok(Math.abs(pulseWidth(0.25) - (BASE_PX + SWELL_PX)) < 1e-9);
  assert.ok(Math.abs(pulseWidth(0.75) - (BASE_PX + SWELL_PX)) < 1e-9);
  assert.ok(Math.abs(pulseWidth(0.5) - BASE_PX) < 1e-9);               // between the two pulses
});

test('each segment becomes four corners and two triangles', () => {
  const q = quads(new Float32Array([0, 0, 0, 10, 0, 0, 0, 5, 0, 0, 5, 9]));
  assert.equal(q.a.length, 24);
  assert.deepEqual([...q.a.subarray(0, 3)], [0, 0, 0]);
  assert.deepEqual([...q.b.subarray(0, 3)], [10, 0, 0]);
  assert.deepEqual([...q.corner.subarray(0, 8)], [0, -1, 0, 1, 1, -1, 1, 1]);
  assert.deepEqual([...q.index.subarray(6, 12)], [4, 6, 5, 5, 6, 7]);
});

test("a building's triangles are only its own rows'", () => {
  const pos = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 5, 5, 5, 6, 5, 5]);
  const bld = new Float32Array([0, 0, 0, 1, 1]);
  const idx = new Uint32Array([0, 1, 2, 3, 4, 2]);
  assert.deepEqual([...trianglesOf(pos, bld, idx, 0)], [0, 0, 0, 1, 0, 0, 0, 1, 0]);
  assert.equal(trianglesOf(pos, bld, idx, 1).length, 0);               // a triangle shared with another row is not its own
});
