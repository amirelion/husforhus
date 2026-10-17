import { test } from 'node:test';
import assert from 'node:assert/strict';
import { metroAt, metroOnFrom, metroHref, stationCard, LINE_COLOURS } from '../metro.js';
import { THEMES } from '../themes.js';
import { rgb } from '../tone.js';

// A small fixture: the green line's first stretch (1950), its extension (1952), the red line (1964), a station that
// closed, and Kymlinge, which never opened.
const metro = {
  segments: [
    { id: 'S01', line: 'green', opened: '1950-10-01', stations: ['Slussen', 'Hökarängen'], track: [[0, 0], [1, 1]] },
    { id: 'S02', line: 'green', opened: '1952-10-26', stations: ['Slussen', 'Hötorget'], track: [[0, 0], [1, 1]] },
    { id: 'S10', line: 'red', opened: '1964-04-05', stations: ['Slussen', 'Fruängen'], track: [[0, 0], [1, 1]] },
    { id: 'S20', line: 'blue', opened: '1975-08-31', closed: '1977-01-01', stations: ['A', 'B'], track: [[0, 0], [1, 1]] },
  ],
  stations: [
    { name: 'Slussen', lines: ['green', 'red'], opened: '1950-10-01', x: 0, z: 0, wikidata: 'Q1', names: [] },
    { name: 'Hökarängen', lines: ['green'], opened: '1950-10-01', x: 1, z: 1, names: [] },
    { name: 'Hötorget', lines: ['green'], opened: '1952-10-26', x: 2, z: 2, wikidata: 'Q2',
      names: [{ name: 'Kungsgatan', from: '1952-10-26', to: '1957-11-23' }] },
    { name: 'Fruängen', lines: ['red'], opened: '1964-04-05', x: 3, z: 3, names: [] },
    { name: 'Gone', lines: ['blue'], opened: '1975-08-31', closed: '1977-01-01', x: 4, z: 4, names: [] },
    { name: 'Kymlinge', lines: ['blue'], opened: null, never: true, x: 5, z: 5, wikidata: 'Q1748454', names: [] },
  ],
};
const names = a => a.map(s => s.name).sort();

test('a segment and a station appear in the year they opened, not before', () => {
  assert.deepEqual(metroAt(metro, 1949).segments, []);
  const at1950 = metroAt(metro, 1950);
  assert.deepEqual(at1950.segments.map(g => g.id), ['S01']);
  assert.deepEqual(names(at1950.stations), ['Hökarängen', 'Slussen']);
  const at1960 = metroAt(metro, 1960);
  assert.deepEqual(at1960.segments.map(g => g.id), ['S01', 'S02']);
  assert.ok(!at1960.segments.some(g => g.line === 'red') && !names(at1960.stations).includes('Fruängen'));
  assert.ok(metroAt(metro, 1964).segments.some(g => g.line === 'red'));
});

test('a closed one goes in its closing year; Kymlinge shows only at Today', () => {
  assert.ok(names(metroAt(metro, 1976).stations).includes('Gone'));
  assert.ok(!names(metroAt(metro, 1977).stations).includes('Gone'));
  assert.deepEqual(metroAt(metro, 2025).never, []);
  const today = metroAt(metro, 2026, '2026-10-17');
  assert.deepEqual(names(today.never), ['Kymlinge']);
  assert.deepEqual(names(today.stations), ['Fruängen', 'Hökarängen', 'Hötorget', 'Slussen']);
  assert.deepEqual(today.segments.map(g => g.id), ['S01', 'S02', 'S10']);
});

test('the switch: off by default, ?metro=1 or a remembered on turns it on, and the URL follows', () => {
  assert.equal(metroOnFrom('', null), false);
  assert.equal(metroOnFrom('?metro=1', null), true);
  assert.equal(metroOnFrom('', 'on'), true);
  assert.equal(metroOnFrom('', 'off'), false);
  assert.equal(metroHref('https://x.se/?a=1', true), 'https://x.se/?a=1&metro=1');
  assert.equal(metroHref('https://x.se/?metro=1&a=1', false), 'https://x.se/?a=1');
});

// WCAG relative luminance contrast against each look's land: the three colours read on all four looks.
const lum = h => rgb(h).map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)).reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
test('the line colours read on every look', () => {
  for (const [look, th] of Object.entries(THEMES)) {
    for (const [line, c] of Object.entries(LINE_COLOURS)) assert.ok(contrast(c, th.land) >= 2.5, `${line} on ${look}: ${contrast(c, th.land)}`);
  }
});

test('the station card: name, lines, opening date, earlier names and the Wikidata link; no image', () => {
  const T = Object.assign((k, v = {}) => ({ 'metro.opened': `Opened ${v.date}`, 'metro.formerly': `Formerly ${v.name} (${v.from}–${v.to})`,
    'metro.wikidata': 'Wikidata', 'card.close': 'Close', 'metro.never': 'Never opened', 'metro.neverName': `${v.name} (never opened)` })[k] ?? k, { lang: 'en' });
  const esc = s => String(s);
  const html = stationCard(metro.stations[2], T, esc);
  assert.match(html, /<h3 id="card-title">Hötorget<\/h3>/);
  assert.match(html, /Green line/);
  assert.match(html, /Opened 26 October 1952/);
  assert.match(html, /Formerly Kungsgatan \(1952–1957\)/);
  assert.match(html, /href="https:\/\/www\.wikidata\.org\/wiki\/Q2"/);
  assert.doesNotMatch(html, /<img/);
  assert.match(stationCard(metro.stations[5], T, esc), /Kymlinge \(never opened\)/);
});
