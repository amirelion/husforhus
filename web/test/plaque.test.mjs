import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { plaquesByGid, plaqueSection } from '../plaque.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const P = { id: 27001, gid: 5, name: 'Bellmanhuset', text: 'Här bodde <Bellman>.', year: 1998, x: 1, z: 2,
  how: 'address', credit: 'Samfundet S:t Erik, CC BY 4.0' };

test('plaquesByGid groups a building\'s plaques', () => {
  const by = plaquesByGid([P, { ...P, id: 2 }, { ...P, id: 3, gid: 9 }]);
  assert.equal(by.get(5).length, 2);
  assert.equal(by.get(9).length, 1);
  assert.equal(plaquesByGid(undefined).size, 0);
});

test('plaqueSection: text, credit and source, escaped', () => {
  assert.equal(plaqueSection(undefined, EN, esc), '');
  assert.equal(plaqueSection([], EN, esc), '');
  const html = plaqueSection([P], EN, esc);
  assert.match(html, /Blue plaque · 1998/);
  assert.match(html, /Här bodde &lt;Bellman&gt;\./);
  assert.match(html, /Samfundet S:t Erik, CC BY 4\.0/);
  assert.match(html, /creativecommons\.org\/licenses\/by\/4\.0/);
  assert.match(html, /stockholmskallan\.stockholm\.se\/post\/27001/);
  assert.match(html, /lang="sv"/);
  assert.match(plaqueSection([P], SV, esc), /Blå skylt/);
  assert.doesNotMatch(plaqueSection([{ ...P, year: 0 }], EN, esc), /·  ?0/);
});
