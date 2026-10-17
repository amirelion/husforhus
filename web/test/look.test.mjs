import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createLooks, initialLook, LOOK_KEY, DEFAULT_LOOK } from '../look.js';
import { THEMES } from '../themes.js';

// A page for the look manager: its URL, its history and its localStorage, all in memory.
function page(href = 'https://husforhus.se/', stored) {
  const location = new URL(href);
  const history = { replaceState(_state, _title, url) { location.href = String(url); } };
  const data = new Map(stored === undefined ? [] : [[LOOK_KEY, stored]]);
  const storage = { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)) };
  return { location, history, storage, data };
}
// localStorage throws in some private windows and with blocked site data.
const broken = { getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('QuotaExceededError'); } };

test('the default look is Ärg (D28)', () => {
  assert.equal(DEFAULT_LOOK, 'arg');
  assert.ok(THEMES[DEFAULT_LOOK]);
});

// Contract C1: pipeline/city.py's PERIODS colours are the default look's, so the pipeline's stockholm.json and
// the viewer's first paint agree.
test("city.py's PERIODS colours are the default look's period colours (C1)", () => {
  const py = readFileSync(new URL('../../pipeline/city.py', import.meta.url), 'utf8');
  const block = py.slice(py.indexOf('PERIODS = ['), py.indexOf(']', py.indexOf('PERIODS = [') + 12));
  const colours = [...block.matchAll(/^\s*\("p\d+",.*"(#[0-9a-f]{6})"\),$/gm)].map(m => m[1]);
  assert.equal(colours.length, 12);
  assert.deepEqual(colours, THEMES[DEFAULT_LOOK].periods);
});

test('the first look: ?theme= wins, then the remembered choice, then Ärg', () => {
  assert.equal(initialLook('?theme=kalk', 'arg'), 'kalk');
  assert.equal(initialLook('?debug=1&theme=blatimme', null), 'blatimme');
  assert.equal(initialLook('', 'paper'), 'paper');
  assert.equal(initialLook('?lang=sv', null), 'arg');
  assert.equal(initialLook('', null), 'arg');
});

test('unknown names fall back: a dropped look in the URL or in storage is ignored', () => {
  assert.equal(initialLook('?theme=night', 'kalk'), 'kalk');
  assert.equal(initialLook('?theme=__proto__', null), 'arg');
  assert.equal(initialLook('?theme=', 'nordic'), 'arg');
  assert.equal(initialLook('', 'toString'), 'arg');
});

test('the manager starts on the look the page asks for', () => {
  assert.equal(createLooks(page('https://husforhus.se/?theme=kalk', 'paper')).current, 'kalk');
  assert.equal(createLooks(page('https://husforhus.se/', 'paper')).current, 'paper');
  assert.equal(createLooks(page()).current, 'arg');
});

test('every look in web/themes.js, by its shown name; paper is "Classic"', () => {
  const looks = createLooks(page());
  assert.deepEqual(looks.items.map(l => [l.id, l.name]),
    [['arg', 'Ärg'], ['kalk', 'Kalkfärg'], ['blatimme', 'Blå timmen'], ['paper', 'Classic']]);
});

test('switching notifies subscribers, remembers the choice and puts it in the URL, keeping the other parameters', () => {
  const p = page('https://husforhus.se/?debug=1&lang=sv');
  const looks = createLooks(p);
  const heard = [];
  looks.subscribe((id, was) => heard.push([id, was]));
  assert.equal(looks.set('blatimme'), true);
  assert.equal(looks.current, 'blatimme');
  assert.deepEqual(heard, [['blatimme', 'arg']]);
  assert.equal(p.data.get(LOOK_KEY), 'blatimme');
  assert.equal(p.location.href, 'https://husforhus.se/?debug=1&lang=sv&theme=blatimme');
  looks.set('paper');
  assert.equal(p.location.href, 'https://husforhus.se/?debug=1&lang=sv&theme=paper'); // replaced, not added twice
  assert.deepEqual(heard, [['blatimme', 'arg'], ['paper', 'blatimme']]);
});

test('an unknown look or the current one changes nothing', () => {
  const p = page('https://husforhus.se/?theme=kalk');
  const looks = createLooks(p);
  let heard = 0;
  looks.subscribe(() => heard++);
  assert.equal(looks.set('night'), false);
  assert.equal(looks.set('kalk'), false);
  assert.equal(looks.current, 'kalk');
  assert.equal(heard, 0);
  assert.equal(p.data.has(LOOK_KEY), false);
});

test('an unsubscribed listener hears nothing more', () => {
  const looks = createLooks(page());
  let heard = 0;
  const off = looks.subscribe(() => heard++);
  looks.set('kalk');
  off();
  looks.set('paper');
  assert.equal(heard, 1);
});

test('storage that throws does not break the looks', () => {
  const p = { ...page('https://husforhus.se/?theme=paper'), storage: broken };
  const looks = createLooks(p);
  assert.equal(looks.current, 'paper');
  let heard = 0;
  looks.subscribe(() => heard++);
  assert.equal(looks.set('kalk'), true);
  assert.equal(heard, 1);
  assert.equal(p.location.href, 'https://husforhus.se/?theme=kalk');
  assert.equal(createLooks({ ...page(), storage: broken }).current, 'arg');
  assert.equal(createLooks({ ...page(), storage: null }).current, 'arg');
});

test('atmospheres: only "none" for now, and an effect is started and stopped as it is switched', () => {
  const looks = createLooks(page());
  const atmos = looks.atmospheres;
  assert.deepEqual(atmos.items.map(a => a.id), ['none']);
  assert.equal(atmos.current, 'none');
  const calls = [];
  atmos.context = { scene: 'the scene' };
  atmos.add({ id: 'snow', name: 'Snow', start: ctx => calls.push(['start', ctx.scene]), stop: () => calls.push(['stop']) });
  const heard = [];
  atmos.subscribe(id => heard.push(id));
  assert.equal(atmos.set('snow'), true);
  assert.equal(atmos.set('rain'), false);
  assert.equal(atmos.set('none'), true);
  assert.deepEqual(calls, [['start', 'the scene'], ['stop']]);
  assert.deepEqual(heard, ['snow', 'none']);
  assert.equal(looks.current, 'arg'); // the look is a separate choice
});
