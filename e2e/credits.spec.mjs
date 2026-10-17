// The corner credit (Plan 4b, Task 9; spec §4.5): visible without interaction, the sources' own words, OpenStreetMap
// linked to its copyright page, "Sources" into About; on a phone it folds to (i) after 5 s.
import { test, expect } from '@playwright/test';

async function open(page) {
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
// The build's own credits: Lantmäteriet only on a build whose terrain came from its model (Plan 3).
const attribution = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  return (await (await fetch(`data/${version}/stockholm.json`)).json()).attribution;
});

test('the credit names its sources in the corner and leads into About', async ({ page }) => {
  await open(page);
  const line = page.locator('#credit');
  await expect(line).toBeVisible();
  const lm = (await attribution(page)).some(a => a.id === 'lm_markhojd');
  await expect(line).toContainText(`© Stockholms stad · RAÄ · © OpenStreetMap contributors${lm ? ' · © Lantmäteriet' : ''} · Sources`);
  await expect(line.getByRole('link', { name: '© OpenStreetMap contributors' }))
    .toHaveAttribute('href', 'https://www.openstreetmap.org/copyright');
  // the drag hint and the credit do not cover each other
  const [hint, credit] = await Promise.all(['.howto', '.credits'].map(s => page.locator(s).boundingBox()));
  expect(hint.y + hint.height).toBeLessThanOrEqual(credit.y + 1);
  await line.getByRole('link', { name: 'Sources' }).click();
  await expect(page.locator('#about-sources')).toBeInViewport();
  await page.keyboard.press('Escape');
  await page.locator('.lang [data-lang="sv"]').click();
  await expect(line).toContainText('© OpenStreetMap-bidragsgivare · Källor');
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
  test('the credit shows at first, folds into (i) after 5 s, and (i) brings it back', async ({ page }) => {
    await open(page);
    await expect(page.locator('#credit')).toBeVisible();
    await expect(page.locator('#credit')).toBeHidden({ timeout: 8_000 });
    const button = page.locator('.credit-open');
    await expect(button).toBeVisible();
    await expect(button).toHaveAttribute('aria-expanded', 'false');
    await button.click();
    await expect(page.locator('#credit')).toBeVisible();
    await expect(page.locator('#credit a').first()).toBeFocused();            // focus stays in the credit (review)
    // under the corner's buttons, never over them (its top follows the corner's height, review)
    const [row, line] = await Promise.all(['.corner', '#credit'].map(s => page.locator(s).boundingBox()));
    expect(line.y).toBeGreaterThanOrEqual(row.y + row.height);
    const box = await page.locator('.credits').boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);                      // inside the screen, no sideways scroll
  });

  test('folded, the credit leaves the strip it spans to the map', async ({ page }) => {
    await open(page);
    await expect(page.locator('#credit')).toBeHidden({ timeout: 8_000 });
    const strip = await page.locator('.credits').boundingBox();
    // a tap or a drag left of the (i) button reaches the canvas, not the credit's empty box
    expect(await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.id, [strip.x + 20, strip.y + strip.height / 2]))
      .toBe('scene');
    await page.setViewportSize({ width: 1024, height: 768 });                  // turned wide: a desktop shows it whole
    await expect(page.locator('#credit')).toBeVisible();
    await expect(page.locator('.credit-open')).toBeHidden();
  });

  for (const width of [390, 360]) {
    test(`the corner's row (search, north, Look, About, EN | SV) fits ${width} px in both languages`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await open(page);
      for (const lang of ['en', 'sv']) {
        if (lang === 'sv') await page.locator('.lang [data-lang="sv"]').click();
        const boxes = await page.locator('.corner .buttons > :is(button, .lang)').evaluateAll(els =>
          els.filter(el => el.offsetParent).map(el => el.getBoundingClientRect().toJSON()));
        expect(boxes.length).toBeGreaterThanOrEqual(4);
        for (const b of boxes) expect(b.left >= 0 && b.right <= width, `${lang}: ${JSON.stringify(b)}`).toBe(true);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      }
    });
  }
});
