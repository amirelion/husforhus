import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { wrapAngle, shortestTurn, northTurn, turnAt, needleDeg, TURN_MS } from '../north.js';

// The north button (brief 2026-10-15, approved by the owner): the map turns to face north, azimuth 0 in the local frame
// (x east, z south: OrbitControls' theta is atan2(x, z) of the camera's offset from the target, so 0 is the camera
// south of the target, looking north). Only the azimuth changes, the short way round, in about half a second; a
// viewer who asks for less motion gets it at once.
const { PI } = Math;
const near = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-12, `${msg ?? ''} ${a} ≈ ${b}`);

test('an angle wraps into (-π, π]', () => {
  near(wrapAngle(0), 0);
  near(wrapAngle(PI / 2), PI / 2);
  near(wrapAngle(PI), PI);
  near(wrapAngle(-PI), PI);                        // the two ends are one direction: π, never -π
  near(wrapAngle(PI + 0.1), -PI + 0.1);
  near(wrapAngle(-PI - 0.1), PI - 0.1);
  near(wrapAngle(2 * PI), 0);
  near(wrapAngle(7), 7 - 2 * PI);
  near(wrapAngle(-7), -7 + 2 * PI);
  near(wrapAngle(5 * PI + 0.25), -PI + 0.25);
  assert.ok(!Object.is(wrapAngle(-0), -0), 'no -0');
});

test('the turn to north takes the short way round', () => {
  near(shortestTurn(0), 0);
  near(shortestTurn(0.5), -0.5);                   // a little east of north: back the way it came
  near(shortestTurn(-0.5), 0.5);
  near(shortestTurn(3), -3);                       // just short of facing south, either side: still under half a turn
  near(shortestTurn(-3), 3);
  for (const from of [-3.1, -2, -1, 0, 1, 2, 3.1]) assert.ok(Math.abs(shortestTurn(from)) <= PI, String(from));
});

test('the turn wraps at ±π: past the seam it goes the other way, never the long way round', () => {
  // OrbitControls' theta comes from atan2, then damping may add a little: it can sit just past ±π.
  near(shortestTurn(PI + 0.1), PI - 0.1);          // π + 0.1 is -π + 0.1: the short way to 0 is forwards
  near(shortestTurn(-PI - 0.1), -PI + 0.1);
  near(shortestTurn(2 * PI + 0.3), -0.3);          // a full extra turn counts for nothing
  near(shortestTurn(-4 * PI - 0.3), 0.3);
  near(Math.abs(shortestTurn(PI)), PI);            // facing south: half a turn either way
  near(Math.abs(shortestTurn(-PI)), PI);
});

test('a turn eases from where the map faces to exactly north in about half a second', () => {
  assert.ok(TURN_MS >= 400 && TURN_MS <= 600, `about half a second: ${TURN_MS}`);
  const turn = northTurn(2, 1000);
  assert.equal(turn.dur, TURN_MS);
  near(turnAt(turn, 1000).theta, 2);
  assert.equal(turnAt(turn, 1000).done, false);
  near(turnAt(turn, 1000 + TURN_MS / 2).theta, 1, 'halfway in time, halfway round (ease in and out)');
  // Monotone, never past north, never back.
  let was = 2;
  for (let ms = 0; ms <= TURN_MS; ms += 10) {
    const { theta } = turnAt(turn, 1000 + ms);
    assert.ok(theta <= was + 1e-12 && theta >= 0, `${ms} ms: ${theta}`);
    was = theta;
  }
  // The end is exactly north (0, not a rounding error), and stays there.
  for (const at of [1000 + TURN_MS, 1000 + TURN_MS + 1, 1e9]) {
    assert.deepEqual(turnAt(turn, at), { theta: 0, done: true });
  }
});

test('a turn near the seam stays on the short side the whole way', () => {
  const turn = northTurn(-PI + 0.2, 0);             // facing a little east of south: the short way is through east
  for (let ms = 0; ms < TURN_MS; ms += 10) {
    const { theta } = turnAt(turn, ms);
    assert.ok(theta <= 0 && theta >= -PI + 0.2 - 1e-12, `${ms} ms: ${theta}`);
  }
  const past = northTurn(PI + 0.2, 0);              // the same direction, read just past the seam
  for (let ms = 0; ms <= TURN_MS; ms += 50) near(turnAt(past, ms).theta, turnAt(turn, ms).theta, `${ms} ms`);
});

test('a frame stamped a little before the click starts the turn where the map faces', () => {
  // The render loop's time is the frame's start, which can come before performance.now() at the click.
  const turn = northTurn(2, 1000);
  assert.deepEqual(turnAt(turn, 990), { theta: 2, done: false });
});

test('a viewer who asks for less motion turns at once (prefers-reduced-motion)', () => {
  const turn = northTurn(2, 1000, { calm: true });
  assert.equal(turn.dur, 0);
  assert.deepEqual(turnAt(turn, 1000), { theta: 0, done: true });
});

test('already north, the turn is over at once', () => {
  assert.equal(northTurn(0, 5).dur, 0);
  assert.deepEqual(turnAt(northTurn(0, 5), 5), { theta: 0, done: true });
  assert.deepEqual(turnAt(northTurn(2 * PI, 5), 5), { theta: 0, done: true });
});

test('the needle turns with the map: clockwise by the azimuth, in degrees', () => {
  // theta π/2: the camera east of the target looks west, so north is to the right of the screen: the needle turns
  // clockwise (a positive CSS rotate). Rounded to a tenth of a degree, so a still map writes no new style.
  assert.equal(needleDeg(0), 0);
  assert.equal(needleDeg(PI / 2), 90);
  assert.equal(needleDeg(-PI / 2), -90);
  assert.equal(needleDeg(PI), 180);
  assert.equal(needleDeg(-PI), 180);
  assert.equal(needleDeg(3 * PI / 2), -90);
  assert.equal(needleDeg(0.1234), 7.1);
  assert.ok(!Object.is(needleDeg(-1e-9), -0), 'no -0');
});

test('the page has the button, labelled by its id (ui.north) in English and Swedish, and the N key', () => {
  const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  // The tooltip names the key; the label does not (a screen reader reads aria-keyshortcuts for that).
  assert.match(html, /<button class="north-open" aria-label="Face north" title="Face north \(N\)" aria-keyshortcuts="N">/);
  // Plan 4b: app.js's SV_UI table moved to web/i18n by id
  const en = JSON.parse(readFileSync(new URL('../i18n/en.json', import.meta.url), 'utf8'));
  const sv = JSON.parse(readFileSync(new URL('../i18n/sv.json', import.meta.url), 'utf8'));
  assert.equal(en['ui.north'], 'Face north');
  assert.equal(sv['ui.north'], 'Vänd mot norr');
  assert.match(app, /northBtn\.setAttribute\('aria-label', T\('ui\.north'\)\)/);
  assert.match(app, /northBtn\.title = `\$\{T\('ui\.north'\)\} \(N\)`/);
  // The needle's halves are needle-n and needle-s: .n is the legend's numbers.
  assert.match(html, /<path class="needle-n" [^>]*\/><path class="needle-s" [^>]*\/>/);
  const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8');
  assert.match(css, /\.north-open \.needle-n \{/);
  assert.match(css, /\.north-open \.needle-s \{/);
  assert.doesNotMatch(css, /\.north-open \.[ns] \{/);
});

// app.js faceNorth stops the controls' inertia through two of the vendored OrbitControls' (r186) own fields. An
// upgrade that renames them would leave a fling spinning on past north: this says so first.
test("the vendored OrbitControls still keeps its inertia where faceNorth stops it", () => {
  const orbit = readFileSync(new URL('../vendor/OrbitControls.js', import.meta.url), 'utf8');
  assert.match(orbit, /this\._sphericalDelta = new Spherical\(\);/);
  assert.match(orbit, /this\._panOffset = new Vector3\(\);/);
  assert.match(orbit, /this\._spherical\.theta \+= this\._sphericalDelta\.theta \* this\.dampingFactor;/);
  const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  assert.match(app, /controls\._sphericalDelta\.set\(0, 0, 0\);/);
  assert.match(app, /controls\._panOffset\.set\(0, 0, 0\);/);
});
