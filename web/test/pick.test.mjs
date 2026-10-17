import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// The pick pass writes vGid + 1 as RGB and app.js decodes it back to a gid. An interpolated varying can land one
// ULP under the integer even when the three vertices agree, and floor(id / 256) then returns the previous
// building's gid (a neighbour's card). A flat varying is never interpolated. The shader is GLSL inside app.js,
// which node cannot run, so this pins the qualifier in both stages; the e2e card click exercises the pick itself.
test('the pick id travels as a flat varying', () => {
  const src = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  assert.match(src, /^\s*flat out float vGid;/m);
  assert.match(src, /^\s*flat in float vGid;/m);
  assert.doesNotMatch(src, /^\s*(out|in) float vGid;/m);
});

// Plan 3: the ground is drawn in the pick pass as nothing (id 0, which decodes to -1) but with depth, so a hill hides
// what stands behind it; e2e/terrain.spec.mjs finds such a building and picks it.
test('the ground draws as id 0 in the pick pass', () => {
  const src = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  assert.match(src, /#ifdef PICK\s+outColor = vec4\(0\.0\);/);
  assert.match(src, /for \(const m of terrainMeshes\) m\.material = m\.userData\.pick;/);
  assert.match(src, /for \(const m of terrainMeshes\) m\.material = m\.userData\.draw;/);
});
