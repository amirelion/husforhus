// The postcard's Poster filter (web/postcard.js; the owner's choice of 2026-10-20 over tilt-shift): the view as a 1930s
// railway travel poster. The map is printed in a few flat inks of the look's own palette, a little more saturated and
// contrasted; "STOCKHOLM" stands large across a sky-coloured head, a band in the look's poster colour names the
// stadsdel under the middle of the view and the year the map shows, and the paper's margin carries the site and the
// data's credit line (the CC BY sources ask for it), as a printer's imprint.
//
// The inks: every pixel takes the nearest (in OKLab) of the look's sky (the weather's, as the screen shows it), land,
// water, and every colour a building can have in the mode on screen, each lit and shaded (posterInks). Gradients (the
// fog, a building's lit and shaded faces) step from ink to ink, which is the poster's charm, and a building's faces
// print in inks of its own colour, as the colours mean ages. A CSS filter cannot do that (an SVG filter steps each
// colour channel on its own, which turned the looks into primaries: white sky, black water, cyan and orange buildings),
// so a shader does it: makePosterPass copies the drawn frame and prints it back through the inks, one extra draw. The
// preview and the saved picture are the same pixels; the head, the title, the band and the imprint are drawn by
// drawPoster on the picture and on a canvas over the map (the preview), from one layout (posterLayout).
//
// app.js makes the pass (makePosterPass) and runs it in the postcard's frame while the Poster filter is on; the top of
// this file is pure, so web/test/poster.test.mjs runs it under node; e2e/postcard.spec.mjs covers the page.
import { rgb, hex, lin, oklabLin } from './tone.js';

export const TITLE = 'STOCKHOLM';
// The inks are the look's colours with this much more saturation and contrast (the CSS functions' own maths, as the
// Sepia filter's steps are): flat colour on paper reads a little stronger than the same colour lit on a screen.
export const BOOST = { saturate: 1.15, contrast: 1.08 };
// A building's faces as app.js lights them (FRAG, themes.js SHADING): roofs at 1.04 of their colour, walls from 0.66
// in the shade to 0.94 facing the sun, all of it darker towards the foot (0.82 at the ground). Matched only as itself,
// a colour's shaded walls printed in whichever other colour lay nearest: "Year unknown"'s grey walls in a period's
// green or teal, or in the water's ink, an ochre's in green. So each colour a building can have is matched at a few of
// those shadings (its RUNGS) and prints in two inks of its own: itself, and SHADED.ink of it (a little lighter than
// the screen's shade, as ink on paper is) for a rung under SHADED.below, a face in the shade. The pale greys, "Year
// unknown" and the Layers mode's maquette, lie near the look's land, water and sky, so they take more rungs; the
// hatch, a darker grey, two.
export const RUNGS = { colour: [1, 0.84, 0.62], grey: [1, 0.93, 0.84, 0.73, 0.62], hatch: [1, 0.62] };
export const SHADED = { below: 0.7, ink: 0.8 };
// At most this many inks (the shader's array): four ground colours, the snow's, "Year unknown"'s other four rungs and
// its hatch's two, and twelve periods' three (47; the Layers mode's maquette and eight groups make 34).
export const MAX_INKS = 48;

// saturate(s) then contrast(c) on one colour (0..1 each), clamped after each step as a chain of CSS filters is.
export function boostInk([r, g, b], { saturate: s, contrast: c } = BOOST) {
  const cl = v => Math.min(1, Math.max(0, v));
  const r1 = cl((0.213 + 0.787 * s) * r + (0.715 - 0.715 * s) * g + (0.072 - 0.072 * s) * b);
  const g1 = cl((0.213 - 0.213 * s) * r + (0.715 + 0.285 * s) * g + (0.072 - 0.072 * s) * b);
  const b1 = cl((0.213 - 0.213 * s) * r + (0.715 - 0.715 * s) * g + (0.072 + 0.928 * s) * b);
  return [r1, g1, b1].map(v => cl((v - 0.5) * c + 0.5));
}

// The colours a picture is matched against (hex), in order: the sky as it is now, land, water, "Year unknown", the
// snow's colour while it snows (app.js lays the snow evenly for the poster, so roofs print white); in the period mode
// "Year unknown"'s other rungs and its hatch's, in the Layers mode the maquette's; then the mode's colours, each at its
// rungs: every period, the Floors ramp's four, or the Layers mode's group colours. `inks` are what is printed,
// boosted: the colour itself for the sky, the ground, the snow and a lit rung, the colour's darker ink for a shaded
// one.
export const shadeOf = (h, k) => hex(rgb(h).map(v => v * k));
export function posterInks({ theme, sky = theme.sky, mode = 'period', groups = [], snow = null }) {
  const ramp = mode === 'floors' ? theme.floors : mode === 'layers' ? groups : theme.periods;
  const pairs = [sky, theme.land, theme.water, theme.unknown, ...(snow ? [snow] : [])].map(h => [h, h]);
  const rungs = (h, ks) => ks.forEach(k => pairs.push([shadeOf(h, k), k < SHADED.below ? shadeOf(h, SHADED.ink) : h]));
  if (mode === 'period') {
    rungs(theme.unknown, RUNGS.grey.slice(1));                      // itself is the fourth colour above
    if (theme.unknownHatch) rungs(theme.unknownHatch, RUNGS.hatch);
  }
  if (mode === 'layers') rungs(theme.maquette, RUNGS.grey);
  for (const h of ramp) rungs(h, RUNGS.colour);
  const kept = pairs.slice(0, MAX_INKS);   // never cut in practice: web/test/poster.test.mjs checks every look and mode
  return { match: kept.map(p => p[0]), inks: kept.map(p => hex(boostInk(rgb(p[1])))) };
}

// The ink a colour (0..1 each) prints in: the index of the nearest match colour in OKLab. The shader (POSTER_FRAG) does
// the same sums.
export function nearestInk(c, labs) {
  const p = oklabLin(c.map(lin));
  let best = Infinity, k = 0;
  labs.forEach((q, i) => {
    const d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2;
    if (d < best) { best = d; k = i; }
  });
  return k;
}
export const matchLabs = match => match.map(h => oklabLin(rgb(h).map(lin)));

// WCAG 2 contrast between two colours.
const relLum = h => { const c = rgb(h).map(lin); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
export const contrast = (a, b) => { const [lo, hi] = [relLum(a), relLum(b)].sort((x, y) => x - y); return (hi + 0.05) / (lo + 0.05); };

// The poster's own colours: the head is the sky's ink (the sky is ink 0, so the head meets the printed sky without a
// seam); the title, the band and its text and the paper come from the look's `poster` colours (web/themes.js). A title
// that would not stand out from a weather's sky (3:1, large text) takes whichever of the look's ink and panel does.
export function posterColours(theme, sky = theme.sky) {
  const head = hex(boostInk(rgb(sky)));
  const P = theme.poster || { title: theme.ui['--ink'], band: theme.ui['--accent'], bandInk: theme.ui['--panel'],
    paper: theme.ui['--panel'], imprint: theme.ui['--ink'] };
  let title = P.title;
  if (contrast(title, head) < 3) {
    title = [theme.ui['--ink'], theme.ui['--panel']].sort((a, b) => contrast(b, head) - contrast(a, head))[0];
  }
  return { head, title, band: P.band, bandInk: P.bandInk, paper: P.paper, imprint: P.imprint };
}

// The year on the band: the timeline's, or this year's at "Today" (the map's last year is the data's, a year behind).
export const posterYear = (year, yearMax, now = new Date()) => String(year >= yearMax ? now.getFullYear() : Math.round(year));
// The band's words: "Gamla stan · 2026", or the year alone over open water.
export const placeLine = (place, year) => [place, year].filter(Boolean).join(' · ');

// The index of the point nearest (x, z) among xz = [x0, z0, x1, z1, …] for which ok(i) holds, within `max`; -1 if none.
// app.js asks it for the building nearest the point the camera looks at, to name the stadsdel under the middle.
export function nearestIndex(xz, x, z, ok = () => true, max = Infinity) {
  let best = max * max, k = -1;
  for (let i = 0, n = xz.length / 2; i < n; i++) {
    const dx = xz[2 * i] - x, dz = xz[2 * i + 1] - z, d = dx * dx + dz * dz;
    if (d < best && ok(i)) { best = d; k = i; }
  }
  return k;
}

// The letters of a spaced line, each with its own left end (pixels), the whole centred on cx: kerning is lost to the
// spacing anyway, and drawing letter by letter works in every browser (ctx.letterSpacing is missing from older Safari).
export function spaced(text, font, size, spacing, cx, measure) {
  const adv = [...text].map(ch => measure(ch, font));
  const width = adv.reduce((s, a) => s + a, 0) + spacing * size * Math.max(0, adv.length - 1);
  let x = cx - width / 2;
  const glyphs = [...text].map((ch, i) => { const g = { ch, x }; x += adv[i] + spacing * size; return g; });
  return { width, glyphs };
}

// The poster on a picture w × h whose CSS pixel is `scale` pixels. Every box is { x, y, w, h } in the picture's
// pixels; texts carry their font and their glyphs (spaced) or their left end, and a baseline. measure(text, font) gives
// a text's width; `family` is the look's font stack; place and year make the band's line; credit is the credit's parts;
// fonts is stampFonts' (the imprint is set as the postcard's stamp is: the page's own text size).
//  - paper: the margin all round (`m`, 2.5% of the shorter side), deeper at the bottom, where the imprint stands: the
//    credit at the left (on more lines if it would reach the site), the site at the right. A thin keyline runs round
//    the print a little out from it, so white land at the picture's edge still ends somewhere.
//  - head: across the top inside the paper, as tall as the title and its air; the title is 800 weight, spaced 0.16 em,
//    as wide as 86% of the head or as tall as 15% of the picture, whichever is less.
//  - band: across the bottom inside the paper, the place line in capitals, 700 weight, spaced 0.12 em, at about a third
//    of the title's size (never under 16 CSS pixels; smaller only to fit a long name in the band).
export const TITLE_SPACING = 0.16, PLACE_SPACING = 0.12, CAP = 0.72;
export function posterLayout({ w, h, scale = 1, measure, family = 'sans-serif', place = '', year = '', credit = [], fonts,
  site = 'husforhus.se' }) {
  const m = Math.max(4, Math.round(Math.min(w, h) * 0.025));
  const innerW = w - 2 * m;
  const k = Math.max(1, Math.round(1.25 * scale)), g = Math.max(1, Math.round(m * 0.35));
  // The title: its size from its width at 100 px, which grows in proportion.
  const font = size => `800 ${size}px ${family}`;
  const at100 = [...TITLE].reduce((s, ch) => s + measure(ch, font(100)), 0) / 100;
  const byWidth = innerW * 0.86 / (at100 + TITLE_SPACING * (TITLE.length - 1));
  const size = Math.max(8, Math.floor(Math.min(byWidth, (h - 2 * m) * 0.15)));
  const cap = size * CAP, padT = Math.round(size * 0.36), padB = Math.round(size * 0.32);
  const head = { x: m, y: m, w: innerW, h: Math.round(padT + cap + padB) };
  const title = { text: TITLE, font: font(size), size, baseline: head.y + padT + cap,
    ...spaced(TITLE, font(size), size, TITLE_SPACING, w / 2, measure) };
  // The imprint, in the paper under the keyline.
  const { px, site: siteFont, credit: creditFont } = fonts;
  const lineH = Math.round(px(0.85) * 1.4), padY = Math.max(m - g - k, px(0.45));
  const siteW = measure(site, siteFont);
  const lines = credit.length ? wrapCredit(credit, innerW - siteW - px(1.2), t => measure(t, creditFont)) : [];
  const imprintH = Math.max(lineH, lines.length * lineH);
  const bottom = Math.round(g + k + 2 * padY + imprintH);
  const imprintTop = h - padY - imprintH;
  const imprint = {
    site: { text: site, font: siteFont, x: w - m - siteW, y: imprintTop + imprintH - lineH / 2 },
    credit: { font: creditFont, lines: lines.map((text, i) => ({ text, x: m, y: imprintTop + (i + 0.5) * lineH })) },
  };
  // The band and its line, the size brought down if a long name would not fit in 90% of it.
  const text = placeLine(place, year).toLocaleUpperCase('sv');
  let pSize = Math.round(Math.max(16 * scale, Math.min(size * 0.36, 44 * scale)));
  const wide = spaced(text, `700 100px ${family}`, 100, PLACE_SPACING, 0, measure).width / 100;
  if (wide * pSize > innerW * 0.9) pSize = Math.max(8, Math.floor(innerW * 0.9 / wide));
  const pFont = `700 ${pSize}px ${family}`, pCap = pSize * CAP, padBand = Math.round(pSize * 0.62);
  const bh = Math.round(pCap + 2 * padBand);
  const band = { x: m, y: h - bottom - bh, w: innerW, h: bh };
  const line = { text, font: pFont, size: pSize, baseline: band.y + padBand + pCap,
    ...spaced(text, pFont, pSize, PLACE_SPACING, w / 2, measure) };
  const keyline = { x: m - g - k / 2, y: m - g - k / 2, w: innerW + 2 * g + k, h: band.y + bh - m + 2 * g + k, width: k };
  return { w, h, scale, m, bottom, head, title, band, place: line, imprint, keyline,
    picture: { x: m, y: head.y + head.h, w: innerW, h: band.y - head.y - head.h } };
}
// The credit's parts on lines no wider than maxW (as the stamp's wrapParts; a part wider than that has a line of its own).
function wrapCredit(parts, maxW, width, sep = ' · ') {
  const lines = [];
  let line = '';
  for (const p of parts) {
    const next = line ? line + sep + p : p;
    if (line && width(next) > maxW) { lines.push(line); line = p; } else line = next;
  }
  if (line) lines.push(line);
  return lines;
}

// Draws the poster's dress over a picture already printed in its inks: the head and its title, the band and its line,
// then the paper over the edges, its keyline and the imprint. ctx is a 2D context; L a posterLayout; C posterColours.
export function drawPoster(ctx, L, C) {
  ctx.save();
  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';
  ctx.fillStyle = C.head;
  ctx.fillRect(L.head.x, L.head.y, L.head.w, L.head.h);
  ctx.fillStyle = C.title;
  ctx.font = L.title.font;
  for (const g of L.title.glyphs) ctx.fillText(g.ch, g.x, L.title.baseline);
  ctx.fillStyle = C.band;
  ctx.fillRect(L.band.x, L.band.y, L.band.w, L.band.h);
  ctx.fillStyle = C.bandInk;
  ctx.font = L.place.font;
  for (const g of L.place.glyphs) ctx.fillText(g.ch, g.x, L.place.baseline);
  // The paper: four strips, the bottom one wider.
  ctx.fillStyle = C.paper;
  ctx.fillRect(0, 0, L.w, L.m);
  ctx.fillRect(0, L.h - L.bottom, L.w, L.bottom);
  ctx.fillRect(0, 0, L.m, L.h);
  ctx.fillRect(L.w - L.m, 0, L.m, L.h);
  ctx.strokeStyle = C.imprint;
  ctx.lineWidth = L.keyline.width;
  ctx.strokeRect(L.keyline.x, L.keyline.y, L.keyline.w, L.keyline.h);
  ctx.fillStyle = C.imprint;
  ctx.textBaseline = 'middle';
  ctx.font = L.imprint.site.font;
  ctx.fillText(L.imprint.site.text, L.imprint.site.x, L.imprint.site.y);
  ctx.font = L.imprint.credit.font;
  for (const l of L.imprint.credit.lines) ctx.fillText(l.text, l.x, l.y);
  ctx.restore();
}

// ---------- The pass ----------
// The shader: each pixel of the copied frame to OKLab (sRGB decoded, LMS, cube roots: tone.js oklabLin's numbers), the
// nearest match colour found, its ink written. uCount match colours are used of MAX_INKS.
export const POSTER_FRAG = /* glsl */ `
uniform sampler2D uFrame;
uniform vec3 uMatch[${MAX_INKS}];
uniform vec3 uInk[${MAX_INKS}];
uniform int uCount;
vec3 toLinear(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
vec3 toLab(vec3 c) {
  vec3 l = toLinear(c);
  vec3 lms = vec3(0.4122214708 * l.r + 0.5363325363 * l.g + 0.0514459929 * l.b,
                  0.2119034982 * l.r + 0.6806995451 * l.g + 0.1073969566 * l.b,
                  0.0883024619 * l.r + 0.2817188376 * l.g + 0.6299787005 * l.b);
  lms = pow(max(lms, vec3(0.0)), vec3(1.0 / 3.0));
  return vec3(0.2104542553 * lms.x + 0.7936177850 * lms.y - 0.0040720468 * lms.z,
              1.9779984951 * lms.x - 2.4285922050 * lms.y + 0.4505937099 * lms.z,
              0.0259040371 * lms.x + 0.7827717662 * lms.y - 0.8086757660 * lms.z);
}
void main() {
  vec3 p = toLab(texelFetch(uFrame, ivec2(gl_FragCoord.xy), 0).rgb);
  float best = 1e9;
  vec3 ink = uInk[0];
  for (int i = 0; i < ${MAX_INKS}; i++) {
    if (i >= uCount) break;
    vec3 d = p - uMatch[i];
    float e = dot(d, d);
    if (e < best) { best = e; ink = uInk[i]; }
  }
  gl_FragColor = vec4(ink, 1.0);
}`;

// The pass: render(draw, inks) calls draw() (the frame, onto the canvas), copies the canvas into a texture and draws it
// back through the inks (posterInks' result), one full-screen triangle pair. The renderer's colours are plain sRGB
// (app.js: no colour management, linear output), so what is copied is what the screen shows, and the inks are written
// as they are. The copy is as large as the drawing buffer, made again when that changes size and let go by release().
export function makePosterPass(THREE, renderer) {
  let frame = null, labsFor = null;
  const size = new THREE.Vector2();
  const vec = () => Array.from({ length: MAX_INKS }, () => new THREE.Vector3());
  const material = new THREE.ShaderMaterial({
    uniforms: { uFrame: { value: null }, uMatch: { value: vec() }, uInk: { value: vec() }, uCount: { value: 0 } },
    vertexShader: 'void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }',
    fragmentShader: POSTER_FRAG,
    depthTest: false, depthWrite: false,
  });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  quad.frustumCulled = false;   // placed by its vertex shader, not by the camera
  const scene = new THREE.Scene();
  scene.add(quad);
  const camera = new THREE.Camera();
  let frames = 0;
  function setInks({ match, inks }) {
    const key = match.join() + inks.join();
    if (key === labsFor) return;
    labsFor = key;
    matchLabs(match).forEach((q, i) => material.uniforms.uMatch.value[i].set(...q));
    inks.forEach((h, i) => material.uniforms.uInk.value[i].set(...rgb(h)));
    material.uniforms.uCount.value = match.length;
  }
  return {
    render(draw, P) {
      draw();
      renderer.getDrawingBufferSize(size);
      if (!frame || frame.image.width !== size.x || frame.image.height !== size.y) {
        frame?.dispose();
        frame = new THREE.FramebufferTexture(size.x, size.y);
        material.uniforms.uFrame.value = frame;
      }
      renderer.copyFramebufferToTexture(frame);
      setInks(P);
      const auto = renderer.autoClear;
      renderer.autoClear = false;
      renderer.render(scene, camera);
      renderer.autoClear = auto;
      frames++;
    },
    // app.js lets the copy go whenever the Poster is not drawn: it is as large as the drawing buffer (59 MB on a 5K
    // screen at the app's pixel ratio of 2), and the next poster frame makes it again.
    release() {
      if (!frame) return;
      frame.dispose();
      frame = null;
      material.uniforms.uFrame.value = null;
    },
    state: () => ({ frames, count: material.uniforms.uCount.value, size: frame ? [frame.image.width, frame.image.height] : null }),
  };
}
