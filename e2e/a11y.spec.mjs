// The launch check (phones, keyboard, screen readers): every control is reached by Tab and visibly focused; Escape
// closes the card, About and Look and gives the focus back; controls and switches are named in both languages; the
// card and About are dialogs with their titles; axe finds nothing serious or critical with a card or About open.
// Runs on whatever web/data/current.json names: the fixture in CI, the whole city on a laptop.
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
const photoGid = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  return (await (await fetch(`data/${version}/photo-gids.json`)).json())[0];
});
// The focused element, and whether a focus ring is drawn on it (an outline, or the search pill's ring).
const focused = page => page.evaluate(() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const s = getComputedStyle(el), box = el.closest('.search-box');
  const ring = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0)
    || (box && getComputedStyle(box).boxShadow.includes('2px'))
    || Boolean(el.closest('.relief-row:has(:focus-visible)'));
  const key = el.matches('.search input') ? '.search-input' : el.id ? `#${el.id}` : el.dataset.lang ? `[data-lang="${el.dataset.lang}"]` : el.dataset.mode ? `[data-mode="${el.dataset.mode}"]`
    : `.${[...el.classList][0] || el.tagName}`;
  return { key, ring };
});

test('Tab reaches every control, each visibly focused', async ({ page }) => {
  test.setTimeout(240_000);
  await open(page);
  const seen = new Map();
  for (let i = 0; i < 70; i++) {
    await page.keyboard.press('Tab');
    const f = await focused(page);
    if (f) seen.set(f.key, f.ring);
    if (seen.has('.grip') && seen.has('#scene') && seen.size > 12 && f?.key === '#scene') break;   // round the page once
  }
  const must = ['#scene', '.search-input', '[data-mode="0"]', '[data-mode="1"]', '.north-open', '.look-open', '.about-open',
    '[data-lang="sv"]', '.sheet-handle', '#photo-only', '#play', '.grip'];
  for (const k of must) expect([...seen.keys()], `${k} is reached by Tab`).toContain(k);
  expect([...seen].filter(([, ring]) => !ring).map(([k]) => k), 'every focused control shows a ring').toEqual([]);
});

test('search results work with the arrows and Enter; Escape closes the card and gives the focus back', async ({ page }) => {
  await open(page);
  const input = page.getByRole('combobox');
  await page.keyboard.press('/');
  await expect(input).toBeFocused();
  const name = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    return (await (await fetch(`data/${version}/search/index.json`)).json()).buildings[0][0];
  });
  await page.keyboard.type(name);
  await expect(page.locator('#search-list [role="option"]').first()).toBeVisible();
  await page.keyboard.press('ArrowDown');
  await expect(input).toHaveAttribute('aria-activedescendant', /search-opt-/);
  await page.keyboard.press('Enter');
  const card = page.locator('#card.pinned');
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card).toHaveAttribute('role', 'dialog');
  await expect(page.locator('#card .card-close')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.locator('#card')).toBeHidden();
  expect(await page.evaluate(() => document.activeElement !== document.body)).toBe(true);
});

test('Escape closes About and Look, and the focus returns to their buttons', async ({ page }) => {
  await open(page);
  for (const [button, dialog] of [['.about-open', '#about'], ['.look-open', '#look']]) {
    await page.locator(button).focus();
    await page.keyboard.press('Enter');
    await expect(page.locator(dialog)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator(dialog)).toBeHidden();
    await expect(page.locator(button)).toBeFocused();
  }
});

test('a card pinned by the keyboard closes with Escape and gives the focus back to the map', async ({ page }) => {
  await open(page);
  const gid = await photoGid(page);
  await page.locator('#scene').focus();
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  await expect(page.locator('#card .card-close')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.locator('#card')).toBeHidden();
  await expect(page.locator('#scene')).toBeFocused();
});

// Every visible control's accessible name, roughly as a screen reader computes it.
const names = page => page.evaluate(() => [...document.querySelectorAll('button, input, [role="slider"], a[href]')]
  .filter(el => el.getClientRects().length && !el.closest('[hidden], dialog:not([open])'))
  .map(el => {
    const by = el.getAttribute('aria-labelledby');
    const n = el.getAttribute('aria-label') || (by && by.split(' ').map(id => document.getElementById(id)?.textContent).join(' '))
      || el.textContent || el.getAttribute('title') || '';
    return { what: el.className || el.id || el.tagName, name: n.trim(), pressed: el.getAttribute('aria-pressed') };
  }));

for (const lang of ['en', 'sv']) {
  test(`controls, switches, the card and About are named in ${lang}`, async ({ page }) => {
    await open(page, lang === 'sv' ? '?lang=sv' : '');
    if (lang === 'sv') {
      if (await page.locator('html').getAttribute('lang') !== 'sv') await page.locator('.lang [data-lang="sv"]').click();
      await expect(page.locator('html')).toHaveAttribute('lang', 'sv');
    }
    expect((await names(page)).filter(c => !c.name), 'every control has a name').toEqual([]);
    for (const sw of ['#photo-only', '.swatch.unknown .switch']) {
      const el = page.locator(sw);
      if (await el.count()) await expect(el).toHaveAttribute('aria-pressed', /^(true|false)$/);
    }
    if (lang === 'sv') {
      await expect(page.locator('.north-open')).toHaveAttribute('aria-label', 'Vänd mot norr');
      await expect(page.locator('#play')).not.toHaveAttribute('aria-label', "Play the city's growth");
    }
    // the card: a dialog named by its title, its photo's alt the building's name
    const gid = await photoGid(page);
    test.skip(gid === undefined, 'this build has no card with a photo');
    await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
    const card = page.getByRole('dialog').filter({ has: page.locator('.card-head') });
    await expect(card).toBeVisible();
    const title = (await page.evaluate(() => document.getElementById('card').getAttribute('aria-labelledby').split(' ')
      .map(id => document.getElementById(id).textContent.trim()).join(' ')));
    expect(title.length).toBeGreaterThan(0);
    const img = page.locator('#card .photo img');
    const shown = await page.evaluate(() => (document.querySelector('#card h3#card-title') || document.querySelector('#card-place'))?.textContent.trim().split(' · ')[0]);
    if (shown) await expect(img).toHaveAttribute('alt', new RegExp(shown.split(' · ')[0].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    expect((await names(page)).filter(c => !c.name)).toEqual([]);
    await page.keyboard.press('Escape');
    // About: a dialog named by its heading
    await page.locator('.about-open').click();
    const heading = await page.locator('#about-title').innerText();
    await expect(page.getByRole('dialog', { name: heading })).toBeVisible();
  });
}

for (const [what, phone] of [['desktop', false], ['phone', true]]) {
  test(`axe: nothing serious or critical with a card, then About, open (${what})`, async ({ browser }) => {
    const ctx = await browser.newContext(phone ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : {});
    const page = await ctx.newPage();
    await open(page);
    const gid = await photoGid(page);
    const serious = async () => (await new AxeBuilder({ page }).analyze()).violations
      .filter(v => v.impact === 'serious' || v.impact === 'critical').map(v => `${v.id}: ${v.nodes.map(n => n.target).join(', ')}`);
    await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
    await expect(page.locator('#card.pinned')).toBeVisible();
    expect(await serious()).toEqual([]);
    await page.keyboard.press('Escape');
    await page.locator('.about-open').click();
    await expect(page.locator('#about')).toBeVisible();
    expect(await serious()).toEqual([]);
    await ctx.close();
  });
}
