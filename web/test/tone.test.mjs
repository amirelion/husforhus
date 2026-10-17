import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { estimateTone, inkOn, rgba, hex, rgb, unknownFill, ESTIMATE_MIX } from '../tone.js';
import { THEMES } from '../themes.js';

test('hex and rgb round-trip', () => {
  assert.equal(hex(rgb('#3f8f6b')), '#3f8f6b');
});

test('estimateTone desaturates towards luminance, then darkens', () => {
  // #3f8f6b: luma 0.4839; channels move 40% towards it, then 25% towards black (every look's estimateTo).
  assert.deepEqual(ESTIMATE_MIX, [0.4, 0.25]);
  assert.equal(estimateTone('#3f8f6b'), '#416555');
  assert.equal(estimateTone('#808080'), '#606060'); // grey keeps its hue, only darkens
  assert.equal(estimateTone('#ffffff'), '#bfbfbf');
  assert.equal(estimateTone('#000000'), '#000000');
});

test('the vertex shader mixes with the same two numbers', () => {
  const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  assert.ok(app.includes(`mix(c, vec3(dot(c, vec3(0.2126, 0.7152, 0.0722))), ${ESTIMATE_MIX[0]});`), 'the luminance mix');
  assert.ok(app.includes(`mix(c, uEstimateTo, ${ESTIMATE_MIX[1]});`), 'the estimateTo mix');
});

test('inkOn and rgba', () => {
  assert.equal(inkOn('#e5b13a'), '#000000');
  assert.equal(inkOn('#3a4f9a'), '#ffffff');
  assert.equal(rgba('#b5c7c6', 0.85), 'rgba(181,199,198,0.85)');
});

test('estimateTone mixes towards black by default and towards a given colour otherwise', () => {
  assert.equal(estimateTone('#8c1c13'), estimateTone('#8c1c13', '#000000'));
  assert.equal(estimateTone('#8c1c13', '#ffffff'), '#8e5c58');
  assert.notEqual(estimateTone('#c28209', '#182233'), estimateTone('#c28209'));
});

// -45deg: the stripes rise from bottom left to top right, as the map's do from the home view.
test('unknownFill: a hatched look gets diagonal stripes of its hatch colour, the others a flat colour (D29)', () => {
  assert.equal(unknownFill({ unknown: '#c9c6c0', unknownHatch: '#aca8a1' }),
    'repeating-linear-gradient(-45deg, #aca8a1 0 1.5px, #c9c6c0 1.5px 5px)');
  assert.equal(unknownFill({ unknown: '#caced3' }), '#caced3');
});

// Plan 4a: the card's band takes the period colour, or the estimate tone for an estimated year; its text (the year, the
// period, the name) must read on it in every look: black or white, whichever contrasts more, and at least 4.5:1.
test('the card band text reads at WCAG AA on every period colour and estimate tone', () => {
  const lin = v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  const L = h => { const c = rgb(h).map(lin); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const contrast = (a, b) => { const [lo, hi] = [L(a), L(b)].sort((x, y) => x - y); return (hi + 0.05) / (lo + 0.05); };
  for (const [name, th] of Object.entries(THEMES)) {
    for (const c of [...th.periods, ...th.periods.map(p => estimateTone(p, th.estimateTo)), th.unknown]) {
      const ink = inkOn(c), other = ink === '#000000' ? '#ffffff' : '#000000';
      assert.ok(contrast(ink, c) >= contrast(other, c), `${name} ${c}: the better of black and white`);
      assert.ok(contrast(ink, c) >= 4.5, `${name} ${c}: ${contrast(ink, c).toFixed(2)}:1`);
    }
  }
  assert.equal(inkOn('#3f8f6b'), '#000000');       // Classic's Funkis: white read at 3.92:1
});
