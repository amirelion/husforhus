// web/search.js: parsing, ranking, house numbers, near misses and the rows' words, on a small index
// in s14_search's shape.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { prepare, parse, score, textRows, streetsFor, findNumber, addressRows, edits, didYouMean, search, rowText, bare }
  from '../search.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');

const INDEX = {
  v: 1, settings: { min_chars: 2, max_rows: 8, max_per_kind: 4, max_edits: 2 }, examples: ['Hornsgatan 30'],
  districts: [['Gamla stan', 430, [-400, -300, 300, 400]], ['Södermalm', 6812, [-2000, 300, 2500, 2600]],
    ['Vasastaden', 2900, [-1500, -3000, 500, -1200]], ['Östermalm', 4100, [0, -3000, 3000, 0]]],
  aliases: [['Vasastan', [2]], ['Söder', [1]], ['Old Town', [0]]],
  outside: ['Solna', 'Nacka'], addressed: 51746,
  streets: [['Hornsgatan', 214, [1], 'h'], ['Hornsbruksgatan', 40, [1], 'h'], ['Götgatan', 180, [1], 'g'],
    ['Ringvägen', 380, [1, 0, 3], 'r'], ['Sankt Eriksgatan', 150, [2], 's'], ['Södermannagatan', 90, [1], 's'],
    ['Södermalmstorg', 12, [1], 's'], ['Stadsgårdsleden', 8, [1], 's']],
  buildings: [['Engelbrektskyrkan', 501, 3, 'Engelbrekt Church'], ['Stockholms stadshus', 502, 0, 'Stockholm City Hall'],
    ['Södra teatern', 503, 1, ''], ['Stockholms slott', 1, 0, 'Stockholm Palace'], ['Södra Stadshuset', 504, 1, ''],
    ['Stockholms stadsteater', 505, 0, '']],
  // as the real cards name them (r4-ux-copy.md §3.2): the palace is "Stockholms slott", City Hall "Stockholms stadshus"
  baliases: [['Kungliga slottet', 1], ['Royal Palace', 1], ['Slottet', 1], ['Stadshuset', 502]],
};
const SHARDS = {
  h: { Hornsgatan: [['28', 10, 1], ['29', 11, 1], ['30', 12, 1], ['30A', 13, 1], ['31', 14, 1], ['35', 15, 1]],
    Hornsbruksgatan: [['2', 20, 1]] },
  g: { Götgatan: [['7', 30, 1]] },
  s: { 'Sankt Eriksgatan': [['12', 40, 2], ['14', 41, 2]] },
  r: { Ringvägen: [['1', 50, 1]] },
};
const P = prepare(INDEX);
const shard = async k => SHARDS[k];

test('prepare folds every name once and keeps the index\'s numbers', () => {
  assert.equal(P.addressed, 51746);
  assert.deepEqual(P.examples, ['Hornsgatan 30']);
  assert.deepEqual([P.districts[1].f, P.streets[4].f, P.buildings[1].fe], ['sodermalm', 'sankt eriksgatan', 'stockholm city hall']);
});

test('parse tells a street and number from text, a year, a lone number and too little', () => {
  assert.deepEqual(parse('Hornsgatan 30'), { kind: 'address', f: 'hornsgatan 30', street: 'hornsgatan', number: '30', letter: '' });
  assert.deepEqual(parse('hornsgatan 30 a'), { kind: 'address', f: 'hornsgatan 30 a', street: 'hornsgatan', number: '30', letter: 'A' });
  assert.equal(parse('Hornsgatan 30A').letter, 'A');
  assert.equal(parse('Hornsg 030').number, '30');
  assert.equal(parse('Hornsgatan 12-14').number, '12');                      // a range: its first number
  assert.equal(parse('S:t Eriksgatan 12').street, 'sankt eriksgatan');
  assert.equal(parse('Hornsgatan 30, 118 20 Stockholm').number, '30');      // fold drops the postcode and the city
  assert.deepEqual(parse('1930'), { kind: 'year', f: '1930', year: 1930 });
  assert.equal(parse('30').kind, 'number');
  assert.equal(parse('30 b').kind, 'number');
  assert.equal(parse('h').kind, 'short');
  assert.equal(parse('  ').kind, 'short');
  assert.equal(parse('Stadshuset').kind, 'text');
});

test('score: exact, prefix, a word inside, anywhere', () => {
  assert.equal(score('hornsgatan', 'hornsgatan'), 0);
  assert.equal(score('hornsgatan', 'hornsg'), 1);
  assert.equal(score('stockholms stadshus', 'stadshus'), 2);
  assert.equal(score('engelbrektskyrkan', 'kyrkan'), 3);
  assert.equal(score('hornsgatan', 'gotgatan'), -1);
  assert.equal(score('hornsgatan', ''), -1);
});

test('text rows: a stadsdel before a building before a street, at most four of a kind', () => {
  const rows = textRows(P, 'soder', 'Söder');
  // "Söder" is Södermalm's everyday name (exact, so once, by it) and the start of two streets, the bigger first
  assert.deepEqual(rows.map(r => [r.kind, r.label]), [['district', 'Södermalm'], ['street', 'Södermannagatan'],
    ['street', 'Södermalmstorg']]);
  assert.equal(rows[0].via, 'Söder');
  const many = textRows(P, 'gatan', 'gatan');
  assert.equal(many.filter(r => r.kind === 'street').length, 4);              // max_per_kind
  assert.deepEqual(textRows(P, 'stadshus', 'stadshus').map(r => r.label), ['Stockholms stadshus', 'Södra Stadshuset']);
  // an English label finds the building, and the row says so in English
  const hall = textRows(P, 'city hall', 'City Hall')[0];
  assert.equal(hall.gid, 502);
  assert.equal(rowText(hall, P, EN).sub, 'Building · “Stockholm City Hall” · Gamla stan');
  assert.equal(rowText(hall, P, SV).sub, 'Byggnad · Gamla stan');
  assert.deepEqual(textRows(P, 'old town', 'Old Town').map(r => [r.kind, r.label, r.via]), [['district', 'Gamla stan', 'Old Town']]);
});

test('the names people type find the best-known buildings: other names, and Swedish\'s definite ending', async () => {
  // r4-ux-copy.md §3.2: the map opens on the palace and City Hall, so these are the first searches
  for (const [q, gid] of [['Stadshuset', 502], ['Kungliga slottet', 1], ['Royal Palace', 1], ['Slottet', 1], ['City Hall', 502]]) {
    assert.equal((await search(P, q, shard)).rows[0].gid, gid, q);
  }
  const palace = textRows(P, 'royal palace', 'Royal Palace')[0];
  assert.equal(palace.label, 'Stockholms slott');                               // the card's own name, found by another
  assert.equal(rowText(palace, P, EN).sub, 'Building · “Royal Palace” · Gamla stan');
  assert.equal(rowText(palace, P, SV).sub, 'Byggnad · “Royal Palace” · Gamla stan');
  // "stadsteatern" is in no name; without its ending, "stadsteater" is
  assert.deepEqual(bare('stadsteatern'), ['stadsteater']);
  assert.equal((await search(P, 'Stadsteatern', shard)).rows[0].gid, 505);
  assert.deepEqual(bare('slottet'), ['slott', 'slotte']);
  assert.deepEqual(bare('kyrkan'), ['kyrka']);
  assert.deepEqual(bare('hus'), []);                                             // too short to lose anything
});

test('the right accents rank first among equal matches', () => {
  const p = prepare({ ...INDEX, streets: [['Hammarby sjö', 1, [1], 'h'], ['Hammarbysjo', 9, [1], 'h']] });
  assert.equal(textRows(p, 'hammarby sjo', 'Hammarby sjö')[0].label, 'Hammarby sjö');
});

test('streetsFor: exact, then prefix, then a word inside, never a match in the middle of a word', () => {
  assert.deepEqual(streetsFor(P, 'hornsgatan').map(s => s.name), ['Hornsgatan']);
  assert.deepEqual(streetsFor(P, 'horns').map(s => s.name), ['Hornsgatan', 'Hornsbruksgatan']);
  assert.deepEqual(streetsFor(P, 'eriksgatan').map(s => s.name), ['Sankt Eriksgatan']);
  assert.deepEqual(streetsFor(P, 'gatan').map(s => s.name), []);
});

test('findNumber: with its letter, the bare number, the nearest on the same side, the nearest', () => {
  const pairs = SHARDS.h.Hornsgatan;
  assert.deepEqual(findNumber(pairs, '30', 'A'), { pair: ['30A', 13, 1], near: null });
  assert.deepEqual(findNumber(pairs, '30', ''), { pair: ['30', 12, 1], near: null });
  assert.deepEqual(findNumber(pairs, '28', 'B'), { pair: ['28', 10, 1], near: '28B' });    // no 28B: 28, saying so
  assert.deepEqual(findNumber(pairs, '33', ''), { pair: ['31', 14, 1], near: '33', side: true });   // odd side: 31, 35
  assert.deepEqual(findNumber([['2', 1, 0], ['4', 2, 0]], '7', ''), { pair: ['4', 2, 0], near: '7', side: false });
  assert.equal(findNumber([], '1', ''), null);
  assert.equal(findNumber(undefined, '1', ''), null);
});

test('address rows: one per matching street, with the stadsdel the address lies in', async () => {
  const rows = await addressRows(P, parse('Horns 2'), shard);
  assert.deepEqual(rows.map(r => r.label), ['Hornsgatan 28', 'Hornsbruksgatan 2']);
  assert.equal(rows[0].near, '2');
  assert.deepEqual(rowText(rows[0], P, EN), { main: 'Hornsgatan 28',
    sub: "Address · Södermalm · no. 2 isn't in our list; this is the nearest on the same side" });
  assert.deepEqual(rowText(rows[1], P, SV), { main: 'Hornsbruksgatan 2', sub: 'Adress · Södermalm' });
  const exact = await addressRows(P, parse('S:t Eriksgatan 14'), shard);
  assert.deepEqual(exact.map(r => [r.label, r.gid, r.near]), [['Sankt Eriksgatan 14', 41, null]]);
});

test('edits and the near miss', () => {
  assert.equal(edits('hornsgatan', 'hornsgatan'), 0);
  assert.equal(edits('hornsgatan', 'honrsgatan'), 2);
  assert.equal(edits('hornsgatan', 'hornsgata'), 1);
  assert.equal(edits('hornsgatan', 'xyz'), 3);                               // gives up past max
  assert.equal(didYouMean(P, 'hornsgaten'), 'Hornsgatan');
  assert.equal(didYouMean(P, 'sodermlam'), 'Södermalm');
  assert.equal(didYouMean(P, 'qqqqqq'), null);
});

test('search: every state a query can end in, with its message id', async () => {
  assert.deepEqual(await search(P, 'h', shard), { rows: [], message: null });
  assert.deepEqual((await search(P, '1930', shard)).message, { id: 'search.year', vars: { year: 1930 } });
  assert.deepEqual((await search(P, '33', shard)).message, { id: 'search.number' });
  assert.deepEqual((await search(P, 'Solna', shard)).message, { id: 'search.outside', vars: { place: 'Solna' } });
  const a = await search(P, 'Hornsgatan 30', shard);
  assert.deepEqual(a.rows.map(r => [r.kind, r.label, r.gid]), [['address', 'Hornsgatan 30', 12]]);
  assert.equal((await search(P, 'Engelbrekt', shard)).rows[0].gid, 501);
  // the suggestion keeps the house number, so taking it searches the address
  assert.deepEqual((await search(P, 'Hornsgaten 30', shard)).message,
    { id: 'search.didyoumean', vars: { name: 'Hornsgatan 30' }, suggest: 'Hornsgatan 30' });
  assert.deepEqual((await search(P, 'zzzzzz', shard)).message, { id: 'search.none', vars: { q: 'zzzzzz' } });
  // a street and number on a street without that number still finds the street itself as text
  const t = await search(P, 'Götgatan', shard);
  assert.deepEqual(t.rows.map(r => r.kind), ['street']);
});

test('the rows read right in English and Swedish', () => {
  const st = textRows(P, 'ringvagen', 'Ringvägen')[0];
  assert.deepEqual(rowText(st, P, EN), { main: 'Ringvägen', sub: 'Street · Södermalm, Gamla stan +1 · 380 buildings' });
  assert.deepEqual(rowText(st, P, SV), { main: 'Ringvägen', sub: 'Gata · Södermalm, Gamla stan +1 · 380 byggnader' });
  const d = textRows(P, 'sodermalm', 'Södermalm')[0];
  assert.deepEqual(rowText(d, P, EN), { main: 'Södermalm', sub: 'District · 6,812 buildings' });
  assert.deepEqual(rowText(d, P, SV), { main: 'Södermalm', sub: `Stadsdel · ${SV.num(6812)} byggnader` });   // 6 812
  const one = rowText({ kind: 'street', label: 'Gränd', n: 1, ds: [] }, P, EN);
  assert.equal(one.sub, 'Street · 1 building');
  const v = textRows(P, 'vasastan', 'Vasastan')[0];
  assert.equal(rowText(v, P, SV).sub, `Stadsdel · kallas även Vasastan · ${SV.num(2900)} byggnader`);
});

// Each case seen on the whole city's index
test('a building matched by its Swedish name ranks before one matched only by its English label', () => {
  const p = prepare({ ...INDEX, buildings: [['Börshuset', 10, 0, 'Stockholm Stock Exchange'],
    ['Stockholms slott', 1, 0, 'Stockholm Palace']] });
  assert.deepEqual(textRows(p, 'stockholm', 'Stockholm').map(r => r.label), ['Stockholms slott', 'Börshuset']);
});

test('buildings with the same name in the same stadsdel are one row', () => {
  const p = prepare({ ...INDEX, buildings: [['Skanskvarnsskolan', 601, 1, ''], ['Skanskvarnsskolan', 602, 1, ''],
    ['Skanskvarnsskolan', 603, 2, '']] });
  assert.deepEqual(textRows(p, 'skanskvarnsskolan', 'Skanskvarnsskolan').map(r => [r.gid, r.d]), [[601, 1], [603, 2]]);
});

test('a neighbouring municipality says the map stops at the border and still lists the streets named after it', async () => {
  const p = prepare({ ...INDEX, streets: [...INDEX.streets, ['Solnavägen', 20, [2], 's']] });
  const r = await search(p, 'Solna', shard);
  assert.deepEqual(r.message, { id: 'search.outside', vars: { place: 'Solna' } });
  assert.deepEqual(r.rows.map(x => x.label), ['Solnavägen']);
});

test('parse reads a range\'s letter, a decade, "nr" and a floor as people write them', () => {
  assert.deepEqual(parse('Hornsgatan 30-32A'), { kind: 'address', f: 'hornsgatan 30 32a', street: 'hornsgatan', number: '30', letter: '' });
  assert.equal(parse('12-14').kind, 'number');
  assert.deepEqual(parse('1930s'), { kind: 'year', f: '1930s', year: 1930 });
  assert.equal(parse('1930-talet').year, 1930);
  for (const q of ['Hornsgatan nr 30', 'Hornsgatan no. 30', 'Hornsgatan 30 3 tr', 'Hornsgatan 30, 3tr']) {
    assert.deepEqual([parse(q).street, parse(q).number], ['hornsgatan', '30'], q);
  }
  assert.equal(parse('Hornsgatan 30 A 2 tr').letter, 'A');
});

test('the near miss also knows the other names and the English labels', () => {
  assert.equal(didYouMean(P, 'ryal palace'), 'Royal Palace');
  assert.equal(didYouMean(P, 'stockholm city hal'), 'Stockholms stadshus');      // by its card's name, never the label
});

test('every search string exists in both languages', () => {
  const ids = Object.keys(TABLES.en).filter(k => k.startsWith('search.'));
  assert.ok(ids.length >= 14);
  for (const id of ids) assert.ok(TABLES.sv[id], id);
});
