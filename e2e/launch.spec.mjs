// The pre-launch audit's fixes (docs/research/2026-10-17-launch-audit.md): no WebGL (finding 2), optional files that
// fail (3), a card from the keyboard (1), a card shard that fails (6), the loading line as a live region (7), the
// legend's accessible names (8), the zoom keys (9) and the icons (10). Runs on whatever web/data/current.json names.
import { test, expect } from '@playwright/test';

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
const frames = page => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));

test('without WebGL the page says plainly that the map needs it, in English and in Swedish', async ({ page }) => {
  await page.addInitScript(() => {
    const get = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      return /webgl/.test(type) ? null : get.call(this, type, ...rest);
    };
  });
  await page.goto('/?lang=en');
  const loading = page.locator('#loading');
  await expect(loading).toHaveText('This map needs WebGL, which this browser has turned off or does not support.',
    { timeout: 30_000 });
  await expect(loading).toHaveAttribute('role', 'alert');
  await expect(loading).not.toContainText('Reload');
  await page.goto('/?lang=sv');
  await expect(loading).toHaveText('Kartan kräver WebGL, som är avstängt eller saknas i den här webbläsaren.',
    { timeout: 30_000 });
});

for (const file of ['labels.json', 'land.bin.gz', 'water.bin.gz', 'terrain.bin.gz']) {
  test(`a failed ${file} leaves a working map without the fatal message`, async ({ page }) => {
    let asked = false;
    await page.route(`**/${file}`, r => { asked = true; return r.abort(); });
    const warned = [];
    page.on('console', m => { if (m.type() === 'warning') warned.push(m.text()); });
    await open(page);
    await page.waitForTimeout(1500);                                 // the deferred files are asked after the first frame
    await expect(page.locator('#loading')).toBeHidden();
    // the flat land is asked only for a build without terrain, or after the terrain failed
    if (asked) expect(warned.join('\n')).toMatch(/did not load/);
  });
}

test('a pack that fails is fatal: the map cannot run without its buildings', async ({ page }) => {
  await page.route('**/pack0.bin.gz', r => r.abort());
  await page.goto('/');
  const loading = page.locator('#loading');
  await expect(loading).toHaveText('Could not load the city data. Reload the page to try again.', { timeout: 60_000 });
  await expect(loading).toHaveAttribute('role', 'alert');
});

test('the loading line is a polite live region that announces start, done and failure, never each percent', async ({ page }) => {
  await page.goto('/');
  const loading = page.locator('#loading');
  await expect(loading).toHaveAttribute('role', 'status');
  await expect(loading).toHaveAttribute('aria-live', 'polite');
  await expect(page.locator('#progress')).toHaveAttribute('aria-hidden', 'true');
  await expect(loading).toBeHidden({ timeout: 60_000 });
  await expect(page.locator('#ready')).toHaveText('The map is ready.');
  await expect(page.locator('#ready')).toHaveAttribute('role', 'status');
});

test('Tab reaches the map; Enter there pins the building at the centre of the screen, Esc gives the map back', async ({ page }) => {
  await open(page);
  // the home view looks at Gamla stan: put a building at the centre first
  const gid = await page.evaluate(async () => {
    const D = window.__dbg;
    for (let g = 0; g < 50000; g++) {
      const b = D.building(g);
      if (b && b.yflag !== 7 && b.height > 12) { await new Promise(r => D.flyTo(b.x, b.z, r, 300)); return g; }
    }
    return -1;
  });
  await frames(page);
  const canvas = page.locator('#scene');
  await expect(canvas).toHaveAttribute('tabindex', '0');
  await canvas.focus();
  await expect(page.locator('.crosshair')).toBeVisible();
  const centre = await page.evaluate(() => window.__dbg.pick(innerWidth / 2, innerHeight / 2));
  expect(centre).toBeGreaterThanOrEqual(0);
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned)).toBe(centre);
  await expect(page.locator('.card-close')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(canvas).toBeFocused();
  expect(gid).toBeGreaterThanOrEqual(0);
});

test('+ and - zoom the map from the keyboard; the how-to line says so', async ({ page }) => {
  await open(page);
  const dist = () => page.evaluate(() => window.__dbg.camera.position.distanceTo(window.__dbg.controls.target));
  const d0 = await dist();
  await page.locator('#scene').focus();
  await page.keyboard.press('+');
  await expect.poll(dist).toBeLessThan(d0 * 0.95);
  const d1 = await dist();
  await page.keyboard.press('-');
  await page.keyboard.press('-');
  await expect.poll(dist).toBeGreaterThan(d1 * 1.2);
  await expect(page.locator('.howto')).toContainText('+ / −');
  // never while typing
  const d2 = await dist();
  await page.getByRole('combobox').focus();
  await page.keyboard.press('-');
  await page.waitForTimeout(200);
  expect(await dist()).toBeCloseTo(d2, 0);
});

test('a card whose details failed to load says so, not that no record dates the building', async ({ page }) => {
  let asked = 0;
  await page.route('**/cards/*.json', r => { asked++; return r.abort(); });
  await open(page);
  const gid = await page.evaluate(() => {
    for (let g = 0; g < 50000; g++) { const b = window.__dbg.building(g); if (b && b.yflag === 7) return g; }
    return -1;
  });
  test.skip(gid < 0, 'this build has no building without a year');
  await page.evaluate(g => window.__dbg.pinCard(g, 400, 300), gid);
  const card = page.locator('#card');
  await expect(card).toContainText("Could not load this building's details. Close the card and open it again to retry.");
  await expect(card).not.toContainText('No open record dates this building yet');
  await expect(card).toContainText('Height');                     // what the map itself knows stays
  // the failed shard is not asked again and again while the card is open (fix-wave review), only when it is reopened
  const n = asked;
  await page.waitForTimeout(1500);
  expect(asked).toBe(n);
  await page.evaluate(g => { window.__dbg.pinCard(-1); window.__dbg.pinCard(g, 400, 300); }, gid);
  await expect.poll(() => asked).toBeGreaterThan(n);
});

test('a lost WebGL context says so, and the message goes when the context comes back', async ({ page }) => {
  await open(page);
  await page.evaluate(() => { window.__lose = window.__dbg.renderer.getContext().getExtension('WEBGL_lose_context'); window.__lose.loseContext(); });
  const loading = page.locator('#loading');
  await expect(loading).toContainText('Reload the page to draw it again');
  await page.evaluate(() => window.__lose.restoreContext());
  await expect(loading).toBeHidden();
  await expect(loading).toHaveAttribute('role', 'status');
});

test('the legend buttons read their period and count as words', async ({ page }) => {
  await open(page);
  const names = await page.locator('.swatch[data-i]').evaluateAll(els => els.map(el => el.getAttribute('aria-label')));
  expect(names.length).toBeGreaterThan(5);
  for (const n of names) expect(n).toMatch(/^.+, [\d  ,]+ buildings$/);
  await expect(page.getByRole('button', { name: names[0], exact: true })).toHaveCount(1);
  // the counts follow the timeline, and the names with them
  const from = page.getByRole('slider', { name: 'Start year' });
  await from.focus();
  for (let i = 0; i < 6; i++) await page.keyboard.press('PageUp');
  await expect.poll(() => page.locator('.swatch[data-i]').evaluateAll(els => els.map(el => el.getAttribute('aria-label'))))
    .not.toEqual(names);
});

test('the page has an SVG favicon and an apple-touch-icon that load', async ({ page, request }) => {
  await page.goto('/');
  const icon = await page.locator('link[rel="icon"]').getAttribute('href');
  const touch = await page.locator('link[rel="apple-touch-icon"]').getAttribute('href');
  expect(icon).toBe('favicon.svg');
  expect(touch).toBe('apple-touch-icon.png');
  const svg = await request.get('/' + icon);
  expect(svg.ok()).toBe(true);
  expect(await svg.text()).toContain('<svg');
  const png = await request.get('/' + touch);
  expect(png.ok()).toBe(true);
  expect((await png.body()).subarray(1, 4).toString()).toBe('PNG');
});
