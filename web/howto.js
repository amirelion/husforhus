// The drag hint under the map (index.html .howto, set by app.js applyStaticText and by turn mode). OrbitControls turns
// the map on a left-drag with Ctrl, Cmd or Shift held, but a real Shift-drag is unreliable (the browser takes a
// Shift-press for selection-extend, some browser shells take Shift-drag for themselves), so the hint names only the keys
// that work everywhere: ⌘ on a Mac, Ctrl elsewhere. In turn mode (web/turn.js) a plain drag turns and the same keys
// move, so it has its own two lines. Pure, so node --test can check it (web/test/howto.test.mjs); app.js translates it
// with t().
export const HOWTO = {
  mac: 'Drag to move. Right-drag or ⌘-drag to turn. Scroll or press + / − to zoom.',
  other: 'Drag to move. Right-drag or Ctrl-drag to turn. Scroll or press + / − to zoom.',
};
export const HOWTO_TURN = {
  mac: 'Drag to turn. Right-drag or ⌘-drag to move. Scroll or press + / − to zoom.',
  other: 'Drag to turn. Right-drag or Ctrl-drag to move. Scroll or press + / − to zoom.',
};

// userAgentData.platform reads "macOS" (Chromium); Safari and Firefox have only navigator.platform, "MacIntel".
export const isMac = nav => /mac/i.test(nav?.userAgentData?.platform || nav?.platform || '');

export const howto = (nav, turning = false) => (turning ? HOWTO_TURN : HOWTO)[isMac(nav) ? 'mac' : 'other'];
