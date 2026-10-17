// The language: the switch turns the whole page without a reload and is
// remembered; ?lang= sets one visit only; a Swedish browser opens in English until city.LANG_FROM_BROWSER turns
// langFromBrowser on, then in Swedish; the no-WebGL message speaks the page's language too.
// Runs on whatever web/data/current.json names.
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

async function expectSwedish(page) {
  await expect(page.locator('html')).toHaveAttribute('lang', 'sv');
  await expect(page.locator('#year')).toHaveText('I dag');
  await expect(page.locator('.tally-count')).toContainText('byggnader');
  await expect(page.locator('.about-open')).toHaveText('Om kartan');
  await expect(page.locator('.modes [data-mode="1"]')).toHaveText('Våningar');
  await expect(page.locator('#play')).toHaveAttribute('aria-label', 'Spela upp stadens tillväxt');
  await expect(page.locator('.look-open')).toContainText('Utseende');
  await expect(page.getByRole('combobox')).toHaveAttribute('placeholder', 'Sök adress, gata eller byggnad');
}

test('the switch turns the page Swedish in place, keeps the address clean and is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);                                                   // Playwright's browser is en-US
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.locator('.lang [data-lang="en"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('.lang [data-lang="sv"]').click();
  await expectSwedish(page);
  await expect(page.locator('#panel h2').first()).toHaveText('Byggår');
  await expect(page.locator('.lang [data-lang="sv"]')).toHaveAttribute('aria-pressed', 'true');
  expect(new URL(page.url()).searchParams.has('lang')).toBe(false);
  expect(await page.evaluate(() => localStorage.getItem('hfh-lang'))).toBe('sv');
  await page.reload();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expectSwedish(page);
  expect(errors).toEqual([]);
});

test('?lang= sets one visit and is not saved; the switch drops it from the address', async ({ page }) => {
  await open(page, '?lang=sv');
  await expectSwedish(page);
  expect(await page.evaluate(() => localStorage.getItem('hfh-lang'))).toBe(null);
  await page.locator('.lang [data-lang="en"]').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  expect(new URL(page.url()).searchParams.has('lang')).toBe(false);
  expect(await page.evaluate(() => localStorage.getItem('hfh-lang'))).toBe('en');
  await open(page, '?lang=sv');                                        // a press link in Swedish: Swedish this visit
  await expectSwedish(page);
  await open(page);                                                   // and the reader's own choice after it
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
});

// A failed start keeps its message when the language switches (it used to become the loading line),
// and a saved Swedish shows the loading line in Swedish before the config is in.
test('a failure after the start keeps its message, in the language the switch picks', async ({ page }) => {
  await page.route('**/pack0.bin.gz', r => r.abort());           // a file the map cannot run without (audit 3)
  await page.goto('/');
  const loading = page.locator('#loading');
  await expect(loading).toHaveText('Could not load the city data. Reload the page to try again.', { timeout: 60_000 });
  await page.locator('.lang [data-lang="sv"]').click();
  await expect(loading).toHaveText('Kunde inte ladda stadens data. Ladda om sidan för att försöka igen.');
  await expect(loading).toBeVisible();
});

test('a saved Swedish shows the loading line in Swedish while the config is on its way', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('hfh-lang', 'sv'));
  let release;
  const held = new Promise(r => { release = r; });
  await page.route('**/stockholm.json', async route => { await held; route.continue(); });
  await page.goto('/');
  await expect(page.locator('#loading')).toContainText('Bygger staden');
  release();
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expectSwedish(page);
});

// The browser-language choice as it may be set (city.LANG_FROM_BROWSER; stockholm.json langFromBrowser): the build's own flag
// is kept as it is, and these tests turn it on in the config the page receives.
const fromBrowser = page => page.route('**/stockholm.json', async route => {
  const response = await route.fetch();
  route.fulfill({ response, json: { ...(await response.json()), langFromBrowser: true } });
});

test.describe('a Swedish browser', () => {
  test.use({ locale: 'sv-SE' });

  test('opens the map in English while the browser-language choice is off, in Swedish once it is on', async ({ page }) => {
    const errors = watchErrors(page);
    const cfg = await page.request.get('/data/current.json').then(r => r.json())
      .then(({ version }) => page.request.get(`/data/${version}/stockholm.json`)).then(r => r.json());
    if (!cfg.langFromBrowser) {
      await open(page);
      await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    }
    await fromBrowser(page);
    await open(page);
    await expectSwedish(page);
    expect(await page.evaluate(() => localStorage.getItem('hfh-lang'))).toBe(null);   // nothing saved until a click
    expect(errors).toEqual([]);
  });

  test('a build without the langFromBrowser key opens in English', async ({ page }) => {
    await page.route('**/stockholm.json', async route => {
      const response = await route.fetch();
      const { langFromBrowser, ...rest } = await response.json();
      route.fulfill({ response, json: rest });
    });
    await open(page);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  });

  test('says in Swedish that the map needs WebGL', async ({ page }) => {
    await fromBrowser(page);
    await page.addInitScript(() => {
      const get = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
        return /webgl/.test(type) ? null : get.call(this, type, ...rest);
      };
    });
    await page.goto('/');
    await expect(page.locator('#loading')).toHaveText(
      'Kartan kräver WebGL, som är avstängt eller saknas i den här webbläsaren.', { timeout: 30_000 });
  });

  test('a module that fails to load is reported in Swedish before any module runs', async ({ page }) => {
    await page.route('**/app.js', r => r.abort());
    await page.goto('/');
    await expect(page.locator('#loading')).toHaveText('Kunde inte ladda stadens data. Ladda om sidan för att försöka igen.');
  });
});
