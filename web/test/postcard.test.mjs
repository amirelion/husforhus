// web/postcard.js (spec 2026-10-20 §7): the postcard's file name, its filters' maths (the CSS filter functions'
// matrices, so the saved picture matches the preview), the tilt-shift masks and blur steps, and the stamp's layout.
// The page itself (the button, the bar, the download) is e2e/postcard.spec.mjs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { FILTERS, STEPS, TILT, VIGNETTE, SITE, MAX_SIDE, MAP_KEYS, fileName, validFilter, cssFilter, filterMatrix,
  applySteps, maskStops, maskCss, vignetteCss, outSize, blurSizes, blurFactor, wrapParts, stampFonts, stampLayout } from '../postcard.js';

const near = (a, b, eps = 1e-9, msg = '') => assert.ok(Math.abs(a - b) <= eps, `${msg} ${a} ≈ ${b}`);
const px = (r, g, b) => new Uint8ClampedArray([r, g, b, 255]);

test('the file is named after the site and the local date', () => {
  assert.equal(fileName(new Date(2026, 9, 20, 23, 59)), 'husforhus-2026-10-20.png');
  assert.equal(fileName(new Date(2027, 0, 5, 0, 1)), 'husforhus-2027-01-05.png');
  assert.match(fileName(), /^husforhus-\d{4}-\d{2}-\d{2}\.png$/);
});

test('three filters, each with its steps; an unknown one is None', () => {
  assert.deepEqual(FILTERS, ['none', 'tilt', 'sepia']);
  for (const f of FILTERS) assert.ok(Array.isArray(STEPS[f]), f);
  assert.equal(validFilter('sepia'), 'sepia');
  assert.equal(validFilter('vintage'), 'none');
  assert.equal(validFilter(undefined), 'none');
});

test('the preview filter is the steps as CSS filter functions, none for None', () => {
  assert.equal(cssFilter('none'), 'none');
  assert.equal(cssFilter('nope'), 'none');
  assert.equal(cssFilter('tilt'), STEPS.tilt.map(([f, a]) => `${f}(${a})`).join(' '));
  assert.match(cssFilter('sepia'), /^sepia\(1\) /);
  assert.match(cssFilter('tilt'), /saturate\(1\.\d+\)/);   // a toy's colours: more saturated than the map
});

test('the matrices are the Filter Effects spec\'s, so the saved picture matches the preview', () => {
  const apply = (m, [r, g, b]) => [0, 1, 2].map(i => m[i * 4] * r + m[i * 4 + 1] * g + m[i * 4 + 2] * b + m[i * 4 + 3]);
  const id = [10, 120, 230];
  // the neutral amounts leave a colour as it is
  for (const [f, a] of [['sepia', 0], ['saturate', 1], ['contrast', 1], ['brightness', 1]]) {
    apply(filterMatrix(f, a), id).forEach((v, i) => near(v, id[i], 1e-9, `${f}(${a})`));
  }
  // sepia(1): the spec's own numbers
  const s = filterMatrix('sepia', 1);
  assert.deepEqual(s.map(v => Math.round(v * 1000) / 1000), [0.393, 0.769, 0.189, 0, 0.349, 0.686, 0.168, 0, 0.272, 0.534, 0.131, 0]);
  near(filterMatrix('sepia', 2)[0], 0.393);                     // clamped to 1, as CSS does
  // saturate(0) is the luminance grey in every channel
  apply(filterMatrix('saturate', 0), id).forEach(v => near(v, 0.213 * 10 + 0.715 * 120 + 0.072 * 230, 1e-9));
  // contrast(0) is mid-grey, brightness(0.5) halves
  apply(filterMatrix('contrast', 0), id).forEach(v => near(v, 127.5));
  assert.deepEqual(apply(filterMatrix('brightness', 0.5), id), [5, 60, 115]);
  assert.throws(() => filterMatrix('blur', 2));
});

test('each step is clamped before the next, as a chain of CSS filter functions is', () => {
  // white under sepia(1) runs past 255 in red and green; clamped there, contrast(0.5) brings it to 191, where one
  // composed matrix would give 236
  const d = px(255, 255, 255);
  applySteps(d, [['sepia', 1], ['contrast', 0.5]]);
  assert.deepEqual([...d], [191, 191, 183, 255]);
  const none = px(12, 34, 56);
  applySteps(none, STEPS.none);
  assert.deepEqual([...none], [12, 34, 56, 255]);
  // alpha is never touched
  const a = new Uint8ClampedArray([200, 100, 50, 77]);
  applySteps(a, STEPS.sepia);
  assert.equal(a[3], 77);
});

test('sepia makes an old postcard: brown (red over green over blue), never pure black or white', () => {
  for (const c of [[15, 35, 51], [217, 223, 227], [236, 112, 52], [40, 160, 170], [0, 0, 0], [255, 255, 255]]) {
    const d = applySteps(px(...c), STEPS.sepia);
    assert.ok(d[0] >= d[1] && d[1] >= d[2], `${c} -> ${[...d]}`);
    assert.ok(d[2] > 8 && d[0] < 250, `${c} -> ${[...d]}: faded, as old paper is`);
  }
});

test('tilt-shift keeps grey grey and pushes a colour further from it', () => {
  const grey = applySteps(px(128, 128, 128), STEPS.tilt);
  assert.ok(Math.abs(grey[0] - grey[1]) <= 1 && Math.abs(grey[1] - grey[2]) <= 1, [...grey]);
  const teal = applySteps(px(40, 160, 170), STEPS.tilt);
  assert.ok(teal[1] - teal[0] > 120 - 1, [...teal]);
});

test('each tilt-shift mask is blurred at both ends and clear around the centre, offsets in order', () => {
  assert.ok(TILT.centre > 0.3 && TILT.centre < 0.7);
  TILT.layers.forEach((L, i) => {
    assert.ok(L.clear < L.full && L.blur > 0, `layer ${i}`);
    const s = maskStops(L);
    assert.equal(s[0][1], 1); assert.equal(s.at(-1)[1], 1);
    for (let k = 1; k < s.length; k++) assert.ok(s[k][0] >= s[k - 1][0], `layer ${i}: ${JSON.stringify(s)}`);
    assert.ok(s.every(([o, a]) => o >= 0 && o <= 1 && (a === 0 || a === 1)));
    assert.deepEqual(s.filter(([o]) => Math.abs(o - TILT.centre) < L.clear + 1e-9).map(([, a]) => a), [0, 0]);
  });
  // the second layer starts further out and blurs more: the blur grows towards the edges
  const [a, b] = TILT.layers;
  assert.ok(b.clear > a.clear && b.full > a.full && b.blur > a.blur);
  // a centre near an edge clamps its stops into 0..1
  assert.ok(maskStops({ clear: 0.1, full: 0.3 }, 0.9).every(([o]) => o >= 0 && o <= 1));
  assert.equal(maskCss([[0, 1], [0.5, 0], [1, 1]]), 'linear-gradient(to bottom, rgb(0 0 0 / 1) 0%, rgb(0 0 0 / 0) 50%, rgb(0 0 0 / 1) 100%)');
});

test('the vignette is a warm brown ellipse to the corners', () => {
  assert.ok(VIGNETTE.from > 0 && VIGNETTE.from < 1 && VIGNETTE.alpha > 0 && VIGNETTE.alpha < 1);
  const [r, g, b] = VIGNETTE.colour;
  assert.ok(r > g && g > b);
  assert.equal(vignetteCss({ from: 0.5, alpha: 0.4, colour: [60, 40, 20] }),
    'radial-gradient(farthest-corner at 50% 50%, rgb(60 40 20 / 0) 50%, rgb(60 40 20 / 0.4) 100%)');
});

test('the picture keeps the canvas\'s size, its longest side at most MAX_SIDE', () => {
  assert.deepEqual(outSize(1400, 900), { w: 1400, h: 900 });
  assert.deepEqual(outSize(5120, 2880), { w: MAX_SIDE, h: 1440 });
  assert.deepEqual(outSize(780, 1688), { w: 780, h: 1688 });
  assert.deepEqual(outSize(1000, 4000, 2000), { w: 500, h: 2000 });
  assert.deepEqual(outSize(0, 0), { w: 1, h: 1 });
});

test('a blur halves the picture down to about 1/factor and doubles it back to the full size', () => {
  const s = blurSizes(1400, 900, 16);
  assert.deepEqual(s.at(-1), [1400, 900]);
  const smallest = s.reduce((m, x) => (x[0] < m[0] ? x : m));
  assert.ok(smallest[0] >= 1400 / 16 - 1 && smallest[0] <= 1400 / 16 * 2, JSON.stringify(smallest));
  const i = s.indexOf(smallest);
  for (let k = 1; k <= i; k++) assert.ok(s[k][0] < s[k - 1][0], 'down');
  for (let k = i + 1; k < s.length; k++) assert.ok(s[k][0] > s[k - 1][0] && s[k][0] <= s[k - 1][0] * 2 + 1, 'up, at most doubling');
  // no step repeats the one before it, and no factor gives an empty canvas
  for (const f of [1, 1.5, 3, 40, 5000]) {
    const t = blurSizes(780, 1688, f);
    assert.deepEqual(t.at(-1), [780, 1688]);
    assert.ok(t.every(([w, h]) => w >= 1 && h >= 1));
    for (let k = 1; k < t.length; k++) assert.notDeepEqual(t[k], t[k - 1]);
  }
  assert.deepEqual(blurSizes(800, 600, 1), [[800, 600]]);
  assert.ok(blurFactor(10) > 10 && blurFactor(0) === 1);
});

// A stand-in for measureText: every character half the font's size wide.
const sizeOf = font => Number(font.match(/(\d+)px/)[1]);
const measure = (t, font) => t.length * sizeOf(font) * 0.5;
const CREDIT = ['© Stockholms stad', 'RAÄ', '© OpenStreetMap contributors', '© Lantmäteriet'];
const inside = (b, w, h) => b.x >= 0 && b.y >= 0 && b.x + b.w <= w && b.y + b.h <= h;
const apart = (a, b) => a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y;

test('credit parts wrap into lines that fit, a part never split', () => {
  const m = t => t.length;
  assert.deepEqual(wrapParts(['ab', 'cd'], 100, m), ['ab · cd']);
  assert.deepEqual(wrapParts(['ab', 'cd', 'ef'], 8, m), ['ab · cd', 'ef']);
  assert.deepEqual(wrapParts(['a very long part', 'b'], 5, m), ['a very long part', 'b']);
  assert.deepEqual(wrapParts([], 5, m), []);
});

test('the stamp: the site bottom right, the credit bottom left, apart and inside the picture', () => {
  const L = stampLayout({ w: 1400, h: 900, scale: 1, credit: CREDIT, measure });
  assert.equal(L.site.text, SITE);
  assert.equal(L.base, 15);                                       // the page's own text size, at most 15 px
  assert.ok(inside(L.site, 1400, 900) && inside(L.credit, 1400, 900));
  assert.ok(apart(L.site, L.credit));
  assert.equal(L.site.x + L.site.w, 1400 - L.pad);                 // right edge, a margin in
  assert.equal(L.site.y + L.site.h, 900 - L.pad);
  assert.equal(L.credit.x, L.pad);
  assert.equal(L.credit.y + L.credit.h, 900 - L.pad);               // the two sit on one line
  assert.deepEqual(L.credit.lines.map(l => l.text), [CREDIT.join(' · ')]);
  assert.match(L.site.font, /^700 \d+px /);
  for (const l of L.credit.lines) assert.ok(l.ty > L.credit.y && l.ty < L.credit.y + L.credit.h);
});

test('on a phone the stamp scales with the pixel ratio and the credit wraps', () => {
  const L = stampLayout({ w: 780, h: 1688, scale: 2, credit: CREDIT, measure });
  assert.equal(L.base, 22);                                       // 11 CSS px, the smallest, times 2
  assert.ok(L.credit.lines.length >= 2, JSON.stringify(L.credit.lines));
  assert.ok(inside(L.site, 780, 1688) && inside(L.credit, 780, 1688) && apart(L.site, L.credit));
  for (const l of L.credit.lines) assert.ok(l.tx + measure(l.text, L.credit.font) <= L.site.x, l.text);
});

test('on a very narrow picture the credit goes above the site, the full width', () => {
  const L = stampLayout({ w: 180, h: 400, scale: 1, credit: CREDIT, measure });
  assert.ok(L.credit.y + L.credit.h <= L.site.y, 'above');
  assert.ok(inside(L.site, 180, 400) && inside(L.credit, 180, 400));
  // a little wider, the credit has its third of the width beside the site, on more lines
  const M = stampLayout({ w: 300, h: 600, scale: 1, credit: CREDIT, measure });
  assert.equal(M.credit.y + M.credit.h, M.site.y + M.site.h);
  assert.ok(M.credit.lines.length >= 3 && apart(M.site, M.credit));
  assert.ok(L.credit.lines.length >= 2);
});

test('the stamp\'s fonts come before its layout, which measures in exactly those', () => {
  // The page loads them first (a pill measured in the fallback would not fit the text drawn in the look's face).
  for (const [w, h, scale] of [[1400, 900, 1], [780, 1688, 2], [180, 400, 1], [5120, 2880, 2]]) {
    const F = stampFonts({ w, h, scale, family: '"Inter", sans-serif' });
    const seen = new Set();
    const L = stampLayout({ w, h, scale, credit: CREDIT, family: '"Inter", sans-serif', measure: (t, f) => { seen.add(f); return measure(t, f); } });
    assert.equal(F.base, L.base);
    assert.equal(F.site, L.site.font);
    assert.equal(F.credit, L.credit.font);
    assert.deepEqual([...seen].sort(), [F.credit, F.site].sort());
  }
  assert.equal(stampFonts({ w: 1400, h: 900 }).site, '700 17px sans-serif');      // 15 px, the largest, times 1.15
  assert.equal(stampFonts({ w: 1400, h: 900 }).credit, '500 13px sans-serif');
});

test('the keys that move the map make a waiting picture out of date; the bar\'s own keys do not', () => {
  for (const k of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '-', '=', '_', 'n', 'N']) assert.ok(MAP_KEYS.has(k), k);
  for (const k of ['Tab', 'Enter', ' ', 'Escape', 'p', 'Shift']) assert.ok(!MAP_KEYS.has(k), k);
});

test('without credit parts there is only the site', () => {
  const L = stampLayout({ w: 1000, h: 700, credit: [], measure });
  assert.equal(L.credit, null);
  assert.ok(inside(L.site, 1000, 700));
});

test('the page has the button, the bar with every filter, and hides what a history scene hides, and more', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /<button class="postcard-open"[^>]*aria-keyshortcuts="P"[^>]*data-i18n-aria="postcard\.open"/);
  for (const f of FILTERS) assert.match(html, new RegExp(`data-filter="${f}"[^>]*data-i18n="postcard\\.${f}"`), f);
  for (const c of ['pc-save', 'pc-share', 'pc-close', 'pc-status']) assert.match(html, new RegExp(`class="${c}[ "]`), c);
  const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8');
  const player = readFileSync(new URL('../scene-player.css', import.meta.url), 'utf8');
  const sceneOn = [...player.matchAll(/body\.scene-on (\S+?)[,\s{]/g)].map(m => m[1]);
  const postcard = new Set([...css.matchAll(/body\.postcard (\S+?)[,\s{]/g)].map(m => m[1]));
  assert.ok(sceneOn.length >= 8);
  for (const s of [...sceneOn, '.search', '.credits', '.veil', '.sp', '#debug', '.crosshair']) assert.ok(postcard.has(s), s);
  assert.match(css, /body\.postcard \.crosshair \{ visibility: hidden; \}/);
  // the loading line too, but not a failure's message (role="alert"), which says why the map is blank
  assert.match(css, /body\.postcard \.loading:not\(\[role="alert"\]\) \{ visibility: hidden; \}/);
});
