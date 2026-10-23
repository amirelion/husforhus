// Turn mode (brief 2026-10-23, approved by the owner, D66): a visitor wrote that it took a while to find out how to
// turn the map (⌘-drag), so the round button after north (index.html .turn-open, app.js Turn mode) and the T key give a
// way into it that shows. Pressed, a plain drag (one finger) turns and tilts the map, and a right-drag, a ⌘/Ctrl-drag
// or two fingers move it; not pressed, the map is as it always was. It is not remembered: every visit starts in move
// mode. The button's tooltip says what a press does now, on a mouse hover (title) and on keyboard focus (data-tip,
// styles.css), where a title shows nothing; its name stays "Turn the map" and aria-pressed carries the state. The hint
// under the map follows the mode (web/howto.js). Pure, so node --test can check it (web/test/turn.test.mjs);
// e2e/turn.spec.mjs covers the page.

// The key that switches it, named in the tooltip and in aria-keyshortcuts.
export const TURN_KEY = 'T';

// The controls' mouse buttons and touches in each mode, given three's MOUSE and TOUCH. Move mode is the map's own: the
// left button moves, the right one turns, one finger moves and two zoom and turn. Turn mode swaps the two buttons, and
// the fingers the same way: one finger turns, two zoom and move. OrbitControls swaps PAN and ROTATE itself while Ctrl,
// ⌘ or Shift is held, so with LEFT on ROTATE a ⌘-drag moves the map, as it turns it in move mode. A touch screen has no
// such key, so two fingers are its way to move the map in turn mode (MapControls keeps that move on the ground). The
// middle button (zoom) is the same in both.
export function controlsFor(on, { MOUSE, TOUCH }) {
  return {
    mouseButtons: { LEFT: on ? MOUSE.ROTATE : MOUSE.PAN, MIDDLE: MOUSE.DOLLY, RIGHT: on ? MOUSE.PAN : MOUSE.ROTATE },
    touches: { ONE: on ? TOUCH.ROTATE : TOUCH.PAN, TWO: on ? TOUCH.DOLLY_PAN : TOUCH.DOLLY_ROTATE },
  };
}

// The button's name and its tooltip by id in web/i18n. The tooltip says what a press does now, and the key.
export const LABEL_ID = 'ui.turn';
export const tipId = on => (on ? 'ui.turn.tip.on' : 'ui.turn.tip.off');
export const turnTitle = (T, on) => `${T(tipId(on))} (${TURN_KEY})`;
