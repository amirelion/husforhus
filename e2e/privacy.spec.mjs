// The card's privacy lines (Plan 4b, Task 8): "Why?" opens About where the card's year is explained, and "Something
// wrong?" writes to the project once the map has an address (decision 2, Plan 4b). Runs on whatever current.json names.
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

test('with an address, every pinned card has "Something wrong? Tell us"', async ({ page }) => {
  await page.addInitScript(() => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/stockholm.json')) return r;
      const config = await r.json();
      config.about = { ...config.about, contact: 'hej@example.org' };
      return new Response(JSON.stringify(config), { headers: { 'content-type': 'application/json' } });
    };
  });
  await open(page);
  await page.evaluate(() => window.__dbg.pinCard(0, 300, 300));
  const a = page.locator('#card.pinned .wrong a');
  await expect(a).toHaveText('Something wrong? Tell us');
  await expect(a).toHaveAttribute('href', /^mailto:hej@example\.org\?subject=Hus%20f%C3%B6r%20hus%3A%20.+&body=About%20building%200%20on%20the%20map%20\(data%20v\w+(-\w+)?\)%3A$/);
});
