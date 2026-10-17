// The legend's "Blue plaques" switch (features.plaques): off on a fresh visit; on, Samfundet S:t Erik's blue markers show
// and a plaque building's pinned card has its plaque section; the choice is remembered and kept in the URL (?plaques=1).
// Runs on whatever web/data/current.json names: the fixture (Gamla stan, with Den Gyldene Freden) in CI.
import { test, expect } from '@playwright/test';

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
const plaques = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  const r = await fetch(`data/${version}/plaques.json`);
  return r.ok ? r.json() : [];
});
const markers = page => page.evaluate(() => ({ on: window.__dbg.plaquesOn, visible: window.__dbg.plaqueGroup.visible,
  n: window.__dbg.plaqueGroup.children.length }));

test('the plaques switch is off on a fresh visit, and on it shows the markers and Den Gyldene Freden\'s plaque', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await open(page);
  const list = await plaques(page);
  const freden = list.find(p => /Gyldene Freden/i.test(`${p.name} ${p.text}`));
  test.skip(!freden, 'this build has no plaque for Den Gyldene Freden');

  // off by default: no markers, no plaque section on the card
  const sw = page.locator('#plaques-on');
  await expect(sw).toHaveText('Blue plaques');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('#plaques-hint')).toBeHidden();
  expect(await markers(page)).toMatchObject({ on: false, visible: false });
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), freden.gid);
  await expect(page.locator('#card.pinned')).toBeVisible();
  await expect(page.locator('#card .plaque')).toHaveCount(0);

  // on: the markers, the line under the switch, the card's plaque, the URL
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#plaques-hint')).toHaveText("Samfundet S:t Erik's plaques on buildings with a story. Their texts are in Swedish.");
  expect(await markers(page)).toEqual({ on: true, visible: true, n: list.length });
  expect(new URL(page.url()).searchParams.get('plaques')).toBe('1');
  const plaque = page.locator('#card.pinned .plaque').first();
  await expect(plaque).toBeVisible();
  await expect(plaque.locator('.plaque-note')).toHaveText('Plaque text in Swedish');
  await expect(plaque).toContainText('Samfundet S:t Erik, CC BY 4.0');
  await page.keyboard.press('Escape');

  // remembered on this device; off again clears it and the URL
  await open(page);
  await expect(page.locator('#plaques-on')).toHaveAttribute('aria-pressed', 'true');
  expect(new URL(page.url()).searchParams.get('plaques')).toBe('1');
  await page.locator('#plaques-on').click();
  expect(await markers(page)).toMatchObject({ on: false, visible: false });
  expect(new URL(page.url()).searchParams.has('plaques')).toBe(false);
  await open(page);
  await expect(page.locator('#plaques-on')).toHaveAttribute('aria-pressed', 'false');
  expect(errors).toEqual([]);
});

test('?plaques=1 turns the switch on, in Swedish too', async ({ page }) => {
  await open(page, '?plaques=1&lang=sv');
  test.skip(!(await plaques(page)).length, 'this build has no plaques');
  await expect(page.locator('#plaques-on')).toHaveText('Blå skyltar');
  await expect(page.locator('#plaques-on')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#plaques-hint')).toHaveText('Samfundet S:t Eriks skyltar på hus med en historia. Texterna är på svenska.');
});

test('a phone shows the switch on in the legend', async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await open(page, '?plaques=1');
  test.skip(!(await plaques(page)).length, 'this build has no plaques');
  const handle = page.locator('.sheet-handle');   // a phone starts with the legend collapsed
  if (await handle.getAttribute('aria-expanded') === 'false') await handle.click();
  await expect(page.locator('#plaques-on')).toBeVisible();
  await page.locator('#plaques-on').scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'data/test-results/plaques-phone.png' });
  await page.close();
});
