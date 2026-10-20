// web/about.js: About written from stockholm.json in both languages, every number from the build.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { aboutHtml, aboutTokens, aboutTarget, pct, SECTIONS } from '../about.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');

// A build in stockholm.json's shape (the m3b numbers, the about block s03_tiles writes).
const CONFIG = {
  version: 'v20261016-m7',
  stats: { buildings: 77743, floorsOsm: 19136,
    byFlag: { exact: 4390, range: 18006, long: 1025, area: 5877, estimate: 4510, period: 0, unknown: 43935 },
    bySrc: { none: 43935, curated: 12, raa: 22049, raa_area: 5877, wikidata: 133, estimate: 4510, raa_old: 809, osm: 418 } },
  accuracy: { near_m: 100, min_cell: 30, min_right: 0.7, max_band: 15,
    cells: [{ group: 'house', era: '1946–1975', inner: false, n: 4000, right_period: 0.8, within_one: 0.95, band: 5, status: 'estimate' },
      { group: 'house', era: '1920–1945', inner: false, n: 3363, right_period: 0.82, within_one: 0.97, band: 5, status: 'estimate' },
      { group: 'apartments', era: 'before 1866', inner: true, n: 89, right_period: 0.303, within_one: 0.708, band: 160, status: 'unknown' },
      { group: 'cottage', era: '1994 on', inner: false, n: 5, status: 'not measurable' }],
    by_true_period: [{ period: 'p8', n: 4000, n_estimate: 3363, right_estimate: 2758 },
      { period: 'p9', n: 5000, n_estimate: 4000, right_estimate: 3240 }],
    external: { n_all: 551, n_estimate: 10, right_estimate: 6, from_1990: { n_all: 219, n_estimate: 0 } },
    area: { n: 39, right_period: 0.769, status: 'measured' } },
  about: { privateCategory: 47336, privateDated: 16864, ratings: [1156, 8216, 12217], protected: 431,
    withArchitect: 19862, addressed: 51746, gamla: { n: 430, dated: 76 }, fewestPrivateYears: 4, lateYear: 2008,
    nearM: 100, rareArchitect: 3, snapshot: '2023-01', maker: '', contact: '', privateAddresses: false },
  terrain: { source: 'contours', relief: 1, reliefMax: 2.5 },
  accuracyLabels: { en: { groups: { house: 'Houses (villa, row, chain)', apartments: 'Apartment blocks', cottage: 'Allotment cottages' }, eras: {} },
    sv: { groups: { house: 'Hus (villor, rad- och kedjehus)', apartments: 'Flerbostadshus', cottage: 'Kolonistugor' },
      eras: { 'before 1866': 'före 1866', '1994 on': '1994 och senare' } } },
  attribution: [{ id: 'osm', text: '© OpenStreetMap contributors, OpenStreetMap data under ODbL (modified)',
    url: 'https://www.openstreetmap.org/copyright', licence: 'ODbL-1.0', licence_url: 'https://opendatacommons.org/licenses/odbl/1-0/',
    credit: { en: 'OpenStreetMap: © OpenStreetMap contributors, ODbL, processed',
      sv: 'OpenStreetMap: © OpenStreetMap-bidragsgivare, ODbL, bearbetad' } }],
};
const text = html => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

test('every placeholder in About\'s strings has a value from the build', () => {
  const tokens = aboutTokens(CONFIG, EN);
  for (const [id, s] of Object.entries(TABLES.en)) {
    if (!id.startsWith('about.') || id === 'about.thanks.code') continue;
    for (const [, name] of s.matchAll(/\{(\w+)\}/g)) assert.ok(name in tokens, `${id}: {${name}}`);
  }
});

test('About types no number of its own: only years, the licences\' versions, "3D" and the GDPR article', () => {
  const allowed = /\b1[0-9]{3}s\b|\b1[0-9]{3}-talet\b|\b(1[0-9]|20)[0-9]{2}\b|\b[1-4]\.0\b|\b3D\b|6\(1\)\(f\)|6\.1 f/g;
  for (const lang of ['en', 'sv']) {
    for (const [id, s] of Object.entries(TABLES[lang])) {
      if (id.startsWith('about.')) assert.doesNotMatch(s.replace(allowed, ''), /\d/, `${lang} ${id}`);
    }
  }
});

test('About reads the build\'s numbers in English and Swedish', () => {
  const en = text(aboutHtml(CONFIG, EN));
  assert.match(en, /Every building standing in Stockholm municipality today \(77,743 of them\)/);
  assert.match(en, /33,808 buildings \(43\.5%\) have a year\. 23,421 come from a record/);
  assert.match(en, /5,877 take the year RAÄ gives their whole area, and 4,510 houses are estimated/);
  // the accuracy page's own counts: by_true_period's exact numbers, not the cells' rounded shares
  assert.match(en, /In the test, 81% of the test houses in the cells the map uses were estimated in the right period \(5,998 of 7,363\), and 96% within one period/);
  assert.match(en, /A snapshot from January 2023\./);
  assert.match(en, /Only 76 of its 430 buildings have a year from a record/);
  assert.match(en, /It gave none of the 219 built from 1990 on a decade/);
  assert.match(en, /never to fewer than 4 years/);
  assert.match(en, /when it appears on 3 or fewer buildings/);
  // The terrain, as built (true height by default, the Hills slider to 2.5×; the City's contour lines here),
  // and the address rule if city.PRIVATE_ADDRESSES is False
  assert.match(en, /The ground is drawn true to scale\. The Hills slider under Look raises the hills up to 2\.5 times as high, or lays the city flat\. The heights come from the City's contour lines\./);
  assert.match(text(aboutHtml({ ...CONFIG, terrain: { source: 'contours', relief: 2, reliefMax: 2.5 } }, EN)),
    /The ground is drawn 2 times as high as it is\. The Hills slider under Look sets it from flat up to 2\.5 times\./);
  assert.match(en, /A private house's street address is not shown on its card either/);
  assert.doesNotMatch(text(aboutHtml({ ...CONFIG, about: { ...CONFIG.about, privateAddresses: true } }, EN)),
    /street address is not shown/);
  assert.match(text(aboutHtml({ ...CONFIG, terrain: { source: 'dtm', relief: 1, reliefMax: 2.5 } }, EN)), /Lantmäteriet's terrain model/);
  assert.doesNotMatch(en, /within a month/);                              // no deadline the project has not set
  assert.match(en, /Who owns or lives in a building: sentences in the Wikipedia texts that say so are left out\./);
  const sv = text(aboutHtml(CONFIG, SV));
  assert.match(sv, /\(77\s743 stycken\)/);                                 // Swedish groups with a narrow space
  assert.match(sv, /33\s808 byggnader \(43,5\s%\) har ett årtal/);
  assert.match(sv, /En ögonblicksbild från januari 2023\./);
  assert.match(sv, /före 1866/);                                          // the table's era in Swedish
  assert.match(sv, /Marken visas i verklig skala\. Reglaget Höjder under Utseende gör höjderna upp till 2,5 gånger så höga, eller lägger staden platt\./);
  assert.doesNotMatch(sv, /upp till 2\.5/);                                // Swedish writes the decimal comma, never "2.5"
  assert.match(text(aboutHtml({ ...CONFIG, terrain: { source: 'contours', relief: 1.5, reliefMax: 2.5 } }, SV)),
    /Marken är ritad med 1,5 gånger verklig höjd\. Reglaget Höjder under Utseende ställer den från platt upp till 2,5 gånger\./);
  assert.match(sv, /Spann/);                                               // the band of years, not a ribbon
  for (const html of [aboutHtml(CONFIG, EN), aboutHtml(CONFIG, SV)]) {
    assert.doesNotMatch(html, /\{\w+\}/);                                  // no placeholder left unfilled
    for (const s of SECTIONS) assert.match(html, new RegExp(`id="about-${s}"`));
  }
});

test('the source table\'s shares are the accuracy page\'s: the kinds rounded together, then split among their sources', () => {
  // v20261017-m8's counts: each row rounded alone gives 28.3% and 8.1%; docs/accuracy.md says 28.4% and 8.0%
  const bySrc = { none: 43453, curated: 72, raa: 22039, raa_area: 6263, wikidata: 131, estimate: 4558, raa_old: 809, osm: 418 };
  const html = aboutHtml({ ...CONFIG, stats: { ...CONFIG.stats, bySrc } }, EN);
  const shares = [...html.matchAll(/<tr><td>[^<]+<\/td><td>[\d,]+<\/td>\s*<td>([\d.]+%)<\/td>/g)].map(m => m[1]);
  assert.deepEqual(shares, ['0.1%', '28.4%', '1.0%', '8.0%', '0.2%', '0.5%', '0.0%', '5.9%', '55.9%']);   // reader: none yet
});

test('About: the readers\' reports row in the years table, and in Sources with the count of applied contributions', () => {
  const bySrc = { ...CONFIG.stats.bySrc, reader: 3 };
  const html = aboutHtml({ ...CONFIG, stats: { ...CONFIG.stats, bySrc }, about: { ...CONFIG.about, readers: 4 } }, EN);
  assert.match(html, /<tr><td>A reader's report, checked by the map's maker<\/td><td>3<\/td>/);
  assert.match(text(html), /Readers' reports: 4 checked and accepted/);
  assert.match(text(aboutHtml({ ...CONFIG, about: { ...CONFIG.about, readers: 4 } }, SV)), /Läsarnas rapporter: 4 granskade/);
});

test('the source table adds up to every building, and the accuracy table names each cell in the page\'s language', () => {
  const html = aboutHtml(CONFIG, EN);
  const rows = [...html.matchAll(/<tr><td>[^<]+<\/td><td>([\d,]+)<\/td>/g)].map(m => +m[1].replace(/,/g, ''));
  assert.equal(rows.reduce((a, b) => a + b, 0), 77743);
  assert.match(html, /<details><summary>The other cells/);
  // a house cell the map does not estimate is in the other table, not left out of both (the review)
  const late = { group: 'house', era: '1976–1993', inner: false, n: 175, right_period: 0.58, within_one: 0.9, band: 20, status: 'unknown' };
  const withLate = aboutHtml({ ...CONFIG, accuracy: { ...CONFIG.accuracy, cells: [...CONFIG.accuracy.cells, late] } }, EN);
  assert.match(text(withLate.split('<details>')[1]), /Houses \(villa, row, chain\) 1976–1993 Outer city 175 58%/);
  assert.doesNotMatch(text(withLate.split('<details>')[0]), /1976–1993/);
  assert.match(text(html), /Apartment blocks before 1866 Inner city 89 30% 71% ±160 Year unknown/);
  assert.match(text(aboutHtml(CONFIG, SV)), /Kolonistugor 1994 och senare Ytterstaden 5 – – – För få för att mäta/);
});

test('without a maker or a contact About says they come before going public; with them it names both', () => {
  const none = text(aboutHtml(CONFIG, EN));
  assert.match(none, /the address to write to is published under Contact before the map goes public/);
  assert.match(none, /The maker and an address for corrections and takedowns are named here before the map goes public\./);
  const named = aboutHtml({ ...CONFIG, about: { ...CONFIG.about, maker: 'Ann <Maker>', contact: 'hej@example.org' } }, EN);
  assert.match(named, /Made by Ann &lt;Maker&gt;\./);                      // escaped
  assert.match(named, /<a href="mailto:hej@example\.org"[^>]*>hej@example\.org<\/a>/);
  assert.doesNotMatch(text(named), /before the map goes public/);
});

test('Contact links to the public code in the page\'s language', () => {
  assert.match(aboutHtml(CONFIG, EN), /The code and data pipeline are open source: <a href="https:\/\/github\.com\/amirelion\/husforhus"[^>]*>github\.com\/amirelion\/husforhus<\/a>/);
  assert.match(aboutHtml(CONFIG, SV), /Koden och datakedjan är öppen källkod: <a href="https:\/\/github\.com\/amirelion\/husforhus"[^>]*>github\.com\/amirelion\/husforhus<\/a>/);
});

test('the sources list carries each licence link, and the ODbL notice covers the database', () => {
  const html = aboutHtml(CONFIG, EN);
  assert.match(html, /<li><a href="https:\/\/www\.openstreetmap\.org\/copyright"[^>]*>OpenStreetMap: © OpenStreetMap contributors, ODbL, processed<\/a> \(<a href="https:\/\/opendatacommons\.org\/licenses\/odbl\/1-0\/"/);
  assert.match(text(html), /published under the Open Database License \(ODbL 1\.0\) as a whole/);
});

test('the sources list credits each source in the standard credit form, in the page\'s language', () => {
  const list = html => html.match(/<ul id="about-data">([\s\S]*?)<\/ul>/)[1];
  assert.match(list(aboutHtml(CONFIG, EN)), />OpenStreetMap: © OpenStreetMap contributors, ODbL, processed</);
  assert.match(list(aboutHtml(CONFIG, SV)), />OpenStreetMap: © OpenStreetMap-bidragsgivare, ODbL, bearbetad</);
  assert.doesNotMatch(list(aboutHtml(CONFIG, SV)), /data under ODbL \(modified\)/);
  // a build from before the standard credit lines keeps its one attribution text
  const older = { ...CONFIG, attribution: CONFIG.attribution.map(({ credit, ...a }) => a) };
  assert.match(list(aboutHtml(older, SV)), />© OpenStreetMap contributors, OpenStreetMap data under ODbL \(modified\)</);
});

test('#about/<section> names a section; anything else is not About', () => {
  assert.equal(aboutTarget('#about/privacy'), 'privacy');
  assert.equal(aboutTarget('#about'), '');
  assert.equal(aboutTarget('#about/nope'), '');
  assert.equal(aboutTarget('#map'), null);
  assert.equal(aboutTarget(''), null);
  assert.equal(pct(0.301, 'en'), '30.1%');
  assert.match(pct(0.301, 'sv'), /^30,1\s%$/);
});

test('a maker without a contact, or a contact without a maker, says only what is still missing (the review)', () => {
  const maker = text(aboutHtml({ ...CONFIG, about: { ...CONFIG.about, maker: 'Ann Maker' } }, EN));
  assert.match(maker, /Made by Ann Maker\. An address for corrections and takedowns is named here before the map goes public\./);
  assert.doesNotMatch(maker, /The maker and an address/);
  const contact = text(aboutHtml({ ...CONFIG, about: { ...CONFIG.about, contact: 'hej@example.org' } }, EN));
  assert.match(contact, /The maker is named here before the map goes public\./);
  assert.doesNotMatch(contact, /The maker and an address/);
});

test('the independent check is "too small" only while the accuracy page says so (the review)', () => {
  assert.match(text(aboutHtml(CONFIG, EN)), /It is too small to confirm the test's figure\./);
  const measured = { ...CONFIG.accuracy.external, status: 'measured', n_estimate: 100, right_estimate: 80 };
  const html = text(aboutHtml({ ...CONFIG, accuracy: { ...CONFIG.accuracy, external: measured } }, EN));
  assert.match(html, /the rule gave 100 of them a decade, 80 in the right period\./);
  assert.doesNotMatch(html, /too small/);
});

test('a build without the about block leaves out the sentences that need it, never "0 of the 0" (the review)', () => {
  for (const T of [EN, SV]) {
    const html = text(aboutHtml({ ...CONFIG, about: undefined }, T));
    assert.doesNotMatch(html, /\b0 (of|av) (the|de) 0\b|before ,|före ,|from \.|från \.|fewer than {2}|färre än {2}/);
    assert.doesNotMatch(html, /\{\w+\}/);
  }
  assert.doesNotMatch(text(aboutHtml({ ...CONFIG, about: undefined }, EN)), /A snapshot from|Only 76|never to fewer/);
  assert.doesNotMatch(aboutHtml({ ...CONFIG, about: undefined, accuracyLabels: undefined }, EN), /<details>|apartments/);
});

test('the sources list names Samfundet S:t Erik\'s plaques with their credit and licence, in both languages', () => {
  // the entries s03_tiles.attribution writes from sources.yml while features.plaques is on
  const plaques = { ...CONFIG, attribution: [...CONFIG.attribution,
    { id: 'samfundet_plaques', url: 'https://samfundetsterik.se/foreningen/kulturhusskyltar/', licence: 'CC-BY-4.0',
      licence_url: 'https://creativecommons.org/licenses/by/4.0/',
      credit: { en: 'Kulturhusskyltar: Samfundet S:t Erik, CC BY 4.0, processed', sv: 'Kulturhusskyltar: Samfundet S:t Erik, CC BY 4.0, bearbetad' } },
    { id: 'openplaques', url: 'https://openplaques.org/places/se/areas/stockholm', licence: 'LicenseRef-PublicDomain',
      licence_url: 'https://openplaques.org/about', credit: { en: 'Open Plaques: Open Plaques, Public Domain, processed', sv: 'Open Plaques: Open Plaques, Public Domain, bearbetad' } }] };
  const list = html => html.match(/<ul id="about-data">([\s\S]*?)<\/ul>/)[1];
  for (const [T, done] of [[EN, 'processed'], [SV, 'bearbetad']]) {
    const html = list(aboutHtml(plaques, T));
    assert.match(html, new RegExp(`<a href="https://samfundetsterik\\.se/[^"]*"[^>]*>Kulturhusskyltar: Samfundet S:t Erik, CC BY 4\\.0, ${done}</a> \\(<a href="https://creativecommons\\.org/licenses/by/4\\.0/"`));
    assert.match(html, /<a href="https:\/\/openplaques\.org\/[^"]*"[^>]*>Open Plaques: /);
  }
});

// app.js sets features.ferries from whether the boats' routes loaded, so the line goes with a missing or empty file.
test('with boats on the map, the limits say they sail real routes, faster and larger, not live, and which are left out', () => {
  const boats = { ...CONFIG, features: { ferries: true } };
  assert.match(text(aboutHtml(boats, EN)), /The boats are an illustration: the city's ferries and the big Baltic ships sail their real routes from OpenStreetMap, several times as fast as in life and drawn larger when the map is zoomed out, but they do not show where any boat is right now\. Archipelago and sightseeing boats are left out\./);
  assert.match(text(aboutHtml(boats, SV)), /Båtarna är en illustration: stadens färjor och de stora Östersjöfartygen följer sina verkliga rutter från OpenStreetMap, flera gånger så fort som i verkligheten och större när kartan är utzoomad, men de visar inte var någon båt är just nu\. Skärgårdsbåtar och sightseeingbåtar är inte med\./);
  assert.doesNotMatch(text(aboutHtml(CONFIG, EN)), /The boats are an illustration/);
  assert.doesNotMatch(text(aboutHtml({ ...CONFIG, features: { ferries: false } }, SV)), /Båtarna/);
});
