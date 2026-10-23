import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { MOUSE, TOUCH } from '../vendor/three.module.js';
import { controlsFor, tipId, turnTitle, LABEL_ID, TURN_KEY } from '../turn.js';
import { makeT } from '../i18n.js';

// Turn mode (D66, brief 2026-10-23, approved by the owner): a visitor took a while to find ⌘-drag, so a button after
// north and the T key make a plain drag turn and tilt the map. Off, the controls are exactly what they always were.
const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const read = name => readFileSync(new URL(`../${name}`, import.meta.url), 'utf8');

test('off, the map moves as it always did: left-drag and one finger move, right-drag turns', () => {
  assert.deepEqual(controlsFor(false, { MOUSE, TOUCH }), {
    mouseButtons: { LEFT: MOUSE.PAN, MIDDLE: MOUSE.DOLLY, RIGHT: MOUSE.ROTATE },
    touches: { ONE: TOUCH.PAN, TWO: TOUCH.DOLLY_ROTATE },
  });
});

test('on, a left-drag and one finger turn, a right-drag and two fingers move; the wheel button is unchanged', () => {
  // OrbitControls swaps PAN and ROTATE while Ctrl, ⌘ or Shift is held (onMouseDown), so with LEFT on ROTATE a ⌘-drag
  // moves the map: the hint's "Right-drag or ⌘-drag to move" holds without code of our own. A touch screen has no such
  // key, so the fingers swap as the buttons do: two fingers zoom and move (OrbitControls' own default pairing), or a
  // phone in turn mode could not move the map at all.
  assert.deepEqual(controlsFor(true, { MOUSE, TOUCH }), {
    mouseButtons: { LEFT: MOUSE.ROTATE, MIDDLE: MOUSE.DOLLY, RIGHT: MOUSE.PAN },
    touches: { ONE: TOUCH.ROTATE, TWO: TOUCH.DOLLY_PAN },
  });
  const vendor = read('vendor/OrbitControls.js');
  assert.match(vendor, /case MOUSE\.ROTATE:\s*if \( event\.ctrlKey \|\| event\.metaKey \|\| event\.shiftKey \) \{[^}]*_handleMouseDownPan/);
  // A fresh object each time, so a caller can never change the other mode's table
  assert.notEqual(controlsFor(true, { MOUSE, TOUCH }).mouseButtons, controlsFor(true, { MOUSE, TOUCH }).mouseButtons);
});

test('the tooltip says what a press does now and names the key, in English and Swedish; the name stays the same', () => {
  const tables = { en: load('en'), sv: load('sv') };
  const en = makeT(tables, 'en'), sv = makeT(tables, 'sv');
  assert.equal(TURN_KEY, 'T');
  assert.deepEqual([tipId(false), tipId(true)], ['ui.turn.tip.off', 'ui.turn.tip.on']);
  assert.equal(turnTitle(en, false), 'Turn the map: press, then drag to turn and tilt (T)');
  assert.equal(turnTitle(en, true), 'Turning: drag turns the map. Press again to move it instead (T)');
  assert.equal(turnTitle(sv, false), 'Vrid kartan: tryck och dra sedan för att vrida och luta (T)');
  assert.equal(turnTitle(sv, true), 'Vrider: dra vrider kartan. Tryck igen för att flytta den i stället (T)');
  assert.equal(en(LABEL_ID), 'Turn the map');
  assert.equal(sv(LABEL_ID), 'Vrid kartan');
});

test('the page has the button after north, a toggle labelled by its id with the T key, styled as north is', () => {
  const html = read('index.html'), app = read('app.js'), css = read('styles.css');
  assert.match(html, /<button class="turn-open" aria-label="Turn the map" aria-pressed="false" title="Turn the map: press, then drag to turn and tilt \(T\)" aria-keyshortcuts="T" data-i18n-aria="ui\.turn">/);
  // Right after the north button in the corner's row
  const buttons = [...html.matchAll(/<button class="([\w-]+)"/g)].map(m => m[1]);
  assert.equal(buttons[buttons.indexOf('north-open') + 1], 'turn-open');
  // Not remembered: every visit starts in move mode, so no storage and no URL parameter
  const section = app.slice(app.indexOf('// ---------- Turn mode ----------'), app.indexOf('// + and - zoom'));
  assert.ok(section.length > 200, 'app.js has its Turn mode section');
  assert.doesNotMatch(section, /localStorage|sessionStorage|URLSearchParams|QUERY|history\./);
  assert.match(section, /let turning = false;/);
  assert.match(app, /Object\.assign\(controls, controlsFor\(false, THREE\)\);/);
  // T waits while the keys go to a field or a dialog, as P and N do, and where the button is out of sight: during a
  // story's warning (the story itself takes the key, scene-player.js) and in postcard mode
  assert.match(section, /e\.key === 't' \|\| e\.key === 'T'\) && !e\.ctrlKey && !e\.metaKey && !e\.altKey && !e\.repeat && !typingIn\(e\.target\)\s*&& !document\.body\.classList\.contains\('scene-on'\) && !postcard\.on\) setTurning\(!turning\);/);
  // The tooltip for keyboard focus is the title's text
  assert.match(section, /turnBtn\.title = tip;\s*turnBtn\.dataset\.tip = tip;/);
  // The same size, colours and touch band as north and the postcard; pressed, the selected EN | SV letters' fill
  assert.match(css, /\.north-open, \.turn-open, \.postcard-open \{ display: grid;[^}]*width: 28px; height: 28px;/);
  const chip = css.match(/\.lang button\[aria-pressed="true"\] \{ ([^}]*) \}/)[1];
  assert.equal(css.match(/\.turn-open\[aria-pressed="true"\] \{ ([^}]*) \}/)[1], chip);
  assert.match(css, /\.north-open::after, \.turn-open::after, \.postcard-open::after, \.search-open::after \{ inset: -8px; \}/);
  // Keyboard focus shows the tooltip from data-tip, on ::before since ::after is the touch band
  assert.match(css, /\.turn-open:focus-visible::before \{ content: attr\(data-tip\);/);
  // In forced colours the pressed button and the EN | SV letters take the system's highlight
  assert.match(css, /@media \(forced-colors: active\) \{\s*\.turn-open\[aria-pressed="true"\], \.lang button\[aria-pressed="true"\] \{ forced-color-adjust: none; background: Highlight;\s*color: HighlightText; \}/);
});
