import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cityCount, layerCount, tallyTitle, tallyFromAttrs, EST_FLAGS, periodCounts } from '../count.js';
import { YFLAG } from '../codes.js';

// A tiny stockholm.json: three periods, known years in `histogram`, area and estimate dates in `histogramEst`,
// and buildings without a year in `unknown`. stats.buildings is the sum of all three.
const config = {
  yearMin: 1850, yearMax: 2020, unknown: 7,
  periods: [{ key: 'p1' }, { key: 'p2' }, { key: 'p3' }],
  histogram: { 1850: [2, 0, 0], 1900: [3, 1, 0], 1901: [0, 4, 0], 1950: [0, 0, 5], 2020: [0, 0, 6] },
  histogramEst: { 1900: [1, 0, 0], 1930: [0, 2, 0], 2020: [0, 0, 1] },
};
const buildings = 2 + 4 + 4 + 5 + 6 + 1 + 2 + 1 + 7; // 32
const start = config.yearMin - 1; // where app.js puts the from-handle at load (uniforms.uYearFrom)
const T0 = Math.floor(config.yearMin / 50) * 50; // the left end of the timeline, as far as the handle goes

test('with the from-handle at its start, "Today" counts every building', () => {
  assert.equal(cityCount(config, start, config.yearMax), buildings);
  // T0 = 1850 fades the 1850 buildings, and a from-handle there has moved, so the ones without a year leave
  assert.equal(cityCount(config, T0, config.yearMax), buildings - 2 - 7);
});

test('a year counts once the to-handle reaches it and stops when the from-handle reaches it', () => {
  // the shader draws year <= to and fades year <= from
  assert.equal(cityCount(config, start, 1900), 2 + 4 + 1);
  assert.equal(cityCount(config, 1900, 1901), 4);
  assert.equal(cityCount(config, 1899, 1900), 4 + 1);
});

test('a mid range counts the dated buildings in it, area and estimate dates included, and no unknown ones', () => {
  assert.equal(cityCount(config, 1900, 1950), 4 + 2 + 5);
});

test('buildings without a year count only where the map draws them: not with the from-handle moved', () => {
  // "1900–Today": the from-handle moved hides them (web/unknown.js), so only the dated buildings count
  assert.equal(cityCount(config, 1900, config.yearMax), 4 + 5 + 6 + 2 + 1);
  assert.equal(cityCount(config, 2019, config.yearMax), 6 + 1);
  assert.equal(cityCount(config, start + 0.4, config.yearMax), buildings); // rounded as the title rounds it: at rest
});

test('with the legend\'s switch set to "show" they count at "Today" wherever the from-handle is, and still not in the past', () => {
  const all = () => true;
  assert.equal(cityCount(config, start, config.yearMax, all, 'show'), buildings);
  assert.equal(cityCount(config, 1900, config.yearMax, all, 'show'), 4 + 5 + 6 + 2 + 1 + 7);
  assert.equal(cityCount(config, start, config.yearMax - 1, all, 'show'), buildings - 6 - 1 - 7);
  assert.equal(cityCount(config, 1900, 1950, all, 'show'), 4 + 2 + 5);
  assert.equal(cityCount(config, 1900, config.yearMax, i => i !== 1, 'show'), 5 + 6 + 1); // a period alone: never
});

test('with the switch set to "hide" they never count, not even at "Today"', () => {
  const all = () => true;
  assert.equal(cityCount(config, start, config.yearMax, all, 'hide'), buildings - 7);
  assert.equal(cityCount(config, 1900, config.yearMax, all, 'hide'), 4 + 5 + 6 + 2 + 1);
  assert.equal(cityCount(config, start, config.yearMax, all, 'auto'), buildings); // left alone: as at load
});

test('before "Today" buildings without a year are not counted', () => {
  assert.equal(cityCount(config, start, config.yearMax - 1), buildings - 6 - 1 - 7);
});

test('a hidden period leaves the count, and so do the buildings without a year (uShowUnknown)', () => {
  const on = i => i !== 1;
  assert.equal(cityCount(config, start, config.yearMax, on), 2 + 3 + 5 + 6 + 1 + 1);
  assert.equal(cityCount(config, 1900, config.yearMax, on), 5 + 6 + 1);
});

test('a config without histogramEst or unknown still counts', () => {
  const { histogramEst, unknown, ...bare } = config;
  assert.equal(cityCount(bare, start, config.yearMax), buildings - 4 - 7);
});

test('with the estimates hidden, area and estimate dates leave the count; the rest stays', () => {
  assert.equal(cityCount(config, start, config.yearMax, () => true, 'auto', { est: false }), buildings - 4);
  assert.equal(cityCount(config, 1900, 1950, () => true, 'auto', { est: false }), 4 + 5);
  assert.equal(cityCount(config, start, config.yearMax, () => true, 'auto', { est: true }), buildings);
  // the hide option and the choice for the buildings without a year work side by side
  assert.equal(cityCount(config, start, config.yearMax, () => true, 'hide', { est: false }), buildings - 4 - 7);
  assert.equal(cityCount(config, 1900, config.yearMax, () => true, 'show', { est: false }), 4 + 5 + 6 + 7);
});

// The tally built from attrs.bin (24-byte records, tile.js readAttrs layout): it counts the shader's years, so a
// private house sits at its decade start, not spread over the decade as stockholm.json's histogram spreads it.
function attrsOf(rows) {
  const view = new DataView(new ArrayBuffer(24 * rows.length));
  rows.forEach(([year, yflag, period], gid) => {
    const o = gid * 24;
    view.setUint8(o + 3, yflag); view.setInt16(o + 4, year, true); view.setUint8(o + 21, period);
  });
  return view;
}
const three = [{ key: 'p1' }, { key: 'p2' }, { key: 'p3' }];
const span3 = { periods: three, yearMin: 1850, yearMax: 2020 };

test('tallyFromAttrs splits known, estimated and unknown by year and period, at the years the shader draws', () => {
  const view = attrsOf([[1850, YFLAG.EXACT, 0], [1900, YFLAG.RANGE, 1], [1900, YFLAG.LONG, 1], [1960, YFLAG.EXACT, 2],
    [1930, YFLAG.AREA, 1], [1952, YFLAG.ESTIMATE, 2], [1950, YFLAG.PERIOD, 2], [0, YFLAG.UNKNOWN, 0], [0, YFLAG.UNKNOWN, 0]]);
  const tally = tallyFromAttrs(view, 9, 24, span3);
  assert.deepEqual(tally.histogram, { 1850: [1, 0, 0], 1900: [0, 2, 0], 1960: [0, 0, 1] });
  assert.deepEqual(tally.histogramEst, { 1930: [0, 1, 0], 1952: [0, 0, 1], 1950: [0, 0, 1] });
  assert.equal(tally.unknown, 2);
  // shaped like stockholm.json, yearMin included: unknownShown reads it (web/unknown.js)
  assert.equal(tally.yearMin, 1850);
  assert.equal(tally.yearMax, 2020);
  assert.equal(tally.periods, three);
  assert.deepEqual(EST_FLAGS, [YFLAG.AREA, YFLAG.ESTIMATE, YFLAG.PERIOD]);
  // the count works from it like from stockholm.json: every building at Today, none of the unknown ones before
  assert.equal(cityCount(tally, 1849, 2020), 9);
  assert.equal(cityCount(tally, 1849, 2019), 7);
  assert.equal(cityCount(tally, 1849, 2020, () => true, 'auto', { est: false }), 6);
  assert.equal(cityCount(tally, 1900, 2020), 4); // the from-handle moved: the unknown ones leave
  // a private house RAÄ dates to 1968 ships as 1960 and is drawn at 1960: the tally counts it from 1960, where the
  // spread histogram would count it from 1967 (a gap left open earlier, closed here)
  const house = attrsOf([[1960, YFLAG.EXACT, 2]]);
  assert.equal(cityCount(tallyFromAttrs(house, 1, 24, span3), 1959, 1965), 1);
  assert.equal(cityCount(tallyFromAttrs(house, 1, 24, span3), 1960, 1965), 0);
});

// Decision 4: the pipeline's ESTIMATED_FLAGS (stockholm.json's histogramEst) and count.js's EST_FLAGS move together.
test('EST_FLAGS is the pipeline\'s ESTIMATED_FLAGS (pipeline/s03_tiles.py)', () => {
  const py = readFileSync(new URL('../../pipeline/s03_tiles.py', import.meta.url), 'utf8');
  const m = py.match(/^ESTIMATED_FLAGS = \(([^)]*)\)/m);
  assert.ok(m, 'ESTIMATED_FLAGS not found in s03_tiles.py');
  const names = m[1].split(',').map(s => s.trim()).filter(Boolean).map(s => s.replace(/^codes\./, ''));
  assert.deepEqual(names.map(n => YFLAG[n]), EST_FLAGS);
});

// Decision 4, the shader's half (F29): the vertex shader in app.js draws in estimate style, and hides behind the
// legend's switch, exactly the yflags the count leaves out with { est: false }.
test("EST_FLAGS is the vertex shader's estimate set (web/app.js)", () => {
  const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  const m = app.match(/^\s*bool est = ([^;]*);$/m);
  assert.ok(m, 'bool est = …; not found in app.js');
  assert.equal(m[1].replace(/yflag == \d+/g, '').replace(/\|\|/g, '').trim(), '', `only yflag tests joined by ||: ${m[1]}`);
  assert.deepEqual([...m[1].matchAll(/yflag == (\d+)/g)].map(x => +x[1]), EST_FLAGS);
  assert.match(app, /^\s*if \(est\) \{$/m, 'the estimate style is drawn for est');
  assert.match(app, /^\s*if \(uMode < 0\.5 && est && uHideEst > 0\.5\) vis = 0\.0;$/m, 'the switch hides est');
  assert.doesNotMatch(app.replace(m[0], ''), /yflag [!=]= [346]\b/, 'no second estimate set in the shader');
});

test('layer groups follow the range too; a group year 0 (no year) never fades', () => {
  const groups = [{ years: { 0: 3, 1900: 2, 1950: 4 } }, { years: { 1960: 1 } }];
  assert.equal(layerCount(groups, start, 2020), 3 + 2 + 4 + 1);
  assert.equal(layerCount(groups, 1900, 2020), 3 + 4 + 1);
  assert.equal(layerCount(groups, 1900, 1955), 3 + 4);
});

// The title over the count says what the map shows (tallyTitle). Real numbers: the oldest building is from 1100
// (config.yearMin) with the from-handle resting just before it, "Today" is 2015 (yearMax), Funkis is 1930–45 in
// config.periods.
const span = { start: 1100, end: 2015 };
const untouched = span.start - 1;
const funkis = { name: 'Funkis', from: 1930, to: 1945 };

test('full range, nothing picked: "Today" and no note after the count', () => {
  assert.deepEqual(tallyTitle({ ...span, from: untouched, to: 2015 }), { title: 'Today', note: '', kind: 'today' });
});

test('the timeline dragged back: the to-year', () => {
  assert.deepEqual(tallyTitle({ ...span, from: untouched, to: 1850 }), { title: '1850', note: '', kind: 'year' });
  assert.equal(tallyTitle({ ...span, from: untouched, to: 1849.6 }).title, '1850'); // the film passes fractions
});

test('the from-handle moved: the range, ending "Today" or at the to-year', () => {
  assert.deepEqual(tallyTitle({ ...span, from: 1900, to: 2015 }), { title: '1900–Today', note: '', kind: 'range' });
  assert.deepEqual(tallyTitle({ ...span, from: 1900, to: 1950 }), { title: '1900–1950', note: '', kind: 'range' });
  assert.equal(tallyTitle({ ...span, from: span.start, to: 2015 }).title, '1100–Today'); // it fades the oldest one
});

test('a from-handle before the oldest building fades nothing: still "Today", wherever the timeline starts', () => {
  // The timeline starts on a multiple of 50 (1100), the oldest building need not (1140): resting at 1139 is untouched.
  assert.deepEqual(tallyTitle({ start: 1140, end: 2015, from: 1139, to: 2015 }), { title: 'Today', note: '', kind: 'today' });
  assert.equal(tallyTitle({ start: 1140, end: 2015, from: 1140, to: 2015 }).title, '1140–Today');
});

test('the range is never backwards, and its years are whole', () => {
  // the film can start before the from-handle; a handle grabbed mid-film can sit on a fraction
  assert.equal(tallyTitle({ ...span, from: 1512, to: 1135 }).title, '1512');
  assert.equal(tallyTitle({ ...span, from: 1849.4, to: 1850 }).title, '1849–1850');
  assert.equal(tallyTitle({ ...span, from: 1930.4, to: 2015, period: funkis }).note, '1930–45');
});

test('one period picked: its name, and its own years after the count', () => {
  assert.deepEqual(tallyTitle({ ...span, from: untouched, to: 2015, period: funkis }),
    { title: 'Funkis', note: '1930–45', kind: 'period' });
  // within a century the end year is shortened; across one it is not; the last period runs to "Today"
  const note = period => tallyTitle({ ...span, from: untouched, to: 2015, period }).note;
  assert.equal(note({ name: 'Jugend', from: 1890, to: 1919 }), '1890–1919');
  assert.equal(note({ name: 'Waterfront districts', from: 1994, to: 2100 }), '1994–Today');
});

test('a period picked on a narrowed timeline: its name, and its years cut to the range', () => {
  const at = (from, to) => tallyTitle({ ...span, from, to, period: funkis });
  assert.deepEqual(at(untouched, 1940), { title: 'Funkis', note: '1930–40', kind: 'period' });
  assert.equal(at(1935, 2015).note, '1935–45');
  assert.equal(at(1900, 1950).note, '1930–45');   // a range wider than the period leaves its years whole
  assert.equal(at(1935, 1935.4).note, '1935');
  assert.equal(at(untouched, 1850).note, '1930–45'); // a range that misses the period keeps the period's own years
});

// The first period starts in 1000 (pipeline/city.py), before the oldest building and the timeline's left end (1100):
// "1000–1610" would name a year the timeline does not show, so its years read "until 1610".
test('a period that starts before the oldest building reads "until" its end year', () => {
  const medieval = { name: 'Medieval & early Vasa', from: 1000, to: 1610 };
  const at = (from, to, t) => tallyTitle({ ...span, from, to, period: medieval }, t).note;
  assert.equal(at(untouched, 2015), 'until 1610');
  assert.equal(at(untouched, 1500), 'until 1500');   // cut by the to-handle
  assert.equal(at(1300, 2015), '1300–1610');          // cut by the from-handle: a range on the timeline again
  assert.equal(at(1700, 2015), 'until 1610');         // a range that misses it keeps the period's own years
  assert.equal(at(untouched, 2015, s => ({ 'until {year}': 'fram till {year}' })[s] || s), 'fram till 1610');
  // a period starting at or after the oldest building keeps its two years
  assert.equal(tallyTitle({ start: 1000, end: 2015, from: 999, to: 2015, period: medieval }).note, '1000–1610');
});

test('the words go through the string table', () => {
  const sv = { Today: 'I dag', '{year}–Today': '{year}–i dag' };
  const t = s => sv[s] || s;
  assert.equal(tallyTitle({ ...span, from: untouched, to: 2015 }, t).title, 'I dag');
  assert.equal(tallyTitle({ ...span, from: 1900, to: 2015 }, t).title, '1900–i dag');
  assert.equal(tallyTitle({ ...span, from: untouched, to: 2015, period: { name: 'Hammarby sjöstad', from: 1994, to: 2100 } }, t).note,
    '1994–i dag');
});

// The legend's numbers follow the range, as the title and the count do.
test('periodCounts counts each period between the handles, estimates only while shown', () => {
  const cfg = { periods: [{}, {}, {}], histogram: { 1650: [2, 0, 0], 1900: [0, 3, 0], 1990: [0, 0, 4] },
    histogramEst: { 1905: [0, 5, 0] }, unknown: 7, yearMin: 1650, yearMax: 1990 };
  assert.deepEqual(periodCounts(cfg, 1649, 1990), [2, 8, 4]);              // "Today", the from-handle at rest
  assert.deepEqual(periodCounts(cfg, 1649, 1900), [2, 3, 0]);              // the timeline at 1900
  assert.deepEqual(periodCounts(cfg, 1900, 1990), [0, 5, 4]);              // 1900 itself fades
  assert.deepEqual(periodCounts(cfg, 1649, 1990, { est: false }), [2, 3, 4]);
});
