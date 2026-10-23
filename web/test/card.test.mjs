import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { yearLine, sourceLine, floorsLine, heightLine, towerLine, ratingLine, protLine, photoCredit, extractFor, cardLinks, fillUrl,
  decade, band, decadeOnly, isEstimate, rebuildLine, placeLine, whyAnchor, citedParts, citedRebuilds, citedShown, citedAlso,
  citedMore, citedHead, permitLine } from '../card.js';
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
  // the other house on a curated footprint its article dates (Historiska museet's Kanslikasernen range), after any
  // rebuild, whether it is older or newer
  assert.equal(rebuildLine({ also: [[1805, 1818]] }, EN), 'Also part of this building: a house built 1805–1818');
  assert.equal(rebuildLine({ also: [[1805, 1818]] }, SV), 'I byggnaden ingår också ett hus byggt 1805–1818');
  assert.equal(rebuildLine({ rebuilt: [[1935, 'extended']], also: [[1700, 1700], [1785, 1790]] }, EN),
    'Extended 1935 · Also part of this building: houses built 1700 and 1785–1790');
  assert.equal(rebuildLine({ also: [[1700, 1700], [1720, 1725], [1785, 1790]] }, SV),
    'I byggnaden ingår också hus byggda 1700, 1720–1725 och 1785–1790');
  for (const also of [[], 'x', [[1805]]]) assert.equal(rebuildLine({ also }, EN), '');
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

// The legend's note promises that "the card says whether from an area, from neighbours or from a record that gives
// only a century or a period" for every estimated year (the estimate tone: AREA, ESTIMATE and PERIOD, a cited record's
// included).
test('the card says area, neighbours or the record for every estimated year, as the legend promises', () => {
  const area = /area|område/, near = /neighbours|nearby|grannarna|närheten/;
  const record = /^≈ .*· (KulturNav|Swedish Wikipedia|svenska Wikipedia|City Museum|Stadsmuseet)/;
  for (const T of [EN, SV]) {
    for (const [a, z] of [[1600, 1699], [1300, 1399], [1650, 1699], [1000, 1520], [1300, 1499]]) {   // centuries and periods
      const cited = b({ year: Math.floor((a + z) / 2), yearFrom: a, yearTo: z, yflag: YFLAG.PERIOD, ysrc: YSRC.CITED });
      assert.match(sourceLine(cited, T, { yc: { s: 'wikipedia_sv', u: 'https://sv.wikipedia.org/w/index.php?oldid=1' } }),
        record);
      assert.ok(isEstimate(cited));      // drawn in the estimate tone, left out by the hide-estimates switch
    }
  }
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

test("a reader's report: the source line with its reference and note, a private house's names the source only", () => {
  const b = { yflag: YFLAG.EXACT, ysrc: YSRC.READER, year: 1938, yearFrom: 1938, yearTo: 1938 };
  const yrd = { ref: 'HFH-12', note: 'The building permit is dated 1938.', url: 'https://github.com/amirelion/husforhus/issues/9' };
  assert.equal(sourceLine(b, EN, { yrd }), "A reader's report (HFH-12), checked: The building permit is dated 1938.");
  assert.equal(sourceLine(b, SV, { yrd }), 'En läsares rapport (HFH-12), granskad: The building permit is dated 1938.');
  assert.equal(sourceLine({ ...b, private: true, year: 1930 }, EN, {}), "A reader's report · " + EN('card.private.rule'));
});

test("a reader's photo is credited with the sender's name, CC BY 4.0, as a reader's photo", () => {
  const photo = { key: '0123456789abcdef-1600.jpg', w: 1600, h: 1200, by: 'A. Reader', lic: 'CC BY 4.0',
    lu: 'https://creativecommons.org/licenses/by/4.0/', rd: 'HFH-12' };
  assert.deepEqual(photoCredit(photo, EN), [{ text: "Photo: A. Reader, CC BY 4.0, a reader's photo" }]);
  assert.deepEqual(photoCredit(photo, SV), [{ text: 'Foto: A. Reader, CC BY 4.0, en läsares foto' }]);
});

test('a cited year: built, a decade, a new house, a period and a medieval house, with its source, in English and Swedish', () => {
  const c = o => ({ ysrc: YSRC.CITED, yflag: YFLAG.EXACT, ...o });
  const kn = { s: 'kulturnav', u: 'https://kulturnav.org/74ce2767-f09f-4bdf-b86e-ea22dbd632b6' };
  const wp = { s: 'wikipedia_sv', u: 'https://sv.wikipedia.org/w/index.php?oldid=1' };
  const cases = [
    [c({ year: 1858, yearFrom: 1855, yearTo: 1858, yflag: YFLAG.RANGE }), kn,
      'Built 1855–1858 · KulturNav (ArkDes)', 'Byggt 1855–1858 · KulturNav (ArkDes)'],
    [c({ year: 1640, yearFrom: 1640, yearTo: 1649, yflag: YFLAG.RANGE }), wp,
      'Built in the 1640s · Swedish Wikipedia', 'Byggt på 1640-talet · svenska Wikipedia'],
    [c({ year: 1854, yearFrom: 1854, yearTo: 1854 }), { ...wp, k: 'rebuilt' },
      'Built 1854, replacing an older house · Swedish Wikipedia', 'Byggt 1854 och ersatte ett äldre hus · svenska Wikipedia'],
    [c({ year: 1650, yearFrom: 1650, yearTo: 1659, yflag: YFLAG.RANGE }), { s: 'ssm_inventory', u: 'x' },
      'Built in the 1650s · City Museum, building inventory', 'Byggt på 1650-talet · Stadsmuseet, byggnadsinventering'],
    [c({ year: 1655, yearFrom: 1600, yearTo: 1699, yflag: YFLAG.PERIOD }), wp,
      '≈ built in the 1600s · Swedish Wikipedia', '≈ byggt på 1600-talet · svenska Wikipedia'],
    [c({ year: 1630, yearFrom: 1600, yearTo: 1649, yflag: YFLAG.PERIOD }), wp,
      '≈ built in the first half of the 1600s · Swedish Wikipedia', '≈ byggt under 1600-talets första hälft · svenska Wikipedia'],
    [c({ year: 1674, yearFrom: 1650, yearTo: 1699, yflag: YFLAG.PERIOD }), { s: 'ssm_br', u: 'x' },
      '≈ built in the second half of the 1600s · City Museum, building archaeology',
      '≈ byggt under 1600-talets andra hälft · Stadsmuseet, byggnadsarkeologi'],
    [c({ year: 1550, yearFrom: 1500, yearTo: 1699, yflag: YFLAG.PERIOD }), wp,
      '≈ built in the 1500s–1600s · Swedish Wikipedia', '≈ byggt på 1500–1600-talet · svenska Wikipedia'],
    // a century's beginning, middle and end, in the record's words, never as end years no record gives (the review
    // of 2026-10-20): 1600–1624, 1640–1660, 1675–1699
    [c({ year: 1617, yearFrom: 1611, yearTo: 1624, yflag: YFLAG.PERIOD }), wp,
      '≈ built 1611–1624 · Swedish Wikipedia', '≈ byggt 1611–1624 · svenska Wikipedia'],
    [c({ year: 1612, yearFrom: 1600, yearTo: 1624, yflag: YFLAG.PERIOD }), wp,
      '≈ built in the early 1600s · Swedish Wikipedia', '≈ byggt i början av 1600-talet · svenska Wikipedia'],
    [c({ year: 1650, yearFrom: 1640, yearTo: 1660, yflag: YFLAG.PERIOD }), { s: 'ssm_br', u: 'x' },
      '≈ built around the mid-1600s · City Museum, building archaeology',
      '≈ byggt kring mitten av 1600-talet · Stadsmuseet, byggnadsarkeologi'],
    [c({ year: 1687, yearFrom: 1675, yearTo: 1699, yflag: YFLAG.PERIOD }), { s: 'ssm_br', u: 'x' },
      '≈ built in the late 1600s · City Museum, building archaeology',
      '≈ byggt i slutet av 1600-talet · Stadsmuseet, byggnadsarkeologi'],
    // "late 1630s or early 1640s", as the Sparre palace's article says it (the map's year is the span's end)
    [c({ year: 1644, yearFrom: 1635, yearTo: 1644, yflag: YFLAG.RANGE }), wp,
      'Built in the late 1630s or early 1640s · Swedish Wikipedia',
      'Byggt i slutet av 1630-talet eller i början av 1640-talet · svenska Wikipedia'],
    // a record's "about" (cited.py circa): "about 1640", never a bare 1640 the record does not claim
    [c({ year: 1640, yearFrom: 1640, yearTo: 1640 }), { ...wp, k: 'rebuilt', c: true },
      'Built about 1640, replacing an older house · Swedish Wikipedia',
      'Byggt omkring 1640 och ersatte ett äldre hus · svenska Wikipedia'],
    [c({ year: 1650, yearFrom: 1650, yearTo: 1650 }), { s: 'ssm_br', u: 'x', c: true },
      'Built about 1650 · City Museum, building archaeology', 'Byggt omkring 1650 · Stadsmuseet, byggnadsarkeologi'],
    // medieval: the records date the old fabric a later rebuild kept, so the card says where the house began
    [c({ year: 1399, yearFrom: 1300, yearTo: 1499, yflag: YFLAG.PERIOD }), wp,
      '≈ medieval origin · Swedish Wikipedia', '≈ medeltida ursprung · svenska Wikipedia'],
    [c({ year: 1349, yearFrom: 1300, yearTo: 1399, yflag: YFLAG.PERIOD }), wp,
      '≈ medieval origin · Swedish Wikipedia', '≈ medeltida ursprung · svenska Wikipedia'],
    [c({ year: 1260, yearFrom: 1000, yearTo: 1520, yflag: YFLAG.PERIOD }), { s: 'ssm_br', u: 'x' },
      '≈ medieval origin · City Museum, building archaeology', '≈ medeltida ursprung · Stadsmuseet, byggnadsarkeologi'],
    [c({ year: 1299, yearFrom: 1000, yearTo: 1599, yflag: YFLAG.PERIOD }), wp,
      '≈ medieval origin · Swedish Wikipedia', '≈ medeltida ursprung · svenska Wikipedia'],
    // a Hjorthagen block dated by its building stage's move-in years (the City's stage page, D63)
    [c({ year: 2017, yearFrom: 2014, yearTo: 2017, yflag: YFLAG.RANGE }),
      { s: 'stockholm_stage', u: 'https://www.norradjurgardsstaden2030.se/resultat/etapp/vastra' },
      'Built 2014–2017 · move-in years of its Hjorthagen stage (City of Stockholm)',
      'Byggt 2014–2017 · inflyttningsåren för husets etapp i Hjorthagen (Stockholms stad)'],
    // a card without its shard entry (the hover card before the shard loads) still says it is a record
    [c({ year: 1643, yearFrom: 1643, yearTo: 1643 }), undefined, 'Built 1643 · a published record', 'Byggt 1643 · en publicerad källa'],
  ];
  for (const [bb, yc, en, sv] of cases) {
    assert.equal(sourceLine(b(bb), EN, { yc }), en);
    assert.equal(sourceLine(b(bb), SV, { yc }), sv);
  }
  // a private house: the source, then the decade rule (or "period only"); never the record's span
  assert.equal(sourceLine(b(c({ year: 1643, yearFrom: 1643, yearTo: 1643, private: 1 })), EN, {}),
    'A published record · ' + EN('card.private.rule'));
  assert.equal(sourceLine(b(c({ year: 1655, yearFrom: 1600, yearTo: 1699, yflag: YFLAG.PERIOD, private: 1 })), SV, {}),
    'En publicerad källa · småhus: bara perioden');
  // the header names the period, as for any period-only year; an "about" year stays the record's year there (§14)
  assert.equal(yearLine(b(c({ year: 1655, yearFrom: 1600, yearTo: 1699, yflag: YFLAG.PERIOD })), 'Stormaktstiden', EN), 'Stormaktstiden');
  assert.equal(yearLine(b(c({ year: 1640, yearFrom: 1640, yearTo: 1640 })), '', EN, { s: 'wikipedia_sv', u: 'x', c: true }), '1640');
});

// AB Stadsholmen's fact sheets (pipeline/cited.py source stadsholmen, D64): named as written with the City Museum and
// linked to the company's property list, never to a sheet (its PDF is named by the property designation)
test('a year from AB Stadsholmen\'s fact sheet names the sheet and links the property list, in English and Swedish', () => {
  const list = 'https://www.stadsholmen.se/fastigheter/', wp = 'https://sv.wikipedia.org/w/index.php?oldid=59514298';
  const sh = { s: 'stadsholmen', u: list };
  const c = over => b({ ysrc: YSRC.CITED, yflag: YFLAG.EXACT, ...over });
  const text = parts => parts.map(p => p.text).join('');
  assert.equal(sourceLine(c({ year: 1520, yearFrom: 1000, yearTo: 1520, yflag: YFLAG.PERIOD }), EN, { yc: sh }),
    '≈ medieval origin · AB Stadsholmen\'s fact sheet (with the City Museum)');
  assert.equal(sourceLine(c({ year: 1520, yearFrom: 1000, yearTo: 1520, yflag: YFLAG.PERIOD }), SV, { yc: sh }),
    '≈ medeltida ursprung · AB Stadsholmens faktablad (med Stadsmuseet)');
  assert.equal(sourceLine(c({ year: 1784, yearFrom: 1784, yearTo: 1784 }), EN, { yc: sh }),
    'Built 1784 · AB Stadsholmen\'s fact sheet (with the City Museum)');
  assert.deepEqual(citedParts(c({ year: 1746, yearFrom: 1746, yearTo: 1746 }), SV, { ...sh, k: 'rebuilt' }), [
    { text: 'Byggt 1746 och ersatte ett äldre hus · AB Stadsholmens faktablad (med Stadsmuseet)', href: list }]);
  // its rebuilds beside another source's year: each linked to the list, the sheet's name as the link's title
  const r = [{ a: 1850, z: 1850, ...sh }, { a: 1970, z: 1979, ...sh }];
  assert.equal(text(citedRebuilds({ s: 'ssm_br', u: 'x', r }, EN)), 'Rebuilt or extended 1850 and in the 1970s');
  assert.deepEqual(citedRebuilds({ s: 'ssm_br', u: 'x', r }, SV)[1],
    { text: '1850', href: list, title: 'AB Stadsholmens faktablad (med Stadsmuseet)' });
  // Köpmanbrinken 4: the sheet's older house with medieval walls, or the block article's new house of the 1680s (no
  // colour: both shown)
  const e = [{ a: 1000, z: 1520, ...sh }, { a: 1680, z: 1689, s: 'wikipedia_sv', u: wp }];
  assert.equal(sourceLine(b({}), EN, { yc: { e } }), '≈ medieval origin, or built in the 1680s (sources differ)');
  assert.equal(sourceLine(b({}), SV, { yc: { e } }), '≈ medeltida ursprung eller byggt på 1680-talet (källorna går isär)');
  assert.deepEqual(citedParts(b({}), EN, { e })[1],
    { text: 'medieval origin', href: list, title: 'AB Stadsholmen\'s fact sheet (with the City Museum)' });
});

// pipeline/cited.py's either pair (two sources that differ, decided 2026-10-20): both readings, each linked to its record
test('two sources that differ: both readings on the card, each linked to its source, in English and Swedish', () => {
  const wp = 'https://sv.wikipedia.org/w/index.php?oldid=1', kn = 'https://kulturnav.org/74ce2767-f09f-4bdf-b86e-ea22dbd632b6';
  const inv = 'https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/Byggnadsinventeringar/10043930.pdf.info';
  const o = (a, z, s = 'wikipedia_sv', u = wp, c = false) => ({ a, z, s, u, ...(c ? { c } : {}) });
  // coloured: one period holds 3/4 of the readings (PERIOD, the estimate tone); or not: no colour, the line all the same
  const coloured = (a, z) => b({ year: Math.floor((a + z) / 2), yearFrom: a, yearTo: z, yflag: YFLAG.PERIOD, ysrc: YSRC.CITED });
  const unknown = b({});
  const cases = [
    [coloured(1785, 1798), [o(1785, 1785), o(1798, 1798, 'ssm_inventory', inv)],
      'Built in 1785 or 1798 (sources differ)', 'Byggt 1785 eller 1798 (källorna går isär)'],
    [coloured(1630, 1649), [o(1630, 1639), o(1640, 1649)],
      'Built in the 1630s or the 1640s (sources differ)', 'Byggt på 1630-talet eller 1640-talet (källorna går isär)'],
    [coloured(1785, 1799), [o(1785, 1785), o(1790, 1799)],
      'Built in 1785 or the 1790s (sources differ)', 'Byggt 1785 eller på 1790-talet (källorna går isär)'],
    // the other reading keeps its verb: "…, or built 1650"
    [coloured(1000, 1699), [o(1000, 1520, 'ssm_br', 'x'), o(1600, 1699, 'kulturnav', kn)],
      '≈ medieval origin, or built in the 1600s (sources differ)',
      '≈ medeltida ursprung eller byggt på 1600-talet (källorna går isär)'],
    [coloured(1300, 1650), [o(1300, 1399), o(1650, 1650)],
      '≈ medieval origin, or built 1650 (sources differ)', '≈ medeltida ursprung eller byggt 1650 (källorna går isär)'],
    // Gåsgränd 4: medieval, or the 1500s to the mid-1600s
    [coloured(1000, 1649), [o(1000, 1520, 'ssm_br', 'x'), o(1500, 1649, 'ssm_br', 'y')],
      '≈ medieval origin, or built between 1500 and the mid-1600s (sources differ)',
      '≈ medeltida ursprung eller byggt mellan 1500 och mitten av 1600-talet (källorna går isär)'],
    [coloured(1600, 1699), [o(1600, 1624), o(1640, 1640, 'wikipedia_sv', wp, true)],
      'Built in the early 1600s or about 1640 (sources differ)',
      'Byggt i början av 1600-talet eller omkring 1640 (källorna går isär)'],
    [coloured(1600, 1699), [o(1600, 1699), o(1643, 1643)],
      '≈ built in the 1600s or 1643 (sources differ)', '≈ byggt på 1600-talet eller 1643 (källorna går isär)'],
    [coloured(1600, 1699), [o(1600, 1649), o(1650, 1699)],
      '≈ built in the first half of the 1600s or the second half of the 1600s (sources differ)',
      '≈ byggt under 1600-talets första hälft eller 1600-talets andra hälft (källorna går isär)'],
    [unknown, [o(1580, 1580), o(1650, 1659)],
      'Built in 1580 or the 1650s (sources differ)', 'Byggt 1580 eller på 1650-talet (källorna går isär)'],
  ];
  for (const [bb, e, en, sv] of cases) {
    assert.ok(citedShown(bb, { e }));
    assert.equal(sourceLine(bb, EN, { yc: { e } }), en);
    assert.equal(sourceLine(bb, SV, { yc: { e } }), sv);
  }
  // each reading is a link to its own record, the source's name its title, the preposition outside the link
  assert.deepEqual(citedParts(cases[0][0], EN, { e: cases[0][1] }), [
    { text: 'Built ' }, { text: 'in ' }, { text: '1785', href: wp, title: 'Swedish Wikipedia' }, { text: ' or ' },
    { text: '1798', href: inv, title: 'City Museum, building inventory' }, { text: ' (sources differ)' }]);
  assert.deepEqual(citedParts(cases[3][0], SV, { e: cases[3][1] }).filter(p => p.href), [
    { text: 'medeltida ursprung', href: 'x', title: 'Stadsmuseet, byggnadsarkeologi' },
    { text: '1600-talet', href: kn, title: 'KulturNav (ArkDes)' }]);
  assert.deepEqual(citedParts(cases[3][0], EN, { e: cases[3][1] }), [
    { text: '≈ ' }, { text: 'medieval origin', href: 'x', title: 'City Museum, building archaeology' },
    { text: ', or built ' }, { text: 'in ' }, { text: 'the 1600s', href: kn, title: 'KulturNav (ArkDes)' },
    { text: ' (sources differ)' }]);
  // the header: the period's name where the readings have one; where none does, that the sources differ (the line
  // gives both), and "Year unknown" only without the card's records
  assert.equal(yearLine(cases[0][0], 'Frihetstid & Gustavian', EN), 'Frihetstid & Gustavian');
  assert.equal(yearLine(unknown, '', EN, { e: cases.at(-1)[1] }), 'Sources differ');
  assert.equal(yearLine(unknown, '', SV, { e: cases.at(-1)[1] }), 'Källorna går isär');
  assert.equal(yearLine(unknown, '', EN), 'Year unknown');
  // an unknown building without the cited line: as before
  assert.ok(!citedShown(unknown, undefined) && !citedShown(unknown, { e: [o(1580, 1580)] }));
  assert.equal(sourceLine(unknown, EN, {}), 'No open record dates this building yet.');
  // a building another source dates never shows a cited line, nor does a private house
  assert.ok(!citedShown(b({ year: 1700, yflag: YFLAG.EXACT, ysrc: YSRC.RAA }), { e: cases[0][1] }));
  assert.ok(!citedShown({ ...cases[0][0], private: 1 }, { e: cases[0][1] }));
});

test('a cited period no map period holds 3/4 of: no colour, but its header and line give the record', () => {
  const wp = 'https://sv.wikipedia.org/w/index.php?oldid=54474172';
  const yc = { s: 'wikipedia_sv', u: wp, a: 1600, z: 1624 };
  const unknown = b({});
  assert.ok(citedShown(unknown, yc));
  assert.equal(sourceLine(unknown, EN, { yc }), '≈ built in the early 1600s · Swedish Wikipedia');
  assert.equal(sourceLine(unknown, SV, { yc }), '≈ byggt i början av 1600-talet · svenska Wikipedia');
  assert.deepEqual(citedParts(unknown, EN, yc), [{ text: '≈ built in the early 1600s · Swedish Wikipedia', href: wp }]);
  assert.equal(sourceLine(unknown, EN, { yc: { ...yc, a: 1580, z: 1650 } }), '≈ built 1580–1650 · Swedish Wikipedia');
  // the header says what the record gives, not "Year unknown" over a dated line (the review of 2026-10-20)
  assert.equal(yearLine(unknown, '', EN, yc), '≈ early 1600s');
  assert.equal(yearLine(unknown, '', SV, yc), '≈ början av 1600-talet');
  assert.equal(yearLine(unknown, '', EN, { ...yc, a: 1580, z: 1649 }), '≈ 1580–1649');
  assert.equal(citedHead({ ...yc, a: 1580, z: 1649 }, SV), '≈ 1580–1649');
  assert.equal(yearLine(unknown, '', EN), 'Year unknown');
  assert.equal(yearLine({ ...unknown, private: 1 }, '', EN, yc), 'Year unknown');      // never a private house's
  // the span is only read where no year ships: a span on an area-dated building is no cited line
  assert.ok(!citedShown(b({ year: 1650, yflag: YFLAG.AREA, ysrc: YSRC.RAA_AREA }), yc));
});

test('the rebuilds a cited record names: the pinned card\'s second line, each year linked to its record', () => {
  const wp = 'https://sv.wikipedia.org/w/index.php?oldid=53738008', ssm = 'x';
  const o = (a, z, s = 'wikipedia_sv', u = wp) => ({ a, z, s, u });
  // "Rebuilt or extended": a rebuild, an extension, a raised storey or a new facade (the review of 2026-10-20)
  const cases = [
    [[o(1780, 1780)], 'Rebuilt or extended 1780', 'Om- eller tillbyggt 1780'],
    [[o(1907, 1907), o(1947, 1947, 'ssm_br', ssm)], 'Rebuilt or extended 1907 and 1947', 'Om- eller tillbyggt 1907 och 1947'],
    [[o(1877, 1888), o(1902, 1902), o(1940, 1949)], 'Rebuilt or extended 1877–1888, 1902 and in the 1940s',
      'Om- eller tillbyggt 1877–1888, 1902 och på 1940-talet'],
    [[o(1910, 1919), o(1940, 1949)], 'Rebuilt or extended in the 1910s and the 1940s',
      'Om- eller tillbyggt på 1910-talet och 1940-talet'],
    [[o(1600, 1699), o(1780, 1780)], 'Rebuilt or extended in the 1600s and 1780', 'Om- eller tillbyggt på 1600-talet och 1780'],
    // two centuries as one span, so "and" never reads as part of an "or" (Didrik Ficks gränd 6)
    [[o(1600, 1799, 'ssm_br', ssm), o(1884, 1884)], 'Rebuilt or extended in the 1600s–1700s and 1884',
      'Om- eller tillbyggt på 1600–1700-talet och 1884'],
    [[o(1640, 1660), o(1780, 1780)], 'Rebuilt or extended around the mid-1600s and 1780',
      'Om- eller tillbyggt kring mitten av 1600-talet och 1780'],
    [[{ ...o(1774, 1774), c: true }], 'Rebuilt or extended about 1774', 'Om- eller tillbyggt omkring 1774'],
  ];
  for (const [r, en, sv] of cases) {
    assert.equal(citedRebuilds({ s: 'wikipedia_sv', u: wp, r }, EN).map(p => p.text).join(''), en);
    assert.equal(citedRebuilds({ s: 'wikipedia_sv', u: wp, r }, SV).map(p => p.text).join(''), sv);
  }
  assert.deepEqual(citedRebuilds({ e: [o(1785, 1785), o(1798, 1798)], r: cases[1][0] }, EN), [
    { text: 'Rebuilt or extended ' }, { text: '1907', href: wp, title: 'Swedish Wikipedia' }, { text: ' and ' },
    { text: '1947', href: ssm, title: 'City Museum, building archaeology' }]);
  assert.deepEqual(citedRebuilds({ s: 'wikipedia_sv', u: wp }, EN), []);
  assert.deepEqual(citedRebuilds(undefined, EN), []);
  // a rebuild never changes the dating line: the year stays the standing house's
  const built = b({ year: 1798, yearFrom: 1798, yearTo: 1798, yflag: YFLAG.EXACT, ysrc: YSRC.CITED });
  assert.equal(sourceLine(built, EN, { yc: { s: 'wikipedia_sv', u: wp, r: cases[0][0] } }), 'Built 1798 · Swedish Wikipedia');
});

test('another house the footprint holds: its own line, never a rebuild of the house the card names', () => {
  const wp = 'https://sv.wikipedia.org/w/index.php?oldid=55158130', kn = 'https://kulturnav.org/d76c01a0-4062-4b29-8dbb-9d6fdbc00fb7';
  const o = (a, z, s = 'wikipedia_sv', u = wp) => ({ a, z, s, u });
  const text = parts => parts.map(p => p.text).join('');
  // Stortorget 20, Schantzska huset (1650), and the 1520s Seyfridtz house beside it on one footprint
  assert.equal(text(citedAlso({ s: 'wikipedia_sv', u: wp, o: [o(1520, 1529)] }, EN)),
    'Also part of this building: a house built in the 1520s');
  assert.equal(text(citedAlso({ s: 'wikipedia_sv', u: wp, o: [o(1520, 1529)] }, SV)),
    'I byggnaden ingår också ett hus byggt på 1520-talet');
  assert.equal(text(citedAlso({ o: [o(1700, 1724), o(1785, 1785)] }, EN)),
    'Also part of this building: houses built in the early 1700s and 1785');
  assert.equal(text(citedAlso({ o: [o(1700, 1724), o(1785, 1785)] }, SV)),
    'I byggnaden ingår också hus byggda i början av 1700-talet och 1785');
  assert.deepEqual(citedAlso({ s: 'wikipedia_sv', u: wp }, EN), []);
  // the Sparre palace: its own raised storey, then Kammarrätten's house; the Stenbock palace's archive, linked
  const sparre = { s: 'wikipedia_sv', u: wp, r: [o(1807, 1808)], o: [o(1804, 1804)] };
  assert.equal(text(citedMore(sparre, EN)), 'Rebuilt or extended 1807–1808 · Also part of this building: a house built 1804');
  assert.equal(text(citedMore(sparre, SV)), 'Om- eller tillbyggt 1807–1808 · I byggnaden ingår också ett hus byggt 1804');
  assert.deepEqual(citedMore({ s: 'wikipedia_sv', u: wp, o: [o(1887, 1890, 'kulturnav', kn)] }, EN), [
    { text: 'Also part of this building: a house built ' }, { text: '1887–1890', href: kn, title: 'KulturNav (ArkDes)' }]);
  assert.deepEqual(citedMore({ s: 'wikipedia_sv', u: wp }, EN), []);
});

// A building-permit year (codes.SRC_BYGGLOV): the closing year of the property's first permit, named with the archive,
// never with "≈" or a span; a private house names its decade and the decade rule (the owner's short wording, 2026-10-21).
test('a permit-dated card says when the first permit closed and names Stadsarkivet, in English and Swedish', () => {
  const pub = b({ year: 1934, yearFrom: 1931, yearTo: 1934, yflag: YFLAG.RANGE, ysrc: YSRC.BYGGLOV });
  assert.equal(yearLine(pub, '', EN), '1934');
  assert.equal(sourceLine(pub, EN), 'Building permit closed 1934 (Stadsarkivet)');
  assert.equal(sourceLine(pub, SV), 'Bygglov avslutat 1934 (Stadsarkivet)');
  const exact = b({ year: 1928, yearFrom: 1928, yearTo: 1928, yflag: YFLAG.EXACT, ysrc: YSRC.BYGGLOV });
  assert.equal(sourceLine(exact, EN), 'Building permit closed 1928 (Stadsarkivet)');
  const house = b({ year: 1930, yearFrom: 1930, yearTo: 1939, yflag: YFLAG.RANGE, ysrc: YSRC.BYGGLOV, private: 1 });
  assert.equal(yearLine(house, '', EN), '1930s');
  assert.equal(yearLine(house, '', SV), '1930-talet');
  assert.equal(sourceLine(house, EN), 'Building permit closed in the 1930s (Stadsarkivet) · private house: decade only');
  assert.equal(sourceLine(house, SV), 'Bygglov avslutat på 1930-talet (Stadsarkivet) · småhus: bara årtiondet');
  // a decade that starts a century prints as its ten years, as everywhere on the card
  const c1900 = b({ year: 1900, yearFrom: 1900, yearTo: 1909, yflag: YFLAG.EXACT, ysrc: YSRC.BYGGLOV, private: 1 });
  assert.equal(sourceLine(c1900, EN), 'Building permit closed 1900–1909 (Stadsarkivet) · private house: decade only');
  assert.equal(permitLine(c1900, SV), 'Bygglov avslutat 1900–1909 (Stadsarkivet)');
  for (const x of [pub, exact, house]) {
    for (const text of [yearLine(x, '', EN), sourceLine(x, EN), yearLine(x, '', SV), sourceLine(x, SV)]) {
      assert.doesNotMatch(text, /≈|193[1-3]|Visa/, text);        // a record, no opening year, no card page
    }
  }
  assert.doesNotMatch(sourceLine(house, EN), /193[1-9]/);          // a private house never shows its year
});
