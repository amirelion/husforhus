// web/i18n: both languages hold the same ids, no empty string, the same placeholders (Plan 4a; spec §2.1).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { makeT, fill, LEGACY, legacy, pickLang } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const EN = load('en'), SV = load('sv');
const holes = s => [...s.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort();

test('English and Swedish hold the same ids, none empty, with the same placeholders', () => {
  assert.deepEqual(Object.keys(SV).sort(), Object.keys(EN).sort());
  for (const [id, en] of Object.entries(EN)) {
    assert.ok(en.trim() && SV[id].trim(), id);
    assert.deepEqual(holes(SV[id]), holes(en), id);
  }
});

test('T fills placeholders, falls back to English and then to the id, and formats numbers per language', () => {
  const T = makeT({ en: { a: 'A {n}', b: 'only English' }, sv: { a: 'Ä {n}' } }, 'sv');
  assert.equal(T('a', { n: 3 }), 'Ä 3');
  assert.equal(T('b'), 'only English');
  assert.equal(T('nope'), 'nope');
  assert.equal(T.lang, 'sv');
  assert.equal(T.num(77743), '77 743');
  assert.equal(T.num(18.44, 1), '18,4');
  assert.equal(makeT({}, 'en').num(77743), '77,743');
  assert.equal(fill('{a} and {b}', { a: 1 }), '1 and {b}');      // a missing value shows, never "undefined"
});

test('every English text the pure modules hand over has an id whose English is that text (Plan 4b)', () => {
  for (const [text, id] of Object.entries(LEGACY)) {
    assert.equal(EN[id], text, id);
    assert.ok(SV[id] && SV[id] !== text, id);
  }
  const t = legacy(makeT({ en: EN, sv: SV }, 'sv'));
  assert.equal(t('Today'), 'I dag');
  assert.equal(t('until {year}').replace('{year}', 1610), 'fram till 1610');   // count.js fills it itself
  assert.equal(t('Play again'), 'Play again');                                   // a v1.1 quest text stays English
});

test('the page opens in ?lang=, else the saved choice, else a Swedish or English browser, else English', () => {
  assert.equal(pickLang({ param: 'sv', saved: 'en', languages: ['en-GB'] }), 'sv');
  assert.equal(pickLang({ param: 'de', saved: 'en', languages: ['sv-SE'] }), 'en');      // an unknown ?lang= is ignored
  assert.equal(pickLang({ saved: 'sv', languages: ['en-US'] }), 'sv');
  assert.equal(pickLang({ languages: ['sv-SE', 'en'] }), 'sv');
  assert.equal(pickLang({ languages: ['de-DE', 'sv'] }), 'sv');                        // the first Swedish or English
  assert.equal(pickLang({ languages: ['nb-NO', 'en-US', 'sv'] }), 'en');
  assert.equal(pickLang({ languages: ['svx'] }), 'en');
  assert.equal(pickLang({ languages: ['sv-SE'], fromBrowser: false }), 'en');        // decision 1 (Plan 4b), if the answer is no
  assert.equal(pickLang({ param: 'sv', languages: ['sv-SE'], enabled: false }), 'en'); // the switch off: English
  assert.equal(pickLang(), 'en');
});

test('every text index.html marks for translation has its id in both languages, and app.js keeps no string table', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  const ids = [...html.matchAll(/data-i18n(?:-aria)?="([\w.]+)"/g)].map(m => m[1]);
  assert.ok(ids.length >= 9);
  for (const id of ids) assert.ok(EN[id] && SV[id], id);
  assert.doesNotMatch(app, /SV_UI/);
});
