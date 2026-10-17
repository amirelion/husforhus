// The scene player's pure parts (web/scene-player.js): beat timing and lat/lon to the viewer's local frame.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { DEFAULT_BEAT_S, beatDuration, timing, playedS, remainingS, fmtClock, prevBeat, clampBeat, flightS, ease,
  toSweref1800, toLocal, polyline, nearestOn, pointAt, routeLegs, askedScene } from '../scene-player.js';

const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} vs ${b} (±${tol})`);

test('a beat lasts its duration_s, else the default', () => {
  assert.equal(beatDuration({ duration_s: 6 }), 6);
  assert.equal(beatDuration({}), DEFAULT_BEAT_S);
  assert.equal(beatDuration({ duration_s: 0 }), DEFAULT_BEAT_S);
  assert.equal(beatDuration({ duration_s: 'x' }), DEFAULT_BEAT_S);
});

test('timing: starts, total, played and remaining', () => {
  const tm = timing([{ duration_s: 6 }, {}, { duration_s: 4 }]);
  assert.deepEqual(tm.durations, [6, 8, 4]);
  assert.deepEqual(tm.offsets, [0, 6, 14]);
  assert.equal(tm.total, 18);
  assert.equal(playedS(tm, 1, 3), 9);
  assert.equal(playedS(tm, 1, 99), 14, 'a beat never counts past its own end');
  assert.equal(remainingS(tm, 0, 0), 18);
  assert.equal(remainingS(tm, 2, 4), 0);
  assert.equal(fmtClock(65.2), '1:06');
  assert.equal(fmtClock(0), '0:00');
});

test('the Vasa scene runs 61 s over 8 beats', () => {
  const vasa = JSON.parse(fs.readFileSync(new URL('../scenes/vasa-1628.json', import.meta.url)));
  const tm = timing(vasa.beats);
  assert.equal(tm.durations.length, 8);
  assert.equal(tm.total, 61);
  assert.equal(tm.offsets[7], 54);
});

test('previous restarts a beat after 1.5 s, else goes back; beats stay in range', () => {
  assert.equal(prevBeat(3, 2), 3);
  assert.equal(prevBeat(3, 1), 2);
  assert.equal(prevBeat(0, 0), 0);
  assert.equal(clampBeat(-1, 8), 0);
  assert.equal(clampBeat(9, 8), 7);
});

test('the flight takes half a beat, at most 3 s, eased from 0 to 1', () => {
  assert.equal(flightS(4), 2);
  assert.equal(flightS(13), 3);
  assert.equal(ease(0), 0);
  assert.equal(ease(1), 1);
  assert.equal(ease(0.5), 0.5);
  assert.equal(ease(-1), 0);
  assert.equal(ease(2), 1);
  assert.ok(ease(0.1) < 0.1 && ease(0.9) > 0.9, 'slow in and out');
});

test('lat/lon to SWEREF 99 18 00 within a centimetre of pyproj (EPSG:4326 to 3011)', () => {
  // reference values: pyproj Transformer.from_crs(4326, 3011, always_xy=True)
  for (const [lat, lon, e, n] of [[59.3308, 18.0775, 154411.536, 6579522.105], [59.325, 18.071, 154042.225, 6578875.568],
    [59.319, 18.0985, 155608.863, 6578209.156], [59.0, 17.0, 92526.069, 6543099.018]]) {
    const [E, N] = toSweref1800(lat, lon);
    near(E, e, 0.01, 'easting');
    near(N, n, 0.01, 'northing');
  }
});

test('the local frame: x east of the origin, z south of it (pipeline/city.py to_local)', () => {
  const origin = [154025.1, 6578886.7];
  const [x, z] = toLocal(59.325, 18.071, origin);
  near(x, 154042.225 - 154025.1, 0.01);
  near(z, -(6578875.568 - 6578886.7), 0.01);
  const [xn, zn] = toLocal(59.3308, 18.0775, origin);
  assert.ok(xn > x && zn < z, 'further north-east is +x, -z');
});

test('routes: nearest point, a point along, and the legs the marker runs per beat', () => {
  const line = polyline([[0, 0], [100, 0], [100, 100]]);
  assert.equal(line.length, 200);
  assert.deepEqual(nearestOn(line, [50, 10]), { s: 50, d: 10 });
  assert.deepEqual(pointAt(line, 150), [100, 50]);
  assert.deepEqual(pointAt(line, 999), [100, 100]);
  // beat 0 is off the route; beat 2 is behind beat 1 on it, so the marker waits rather than going back
  const legs = routeLegs(line, [[500, 500], [100, 20], [60, 0], [100, 100]]);
  assert.deepEqual(legs, [null, { from: 120, to: 120 }, { from: 120, to: 120 }, { from: 120, to: 200 }]);
});

test('?scene= opens a scene only when features.scenes is on', () => {
  assert.equal(askedScene(true, '?scene=vasa-1628'), 'vasa-1628');
  assert.equal(askedScene(true, '?lang=sv'), null);
  assert.equal(askedScene(false, '?scene=vasa-1628'), null, 'off: the URL is ignored');
  assert.equal(askedScene(undefined, '?scene=vasa-1628'), null, 'a config without the switch counts as off');
});

test('ghosts: shown from their beat to their last; the hull is 69 m long and 12 m wide', async () => {
  const { ghostShown, hullOutline } = await import('../scene-player.js');
  assert.equal(ghostShown({ from: 2 }, 0), false);
  assert.equal(ghostShown({ from: 2 }, 1), true);
  assert.equal(ghostShown({ from: 1, until: 4 }, 4), false);
  const xs = hullOutline().map(p => p[0]), zs = hullOutline().map(p => p[1]);
  assert.equal(Math.max(...xs) - Math.min(...xs), 69);
  assert.equal(Math.max(...zs) - Math.min(...zs), 12);
});

// The three ready stories: every beat's camera looks down on its target at 25° or more (flat ground), and every
// lost building has a shape, a height and a first beat inside the story.
for (const id of ['vasa-1628', 'tre-kronor-1697', 's10-olympics-1912']) {
  test(`${id}: cameras look down at 25° or more; ghosts are drawable`, () => {
    const s = JSON.parse(fs.readFileSync(new URL(`../scenes/${id}.json`, import.meta.url)));
    assert.equal(s.ready, true);
    const origin = [150000, 6580000];
    for (const b of s.beats) {
      const [cx, cz] = toLocal(b.camera.lat, b.camera.lon, origin), [tx, tz] = toLocal(b.target.lat, b.target.lon, origin);
      const down = Math.atan2(b.camera.height_m, Math.hypot(cx - tx, cz - tz)) * 180 / Math.PI;
      assert.ok(down >= 25, `${id} beat ${b.n}: ${down.toFixed(1)}°`);
    }
    const ghosts = s.overlays.filter(o => o.type === 'ghost');
    assert.ok(ghosts.length >= 3, `${id}: ghosts`);
    for (const g of ghosts) {
      assert.ok(g.from >= 1 && g.from <= s.beats.length && g.heights.every(h => h > 0), g.label.en);
      assert.ok(g.ship || g.rings.every(r => r.length >= 4), g.label.en);
    }
  });
}
