// Smoke test for the viewer. It runs on whatever web/data/current.json points at: the
// Gamla stan + Riddarholmen fixture in CI (HFH_FIXTURE=1), the whole city on a laptop.
import { test, expect } from '@playwright/test';
import { THEMES } from '../web/themes.js';

// Page errors, console errors and HTTP responses >= 400, as lines. `expected` names the failures a test causes
// on purpose, so only the others are collected.
function watchErrors(page, expected = () => false) {
  const errors = [];
  const add = e => { if (!expected(e)) errors.push(e); };
  page.on('pageerror', e => add(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') add(`console: ${m.text()} (${m.location().url})`); });
  page.on('response', r => { if (r.status() >= 400) add(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}

// The config the page loaded: the version current.json names.
const cityConfig = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  return (await fetch(`data/${version}/stockholm.json`)).json();
});
// The terrain arrives after the first frame and rises over 1.2 s (two textures, and every building lifted).
// A test that counts textures or aims at a building waits for it to stand; a build without terrain does not wait. A
// terrain that failed is final: the wait ends there and fails at once, not after 60 s.
const terrainSettled = async page => {
  if (!(await cityConfig(page)).terrain) return;
  const stands = () => page.evaluate(() => {
    const t = window.__dbg.terrain();
    if (t.state === 'failed') return 'failed';
    return t.state === 'ready' && Math.abs(t.relief - window.__dbg.relief) < 1e-6;   // the Hills slider's relief
  });
  await expect.poll(stands, { timeout: 60_000 }).not.toBe(false);
  expect(await stands(), 'the terrain failed to load').toBe(true);
};

test('the city loads, switches to Floors, opens a card and plays', async ({ page }) => {
  const errors = watchErrors(page);

  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(page).toHaveTitle('Hus för hus');

  // v1.1 features stay in the page, hidden by config.features; the language switch is on since 2026-10-17, quests and
  // walks since 2026-10-18 (e2e/quests.spec.mjs has their Look switch).
  await expect(page.locator('.quests-open')).toBeVisible();
  await expect(page.locator('.walks-open')).toBeVisible();
  await expect(page.locator('.modes [data-mode="3"]')).toBeHidden();
  await expect(page.locator('.lang [data-lang="sv"]')).toBeVisible();

  // At "Today" the count is every building: dated, dated by area, and without a year.
  const config = await cityConfig(page);
  await expect(page.locator('#year')).toHaveText('Today');
  await expect.poll(async () => Number((await page.locator('#count').innerText()).replace(/\D/g, '')))
    .toBe(config.stats.buildings);

  // Floors mode, and back.
  const floors = page.locator('.modes button[data-mode="1"]');
  await floors.click();
  await expect(floors).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#panel-body h2')).toHaveText('Floors');
  await page.locator('.modes button[data-mode="0"]').click();

  // A click near the middle of the map pins a building card; try a few points in case the centre is water.
  const box = await page.locator('#scene').boundingBox();
  const pinned = page.locator('#card.pinned');
  const offsets = [[0, 0], [30, 0], [-30, 0], [0, 30], [0, -30], [60, 40], [-60, 40], [60, -40], [-60, -40], [100, 0], [-100, 0], [0, 80]];
  let opened = false;
  for (const [dx, dy] of offsets) {
    await page.mouse.click(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy);
    if (await pinned.isVisible()) { opened = true; break; }
  }
  expect(opened, 'a click near the centre opens a card').toBe(true);
  await expect(pinned.locator('.card-head .y')).not.toBeEmpty();
  await page.keyboard.press('Escape');
  await expect(pinned).toBeHidden();

  // Play and pause.
  const play = page.locator('#play');
  await expect(play).toHaveAttribute('aria-label', "Play the city's growth");
  await play.click();
  await expect(play).toHaveAttribute('aria-label', 'Pause');
  await play.click();
  await expect(play).toHaveAttribute('aria-label', "Play the city's growth");

  expect(errors).toEqual([]);
});

// The title over the count says what the map shows (web/count.js tallyTitle): "Today", a range once the
// from-handle moves, or the name of the period shown alone.
test('the title follows the legend and the timeline', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const title = page.locator('#year'), line = page.locator('.tally-count');
  await expect(title).toHaveText('Today');
  await expect(line).toHaveText(/^[\d,\s]+ buildings$/);

  // One period alone: its name, and its own years after the count. Funkis is 1930–45: one century, end shortened.
  const i = config.periods.findIndex(p => p.key === 'p8');
  const p = config.periods[i];
  await page.locator(`.swatch[data-i="${i}"]`).click();
  await expect(title).toHaveText(p.label);
  await expect(line).toHaveText(new RegExp(` buildings · ${p.from}–${String(p.to).slice(2)}$`));
  await page.locator(`.swatch[data-i="${i}"]`).click(); // the same period again shows them all
  await expect(title).toHaveText('Today');
  await expect(line).toHaveText(/^[\d,\s]+ buildings$/);

  // The from-handle (the nearer one at the left) moved: a range to "Today"; then the to-handle back: two years.
  const box = await page.locator('#hist').boundingBox();
  const at = share => page.mouse.click(box.x + box.width * share, box.y + box.height / 2);
  await at(0.3);
  await expect(title).toHaveText(/^\d{4}–Today$/);
  // Play from "Today" starts the film after the from-handle, so its first frame is a range that runs forwards.
  const play = page.locator('#play');
  await play.click();
  const first = await page.evaluate(() => new Promise(done =>
    requestAnimationFrame(() => requestAnimationFrame(() => done(document.getElementById('year').textContent)))));
  const [lo, hi] = first.split('–').map(Number);
  expect(hi, first).toBeGreaterThan(lo);
  await play.click();
  await at(0.85);
  await expect(title).toHaveText(/^\d{4}–\d{4}$/);
  // The from-handle dragged back past the left end rests again: nothing fades, the title is the to-year, then "Today".
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x - 20, box.y + box.height / 2, { steps: 4 });
  await page.mouse.up();
  await expect(title).toHaveText(/^\d{4}$/);
  await page.mouse.click(box.x + box.width - 1, box.y + box.height / 2);
  await expect(title).toHaveText('Today');
  await expect.poll(async () => Number((await page.locator('#count').innerText()).replace(/\D/g, '')))
    .toBe(config.stats.buildings);
  expect(errors).toEqual([]);
});

// Final review VIEWER-1: picking a period rebuilds the legend, and a keyboard user must not land on <body> (the
// switches after the period list would be about 13 Tab stops away again). The chip keeps the focus, as the look
// switcher's cards do.
test('a period picked from the keyboard keeps the focus on its chip', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const i = config.periods.findIndex(p => p.key === 'p8');
  const chip = page.locator(`#panel-body .swatch[data-i="${i}"]`), next = page.locator(`#panel-body .swatch[data-i="${i + 1}"]`);
  await chip.focus();
  await page.keyboard.press('Enter');
  await expect(next).toHaveAttribute('aria-pressed', 'false'); // the period alone
  await expect(chip).toHaveAttribute('aria-pressed', 'true');
  await expect(chip).toBeFocused();
  await page.keyboard.press('Space'); // the same period again shows them all
  await expect(next).toHaveAttribute('aria-pressed', 'true');
  await expect(chip).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(next).toBeFocused();
  expect(errors).toEqual([]);
});

// Buildings without a year: left alone, drawn at "Today" and gone whenever the map shows the past; the
// legend's switch "Show" always reads what the map does, and once flipped the choice holds at every year. uShowUnknown
// is how far they stand, 1 to 0: app.js eases it towards web/unknown.js unknownShown, and the vertex shader draws them
// by it.
const standing = page => page.evaluate(() => window.__dbg.uniforms.uShowUnknown.value);
const shownCount = async page => Number((await page.locator('#count').innerText()).replace(/\D/g, ''));
const stored = page => page.evaluate(() => localStorage.getItem('hfh-unknown'));
const SWITCH = '#panel-body .swatch.unknown button.switch', HINT = '#panel-body .unknown-hint';
const SOLO_HINT = 'Hidden while one period is shown alone.';
// The dated buildings the map draws between the handles (from < year <= to): the count's own tally from attrs.bin
// (window.__dbg.attrTally, web/count.js tallyFromAttrs), a private house at its decade start as the shader draws it,
// not spread over the decade as stockholm.json's histograms are (F17).
const datedCount = (page, from, to) => page.evaluate(([from, to]) => {
  const T = window.__dbg.attrTally;
  return [T.histogram, T.histogramEst].reduce((n, h) => n +
    Object.entries(h).reduce((m, [y, v]) => m + (+y > from && +y <= to ? v.reduce((a, b) => a + b, 0) : 0), 0), 0);
}, [from, to]);
const handles = page => page.evaluate(() => [window.__dbg.uniforms.uYearFrom.value, window.__dbg.uniforms.uYear.value]);
// A click on `selector`, then how long until they stand at `value`: milliseconds in the page's own time, and frames.
const settleAfter = (page, selector, value) => page.evaluate(([selector, value]) => new Promise(done => {
  const t0 = performance.now();
  let frames = 0;
  document.querySelector(selector).click();
  const check = () => {
    frames++;
    if (window.__dbg.uniforms.uShowUnknown.value === value) done({ ms: performance.now() - t0, frames });
    else requestAnimationFrame(check);
  };
  requestAnimationFrame(check);
}), [selector, value]);

test('buildings without a year stand at "Today" and leave whenever the map shows the past; the switch reads the map', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/?film=4'); // a 4-second film, to see it end
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const title = page.locator('#year'), play = page.locator('#play');
  const sw = page.locator(SWITCH);
  await expect(sw).toHaveText('Show');
  // A screen reader hears which row it belongs to, and the hint under it: what the switch does now.
  await expect(sw).toHaveAccessibleDescription('Year unknown Shown at “Today”, hidden in the past.');
  await expect(page.locator(HINT)).toHaveText('Shown at “Today”, hidden in the past.');
  // The hint is on the "Year unknown" row, under the switch, not in the legend's note.
  expect(await page.locator(HINT).evaluate(el => el.parentElement.matches('.swatch.unknown'))).toBe(true);
  // At load they stand, and the switch says so.
  await expect(title).toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  expect(await standing(page)).toBe(1);

  // Play from "Today": gone within a second, sinking over more than one frame rather than in one, and gone while the
  // film plays; the switch reads off. The easing goes by time, so one long frame may cover most of it: no floor on the
  // time or a larger number of frames, which would flake on a slow runner (review F4).
  const out = await settleAfter(page, '#play', 0);
  expect(out.ms).toBeLessThan(1000);
  expect(out.frames).toBeGreaterThanOrEqual(2);
  await expect(play).toHaveAttribute('aria-label', 'Pause');
  await expect(title).not.toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  expect(await standing(page)).toBe(0);
  // The film ends at "Today": not playing any more, so they come back, and the switch with them.
  await expect(play).toHaveAttribute('aria-label', "Play the city's growth", { timeout: 10_000 });
  await expect(title).toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => standing(page)).toBe(1);

  // The timeline dragged back (the to-handle, the nearer one at the right): gone; back to the end: back.
  const box = await page.locator('#hist').boundingBox();
  const at = share => page.mouse.click(box.x + box.width * share, box.y + box.height / 2);
  await at(0.8);
  await expect(title).toHaveText(/^\d{4}$/);
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => standing(page)).toBe(0);
  await page.mouse.click(box.x + box.width - 1, box.y + box.height / 2);
  await expect(title).toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => standing(page)).toBe(1);

  // The from-handle moved: gone, though the to-handle is at "Today", and the count leaves them out as the map does
  // (review F1). Dragged back past the left end the handle rests: back, and counted.
  await at(0.3);
  await expect(title).toHaveText(/^\d{4}–Today$/);
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => standing(page)).toBe(0);
  const [from] = await handles(page);
  await expect.poll(() => shownCount(page)).toBe(await datedCount(page, from, config.yearMax));
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x - 20, box.y + box.height / 2, { steps: 4 });
  await page.mouse.up();
  await expect(title).toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => standing(page)).toBe(1);
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);

  // A period shown alone takes them away at once, as it does every other period, and brings them back at once. While
  // it is alone the switch reads off and is disabled: a click changes nothing.
  const i = config.periods.findIndex(p => p.key === 'p8');
  const solo = `.swatch[data-i="${i}"]`;
  expect((await settleAfter(page, solo, 0)).frames).toBeLessThanOrEqual(2);
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect(sw).toHaveAttribute('aria-disabled', 'true');
  await expect(sw).toBeDisabled(); // as assistive technology hears it
  await expect(page.locator(HINT)).toHaveText(SOLO_HINT); // the hint says why, not the automatic rule
  await sw.click({ force: true }); // a pointer can still press it
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  expect(await standing(page)).toBe(0);
  expect((await settleAfter(page, solo, 1)).frames).toBeLessThanOrEqual(2);
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect(sw).not.toHaveAttribute('aria-disabled', 'true');
  await expect(page.locator(HINT)).toHaveText('Shown at “Today”, hidden in the past.');

  // Nothing was chosen, so nothing is stored, and at "Today" the count is every building.
  expect(await stored(page)).toBeNull();
  await expect(page.locator(HINT)).toHaveText('Shown at “Today”, hidden in the past.');
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  expect(errors).toEqual([]);
});

// Flipped on while the film hides them: they come back and stay at every year, and the choice is remembered.
test('the switch flipped on during Play keeps buildings without a year at every year, and is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const title = page.locator('#year'), play = page.locator('#play');
  const sw = page.locator(SWITCH);
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await play.click();
  await expect(play).toHaveAttribute('aria-label', 'Pause');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => standing(page)).toBe(0);
  // Keyboard: focused, Space turns it on mid-film.
  await sw.focus();
  await page.keyboard.press('Space');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect(sw).toBeFocused(); // switched in place, not rebuilt
  await expect.poll(() => standing(page)).toBe(1);
  expect(await stored(page)).toBe('show');
  await expect(page.locator(HINT)).toHaveText('Your choice is remembered.');
  // The film goes on, and they stay.
  await page.waitForTimeout(1200);
  await expect(play).toHaveAttribute('aria-label', 'Pause');
  expect(await standing(page)).toBe(1);
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  // Paused in the past: drawn, but not counted at a past year. Pause rounds the film's year, and the count
  // follows it at once, before any frame redraws it (a frame redraws the count only while the film plays): paused at
  // n + 0.6, it reads n + 1's buildings, whatever the frame rate.
  const n = config.yearMax - 50;
  const paused = await page.evaluate(n => {
    const D = window.__dbg, count = () => Number(document.getElementById('count').textContent.replace(/\D/g, ''));
    const before = count();
    D.uniforms.uYear.value = n + 0.6;
    document.getElementById('play').click();
    return { before, year: D.uniforms.uYear.value, count: count() };
  }, n);
  await expect(play).toHaveAttribute('aria-label', "Play the city's growth");
  expect(paused.year).toBe(n + 1);
  await expect(title).toHaveText(String(n + 1));
  const [from, to] = await handles(page);
  expect(to).toBe(n + 1);
  const expected = await datedCount(page, from, n + 1);
  expect(expected, 'the film\'s last count differs from n + 1\'s, so the check can tell').not.toBe(paused.before);
  expect(paused.count).toBe(expected);
  expect(await standing(page)).toBe(1);

  // Reloaded: on at "Today" and counted; the timeline dragged back, still there and still on; the from-handle moved,
  // "1900–Today" counts them too.
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(title).toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  expect(await standing(page)).toBe(1);
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  const box = await page.locator('#hist').boundingBox();
  const at = share => page.mouse.click(box.x + box.width * share, box.y + box.height / 2);
  await at(0.6);
  await expect(title).toHaveText(/^\d{4}$/);
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  expect(await standing(page)).toBe(1);
  await page.mouse.click(box.x + box.width - 1, box.y + box.height / 2);
  await at(0.3);
  await expect(title).toHaveText(/^\d{4}–Today$/);
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  expect(await standing(page)).toBe(1);
  const [from2] = await handles(page);
  await expect.poll(() => shownCount(page)).toBe(await datedCount(page, from2, config.yearMax) + config.unknown);
  expect(errors).toEqual([]);
});

// Flipped off at "Today": they leave there too, and the choice is remembered.
test('the switch flipped off at "Today" hides buildings without a year there too, and is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  // Every animation frame, uShowUnknown as the page has it (undefined until the uniforms exist), kept per document.
  await page.addInitScript(() => {
    const raf = window.requestAnimationFrame.bind(window);
    window.__unknownFrames = [];
    window.requestAnimationFrame = cb => raf(ts => {
      const v = window.__dbg?.uniforms?.uShowUnknown?.value;
      if (v !== undefined && window.__unknownFrames.length < 600) window.__unknownFrames.push(v);
      return cb(ts);
    });
  });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const title = page.locator('#year'), play = page.locator('#play');
  const sw = page.locator(SWITCH);
  await expect(title).toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => standing(page)).toBe(0);
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings - config.unknown); // the count follows the map
  expect(await stored(page)).toBe('hide');
  await expect(page.locator(HINT)).toHaveText('Your choice is remembered.');
  // A period shown alone: the hint says why they are gone, then the choice again once the period is let go.
  await page.locator('.swatch[data-i="0"]').click();
  await expect(page.locator(HINT)).toHaveText(SOLO_HINT);
  await page.locator('.swatch[data-i="0"]').click();
  await expect(page.locator(HINT)).toHaveText('Your choice is remembered.');

  // Reloaded: off at "Today" from the first frame, not sinking at load (every frame from the first is sampled by
  // the init script: a page that eased 1 to 0 after load would record values above 0), and not counted.
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const frames = await page.evaluate(() => window.__unknownFrames);
  expect(frames.length, 'frames were sampled before the first draw').toBeGreaterThan(10);
  expect(frames.filter(v => v !== 0)).toEqual([]);
  expect(await standing(page)).toBe(0);
  await expect(title).toHaveText('Today');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings - config.unknown);
  // Play and pause: still off. Turned on again with Enter: back, and that is remembered instead.
  await play.click();
  await expect(play).toHaveAttribute('aria-label', 'Pause');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await play.click();
  await sw.focus();
  await page.keyboard.press('Enter');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => standing(page)).toBe(1);
  expect(await stored(page)).toBe('show');
  expect(errors).toEqual([]);
});

// The hint in Swedish. The language switch was off in the shipped config until 2026-10-17 (features.lang); this
// run still turns it on in the page's own copy of the config, so it does not depend on that.
test('with one period shown alone the hint is Swedish too', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/stockholm.json')) return r;
      const config = await r.json();
      config.features = { ...config.features, lang: true };
      return new Response(JSON.stringify(config), { headers: { 'content-type': 'application/json' } });
    };
  });
  await page.goto('/?lang=sv');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(page.locator(SWITCH)).toHaveText('Visa');
  await expect(page.locator(HINT)).toHaveText('Visas vid ”I dag”, döljs bakåt i tiden.');
  await page.locator('.swatch[data-i="0"]').click();
  await expect(page.locator(HINT)).toHaveText('Döljs medan en period visas ensam.');
  await page.locator('.swatch[data-i="0"]').click();
  await expect(page.locator(HINT)).toHaveText('Visas vid ”I dag”, döljs bakåt i tiden.');
  expect(errors).toEqual([]);
});

// The first unknown-year switch stored 'always' when it was on ("Show at every year"): that is 'show' now.
test('a visitor who had "Show at every year" on keeps them at every year', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => { if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1'); localStorage.setItem('hfh-unknown', 'always'); } });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const sw = page.locator(SWITCH);
  expect(await stored(page)).toBe('show');
  await page.locator('#play').click();
  await page.waitForTimeout(800);
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  expect(await standing(page)).toBe(1);
  await page.locator('#play').click();
  expect(errors).toEqual([]);
});

// The oldest building's year need not sit on the timeline's 50-year grid: the from-handle rests just before it, and
// the page still loads at "Today". This run moves the oldest buildings to 40 years after the timeline's left end.
test('the title reads "Today" at load when the oldest year is off the timeline grid', async ({ page }) => {
  const errors = watchErrors(page);
  // The page's own fetch changes the config (page.route would intercept every request, and the burst of module
  // requests then reset connections on a scripts/serve.py older than Server.request_queue_size).
  await page.addInitScript(() => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/stockholm.json')) return r;
      const config = await r.json();
      // first is the faked yearMin (40 past a multiple of 50, off the timeline grid). It must lie after the oldest
      // year or nothing fades (a fixture whose oldest year were 1292 would give 1290): then the next one, 50 on
      // (final review ALIGNMENT-3).
      let first = Math.floor(config.yearMin / 50) * 50 + 40;
      if (first <= config.yearMin) first += 50;
      for (const h of [config.histogram, config.histogramEst || {}]) {
        for (const y of Object.keys(h).filter(y => +y < first)) {
          const into = h[first] || (h[first] = h[y].map(() => 0));
          h[y].forEach((c, i) => { into[i] += c; });
          delete h[y];
        }
      }
      config.yearMin = first;
      return new Response(JSON.stringify(config), { headers: { 'content-type': 'application/json' } });
    };
  });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await page.evaluate(() => fetch('data/current.json').then(r => r.json())
    .then(({ version }) => fetch(`data/${version}/stockholm.json`)).then(r => r.json()));
  expect(config.yearMin % 50).toBe(40);
  await expect(page.locator('#year')).toHaveText('Today');
  // Only stockholm.json is changed: attrs.bin and the tiles keep the oldest buildings at their own years, so the
  // from-handle resting before the new yearMin fades them on the map, and the count, built from attrs.bin (
  // web/count.js tallyFromAttrs), leaves them out as the map does. The test reads attrs.bin itself, apart from the
  // count's own tally: every dated record (yflag, byte 3, not 7 UNKNOWN) whose year (bytes 4–5) is before the new yearMin,
  // the init script's `first` (config.yearMin here is the faked one, read through the patched fetch).
  const faded = await page.evaluate(async ([first, stride]) => {
    const { version } = await (await fetch('data/current.json')).json();
    let buf = await (await fetch(`data/${version}/attrs.bin.gz`)).arrayBuffer();
    const u8 = new Uint8Array(buf);
    if (u8[0] === 0x1f && u8[1] === 0x8b) buf = await new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    const v = new DataView(buf);
    let n = 0;
    for (let o = 0; o + stride <= buf.byteLength; o += stride) if (v.getUint8(o + 3) !== 7 && v.getInt16(o + 4, true) < first) n++;
    return n;
  }, [config.yearMin, config.attrStride]);
  expect(faded, 'the faked yearMin fades some buildings').toBeGreaterThan(0);
  await expect.poll(async () => Number((await page.locator('#count').innerText()).replace(/\D/g, '')))
    .toBe(config.stats.buildings - faded);
  expect(errors).toEqual([]);
});

// The Look switcher (web/look.js, web/switcher.js): each look applies at once, with no reload, and is remembered;
// ?theme= in a link beats the remembered one. A first visit, with nothing remembered, is in Ärg.
test('the look switcher changes the look in place and remembers it', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const html = page.locator('html');
  await expect(html).toHaveAttribute('data-theme', 'arg');
  // The page's CSS ground, the WebGL clear colour (the sky), the buildings' first period colour, the street names.
  const drawn = () => page.evaluate(() => {
    const sky = { copy(c) { Object.assign(this, { r: c.r, g: c.g, b: c.b }); return this; } };
    window.__dbg.renderer.getClearColor(sky);
    const hex = v => Math.round(v * 255).toString(16).padStart(2, '0');
    const chip = document.querySelector('#panel-body .swatch.unknown > i');
    return { bg: getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(), sky: `#${hex(sky.r)}${hex(sky.g)}${hex(sky.b)}`,
      p1: `#${window.__dbg.uniforms.uPalette.value[0].getHexString()}`, hatch: window.__dbg.uniforms.uHatch.value,
      chip: chip && getComputedStyle(chip).backgroundImage, ...window.__dbg.stats() };
  });
  // "Year unknown" is hatched in Ärg only: in the shader, and on the legend chip.
  const hatched = (now, id) => {
    expect(now.hatch).toBe(id === 'arg' ? 1 : 0);
    if (now.chip !== null) expect(now.chip.startsWith('repeating-linear-gradient')).toBe(id === 'arg');
  };
  await expect.poll(async () => (await drawn()).labels, { timeout: 15_000 }).toBeGreaterThan(0);
  await terrainSettled(page);
  const before = await drawn();
  hatched(before, 'arg');
  // ... and on the band of a card for a building with no year, the same as the legend chip.
  const band = await page.evaluate(() => {
    const D = window.__dbg;
    let g = 0;
    while (g < 1e6 && D.building(g).yflag !== 7) g++;
    D.pinCard(g, 300, 300);
    const head = getComputedStyle(document.querySelector('#card .card-head')).backgroundImage;
    D.pinCard(-1);
    return head;
  });
  expect(band).toBe(before.chip);
  await page.evaluate(() => { window.__sameDocument = true; }); // a reload would lose it
  // The legend is recoloured in place, not rebuilt: its scroll, focus and anything typed in it stay.
  await page.evaluate(() => { window.__swatch = document.querySelector('#panel-body .swatch[data-i="0"] > i'); });

  const button = page.locator('.look-open'), panel = page.locator('#look');
  await button.click();
  await expect(panel).toBeVisible();
  await expect(button).toHaveAttribute('aria-expanded', 'true');
  await expect(panel.locator('.look-card')).toHaveCount(Object.keys(THEMES).length);
  await expect(panel.locator('.look-card[aria-pressed="true"]')).toHaveAttribute('data-look', 'arg');
  await expect(panel.locator('.look-card[aria-pressed="true"]')).toBeFocused();
  // The weather row (web/weather.js; e2e/weather.spec.mjs switches it): Clear, Snow, Rain and Fog, Clear pressed.
  await expect(panel.locator('#atmos-title')).toHaveText('Weather');
  await expect(panel.locator('.look-atmos button')).toHaveText(['Clear', 'Snow', 'Rain', 'Fog']);
  await expect(panel.locator('.look-atmos [aria-pressed="true"]')).toHaveAttribute('data-atmos', 'none');

  const rgbOf = hex => `rgb(${[1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)).join(', ')})`;
  for (const id of ['kalk', 'paper', 'arg', 'blatimme']) {
    await panel.locator(`.look-card[data-look="${id}"]`).click();
    await expect(html).toHaveAttribute('data-theme', id);
    await expect(panel.locator('.look-card[aria-pressed="true"]')).toHaveAttribute('data-look', id);
    await expect(panel).toBeVisible(); // it stays open, to compare
    // the names come back, drawn again in the new look's font
    await expect.poll(async () => (await drawn()).labels, { timeout: 15_000 }).toBeGreaterThan(0);
    const now = await drawn();
    expect(now.theme).toBe(id);
    expect(now.bg).toBe(THEMES[id].ui['--bg']);
    expect(now.sky).toBe(THEMES[id].sky);
    expect(now.p1).toBe(THEMES[id].periods[0]);
    hatched(now, id);
    // The "Year unknown" switch's label reads the ink when it is on and the muted ink when it is off, in every look
    // (review R1: `.swatch.unknown .switch` once beat the on-state rule). Read from the style sheet with the attribute
    // set both ways for a moment, with no frame between, so the choice stays untouched.
    expect(await page.evaluate(() => {
      const sw = document.querySelector('#panel-body .swatch.unknown button.switch'), was = sw.getAttribute('aria-pressed');
      const read = pressed => { sw.setAttribute('aria-pressed', pressed); return getComputedStyle(sw).color; };
      const colours = { on: read('true'), off: read('false') };
      sw.setAttribute('aria-pressed', was);
      return colours;
    })).toEqual({ on: rgbOf(THEMES[id].ui['--ink']), off: rgbOf(THEMES[id].ui['--muted']) });
  }
  await expect(page).toHaveURL(/[?&]theme=blatimme/);
  expect(await page.evaluate(() => window.__sameDocument)).toBe(true);
  expect(await page.evaluate(() => window.__swatch.isConnected && getComputedStyle(window.__swatch).backgroundColor))
    .toBe(rgbOf(THEMES.blatimme.periods[0]));
  // Every switch disposes the old names' textures: the same names on screen, no more textures than before.
  expect((await drawn()).textures).toBeLessThanOrEqual(before.textures);

  // Keyboard: the arrows move between the cards, Escape closes and gives the focus back to the button.
  await page.keyboard.press('ArrowRight');
  await expect(panel.locator('.look-card[data-look="paper"]')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  await expect(button).toBeFocused();
  await expect(button).toHaveAttribute('aria-expanded', 'false');
  await page.keyboard.press('Enter');
  await expect(panel).toBeVisible();
  await expect(panel.locator('.look-card[data-look="blatimme"]')).toBeFocused();
  // A click outside closes it.
  await page.locator('#year').click();
  await expect(panel).toBeHidden();

  // The choice is remembered without the URL, and a ?theme= link beats it.
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(html).toHaveAttribute('data-theme', 'blatimme');
  await page.goto('/?theme=kalk');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(html).toHaveAttribute('data-theme', 'kalk');
  expect(errors).toEqual([]);
});

// The code itself can fail to arrive too: app.js, or a module it imports. The module then never runs, and the page
// must not stay at "Building the city 0%" (web/boot.js).
test('a missing app.js or module shows the failure message', async ({ page }) => {
  // The 404s below are deliberate, and so are the browser's console lines about them.
  const errors = watchErrors(page, e => /^(HTTP 404|console): .*\/(app|look)\.js/.test(e));
  for (const file of ['app.js', 'look.js']) {
    await page.route(`**/${file}`, route => route.fulfill({ status: 404, body: 'Not found' }));
    await page.goto('/');
    const loading = page.locator('#loading');
    await expect(loading).toHaveText('Could not load the city data. Reload the page to try again.');
    await expect(loading).toBeVisible();
    await page.unroute(`**/${file}`);
  }
  expect(errors).toEqual([]);
});

// A module that arrives but cannot run (it throws at the top, or uses syntax this browser cannot parse) reports on
// the window, not at its <script>; that too must not leave "Building the city 0%" on screen (web/boot.js).
test('a module that fails to run shows the failure message', async ({ page }) => {
  const errors = watchErrors(page, e => /^pageerror: (boom|Unexpected token)/.test(e));
  const throws = 'export const createLooks = () => {}; throw new Error("boom");';
  for (const [file, body] of [['look.js', throws], ['app.js', 'export const = ;']]) {
    await page.route(`**/${file}`, route => route.fulfill({ status: 200, contentType: 'text/javascript', body }));
    await page.goto('/');
    const loading = page.locator('#loading');
    await expect(loading).toHaveText('Could not load the city data. Reload the page to try again.');
    await expect(loading).toBeVisible();
    await page.unroute(`**/${file}`);
  }
  expect(errors).toEqual([]);
});

// The first paint is Ärg before any script runs: styles.css's own tokens, font and color-scheme, so a slow
// app.js never shows another look first. Here app.js never arrives.
test('the page is in Ärg before app.js runs', async ({ page }) => {
  await page.route('**/app.js', route => route.abort());
  await page.goto('/');
  const css = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    return { bg: root.getPropertyValue('--bg').trim(), ink: root.getPropertyValue('--ink').trim(),
      panel: root.getPropertyValue('--panel').trim(), font: root.getPropertyValue('--font').trim(),
      scheme: root.colorScheme, body: getComputedStyle(document.body).backgroundColor,
      theme: document.documentElement.dataset.theme ?? null };
  });
  const arg = THEMES.arg;
  expect(css.theme).toBeNull(); // nothing has run
  expect(css).toMatchObject({ bg: arg.ui['--bg'], ink: arg.ui['--ink'], panel: arg.ui['--panel'], font: `"${arg.font}"`,
    scheme: 'light' });
  expect(css.body).toBe(`rgb(${[1, 3, 5].map(i => parseInt(arg.ui['--bg'].slice(i, i + 2), 16)).join(', ')})`);
});

// Estimated years (area, kNN, period-only) are drawn in estimate style and can be hidden by the legend's
// switch under "Year unknown", the same switch component as that row's (a button with aria-pressed, changed in place so
// it keeps the focus; F5). The map, the count, the legend's totals and the histogram follow, the choice is remembered,
// and it holds in the period view only. The switch stays live with a period shown alone.
const HIDE_EST = '#panel-body .est-row button.switch#hide-est';
const estHidden = page => page.evaluate(() => window.__dbg.uniforms.uHideEst.value);
const legendSum = page => page.evaluate(() => [...document.querySelectorAll('#panel-body .swatch[data-i] .n')]
  .reduce((n, el) => n + Number(el.textContent.replace(/\D/g, '')), 0));
const histPixels = page => page.evaluate(async () => {
  await document.fonts.ready;
  await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
  return document.getElementById('hist').toDataURL();
});
// What the pick pass sees at the middle of the screen (the pick pass draws what the map draws), two frames on.
const pickCentre = page => page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(() =>
  done(window.__dbg.pick(innerWidth / 2, innerHeight / 2))))));

test('the hide-estimates switch takes the estimated years off the map, the count, the legend and the histogram, and is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const f = config.stats.byFlag, est = f.area + f.estimate + f.period, known = f.exact + f.range + f.long;
  test.skip(est === 0, 'this build has no estimated years (the fixture city)');
  const sw = page.locator(HIDE_EST);
  const stored = () => page.evaluate(() => localStorage.getItem('hfh-estimates'));
  // The product default (decision 3) is whatever app.js starts with; the test starts from "shown" either way.
  if (await estHidden(page) === 1) await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect(sw).toHaveText(`Hide the ${est.toLocaleString('en')} estimated years`);
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  expect(await legendSum(page)).toBe(known + est);
  // Its own row: not part of "Year unknown", its track at the legend's left edge (under the period chips), not
  // indented under the "Show" track. The legend's note ends with the estimates sentence (no unknown-year hint in it).
  const left = sel => page.locator(sel).evaluate(el => Math.round(el.getBoundingClientRect().left));
  expect(await page.locator(HIDE_EST).evaluate(el => !!el.closest('.swatch'))).toBe(false);
  expect(await left(`${HIDE_EST} .toggle`)).toBe(await left('#panel-body .swatch[data-i="0"] > i'));
  expect(await left(`${HIDE_EST} .toggle`)).toBeLessThan(await left(`${SWITCH} .toggle`));
  await expect(page.locator('#panel-body .note')).toHaveText(
    'Click a period to see it alone. Muted, darker colours are estimates (≈): the card says whether from an area or from neighbours.');
  await expect(page.locator('#about-body')).toContainText('houses are estimated from similar dated buildings nearby');

  // On the map: the tallest estimated buildings, flown to one by one, until one is picked at the middle of the screen
  // (a taller neighbour may stand in front). Hidden, it is not drawn there, so the pick pass finds something else.
  await expect.poll(() => page.evaluate(() => { const s = window.__dbg.stats(); return s.tiles === s.tilesTotal; }),
    { timeout: 60_000 }).toBe(true);
  await terrainSettled(page);
  const candidates = await page.evaluate(n => {
    const out = [];
    for (let g = 0; g < n; g++) { const b = window.__dbg.building(g); if ([3, 4, 6].includes(b.yflag)) out.push([b.height, g]); }
    return out.sort((a, b) => b[0] - a[0]).slice(0, 8).map(([, g]) => g);
  }, config.stats.buildings);
  let target = -1;
  for (const g of candidates) {
    await page.evaluate(g => new Promise(done => { const b = window.__dbg.building(g); window.__dbg.flyTo(b.x, b.z, done, 260); }), g);
    if (await pickCentre(page) === g) { target = g; break; }
  }
  expect(target, 'an estimated building is picked at the middle of the screen').toBeGreaterThanOrEqual(0);
  const histShown = await histPixels(page);

  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect(sw).toBeFocused(); // changed in place, not rebuilt
  expect(await estHidden(page)).toBe(1);
  expect(await stored()).toBe('hidden');
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings - est);
  expect(await legendSum(page)).toBe(known); // the periods' totals drop their estimated share
  await expect(page.locator('#panel-body .swatch.unknown .n')).toHaveText(config.unknown.toLocaleString('en'));
  expect(await pickCentre(page)).not.toBe(target);
  expect(await histPixels(page)).not.toBe(histShown);
  await sw.click(); // and back: the same building, the same histogram
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  expect(await pickCentre(page)).toBe(target);
  expect(await histPixels(page)).toBe(histShown);
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'true');

  // Floors shows every building again (the switch lives in the period legend); back in Period mode it still holds.
  await page.locator('.modes button[data-mode="1"]').click();
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  expect(await pickCentre(page)).toBe(target);
  await page.locator('.modes button[data-mode="0"]').click();
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings - est);

  // A period shown alone counts its known years only while the switch is on; the switch stays live there. The period
  // is the one with the most estimated years (stockholm.json's histogramEst), so its estimates do leave and come back.
  const sum = (h, j) => Object.values(h).reduce((n, v) => n + v[j], 0);
  const estBy = config.periods.map((_, j) => sum(config.histogramEst, j));
  const i = estBy.indexOf(Math.max(...estBy));
  const pKnown = sum(config.histogram, i), pEst = estBy[i];
  expect(pEst, `${config.periods[i].key} has estimated years`).toBeGreaterThan(0);
  await page.locator(`.swatch[data-i="${i}"]`).click();
  await expect.poll(() => shownCount(page)).toBe(pKnown);
  await expect(sw).not.toHaveAttribute('aria-disabled', 'true');
  await sw.click();
  await expect.poll(() => shownCount(page)).toBe(pKnown + pEst);
  await sw.click();
  await expect.poll(() => shownCount(page)).toBe(pKnown);
  await page.locator(`.swatch[data-i="${i}"]`).click();

  // Remembered across a reload; turned off from the keyboard, everything is back.
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  expect(await estHidden(page)).toBe(1);
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings - est);
  expect(await legendSum(page)).toBe(known);
  await sw.focus();
  await page.keyboard.press('Space');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect(sw).toBeFocused();
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  expect(await legendSum(page)).toBe(known + est);
  expect(await stored()).toBe('shown');
  expect(errors).toEqual([]);
});

// An estimate's card says "≈" (in the system font: the latin subsets lack it, W7) and its band; a private house dated by
// its period only shows the period's name, never "Year unknown" or a decade. The fixture data has no kNN or period-only
// rows, so this run turns two estimated rows (area, kNN or period-only, not private) into one of each in the page's
// own copy of attrs.bin: both stay in the estimated set and keep their year and period, so the map and the count do
// not change. On a build with real estimates it does the same to real rows.
test('an estimate\'s card says ≈ and ±N years; a private period-only house shows its period', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/attrs.bin.gz')) return r;
      let buf = await r.arrayBuffer();
      const u8 = new Uint8Array(buf);
      if (u8[0] === 0x1f && u8[1] === 0x8b) buf = await new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
      // 24-byte records; yflag at 3, year 4, year_from 6, year_to 8 (i16), ysrc 10, private 22
      const v = new DataView(buf), picked = [];
      for (let o = 0; o + 24 <= buf.byteLength && picked.length < 2; o += 24) {
        if ([3, 4, 6].includes(v.getUint8(o + 3)) && !v.getUint8(o + 22)) picked.push(o / 24);
      }
      const [e, p] = picked.map(g => g * 24);
      if (e !== undefined) {
        const year = v.getInt16(e + 4, true);
        v.setUint8(e + 3, 4); v.setUint8(e + 10, 5); // ESTIMATE, from the kNN
        v.setInt16(e + 6, year - 6, true); v.setInt16(e + 8, year + 4, true); // a band of ±6 (the larger side)
      }
      if (p !== undefined) { v.setUint8(p + 3, 6); v.setUint8(p + 10, 5); v.setUint8(p + 22, 1); } // PERIOD, private
      window.__patched = picked;
      return new Response(buf);
    };
  });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const [estGid, periodGid] = await page.evaluate(() => window.__patched);
  test.skip(periodGid === undefined, 'this build has fewer than two estimated rows');
  const config = await cityConfig(page);
  const card = page.locator('#card.pinned');

  const e = await page.evaluate(g => window.__dbg.building(g), estGid);
  expect([e.yflag, e.ysrc]).toEqual([4, 5]);
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), estGid);
  await expect(card.locator('.card-head .y')).toHaveText(`≈ ${e.year}`);
  await expect(card.locator('.card-head .y .approx')).toHaveText('≈');
  await expect(card.locator('.card-head .period')).toHaveText(config.periods[e.period].label);
  const dating = card.locator('.dating');           // one unlabelled line under the band
  await expect(dating).toHaveText('≈ estimated from similar dated buildings nearby (±6 years)');
  await expect(dating.locator('.approx')).toHaveText('≈');
  expect(await dating.locator('.approx').evaluate(el => getComputedStyle(el).fontFamily)).toMatch(/^system-ui/);
  await page.keyboard.press('Escape');
  await expect(card).toBeHidden();

  const p = await page.evaluate(g => window.__dbg.building(g), periodGid);
  expect([p.yflag, p.private]).toEqual([6, 1]);
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), periodGid);
  await expect(card.locator('.card-head .y')).toHaveText(config.periods[p.period].label);
  await expect(card.locator('.card-head .period')).toHaveCount(0); // named once, in the big line
  // A pinned private house's dating line ends with "Why?", a link to About's privacy rule
  await expect(card.locator('.dating')).toHaveText('Private house: period only, estimated from neighbours Why?');
  await page.keyboard.press('Escape');

  // Every kNN estimate is a private house now, published as its decade. Its card says it is an
  // estimate and how the decade is known, never the band. A real one from the build, when it has estimates (the
  // fixture city has none).
  const privEst = await page.evaluate(n => {
    for (let g = 0; g < n; g++) { const x = window.__dbg.building(g); if (x.yflag === 4 && x.ysrc === 5 && x.private) return g; }
    return -1;
  }, config.stats.buildings);
  if (config.stats.byFlag.estimate > 0) {
    expect(privEst, 'a private house among the estimates').toBeGreaterThanOrEqual(0);
    const h = await page.evaluate(g => window.__dbg.building(g), privEst);
    await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), privEst);
    await expect(card.locator('.card-head .y')).toHaveText(`≈ ${Math.floor(h.year / 10) * 10}s`);
    await expect(card.locator('.dating')).toHaveText('≈ estimated from similar dated houses nearby · private house: decade only Why?');
    await page.keyboard.press('Escape');
  }

  // Both are still estimated years: the count at "Today" is every building, and without the estimates the same less.
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  await page.evaluate(() => window.__dbg.setHideEst(true));
  const f = config.stats.byFlag;
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings - f.area - f.estimate - f.period);
  await page.evaluate(() => window.__dbg.setHideEst(false));
  expect(errors).toEqual([]);
});

// The switch and the legend's note in Swedish. The language switch was off in the shipped config until 2026-10-17
// (features.lang); this run still turns it on in the page's own copy of the config, as the Swedish hint test above does.
test('the hide-estimates switch and the legend note are Swedish too', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/stockholm.json')) return r;
      const config = await r.json();
      config.features = { ...config.features, lang: true };
      return new Response(JSON.stringify(config), { headers: { 'content-type': 'application/json' } });
    };
  });
  await page.goto('/?lang=sv');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const f = config.stats.byFlag, est = f.area + f.estimate + f.period;
  await expect(page.locator('#panel-body .note')).toHaveText('Klicka på en period för att se den ensam. Dämpade, mörkare ' +
    'färger är uppskattningar (≈): kortet visar om de bygger på ett helt område eller på grannarna.');
  if (est) await expect(page.locator(HIDE_EST)).toHaveText(`Dölj de ${est.toLocaleString('sv-SE')} uppskattade åren`);
  else await expect(page.locator(HIDE_EST)).toHaveCount(0); // no estimated years, no switch
  expect(errors).toEqual([]);
});

// A period shown alone belongs to the period legend: Floors lets go of it, so the map (uMask, which Floors also
// draws by), the legend and the count agree; back in the period view every period is shown.
test('entering Floors lets go of a period shown alone, so the map, the legend and the count agree', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const mask = () => page.evaluate(() => [...window.__dbg.uniforms.uMask.value]);
  const i = config.periods.findIndex(p => p.key === 'p8');
  await page.locator(`.swatch[data-i="${i}"]`).click();
  await expect.poll(mask).toEqual(config.periods.map((_, j) => (j === i ? 1 : 0)));
  await page.locator('.modes button[data-mode="1"]').click();
  await expect.poll(mask).toEqual(config.periods.map(() => 1));
  await expect(page.locator('#year')).toHaveText('Today');
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  await page.locator('.modes button[data-mode="0"]').click();
  for (let j = 0; j < config.periods.length; j++) {
    await expect(page.locator(`.swatch[data-i="${j}"]`)).toHaveAttribute('aria-pressed', 'true');
  }
  await expect.poll(() => shownCount(page)).toBe(config.stats.buildings);
  expect(errors).toEqual([]);
});

// Review Focus #4: Safari before 16.4 has no DecompressionStream; the vendored fflate must build the same city.
test('the city loads with the fflate fallback when DecompressionStream is missing', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => { delete window.DecompressionStream; });

  await page.goto('/?debug=1');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const stats = await page.evaluate(() => window.__dbg.stats());
  expect(stats.decoder).toBe('fflate');
  expect(stats.tiles).toBe(stats.tilesTotal);
  const buildings = (await cityConfig(page)).stats.buildings;
  await expect.poll(async () => Number((await page.locator('#count').innerText()).replace(/\D/g, ''))).toBe(buildings);
  expect(errors).toEqual([]);
});

// A failed start must say so and how to recover, not leave "Building the city 0%" on screen.
test('a city file that fails to load shows the failure message', async ({ page }) => {
  // The 404 below is deliberate, and so are the browser's and loadFailed's console lines about it; a page error
  // (an uncaught rejection) or any other failure is still collected.
  const errors = watchErrors(page, e => /^(HTTP 404|console): .*stockholm\.json/.test(e));
  await page.route('**/stockholm.json', route => route.fulfill({ status: 404, body: 'Not found' }));

  await page.goto('/');
  const loading = page.locator('#loading');
  await expect(loading).toHaveText('Could not load the city data. Reload the page to try again.');
  await expect(loading).toBeVisible();
  // The Look button does not wait for the city: it works here too.
  await page.locator('.look-open').click();
  await expect(page.locator('#look .look-card')).toHaveCount(Object.keys(THEMES).length);
  await page.locator('#look .look-card[data-look="kalk"]').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'kalk');
  expect(errors).toEqual([]);
});

// Browser zoom gives fractional pixel ratios (90% on a retina screen is 1.8). The timeline canvas sizes its bitmap from
// its own width × devicePixelRatio; if that bitmap's aspect ratio fed back into the flex layout, every redraw widened it
// and Play pushed the playhead off screen. The canvas must keep its width while Play redraws it every frame.
test('the timeline keeps its width during Play at a fractional pixel ratio', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1000, height: 550 }, deviceScaleFactor: 1.8 });
  const page = await context.newPage();
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const width = () => page.evaluate(() => document.getElementById('hist').getBoundingClientRect().width);
  const footer = await page.evaluate(() => document.querySelector('.timeline').getBoundingClientRect().width);
  const before = await width();
  await page.locator('#play').click();
  await page.waitForTimeout(3000);
  const during = await width();
  await page.locator('#play').click();
  expect(before).toBeLessThan(footer);
  expect(Math.abs(during - before)).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
  await context.close();
});

// The north button (brief 2026-10-15, approved by the owner): a compass next to Look and About turns the map to face north,
// azimuth 0 (x east, z south), the short way round in about half a second, at once for a viewer who asks for less
// motion. The place, the zoom and the tilt stay; a drag cancels the turn; the needle always points north.
const NORTH = '.north-open';
const view = page => page.evaluate(() => {
  const c = window.__dbg.controls;
  return { az: c.getAzimuthalAngle(), polar: c.getPolarAngle(), dist: c.getDistance(), target: c.target.toArray() };
});
// Turns the map to azimuth `az` the way a script would: the camera moves round the target at the same height and
// distance, and the controls take it in.
const turnTo = (page, az) => page.evaluate(az => {
  const { camera, controls } = window.__dbg;
  const o = camera.position.clone().sub(controls.target), h = Math.hypot(o.x, o.z);
  camera.position.set(controls.target.x + h * Math.sin(az), camera.position.y, controls.target.z + h * Math.cos(az));
  controls.update();
}, az);
// Presses the north button and reads every frame's azimuth for `ms` milliseconds after, each after the render loop's own
// frame. In the page, so no round trip comes between the press and the first frame: the whole city renders at a few
// frames a second in a headless browser, and a turn is half a second.
const pressAndSample = (page, ms) => page.evaluate(([sel, ms]) => new Promise(done => {
  const out = [], t0 = performance.now();
  const step = () => {
    out.push(window.__dbg.controls.getAzimuthalAngle());
    if (performance.now() - t0 < ms) requestAnimationFrame(step); else done(out);
  };
  document.querySelector(sel).click();
  requestAnimationFrame(step);
}), [NORTH, ms]);
// A close view from above. At the hero view the whole city renders at a few frames a second in a headless browser
// (200–450 ms a frame on a laptop), too few to see a half-second turn on its way; from here, 40 ms or so.
const closeAbove = page => page.evaluate(() => {
  const { camera, controls } = window.__dbg;
  camera.position.set(controls.target.x, 400, controls.target.z + 120);
  controls.update();
});
// The camera's target rides on the ground (app.js followGround, a time constant of 0.1 s), while the
// terrain rises after the first frame. A test that holds the view still waits until the target has arrived
// (followGround stops moving it within 1 mm), so only what the test does moves it.
const groundSettled = async page => {
  await terrainSettled(page);
  await expect.poll(() => page.evaluate(() => {
    const { controls, surfaceAt } = window.__dbg, t = controls.target;
    return surfaceAt ? Math.abs(t.y - surfaceAt(t.x, t.z)) : 0;
  }), { timeout: 30_000 }).toBeLessThanOrEqual(0.001);
};
// Waits for the map to face north, however slowly the frames come.
const untilNorth = page => expect.poll(async () => Math.abs((await view(page)).az)).toBeLessThan(1e-6);
// The needle's turn in degrees, from its inline style (a CSS transform, never layout).
const needle = page => page.evaluate(() => {
  const m = document.querySelector('.north-open svg').style.transform.match(/^rotate\((-?[\d.]+)deg\)$/);
  return m ? Number(m[1]) : null;
});
const expectNorth = (now, before) => {
  expect(Math.abs(now.az)).toBeLessThan(1e-6);
  expect(now.polar).toBeCloseTo(before.polar, 6);
  expect(now.dist).toBeCloseTo(before.dist, 3);
  now.target.forEach((v, i) => expect(v).toBeCloseTo(before.target[i], 6));
};

test('the north button turns the map to face north, smoothly, and only the azimuth changes', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await groundSettled(page);
  await closeAbove(page);
  await turnTo(page, 2.5);
  const before = await view(page);
  expect(before.az).toBeCloseTo(2.5, 6);
  // A turn, not a jump: frames on the way, each closer to north, the short way (2.5 rad round, not 3.8 the other way).
  const seen = await pressAndSample(page, 1200);
  expect(seen.some(az => az > 0.05 && az < 2.45), seen.join(' ')).toBe(true);
  seen.slice(1).forEach((az, i) => expect(az).toBeLessThanOrEqual(seen[i] + 1e-9));
  expect(Math.min(...seen)).toBeGreaterThan(-1e-6);
  expectNorth(await view(page), before);
  // Damping does not take it further: still north a second later.
  await page.waitForTimeout(1000);
  expectNorth(await view(page), before);
  // Already north, the button stays where it was, the needle up.
  const box = await page.locator(NORTH).boundingBox();
  await page.locator(NORTH).click();
  await page.waitForTimeout(500);
  expectNorth(await view(page), before);
  expect(await page.locator(NORTH).boundingBox()).toEqual(box);
  expect(await needle(page)).toBe(0);
  expect(errors).toEqual([]);
});

test('the north button ends exactly north after a fling, and a drag cancels the turn', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await groundSettled(page);
  const box = await page.locator('#scene').boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  // A quick right-drag leaves the map spinning on (damping); the button straight after must still end at north.
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(cx + 260, cy, { steps: 3 });
  await page.mouse.up({ button: 'right' });
  const before = await view(page);
  await page.locator(NORTH).click();
  await untilNorth(page);
  await page.waitForTimeout(1000); // the fling's inertia would have turned it on by now
  const after = await view(page);
  expect(Math.abs(after.az)).toBeLessThan(1e-6);
  // The fling's own inertia may have moved the azimuth only: the place stays, the tilt is the one at the click.
  after.target.forEach((v, i) => expect(v).toBeCloseTo(before.target[i], 3));
  expect(after.polar).toBeCloseTo(before.polar, 3);

  // A drag starting during the turn stops it where it is: the map never reaches north. In the page, two frames into
  // the turn, so the pointer comes down mid-turn however slowly the frames come (a round trip from here can outlast
  // the half second). The left button moves the map, so the azimuth holds after it.
  await closeAbove(page);
  await turnTo(page, 2.5);
  const [atDown, held] = await page.evaluate(([sel, x, y]) => new Promise(done => {
    const az = () => window.__dbg.controls.getAzimuthalAngle(), canvas = document.getElementById('scene');
    const ptr = type => canvas.dispatchEvent(new PointerEvent(type, { pointerId: 1, pointerType: 'mouse', isPrimary: true,
      button: 0, buttons: type === 'pointerup' ? 0 : 1, clientX: x, clientY: y, bubbles: true }));
    document.querySelector(sel).click();
    requestAnimationFrame(() => requestAnimationFrame(() => {
      ptr('pointerdown');
      const at = az();
      setTimeout(() => { const now = az(); ptr('pointerup'); done([at, now]); }, 800);
    }));
  }), [NORTH, cx, cy]);
  expect(atDown).toBeLessThanOrEqual(2.5 + 1e-9);
  expect(atDown).toBeGreaterThan(0.3);
  expect(held).toBeCloseTo(atDown, 3);
  expect(errors).toEqual([]);
});

test('the N key faces north too, but not while typing or in a dialog', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await groundSettled(page);
  await turnTo(page, -2);
  const before = await view(page);
  await page.keyboard.press('n');
  await untilNorth(page);
  expectNorth(await view(page), before);

  // Typing: there is no search box yet (features.search is off), so a field like one stands in for it.
  await turnTo(page, -2);
  await page.evaluate(() => {
    const f = Object.assign(document.createElement('input'), { type: 'search', id: 'north-test-field' });
    document.body.append(f);
  });
  await page.locator('#north-test-field').focus();
  await page.keyboard.type('Norrmalm n');
  await page.waitForTimeout(700);
  await expect(page.locator('#north-test-field')).toHaveValue('Norrmalm n');
  expect((await view(page)).az).toBeCloseTo(-2, 6);
  // A dialog has the keys: About open, N does nothing.
  await page.locator('.about-open').click();
  await expect(page.locator('#about')).toBeVisible();
  await page.keyboard.press('n');
  await page.waitForTimeout(700);
  expect((await view(page)).az).toBeCloseTo(-2, 6);
  await page.keyboard.press('Escape');
  await expect(page.locator('#about')).toBeHidden();
  // With Ctrl or Cmd it is the browser's, not the map's.
  await page.locator('#year').click();
  await page.keyboard.press('ControlOrMeta+n').catch(() => {});
  await page.waitForTimeout(700);
  expect((await view(page)).az).toBeCloseTo(-2, 6);
  expect(errors).toEqual([]);
});

test('a viewer who asks for less motion is turned north at once', async ({ page }) => {
  const errors = watchErrors(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await groundSettled(page);
  await closeAbove(page);
  await turnTo(page, 2.5);
  const before = await view(page);
  // The first frame after the press is already north (a turn would still be at or near 2.5 there).
  const seen = await pressAndSample(page, 300);
  expect(seen.every(az => Math.abs(az) < 1e-6), seen.join(' ')).toBe(true);
  expectNorth(await view(page), before);
  expect(errors).toEqual([]);
});

test('the needle follows the map, and the button is a labelled stop on the keyboard', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await groundSettled(page);
  const button = page.locator(NORTH);
  await expect(button).toBeVisible();
  await expect(button).toHaveAttribute('aria-label', 'Face north');
  await expect(button).toHaveAttribute('title', 'Face north (N)');
  await expect(button).toHaveAttribute('aria-keyshortcuts', 'N');
  // The needle turns clockwise by the azimuth: facing west (the camera east of the place), north is to the right.
  for (const az of [Math.PI / 2, -1, 2.5]) {
    await turnTo(page, az);
    await expect.poll(() => needle(page)).toBeCloseTo(az * 180 / Math.PI, 0);
  }
  // Tab reaches it; Enter and Space press it.
  await page.locator('#year').click();
  let tabs = 0;
  while (!(await button.evaluate(b => b === document.activeElement)) && tabs++ < 20) await page.keyboard.press('Tab');
  await expect(button).toBeFocused();
  const before = await view(page);
  await page.keyboard.press('Enter');
  await untilNorth(page);
  expectNorth(await view(page), before);
  await expect.poll(() => needle(page)).toBe(0);
  await turnTo(page, -1);
  await page.keyboard.press('Space');
  await untilNorth(page);
  expectNorth(await view(page), before);
  expect(errors).toEqual([]);
});

// The label in Swedish. The language switch is off in the shipped config (features.lang), so this run turns it on in
// the page's own copy of the config, as the Swedish hint test above does.
test('the north button is labelled in Swedish too', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/stockholm.json')) return r;
      const config = await r.json();
      config.features = { ...config.features, lang: true };
      return new Response(JSON.stringify(config), { headers: { 'content-type': 'application/json' } });
    };
  });
  await page.goto('/?lang=sv');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(page.locator(NORTH)).toHaveAttribute('aria-label', 'Vänd mot norr');
  await expect(page.locator(NORTH)).toHaveAttribute('title', 'Vänd mot norr (N)');
  await page.locator('.lang [data-lang="en"]').click();
  await expect(page.locator(NORTH)).toHaveAttribute('aria-label', 'Face north');
  await expect(page.locator(NORTH)).toHaveAttribute('title', 'Face north (N)');
  expect(errors).toEqual([]);
});

// Review round 1, finding 1: a flight (flyTo: a quest, a note, a script) owns the camera until it lands. A press during
// one did turn the map for half a second, then the flight put it back in one frame. Now the flight wins: no turn, no
// jump. Pressed in the same task as the flight starts, then every frame for two seconds (a flight is 1.4 s).
test('the north button leaves a flight alone: no turn, and no jump back', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await closeAbove(page);
  await turnTo(page, 2.5);
  const { az0, seen } = await page.evaluate(() => new Promise(done => {
    const D = window.__dbg, c = D.controls, az0 = c.getAzimuthalAngle(), seen = [], t0 = performance.now();
    D.flyTo(c.target.x + 300, c.target.z - 200, null, 520);
    D.faceNorth();
    const step = () => {
      seen.push(c.getAzimuthalAngle());
      if (performance.now() - t0 < 2000) requestAnimationFrame(step); else done({ az0, seen });
    };
    requestAnimationFrame(step);
  }));
  const jumps = seen.slice(1).map((az, i) => Math.abs(az - seen[i]));
  expect(Math.max(...jumps), seen.join(' ')).toBeLessThan(0.3);
  expect(seen.at(-1)).toBeCloseTo(az0, 3);                 // where the flight faces: the way the map faced before
  expect(errors).toEqual([]);
});

// Review round 1, finding 3: the press stops the controls' glide (OrbitControls' damping), so the place and the tilt
// stay where they were at the press. A quick drag leaves the map gliding on; the press comes in the page, so no round
// trip lets the glide move it first. Without faceNorth's two lines that stop it, the place drifts and the tilt runs on.
test('the north button stops a glide: the place and the tilt stay where they were at the press', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await groundSettled(page);
  await turnTo(page, 1.2);
  const box = await page.locator('#scene').boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  const pressAndHold = () => page.evaluate(sel => new Promise(done => {
    const c = window.__dbg.controls;
    document.querySelector(sel).click();
    const at = { target: c.target.toArray(), polar: c.getPolarAngle() };
    setTimeout(() => done({ at, later: { target: c.target.toArray(), polar: c.getPolarAngle(), az: c.getAzimuthalAngle() } }), 1000);
  }), NORTH);
  // A quick left-drag: the place glides on.
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 220, cy + 120, { steps: 3 });
  await page.mouse.up();
  const pan = await pressAndHold();
  // the place: x and z (the target's height rides on the ground, followGround)
  [0, 2].forEach(i => expect(pan.later.target[i], `target[${i}]`).toBeCloseTo(pan.at.target[i], 3));
  expect(Math.abs(pan.later.az)).toBeLessThan(1e-6);
  // A quick diagonal right-drag: the map turns and tilts on (downwards, towards a view from above, away from the
  // controls' tilt limit, which would stop the glide by itself).
  await turnTo(page, 1.2);
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(cx + 160, cy + 140, { steps: 3 });
  await page.mouse.up({ button: 'right' });
  const tilt = await pressAndHold();
  expect(tilt.later.polar).toBeCloseTo(tilt.at.polar, 4);
  [0, 2].forEach(i => expect(tilt.later.target[i], `target[${i}]`).toBeCloseTo(tilt.at.target[i], 3));
  expect(Math.abs(tilt.later.az)).toBeLessThan(1e-6);
  expect(errors).toEqual([]);
});

// Review round 1, finding 2: on a touch screen the top-right buttons take a tap a little outside their drawn edge (a
// wider hit area on a coarse pointer, ::after), so a 28 px button is a 44 px target; what is drawn stays the same size.
test('on a touch screen the top-right buttons take a tap just outside their edge, at the same drawn size', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
  const hits = await page.evaluate(() => ['.north-open', '.look-open', '.about-open', '.postcard-open'].map(sel => {
    const b = document.querySelector(sel), r = b.getBoundingClientRect(), x = r.left + r.width / 2;
    const at = y => document.elementFromPoint(x, y)?.closest('button') === b;
    return { sel, above: at(r.top - 7), below: at(r.bottom + 7), size: [Math.round(r.width), Math.round(r.height)] };
  }));
  for (const h of hits) expect(h, h.sel).toMatchObject({ above: true, below: true });
  expect(hits[0].size).toEqual([28, 28]);
  expect(hits[1].size[1]).toBe(28);
  expect(hits[3].size).toEqual([28, 28]);                          // the postcard's camera, drawn as north is
  // A tap just under the north button turns the map.
  await turnTo(page, 2);
  const north = await page.locator(NORTH).boundingBox();
  await page.touchscreen.tap(north.x + north.width / 2, north.y + north.height + 6);
  await untilNorth(page);
  expect(errors).toEqual([]);
  await context.close();
});

// The title over the count ("Today") is set tight (line-height .85), so its descenders hang below its line box: the y of
// "Today" once sat on "buildings" (coordinator, 2026-10-15). Measured on the ink, not the boxes: each line's baseline
// from a zero-size probe sitting on it, and the glyphs' own depth and height from the canvas text metrics in the same
// font. The lowest ink of the title must stay at least TALLY_GAP px above the highest ink of the count line, for every
// title the map can show (web/count.js tallyTitle, English and Swedish, a period's name on two lines), in every look,
// on a desktop and on a phone.
const TALLY_GAP = 3;
const tallyGaps = (page, titles) => page.evaluate(async titles => {
  const year = document.getElementById('year'), count = document.querySelector('.tally-count');
  const font = getComputedStyle(document.documentElement).getPropertyValue('--font').trim();
  await document.fonts.load(`800 64px ${font}`);
  await document.fonts.load(`400 14px ${font}`);
  const ctx = document.createElement('canvas').getContext('2d');
  // Measured in the look's own font, never a fallback with other metrics (review round 1): a font that has not loaded
  // stops the test instead.
  // The glyphs' height and depth are read off their painted ink, drawn at SCALE times the size and scaled back (a tenth
  // of a pixel). Not from measureText: on Linux headless Chromium its actualBoundingBox values come back whole-pixel
  // even at SCALE, and for the "g" of "1900–i dag" at 64px it reported a descent of 14 px where the ink (in the canvas
  // and on the page) ends at 13.05: the 2.5 px "gap" on Linux in PR #2 was that pixel. macOS paints what it reports.
  const SCALE = 10;
  const metrics = (el, text) => {
    const cs = getComputedStyle(el);
    ctx.font = `${cs.fontWeight} ${parseFloat(cs.fontSize) * SCALE}px ${cs.fontFamily}`;
    if (!document.fonts.check(ctx.font)) throw new Error(ctx.font);
    const size = parseFloat(cs.fontSize) * SCALE;
    const w = Math.ceil(ctx.measureText(text).width + size), h = Math.ceil(size * 3), base = Math.round(size * 2);
    ctx.canvas.width = w; ctx.canvas.height = h; // resets the context, so the font is set again
    ctx.font = `${cs.fontWeight} ${size}px ${cs.fontFamily}`;
    ctx.fillText(text, size / 2, base);
    const px = ctx.getImageData(0, 0, w, h).data;
    const inked = y => { for (let x = 0; x < w; x++) if (px[(y * w + x) * 4 + 3]) return true; return false; };
    let top = 0, bottom = h - 1;
    while (top < h && !inked(top)) top++;
    while (bottom >= 0 && !inked(bottom)) bottom--;
    if (top > bottom) throw new Error(`no ink: ${text}`);
    return { actualBoundingBoxAscent: (base - top) / SCALE, actualBoundingBoxDescent: (bottom + 1 - base) / SCALE };
  };
  // The baseline of the line the probe lands on: the title's last line, the count's first.
  const baseline = (el, first) => {
    const probe = document.createElement('span');
    probe.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline';
    if (first) el.prepend(probe); else el.append(probe);
    const y = probe.getBoundingClientRect().bottom;
    probe.remove();
    return y;
  };
  const was = [year.textContent, year.className];
  const out = titles.map(([text, named]) => {
    year.textContent = text;
    year.classList.toggle('named', named);
    const low = baseline(year, false) + metrics(year, text).actualBoundingBoxDescent;
    const high = baseline(count, true) - metrics(count, count.textContent).actualBoundingBoxAscent;
    return { text, gap: Math.round((high - low) * 10) / 10 };
  });
  [year.textContent, year.className] = was;
  return out;
}, titles);

test('the title over the count never touches the count line, in every look, on a desktop and a phone', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const config = await cityConfig(page);
  const names = config.periods.map(p => p.label);
  const titles = [['Today', false], ['1890–1919', false], ['1900–Today', false], ['until 1900', false], ['1950', false],
    ['I dag', false], ['1900–i dag', false], ['fram till 1900', false], ...names.map(n => [n, true])];
  const look = page.locator('.look-open'), panel = page.locator('#look');
  const bad = [];
  for (const id of Object.keys(THEMES)) {
    await look.click();
    await panel.locator(`.look-card[data-look="${id}"]`).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', id);
    await page.keyboard.press('Escape');
    for (const [device, size] of [['desktop', { width: 1400, height: 900 }], ['narrow desktop', { width: 900, height: 700 }],
      ['phone', { width: 390, height: 844 }]]) {
      await page.setViewportSize(size);
      for (const { text, gap } of await tallyGaps(page, titles)) if (gap < TALLY_GAP) bad.push(`${id}, ${device}, "${text}": ${gap} px`);
    }
    await page.setViewportSize({ width: 1400, height: 900 });
  }
  expect(bad).toEqual([]);
  // The north button and the others stay under the count, clear of it.
  const countBox = await page.locator('.tally-count').boundingBox(), north = await page.locator('.north-open').boundingBox();
  expect(north.y).toBeGreaterThanOrEqual(countBox.y + countBox.height);
  expect(errors).toEqual([]);
});

// Review round 1, finding 7: in Classic the count read "77 , 743". Its font (Schibsted Grotesk) has tabular forms of the
// comma and the full stop as wide as a figure, and the counts asked for tabular figures. Measured as drawn: a grouped
// number in the count line, a legend count and a card value, each glyph's width from a Range. The comma must be much
// narrower than the figure before it, in every look.
test('a count\'s thousands comma is drawn narrow in every look, never as wide as a figure', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const look = page.locator('.look-open'), panel = page.locator('#look');
  const bad = [];
  for (const id of Object.keys(THEMES)) {
    await look.click();
    await panel.locator(`.look-card[data-look="${id}"]`).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', id);
    await page.keyboard.press('Escape');
    const widths = await page.evaluate(async () => {
      const font = getComputedStyle(document.documentElement).getPropertyValue('--font').trim();
      await document.fonts.load(`400 14px ${font}`);
      const card = Object.assign(document.createElement('div'), { className: 'card', innerHTML: '<dl><dd></dd></dl>' });
      document.body.append(card);
      const places = { count: document.getElementById('count'), legend: document.querySelector('#panel-body .swatch .n'),
        card: card.querySelector('dd') };
      const out = {};
      for (const [name, el] of Object.entries(places)) {
        // Drawn at ten times its size for the measurement: Linux headless Chromium gives whole-pixel glyph widths, and at
        // a legend's size a figure is about 4 px. The ratio of comma to figure is the font's, so the check is unchanged.
        const was = el.textContent, size = el.style.fontSize;
        el.style.fontSize = `${parseFloat(getComputedStyle(el).fontSize) * 10}px`;
        el.textContent = '77,743';
        const r = document.createRange(), w = i => { r.setStart(el.firstChild, i); r.setEnd(el.firstChild, i + 1); return r.getBoundingClientRect().width; };
        out[name] = { seven: w(1), comma: w(2) };
        el.textContent = was;
        el.style.fontSize = size;
      }
      card.remove();
      return out;
    });
    for (const [name, { seven, comma }] of Object.entries(widths)) {
      if (!(comma > 0 && comma <= 0.6 * seven)) bad.push(`${id}, ${name}: comma ${comma.toFixed(2)} px, 7 ${seven.toFixed(2)} px`);
    }
  }
  expect(bad).toEqual([]);
  expect(errors).toEqual([]);
});
