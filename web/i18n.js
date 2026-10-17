// Strings by stable id: web/i18n/en.json and web/i18n/sv.json, both loaded at start (a few KB) so the
// language can switch without a reload. Pure, tested by node --test (web/test/i18n.test.mjs). It holds the
// card's, the Floors legend's and the timeline's strings and the rest of the v1 interface (app.js's old SV_UI).

// "{name}" placeholders filled from vars; a placeholder with no value stays as it is, so a missing one shows.
export const fill = (s, vars = {}) => String(s).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));

// T(id, vars): the string in `lang`, else English, else the id itself. T.lang is the language, T.num(n, digits) a number
// in its format (English 77,743 and 18.4; Swedish 77 743 and 18,4).
export function makeT(tables, lang) {
  const own = tables?.[lang] || {}, en = tables?.en || {};
  const T = (id, vars) => fill(own[id] ?? en[id] ?? id, vars);
  T.lang = lang;
  T.num = (n, digits = 0) => new Intl.NumberFormat(lang === 'sv' ? 'sv-SE' : 'en',
    { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
  return T;
}

// The pure modules that hand app.js English text (count.js tallyTitle, unknown.js unknownHint, howto.js, the look
// switcher) keep their tested English; LEGACY names the id each of those texts has in web/i18n, and legacy(T) gives
// the t(text) those modules take. A text that is not here (the v1.1 quests and context layers, still English, spec
// §2.1) passes through unchanged. web/test/i18n.test.mjs holds every entry to en.json's text.
export const LEGACY = {
  'Today': 'ui.today', '{year}–Today': 'ui.fromToday', 'until {year}': 'ui.until',
  'Look': 'ui.look', 'Classic': 'ui.classic', 'Atmosphere': 'ui.atmosphere', 'None': 'ui.none', 'Close': 'ui.close',
  'Ground': 'ui.relief.title', 'Hills': 'ui.hills',
  'Shown at “Today”, hidden in the past.': 'ui.unknown.auto', 'Your choice is remembered.': 'ui.unknown.chosen',
  'Hidden while one period is shown alone.': 'ui.unknown.solo',
  'Drag to move. Right-drag or ⌘-drag to turn. Scroll or press + / − to zoom.': 'ui.howto.mac',
  'Drag to move. Right-drag or Ctrl-drag to turn. Scroll or press + / − to zoom.': 'ui.howto.other',
};
export const legacy = T => s => (LEGACY[s] ? T(LEGACY[s]) : s);

// Which language the page opens in: ?lang= for this visit only, else the visitor's own
// choice (localStorage hfh-lang, written only by the switch), else the browser's first language that is Swedish or
// English when fromBrowser (city.LANG_FROM_BROWSER), else English. With the switch off
// (features.lang false), always English.
export function pickLang({ param = null, saved = null, languages = [], fromBrowser = true, enabled = true } = {}) {
  if (!enabled) return 'en';
  if (param === 'sv' || param === 'en') return param;
  if (saved === 'sv' || saved === 'en') return saved;
  if (fromBrowser) {
    for (const l of languages || []) {
      const p = String(l).toLowerCase();
      if (p === 'sv' || p.startsWith('sv-')) return 'sv';
      if (p === 'en' || p.startsWith('en-')) return 'en';
    }
  }
  return 'en';
}
