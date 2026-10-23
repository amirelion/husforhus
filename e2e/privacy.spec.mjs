// The card's privacy lines: "Why?" opens About where the card's year is explained, and "Something
// wrong?" writes to the project once the map has an address. Runs on whatever current.json names.
import { test, expect } from '@playwright/test';

async function open(page) {
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
const firstGid = (page, src) => page.evaluate(async s => {
  const { version } = await (await fetch('data/current.json')).json();
  const n = (await (await fetch(`data/${version}/stockholm.json`)).json()).stats.buildings;
  const ok = new Function('b', `return (${s})(b)`);
  for (let g = 0; g < n; g++) if (ok(window.__dbg.building(g))) return g;
  return -1;
}, src.toString());

test('"Why?" on a private house opens About at its privacy section', async ({ page }) => {
  await open(page);
  const gid = await firstGid(page, b => b.private === 1);
  test.skip(gid < 0, 'this build has no private house');
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  // "Something wrong?" exactly when the build has an address to write to (decision 2, set on 2026-10-17)
  const contact = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    return (await (await fetch(`data/${version}/stockholm.json`)).json()).about?.contact || '';
  });
  await expect(page.locator('#card.pinned .wrong')).toHaveCount(contact ? 1 : 0);
  await page.locator('#card.pinned .dating .why').click();
  await expect(page.locator('#about-privacy')).toBeInViewport();
});

test('"Why?" on a building without a year opens About where the years are explained', async ({ page }) => {
  await open(page);
  const gid = await firstGid(page, b => b.yflag === 7);
  test.skip(gid < 0, 'this build has no building without a year');
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  await page.locator('#card.pinned .dating .why').click();
  await expect(page.locator('#about-years')).toBeInViewport();
});

test('every pinned card has "Something wrong?", which opens the report form for that building', async ({ page }) => {
  await open(page);
  await page.evaluate(() => window.__dbg.pinCard(0, 300, 300));
  const b = page.locator('#card.pinned .wrong button');
  await expect(b).toHaveText('Something wrong?');
  await b.click();
  const dialog = page.getByRole('dialog', { name: 'Something wrong?' });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('.report-ref')).toContainText('building 0, data v');
});

test('a pinned card has a Google Maps pin, but never a private house\'s', async ({ page }) => {
  await open(page);
  const home = await firstGid(page, b => b.private === 1);
  const other = await firstGid(page, b => b.private !== 1);
  test.skip(home < 0 || other < 0, 'this build lacks a private house or another building');
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), other);
  const pin = page.locator('#card.pinned .gmaps');
  await expect(pin).toHaveCount(1);
  // the card's first address in Stockholm, or the building's position when its card has no address
  await expect(pin).toHaveAttribute('href',
    /^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=([^&]+%2C%20Stockholm|59\.\d{6},1[78]\.\d{6})$/);
  await expect(pin).toHaveAttribute('aria-label', 'Open in Google Maps');
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), home);
  await expect(page.locator('#card.pinned')).toBeVisible();
  await expect(page.locator('#card.pinned .gmaps')).toHaveCount(0);
});
