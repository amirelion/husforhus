// The Look panel's "Tunnelbanan" switch (features.metro, s16_metro's metro.json): off on a fresh visit; on, the lines grow
// with the timeline: at 1960 the green line's first stations and no red line (opened 1964); at Today every line, and
// Kymlinge as "never opened". A station's card has its name, lines, opening date and Wikidata link, and no image.
import { test, expect } from '@playwright/test';

// The layer switches sit in the Look panel (web/switcher.js): open it before a click.
async function openLook(page) {
  if (await page.locator('.look-open').getAttribute('aria-expanded') !== 'true') await page.locator('.look-open').click();
  await expect(page.locator('#look')).toBeVisible();
}
async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
const hasMetro = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  return (await fetch(`data/${version}/metro.json`)).ok;
});
const shown = page => page.evaluate(() => {
  const l = window.__dbg.metroLayer, segs = window.__dbg.metroLayer.shownSegments;
  return { on: window.__dbg.metroOn, visible: l.group.visible, stations: l.shownStations,
    lines: [...new Set(l.group.children.filter(m => m.userData.segment && segs.includes(m.userData.segment.id)).map(m => m.userData.segment.line))].sort() };
});
const atYear = (page, y) => page.evaluate(y => { const u = window.__dbg.uniforms; u.uYear.value = y ?? Infinity; }, y);

test('the switch grows the lines with the timeline: green in 1960, no red until 1964, every line at Today', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await open(page);
  test.skip(!(await hasMetro(page)), 'this build has no metro.json');
  const sw = page.locator('#metro-on');
  await expect(sw).toHaveText('Tunnelbanan');
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  expect((await shown(page)).visible).toBe(false);

  await atYear(page, 1960);
  await openLook(page);
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');   // closes the Look panel
  expect(new URL(page.url()).searchParams.get('metro')).toBe('1');
  await expect.poll(async () => (await shown(page)).lines).toEqual(['green']);
  const s1960 = await shown(page);
  expect(s1960.stations).toEqual(expect.arrayContaining(['Slussen', 'Medborgarplatsen', 'Gullmarsplan', 'Hökarängen']));
  expect(s1960.stations).not.toContain('Fruängen');               // the red line, 1964
  expect(s1960.stations).not.toContain('Kymlinge');

  const yearMax = await page.evaluate(() => fetch('data/current.json').then(r => r.json())
    .then(({ version }) => fetch(`data/${version}/stockholm.json`)).then(r => r.json()).then(c => c.yearMax));
  await atYear(page, yearMax);
  await expect.poll(async () => (await shown(page)).lines).toEqual(['blue', 'green', 'red']);
  const today = await shown(page);
  expect(today.stations).toEqual(expect.arrayContaining(['Fruängen', 'Akalla', 'Kymlinge']));
  expect(today.stations.length).toBe(101);

  // a station's card: name, lines, the date, the Wikidata item; no photo
  await page.evaluate(() => window.__dbg.pinStation(window.__dbg.metroLayer.group.children.find(m => m.userData.station?.name === 'Hötorget').userData.station, 300, 300));
  const card = page.locator('#card.pinned.station');
  await expect(card.locator('h3')).toHaveText('Hötorget');
  await expect(card).toContainText('Green line');
  await expect(card).toContainText('Opened 26 October 1952');
  await expect(card).toContainText('Formerly Kungsgatan');
  await expect(card.locator('a[href^="https://www.wikidata.org/wiki/Q"]')).toHaveCount(1);
  await expect(card.locator('img')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(card).toBeHidden();

  // remembered; off clears it and the URL
  await open(page);
  await expect(page.locator('#metro-on')).toHaveAttribute('aria-pressed', 'true');
  await openLook(page);
  await page.locator('#metro-on').click();
  expect(new URL(page.url()).searchParams.has('metro')).toBe(false);
  expect((await shown(page)).visible).toBe(false);
  expect(errors).toEqual([]);
});

test('a phone shows the lines with the switch on', async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await open(page, '?metro=1');
  test.skip(!(await hasMetro(page)), 'this build has no metro.json');
  await page.evaluate(() => window.__dbg.viewAt(9000));
  await openLook(page);
  await expect(page.locator('#metro-on')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#metro-on').scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  await page.screenshot({ path: 'data/test-results/metro-phone.png' });
  await page.close();
});

// A story with "layers": ["metro"] (metro-1950) shows the lines whatever the switch says, as of each beat's year,
// and hands the switch's state back at Exit.
test('a metro story shows the lines as of each beat, with the switch off, and puts it back at Exit', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/stockholm.json', async route => {
    const r = await route.fetch();
    const config = await r.json();
    config.features = { ...config.features, scenes: true };
    await route.fulfill({ response: r, json: config });
  });
  await open(page, '?scene=metro-1950');
  test.skip(!(await hasMetro(page)), 'this build has no metro.json');
  await expect(page.locator('.sp-cinema')).toBeVisible();
  expect(await page.evaluate(() => window.__dbg.metroOn)).toBe(false);
  await expect.poll(async () => (await shown(page)).visible).toBe(true);
  await expect.poll(async () => (await shown(page)).stations).toEqual(expect.arrayContaining(['Slussen', 'Hökarängen']));
  expect((await shown(page)).stations).not.toContain('T-Centralen');     // 1957
  await expect(page.locator('.sp-year')).toHaveText('1950');
  for (let i = 1; i < 6; i++) await page.keyboard.press('ArrowRight');
  await expect(page.locator('.sp-count')).toContainText('6 / 6');
  await expect(page.locator('.sp-year')).toHaveText('1957');
  await expect.poll(async () => (await shown(page)).stations).toEqual(expect.arrayContaining(['T-Centralen', 'Gamla stan', 'Vällingby']));
  await page.locator('.sp-exit').click();
  await expect(page.locator('.sp-cinema')).toBeHidden();
  expect((await shown(page)).visible).toBe(false);
  await expect(page.locator('#metro-on')).toHaveAttribute('aria-pressed', 'false');
});
