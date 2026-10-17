// The legend's "Highlight buildings with a photo" switch: on, every building whose card has no photo fades to the maquette
// (the shader reads a per-building flag written once per tile, web/panel.js markPhotos); a photo building keeps its
// colour and its card still opens with the photo; the choice is kept in the URL. Runs on whatever web/data/current.json
// names: the fixture in CI, the whole city on a laptop.
import { test, expect } from '@playwright/test';

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}

// The photo flag the shader reads for gid g (null: in no loaded tile) and whether the switch's uniform is on.
const state = (page, g) => page.evaluate(gid => {
  const d = window.__dbg;
  for (const m of d.meshes) {
    const a = m.material.uniforms.uAttr.value.image.data;
    for (let b = 0; b < m.userData.nB; b++) if (a[b * 12 + 3] === gid) return { flag: a[b * 12 + 9], on: d.uniforms.uPhotoOnly.value };
  }
  return { flag: null, on: d.uniforms.uPhotoOnly.value };
}, g);

test('the photo switch fades the buildings without a photo, keeps the URL and the photo card', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await open(page);
  const { photo, plain } = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    const gids = await (await fetch(`data/${version}/photo-gids.json`)).json();
    const n = (await (await fetch(`data/${version}/stockholm.json`)).json()).stats.buildings;
    const set = new Set(gids);
    let plain = -1;
    for (let g = 0; g < n && plain < 0; g++) if (!set.has(g)) plain = g;
    return { photo: gids[0], plain };
  });
  test.skip(photo === undefined, 'this build has no card with a photo');

  const sw = page.locator('#photo-only');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  expect((await state(page, photo)).on).toBe(0);
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => state(page, photo)).toEqual({ flag: 1, on: 1 });   // stays coloured
  expect(await state(page, plain)).toEqual({ flag: 0, on: 1 });              // fades
  expect(new URL(page.url()).searchParams.get('photos')).toBe('1');
  await page.screenshot({ path: 'data/test-results/photos-desktop.png' });

  // a photo building's card opens with its photo, as without the switch
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), photo);
  await expect(page.locator('#card.pinned .photo img')).toBeVisible();
  await page.keyboard.press('Escape');

  // off restores everything
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  expect((await state(page, plain)).on).toBe(0);
  expect(new URL(page.url()).searchParams.has('photos')).toBe(false);
  expect(errors).toEqual([]);
});

test('?photos=1 opens with the switch on, in Swedish too, on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '?photos=1&lang=sv');
  const sw = page.locator('#photo-only');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect(sw).toContainText('Markera hus med foto');
  await expect(page.locator('#photo-hint')).not.toHaveAttribute('hidden');   // the legend sheet itself starts folded on a phone
  await expect(page.locator('#photo-hint')).toContainText('Övriga hus blir bleka');
  await expect.poll(() => page.evaluate(() => window.__dbg.uniforms.uPhotoOnly.value)).toBe(1);
  await page.locator('.sheet-handle').click().catch(() => {});   // open the legend sheet for the screenshot
  await page.screenshot({ path: 'data/test-results/photos-phone.png' });
});
