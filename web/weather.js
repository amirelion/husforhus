// The weather over the map (spec 2026-10-20, features 1 and 4): Clear, Snow, Rain or Fog, chosen in the Look panel's
// Weather row (web/look.js atmospheres, web/switcher.js), and the water's slow shimmer, which is always on. app.js
// registers the three kinds as atmospheres, gives the shared uniforms to makeWeather, calls step() from its loop, takes
// the sky from sky() (skyNow) and the fog's distances from fog(), and hides `group` in the pick pass. The buildings'
// and the terrain's shaders read uSnow, uWet, uSnowInk, uWave and uRipple, with the constants below (SNOW, WET,
// SHIMMER) written into them, so the numbers tested here are the numbers drawn.
//
// Snow whitens the roofs and, less, the ground, keys the sky to a winter blue-grey and lets flakes fall; rain darkens
// roofs and ground a little (wet), greys the sky and draws thin falling streaks; fog greys the sky and pulls the fog in
// to just past the point the camera looks at. A switch eases over about a second, at once under reduced motion, where
// nothing falls and the water stands still. The falling flakes are one THREE.Points whose motion is all in its shader.
// Remembered as localStorage hfh-weather; ?weather=snow|rain|fog in a link wins, and Clear takes it out of the address.
// Pure helpers tested by web/test/weather.test.mjs; e2e/weather.spec.mjs checks the page.
import { rgb, hex, luma } from './tone.js';

export const WEATHER_KEY = 'hfh-weather';

// Per kind: the sky's target on a light look and on the dark one (Blå timmen), how far the look's sky moves towards it,
// the fog's start and end as multiples of the camera's distance to its target (app.js sets uFog from them every frame),
// and what falls. The pale looks' skies are near white, so white flakes would vanish against them: snow takes the sky
// down to a winter blue-grey, and the dark look's sky goes to a dark one, so it stays dark. Fog starts at 0.7 of the
// distance, so the building the camera looks at stays clear (about a tenth fogged), and is whole at 2.2.
export const WEATHER = {
  none: { fog: [1.6, 4] },
  snow: { light: '#8c98a7', dark: '#2b3749', mix: 0.6, fog: [1.1, 3.2], falls: 'snow' },
  rain: { light: '#6f7984', dark: '#0b1018', mix: 0.7, fog: [1.0, 3.0], falls: 'rain' },
  fog: { light: '#c3c8cc', dark: '#353e4a', mix: 0.85, fog: [0.7, 2.2] },
};
export const KINDS = Object.keys(WEATHER);
// The kinds the Look panel lists after Clear (web/look.js's own 'none'), by the English names app.js's t() translates.
export const NAMES = { snow: 'Snow', rain: 'Rain', fog: 'Fog' };

// The first weather: ?weather= wins (a shared link shows what its sender saw), then the visitor's remembered choice,
// then Clear. A name that is not a kind falls through, as look.js initialLook does.
export function initialWeather(search, stored, ids = KINDS) {
  const q = new URLSearchParams(search).get('weather');
  if (ids.includes(q)) return q;
  if (ids.includes(stored)) return stored;
  return 'none';
}
// The address after a switch: ?weather=<kind>, the other parameters kept; Clear takes the parameter out.
export function weatherHref(href, kind) {
  const u = new URL(href);
  if (kind === 'none' || !WEATHER[kind]) u.searchParams.delete('weather');
  else u.searchParams.set('weather', kind);
  return String(u);
}

const mixHex = (a, b, k) => { const p = rgb(a), q = rgb(b); return hex(p.map((v, i) => v + (q[i] - v) * k)); };
// A look is dark when its sky is (Blå timmen's luma is 0.11, the light looks' 0.86 to 0.91).
export const isDark = sky => luma(rgb(sky)) < 0.4;
// The sky in full weather, for a look's sky.
export const weatherSky = (sky, kind) => {
  const w = WEATHER[kind];
  return w?.mix ? mixHex(sky, isDark(sky) ? w.dark : w.light, w.mix) : sky;
};
// The sky now: the look's sky moved towards each kind's by how far that kind has come in (levels: 0 to 1 per kind;
// two are above 0 only during a switch). The look's own sky, exactly, when the weather is Clear.
export function skyAt(sky, levels = {}) {
  let out = sky;
  for (const k of KINDS) if (levels[k] > 0) out = mixHex(out, weatherSky(sky, k), Math.min(1, levels[k]));
  return out;
}
// The fog's two factors now, by the same levels.
export function fogAt(levels = {}) {
  const f = [...WEATHER.none.fog];
  for (const k of KINDS) {
    const l = Math.min(1, Math.max(0, levels[k] || 0));
    if (l > 0) for (const i of [0, 1]) f[i] += (WEATHER[k].fog[i] - f[i]) * l;
  }
  return f;
}

// Snow on the map (app.js WEATHER_GLSL): a roof whitens towards the look's snow by at most `roof` (the spec's 60%),
// in drifts that leave the thinnest part at `patch` of that, so a roof is never a flat white; the ground by `ground`,
// about half the roofs'. Rain darkens roofs and ground by WET (wet stone and asphalt). Snow is a cool white on the
// light looks and a blue one on the dark look, where full white would glare.
export const SNOW = { roof: 0.6, ground: 0.32, patch: 0.55 };
export const WET = { roof: 0.14, ground: 0.1 };
export const snowInk = theme => (isDark(theme.sky) ? '#bccadd' : '#f6f9fc');
// The falling flakes and streaks per look: their colour and opacity.
export function fallInk(theme, kind) {
  const dark = isDark(theme.sky);
  if (kind === 'rain') return dark ? ['#8ea4c2', 0.5] : ['#eef3f8', 0.55];
  return dark ? ['#e4ebf5', 0.95] : ['#ffffff', 0.95];
}

// The water's shimmer (app.js WAVE_GLSL): ripple crests lighten the water towards white by at most `light`, troughs
// darken it by at most `dark`, and rain makes both `rain` times stronger. Small on purpose: the water names keep their
// contrast (web/test/themes.test.mjs holds waterInk to 4.5:1 on the water), no pixel moves by 30 (the RGB sum
// e2e/search.spec.mjs counts as a change), and the colour never moves by more than about 4%.
export const SHIMMER = { light: 0.028, dark: 0.02, rain: 1.35 };
// The water's darkest and lightest colours under the shimmer, k times as strong (1, or SHIMMER.rain in the rain).
export function shimmerRange(water, k = 1) {
  const c = rgb(water);
  return [hex(c.map(v => v * (1 - SHIMMER.dark * k))), hex(c.map(v => v + (1 - v) * SHIMMER.light * k))];
}
// The water's motion: uWave is a phase from 0 to 1 over WAVE_S seconds, wrapped (each ripple field moves a whole
// number of its tiles per turn, so the wrap moves nothing, at about half a metre a second); likewise the flakes' fall
// over FALL_S (each flake falls a whole number of box heights per turn).
export const WAVE_S = 300;
export const FALL_S = 60;

// How many flakes fall: fewer on a phone (a narrow screen or a coarse pointer), half again when the frame rate has
// stayed under 30 for SLOW_S seconds while they fall.
export const FLAKES = { phone: 3500, desktop: 14000 };
export const flakeCount = ({ small = false, slow = false } = {}) =>
  Math.round((small ? FLAKES.phone : FLAKES.desktop) / (slow ? 2 : 1));
export const SLOW_S = 2;
// The frame rate the flakes are judged by, from the lengths in ms of the last frames (app.js frameMs). A frame of
// GAP_MS or more is left out: the browser pauses the frames of a tab in the background, so the first frame back spans
// the whole time away, and one long task (a pack decoding) is one frame; neither is the pace of the drawing, and either
// would pull the mean of 60 frames under 30 for a second. When most frames are that long they all count: the drawing
// really is that slow. 60 before there is a frame.
export const GAP_MS = 250;
export function frameRate(ms) {
  const paced = ms.filter(m => m < GAP_MS), use = 2 * paced.length >= ms.length ? paced : ms;
  return use.length ? 1000 * use.length / use.reduce((a, b) => a + b, 0) : 60;
}

// A switch eases over EASE_S seconds; falling flakes leave in OUT_S before another kind's start.
export const EASE_S = 1;
const OUT_S = 0.4;
// From a to b by at most `step`.
export const approach = (a, b, step) => (a < b ? Math.min(b, a + step) : Math.max(b, a - step));
const smooth = x => x * x * (3 - 2 * x);
const fract = x => x - Math.floor(x);

// The flakes live in a box on the camera's target, BOX.half of the camera's distance to each side and at least
// BOX.high of it tall (always above the camera), so they fill the view at any zoom. Their size is in world metres per
// metre of that distance, so they read about the same at every zoom, clamped in pixels. Across the box each flake
// sits at its seed plus a phase (uPhase, 0 to 1 a side) that step() moves against the target's pans, so a pan moves
// the camera through flakes that stay put in the world, and a zoom, which changes only the box's size, spreads them out
// from the target or draws them in, with the view. Anchored to the world's origin instead, every flake would slide
// sideways by the target's distance from Stortorget times the zoom's share, several box widths a notch far from Gamla
// stan.
const BOX = { half: 1.25, high: 0.6, low: 0.05 };
const FALL = {
  snow: { size: 0.003, px: [1, 7], speed: [3, 6] },     // a flake 1-7 px; 3 to 6 box heights a minute
  rain: { size: 0.011, px: [5, 26], speed: [45, 70] },  // a streak 5-26 px tall; 45 to 70 box heights a minute
};

const FLAKE_VERT = /* glsl */`
  in float aRand;
  uniform vec3 uBoxMin, uBoxSize;
  uniform float uT, uRain, uSize, uPx, uPr, uNear, uSpeed0, uSpeed1;
  uniform vec2 uFog, uClamp, uPhase;
  out float vAlpha;
  out float vSize;
  const float TAU = 6.2831853;
  void main() {
    // Each flake falls a whole number of box heights per turn of uT (FALL_S), so the turn's wrap moves none of them.
    float k = floor(mix(uSpeed0, uSpeed1 + 1.0, aRand));
    float fy = fract(position.y - uT * k);
    // Across the box, 0 to 1: the seed moved by the phase (step() keeps the flakes put in the world as the target pans)
    // and, for snow, a sway, a whole number of times per turn; rain falls straight. Nothing here is kilometres large,
    // so the flakes keep their places 17 km from the origin too.
    vec2 s = fract(position.xz + uPhase + (1.0 - uRain) * 0.004
      * vec2(sin(TAU * fract(uT * 13.0 + aRand)), cos(TAU * fract(uT * 11.0 + aRand * 1.7))));
    vec3 w = vec3(uBoxMin.x + s.x * uBoxSize.x, uBoxMin.y + fy * uBoxSize.y, uBoxMin.z + s.y * uBoxSize.z);
    vec2 e = abs(2.0 * s - 1.0);
    float edge = (1.0 - smoothstep(0.8, 1.0, max(e.x, e.y))) * smoothstep(0.0, 0.06, fy) * (1.0 - smoothstep(0.92, 1.0, fy));
    vec4 mv = modelViewMatrix * vec4(w, 1.0);
    float z = -mv.z;
    float px = uSize * (0.6 + 0.8 * fract(aRand * 7.31)) * uPx / max(z, 1e-3);
    // None right at the camera (they would fill the screen), fewer and fainter with distance, gone in the fog.
    vAlpha = edge * smoothstep(uNear, 4.0 * uNear, z) * (1.0 - smoothstep(uFog.x, uFog.y, length(mv.xyz)))
      * clamp(px / uClamp.x, 0.0, 1.0);
    vSize = clamp(px, uClamp.x, uClamp.y) * uPr;
    gl_PointSize = vSize;
    gl_Position = projectionMatrix * mv;
  }
`;
const FLAKE_FRAG = /* glsl */`
  precision highp float;
  uniform vec3 uInk;
  uniform float uAmount, uAlpha, uRain, uPr;
  in float vAlpha;
  in float vSize;
  out vec4 outColor;
  void main() {
    vec2 q = gl_PointCoord - 0.5;
    float a;
    if (uRain > 0.5) {
      // a streak about one CSS pixel wide down the middle, thinning out towards both ends
      float w = 0.5 * uPr / vSize;
      a = (1.0 - smoothstep(w, w + 1.0 / vSize, abs(q.x))) * (1.0 - smoothstep(0.15, 0.5, abs(q.y)));
    } else {
      // a round flake, its rim soft over about a pixel, so even a flake two pixels wide shows whole
      a = clamp((0.5 - length(q)) * vSize / uPr + 0.5, 0.0, 1.0);
    }
    a *= vAlpha * uAmount * uAlpha;
    if (a < 0.004) discard;
    outColor = vec4(uInk, a);
  }
`;

// A fixed sequence (mulberry32), so the snow falls the same way on every visit and in every test.
function random(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// uniforms: app.js's shared uniforms (uSnow, uWet, uSnowInk, uWave, uRipple and uFog are read and written here);
// camera, renderer: the map's. reduced(): the visitor asks for less motion; small(): a phone; fps(): the recent frame
// rate (app.js: frameRate of its last frames). Returns { group, set(kind, instant), step(dt, dist, target),
// sky(lookSky), fog(), retheme(theme), pause(on), state(), kind }. step() returns true while the sky or the fog moves,
// so app.js re-applies them only then.
export function makeWeather(THREE, { uniforms, camera, renderer, reduced = () => false, small = () => false, fps = () => 60 }) {
  const n = FLAKES.desktop;
  const seeds = new Float32Array(n * 3), rand = new Float32Array(n);
  const r = random(1729);
  for (let i = 0; i < n; i++) { seeds[3 * i] = r(); seeds[3 * i + 1] = r(); seeds[3 * i + 2] = r(); rand[i] = r(); }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(seeds, 3));
  geo.setAttribute('aRand', new THREE.BufferAttribute(rand, 1));
  const u = {
    uBoxMin: { value: new THREE.Vector3() }, uBoxSize: { value: new THREE.Vector3(1, 1, 1) },
    uPhase: { value: new THREE.Vector2() }, uT: { value: 0 }, uRain: { value: 0 }, uSize: { value: 1 }, uPx: { value: 1 },
    uPr: { value: 1 }, uNear: { value: 1 },
    uSpeed0: { value: 3 }, uSpeed1: { value: 6 }, uClamp: { value: new THREE.Vector2(1, 6) }, uFog: uniforms.uFog,
    uInk: { value: new THREE.Color('#ffffff') }, uAmount: { value: 0 }, uAlpha: { value: 1 },
  };
  const material = new THREE.ShaderMaterial({ glslVersion: THREE.GLSL3, vertexShader: FLAKE_VERT,
    fragmentShader: FLAKE_FRAG, uniforms: u, transparent: true, depthWrite: false });
  const points = new THREE.Points(geo, material);
  points.name = 'weather-flakes';
  points.frustumCulled = false;   // placed by the shader around the camera's target, never where the geometry says
  points.visible = false;
  points.renderOrder = 6;         // over the names and the metro, under the markers drawn without depth
  const group = new THREE.Group();
  group.name = 'weather';
  group.add(points);

  let kind = 'none', paused = false, slow = false, drawn = null, amount = 0, lowFor = 0, theme = null;
  const levels = { snow: 0, rain: 0, fog: 0 };
  // The target the phase was last moved for, and the box's size then (0: none yet, as after the flakes were hidden).
  const last = new THREE.Vector2();
  let lastSize = 0;
  let fogNow = fogAt(levels);
  const buffer = new THREE.Vector2();

  // The kind the switcher chose; `instant` (a page opened in it, or reduced motion) skips the ease.
  function set(next, instant = false) {
    if (!WEATHER[next]) return;
    kind = next;
    if (instant) {
      for (const k of Object.keys(levels)) levels[k] = k === kind ? 1 : 0;
      drawn = WEATHER[kind].falls || null;
      amount = drawn ? 1 : 0;
      paintLevels();
      paintFall();
    }
  }
  // The shared uniforms and the fog, from the levels: while a switch eases, and once more when it ends.
  function paintLevels() {
    uniforms.uSnow.value = smooth(levels.snow);
    uniforms.uWet.value = smooth(levels.rain);
    uniforms.uRipple.value = 1 + (SHIMMER.rain - 1) * smooth(levels.rain);
    fogNow = fogAt({ snow: smooth(levels.snow), rain: smooth(levels.rain), fog: smooth(levels.fog) });
  }
  // What falls, in the look's colours: when the kind that falls changes, and at a look switch.
  function paintFall() {
    if (!drawn) return;
    const f = FALL[drawn];
    u.uRain.value = drawn === 'rain' ? 1 : 0;
    u.uSpeed0.value = f.speed[0]; u.uSpeed1.value = f.speed[1];
    u.uClamp.value.set(...f.px);
    if (theme) { const [ink, alpha] = fallInk(theme, drawn); u.uInk.value.set(ink); u.uAlpha.value = alpha; }
  }
  // A look switch: the snow's colour on roofs and ground, the flakes' colour.
  function retheme(th) {
    theme = th;
    uniforms.uSnowInk.value.set(snowInk(th));
    paintFall();
  }

  function step(dt, dist, target) {
    dt = Math.min(Math.max(dt, 0), 0.1);   // a tab back from the background does not jump
    const still = reduced();
    let moved = false;
    for (const k of Object.keys(levels)) {
      const want = k === kind ? 1 : 0;
      if (levels[k] !== want) { levels[k] = still ? want : approach(levels[k], want, dt / EASE_S); moved = true; }
    }
    // The water moves unless the visitor asks for less motion or a test holds it still.
    if (!still && !paused) uniforms.uWave.value = (uniforms.uWave.value + dt / WAVE_S) % 1;
    // What falls: the old kind's flakes leave before the new kind's come.
    const want = WEATHER[kind].falls || null;
    if (drawn !== want) {
      amount = still ? 0 : approach(amount, 0, dt / OUT_S);
      if (amount === 0) { drawn = want; lowFor = 0; paintFall(); }
    } else if (drawn && amount < 1) amount = still ? 1 : approach(amount, 1, dt / EASE_S);
    if (moved) paintLevels();
    points.visible = !!drawn && amount > 0 && !still;
    if (!points.visible) { lowFor = 0; lastSize = 0; return moved; }
    u.uAmount.value = smooth(amount);
    // Half the flakes when the frame rate stays under 30 for SLOW_S seconds with them falling, once, for the rest of the
    // visit. One long frame does not count (fps(): frameRate leaves it out), nor a dip shorter than that.
    lowFor = fps() < 30 ? lowFor + dt : 0;
    if (lowFor > SLOW_S) slow = true;
    const count = flakeCount({ small: small(), slow });
    if (geo.drawRange.count !== count) geo.setDrawRange(0, count);
    if (!paused) u.uT.value = (u.uT.value + dt / FALL_S) % 1;
    const half = dist * BOX.half, size = 2 * half, above = Math.max(0, camera.position.y - target.y);
    // The phase takes up the target's pan, so the flakes stay where they are in the world; a zoom leaves it.
    if (lastSize) u.uPhase.value.set(fract(u.uPhase.value.x - (target.x - last.x) / size),
      fract(u.uPhase.value.y - (target.z - last.y) / size));
    last.set(target.x, target.z);
    lastSize = size;
    u.uBoxMin.value.set(target.x - half, target.y - dist * BOX.low, target.z - half);
    u.uBoxSize.value.set(size, Math.max(dist * BOX.high, above + 0.15 * dist), size);
    u.uSize.value = dist * FALL[drawn].size;
    renderer.getDrawingBufferSize(buffer);
    u.uPr.value = renderer.getPixelRatio();
    u.uPx.value = buffer.y / u.uPr.value / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
    u.uNear.value = Math.max(camera.near, dist * 0.04);
    return moved;
  }

  return {
    group, set, step, retheme,
    get kind() { return kind; },
    sky: lookSky => skyAt(lookSky, { snow: smooth(levels.snow), rain: smooth(levels.rain), fog: smooth(levels.fog) }),
    fog: () => fogNow,
    // A test that compares two screenshots can hold the water and the flakes still (the shimmer alone is small enough
    // for e2e/search.spec.mjs's: no pixel moves by 30).
    pause(on = true) { paused = !!on; },
    state: () => ({ kind, snow: uniforms.uSnow.value, wet: uniforms.uWet.value, fog: fogNow.slice(), paused,
      falling: points.visible ? drawn : null, particles: points.visible ? geo.drawRange.count : 0, slow }),
  };
}
