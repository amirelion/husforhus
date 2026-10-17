// web/codes.js must mirror pipeline/codes.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { YFLAG, YSRC, FSRC, RATING, PROT } from '../codes.js';

const py = readFileSync(new URL('../../pipeline/codes.py', import.meta.url), 'utf8');
// Reads `A, B = 0, 1` and `A = 0` assignments.
const consts = {};
for (const m of py.matchAll(/^([A-Z_][A-Z0-9_]*(?:\s*,\s*[A-Z_][A-Z0-9_]*)*)\s*=\s*(\d+(?:\s*,\s*\d+)*)\s*(?:#.*)?$/gm)) {
  const names = m[1].split(',').map(s => s.trim()), values = m[2].split(',').map(Number);
  names.forEach((n, i) => { consts[n] = values[i]; });
}

test('yflag codes match', () => {
  for (const [k, v] of Object.entries(YFLAG)) assert.equal(consts[k], v, k);
});
test('ysrc codes match', () => {
  for (const [k, v] of Object.entries(YSRC)) assert.equal(consts[`SRC_${k}`], v, k);
});
test('every Python code has its mirror (a code added only in codes.py would go unnoticed otherwise)', () => {
  const flags = ['EXACT', 'RANGE', 'LONG', 'AREA', 'ESTIMATE', 'PERIOD', 'UNKNOWN'];
  for (const k of Object.keys(consts)) {
    if (k.startsWith('SRC_')) assert.ok(k.slice(4) in YSRC, k);
    else if (k.startsWith('FLOORS_')) assert.ok(k.slice(7) in FSRC, k);
    else if (k.startsWith('PROT_')) assert.equal(PROT[k.slice(5)], consts[k], k);
    else if (flags.includes(k)) assert.ok(k in YFLAG, k);
  }
});
test('fsrc codes match', () => {
  assert.equal(consts.FLOORS_OSM, FSRC.OSM);
  assert.equal(consts.FLOORS_HEIGHT, FSRC.HEIGHT);
});
test('rating codes match', () => {
  const body = py.match(/RATING\s*=\s*\{([^}]*)\}/)[1];
  const pyRating = Object.fromEntries([...body.matchAll(/"([^"]+)"\s*:\s*(\d+)/g)].map(m => [m[1], +m[2]]));
  assert.deepEqual(pyRating, { ...RATING });
});
test('protection codes match both ways', () => {
  for (const [k, v] of Object.entries(PROT)) assert.equal(consts[`PROT_${k}`], v, k);
  const body = py.match(/PROTECTION\s*=\s*\{([^}]*)\}/)[1];
  const names = [...body.matchAll(/"([^"]+)"\s*:\s*PROT_([A-Z]+)/g)].map(m => [m[1], PROT[m[2]]]);
  assert.deepEqual(Object.fromEntries(names), { 'Statligt byggnadsminne': 1, 'Byggnadsminne': 2, 'Kyrkligt kulturminne': 3 });
});
