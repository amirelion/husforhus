// The history-scene player (web/scene-player.js) on the fixture build: ?scene=vasa-1628 opens the Vasa at 1628 with
// its first caption, the arrow keys step to the last beat, and Esc puts the map back as it was.
import { test, expect } from '@playwright/test';

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}
const across = page => page.evaluate(() => { const p = window.__dbg.camera.position; return [Math.round(p.x), Math.round(p.z)]; });
// The ground rises after the first frame and the camera rides on it: wait until it stands still.
async function settle(page) {
  await expect.poll(async () => {
    const a = await across(page);
    await page.waitForTimeout(300);
    return JSON.stringify(a) === JSON.stringify(await across(page));
  }, { timeout: 30_000 }).toBe(true);
}

// Scenes are off in the shipped config (features.scenes); these runs turn them on in the page's own copy of it.
function scenesOn(page, on = true) {
  return page.addInitScript(on => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/stockholm.json')) return r;
      const config = await r.json();
      config.features = { ...config.features, scenes: on };
      return new Response(JSON.stringify(config), { headers: { 'content-type': 'application/json' } });
    };
  }, on);
}

test('with scenes off, the Stories button is hidden and ?scene= is ignored', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/?scene=vasa-1628');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(page.locator('.stories-open')).toBeHidden();
  await page.waitForTimeout(1000);
  await expect(page.locator('.sp-warning')).toBeHidden();
  await expect(page.locator('.sp-cinema')).toBeHidden();
  expect(errors).toEqual([]);
});

test('?scene=vasa-1628 plays the Vasa at 1628, steps to its last beat, and Esc restores the map', async ({ page }) => {
  const errors = watchErrors(page);
  await scenesOn(page);
  const vasa = await (await page.request.get('scenes/vasa-1628.json')).json();

  // the map as it stands without a scene
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await settle(page);
  const home = await across(page);
  const yearText = await page.locator('#year').textContent();
  const to = page.locator('.grip-to');
  const toBefore = await to.getAttribute('aria-valuenow');

  await page.goto('/?scene=vasa-1628');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  // a sensitive scene asks first; Skip has the focus
  const warning = page.locator('.sp-warning');
  await expect(warning).toBeVisible();
  await expect(page.locator('.sp-warn-skip')).toBeFocused();
  await page.locator('.sp-warn-go').click();

  const cinema = page.locator('.sp-cinema');
  await expect(cinema).toBeVisible();
  await expect(page.locator('.sp-year')).toHaveText('1628');
  await expect(page.locator('.sp-caption')).toHaveText(vasa.beats[0].caption.en);
  await expect(page.locator('.sp-source')).toContainText(vasa.beats[0].sources[0]);
  await expect(page.locator('.sp-tick')).toHaveCount(8);
  await expect(page.locator('.sp-count')).toContainText('1 / 8');
  await expect(page.locator('.sp-count')).toContainText('remaining');
  await expect(page.locator('.sp-play')).toBeFocused();
  // the timeline itself is at the scene's year, and the viewer's panels have stepped aside
  await expect(to).toHaveAttribute('aria-valuenow', '1628');
  await expect(page.locator('.panel')).toBeHidden();
  await expect(page.locator('.sp-mover')).toHaveCount(1);
  await expect(page.locator('.sp-pin:not(.sp-ghost)')).toHaveCount(7);

  for (let i = 0; i < 7; i++) await page.keyboard.press('ArrowRight');
  await expect(page.locator('.sp-count')).toContainText('8 / 8');
  await expect(page.locator('.sp-caption')).toHaveText(vasa.beats[7].caption.en);
  // the camera flew to the last beat: well away from the home view
  await expect.poll(async () => {
    const [x, z] = await across(page);
    return Math.hypot(x - home[0], z - home[1]);
  }).toBeGreaterThan(200);

  await page.keyboard.press('Escape');
  await expect(cinema).toBeHidden();
  await expect(page.locator('.panel')).toBeVisible();
  await expect(to).toHaveAttribute('aria-valuenow', toBefore);
  await expect(page.locator('#year')).toHaveText(yearText);
  await expect(page.locator('.sp-pin')).toHaveCount(0);
  expect(new URL(page.url()).searchParams.has('scene')).toBe(false);
  await settle(page);
  expect(await across(page)).toEqual(home);
  expect(errors).toEqual([]);
});

test('a 1912 beat with a photo shows it from the site itself, with its alt text and a linked credit', async ({ page }) => {
  const errors = watchErrors(page);
  await scenesOn(page);
  const s10 = await (await page.request.get('scenes/s10-olympics-1912.json')).json();
  const photo = s10.beats[0].photo;
  await page.goto('/?scene=s10-olympics-1912');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await page.locator('.sp-warn-go').click();
  const img = page.locator('.sp-photo img');
  await expect(img).toBeVisible();
  await expect(img).toHaveAttribute('alt', photo.caption.en);
  expect(new URL(await img.evaluate(i => i.currentSrc)).origin).toBe(new URL(page.url()).origin);
  await expect.poll(() => img.evaluate(i => i.complete && i.naturalWidth)).toBeGreaterThan(0);
  const credit = page.locator('.sp-photo-credit');
  await expect(credit).toHaveText(`Photo: ${photo.credit.author}, ${photo.credit.licence}, Wikimedia Commons`);
  await expect(credit).toHaveAttribute('href', photo.credit.page);
  // a beat without a photo hides the card
  const plain = s10.beats.findIndex(b => !b.photo);
  for (let i = 0; i < plain; i++) await page.keyboard.press('ArrowRight');
  await expect(page.locator('.sp-photo')).toBeHidden();
  expect(errors).toEqual([]);
});
