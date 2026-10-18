import test from 'node:test';
import assert from 'node:assert/strict';
import { planWalk, walkMapsUrl, stopScore, walkMinutes, DETOUR } from '../walk.js';
import { toSweref, fromSweref, latLonToLocal, localToLatLon } from '../sweref.js';

const ORIGIN = [154025.1, 6578886.7];
// a row of stops every 100 m east of the start, two interests
const row = Array.from({ length: 12 }, (_, i) => ({ id: i, x: (i + 1) * 100, z: 0, kinds: [i % 2 ? 'plaques' : 'landmarks'] }));

test('a loop stays within its distance and comes back', () => {
  const w = planWalk(row, { kinds: [], km: 2, loop: true, stops: 0 }, [0, 0]);
  assert.ok(w.stops.length >= 4 && !w.stretched);
  assert.ok(w.length <= 2000 + 1e-6, `length ${w.length}`);
  assert.deepEqual([w.route[0], w.route.at(-1)].map(p => p.start), [true, true]);
});

test('interests filter the stops, and nothing chosen takes them all', () => {
  assert.equal(stopScore(row[1], ['landmarks']), 0);
  assert.equal(stopScore(row[1], []), 1);
  const w = planWalk(row, { kinds: ['plaques'], km: 3, loop: false, stops: 0 }, [0, 0]);
  assert.ok(w.stops.length && w.stops.every(p => p.kinds.includes('plaques')));
});

test('a walk too short for four stops is stretched, and the stop count is a cap', () => {
  const w = planWalk(row, { kinds: [], km: 0.2, loop: false, stops: 0 }, [0, 0]);
  assert.equal(w.stretched, true);
  assert.ok(w.stops.length >= 4);
  assert.ok(planWalk(row, { kinds: [], km: 8, loop: false, stops: 3 }, [0, 0]).stops.length <= 3);
});

test('the stops come in walking order (2-opt)', () => {
  const w = planWalk(row, { kinds: [], km: 2, loop: false, stops: 0 }, [0, 0]);
  const xs = w.stops.map(p => p.x);
  assert.deepEqual(xs, [...xs].sort((a, b) => a - b));
  assert.ok(walkMinutes(w) > 0 && DETOUR > 1);
});

test('the Google Maps link has at most nine waypoints and walks', () => {
  const many = Array.from({ length: 20 }, (_, i) => ({ id: i, x: (i % 5) * 60, z: Math.floor(i / 5) * 60, kinds: ['a'] }));
  const w = planWalk(many, { kinds: [], km: 8, loop: true, stops: 20 }, [0, 0]);
  const u = new URL(walkMapsUrl(w, p => localToLatLon(p.x, p.z, ORIGIN)));
  assert.equal(u.searchParams.get('travelmode'), 'walking');
  assert.ok(u.searchParams.get('waypoints').split('|').length <= 9);
  assert.equal(u.searchParams.get('origin'), u.searchParams.get('destination'));
});

test('SWEREF 99 18 00 matches pyproj at Stortorget and round-trips', () => {
  // pyproj (EPSG:3011 -> 4326), 2026-10-18: ORIGIN is 59.325100088, 18.070699421; 160000, 6585000 is 59.379877085, 18.175929623
  const [lat, lon] = fromSweref(...ORIGIN);
  assert.ok(Math.abs(lat - 59.325100088) < 1e-7 && Math.abs(lon - 18.070699421) < 1e-7, `${lat} ${lon}`);
  const [lat2, lon2] = fromSweref(160000, 6585000);
  assert.ok(Math.abs(lat2 - 59.379877085) < 1e-7 && Math.abs(lon2 - 18.175929623) < 1e-7);
  const [e, n] = toSweref(lat2, lon2);
  assert.ok(Math.hypot(e - 160000, n - 6585000) < 0.001);
  const [x, z] = latLonToLocal(lat, lon, ORIGIN);
  assert.ok(Math.hypot(x, z) < 0.001);
});
