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

// A permit-dated building (ysrc 10, codes.SRC_BYGGLOV): the fixture (Gamla stan, which the tier leaves out) has none, so
// CI skips this; on a laptop's full-city build it pins the card's wording (web/test/card.test.mjs holds the logic).
test('a permit-dated card names the archive and, on a private house, only its decade', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const priv = await firstGid(page, b => b.ysrc === 10 && b.private === 1);
  const pub = await firstGid(page, b => b.ysrc === 10 && b.private !== 1);
  test.skip(priv < 0 && pub < 0, 'this build has no permit-dated building');
  const card = page.locator('#card.pinned');
  if (priv >= 0) {
    await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), priv);
    const head = card.locator('.card-head .y');
    await expect(head).toHaveText(/^(\d{3}0s|\d{2}00–\d{2}09)$/);           // a record: no "≈"
    // the line, then the "Why?" link to About's privacy section that every private house's line ends with
    await expect(card.locator('.dating')).toHaveText(
      /^Building permit closed (in the \d{3}0s|\d{2}00–\d{2}09) \(Stadsarkivet\) · private house: decade only Why\?$/);
    await expect(card.locator('.sources')).toHaveCount(0);
    const start = Number((await head.textContent()).slice(0, 4));
    const html = await card.innerHTML();
    // no year but the decade's ends, and no link to the archive's card page (it shows the designation and the year)
    const runs = (await card.innerText()).match(/\d{4,}/g) || [];
    expect(runs.filter(y => ![start, start + 9].includes(Number(y)))).toEqual([]);
    expect(html).not.toContain('/Visa/');
    expect(html).not.toContain('bygglov1875');
  }
  if (pub >= 0) {
    await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), pub);
    const year = (await card.locator('.card-head .y').textContent()).trim();
    expect(year).toMatch(/^\d{4}$/);
    await expect(card.locator('.dating')).toHaveText(`Building permit closed ${year} (Stadsarkivet)`);
  }
  await open(page, '?lang=sv');
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), priv >= 0 ? priv : pub);
  await expect(card.locator('.dating')).toHaveText(priv >= 0
    ? /^Bygglov avslutat (på \d{3}0-talet|\d{2}00–\d{2}09) \(Stadsarkivet\) · småhus: bara årtiondet Varför\?$/
    : /^Bygglov avslutat \d{4} \(Stadsarkivet\)$/);
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
      shard[gid] = { ...shard[gid], rebuilt: [[1757, 'rebuilt'], [1857, 'raised']], cellars: true,
        also: [[1805, 1818]] };
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
  // the other house on its footprint (pipeline/landmarks.py `also`, Historiska museet's range: D65) after the rebuilds
  await expect(card.locator('.rebuilt'))
    .toHaveText('Rebuilt 1757 · raised 1857 · Also part of this building: a house built 1805–1818');
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

// A cited record where two sources differ (pipeline/cited.py's either pair), the rebuilds and other houses the records
// name, and a cited period no map period holds 3/4 of (decided 2026-10-20: shown, not held). No build carries them yet,
// so the test adds them to two "Year unknown" buildings' cards as their shards reach the page: the uncoloured case,
// where the card still gives what the records say, its header too. The coloured one (one period holding the readings,
// PERIOD) and Swedish are web/test/card.test.mjs's.
test('a cited card gives both readings where sources differ, its rebuilds when pinned, and a span no period holds', async ({ page }) => {
  const errors = watchErrors(page);
  const WP = 'https://sv.wikipedia.org/w/index.php?oldid=53738008', WP2 = 'https://sv.wikipedia.org/w/index.php?oldid=55051795';
  const KN = 'https://kulturnav.org/74ce2767-f09f-4bdf-b86e-ea22dbd632b6';
  const add = {};
  await page.route('**/cards/*.json', async route => {
    const r = await route.fetch();
    const shard = await r.json();
    for (const [g, yc] of Object.entries(add)) {
      if (route.request().url().endsWith(`/${String(g % 64).padStart(2, '0')}.json`)) shard[g] = { ...shard[g], yc };
    }
    await route.fulfill({ response: r, json: shard });
  });
  await open(page);
  // two "Year unknown" buildings that are no private house, in two shards
  const [g1, g2] = await page.evaluate(async () => {
    const { version } = await (await fetch('data/current.json')).json();
    const n = (await (await fetch(`data/${version}/stockholm.json`)).json()).stats.buildings;
    const out = [];
    for (let g = 0; g < n && out.length < 2; g++) {
      const b = window.__dbg.building(g);
      if (b.yflag === 7 && b.ysrc === 0 && !b.private && (!out.length || out[0] % 64 !== g % 64)) out.push(g);
    }
    return out;
  });
  test.skip(g2 === undefined, 'this build has no two "Year unknown" buildings');
  add[g1] = { e: [{ a: 1785, z: 1785, s: 'wikipedia_sv', u: WP }, { a: 1798, z: 1798, s: 'kulturnav', u: KN }],
    r: [{ a: 1907, z: 1907, s: 'wikipedia_sv', u: WP }, { a: 1947, z: 1947, s: 'wikipedia_sv', u: WP2 }],
    o: [{ a: 1804, z: 1804, s: 'kulturnav', u: KN }] };
  add[g2] = { s: 'wikipedia_sv', u: WP2, a: 1600, z: 1624 };
  const links = l => l.evaluateAll(as => as.map(a => [a.textContent, a.href, a.title, a.target]));

  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), g1);
  const card = page.locator('#card.pinned');
  await expect(card.locator('.dating')).toHaveText(/^Built in 1785 or 1798 \(sources differ\)/);
  // each reading links its own record, the source named in its title; no colour, and the header says the sources differ
  expect(await links(card.locator('.dating a.cited'))).toEqual([
    ['1785', WP, 'Swedish Wikipedia', '_blank'], ['1798', KN, 'KulturNav (ArkDes)', '_blank']]);
  await expect(card.locator('.when .y')).toHaveText('Sources differ');
  // the rebuilds and the other house: the second line, each year linked to its record
  await expect(card.locator('.rebuilt')).toHaveText('Rebuilt or extended 1907 and 1947 · Also part of this building: a house built 1804');
  expect(await links(card.locator('.rebuilt a.cited'))).toEqual([
    ['1907', WP, 'Swedish Wikipedia', '_blank'], ['1947', WP2, 'Swedish Wikipedia', '_blank'],
    ['1804', KN, 'KulturNav (ArkDes)', '_blank']]);
  // the hover card: the line, never the rebuilds
  await page.evaluate(() => window.__dbg.pinCard(-1));
  await expect(page.locator('#card.pinned')).toHaveCount(0);
  await page.evaluate(g => window.__dbg.showCard(g, 300, 300), g1);
  await expect(page.locator('#card .hint')).toBeVisible();
  await expect(page.locator('#card .dating')).toHaveText('Built in 1785 or 1798 (sources differ)');
  await expect(page.locator('#card .rebuilt')).toHaveCount(0);

  // a cited period no map period holds 3/4 of: no colour on the map, the record's words on the card, linked, and in
  // the header ("the beginning of the 1600s", 1600–1624)
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), g2);
  await expect(card.locator('.dating')).toHaveText(/^≈ built in the early 1600s · Swedish Wikipedia/);
  expect(await links(card.locator('.dating a.cited'))).toEqual([['≈ built in the early 1600s · Swedish Wikipedia', WP2, '', '_blank']]);
  await expect(card.locator('.when .y')).toHaveText('≈ early 1600s');
  await expect(card.locator('.rebuilt')).toHaveCount(0);
  expect(errors).toEqual([]);
});

// AB Stadsholmen's fact sheets (D64): the card names the sheet as written with the City Museum and links the company's
// property list, never a sheet (each PDF is named by the property designation). Added to a "Year unknown" building's
// card as its shard reaches the page, so the test runs on the fixture too: an early-1600s span no period holds, a
// rebuild and another house.
test('a year from AB Stadsholmen\'s fact sheet names the sheet and links the property list', async ({ page }) => {
  const errors = watchErrors(page);
  const LIST = 'https://www.stadsholmen.se/fastigheter/', NAME = 'AB Stadsholmen\'s fact sheet (with the City Museum)';
  let gid = -1;
  await page.route('**/cards/*.json', async route => {
    const r = await route.fetch();
    const shard = await r.json();
    if (gid >= 0 && route.request().url().endsWith(`/${String(gid % 64).padStart(2, '0')}.json`)) {
      shard[gid] = { ...shard[gid], yc: { s: 'stadsholmen', u: LIST, a: 1600, z: 1624,
        r: [{ a: 1750, z: 1750, c: true, s: 'stadsholmen', u: LIST }], o: [{ a: 1646, z: 1646, s: 'stadsholmen', u: LIST }] } };
    }
    await route.fulfill({ response: r, json: shard });
  });
  await open(page);
  gid = await firstGid(page, b => b.yflag === 7 && b.ysrc === 0 && !b.private);
  test.skip(gid < 0, 'this build has no "Year unknown" building');
  const links = l => l.evaluateAll(as => as.map(a => [a.textContent, a.href, a.title]));
  await page.evaluate(g => window.__dbg.pinCard(g, 300, 300), gid);
  const card = page.locator('#card.pinned');
  await expect(card.locator('.dating')).toHaveText(new RegExp(`^≈ built in the early 1600s · ${NAME.replace(/[()]/g, '\\$&')}`));
  expect(await links(card.locator('.dating a.cited'))).toEqual([[`≈ built in the early 1600s · ${NAME}`, LIST, '']]);
  await expect(card.locator('.rebuilt')).toHaveText('Rebuilt or extended about 1750 · Also part of this building: a house built 1646');
  expect(await links(card.locator('.rebuilt a.cited'))).toEqual([['1750', LIST, NAME], ['1646', LIST, NAME]]);
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
