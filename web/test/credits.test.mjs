// web/credits.js: the corner credit from sources.yml's corner words.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cornerParts, cornerHtml } from '../credits.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const OSM = { en: '© OpenStreetMap contributors', sv: '© OpenStreetMap-bidragsgivare', url: 'https://www.openstreetmap.org/copyright' };
const ATTRIBUTION = [   // as stockholm.json carries sources.yml (ids, texts and corners as in the repository)
  { id: 'city_lod1', corner: { en: '© Stockholms stad', sv: '© Stockholms stad' } },
  { id: 'city_stadsdelar', corner: { en: '© Stockholms stad', sv: '© Stockholms stad' } },
  { id: 'raa_bebyggelse', corner: { en: 'RAÄ', sv: 'RAÄ' } }, { id: 'raa_old', corner: { en: 'RAÄ', sv: 'RAÄ' } },
  { id: 'wikidata' }, { id: 'osm', corner: OSM }, { id: 'wikipedia' }];

test('each source\'s words once, in the page\'s language; OpenStreetMap links its copyright page', () => {
  assert.deepEqual(cornerParts(ATTRIBUTION, 'en'), [
    { text: '© Stockholms stad', href: '#about/sources' }, { text: 'RAÄ', href: '#about/sources' },
    { text: '© OpenStreetMap contributors', href: 'https://www.openstreetmap.org/copyright' }]);
  assert.equal(cornerParts(ATTRIBUTION, 'sv')[2].text, '© OpenStreetMap-bidragsgivare');
  assert.deepEqual(cornerParts([], 'en'), []);
  assert.deepEqual(cornerParts(undefined, 'en'), []);
});

test('the line ends with Sources, which opens About at its credits', () => {
  const en = cornerHtml(ATTRIBUTION, makeT(TABLES, 'en'));
  assert.equal(en, '<a href="#about/sources">© Stockholms stad</a> · <a href="#about/sources">RAÄ</a> · '
    + '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>'
    + ' · <a href="#about/sources">Sources</a>');
  assert.match(cornerHtml(ATTRIBUTION, makeT(TABLES, 'sv')), /OpenStreetMap-bidragsgivare<\/a> · <a href="#about\/sources">Källor<\/a>$/);
});
