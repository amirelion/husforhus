// Share a building: the pinned card's "Share" copies a link (?q= its name, else ?at=), and opening that link in a
// new page flies to the building and pins its card. Needs Börshuset in the build (the fixture and the whole city).
import { test, expect } from '@playwright/test';

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}

// Börshuset's gid in this build, from the 64 card shards.
const gidOf = (page, name) => page.evaluate(async name => {
  const { version } = await (await fetch('data/current.json')).json();
  for (let k = 0; k < 64; k++) {
    const shard = await (await fetch(`data/${version}/cards/${String(k).padStart(2, '0')}.json`)).json();
    for (const [g, c] of Object.entries(shard)) if (c.name === name) return +g;
  }
  return -1;
}, name);

test('sharing Börshuset copies a link that opens with its card pinned', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await open(page);
  const gid = await gidOf(page, 'Börshuset');
  expect(gid).toBeGreaterThanOrEqual(0);
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  const share = page.locator('#card.pinned .card-share');
  await expect(share).toHaveText('Share');
  await share.click();
  await expect(share).toHaveText('Link copied');
  const link = await page.evaluate(() => navigator.clipboard.readText());
  // ?q= when this build's search finds the name back to it; a build without search links by the point
  const searchable = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    return !!(await (await fetch(`data/${version}/stockholm.json`)).json()).features?.search;
  });
  if (searchable) expect(link).toBe('https://husforhus.se/?q=B%C3%B6rshuset');
  else expect(link).toMatch(/^https:\/\/husforhus\.se\/\?at=-?\d+\.\d,-?\d+\.\d,\d+$/);
  await expect(share).toHaveText('Share', { timeout: 4000 });

  const other = await context.newPage();
  await open(other, new URL(link).search + '&lang=sv');
  const card = other.locator('#card.pinned');
  await expect(card.locator('#card-title')).toHaveText('Börshuset', { timeout: 30_000 });
  await expect(card.locator('.card-share')).toHaveText('Dela');
});

test('an ?at= link flies to the point and pins the building under it', async ({ page }) => {
  await open(page);
  const gid = await gidOf(page, 'Börshuset');
  const { x, z } = await page.evaluate(g => window.__dbg.building(g), gid);
  await open(page, `?at=${x.toFixed(1)},${z.toFixed(1)},300`);
  await expect(page.locator('#card.pinned')).toBeVisible({ timeout: 30_000 });
});
