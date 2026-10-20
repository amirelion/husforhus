// The building card: text first, the photo and the excerpt with their credits, the links, nothing on
// a private house that could give its exact year, focus in and out, Swedish. Runs on whatever web/data/current.json
// names: the fixture in CI, the whole city on a laptop.
import { test, expect } from '@playwright/test';

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}

// Every card of the build, read the way the page reads them (64 shards), with each building's attrs.
const cards = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  // the 64 shards at once: one after another, the whole city's took most of the test's 2 minutes
  const shards = await Promise.all([...Array(64).keys()].map(async k =>
    (await fetch(`data/${version}/cards/${String(k).padStart(2, '0')}.json`)).json()));
  return Object.assign({}, ...shards);
});

// Every excerpt of the build ({gid: {lang: {t, r}}}), from the 64 wiki shards.
const excerpts = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  const shards = await Promise.all([...Array(64).keys()].map(async k =>
    (await (await fetch(`data/${version}/wiki/${String(k).padStart(2, '0')}.json`)).json()).items));
  return Object.assign({}, ...shards);
});

// The first gid whose attrs (window.__dbg.building) pass `test`, or -1.
const firstGid = (page, test) => page.evaluate(async src => {
  const { version } = await (await fetch('data/current.json')).json();
  const n = (await (await fetch(`data/${version}/stockholm.json`)).json()).stats.buildings;
  const ok = new Function('b', `return (${src})(b)`);
  for (let g = 0; g < n; g++) if (ok(window.__dbg.building(g))) return g;
  return -1;
}, test.toString());

async function open(page, query = '') {
  await page.goto('/' + query);
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
}

test('a pinned card shows the photo, the excerpt and the links with their credits, all from this site', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const [all, wiki] = [await cards(page), await excerpts(page)];
  // a card with an English excerpt when the build has one, so the excerpt's credit is checked
  const withPhoto = Object.keys(all).filter(g => all[g].photo && all[g].wp?.length);
  const gid = withPhoto.find(g => wiki[g]?.en) ?? withPhoto[0];
  test.skip(gid === undefined, 'this build has no card with a photo and an article');
  const requests = [];
  page.on('request', r => requests.push(r.url()));
  await page.locator('.about-open').focus();                            // where the focus must come back to
  await page.evaluate(g => window.__dbg.pinCard(+g, 300, 300), gid);
  const card = page.locator('#card.pinned');
  await expect(card).toHaveAttribute('role', 'dialog');
  await expect(card.locator('.card-close')).toBeFocused();              // the keyboard lands in the card
  const photo = all[gid].photo;
  const img = card.locator('.photo img');
  await expect(img).toHaveAttribute('src', `data/photos/${photo.key}`);
  await expect.poll(() => img.evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true);
  await expect(card.locator('.photo figcaption a', { hasText: 'Wikimedia Commons' })).toHaveAttribute('href', photo.page);
  await expect(card.locator('.photo figcaption')).toContainText(photo.by === 'unknown' ? 'unknown photographer' : photo.by);
  // the excerpt, when the build has one in English for it, names its licence and links its revision
  const ex = card.locator('.extract');
  if (wiki[gid]?.en) {
    await expect(ex).toBeVisible();
    await expect(ex).toHaveAttribute('lang', 'en');
    await expect(ex.locator('a', { hasText: 'CC BY-SA 4.0' })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/');
    await expect(ex.locator('a', { hasText: 'Wikipedia' })).toHaveAttribute('href', /^https:\/\/en\.wikipedia\.org\/w\/index\.php\?oldid=\d+$/);
  }
  await expect(card.locator('.sources a', { hasText: 'Wikidata' })).toHaveAttribute('href', `https://www.wikidata.org/wiki/${all[gid].qid}`);
  // no request leaves the site: the photo is our copy (the privacy section promises it)
  const origin = new URL(page.url()).origin;
  expect(requests.filter(u => !u.startsWith(origin))).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(card).toBeHidden();
  await expect(page.locator('.about-open')).toBeFocused();
  expect(errors).toEqual([]);
});

test.describe('on a laptop screen', () => {
  test.use({ viewport: { width: 1280, height: 800 } });
  test('a tall pinned card stays clear of the title, the corner buttons and the timeline, and scrolls inside', async ({ page }) => {
    await open(page);
    const all = await cards(page);
    const gid = Object.keys(all).find(g => all[g].photo && all[g].wp?.length) ?? Object.keys(all)[0];
    await page.evaluate(g => window.__dbg.pinCard(+g, 1100, 700), gid);     // pinned low on the right
    await expect(page.locator('#card.pinned')).toBeVisible();
    const box = s => page.locator(s).boundingBox();
    const [card, tally, buttons, hist] = [await box('#card'), await box('.corner .tally'), await box('.corner .buttons'),
      await box('#hist')];
    const apart = (a, b) => a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y;
    expect(apart(card, tally) && apart(card, buttons), 'the card covers the corner').toBe(true);
    expect(card.y + card.height).toBeLessThanOrEqual(hist.y);
    // a card taller than that room scrolls inside it (its max-height is the room)
    expect(await page.locator('#card').evaluate(el => getComputedStyle(el).overflowY)).toBe('auto');
  });
});

test('a private house card shows its decade and nothing that could give the year away', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  // a decade-dated private house whose card carries an architect: the architect's row shows that the card's shard has
  // arrived, so the checks for what must be absent run on the whole card
  const all = await cards(page);
  const gid = await page.evaluate(gids => gids.find(g => { const b = window.__dbg.building(g);
    return b.private === 1 && b.yflag !== 6 && b.yflag !== 7; }) ?? -1,
  Object.keys(all).filter(g => all[g].architects?.length).map(Number));
  test.skip(gid < 0, 'this build has no dated private house with an architect on its card');
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  const card = page.locator('#card.pinned');
  await expect(card.locator('dd', { hasText: all[gid].architects[0] })).toBeVisible();
  await expect(card.locator('.card-head .y')).toHaveText(/^(≈ )?(\d{3}0s|\d{2}00–\d{2}09)$/);
  await expect(card.locator('.dating')).toContainText('private house: decade only');
  await expect(card.locator('.photo, .extract')).toHaveCount(0);
  await expect(card.locator('.sources')).toHaveCount(0);                 // no RAÄ, Wikipedia or Wikidata link
  expect(errors).toEqual([]);
});

test('the hover card is the band and how the year is known; Swedish when the language is', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => {
    const fetch0 = window.fetch;
    window.fetch = async (url, init) => {
      const r = await fetch0(url, init);
      if (!String(url).endsWith('/stockholm.json')) return r;
      const config = await r.json();
      config.features = { ...config.features, lang: true };
      return new Response(JSON.stringify(config), { headers: { 'content-type': 'application/json' } });
    };
  });
  await open(page, '?lang=sv');
  const gid = await firstGid(page, b => b.yflag === 7);
  test.skip(gid < 0, 'this build has no building without a year');
  await page.evaluate(g => window.__dbg.showCard(g, 300, 300), gid);
  const card = page.locator('#card');
  await expect(card.locator('.card-head .y')).toHaveText('Okänt byggår');
  await expect(card.locator('.dating')).toHaveText('Inget öppet register daterar byggnaden ännu.');
  await expect(card.locator('.hint')).toHaveText('Klicka för mer');
  await expect(card.locator('dl')).toHaveCount(0);                       // facts only on a pinned card
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  await expect(page.locator('#card.pinned dt').first()).toHaveText('Höjd');
  await expect(page.locator('#card.pinned dd').first()).toHaveText(/^\d+(,\d)? m till taket$/);
  expect(errors).toEqual([]);
});

test('a card names its address and stadsdel in its band', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const all = await cards(page);
  const several = Object.keys(all).filter(g => all[g].addr && all[g].addrn > 1);
  test.skip(several.length === 0, 'this build has no card with several addresses');
  // the stadsdel comes from districts.bin.gz, fetched with the first card; then one of them that lies in a stadsdel
  // (a building outside every stadsdel has none, and would wait in vain)
  await page.evaluate(g => window.__dbg.showCard(+g, 300, 300), several[0]);
  const cardGids = Object.keys(all);
  await expect.poll(() => page.evaluate(gs => gs.some(g => window.__dbg.districtOf(+g) !== ''), cardGids)).toBe(true);
  const gid = await page.evaluate(gs => gs.find(g => window.__dbg.districtOf(+g) !== ''), several);
  test.skip(gid === undefined, 'no card with several addresses lies in a stadsdel');
  const { addr, addrn } = all[gid];
  await page.evaluate(g => window.__dbg.showCard(+g, 300, 300), gid);   // the hover card has it too
  const dist = await page.evaluate(g => window.__dbg.districtOf(+g), gid);
  await expect(page.locator('#card .card-head .place')).toHaveText(`${addr} (and ${addrn - 1} more) · ${dist}`);
  await page.evaluate(g => window.__dbg.pinCard(+g, 300, 300), gid);
  await expect(page.locator('#card.pinned .card-head .place')).toHaveText(`${addr} (and ${addrn - 1} more) · ${dist}`);
  expect(errors).toEqual([]);
});

// A curated card's rebuilds show as a second line under the dating line on the pinned card, never on the
// hover card, and older cellars change the dating line on both. No curated entry carries them yet, so the test adds
// them to the first timeline landmark's card as its shard reaches the page (§14's example years).
test('a curated card shows its rebuilds when pinned, never on hover, and its older cellars on both', async ({ page }) => {
  const errors = watchErrors(page);
  let gid = -1;
  await page.route('**/cards/*.json', async route => {
    const r = await route.fetch();
    const shard = await r.json();
    if (gid >= 0 && route.request().url().endsWith(`/${String(gid % 64).padStart(2, '0')}.json`)) {
      shard[gid] = { ...shard[gid], rebuilt: [[1757, 'rebuilt'], [1857, 'raised']], cellars: true };
    }
    await route.fulfill({ response: r, json: shard });
  });
  await open(page);
  gid = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    return (await (await fetch(`data/${version}/stockholm.json`)).json()).landmarks[0]?.gid ?? -1;
  });
  test.skip(gid < 0, 'this build has no timeline landmark');
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  const card = page.locator('#card.pinned');
  await expect(card.locator('.rebuilt')).toHaveText('Rebuilt 1757 · raised 1857');
  await expect(card.locator('.dating')).toHaveText(/^Hand-checked landmark: built [\d–]+ on older cellar walls$/);
  // the rebuild line stands right under the dating line, in its colour and size
  const [dating, rebuilt] = await Promise.all([card.locator('.dating'), card.locator('.rebuilt')].map(l => l.evaluate(el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return { top: r.top, bottom: r.bottom, color: s.color, size: s.fontSize, next: el.nextElementSibling?.className };
  })));
  expect(dating.next).toBe('rebuilt');
  expect(Math.abs(rebuilt.top - dating.bottom)).toBeLessThan(1);
  expect([rebuilt.color, rebuilt.size]).toEqual([dating.color, dating.size]);
  await page.evaluate(() => window.__dbg.pinCard(-1));
  await expect(page.locator('#card.pinned')).toHaveCount(0);
  await page.evaluate(g => window.__dbg.showCard(g, 300, 300), gid);
  await expect(page.locator('#card .hint')).toBeVisible();                // the hover card
  await expect(page.locator('#card .dating')).toHaveText(/on older cellar walls$/);
  await expect(page.locator('#card .rebuilt')).toHaveCount(0);
  expect(errors).toEqual([]);
});

// The City Museum's building-archaeology register (PR 57): a pinned card of a building it covers shows the section,
// with its report links to Digitala Stadsmuseet and the credit; the hover card and a building it does not cover never do.
test('a building the City Museum documented shows its building archaeology when pinned, never on hover', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const [withBr, without] = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    let a = -1, b = -1;
    for (let k = 0; k < 64 && (a < 0 || b < 0); k++) {
      const shard = await (await fetch(`data/${version}/cards/${String(k).padStart(2, '0')}.json`)).json();
      for (const [g, c] of Object.entries(shard)) {
        if (a < 0 && c.br?.inv?.some(e => e.report)) a = +g;
        if (b < 0 && !c.br && c.name) b = +g;
      }
    }
    return [a, b];
  });
  test.skip(withBr < 0, 'this build has no City Museum register');
  await page.evaluate(g => window.__dbg.showCard(g, 400, 300), withBr);
  await expect(page.locator('#card .archaeology')).toHaveCount(0);
  await page.evaluate(g => window.__dbg.pinCard(g, 400, 300), withBr);
  const s = page.locator('#card.pinned .archaeology');
  await expect(s.locator('h4')).toHaveText('Building archaeology');
  await expect(s.locator('.reports a').first()).toHaveAttribute('href', /^https:\/\/digitalastadsmuseet\.stockholm\.se\//);
  await expect(s.locator('.credit')).toHaveText('Stadsmuseet i Stockholm');
  await page.evaluate(g => window.__dbg.pinCard(g, 400, 300), without);
  await expect(page.locator('#card.pinned')).toBeVisible();
  await expect(page.locator('#card .archaeology')).toHaveCount(0);
});
