// web/search.js: what is inside a building (index.occupants, pipeline/s14_search.py): found by its Swedish name, its
// English one or another name, shown as "Nobel Prize Museum, in Börshuset", picked like the building, and ranked
// below an exact match on a building's own name.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { prepare, textRows, search, rowText } from '../search.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');

const P = prepare({
  v: 1, settings: { min_chars: 2, max_rows: 8, max_per_kind: 4, max_edits: 2 }, examples: [], addressed: 1,
  districts: [['Gamla stan', 430, [-400, -300, 300, 400]]], aliases: [], outside: [], streets: [],
  buildings: [['Börshuset', 229, 0, 'Stockholm Stock Exchange Building'], ['Nobelhuset', 300, 0, '']],
  baliases: [],
  occupants: [['Nobelprismuseet', 'Nobel Prize Museum', 229, ['Nobelmuseet', 'Nobel Museum']],
    ['Nobelhuset', 'Nobel House', 300, []], ['Svenska Akademien', 'Swedish Academy', 229, []],
    ['Ingenstans', 'Nowhere', 999, []]],                     // a gid no building row names: never shown
});

test('"nobel" finds the museum inside Börshuset, a row that flies to the building', async () => {
  const { rows } = await search(P, 'nobel', async () => ({}));
  const museum = rows.find(r => r.kind === 'occupant' && r.gid === 229);
  assert.ok(museum);
  assert.equal(museum.d, 0);
  assert.deepEqual(rowText(museum, P, EN), { main: 'Nobel Prize Museum, in Börshuset', sub: 'Inside a building · Gamla stan' });
  assert.deepEqual(rowText(museum, P, SV), { main: 'Nobelprismuseet, i Börshuset', sub: 'I en byggnad · Gamla stan' });
});

test('found by its English name and by an older name, with the same folding as the rest', () => {
  for (const q of ['nobel prize', 'nobelmuseet', 'NOBELPRISMUSÉET', 'akademien', 'swedish acad']) {
    assert.ok(textRows(P, q.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '')).some(r => r.kind === 'occupant'), q);
  }
  assert.ok(!textRows(P, 'ingenstans').length);
});

test('an exact building name ranks above an occupant of the same name', () => {
  const rows = textRows(P, 'nobelhuset', 'nobelhuset');
  assert.deepEqual(rows.map(r => r.kind), ['building', 'occupant']);
  assert.equal(textRows(P, 'borshuset')[0].kind, 'building');
});
