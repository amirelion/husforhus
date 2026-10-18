// Quests and walks are on for everyone (config.features, no ?try= needed). The Look panel's "Quests and walks" switch,
// under its own heading, hides their buttons; the choice is remembered per device (hfh-quests-walks) and, unlike the
// map's layer switches, never lights the dot on the Look button.
import { test, expect } from '@playwright/test';

test('the Quests and Walk buttons show by default; the Look switch hides them, and a reload remembers it', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const buttons = page.locator('.quests-open, .walks-open');
  await expect(page.locator('.quests-open')).toBeVisible();
  await expect(page.locator('.walks-open')).toBeVisible();
  await expect(page.locator('.look-dot')).toBeHidden();   // on by default, and not a map layer

  await page.locator('.look-open').click();
  await expect(page.locator('#extras-title')).toHaveText('Explore');
  const sw = page.locator('#look #quests-walks-on');
  await expect(sw).toHaveText('Quests and walks');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect(buttons).toHaveCount(2);
  for (const b of await buttons.all()) await expect(b).toBeHidden();
  expect(await page.evaluate(() => localStorage.getItem('hfh-quests-walks'))).toBe('off');
  await page.keyboard.press('Escape');
  await expect(page.locator('.look-dot')).toBeHidden();

  await page.reload();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  for (const b of await buttons.all()) await expect(b).toBeHidden();
  await page.locator('.look-open').click();
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await sw.click();
  await expect(page.locator('.quests-open')).toBeVisible();
  await expect(page.locator('.walks-open')).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('hfh-quests-walks'))).toBe('on');
  expect(errors).toEqual([]);
});

test('in Swedish the switch reads "Uppdrag och promenader" under "Utforska"', async ({ page }) => {
  await page.goto('/?lang=sv');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await page.locator('.look-open').click();
  await expect(page.locator('#extras-title')).toHaveText('Utforska');
  await expect(page.locator('#look #quests-walks-on')).toHaveText('Uppdrag och promenader');
});
