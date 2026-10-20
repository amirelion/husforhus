// The weather (web/weather.js) and the water's shimmer: the choice and its link, the skies and fog per look, the snow
// and shimmer constants the shaders are written with, the frame rate the flakes are judged by, the factory's easing,
// falling, pausing and flake placement (with three.js itself and a stand-in renderer), and the lines in app.js that put
// them on the map. e2e/weather.spec.mjs checks the page.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as THREE from '../vendor/three.module.js';
import { THEMES } from '../themes.js';
import { rgb, lin, luma, oklab } from '../tone.js';
import { WEATHER, KINDS, NAMES, WEATHER_KEY, initialWeather, weatherHref, weatherSky, skyAt, fogAt, isDark, SNOW, WET,
  snowInk, fallInk, SHIMMER, shimmerRange, FLAKES, flakeCount, SLOW_S, GAP_MS, frameRate, approach, EASE_S, makeWeather }
  from '../weather.js';

const Y = h => { const c = rgb(h).map(lin); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const contrast = (a, b) => { const [lo, hi] = [Y(a), Y(b)].sort((x, y) => x - y); return (hi + 0.05) / (lo + 0.05); };
const L = h => luma(rgb(h));
const chroma = h => { const [, a, b] = oklab(h); return Math.hypot(a, b); };
const rgbSum = (a, b) => rgb(a).reduce((s, v, i) => s + Math.abs(v - rgb(b)[i]) * 255, 0);
const smoothstep = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

test('the kinds: Clear (look.js\'s none), Snow, Rain and Fog, remembered as hfh-weather', () => {
  assert.deepEqual(KINDS, ['none', 'snow', 'rain', 'fog']);
  assert.deepEqual(NAMES, { snow: 'Snow', rain: 'Rain', fog: 'Fog' });
  assert.equal(WEATHER_KEY, 'hfh-weather');
});

test('the first weather: ?weather= wins, then the remembered one, then Clear; nonsense falls through', () => {
  assert.equal(initialWeather('?weather=snow', 'rain'), 'snow');
  assert.equal(initialWeather('?theme=kalk&weather=fog', null), 'fog');
  assert.equal(initialWeather('', 'rain'), 'rain');
  assert.equal(initialWeather('', 'none'), 'none');
  assert.equal(initialWeather('', null), 'none');
  assert.equal(initialWeather('?weather=hail', 'snow'), 'snow');
  assert.equal(initialWeather('?weather=__proto__', 'toString'), 'none');
  assert.equal(initialWeather('?weather=', 'fog'), 'fog');
  assert.equal(initialWeather('?weather=none', 'snow'), 'none');   // the app never writes it (Clear takes it out), but it means Clear
});

test('a switch writes ?weather=<kind> and keeps the other parameters; Clear takes it out', () => {
  assert.equal(weatherHref('https://husforhus.se/?theme=kalk', 'snow'), 'https://husforhus.se/?theme=kalk&weather=snow');
  assert.equal(weatherHref('https://husforhus.se/?weather=snow&theme=kalk', 'rain'), 'https://husforhus.se/?weather=rain&theme=kalk');
  assert.equal(weatherHref('https://husforhus.se/?theme=kalk&weather=fog', 'none'), 'https://husforhus.se/?theme=kalk');
  assert.equal(weatherHref('https://husforhus.se/', 'none'), 'https://husforhus.se/');
  assert.equal(weatherHref('https://husforhus.se/#about', 'fog'), 'https://husforhus.se/?weather=fog#about');
});

test('Clear is the look\'s own sky, exactly; a kind at level 1 is its full sky, and a switch passes between', () => {
  for (const th of Object.values(THEMES)) {
    assert.equal(skyAt(th.sky, {}), th.sky);
    assert.equal(skyAt(th.sky, { snow: 0, rain: 0, fog: 0 }), th.sky);
    assert.equal(weatherSky(th.sky, 'none'), th.sky);
    for (const k of ['snow', 'rain', 'fog']) {
      assert.equal(skyAt(th.sky, { [k]: 1 }), weatherSky(th.sky, k));
      const half = skyAt(th.sky, { [k]: 0.5 });
      const lo = Math.min(L(th.sky), L(weatherSky(th.sky, k))), hi = Math.max(L(th.sky), L(weatherSky(th.sky, k)));
      assert.ok(L(half) >= lo - 1e-9 && L(half) <= hi + 1e-9, `${k}: ${half} lies between`);
    }
  }
});

// The roadmap's point: the pale looks' skies are near white, so white flakes vanish against them. Snow keys the sky to
// a winter blue-grey (a cool grey, under its look's sky), rain to a darker grey, fog to a soft one; the dark look stays dark.
test('snow and rain skies give white flakes something to fall against; the dark look stays dark', () => {
  for (const [name, th] of Object.entries(THEMES)) {
    const snow = weatherSky(th.sky, 'snow'), rain = weatherSky(th.sky, 'rain'), fog = weatherSky(th.sky, 'fog');
    if (isDark(th.sky)) {
      for (const s of [snow, rain, fog]) assert.ok(L(s) < 0.25, `${name}: ${s} stays dark`);
      assert.ok(L(rain) < L(th.sky), `${name}: rain darker`);
      continue;
    }
    assert.ok(contrast('#ffffff', th.sky) < 1.4, `${name}: its own sky is near white`);
    assert.ok(contrast('#ffffff', snow) >= 1.9, `${name}: white on the snow sky ${snow}: ${contrast('#ffffff', snow).toFixed(2)}`);
    assert.ok(L(rain) < L(snow) && L(snow) < L(fog), `${name}: rain darker than snow, fog the palest`);
    const [, , b] = oklab(snow);
    assert.ok(b < 0, `${name}: the snow sky is blue-grey`);
    for (const s of [snow, rain, fog]) assert.ok(chroma(s) < 0.03, `${name}: ${s} is a grey`);
  }
  assert.equal(isDark(THEMES.blatimme.sky), true);
  for (const k of ['arg', 'kalk', 'paper']) assert.equal(isDark(THEMES[k].sky), false);
});

test('fog: Clear keeps the old distances; Fog starts short of the target and is whole before the far plane', () => {
  assert.deepEqual(fogAt({}), [1.6, 4]);           // app.js's uFog before the weather: dist * 1.6 to dist * 4
  for (const k of KINDS) {
    const [a, b] = WEATHER[k].fog;
    assert.ok(a < b, k);
    assert.ok(b <= 4.5, `${k}: whole by the far plane (app.js followGround: far = dist * 4.5)`);
    // the point the camera looks at lies at 1 (its distance): at most a little fogged
    assert.ok(smoothstep(a, b, 1) <= 0.12, `${k}: the target ${(100 * smoothstep(a, b, 1)).toFixed(0)}% fogged`);
  }
  assert.equal(WEATHER.fog.fog[0], 0.7);
  assert.ok(WEATHER.fog.fog[1] < WEATHER.snow.fog[1] && WEATHER.snow.fog[1] < WEATHER.none.fog[1]);
  assert.deepEqual(fogAt({ fog: 1 }), WEATHER.fog.fog);
  const half = fogAt({ fog: 0.5 });
  assert.ok(half[0] < 1.6 && half[0] > 0.7);
});

test('snow lies at most 60% on the roofs, about half that on the ground, in drifts; rain wets both a little', () => {
  assert.equal(SNOW.roof, 0.6);
  assert.ok(SNOW.ground >= 0.25 && SNOW.ground <= 0.35);
  assert.ok(SNOW.patch > 0.3 && SNOW.patch < 1);
  assert.ok(WET.roof > 0 && WET.roof <= 0.2 && WET.ground > 0 && WET.ground <= WET.roof);
  // the snow is lighter than every look's land, so the ground whitens; a blue snow on the dark look
  for (const [name, th] of Object.entries(THEMES)) assert.ok(L(snowInk(th)) > L(th.land), name);
  assert.notEqual(snowInk(THEMES.blatimme), snowInk(THEMES.arg));
  for (const th of Object.values(THEMES)) for (const k of ['snow', 'rain']) {
    const [ink, alpha] = fallInk(th, k);
    assert.match(ink, /^#[0-9a-f]{6}$/);
    assert.ok(alpha > 0 && alpha <= 1);
  }
});

// The shimmer moves the water by a few percent: the water names keep 4.5:1 (themes.test.mjs's rule for the three
// Stockholm looks) even at the rain's strength, no pixel moves by 30 in the RGB sum in Clear weather (e2e/search.spec.mjs
// counts such a pixel as changed), and the colour never moves by more than about 4%.
test('the water shimmer is small: names keep their contrast, no pixel swings by 30, at most about 4%', () => {
  assert.ok(SHIMMER.light * SHIMMER.rain <= 0.042 && SHIMMER.dark * SHIMMER.rain <= 0.042);
  assert.ok(SHIMMER.rain > 1);
  for (const name of ['arg', 'kalk', 'blatimme']) {
    const th = THEMES[name];
    for (const k of [1, SHIMMER.rain]) {
      for (const c of shimmerRange(th.water, k)) {
        assert.ok(contrast(th.waterInk, c) >= 4.5, `${name} ×${k}: ${th.waterInk} on ${c}: ${contrast(th.waterInk, c).toFixed(2)}`);
      }
    }
  }
  for (const [name, th] of Object.entries(THEMES)) {
    const [dark, light] = shimmerRange(th.water, 1);
    assert.ok(rgbSum(dark, light) < 30, `${name}: ${dark} to ${light} swings ${rgbSum(dark, light).toFixed(0)}`);
    assert.notEqual(dark, light, `${name}: the shimmer shows`);
  }
});

test('fewer flakes on a phone, half again when the frame rate drops', () => {
  assert.ok(FLAKES.phone >= 3000 && FLAKES.phone <= 4000);
  assert.ok(FLAKES.desktop >= 12000 && FLAKES.desktop <= 15000);
  assert.equal(flakeCount(), FLAKES.desktop);
  assert.equal(flakeCount({ small: true }), FLAKES.phone);
  assert.equal(flakeCount({ slow: true }), FLAKES.desktop / 2);
  assert.equal(flakeCount({ small: true, slow: true }), FLAKES.phone / 2);
});

// app.js passes frameRate(frameMs), the lengths of the last 60 frames: a hidden tab's first frame back spans the whole
// time away, and a long task is one long frame, so neither may pull the rate under 30.
test('the frame rate leaves out a frame of 250 ms or more, unless most frames are that long', () => {
  assert.equal(GAP_MS, 250);
  assert.equal(frameRate([]), 60);
  const at = (hz, n = 60) => Array(n).fill(1000 / hz);
  assert.ok(Math.abs(frameRate(at(60)) - 60) < 1e-9);
  assert.ok(Math.abs(frameRate([...at(120, 59), 2500]) - 120) < 1e-9, 'a tab back after 2.5 s');
  assert.ok(Math.abs(frameRate([...at(60, 59), 60000]) - 60) < 1e-9, 'a tab back after a minute');
  assert.ok(Math.abs(frameRate([...at(60, 50), ...Array(10).fill(200)]) - 60000 / (50000 / 60 + 2000)) < 1e-9,
    'long frames under 250 ms count');
  assert.ok(frameRate(Array(60).fill(300)) < 4, 'a drawing that slow is that slow');
  assert.ok(frameRate([...Array(40).fill(400), ...at(60, 20)]) < 4);
});

test('approach moves by at most a step and stops on its target', () => {
  assert.equal(approach(0, 1, 0.25), 0.25);
  assert.equal(approach(0.9, 1, 0.25), 1);
  assert.equal(approach(1, 0, 0.25), 0.75);
  assert.equal(approach(0.1, 0, 0.25), 0);
  assert.equal(approach(1, 1, 0.25), 1);
});

// The factory with three.js itself, the app's uniforms as app.js declares them and a stand-in renderer. fps is a
// number, or a function (app.js's frameRate over a window of frames, below).
function rig({ reduced = false, small = false, fps = 60 } = {}) {
  const uniforms = { uSnow: { value: 0 }, uWet: { value: 0 }, uSnowInk: { value: new THREE.Color() },
    uWave: { value: 0 }, uRipple: { value: 1 }, uFog: { value: new THREE.Vector2() } };
  const camera = new THREE.PerspectiveCamera(35, 1400 / 900, 45, 10000);
  camera.position.set(2000, 650, 500);
  const renderer = { getDrawingBufferSize: v => v.set(1400, 900), getPixelRatio: () => 1 };
  const flags = { reduced, small, fps };
  const w = makeWeather(THREE, { uniforms, camera, renderer, reduced: () => flags.reduced, small: () => flags.small,
    fps: () => (typeof flags.fps === 'function' ? flags.fps() : flags.fps) });
  w.retheme(THEMES.arg);
  const target = new THREE.Vector3(0, 0, 0);
  const run = (seconds, dt = 1 / 60) => { let moved = false; for (let t = 0; t < seconds; t += dt) moved = w.step(dt, 2250, target) || moved; return moved; };
  return { w, uniforms, flags, run, target, points: w.group.children[0] };
}

test('Clear settled is no work: nothing falls, the sky and fog are the look\'s, step says nothing moved', () => {
  const { w, uniforms, run, points } = rig();
  assert.equal(w.kind, 'none');
  assert.equal(run(0.5), false);
  assert.equal(points.visible, false);
  assert.equal(points.frustumCulled, false);   // placed by its shader: three.js's culling would drop it
  assert.equal(w.sky(THEMES.arg.sky), THEMES.arg.sky);
  assert.deepEqual(w.fog(), [1.6, 4]);
  assert.equal(uniforms.uSnow.value, 0);
  assert.equal(w.state().particles, 0);
  assert.ok(uniforms.uWave.value > 0, 'the water moves in Clear weather too');
});

test('snow eases in over about a second, flakes fall, and Clear eases it out again', () => {
  const { w, uniforms, run, points } = rig();
  w.set('snow');
  assert.equal(run(EASE_S / 2), true);
  assert.ok(uniforms.uSnow.value > 0.2 && uniforms.uSnow.value < 0.8, `half way: ${uniforms.uSnow.value}`);
  run(EASE_S);
  assert.equal(uniforms.uSnow.value, 1);
  assert.equal(points.visible, true);
  assert.deepEqual(w.state(), { kind: 'snow', snow: 1, wet: 0, fog: WEATHER.snow.fog, paused: false, falling: 'snow',
    particles: FLAKES.desktop, slow: false });
  assert.equal(w.sky(THEMES.arg.sky), weatherSky(THEMES.arg.sky, 'snow'));
  assert.equal(run(0.5), false, 'settled: the sky stands');
  w.set('none');
  run(2 * EASE_S);
  assert.equal(uniforms.uSnow.value, 0);
  assert.equal(points.visible, false);
  assert.equal(w.sky(THEMES.arg.sky), THEMES.arg.sky);
});

test('from snow to rain: the flakes leave before the streaks come; rain wets and stirs the water', () => {
  const { w, uniforms, run } = rig();
  w.set('snow', true);
  w.set('rain');
  run(0.1);
  assert.equal(w.state().falling, 'snow');
  run(0.6);
  assert.equal(w.state().falling, 'rain');
  run(2);
  assert.equal(uniforms.uSnow.value, 0);
  assert.equal(uniforms.uWet.value, 1);
  assert.equal(uniforms.uRipple.value, SHIMMER.rain);
  w.set('fog');
  run(2);
  assert.equal(w.state().falling, null);
  assert.deepEqual(w.fog(), WEATHER.fog.fog);
});

test('a page opened in a weather starts in it at once', () => {
  const { w, uniforms, run } = rig();
  w.set('fog', true);
  assert.deepEqual(w.fog(), WEATHER.fog.fog);
  assert.equal(w.sky(THEMES.kalk.sky), weatherSky(THEMES.kalk.sky, 'fog'));
  w.set('snow', true);
  assert.equal(uniforms.uSnow.value, 1);
  run(1 / 60);
  assert.equal(w.state().falling, 'snow');
  w.set('hail');
  assert.equal(w.kind, 'snow');   // an unknown kind changes nothing
});

test('reduced motion: the weather is there at once, nothing falls, the water stands still', () => {
  const { w, uniforms, run, points } = rig({ reduced: true });
  w.set('snow');
  run(1 / 60);
  assert.equal(uniforms.uSnow.value, 1);
  assert.equal(points.visible, false);
  assert.equal(w.state().particles, 0);
  assert.equal(uniforms.uWave.value, 0);
  assert.equal(w.sky(THEMES.arg.sky), weatherSky(THEMES.arg.sky, 'snow'));
});

test('a phone gets fewer flakes; a frame rate that stays under 30 for two seconds halves them, for good', () => {
  assert.equal(SLOW_S, 2);
  const phone = rig({ small: true });
  phone.w.set('snow', true);
  phone.run(0.1);
  assert.equal(phone.w.state().particles, FLAKES.phone);
  const slow = rig({ fps: 24 });
  slow.w.set('rain', true);
  slow.run(1);
  assert.equal(slow.w.state().particles, FLAKES.desktop);
  slow.run(1.5);
  assert.equal(slow.w.state().particles, FLAKES.desktop / 2);
  slow.flags.fps = 60;
  slow.run(1);
  assert.equal(slow.w.state().slow, true);   // it stays halved: no flicker between the two
  // a dip shorter than two seconds, however deep, is not a slow frame rate
  const dip = rig();
  dip.w.set('snow', true);
  dip.run(3);
  dip.flags.fps = 10;
  dip.run(1.5);
  dip.flags.fps = 60;
  dip.run(3);
  assert.equal(dip.w.state().slow, false);
});

// app.js's loop as it is: each frame's length joins a window of the last 60, frameRate reads it, then the weather
// steps with the frame's length in seconds. Browsers pause the frames of a tab in the background, so the first frame
// back is as long as the visitor was away; before the fix, one such frame halved the flakes for the rest of the visit.
test('one long frame (a tab back from the background, a long task) never halves the flakes', () => {
  for (const hz of [60, 120]) for (const gap of [1100, 1600, 2500, 60000]) {
    const { w, flags, target } = rig();
    const ms = [];
    flags.fps = () => frameRate(ms);
    const frame = len => { ms.push(len); if (ms.length > 60) ms.shift(); w.step(len / 1000, 2250, target); };
    const frames = (seconds, len = 1000 / hz) => { for (let t = 0; t < seconds * 1000; t += len) frame(len); };
    w.set('snow', true);
    frames(4);
    frame(gap);
    frames(10);
    assert.deepEqual([w.state().slow, w.state().particles], [false, FLAKES.desktop], `${hz} Hz, ${gap} ms away`);
  }
  // the factory itself, whatever fps() says: a step three seconds long, at 60 fps before and after
  const { w, run, target } = rig();
  w.set('snow', true);
  run(4);
  w.step(3, 2250, target);
  run(10);
  assert.equal(w.state().slow, false);
  // and a drawing that really is slow, a frame every 300 ms, halves them
  const crawl = rig();
  const ms = [];
  crawl.flags.fps = () => frameRate(ms);
  crawl.w.set('snow', true);
  for (let k = 0; k < 40; k++) { ms.push(300); if (ms.length > 60) ms.shift(); crawl.w.step(0.3, 2250, crawl.target); }
  assert.equal(crawl.w.state().slow, true);
});

test('pause holds the water and the flakes still for a test, and the phases wrap', () => {
  const { w, uniforms, run, points } = rig();
  w.set('snow', true);
  run(0.2);
  w.pause(true);
  const wave = uniforms.uWave.value, fall = points.material.uniforms.uT.value;
  run(0.5);
  assert.equal(uniforms.uWave.value, wave);
  assert.equal(points.material.uniforms.uT.value, fall);
  assert.equal(w.state().paused, true);
  w.pause(false);
  run(0.2);
  assert.ok(uniforms.uWave.value > wave);
  uniforms.uWave.value = 0.99999;
  run(0.1);
  assert.ok(uniforms.uWave.value >= 0 && uniforms.uWave.value < 1);
});

test('the flakes\' box sits on the target, reaches above the camera and scales with the distance', () => {
  const { w, run, points } = rig();
  w.set('snow', true);
  run(1 / 60);
  const u = points.material.uniforms;
  const mid = u.uBoxMin.value.clone().addScaledVector(u.uBoxSize.value, 0.5);
  assert.ok(Math.abs(mid.x) < 1e-6 && Math.abs(mid.z) < 1e-6, 'centred on the target');
  assert.ok(u.uBoxMin.value.y + u.uBoxSize.value.y > 650, 'above the camera');
  assert.ok(u.uBoxSize.value.x > 2 * 2250, 'wider than the camera is far');
  assert.ok(u.uNear.value >= 45, 'never in front of the near plane');
});

// FLAKE_VERT's placement across the box, as the shader has it (pinned below): rain, so no sway.
const weatherSrc = readFileSync(new URL('../weather.js', import.meta.url), 'utf8');
const fract = x => x - Math.floor(x);
function flakesXZ(points) {
  const u = points.material.uniforms, seeds = points.geometry.attributes.position.array, out = [];
  for (let i = 0; i < 3000; i++) {
    const s = [fract(seeds[3 * i] + u.uPhase.value.x), fract(seeds[3 * i + 2] + u.uPhase.value.y)];
    out.push([u.uBoxMin.value.x + s[0] * u.uBoxSize.value.x, u.uBoxMin.value.z + s[1] * u.uBoxSize.value.z]);
  }
  return out;
}

test('the flakes keep their places: a pan moves the camera through them, a zoom spreads them from the target', () => {
  assert.match(weatherSrc, /vec2 s = fract\(position\.xz \+ uPhase \+ \(1\.0 - uRain\) \* 0\.004/);
  assert.match(weatherSrc, /vec3 w = vec3\(uBoxMin\.x \+ s\.x \* uBoxSize\.x, uBoxMin\.y \+ fy \* uBoxSize\.y, uBoxMin\.z \+ s\.y \* uBoxSize\.z\);/);
  assert.match(weatherSrc, /vec2 e = abs\(2\.0 \* s - 1\.0\);/);
  assert.doesNotMatch(weatherSrc, /mod\(p\.x - uBoxMin\.x/);   // the world's origin no longer anchors the pattern
  const { w, points } = rig();
  w.set('rain', true);
  // far from Stortorget, where an origin-anchored pattern slid several hundred metres a notch
  const target = new THREE.Vector3(6000, 0, -4000);
  w.step(1 / 60, 320, target);
  const before = flakesXZ(points), size0 = points.material.uniforms.uBoxSize.value.x;
  // a zoom in by a tenth: each flake moves towards the target by its share of the box's change, at most half of it
  w.step(1 / 60, 288, target);
  const zoomed = flakesXZ(points), shrink = size0 - points.material.uniforms.uBoxSize.value.x;
  const most = Math.max(...before.map((b, i) => Math.hypot(b[0] - zoomed[i][0], b[1] - zoomed[i][1])));
  assert.ok(most <= 0.5 * Math.SQRT2 * shrink + 1e-6, `a flake moved ${most.toFixed(1)} m for a box ${shrink} m smaller`);
  // a pan: every flake stays where it is in the world, or wraps by a whole box to the side the camera goes
  target.x += 137.5; target.z -= 59.25;
  w.step(1 / 60, 288, target);
  const size = points.material.uniforms.uBoxSize.value.x, panned = flakesXZ(points);
  let stayed = 0;
  zoomed.forEach((z, i) => {
    for (const k of [0, 1]) {
      const d = Math.abs(panned[i][k] - z[k]);
      assert.ok(d < 1e-6 || Math.abs(d - size) < 1e-6, `flake ${i} moved ${d} m`);
    }
    if (Math.hypot(panned[i][0] - z[0], panned[i][1] - z[1]) < 1e-6) stayed++;
  });
  assert.ok(stayed > 0.7 * zoomed.length, `${stayed} of ${zoomed.length} stayed put`);
  // hidden and shown again: the pattern starts from where it is, not from a pan across the gap
  w.set('fog', true);
  w.step(1 / 60, 288, target);
  const phase = points.material.uniforms.uPhase.value.clone();
  target.x += 5000;
  w.set('rain', true);
  w.step(1 / 60, 288, target);
  assert.deepEqual(points.material.uniforms.uPhase.value.toArray(), phase.toArray());
});

// app.js: the shaders and hooks that put the weather and the shimmer on the map. A headless browser cannot judge a
// shimmer of 3%, so its lines are pinned here, as web/test/terrain-shaders.test.mjs pins the terrain's.
const src = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const glsl = {};
for (const [, name, body] of src.matchAll(/const (\w+) = \/\* glsl \*\/`([\s\S]*?)`;/g)) glsl[name] = body;
const lines = (...ls) => new RegExp(ls.map(l => l.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('(?:\\s|//[^\\n]*)*'));

test('the water shimmers in TERRAIN_FRAG\'s water branch, before the edge and distance fades', () => {
  assert.match(glsl.TERRAIN_FRAG, /\$\{WEATHER_GLSL\}\s*\$\{WAVE_GLSL\}/);   // the shimmer uses WEATHER_GLSL's hash
  assert.match(glsl.TERRAIN_FRAG, lines(
    '} else {',
    'c = shimmer(c, vWorld.xz, length(vWorld - cameraPosition));',
    '}',
    'c = mix(uFogColor, c, fadeAt(vWorld.xz));',
    'c = mix(c, uFogColor, smoothstep(uFog.x, uFog.y, length(vWorld - cameraPosition)));',
  ));
  // two fields, tiled and moved by whole tiles per turn of uWave, faded where they would alias and far off
  assert.equal([...glsl.WAVE_GLSL.matchAll(/rippleField\(w, vec2\([-\d., ]+\), [\d.]+, -?\d+\.0\)/g)].length, 2);
  assert.match(glsl.WAVE_GLSL, /p\.x -= 32\.0 \* tiles \* uWave;/);
  assert.match(glsl.WAVE_GLSL, /mod\(i, 32\.0\)/);
  assert.match(glsl.WAVE_GLSL, /smoothstep\([\d.]+, [\d.]+, length\(fwidth\(p\)\)\)/);
  assert.match(glsl.WAVE_GLSL, /1\.0 - smoothstep\(1500\.0, 2500\.0, d\)/);
  // its strength from web/weather.js SHIMMER, the numbers tested above
  assert.match(glsl.WAVE_GLSL, /\$\{glf\(SHIMMER\.light\)\} \* uRipple/);
  assert.match(glsl.WAVE_GLSL, /\$\{glf\(SHIMMER\.dark\)\} \* uRipple/);
  assert.doesNotMatch(glsl.WAVE_GLSL, /\bsin\(/);   // value noise: nothing loses precision 17 km out
});

test('snow and rain in the buildings\' FRAG: roofs only, after the light and before the fog; pick and faint untouched', () => {
  assert.match(glsl.FRAG, lines(
    '#ifdef PICK',
    'float id = vGid + 1.0;',
    'outColor = vec4(mod(id, 256.0), mod(floor(id / 256.0), 256.0), floor(id / 65536.0), 255.0) / 255.0;',
    '#elif defined(FAINT)',
    'outColor = vec4(uFaintColor, uFaint);',
    '#else',
  ));
  assert.match(glsl.FRAG, lines(
    'vec3 c = base * light * foot;',
    'float flatTop = smoothstep(0.85, 0.95, n.y);',
    'c *= 1.0 - ${glf(WET.roof)} * uWet * flatTop;',
    'if (uSnow > 0.0) {',
    'float lie = uSnow * ${glf(SNOW.roof)} * flatTop * step(-0.5, vLit) * mix(${glf(SNOW.patch)}, 1.0, drift(vWorld.xz));',
    'c = mix(c, mix(uSnowInk, uHoverTo, 0.35 * max(vLit, 0.0)), lie);',
    '}',
    'c = mix(uFogColor, c, mix(1.0, fadeAt(vWorld.xz), uEdgeBuildings));',
  ));
  // the hover mark travels to the roof's snow: the same 35% as the vertex shader's hover mix; the quest's red building is
  // marked after the hover, so the pointer over it never brings the snow back onto its roof
  assert.match(glsl.VERT, lines('vLit = 0.0;', 'if (vGid == uHover || (vGid == uSelected && uBlind < 0.5)) {',
    'c = mix(c, uHoverTo, 0.35);', 'h = mix(h, uHoverTo, 0.35);', 'vLit = 1.0;', '}',
    'if (uBlind > 0.5 && vGid == uSelected) vLit = -1.0;'));
  assert.equal([...glsl.VERT.matchAll(/vLit = /g)].length, 3);
  assert.match(glsl.TERRAIN_FRAG, lines('c = shaded(c, normalize(vNormal));', 'c = weatherGround(c, vWorld.xz);'));
  assert.match(glsl.WEATHER_GLSL, /\$\{glf\(SNOW\.ground\)\}/);
});

test('the weather\'s uniforms are declared up front, and the hooks: one sky, the pick pass, the fog, the loop', () => {
  const literal = src.slice(src.indexOf('const uniforms = {'), src.indexOf('};', src.indexOf('const uniforms = {')));
  for (const u of ['uSnow', 'uWet', 'uSnowInk', 'uWave', 'uRipple']) assert.match(literal, new RegExp(`\\b${u}: \\{ value:`), u);
  // nothing new in the pick pass, and the sky put back is the weather's
  const pick = src.slice(src.indexOf('function pick(x, y) {'), src.indexOf('\n}\n', src.indexOf('function pick(x, y) {')));
  const render = pick.indexOf('renderer.render(scene, camera);'), hide = pick.indexOf('weather.group.visible = false;');
  assert.ok(render > 0);
  assert.ok(hide >= 0 && hide < render, 'pick() hides the flakes before it renders');
  assert.ok(pick.indexOf('weather.group.visible = true;') > render, 'and shows them again after');
  assert.match(pick, /renderer\.setClearColor\(skyNow\(\), 1\);/);
  // the sky's one source; the look's own sky reaches the clear colour and the fog only through it
  assert.match(src, lines('const skyNow = () => weather.sky(THEME.sky);', 'function applySky() {', 'const sky = skyNow();',
    'renderer.setClearColor(sky);', 'uniforms.uFogColor.value.set(sky);'));
  assert.doesNotMatch(src, /uFogColor\.value\.set\(THEME\.sky\)|setClearColor\(THEME\.sky, 1\)/);
  assert.match(src, lines('if (weather.step(dt, dist, controls.target)) applySky();', 'const [fogNear, fogFar] = weather.fog();',
    'uniforms.uFog.value.set(dist * fogNear, dist * fogFar);'));
  // the flakes are judged by the frame rate without its gaps (frameRate, tested above)
  assert.match(src, /fps: \(\) => frameRate\(frameMs\)/);
});

// The street names lie on the ground, so they fog as it does: in Fog the far names go grey with the city.
test('names fade into the fog by the same distances as the ground under them', () => {
  const label = src.slice(src.indexOf('function labelMaterial('), src.indexOf('\n}\n', src.indexOf('function labelMaterial(')));
  assert.match(label, /s\.uniforms\.uFog = uniforms\.uFog;/);   // the shared uniform the loop sets from weather.fog()
  assert.match(label, lines('float dEye = length(mvPosition.xyz);', 'vDEye = dEye;'));
  assert.match(label, lines("s.fragmentShader.replace('#include <map_fragment>', `#include <map_fragment>",
    'diffuseColor.a *= 1.0 - smoothstep(uFog.x, uFog.y, vDEye);'));
  // and three.js's basic material still has the line it is put after
  const three = readFileSync(new URL('../vendor/three.module.js', import.meta.url), 'utf8');
  assert.match(three, /fragment\$a="uniform vec3 diffuse;[^"]*#include <map_fragment>/);
});
