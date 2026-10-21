// web/search.js: what is inside a building (index.occupants, pipeline/s14_search.py): found by its Swedish name, its
// English one or another name, shown as "Nobel Prize Museum, in Börshuset", picked like the building, and ranked
// below an exact match on a building's own name. One on a footprint whose card has no name (the hand-checked table,
// pipeline/occupant_pins.csv) stands alone, with the stadsdel its entry carries.
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
    // a footprint no building row names: Historiska museet, whose card shows no name of its own, in stadsdel 0
    ['Historiska museet', 'Swedish History Museum', 999, ['Statens historiska museum'], 0]],
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

test('an institution on a footprint with no named card is found alone, flies to its footprint, says where it is', async () => {
  for (const q of ['Historiska museet', 'statens historiska', 'Swedish History']) {
    const { rows } = await search(P, q, async () => ({}));
    assert.equal(rows[0].kind, 'occupant', q);
    assert.equal(rows[0].gid, 999, q);
  }
  const [row] = (await search(P, 'historiska museet', async () => ({}))).rows;
  assert.deepEqual(rowText(row, P, SV), { main: 'Historiska museet', sub: 'I en byggnad · Gamla stan' });
  assert.deepEqual(rowText(row, P, EN), { main: 'Swedish History Museum', sub: 'Inside a building · Gamla stan' });
});

test('an exact building name ranks above an occupant of the same name', () => {
  const rows = textRows(P, 'nobelhuset', 'nobelhuset');
  assert.deepEqual(rows.map(r => r.kind), ['building', 'occupant']);
  assert.equal(textRows(P, 'borshuset')[0].kind, 'building');
});
