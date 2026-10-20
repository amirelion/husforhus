// Postcard mode (spec 2026-10-20 §7): the map without its panels, framed by the visitor, saved as a picture with a
// filter (None, Sepia, Poster) and a stamp: "husforhus.se" bottom right and the data's credit line bottom left (the
// CC BY sources ask for it). The camera button in the corner (index.html .postcard-open) or P opens it; Close or
// Escape puts the page back and gives the focus back. The map still moves while it is open, so the shot can be framed.
//
// Sepia's live preview is CSS (a filter on the map's canvas and a vignette overlay); the saved picture is drawn on a 2D
// canvas with the same numbers, in ways every browser supports: the colour steps by pixel maths (the CSS filter
// functions' own matrices, ctx.filter being missing from older Safari). The Poster (web/poster.js, the owner's choice
// over tilt-shift on 2026-10-20) is printed in the look's inks by app.js's draw itself, so the screen and the picture
// hold the same pixels, and its title, band and imprint are drawn by poster.js's drawPoster on the picture and on a
// canvas over the map. The renderer keeps no drawing buffer (no preserveDrawingBuffer), so a frame is drawn and copied
// in the same task. A phone shares the PNG (the share sheet offers Save Image); a desktop downloads it.
//
// app.js mounts it (mountPostcard) with the renderer and its own hooks: draw(kind) draws the frame for the shot (the
// hover tint, the pinned outline, a search pick the map's settings hide, a walk's discs and the quest's circle left out;
// in the poster's inks for 'poster'), poster() gives the band's place and year and the poster's colours,
// canOpen() says whether the mode may open (not during a history scene) and onOpen() stops the growth film. A save still
// being made when the mode closes is dropped, and "Share image" only ever holds the newest picture of what the screen
// shows. The top of this file is pure, so web/test/postcard.test.mjs runs it under node; e2e/postcard.spec.mjs covers
// the page.

import { posterLayout, drawPoster } from './poster.js';

export const FILTERS = ['none', 'sepia', 'poster'];
export const SITE = 'husforhus.se';
// The saved picture's longest side at most, in pixels: a 5K screen's full buffer would make a PNG of 15 MB or more.
export const MAX_SIDE = 2560;

// The colour steps of each filter, in order, as CSS filter functions: the preview applies them as a CSS filter, the
// saved picture by the same functions' matrices (filterMatrix). Sepia: an old postcard's brown, faded and a little
// light, with its vignette (VIGNETTE). The Poster has none: its colours are its inks (web/poster.js), printed by the
// draw itself.
export const STEPS = {
  none: [],
  sepia: [['sepia', 1], ['saturate', 1.3], ['contrast', 0.82], ['brightness', 1.05]],
  poster: [],
};
// Sepia's vignette: a warm dark brown from `from` (a fraction of the way to the corners) to `alpha` at the corners.
export const VIGNETTE = { from: 0.45, alpha: 0.6, colour: [62, 40, 20] };

// The file's name: the site and the local date, so a day's postcards sort together.
export function fileName(date = new Date()) {
  const p = n => String(n).padStart(2, '0');
  return `husforhus-${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}.png`;
}

export const validFilter = f => (FILTERS.includes(f) ? f : 'none');

// The preview's CSS filter for the map's canvas.
export const cssFilter = kind => ((STEPS[kind] || []).map(([f, a]) => `${f}(${a})`).join(' ') || 'none');

// The 3 × 4 matrix (rows: r, g, b; columns: r, g, b, offset in 0..255) of one CSS filter function, as the Filter
// Effects spec defines it, so the saved picture matches the preview.
export function filterMatrix(fn, a) {
  if (fn === 'sepia') {
    const k = 1 - Math.min(1, Math.max(0, a));
    return [0.393 + 0.607 * k, 0.769 - 0.769 * k, 0.189 - 0.189 * k, 0,
      0.349 - 0.349 * k, 0.686 + 0.314 * k, 0.168 - 0.168 * k, 0,
      0.272 - 0.272 * k, 0.534 - 0.534 * k, 0.131 + 0.869 * k, 0];
  }
  if (fn === 'saturate') {
    return [0.213 + 0.787 * a, 0.715 - 0.715 * a, 0.072 - 0.072 * a, 0,
      0.213 - 0.213 * a, 0.715 + 0.285 * a, 0.072 - 0.072 * a, 0,
      0.213 - 0.213 * a, 0.715 - 0.715 * a, 0.072 + 0.928 * a, 0];
  }
  if (fn === 'contrast') { const o = 255 * (1 - a) / 2; return [a, 0, 0, o, 0, a, 0, o, 0, 0, a, o]; }
  if (fn === 'brightness') return [a, 0, 0, 0, 0, a, 0, 0, 0, 0, a, 0];
  throw new Error(`no filter ${fn}`);
}

// Applies the steps to RGBA pixels in place. Each step's result is clamped to 0..255 before the next, as a chain of CSS
// filter functions is: composed into one matrix, a sepia that runs past white would come back from it under contrast.
export function applySteps(data, steps) {
  const ms = steps.map(([f, a]) => filterMatrix(f, a));
  if (!ms.length) return data;
  const clamp = v => (v < 0 ? 0 : v > 255 ? 255 : v);
  for (let i = 0; i < data.length; i += 4) {
    let r = data[i], g = data[i + 1], b = data[i + 2];
    for (const m of ms) {
      const r2 = m[0] * r + m[1] * g + m[2] * b + m[3];
      const g2 = m[4] * r + m[5] * g + m[6] * b + m[7];
      const b2 = m[8] * r + m[9] * g + m[10] * b + m[11];
      r = clamp(r2); g = clamp(g2); b = clamp(b2);
    }
    data[i] = r; data[i + 1] = g; data[i + 2] = b;   // a Uint8ClampedArray rounds
  }
  return data;
}

export const vignetteCss = (v = VIGNETTE) => {
  const c = v.colour.join(' ');
  return `radial-gradient(farthest-corner at 50% 50%, rgb(${c} / 0) ${v.from * 100}%, rgb(${c} / ${v.alpha}) 100%)`;
};

// The saved picture's size: the canvas's own, its longest side at most `max`.
export function outSize(w, h, max = MAX_SIDE) {
  const k = Math.min(1, max / Math.max(w, h, 1));
  return { w: Math.max(1, Math.round(w * k)), h: Math.max(1, Math.round(h * k)) };
}

// Splits the credit's parts into lines no wider than maxW (a part wider than that gets a line of its own).
export function wrapParts(parts, maxW, measure, sep = ' · ') {
  const lines = [];
  let line = '';
  for (const p of parts) {
    const next = line ? line + sep + p : p;
    if (line && measure(next) > maxW) { lines.push(line); line = p; } else line = next;
  }
  if (line) lines.push(line);
  return lines;
}

// The stamp's text size on a picture w × h whose CSS pixel is `scale` pixels (base: the page's own text, 11 to 15 CSS
// pixels, so the stamp reads like the credit line on screen) and its two fonts, the site's and the credit's. Apart from
// stampLayout, so the page can load the fonts before anything is measured in them.
export function stampFonts({ w, h, scale = 1, family = 'sans-serif' }) {
  const base = scale * Math.min(15, Math.max(11, Math.min(w, h) / scale * 0.018));
  const px = k => Math.max(1, Math.round(base * k));
  return { base, px, site: `700 ${px(1.15)}px ${family}`, credit: `500 ${px(0.85)}px ${family}` };
}

// Where the stamp goes on a picture w × h whose CSS pixel is `scale` pixels: "husforhus.se" in a pill at the bottom
// right, the credit in a pill at the bottom left (on more lines if it would reach the site's pill; above it, the
// picture's full width, on a very narrow picture), in stampFonts' sizes. measure(text, font) gives a text's width in
// pixels. Every box is { x, y, w, h } in the picture's pixels, with each text's own place (tx, ty: its left end and
// middle).
export function stampLayout({ w, h, scale = 1, credit = [], measure, family = 'sans-serif', site = SITE }) {
  const { base, px, site: siteFont, credit: creditFont } = stampFonts({ w, h, scale, family });
  const pad = px(1.1), gap = px(0.6), padX = px(0.6), padY = px(0.3);
  const siteLine = Math.round(px(1.15) * 1.3), creditLine = Math.round(px(0.85) * 1.35);
  const sw = Math.ceil(measure(site, siteFont)) + 2 * padX, sh = siteLine + 2 * padY;
  const siteBox = { x: w - pad - sw, y: h - pad - sh, w: sw, h: sh, font: siteFont, text: site };
  siteBox.tx = siteBox.x + padX; siteBox.ty = siteBox.y + sh / 2;
  if (!credit.length) return { base, pad, site: siteBox, credit: null };
  // Beside the site's pill when the credit has at least a third of the picture there; else above it.
  let room = siteBox.x - gap - pad, bottom = h - pad;
  if (room < w / 3) { room = w - 2 * pad; bottom = siteBox.y - gap; }
  const lines = wrapParts(credit, room - 2 * padX, t => measure(t, creditFont));
  const cw = Math.ceil(Math.max(...lines.map(t => measure(t, creditFont)))) + 2 * padX;
  const ch = lines.length * creditLine + 2 * padY;
  const box = { x: pad, y: bottom - ch, w: cw, h: ch, font: creditFont };
  box.lines = lines.map((text, i) => ({ text, tx: box.x + padX, ty: box.y + padY + (i + 0.5) * creditLine }));
  return { base, pad, site: siteBox, credit: box };
}

// The keys that move the map (app.js: the arrows pan, and turn with Shift, Ctrl or Cmd; + and - zoom, = and _ too;
// N faces north). Pressed while a picture waits behind "Share image", they make it out of date.
export const MAP_KEYS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', '_', 'n', 'N']);

// The look's font with the stamp's fallbacks.
export const familyOf = font => `"${font}", "Helvetica Neue", Arial, sans-serif`;
// The faces a poster is set in: the title's and the band's weights of the look's font, and the imprint's two.
export const posterFaces = (family, fonts) => [`800 100px ${family}`, `700 100px ${family}`, fonts.site, fonts.credit];

// How far the bar stands up while the Poster previews, in CSS pixels: onto the band (`band`, the band and the paper
// under it), so the band's place and year show whole, when that still leaves at least LIFT_ROOM of the screen's height
// for the map between the head (which ends at `headEnd`) and the bar (`barH` tall, `barGap` up from the bottom when
// down). Else 0: on a phone held sideways (667 × 375) the raised bar would leave a third of the screen, the bar in the
// lower middle of the frame being composed, so it stays down over the band there; the band still prints in the picture.
export const LIFT_ROOM = 0.45;
export function posterLift({ viewH, headEnd, band, barH, barGap }) {
  const lift = Math.round(band);
  return viewH - barGap - lift - barH - headEnd >= LIFT_ROOM * viewH ? lift : 0;
}

// ---------- The page ----------
// Everything below needs a browser. opts: button, bar (index.html), renderer, draw(kind) (the frame for the shot, in
// the poster's inks for 'poster'), T() (the strings), credit() (the credit's parts as text), look() ({ font, ink,
// panel }: the look's font and colours), poster() ({ place, year, colours }: the band's words and posterColours),
// typingIn(el), canOpen(), onOpen() (app.js stops the growth film, whose pause button is out of sight).
export function mountPostcard(opts) {
  const { button, bar, renderer, draw, T, credit, look, poster, typingIn, canOpen = () => true, onOpen = () => {} } = opts;
  const canvas = renderer.domElement;
  const $ = s => bar.querySelector(s);
  const save = $('.pc-save'), share = $('.pc-share'), close = $('.pc-close'), status = $('.pc-status'), hint = $('.pc-hint');
  // A phone or a tablet shares; a narrow desktop window still downloads (macOS would open its share menu instead).
  const handheld = matchMedia('(pointer: coarse)');
  let on = false, filter = 'none', returnFocus = null, busy = false, ready = null, lastStamp = null, savedTimer = 0;
  let lastPoster = null, dressed = null, dressKey = '', dressRaf = 0, dressLayout = null, lifted = 0;
  // session counts each open and close, view each change to what the screen shows (a filter, a move of the map). A save
  // keeps both from its tap: closed since, it is dropped; reframed since, its picture is not offered behind "Share
  // image", which only ever holds what the screen still shows.
  let session = 0, view = 0;

  // The preview's overlays, just above the map: sepia's vignette, and the poster's dress (its head and title, its band
  // and its paper) on a canvas of the map's own size, drawn by the same drawPoster as the picture.
  const vignette = document.createElement('div');
  vignette.className = 'pc-vignette';
  vignette.hidden = true;
  vignette.setAttribute('aria-hidden', 'true');
  vignette.style.background = vignetteCss();
  const dress = document.createElement('canvas');
  dress.className = 'pc-poster';
  dress.hidden = true;
  dress.setAttribute('aria-hidden', 'true');
  canvas.after(vignette, dress);

  const measureIn = ctx => (t, font) => { ctx.font = font; return ctx.measureText(t).width; };
  // The poster's layout on a picture w × h whose CSS pixel is `scale` pixels, with P (poster()) for its words.
  function posterOn(ctx, w, h, scale, P) {
    const family = familyOf(look().font), fonts = stampFonts({ w, h, scale, family });
    return posterLayout({ w, h, scale, family, fonts, place: P.place, year: P.year, credit: credit(), measure: measureIn(ctx) });
  }
  // What the tests read of a poster: its boxes, its texts and where they stand, its colours.
  const describe = (L, colours) => ({
    width: L.w, height: L.h, scale: L.scale, m: L.m, bottom: L.bottom, head: box(L.head), band: box(L.band),
    picture: box(L.picture), colours,
    title: { text: L.title.text, font: L.title.font, size: L.title.size, baseline: L.title.baseline,
      x0: L.title.glyphs[0].x, x1: L.title.glyphs[0].x + L.title.width },
    place: { text: L.place.text, font: L.place.font, baseline: L.place.baseline, width: L.place.width },
    site: { text: L.imprint.site.text, x: L.imprint.site.x, y: L.imprint.site.y },
    credit: L.imprint.credit.lines.map(l => l.text),
  });

  // While the Poster previews, each frame looks at what its dress shows (the screen's size, the stadsdel under the
  // middle and the year, the look, the weather's sky, the language's credit, whether the look's font is in) and draws
  // it again when that changed: a pan to another stadsdel renames the band as the map moves. The bar stands on the
  // band, so the band shows whole, where the screen has the room (posterLift).
  function dressFrame() {
    dressRaf = 0;
    if (dress.hidden) return;
    dressRaf = requestAnimationFrame(dressFrame);
    const w = canvas.width, h = canvas.height, scale = w / Math.max(1, canvas.clientWidth);
    const P = poster(), family = familyOf(look().font);
    const faces = posterFaces(family, stampFonts({ w, h, scale, family }));
    const loaded = faces.every(f => document.fonts?.check(f) ?? true);
    const key = JSON.stringify([w, h, scale, family, P, credit(), loaded]);
    if (key !== dressKey) {
      dressKey = key;
      if (!loaded) faces.forEach(f => document.fonts?.load(f).catch(() => {}));
      if (dress.width !== w) dress.width = w;
      if (dress.height !== h) dress.height = h;
      const ctx = dress.getContext('2d');
      ctx.clearRect(0, 0, w, h);
      dressLayout = posterOn(ctx, w, h, scale, P);
      drawPoster(ctx, dressLayout, P.colours);
      dressed = describe(dressLayout, P.colours);
    }
    liftBar();
  }
  // Every frame, as the bar's height can change without the dress (a failed save's message in the hint, "Share
  // image"); the style is only written when the lift changes.
  function liftBar() {
    const L = dressLayout, viewH = canvas.clientHeight, r = bar.getBoundingClientRect();
    const next = posterLift({ viewH, headEnd: (L.head.y + L.head.h) / L.scale, band: (L.band.h + L.bottom) / L.scale,
      barH: r.height, barGap: viewH - r.bottom - lifted });
    if (next === lifted) return;
    lifted = next;
    if (next) bar.style.setProperty('--pc-lift', `${next}px`); else bar.style.removeProperty('--pc-lift');
  }

  function preview() {
    canvas.style.filter = on && STEPS[filter].length ? cssFilter(filter) : '';
    vignette.hidden = !(on && filter === 'sepia');
    const show = on && filter === 'poster';
    if (dress.hidden === show) {
      dress.hidden = !show;
      dressKey = '';
      if (show) { if (!dressRaf) dressFrame(); } else {
        dressed = null; dressLayout = null; lifted = 0;
        bar.style.removeProperty('--pc-lift');
        // A hidden canvas keeps its pixels, as large as the screen's buffer: let them go (dressFrame sizes it again).
        dress.width = 0; dress.height = 0;
      }
    }
    bar.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === filter)));
  }
  function setFilter(f) {
    const next = validFilter(f);
    if (next !== filter) reframed();
    filter = next;
    hintSays('postcard.hint');
    preview();
  }

  // The picture waiting behind "Share image" goes, and the button with it (the focus to Save, if it was on the button).
  function drop() {
    ready = null;
    if (share.hidden) return;
    const focused = document.activeElement === share;
    share.hidden = true;
    if (focused) save.focus({ preventScroll: true });
  }
  // What the screen shows has changed: the waiting picture no longer matches it.
  function reframed() { view++; drop(); }
  // The hint above the row, or a failed save's message in its place, where it is seen (the status, a live region, says
  // it too, but is not on screen). Its data-i18n follows, so a language switch redraws whichever it shows.
  function hintSays(id) {
    if (hint.dataset.i18n === id) return;
    hint.dataset.i18n = id;
    hint.textContent = T()(id);
    hint.classList.toggle('pc-fail', id === 'postcard.failed');
  }
  // A new opening starts clean: nothing from an earlier one (a waiting picture, a message, "Done") shows in the bar.
  function reset() {
    session++;
    reframed();
    status.textContent = '';
    hintSays('postcard.hint');
    if (!busy) { clearTimeout(savedTimer); save.textContent = T()('postcard.save'); }
  }

  function open() {
    if (on || !canOpen()) return;
    on = true;
    reset();
    onOpen();
    returnFocus = document.activeElement;
    document.body.classList.add('postcard');
    bar.hidden = false;
    preview();
    bar.querySelector('[data-filter][aria-pressed="true"]')?.focus({ preventScroll: true });
  }
  function exit() {
    if (!on) return;
    on = false;
    reset();
    document.body.classList.remove('postcard');
    bar.hidden = true;
    preview();
    const back = returnFocus?.isConnected && returnFocus !== document.body && returnFocus.checkVisibility?.() !== false
      ? returnFocus : button;
    back.focus({ preventScroll: true });
    returnFocus = null;
  }

  // After the next paint: a frame's callback, then a task after it. A hidden page runs no frames, so a timer stands in.
  const nextPaint = () => new Promise(resolve => { requestAnimationFrame(() => setTimeout(resolve, 0)); setTimeout(resolve, 250); });

  // The look's faces loaded before anything is measured in them: measured in the fallback (a slow line, a save just
  // after a look switch), the pills and the title would fit its widths and the text drawn in the real face would not.
  async function loadFonts(list) {
    await Promise.all(list.map(f => (document.fonts?.load(f) ?? Promise.resolve()).catch(() => {})));
    await document.fonts?.ready;
  }

  // The picture: the frame drawn and copied at once (draw() and drawImage in one task), then the filter and the
  // stamp (the poster's dress, for the Poster). Returns the 2D canvas.
  async function capture({ filter: kind = filter, stamp = true } = {}) {
    kind = validFilter(kind);
    draw(kind);
    const { w, h } = outSize(canvas.width, canvas.height);
    const shot = document.createElement('canvas');
    shot.width = w; shot.height = h;
    const ctx = shot.getContext('2d');
    ctx.drawImage(canvas, 0, 0, w, h);
    const scale = w / Math.max(1, canvas.clientWidth);
    const P = kind === 'poster' && stamp ? poster() : null;   // the place and the year of this frame
    // The frame is safe in the copy. The pixel work below takes a tenth of a second on a laptop and more on a phone, so
    // it waits for a paint: Download's "Preparing…" shows at the tap, not after the work it stands for.
    await nextPaint();
    if (STEPS[kind].length) {
      const img = ctx.getImageData(0, 0, w, h);
      applySteps(img.data, STEPS[kind]);
      ctx.putImageData(img, 0, 0);
    }
    if (kind === 'sepia') drawVignette(ctx, w, h);
    lastStamp = null;
    lastPoster = null;
    if (P) {
      // The poster carries the stamp in its imprint.
      const family = familyOf(look().font);
      await loadFonts(posterFaces(family, stampFonts({ w, h, scale, family })));
      const L = posterOn(ctx, w, h, scale, P);
      drawPoster(ctx, L, P.colours);
      lastPoster = describe(L, P.colours);
    } else if (stamp) {
      const L = look(), family = familyOf(L.font);
      const fonts = stampFonts({ w, h, scale, family });
      await loadFonts([fonts.site, fonts.credit]);
      const layout = stampLayout({ w, h, scale, credit: credit(), family, measure: measureIn(ctx) });
      drawStamp(ctx, layout, L);
      lastStamp = { width: w, height: h, scale, base: fonts.base, fonts: { site: fonts.site, credit: fonts.credit },
        site: box(layout.site), credit: layout.credit && box(layout.credit), lines: layout.credit?.lines.map(l => l.text) || [] };
    }
    return shot;
  }
  const box = b => ({ x: b.x, y: b.y, w: b.w, h: b.h });

  // CSS's farthest-corner ellipse is a circle through the corners, stretched to the picture's shape.
  function drawVignette(ctx, w, h) {
    const { from, alpha, colour: [r, g, b] } = VIGNETTE;
    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.scale(w / 2 * Math.SQRT2, h / 2 * Math.SQRT2);
    const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
    grad.addColorStop(from, `rgba(${r},${g},${b},0)`);
    grad.addColorStop(1, `rgba(${r},${g},${b},${alpha})`);
    ctx.fillStyle = grad;
    ctx.fillRect(-1, -1, 2, 2);
    ctx.restore();
  }
  // A box with rounded corners, drawn with arcs (ctx.roundRect is missing from older Safari).
  function pill(ctx, { x, y, w, h }) {
    const r = Math.min(h / 2, w / 2, Math.round(h * 0.3));
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
    ctx.fill();
  }
  function drawStamp(ctx, layout, L) {
    ctx.save();
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    for (const b of [layout.site, layout.credit].filter(Boolean)) {
      ctx.globalAlpha = 0.86;
      ctx.fillStyle = L.panel;
      pill(ctx, b);
      ctx.globalAlpha = 1;
      ctx.fillStyle = L.ink;
      ctx.font = b.font;
      for (const t of b.lines || [{ text: b.text, tx: b.tx, ty: b.ty }]) ctx.fillText(t.text, t.tx, t.ty);
    }
    ctx.restore();
  }

  const toBlob = c => new Promise((resolve, reject) => c.toBlob(b => (b ? resolve(b) : reject(new Error('toBlob'))), 'image/png'));
  function download(blob, name) {
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = name; a.hidden = true;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }
  function say(id) {
    status.textContent = T()(id);
  }
  function saved() {
    say('postcard.saved');
    save.textContent = T()('postcard.saved');
    clearTimeout(savedTimer);
    savedTimer = setTimeout(() => { save.textContent = T()('postcard.save'); }, 2000);
  }
  // A phone shares the file. iOS refuses a share that comes long after the tap (NotAllowedError), so a picture Save
  // made then waits behind a second button, "Share image", whose own tap shares it: always the newest picture, and only
  // while the screen still shows it (`frame`, the view it was taken in). Refused at that button too, it downloads. A
  // cancelled share is left alone; any other failure downloads. Closed or opened again meanwhile, the bar is left alone.
  async function shareFile(file, blob, { button: fromButton = false, frame = view } = {}) {
    const mine = session;
    try {
      await navigator.share({ files: [file] });
      if (session !== mine) return;
      if (fromButton) drop();                              // its work is done
      saved();
    } catch (e) {
      if (e?.name === 'AbortError' || session !== mine) return;
      if (e?.name === 'NotAllowedError' && !fromButton) {
        if (frame !== view) return;                        // reframed while it was made: Save makes the new one
        ready = { file, blob };
        share.hidden = false;
        share.focus({ preventScroll: true });
        return;
      }
      if (fromButton) drop();
      download(blob, file.name);
      saved();
    }
  }
  async function savePicture() {
    if (busy) return;
    busy = true;
    const mine = session, frame = view;
    drop();                                                // the picture it replaces
    hintSays('postcard.hint');
    clearTimeout(savedTimer);
    save.setAttribute('aria-busy', 'true');
    save.textContent = T()('postcard.saving');
    try {
      const blob = await toBlob(await capture());
      save.textContent = T()('postcard.save');
      // Closed while it was made (Close and Escape still work during "Preparing…"), maybe opened again: the visitor left
      // this picture, so it is neither downloaded nor shared, and nothing of it reaches the bar.
      if (session !== mine) return;
      const name = fileName(new Date());
      const file = typeof File === 'function' ? new File([blob], name, { type: 'image/png' }) : null;
      if (file && handheld.matches && navigator.canShare?.({ files: [file] })) await shareFile(file, blob, { frame });
      else { download(blob, name); saved(); }
    } catch (e) {
      save.textContent = T()('postcard.save');
      if (session !== mine) return;
      console.warn('The postcard could not be made', e);
      say('postcard.failed');
      hintSays('postcard.failed');
    } finally {
      busy = false;
      save.removeAttribute('aria-busy');
    }
  }

  button.onclick = () => (on ? exit() : open());
  bar.addEventListener('click', e => {
    const f = e.target.closest('[data-filter]');
    if (f) setFilter(f.dataset.filter);
  });
  save.onclick = savePicture;
  close.onclick = exit;
  share.onclick = () => { if (ready) shareFile(ready.file, ready.blob, { button: true }); };
  // A phone turned sideways (or a window made wider or narrower) frames another picture. Only the width counts: a
  // phone's toolbars come and go in the height alone.
  let width = canvas.clientWidth;
  addEventListener('resize', () => {
    if (on && canvas.clientWidth !== width) reframed();
    width = canvas.clientWidth;
  });
  // A press or a wheel on the map moves it, or is about to: the screen will not show the waiting picture any more.
  canvas.addEventListener('pointerdown', () => { if (on) reframed(); });
  canvas.addEventListener('wheel', () => { if (on) reframed(); }, { passive: true });
  // Capture phase, before the page's own keys: while it is open Escape closes it (and only it: a pinned card stays
  // pinned under it), and the search's keys wait; P opens and closes it, unless the keys are going to a field. A key
  // that moves the map makes the waiting picture out of date, as a press on the map does.
  addEventListener('keydown', e => {
    if (on && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); exit(); return; }
    if (on && (e.key === '/' || ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)))) {
      e.preventDefault(); e.stopImmediatePropagation(); return;
    }
    if (on && MAP_KEYS.has(e.key) && !typingIn(e.target)) reframed();
    if ((e.key === 'p' || e.key === 'P') && !e.ctrlKey && !e.metaKey && !e.altKey && !e.repeat && !typingIn(e.target)) {
      e.preventDefault();
      if (on) exit(); else open();
    }
  }, true);

  // stamp: the last picture's stamp; poster: the last poster picture's layout, dress: the poster preview's (null while
  // the Poster is not on screen), lift: how far the bar stands up on its band (0: down).
  return {
    get on() { return on; }, get filter() { return filter; }, get stamp() { return lastStamp; },
    get poster() { return lastPoster; }, get dress() { return dressed; }, get lift() { return lifted; },
    open, exit, setFilter, capture, save: savePicture,
  };
}
