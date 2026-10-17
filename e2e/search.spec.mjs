// Search: the keyboard, the combobox, a pick that flies and opens the card, a street,
// the phone sheet and ?q=. Runs on whatever web/data/current.json names (the fixture in CI, the whole city on a
// laptop): it reads an address, a street and a named building from the build's own index.
import { test, expect } from '@playwright/test';

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}

// From the build's index: a street with at least two numbers, one of its addresses, and a named building built after
// 1800 (the first one in the index; the page must be up, since the year comes from window.__dbg).
const sample = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  const index = await (await fetch(`data/${version}/search/index.json`)).json();
  const street = index.streets.filter(s => s[1] >= 2).sort((a, b) => b[1] - a[1])[0];
  const pairs = street && (await (await fetch(`data/${version}/search/addr/${street[3]}.json`)).json())[street[0]];
  const building = window.__dbg && index.buildings.find(b => window.__dbg.building(b[1]).year > 1800);
  return { street: street?.[0], number: pairs?.[0][0], gid: pairs?.[0][1], building };
});
const target = page => page.evaluate(() => window.__dbg.controls.target.toArray().map(Math.round));

test('"/" focuses the field; an address picked with Enter flies there and opens its card', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const s = await sample(page);
  test.skip(!s.street, 'this build has no street with two addresses');
  const input = page.getByRole('combobox');
  await expect(input).toHaveAttribute('placeholder', 'Search address, street or building');
  await page.keyboard.press('/');
  await expect(input).toBeFocused();
  await expect(page.locator('.search-msg')).toContainText('Addresses come from OpenStreetMap');
  const before = await target(page);
  await page.keyboard.type(`${s.street} ${s.number}`);
  for (const k of ['ArrowLeft', 'ArrowUp', 'ArrowRight']) await page.keyboard.press(k);   // typing never pans the map
  expect(await target(page)).toEqual(before);
  const first = page.getByRole('option').first();
  await expect(first).toContainText(`${s.street} ${s.number}`);
  await expect(input).toHaveAttribute('aria-expanded', 'true');
  await expect(input).toHaveAttribute('aria-activedescendant', 'search-opt-0');
  await expect(page.locator('.search-status')).toHaveText(/^\d+ results?$/);
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(s.gid);
  // The card names the building's first address, and how many more it has: the picked one when it is the only one.
  const place = page.locator('#card.pinned .card-head .place');
  await expect(place).toHaveText(/^\S.* \d+\S*( \(and \d+ more\))? · /);
  const line = await place.innerText();
  if (!/\(and \d+ more\)/.test(line)) expect(line).toContain(`${s.street} ${s.number}`);
  await expect(page.getByRole('listbox')).toBeHidden();
  expect(new URL(page.url()).searchParams.has('q')).toBe(false);          // a pick is never written into the address
  expect(errors).toEqual([]);
});

test('a building found by name is drawn and noted even when the timeline would hide it', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const s = await sample(page);
  test.skip(!s.building, 'this build has no named building built after 1800');
  const [name, gid] = s.building;
  await page.evaluate(() => { window.__dbg.uniforms.uYear.value = 1700; });   // the map set to 1700: it is not built
  await page.getByRole('combobox').fill(name);
  await page.getByRole('option', { name: new RegExp(name) }).first().click();
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(gid);
  expect(await page.evaluate(() => window.__dbg.forced)).toBe(gid);
  await expect(page.locator('#card.pinned .picked')).toHaveText("Picked from search: shown although the map's settings would hide it.");
  await page.evaluate(() => { window.__dbg.uniforms.uYear.value = 2026; });   // the map would show it now: no note
  await expect(page.locator('#card.pinned .picked')).toHaveCount(0);
  await page.keyboard.press('Escape');                                    // closing the card lets the building go
  expect(await page.evaluate(() => window.__dbg.forced)).toBe(-1);
  expect(errors).toEqual([]);
});

test('Enter typed straight after the number picks that address, not a row of the street before its numbers load', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const s = await sample(page);
  test.skip(!s.street, 'this build has no street with two addresses');
  const input = page.getByRole('combobox');
  await input.focus();
  await page.keyboard.type(`${s.street} ${s.number}`);
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(s.gid);
  await page.waitForTimeout(300);
  await expect(page.getByRole('listbox')).toBeHidden();                  // no late answer opens the list again
  expect(errors).toEqual([]);
});

test('a street flies to its buildings without a card; Esc twice clears the field', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const s = await sample(page);
  test.skip(!s.street, 'this build has no street with two addresses');
  const input = page.getByRole('combobox');
  await input.fill(s.street);
  const row = page.getByRole('option').filter({ hasText: /Street|Gata/ }).first();
  await expect(row).toBeVisible();
  const before = await target(page);
  await row.click();
  await expect.poll(() => target(page), { timeout: 10_000 }).not.toEqual(before);
  expect(await page.evaluate(() => window.__dbg.pinned)).toBe(-1);
  await input.focus();
  await input.fill('zzzzqqqq');
  await expect(page.locator('.search-msg')).toContainText('Nothing found for');
  await page.keyboard.press('Escape');
  await expect(page.locator('.search-msg')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(input).toHaveValue('');
  await expect(input).not.toBeFocused();
  expect(errors).toEqual([]);
});

test('a year or a neighbouring municipality says what to do instead', async ({ page }) => {
  await open(page);
  const input = page.getByRole('combobox');
  await input.fill('1930');
  await expect(page.locator('.search-msg')).toHaveText('To see the city in 1930, drag the timeline.');
  await input.fill('Solna');
  await expect(page.locator('.search-msg')).toHaveText('Solna is outside Stockholm municipality, which is all this map covers.');
});

test('?q= picks the top result on load', async ({ page }) => {
  await page.goto('/');
  const s = await sample(page);
  test.skip(!s.street, 'this build has no street with two addresses');
  await open(page, `?q=${encodeURIComponent(`${s.street} ${s.number}`)}`);
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 15_000 }).toBe(s.gid);
});

// The share of a clip's pixels that changed between two screenshots, compared in the page (no image library).
const changed = (page, a, b) => page.evaluate(async ([a, b]) => {
  const load = src => new Promise(r => { const i = new Image(); i.onload = () => r(i); i.src = src; });
  const [ia, ib] = await Promise.all([load(a), load(b)]);
  const c = document.createElement('canvas'); c.width = ia.width; c.height = ia.height;
  const x = c.getContext('2d');
  x.drawImage(ia, 0, 0); const da = x.getImageData(0, 0, c.width, c.height).data;
  x.drawImage(ib, 0, 0); const db = x.getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  for (let i = 0; i < da.length; i += 4) if (Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]) > 30) n++;
  return n / (da.length / 4);
}, [a, b].map(buf => `data:image/png;base64,${buf.toString('base64')}`));
const frames = page => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));

// The owner's look change (2026-10-17): the pick is marked on the building itself, not by a red ring on the ground: a
// thin outline along its edges in the look's accent colour, two gentle pulses when the camera arrives, then steady
// while the card is open; under prefers-reduced-motion, no pulse.
const unknownGid = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  const n = (await (await fetch(`data/${version}/stockholm.json`)).json()).stats.buildings;
  for (let g = 0; g < n; g++) if (window.__dbg.building(g).yflag === 7 && window.__dbg.building(g).height > 8) return g;
  return -1;
});

test('a picked building is outlined in the look\'s accent colour, so it stands out among neighbours that look the same', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  // a "Year unknown" building: hatched grey like most of its neighbours, where the selection tint alone barely shows
  const gid = await unknownGid(page);
  test.skip(gid < 0, 'this build has no building without a year');
  await page.evaluate(g => { const b = window.__dbg.building(g); return new Promise(r => window.__dbg.flyTo(b.x, b.z, r, 420)); }, gid);
  await frames(page);
  const pos = await page.evaluate(g => {
    const D = window.__dbg, b = D.building(g);
    const v = new D.camera.position.constructor(b.x, D.surfaceAt ? D.surfaceAt(b.x, b.z) : 0, b.z).project(D.camera);
    return { x: Math.round((v.x + 1) / 2 * innerWidth), y: Math.round((1 - v.y) / 2 * innerHeight) };
  }, gid);
  const clip = { x: pos.x - 120, y: pos.y - 120, width: 240, height: 240 };
  const before = await page.screenshot({ clip });
  await page.evaluate(g => window.__dbg.force(g), gid);
  await frames(page);
  const hl = await page.evaluate(() => window.__dbg.highlight());
  const accent = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--accent').trim());
  expect(hl).toMatchObject({ gid, visible: true, colour: accent });
  expect(hl.segments).toBeGreaterThanOrEqual(8);                       // at least a box's roof and walls
  expect(await changed(page, before, await page.screenshot({ clip }))).toBeGreaterThan(0.002);
  // no ring, and nothing red
  expect(await page.evaluate(() => window.__dbg.scene.getObjectByName('pick-ring'))).toBeFalsy();
  await page.evaluate(() => window.__dbg.force(-1));                    // let go: the outline goes with the pick
  await frames(page);
  expect((await page.evaluate(() => window.__dbg.highlight())).visible).toBe(false);
  expect(await changed(page, before, await page.screenshot({ clip }))).toBeLessThan(0.01);
  expect(errors).toEqual([]);
});

test('a pick pulses twice on arrival, then stays steady while the card is open', async ({ page }) => {
  await open(page);
  const s = await sample(page);
  test.skip(!s.street, 'this build has no street with two addresses');
  await page.getByRole('combobox').fill(`${s.street} ${s.number}`);
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(s.gid);
  expect((await page.evaluate(() => window.__dbg.highlight())).pulses).toBe(2);
  await expect.poll(() => page.evaluate(() => window.__dbg.highlight().pulsing), { timeout: 5_000 }).toBe(false);
  expect(await page.evaluate(() => window.__dbg.highlight())).toMatchObject({ gid: s.gid, visible: true });
});

test.describe('with reduced motion', () => {
  test('a pick does not pulse', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await open(page);
    const s = await sample(page);
    test.skip(!s.street, 'this build has no street with two addresses');
    await page.getByRole('combobox').fill(`${s.street} ${s.number}`);
    await page.keyboard.press('Enter');
    await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(s.gid);
    expect(await page.evaluate(() => window.__dbg.highlight())).toMatchObject({ visible: true, pulses: 0, pulsing: false });
  });
});

// Final review F2: Tab from the empty field reaches the examples, and from a misspelt query the suggestion; the
// message is a live region.
test('Tab reaches the "Try:" examples and the "Did you mean" suggestion without closing them', async ({ page }) => {
  await open(page);
  const input = page.getByRole('combobox');
  await page.keyboard.press('/');
  await expect(page.locator('.search-msg')).toContainText('Addresses come from OpenStreetMap');
  await expect(page.locator('.search-msg')).toHaveAttribute('aria-live', 'polite');
  const tries = page.locator('.search-msg .search-try');
  test.skip(await tries.count() === 0, 'this build has no examples');
  for (let i = 0; i < 4 && !(await tries.first().evaluate(el => el === document.activeElement)); i++) await page.keyboard.press('Tab');
  await expect(tries.first()).toBeFocused();
  await expect(page.locator('.search-msg')).toBeVisible();
  const q = await tries.first().getAttribute('data-q');
  await page.keyboard.press('Enter');
  await expect(input).toHaveValue(q);
  await expect(input).toBeFocused();
  // Tab away from the whole search: the message closes
  await input.fill('');
  await page.locator('.modes button').first().focus();
  await expect(page.locator('.search-msg')).toBeHidden();
});

// Final review F5: a street's shard arriving after a newer action no longer takes the camera back.
test('a street pick whose numbers arrive late does not undo a building pinned meanwhile', async ({ page }) => {
  await open(page);
  const s = await sample(page);
  test.skip(!s.street, 'this build has no street with two addresses');
  let release;
  const held = new Promise(r => { release = r; });
  await page.route('**/search/addr/*.json', async route => { await held; route.continue(); });
  const input = page.getByRole('combobox');
  await input.fill(s.street);
  await expect(page.getByRole('option').first()).toBeVisible();
  const streetRow = page.getByRole('option').filter({ hasText: /Street|Gata/ }).first();
  await streetRow.click();
  await page.evaluate(g => window.__dbg.pinCard(g, 400, 300), s.gid);
  const before = await target(page);
  release();
  await page.waitForTimeout(1500);
  expect(await page.evaluate(() => window.__dbg.pinned)).toBe(s.gid);
  expect(await target(page)).toEqual(before);
});

// Fix-wave review: a redraw of the open card (a shard arriving) is not a newer action; the street pick still flies.
test('a street pick is not cancelled by the open card being redrawn while its numbers load', async ({ page }) => {
  await open(page);
  const s = await sample(page);
  test.skip(!s.street, 'this build has no street with two addresses');
  await page.evaluate(g => window.__dbg.pinCard(g, 400, 300), s.gid);
  let release;
  const held = new Promise(r => { release = r; });
  await page.route('**/search/addr/*.json', async route => { await held; route.continue(); });
  await page.getByRole('combobox').fill(s.street);
  const before = await target(page);
  await page.getByRole('option').filter({ hasText: /Street|Gata/ }).first().click();
  await page.evaluate(g => window.__dbg.pinCard(g, 400, 300), s.gid);        // the same card, drawn again
  release();
  await expect.poll(() => target(page), { timeout: 10_000 }).not.toEqual(before);
});

// Final review F7: a ?q= with no match shows its message unfocused; a language switch redraws it.
test('a message under the unfocused pill follows a language switch', async ({ page }) => {
  await open(page, '?q=zzqqxx');
  const msg = page.locator('.search-msg');
  await expect(msg).toBeVisible();
  const en = await msg.textContent();
  await page.locator('.lang [data-lang="sv"]').click();
  await expect(msg).not.toHaveText(en);
});

test.describe('on a narrow desktop', () => {
  test.use({ viewport: { width: 1101, height: 760 } });
  test('the focused search pill never covers the title and the count', async ({ page }) => {
    await open(page);
    await page.getByRole('combobox').focus();
    const [pill, tally] = [await page.locator('.search').boundingBox(), await page.locator('.corner .tally').boundingBox()];
    expect(pill.x + pill.width).toBeLessThanOrEqual(tally.x);
  });
  // Final review F6: the title widens with a range or a long period; the pill follows, or moves under the modes.
  test('the pill keeps clear of a wider title', async ({ page }) => {
    await open(page);
    const clear = async () => {
      const [pill, corner] = [await page.locator('.search').boundingBox(), await page.locator('.corner').boundingBox()];
      const apart = pill.x + pill.width <= corner.x || pill.y >= corner.y + corner.height;
      expect(apart).toBe(true);
    };
    const from = page.getByRole('slider', { name: 'Start year' });
    await from.focus();
    for (let i = 0; i < 8; i++) await page.keyboard.press('PageUp');
    await expect(from).not.toHaveAttribute('aria-valuetext', 'No start year');
    await page.waitForTimeout(400);
    await clear();
    await page.setViewportSize({ width: 1180, height: 760 });
    await page.waitForTimeout(400);
    await clear();
  });
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
  test('the search button opens a full-screen sheet; a pick closes it and opens the card', async ({ page }) => {
    const errors = watchErrors(page);
    await open(page);
    const s = await sample(page);
    test.skip(!s.street, 'this build has no street with two addresses');
    const input = page.getByRole('combobox');
    await expect(input).toBeHidden();
    await page.locator('.search-open').click();
    await expect(input).toBeFocused();
    const box = await page.locator('.search').boundingBox();
    expect(box.width).toBe(390);
    // 16 px or more: iPhone Safari zooms into a smaller field and stays zoomed; the page behind the sheet is inert
    expect(parseFloat(await input.evaluate(el => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    expect(await page.locator('.corner').evaluate(el => el.inert)).toBe(true);
    await input.fill(`${s.street} ${s.number}`);
    await page.getByRole('option').first().click();
    await expect(page.locator('.search')).toBeHidden();
    await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(s.gid);
    // the building lands between the corner's buttons and the card's sheet at its tallest (72% of the screen)
    const y = await page.evaluate(() => {
      const D = window.__dbg, b = D.building(D.pinned);
      const v = new D.camera.position.constructor(b.x, D.surfaceAt ? D.surfaceAt(b.x, b.z) : 0, b.z).project(D.camera);
      return (1 - v.y) / 2 * innerHeight;
    });
    const corner = await page.locator('.corner').boundingBox();
    expect(y).toBeGreaterThan(corner.y + corner.height);
    expect(y).toBeLessThan(844 * 0.28);
    await page.locator('.search-open').click();
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.locator('.search')).toBeHidden();
    expect(await page.locator('.corner').evaluate(el => el.inert)).toBe(false);
    await expect(page.locator('.search-open')).toBeFocused();             // the keyboard is back where it was
    expect(errors).toEqual([]);
  });
});

test('"nobel" finds the Nobel Prize Museum and flies to Börshuset', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const gid = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    const index = await (await fetch(`data/${version}/search/index.json`)).json();
    const o = (index.occupants || []).find(e => /nobel/i.test(e[0]));
    return o && index.buildings.some(b => b[0] === 'Börshuset' && b[1] === o[2]) ? o[2] : null;
  });
  test.skip(gid === null, 'this build has no Nobel occupant in Börshuset');
  await page.getByRole('combobox').fill('nobel');
  const row = page.getByRole('option', { name: /, in Börshuset/ }).first();
  await expect(row).toContainText('Nobel Prize Museum, in Börshuset');
  await expect(row).toContainText('Inside a building');
  await row.click();
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned), { timeout: 10_000 }).toBe(gid);
  await expect(page.locator('#card.pinned')).toContainText('Börshuset');
  expect(errors).toEqual([]);
});
