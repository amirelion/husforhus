// The shader and box lines that put the map on its terrain, pinned by their source in the style of
// pick.test.mjs: a headless browser cannot judge a wall's foot or a name's height, and a box that ignores the lift only
// shows at some screen edges. e2e/terrain.spec.mjs checks the picture end to end.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
// Lines of source, matched in order with any whitespace or // comments between them.
const lines = (...ls) => new RegExp(ls.map(l => l.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('(?:\\s|//[^\\n]*)*'));
const glsl = {};
for (const [, name, body] of src.matchAll(/const (\w+) = \/\* glsl \*\/`([\s\S]*?)`;/g)) glsl[name] = body;

test('buildings stand on their ground: the lift, skirts down the slope, a base-relative foot and hatch, lifted boxes', () => {
  // the lift comes last, after the unknown-year sinking, a layer's rise and the fly-in, so a building sinks into its own ground
  // and flies in with its skirt; the skirt only with the relief on; vRel keeps the fly-in's offset at the wall's foot
  assert.match(glsl.VERT, lines(
    'float lift = groundDm * uRelief;',
    'vRel = p.y * 0.1;',
    'if (position.y == 0.0 && uRelief > 0.0) {',
    'vec2 xz = (modelMatrix * vec4(position, 1.0)).xz;',
    'float skirt = min(hEff(xz) * 10.0 - lift, 0.0) - 20.0 - 5.0 * hRange(xz);',
    'p.y += skirt;',
    'vRel += skirt * 0.1;',
    '}',
    'p.y += lift;',
    'vec4 w = modelMatrix * vec4(p, 1.0);',
  ));
  const writes = [...glsl.VERT.matchAll(/(?<![\w.])p(?:\.[xyz]+)?\s*[-+*\/]?=(?!=)[^;]*;/g)].map(m => m[0]);
  assert.deepEqual(writes.slice(-2), ['p.y += skirt;', 'p.y += lift;']);
  assert.ok(writes.filter(w => w.startsWith('p.y *=')).length >= 2, 'the unknown-year sinking and the layers scale p.y before the lift');
  assert.match(src, /float foot = mix\(0\.82, 1\.0, clamp\(vRel \/ 12\.0, 0\.0, 1\.0\)\);/);
  assert.match(src, /float s = mix\(dot\(vWorld\.xz, along\) \+ vRel, vWorld\.x - vWorld\.z, roof\)/);
  // the box itself: web/bounds.js, checked against the lifted fixture tile in bounds.test.mjs
  assert.match(src, /liftBounds\(g, m, config\.terrain\);/);
  assert.doesNotMatch(src, /computeBoundingBox\(\);\s*g\.boundingBox/);
});

test('the lookup texture holds ATTR_FLOATS per building, and the shader reads the ground from its third texel', () => {
  assert.match(src, /import \{[^}]*\bATTR_FLOATS\b[^}]*\} from '\.\/tile\.js';/);
  assert.match(glsl.VERT, lines('ivec2 tc = ivec2(${ATTR_FLOATS / 4} * (i % ${ATTR_W}), i / ${ATTR_W});'));
  assert.match(glsl.VERT, lines('float groundDm = texelFetch(uAttr, tc + ivec2(2, 0), 0).x;'));
  assert.match(src, lines('const data = new Float32Array(ATTR_W * ATTR_FLOATS * rows);'));
  assert.match(src, lines('const tex = new THREE.DataTexture(data, ATTR_W * ATTR_FLOATS / 4, rows, THREE.RGBAFormat, THREE.FloatType);'));
  assert.doesNotMatch(src, /ATTR_W \* \d/);   // no texel count written out
});

test('the shaders interpolate the terrain as web/terrain.js makeGround does: x along the columns, z down the rows', () => {
  assert.match(glsl.GRID_GLSL, lines('uniform vec2 uGridO, uGridN;', 'uniform float uCell;'));
  assert.match(glsl.TERRAIN_GLSL, lines(
    'float hNode(ivec2 i) {',
    'vec2 v = texelFetch(uTerrain, clamp(i, ivec2(0), ivec2(uGridN) - 1), 0).rg;',
    'return uRelief * v.r - uCutK * v.g;',
    '}',
    'float hEff(vec2 w) {',
    'vec2 g = (w - uGridO) / uCell, f = floor(g), t = g - f;',
    'ivec2 i = ivec2(f);',
    'return mix(mix(hNode(i), hNode(i + ivec2(1, 0)), t.x), mix(hNode(i + ivec2(0, 1)), hNode(i + ivec2(1, 1)), t.x), t.y);',
    '}',
  ));
  assert.match(glsl.TERRAIN_GLSL, lines(
    'float hRange(vec2 w) {',
    'ivec2 i = ivec2(floor((w - uGridO) / uCell));',
    'float a = hNode(i), b = hNode(i + ivec2(1, 0)), c = hNode(i + ivec2(0, 1)), d = hNode(i + ivec2(1, 1));',
    'return max(max(a, b), max(c, d)) - min(min(a, b), min(c, d));',
    '}',
  ));
});

test('every shader stage declares each uniform once: the grid\'s come from GRID_GLSL, included once per stage', () => {
  const expand = s => s.replace(/\$\{(\w+_GLSL)\}/g, (_, k) => expand(glsl[k]));
  const declared = s => [...s.matchAll(/\buniform\s+(?:(?:lowp|mediump|highp)\s+)?\w+\s+([^;]+);/g)]
    .flatMap(m => m[1].split(',').map(n => n.trim().replace(/\[.*$/, '')));
  for (const k of ['TERRAIN_GLSL', 'FADE_GLSL']) {
    assert.deepEqual(declared(glsl[k]).filter(n => ['uGridO', 'uGridN', 'uCell'].includes(n)), [], k);
  }
  for (const stage of ['VERT', 'FRAG', 'GROUND_VERT', 'WALL_VERT', 'WATER_VERT', 'TERRAIN_FRAG']) {
    assert.ok(glsl[stage], stage);
    const u = declared(expand(glsl[stage]));
    assert.deepEqual(u.filter((n, i) => u.indexOf(n) !== i), [], `${stage} declares a uniform twice`);
    if (/\$\{(TERRAIN|FADE)_GLSL\}/.test(glsl[stage])) assert.ok(u.includes('uGridO'), `${stage} needs GRID_GLSL`);
  }
  // the names: three.js's own vertex shader, with the grid and the terrain in front
  assert.match(src, /s\.vertexShader = GRID_GLSL \+ TERRAIN_GLSL \+ `/);
});

test('the ground takes its height from the texture; chunks and groups are boxed to the most relief offered', () => {
  assert.match(src, /w\.y = hEff\(w\.xz\);/);
  assert.match(src, /new THREE\.Vector3\(c\.cells\[0\] \* g\.cell \* 10, Math\.max\(0, c\.hMax\) \* RMAX \* 10 \+ 10, c\.cells\[1\] \* g\.cell \* 10\)/);
  assert.match(src, /new THREE\.Vector3\(x1, Math\.max\(0, grp\.hMax\) \* RMAX \+ 1, z1\)/);
  assert.match(src, /part\.setDrawRange\(grp\.start, grp\.count\);/);
  // low banks keep the ground's colour, quays over 3 m the look's stone
  assert.match(src, /smoothstep\(1\.0, 3\.0, vWallH\)/);
});

// The ground's light comes from themes.js SHADING, which web/test/themes.test.mjs checks the looks' colours with: the
// shader takes every constant from there (no number of its own), and so does the sun the buildings share.
test('the ground and the walls are shaded with themes.js SHADING, the constants the colour test uses', () => {
  assert.match(src, /import \{[^}]*\bSHADING\b[^}]*\} from '\.\/themes\.js';/);
  assert.match(glsl.TERRAIN_FRAG, lines(
    'vec3 shaded(vec3 c, vec3 n) { return c * clamp(1.0 + uShade * (dot(n, uSun) - uSun.y),',
    '1.0 - ${glf(SHADING.dark)} * uShade, 1.0 + ${glf(SHADING.light)} * uShade); }',
  ));
  assert.match(glsl.TERRAIN_FRAG, lines(
    'c = mix(shaded(uLand, n), c * (${glf(SHADING.wallMin)} + ${glf(SHADING.wallLit)} * max(dot(n, uSun), 0.0)),',
    'smoothstep(1.0, 3.0, vWallH));',
  ));
  assert.doesNotMatch(glsl.TERRAIN_FRAG, /\b0\.(6|3|66|34)\b/);
  assert.match(src, /uSun: \{ value: new THREE\.Vector3\(\.\.\.SHADING\.sun\)\.normalize\(\) \}/);
  // the buildings' walls take the same wallMin + wallLit as the quay walls
  assert.match(src, lines('float light = n.y > 0.9 ? 1.04 : ${glf(SHADING.wallMin)} + ${glf(SHADING.wallLit)} * sun;'));
  assert.doesNotMatch(src, /0\.66 \+ 0\.34 \* sun/);
  // and the looks' own values, with no fallback: every look has them (themes.test.mjs)
  assert.match(src, /uQuay: \{ value: col\(THEME\.quay\) \}/);
  assert.match(src, /uShade: \{ value: THEME\.reliefShade \}/);
  assert.doesNotMatch(src, /THEME\.quay \|\||THEME\.reliefShade \?\?/);
});

test('names lie on the ground, water names on their own water, nudged towards the camera by the ground\'s own error', () => {
  assert.match(src, /wpos\.y = uOnWater > 0\.5 \? uLevel \* uRelief \+ 0\.4 : hEff\(wpos\.xz\) \+ 0\.6;/);
  // a land name moves by the ground's own error; a water name, flat at its level, by half a metre
  assert.match(src, lines(
    'float bias = 0.5 + ${LOD_TOL.toFixed(1)} * uRelief + 2.0 * hTwist(wpos.xz);',
    'bias = uOnWater > 0.5 ? 0.5 : bias;',
    'mvPosition.xyz *= max(dEye - bias, 1.0) / dEye;',
  ));
  // a water name's level: the water's under it as the name is made, and again for every name once the terrain is in
  assert.match(src, lines(
    'l.mesh = new THREE.Mesh(labelPlane, labelMaterial(tex, l.L.water));',
    'l.mesh.material.userData.level.value = l.L.water ? waterAt(l.x, l.z) : 0;',
  ));
  assert.match(src, lines(
    'const waterPolys = parsePolygons(waterBuf);',
    'waterAt = (x, z) => levelAt(waterPolys, m.levels, x, z);',
    'for (const l of labels) if (l.mesh && l.L.water) l.mesh.material.userData.level.value = waterAt(l.x, l.z);',
  ));
  // culled where they are drawn: the mesh stands at the name's lifted height, and three.js's culling stays on
  assert.match(src, lines(
    'const labelY = l => (l.L.water ? l.mesh.material.userData.level.value * uRelief.value + 0.4 : surfaceAt(l.x, l.z) + 0.6);',
  ));
  assert.match(src, lines('l.mesh.position.set(l.x, labelY(l), l.z);'));
  assert.match(src, lines('if (show) { l.mesh.scale.set(w, h, 1); l.mesh.position.y = labelY(l); shown++; }'));
  assert.doesNotMatch(src, /frustumCulled = false/);
  // the search ring stands on the ground too
  assert.match(src, /ring\.position\.set\(cx, surfaceAt\(cx, cz\) \+ 2, cz\);/);
});

test('the camera rides the ground at any frame rate, at once with reduced motion; the floor re-aims what it lifts', () => {
  assert.match(src, lines(
    'const gap = surfaceAt(controls.target.x, controls.target.z) - controls.target.y;',
    'if (Math.abs(gap) > 1e-3) {',
    'const dy = gap * (calm.matches ? 1 : 1 - Math.exp(-dt / RIDE_S));',
    'controls.target.y += dy; camera.position.y += dy;',
  ));
  assert.match(src, lines('const dist = camera.position.distanceTo(controls.target);', 'followGround(dist, dt);'));
  assert.match(src, lines('if (camera.position.y < floor) { camera.position.y = floor; camera.lookAt(controls.target); }'));
  // the far plane follows the distance only once the terrain (and its fog) is in
  assert.match(src, lines("const far = terrainState === 'ready' ? Math.max(4000, dist * 4.5) : 60000;"));
});

test('?fade= and the terrain worker go through web/terrain.js\'s checked helpers; the flat land only when needed', () => {
  assert.match(src, /const FADE_M = fadeWidth\(PARAMS\.get\('fade'\), TERRAIN\?\.fadeM \?\? 400\);/);
  // a download that stalls (FETCH_TIMEOUT_MS without a chunk: fetchGz reports each one to withTimeout) or a worker
  // that hangs (WORKER_TIMEOUT_MS) times out, and the catch at startup then loads the flat land
  assert.match(src, lines(
    'const file = withTimeout((signal, alive) => fetchGz(`${DATA}${TERRAIN.file}`, 2, signal, alive), FETCH_TIMEOUT_MS,',
    'TERRAIN.file);',
    'const [buf, waterBuf] = await Promise.all([file, base]);',
  ));
  assert.match(src, /const m = await askWorker\(new Worker\('terrain-worker\.js', \{ type: 'module' \}\),/);
  // the flat land: fetched with the water only for a build without terrain, else only once the terrain has failed;
  // and the flat water is drawn only with it, so the land never shows the sky's colour while the terrain loads (the
  // final review's VIEWER-4): with the terrain in, its own water at the levels replaces it
  assert.match(src, lines('if (!TERRAIN) await showFlat();', 'return waterBuf;'));
  assert.match(src, lines('async function showFlat() {', 'await loadLand();', 'flat.add(water);', '}'));
  assert.equal([...src.matchAll(/flat\.add\(water\)/g)].length, 1);
  assert.match(src, lines(
    'loadTerrain(base).catch(e => {',
    "terrainState = 'failed';",
    "console.warn('The terrain did not load; the map stays flat.', e);",
    "showFlat().catch(optional('The land'));",
    'switcher.markRelief();',   // last: the slider is disabled and says so (e2e)
  ));
});
