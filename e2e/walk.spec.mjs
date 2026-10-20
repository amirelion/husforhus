// A walk on a phone (2026-10-20): a bar above the modes, folded to its summary so the route shows; its header opens
// the stops with the Google Maps link in reach; a touch on the map folds it again; a pinned card hides the bar until
// it closes; only the × ends the walk. On a desktop it opens unfolded, as before.
import { test, expect } from '@playwright/test';

const walkState = page => page.evaluate(() => {
  const w = document.getElementById('walk'), r = w.getBoundingClientRect();
  return { shown: !w.hidden && getComputedStyle(w).display !== 'none', folded: w.classList.contains('folded'),
    top: Math.round(r.top), bottom: Math.round(r.bottom) };
});

async function planWalk(page) {
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  test.skip(await page.locator('.walks-open').isHidden(), 'this build has no walks');
  await page.locator('.walks-open').click();
  await page.getByRole('button', { name: 'Make my walk' }).click();
  await expect(page.locator('#walk')).toBeVisible();
}

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  test('the walk is a folded bar above the modes; it opens, folds at a map touch and steps aside for a card', async ({ page }) => {
    await planWalk(page);
    let s = await walkState(page);
    const modes = await page.locator('.modes').boundingBox();
    expect(s).toMatchObject({ shown: true, folded: true });
    expect(s.bottom).toBeLessThanOrEqual(Math.round(modes.y));       // above the modes, the map clear above it
    expect(s.top).toBeGreaterThan(844 / 2);
    await expect(page.locator('.panel')).toBeHidden();                 // the legend steps aside while walking

    await page.locator('#walk header').click();
    s = await walkState(page);
    expect(s.folded).toBe(false);
    await expect(page.locator('#walk .w-google')).toBeInViewport();    // the Google Maps link stays in reach

    await page.touchscreen.tap(200, 200);                              // a touch on the map folds it, never ends it
    await expect.poll(async () => (await walkState(page)).folded).toBe(true);
    expect((await walkState(page)).shown).toBe(true);

    await page.locator('#walk header').click();
    await page.locator('#walk .w-list button').nth(1).click();         // a stop: folded, and its card opens
    await expect(page.locator('#card.pinned')).toBeVisible({ timeout: 15_000 });
    expect((await walkState(page)).shown).toBe(false);
    await page.locator('#card .card-close').click();
    await expect.poll(async () => (await walkState(page)).shown).toBe(true);

    await page.locator('#walk .q-close').click();                      // only the × ends the walk
    await expect(page.locator('#walk')).toBeHidden();
  });
});

test('on a desktop the walk opens unfolded and its header folds it', async ({ page }) => {
  await planWalk(page);
  expect((await walkState(page)).folded).toBe(false);
  await page.locator('#walk header').click();
  expect((await walkState(page)).folded).toBe(true);
  await expect(page.locator('#walk .w-google')).toBeHidden();
});
