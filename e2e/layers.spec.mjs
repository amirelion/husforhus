// The map's layer switches live in the Look panel under "Show on the map" (web/switcher.js), not in the legend.
// ?metro=1, ?plaques=1 and ?photos=1 still switch them on; while one is on, a dot on the closed Look button says so.
import { test, expect } from '@playwright/test';

test('the URL parameters switch the layers on, the Look button shows a dot, switching them off removes it', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/?metro=1&plaques=1&photos=1');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const ids = ['#metro-on', '#plaques-on', '#photo-only'];
  const present = [];
  for (const id of ids) if (await page.locator(id).count()) present.push(id);
  expect(present).toContain('#photo-only');
  await expect(page.locator('#panel #photo-only, #panel #plaques-on, #panel #metro-on')).toHaveCount(0);   // not in the legend
  for (const id of present) await expect(page.locator(`#look ${id}`)).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.look-dot')).toBeVisible();

  await page.locator('.look-open').click();
  await expect(page.locator('#look')).toBeVisible();
  await expect(page.locator('#layers-title')).toHaveText('Show on the map');
  await expect(page.locator('.look-dot')).toBeHidden();   // the open panel shows the switches themselves
  for (const id of present) {
    await page.locator(id).click();
    await expect(page.locator(id)).toHaveAttribute('aria-pressed', 'false');
  }
  const q = new URL(page.url()).searchParams;
  expect(['metro', 'plaques', 'photos'].filter(k => q.has(k))).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(page.locator('#look')).toBeHidden();
  await expect(page.locator('.look-dot')).toBeHidden();
  expect(errors).toEqual([]);
});
