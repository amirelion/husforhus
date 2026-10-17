import * as THREE from './vendor/three.module.js';
import { MapControls } from './vendor/MapControls.js';
import { fetchGz, decoder } from './gz.js';
import { readAttrs, ATTR_FLOATS } from './tile.js';
import { liftBounds } from './bounds.js';
import { YFLAG } from './codes.js';
import { yearLine, sourceLine, rebuildLine, floorsLine, heightLine, ratingLine, protLine, photoCredit, extractFor, cardLinks, fillUrl,
  isEstimate, placeLine, whyAnchor, wrongHref } from './card.js';
import { makeT, legacy, pickLang } from './i18n.js';
import { estimateTone, inkOn, rgba, luma, rgb, unknownFill } from './tone.js';
import { THEMES, SHADING } from './themes.js';
import { createLooks } from './look.js';
import { mountSwitcher } from './switcher.js';
import { initialCollapsed, LEGEND_KEY, photoOnlyFrom, photoOnlyHref, markPhotos } from './panel.js';
import { cityCount, layerCount, tallyTitle, tallyFromAttrs, periodCounts } from './count.js';
import { placeLabels, labelAt, stepYear } from './timeline.js';
import { unknownShown, readPref, writePref, prefAfterClick, unknownHint, easeShown } from './unknown.js';
import { makeGround, cutFactor, levelAt, LOD_TOL, parsePolygons, fadeWidth, askWorker, withTimeout, FETCH_TIMEOUT_MS }
  from './terrain.js';
import { RELIEF_KEY, RELIEF_MAX, RELIEF_STEP, initialRelief, reliefNote, reliefValue, ease } from './relief.js';
import { howto } from './howto.js';
import { northTurn, turnAt, needleDeg } from './north.js';
import { mountSearch } from './searchbox.js';
import { makeHighlight } from './highlight.js';
import { aboutHtml, aboutTarget } from './about.js';
import { cornerHtml } from './credits.js';
import { mountScenePlayer } from './scene-player.js';

// Colours are authored in sRGB and drawn as they are.
THREE.ColorManagement.enabled = false;

// Looks (web/themes.js), chosen in web/look.js: ?theme=arg|kalk|blatimme|paper, else the viewer's last choice, else
// Ärg. THEME is the look on now (THEME.unknown: buildings with no year yet, a neutral grey apart from the maquette).
// applyLook (see Looks below) re-applies a switch to everything drawn in the look's colours. The page's own colours
// and font are set here already, before the city loads, so the loading line is drawn in the look.
const looks = createLooks();
let THEME_NAME, THEME, FONT;
function applyPageLook(name) {
  THEME_NAME = name;
  THEME = THEMES[name];
  FONT = `"${THEME.font}"`;
  for (const [k, v] of Object.entries(THEME.ui)) document.documentElement.style.setProperty(k, v);
  document.documentElement.style.setProperty('--font', FONT);
  document.documentElement.dataset.theme = name;
  // Native surfaces (scrollbars, form controls, the dialog's own surface) follow the look's ground, dark or light.
  document.documentElement.style.colorScheme = luma(rgb(THEME.ui['--bg'])) < 0.5 ? 'dark' : 'light';
}
applyPageLook(looks.current);
const GROUP_COLORS = ['#ec0000', '#1f4e8c', '#d99a12', '#2e8b57', '#7b3fa0', '#00909a', '#8c5a2b', '#d6336c'];
const MAX_GROUPS = GROUP_COLORS.length;
const ATTR_W = 256;
// The "Year unknown" hatch: stripes HATCH_M metres apart, measured across them, each line HATCH_W of that.
// Seen from further away they go to twice that apart, then fade into their mean tone (FRAG).
const HATCH_M = 4, HATCH_W = 0.25;
const WORKERS = Math.min(4, navigator.hardwareConcurrency || 2);
const MODE = { period: 0, floors: 1, layers: 3 }; // 2 was Energy, removed

// Data lives in web/data/<version>/ (pipeline/s03_tiles.py); data/current.json names the version.
const CITY = 'stockholm';
const getJson = (url, init) => fetch(url, init).then(r => {
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
});
// UI strings come from web/i18n by stable id through T (see Language below), which exists once the strings are in.
// Until then the page speaks the language it is about to open in (web/i18n.js pickLang, the switch assumed on), from
// the one built-in line a failed start needs (boot.js has the same pair).
const QUERY = new URLSearchParams(location.search);
const savedLang = () => { try { return localStorage.getItem('hfh-lang'); } catch { return null; } };
let LANG = pickLang({ param: QUERY.get('lang'), saved: savedLang(), languages: navigator.languages || [navigator.language] });
let T = null;
const FAILED = { en: 'Could not load the city data. Reload the page to try again.',
  sv: 'Kunde inte ladda stadens data. Ladda om sidan för att försöka igen.' };
// The loading line in Swedish from the first moment: ?lang=, a saved choice, or a Swedish browser
// (decided 2026-10-17: city.LANG_FROM_BROWSER).
{
  const early = pickLang({ param: QUERY.get('lang'), saved: savedLang(), languages: navigator.languages || [navigator.language] });
  const ld = document.getElementById('loading');
  if (early === 'sv' && ld.querySelector('#progress') && ld.firstChild) ld.firstChild.textContent = 'Bygger staden ';
}
let failedId = null;   // the message a failed start shows, redrawn by a language switch (applyStaticText)
// t(text): the English text the pure modules hand over (count.js, unknown.js, howto.js, the switcher), by its id
// (web/i18n.js LEGACY); the v1.1 quests and layers keep their English.
const t = s => (T ? legacy(T)(s) : s);
function loadFailed(e, id = 'ui.failed') {
  console.error(e);
  failedId = id;
  const el = document.getElementById('loading');
  el.hidden = false;
  el.setAttribute('role', 'alert');      // the audit's finding 7: a failure is announced at once
  el.removeAttribute('aria-live');
  el.textContent = T ? T(id) : FAILED[LANG] || FAILED.en;
}
// A file the map can do without (the street names, the land, the water, the terrain): a warning in the console, never
// the fatal message over a map that works (the audit's finding 3).
const optional = what => e => console.warn(`${what} did not load; the map goes on without it.`, e);
// A failed start (a missing file, a dropped connection, bad JSON, no WebGL) shows loadFailed's message and stops
// the module here, on a promise that never settles: everything below needs the config.
const halt = (e, id) => { loadFailed(e, id); return new Promise(() => {}); };
// The Look button works from the start, while the city loads and after a failed start: until the scene is up a
// switch changes the page's own colours (applyPageLook); then applyLook (see Looks below) takes over.
// The Hills slider sits in the Look panel; it appears once the city's terrain is known
// (applyStaticText), and is disabled if the terrain does not load. Its value reads "Flat" or the factor, and its line
// says what the map shows now (web/relief.js reliefValue, reliefNote). Read only once available (after the config).
const reliefUi = { available: false, step: RELIEF_STEP, get value() { return relief; }, get max() { return reliefMax; },
  get disabled() { return terrainState === 'failed'; }, choose: v => chooseRelief(v), label: v => reliefValue(v, LANG),
  note: () => reliefNote(relief, LANG, terrainState) };
const switcher = mountSwitcher({ button: document.querySelector('.look-open'), panel: document.getElementById('look'), looks, t,
  relief: reliefUi });
const pageLookOnly = looks.subscribe(applyPageLook);
const { version } = await getJson('data/current.json', { cache: 'no-cache' }).catch(halt);
const DATA = `data/${version}/`;
// Load order: config and the hot attributes, then pack0 (see Tiles). The other packs follow the first tile;
// land, water and labels follow the first frame with buildings.
// The strings (web/i18n): both languages, a few KB, so the language switches without a reload.
const [config, attrBuf, I18N_EN, I18N_SV] = await Promise.all([getJson(`${DATA}${CITY}.json`),
  fetchGz(`${DATA}attrs.bin.gz`), getJson('i18n/en.json'), getJson('i18n/sv.json')]).catch(halt);
const I18N = { en: I18N_EN, sv: I18N_SV };
const attrs = new DataView(attrBuf);
// The count's own tally, built once from attrs.bin: the years the shader draws, a private house at its decade start
// (web/count.js tallyFromAttrs). stockholm.json's spread histograms stay for drawHist.
const attrTally = tallyFromAttrs(attrs, config.stats.buildings, config.attrStride,
  { periods: config.periods, yearMin: config.yearMin, yearMax: config.yearMax });
// Features for v1.1 (Quests, Context layers, the language switch) stay in the code, switched off by
// config.features (pipeline/city.py FEATURES); their buttons are hidden, never removed.
const FEATURES = config.features || {};
const layers = FEATURES.layers ? await getJson(`${DATA}layers.json`).catch(halt) : [];

// ---------- Language ----------
// English and Swedish (features.lang turns the switch on). ?lang= sets this visit only; the switch's
// choice is remembered (hfh-lang); otherwise English, or the browser's language when it is Swedish once
// the build says so (config.langFromBrowser, off until then; web/i18n.js pickLang). The messages of a start
// that fails before the config is in follow the browser (above). Data may carry `<field>_sv` next to each English
// text (tr). T(id, vars): web/i18n's string in LANG; setLang renews it.
LANG = pickLang({ param: QUERY.get('lang'), saved: savedLang(), languages: navigator.languages || [navigator.language],
  fromBrowser: config.langFromBrowser === true, enabled: !!FEATURES.lang });   // a build without the key: English
const tr = (o, k) => (LANG === 'sv' && o?.[k + '_sv']) || o?.[k];
T = makeT(I18N, LANG);
const fmtLocale = () => (LANG === 'sv' ? 'sv-SE' : 'en');
document.querySelector('.quests-open').hidden = !FEATURES.quests;
document.querySelector('.modes [data-mode="3"]').hidden = !FEATURES.layers;
document.querySelectorAll('.lang [data-lang]').forEach(b => { b.hidden = !FEATURES.lang; });
const periods = config.periods.map((p, i) => ({ ...p, color: THEME.periods[i] || p.color }));
const estColors = periods.map(p => estimateTone(p.color, THEME.estimateTo));
// The hide-estimates switch: area, estimate and period-only buildings leave the map, the count, the
// legend's totals and the histogram while the city is coloured by period. Remembered per device.
const EST_KEY = 'hfh-estimates';
let hideEst = false;
try { hideEst = localStorage.getItem(EST_KEY) === 'hidden'; } catch {}
// The "Highlight buildings with a photo" switch: the rest fade to the maquette, as the timeline's range fade does. On in the
// URL (?photos=1, web/panel.js). photoGids (photo-gids.json, s03_tiles) loads on first use.
let photoOnly = photoOnlyFrom(location.search);
let photoGids = null;
// Terrain. What the map draws is uRelief * t - uCutK * cut (true metres t and the terrace cut, web/terrain.js),
// in every shader and in surfaceAt, the CPU's copy: flat until the terrain is in.
const uRelief = { value: 0 }, uCutK = { value: 0 };
let ground = makeGround(null);
const surfaceAt = (x, z) => ground.surfaceAt(x, z, uRelief.value, uCutK.value);
// stockholm.json's terrain block and the Hills slider (web/relief.js), plus the M4 review's comparison levers,
// none offered to visitors: ?terrace=full|true|none (how much of the terrace cut to use), ?fade=<metres> (the edge
// fade's width) and ?edgebuildings=1 (buildings fade at the edge too).
const TERRAIN = config.terrain || null;
const PARAMS = new URLSearchParams(location.search);
// relief: the relief asked for, from 0 (flat) to reliefMax (the slider's top, 2.5), 1 being the true heights
const reliefMax = TERRAIN?.reliefMax ?? RELIEF_MAX;
let relief = initialRelief(location.search, (() => { try { return localStorage.getItem(RELIEF_KEY); } catch { return null; } })(),
  TERRAIN?.relief ?? 0, reliefMax);
let terrainState = 'flat';  // 'flat' (none yet, or none in this build), 'loading', 'ready' or 'failed' (still flat)
const TERRACE = ['full', 'true', 'none'].includes(PARAMS.get('terrace')) ? PARAMS.get('terrace') : TERRAIN?.terrace || 'full';
const FADE_M = fadeWidth(PARAMS.get('fade'), TERRAIN?.fadeM ?? 400);
// ?labels=top: names drawn over everything, as first specified (for comparison)
const LABELS_ON_TOP = PARAMS.get('labels') === 'top';
reliefUi.available = !!TERRAIN;
// The level of the water under a point (true metres; 0 until the terrain is in): where a water name lies.
let waterAt = () => 0;

// ---------- Scene ----------
const canvas = document.getElementById('scene');
let renderer;
// No WebGL: say so in the page's language, not that the data failed.
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true }); } catch (e) { await halt(e, 'ui.nowebgl'); }
// A lost context (a GPU reset, a phone short of memory) leaves a blank map: say so, and that a reload draws it again.
canvas.addEventListener('webglcontextlost', e => loadFailed(e, 'ui.contextlost'));
// ... and when the browser gives it back (three.js asks it to), the map draws again and the message goes.
canvas.addEventListener('webglcontextrestored', () => {
  if (failedId !== 'ui.contextlost') return;
  failedId = null;
  const el = document.getElementById('loading');
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');
  el.hidden = true;
});
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(THEME.sky);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 5, 60000);
const controls = new MapControls(camera, canvas);
controls.enableDamping = true;
// Like a web map: drag moves the city; Ctrl/Cmd with the left button, or the right button, turns and tilts it.
// (OrbitControls swaps PAN for ROTATE itself while Ctrl, Cmd or Shift is held.) Shift works too but is not advertised
// (web/howto.js): a real Shift-drag is unreliable, since the browser takes a Shift-press for selection-extend and some
// browser shells take Shift-drag for themselves. One finger moves, two zoom and turn.
controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
controls.rotateSpeed = 0.6;
controls.maxPolarAngle = Math.PI * 0.47;
controls.minDistance = 60;
controls.maxDistance = 30000;
// Arrow keys move the map (Shift/Ctrl/Cmd with them turns it), but not while a text field, a slider (input matches
// every type: the Look panel's Hills slider, a range, moves with them; the timeline's handles, role="slider")
// or a dialog (the pinned card too) has the keys. The N key (see Facing north) waits the same way.
const MAP_KEYS = { ...controls.keys };
// A code no key has: '' would match the empty code a phone's soft keyboard sends, and pan the map while
// someone types in the search field.
const NO_KEYS = { LEFT: 'NoKey', UP: 'NoKey', RIGHT: 'NoKey', BOTTOM: 'NoKey' };
controls.keyPanSpeed = 40;
controls.listenToKeyEvents(window);
const typingIn = el => el instanceof Element && Boolean(el.closest('input, textarea, select, dialog, [role="dialog"], [role="slider"]') || el.isContentEditable);
// Runs before the controls' own listener on window (capture phase), so each key press picks the key map to use.
addEventListener('keydown', e => { controls.keys = typingIn(e.target) ? NO_KEYS : MAP_KEYS; }, true);

// The hero view (city.HOME). A portrait screen sees a narrower slice, so the camera steps back until the
// same width fits, up to 2.2 times as far.
function goHome(h = config.home) {
  const az = THREE.MathUtils.degToRad(h.azimuth), el = THREE.MathUtils.degToRad(h.elevation);
  const d = h.span * 0.9 * Math.min(2.2, Math.max(1, 0.95 * innerHeight / innerWidth));
  const y = surfaceAt(h.x, h.z);
  controls.target.set(h.x, y, h.z);
  camera.position.set(h.x + d * Math.cos(el) * Math.sin(az), y + d * Math.sin(el), h.z + d * Math.cos(el) * Math.cos(az));
  controls.update();
}
goHome();
// Same direction, another distance: the overview for draw-call measurements is viewAt(20000).
function viewAt(distance) {
  const dir = camera.position.clone().sub(controls.target).normalize();
  camera.position.copy(controls.target).addScaledVector(dir, distance);
  controls.update();
}

// Land and water: flat polygons in the local frame (see pipeline/s04_base.py). With the terrain in, the land is drawn
// by the terrain and the water at its levels (loadTerrain). The flat land is fetched only for a build without terrain
// or when the terrain fails, and the flat water is drawn only with it (showFlat): drawn alone while the terrain
// loaded, it left the land in the sky's colour for 22 s on a slow line (the final review's VIEWER-4).
function polygonGeometry(buf) {
  const [nPoly, nRing, nVert] = new Uint32Array(buf, 0, 3);
  const ringStart = new Uint32Array(buf, 12, nPoly + 1);
  const vertStart = new Uint32Array(buf, 12 + 4 * (nPoly + 1), nRing + 1);
  const xz = new Float32Array(buf, 12 + 4 * (nPoly + 1) + 4 * (nRing + 1), 2 * nVert);
  const ring = r => {
    const pts = [];
    for (let v = vertStart[r]; v < vertStart[r + 1]; v++) pts.push(new THREE.Vector2(xz[2 * v], -xz[2 * v + 1]));
    return pts;
  };
  const shapes = [];
  for (let p = 0; p < nPoly; p++) {
    const shape = new THREE.Shape(ring(ringStart[p]));
    for (let r = ringStart[p] + 1; r < ringStart[p + 1]; r++) shape.holes.push(new THREE.Path(ring(r)));
    shapes.push(shape);
  }
  const g = new THREE.ShapeGeometry(shapes);
  g.rotateX(-Math.PI / 2);
  return g;
}
const flat = new THREE.Group();
scene.add(flat);
const land = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial({ color: THEME.land }));
const water = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial({ color: THEME.water }));
land.position.y = -0.05;
water.position.y = -0.4;
// Requested after the first frame with buildings (see the loop), so they never compete with pack0. Resolves with
// water.bin, which the terrain worker needs too.
async function loadBase() {
  const waterBuf = await fetchGz(`${DATA}water.bin.gz`);
  water.geometry = polygonGeometry(waterBuf);
  if (!TERRAIN) await showFlat();
  return waterBuf;
}
async function loadLand() {
  land.geometry = polygonGeometry(await fetchGz(`${DATA}land.bin.gz`));
  flat.add(land);
}
// The flat map: the land, then the water with it (its geometry arrives with loadBase, before or after).
async function showFlat() {
  await loadLand();
  flat.add(water);
}

// ---------- Street and canal names ----------
// Flat on the ground, turned along the street (pipeline/s07_labels.py). Textures are drawn on first use, and drawn
// again in the new look's colours and font after a switch (redrawLabels).
const labelGroup = new THREE.Group();
scene.add(labelGroup);
const labelTex = new Map();
const LABEL_PX = 64;
function textureFor(L) {
  let t = labelTex.get(L.name + L.water);
  if (t) return t;
  const c = document.createElement('canvas'), ctx = c.getContext('2d');
  const font = `${L.water ? 'italic 500' : '500'} ${LABEL_PX * 0.62}px ${FONT}, sans-serif`;
  ctx.font = font;
  c.width = Math.ceil(ctx.measureText(L.name).width + LABEL_PX * 0.4);
  c.height = LABEL_PX;
  ctx.font = font;
  ctx.textBaseline = 'middle';
  ctx.lineWidth = LABEL_PX * 0.12;
  ctx.strokeStyle = L.water ? rgba(THEME.water, 0.85) : THEME.labelHalo;
  ctx.fillStyle = L.water ? THEME.waterInk : THEME.labelInk;
  ctx.strokeText(L.name, LABEL_PX * 0.2, LABEL_PX / 2);
  ctx.fillText(L.name, LABEL_PX * 0.2, LABEL_PX / 2);
  t = new THREE.CanvasTexture(c);
  t.anisotropy = 4;
  t.userData = { aspect: c.width / c.height };
  labelTex.set(L.name + L.water, t);
  return t;
}
// Sixteen segments along a name and two across, so it can follow the ground (labelMaterial). Its bounding sphere
// (radius 1, a name's whole length once scaled) holds a name on a slope of up to 60° along it: the mesh stands at the
// name's lifted height (labelY), and three.js culls it like everything else.
const labelPlane = new THREE.PlaneGeometry(1, 1, 16, 2);
labelPlane.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1);
// Names lie on the ground: the vertex shader sets each vertex's height from the terrain (hEff, like everything
// else) plus 0.6 m, or a water name's on its water's level plus 0.4 m (uOnWater, uLevel: a canal's banks are carried
// two nodes into it), then moves it towards the camera along its own ray by how far the drawn ground may stand above
// hEff there (the cell's twist, doubled for the name's own straight spans, and LOD_TOL at the relief), so the pixel
// stays where it is but the name never sinks into a slope; a water name, flat at its level, moves 0.5 m. Hills and
// buildings in front still hide them (depth test on). ?labels=top turns the depth test off, as first specified,
// for the M4 comparison.
const TERRAIN_UNIFORMS = ['uTerrain', 'uGridO', 'uGridN', 'uCell', 'uRelief', 'uCutK'];
function labelMaterial(map, onWater) {
  const m = new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false, depthTest: !LABELS_ON_TOP });
  m.userData.level = { value: 0 };
  m.onBeforeCompile = s => {
    for (const k of TERRAIN_UNIFORMS) s.uniforms[k] = uniforms[k];
    s.uniforms.uLevel = m.userData.level;
    s.uniforms.uOnWater = { value: onWater ? 1 : 0 };
    s.vertexShader = GRID_GLSL + TERRAIN_GLSL + `
      uniform float uLevel, uOnWater;
      float hTwist(vec2 w) {
        ivec2 i = ivec2(floor((w - uGridO) / uCell));
        return 0.25 * abs(hNode(i) - hNode(i + ivec2(1, 0)) - hNode(i + ivec2(0, 1)) + hNode(i + ivec2(1, 1)));
      }
` + s.vertexShader.replace('#include <project_vertex>', `
      vec4 wpos = modelMatrix * vec4(transformed, 1.0);
      wpos.y = uOnWater > 0.5 ? uLevel * uRelief + 0.4 : hEff(wpos.xz) + 0.6;
      vec4 mvPosition = viewMatrix * wpos;
      float dEye = length(mvPosition.xyz);
      float bias = 0.5 + ${LOD_TOL.toFixed(1)} * uRelief + 2.0 * hTwist(wpos.xz);
      bias = uOnWater > 0.5 ? 0.5 : bias;   // water is flat at its level: the ground's error is not its own
      mvPosition.xyz *= max(dEye - bias, 1.0) / dEye;
      gl_Position = projectionMatrix * mvPosition;`);
  };
  m.customProgramCacheKey = () => 'hfh-label';
  return m;
}
// The height labelMaterial lifts a name to at its middle: where its mesh stands, so three.js culls it where it is drawn
// (updateLabels follows the relief as it changes). A water name's level is its material's uLevel, read once.
const labelY = l => (l.L.water ? l.mesh.material.userData.level.value * uRelief.value + 0.4 : surfaceAt(l.x, l.z) + 0.6);
// Each visible name is one draw call: at most this many at once, most important first (tier, then length).
const MAX_LABELS = 120;
let labelsShown = 0;
// Set once the look's font has loaded or failed to (loadLabelFont); a switch unsets it until the new font is in, so
// no name is drawn in a fallback face. A failed load (a missing or corrupt woff2) must not stall the labels for good:
// it only logs, and the labels draw in the fallback font. Only the latest switch's font counts.
let fontReady = false, fontAsked = 0;
function loadLabelFont() {
  fontReady = false;
  const ask = ++fontAsked, font = FONT;
  (document.fonts?.load(`500 16px ${font}`) ?? Promise.resolve())
    .catch(e => console.warn(`The font ${font} did not load; labels use the fallback`, e))
    .then(() => { if (ask === fontAsked) { fontReady = true; drawHist(); } });
}
// A switch disposes every name's mesh material and texture; updateLabels makes new ones once the font is in.
function redrawLabels() {
  for (const l of labels) if (l.mesh) { labelGroup.remove(l.mesh); l.mesh.material.dispose(); l.mesh = null; }
  for (const tex of labelTex.values()) tex.dispose();
  labelTex.clear();
  labelsShown = 0;
  loadLabelFont();
}
let labels = [];
// Requested after the first frame with buildings, like land and water.
async function loadLabels() {
  const data = await getJson(`${DATA}labels.json`);
  labels = data.flatMap(L => L.pts.map(([x, z, ang, len, wid]) => ({ L, x, z, ang, len, wid: wid || 20, mesh: null })))
    .sort((a, b) => a.L.tier - b.L.tier || b.len - a.len);
}
function updateLabels(dist) {
  if (!fontReady) return;
  // Label height in metres, roughly constant on screen; the canals and main streets read larger.
  const h1 = THREE.MathUtils.clamp(dist * 0.014, 4, 44), h2 = THREE.MathUtils.clamp(dist * 0.01, 3, 15);
  // Names appear only when the camera comes close: canals and main streets first, the rest closer still.
  const near = dist * 1.2, far = dist * 2;
  // Greedy collision: canals and main streets first, then the longest stretches; a label is dropped
  // when an accepted one already sits within a few label heights of it.
  const taken = new Map(), C = h1 * 5; // one grid, cells as wide as the largest separation
  const cellOf = (x, z) => `${Math.floor(x / C)},${Math.floor(z / C)}`;
  const clear = (l, sep) => {
    const cx = Math.floor(l.x / C), cz = Math.floor(l.z / C);
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
      for (const q of taken.get(`${cx + i},${cz + j}`) || []) if ((q.x - l.x) ** 2 + (q.z - l.z) ** 2 < sep * sep) return false;
    }
    return true;
  };
  let shown = 0;
  for (const l of labels) {
    const d = Math.hypot(l.x - camera.position.x, l.z - camera.position.z);
    let show = shown < MAX_LABELS && d < (l.L.tier === 1 ? far : near) && dist < (l.L.tier === 1 ? 3200 : 1300);
    const sep = (l.L.tier === 1 ? h1 : h2) * 5;
    if (show && !clear(l, sep)) show = false;
    if (show) {
      const key = cellOf(l.x, l.z);
      if (!taken.has(key)) taken.set(key, []);
      taken.get(key).push(l);
    }
    if (show && !l.mesh) {
      const tex = textureFor(l.L);
      l.mesh = new THREE.Mesh(labelPlane, labelMaterial(tex, l.L.water));
      l.mesh.material.userData.level.value = l.L.water ? waterAt(l.x, l.z) : 0;
      // Turn about the vertical first, then lay the plane flat; its height comes from the ground (labelMaterial).
      l.mesh.rotation.set(-Math.PI / 2, THREE.MathUtils.degToRad(-l.ang), 0, "YXZ"); // ang is measured towards +z, Y turns towards -z
      l.mesh.position.set(l.x, labelY(l), l.z);
      l.mesh.renderOrder = 2;
      labelGroup.add(l.mesh);
    }
    if (l.mesh) {
      // Never taller than the street or canal is wide, so a name stays off the buildings.
      const h = Math.min(l.L.tier === 1 ? h1 : h2, l.wid * 0.55);
      const w = h * l.mesh.material.map.userData.aspect;
      // A name much longer than its stretch of street would spill over the buildings.
      if (show && (w > l.len * 1.1 || h < 2.5)) show = false;
      l.mesh.visible = show;
      if (show) { l.mesh.scale.set(w, h, 1); l.mesh.position.y = labelY(l); shown++; }
    }
  }
  labelsShown = shown;
}

// ---------- Shared uniforms ----------
const col = c => new THREE.Color(c);
// A number written into GLSL as a float literal (1 -> 1.0), for constants shared with JavaScript (themes.js SHADING).
const glf = x => (Number.isInteger(x) ? x.toFixed(1) : String(x));
function dataTexture(data, w, h, format, type) {
  const t = new THREE.DataTexture(data, w, h, format, type);
  t.unpackAlignment = 1;   // a one-byte texel row of odd width is not 4-byte aligned
  t.needsUpdate = true;
  return t;
}
const uniforms = {
  uYear: { value: config.yearMax },
  uYearFrom: { value: config.yearMin - 1 },
  uMode: { value: MODE.period },
  uPalette: { value: periods.map(p => col(p.color)) },
  uMask: { value: periods.map(() => 1) },
  uNow: { value: 0 },                              // seconds, for tiles dropping in as they load
  uPlaying: { value: 0 },                          // while the film plays buildings fly in rather than grow
  uRise: { value: 0.01 },
  uLayerAt: { value: -10 },                        // seconds; when a context layer opened, its buildings rise                          // years a building's entrance spans; only the film widens it
  uGroupBit: { value: Array(MAX_GROUPS).fill(-1) },
  uGroupColor: { value: GROUP_COLORS.map(col) },
  uMaquette: { value: col(THEME.maquette) },
  uUnknown: { value: col(THEME.unknown) },
  uEstimateTo: { value: col(THEME.estimateTo) },   // estimates mix towards this; hover towards uHoverTo (web/themes.js)
  uHoverTo: { value: col(THEME.hoverTo) },
  uShowUnknown: { value: 1 },                      // how far buildings without a year stand, 1 to 0 (stepUnknown)
  uHideEst: { value: hideEst ? 1 : 0 },            // 1 while the legend's switch hides the estimated years
  uPhotoOnly: { value: 0 },                        // 1 while the legend's photo switch fades buildings without one
  uHatch: { value: THEME.unknownHatch ? 1 : 0 },   // 1 on a look that hatches "Year unknown", in uHatchInk
  uHatchInk: { value: col(THEME.unknownHatch || THEME.unknown) },
  uFloors: { value: THEME.floors.map(col) },       // the look's Floors ramp (web/themes.js)
  uHover: { value: -1 },
  uSelected: { value: -1 },
  uForce: { value: -1 },                           // the building picked from search: drawn whatever hides it
  uBlind: { value: 0 },
  uFogColor: { value: col(THEME.sky) },
  uFog: { value: new THREE.Vector2(9000, 26000) },
  // Terrain: one texture of (true metres, terrace cut) per grid node, read with texelFetch, and the edge fade;
  // 1 x 1 placeholders until loadTerrain replaces them. uSun is the one sun buildings and ground share (themes.js
  // SHADING, which the looks' colour checks use too).
  uRelief, uCutK,
  uTerrain: { value: dataTexture(new Float32Array(2), 1, 1, THREE.RGFormat, THREE.FloatType) },
  uFade: { value: dataTexture(new Uint8Array([255]), 1, 1, THREE.RedFormat, THREE.UnsignedByteType) },
  uGridO: { value: new THREE.Vector2(0, 0) }, uGridN: { value: new THREE.Vector2(1, 1) }, uCell: { value: 1 },
  uEdgeBuildings: { value: 0 },
  uSun: { value: new THREE.Vector3(...SHADING.sun).normalize() },
};

// The terrain grid's uniforms: every shader stage that reads the grid includes this once, before TERRAIN_GLSL,
// FADE_GLSL or both (GLSL ES 3.00 refuses a uniform declared twice in one stage).
const GRID_GLSL = /* glsl */`
  uniform vec2 uGridO, uGridN;
  uniform float uCell;
`;
// The terrain's height in every shader that needs it (buildings, ground, walls, names): bilinear over the nodes, each
// clamped on its own, exactly as web/terrain.js makeGround and pipeline/terrain.py bilinear do. Needs GRID_GLSL.
const TERRAIN_GLSL = /* glsl */`
  uniform sampler2D uTerrain;
  uniform float uRelief, uCutK;
  float hNode(ivec2 i) {
    vec2 v = texelFetch(uTerrain, clamp(i, ivec2(0), ivec2(uGridN) - 1), 0).rg;
    return uRelief * v.r - uCutK * v.g;
  }
  float hEff(vec2 w) {
    vec2 g = (w - uGridO) / uCell, f = floor(g), t = g - f;
    ivec2 i = ivec2(f);
    return mix(mix(hNode(i), hNode(i + ivec2(1, 0)), t.x), mix(hNode(i + ivec2(0, 1)), hNode(i + ivec2(1, 1)), t.x), t.y);
  }
  vec2 hEffGrad(vec2 w) {
    ivec2 i = ivec2(floor((w - uGridO) / uCell + 0.5));
    return vec2(hNode(i + ivec2(1, 0)) - hNode(i - ivec2(1, 0)), hNode(i + ivec2(0, 1)) - hNode(i - ivec2(0, 1))) / (2.0 * uCell);
  }
  // how much the drawn ground varies over the cell under w: a wall's skirt reaches half of it further down
  float hRange(vec2 w) {
    ivec2 i = ivec2(floor((w - uGridO) / uCell));
    float a = hNode(i), b = hNode(i + ivec2(1, 0)), c = hNode(i + ivec2(0, 1)), d = hNode(i + ivec2(1, 1));
    return max(max(a, b), max(c, d)) - min(min(a, b), min(c, d));
  }
`;
// The edge fade: 1 inside, 0 at the municipality's edge, linear between nodes. Needs GRID_GLSL.
const FADE_GLSL = /* glsl */`
  uniform sampler2D uFade;
  float fadeAt(vec2 w) { return texture(uFade, ((w - uGridO) / uCell + 0.5) / uGridN).r; }
`;

const VERT = /* glsl */`
  in float bld;
  uniform sampler2D uAttr;
  uniform float uYear, uYearFrom, uMode, uHover, uSelected, uForce, uBlind, uNow, uBorn, uPlaying, uRise, uLayerAt;
  uniform vec3 uPalette[${periods.length}];
  uniform float uMask[${periods.length}];
  uniform int uGroupBit[${MAX_GROUPS}];
  uniform vec3 uGroupColor[${MAX_GROUPS}];
  uniform vec3 uMaquette, uUnknown, uEstimateTo, uHoverTo, uHatchInk;
  uniform vec3 uFloors[4];
  uniform float uShowUnknown, uHatch, uHideEst, uPhotoOnly;
  ${GRID_GLSL}
  ${TERRAIN_GLSL}
  out vec3 vColor;
  out vec3 vWorld;
  out float vRel;        // metres above the building's own base (its foot and hatch use this, not world height)
  flat out float vGid;   // flat: the pick pass reads it as an exact integer, never interpolated
  flat out vec3 vHatchInk;
  flat out float vHatch; // 1: the fragment shader hatches this building in vHatchInk ("Year unknown")

  // 1 floor to 40 and more on a log scale, through the look's four colours (uFloors; the legend draws the same).
  vec3 floorsRamp(float f) {
    float t = clamp(log(max(f, 1.0)) / log(40.0), 0.0, 1.0);
    return t < 0.33 ? mix(uFloors[0], uFloors[1], t / 0.33)
      : t < 0.66 ? mix(uFloors[1], uFloors[2], (t - 0.33) / 0.33) : mix(uFloors[2], uFloors[3], (t - 0.66) / 0.34);
  }

  bool hasBit(vec4 words, int bit) {
    int w = bit / 16;
    float v = w == 0 ? words.x : w == 1 ? words.y : w == 2 ? words.z : words.w;
    return ((int(v + 0.5) >> (bit - w * 16)) & 1) == 1;
  }

  void main() {
    int i = int(bld + 0.5);
    ivec2 tc = ivec2(${ATTR_FLOATS / 4} * (i % ${ATTR_W}), i / ${ATTR_W});
    vec4 a = texelFetch(uAttr, tc, 0);
    vec4 lay = texelFetch(uAttr, tc + ivec2(1, 0), 0);
    float groundDm = texelFetch(uAttr, tc + ivec2(2, 0), 0).x;   // web/worker.js: the building's ground
    float year = a.x;
    int pf = int(a.y + 0.5);
    int period = pf % 16;
    int yflag = pf / 16;   // pipeline/codes.py: 3 AREA, 4 ESTIMATE and 6 PERIOD are estimates, 7 UNKNOWN has year 0
    vGid = a.w;
    vHatch = 0.0;
    vec3 h = uHatchInk;
    float seed = fract(sin(a.w * 12.9898) * 43758.5453);
    // Estimated years (3 AREA, 4 ESTIMATE, 6 PERIOD; web/count.js EST_FLAGS) are drawn in estimate style below.
    bool est = yflag == 3 || yflag == 4 || yflag == 6;
    // Buildings without a year stand at "Today" and leave when the map shows the past, or when one period is
    // shown alone. uShowUnknown (stepUnknown) is how far they stand, 1 to 0; each one rises out of the ground or
    // sinks into it in turn, by its seed, with the same stagger and overshoot as a context layer's (uLayerAt below).
    float vis = uMode < 1.5 ? (yflag == 7 ? clamp(uShowUnknown * 1.6 - seed * 0.6, 0.0, 1.0) : uMask[period]) : 1.0;
    // The legend's switch hides the estimated years in the period view: moved off screen like a masked period, so a
    // hidden one cannot be picked either.
    if (uMode < 0.5 && est && uHideEst > 0.5) vis = 0.0;
    float g = clamp((uYear - year + 1.0) / uRise, 0.0, 1.0);
    g = g * g * (3.0 - 2.0 * g);
    // The building picked from search stands whatever the timeline, a period shown alone or a switch says.
    if (abs(a.w - uForce) < 0.5) { vis = 1.0; g = 1.0; }
    if (g <= 0.003 || vis <= 0.003) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }

    // Entrances, only while the film plays and while tiles load: a building drops in from its own side of the
    // sky, the same side every time (seeded by its id). Filters and scrubbing change the dated city at once.
    vec3 p = position;
    if (yflag == 7 && vis < 1.0) { float q = vis - 1.0; p.y *= 1.0 + 2.70158 * q * q * q + 1.70158 * q * q; }
    float arrive = clamp((uNow - uBorn) / 0.9 - seed * 0.35, 0.0, 1.0);
    float fly = 1.0 - arrive;
    if (uPlaying > 0.5) fly = max(fly, 1.0 - g);
    if (fly > 0.0) {
      float e = fly * fly * fly;
      float ang = seed * 6.2831853;
      // positions are in decimetres: a few hundred metres sideways and up
      p += vec3(cos(ang), 0.0, sin(ang)) * (1800.0 + 1600.0 * fract(seed * 7.13)) * e;
      p.y += (2600.0 + 2400.0 * fract(seed * 3.71)) * e;
    }
    vec3 c;
    if (uMode < 0.5) {
      c = uPalette[period];
      if (est) {
        // Estimate style (web/tone.js estimateTone, ESTIMATE_MIX): 40% towards its own luminance, then 25% towards
        // the look's estimate colour (black in every look). Duller and darker than the period colour, unlike the
        // range fade below (towards the pale maquette) and unlike the hatched "Year unknown".
        c = mix(c, vec3(dot(c, vec3(0.2126, 0.7152, 0.0722))), 0.4);
        c = mix(c, uEstimateTo, 0.25);
      }
      if (yflag == 7) { c = uUnknown; vHatch = uHatch; }
    } else if (uMode < 1.5) {
      c = floorsRamp(a.z);
    } else {
      c = uMaquette;
      for (int g = 0; g < ${MAX_GROUPS}; g++) {
        if (uGroupBit[g] >= 0 && hasBit(lay, uGroupBit[g])) {
          c = uGroupColor[g];
          // Opening a layer: its buildings rise out of the ground in a quick wave, overshoot a little, settle.
          float k = clamp((uNow - uLayerAt) / 0.55 - seed * 0.6, 0.0, 1.0);
          float q = k - 1.0;
          p.y *= 1.0 + 2.70158 * q * q * q + 1.70158 * q * q;
          break;
        }
      }
    }
    if (yflag != 7 && year <= uYearFrom) c = mix(c, uMaquette, 0.8);
    // The photo switch: a building whose card has no photo (float 9, web/panel.js markPhotos) fades the same way.
    float photo = texelFetch(uAttr, tc + ivec2(2, 0), 0).y;
    if (uMode < 0.5 && uPhotoOnly > 0.5 && photo < 0.5) { c = mix(c, uMaquette, 0.8); vHatch = 0.0; }
    // A quest's question about one building turns it red; a year riddle also hides every other age.
    if (uBlind > 0.5 && vGid == uSelected) c = vec3(0.925, 0.0, 0.0);
    else if (uBlind > 0.5 && uBlind < 1.5) c = uMaquette;
    if (uBlind > 0.5 && (vGid == uSelected || uBlind < 1.5)) vHatch = 0.0;
    // Hover and selection mix towards the theme's hover colour: black on light looks, white on the dark one.
    if (vGid == uHover || (vGid == uSelected && uBlind < 0.5)) {
      c = mix(c, uHoverTo, 0.35);
      h = mix(h, uHoverTo, 0.35);
    }
    vColor = c;
    vHatchInk = h;
    // On the terrain: the building stands on its own ground, lifted by ground * uRelief. Its wall bottoms
    // (position.y 0) reach down to the terrain under each corner and 2 m further, plus half of how much the ground
    // varies over that corner's cell (the skirt), so a slope never shows a gap under the uphill or downhill wall, even
    // where the ground dips between two corners; the skirt flies in with the building. Positions are decimetres.
    float lift = groundDm * uRelief;
    vRel = p.y * 0.1;
    if (position.y == 0.0 && uRelief > 0.0) {
      vec2 xz = (modelMatrix * vec4(position, 1.0)).xz;
      float skirt = min(hEff(xz) * 10.0 - lift, 0.0) - 20.0 - 5.0 * hRange(xz);
      p.y += skirt;
      vRel += skirt * 0.1;   // below the base by the skirt, keeping a fly-in's offset as the wall's top does
    }
    p.y += lift;
    vec4 w = modelMatrix * vec4(p, 1.0);
    vWorld = w.xyz;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;

const FRAG = /* glsl */`
  precision highp float;
  uniform vec3 uFogColor, uSun;
  uniform vec2 uFog;
  uniform float uEdgeBuildings;
  ${GRID_GLSL}
  ${FADE_GLSL}
  in vec3 vColor;
  in vec3 vWorld;
  in float vRel;
  flat in float vGid;
  flat in vec3 vHatchInk;
  flat in float vHatch;
  out vec4 outColor;
  // The share of a pixel a hatch line covers: lines HATCH_W of a period wide around every whole s, anti-aliased over
  // one pixel (fw: periods per pixel).
  float hatchLine(float s, float fw) {
    return clamp((${(HATCH_W / 2).toFixed(6)} - (0.5 - abs(fract(s) - 0.5))) / fw + 0.5, 0.0, 1.0);
  }
  void main() {
    #ifdef PICK
      float id = vGid + 1.0;
      outColor = vec4(mod(id, 256.0), mod(floor(id / 256.0), 256.0), floor(id / 65536.0), 255.0) / 255.0;
    #else
      // n faces the camera (screen-space derivatives), so on every wall seen from outside it is the outward normal.
      vec3 n = normalize(cross(dFdx(vWorld), dFdy(vWorld)));
      float d = length(vWorld - cameraPosition);
      // "Year unknown" on a hatched look: diagonal stripes fixed in the world (metres), ${HATCH_M} m apart. Roofs
      // take them from x - z (diagonal on screen from the hero view); walls from the distance along the wall plus
      // the height, so they slant the same way on every wall seen face on. Where those stripes would come closer than
      // about 5 px, every other one goes and the rest widen (${2 * HATCH_M} m apart, the same share of ink). As those
      // come from 6 to 3 px apart (lines 1.5 to 0.75 px wide), or the building from 2.6 to 3.6 km away, the hatch fades
      // into its own mean tone. So it shows at the home view, even on a 1x screen, never shimmers or moirés, and the
      // tone is the same at every distance. Computed for every fragment, outside any branch: the derivatives need
      // their neighbours.
      float roof = step(0.5, n.y);
      vec2 along = vec2(-n.z, n.x) / max(length(n.xz), 1e-4);
      float s = mix(dot(vWorld.xz, along) + vRel, vWorld.x - vWorld.z, roof) / ${(HATCH_M * Math.SQRT2).toFixed(6)};
      float fw = max(length(vec2(dFdx(s), dFdy(s))), 1e-6);   // stripe periods per pixel, across the stripes
      float line = mix(hatchLine(0.5 * s, 0.5 * fw), hatchLine(s, fw), smoothstep(4.0, 6.0, 1.0 / fw));
      float fade = smoothstep(3.0, 6.0, 2.0 / fw) * (1.0 - smoothstep(2600.0, 3600.0, d));
      vec3 base = mix(vColor, vHatchInk, vHatch * mix(${HATCH_W.toFixed(6)}, line, fade));
      // Low afternoon sun from the south-west (uSun, shared with the ground), a soft sky from above. The foot darkens
      // the first 12 m above the building's own base, and the skirt under it.
      float sun = max(dot(n, uSun), 0.0);
      float light = n.y > 0.9 ? 1.04 : ${glf(SHADING.wallMin)} + ${glf(SHADING.wallLit)} * sun;
      float foot = mix(0.82, 1.0, clamp(vRel / 12.0, 0.0, 1.0));
      vec3 c = base * light * foot;
      c = mix(uFogColor, c, mix(1.0, fadeAt(vWorld.xz), uEdgeBuildings));   // ?edgebuildings=1: they fade at the edge too
      c = mix(c, uFogColor, smoothstep(uFog.x, uFog.y, d));
      outColor = vec4(c, 1.0);
    #endif
  }
`;

function makeMaterial(tex, pick, born) {
  return new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    uniforms: { ...uniforms, uAttr: { value: tex }, uBorn: born },
    vertexShader: VERT,
    fragmentShader: FRAG,
    defines: pick ? { PICK: 1 } : {},
    side: THREE.DoubleSide,
  });
}

// ---------- Tiles ----------
const meshes = [];
let loaded = 0;
const queue = [...config.tiles];
const progressEl = document.getElementById('progress');
const pool = Array.from({ length: WORKERS }, () => new Worker('worker.js', { type: 'module' }));

function addTile(m) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(m.pos, 3));
  g.setAttribute('bld', new THREE.BufferAttribute(m.bld, 1));
  g.setIndex(new THREE.BufferAttribute(m.idx, 1));
  const rows = Math.ceil(m.nB / ATTR_W);
  const data = new Float32Array(ATTR_W * ATTR_FLOATS * rows);
  data.set(m.attr);
  if (photoGids) markPhotos(data, m.nB, photoGids, ATTR_FLOATS);
  const tex = new THREE.DataTexture(data, ATTR_W * ATTR_FLOATS / 4, rows, THREE.RGBAFormat, THREE.FloatType);
  tex.needsUpdate = true;
  // Bounds that hold the shader's lift and skirts at the most relief the viewer offers (web/bounds.js): three.js's own
  // would leave a tile on a hill culled at the screen's edge and missed by the pick pass.
  liftBounds(g, m, config.terrain);
  const born = { value: performance.now() / 1000 };
  const mesh = new THREE.Mesh(g, makeMaterial(tex, false, born));
  mesh.userData = { draw: mesh.material, pick: makeMaterial(tex, true, born), attr: m.attr, nB: m.nB };   // attr, nB: the pick's outline
  mesh.scale.setScalar(0.1);
  mesh.position.set(m.origin[0], 0, m.origin[1]);
  scene.add(mesh);
  meshes.push(mesh);
  fetchRestPacks();
}

// Tiles come in gzip packs (see pipeline/s03_tiles.py); offsets refer to the unpacked pack. pack0 is requested
// at once, the others when the first tile is on the map (addTile), or sooner if a worker needs one.
// config.packs holds file names ("pack0.bin.gz"); a tile's `pack` names its pack (an index also works).
const packs = {};
const packName = p => (typeof p === 'string' ? p : p.file);
const packOf = t => packName(typeof t.pack === 'number' ? config.packs[t.pack] : t.pack);
const fetchPack = name => (packs[name] ??= fetchGz(DATA + name));
let restRequested = false;
function fetchRestPacks() {
  if (restRequested) return;
  restRequested = true;
  // Two at a time, centre-out: the line stays busy without a burst of parallel requests.
  const names = config.packs.map(packName);
  for (let lane = 0; lane < 2; lane++) {
    (async () => { while (names.length) await fetchPack(names.shift()).catch(() => {}); })();
  }
}
fetchPack(packName(config.packs[0]));
for (const w of pool) {
  const next = async () => {
    const t = queue.shift();
    if (!t) return;
    try {
      const buf = (await fetchPack(packOf(t))).slice(t.offset, t.offset + t.length);
      w.postMessage({ buf, id: t.file }, [buf]);
    } catch (e) { loadFailed(e); }
  };
  // A tile that fails to parse throws inside the worker; without this its lane would stop at a percentage.
  w.onerror = e => loadFailed(e);
  w.onmessage = ({ data }) => {
    addTile(data);
    loaded++;
    progressEl.textContent = Math.round(100 * loaded / config.tiles.length);
    if (loaded === config.tiles.length && !failedId) {   // a failure stays
      document.getElementById('loading').hidden = true;
      document.getElementById('ready').textContent = T('ui.ready');   // the live region's "done" (finding 7)
      foldCreditSoon();
    }
    next();
  };
  next();
}

// ---------- Terrain ----------
// terrain.bin.gz (pipeline/s04_base.py) and water.bin go to web/terrain-worker.js after the first frame.
// It returns the land in chunks of terrain.chunk metres (each at 20 m, or beyond LOD_FAR at 40 m where that stays
// within web/terrain.js LOD_TOL of the 20 m grid), the exact cut along the shores and the municipality's edge and the
// quay walls (both in groups of two by two chunks, so they cull), and the water at its levels. Everything takes its
// height from one texture (uTerrain) as uRelief * t - uCutK * cut, so the Hills slider moves two uniforms and nothing
// is rebuilt. A failure leaves the flat land and water: the map stays usable, with a console warning.
const terrainGroup = new THREE.Group();
scene.add(terrainGroup);
const terrainMeshes = [];   // chunks, edge cells and walls: drawn as nothing (id 0) in the pick pass, hiding what is behind
const chunkMeshes = [];
let waterLevels = null;     // the water at its levels, which replaces the flat water once the terrain is in
const LOD_FAR = 4000;       // metres from the camera to a chunk's nearest corner, give or take 10%
Object.assign(uniforms, {
  uLand: { value: col(THEME.land) }, uWater: { value: col(THEME.water) }, uQuay: { value: col(THEME.quay) },
  uShade: { value: THEME.reliefShade },
});
uniforms.uEdgeBuildings.value = PARAMS.get('edgebuildings') === '1' ? 1 : 0;   // the M4 review's lever (Decision 4)
// Ground: the vertex's height and normal from the texture. The chunks' positions are decimetres from their corner
// (modelMatrix scales and places them); the edge cells' are metres (identity): the same shader serves both.
const GROUND_VERT = /* glsl */`
  ${GRID_GLSL}
  ${TERRAIN_GLSL}
  out vec3 vWorld;
  out vec3 vNormal;
  out float vWallH;
  void main() {
    vec4 w = modelMatrix * vec4(position.x, 0.0, position.z, 1.0);
    w.y = hEff(w.xz);
    vec2 g = hEffGrad(w.xz);
    vNormal = normalize(vec3(-g.x, 1.0, -g.y));
    vWorld = w.xyz;
    vWallH = 0.0;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;
// Quay walls: from the terrain's height at the shore (never under the water) down to the water's level. vWallH is the
// wall's true height there: a low bank keeps the ground's colour, a real quay (over 3 m) the look's stone.
const WALL_VERT = /* glsl */`
  ${GRID_GLSL}
  ${TERRAIN_GLSL}
  in float aTop;
  in float aLevel;
  out vec3 vWorld;
  out vec3 vNormal;
  out float vWallH;
  void main() {
    vec4 w = modelMatrix * vec4(position.x, 0.0, position.z, 1.0);
    float water = aLevel * uRelief, top = max(hEff(w.xz), water);
    w.y = aTop > 0.5 ? top : water;
    vNormal = vec3(0.0, 1.0, 0.0);   // unused: walls light from their own facing (TERRAIN_FRAG)
    vWorld = w.xyz;
    vWallH = (top - water) / max(uRelief, 0.001);
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;
const WATER_VERT = /* glsl */`
  uniform float uRelief;
  in float aLevel;
  out vec3 vWorld;
  out vec3 vNormal;
  out float vWallH;
  void main() {
    vec4 w = modelMatrix * vec4(position.x, aLevel * uRelief, position.z, 1.0);
    vNormal = vec3(0.0, 1.0, 0.0);
    vWorld = w.xyz;
    vWallH = 0.0;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;
// Ground in the look's land colour, shaded by the shared sun so that flat ground is exactly that colour (uShade, per
// look); walls shaded like a slope where the bank is low (most shores are natural) and lit like the buildings' walls in
// the look's quay colour where they stand over 3 m; water flat. The constants are themes.js SHADING, which the looks'
// colour checks (web/test/themes.test.mjs) use too. All fade into the sky at the municipality's edge
// and into the fog like the buildings. In the pick pass they write id 0 (nothing) with depth, so a hill hides what is
// behind it.
const TERRAIN_FRAG = /* glsl */`
  precision highp float;
  uniform vec3 uFogColor, uSun, uColour, uLand;
  uniform vec2 uFog;
  uniform float uShade, uKind;   // uKind: 0 ground, 1 wall, 2 water
  ${GRID_GLSL}
  ${FADE_GLSL}
  in vec3 vWorld;
  in vec3 vNormal;
  in float vWallH;
  out vec4 outColor;
  vec3 shaded(vec3 c, vec3 n) { return c * clamp(1.0 + uShade * (dot(n, uSun) - uSun.y),
    1.0 - ${glf(SHADING.dark)} * uShade, 1.0 + ${glf(SHADING.light)} * uShade); }
  void main() {
    #ifdef PICK
      outColor = vec4(0.0);
    #else
      vec3 c = uColour;
      if (uKind < 0.5) {
        c = shaded(c, normalize(vNormal));
      } else if (uKind < 1.5) {
        vec3 n = normalize(cross(dFdx(vWorld), dFdy(vWorld)));
        c = mix(shaded(uLand, n), c * (${glf(SHADING.wallMin)} + ${glf(SHADING.wallLit)} * max(dot(n, uSun), 0.0)),
          smoothstep(1.0, 3.0, vWallH));
      }
      c = mix(uFogColor, c, fadeAt(vWorld.xz));
      c = mix(c, uFogColor, smoothstep(uFog.x, uFog.y, length(vWorld - cameraPosition)));
      outColor = vec4(c, 1.0);
    #endif
  }
`;
function terrainMaterial(vert, colour, kind, pick, side = THREE.FrontSide) {
  return new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3, vertexShader: vert, fragmentShader: TERRAIN_FRAG, defines: pick ? { PICK: 1 } : {}, side,
    uniforms: { ...uniforms, uColour: uniforms[colour], uKind: { value: kind } },
  });
}

async function loadTerrain(base) {
  if (!TERRAIN) return;
  terrainState = 'loading';
  // a download that stalls (no answer, or no chunk of it, for FETCH_TIMEOUT_MS) is stopped, and the caller then loads
  // the flat land; a slow one that keeps arriving goes on
  const file = withTimeout((signal, alive) => fetchGz(`${DATA}${TERRAIN.file}`, 2, signal, alive), FETCH_TIMEOUT_MS,
    TERRAIN.file);
  const [buf, waterBuf] = await Promise.all([file, base]);
  // a worker that errs, refuses the file or hangs (WORKER_TIMEOUT_MS) rejects: the caller then loads the flat land
  const m = await askWorker(new Worker('terrain-worker.js', { type: 'module' }), { terrain: buf, water: waterBuf.slice(0),
    chunkCells: Math.round(TERRAIN.chunk / TERRAIN.cell), fadeM: FADE_M }, [buf]);
  const g = m.grid, RMAX = reliefMax;
  uniforms.uTerrain.value.dispose();
  uniforms.uTerrain.value = dataTexture(m.tex, g.nx, g.nz, THREE.RGFormat, THREE.FloatType);
  const fade = dataTexture(m.fade, g.nx, g.nz, THREE.RedFormat, THREE.UnsignedByteType);
  fade.magFilter = fade.minFilter = THREE.LinearFilter;
  uniforms.uFade.value.dispose();
  uniforms.uFade.value = fade;
  uniforms.uGridO.value.set(g.x0, g.z0);
  uniforms.uGridN.value.set(g.nx, g.nz);
  uniforms.uCell.value = g.cell;
  ground = makeGround({ ...g, tex: m.tex });   // the CPU reads the texture's own data: one copy of the grid
  const ground0 = terrainMaterial(GROUND_VERT, 'uLand', 0, false), ground1 = terrainMaterial(GROUND_VERT, 'uLand', 0, true);
  const add = (mesh, draw, pick, order) => {
    mesh.userData = { ...mesh.userData, draw, pick };
    mesh.renderOrder = order;   // after the buildings, so early depth rejects the ground they cover
    terrainGroup.add(mesh);
    terrainMeshes.push(mesh);
  };
  // The chunks: one shared vertex grid (decimetres from a chunk's corner), two index lists each, a box for culling
  // (the most relief the viewer offers over the chunk's highest node; 30 m under sea level for the walls' feet).
  const pos = new THREE.BufferAttribute(m.verts, 3);
  const span = Math.round(TERRAIN.chunk / g.cell);
  for (const c of m.chunks) {
    const box = new THREE.Box3(new THREE.Vector3(0, -300, 0),
      new THREE.Vector3(c.cells[0] * g.cell * 10, Math.max(0, c.hMax) * RMAX * 10 + 10, c.cells[1] * g.cell * 10));
    const geos = [c.lod0, c.lod1].map(idx => {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', pos);
      geo.setIndex(new THREE.BufferAttribute(idx, 1));
      geo.boundingBox = box;
      geo.boundingSphere = box.getBoundingSphere(new THREE.Sphere());
      return geo;
    });
    const mesh = new THREE.Mesh(geos[0], ground0);
    mesh.scale.setScalar(0.1);
    mesh.position.set(g.x0 + c.i0 * g.cell, 0, g.z0 + c.j0 * g.cell);
    const half = span * g.cell / 2;
    mesh.userData = { geos, lod: 0, centre: new THREE.Vector3(mesh.position.x + half, 0, mesh.position.z + half),
      radius: Math.SQRT2 * half };
    add(mesh, ground0, ground1, 1);
    chunkMeshes.push(mesh);
  }
  // Edge cells and walls: positions in metres, one buffer each, a mesh per group (its own index range and box) sharing
  // it; the leveled water is one mesh (it is hidden in the pick pass anyway).
  const geometryOf = (xz, idx, attrs) => {
    const p = new Float32Array(xz.length / 2 * 3);
    for (let k = 0; k < xz.length / 2; k++) { p[3 * k] = xz[2 * k]; p[3 * k + 2] = xz[2 * k + 1]; }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(p, 3));
    for (const [name, a] of Object.entries(attrs)) geo.setAttribute(name, new THREE.BufferAttribute(a, 1));
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    return geo;
  };
  const grouped = (geo, groups, draw, pick) => {
    for (const grp of groups) {
      const part = new THREE.BufferGeometry();
      for (const [name, a] of Object.entries(geo.attributes)) part.setAttribute(name, a);
      part.setIndex(geo.index);
      part.setDrawRange(grp.start, grp.count);
      const [x0, z0, x1, z1] = grp.box;
      part.boundingBox = new THREE.Box3(new THREE.Vector3(x0, -30, z0), new THREE.Vector3(x1, Math.max(0, grp.hMax) * RMAX + 1, z1));
      part.boundingSphere = part.boundingBox.getBoundingSphere(new THREE.Sphere());
      add(new THREE.Mesh(part, draw), draw, pick, 1);
    }
  };
  grouped(geometryOf(m.edge.xz, m.edge.idx, {}), m.edge.groups, ground0, ground1);
  const wallDraw = terrainMaterial(WALL_VERT, 'uQuay', 1, false, THREE.DoubleSide);
  grouped(geometryOf(m.walls.xz, m.walls.idx, { aTop: m.walls.top, aLevel: m.walls.level }), m.walls.groups, wallDraw,
    terrainMaterial(WALL_VERT, 'uQuay', 1, true, THREE.DoubleSide));
  waterLevels = new THREE.Mesh(geometryOf(m.water.xz, m.water.idx, { aLevel: m.water.level }),
    terrainMaterial(WATER_VERT, 'uWater', 2, false));
  waterLevels.geometry.boundingBox = new THREE.Box3(new THREE.Vector3(g.x0, -1, g.z0),
    new THREE.Vector3(g.x0 + (g.nx - 1) * g.cell, Math.max(0, ...m.levels) * RMAX + 1, g.z0 + (g.nz - 1) * g.cell));
  waterLevels.geometry.boundingSphere = waterLevels.geometry.boundingBox.getBoundingSphere(new THREE.Sphere());
  waterLevels.renderOrder = 2;
  flat.add(waterLevels);            // hidden in the pick pass, as the flat water is
  land.visible = water.visible = false;
  const waterPolys = parsePolygons(waterBuf);
  waterAt = (x, z) => levelAt(waterPolys, m.levels, x, z);
  for (const l of labels) if (l.mesh && l.L.water) l.mesh.material.userData.level.value = waterAt(l.x, l.z);
  terrainState = 'ready';
  setRelief(relief, true);          // the city rises (at once for a visitor who asked for less motion)
}

// The relief: uRelief eases to the slider's value, 1.2 s when the terrain first rises, 0.6 s on a move (from where it
// is, so a drag or a run of key presses follows smoothly), at once for reduced motion; uCutK follows (web/terrain.js
// cutFactor), and so does the camera (followGround). Flat until the terrain is ready.
let reliefTween = null, reliefRisen = false;
function applyRelief(R) {
  uRelief.value = R;
  uCutK.value = cutFactor(TERRACE, R);
}
function setRelief(value, animate = true) {
  relief = Math.min(reliefMax, Math.max(0, Number(value) || 0));
  const to = terrainState === 'ready' ? relief : 0, from = uRelief.value;
  const dur = reliefRisen ? 600 : 1200;
  if (terrainState === 'ready') reliefRisen = true;
  reliefTween = animate && !calm.matches && from !== to ? { from, to, t0: performance.now(), dur } : null;
  if (!reliefTween) applyRelief(to);
  switcher.markRelief();
}
function stepRelief(now) {
  if (!reliefTween) return;
  const k = (now - reliefTween.t0) / reliefTween.dur;
  applyRelief(ease(reliefTween.from, reliefTween.to, k));
  if (k >= 1) reliefTween = null;
}
// A move of the slider is the visitor's choice: remembered (the number), and ?relief= leaves the address (as look.js
// keeps ?theme= current), so a reload keeps the move instead of the link it was made on.
function chooseRelief(value) {
  setRelief(value);
  try { localStorage.setItem(RELIEF_KEY, String(relief)); } catch {}
  const u = new URL(location.href);
  if (u.searchParams.has('relief')) {
    u.searchParams.delete('relief');
    history.replaceState(null, '', u);
  }
}
// A chunk further than LOD_FAR (10% either way, so it does not flicker at the line) draws its 40 m level.
function updateLods() {
  for (const mesh of chunkMeshes) {
    const u = mesh.userData;
    const d = Math.max(0, camera.position.distanceTo(u.centre) - u.radius);
    const lod = d > LOD_FAR * (u.lod ? 0.9 : 1.1) ? 1 : 0;
    if (lod !== u.lod) { u.lod = lod; mesh.geometry = u.geos[lod]; }
  }
}
// After the controls each frame: the target rides on the ground (MapControls pans on a level plane through it), the
// camera keeps clear of the ground under it and around it (a ring of max(30 m, 5% of the distance): beside a cliff
// at 2.5x the ground rises within metres, and the ground's back faces are not drawn), and the near and far planes
// follow the distance, which keeps depth precise enough for wall bottoms, quays and water from 60 m to 30 km (a fixed
// near of 5 m flickered at 20 km).
// The north turn (stepNorth) runs before the controls and keeps the camera's height; the ride then moves target and
// camera together, so the turn keeps its azimuth. On hills the floor may lift the camera during a north turn (the
// floor wins over the north button's "keeps the tilt"), but the turn still ends exactly north.
// The ride closes the gap with a time constant of RIDE_S whatever the frame rate (dt, seconds since the last frame),
// all of it at once for a viewer who asks for less motion, and stops within 1 mm. A camera the floor lifts is aimed at
// the target again before the frame is drawn. The far plane stays at 60 km until the terrain is in: the flat land and
// water have no fog, so a nearer far plane would cut them off in plain view.
const RIDE_S = 0.1;
function followGround(dist, dt) {
  if (!flight) {
    const gap = surfaceAt(controls.target.x, controls.target.z) - controls.target.y;
    if (Math.abs(gap) > 1e-3) {
      const dy = gap * (calm.matches ? 1 : 1 - Math.exp(-dt / RIDE_S));
      controls.target.y += dy; camera.position.y += dy;
    }
  }
  const { x, z } = camera.position, r = Math.max(30, 0.05 * dist);
  let under = surfaceAt(x, z);
  for (let k = 0; k < 8; k++) under = Math.max(under, surfaceAt(x + r * Math.cos(k * Math.PI / 4), z + r * Math.sin(k * Math.PI / 4)));
  const floor = under + Math.max(20, 0.05 * dist);
  if (camera.position.y < floor) { camera.position.y = floor; camera.lookAt(controls.target); }
  const near = THREE.MathUtils.clamp(dist * 0.02, 2, 400);
  const far = terrainState === 'ready' ? Math.max(4000, dist * 4.5) : 60000;
  if (Math.abs(near - camera.near) > 0.1 * camera.near || Math.abs(far - camera.far) > 0.1 * camera.far) {
    camera.near = near;
    camera.far = far;
    camera.updateProjectionMatrix();
  }
}

// ---------- Picking ----------
const pickTarget = new THREE.WebGLRenderTarget(1, 1);
const pickPixel = new Uint8Array(4);
function pick(x, y) {
  const w = renderer.domElement.clientWidth, h = renderer.domElement.clientHeight;
  camera.setViewOffset(w, h, x, y, 1, 1);
  for (const m of meshes) m.material = m.userData.pick;
  for (const m of terrainMeshes) m.material = m.userData.pick;
  flat.visible = false;
  labelGroup.visible = false;
  const outlined = highlight.mesh.visible;
  highlight.mesh.visible = false;
  renderer.setRenderTarget(pickTarget);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  renderer.render(scene, camera);
  renderer.readRenderTargetPixels(pickTarget, 0, 0, 1, 1, pickPixel);
  renderer.setRenderTarget(null);
  renderer.setClearColor(THEME.sky, 1);
  flat.visible = true;
  labelGroup.visible = true;
  highlight.mesh.visible = outlined;
  for (const m of meshes) m.material = m.userData.draw;
  for (const m of terrainMeshes) m.material = m.userData.draw;
  camera.clearViewOffset();
  return pickPixel[0] + pickPixel[1] * 256 + pickPixel[2] * 65536 - 1;
}

// ---------- Building lookup ----------
const residentsLayer = layers.find(L => L.id === 'residents');
const contextLayers = layers;
// The card shows residents in their own section, so they are left out of its list of layers.
const groupsByBit = layers.filter(L => L !== residentsLayer).flatMap(L => L.groups.map(g => ({ ...g, layer: L })));

// The hot attributes: one fixed record per gid (decoded by tile.js).
const building = gid => ({ ...readAttrs(attrs, gid, config.attrStride), groups: [] });

// ---------- Building card ----------
// Hover shows a light card that follows the pointer: the band with the year and how it is known. A click pins it, and
// the pinned card adds the photo, the facts, the excerpt and the links (text first, so it looks finished
// without a photo). Names, architects, links and photo credits come from 64 lazy shards, cards/NN.json with
// NN = gid % 64; Wikipedia excerpts from wiki/NN.json (CC BY-SA 4.0, their own files), fetched only for a pinned card;
// photos from data/photos/<key> (s06_wiki), loaded only when a card that has one is pinned.
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const link = (href, text) => `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(text)}</a>`;
// The self-hosted latin font subsets lack "≈" (U+2248); the span gives it the system font on purpose (W7). The card
// and the legend's note use it.
const approx = s => esc(s).replace(/≈/g, '<span class="approx">≈</span>');
// One lazy family of shards (cards/ or wiki/): a shard that fails is forgotten, so the next card asks again, and the
// card shows what it has meanwhile (optional fetches fail soft). `failed(gid)`: its shard's last fetch
// failed, so the card says so instead of reading as a building with no details (the audit's finding 6).
function shardCache(dir, pick) {
  const cache = {}, failedAt = new Set();
  const of = gid => {
    const n = String(gid % 64).padStart(2, '0');
    // a failed shard is asked again only when a card is opened anew (of.retry), never by the redraw its failure asks for
    if (cache[n] === undefined && !failedAt.has(n)) {
      cache[n] = null;
      getJson(`${DATA}${dir}/${n}.json`).then(d => { cache[n] = d; failedAt.delete(n); refreshCard(); })
        .catch(() => { delete cache[n]; failedAt.add(n); refreshCard(); });
    }
    return pick(cache[n], gid) || {};
  };
  of.retry = () => failedAt.clear();
  of.failed = gid => failedAt.has(String(gid % 64).padStart(2, '0')) && !cache[String(gid % 64).padStart(2, '0')];
  return of;
}
const cardOf = shardCache('cards', (d, gid) => d?.[gid]);
// Each building's stadsdel: districts.bin.gz, one byte per gid naming config.districts (0: none), fetched
// with the first card and kept; a failed fetch is asked again by the next card.
let districtBytes = null, districtAsked = false;
function districtOf(gid) {
  if (!districtAsked && config.districts) {
    districtAsked = true;
    fetchGz(`${DATA}districts.bin.gz`).then(b => { districtBytes = new Uint8Array(b); refreshCard(); })
      .catch(() => { districtAsked = false; });
  }
  const c = districtBytes?.[gid];
  return c ? config.districts[c - 1] : '';
}
const wikiOf = shardCache('wiki', (d, gid) => d?.items?.[gid]);
// A shard that arrives after the card is drawn redraws it.
function refreshCard() {
  if (card.hidden) return;
  if (pinnedGid >= 0) pinCard(pinnedGid, ...lastPin);
  else if (hoverGid >= 0) { const g = hoverGid; hoverGid = -1; showCard(g, ...(pointer || lastPin)); }
}

function cardHtml(gid, pinned) {
  const b = building(gid), more = cardOf(gid), p = periods[b.period] || periods[0];
  const unknown = b.yflag === YFLAG.UNKNOWN;
  // A period-only building's big line is its period's name (web/card.js yearLine), never empty: an empty one would
  // read "Year unknown" (every period city.py ships has both labels, web/test/card.test.mjs; the years are a guard).
  const label = tr(p, 'label') || `${p.from}–${p.to}`;
  // The band is drawn as the map draws the building: its period colour, the estimate tone for an area, estimated or
  // period-only year, and "Year unknown" like the legend chip.
  const band = unknown ? THEME.unknown : isEstimate(b) ? estColors[b.period] : p.color;
  const place = placeLine({ ...more, dist: districtOf(gid) }, T);   // the first address and the stadsdel
  const head = `
    <header class="card-head" style="--band:${unknown ? unknownFill(THEME) : band};--band-ink:${inkOn(band)}">
      ${more.name ? `<h3 id="card-title">${esc(more.name)}</h3>` : ''}
      ${more.en && LANG === 'en' ? `<p class="en">${esc(more.en)}</p>` : ''}
      ${place ? `<p class="place">${esc(place)}</p>` : ''}
      <div class="when"><span class="y" ${more.name ? '' : 'id="card-title"'}>${approx(yearLine(b, label, T))}</span>
        ${unknown || b.yflag === YFLAG.PERIOD ? '' : `<span class="period">${esc(label)}</span>`}</div>
    </header>`;
  const why = pinned && whyAnchor(b);   // the pinned card links About's explanation of its year
  // A shard that failed: say so, in place of "No open record dates this building yet", which it cannot tell
  const failed = pinned && cardOf.failed(gid);
  const dating = failed && unknown ? `<p class="dating card-failed">${esc(T('card.failed'))}</p>`
    : `<p class="dating">${approx(sourceLine(b, T, more))}${why ? ` <a class="why" href="#about/${why}">${esc(T('card.why'))}</a>` : ''}</p>${
      failed ? `<p class="dating card-failed">${esc(T('card.failed'))}</p>` : ''}`;
  if (!pinned) return `${head}${dating}<p class="hint">${esc(T('card.hint'))}</p>`;
  // A curated building's rebuilds, raised storeys and extensions, on a second line under the dating line;
  // never on the hover card. Its class is its own (an e2e's `.dating` stays one line); its rules are the dating
  // line's, inline, with no top padding so it reads as that line's second (its rules are inline too).
  const rebuilt = rebuildLine(more, T);
  const rebuiltStyle = 'margin:0;padding:0 16px 8px;color:var(--muted);font-size:12px;line-height:1.45';
  const rebuiltHtml = rebuilt ? `<p class="rebuilt" style="${rebuiltStyle}">${esc(rebuilt)}</p>` : '';
  const architects = more.architects || [];
  const floors = floorsLine(b, T, more);
  const facts = [
    [`<span title="${esc(T('card.height.note'))}">${esc(T('card.height'))}</span>`, esc(heightLine(b, T))],
    floors && [esc(T('card.floors')), approx(floors)],
    architects.length && [esc(T(architects.length > 1 ? 'card.architects' : 'card.architect')), architects.map(esc).join(', ')],
    b.rating && [esc(T('card.rating')), `<i class="rating r${b.rating}"></i>${esc(ratingLine(b.rating, T))}`],
    more.prot && [esc(T('card.prot')), esc(protLine(more, T))],
  ].filter(Boolean);
  // A photo that failed to load stays off this card's redraws; its width and height (when known) keep its room.
  const ph = more.photo && !failedPhotos.has(more.photo.key) ? more.photo : null;
  const size = ph && ph.w > 0 && ph.h > 0 ? `width="${+ph.w}" height="${+ph.h}"` : '';
  const photo = ph && `
    <figure class="photo"><img src="data/photos/${esc(ph.key)}" ${size}
      alt="${esc(more.name ? T('card.photo.alt', { name: more.name }) : T('card.photo.alt.none'))}" loading="lazy" decoding="async">
      <figcaption>${photoCredit(ph, T).map(c => (c.href ? link(c.href, c.text) : esc(c.text))).join(' · ')}</figcaption></figure>`;
  const ex = more.wp ? extractFor(wikiOf(gid), LANG) : null;
  const excerpt = ex && `
    <section class="extract" lang="${ex.lang}"><p>${esc(ex.text)}</p>
      <p class="credit">${T('card.extract.credit', {
        wikipedia: link(fillUrl(config.links.wikipedia_rev, { lang: ex.lang, rev: ex.rev }), 'Wikipedia'),
        licence: link('https://creativecommons.org/licenses/by-sa/4.0/', 'CC BY-SA 4.0') })}</p></section>`;
  // The RAÄ record, a Wikidata item or an article would give a private house's exact years, so its card links none
  //. s03 already leaves them out of the card of every non-curated building in PRIVATE_HOUSE_KATEGORI;
  // cardLinks is a second guard for the RAÄ link.
  const links = cardLinks(more, b, T, config.links);
  const wrong = wrongHref(config.about?.contact, more, gid, T, config.version);   // once the map has an address
  const picked = gid === forcedGid && hiddenByMap(b) ? `<p class="picked">${esc(T('card.picked'))}</p>` : '';
  return `
    <button class="card-close" aria-label="${esc(T('card.close'))}">×</button>
    ${photo || ''}${head}${dating}${rebuiltHtml}${picked}
    <section><dl>${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
      ${b.rating ? `<p class="why">${esc(T('card.rating.why'))}</p>` : ''}</section>
    ${excerpt || ''}
    ${links.length ? `<section class="sources"><h4>${esc(T('card.readmore'))}</h4><p>${links.map(l => link(l.href, l.text)).join(' · ')}</p></section>` : ''}
    ${wrong ? `<p class="wrong"><a href="${esc(wrong)}">${esc(T('card.wrong'))}</a></p>` : ''}`;
}

const card = document.getElementById('card');
card.setAttribute('aria-label', T('card.label'));
let pinnedGid = -1;
let lastPin = [0, 0];
let focusBack = null;     // where the keyboard focus goes when a pinned card closes
const failedPhotos = new Set();   // photo keys that failed to load: not asked for again on a redraw
// A pinned card on a wide screen stays between the corner (the title, the count and its buttons) and the timeline, so
// a tall card (a photo and an excerpt) never covers them or a timeline handle; it scrolls inside when it is taller
// than that room. The hover card follows the pointer anywhere; on a phone the card is a sheet (styles.css).
function placeCard(x, y) {
  const room = card.classList.contains('pinned') && !phone.matches
    ? [document.querySelector('.corner').getBoundingClientRect().bottom + 8, hist.getBoundingClientRect().top - 8]
    : [12, innerHeight - 12];
  card.style.maxHeight = card.classList.contains('pinned') && !phone.matches ? `${Math.max(160, room[1] - room[0])}px` : '';
  const r = card.getBoundingClientRect();
  card.style.left = Math.max(12, Math.min(x + 18, innerWidth - r.width - 12)) + 'px';
  card.style.top = Math.max(room[0], Math.min(y + 18, room[1] - r.height)) + 'px';
}
let hoverGid = -1;
function showCard(gid, x, y) {
  if (pinnedGid >= 0 || phone.matches) return;
  if (cardsLocked()) { card.hidden = true; return; }
  if (gid < 0) { card.hidden = true; hoverGid = -1; return; }
  if (gid !== hoverGid || card.hidden) {
    // Re-render only when the building changes.
    hoverGid = gid;
    card.innerHTML = cardHtml(gid, false);
    card.classList.remove('pinned');
    card.removeAttribute('role');
    card.hidden = false;
  }
  placeCard(x, y);
}
// A pinned card is a non-modal dialog: it takes the keyboard focus (its close button) when it opens, and gives it
// back when it closes, by its button or Escape.
function pinCard(gid, x, y) {
  if (gid >= 0 && gid !== pinnedGid) pickSeq++;          // a new pin (not a redraw): a street's numbers still coming
                                                         // no longer move the camera
  if (gid !== forcedGid && forcedGid >= 0) force(-1);   // another building or none: the search pick is let go
  const was = pinnedGid;
  pinnedGid = gid;
  hoverGid = -1;
  uniforms.uSelected.value = gid;
  if (gid < 0) {
    const hadFocus = was >= 0 && card.contains(document.activeElement);     // read before the card hides
    card.hidden = true;
    card.classList.remove('pinned');
    card.removeAttribute('role');
    if (hadFocus) (focusBack?.isConnected ? focusBack : canvas).focus?.({ preventScroll: true });
    return;
  }
  if (was < 0) focusBack = document.activeElement;
  if (gid !== was) { cardOf.retry(); wikiOf.retry(); }    // a card opened anew asks a failed shard again
  // The same card drawn again (a shard arrived): keep where the reader was, its scroll and the link or button that
  // had the keyboard, instead of sending the focus back to the close button.
  const redraw = was === gid, scroll = card.scrollTop;
  // The focused link is found again by what it is (an excerpt arriving puts links before it), else by its place.
  const focusable = () => [...card.querySelectorAll('a[href], button')];
  const focusKey = el => `${el.tagName} ${el.getAttribute('href') || el.className} ${el.textContent}`;
  const focusAt = redraw ? focusable().indexOf(document.activeElement) : -1;
  const focusWas = focusAt >= 0 ? focusKey(document.activeElement) : '';
  card.innerHTML = cardHtml(gid, true);
  card.classList.add('pinned');
  card.setAttribute('role', 'dialog');
  card.setAttribute('aria-labelledby', 'card-title');
  lastPin = [x, y];
  collapsePanelOnPhone();
  card.hidden = false;
  const close = card.querySelector('.card-close');
  close.onclick = () => pinCard(-1);
  card.querySelector('.photo img')?.addEventListener('error', e => {
    failedPhotos.add(cardOf(gid).photo?.key);
    if (!e.target.isConnected || pinnedGid !== gid) return;    // a late error from a card drawn over since
    e.target.closest('.photo')?.remove();
    placeCard(...lastPin);
  });
  placeCard(x, y);
  if (!redraw) close.focus({ preventScroll: true });
  else {
    card.scrollTop = scroll;
    if (focusAt >= 0) {
      const now = focusable();
      (now.find(el => focusKey(el) === focusWas) || now[focusAt] || close).focus({ preventScroll: true });
    }
  }
}
// Escape closes the pinned card, unless it is closing another dialog (About, Look), which keeps the card.
addEventListener('keydown', e => {
  if (e.key === 'Escape' && !(e.target instanceof Element && e.target.closest('dialog'))) pinCard(-1);
});

// A click (not a drag) pins the building under the pointer, or clears the pin on empty ground.
let pointer = null, dragging = false, downAt = null;
canvas.addEventListener('pointermove', e => { pointer = [e.clientX, e.clientY]; });
canvas.addEventListener('pointerdown', e => {
  dragging = true; downAt = [e.clientX, e.clientY];
  if (pinnedGid < 0) card.hidden = true;
});
canvas.addEventListener('pointerup', e => {
  dragging = false;
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
  const gid = pick(e.clientX, e.clientY);
  if (quest && !solved && qStep().kind === 'find') { questClick(gid); return; }
  if (cardsLocked()) return;
  pinCard(gid === pinnedGid ? -1 : gid, e.clientX, e.clientY);
});
canvas.addEventListener('pointerleave', () => { pointer = null; if (pinnedGid < 0) card.hidden = true; uniforms.uHover.value = -1; });

// ---------- Flying to a building ----------
let flight = null;
function flyTo(x, z, done, distance = 520, up = 0) {
  const dir = camera.position.clone().sub(controls.target).normalize();
  if (dir.y < 0.45) { dir.y = 0.45; dir.normalize(); }
  // a phone's search pick looks down at least this steeply (flyAbove); the direction it faces is kept
  if (dir.y < up) dir.setY(0).setLength(Math.sqrt(1 - up * up)).setY(up);
  const target = new THREE.Vector3(x, surfaceAt(x, z), z);
  const toP = target.clone().add(dir.multiplyScalar(distance));
  if (calm.matches) {             // reduced motion: no sweep, the camera is there at once
    flight = null;
    controls.target.copy(target);
    camera.position.copy(toP);
    done?.();
    return;
  }
  flight = { t0: performance.now(), dur: 1400, fromT: controls.target.clone(), toT: target,
    fromP: camera.position.clone(), toP, done };
}

// ---------- Search ----------
// The field and its list are web/searchbox.js over web/search.js; the index (search/index.json) loads on the first
// focus. A pick flies there: an address or a building opens its card, drawn even where the map's settings would hide
// it (uForce) and with a note saying so; a street fits its buildings in view; a stadsdel its bounds. Nothing about a
// search is stored or written into the address.
let forcedGid = -1;
// The picked building is outlined along its edges in the look's accent colour (web/highlight.js; a look change decided
// 2026-10-17 in place of a red ring on the ground), so it can be found among neighbours that look the same (a hatched
// "Year unknown" block among others, where the selection tint alone barely shows); it goes when the pick is let go.
let pickSeq = 0;   // a newer pick or pinned card: a street's numbers arriving late leave the camera alone (final review F5)
const highlight = makeHighlight(THREE, { uRelief, attrFloats: ATTR_FLOATS, renderer, reduced: () => calm.matches });
function force(gid) {
  forcedGid = gid; uniforms.uForce.value = gid;
  highlight.show(gid, meshes);
}
// The card's "Picked from search" note follows the map's settings: shown exactly while they would hide the building.
// (The outline follows the ground itself: the terrain may arrive, or the Hills slider move, after the pick.)
function stepPick() {
  if (forcedGid < 0) return;
  const b = building(forcedGid);
  if (pinnedGid === forcedGid && !card.hidden && hiddenByMap(b) !== Boolean(card.querySelector('.picked'))) refreshCard();
}
// Would the map hide this building now? The shader's own tests: the timeline, a period shown alone, the unknown and
// estimate switches.
function hiddenByMap(b) {
  const legend = uniforms.uMode.value < 1.5;
  if (b.yflag === YFLAG.UNKNOWN) return legend && uniforms.uShowUnknown.value < 0.5;
  if (b.year > uniforms.uYear.value) return true;
  if (legend && !maskTarget[b.period]) return true;
  return uniforms.uMode.value === MODE.period && hideEst && isEstimate(b);
}
// On a phone the card is a sheet over up to 72% of the screen (styles.css), so the building must land in the band
// between the corner's buttons and the sheet's highest top. The camera looks down at least PHONE_UP (about 55°) and
// aims short of the building by s, which puts it n (in clip space) above the middle: s = n·t·D / (sin θ − n·t·cos θ),
// t = tan(fov / 2). At the flyTo's usual 25° the aim would have to be about a whole distance short.
const PHONE_UP = 0.82, PHONE_SHEET = 0.72;
function flyAbove(x, z, distance, done) {
  if (!phone.matches) return flyTo(x, z, done, distance);
  const up = Math.max(PHONE_UP, camera.position.clone().sub(controls.target).normalize().y);
  const f = controls.target.clone().sub(camera.position).setY(0);
  if (f.lengthSq() < 1e-6) f.set(0, 0, -1);
  f.normalize();
  const top = document.querySelector('.corner').getBoundingClientRect().bottom / innerHeight;
  const n = 1 - (top + 1 - PHONE_SHEET);              // the band's middle, from the top: (top + (1 − sheet)) / 2
  const t = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const s = n * t * distance / (up - n * t * Math.sqrt(1 - up * up));
  flyTo(x - f.x * s, z - f.z * s, done, distance, up);
}
async function pickResult(row, loadShard) {
  stopPlay();
  const my = ++pickSeq;
  if (row.gid !== undefined) {
    const b = building(row.gid);
    // The open card goes now: a shard of it arriving during the flight would pin it again and let this pick go.
    pinCard(-1);
    force(row.gid);
    // docked top right on a desktop, under the title and its buttons (placeCard adds 18 px); not when the visitor has
    // pinned another building or closed the pick during the flight
    flyAbove(b.x, b.z, 420, () => {
      if (forcedGid !== row.gid) return;
      pinCard(row.gid, innerWidth, document.querySelector('.corner').getBoundingClientRect().bottom - 8);
      highlight.pulse(performance.now());
    });
    return;
  }
  let box = row.box;
  if (row.kind === 'street') {
    const pairs = (await loadShard(row.shard).catch(() => ({})))[row.street] || [];
    if (my !== pickSeq) return;            // the visitor picked or pinned something else meanwhile
    const bs = pairs.map(p => building(p[1]));
    if (!bs.length) return;
    box = [Math.min(...bs.map(b => b.x)), Math.min(...bs.map(b => b.z)), Math.max(...bs.map(b => b.x)), Math.max(...bs.map(b => b.z))];
  }
  if (!box) return;
  const [x0, z0, x1, z1] = box;
  pinCard(-1);
  flyTo((x0 + x1) / 2, (z0 + z1) / 2, undefined, Math.min(5200, Math.max(500, 1.3 * Math.hypot(x1 - x0, z1 - z0))));
}
const searchRoot = document.querySelector('.search');
const searchOpen = document.querySelector('.search-open');
searchRoot.hidden = !FEATURES.search;
searchOpen.hidden = !FEATURES.search;
const searchBox = FEATURES.search ? mountSearch({
  root: searchRoot, openButton: searchOpen, getJson, base: `${DATA}search/`, T: () => T, onPick: pickResult,
  buildings: config.stats.buildings, isPhone: () => phone.matches, focusMap: () => canvas.focus?.({ preventScroll: true }),
  swatch: gid => { const b = building(gid); return b.yflag === YFLAG.UNKNOWN ? unknownFill(THEME) : isEstimate(b) ? estColors[b.period] : periods[b.period].color; },
}) : null;
// On a wide desktop the pill sits just right of the modes, whose width changes with the language.
// It never reaches under the title and the count: the pill narrows when the corner is wide, and where less than
// 180 px is left (a range or a long period widens the title) it moves under the modes. The corner's ResizeObserver
// calls this too (the final review's F6).
function placeSearch() {
  searchRoot.style.top = '';
  if (searchRoot.hidden || innerWidth <= 1100) { searchRoot.style.left = searchRoot.style.maxWidth = ''; return; }
  const modes = document.querySelector('.modes').getBoundingClientRect();
  const left = modes.right + 10, room = document.querySelector('.corner').getBoundingClientRect().left - 10 - left;
  if (room >= 180) {
    searchRoot.style.left = `${left}px`;
    searchRoot.style.maxWidth = `${room}px`;
  } else {
    searchRoot.style.left = `${modes.left}px`;
    searchRoot.style.top = `${modes.bottom + 8}px`;
    searchRoot.style.maxWidth = `${Math.max(180, modes.width)}px`;
  }
}
function stepFlight(now) {
  if (!flight) return;
  const k = Math.min(1, (now - flight.t0) / flight.dur), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
  controls.target.lerpVectors(flight.fromT, flight.toT, e);
  camera.position.lerpVectors(flight.fromP, flight.toP, e);
  if (k >= 1) { const d = flight.done; flight = null; d?.(); }
}

// ---------- Quests ----------
// Short walks through the city as riddles (pipeline/quests.py, checked by s13_quests): find a building on the map,
// guess a building's year with the colours hidden, or pick one of three answers. Each step is worth three crosses,
// the X of the city's arms; a hint or a wrong answer costs one. Progress stays in this browser.
let quests = [];
if (FEATURES.quests) getJson(`${DATA}quests.json`).then(q => { quests = q; }).catch(() => {});
const questEl = document.getElementById('quest');
const questsDlg = document.getElementById('quests');
const L10 = o => o?.[LANG] || o?.en || '';
const LEVEL = ['', 'Easy', 'Medium', 'Hard'];
const qStore = () => { try { return JSON.parse(localStorage.getItem('hfh-quests') || '{}'); } catch { return {}; } };
function qSave(id, patch) {
  try { const p = qStore(); p[id] = { ...(p[id] || {}), ...patch }; localStorage.setItem('hfh-quests', JSON.stringify(p)); } catch {}
}
const crosses = (n, of = 3) => `<span class="q-x" aria-label="${n} / ${of}">${Array.from({ length: of }, (_, i) =>
  `<i class="${i < n ? 'on' : ''}">×</i>`).join('')}</span>`;
const levelMark = lv => `<span class="q-level">${crosses(lv)}${t(LEVEL[lv])}</span>`;
// A small seeded generator: the same circle offset and answer order every time a step is played.
function rng(seed) { let h = 2166136261; for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) ^ Math.imul(h ^ (h >>> 13), 3266489909)) >>> 0) / 4294967296; }

function renderQuestList() {
  const p = qStore();
  const total = quests.reduce((n, q) => n + (p[q.id]?.best || 0), 0), max = quests.reduce((n, q) => n + q.steps.length * 3, 0);
  const tile = (q, st) => {
    const n = q.steps.length, done = Math.min(st.step || 0, n), complete = done >= n;
    return `<li class="q-tile l${q.level}${complete ? ' complete' : ''}">
      ${levelMark(q.level)}
      <h3>${esc(L10(q.title))}</h3><p>${esc(L10(q.intro))}</p>
      <footer><span class="q-progress">${complete ? `${st.score || 0} / ${n * 3}` : `${done} / ${n}`}</span>
        <button class="q-start" data-q="${q.id}">${complete ? t('Play again') : done ? t('Continue') : t('Start')}</button></footer></li>`;
  };
  document.getElementById('quests-body').innerHTML = `
    <h2 id="quests-title">${t('Quests')}</h2>
    <p class="q-lede">${t('Find buildings from riddles and old photos, guess their age with the colours switched off. Every answer is worth three crosses; hints and wrong answers cost one.')}</p>
    <p class="q-score">${t('Your crosses')}: <b>${total}</b> / ${max}</p>
    <ul class="q-grid">${quests.map(q => tile(q, p[q.id] || {})).join('')}</ul>`;
  questsDlg.querySelectorAll('.q-start').forEach(b => b.onclick = () => {
    const q = quests.find(q => q.id === b.dataset.q), st = qStore()[q.id] || {};
    questsDlg.close();
    const fresh = !st.step || st.step >= q.steps.length;
    startQuest(q, fresh ? 0 : st.step, fresh ? 0 : st.score || 0, fresh ? [] : st.marks || []);
  });
}
function openQuests() { renderQuestList(); questsDlg.showModal(); }
document.querySelector('.quests-open').onclick = openQuests;
questsDlg.querySelector('.about-close').onclick = () => questsDlg.close();
questsDlg.addEventListener('click', e => { if (e.target === questsDlg) questsDlg.close(); });

// The search circle: a red ring on the ground around (not centred on) the answer.
const ring = new THREE.Group();
ring.add(new THREE.Mesh(new THREE.RingGeometry(0.97, 1, 128), new THREE.MeshBasicMaterial({ color: 0xec0000, depthTest: false, transparent: true, opacity: 0.95 })));
ring.add(new THREE.Mesh(new THREE.CircleGeometry(0.97, 128), new THREE.MeshBasicMaterial({ color: 0xec0000, depthTest: false, transparent: true, opacity: 0.06 })));
ring.children.forEach(m => { m.rotation.x = -Math.PI / 2; m.renderOrder = 20; });
ring.visible = false;
scene.add(ring);

let quest = null, step = 0, score = 0, marks = [], hintsShown = 0, tries = 0, solved = false, revealed = false, lastDist = null;
let folded = false, guess = 1800;
const qStep = () => quest.steps[step];
const stepGids = s => (s.gids || []).filter(g => g >= 0 && g < config.stats.buildings);
function centre(gids) {
  const bs = gids.map(building);
  return [bs.reduce((a, b) => a + b.x, 0) / bs.length, bs.reduce((a, b) => a + b.z, 0) / bs.length];
}
// The map's state while a step asks about one building: its card locked, its colours hidden for a year riddle.
let quizGid = -1;
function setQuiz(gid, blind) {
  quizGid = gid;
  uniforms.uSelected.value = gid;
  uniforms.uBlind.value = gid < 0 ? 0 : blind ? 1 : 2;
  if (gid >= 0) { pinCard(-1); uniforms.uSelected.value = gid; }
}
const cardsLocked = () => quest && !solved && quizGid >= 0;

function startQuest(q, n, sc = 0, mk = []) {
  quest = q; step = n; score = sc; marks = mk;
  document.body.classList.add('questing');
  pinCard(-1);
  enterStep(true);
}
function enterStep(first) {
  hintsShown = 0; tries = 0; solved = false; revealed = false; lastDist = null; folded = false; guess = 1800;
  ring.visible = false;
  const s = qStep(), gids = stepGids(s);
  if (s.kind === 'find') {
    setQuiz(-1, false);
    if (first) {
      // Open on the whole quest: every building it visits in view.
      const all = quest.steps.flatMap(stepGids), [x, z] = centre(all);
      const spread = Math.max(...all.map(g => { const b = building(g); return Math.hypot(b.x - x, b.z - z); }));
      flyTo(x, z, null, Math.min(5200, Math.max(900, spread * 2.2)));
    }
  } else if (gids.length) {
    const b = building(gids[0]);
    setQuiz(gids[0], s.kind === 'year');
    questFly(b.x, b.z, s.kind === 'year' ? 300 : 380);
  }
  renderQuest();
}
// On a phone the quest sits over the top half of the map: aim past the building so it lands in the lower half.
function questFly(x, z, dist, done = null) {
  if (phone.matches) {
    const f = controls.target.clone().sub(camera.position).setY(0).normalize();
    x += f.x * dist * 0.2; z += f.z * dist * 0.2;
  }
  flyTo(x, z, done, dist);
}
function closeQuest() {
  document.body.classList.remove('questing');
  quest = null; questEl.hidden = true; ring.visible = false; setQuiz(-1, false);
}
function setModeNamed(name) {
  document.querySelector(`.modes button[data-mode="${MODE[name]}"]`)?.click();
}
function showRing() {
  const s = qStep(), [x, z] = centre(stepGids(s));
  const r = { 1: 220, 2: 300, 3: 380 }[quest.level] || 300;
  const k = rng(quest.id + step), a = k() * Math.PI * 2, d = r * 0.55 * Math.sqrt(k());
  const cx = x + Math.cos(a) * d, cz = z + Math.sin(a) * d;
  ring.position.set(cx, surfaceAt(cx, cz) + 2, cz); ring.scale.setScalar(r); ring.visible = true;
  questFly(cx, cz, r * 5);
}

function photoOf(s) {
  if (s.clue?.thumb) return { src: s.clue.thumb, credit: link(s.clue.page || s.clue.thumb, [s.clue.artist, s.clue.license].filter(Boolean).join(', ') || 'Wikimedia Commons') };
  return null;
}
const progress = () => `<div class="q-steps">${quest.steps.map((_, i) => `<i class="${i < step || (i === step && solved) ? 'done' : i === step ? 'now' : ''}"></i>`).join('')}
  <span>${step + 1} / ${quest.steps.length}</span></div>`;
const worth = () => {
  const s = qStep();
  if (s.kind === 'find') return revealed ? 0 : Math.max(1, 3 - hintsShown);
  if (s.kind === 'choice') return [3, 1, 0][Math.min(tries, 2)];
  return 3;
};
function yearPoints(d) { return d <= 5 ? 3 : d <= 20 ? 2 : d <= 50 ? 1 : 0; }

function renderQuest() {
  if (!quest) return;
  const s = qStep(), ph = photoOf(s);
  const title = esc(L10(quest.title));
  questEl.className = `quest k-${s.kind}${solved ? ' solved' : ''}${folded ? ' folded' : ''}`;
  let body = '';
  if (s.kind === 'find') {
    const hints = Array.from({ length: hintsShown }, (_, i) => i === 0 ? t('Look inside the red circle.') : L10(s.hints[i - 1]));
    const more = hintsShown < s.hints.length + 1;
    body = `
      ${ph && !solved ? `<figure class="q-photo${s.clue?.id ? ' old' : ''}"><img src="${esc(ph.src)}" alt="${t('A photo of the building to find')}">${ph.year ? `<span class="year">${ph.year}</span>` : ''}</figure><p class="q-credit">${ph.credit}</p>` : ''}
      <p class="q-riddle">${esc(L10(s.riddle))}</p>
      ${hints.length ? `<ul class="q-hints">${hints.map(h => `<li>${esc(h)}</li>`).join('')}</ul>` : ''}
      ${solved ? '' : `<p class="q-feedback">${t('Find it on the map and click it.')}</p>`}
      ${solved ? '' : `<div class="q-actions">
        ${more ? `<button class="q-hint">${t('Hint')} <small>−×</small></button>` : ''}
        ${s.mode ? `<button class="q-mode">${t(s.mode === 'floors' ? 'Colour by floors' : 'Colour by period')}</button>` : ''}
        <button class="q-reveal">${t('Show me')}</button>
        <span class="q-worth">${crosses(worth())}</span></div>`}`;
  } else if (s.kind === 'year') {
    body = `
      ${ph ? `<figure class="q-photo"><img src="${esc(ph.src)}" alt=""></figure><p class="q-credit">${ph.credit}</p>` : ''}
      <p class="q-riddle">${esc(L10(s.ask))}</p>
      ${solved ? '' : `<div class="q-year"><output>${guess}</output>
        <input type="range" min="1250" max="2025" step="1" value="${guess}" aria-label="${t('Your guess')}">
        <div class="q-scale"><span>1250</span><span>1500</span><span>1750</span><span>2000</span></div></div>
        <div class="q-actions"><button class="primary q-guess">${t('Guess')}</button><span class="q-worth">${crosses(3)}</span></div>`}`;
  } else {
    const order = s.options.map((o, i) => i).sort((a, b) => rng(quest.id + step + a)() - rng(quest.id + step + b)());
    body = `
      <p class="q-riddle">${esc(L10(s.ask))}</p>
      <div class="q-options">${order.map(i => `<button data-i="${i}" ${solved ? 'disabled' : ''} class="${solved && i === 0 ? 'right' : ''}">${esc(L10(s.options[i]))}</button>`).join('')}</div>
      ${solved ? '' : `<div class="q-actions"><span class="q-feedback"></span><span class="q-worth">${crosses(worth())}</span></div>`}`;
  }
  questEl.innerHTML = `
    <button class="q-close" aria-label="${t('Close')}">×</button>
    <header><b>${title}</b>${levelMark(quest.level)}</header>
    ${progress()}${body}${solved ? revealHtml(s) : ''}`;
  questEl.hidden = false;
  wireQuest(s);
}
function revealHtml(s) {
  const got = marks[step] ?? 0, last = step === quest.steps.length - 1;
  const extra = s.kind === 'year' ? `<p class="q-yeardiff">${t('Your guess')}: <b>${guess}</b>. ${t('Built')}: <b>${s.year}</b>. ${Math.abs(guess - s.year) === 0 ? t('Exactly right.') : `${Math.abs(guess - s.year)} ${t(Math.abs(guess - s.year) === 1 ? 'year off' : 'years off')}.`}</p>` : '';
  return `<div class="q-found">
    <div class="q-stamp" aria-hidden="true">${crosses(got)}</div>
    ${extra}
    <p>${esc(L10(s.reveal))}${s.sources?.length ? ' ' + s.sources.map((u, i) => link(u, s.sources.length > 1 ? `${t('Source')} ${i + 1}` : t('Source'))).join(', ') : ''}</p>
    <p class="q-earned">${revealed ? t('Shown, not found: no crosses.') : got === 3 ? t('Full marks.') : ''}</p></div>
    <div class="q-actions">${last ? `<button class="primary q-finish">${t('See the result')}</button>`
      : `<button class="primary q-next">${t('Next')}</button>`}<button class="q-card">${t('Open its card')}</button></div>`;
}
function wireQuest(s) {
  questEl.querySelector('header').onclick = () => { folded = !folded; questEl.classList.toggle('folded', folded); };
  questEl.querySelector('.q-close').onclick = closeQuest;
  const foldOnPhone = () => { if (phone.matches) { folded = true; questEl.classList.add('folded'); } };
  questEl.querySelector('.q-hint')?.addEventListener('click', () => { hintsShown++; if (hintsShown === 1) { showRing(); foldOnPhone(); } renderQuest(); if (phone.matches && hintsShown === 1) { folded = true; questEl.classList.add('folded'); } });
  questEl.querySelector('.q-mode')?.addEventListener('click', () => { setModeNamed(s.mode); foldOnPhone(); });
  questEl.querySelector('.q-reveal')?.addEventListener('click', () => {
    const g = stepGids(s)[0]; if (g === undefined) return;
    revealed = true; const b = building(g);
    questFly(b.x, b.z, 420, () => solve(g));
  });
  const range = questEl.querySelector('.q-year input');
  if (range) range.oninput = () => { guess = +range.value; questEl.querySelector('.q-year output').textContent = guess; };
  questEl.querySelector('.q-guess')?.addEventListener('click', () => solve(stepGids(s)[0], yearPoints(Math.abs(guess - s.year))));
  questEl.querySelectorAll('.q-options button').forEach(b => b.onclick = () => {
    if (+b.dataset.i === 0) { b.classList.add('right'); solve(stepGids(s)[0]); return; }
    tries++; b.classList.add('wrong'); b.disabled = true;
    questEl.querySelector('.q-actions .q-worth').innerHTML = crosses(worth());
    const fb = questEl.querySelector('.q-feedback'); fb.textContent = t('Not that one.'); fb.classList.remove('miss'); void fb.offsetWidth; fb.classList.add('miss');
  });
  questEl.querySelector('.q-next')?.addEventListener('click', () => { step++; qSave(quest.id, { step, score, marks }); enterStep(false); });
  questEl.querySelector('.q-finish')?.addEventListener('click', finished);
  questEl.querySelector('.q-card')?.addEventListener('click', () => { const g = stepGids(s)[0]; const b = building(g); quizGid = -1; uniforms.uBlind.value = 0; flyTo(b.x, b.z, () => pinCard(g, innerWidth * 0.3, 120), 380); });
}
function solve(gid, points) {
  const s = qStep();
  solved = true; folded = false; ring.visible = false;
  const got = points ?? worth();
  marks[step] = got; score += got;
  uniforms.uBlind.value = 0;
  quizGid = -1;
  if (gid >= 0) { pinCard(-1); uniforms.uSelected.value = gid; }
  const st = qStore()[quest.id] || {};
  const patch = { step: step + 1, score, marks };
  if (step === quest.steps.length - 1) patch.best = Math.max(st.best || 0, score);
  qSave(quest.id, patch);
  renderQuest();
}
// The result, and a line to share: one group of crosses per step, a dot for each one lost.
function finished() {
  const n = quest.steps.length, line = marks.map(m => '×'.repeat(m) + '·'.repeat(3 - m)).join(' ');
  const text = `${config.name} · ${L10(quest.title)}\n${line}\n${score} / ${n * 3}\n${location.origin}${location.pathname}`;
  const verdict = score >= n * 3 - 1 ? 'A true Stockholmer.' : score >= n * 2 ? 'You know your way around.' : score >= n ? 'A good walk.' : 'Time for a walk through town.';
  questEl.className = 'quest done';
  questEl.innerHTML = `
    <button class="q-close" aria-label="${t('Close')}">×</button>
    <header><b>${esc(L10(quest.title))}</b></header>
    <div class="q-result"><p class="q-total"><b>${score}</b> / ${n * 3}</p><p class="q-verdict">${t(verdict)}</p>
      <p class="q-line" aria-label="${score} / ${n * 3}">${line}</p></div>
    <div class="q-actions"><button class="primary q-share">${t('Copy result')}</button><button class="q-list">${t('More quests')}</button></div>`;
  questEl.hidden = false;
  ring.visible = false; setQuiz(-1, false);
  questEl.querySelector('.q-close').onclick = closeQuest;
  questEl.querySelector('.q-list').onclick = () => { closeQuest(); openQuests(); };
  questEl.querySelector('.q-share').onclick = async e => {
    try { await navigator.clipboard.writeText(text); e.target.textContent = t('Copied'); } catch { e.target.textContent = text.split('\n')[1]; }
  };
}
// Every click on the map while a find step is open.
function questClick(gid) {
  if (!quest || solved || gid < 0 || qStep().kind !== 'find') return;
  const s = qStep(), targets = stepGids(s);
  if (targets.includes(gid)) { solve(gid); return; }
  const fb = questEl.querySelector('.q-feedback');
  if (!fb) return;
  const b = building(gid);
  const d = Math.min(...targets.map(g => { const a = building(g); return Math.hypot(a.x - b.x, a.z - b.z); }));
  let msg = d < 40 ? t('Not this one, but right next to it.') : d < 200 ? t('Not this one. Very warm.')
    : d < 700 ? t('Not this one. A few streets away.') : t('Not this one. Far off.');
  if (lastDist !== null && d >= 40) msg += ' ' + t(d < lastDist - 20 ? 'Warmer than before.' : d > lastDist + 20 ? 'Colder than before.' : '');
  lastDist = d;
  fb.textContent = msg.trim();
  fb.className = `q-feedback ${d < 40 ? 'hot' : d < 200 ? 'warm' : 'cold'}`;
  void fb.offsetWidth; fb.classList.add('miss');
}
addEventListener('keydown', e => { if (e.key === 'Escape' && questsDlg.open) questsDlg.close(); });

// ---------- Panel ----------
const panelEl = document.getElementById('panel');
const panel = document.getElementById('panel-body');
const sheetHandle = panelEl.querySelector('.sheet-handle');
const phone = matchMedia('(max-width: 720px)');
const wide = matchMedia('(min-width: 1200px)');
// The legend folds away on every screen. On a phone it is a sheet: folded to one line until opened, and folded
// again when the city is the point. On a desktop it folds to a small pill. Only a click on the handle is
// remembered (localStorage 'hfh-legend'), so the automatic folding on a phone never overrides the viewer's choice.
function setCollapsed(c, remember = false) {
  panelEl.classList.toggle('collapsed', c);
  sheetHandle.setAttribute('aria-expanded', String(!c));
  sheetHandle.textContent = T(c ? 'ui.legend.show' : 'ui.legend.hide');
  if (remember) { try { localStorage.setItem(LEGEND_KEY, c ? 'collapsed' : 'open'); } catch {} }
}
sheetHandle.onclick = () => setCollapsed(!panelEl.classList.contains('collapsed'), true);
function collapsePanelOnPhone() { if (phone.matches) setCollapsed(true); }
let storedLegend = null;
try { storedLegend = localStorage.getItem(LEGEND_KEY); } catch {}
setCollapsed(initialCollapsed({ stored: storedLegend, phone: phone.matches, wide: wide.matches }));
// Each period's estimated share (histogramEst: area, estimate and period-only dates). While the switch hides the
// estimates the legend counts known years only.
const estTotals = periods.map(() => 0);
for (const v of Object.values(config.histogramEst || {})) v.forEach((n, i) => estTotals[i] += n);
const estTotal = estTotals.reduce((a, b) => a + b, 0);
// The legend's numbers follow the range, as the title and the count do (web/count.js periodCounts); at
// "Today" with the from-handle at rest they are the periods' totals.
const legendCounts = () => periodCounts(attrTally, uniforms.uYearFrom.value, uniforms.uYear.value, { est: estShown() });
function syncLegendCounts() {
  const n = legendCounts();
  panel.querySelectorAll('.swatch[data-i]').forEach(b => {
    const i = +b.dataset.i;
    b.querySelector('.n').textContent = fmt(n[i]);
    b.setAttribute('aria-label', swatchName(i, n[i]));
  });
}
// A legend button's name, "Funkis, 6 buildings": its two spans alone would read "Funkis6" (the audit's finding 8).
const swatchName = (i, n) => `${tr(periods[i], 'label')}, ${fmt(n)} ${T('ui.buildings')}`;
const fmt = n => n.toLocaleString(fmtLocale());
let activeLayer = null;
const SECTION_ORDER = ['Discover', 'Architecture', 'Trade and empire', 'Faith and community', 'Countries and communities',
  'The modern city', 'War and occupation'];
const groupOn = {};
let maskTarget = periods.map(() => 1);

const ICON = {
  'Discover': '<circle cx="8" cy="8" r="6.2"/><path d="M10.6 5.4 9 9 5.4 10.6 7 7z"/>',
  'Architecture': '<path d="M3 14.5V7l5-4.5L13 7v7.5z"/><path d="M6.5 14.5v-4h3v4"/>',
  'Trade and empire': '<path d="M2 11h12l-1.8 3H3.8z"/><path d="M8 2v9M8 3l4.5 6H8"/>',
  'Faith and community': '<path d="M8 1.5v4M6.2 3.3h3.6"/><path d="M4 14.5V8.5L8 5.5l4 3v6z"/><path d="M7 14.5v-3h2v3"/>',
  'The modern city': '<rect x="2.5" y="5" width="5" height="9.5"/><rect x="8.5" y="2" width="5" height="12.5"/><path d="M4.5 7.5h1M4.5 10h1M10.5 4.5h1M10.5 7h1M10.5 9.5h1"/>',
  'War and occupation': '<path d="M8 1.8 13 4v4c0 3.2-2.2 5.3-5 6.3-2.8-1-5-3.1-5-6.3V4z"/>',
};
const sectionIcon = sec => `<svg class="icon" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round">${ICON[sec] || ''}</svg>`;

function renderPanel() {
  const mode = uniforms.uMode.value;
  if (mode === MODE.period) {
    // The rebuild below drops the focus: a period chip picked from the keyboard gets it back (as switcher.js does).
    const focused = panel.contains(document.activeElement) ? document.activeElement.closest('.swatch[data-i]')?.dataset.i : undefined;
    const counts = legendCounts();
    panel.innerHTML = `<h2>${esc(T('ui.builtin'))}</h2><div class="swatches">${periods.map((p, i) => `
      <button class="swatch" data-i="${i}" aria-pressed="${!!maskTarget[i]}" aria-label="${esc(swatchName(i, counts[i]))}">
        <i style="background:${p.color}"></i><span>${esc(tr(p, 'label'))}</span><span class="n">${fmt(counts[i])}</span>
      </button>`).join('')}
      ${config.unknown ? `<div class="swatch unknown"><i style="background:${unknownFill(THEME)}"></i><span id="unknown-label">${esc(T('ui.unknown'))}</span><span class="n">${fmt(config.unknown)}</span>
        <button class="switch" aria-describedby="unknown-label unknown-hint"><span class="toggle" aria-hidden="true"></span>${esc(T('ui.show'))}</button>
        <span class="unknown-hint" id="unknown-hint"></span></div>` : ''}</div>
      <div class="est-row"><button class="switch" id="photo-only" aria-pressed="${photoOnly}" aria-describedby="photo-hint"><span class="toggle" aria-hidden="true"></span>${
        esc(T('ui.photoOnly'))}</button><span class="photo-hint" id="photo-hint"${photoOnly ? '' : ' hidden'}>${esc(T('ui.photoOnly.hint'))}</span></div>
      ${estTotal ? `<div class="est-row"><button class="switch" id="hide-est" aria-pressed="${hideEst}"><span class="toggle" aria-hidden="true"></span>${
        esc(T('ui.hideEst', { n: fmt(estTotal) }))}</button></div>` : ''}
      <p class="note">${approx(T('ui.legend.note'))}</p>`;
    const sw = panel.querySelector('.swatch.unknown button.switch');
    if (sw) { sw.onclick = flipUnknown; syncUnknownSwitch(); }
    const estSw = panel.querySelector('#hide-est');
    if (estSw) estSw.onclick = () => setHideEst(!hideEst);
    panel.querySelector('#photo-only').onclick = () => setPhotoOnly(!photoOnly);
    panel.querySelectorAll('.swatch[data-i]').forEach(b => b.onclick = () => {
      const i = +b.dataset.i, m = maskTarget;
      const solo = m.every((v, j) => (j === i) === !!v);
      maskTarget = periods.map((_, j) => (solo || j === i) ? 1 : 0);
      renderPanel(); drawHist();
    });
    if (focused !== undefined) panel.querySelector(`.swatch[data-i="${focused}"]`)?.focus();
  } else if (mode === MODE.floors) {
    // The look's own ramp (web/themes.js floors), and where the floors come from, in the page's language
    panel.innerHTML = `<h2>${esc(T('floors.title'))}</h2>
      <div class="ramp" style="background:${floorsGradient()}"></div>
      <div class="ramp-scale" style="position:relative;height:1.4em">${floorsScale()}</div>
      <p class="note">${approx(config.stats.floorsOsm
        ? T('floors.note.osm', { osm: fmt(config.stats.floorsOsm), height: fmt(config.stats.floorsHeight) })
        : T('floors.note.height'))}</p>`;
  } else if (activeLayer && activeLayer === residentsLayer) {
    const notes = Object.entries(residentsLayer?.notes || {});
    const people = notes.flatMap(([bag, n]) => n.people.map(p => ({ ...p, bag, at: n.at })))
      .sort((a, b) => b.links - a.links);
    panel.innerHTML = `<button class="back">${t('All context layers')}</button><h2 class="layer-title">${esc(tr(residentsLayer, 'title'))}</h2>
      <p class="layer-intro">${esc(tr(residentsLayer, 'text') || '')}</p>
      <input class="filter" type="search" placeholder="${t('Find a person')}" aria-label="${t('Find a person')}">
      <ul class="stories people">${people.map(p => `<li data-q="${esc((p.person + ' ' + (p.desc || '')).toLowerCase())}">
        <button class="story" data-bag="${p.bag}"><b>${esc(p.person)}</b>
        <span>${[p.born && p.died ? `${p.born}–${p.died}` : p.born, p.desc].filter(Boolean).map(esc).join(', ')}</span>
        <span class="addr">${esc(p.address)}</span></button></li>`).join('')}</ul>
      ${residentsLayer?.caveat ? `<p class="caveat">${esc(tr(residentsLayer, 'caveat'))}</p>` : ''}`;
    panel.querySelector('.back').onclick = () => setLayer(null);
    panel.querySelector('.filter').oninput = e => {
      const q = e.target.value.toLowerCase();
      panel.querySelectorAll('.people li').forEach(li => { li.hidden = q && !li.dataset.q.includes(q); });
    };
    panel.querySelectorAll('.story').forEach(b => b.onclick = () => {
      const n = residentsLayer.notes[b.dataset.bag];
      collapsePanelOnPhone();
      flyTo(n.at[0], n.at[1], () => { const gid = +b.dataset.bag; if (gid >= 0) pinCard(gid, innerWidth * 0.62, innerHeight * 0.18); }); // notes are keyed by gid
    });
  } else if (!activeLayer) {
    const sections = [...new Set(contextLayers.map(L => L.section))].sort((a, b) => SECTION_ORDER.indexOf(a) - SECTION_ORDER.indexOf(b));
    const secTitle = sec => tr(contextLayers.find(L => L.section === sec), 'section');
    panel.innerHTML = `<nav class="jump" aria-label="${t('Context layers')}">${sections.map(sec => `
      <button data-sec="${esc(sec)}" title="${esc(secTitle(sec))}" aria-label="${esc(secTitle(sec))}">${sectionIcon(sec)}</button>`).join('')}</nav>` +
      sections.map(sec => `<h2 class="section" id="sec-${sec.replace(/\W+/g, '-')}">${sectionIcon(sec)}${esc(secTitle(sec))}</h2><div class="layers">${contextLayers.filter(L => L.section === sec).map(L => `
      <button class="layer" data-id="${L.id}">
        <b>${esc(tr(L, 'title'))}</b><span class="n">${fmt(L.count)}</span><span class="era">${esc(tr(L, 'era'))}</span>
      </button>`).join('')}</div>`).join('');
    panel.querySelectorAll('.jump button').forEach(b => b.onclick = () =>
      panel.querySelector(`#sec-${b.dataset.sec.replace(/\W+/g, '-')}`).scrollIntoView({ behavior: 'smooth', block: 'start' }));
    panel.querySelectorAll('.layer').forEach(b => b.onclick = () => setLayer(contextLayers.find(l => l.id === b.dataset.id)));
  } else {
    panel.innerHTML = `<button class="back">${t('All context layers')}</button>
      <h2 class="layer-title">${sectionIcon(activeLayer.section)}${esc(tr(activeLayer, 'title'))}</h2><p class="layer-era">${esc(tr(activeLayer, 'era'))}</p>${layerDetail(activeLayer)}`;
    panel.querySelector('.back').onclick = () => setLayer(null);
    panel.querySelectorAll('.story').forEach(b => b.onclick = () => {
      const n = activeLayer.notes[b.dataset.bag];
      collapsePanelOnPhone();
      flyTo(n.at[0], n.at[1], () => {
        const gid = +b.dataset.bag; // notes are keyed by gid
        if (gid >= 0) pinCard(gid, innerWidth * 0.62, innerHeight * 0.18);
      });
    });
    panel.querySelectorAll('.swatch').forEach(b => b.onclick = () => {
      groupOn[b.dataset.bit] = groupOn[b.dataset.bit] === false;
      setLayer(activeLayer);
    });
  }
}

// The legend's ramp: the shader's stops at 1, about 3.4 and about 11 floors and at 40 (t = 0, 0.33, 0.66, 1 of a log
// scale). Its labels 1, 3, 8, 20, 40+ stand where the same scale puts them (3 at 30%, 8 at 56%, 20 at 81%), each
// shifted left by its own share so the end ones stay inside the bar.
const floorsGradient = () => `linear-gradient(90deg,${THEME.floors[0]} 0%,${THEME.floors[1]} 33%,${THEME.floors[2]} 66%,${THEME.floors[3]} 100%)`;
const floorsScale = () => [1, 3, 8, 20, 40].map(n => {
  const at = (Math.log(n) / Math.log(40) * 100).toFixed(1);
  return `<span style="position:absolute;left:${at}%;transform:translateX(-${at}%)">${n === 40 ? '40+' : n}</span>`;
}).join('');

function layerDetail(L) {
  const groups = L.groups.length > 1 ? `<div class="swatches">${L.groups.map((g, i) => `
    <button class="swatch" data-bit="${g.bit}" aria-pressed="${groupOn[g.bit] !== false}">
      <i style="background:${GROUP_COLORS[i]}"></i><span>${esc(tr(g, 'label'))}</span><span class="n">${fmt(g.count)}</span>
    </button>`).join('')}</div>` : '';
  // One line per story: a building made of several BAG parts carries the same note on each.
  const seenName = new Set();
  const named = Object.entries(L.notes || {}).filter(([, n]) => n.name && n.at && !seenName.has(n.name) && seenName.add(n.name));
  const stories = named.length ? `<h2 class="section">${t('Buildings and their stories')}</h2><ul class="stories">${named.map(([bag, n]) => `
    <li><button class="story" data-bag="${bag}"><b>${esc(tr(n, 'name'))}</b><span>${esc(tr(n, 'story'))}</span></button></li>`).join('')}</ul>` : '';
  return `<div class="layer-detail"><p>${esc(tr(L, 'text'))}</p>${groups}${stories}
    ${L.caveat ? `<p class="caveat">${esc(tr(L, 'caveat'))}</p>` : ''}
    <a href="${L.source.url}" target="_blank" rel="noopener">${esc(tr(L.source, 'label'))}</a></div>`;
}

// The hide-estimates switch: the shader, the count, the legend's totals and the histogram follow, and the
// choice is remembered. Like the unknown-year switch it changes in place, not by rebuilding the legend, so it keeps the keyboard
// focus. It stays live with a period shown alone: that period's estimates leave too.
function setHideEst(v) {
  hideEst = !!v;
  uniforms.uHideEst.value = hideEst ? 1 : 0;
  try { localStorage.setItem(EST_KEY, hideEst ? 'hidden' : 'shown'); } catch {}
  panel.querySelector('#hide-est')?.setAttribute('aria-pressed', String(hideEst));
  drawHist();   // the legend's numbers follow (syncLegendCounts)
}
// The photo switch: the list loads once, then each tile's flags are written once (addTile marks later tiles); the
// switch itself is one uniform. The choice goes into the URL.
async function setPhotoOnly(v) {
  photoOnly = !!v;
  panel.querySelector('#photo-only')?.setAttribute('aria-pressed', String(photoOnly));
  const hint = panel.querySelector('#photo-hint');
  if (hint) hint.hidden = !photoOnly;
  history.replaceState(history.state, '', photoOnlyHref(location.href, photoOnly));
  if (photoOnly && !photoGids) {
    try {
      photoGids = new Set(await (await fetch(DATA + 'photo-gids.json')).json());
    } catch (e) {
      console.warn('photo-gids.json did not load; the photo switch is off', e);
      photoOnly = false;
      panel.querySelector('#photo-only')?.setAttribute('aria-pressed', 'false');
      if (panel.querySelector('#photo-hint')) panel.querySelector('#photo-hint').hidden = true;
      history.replaceState(history.state, '', photoOnlyHref(location.href, false));
      return;
    }
    for (const mesh of meshes) {
      const tex = mesh.material.uniforms.uAttr.value;
      markPhotos(tex.image.data, mesh.userData.nB, photoGids, ATTR_FLOATS);
      tex.needsUpdate = true;
    }
  }
  uniforms.uPhotoOnly.value = photoOnly ? 1 : 0;
}
// Estimates are hidden only while the city is coloured by period (the switch lives in that legend).
const estShown = () => !(hideEst && uniforms.uMode.value === MODE.period);

function setLayer(L) {
  if (L) uniforms.uLayerAt.value = performance.now() / 1000;
  activeLayer = L;
  const bits = Array(MAX_GROUPS).fill(-1);
  if (L) L.groups.forEach((g, i) => { if (i < MAX_GROUPS && groupOn[g.bit] !== false) bits[i] = g.bit; });
  uniforms.uGroupBit.value = bits;
  renderPanel(); drawHist();
}

document.querySelectorAll('.modes button[data-mode]').forEach(b => b.onclick = () => {
  uniforms.uMode.value = +b.dataset.mode;
  // Only the period legend can show a period alone: any other mode lets go of it, so the map (uMask also applies in
  // Floors), the legend and the count agree.
  if (uniforms.uMode.value !== MODE.period) maskTarget = periods.map(() => 1);
  document.querySelectorAll('.modes button[data-mode]').forEach(x => x.setAttribute('aria-pressed', x === b));
  const bits = Array(MAX_GROUPS).fill(-1);
  if (activeLayer) activeLayer.groups.forEach((g, i) => { if (groupOn[g.bit] !== false) bits[i] = g.bit; });
  uniforms.uGroupBit.value = bits;
  if (uniforms.uMode.value === MODE.layers && activeLayer) uniforms.uLayerAt.value = performance.now() / 1000;
  // On a phone the sheet opens only when there is a choice to make: a layer to pick. On a desktop a legend the
  // viewer has folded stays folded: only a click on the handle opens it again.
  if (phone.matches && uniforms.uMode.value === MODE.layers && !activeLayer) setCollapsed(false);
  renderPanel(); drawHist();
});

// ---------- Timeline ----------
const hist = document.getElementById('hist');
const hctx = hist.getContext('2d');
const T0 = Math.floor(config.yearMin / 50) * 50, T1 = config.yearMax + 1;
// The from-handle rests just before the oldest building (uniforms.uYearFrom at load): nothing fades, no line.
const FROM_REST = config.yearMin - 1;
// Known years stack by period; area, estimate and period-only dates (histogramEst) stack above them in the estimate
// tone (estColors), and leave while the legend's switch hides them.
const years = Object.entries(config.histogram).map(([y, v]) => [+y, v]);
const yearsEst = Object.entries(config.histogramEst || {}).map(([y, v]) => [+y, v]);
const yearTotal = {};
for (const [y, v] of [...years, ...yearsEst]) yearTotal[y] = (yearTotal[y] || 0) + v.reduce((a, b) => a + b, 0);
const yMax = Math.max(1, ...Object.values(yearTotal));
const xOf = y => (y - T0) / (T1 - T0) * hist.clientWidth;
const yearOf = x => Math.round(T0 + x / hist.clientWidth * (T1 - T0));

function layerGroupsShown() {
  if (uniforms.uMode.value !== MODE.layers || !activeLayer) return [];
  return activeLayer.groups.map((g, i) => ({ ...g, color: GROUP_COLORS[i] })).filter(g => groupOn[g.bit] !== false);
}

// The count follows the range: what the map draws in colour between the two handles (web/count.js).
function visibleCount() {
  const Y = uniforms.uYear.value, Yf = uniforms.uYearFrom.value;
  const shown = layerGroupsShown();
  if (shown.length) return layerCount(shown, Yf, Y);
  return cityCount(attrTally, Yf, Y, i => uniforms.uMode.value !== MODE.period || maskTarget[i], unknownPref,
    { est: estShown() });
}

function drawHist() {
  const w = hist.clientWidth, h = hist.clientHeight, dpr = devicePixelRatio;
  hist.width = w * dpr; hist.height = h * dpr;
  hctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  hctx.clearRect(0, 0, w, h);
  const plotH = h - 20, bw = Math.max(1, w / (T1 - T0));
  const Y = uniforms.uYear.value, Yf = uniforms.uYearFrom.value;
  const shown = layerGroupsShown();
  const bar = (y, bh, top, color, on) => {
    hctx.fillStyle = color;
    hctx.globalAlpha = on ? (y <= Yf ? 0.3 : 1) : 0.18;
    hctx.fillRect(xOf(y), top - bh, bw, bh);
  };
  if (shown.length) {
    // Layer mode: the city behind in the look's "Year unknown" colour, the layer's own buildings in its colours.
    for (const [y, v] of years) {
      const bh = Math.sqrt(v.reduce((a, b) => a + b, 0) / yMax) * (plotH - 6);
      bar(y, bh, plotH, THEME.unknown, false);
    }
    // Stack the groups per year; the stack's total height follows sqrt(total), split in proportion.
    const total = {};
    for (const g of shown) for (const [y, c] of Object.entries(g.years)) total[y] = (total[y] || 0) + c;
    const lMax = Math.max(1, ...Object.values(total));
    const stack = {};
    for (const g of shown) for (const [ys, c] of Object.entries(g.years)) {
      const y = +ys, full = Math.sqrt(total[ys] / lMax) * (plotH - 6) * 0.9, bh = full * c / total[ys];
      bar(y, bh, plotH - (stack[y] || 0), g.color, y <= Y);
      stack[y] = (stack[y] || 0) + bh;
    }
  } else {
    // One bar per year, sqrt-scaled by its total, split in proportion: known dates below, estimates above.
    for (const [y, total] of Object.entries(yearTotal)) {
      const full = Math.sqrt(total / yMax) * (plotH - 6);
      let top = plotH;
      for (const [h, est] of [[config.histogram, false], [config.histogramEst || {}, true]]) {
        if (est && !estShown()) continue; // hidden by the legend's switch; the bars keep their scale
        (h[y] || []).forEach((c, i) => {
          if (!c) return;
          const bh = full * c / total;
          const masked = uniforms.uMode.value === MODE.period && !maskTarget[i];
          bar(+y, bh, top, est ? estColors[i] : periods[i].color, !masked && +y <= Y);
          top -= bh;
        });
      }
    }
  }
  hctx.globalAlpha = 1;
  hctx.fillStyle = THEME.ui['--muted'];
  hctx.font = `500 11px ${FONT}, sans-serif`;
  const step = w < 500 ? 200 : 100;
  for (let y = Math.ceil(T0 / step) * step; y <= T1; y += step) hctx.fillText(y, Math.min(w - 28, Math.max(0, xOf(y) - 13)), h - 4);
  hctx.fillStyle = THEME.ui['--ink'];
  hctx.fillRect(xOf(Y) - 1, 0, 2, plotH);
  if (Yf > FROM_REST) { hctx.fillStyle = THEME.ui['--muted']; hctx.fillRect(xOf(Yf) - 0.5, 0, 1, plotH); }
  drawLandmarks(w);
  placeGrips();
  if (uniforms.uMode.value === MODE.period) syncLegendCounts();
  // The title says what the map shows (web/count.js tallyTitle): "Today" at the end of the timeline rather than a
  // year that reads like a date, a year, a range once the from-handle moves, or the period shown alone.
  const solo = uniforms.uMode.value === MODE.period && maskTarget.filter(Boolean).length === 1 ? periods[maskTarget.indexOf(1)] : null;
  const tally = tallyTitle({ from: Yf, to: Y, start: config.yearMin, end: config.yearMax,
    period: solo && { name: tr(solo, 'label'), from: solo.from, to: solo.to } }, t);
  const yearEl = document.getElementById('year');
  yearEl.textContent = tally.title;
  yearEl.classList.toggle('named', tally.kind === 'period');
  document.getElementById('count').textContent = fmt(visibleCount());
  document.getElementById('tally-note').textContent = tally.note && ` · ${tally.note}`;
}

// Landmark labels: the curated buildings with an exact, article-checked year (stockholm.json
// `landmarks`, s03_tiles), the ones that fit drawn at their years in the strip above the bars (web/timeline.js); a click
// on one flies to the building and opens its card. Swedish names in both languages.
let placedLabels = [];
const LABEL_FONT = () => `600 10px ${FONT}, sans-serif`;
function drawLandmarks(w) {
  hctx.font = LABEL_FONT();
  placedLabels = placeLabels(config.landmarks || [], { xOf, width: w, measure: s => hctx.measureText(s).width });
  hctx.textBaseline = 'top';
  for (const L of placedLabels) {
    const on = L.year <= uniforms.uYear.value;
    hctx.globalAlpha = on ? 1 : 0.45;
    hctx.lineWidth = 3;
    hctx.strokeStyle = THEME.ui['--bg'];
    hctx.strokeText(L.name, L.x0, 1);
    hctx.fillStyle = THEME.ui['--ink'];
    hctx.fillText(L.name, L.x0, 1);
    hctx.fillRect(Math.round(xOf(L.year)), 13, 1, 5);
  }
  hctx.globalAlpha = 1;
  hctx.textBaseline = 'alphabetic';
}
function flyToLandmark(L) {
  stopPlay();
  flyTo(L.x, L.z, () => pinCard(L.gid, innerWidth * 0.62, innerHeight * 0.18));
}

// The handles: the pointer drags the nearer one on the canvas; each is also a slider for the keyboard (the grips,
// web/timeline.js stepYear: arrows a year, Shift or Page Up/Down ten, Home/End the ends), with its year, "Today" or
// "No start year" read out.
const grips = { uYearFrom: document.querySelector('.grip-from'), uYear: document.querySelector('.grip-to') };
let handle = null, labelDown = null;
// A press within GRAB_PX of a handle grabs it, even where a landmark's label sits: a handle's knob is the obvious thing
// to take hold of, and a landmark's year is where a handle often stops. Elsewhere a label is a link.
const GRAB_PX = 10;
const labelUnder = (x, y) => {
  const near = Math.min(Math.abs(x - xOf(uniforms.uYearFrom.value)), Math.abs(x - xOf(uniforms.uYear.value)));
  return near > GRAB_PX ? labelAt(placedLabels, x, y) : null;
};
hist.addEventListener('pointerdown', e => {
  // the main button only: a right-press opens the context menu, which can swallow the release and leave a handle
  // following a mouse with no button down
  if (e.button !== 0) return;
  const x = e.offsetX;
  hist.setPointerCapture(e.pointerId);   // a label's release too, wherever it lands
  const label = labelUnder(x, e.offsetY);
  labelDown = label && { L: label, x };
  if (labelDown) return;
  handle = Math.abs(x - xOf(uniforms.uYearFrom.value)) < Math.abs(x - xOf(uniforms.uYear.value)) ? 'uYearFrom' : 'uYear';
  stopPlay(); // first: it rounds the film's year, so a handle set against it is a whole year too
  moveHandle(x);
});
hist.addEventListener('pointermove', e => {
  if (handle && e.pointerType === 'mouse' && !e.buttons) handle = null;   // a release that never arrived
  if (handle) { moveHandle(e.offsetX); return; }
  // over a label the pointer says it is a link (styles.css's ew-resize elsewhere)
  if (!labelDown) hist.style.cursor = e.pointerType === 'mouse' && labelUnder(e.offsetX, e.offsetY) ? 'pointer' : '';
});
hist.addEventListener('pointerup', e => {
  // released on the label it was pressed on, and close to the press: dragged away, it is no click
  if (labelDown && Math.abs(e.offsetX - labelDown.x) < 5 && labelUnder(e.offsetX, e.offsetY) === labelDown.L) {
    flyToLandmark(labelDown.L);
  }
  handle = null; labelDown = null;
});
hist.addEventListener('pointercancel', () => { handle = null; labelDown = null; });
// Dragged back to the timeline's left end, or anywhere before the oldest building, the from-handle rests again.
function setHandle(which, y) {
  y = Math.max(T0, Math.min(config.yearMax, y));
  if (which === 'uYear') uniforms.uYear.value = Math.max(y, uniforms.uYearFrom.value + 1);
  else uniforms.uYearFrom.value = y <= Math.max(T0, FROM_REST) ? FROM_REST : Math.min(y, uniforms.uYear.value - 1);
  drawHist();
}
function moveHandle(x) { setHandle(handle, yearOf(x)); }
function placeGrips() {
  const set = (el, k, v) => { if (el.getAttribute(k) !== v) el.setAttribute(k, v); };
  const from = Math.round(uniforms.uYearFrom.value), to = Math.round(uniforms.uYear.value);
  // every position read before any is written: a write between two reads of the canvas's width forces a layout each
  // frame of Play
  const at = { uYearFrom: xOf(from), uYear: xOf(to) };
  for (const [which, el] of Object.entries(grips)) {
    const v = which === 'uYear' ? to : from, rest = which === 'uYearFrom' && v <= FROM_REST;
    el.style.left = `${rest ? 0 : at[which]}px`;
    el.classList.toggle('rest', rest);
    set(el, 'aria-label', T(which === 'uYear' ? 'timeline.to' : 'timeline.from'));
    // each handle's bounds are the keys' (below): a year apart from the other handle, as in WAI-ARIA's two-thumb slider
    set(el, 'aria-valuemin', String(which === 'uYear' ? from + 1 : FROM_REST));
    set(el, 'aria-valuemax', String(which === 'uYear' ? config.yearMax : to - 1));
    set(el, 'aria-valuenow', String(rest ? FROM_REST : v));
    // a year a landmark on the timeline was finished in says so: "1754, Stockholms slott" (the labels are drawn on
    // the canvas, so the keyboard and a screen reader meet them here)
    const named = (config.landmarks || []).filter(L => L.year === v).map(L => L.name).join(', ');
    set(el, 'aria-valuetext', rest ? T('timeline.none') : v >= config.yearMax ? T('timeline.today')
      : named ? `${v}, ${named}` : String(v));
  }
}
// While a handle has the keyboard its own value is read out on every key; the title and count above say the same, so
// their live region waits until the handle lets go.
const tallyEl = document.querySelector('.tally');
for (const el of Object.values(grips)) {
  el.addEventListener('focus', () => tallyEl.setAttribute('aria-live', 'off'));
  el.addEventListener('blur', () => tallyEl.setAttribute('aria-live', 'polite'));
}
for (const [which, el] of Object.entries(grips)) {
  el.addEventListener('keydown', e => {
    const value = Math.round(uniforms[which].value);
    const to = which === 'uYear';
    const next = stepYear(e.key, { value: !to && value <= FROM_REST ? Math.max(T0, FROM_REST) : value, shift: e.shiftKey,
      min: to ? Math.round(uniforms.uYearFrom.value) + 1 : FROM_REST, max: to ? config.yearMax : Math.round(uniforms.uYear.value) - 1 });
    if (next === null) return;
    e.preventDefault();
    stopPlay();
    setHandle(which, next);
  });
}

// Play: quickly through the sparse centuries, then slowly through the dense ones.
let playing = false, playT0 = 0, playStart = 0;
const playBtn = document.getElementById('play');
const playIcon = document.getElementById('play-icon');
const DURATION = (+new URLSearchParams(location.search).get('film') || 30) * 1000; // ?film=6 for a short film
function playYear(t) {
  const k = 0.35; // share of time spent before 1850
  return t < k ? T0 + (1850 - T0) * (t / k) : 1850 + (config.yearMax - 1850) * ((t - k) / (1 - k));
}
function startPlay() {
  playing = true; playStart = performance.now();
  // From "Today" the film starts again, just after the from-handle: before it everything stays faded.
  if (uniforms.uYear.value >= config.yearMax) uniforms.uYear.value = Math.max(T0, uniforms.uYearFrom.value + 1);
  playT0 = 0;
  while (playT0 < 1 && playYear(playT0) < uniforms.uYear.value) playT0 += 0.001;
  playIcon.setAttribute('d', 'M4 2.5h3v11H4zM9 2.5h3v11H9z');
  uniforms.uPlaying.value = 1;
  playBtn.setAttribute('aria-label', T('ui.pause'));
}
function stopPlay() {
  playing = false;
  uniforms.uPlaying.value = 0;
  uniforms.uRise.value = 0.01;
  uniforms.uYear.value = Math.round(uniforms.uYear.value);
  // The count follows the rounded year at once, as the title does: the count only redraws in a frame while the film
  // plays, so a year rounded up left it one year behind the map (the slower frames of the terrain showed it).
  drawHist();
  playIcon.setAttribute('d', 'M4 2.5v11l9-5.5z');
  playBtn.setAttribute('aria-label', T('ui.play'));   // in the page's language, not English
}
playBtn.onclick = () => playing ? stopPlay() : startPlay();

// ---------- Buildings without a year ----------
// Left alone they stand at "Today" and leave whenever the map shows the past: during Play, with the timeline dragged
// back, or with the from-handle moved (web/unknown.js unknownShown). The legend's "Year unknown" row has a switch,
// "Show", that always reads what the map does now: on while they stand, off while they are gone. Flipped, it turns
// off what is on and on what is off, and that choice ('show' or 'hide') then holds at every year and is remembered
// on the device. With a period shown alone they are hidden like every other period, and the switch
// reads off and is disabled. stepUnknown eases uShowUnknown towards what unknownShown says every frame, and the
// vertex shader sinks them into the ground and raises them again like a context layer: out in half a second, so the
// film starts on an empty city, back in the layer's own 0.88 s. A period picked alone takes them away and brings them
// back at once, as it does the other periods; so does a viewer who asks for less motion. The count takes them in
// where they are drawn, and only at "Today" (web/count.js), so a flip redraws it.
const calm = matchMedia('(prefers-reduced-motion: reduce)');
const store = () => localStorage;
let unknownPref = readPref(store);
function unknownNow() {
  const solo = !maskTarget.every(Boolean);
  return { solo, shown: unknownShown({ from: uniforms.uYearFrom.value, to: uniforms.uYear.value, start: config.yearMin,
    end: config.yearMax, playing, pref: unknownPref, solo }) };
}
uniforms.uShowUnknown.value = unknownNow().shown ? 1 : 0; // a visitor who chose "hide" never sees them sink at load
let unknownSolo = false, unknownWas = null;
function stepUnknown(dt) {
  const { shown, solo } = unknownNow();
  const u = uniforms.uShowUnknown;
  if (solo !== unknownSolo || calm.matches) u.value = shown ? 1 : 0;
  else u.value = easeShown(u.value, shown, dt);
  if (shown !== unknownWas || solo !== unknownSolo) syncUnknownSwitch();
  unknownSolo = solo; unknownWas = shown;
}
// The switch changes in place, not by rebuilding the legend, so it keeps the keyboard focus.
function syncUnknownSwitch() {
  const sw = panel.querySelector('.swatch.unknown button.switch');
  if (!sw) return;
  const { shown, solo } = unknownNow();
  sw.setAttribute('aria-pressed', String(shown));
  if (solo) sw.setAttribute('aria-disabled', 'true');
  else sw.removeAttribute('aria-disabled');
  const hint = panel.querySelector('.unknown-hint');
  if (hint) hint.textContent = t(unknownHint(unknownPref, solo));
}
function flipUnknown() {
  const now = unknownNow();
  if (now.solo) return; // disabled: a period is shown alone
  unknownPref = prefAfterClick({ ...now, pref: unknownPref });
  writePref(store, unknownPref);
  syncUnknownSwitch();
  drawHist(); // the count follows the map
}

// ---------- Facing north ----------
// The compass next to Look and About (index.html .north-open, web/north.js). A press, or the N key, turns the map to
// face north the short way round in half a second, at once for a viewer who asks for less motion (calm, above). Only
// the azimuth changes: each frame the camera moves round the place at its own height and distance, so the place, the
// zoom and the tilt stay, and a zoom during the turn is kept. A drag on the map cancels it. The controls' inertia
// (damping) is stopped as the turn starts and their spin held at nought while it runs, so the turn ends exactly north
// and stays there. A flight (flyTo) owns the camera until it lands: a press during one does nothing, and a flight that
// starts during a turn ends it (review round 1: the flight used to put the map back in one frame). The needle follows
// the azimuth on every frame it changes (stepNeedle); the hero view and flights move the camera as before, and the
// needle simply follows.
const northBtn = document.querySelector('.north-open');
const needleEl = northBtn.querySelector('svg');
let turn = null, needleAt = null;
function faceNorth() {
  if (flight) return;
  turn = northTurn(controls.getAzimuthalAngle(), performance.now(), { calm: calm.matches });
  // The vendored OrbitControls' (r186) own inertia: a fling just before must not carry on (web/test/north.test.mjs).
  controls._sphericalDelta.set(0, 0, 0);
  controls._panOffset.set(0, 0, 0);
}
function stepNorth(now) {
  if (!turn) return;
  if (flight) { turn = null; return; }
  const { theta, done } = turnAt(turn, now);
  const p = camera.position, c = controls.target, h = Math.hypot(p.x - c.x, p.z - c.z);
  p.set(c.x + h * Math.sin(theta), p.y, c.z + h * Math.cos(theta));
  controls._sphericalDelta.theta = 0;
  if (done) turn = null;
}
function stepNeedle() {
  const deg = needleDeg(controls.getAzimuthalAngle());
  if (deg === needleAt) return;
  needleAt = deg;
  needleEl.style.transform = `rotate(${deg}deg)`;
}
northBtn.onclick = faceNorth;
canvas.addEventListener('pointerdown', () => { turn = null; });
addEventListener('keydown', e => {
  if ((e.key === 'n' || e.key === 'N') && !e.ctrlKey && !e.metaKey && !e.altKey && !e.repeat && !typingIn(e.target)) faceNorth();
});
// + and - zoom (= and _ too, the same keys unshifted), as the arrows pan and Shift + arrows turn (the audit's finding 9).
function zoomBy(k) {
  flight = null;
  const off = camera.position.clone().sub(controls.target);
  off.setLength(THREE.MathUtils.clamp(off.length() * k, controls.minDistance, controls.maxDistance));
  camera.position.copy(controls.target).add(off);
  controls.update();
}
addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey || typingIn(e.target)) return;
  if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomBy(0.8); }
  else if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomBy(1.25); }
});
// The map takes the keyboard too (the audit's finding 1): Tab reaches it, a cross marks the middle of the screen while
// it has the keyboard, and Enter pins the building there, as a click would.
canvas.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || e.repeat) return;
  e.preventDefault();                      // or the Enter would also press the card's close button, focused by now
  const x = innerWidth / 2, y = innerHeight / 2, gid = pick(x, y);
  if (gid >= 0) pinCard(gid, x, y);
});

// ---------- Loop ----------
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  drawHist();
  if (pinnedGid >= 0 && !card.hidden) placeCard(...lastPin);    // the docked card's room follows the window
  placeSearch();
}
addEventListener('resize', resize);
function applyStaticText() {
  document.documentElement.lang = LANG;
  document.querySelector('.dek').textContent = config.subtitle?.[LANG] || config.subtitle?.en || '';
  document.querySelector('meta[name="description"]')?.setAttribute('content', T('ui.description'));
  // Every static text and label by its id (data-i18n, data-i18n-aria in index.html)
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = T(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-aria]').forEach(el => el.setAttribute('aria-label', T(el.dataset.i18nAria)));
  northBtn.setAttribute('aria-label', T('ui.north'));
  northBtn.title = `${T('ui.north')} (N)`;
  renderAbout();
  document.getElementById('credit').innerHTML = cornerHtml(config.attribution, T);   // the corner credit
  document.querySelector('.quests-open span').textContent = t('Quests');
  document.querySelector('.tally-count').childNodes[1].textContent = ' ' + T('ui.buildings');
  document.querySelector('.howto').textContent = t(howto(navigator));
  const ld = document.getElementById('loading');
  if (failedId) ld.textContent = T(failedId);   // a failed start keeps its message, in the new language
  else if (ld.firstChild) ld.firstChild.textContent = T('ui.loading') + ' ';
  const ready = document.getElementById('ready');
  if (ready.textContent) ready.textContent = T('ui.ready');
  playBtn.setAttribute('aria-label', T(playing ? 'ui.pause' : 'ui.play'));
  document.querySelectorAll('.lang [data-lang]').forEach(b => b.setAttribute('aria-pressed', b.dataset.lang === LANG));
  sheetHandle.textContent = T(panelEl.classList.contains('collapsed') ? 'ui.legend.show' : 'ui.legend.hide');
  card.setAttribute('aria-label', T('card.label'));
  switcher.render();
  searchBox?.applyText();
  document.getElementById('search-list').setAttribute('aria-label', T('search.list'));
  placeSearch();
}
// About (web/about.js): written from stockholm.json in the page's language, with the sources (each licence
// linked: CC BY attribution needs both, stockholm.json attribution). #about or #about/<section> opens it there, so the card's
// "Why?" links and the corner credit can point into it; its own section links scroll without changing the address.
const about = document.getElementById('about');
const aboutBody = document.getElementById('about-body');
function renderAbout() {
  aboutBody.innerHTML = aboutHtml(config, T, t(howto(navigator)));
  aboutBody.lang = LANG;
}
function openAbout(section = '') {
  if (!about.open) about.showModal();
  const el = section && document.getElementById(`about-${section}`);
  if (el) { el.scrollIntoView({ block: 'start' }); el.focus({ preventScroll: true }); } else about.scrollTop = 0;
}
function aboutFromHash() { const s = aboutTarget(location.hash); if (s !== null) openAbout(s); }
addEventListener('hashchange', aboutFromHash);
aboutBody.addEventListener('click', e => {
  const a = e.target.closest('a[data-section]');
  if (a) { e.preventDefault(); openAbout(a.dataset.section); }
});
document.querySelector('.about-open').onclick = () => openAbout();
about.querySelector('.about-close').onclick = () => about.close();
about.addEventListener('click', e => { if (e.target === about) about.close(); });
// Closing it lets go of an #about link, so the back button and a reload show the map.
about.addEventListener('close', () => {
  if (aboutTarget(location.hash) !== null) history.replaceState(null, '', location.pathname + location.search);
});

function setLang(l) {
  LANG = l;
  T = makeT(I18N, LANG);
  try { localStorage.setItem('hfh-lang', l); } catch {}
  // The switch never writes ?lang= (a shared link opens in each reader's own language); a ?lang= that came with
  // the link goes, so a reload keeps the visitor's choice.
  const u = new URL(location.href);
  if (u.searchParams.has('lang')) { u.searchParams.delete('lang'); history.replaceState(null, '', u); }
  applyStaticText(); renderPanel(); drawHist();
  refreshCard();
  if (quest && !questEl.hidden && !questEl.classList.contains('done')) renderQuest();
  if (questsDlg.open) renderQuestList();
}
document.querySelectorAll('.lang [data-lang]').forEach(b => b.onclick = () => setLang(b.dataset.lang));

// ---------- Looks ----------
// A switch (web/look.js; the Look button, web/switcher.js) re-applies the look to everything drawn in its colours:
// the page, sky and fog, land and water, the buildings' palette, the street names (redrawn in the look's font), the
// legend, the timeline and an open card. Called at startup and on every switch; nothing reloads.
function applyLook(name) {
  applyPageLook(name);
  periods.forEach((p, i) => {
    p.color = THEME.periods[i] || config.periods[i].color;
    estColors[i] = estimateTone(p.color, THEME.estimateTo);
  });
  renderer.setClearColor(THEME.sky);
  land.material.color.set(THEME.land);
  water.material.color.set(THEME.water);
  uniforms.uLand.value.set(THEME.land);
  uniforms.uWater.value.set(THEME.water);
  uniforms.uQuay.value.set(THEME.quay);
  uniforms.uShade.value = THEME.reliefShade;
  uniforms.uPalette.value.forEach((c, i) => c.set(periods[i].color));
  uniforms.uMaquette.value.set(THEME.maquette);
  uniforms.uUnknown.value.set(THEME.unknown);
  uniforms.uHatch.value = THEME.unknownHatch ? 1 : 0;
  uniforms.uHatchInk.value.set(THEME.unknownHatch || THEME.unknown);
  uniforms.uFloors.value.forEach((c, i) => c.set(THEME.floors[i]));
  uniforms.uEstimateTo.value.set(THEME.estimateTo);
  uniforms.uHoverTo.value.set(THEME.hoverTo);
  uniforms.uFogColor.value.set(THEME.sky);
  redrawLabels();
  recolourLegend(); drawHist(); refreshCard();
}
// The period legend and the Floors ramp take the new colours in place: rebuilt, the legend would lose its scroll and
// focus. The context layers' panel draws nothing in the look's colours.
function recolourLegend() {
  panel.querySelectorAll('.swatch[data-i] > i').forEach(el => { el.style.background = periods[el.parentNode.dataset.i].color; });
  const ramp = panel.querySelector('.ramp');
  if (ramp) ramp.style.background = floorsGradient();
  const unknown = panel.querySelector('.swatch.unknown > i');
  if (unknown) unknown.style.background = unknownFill(THEME);
}
// What an atmosphere's start(ctx) gets to work with (web/look.js); none are built yet.
looks.atmospheres.context = { scene, uniforms, camera, renderer, get theme() { return THEME; } };
pageLookOnly(); // applyLook takes over, the page's own colours included
looks.subscribe(applyLook);

applyStaticText();
renderPanel();
if (photoOnly) setPhotoOnly(true);
applyLook(looks.current);
resize();
document.fonts?.ready.then(() => { drawHist(); placeSearch(); });
aboutFromHash();
// The corner credit: always shown on a desktop; on a phone it folds into its (i) button 5 s after the city
// is on screen (counted from the loading line's end, so a slow load does not fold it unseen), and the button opens it
// again for good. Its links into About work through the hash (#about/sources). On a phone it sits under the corner,
// however tall a wrapped period name or a larger text makes it; a phone turned wide shows it whole, as a desktop does.
const credits = document.querySelector('.credits'), creditOpen = document.querySelector('.credit-open');
const corner = document.querySelector('.corner');
function foldCredit(folded) {
  credits.classList.toggle('folded', folded);
  creditOpen.hidden = !folded;
  creditOpen.setAttribute('aria-expanded', String(!folded));
}
function foldCreditSoon() { setTimeout(() => { if (phone.matches) foldCredit(true); }, 5000); }
function placeCredit() { credits.style.top = phone.matches ? `${corner.getBoundingClientRect().bottom + 8}px` : ''; }
new ResizeObserver(() => { placeCredit(); placeSearch(); }).observe(corner);
addEventListener('resize', placeCredit);   // the corner can move (the safe area) without changing size
phone.addEventListener('change', () => {
  placeCredit();
  if (phone.matches) return;
  const focused = document.activeElement === creditOpen;
  foldCredit(false);
  if (focused) credits.querySelector('#credit a')?.focus();
});
placeCredit();
creditOpen.onclick = () => {
  foldCredit(false);
  credits.querySelector('#credit a')?.focus();   // the button goes; focus stays in the credit, not on the page
};
// ?q=: search once on load and pick the top row (picking never writes ?q= back).
const askedQ = new URLSearchParams(location.search).get('q');
if (searchBox && askedQ) searchBox.runQuery(askedQ).catch(() => {});

// ---------- Debug ----------
// ?debug=1 shows renderer statistics; scripts/measure.mjs reads the same numbers from __dbg.stats().
const frameMs = [];
let lastFrameAt = 0;
function stats() {
  const r = renderer.info.render, m = renderer.info.memory;
  const fps = frameMs.length ? 1000 * frameMs.length / frameMs.reduce((a, b) => a + b, 0) : 0;
  return {
    version, theme: THEME_NAME, tileSize: config.tileSize, calls: r.calls, triangles: r.triangles, geometries: m.geometries,
    textures: m.textures, fps: Math.round(fps * 10) / 10, tiles: loaded, tilesTotal: config.tiles.length,
    labels: labelsShown, distance: Math.round(camera.position.distanceTo(controls.target)), decoder: decoder(),
    pixelRatio: renderer.getPixelRatio(), viewport: [innerWidth, innerHeight],
    terrain: terrainState, relief: Math.round(uRelief.value * 100) / 100, terrainChunks: chunkMeshes.length,
    terrainFar: chunkMeshes.filter(m => m.userData.lod).length,
  };
}
if (new URLSearchParams(location.search).has('debug')) {
  const el = document.getElementById('debug');
  el.hidden = false;
  el.querySelector('[data-view="home"]').onclick = () => goHome();
  el.querySelector('[data-view="overview"]').onclick = () => viewAt(20000);
  setInterval(() => { el.querySelector('pre').textContent = JSON.stringify(stats(), null, 1).slice(2, -2); }, 500);
}

let frame = 0, deferredRequested = false;
renderer.setAnimationLoop(now => {
  frame++;
  const dt = lastFrameAt ? (now - lastFrameAt) / 1000 : 0;
  if (lastFrameAt) { frameMs.push(now - lastFrameAt); if (frameMs.length > 60) frameMs.shift(); }
  lastFrameAt = now;
  stepFlight(now);
  stepNorth(now);
  stepRelief(now);
  uniforms.uNow.value = now / 1000;
  uniforms.uMask.value = maskTarget;
  stepUnknown(dt);
  controls.update();
  stepNeedle();
  const dist = camera.position.distanceTo(controls.target);
  followGround(dist, dt);
  updateLods();
  uniforms.uFog.value.set(dist * 1.6, dist * 4);
  if (frame % 6 === 0) { updateLabels(dist); stepPick(); }
  highlight.step(now, THEME.ui['--accent'], meshes);
  if (playing) {
    const t = Math.min(1, playT0 + (now - playStart) / DURATION);
    uniforms.uYear.value = playYear(t);
    // A flight lasts about 0.8 s on screen whatever the film's pace: as many years as the film covers in that time.
    uniforms.uRise.value = Math.max(2, (playYear(Math.min(1, t + 800 / DURATION)) - playYear(t)));
    if (t >= 1) stopPlay();
    drawHist();
  }
  if (pointer && !dragging && frame % 3 === 0) {
    const gid = pick(pointer[0], pointer[1]);
    uniforms.uHover.value = gid;
    showCard(gid, pointer[0], pointer[1]);
  }
  renderer.render(scene, camera);
  if (!deferredRequested && meshes.length) {
    deferredRequested = true;
    const base = loadBase();
    base.catch(optional('The water (or the flat land)'));
    loadLabels().catch(optional('The street names'));
    loadTerrain(base).catch(e => {
      terrainState = 'failed';
      console.warn('The terrain did not load; the map stays flat.', e);
      showFlat().catch(optional('The land'));
      switcher.markRelief();   // the slider is disabled and its line says the heights did not load
    });
  }
});


// History scenes (web/scene-player.js): the Stories button and ?scene=<id>, both only with FEATURES.scenes. The year goes through the timeline's own
// setHandle, the from-handle first to rest so the to-handle can reach the scene's year.
const scenePlayer = mountScenePlayer({ THREE, scene, camera, controls, origin: config.origin, surfaceAt, calm,
  lang: () => LANG, setLang: FEATURES.lang ? setLang : null, stopFlight: () => { flight = null; },
  button: document.querySelector('.stories-open'), enabled: !!FEATURES.scenes,
  year: { save: () => [uniforms.uYearFrom.value, uniforms.uYear.value],
    set: y => { stopPlay(); setHandle('uYearFrom', FROM_REST); setHandle('uYear', y); },
    restore: ([from, to]) => { stopPlay(); uniforms.uYearFrom.value = from; uniforms.uYear.value = to; drawHist(); } } });

window.__dbg = { scenePlayer, renderer, stats, goHome, viewAt, pick, uniforms, camera, controls, setLayer, layers, pinCard, showCard, building, attrTally, setHideEst, setPhotoOnly, get photoGids() { return photoGids; }, meshes, labelGroup, get labels() { return labels; }, flyTo, faceNorth, startPlay, questClick, startQuest, get quests() { return quests; },
  surfaceAt, setRelief, chooseRelief, get relief() { return relief; }, terrain: () => ({ state: terrainState, source: TERRAIN?.source, relief: uRelief.value, cutK: uCutK.value, chunks: chunkMeshes.length }),
  get timelineLabels() { return placedLabels; }, get pinned() { return pinnedGid; }, districtOf,
  get forced() { return forcedGid; }, force, scene, highlight: () => highlight.state() };
