import { unknownShown } from './unknown.js';
import { YFLAG } from './codes.js';

// The building count under the timeline (the count follows the range). Pure, so it can be tested
// without a browser. It counts what the vertex shader in app.js draws in colour, neither hidden nor faded:
// - a dated building (every yflag but 7 UNKNOWN; area and estimate dates too) stands once its year <= to
//   (uYear) and fades once its year <= from (uYearFrom), so it counts when from < year <= to;
// - a building without a year (yflag 7, year 0) never fades. The count takes these in only at the end of the
//   timeline (never at a past year), and there only where the map draws them (web/unknown.js unknownShown):
//   left alone, at "Today" with the from-handle at rest; with the legend's switch set to show, wherever the
//   from-handle is; with it set to hide, never; and never while a period is shown alone. So "1900–Today" counts the
//   dated buildings only, unless the visitor chose to show them;
// - with the estimates hidden ({ est: false }) the area, estimate and period-only buildings leave the count.

// The yflags drawn in estimate style and hidden by the switch: dated by an area or by the kNN, or by a period only.
// pipeline/s03_tiles.py ESTIMATED_FLAGS (stockholm.json's histogramEst) and the vertex shader's `est` in app.js are the
// same set (web/test/count.test.mjs checks both).
export const EST_FLAGS = [YFLAG.AREA, YFLAG.ESTIMATE, YFLAG.PERIOD];

// The tally the count works from, built from attrs.bin (tile.js readAttrs layout) so it counts exactly what the
// shader draws: a private house at its decade start, where stockholm.json's histogram spreads it over the decade
// (that spread is for drawHist only). Shaped like stockholm.json: {histogram, histogramEst,
// unknown, yearMin, yearMax, periods}, with histogram = EXACT/RANGE/LONG and histogramEst = AREA/ESTIMATE/PERIOD by
// year; yearMin and yearMax are config's, which unknownShown reads.
export function tallyFromAttrs(view, n, stride, { periods, yearMin, yearMax }) {
  const histogram = {}, histogramEst = {};
  let unknown = 0;
  for (let gid = 0; gid < n; gid++) {
    const o = gid * stride;
    const yflag = view.getUint8(o + 3), year = view.getInt16(o + 4, true), period = view.getUint8(o + 21);
    if (yflag === YFLAG.UNKNOWN) { unknown++; continue; }
    const h = EST_FLAGS.includes(yflag) ? histogramEst : histogram;
    (h[year] ??= periods.map(() => 0))[period]++;
  }
  return { histogram, histogramEst, unknown, yearMin, yearMax, periods };
}

// config: stockholm.json or a tally from tallyFromAttrs (histogram, histogramEst, unknown, yearMin, yearMax,
// periods); on(i): is period i shown; pref: the visitor's choice for the buildings without a year, 'auto', 'show' or
// 'hide' (web/unknown.js); est: are the estimates shown (the hide switch).
export function cityCount(config, from, to, on = () => true, pref = 'auto', { est = true } = {}) {
  let n = 0;
  for (const h of [config.histogram, est ? config.histogramEst || {} : {}]) {
    for (const [y, v] of Object.entries(h)) if (+y > from && +y <= to) v.forEach((c, i) => { if (on(i)) n += c; });
  }
  const solo = !config.periods.every((_, i) => on(i));
  if (to >= config.yearMax && unknownShown({ from, to, start: config.yearMin, end: config.yearMax, pref, solo })) {
    n += config.unknown || 0;
  }
  return n;
}

// The legend's number per period: the dated buildings of each period the map draws in colour between the
// handles, from < year <= to, the estimated ones only while shown. At "Today" with the from-handle at rest it is the
// period's total.
export function periodCounts(config, from, to, { est = true } = {}) {
  const out = config.periods.map(() => 0);
  for (const h of [config.histogram, est ? config.histogramEst || {} : {}]) {
    for (const [y, v] of Object.entries(h)) if (+y > from && +y <= to) v.forEach((c, i) => { out[i] += c; });
  }
  return out;
}

// Context layers: groups of {years: {year: count}}. A group's year 0 (no year) never fades, as in the shader.
export function layerCount(groups, from, to) {
  let n = 0;
  for (const g of groups) {
    for (const [y, c] of Object.entries(g.years)) if ((+y === 0 || +y > from) && +y <= to) n += c;
  }
  return n;
}

// The big title over the count, and the note after it: what the map shows. Years are the handles' positions, as
// the timeline draws them, in whole years and never backwards. start: config.yearMin, the oldest building's year (a
// from-handle below it fades nothing, so it has not been moved); end: config.yearMax, shown as "Today". period: the
// one period shown alone, { name, from, to } with its own years from config.periods, or null. t: app.js's string
// table.
// - Nothing picked: the to-year ("1850", "Today" at the end); once the from-handle moves, the range
//   ("1900–1950", "1900–Today").
// - One period picked: its name, and its years in the note ("1930–45"). A narrowed timeline cuts those years to
//   the range ("1930–40" with the to-handle at 1940); a range that misses the period keeps the period's own years.
//   A period that starts before the oldest building (the first one starts in 1000, the timeline in 1100) reads
//   "until 1610": its start year is not on the timeline.
export function tallyTitle({ from, to, start, end, period = null }, t = s => s) {
  from = Math.round(from);
  to = Math.max(to, from);
  const year = y => (y >= end ? t('Today') : String(Math.round(y)));
  const range = (lo, hi, short) => {
    if (hi >= end) return t('{year}–Today').replace('{year}', lo);
    hi = Math.round(hi);
    if (lo < start) return t('until {year}').replace('{year}', hi);
    if (lo === hi) return String(lo);
    // within a century the end year is shortened: 1930–45, but 1890–1919
    return `${lo}–${short && Math.floor(lo / 100) === Math.floor(hi / 100) ? String(hi).slice(-2) : hi}`;
  };
  const moved = from >= start;
  if (period) {
    const lo = moved ? Math.max(period.from, from) : period.from, hi = Math.min(period.to, to);
    const cut = lo <= Math.round(hi);
    return { title: period.name, note: cut ? range(lo, hi, true) : range(period.from, period.to, true), kind: 'period' };
  }
  if (moved) return { title: range(from, to, false), note: '', kind: 'range' };
  return { title: year(to), note: '', kind: to >= end ? 'today' : 'year' };
}
