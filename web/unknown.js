// Buildings without a known year (yflag 7 UNKNOWN). Pure, so it can be tested without a browser. app.js eases the
// map towards what unknownShown says (uShowUnknown), and the legend's "Year unknown" row has a switch, "Show", that
// always reads what the map does now. The count takes them in where they are drawn, and only at "Today"
// (web/count.js).

// The visitor's choice (revised the same day): 'auto' until the switch is flipped (on at "Today", off in the
// past), then 'show' or 'hide' at every year. Kept per device in localStorage under UNKNOWN_KEY: 'show' or 'hide';
// automatic is nothing stored. Only clearing the site's storage brings 'auto' back.
export const UNKNOWN_KEY = 'hfh-unknown';

// What a stored value means. The first switch ("Show at every year") stored 'always' when on, which is 'show' now,
// and 'today' when off, which was the automatic rule.
export function storedPref(stored) {
  if (stored === 'show' || stored === 'always') return 'show';
  if (stored === 'hide') return 'hide';
  return 'auto';
}

// The choice on this device. storage() returns localStorage: the accessor itself can throw (blocked site data), as
// can every call, and then it is automatic. The first switch's values are rewritten on the way: 'always' as 'show',
// 'today' removed.
export function readPref(storage) {
  let stored = null;
  try {
    const s = storage();
    stored = s.getItem(UNKNOWN_KEY);
    if (stored === 'always') s.setItem(UNKNOWN_KEY, 'show');
    else if (stored === 'today') s.removeItem(UNKNOWN_KEY);
  } catch {}
  return storedPref(stored);
}
export function writePref(storage, pref) {
  try { storage().setItem(UNKNOWN_KEY, pref); } catch {}
}

// A click on the switch turns off what is on now and turns on what is off: shown → 'hide', hidden → 'show'. With a
// period shown alone the switch is off and disabled, and the choice stays as it was.
export function prefAfterClick({ shown, solo = false, pref }) {
  if (solo) return pref;
  return shown ? 'hide' : 'show';
}

// Are they drawn? solo (a period shown alone in the legend) hides them, as it hides every other period. A choice
// holds at every year. Left alone ('auto') they stand at "Today": the to-handle at the end of the timeline (end:
// config.yearMax), the from-handle at rest before the oldest building (start: config.yearMin; `from` rounded as the
// title rounds it, web/count.js tallyTitle), and the film not playing. So they leave whenever the map shows the past:
// during Play, with the timeline dragged back, or with the from-handle moved; a film that ends at "Today" brings them
// back. The legend's switch reads this, so it is on exactly when they are drawn.
export function unknownShown({ from, to, start, end, playing = false, pref = 'auto', solo = false }) {
  if (solo) return false;
  if (pref === 'show') return true;
  if (pref === 'hide') return false;
  return !playing && to >= end && Math.round(from) < start;
}

// The hint after the legend's note (app.js puts it through t()): what the automatic rule does, or, once the visitor
// has flipped the switch, that the choice stays. With a period shown alone the switch reads off and is disabled, and
// the hint says why, whatever the choice is.
export function unknownHint(pref, solo = false) {
  if (solo) return 'Hidden while one period is shown alone.';
  return pref === 'auto' ? 'Shown at “Today”, hidden in the past.' : 'Your choice is remembered.';
}

// How far they stand after a frame of dt seconds, eased towards shown: they rise in UNKNOWN_IN_S (a context layer's
// own 0.88 s) and sink in UNKNOWN_OUT_S, so the film starts on an empty city. app.js stepUnknown sets uShowUnknown.
// A frame that runs backwards (a clock set back, as a test's fake clock can) moves nothing, and the result stays
// between 0 and 1.
export const UNKNOWN_IN_S = 0.88, UNKNOWN_OUT_S = 0.5;
export function easeShown(value, shown, dt) {
  const step = Math.max(0, dt);
  return Math.min(1, Math.max(0, shown ? value + step / UNKNOWN_IN_S : value - step / UNKNOWN_OUT_S));
}
