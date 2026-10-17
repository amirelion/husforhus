import { test } from 'node:test';
import assert from 'node:assert/strict';
import { unknownShown, storedPref, readPref, writePref, prefAfterClick, unknownHint, easeShown, UNKNOWN_KEY,
  UNKNOWN_IN_S, UNKNOWN_OUT_S } from '../unknown.js';
import { makeT, legacy } from '../i18n.js';
import { cityCount, tallyTitle } from '../count.js';
import { readFileSync } from 'node:fs';

// Buildings without a year (D30, revised): left alone ('auto') they are drawn at "Today" and gone whenever the map
// shows the past; once the visitor flips the legend's switch, 'show' or 'hide' holds at every year. A period shown
// alone hides them either way. Real numbers: the oldest building is from 1100 (config.yearMin) with the from-handle
// resting just before it, "Today" is 2015 (config.yearMax).
const span = { start: 1100, end: 2015 };
const rest = span.start - 1;
const PREFS = ['auto', 'show', 'hide'];

// A localStorage stand-in: a Map behind getItem/setItem/removeItem, or one whose every call throws.
const memory = (entries = {}) => {
  const m = new Map(Object.entries(entries));
  return { m, getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k) };
};
const broken = () => { throw new Error('SecurityError'); };
const throwing = { getItem: broken, setItem: broken, removeItem: broken };

test('the choice is kept under hfh-unknown: "show" or "hide", and anything else is automatic', () => {
  assert.equal(UNKNOWN_KEY, 'hfh-unknown');
  assert.equal(storedPref('show'), 'show');
  assert.equal(storedPref('hide'), 'hide');
  for (const stored of ['', 'SHOW', 'auto', 'true', '1', null, undefined]) assert.equal(storedPref(stored), 'auto', String(stored));
});

test('the first switch\'s values carry over: "always" (on) is "show", "today" (off) is automatic', () => {
  assert.equal(storedPref('always'), 'show');
  assert.equal(storedPref('today'), 'auto');
});

test('reading migrates the first switch\'s values in storage: "always" becomes "show", "today" goes', () => {
  const was = memory({ [UNKNOWN_KEY]: 'always' });
  assert.equal(readPref(() => was), 'show');
  assert.equal(was.m.get(UNKNOWN_KEY), 'show');
  const off = memory({ [UNKNOWN_KEY]: 'today' });
  assert.equal(readPref(() => off), 'auto');
  assert.equal(off.m.has(UNKNOWN_KEY), false); // automatic is nothing stored
  for (const pref of ['show', 'hide']) {
    const s = memory({ [UNKNOWN_KEY]: pref });
    assert.equal(readPref(() => s), pref);
    assert.equal(s.m.get(UNKNOWN_KEY), pref);
  }
  const none = memory();
  assert.equal(readPref(() => none), 'auto');
  assert.equal(none.m.size, 0); // a first visit stores nothing
});

test('storage that throws (blocked, private, full) leaves it automatic and never throws', () => {
  assert.equal(readPref(() => throwing), 'auto');
  assert.equal(readPref(broken), 'auto'); // the localStorage accessor itself can throw
  assert.doesNotThrow(() => writePref(() => throwing, 'hide'));
  assert.doesNotThrow(() => writePref(broken, 'show'));
  // read works but the migration's write fails: the old value still counts
  const full = { ...memory({ [UNKNOWN_KEY]: 'always' }), setItem: broken, removeItem: broken };
  assert.equal(readPref(() => full), 'show');
});

test('a choice is written as "show" or "hide", and read back', () => {
  const s = memory();
  writePref(() => s, 'hide');
  assert.equal(s.m.get(UNKNOWN_KEY), 'hide');
  assert.equal(readPref(() => s), 'hide');
  writePref(() => s, 'show');
  assert.equal(readPref(() => s), 'show');
});

test('a click turns off what is on and on what is off; with a period shown alone it changes nothing', () => {
  for (const pref of PREFS) {
    assert.equal(prefAfterClick({ shown: true, pref }), 'hide', pref);
    assert.equal(prefAfterClick({ shown: false, pref }), 'show', pref);
    for (const shown of [true, false]) assert.equal(prefAfterClick({ shown, solo: true, pref }), pref, `solo ${pref}`);
  }
});

test('after a click the switch reads the other way, wherever the timeline is', () => {
  for (const pref of PREFS) for (const to of [1300, 1850, span.end]) for (const from of [rest, 1200]) for (const playing of [true, false]) {
    if (to <= from) continue;
    const state = { ...span, from, to, playing };
    const shown = unknownShown({ ...state, pref });
    assert.equal(unknownShown({ ...state, pref: prefAfterClick({ shown, pref }) }), !shown, JSON.stringify({ pref, from, to, playing }));
  }
});

test('every combination: a period alone hides them, a choice holds, otherwise only "Today" shows them', () => {
  for (const atToday of [true, false]) for (const fromAtRest of [true, false]) for (const playing of [true, false]) {
    for (const pref of PREFS) for (const solo of [true, false]) {
      const state = { ...span, to: atToday ? span.end : 1850, from: fromAtRest ? rest : 1900, playing, pref, solo };
      const want = !solo && (pref === 'show' || (pref === 'auto' && atToday && fromAtRest && !playing));
      assert.equal(unknownShown(state), want, JSON.stringify({ atToday, fromAtRest, playing, pref, solo }));
    }
  }
});

test('at load ("Today", nothing moved, nothing chosen) they are drawn', () => {
  assert.equal(unknownShown({ ...span, from: rest, to: span.end }), true);
  assert.equal(unknownShown({ ...span, from: rest, to: span.end, pref: 'auto' }), true);
});

test('the film hides them until it has ended at "Today"', () => {
  // the film passes fractions of a year, and its last frame is at the end of the timeline, still playing
  assert.equal(unknownShown({ ...span, from: rest, to: 1100.4, playing: true }), false);
  assert.equal(unknownShown({ ...span, from: rest, to: span.end - 0.4, playing: true }), false);
  assert.equal(unknownShown({ ...span, from: rest, to: span.end, playing: true }), false);
  // ended: the to-year is at the end and nothing plays, so they are back
  assert.equal(unknownShown({ ...span, from: rest, to: span.end, playing: false }), true);
  // paused in the past: still gone
  assert.equal(unknownShown({ ...span, from: rest, to: 1700, playing: false }), false);
});

test('the timeline dragged back by one year hides them; back at the end they return', () => {
  assert.equal(unknownShown({ ...span, from: rest, to: span.end - 1 }), false);
  assert.equal(unknownShown({ ...span, from: rest, to: span.end }), true);
});

test('the from-handle moved off its rest hides them, even with the to-handle at "Today"', () => {
  assert.equal(unknownShown({ ...span, from: span.start, to: span.end }), false); // it fades the oldest building
  assert.equal(unknownShown({ ...span, from: 1900, to: span.end }), false);
  assert.equal(unknownShown({ ...span, from: rest, to: span.end }), true);
  assert.equal(unknownShown({ ...span, from: 1050, to: span.end }), true); // before the oldest building: still at rest
});

test('"show" keeps them at every year and during the film, "hide" keeps them away even at "Today"', () => {
  for (const [from, to, playing] of [[rest, span.end, false], [rest, 1850, false], [1900, 1950, false], [rest, 1300, true]]) {
    assert.equal(unknownShown({ ...span, from, to, playing, pref: 'show' }), true, `show ${from}–${to} playing=${playing}`);
    assert.equal(unknownShown({ ...span, from, to, playing, pref: 'hide' }), false, `hide ${from}–${to} playing=${playing}`);
    assert.equal(unknownShown({ ...span, from, to, playing, pref: 'show', solo: true }), false, `solo ${from}–${to}`);
  }
});

// The title says what the map shows (tallyTitle): left alone, with the film stopped, buildings without a year are
// drawn exactly when the title reads "Today".
test('left alone and with nothing playing, they are drawn exactly when the title reads "Today"', () => {
  for (const from of [rest - 50, rest, rest + 0.4, span.start, 1500, 2014]) {
    for (const to of [1100, 1850, 2014, 2014.6, span.end]) {
      if (to <= from) continue;
      const today = tallyTitle({ ...span, from, to }).kind === 'today';
      assert.equal(unknownShown({ ...span, from, to }), today, `${from}–${to}`);
    }
  }
});

// The count takes them in only where the map draws them, and only at "Today" (P17: never at a past year): with the
// film stopped, a city of nothing but buildings without a year counts them exactly when they are drawn and the
// to-handle is at the end. So "1900–Today" never counts 49,804 buildings the map does not show (review F1).
test('the count takes them in exactly when they are drawn at the end of the timeline', () => {
  const config = { yearMin: span.start, yearMax: span.end, unknown: 7, periods: [{}, {}], histogram: {} };
  for (const from of [rest - 50, rest, rest + 0.4, span.start, 1500, 2014]) for (const to of [1850, 2014, span.end]) {
    for (const pref of PREFS) for (const solo of [true, false]) {
      if (to <= from) continue;
      const on = i => !solo || i === 0;
      const drawn = unknownShown({ ...span, from, to, pref, solo }) && to >= span.end;
      assert.equal(cityCount(config, from, to, on, pref), drawn ? 7 : 0, JSON.stringify({ from, to, pref, solo }));
    }
  }
});

// The hint under the legend says what "automatic" does; once the visitor has chosen, it says the choice stays.
test('the hint explains the automatic rule, or that the choice is remembered', () => {
  assert.equal(unknownHint('auto'), 'Shown at “Today”, hidden in the past.');
  assert.equal(unknownHint('show'), 'Your choice is remembered.');
  assert.equal(unknownHint('hide'), 'Your choice is remembered.');
});

// With one period shown alone the switch reads off and is disabled whatever the choice is, so the hint says why
// instead of the automatic rule (review R4).
test('the hint says they are hidden while one period is shown alone, whatever the choice', () => {
  for (const pref of PREFS) assert.equal(unknownHint(pref, true), 'Hidden while one period is shown alone.', pref);
  for (const pref of PREFS) assert.equal(unknownHint(pref, false), unknownHint(pref), pref); // solo defaults to off
});

// The hint goes through t() in app.js: every text unknownHint can return needs its id in web/i18n.js LEGACY and a
// Swedish line in web/i18n/sv.json (Plan 4b; app.js's SV_UI before).
test('every hint has a Swedish line in web/i18n', () => {
  const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
  const sv = legacy(makeT({ en: load('en'), sv: load('sv') }, 'sv'));
  for (const pref of PREFS) for (const solo of [false, true]) {
    const en = unknownHint(pref, solo);
    assert.notEqual(sv(en), en, `no Swedish for "${en}"`);
  }
  assert.equal(sv('Hidden while one period is shown alone.'), 'Döljs medan en period visas ensam.');
});

// stepUnknown in app.js eases uShowUnknown by the frame's length: up in UNKNOWN_IN_S, down in UNKNOWN_OUT_S.
test('the easing moves by the frame\'s length towards shown, and stays between 0 and 1', () => {
  assert.equal(easeShown(0, true, UNKNOWN_IN_S / 2), 0.5);
  assert.equal(easeShown(1, false, UNKNOWN_OUT_S / 4), 0.75);
  assert.equal(easeShown(0.9, true, 1), 1);
  assert.equal(easeShown(0.1, false, 1), 0);
  assert.equal(easeShown(1, true, 0.016), 1);
  assert.equal(easeShown(0, false, 0.016), 0);
});

test('a frame with a negative length (a clock set back) moves nothing, and never leaves 0 to 1 (review F2)', () => {
  // a fake clock (page.clock.install) can hand the first frame a time before the last real one
  for (const value of [0, 0.4, 1]) for (const shown of [true, false]) {
    assert.equal(easeShown(value, shown, -3), value, `${value} ${shown}`);
  }
  for (const dt of [-1e9, -1, 0, 0.016, 1, 1e9]) for (const shown of [true, false]) {
    const v = easeShown(0.5, shown, dt);
    assert.ok(v >= 0 && v <= 1, `${dt} ${shown}: ${v}`);
  }
});
