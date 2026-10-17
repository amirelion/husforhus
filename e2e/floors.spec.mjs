// Floors mode (Plan 4a, Task 11): the look's own ramp on the map and in the legend, where the floors come from, and
// the ramp following a look switch.
import { test, expect } from '@playwright/test';
import { THEMES } from '../web/themes.js';

const hexToRgb = h => `rgb(${[1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)).join(', ')})`;
// the legend's gradient as the browser computes it: the four colours in order, at the shader's stops
const gradient = floors => `linear-gradient(90deg, ${floors.map((c, i) => `${hexToRgb(c)} ${[0, 33, 66, 100][i]}%`).join(', ')})`;
// how many pixels of the page read as magenta (red and blue well above green)
const magenta = async page => page.evaluate(async b64 => {
  const img = new Image();
  img.src = `data:image/png;base64,${b64}`;
  await img.decode();
  const g = new OffscreenCanvas(img.width, img.height).getContext('2d');
  g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, img.width, img.height).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i] - d[i + 1] > 80 && d[i + 2] - d[i + 1] > 80) n++;
  return n;
}, (await page.screenshot()).toString('base64'));

test('Floors draws the look\'s ramp, says where the floors come from, and follows a look switch', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto('/?theme=arg');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const cfg = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    return (await fetch(`data/${version}/stockholm.json`)).json();
  });
  await page.locator('.modes button[data-mode="1"]').click();
  const ramp = page.locator('#panel-body .ramp');
  const bg = () => ramp.evaluate(el => getComputedStyle(el).backgroundImage);
  for (const c of THEMES.arg.floors) expect(await bg()).toContain(hexToRgb(c));
  expect(await bg()).toBe(gradient(THEMES.arg.floors));
  const shader = await page.evaluate(() => window.__dbg.uniforms.uFloors.value.map(c => '#' + c.getHexString()));
  expect(shader).toEqual(THEMES.arg.floors);
  // the scale's labels stand on the same log scale as the colours: n floors at log n / log 40 of the bar, each label
  // shifted left by that share of its own width (so the end ones stay under the bar)
  const off = await page.evaluate(() => {
    const bar = document.querySelector('#panel-body .ramp').getBoundingClientRect();
    return [...document.querySelectorAll('#panel-body .ramp-scale span')].map((el, i) => {
      const r = el.getBoundingClientRect(), p = Math.log([1, 3, 8, 20, 40][i]) / Math.log(40);
      return Math.abs(r.left - (bar.left + p * (bar.width - r.width)));
    });
  });
  expect(off).toHaveLength(5);
  off.forEach(d => expect(d).toBeLessThan(1));
  // the map draws from uFloors: with every stop magenta the buildings turn magenta, and back again
  expect(await magenta(page)).toBeLessThan(100);
  await page.evaluate(() => window.__dbg.uniforms.uFloors.value.forEach(c => c.set('#ff00ff')));
  await expect.poll(() => magenta(page), { timeout: 10_000 }).toBeGreaterThan(2_000);
  await page.evaluate(floors => window.__dbg.uniforms.uFloors.value.forEach((c, i) => c.set(floors[i])), THEMES.arg.floors);
  const note = page.locator('#panel-body .note');
  if (cfg.stats.floorsOsm) {
    await expect(note).toHaveText(`${cfg.stats.floorsOsm.toLocaleString('en')} buildings take their floors from OpenStreetMap; ` +
      `the other ${cfg.stats.floorsHeight.toLocaleString('en')} are estimated from their height (≈).`);
  } else {
    await expect(note).toHaveText('Floors are estimated from each building\'s height (≈).');
  }
  // a look switch recolours the ramp in place and the shader with it
  await page.locator('.look-open').click();
  await page.locator('.look-card', { hasText: 'Blå timmen' }).click();
  for (const c of THEMES.blatimme.floors) expect(await bg()).toContain(hexToRgb(c));
  expect(await bg()).toBe(gradient(THEMES.blatimme.floors));
  expect(await page.evaluate(() => window.__dbg.uniforms.uFloors.value.map(c => '#' + c.getHexString())))
    .toEqual(THEMES.blatimme.floors);
  expect(errors).toEqual([]);
});
