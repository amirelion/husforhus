import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// scripts/look.mjs renders the M3 review set: a bad --looks, --views or --estimates value must stop
// it with a clear message and a usage exit code before Playwright loads and before the out folder is created, never
// render the wrong set under the right file names. It runs from a copy of the script, web/themes.js and web/relief.js
// (the Hills slider's range) in a temp folder with no node_modules above it, as CI's offline job runs (no npm ci;
// a review found), so a static Playwright import would fail these tests. The URL points at a closed port. Each
// run removes its temp folder.
const SCRIPT = fileURLToPath(new URL('../../scripts/look.mjs', import.meta.url));
const THEMES = fileURLToPath(new URL('../themes.js', import.meta.url));
const RELIEF = fileURLToPath(new URL('../relief.js', import.meta.url));
// scripts/lib (the terrain wait) holds no Playwright import, so the temp copies carry it along.
const LIB = fileURLToPath(new URL('../../scripts/lib', import.meta.url));

// The environment of a script's run: the caller's, without its HFH_PORT unless the test sets one.
function runEnv(env) {
  const e = { ...process.env, ...env };
  if (!('HFH_PORT' in env)) delete e.HFH_PORT;
  return e;
}

// A leading object is the run's extra environment (HFH_PORT); without a --url of its own the run gets the closed port.
function look(...args) {
  const env = typeof args[0] === 'object' ? args.shift() : {};
  const root = mkdtempSync(join(tmpdir(), 'hfh-look-'));
  try {
    mkdirSync(join(root, 'scripts'));
    mkdirSync(join(root, 'web'));
    copyFileSync(SCRIPT, join(root, 'scripts', 'look.mjs'));
    cpSync(LIB, join(root, 'scripts', 'lib'), { recursive: true });
    copyFileSync(THEMES, join(root, 'web', 'themes.js'));
    copyFileSync(RELIEF, join(root, 'web', 'relief.js'));
    const out = join(root, 'never');
    const url = args.includes('--url') ? [] : ['--url', 'http://127.0.0.1:9/'];
    const r = spawnSync(process.execPath, [join(root, 'scripts', 'look.mjs'), ...url, '--out', out,
      ...args], { encoding: 'utf8', timeout: 60_000, env: runEnv(env) });
    return { ...r, outCreated: existsSync(out) };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test('look.mjs refuses an unknown view before Playwright loads or the out folder exists', () => {
  const r = look('--looks', 'arg', '--views', 'hero,nowhere');
  assert.equal(r.status, 2, r.stderr);
  assert.match(r.stderr,
    /look\.mjs: unknown view "nowhere" \(known: hero, overview, far, gamlastan, cliffs, soder, south, quays, shore, lakes, edge-east, edge-ne, streets, pond, crater, pedestals-hasselby, pedestals-soder\)/);
  assert.equal(r.outCreated, false);
});

test('look.mjs refuses an --estimates value other than shown or hidden', () => {
  const r = look('--looks', 'arg', '--views', 'hero', '--estimates', 'hide');
  assert.equal(r.status, 2, r.stderr);
  assert.match(r.stderr, /look\.mjs: --estimates must be shown or hidden, not "hide"/);
  assert.equal(r.outCreated, false);
});

test('look.mjs refuses an unknown look', () => {
  const r = look('--looks', 'arg,neon', '--views', 'hero');
  assert.equal(r.status, 2, r.stderr);
  assert.match(r.stderr, /look\.mjs: unknown look "neon" \(known: /);
  assert.equal(r.outCreated, false);
});

test('look.mjs refuses an option given without its value', () => {
  for (const flag of ['--views', '--looks', '--estimates', '--variants', '--devices', '--legend']) {
    const r = look(flag);
    assert.equal(r.status, 2, `${flag}: ${r.stderr}`);
    assert.match(r.stderr, new RegExp(`look\\.mjs: ${flag} needs a value`));
    assert.doesNotMatch(r.stderr, /TypeError/);
    assert.equal(r.outCreated, false);
  }
  const r = look('--views', '--looks', 'arg');      // the next flag is not a value
  assert.equal(r.status, 2);
  assert.match(r.stderr, /look\.mjs: --views needs a value/);
});

// A name every object has (constructor, __proto__, toString) is no look, view, device or
// variant setting: refused with the usage exit code, never taken for one.
test('look.mjs refuses an inherited name as a look, view, device or variant setting', () => {
  for (const [args, message] of [
    [['--looks', 'constructor', '--views', 'hero'], /unknown look "constructor"/],
    [['--looks', 'arg', '--views', '__proto__'], /unknown view "__proto__"/],
    [['--looks', 'arg', '--views', 'hero', '--devices', 'toString'], /unknown device "toString"/],
    [['--looks', 'arg', '--views', 'hero', '--variants', 'constructor=1'], /unknown variant setting "constructor"/],
    [['--looks', 'arg', '--views', 'hero', '--variants', '__proto__=1'], /unknown variant setting "__proto__"/],
  ]) {
    const r = look(...args);
    assert.equal(r.status, 2, `${args.join(' ')}: ${r.stderr}`);
    assert.match(r.stderr, message);
    assert.doesNotMatch(r.stderr, /TypeError/);
    assert.equal(r.outCreated, false);
  }
});

test('look.mjs refuses an unknown device', () => {
  const r = look('--looks', 'arg', '--views', 'hero', '--devices', 'desktop,tablet');
  assert.equal(r.status, 2, r.stderr);
  assert.match(r.stderr, /look\.mjs: unknown device "tablet" \(known: desktop, phone\)/);
  assert.equal(r.outCreated, false);
});

// scripts/sheet.mjs lays screenshots side by side for the M4 review: a bad call stops before Playwright loads
// and before the out folder exists. Like look(), it runs from a temp copy with no node_modules above it, as in CI.
const SHEET = fileURLToPath(new URL('../../scripts/sheet.mjs', import.meta.url));

function sheet(...args) {
  const root = mkdtempSync(join(tmpdir(), 'hfh-sheet-'));
  try {
    mkdirSync(join(root, 'scripts'));
    copyFileSync(SHEET, join(root, 'scripts', 'sheet.mjs'));
    const dir = join(root, 'never');
    const r = spawnSync(process.execPath, [join(root, 'scripts', 'sheet.mjs'),
      ...args.map(a => a.replace('<out>', join(dir, 'sheet.png')))], { encoding: 'utf8', timeout: 60_000 });
    return { ...r, outCreated: existsSync(dir) };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test('sheet.mjs needs --out with a value, at least one screenshot, and files that exist', () => {
  for (const [args, message] of [
    [['a.png'], /sheet\.mjs: --out is required/],
    [['a.png', '--out'], /sheet\.mjs: --out needs a value/],
    [['--out', '<out>'], /sheet\.mjs: no screenshots given/],
    [['--out', '<out>', '/nowhere/hero.png=Flat'], /sheet\.mjs: no such file: \/nowhere\/hero\.png/],
  ]) {
    const r = sheet(...args);
    assert.equal(r.status, 2, `${args.join(' ')}: ${r.stderr}`);
    assert.match(r.stderr, message);
    assert.equal(r.outCreated, false);
  }
});

// scripts/look.mjs and scripts/measure.mjs read HFH_PORT as playwright.config.mjs does (Number(HFH_PORT) || 8653) and
// never aim at 8642, the owner's preview of the main checkout: HFH_PORT=8642 or a --url on
// 8642 stops them with exit code 2 and Playwright's message, before Playwright loads. measure.mjs runs from a temp copy
// with no node_modules above it, like look().
const MEASURE = fileURLToPath(new URL('../../scripts/measure.mjs', import.meta.url));

function measure(env, ...args) {
  const root = mkdtempSync(join(tmpdir(), 'hfh-measure-'));
  try {
    mkdirSync(join(root, 'scripts'));
    copyFileSync(MEASURE, join(root, 'scripts', 'measure.mjs'));
    cpSync(LIB, join(root, 'scripts', 'lib'), { recursive: true });
    return spawnSync(process.execPath, [join(root, 'scripts', 'measure.mjs'), ...args],
      { encoding: 'utf8', timeout: 60_000, env: runEnv(env) });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test('look.mjs and measure.mjs never aim at 8642, from HFH_PORT or --url', () => {
  for (const [name, r] of [
    ['look', look({ HFH_PORT: '8642' }, '--looks', 'arg', '--views', 'hero')],
    ['measure', measure({ HFH_PORT: '8642' })],
  ]) {
    assert.equal(r.status, 2, `${name}: ${r.stderr}`);
    assert.match(r.stderr, new RegExp(`${name}\\.mjs: 8642 is the preview server of the main checkout: pick another HFH_PORT`));
    assert.equal(r.outCreated ?? false, false);
  }
  for (const [name, r] of [
    ['look', look('--url', 'http://localhost:8642/', '--looks', 'arg', '--views', 'hero')],
    ['measure', measure({}, '--url', 'http://127.0.0.1:8642/')],
  ]) {
    assert.equal(r.status, 2, `${name}: ${r.stderr}`);
    assert.match(r.stderr, new RegExp(`${name}\\.mjs: 8642 is the preview server of the main checkout: pick another --url`));
    assert.equal(r.outCreated ?? false, false);
  }
  const r = look('--url', 'localhost 8653', '--looks', 'arg', '--views', 'hero');
  assert.equal(r.status, 2, r.stderr);
  assert.match(r.stderr, /look\.mjs: --url is not a URL: "localhost 8653"/);
  assert.doesNotMatch(r.stderr, /TypeError/);
});

// --variants takes only the settings web/app.js reads, with values it accepts, so a typo
// never renders the default map under a variant's file name. A bad one stops the run before Playwright loads.
test('look.mjs refuses a variant setting it does not know, or a value web/app.js would not take', () => {
  for (const [variants, message] of [
    ['relief=on,shadows=1', /look\.mjs: unknown variant setting "shadows" in "shadows=1" \(known: relief, terrace, fade, edgebuildings, labels\)/],
    ['relief', /look\.mjs: variant "relief": relief must be off, on or 0 to 2\.5 in steps of 0\.5, not ""/],
    ['relief=5', /look\.mjs: variant "relief=5": relief must be off, on or 0 to 2\.5 in steps of 0\.5, not "5"/],
    ['relief=3', /relief must be off, on or 0 to 2\.5 in steps of 0\.5, not "3"/],     // the Hills slider's top is 2.5
    ['relief=2.6', /relief must be off, on or 0 to 2\.5 in steps of 0\.5, not "2\.6"/],
    ['relief=-1', /relief must be off, on or 0 to 2\.5 in steps of 0\.5, not "-1"/],
    ['relief=1e0', /relief must be off, on or 0 to 2\.5 in steps of 0\.5, not "1e0"/],
    ['relief=1.2', /relief must be off, on or 0 to 2\.5 in steps of 0\.5, not "1\.2"/],   // off the slider's step
    ['relief=0.25', /in steps of 0\.5, not "0\.25"/],
    ['terrace=half', /look\.mjs: variant "terrace=half": terrace must be full, true or none, not "half"/],
    ['fade=6000', /fade must be a number of metres from 0 to 5000, not "6000"/],
    ['fade=-1', /fade must be a number of metres from 0 to 5000, not "-1"/],
    ['edgebuildings=yes', /edgebuildings must be on, off, 1 or 0, not "yes"/],
    ['labels=bottom', /labels must be top, not "bottom"/],
    ['relief=on&relief=off', /look\.mjs: variant "relief=on&relief=off" sets relief twice/],
  ]) {
    const r = look('--looks', 'arg', '--views', 'hero', '--variants', variants);
    assert.equal(r.status, 2, `${variants}: ${r.stderr}`);
    assert.match(r.stderr, message);
    assert.equal(r.outCreated, false);
  }
});

test('look.mjs takes every variant web/app.js reads, and an empty one for the plain map', () => {
  const r = look('--looks', 'arg', '--views', 'hero', '--variants', ',relief=off,relief=on,relief=0,relief=0.5,relief=1,relief=1.5,relief=2.0,relief=2.5,' +
    'relief=2.5&terrace=none,terrace=full,terrace=true,fade=0,fade=800,fade=5000,edgebuildings=1,edgebuildings=0,' +
    'edgebuildings=on,edgebuildings=off,labels=top');
  assert.doesNotMatch(r.stderr, /look\.mjs:/);
  assert.match(r.stderr, /Cannot find package '@playwright\/test'/);   // past every check: the temp copy has no node_modules
});

// The legend covers the left of a desktop frame: look.mjs folds it for the terrain views unless --legend open.
test('look.mjs takes --legend auto or open only', () => {
  const r = look('--looks', 'arg', '--views', 'hero', '--legend', 'shut');
  assert.equal(r.status, 2, r.stderr);
  assert.match(r.stderr, /look\.mjs: --legend must be auto or open, not "shut"/);
  assert.equal(r.outCreated, false);
});

test('sheet.mjs refuses a folder given as a screenshot', () => {
  const r = sheet('--out', '<out>', tmpdir());
  assert.equal(r.status, 2, r.stderr);
  assert.match(r.stderr, /sheet\.mjs: not a file: /);
  assert.doesNotMatch(r.stderr, /EISDIR/);
  assert.equal(r.outCreated, false);
});

// scripts/compare-tiles.sh runs measure.mjs, which refuses 8642: its default URL follows HFH_PORT as the scripts do.
test('compare-tiles.sh aims measure.mjs at HFH_PORT (default 8653), never at 8642', () => {
  const sh = readFileSync(fileURLToPath(new URL('../../scripts/compare-tiles.sh', import.meta.url)), 'utf8');
  assert.match(sh, /^URL="\$\{HFH_URL:-http:\/\/127\.0\.0\.1:\$\{HFH_PORT:-8653\}\/\}"$/m);
  assert.doesNotMatch(sh.replace(/^\s*#.*$/gm, ''), /8642/);    // no command names 8642
  assert.doesNotMatch(sh, /serve\.py 8642/);
});

// scripts/lib/terrain-wait.mjs (fix round 1): the wait both scripts use. terrainStatus is passed to Playwright's
// waitForFunction and evaluate, so it must be self-contained; here it runs against a fake window.__dbg, as the page
// reports it (web/app.js: terrain() and relief). Imported when a test runs, so a missing file fails only these tests.
// The wait is done when the terrain stands or has failed (final: the map stays flat); a failure then stops the run at
// once, never after the 60 s a terrain still loading gets.
const terrainLib = () => import('../../scripts/lib/terrain-wait.mjs');
function fakeDbg(t, relief) { globalThis.window = { __dbg: { terrain: () => t, relief } }; }
// window.__dbg.relief: the relief asked for, a number (0 is flat; the Hills slider)
const ON = 2.5, OFF = 0;

test('terrainStatus: the wait is done when the terrain stands at the relief asked for, has none, or has failed', async () => {
  const { terrainStatus } = await terrainLib();
  const serialised = new Function(`return (${terrainStatus})`)();     // as Playwright sends it: no module scope
  try {
    for (const [what, t, relief, done, stands] of [
      ['ready and risen', { source: 'contours', state: 'ready', relief: 2.5 }, ON, true, true],
      ['ready, still rising', { source: 'contours', state: 'ready', relief: 1.2 }, ON, false, false],
      ['ready, flat as asked', { source: 'dtm', state: 'ready', relief: 0 }, OFF, true, true],
      ['loading', { source: 'contours', state: 'loading', relief: 0 }, ON, false, false],
      ['failed: done at once, but the map is flat', { source: 'contours', state: 'failed', relief: 0 }, ON, true, false],
      ['failed, though flat was asked', { source: 'contours', state: 'failed', relief: 0 }, OFF, true, false],
      ['no terrain in this build', { source: undefined, state: 'flat', relief: 0 }, 0, true, true],
    ]) {
      fakeDbg(t, relief);
      assert.equal(terrainStatus(true), done, what);
      assert.equal(serialised(true), done, what);
      assert.equal(terrainStatus().stands, stands, what);
    }
    fakeDbg({ source: 'contours', state: 'failed', relief: 0 }, ON);
    assert.deepEqual(terrainStatus(), { source: 'contours', state: 'failed', relief: 0, wanted: 2.5, stands: false });
    fakeDbg({ source: undefined, state: 'flat', relief: 0 }, 0);
    assert.deepEqual(serialised(), { source: null, state: 'flat', relief: 0, wanted: 0, stands: true });
  } finally {
    delete globalThis.window;
  }
});

test('waitForTerrain stops at once on a failed terrain, names the state on a timeout, passes other errors on', async () => {
  const { waitForTerrain } = await terrainLib();
  const page = fail => ({
    waitForFunction: async (fn, arg) => { if (fail) throw fail; assert.equal(fn(arg), true); },
    evaluate: async (fn, arg) => fn(arg),
  });
  const timeout = Object.assign(new Error('page.waitForFunction: Timeout 60000ms exceeded.'), { name: 'TimeoutError' });
  try {
    fakeDbg({ source: 'contours', state: 'failed', relief: 0 }, ON);
    await assert.rejects(waitForTerrain(page(null), 'arg desktop relief=on'),
      { message: 'terrain failed to load (arg desktop relief=on)' });
    fakeDbg({ source: 'contours', state: 'loading', relief: 0 }, ON);
    await assert.rejects(waitForTerrain(page(timeout), 'arg desktop relief=on'),
      { message: 'terrain did not stand in 60 s (arg desktop relief=on: state=loading, relief=0, wanted=2.5)' });
    fakeDbg({ source: 'contours', state: 'ready', relief: 1.23456 }, ON);
    await assert.rejects(waitForTerrain(page(timeout), 'arg phone', 5000),
      { message: 'terrain did not stand in 5 s (arg phone: state=ready, relief=1.23, wanted=2.5)' });
    const closed = new Error('Target page, context or browser has been closed');
    await assert.rejects(waitForTerrain(page(closed), 'arg desktop'), closed);
    fakeDbg({ source: 'contours', state: 'ready', relief: 2.5 }, ON);
    assert.deepEqual(await waitForTerrain(page(null), 'arg desktop'),
      { source: 'contours', state: 'ready', relief: 2.5, wanted: 2.5, stands: true });
  } finally {
    delete globalThis.window;
  }
});

test('pageProblem: console errors and terrain warnings count; other warnings and logs do not', async () => {
  const { pageProblem } = await terrainLib();
  assert.equal(pageProblem('error', 'Failed to load resource'), true);
  assert.equal(pageProblem('warning', 'The terrain did not load; the map stays flat. Error: …'), true);
  assert.equal(pageProblem('warning', 'The font Inter did not load; labels use the fallback'), false);
  assert.equal(pageProblem('log', 'terrain ready'), false);
});
