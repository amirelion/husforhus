// A boat's tooltip (asked for on 2026-10-20: which line it is, where from and where to): which line, where it goes
// and which way this boat is heading, as web/ferries.js boatInfo words it. With a mouse it follows the pointer while a
// boat is under it (hover); on a touch screen a tap on a boat shows it (tap), as the building card's sheet on a phone
// (styles.css .card) and beside the boat elsewhere, following it, until a tap on it or somewhere else, a card pinned
// any way (app.js pinCard, pinStation), the boat sailing off the screen or out of sight, or the boats hiding (app.js
// stepBoatTip).
// A tapped one takes taps (the class tapped, styles.css), and a tap on it lets it go: on a phone its sheet lies over the
// modes and the timeline, and elsewhere over the map beside the boat, which would otherwise take that tap (a mode, a
// year, the building under it). A hovered one never does, as the hover card: the pointer is on the map.
// It is for pointer users: aria-hidden and never focused, so it traps nothing; a screen reader has About's line on the
// boats. It never animates. app.js finds the boat (web/ferries-layer.js hitAt) and calls hover, tap, follow and hide;
// covered by e2e/ferries.spec.mjs.

const GAP = 16;     // pixels between the pointer (or the boat) and the tooltip
const EDGE = 12;    // pixels kept clear of the window's edges

// el: the tooltip's element; html(boat): its content for a boat ({route, toward, ...}, ferries-layer.js boatOf).
export function mountBoatTip(el, { html }) {
  let shown = null;   // {k, mode: 'hover' | 'tap'} while it shows
  let drawn = '';
  function draw(boat) {
    const h = html(boat);
    if (h !== drawn) { el.innerHTML = h; drawn = h; }
  }
  // Beside (x, y), below and to the right, else where it fits; a phone's sheet ignores this (styles.css).
  function place(x, y) {
    const r = el.getBoundingClientRect();
    const left = Math.max(EDGE, Math.min(x + GAP, innerWidth - r.width - EDGE));
    const top = y + GAP + r.height <= innerHeight - EDGE ? y + GAP : Math.max(EDGE, y - GAP - r.height);
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
  }
  function show(boat, mode, x, y) {
    shown = { k: boat.k, mode };
    el.classList.toggle('tapped', mode === 'tap');
    draw(boat);
    el.hidden = false;
    place(x, y);
  }
  const api = {
    // a tapped boat hovered stays tapped, so the pointer leaving it does not hide what the tap showed
    hover: (boat, x, y) => show(boat, shown?.mode === 'tap' && shown.k === boat.k ? 'tap' : 'hover', x, y),
    tap: (boat, x, y) => show(boat, 'tap', x, y),
    // a tapped boat as it is now, its middle at `at` on the screen: the text follows its direction, the tooltip it
    follow(boat, at) {
      if (!shown || shown.k !== boat.k) return;
      draw(boat);
      place(at[0], at[1]);
    },
    // hide(), or hide('hover') / hide('tap') to hide it only when it shows that way
    hide(mode) {
      if (!shown || (mode && shown.mode !== mode)) return;
      shown = null;
      el.hidden = true;
      el.classList.remove('tapped');
    },
    get shown() { return shown && { ...shown }; },
  };
  // On click, the last event of a tap, so no part of the tap is left to reach what lies under it once it hides.
  el.addEventListener('click', () => api.hide());
  return api;
}
