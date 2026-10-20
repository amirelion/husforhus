// What's new: About's second tab (web/news.js, web/news.json), its #about/news link, its actions, the About button's
// dot, in Swedish, on a phone and in every look. Runs on whatever web/data/current.json names.
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}
const news = page => page.evaluate(async () => (await fetch('news.json')).json());
const longDate = (iso, locale) => new Date(`${iso}T00:00:00Z`)
  .toLocaleDateString(locale, { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const tabs = page => ({ about: page.locator('#about-tab-about'), news: page.locator('#about-tab-news') });

test('About opens on About; a click and the arrow keys switch between About and What\'s new', async ({ page }) => {
  await open(page);
  const entries = await news(page);
  await page.locator('.about-open').click();
  const about = page.locator('#about'), tab = tabs(page);
  await expect(about.getByRole('tablist')).toBeVisible();
  await expect(about.getByRole('tab', { name: 'About', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(about.locator('#about-title')).toBeVisible();                 // today's page, with its jump links
  await expect(about.locator('.about-nav a[data-section="sources"]')).toBeVisible();
  await expect(about.locator('#about-panel-news')).toBeHidden();
  // a click
  await about.getByRole('tab', { name: "What's new", exact: true }).click();
  await expect(tab.news).toHaveAttribute('aria-selected', 'true');
  await expect(tab.about).toHaveAttribute('aria-selected', 'false');
  await expect(about.locator('#about-panel-news')).toBeVisible();
  await expect(about.locator('#about-panel-about')).toBeHidden();
  const first = about.locator('.news li').first();
  await expect(first.locator('h3')).toHaveText(entries[0].title.en);
  await expect(first.locator('time')).toHaveText(longDate(entries[0].date, 'en-GB'));   // "20 October 2026"
  await expect(first.locator('.news-kind')).toHaveText(entries[0].kind === 'data' ? 'Data' : 'Feature');
  await expect(about.locator('.news li')).toHaveCount(entries.length);
  // the arrow keys, from the focused tab (the selected tab is the only one in the tab order)
  await expect(tab.news).toBeFocused();
  await expect(tab.about).toHaveAttribute('tabindex', '-1');
  await page.keyboard.press('ArrowLeft');
  await expect(tab.about).toBeFocused();
  await expect(tab.about).toHaveAttribute('aria-selected', 'true');
  await expect(about.locator('#about-panel-about')).toBeVisible();
  await page.keyboard.press('ArrowRight');
  await expect(tab.news).toBeFocused();
  await expect(tab.news).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowRight');                                    // wraps
  await expect(tab.about).toHaveAttribute('aria-selected', 'true');
  // closed and opened again from the button: on About
  await page.keyboard.press('Escape');
  await page.locator('.about-open').click();
  await expect(tab.about).toHaveAttribute('aria-selected', 'true');
});

test('#about/news opens on What\'s new; an About action opens its section; #about/<section> keeps opening About', async ({ page }) => {
  await open(page, '#about/news');
  const tab = tabs(page);
  await expect(page.locator('#about')).toBeVisible();
  await expect(tab.news).toHaveAttribute('aria-selected', 'true');
  await expect(tab.news).toBeFocused();
  await expect(page.locator('#about-panel-news')).toBeVisible();
  // an action into About: the About tab, at that section
  const action = page.locator('#about-panel-news a.news-action[href^="#about/"]').first();
  const section = (await action.getAttribute('href')).slice('#about/'.length);
  await action.click();
  await expect(tab.about).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator(`#about-${section}`)).toBeInViewport();
  await expect(page.locator(`#about-${section}`)).toBeFocused();
  // the existing links open the About tab, even from What's new
  await tab.news.click();
  await page.evaluate(() => { location.hash = '#about/privacy'; });
  await expect(tab.about).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#about-privacy')).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(page.locator('#about')).toBeHidden();
  await expect(page).toHaveURL(u => !new URL(u).hash);
});

test('an action outside About closes it and does what its link says (Tunnelbanan, Stories)', async ({ page }) => {
  await open(page, '?try=stories#about/news');                               // Stories on even in a build without them
  const metro = page.locator('#about-panel-news a.news-action[href="?metro=1"]');
  const stories = page.locator('#about-panel-news button.news-action[data-open="stories"]');
  await expect(stories.first()).toBeVisible();
  if (await metro.count()) {                                                  // only in a build with Tunnelbanan
    await expect(metro.first()).toBeVisible();
    await metro.first().click();
    await expect(page.locator('#about')).toBeHidden();
    await expect.poll(() => page.evaluate(() => window.__dbg.metroOn)).toBe(true);
    await expect(page).toHaveURL(/[?&]metro=1/);
    await page.evaluate(() => window.__dbg.setMetro(false));
    await page.evaluate(() => { location.hash = '#about/news'; });
  }
  await stories.first().click();
  await expect(page.locator('#about')).toBeHidden();
  await expect(page.locator('.stories-open')).toHaveAttribute('aria-expanded', 'true');
});

test('the dot shows for an older stored date and clears once What\'s new is opened; a first visit has none', async ({ page }) => {
  await open(page);
  const entries = await news(page);
  await expect(page.locator('.news-dot')).toBeHidden();                       // a first visit
  expect(await page.evaluate(() => localStorage.getItem('hfh-news'))).toBe(entries[0].date);
  await page.evaluate(() => localStorage.setItem('hfh-news', '2026-10-01'));
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(page.locator('.news-dot')).toBeVisible();
  await page.locator('.about-open').click();
  await expect(page.locator('.news-dot')).toBeVisible();                      // the About tab alone does not clear it
  await tabs(page).news.click();
  await expect(page.locator('.news-dot')).toBeHidden();
  expect(await page.evaluate(() => localStorage.getItem('hfh-news'))).toBe(entries[0].date);
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect(page.locator('.news-dot')).toBeHidden();
});

test('in Swedish: the tabs, the dates and the tags', async ({ page }) => {
  await open(page, '?lang=sv#about/news');
  const entries = await news(page);
  const about = page.locator('#about');
  await expect(about.getByRole('tab', { name: 'Nytt', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(about.getByRole('tab', { name: 'Om kartan', exact: true })).toBeVisible();
  const first = about.locator('.news li').first();
  await expect(first.locator('h3')).toHaveText(entries[0].title.sv);
  await expect(first.locator('time')).toHaveText(longDate(entries[0].date, 'sv-SE'));   // "20 oktober 2026"
  await expect(first.locator('.news-kind')).toHaveText(entries[0].kind === 'data' ? 'Data' : 'Funktion');
  await page.keyboard.press('ArrowLeft');
  await expect(about.getByRole('tab', { name: 'Om kartan', exact: true })).toHaveAttribute('aria-selected', 'true');
});

test('on a phone: both tabs fit, the timeline reads without sideways scrolling, a tap switches', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  await open(page, '#about/news');
  const box = await page.locator('#about').boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
  for (const t of Object.values(tabs(page))) {
    await expect(t).toBeInViewport();
    expect((await t.boundingBox()).height).toBeGreaterThanOrEqual(44);
  }
  expect(await page.locator('#about').evaluate(d => d.scrollWidth <= d.clientWidth + 1)).toBe(true);
  await tabs(page).about.tap();
  await expect(tabs(page).about).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#about-title')).toBeVisible();
  await ctx.close();
});

for (const look of ['arg', 'kalk', 'blatimme', 'paper']) {
  test(`What's new reads in the ${look} look (axe: no contrast or ARIA problems)`, async ({ page }) => {
    await open(page, `?theme=${look}#about/news`);
    await expect(page.locator('#about-panel-news')).toBeVisible();
    const found = (await new AxeBuilder({ page }).include('#about').analyze()).violations
      .filter(v => v.impact === 'serious' || v.impact === 'critical').map(v => `${v.id}: ${v.nodes.map(n => n.target).join(', ')}`);
    expect(found).toEqual([]);
  });
}
