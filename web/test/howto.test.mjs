import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { howto, isMac, HOWTO, HOWTO_TURN } from '../howto.js';
import { makeT, legacy } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));

// Reported 2026-10-15: Shift-drag does not turn the map on the owner's Mac, Cmd-drag does. OrbitControls turns on Ctrl,
// Cmd or Shift, but a real Shift-press is unreliable (the browser takes it for selection-extend, some shells for
// themselves), so the hint names only the keys that work everywhere: ⌘ on a Mac, Ctrl elsewhere.
test('the drag hint names ⌘ on a Mac and Ctrl elsewhere, never Shift', () => {
  const mac = 'Drag to move. Right-drag or ⌘-drag to turn. Scroll or press + / − to zoom.';
  const other = 'Drag to move. Right-drag or Ctrl-drag to turn. Scroll or press + / − to zoom.';
  assert.equal(howto({ userAgentData: { platform: 'macOS' }, platform: 'MacIntel' }), mac);
  assert.equal(howto({ platform: 'MacIntel' }), mac);                         // Safari and Firefox: no userAgentData
  assert.equal(howto({ userAgentData: { platform: 'Windows' }, platform: 'Win32' }), other);
  assert.equal(howto({ platform: 'Linux x86_64' }), other);
  assert.equal(howto({ userAgentData: { platform: '' }, platform: '' }), other);
  assert.equal(howto(undefined), other);
  assert.deepEqual([isMac({ platform: 'MacIntel' }), isMac({ platform: 'Win32' })], [true, false]);
  for (const text of Object.values(HOWTO)) assert.doesNotMatch(text, /shift/i);
});

// Turn mode (D66, web/turn.js): a plain drag turns and the same keys move, so the hint swaps the two verbs.
test('in turn mode the hint says a drag turns and a right-drag or ⌘/Ctrl-drag moves', () => {
  const mac = { userAgentData: { platform: 'macOS' }, platform: 'MacIntel' }, win = { platform: 'Win32' };
  assert.equal(howto(mac, true), 'Drag to turn. Right-drag or ⌘-drag to move. Scroll or press + / − to zoom.');
  assert.equal(howto(win, true), 'Drag to turn. Right-drag or Ctrl-drag to move. Scroll or press + / − to zoom.');
  assert.equal(howto(mac, false), HOWTO.mac);                                 // off is today's hint, word for word
  assert.equal(howto(win), HOWTO.other);
  for (const text of Object.values(HOWTO_TURN)) assert.doesNotMatch(text, /shift/i);
});

test('the page shows the hint the platform picks, with Swedish for both', () => {
  const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(app, /document\.querySelector\('\.howto'\)\.textContent = t\(howto\(navigator, turning\)\);/);
  assert.match(html, /<p class="howto">Drag to move\. Right-drag or Ctrl-drag to turn\. Scroll or press \+ \/ − to zoom\.<\/p>/);
  // The Swedish lines live in web/i18n, reached through web/i18n.js LEGACY
  const T = makeT({ en: load('en'), sv: load('sv') }, 'sv');
  assert.equal(legacy(T)(HOWTO.mac), 'Dra för att flytta. Högerdra eller ⌘-dra för att vrida. Scrolla eller tryck + / − för att zooma.');
  assert.equal(legacy(T)(HOWTO.other), 'Dra för att flytta. Högerdra eller Ctrl-dra för att vrida. Scrolla eller tryck + / − för att zooma.');
  assert.equal(legacy(T)(HOWTO_TURN.mac), 'Dra för att vrida. Högerdra eller ⌘-dra för att flytta. Scrolla eller tryck + / − för att zooma.');
  assert.equal(legacy(T)(HOWTO_TURN.other), 'Dra för att vrida. Högerdra eller Ctrl-dra för att flytta. Scrolla eller tryck + / − för att zooma.');
  assert.doesNotMatch(html + app, /Drag to move\. Shift-drag/);           // the old hint (comments may name Shift)
});
