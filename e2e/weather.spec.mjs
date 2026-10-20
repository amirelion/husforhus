// The weather (web/weather.js) in the Look panel's Weather row: Clear, Snow, Rain and Fog switch in place with their
// pressed state, the sky really changes, the choice is remembered and a ?weather= link wins over it (Clear takes the
// parameter out), a page opens in its weather at once, the row speaks Swedish, the masthead's muted lines keep 4.5:1 in
// every weather, the pick pass draws nothing new (a building under falling snow still picks as itself), the quest's red
// building keeps its roof bare under the pointer, one long frame does not halve the flakes, reduced motion lets snow
// lie but nothing fall, and the snow costs one draw call. Runs on whatever web/data/current.json names (the fixture in
// CI, the whole city on a laptop).
import { test, expect } from '@playwright/test';
import { settled } from './settled.mjs';
import { THEMES } from '../web/themes.js';
import { weatherSky, WEATHER, FLAKES } from '../web/weather.js';

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}
const weather = page => page.evaluate(() => window.__dbg.weather);
// The colours the map is drawn with: the WebGL clear colour (the sky) and the fog's colour, as hex.
const skies = page => page.evaluate(() => {
  const D = window.__dbg, c = { copy(v) { Object.assign(this, { r: v.r, g: v.g, b: v.b }); return this; } };
  D.renderer.getClearColor(c);
  const hex = v => Math.round(v * 255).toString(16).padStart(2, '0');
  return { clear: `#${hex(c.r)}${hex(c.g)}${hex(c.b)}`, fog: `#${D.uniforms.uFogColor.value.getHexString()}` };
});
const stored = page => page.evaluate(() => localStorage.getItem('hfh-weather'));
const param = page => new URL(page.url()).searchParams.get('weather');
// The mean colour of a screenshot (PNG bytes), decoded in the page.
const meanOf = (page, png) => page.evaluate(async src => {
  const i = await new Promise(r => { const im = new Image(); im.onload = () => r(im); im.src = src; });
  const c = document.createElement('canvas'); c.width = i.width; c.height = i.height;
  const x = c.getContext('2d'); x.drawImage(i, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height).data, m = [0, 0, 0];
  for (let k = 0; k < d.length; k += 4) for (let j = 0; j < 3; j++) m[j] += d[k + j];
  return m.map(v => v / (d.length / 4));
}, `data:image/png;base64,${png.toString('base64')}`);
const frames = (page, n = 2) => page.evaluate(n => new Promise(done => {
  const step = k => (k ? requestAnimationFrame(() => step(k - 1)) : done());
  step(n);
}), n);
// The weather as the page first has it: caught as app.js sets window.__dbg, in the same run that restores the weather,
// before any frame could ease it in. A page that eased in from Clear would show 0 there.
const catchStart = page => page.addInitScript(() => {
  Object.defineProperty(window, '__dbg', { configurable: true, get: () => undefined, set(v) {
    Object.defineProperty(window, '__dbg', { value: v, writable: true, configurable: true, enumerable: true });
    window.__weatherAtStart = v.weather;
  } });
});
const atStart = page => page.evaluate(() => window.__weatherAtStart);
// The veils over the top and bottom of the map, hidden so a strip of the map's own sky can be read.
const veils = (page, shown) => page.evaluate(v => document.querySelectorAll('.veil').forEach(e => {
  e.style.visibility = v;
}), shown ? '' : 'hidden');

test('the Look panel switches the weather in place, the sky changes, and the choice is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await settled(page);
  expect(await weather(page)).toMatchObject({ kind: 'none', snow: 0, wet: 0, particles: 0, falling: null });
  expect(await skies(page)).toEqual({ clear: THEMES.arg.sky, fog: THEMES.arg.sky });
  // a strip of sky above the far shore of the home view, the veils hidden: in a weather the top one reaches past it
  const strip = { x: 560, y: 141, width: 240, height: 8 };
  await veils(page, false);
  const clearSky = await meanOf(page, await page.screenshot({ clip: strip }));
  await veils(page, true);

  const button = page.locator('.look-open'), panel = page.locator('#look');
  await button.click();
  await expect(panel.locator('#atmos-title')).toHaveText('Weather');
  const row = panel.locator('.look-atmos button');
  await expect(row).toHaveText(['Clear', 'Snow', 'Rain', 'Fog']);
  const pressed = async id => {
    for (const k of ['none', 'snow', 'rain', 'fog']) {
      await expect(panel.locator(`[data-atmos="${k}"]`)).toHaveAttribute('aria-pressed', String(k === id));
    }
  };
  await pressed('none');

  // Snow: it eases in, flakes fall, the sky goes to the winter blue-grey, and the address and the store say so.
  await panel.locator('[data-atmos="snow"]').click();
  await pressed('snow');
  await expect(panel).toBeVisible();   // the panel stays open, as for the looks
  await expect.poll(async () => (await weather(page)).snow, { timeout: 5_000 }).toBe(1);
  const snow = await weather(page);
  expect(snow.falling).toBe('snow');
  expect(snow.particles === FLAKES.desktop || snow.particles === FLAKES.desktop / 2, `${snow.particles} flakes`).toBe(true);
  expect(await skies(page)).toEqual({ clear: weatherSky(THEMES.arg.sky, 'snow'), fog: weatherSky(THEMES.arg.sky, 'snow') });
  expect(param(page)).toBe('snow');
  expect(await stored(page)).toBe('snow');
  expect(await page.evaluate(() => window.__dbg.uniforms.uSnow.value)).toBe(1);

  // Rain, by the keyboard: the arrows move along the row, Enter picks.
  await panel.locator('[data-atmos="snow"]').focus();
  await page.keyboard.press('ArrowRight');
  await expect(panel.locator('[data-atmos="rain"]')).toBeFocused();
  await page.keyboard.press('Enter');
  await pressed('rain');
  await expect.poll(async () => { const w = await weather(page); return [w.wet, w.snow, w.falling]; }, { timeout: 5_000 })
    .toEqual([1, 0, 'rain']);
  expect(param(page)).toBe('rain');

  // Fog: nothing falls, the fog comes in to just past the target, and the sky on screen is a softer grey.
  await panel.locator('[data-atmos="fog"]').click();
  await pressed('fog');
  await expect.poll(async () => (await weather(page)).fog, { timeout: 5_000 }).toEqual(WEATHER.fog.fog);
  expect(await weather(page)).toMatchObject({ kind: 'fog', particles: 0, falling: null });
  expect((await skies(page)).clear).toBe(weatherSky(THEMES.arg.sky, 'fog'));
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  await veils(page, false);
  await frames(page);
  const fogSky = await meanOf(page, await page.screenshot({ clip: strip }));
  await veils(page, true);
  const diff = clearSky.reduce((s, v, j) => s + Math.abs(v - fogSky[j]), 0);
  expect(diff, `sky ${clearSky.map(Math.round)} to ${fogSky.map(Math.round)}`).toBeGreaterThan(25);

  // Remembered: a reload (no parameter) opens in fog, at once.
  await catchStart(page);
  await page.goto('/');
  await page.waitForFunction(() => window.__dbg);
  expect(await atStart(page)).toMatchObject({ kind: 'fog', fog: WEATHER.fog.fog });
  await settled(page);
  expect(await weather(page)).toMatchObject({ kind: 'fog', fog: WEATHER.fog.fog });
  await button.click();
  await pressed('fog');
  // Clear takes the weather away, the parameter out of the address, and is remembered too.
  await panel.locator('[data-atmos="none"]').click();
  await pressed('none');
  await expect.poll(async () => (await weather(page)).fog, { timeout: 5_000 }).toEqual(WEATHER.none.fog);
  expect(await skies(page)).toEqual({ clear: THEMES.arg.sky, fog: THEMES.arg.sky });
  expect(param(page)).toBeNull();
  expect(await stored(page)).toBe('none');
  // A look switch keeps the weather and re-keys it to the new look's sky.
  await panel.locator('[data-atmos="snow"]').click();
  await panel.locator('.look-card[data-look="kalk"]').click();
  await expect.poll(async () => (await skies(page)).clear, { timeout: 5_000 }).toBe(weatherSky(THEMES.kalk.sky, 'snow'));
  expect(new URL(page.url()).searchParams.get('theme')).toBe('kalk');
  expect(param(page)).toBe('snow');
  expect(errors).toEqual([]);
});

test('a ?weather= link wins over the remembered weather, and Clear takes it out of the address', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await page.evaluate(() => localStorage.setItem('hfh-weather', 'snow'));
  await catchStart(page);
  await page.goto('/?weather=rain&theme=paper');
  await page.waitForFunction(() => window.__dbg);
  expect(await atStart(page)).toMatchObject({ kind: 'rain', wet: 1, snow: 0 });   // there at once, not eased in
  await settled(page);
  expect(await weather(page)).toMatchObject({ kind: 'rain', wet: 1 });
  expect((await skies(page)).clear).toBe(weatherSky(THEMES.paper.sky, 'rain'));
  expect(await stored(page)).toBe('snow');   // the link shows the sender's weather; it does not change the reader's
  await page.locator('.look-open').click();
  await expect(page.locator('#look [data-atmos="rain"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#look [data-atmos="none"]').click();
  await expect(page.locator('#look [data-atmos="none"]')).toHaveAttribute('aria-pressed', 'true');
  expect(param(page)).toBeNull();
  expect(new URL(page.url()).searchParams.get('theme')).toBe('paper');   // the other parameters stay
  expect(await stored(page)).toBe('none');
  // an unknown kind in a link is ignored
  await page.goto('/?weather=hail');
  await settled(page);
  expect((await weather(page)).kind).toBe('none');
  expect(errors).toEqual([]);
});

test('the Weather row speaks Swedish', async ({ page }) => {
  await page.goto('/?lang=sv');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await page.locator('.look-open').click();
  await expect(page.locator('#look #atmos-title')).toHaveText('Väder');
  await expect(page.locator('#look .look-atmos button')).toHaveText(['Klart', 'Snö', 'Regn', 'Dimma']);
  // and switches language in place
  await page.keyboard.press('Escape');
  await page.locator('.lang [data-lang="en"]').click();
  await page.locator('.look-open').click();
  await expect(page.locator('#look .look-atmos button')).toHaveText(['Clear', 'Snow', 'Rain', 'Fog']);
});

// A weather's sky is darker than the look's own background, and its flakes fall behind the masthead: the top veil
// (styles.css) is solid behind the subtitle and the count in a weather, so their muted ink keeps 4.5:1 in every look.
// Every pixel behind each line is read with the masthead and the tally hidden, against the look's --muted; the count
// once more under the longest period name, which puts it on two lines lower down.
const lin = v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const luminance = hex => {
  const c = [1, 3, 5].map(i => lin(parseInt(hex.slice(i, i + 2), 16) / 255));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const worstBehind = (page, png, ink) => page.evaluate(async ([src, Y]) => {
  const i = await new Promise(r => { const im = new Image(); im.onload = () => r(im); im.src = src; });
  const c = document.createElement('canvas'); c.width = i.width; c.height = i.height;
  const x = c.getContext('2d'); x.drawImage(i, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height).data;
  const lin = v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);   // the page has no module scope of ours
  let worst = Infinity, at = null;
  for (let k = 0; k < d.length; k += 4) {
    const L = 0.2126 * lin(d[k] / 255) + 0.7152 * lin(d[k + 1] / 255) + 0.0722 * lin(d[k + 2] / 255);
    const ratio = (Math.max(L, Y) + 0.05) / (Math.min(L, Y) + 0.05);
    if (ratio < worst) { worst = ratio; at = [d[k], d[k + 1], d[k + 2]]; }
  }
  return { worst, at };
}, [`data:image/png;base64,${png.toString('base64')}`, luminance(ink)]);
const textHidden = (page, hidden) => page.evaluate(v => document.querySelectorAll('.masthead, .tally').forEach(e => {
  e.style.visibility = v;
}), hidden ? 'hidden' : '');
const boxOf = (page, sel) => page.evaluate(s => {
  const b = document.querySelector(s).getBoundingClientRect();
  return { x: Math.floor(b.left), y: Math.floor(b.top), width: Math.ceil(b.width), height: Math.ceil(b.height) };
}, sel);

test('the subtitle and the count keep 4.5:1 over every weather, in every look', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await settled(page);
  const panel = page.locator('#look');
  await page.locator('.look-open').click();
  const lines = { subtitle: await boxOf(page, '.dek'), count: await boxOf(page, '.tally-count') };
  const read = async (look, box) => {
    await textHidden(page, true);
    const r = await worstBehind(page, await page.screenshot({ clip: box }), THEMES[look].ui['--muted']);
    await textHidden(page, false);
    return r;
  };
  const full = { snow: w => w.snow === 1 && w.falling === 'snow', rain: w => w.wet === 1 && w.falling === 'rain',
    fog: w => w.fog[0] === WEATHER.fog.fog[0] && w.falling === null };
  // Ärg in the rain last: the darkest sky behind the default look's lightest muted ink
  for (const look of ['blatimme', 'kalk', 'paper', 'arg']) {
    await panel.locator(`.look-card[data-look="${look}"]`).click();
    for (const kind of ['snow', 'fog', 'rain']) {
      await panel.locator(`[data-atmos="${kind}"]`).click();
      await expect.poll(async () => full[kind](await weather(page)), { timeout: 5_000 }).toBe(true);
      await frames(page);
      for (const [name, box] of Object.entries(lines)) {
        const { worst, at } = await read(look, box);
        expect(worst, `${look}, ${kind}: the ${name} on rgb(${at}): ${worst.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
      }
    }
  }
  // the count under the longest period name (a period shown alone names it in the tally)
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  const longest = await page.evaluate(() => [...document.querySelectorAll('.swatch[data-i]')]
    .sort((a, b) => b.getAttribute('aria-label').length - a.getAttribute('aria-label').length)[0].dataset.i);
  await page.locator(`.swatch[data-i="${longest}"]`).click();
  await expect(page.locator('#year')).toHaveClass(/named/);
  const low = await boxOf(page, '.tally-count');
  expect(low.y).toBeGreaterThan(lines.count.y);
  const { worst, at } = await read('arg', low);
  expect(worst, `arg, rain: the count under a period's name on rgb(${at}): ${worst.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
  expect(errors).toEqual([]);
});

// Nothing new in the pick pass: the falling snow is hidden while the 1x1 pick renders (as the metro and the names are),
// so a building under it still picks as itself.
test('with snow falling, the pick pass draws no flakes and a building still picks as itself', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/?weather=snow');
  await settled(page);
  expect((await weather(page)).particles).toBeGreaterThan(0);
  const result = await page.evaluate(async () => {
    const D = window.__dbg, cam = D.camera, ctl = D.controls;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const flakes = D.scene.getObjectByName('weather');
    // what the pick pass sees: the flakes' group as the pixel is read back
    const seen = [];
    const read = D.renderer.readRenderTargetPixels.bind(D.renderer);
    D.renderer.readRenderTargetPixels = (...a) => { seen.push(flakes.visible); return read(...a); };
    // a building seen from straight above, 300 m up, at the middle of the screen
    let g = 0;
    while (D.building(g).height < 10) g++;
    const b = D.building(g), y = D.surfaceAt(b.x, b.z);
    ctl.target.set(b.x, y, b.z);
    cam.position.set(b.x, y + 300, b.z + 1);
    ctl.update();
    await frame();
    const v = cam.position.clone().set(b.x, y + b.height, b.z).project(cam);
    const at = [(v.x + 1) / 2 * innerWidth, (1 - v.y) / 2 * innerHeight];
    const picks = [];
    for (let k = 0; k < 5; k++) { picks.push(D.pick(...at)); await frame(); }
    D.renderer.readRenderTargetPixels = read;
    return { g, picks, seen, after: flakes.visible, particles: D.weather.particles };
  });
  expect(result.picks).toEqual(Array(5).fill(result.g));
  expect(result.seen.length).toBeGreaterThanOrEqual(5);
  expect(result.seen.every(v => v === false), 'the flakes are hidden in every pick pass').toBe(true);
  expect(result.after).toBe(true);
  expect(result.particles).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});

// A quest's question turns its building red (app.js VERT) and keeps the snow off its roof, under the pointer too: the
// hover's mark comes before the quest's in the shader, so the pointer over it cannot bring the snow back. Read from
// straight above with reduced motion (snow lies, nothing falls in front), the hover and the question set as the loop and
// the quest set them, and the mouse kept off the map so the loop leaves them.
test('in the snow, the quest\'s red building keeps its red roof under the pointer', async ({ page }) => {
  const errors = watchErrors(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?weather=snow');
  await settled(page);
  await expect.poll(() => page.evaluate(() => { const s = window.__dbg.stats(); return s.tiles === s.tilesTotal; }),
    { timeout: 60_000 }).toBe(true);   // the building's own tile among them
  expect(await weather(page)).toMatchObject({ kind: 'snow', snow: 1 });
  const g = await page.evaluate(() => {
    const D = window.__dbg, cam = D.camera, ctl = D.controls;
    let g = 0;
    while (D.building(g).height < 10) g++;
    const b = D.building(g), y = D.surfaceAt(b.x, b.z) + b.height;
    ctl.target.set(b.x, y, b.z);
    cam.position.set(b.x, y + 150, b.z + 1);
    ctl.update();
    return g;
  });
  // a spot on its roof near the middle of the screen, once the building is drawn there (a building's centre may lie in
  // its courtyard): one whose corners all pick as the building
  let roof = null;
  await expect.poll(async () => (roof = await page.evaluate(g => {
    const D = window.__dbg;
    const on = (x, y) => [[-3, -3], [3, -3], [-3, 3], [3, 3], [0, 0]].every(([dx, dy]) => D.pick(x + dx, y + dy) === g);
    const [cx, cy] = [Math.round(innerWidth / 2), Math.round(innerHeight / 2)];
    if (on(cx, cy)) return { x: cx, y: cy };
    for (let r = 12; r <= 120; r += 12) for (let a = 0; a < 16; a++) {
      const x = Math.round(cx + r * Math.cos(a * Math.PI / 8)), y = Math.round(cy + r * Math.sin(a * Math.PI / 8));
      if (on(x, y)) return { x, y };
    }
    return null;
  }, g)), { timeout: 15_000, message: 'a spot on the roof' }).not.toBeNull();
  roof.g = g;
  const colour = async (selected, blind) => {
    await page.evaluate(([g, sel, blind]) => {
      const u = window.__dbg.uniforms;
      u.uHover.value = g; u.uSelected.value = sel; u.uBlind.value = blind;
    }, [roof.g, selected, blind]);
    await frames(page, 3);
    return (await meanOf(page, await page.screenshot({ clip: { x: roof.x - 3, y: roof.y - 3, width: 6, height: 6 } })))
      .map(Math.round);
  };
  // hovered outside a quest, the roof takes the snow in the hover's tint
  const hovered = await colour(-1, 0);
  expect(hovered[1], `hovered: rgb(${hovered})`).toBeGreaterThan(40);
  // the quest's red building under the pointer: red, no snow on it (FRAG mixes towards a pale grey, lifting green)
  const red = await colour(roof.g, 2);
  expect(red[0], `quest: rgb(${red})`).toBeGreaterThan(110);
  expect(Math.max(red[1], red[2]), `quest: rgb(${red})`).toBeLessThan(25);
  await page.evaluate(() => {
    const u = window.__dbg.uniforms;
    u.uHover.value = -1; u.uSelected.value = -1; u.uBlind.value = 0;
  });
  expect(errors).toEqual([]);
});

// Browsers pause the frames of a tab in the background, so the first frame back is as long as the visitor was away; a
// long task does the same. That is not a slow frame rate: the flakes stay as many (web/weather.js frameRate). A machine
// that draws the snow slowly anyway (a CPU renderer in CI) says nothing here, so the test stands aside there.
test('one long frame, as when a tab comes back from the background, does not halve the flakes', async ({ page }) => {
  await page.goto('/?weather=snow');
  await settled(page);
  await page.evaluate(() => new Promise(r => setTimeout(r, 2500)));   // flakes have fallen past the old two-second grace
  const before = await page.evaluate(() => ({ ...window.__dbg.weather, fps: window.__dbg.stats().fps }));
  test.skip(before.slow || before.fps < 50, `this browser draws the snow at ${before.fps} fps`);
  expect(before.particles).toBe(FLAKES.desktop);
  await page.evaluate(() => { const t = performance.now(); while (performance.now() - t < 2500); });
  await frames(page, 2);
  // the plain mean of the last 60 frames (what the flakes went by before) is under 30 now
  expect(await page.evaluate(() => window.__dbg.stats().fps)).toBeLessThan(30);
  await frames(page, 240);
  expect(await weather(page)).toMatchObject({ slow: false, particles: FLAKES.desktop });
});

test('snow costs one draw call: under 300 at home and from 20 km', async ({ page }) => {
  await page.goto('/?debug=1&weather=snow');
  await settled(page);
  await expect.poll(() => page.evaluate(() => { const s = window.__dbg.stats(); return s.tiles === s.tilesTotal; }),
    { timeout: 60_000 }).toBe(true);
  await page.evaluate(() => window.__dbg.pauseEffects(true));
  await frames(page, 4);
  const snowHome = await page.evaluate(() => window.__dbg.stats().calls);
  await page.evaluate(() => window.__dbg.viewAt(20000));
  await frames(page, 6);
  const snowFar = await page.evaluate(() => window.__dbg.stats().calls);
  expect(snowHome).toBeLessThan(300);
  expect(snowFar).toBeLessThan(300);
  // the same views in Clear: one call fewer
  await page.locator('.look-open').click();
  await page.locator('#look [data-atmos="none"]').click();
  await expect.poll(async () => (await weather(page)).particles, { timeout: 5_000 }).toBe(0);
  await frames(page, 6);
  const clearFar = await page.evaluate(() => window.__dbg.stats().calls);
  await page.evaluate(() => window.__dbg.goHome());
  await frames(page, 6);
  const clearHome = await page.evaluate(() => window.__dbg.stats().calls);
  expect(snowHome - clearHome).toBeLessThanOrEqual(1);
  expect(snowFar - clearFar).toBeLessThanOrEqual(1);
});

test.describe('with reduced motion', () => {
  test('snow lies on the roofs and the sky turns, but nothing falls and the water stands still', async ({ page }) => {
    const errors = watchErrors(page);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/?weather=snow');
    await settled(page);
    await frames(page, 4);
    const w = await weather(page);
    expect(w).toMatchObject({ kind: 'snow', snow: 1, particles: 0, falling: null });
    expect(await page.evaluate(() => window.__dbg.scene.getObjectByName('weather-flakes').visible)).toBe(false);
    expect((await skies(page)).clear).toBe(weatherSky(THEMES.arg.sky, 'snow'));
    const wave = await page.evaluate(() => window.__dbg.uniforms.uWave.value);
    await frames(page, 10);
    expect(await page.evaluate(() => window.__dbg.uniforms.uWave.value)).toBe(wave);
    // a switch is at once: rain is there on the next frame, and it does not fall either
    await page.locator('.look-open').click();
    await page.locator('#look [data-atmos="rain"]').click();
    await frames(page, 2);
    expect(await weather(page)).toMatchObject({ kind: 'rain', wet: 1, snow: 0, particles: 0 });
    expect(errors).toEqual([]);
  });
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  test('fewer flakes fall', async ({ page }) => {
    await page.goto('/?weather=snow');
    await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
    await expect.poll(async () => (await weather(page)).particles, { timeout: 10_000 }).toBeGreaterThan(0);
    const n = (await weather(page)).particles;
    expect(n === FLAKES.phone || n === FLAKES.phone / 2, `${n} flakes`).toBe(true);
  });
});
