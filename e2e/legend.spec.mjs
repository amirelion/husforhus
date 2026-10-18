// The legend on a phone: an open sheet folds when the map is touched or its handle is swiped down, without
// overwriting the viewer's remembered choice; the handle still opens and folds it from the keyboard.
import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

async function openLegend(page) {
  await page.addInitScript(() => localStorage.setItem('hfh-legend', 'open'));
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const handle = page.locator('.sheet-handle');
  await expect(handle).toHaveAttribute('aria-expanded', 'true');
  return handle;
}

test('a touch on the map folds the open legend, and the choice stays remembered', async ({ page }) => {
  const handle = await openLegend(page);
  await page.locator('#scene').dispatchEvent('pointerdown', { clientX: 180, clientY: 250 });
  await expect(handle).toHaveAttribute('aria-expanded', 'false');
  expect(await page.evaluate(() => localStorage.getItem('hfh-legend'))).toBe('open');
});

test('a swipe down on the handle folds the legend', async ({ page }) => {
  const handle = await openLegend(page);
  const box = await handle.boundingBox();
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await handle.dispatchEvent('pointerdown', { clientX: x, clientY: y });
  await handle.dispatchEvent('pointerup', { clientX: x, clientY: y + 60 });
  await handle.dispatchEvent('click');
  await expect(handle).toHaveAttribute('aria-expanded', 'false');
});

test('the handle still opens and folds the legend from the keyboard', async ({ page }) => {
  const handle = await openLegend(page);
  await handle.focus();
  await page.keyboard.press('Enter');
  await expect(handle).toHaveAttribute('aria-expanded', 'false');
  await page.keyboard.press('Enter');
  await expect(handle).toHaveAttribute('aria-expanded', 'true');
});
