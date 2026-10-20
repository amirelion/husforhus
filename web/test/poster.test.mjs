// web/poster.js: the Poster filter's inks (which colours, boosted how, and the nearest-ink rule the shader follows;
// a building's lit and shaded faces in its own colour's inks), the poster's own colours in every look and weather, the
// band's year and words, the place lookup, the layout of the head, the band, the paper and its imprint on a desktop
// and a phone, the drawing order, the shader's numbers and the pass (with three.js itself and a stand-in renderer; its
// copy let go), and the lines in app.js that run it. e2e/postcard.spec.mjs checks the page and the saved picture.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as THREE from '../vendor/three.module.js';
import { THEMES } from '../themes.js';
import { rgb, hex, lin, oklabLin, oklab } from '../tone.js';
import { WEATHER, KINDS, weatherSky, snowInk } from '../weather.js';
import { stampFonts } from '../postcard.js';
import { TITLE, BOOST, MAX_INKS, RUNGS, SHADED, boostInk, shadeOf, posterInks, nearestInk, matchLabs, contrast,
  posterColours, posterYear, placeLine, nearestIndex, spaced, posterLayout, drawPoster, POSTER_FRAG, makePosterPass,
  TITLE_SPACING, PLACE_SPACING } from '../poster.js';

const HEX = /^#[0-9a-f]{6}$/;
const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
// The Layers mode's group colours, as app.js has them.
const GROUPS = app.match(/const GROUP_COLORS = \[([^\]]*)\]/)[1].match(/#[0-9a-f]{6}/g);
// The colours a building can have in a mode: every period, the Floors ramp, or the Layers mode's maquette and groups.
const rampOf = (th, mode) => (mode === 'floors' ? th.floors : mode === 'layers' ? [th.maquette, ...GROUPS] : th.periods);
// Which colour each match colour stands for, in posterInks' order: the sky, land, water, "Year unknown" (its rungs and
// its hatch's too), then each of rampOf's colours by its index, once per rung (the maquette at the grey rungs).
const owners = (th, mode = 'period') => {
  const unknown = mode === 'period' ? RUNGS.grey.length - 1 + (th.unknownHatch ? RUNGS.hatch.length : 0) : 0;
  return ['sky', 'land', 'water', 'unknown', ...Array(unknown).fill('unknown'),
    ...rampOf(th, mode).flatMap((_, i) => (mode === 'layers' && i === 0 ? RUNGS.grey : RUNGS.colour).map(() => i))];
};
const dE = (a, b) => 100 * Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const near = (a, b, eps = 1e-9, msg = '') => assert.ok(Math.abs(a - b) <= eps, `${msg} ${a} ≈ ${b}`);
const chroma = c => { const [, a, b] = oklabLin(c.map(lin)); return Math.hypot(a, b); };

test('an ink is its colour a little more saturated and contrasted, as CSS saturate() then contrast() would make it', () => {
  assert.deepEqual(BOOST, { saturate: 1.15, contrast: 1.08 });
  // grey stays grey, mid-grey stays put, light greys get lighter and dark ones darker
  boostInk([0.5, 0.5, 0.5]).forEach(v => near(v, 0.5, 1e-12));
  const light = boostInk([0.8, 0.8, 0.8]), dark = boostInk([0.2, 0.2, 0.2]);
  assert.ok(light[0] > 0.8 && dark[0] < 0.2);
  assert.ok(Math.abs(light[0] - light[1]) < 1e-12 && Math.abs(light[1] - light[2]) < 1e-12);
  // a colour moves away from grey, white and black stay in range
  for (const h of ['#aa6446', '#3c8e97', '#ffc861', '#669f72']) assert.ok(chroma(boostInk(rgb(h))) > chroma(rgb(h)), h);
  for (const c of [[1, 1, 1], [0, 0, 0], [1, 0, 0]]) assert.ok(boostInk(c).every(v => v >= 0 && v <= 1));
  // the neutral amounts change nothing
  assert.deepEqual(boostInk([0.1, 0.4, 0.9], { saturate: 1, contrast: 1 }).map(v => +v.toFixed(12)), [0.1, 0.4, 0.9]);
});

test('the inks: the sky as it is now, land, water, "Year unknown", the snow while it snows, then each building colour at its rungs', () => {
  const th = THEMES.arg;
  const P = posterInks({ theme: th });
  // [match, printed before the boost]: a rung under SHADED.below prints the colour's darker ink
  const at = (h, ks) => ks.map(k => [shadeOf(h, k), k < SHADED.below ? shadeOf(h, SHADED.ink) : h]);
  const want = [[th.sky, th.sky], [th.land, th.land], [th.water, th.water], [th.unknown, th.unknown],
    ...at(th.unknown, RUNGS.grey.slice(1)), ...at(th.unknownHatch, RUNGS.hatch), ...th.periods.flatMap(h => at(h, RUNGS.colour))];
  assert.deepEqual(P.match, want.map(p => p[0]));
  assert.deepEqual(P.inks, want.map(p => hex(boostInk(rgb(p[1])))));
  // every period has its inks now (not every other one), each with a lit rung of its own colour and one shaded
  for (const h of th.periods) assert.ok(P.match.includes(h) && P.match.includes(shadeOf(h, RUNGS.colour.at(-1))), h);
  assert.deepEqual(RUNGS.colour.map(k => k < SHADED.below), [false, false, true]);
  assert.equal(RUNGS.grey[0], 1);
  assert.equal(shadeOf('#8ed3d0', 1), '#8ed3d0');
  // the weather's sky comes first, the snow's colour after the ground's four
  const snowSky = weatherSky(th.sky, 'snow');
  const S = posterInks({ theme: th, sky: snowSky, snow: snowInk(th) });
  assert.equal(S.match[0], snowSky);
  assert.equal(S.match[4], snowInk(th));
  assert.equal(S.match.length, P.match.length + 1);
  // Floors: its ramp's rungs; Layers: the maquette's (a pale grey, at the grey rungs) and the groups'; neither has
  // "Year unknown"'s rungs
  assert.deepEqual(posterInks({ theme: th, mode: 'floors' }).match.slice(4), th.floors.flatMap(h => RUNGS.colour.map(k => shadeOf(h, k))));
  const L = posterInks({ theme: th, mode: 'layers', groups: GROUPS, snow: '#ffffff' });
  assert.deepEqual(L.match.slice(5), [...RUNGS.grey.map(k => shadeOf(th.maquette, k)), ...GROUPS.flatMap(h => RUNGS.colour.map(k => shadeOf(h, k)))]);
  // every look, weather and mode fits the shader's array whole (posterInks would cut the last colours off)
  for (const t of Object.values(THEMES)) for (const kind of KINDS) for (const mode of ['period', 'floors', 'layers']) {
    const snow = kind === 'snow' ? snowInk(t) : null;
    const Q = posterInks({ theme: t, sky: weatherSky(t.sky, kind), mode, groups: GROUPS, snow });
    assert.equal(Q.match.length, owners(t, mode).length + (snow ? 1 : 0), `${t.name} ${kind} ${mode}`);
    assert.ok(Q.match.length <= MAX_INKS);
    for (const h of Q.inks) assert.match(h, HEX);
  }
});

test('every pixel takes the nearest ink in OKLab: each match colour itself, a colour between two the nearer', () => {
  for (const th of Object.values(THEMES)) {
    const P = posterInks({ theme: th }), labs = matchLabs(P.match);
    // every match colour prints as itself, every period among them
    P.match.forEach((h, i) => {
      const k = nearestInk(rgb(h), labs);
      assert.equal(P.match[k], P.match[i], `${th.name}: ${h}`);
    });
    th.periods.forEach(h => assert.equal(P.inks[nearestInk(rgb(h), labs)], hex(boostInk(rgb(h))), `${th.name}: ${h}`));
  }
  const labs = matchLabs(['#000000', '#ffffff']);
  assert.equal(nearestInk([0.3, 0.3, 0.3], labs), 0);
  assert.equal(nearestInk([0.7, 0.7, 0.7], labs), 1);
});

test('the fog bands into a few flat steps: the ground, the water and "Year unknown" fade into the sky ink by ink', () => {
  // The printed inks along a fade from a to b, as bands [ink, first t, last t].
  const bands = (P, labs, a, b) => {
    const run = [];
    for (let i = 0; i <= 100; i++) {
      const t = i / 100, ink = P.inks[nearestInk(rgb(a).map((v, j) => v + (rgb(b)[j] - v) * t), labs)];
      if (run.at(-1)?.[0] === ink) run.at(-1)[2] = t; else run.push([ink, t, t]);
    }
    return run;
  };
  for (const [name, th] of Object.entries(THEMES)) {
    const P = posterInks({ theme: th }), labs = matchLabs(P.match), sky = hex(boostInk(rgb(th.sky)));
    for (const a of [th.land, th.water, th.unknown]) {
      const run = bands(P, labs, a, th.sky), msg = `${name} ${a}: ${run.map(b => b[0])}`;
      // flat bands, a few of them, ending in the sky's ink. Ärg's ink-dark water into its pale sky is the longest fade
      // of any look: it crosses the dark periods' inks and "Year unknown"'s greys, so it takes more.
      assert.ok(run.length >= 2 && run.length <= (name === 'arg' && a === th.water ? 12 : 6), msg);
      assert.equal(run.at(-1)[0], sky, msg);
      // an ink that comes back does so across less than a twentieth of the fade: a hairline, never a flicker
      run.forEach(([ink], j) => {
        const i = run.findIndex(b => b[0] === ink);
        if (i < j) assert.ok(run[j][1] - run[i][2] < 0.05, msg);
      });
    }
    // a building fogs from its own colour into the sky's ink
    for (const i of [0, 4, 8]) {
      const run = bands(P, labs, th.periods[i], th.sky);
      assert.equal(run[0][0], hex(boostInk(rgb(th.periods[i]))), `${name} period ${i}`);
      assert.equal(run.at(-1)[0], sky);
    }
  }
});

test('a building\'s faces print in its own colour, lit and shaded: "Year unknown" in its greys, each period in its own', () => {
  // The faces as app.js lights them (FRAG): from the foot of a wall in the shade (0.66 x 0.82 of its colour) to a roof
  // (1.04). Before the rungs, a shaded wall printed in whichever colour lay nearest: in Kalkfärg "Year unknown"'s grey
  // walls in the 1920s green or the water's ink, the ochre's in green, the newest purple in steel blue; in Ärg the
  // grey walls and their hatch in teal, so Gamla stan printed as a district of dated buildings.
  const faces = Array.from({ length: 51 }, (_, i) => 0.54 + i / 100);
  const face = (h, f) => rgb(h).map(v => Math.min(1, v * f));
  for (const [name, th] of Object.entries(THEMES)) {
    for (const mode of ['period', 'floors', 'layers']) {
      const P = posterInks({ theme: th, mode, groups: GROUPS }), labs = matchLabs(P.match), own = owners(th, mode);
      assert.equal(own.length, P.match.length);
      if (mode === 'period') {
        // "Year unknown", its hatch and the hatch's mean tone far off: always in "Year unknown"'s inks
        const greys = th.unknownHatch ? [th.unknown, th.unknownHatch, hex(rgb(th.unknown).map((v, i) => 0.75 * v + 0.25 * rgb(th.unknownHatch)[i]))] : [th.unknown];
        for (const g of greys) for (const f of faces) {
          const k = nearestInk(face(g, f), labs);
          assert.equal(own[k], 'unknown', `${name}: ${g} at ${f.toFixed(2)} prints as ${P.match[k]}`);
        }
      }
      // each of the mode's colours: its own inks or a neighbour's in the ramp, or one the screen shows within 4.5 ΔE
      // of the face (the ramps' neighbours look alike: Ärg's teals, Kalkfärg's ochres); in the period mode never the
      // ground's or "Year unknown"'s, which would say no year
      rampOf(th, mode).forEach((h, i) => {
        for (const f of faces) {
          const c = face(h, f), k = nearestInk(c, labs), msg = `${name} ${mode} ${h} at ${f.toFixed(2)} prints as ${P.match[k]}`;
          if (mode === 'period') assert.equal(typeof own[k], 'number', msg);
          if (own[k] !== i && !(Math.abs(own[k] - i) === 1)) assert.ok(dE(oklabLin(c.map(lin)), labs[k]) < 4.5, msg);
        }
        // its lit faces in its own ink, the faces in the shade in its darker one
        assert.equal(P.inks[nearestInk(face(h, 1), labs)], hex(boostInk(rgb(h))), `${name} ${mode} ${h} lit`);
        if (mode === 'period') assert.equal(P.inks[nearestInk(face(h, 0.62), labs)], hex(boostInk(rgb(shadeOf(h, SHADED.ink)))), `${name} ${h} shaded`);
      });
    }
  }
  // the cases that were wrong, by name
  const k = (th, h, f) => { const P = posterInks({ theme: th }); return P.match[nearestInk(face(h, f), matchLabs(P.match))]; };
  assert.equal(k(THEMES.kalk, THEMES.kalk.unknown, 0.66), shadeOf(THEMES.kalk.unknown, 0.62));
  assert.notEqual(k(THEMES.kalk, THEMES.kalk.periods[4], 0.8), THEMES.kalk.periods[6]);
  assert.equal(k(THEMES.kalk, THEMES.kalk.periods[11], 0.9), shadeOf(THEMES.kalk.periods[11], 0.84));
});

test('the poster\'s colours read in every look and every weather: the title on the head, the band\'s line, the imprint', () => {
  for (const [name, th] of Object.entries(THEMES)) {
    assert.ok(th.poster, name);
    for (const k of ['title', 'band', 'bandInk', 'paper', 'imprint']) assert.match(th.poster[k], HEX, `${name} ${k}`);
    for (const kind of KINDS) {
      const sky = weatherSky(th.sky, kind), C = posterColours(th, sky);
      // the head is the sky's ink, so it meets the printed sky without a seam
      assert.equal(C.head, posterInks({ theme: th, sky }).inks[0], `${name} ${kind}`);
      assert.ok(contrast(C.title, C.head) >= 3, `${name} ${kind}: title ${C.title} on ${C.head}`);
    }
    const C = posterColours(th);
    assert.equal(C.title, th.poster.title, `${name}: the look's own title colour in clear weather`);
    assert.ok(contrast(C.bandInk, C.band) >= 4.5, `${name}: band`);
    assert.ok(contrast(C.imprint, C.paper) >= 4.5, `${name}: imprint`);
    // the paper is not the land's ink: white land at the picture's edge would melt into it (the keyline helps too)
    const land = oklab(posterInks({ theme: th }).inks[1]), paper = oklab(C.paper);
    assert.ok(100 * Math.hypot(land[0] - paper[0], land[1] - paper[1], land[2] - paper[2]) > 2, `${name}: paper vs land`);
  }
  // dark ink on the pale skies, light on Blå timmen's
  assert.ok(oklab(THEMES.arg.poster.title)[0] < 0.4 && oklab(THEMES.kalk.poster.title)[0] < 0.4);
  assert.ok(oklab(THEMES.blatimme.poster.title)[0] > 0.7);
  // a title that would not stand out takes the look's ink or panel, whichever does
  const odd = { ...THEMES.arg, poster: { ...THEMES.arg.poster, title: '#d0d6da' } };
  const C = posterColours(odd);
  assert.ok(contrast(C.title, C.head) >= 3 && [odd.ui['--ink'], odd.ui['--panel']].includes(C.title));
  // a look without poster colours borrows its interface's
  const plain = { ...THEMES.kalk };
  delete plain.poster;
  assert.equal(posterColours(plain).band, plain.ui['--accent']);
  assert.ok(Object.keys(WEATHER).length >= 4);
});

test('the band\'s year is the timeline\'s, this year at "Today"; its words the stadsdel and the year', () => {
  assert.equal(posterYear(2025, 2025, new Date(2026, 9, 20)), '2026');
  assert.equal(posterYear(2025, 2025, new Date(2031, 0, 1)), '2031');
  assert.equal(posterYear(1900, 2025), '1900');
  assert.equal(posterYear(1899.6, 2025), '1900');
  assert.equal(placeLine('Gamla stan', '2026'), 'Gamla stan · 2026');
  assert.equal(placeLine('', '1900'), '1900');
});

test('the place: the nearest point that has a stadsdel, within the reach; none beyond it', () => {
  const xz = new Float32Array([0, 0, 100, 0, 0, 50, 1000, 1000]);
  assert.equal(nearestIndex(xz, 90, 5), 1);
  assert.equal(nearestIndex(xz, 10, 40), 2);
  assert.equal(nearestIndex(xz, 10, 40, i => i !== 2), 0);       // the nearest without a stadsdel is passed over
  assert.equal(nearestIndex(xz, 600, 600, () => true, 600), 3);
  assert.equal(nearestIndex(xz, 5000, 5000, () => true, 1500), -1);
  assert.equal(nearestIndex(new Float32Array(0), 0, 0), -1);
});

// A stand-in for measureText: every character 0.6 of the font's size wide, "M" and "W" wider, "I" narrower.
const sizeOf = font => Number(font.match(/(\d+(?:\.\d+)?)px/)[1]);
const measure = (t, font) => [...t].reduce((s, ch) => s + sizeOf(font) * (/[MW]/.test(ch) ? 0.85 : /[Il.·]/.test(ch) ? 0.3 : 0.6), 0);
const CREDIT = ['© Stockholms stad', 'RAÄ', '© OpenStreetMap contributors', '© Lantmäteriet'];
const inside = (b, w, h) => b.x >= 0 && b.y >= 0 && b.x + b.w <= w + 1e-9 && b.y + b.h <= h + 1e-9;

test('spaced letters: each glyph\'s left end, the line centred on its middle, the spacing between them only', () => {
  const s = spaced('AB', '10px x', 10, 0.5, 100, measure);
  assert.equal(s.width, 6 + 6 + 5);
  assert.deepEqual(s.glyphs, [{ ch: 'A', x: 100 - 8.5 }, { ch: 'B', x: 100 - 8.5 + 11 }]);
  assert.equal(spaced('', '10px x', 10, 0.5, 0, measure).width, 0);
});

const layout = (w, h, scale, extra = {}) => {
  const family = '"Inter", sans-serif';
  return posterLayout({ w, h, scale, family, measure, credit: CREDIT, place: 'Gamla stan', year: '2026',
    fonts: stampFonts({ w, h, scale, family }), ...extra });
};

for (const [label, w, h, scale] of [['desktop', 1400, 900, 1], ['phone', 780, 1688, 2], ['5K screen', 2560, 1440, 2],
  ['phone held sideways', 1334, 750, 2]]) {
  test(`the poster on a ${label}: paper, head, picture, band and imprint stacked down the picture, nothing outside`, () => {
    const L = layout(w, h, scale);
    for (const b of [L.head, L.band, L.picture, L.keyline]) assert.ok(inside(b, w, h), JSON.stringify(b));
    // head at the top inside the paper, the picture under it, the band under that, the imprint in the paper below
    assert.equal(L.head.y, L.m);
    assert.equal(L.picture.y, L.head.y + L.head.h);
    assert.equal(L.band.y, L.picture.y + L.picture.h);
    assert.equal(L.band.y + L.band.h, h - L.bottom);
    assert.ok(L.picture.h > h * 0.45, 'most of the poster is the picture');
    assert.ok(L.bottom > L.m, 'the paper is deeper at the bottom');
    // the keyline runs round the print, in the paper
    assert.ok(L.keyline.x < L.m && L.keyline.y < L.m && L.keyline.x + L.keyline.w > w - L.m);
    assert.ok(L.keyline.y + L.keyline.h > L.band.y + L.band.h && L.keyline.y + L.keyline.h < h - L.bottom + L.bottom / 2);
    // the title: STOCKHOLM, centred, at most 86% of the head's width and 15% of the picture's height, inside the head
    assert.equal(L.title.text, TITLE);
    near(L.title.glyphs[0].x + L.title.width / 2, w / 2, 1e-6);
    assert.ok(L.title.width <= L.head.w * 0.86 + 1);
    assert.ok(L.title.size <= (h - 2 * L.m) * 0.15);
    assert.ok(L.title.baseline - L.title.size * 0.72 > L.head.y && L.title.baseline < L.head.y + L.head.h);
    assert.match(L.title.font, /^800 \d+px "Inter"/);
    assert.equal(L.title.glyphs.length, TITLE.length);
    // the band: the place line in capitals, centred, inside the band, at least the page's 16 px
    assert.equal(L.place.text, 'GAMLA STAN · 2026');
    assert.ok(L.place.size >= 16 * scale);
    assert.ok(L.place.width <= L.band.w * 0.9);
    assert.ok(L.place.baseline > L.band.y && L.place.baseline < L.band.y + L.band.h);
    near(L.place.glyphs[0].x + L.place.width / 2, w / 2, 1e-6);
    // the imprint: below the keyline, the credit at the left clear of the site at the right, inside the picture
    const site = L.imprint.site, sw = measure(site.text, site.font);
    assert.equal(site.text, 'husforhus.se');
    assert.ok(site.x + sw <= w - L.m + 1e-6);
    const lines = L.imprint.credit.lines;
    assert.deepEqual(lines.map(l => l.text).join(' · '), CREDIT.join(' · '));
    for (const l of lines) {
      assert.ok(l.x + measure(l.text, L.imprint.credit.font) < site.x, l.text);
      assert.ok(l.y > L.keyline.y + L.keyline.h && l.y < h, l.text);
    }
    assert.ok(site.y > L.keyline.y + L.keyline.h && site.y < h);
  });
}

test('the phone\'s credit wraps under its band; a desktop\'s fits on one line', () => {
  assert.equal(layout(1400, 900, 1).imprint.credit.lines.length, 1);
  assert.ok(layout(780, 1688, 2).imprint.credit.lines.length >= 2);
});

test('a long stadsdel still fits its band; over open water the band says the year alone', () => {
  for (const [w, h, scale] of [[780, 1688, 2], [1400, 900, 1], [640, 1136, 2]]) {
    const L = layout(w, h, scale, { place: 'Ulvsunda industriområde', year: '1958' });
    assert.equal(L.place.text, 'ULVSUNDA INDUSTRIOMRÅDE · 1958');
    assert.ok(L.place.width <= L.band.w * 0.9 + 1e-6, `${w}: ${L.place.width} of ${L.band.w}`);
  }
  assert.equal(layout(1400, 900, 1, { place: '' }).place.text, '2026');
  // capitals the Swedish way
  assert.equal(layout(1400, 900, 1, { place: 'Södermalm' }).place.text, 'SÖDERMALM · 2026');
  assert.ok(TITLE_SPACING > PLACE_SPACING && PLACE_SPACING > 0);
});

test('drawPoster: the head and its title, the band and its line, then the paper, its keyline and the imprint', () => {
  const L = layout(1400, 900, 1), C = posterColours(THEMES.blatimme);
  const calls = [];
  const ctx = new Proxy({}, {
    get: (o, k) => (k in o ? o[k] : ['save', 'restore', 'fillRect', 'fillText', 'strokeRect'].includes(k)
      ? (...a) => calls.push([k, o.fillStyle, o.strokeStyle, ...a]) : undefined),
    set: (o, k, v) => { o[k] = v; return true; },
  });
  drawPoster(ctx, L, C);
  const rects = calls.filter(c => c[0] === 'fillRect'), texts = calls.filter(c => c[0] === 'fillText');
  assert.deepEqual(rects[0].slice(1, 2).concat(rects[0].slice(3)), [C.head, L.head.x, L.head.y, L.head.w, L.head.h]);
  assert.deepEqual(rects[1].slice(1, 2).concat(rects[1].slice(3)), [C.band, L.band.x, L.band.y, L.band.w, L.band.h]);
  assert.equal(rects.slice(2).filter(r => r[1] === C.paper).length, 4);
  assert.equal(texts.filter(t => t[1] === C.title).map(t => t[3]).join(''), TITLE);
  assert.equal(texts.filter(t => t[1] === C.bandInk).map(t => t[3]).join(''), L.place.text.replace(/ /g, ' '));
  assert.deepEqual(texts.filter(t => t[1] === C.imprint).map(t => t[3]), ['husforhus.se', ...L.imprint.credit.lines.map(l => l.text)]);
  const key = calls.find(c => c[0] === 'strokeRect');
  assert.equal(key[2], C.imprint);
  // the paper and the keyline come after the head and the band, the imprint last
  const order = calls.map(c => c[0]);
  assert.ok(order.indexOf('strokeRect') > order.lastIndexOf('fillRect'));
  assert.equal(order[0], 'save');
  assert.equal(order.at(-1), 'restore');
});

test('the shader sums OKLab with tone.js\'s numbers, over at most MAX_INKS inks, from the copied frame\'s own pixel', () => {
  const nums = [...POSTER_FRAG.matchAll(/-?\d+\.\d{6,}/g)].map(m => +m[0]);
  const src = readFileSync(new URL('../tone.js', import.meta.url), 'utf8');
  const fn = src.slice(src.indexOf('export function oklabLin'), src.indexOf('export const oklab ='));
  const tone = [...fn.matchAll(/-?\d+\.\d{6,}/g)].map(m => +m[0]);
  assert.equal(tone.length, 18);
  // the same 18 numbers, in the same order, signs carried by the expression in each
  assert.deepEqual(nums.map(Math.abs), tone.map(Math.abs));
  assert.match(POSTER_FRAG, new RegExp(`uniform vec3 uMatch\\[${MAX_INKS}\\];`));
  assert.match(POSTER_FRAG, new RegExp(`uniform vec3 uInk\\[${MAX_INKS}\\];`));
  assert.match(POSTER_FRAG, /texelFetch\(uFrame, ivec2\(gl_FragCoord\.xy\), 0\)/);
  assert.match(POSTER_FRAG, /step\(0\.04045, c\)/);
  assert.match(POSTER_FRAG, /pow\(\(c \+ 0\.055\) \/ 1\.055, vec3\(2\.4\)\)/);
  assert.match(POSTER_FRAG, /if \(i >= uCount\) break;/);
});

test('the pass: draws the frame, copies it at the drawing buffer\'s size, prints it through the inks in one more draw', () => {
  const log = [];
  let size = [1400, 900];
  const renderer = {
    autoClear: true,
    getDrawingBufferSize: v => v.set(...size),
    copyFramebufferToTexture: t => log.push(['copy', t.image.width, t.image.height]),
    render: (scene, camera) => log.push(['render', scene.children.length, camera.isCamera, renderer.autoClear]),
  };
  const pass = makePosterPass(THREE, renderer);
  const P = posterInks({ theme: THEMES.kalk });
  pass.render(() => log.push(['draw']), P);
  assert.deepEqual(log, [['draw'], ['copy', 1400, 900], ['render', 1, true, false]]);
  assert.equal(renderer.autoClear, true);                         // put back
  const st = pass.state();
  assert.deepEqual(st, { frames: 1, count: P.match.length, size: [1400, 900] });
  // a resized window copies into a new texture of its size
  size = [780, 1688];
  pass.render(() => {}, P);
  assert.deepEqual(log.at(-2), ['copy', 780, 1688]);
  assert.equal(pass.state().frames, 2);
});

test('the pass\'s uniforms hold the match colours in OKLab and the inks as they are printed', () => {
  const renderer = { autoClear: true, getDrawingBufferSize: v => v.set(10, 10), copyFramebufferToTexture() {}, render() {} };
  let material;
  const Three = { ...THREE, Mesh: class extends THREE.Mesh { constructor(g, m) { super(g, m); material = m; } } };
  const pass = makePosterPass(Three, renderer);
  const P = posterInks({ theme: THEMES.blatimme, snow: snowInk(THEMES.blatimme) });
  pass.render(() => {}, P);
  const u = material.uniforms;
  assert.equal(u.uCount.value, P.match.length);
  assert.equal(u.uMatch.value.length, MAX_INKS);
  P.match.forEach((h, i) => {
    oklabLin(rgb(h).map(lin)).forEach((v, j) => near(u.uMatch.value[i].getComponent(j), v, 1e-12));
    rgb(P.inks[i]).forEach((v, j) => near(u.uInk.value[i].getComponent(j), v, 1e-12));
  });
  assert.equal(material.depthTest, false);
  assert.equal(material.depthWrite, false);
  assert.equal(material.fragmentShader, POSTER_FRAG);
});

test('the pass lets its copy of the frame go when the Poster stops, and makes it again with the next poster frame', () => {
  const renderer = { autoClear: true, getDrawingBufferSize: v => v.set(1400, 900), copyFramebufferToTexture() {}, render() {} };
  let material, made = 0, freed = 0;
  const Three = { ...THREE,
    Mesh: class extends THREE.Mesh { constructor(g, m) { super(g, m); material = m; } },
    FramebufferTexture: class extends THREE.FramebufferTexture {
      constructor(...a) { super(...a); made++; }
      dispose() { freed++; super.dispose(); }
    } };
  const pass = makePosterPass(Three, renderer), P = posterInks({ theme: THEMES.arg });
  pass.release();                                                  // nothing yet: nothing to let go
  assert.equal(freed, 0);
  pass.render(() => {}, P);
  assert.deepEqual([made, pass.state().size], [1, [1400, 900]]);
  pass.release();
  assert.deepEqual([freed, pass.state().size, material.uniforms.uFrame.value], [1, null, null]);
  pass.release();                                                  // a second time costs nothing
  assert.equal(freed, 1);
  pass.render(() => {}, P);
  assert.equal(made, 2);
  assert.equal(material.uniforms.uFrame.value.image.width, 1400);
});

// app.js: the lines that run the pass in the postcard's frame, and the even snow it is drawn with.
test('app.js prints the poster\'s frame through the pass, with the weather\'s sky and the snow laid evenly, then puts the snow back', () => {
  const shot = app.slice(app.indexOf('function drawShot('), app.indexOf('\n}\n', app.indexOf('function drawShot(')));
  const on = shot.indexOf('uniforms.uSnowEven.value = 1;'), pass = shot.indexOf('posterPass.render('),
    off = shot.indexOf('uniforms.uSnowEven.value = 0;');
  assert.ok(on > 0 && pass > on && off > pass, 'even snow only around the poster\'s draw');
  assert.match(shot, /posterInks\(\{ theme: THEME, sky: skyNow\(\), mode: posterMode\(\),/);
  assert.match(shot, /snow: uniforms\.uSnow\.value > 0 \? snowInk\(THEME\) : null/);
  assert.match(shot, /function drawShot\(kind = postcard\.filter\)/);
  // declared up front, read by the drifts
  const literal = app.slice(app.indexOf('const uniforms = {'), app.indexOf('};', app.indexOf('const uniforms = {')));
  assert.match(literal, /\buSnowEven: \{ value: 0 \}/);
  assert.match(app, /uniform float uSnow, uWet, uSnowEven;/);
  assert.match(app, /return mix\(smoothstep\(0\.25, 0\.65, 0\.7 \* na \+ 0\.3 \* nb\), 1\.0, uSnowEven\);/);
  // nothing of the poster in the pick pass
  const pick = app.slice(app.indexOf('function pick(x, y) {'), app.indexOf('\n}\n', app.indexOf('function pick(x, y) {')));
  assert.doesNotMatch(pick, /poster/i);
  // the place under the middle: the building nearest the camera's target with a stadsdel, within 1.5 km
  assert.match(app, /nearestIndex\(posterXZ, t\.x, t\.z, i => districtBytes\[i\] > 0, 1500\)/);
  // the loop lets the pass's copy go whenever the Poster is not on screen, after the frame is drawn
  const loop = app.indexOf('if (postcard.on) drawShot(); else renderer.render(scene, camera);');
  assert.ok(loop > 0 && app.indexOf("if (!postcard.on || postcard.filter !== 'poster') posterPass.release();") > loop);
  // a failed fetch of the districts waits before it is asked again: the Poster's preview asks on every frame
  assert.match(app, /if \(!districtAsked && config\.districts && performance\.now\(\) >= districtRetryAt\)/);
  assert.match(app, /\.catch\(\(\) => \{ districtAsked = false; districtRetryAt = performance\.now\(\) \+ DISTRICT_RETRY_MS; \}\)/);
});
