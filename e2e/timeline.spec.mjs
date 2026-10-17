// The timeline: the handles as keyboard sliders that never move the map, the legend's numbers
// following the range, and the landmark labels that fly to their building.
import { test, expect } from '@playwright/test';

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}
const config = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  return (await fetch(`data/${version}/stockholm.json`)).json();
});
const camera = page => page.evaluate(() => window.__dbg.camera.position.toArray().map(v => Math.round(v)));

test('the handles are sliders: keys move the years, read them out, and never move the map', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const cfg = await config(page);
  const to = page.locator('.grip-to'), from = page.locator('.grip-from');
  await expect(to).toHaveAttribute('role', 'slider');
  await expect(to).toHaveAttribute('aria-valuetext', 'Today');
  await expect(from).toHaveAttribute('aria-valuetext', 'No start year');
  // each handle's bounds stop a year short of the other's (the to-handle from the oldest building on)
  await expect(to).toHaveAttribute('aria-valuemin', String(cfg.yearMin));
  await expect(from).toHaveAttribute('aria-valuemax', String(cfg.yearMax - 1));
  // The ground rises after the first frame and the camera rides on it: wait until it stands still.
  await expect.poll(async () => {
    const a = await camera(page);
    await page.waitForTimeout(300);
    return JSON.stringify(a) === JSON.stringify(await camera(page));
  }, { timeout: 30_000 }).toBe(true);
  const before = await camera(page);
  await to.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(to).toHaveAttribute('aria-valuenow', String(cfg.yearMax - 1));
  await expect(page.locator('#year')).toHaveText(String(cfg.yearMax - 1));
  await expect(from).toHaveAttribute('aria-valuemax', String(cfg.yearMax - 2));
  await page.keyboard.press('Shift+ArrowLeft');
  await page.keyboard.press('PageDown');
  await expect(to).toHaveAttribute('aria-valuetext', String(cfg.yearMax - 21));
  // the arrows went to the slider, not the map: a map's arrow key moves the camera across (x and z), while the ground
  // it rides on can still lift it (y) on a slow machine
  const across = p => [p[0], p[2]];
  expect(across(await camera(page))).toEqual(across(before));
  await page.keyboard.press('End');
  await expect(to).toHaveAttribute('aria-valuetext', 'Today');
  // the from-handle: a year away from rest, and Home puts it back at rest
  await from.focus();
  await page.keyboard.press('ArrowRight');
  await expect(from).not.toHaveAttribute('aria-valuetext', 'No start year');
  // off its rest the from-handle sets the to-handle's lower bound: a year after its own
  const fromNow = Number(await from.getAttribute('aria-valuenow'));
  await expect(to).toHaveAttribute('aria-valuemin', String(fromNow + 1));
  await expect(page.locator('#year')).toHaveText(/–Today$/);
  await page.keyboard.press('Home');
  await expect(from).toHaveAttribute('aria-valuetext', 'No start year');
  await expect(page.locator('#year')).toHaveText('Today');
  expect(errors).toEqual([]);
});

test('the legend counts each period within the range', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const n = i => page.locator(`.swatch[data-i="${i}"] .n`).innerText().then(s => Number(s.replace(/\D/g, '')));
  const funkis = await n(7);
  test.skip(funkis === 0, 'this build has no Funkis building');
  await page.locator('.grip-to').focus();
  for (let k = 0; k < 20; k++) await page.keyboard.press('PageDown');      // back to well before 1930
  await expect.poll(() => n(7)).toBe(0);
  await page.keyboard.press('End');
  await expect.poll(() => n(7)).toBe(funkis);
  expect(errors).toEqual([]);
});

test('a landmark label on the timeline flies to its building and opens its card', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const labels = await page.evaluate(() => window.__dbg.timelineLabels);
  test.skip(!labels.length, 'this build has no timeline landmark');
  const L = labels[0];
  const box = await page.locator('#hist').boundingBox();
  await page.mouse.click(box.x + (L.x0 + L.x1) / 2, box.y + 6);
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(L.gid);
  await expect(page.locator('#card.pinned h3')).toHaveText(L.name);
  expect(errors).toEqual([]);
});

test('with reduced motion the fly-to sets the camera at once', async ({ page }) => {
  // A landmark label's flight always swept the camera for 1.4 s
  const errors = watchErrors(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const after = await page.evaluate(() => {
    let done = false;
    window.__dbg.flyTo(120, -80, () => { done = true; });
    const t = window.__dbg.controls.target;
    return { x: Math.round(t.x), z: Math.round(t.z), done };
  });
  expect(after).toEqual({ x: 120, z: -80, done: true });
  expect(errors).toEqual([]);
});

test('a handle grabbed by its knob drags, even on a landmark\'s label, and its year names the landmark', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const labels = await page.evaluate(() => window.__dbg.timelineLabels);
  const cfg = await config(page);
  // a label before the timeline's end, whose year the to-handle can stand on and name (at the end it reads "Today")
  const L = labels.filter(l => l.year < cfg.yearMax).at(-1);
  test.skip(!L, 'this build has no timeline landmark before the end');
  const to = page.locator('.grip-to');
  await to.focus();
  await page.keyboard.press('End');
  let y = cfg.yearMax;                                                             // the to-handle on its year:
  for (; y - 10 >= L.year; y -= 10) await page.keyboard.press('PageDown');        // ten years a press,
  for (; y > L.year; y--) await page.keyboard.press('ArrowLeft');                // then one
  // its name among the year's landmarks (two can share a year)
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  await expect(to).toHaveAttribute('aria-valuetext', new RegExp(`^${L.year}, (.+, )?${esc(L.name)}(, .+)?$`));
  await expect(page.locator('.tally')).toHaveAttribute('aria-live', 'off');         // the slider speaks, the title waits
  const box = await page.locator('#hist').boundingBox();
  const x = box.x + await page.evaluate(() => {
    const g = document.querySelector('.grip-to'), h = document.getElementById('hist').getBoundingClientRect();
    return g.getBoundingClientRect().left + g.getBoundingClientRect().width / 2 - h.left;
  });
  await page.mouse.move(x, box.y + 6);                                              // the knob, on the label
  await page.mouse.down();
  await page.mouse.move(x - 80, box.y + 6, { steps: 8 });
  await page.mouse.up();
  expect(await page.evaluate(() => Math.round(window.__dbg.uniforms.uYear.value))).toBeLessThan(L.year);
  expect(await page.evaluate(() => window.__dbg.pinned)).toBe(-1);                 // no flight, no card
  expect(errors).toEqual([]);
});

