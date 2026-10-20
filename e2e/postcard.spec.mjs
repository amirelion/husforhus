// Postcard mode (spec 2026-10-20 §7, web/postcard.js): the camera button, or P, sets the page's panels aside and shows
// the bar; Close and Escape put them back and give the focus back; the shot leaves out the hover tint, the pinned
// building's tint and outline, a search pick the map's settings hide, and a walk's route; the film stops and the loading
// line steps aside; each filter shows its preview and saves what it shows; Save downloads husforhus-<date>.png with the
// map and its stamp, measured in the look's own font; a failed save says so on screen. On a phone the bar fits the
// screen (one row held sideways) and takes taps in 44 px, the labels speak Swedish, a share the browser refuses waits
// behind "Share image", which only ever holds the newest picture of what the screen shows, and closing drops a save
// still being made.
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import { settled } from './settled.mjs';

async function open(page, query = '') {
  await page.goto('/' + query);
  await settled(page);
  // The tests compare shots taken moments apart: in a build with boats they would sail between two shots, and the water
  // would ripple, so both stand still here (the frames are what the postcard leaves out, not what moves).
  await page.evaluate(() => { window.__dbg.ferries?.freeze(0); window.__dbg.pauseEffects(true); });
}
// What a history scene sets aside, and the search, the credit and the veils.
const ASIDE = ['.masthead', '.modes', '.corner', '.panel', '.timeline', '.howto', '.credits', '.veil-top', '.veil-bottom'];
const visibility = (page, sels) => page.evaluate(sels => sels.map(s => {
  const el = document.querySelector(s);
  return el ? getComputedStyle(el).visibility : 'none';
}), sels);
const isOn = page => page.evaluate(() => document.body.classList.contains('postcard'));

// A building under the middle of the screen, for the pinned card and the hover.
const buildingInView = page => page.evaluate(() => {
  for (const [x, y] of [[0.47, 0.47], [0.5, 0.5], [0.45, 0.55], [0.55, 0.45], [0.3, 0.6], [0.7, 0.4]]) {
    const px = Math.round(innerWidth * x), py = Math.round(innerHeight * y), gid = window.__dbg.pick(px, py);
    if (gid >= 0) return { gid, x: px, y: py };
  }
  return null;
});

// A capture's pixels kept in the page under `key` (window.__shots), so tests compare them there, not over the wire.
const keep = (page, key, opts = {}) => page.evaluate(async ([key, opts]) => {
  const c = await window.__dbg.postcard.capture(opts);
  (window.__shots ||= {})[key] = c.getContext('2d').getImageData(0, 0, c.width, c.height);
  return { width: c.width, height: c.height };
}, [key, opts]);
// The plain frame as the map draws it outside the postcard (tint, outline and all).
const keepPlain = (page, key) => page.evaluate(key => {
  const d = window.__dbg, src = d.renderer.domElement;
  d.renderer.render(d.scene, d.camera);
  const c = document.createElement('canvas');
  c.width = src.width; c.height = src.height;
  const ctx = c.getContext('2d');
  ctx.drawImage(src, 0, 0);
  (window.__shots ||= {})[key] = ctx.getImageData(0, 0, c.width, c.height);
}, key);
// The share of pixels of `a` and `b` (optionally in a box) whose RGB differ by more than 30 in all.
const changed = (page, a, b, box = null) => page.evaluate(([a, b, box]) => {
  const A = window.__shots[a], B = window.__shots[b], w = A.width;
  const [x0, y0, x1, y1] = box || [0, 0, w, A.height];
  let n = 0, all = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
    const i = (y * w + x) * 4;
    all++;
    if (Math.abs(A.data[i] - B.data[i]) + Math.abs(A.data[i + 1] - B.data[i + 1]) + Math.abs(A.data[i + 2] - B.data[i + 2]) > 30) n++;
  }
  return n / all;
}, [a, b, box]);

test('the button opens postcard mode and the page steps aside; Escape and Close put it back and give the focus back', async ({ page }) => {
  await open(page);
  const button = page.locator('.postcard-open'), bar = page.locator('.postcard-bar');
  await expect(button).toHaveAttribute('aria-label', 'Postcard');
  await expect(button).toHaveAttribute('aria-keyshortcuts', 'P');
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(bar).toBeVisible();
  expect(await isOn(page)).toBe(true);
  expect(await visibility(page, ASIDE)).toEqual(ASIDE.map(() => 'hidden'));
  await expect(page.locator('[data-filter="none"]')).toBeFocused();       // the bar has the keyboard
  await expect(page.locator('[data-filter="none"]')).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await expect(bar).toBeHidden();
  expect(await isOn(page)).toBe(false);
  expect(await visibility(page, ASIDE)).toEqual(ASIDE.map(() => 'visible'));
  await expect(button).toBeFocused();
  // P from the map, Close back to the map
  await page.locator('#scene').focus();
  await page.keyboard.press('p');
  await expect(bar).toBeVisible();
  await page.locator('.pc-close').click();
  await expect(bar).toBeHidden();
  await expect(page.locator('#scene')).toBeFocused();
  // P while typing in the search field types a p
  const input = page.getByRole('combobox');
  await input.focus();
  await page.keyboard.press('p');
  await expect(input).toHaveValue('p');
  expect(await isOn(page)).toBe(false);
  await input.fill('');
  // not over a history scene, which has the screen
  await page.evaluate(() => document.body.classList.add('scene-on'));
  await page.locator('#scene').focus();
  await page.keyboard.press('p');
  expect(await isOn(page)).toBe(false);
  await page.evaluate(() => document.body.classList.remove('scene-on'));
});

test('the map still moves while the postcard is open, and a click on it opens no card', async ({ page }) => {
  await open(page);
  await page.locator('.postcard-open').click();
  const before = await page.evaluate(() => window.__dbg.controls.target.toArray());
  await page.locator('#scene').focus();
  await page.keyboard.down('ArrowLeft');
  await page.waitForTimeout(400);
  await page.keyboard.up('ArrowLeft');
  const after = await page.evaluate(() => window.__dbg.controls.target.toArray());
  expect(Math.hypot(after[0] - before[0], after[2] - before[2])).toBeGreaterThan(5);
  const b = await buildingInView(page);
  test.skip(!b, 'no building in view');
  await page.mouse.click(b.x, b.y);
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.__dbg.pinned)).toBe(-1);
});

test('the shot leaves out the hover tint and the pinned building\'s tint and outline; Escape keeps the card pinned', async ({ page }) => {
  await open(page);
  const b = await buildingInView(page);
  test.skip(!b, 'no building in view');
  // pinned from search: the selection tint and the outline; the pointer on it: the hover tint
  await page.evaluate(gid => { window.__dbg.force(gid); window.__dbg.pinCard(gid, 120, innerHeight - 120); }, b.gid);
  await page.mouse.move(b.x, b.y);
  await expect.poll(() => page.evaluate(() => window.__dbg.uniforms.uHover.value)).toBe(b.gid);
  await expect.poll(() => page.evaluate(() => window.__dbg.highlight().visible)).toBe(true);
  await keepPlain(page, 'marked');
  // opened from the keyboard, so the pointer stays on the building (P would go to the pinned card, a dialog)
  await page.locator('.postcard-open').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.postcard-bar')).toBeVisible();
  await expect(page.locator('#card')).toHaveCSS('visibility', 'hidden');
  await keep(page, 'shot', { stamp: false });
  // Escape closes the postcard only: the card is still pinned, and shows again
  await page.keyboard.press('Escape');
  expect(await isOn(page)).toBe(false);
  expect(await page.evaluate(() => window.__dbg.pinned)).toBe(b.gid);
  await expect(page.locator('#card.pinned')).toBeVisible();
  // the same view with nothing marked
  await page.evaluate(() => window.__dbg.pinCard(-1));     // the card and the outline go
  await page.evaluate(() => { document.getElementById('scene').dispatchEvent(new PointerEvent('pointerleave')); });
  await expect.poll(() => page.evaluate(() => window.__dbg.uniforms.uHover.value)).toBe(-1);
  await keepPlain(page, 'clear');
  // around the building (device pixels), and over the whole picture
  const k = await page.evaluate(() => window.__dbg.renderer.getPixelRatio());
  const around = [b.x - 60, b.y - 60, b.x + 60, b.y + 60].map(v => Math.round(v * k));
  expect(await changed(page, 'marked', 'clear', around), 'the tint and the outline show on the map').toBeGreaterThan(0.02);
  expect(await changed(page, 'shot', 'clear', around), 'and not in the postcard').toBe(0);
  expect(await changed(page, 'shot', 'clear')).toBeLessThan(0.0001);
});

test('a building picked from search that the map\'s settings hide stays out of the shot', async ({ page }) => {
  await open(page);
  // a dated building in view, built after 1800, then the timeline at 1700: the map hides it
  const b = await page.evaluate(() => {
    const d = window.__dbg;
    for (const [x, y] of [[0.47, 0.47], [0.5, 0.5], [0.45, 0.55], [0.55, 0.45], [0.4, 0.5], [0.6, 0.5], [0.3, 0.6], [0.7, 0.4]]) {
      const px = Math.round(innerWidth * x), py = Math.round(innerHeight * y), gid = d.pick(px, py);
      if (gid < 0) continue;
      const { year, yflag } = d.building(gid);
      if (yflag !== 7 && year > 1800) return { gid, x: px, y: py };     // 7: "Year unknown"
    }
    return null;
  });
  test.skip(!b, 'no dated building after 1800 in view');
  await page.evaluate(() => { window.__dbg.uniforms.uYear.value = 1700; });
  await page.waitForTimeout(1000);                       // the buildings without a year sink out too
  expect(await page.evaluate(([x, y]) => window.__dbg.pick(x, y), [b.x, b.y])).not.toBe(b.gid);
  // picked from search: it stands whatever the timeline says, tinted and outlined, its card says why
  await page.evaluate(gid => { window.__dbg.force(gid); window.__dbg.pinCard(gid, 120, innerHeight - 120); }, b.gid);
  await expect.poll(() => page.evaluate(() => window.__dbg.highlight().visible)).toBe(true);
  await keepPlain(page, 'forced');
  await page.evaluate(() => window.__dbg.postcard.open());
  await expect(page.locator('#card')).toHaveCSS('visibility', 'hidden');
  await keep(page, 'shot', { stamp: false });
  expect(await page.evaluate(() => window.__dbg.forced)).toBe(b.gid);     // still picked: only the drawing leaves it out
  await page.evaluate(() => window.__dbg.postcard.exit());
  await page.evaluate(() => window.__dbg.pinCard(-1));                   // the pick is let go
  expect(await page.evaluate(() => window.__dbg.forced)).toBe(-1);
  await keepPlain(page, 'clear');
  const k = await page.evaluate(() => window.__dbg.renderer.getPixelRatio());
  const around = [b.x - 60, b.y - 60, b.x + 60, b.y + 60].map(v => Math.round(v * k));
  expect(await changed(page, 'forced', 'clear', around), 'the pick stands on the map').toBeGreaterThan(0.02);
  expect(await changed(page, 'shot', 'clear', around), 'and not in the postcard of 1700').toBe(0);
  expect(await changed(page, 'shot', 'clear')).toBeLessThan(0.0001);
});

test('the loading line steps aside with the rest; a failure\'s message stays', async ({ page }) => {
  await open(page);
  // as while the tiles still stream in: the postcard can open before the city is complete
  await page.evaluate(() => { document.getElementById('loading').hidden = false; });
  await page.keyboard.press('p');
  expect(await isOn(page)).toBe(true);
  await expect(page.locator('#loading')).toHaveCSS('visibility', 'hidden');
  // a failure (app.js loadFailed) says why the map is blank: it shows over the postcard too
  await page.evaluate(() => document.getElementById('loading').setAttribute('role', 'alert'));
  await expect(page.locator('#loading')).toHaveCSS('visibility', 'visible');
});

test('opening the postcard stops the growth film at the year on screen', async ({ page }) => {
  await open(page);
  await page.evaluate(() => window.__dbg.startPlay());
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => window.__dbg.uniforms.uPlaying.value)).toBe(1);
  await page.keyboard.press('p');
  expect(await isOn(page)).toBe(true);
  const year = await page.evaluate(() => window.__dbg.uniforms.uYear.value);
  expect(await page.evaluate(() => window.__dbg.uniforms.uPlaying.value)).toBe(0);
  await page.waitForTimeout(600);
  expect(await page.evaluate(() => window.__dbg.uniforms.uYear.value)).toBe(year);
  await page.keyboard.press('Escape');
  await expect(page.locator('#play')).toHaveAttribute('aria-label', "Play the city's growth");
});

test('a walk\'s route and discs stay out of the shot', async ({ page }) => {
  await open(page);
  test.skip(await page.locator('.walks-open').isHidden(), 'this build has no walks');
  await page.locator('.walks-open').click();
  await page.getByRole('button', { name: 'Make my walk' }).click();
  await expect(page.locator('#walk')).toBeVisible();
  await page.waitForTimeout(2000);                         // the camera settles on the route
  await keepPlain(page, 'walk');
  await keep(page, 'walkShot', { stamp: false });
  await page.locator('#walk .q-close').click();
  await expect(page.locator('#walk')).toBeHidden();
  await page.waitForTimeout(300);
  await keepPlain(page, 'noWalk');
  expect(await changed(page, 'walk', 'noWalk'), 'the route shows on the map').toBeGreaterThan(0.001);
  expect(await changed(page, 'walkShot', 'noWalk'), 'and not in the postcard').toBeLessThan(0.0001);
});

test('each filter shows its preview, and saves what it shows', async ({ page }) => {
  await open(page);
  await page.locator('.postcard-open').click();
  const preview = () => page.evaluate(() => ({
    filter: getComputedStyle(document.getElementById('scene')).filter,
    tilt: !document.querySelector('.pc-tilt').hidden,
    blur: [...document.querySelectorAll('.pc-tilt > i')].map(i => getComputedStyle(i).backdropFilter),
    vignette: !document.querySelector('.pc-vignette').hidden,
  }));
  let p = await preview();
  expect(p).toMatchObject({ filter: 'none', tilt: false, vignette: false });
  await page.locator('[data-filter="tilt"]').click();
  await expect(page.locator('[data-filter="tilt"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('[data-filter="none"]')).toHaveAttribute('aria-pressed', 'false');
  p = await preview();
  expect(p.filter).toMatch(/saturate/);
  expect(p.tilt).toBe(true);
  expect(p.blur).toHaveLength(2);
  for (const f of p.blur) expect(f).toMatch(/^blur\(\d/);
  expect(p.vignette).toBe(false);
  await page.locator('[data-filter="sepia"]').click();
  p = await preview();
  expect(p.filter).toMatch(/sepia/);
  expect(p).toMatchObject({ tilt: false, vignette: true });
  // Saved: sepia is brown (red over green over blue) nearly everywhere; tilt-shift is soft at the top and the bottom
  // and as sharp as the plain picture in its middle band.
  await keep(page, 'none', { filter: 'none', stamp: false });
  await keep(page, 'tilt', { filter: 'tilt', stamp: false });
  await keep(page, 'sepia', { filter: 'sepia', stamp: false });
  const measures = await page.evaluate(() => {
    const S = window.__shots, { width: w, height: h } = S.none;
    const brown = (() => {
      const d = S.sepia.data;
      let n = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i] + 2 >= d[i + 1] && d[i + 1] + 2 >= d[i + 2]) n++;
      return n / (d.length / 4);
    })();
    // the mean step between neighbouring pixels in a band of rows: how sharp it is
    const edges = (img, f0, f1) => {
      const d = img.data, y0 = Math.round(h * f0), y1 = Math.round(h * f1);
      let s = 0, n = 0;
      for (let y = y0; y < y1; y++) for (let x = 1; x < w; x++) {
        const i = (y * w + x) * 4;
        s += Math.abs(d[i] - d[i - 4]) + Math.abs(d[i + 1] - d[i - 3]) + Math.abs(d[i + 2] - d[i - 2]);
        n++;
      }
      return s / n;
    };
    const ratio = (f0, f1) => edges(S.tilt, f0, f1) / Math.max(1e-6, edges(S.none, f0, f1));
    return { brown, bottom: ratio(0.85, 0.97), middle: ratio(0.48, 0.56) };
  });
  expect(measures.brown).toBeGreaterThan(0.97);
  expect(measures.bottom).toBeLessThan(0.6);
  expect(measures.middle).toBeGreaterThan(0.85);
  await page.keyboard.press('Escape');
  expect((await preview()).filter).toBe('none');
  expect(await page.evaluate(() => document.querySelector('.pc-tilt').hidden && document.querySelector('.pc-vignette').hidden)).toBe(true);
});

test('Download saves husforhus-<date>.png: the map, not the sky alone, with the stamp in its corners', async ({ page }) => {
  await open(page);
  await page.locator('.postcard-open').click();
  const expected = await page.evaluate(() => {
    const d = new Date(), p = n => String(n).padStart(2, '0');
    return `husforhus-${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}.png`;
  });
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('.pc-save').click()]);
  expect(download.suggestedFilename()).toBe(expected);
  const bytes = readFileSync(await download.path());
  expect(bytes.length).toBeGreaterThan(100_000);
  expect([...bytes.subarray(0, 8)]).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);   // a PNG
  await expect(page.locator('.pc-save')).toHaveText('Done');
  await expect(page.locator('.pc-status')).toHaveText('Done');
  // the same frame without the stamp, then the saved file decoded beside it
  const size = await keep(page, 'bare', { stamp: false });
  const stamp = await page.evaluate(() => window.__dbg.postcard.stamp);
  expect(stamp).toBeNull();                                // the last capture had none
  await page.evaluate(async b64 => {
    const bin = atob(b64), u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    const bmp = await createImageBitmap(new Blob([u], { type: 'image/png' }));
    const c = document.createElement('canvas');
    c.width = bmp.width; c.height = bmp.height;
    const ctx = c.getContext('2d');
    ctx.drawImage(bmp, 0, 0);
    window.__shots.saved = ctx.getImageData(0, 0, c.width, c.height);
  }, bytes.toString('base64'));
  const saved = await page.evaluate(() => ({ width: window.__shots.saved.width, height: window.__shots.saved.height }));
  expect(saved).toEqual(size);
  // not all the sky: most of the picture differs from its top-left corner
  const notSky = await page.evaluate(() => {
    const d = window.__shots.saved.data, [r, g, b] = d;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - r) + Math.abs(d[i + 1] - g) + Math.abs(d[i + 2] - b) > 40) n++;
    return n / (d.length / 4);
  });
  expect(notSky).toBeGreaterThan(0.3);
  // the stamp: where the layout put the site and the credit, the saved picture differs from the bare one; elsewhere not
  await keep(page, 'stamped', { stamp: true });
  const L = await page.evaluate(() => window.__dbg.postcard.stamp);
  expect(L.width).toBe(size.width);
  expect(L.site.x + L.site.w).toBeGreaterThan(size.width * 0.8);            // bottom right
  expect(L.site.y + L.site.h).toBeGreaterThan(size.height * 0.9);
  expect(L.credit.x).toBeLessThan(size.width * 0.1);                         // bottom left
  expect(L.lines.join(' · ')).toContain('© OpenStreetMap contributors');
  const boxOf = r => [r.x, r.y, r.x + r.w, r.y + r.h];
  expect(await changed(page, 'saved', 'bare', boxOf(L.site))).toBeGreaterThan(0.2);
  expect(await changed(page, 'saved', 'bare', boxOf(L.credit))).toBeGreaterThan(0.2);
  expect(await changed(page, 'saved', 'bare', [0, 0, size.width, Math.round(size.height * 0.8)])).toBeLessThan(0.001);
});

test('the stamp is measured in the look\'s own font, even one that arrives only after Download', async ({ page }) => {
  // Blåtimme's Inter held back (a slow line): the page draws in the fallback meanwhile
  let release;
  const held = new Promise(r => { release = r; });
  await page.route('**/fonts/inter/**', async route => { await held; await route.continue(); });
  await page.goto('/?theme=blatimme', { waitUntil: 'domcontentloaded' });
  await settled(page);
  expect(await page.evaluate(() => document.fonts.check('700 17px "Inter"'))).toBe(false);
  await page.evaluate(() => { window.__capture = window.__dbg.postcard.capture({ filter: 'none' }); });
  await page.waitForTimeout(300);
  release();
  await page.evaluate(() => window.__capture.then(() => null));
  expect(await page.evaluate(() => document.fonts.check('700 17px "Inter"'))).toBe(true);
  // each pill as wide as its text in Inter, and its padding
  const fit = await page.evaluate(() => {
    const S = window.__dbg.postcard.stamp, ctx = document.createElement('canvas').getContext('2d');
    const m = (t, f) => { ctx.font = f; return Math.ceil(ctx.measureText(t).width); };
    const padX = Math.max(1, Math.round(S.base * 0.6));
    return { fonts: S.fonts, site: [S.site.w, m('husforhus.se', S.fonts.site) + 2 * padX],
      credit: [S.credit.w, Math.max(...S.lines.map(l => m(l, S.fonts.credit))) + 2 * padX] };
  });
  expect(fit.fonts.site).toContain('"Inter"');
  expect(fit.site[0], 'the site\'s pill').toBe(fit.site[1]);
  expect(fit.credit[0], 'the credit\'s pill').toBe(fit.credit[1]);
});

test('a save that fails says so in the bar, where it is seen; a filter puts the hint back', async ({ page }) => {
  await open(page);
  await page.locator('.postcard-open').click();
  const hint = page.locator('.pc-hint'), save = page.locator('.pc-save');
  const muted = await hint.evaluate(el => getComputedStyle(el).color);
  // the browser cannot make the PNG (a phone short of memory): toBlob gives null, once
  await page.evaluate(() => {
    const real = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function (cb) { HTMLCanvasElement.prototype.toBlob = real; cb(null); };
  });
  await save.click();
  await expect(hint).toHaveText('The picture could not be made. Try again.');
  await expect(hint).toBeVisible();
  expect(await hint.evaluate(el => getComputedStyle(el).color)).not.toBe(muted);   // the ink's colour, not the hint's
  await expect(page.locator('.pc-status')).toHaveText('The picture could not be made. Try again.');
  await expect(save).toHaveText('Download');
  await expect(save).not.toHaveAttribute('aria-busy');
  await page.locator('[data-filter="sepia"]').click();
  await expect(hint).toHaveText('Move the map to frame your picture.');
  expect(await hint.evaluate(el => getComputedStyle(el).color)).toBe(muted);
  // and the next save works
  const [download] = await Promise.all([page.waitForEvent('download'), save.click()]);
  expect(download.suggestedFilename()).toMatch(/^husforhus-\d{4}-\d{2}-\d{2}\.png$/);
  await expect(hint).toHaveText('Move the map to frame your picture.');
});

test('Tab in postcard mode goes round the bar and the map, each visibly focused; axe finds nothing serious', async ({ page }) => {
  await open(page);
  await page.locator('.postcard-open').click();
  const seen = new Set();
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab');
    const f = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;            // past the last control, the browser's own turn
      const s = getComputedStyle(el);
      return { key: el.dataset.filter || el.className || el.id, ring: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0,
        inBar: !!el.closest('.postcard-bar') || el.id === 'scene' };
    });
    if (!f) continue;
    expect(f.inBar, f.key).toBe(true);
    expect(f.ring, f.key).toBe(true);
    seen.add(f.key);
  }
  for (const k of ['none', 'tilt', 'sepia', 'pc-save', 'pc-close', 'scene']) expect([...seen]).toContain(k);
  const serious = (await new AxeBuilder({ page }).analyze()).violations
    .filter(v => v.impact === 'serious' || v.impact === 'critical').map(v => `${v.id}: ${v.nodes.map(n => n.target).join(', ')}`);
  expect(serious).toEqual([]);
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('the bar fits the screen, takes taps in 44 px and speaks Swedish', async ({ page }) => {
    await open(page, '?lang=sv');
    if (await page.locator('html').getAttribute('lang') !== 'sv') await page.locator('.lang [data-lang="sv"]').click();
    const button = page.locator('.postcard-open');
    await expect(button).toHaveAttribute('aria-label', 'Vykort');
    await button.tap();
    const bar = page.locator('.postcard-bar');
    await expect(bar).toBeVisible();
    await expect(bar).toHaveAttribute('aria-label', 'Vykort');
    await expect(page.locator('.pc-hint')).toHaveText('Flytta kartan för att rama in bilden.');
    await expect(page.locator('.pc-filters')).toHaveAttribute('aria-label', 'Bildfilter');
    await expect(page.locator('[data-filter]')).toHaveText(['Inget', 'Miniatyr', 'Sepiaton']);   // inget filter
    await expect(page.locator('.pc-save')).toHaveText('Ladda ner');
    await expect(page.locator('.pc-close')).toHaveAttribute('aria-label', 'Stäng');
    const box = await bar.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.y).toBeGreaterThan(844 / 2);
    expect(box.y + box.height).toBeLessThanOrEqual(844);
    for (const b of await page.locator('.postcard-bar button:not([hidden])').evaluateAll(els => els.map(el => {
      const r = el.getBoundingClientRect();
      return { name: el.textContent || el.getAttribute('aria-label'), w: r.width, h: r.height, left: r.left, right: r.right };
    }))) {
      expect(b.h, b.name).toBeGreaterThanOrEqual(44);
      expect(b.w, b.name).toBeGreaterThanOrEqual(44);
      expect(b.left >= 0 && b.right <= 390, b.name).toBe(true);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    const serious = (await new AxeBuilder({ page }).analyze()).violations
      .filter(v => v.impact === 'serious' || v.impact === 'critical').map(v => `${v.id}: ${v.nodes.map(n => n.target).join(', ')}`);
    expect(serious).toEqual([]);
    await page.locator('.pc-close').tap();
    await expect(bar).toBeHidden();
    await expect(page.locator('.corner')).toHaveCSS('visibility', 'visible');
  });

  test('a phone shares the picture; refused (iOS, too long after the tap), "Share image" shares the ready file', async ({ page }) => {
    await page.addInitScript(() => {
      window.__shares = [];
      Object.defineProperty(navigator, 'canShare', { configurable: true, value: d => !!d?.files?.length });
      Object.defineProperty(navigator, 'share', { configurable: true, value: async d => {
        window.__shares.push(d.files.map(f => ({ name: f.name, type: f.type, size: f.size })));
        if (window.__shares.length === 1) throw new DOMException('Too late after the tap', 'NotAllowedError');
      } });
    });
    await open(page);
    await page.locator('.postcard-open').tap();
    await page.locator('.pc-save').tap();
    const share = page.locator('.pc-share');
    await expect(share).toBeVisible();
    await expect(share).toHaveText('Share image');
    await expect(share).toBeFocused();
    await share.tap();
    await expect(share).toBeHidden();
    await expect(page.locator('.pc-save')).toHaveText('Done');
    const shares = await page.evaluate(() => window.__shares);
    expect(shares).toHaveLength(2);
    for (const files of shares) {
      expect(files).toHaveLength(1);
      expect(files[0].name).toMatch(/^husforhus-\d{4}-\d{2}-\d{2}\.png$/);
      expect(files[0].type).toBe('image/png');
      expect(files[0].size).toBeGreaterThan(50_000);
    }
  });

  // A share sheet that refuses while window.__refuse is set (iOS, too long after the tap), the files it was given, the
  // downloads (an <a download> clicked), and a PNG that takes window.__slow ms (a big picture on a slow phone).
  const phoneStubs = page => page.addInitScript(() => {
    window.__files = []; window.__downloads = []; window.__refuse = true; window.__slow = 0;
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: d => !!d?.files?.length });
    Object.defineProperty(navigator, 'share', { configurable: true, value: async d => {
      window.__files.push(d.files[0]);
      if (window.__refuse) throw new DOMException('Too late after the tap', 'NotAllowedError');
    } });
    const click = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () { if (this.download) window.__downloads.push(this.download); else click.call(this); };
    const toBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function (cb, ...rest) { toBlob.call(this, b => setTimeout(() => cb(b), window.__slow), ...rest); };
  });

  test('"Share image" holds only the newest picture of what the screen shows: a filter, a move or a new Download replace it', async ({ page }) => {
    await phoneStubs(page);
    await open(page);
    const share = page.locator('.pc-share'), save = page.locator('.pc-save');
    await page.locator('.postcard-open').tap();
    await page.locator('[data-filter="tilt"]').tap();
    await save.tap();
    await expect(share).toBeVisible();                       // refused: the tilt-shift picture waits
    await page.locator('[data-filter="sepia"]').tap();
    await expect(share).toBeHidden();                        // the screen shows sepia now
    await save.tap();
    await expect(share).toBeVisible();                       // refused again: the sepia picture waits, not a download
    await expect(share).toBeFocused();
    expect(await page.evaluate(() => window.__downloads)).toEqual([]);
    await page.evaluate(() => { window.__refuse = false; });
    await share.tap();
    await expect(share).toBeHidden();
    await expect(save).toHaveText('Done');
    // three shares: tilt-shift, sepia, and the button's, which was the sepia file
    expect(await page.evaluate(() => { const f = window.__files; return [f.length, f[2] === f[1], f[2] === f[0]]; })).toEqual([3, true, false]);
    // a key that moves the map, then a touch on it
    await page.evaluate(() => { window.__refuse = true; });
    await save.tap();
    await expect(share).toBeVisible();
    await page.keyboard.press('ArrowLeft');
    await expect(share).toBeHidden();
    await expect(save).toBeFocused();                        // the focus was on the button that went
    await save.tap();
    await expect(share).toBeVisible();
    await page.touchscreen.tap(195, 300);
    await expect(share).toBeHidden();
    expect(await page.evaluate(() => window.__downloads)).toEqual([]);
  });

  test('a save still being made when the postcard closes is dropped: nothing shared, no "Share image" when it opens again', async ({ page }) => {
    await phoneStubs(page);
    await open(page);
    const share = page.locator('.pc-share'), save = page.locator('.pc-save'), bar = page.locator('.postcard-bar');
    await page.evaluate(() => { window.__slow = 1500; });
    // closed while it is made, and opened again only after it is done
    await page.locator('.postcard-open').tap();
    await save.tap();
    await expect(save).toHaveText('Preparing…');
    await page.locator('.pc-close').tap();                   // Close still works during "Preparing…"
    await expect(bar).toBeHidden();
    await expect(save).toHaveText('Download', { timeout: 10_000 });
    await page.locator('.postcard-open').tap();
    await expect(bar).toBeVisible();
    await expect(share).toBeHidden();
    await expect(page.locator('.pc-status')).toHaveText('');
    // closed and opened again while it is still made
    await save.tap();
    await expect(save).toHaveText('Preparing…');
    await page.keyboard.press('Escape');
    await expect(bar).toBeHidden();
    await page.locator('.postcard-open').tap();
    await expect(save).toHaveText('Preparing…');                // it is still running: Download waits for it
    await expect(save).toHaveText('Download', { timeout: 10_000 });
    await expect(share).toBeHidden();
    expect(await page.evaluate(() => [window.__files.length, window.__downloads.length])).toEqual([0, 0]);
    // a save made with the postcard open still offers its picture
    await page.evaluate(() => { window.__slow = 0; });
    await save.tap();
    await expect(share).toBeVisible();
    expect(await page.evaluate(() => window.__files.length)).toBe(1);
  });
});

test.describe('on a phone held sideways', () => {
  test.use({ viewport: { width: 667, height: 375 }, isMobile: true, hasTouch: true });

  test('the bar keeps to one centred row, "Share image" too, and takes taps in 44 px', async ({ page }) => {
    await open(page, '?lang=sv');                            // the longer labels
    if (await page.locator('html').getAttribute('lang') !== 'sv') await page.locator('.lang [data-lang="sv"]').click();
    await page.locator('.postcard-open').tap();
    const bar = page.locator('.postcard-bar');
    await expect(bar).toBeVisible();
    await page.evaluate(() => { document.querySelector('.pc-share').hidden = false; });   // as after a refused share
    const box = await bar.boundingBox();
    expect(box.height, 'the hint and one row of 44 px').toBeLessThan(100);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(667);
    expect(Math.abs(box.x + box.width / 2 - 667 / 2)).toBeLessThanOrEqual(1);
    const buttons = await page.locator('.postcard-bar button:not([hidden])').evaluateAll(els => els.map(el => {
      const r = el.getBoundingClientRect();
      return { name: el.textContent || el.getAttribute('aria-label'), top: r.top, w: r.width, h: r.height };
    }));
    expect(buttons).toHaveLength(6);
    for (const b of buttons) {
      expect(b.h, b.name).toBeGreaterThanOrEqual(44);
      expect(b.w, b.name).toBeGreaterThanOrEqual(44);
      expect(Math.abs(b.top - buttons[0].top), b.name).toBeLessThan(1);
    }
  });
});
