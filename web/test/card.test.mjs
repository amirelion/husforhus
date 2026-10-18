import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { yearLine, sourceLine, floorsLine, heightLine, towerLine, ratingLine, protLine, photoCredit, extractFor, cardLinks, fillUrl,
  decade, band, decadeOnly, isEstimate, rebuildLine, placeLine, whyAnchor } from '../card.js';
import { makeT } from '../i18n.js';
import { YFLAG, YSRC, FSRC } from '../codes.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');
const LINKS = {   // pipeline/city.py LINKS, as stockholm.json carries them
  raa: 'https://pub.raa.se/visa/objekt/bebyggelse/{id}', wikidata: 'https://www.wikidata.org/wiki/{qid}',
  wikipedia: 'https://www.wikidata.org/wiki/Special:GoToLinkedPage/{lang}wiki/{qid}',
  wikipedia_rev: 'https://{lang}.wikipedia.org/w/index.php?oldid={rev}',
};
const b = o => ({ year: 0, yearFrom: 0, yearTo: 0, yflag: YFLAG.UNKNOWN, ysrc: YSRC.NONE, fsrc: FSRC.HEIGHT, floors: 1,
  height: 10, rating: 0, private: 0, ...o });

test('yearLine', () => {
  assert.equal(yearLine(b({ year: 1927, yflag: YFLAG.RANGE, ysrc: YSRC.RAA }), '', EN), '1927');
  assert.equal(yearLine(b({ year: 1650, yflag: YFLAG.LONG, ysrc: YSRC.RAA }), '', EN), '1650');
  // A private house shows only its decade, whatever its yflag; an estimated or area-dated one says so
  assert.equal(yearLine(b({ year: 1950, yflag: YFLAG.EXACT, ysrc: YSRC.RAA, private: 1 }), '', EN), '1950s');
  assert.equal(yearLine(b({ year: 1930, yflag: YFLAG.AREA, ysrc: YSRC.RAA_AREA, private: 1 }), '', EN), '≈ 1930s');
  assert.equal(yearLine(b({ year: 1938, yflag: YFLAG.AREA, ysrc: YSRC.RAA_AREA }), '', EN), '≈ 1938');
  assert.equal(yearLine(b({}), '', EN), 'Year unknown');
  assert.equal(yearLine(b({}), '', SV), 'Okänt byggår');                         // Swedish too
  assert.equal(yearLine(b({ year: 1935, yflag: YFLAG.PERIOD }), 'Funkis', EN), 'Funkis');
  assert.equal(yearLine(b({ year: 1952, yearFrom: 1947, yearTo: 1957, yflag: YFLAG.ESTIMATE, ysrc: YSRC.ESTIMATE }), '', EN), '≈ 1952');
  assert.equal(yearLine(b({ year: 1630, yflag: YFLAG.EXACT, ysrc: YSRC.WIKIDATA }), '', EN), '1630');
  // a source that said only the decade reads as the decade; "~1920" as 1920; RAÄ's completion year as before
  assert.equal(yearLine(b({ year: 1640, yearFrom: 1640, yearTo: 1649, yflag: YFLAG.RANGE, ysrc: YSRC.WIKIDATA }), '', SV), '1640-talet');
  assert.equal(yearLine(b({ year: 1920, yearFrom: 1915, yearTo: 1925, yflag: YFLAG.RANGE, ysrc: YSRC.OSM }), '', EN), '1920');
  assert.equal(yearLine(b({ year: 1649, yearFrom: 1640, yearTo: 1649, yflag: YFLAG.RANGE, ysrc: YSRC.RAA }), '', EN), '1649');
});

test('every period in city.py has an English and a Swedish label, so a period-only card names its period', () => {
  const py = readFileSync(new URL('../../pipeline/city.py', import.meta.url), 'utf8');
  const block = py.slice(py.indexOf('PERIODS = ['), py.indexOf('\n]', py.indexOf('PERIODS = [')));
  const rows = [...block.matchAll(/^\s*\("(p\d+)",\s*"([^"]*)",\s*"([^"]*)",/gm)];
  assert.equal(rows.length, 12);
  for (const [, key, en, sv] of rows) {
    assert.ok(en.trim() && sv.trim(), `${key}: both labels`);
    assert.equal(yearLine(b({ year: 1935, yflag: YFLAG.PERIOD, ysrc: YSRC.ESTIMATE, private: 1 }), sv, SV), sv);
  }
});

// Every kind of building has a fixed dating line in both languages (docs: r4 §2.3).
const KINDS = [
  [{ year: 1924, yearFrom: 1924, yearTo: 1924, yflag: YFLAG.EXACT, ysrc: YSRC.RAA },
    'Heritage register (RAÄ): built 1924', 'Bebyggelseregistret (RAÄ): byggt 1924'],
  [{ year: 1927, yearFrom: 1924, yearTo: 1927, yflag: YFLAG.RANGE, ysrc: YSRC.RAA },
    'Heritage register (RAÄ): built 1924–1927', 'Bebyggelseregistret (RAÄ): byggt 1924–1927'],
  [{ year: 1640, yearFrom: 1640, yearTo: 1890, yflag: YFLAG.LONG, ysrc: YSRC.RAA },
    'Heritage register (RAÄ): 1640–1890, a long building history; the map shows the first year',
    'Bebyggelseregistret (RAÄ): 1640–1890, lång byggnadshistoria; kartan visar det första året'],
  [{ year: 1931, yearFrom: 1931, yearTo: 1931, yflag: YFLAG.EXACT, ysrc: YSRC.RAA_OLD },
    'Heritage register (RAÄ, earlier inventory): built 1931', 'Bebyggelseregistret (RAÄ, tidigare inventering): byggt 1931'],
  [{ year: 1931, yearFrom: 1931, yearTo: 1931, yflag: YFLAG.EXACT, ysrc: YSRC.WIKIDATA }, 'Wikidata: built 1931', 'Wikidata: byggt 1931'],
  [{ year: 1640, yearFrom: 1640, yearTo: 1649, yflag: YFLAG.RANGE, ysrc: YSRC.WIKIDATA },
    'Wikidata: built in the 1640s', 'Wikidata: byggt på 1640-talet'],
  [{ year: 1700, yearFrom: 1700, yearTo: 1709, yflag: YFLAG.RANGE, ysrc: YSRC.OSM },
    'OpenStreetMap contributors: built 1700–1709', 'OpenStreetMap-bidragsgivare: byggt 1700–1709'],
  [{ year: 1931, yearFrom: 1931, yearTo: 1931, yflag: YFLAG.EXACT, ysrc: YSRC.OSM },
    'OpenStreetMap contributors: built 1931', 'OpenStreetMap-bidragsgivare: byggt 1931'],
  [{ year: 1754, yearFrom: 1697, yearTo: 1754, yflag: YFLAG.RANGE, ysrc: YSRC.CURATED },
    'Hand-checked landmark: built 1697–1754', 'Kontrollerat landmärke: byggt 1697–1754'],
  [{ year: 1972, yearFrom: 1965, yearTo: 1975, yflag: YFLAG.AREA, ysrc: YSRC.RAA_AREA },
    '≈ dated with its whole area (RAÄ)', '≈ daterat utifrån hela området (RAÄ)'],
  [{ year: 1952, yearFrom: 1947, yearTo: 1957, yflag: YFLAG.ESTIMATE, ysrc: YSRC.ESTIMATE },
    '≈ estimated from similar dated buildings nearby (±5 years)', '≈ uppskattat utifrån liknande daterade byggnader i närheten (±5 år)'],
  [{ year: 1952, yearFrom: 1946, yearTo: 1964, yflag: YFLAG.PERIOD, ysrc: YSRC.ESTIMATE },
    '≈ period only, estimated from neighbours', '≈ bara perioden, uppskattad utifrån grannarna'],
  [{}, 'No open record dates this building yet.', 'Inget öppet register daterar byggnaden ännu.'],
];

test('sourceLine for every kind, in English and Swedish', () => {
  for (const [o, en, sv] of KINDS) {
    assert.equal(sourceLine(b(o), EN), en);
    assert.equal(sourceLine(b(o), SV), sv);
  }
  // a band cut by 2026 still reads as its full width
  assert.equal(sourceLine(b({ year: 2024, yearFrom: 2019, yearTo: 2026, yflag: YFLAG.ESTIMATE, ysrc: YSRC.ESTIMATE }), EN),
    '≈ estimated from similar dated buildings nearby (±5 years)');
  assert.equal(band(b({ year: 1952, yearFrom: 1947, yearTo: 1957 })), 5);
  assert.equal(band(b({ year: 2024, yearFrom: 2014, yearTo: 2026 })), 10);
});

// A curated card's rebuilds on a second line, never with "≈"; a building
// rebuilt from new on older cellars says so in its dating line.
test('rebuildLine and the cellar wording, in English and Swedish', () => {
  const card = { rebuilt: [[1757, 'rebuilt'], [1857, 'raised']] };
  assert.equal(rebuildLine(card, EN), 'Rebuilt 1757 · raised 1857');
  assert.equal(rebuildLine(card, SV), 'Ombyggt 1757 · påbyggt 1857');
  assert.equal(rebuildLine({ rebuilt: [[1935, 'extended']] }, EN), 'Extended 1935');
  assert.equal(rebuildLine({ rebuilt: [[1935, 'extended']] }, SV), 'Tillbyggt 1935');
  for (const c of [{}, { rebuilt: [] }, undefined, { rebuilt: [[1900, 'facade']] }]) assert.equal(rebuildLine(c, EN), '');
  const palace = b({ year: 1754, yearFrom: 1697, yearTo: 1754, yflag: YFLAG.RANGE, ysrc: YSRC.CURATED });
  assert.equal(sourceLine(palace, EN, { cellars: true }), 'Hand-checked landmark: built 1697–1754 on older cellar walls');
  assert.equal(sourceLine(palace, SV, { cellars: true }), 'Kontrollerat landmärke: byggt 1697–1754 på äldre källarmurar');
  assert.equal(sourceLine(palace, EN, {}), 'Hand-checked landmark: built 1697–1754');
  assert.equal(sourceLine(palace, SV), 'Kontrollerat landmärke: byggt 1697–1754');
  // cellars belong to a curated entry only: another source's line never takes the wording
  const raa = b({ year: 1863, yearFrom: 1863, yearTo: 1863, yflag: YFLAG.EXACT, ysrc: YSRC.RAA });
  assert.equal(sourceLine(raa, EN, { cellars: true }), 'Heritage register (RAÄ): built 1863');
});

// Every kNN estimate is a private house (houses only, and a private house shows only its decade), published as its decade: the card says it is an
// estimate and how the decade is known, then the decade rule; never the span or the band.
const PRIVATE = [
  [YFLAG.ESTIMATE, YSRC.ESTIMATE, '≈ 1950s', '≈ 1950-talet', '≈ estimated from similar dated houses nearby · private house: decade only',
    '≈ uppskattat utifrån liknande daterade hus i närheten · småhus: bara årtiondet'],
  [YFLAG.AREA, YSRC.RAA_AREA, '≈ 1950s', '≈ 1950-talet', '≈ dated with its whole area (RAÄ) · private house: decade only',
    '≈ daterat utifrån hela området (RAÄ) · småhus: bara årtiondet'],
  [YFLAG.EXACT, YSRC.RAA, '1950s', '1950-talet', 'Heritage register (RAÄ) · private house: decade only',
    'Bebyggelseregistret (RAÄ) · småhus: bara årtiondet'],
  [YFLAG.RANGE, YSRC.RAA_OLD, '1950s', '1950-talet', 'Heritage register (RAÄ, earlier inventory) · private house: decade only',
    'Bebyggelseregistret (RAÄ, tidigare inventering) · småhus: bara årtiondet'],
  [YFLAG.LONG, YSRC.WIKIDATA, '1950s', '1950-talet', 'Wikidata · private house: decade only', 'Wikidata · småhus: bara årtiondet'],
  [YFLAG.EXACT, YSRC.OSM, '1950s', '1950-talet', 'OpenStreetMap contributors · private house: decade only',
    'OpenStreetMap-bidragsgivare · småhus: bara årtiondet'],
];

test('a private house says how its decade is known, and an estimated one says ≈, in English and Swedish', () => {
  for (const [yflag, ysrc, yearEn, yearSv, sourceEn, sourceSv] of PRIVATE) {
    const h = b({ year: 1950, yearFrom: 1950, yearTo: 1959, yflag, ysrc, private: 1 });
    assert.equal(yearLine(h, '', EN), yearEn);
    assert.equal(yearLine(h, '', SV), yearSv);
    assert.equal(sourceLine(h, EN), sourceEn);
    assert.equal(sourceLine(h, SV), sourceSv);
    for (const text of [yearLine(h, '', EN), sourceLine(h, EN), yearLine(h, '', SV), sourceLine(h, SV)]) {
      assert.doesNotMatch(text, /±|years|år\b|195[1-9]|–/, text);          // never a band or a span
    }
  }
  const p = b({ year: 1930, yearFrom: 1930, yearTo: 1939, yflag: YFLAG.PERIOD, ysrc: YSRC.ESTIMATE, private: 1 });
  assert.equal(yearLine(p, 'Funktionalism', SV), 'Funktionalism');
  assert.equal(sourceLine(p, SV), 'Småhus: bara perioden, uppskattad utifrån grannarna');
  assert.equal(sourceLine(p, EN), 'Private house: period only, estimated from neighbours');
});

test('a decade that starts a century prints as its ten years, in English and Swedish', () => {
  for (const y of [1600, 1700, 1800, 1900, 2000]) {
    for (const T of [EN, SV]) {
      assert.equal(decade(y + 5, T.lang), `${y}–${y + 9}`);
      const house = { year: y, yearFrom: y, yearTo: y + 9, private: 1 };
      assert.equal(yearLine(b({ ...house, yflag: YFLAG.EXACT, ysrc: YSRC.RAA }), '', T), `${y}–${y + 9}`);
      assert.equal(yearLine(b({ ...house, yflag: YFLAG.ESTIMATE, ysrc: YSRC.ESTIMATE }), '', T), `≈ ${y}–${y + 9}`);
    }
  }
  assert.equal(yearLine(b({ year: 1700, yearFrom: 1700, yearTo: 1709, yflag: YFLAG.RANGE, ysrc: YSRC.WIKIDATA }), '', EN), '1700–1709');
  assert.deepEqual([decade(1950), decade(1950, 'sv'), decade(1910), decade(1990, 'sv'), decade(2010), decade(1609)],
    ['1950s', '1950-talet', '1910s', '1990-talet', '2010s', '1600–1609']);
  assert.ok(decadeOnly(b({ year: 1640, yearFrom: 1640, yearTo: 1649, yflag: YFLAG.RANGE })));
});

// The legend's note promises that "the card says whether from an area or from neighbours" for every estimated year.
test('the card says area or neighbours for every estimated year, as the legend promises', () => {
  const area = /area|område/, near = /neighbours|nearby|grannarna|närheten/;
  for (const priv of [0, 1]) {
    for (const T of [EN, SV]) {
      const year = { year: 1950, yearFrom: 1950, yearTo: 1959, private: priv };
      assert.match(sourceLine(b({ ...year, yflag: YFLAG.AREA, ysrc: YSRC.RAA_AREA }), T), area);
      assert.match(sourceLine(b({ ...year, yflag: YFLAG.ESTIMATE, ysrc: YSRC.ESTIMATE }), T), near);
      assert.match(sourceLine(b({ ...year, yflag: YFLAG.PERIOD, ysrc: YSRC.ESTIMATE }), T), near);
      for (const yflag of [YFLAG.AREA, YFLAG.ESTIMATE]) {
        assert.match(yearLine(b({ ...year, yflag, ysrc: YSRC.ESTIMATE }), '', T), /^≈ /);
        assert.ok(isEstimate(b({ yflag })));
      }
    }
  }
});

test('height, floors, rating and protection lines', () => {
  assert.equal(heightLine(b({ height: 18.4 }), EN), '18.4 m to the roof');
  assert.equal(heightLine(b({ height: 18.4 }), SV), '18,4 m till taket');
  assert.equal(floorsLine(b({ floors: 5, fsrc: FSRC.HEIGHT }), EN), '≈ 5 (from its height)');
  assert.equal(floorsLine(b({ floors: 7, fsrc: FSRC.OSM }), SV), '7 (OpenStreetMap)');
  assert.equal(floorsLine(b({ floors: 5 }), EN, { nofloors: true }), '');          // a church: no floors row
  assert.equal(ratingLine(1, EN), 'Blue: exceptional heritage value');
  assert.equal(ratingLine(3, SV), 'Gult: positiv betydelse för stadsbilden och/eller visst kulturhistoriskt värde');
  assert.equal(ratingLine(0, EN), '');
  assert.equal(protLine({ prot: 1, since: 1935 }, EN), 'State-listed building (statligt byggnadsminne) since 1935');
  assert.equal(protLine({ prot: 2, since: 1978 }, SV), 'Byggnadsminne sedan 1978');
  assert.equal(protLine({ prot: 2 }, EN), 'Listed building (byggnadsminne)');
  assert.equal(protLine({ prot: 3, since: 1990 }, SV), 'Kyrkligt kulturminne');     // church heritage has no "since"
  assert.equal(protLine({}, EN), '');
});

test('the photo credit names the author, the title where asked, the licence and Commons', () => {
  const photo = { key: 'a.jpg', by: 'Ann Foto', lic: 'CC BY-SA 3.0', title: 'Kyrkan 2012',
    lu: 'https://creativecommons.org/licenses/by-sa/3.0', page: 'https://commons.wikimedia.org/w/index.php?curid=42' };
  assert.deepEqual(photoCredit(photo, EN), [{ text: 'Photo: Ann Foto' }, { text: '“Kyrkan 2012”' },
    { text: 'CC BY-SA 3.0', href: photo.lu }, { text: 'Wikimedia Commons', href: photo.page }]);
  const pd = photoCredit({ ...photo, by: 'unknown', lic: 'Public domain', lu: '', title: undefined }, SV);
  assert.deepEqual(pd.map(p => p.text), ['Foto: okänd fotograf', 'fri från upphovsrätt', 'Wikimedia Commons']);
  // a simple photograph from before 1969 (Commons' "PD Sweden"): free here, not necessarily elsewhere
  assert.equal(photoCredit({ ...photo, lic: 'Public domain (Sweden)', title: undefined }, EN)[1].text, 'public domain in Sweden');
});

test('the excerpt shows in the page language only, and the links follow the privacy rule', () => {
  const wiki = { sv: { t: 'Slottet byggdes 1697–1754.', r: 5 } };
  assert.deepEqual(extractFor(wiki, 'sv'), { lang: 'sv', text: 'Slottet byggdes 1697–1754.', rev: 5 });
  assert.equal(extractFor(wiki, 'en'), null);
  assert.equal(extractFor(undefined, 'en'), null);
  const card = { raa: 'r-1', qid: 'Q750444', wp: ['sv'] };
  assert.deepEqual(cardLinks(card, b({}), EN, LINKS), [
    { text: 'Heritage register (RAÄ)', href: 'https://pub.raa.se/visa/objekt/bebyggelse/r-1' },
    { text: 'Wikipedia (in Swedish)', href: 'https://www.wikidata.org/wiki/Special:GoToLinkedPage/svwiki/Q750444' },
    { text: 'Wikidata', href: 'https://www.wikidata.org/wiki/Q750444' }]);
  assert.equal(cardLinks({ ...card, wp: ['sv', 'en'] }, b({}), EN, LINKS)[1].text, 'Wikipedia');
  assert.equal(cardLinks({ ...card, wp: ['en'] }, b({}), SV, LINKS)[1].text, 'Wikipedia (på engelska)');
  // A private house never links RAÄ, even if its card carried the id (s03 leaves it out; a second guard)
  assert.deepEqual(cardLinks({ raa: 'r-1' }, b({ private: 1 }), EN, LINKS), []);
  assert.equal(fillUrl(LINKS.wikipedia_rev, { lang: 'sv', rev: 5 }), 'https://sv.wikipedia.org/w/index.php?oldid=5');
});

test('the place line: the first address, how many more, and the stadsdel, in English and Swedish', () => {
  assert.equal(placeLine({ addr: 'Hornsgatan 30', addrn: 3, dist: 'Södermalm' }, EN), 'Hornsgatan 30 (and 2 more) · Södermalm');
  assert.equal(placeLine({ addr: 'Hornsgatan 30', addrn: 3, dist: 'Södermalm' }, SV), 'Hornsgatan 30 (och 2 till) · Södermalm');
  assert.equal(placeLine({ addr: 'Slottsbacken 1', dist: 'Gamla stan' }, EN), 'Slottsbacken 1 · Gamla stan');
  assert.equal(placeLine({ dist: 'Grimsta' }, SV), 'Grimsta');           // no OSM address: the stadsdel alone
  assert.equal(placeLine({}, EN), '');
  assert.equal(placeLine(undefined, EN), '');
});

test('"Why?" points a private house at the privacy rule and an undated building at where the years come from', () => {
  assert.equal(whyAnchor(b({ private: 1, yflag: YFLAG.EXACT, year: 1960 })), 'privacy');
  assert.equal(whyAnchor(b({ private: 1, yflag: YFLAG.PERIOD, year: 1930 })), 'privacy');
  assert.equal(whyAnchor(b({})), 'years');                                 // b() is a building with no year
  assert.equal(whyAnchor(b({ yflag: YFLAG.EXACT, year: 1924, ysrc: YSRC.RAA })), null);
});

test('the tower row: a laser-measured tower, to its top', () => {
  assert.equal(towerLine({ tower: 103 }, EN), '103 m to the top');
  assert.equal(towerLine({ tower: 103 }, SV), '103 m till toppen');
  assert.equal(towerLine({}, EN), '');
});
