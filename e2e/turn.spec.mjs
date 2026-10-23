// Turn mode (D66, web/turn.js): the orbit button after north, or T, makes a plain drag turn and tilt the map. The button
// is a toggle (aria-pressed) whose tooltip says what a press does now, in English and Swedish, on a mouse hover and on
// keyboard focus, and whose name stays the same; T does nothing while the keys go to the search field; the hint under
// the map follows the mode; nothing is remembered. A drag in turn mode turns the camera round the place it looks at and
// leaves that place where it is; a right-drag or a ⌘/Ctrl-drag moves it, and in move mode a drag moves it, as before.
// On a touch screen one finger turns and two fingers move. The button steps aside with the corner in postcard mode and
// in a story, whose camera still works, T waits there, and the button comes back pressed. At 390, 375, 340 and 320 px
// wide the corner's row stays inside the gutters and the button takes taps in 44 px; at 768 px the search pill leaves
// the row alone. Forced colours mark the pressed button. Each look and size is saved to data/shots-turn/ for review
// (light: Ärg, dark: Blå timmen).
import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { settled } from './settled.mjs';

const TURN = '.turn-open';
const SHOTS = 'data/shots-turn';
const SV = JSON.parse(readFileSync(new URL('../web/i18n/sv.json', import.meta.url), 'utf8'));
// The key that makes a left-drag do the other thing: ⌘ on a Mac (Ctrl-click is a right-click there), Ctrl elsewhere.
const MOD = process.platform === 'darwin' ? 'Meta' : 'Control';

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}
// The stories are on in this page's copy of the config, whichever way a build ships them.
const scenesOn = page => page.route('**/stockholm.json', async route => {
  const r = await route.fetch(), config = await r.json();
  config.features = { ...config.features, scenes: true };
  await route.fulfill({ response: r, json: config });
});
async function open(page, query = '') {
  await page.goto('/' + query);
  await settled(page);
  // Boats and weather stand still, so only the drags move the view
  await page.evaluate(() => { window.__dbg.ferries?.freeze(0); window.__dbg.pauseEffects(true); });
}
const view = page => page.evaluate(() => {
  const c = window.__dbg.controls;
  return { az: c.getAzimuthalAngle(), polar: c.getPolarAngle(), target: c.target.toArray() };
});
// The view once the drag's glide (damping, which only ever shrinks) and the target's ride on the ground have all but
// stopped: a quarter of a second apart, under a ten-thousandth of a radian and a millimetre.
async function still(page) {
  let was = await view(page);
  await expect.poll(async () => {
    await page.waitForTimeout(250);
    const now = await view(page);
    const moved = Math.max(Math.abs(now.az - was.az), Math.abs(now.polar - was.polar)) > 1e-4
      || now.target.some((v, i) => Math.abs(v - was.target[i]) > 1e-3);
    was = now;
    return moved;
  }, { timeout: 30_000 }).toBe(false);
  return was;
}
// A close view from above, where frames come quickly enough to follow a drag.
const closeAbove = page => page.evaluate(() => {
  const { camera, controls } = window.__dbg;
  camera.position.set(controls.target.x, controls.target.y + 400, controls.target.z + 120);
  controls.update();
});
const across = (a, b) => Math.hypot(a.target[0] - b.target[0], a.target[2] - b.target[2]);
const turned = (a, b) => Math.abs(Math.atan2(Math.sin(a.az - b.az), Math.cos(a.az - b.az)));
// A mouse drag over the middle of the map, right and up, with `button` and the modifier keys held.
async function drag(page, { button = 'left', keys = [] } = {}) {
  const box = await page.locator('#scene').boundingBox();
  const x = box.x + box.width / 2, y = box.y + box.height * 0.45;
  for (const k of keys) await page.keyboard.down(k);
  await page.mouse.move(x, y);
  await page.mouse.down({ button });
  await page.mouse.move(x + 200, y - 80, { steps: 10 });
  await page.mouse.up({ button });
  for (const k of keys) await page.keyboard.up(k);
}
// What the hint says on this browser's platform: the ⌘ lines on a Mac, the Ctrl lines elsewhere.
const isMac = page => page.evaluate(() => /mac/i.test(navigator.userAgentData?.platform || navigator.platform || ''));
const hintFor = async (page, turning) => page.evaluate(async on => (await import('./howto.js')).howto(navigator, on), turning);

test('the button and T switch turn mode, the tooltip and the hint follow, and nothing is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  const button = page.locator(TURN), hint = page.locator('.howto');
  const storage = await page.evaluate(() => Object.keys(localStorage).sort());
  // Right after north, the same round button, off
  expect(await page.evaluate(() => document.querySelector('.north-open').nextElementSibling.className)).toBe('turn-open');
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  await expect(button).toHaveAttribute('aria-label', 'Turn the map');
  await expect(button).toHaveAttribute('aria-keyshortcuts', 'T');
  await expect(button).toHaveAttribute('title', 'Turn the map: press, then drag to turn and tilt (T)');
  await expect(hint).toHaveText(await hintFor(page, false));
  await expect(hint).toHaveText(/^Drag to move\. Right-drag or (⌘|Ctrl)-drag to turn\./);
  // A title shows only on a mouse hover: on keyboard focus the button shows the same words itself, and only then
  const tipShown = () => page.evaluate(sel => {
    const b = document.querySelector(sel), s = getComputedStyle(b, '::before');
    return { tip: s.content === 'none' ? null : JSON.parse(s.content), title: b.title };
  }, TURN);
  expect((await tipShown()).tip).toBeNull();
  await page.locator('.north-open').focus();
  await page.keyboard.press('Tab');
  await expect(button).toBeFocused();
  let shown = await tipShown();
  expect(shown.tip).toBe(shown.title);
  await page.keyboard.press('Enter');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  shown = await tipShown();
  expect(shown.tip).toBe('Turning: drag turns the map. Press again to move it instead (T)');
  expect(shown.tip).toBe(shown.title);
  await page.keyboard.press('Space');
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  await button.blur();
  expect((await tipShown()).tip).toBeNull();
  const looks = () => page.evaluate(sel => {
    const b = document.querySelector(sel), s = getComputedStyle(b);
    return { bg: s.backgroundColor, ink: s.color, icon: b.querySelector('svg').outerHTML, size: [b.offsetWidth, b.offsetHeight] };
  }, TURN);
  const off = await looks(), north = await page.evaluate(() => getComputedStyle(document.querySelector('.north-open')).backgroundColor);
  expect(off.bg).toBe(north);
  expect(off.size).toEqual([28, 28]);

  // A click: on. The name stays, the tooltip and the hint say what a drag does now.
  await button.click();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await expect(button).toHaveAttribute('aria-label', 'Turn the map');
  await expect(button).toHaveAttribute('title', 'Turning: drag turns the map. Press again to move it instead (T)');
  await expect(hint).toHaveText(await hintFor(page, true));
  await expect(hint).toHaveText(/^Drag to turn\. Right-drag or (⌘|Ctrl)-drag to move\. Scroll or press \+ \/ − to zoom\.$/);
  expect(await page.evaluate(() => window.__dbg.turning)).toBe(true);
  // Pressed, it takes the selected EN | SV letters' fill and ink; the icon is the same
  const on = await looks();
  const chip = await page.evaluate(() => {
    const s = getComputedStyle(document.querySelector('.lang [aria-pressed="true"]'));
    return { bg: s.backgroundColor, ink: s.color };
  });
  expect({ bg: on.bg, ink: on.ink }).toEqual(chip);
  expect(on.icon).toBe(off.icon);
  expect(on.size).toEqual([28, 28]);

  // T switches it back, and on again, from the map or the button
  await page.locator('#scene').focus();
  await page.keyboard.press('t');
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  await expect(button).toHaveAttribute('title', 'Turn the map: press, then drag to turn and tilt (T)');
  await expect(hint).toHaveText(await hintFor(page, false));
  await page.keyboard.press('Shift+T');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  // Not with Ctrl or ⌘ held, and not while typing: the search field gets its t
  await page.keyboard.press(`${MOD}+t`);
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  const input = page.getByRole('combobox');
  await input.focus();
  await page.keyboard.press('t');
  await expect(input).toHaveValue('t');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await input.fill('');
  // Nothing written down: no new storage key, nothing in the address
  expect(await page.evaluate(() => Object.keys(localStorage).sort())).toEqual(storage);
  expect(new URL(page.url()).search).toBe('');
  // The next visit starts in move mode
  await page.reload();
  await settled(page);
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  expect(await page.evaluate(() => window.__dbg.turning)).toBe(false);
  expect(await page.evaluate(() => window.__dbg.controls.mouseButtons.LEFT)).toBe(2);   // THREE.MOUSE.PAN
  expect(errors).toEqual([]);
});

test('in Swedish the tooltip, the name and the hint are Swedish, and a language switch keeps the mode', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page, '?lang=sv');
  const button = page.locator(TURN), hint = page.locator('.howto');
  const mac = await isMac(page);
  await expect(button).toHaveAttribute('aria-label', 'Vrid kartan');
  await expect(button).toHaveAttribute('title', 'Vrid kartan: tryck och dra sedan för att vrida och luta (T)');
  await expect(hint).toHaveText(SV[mac ? 'ui.howto.mac' : 'ui.howto.other']);
  await button.click();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await expect(button).toHaveAttribute('aria-label', 'Vrid kartan');
  await expect(button).toHaveAttribute('title', 'Vrider: dra vrider kartan. Tryck igen för att flytta den i stället (T)');
  await expect(hint).toHaveText(SV[mac ? 'ui.howto.turn.mac' : 'ui.howto.turn.other']);
  await expect(hint).toHaveText(/^Dra för att vrida\. Högerdra eller (⌘|Ctrl)-dra för att flytta\./);
  // To English and back, still turning
  await page.locator('.lang [data-lang="en"]').click();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await expect(button).toHaveAttribute('aria-label', 'Turn the map');
  await expect(button).toHaveAttribute('title', 'Turning: drag turns the map. Press again to move it instead (T)');
  await expect(hint).toHaveText(await hintFor(page, true));
  await page.locator('.lang [data-lang="sv"]').click();
  await expect(button).toHaveAttribute('title', 'Vrider: dra vrider kartan. Tryck igen för att flytta den i stället (T)');
  expect(errors).toEqual([]);
});

test('a drag in turn mode turns and tilts round the place; a right-drag or a ⌘/Ctrl-drag moves it; move mode is as before', async ({ page }) => {
  const errors = watchErrors(page);
  await open(page);
  await closeAbove(page);
  // Move mode: a drag moves the place the camera looks at and leaves the way the map faces
  let before = await still(page);
  await drag(page);
  let after = await still(page);
  expect(across(after, before), 'move mode: the drag moves the map').toBeGreaterThan(20);
  expect(turned(after, before)).toBeLessThan(1e-3);
  // ... and a right-drag turns it, as before
  before = after;
  await drag(page, { button: 'right' });
  after = await still(page);
  expect(turned(after, before), 'move mode: a right-drag turns').toBeGreaterThan(0.3);

  // Turn mode: a plain drag turns and tilts, round the place, which stays where it is
  await page.locator(TURN).click();
  before = await still(page);
  await drag(page);
  after = await still(page);
  expect(turned(after, before), 'turn mode: the drag turns the map').toBeGreaterThan(0.3);
  expect(Math.abs(after.polar - before.polar), 'and tilts it').toBeGreaterThan(0.1);
  expect(across(after, before), 'the place stays').toBeLessThan(0.01);
  // A right-drag moves it
  before = after;
  await drag(page, { button: 'right' });
  after = await still(page);
  expect(across(after, before), 'turn mode: a right-drag moves the map').toBeGreaterThan(20);
  expect(turned(after, before)).toBeLessThan(1e-3);
  // A ⌘/Ctrl-drag moves it too (OrbitControls swaps PAN and ROTATE while the key is held)
  before = after;
  await drag(page, { keys: [MOD] });
  after = await still(page);
  expect(across(after, before), `turn mode: a ${MOD}-drag moves the map`).toBeGreaterThan(20);
  expect(turned(after, before)).toBeLessThan(1e-3);
  // Off again: a drag moves, as at the start
  await page.keyboard.press('t');
  await expect(page.locator(TURN)).toHaveAttribute('aria-pressed', 'false');
  before = after;
  await drag(page);
  after = await still(page);
  expect(across(after, before)).toBeGreaterThan(20);
  expect(turned(after, before)).toBeLessThan(1e-3);
  expect(errors).toEqual([]);
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  // One finger across the middle of the map, or two side by side moved together, by the browser's own touch events.
  async function swipe(page, fingers = 1) {
    const cdp = await page.context().newCDPSession(page);
    const x = 140, y = 360, to = [x + 150, y - 60];
    const points = (px, py) => Array.from({ length: fingers }, (_, id) => ({ x: px + id * 100, y: py, id }));
    for (const p of points(x, y)) expect(await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.id, p)).toBe('scene');
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: points(x, y) });
    for (let i = 1; i <= 10; i++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove',
        touchPoints: points(x + (to[0] - x) * i / 10, y + (to[1] - y) * i / 10) });
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await cdp.detach();
  }
  test('one finger moves the map, and turns it once the button is tapped; then two fingers move it', async ({ page }) => {
    const errors = watchErrors(page);
    await open(page);
    await closeAbove(page);
    let before = await still(page);
    await swipe(page);
    let after = await still(page);
    expect(across(after, before), 'move mode: one finger moves the map').toBeGreaterThan(20);
    expect(turned(after, before)).toBeLessThan(1e-3);
    await page.locator(TURN).tap();
    await expect(page.locator(TURN)).toHaveAttribute('aria-pressed', 'true');
    before = after;
    await swipe(page);
    after = await still(page);
    expect(turned(after, before), 'turn mode: one finger turns the map').toBeGreaterThan(0.3);
    expect(across(after, before), 'the place stays').toBeLessThan(0.01);
    // A touch screen has no right button or ⌘ key: two fingers moved together move the map in turn mode
    before = after;
    await swipe(page, 2);
    after = await still(page);
    expect(across(after, before), 'turn mode: two fingers move the map').toBeGreaterThan(20);
    expect(turned(after, before)).toBeLessThan(1e-3);
    expect(errors).toEqual([]);
  });
});

test('the button steps aside in postcard mode and in a story, whose camera still works, and comes back pressed', async ({ page }) => {
  const errors = watchErrors(page);
  await scenesOn(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });   // each beat's camera in place at once, nothing autoplays
  await open(page);
  const button = page.locator(TURN);
  await button.click();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  // Postcard: the corner steps aside, the button with it; Escape puts it back, still pressed
  await page.locator('#scene').focus();
  await page.keyboard.press('p');
  await expect(page.locator('.postcard-bar')).toBeVisible();
  await expect(button).toBeHidden();
  await expect(page.locator('.north-open')).toBeHidden();
  // T waits here: the button and the hint are out of sight, so nothing would show that a drag now does the other thing
  await page.keyboard.press('t');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  expect(await page.evaluate(() => window.__dbg.turning)).toBe(true);
  await page.keyboard.press('Escape');
  await expect(button).toBeVisible();
  await expect(button).toHaveAttribute('aria-pressed', 'true');

  // A story: hidden as the other corner buttons are; its camera moves from beat to beat in turn mode; T waits
  const story = 'metro-1950';
  const beats = (await (await page.request.get(`scenes/${story}.json`)).json()).beats.length;
  expect(beats).toBeGreaterThan(1);
  await page.evaluate(id => window.__dbg.scenePlayer.open(id), story);
  await expect(page.locator('.sp-cinema')).toBeVisible();
  await expect(button).toBeHidden();
  await expect(page.locator('.north-open')).toBeHidden();
  const cam = () => page.evaluate(() => window.__dbg.camera.position.toArray());
  const first = await cam();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('.sp-count')).toContainText(`2 / ${beats}`);
  await expect.poll(async () => {
    const now = await cam();
    return Math.hypot(now[0] - first[0], now[2] - first[2]);
  }, { message: 'the story\'s camera moves to the next beat' }).toBeGreaterThan(50);
  // T waits during the story too, but here the story player takes the key itself (scene-player.js: while a story plays
  // its capture-phase listener stops every key but its own), so this checks the outcome, not app.js's scene-on check
  await page.keyboard.press('t');
  expect(await page.evaluate(() => window.__dbg.turning)).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.locator('.sp-cinema')).toBeHidden();
  await expect(button).toBeVisible();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  // The scene-on check is what holds T at a sensitive story's warning, which lets keys through: with the focus off the
  // warning's dialog (where typingIn would also stop it), T still leaves the mode as it is
  const sensitive = 'vasa-1628';
  expect((await (await page.request.get(`scenes/${sensitive}.json`)).json()).sensitive).toBe(true);
  await page.evaluate(id => window.__dbg.scenePlayer.open(id), sensitive);
  await expect(page.locator('.sp-warning')).toBeVisible();
  await expect(button).toBeHidden();
  await page.evaluate(() => document.activeElement.blur());
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
  await page.keyboard.press('t');
  expect(await page.evaluate(() => window.__dbg.turning)).toBe(true);
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await expect(page.locator('.sp-warning')).toBeHidden();
  await expect(button).toBeVisible();
  // ... and the map still turns on a drag afterwards
  await closeAbove(page);
  const before = await still(page);
  await drag(page);
  const after = await still(page);
  expect(turned(after, before)).toBeGreaterThan(0.3);
  expect(across(after, before)).toBeLessThan(0.01);
  expect(errors).toEqual([]);
});

// The corner's row at a phone's width, in both languages, off and on: every button inside the 16 px gutters (the row
// once ran to 1 px from the left edge at 384 to 404 px in Swedish and 335 to 354 px in English), no sideways scroll,
// the turn button 28 px drawn and a 44 px target that leaves its neighbours' taps to them. Saved for review.
for (const width of [390, 375, 340, 320]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 740 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    for (const [look, kind] of [['arg', 'light'], ['blatimme', 'dark']]) {
      test(`the corner's row fits with the turn button, ${kind} (${look})`, async ({ page }) => {
        const errors = watchErrors(page);
        mkdirSync(SHOTS, { recursive: true });
        await open(page, `?theme=${look}`);
        await expect(page.locator('html')).toHaveAttribute('data-theme', look);
        expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
        for (const lang of ['en', 'sv']) {
          if (lang === 'sv') await page.locator('.lang [data-lang="sv"]').click();
          await expect(page.locator('html')).toHaveAttribute('lang', lang);
          for (const state of ['off', 'on']) {
            if (state === 'on') await page.locator(TURN).tap();
            await expect(page.locator(TURN)).toHaveAttribute('aria-pressed', String(state === 'on'));
            const boxes = await page.locator('.corner .buttons > :is(button, .lang)').evaluateAll(els =>
              els.filter(el => el.offsetParent).map(el => ({ cls: el.className, ...el.getBoundingClientRect().toJSON() })));
            expect(boxes.map(b => b.cls)).toContain('turn-open');
            for (const b of boxes) expect(b.left >= 16 && b.right <= width - 16, `${lang} ${state}: ${JSON.stringify(b)}`).toBe(true);
            expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
            // 44 px: a tap 7 px past any edge of the turn button is still the turn button, and 7 px past the edge of a
            // round neighbour is still that neighbour
            const hits = await page.evaluate(() => ['.search-open', '.north-open', '.turn-open', '.postcard-open'].map(sel => {
              const b = document.querySelector(sel), r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
              const at = (px, py) => document.elementFromPoint(px, py)?.closest('button') === b;
              return { sel, size: [Math.round(r.width), Math.round(r.height)],
                edges: [at(x, r.top - 7), at(x, r.bottom + 7), at(r.left - 7, y), at(r.right + 7, y)] };
            }));
            for (const h of hits) expect(h, `${lang} ${state}`).toMatchObject({ size: [28, 28], edges: [true, true, true, true] });
            await page.waitForTimeout(700);   // the browser's tap highlight fades first, so the shot shows the fill alone
            await page.screenshot({ path: `${SHOTS}/${look}-${width}-${lang}-${state}.png` });
          }
          await page.locator(TURN).tap();   // back off for the next language
        }
        expect(errors).toEqual([]);
      });
    }
  });
}

// On a tablet the search pill sits under the modes, over the top of the corner's row as it was: now the row starts
// below it, in both languages, with a mouse and on a touch screen. Saved for review.
for (const touch of [false, true]) {
  test.describe(`at 768 px, ${touch ? 'touch' : 'mouse'}`, () => {
    test.use({ viewport: { width: 768, height: 1024 }, hasTouch: touch });
    test('no button in the corner\'s row is under the search pill', async ({ page }) => {
      const errors = watchErrors(page);
      mkdirSync(SHOTS, { recursive: true });
      await open(page, '?theme=arg');
      expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(touch);
      for (const lang of ['en', 'sv']) {
        if (lang === 'sv') await page.locator('.lang [data-lang="sv"]').click();
        await expect(page.locator('html')).toHaveAttribute('lang', lang);
        for (const state of ['off', 'on']) {
          if (state === 'on') await page.locator(TURN).click();
          await expect(page.locator(TURN)).toHaveAttribute('aria-pressed', String(state === 'on'));
          const hits = await page.evaluate(() => {
            const r = el => el.getBoundingClientRect();
            const over = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
            const others = ['.search', '.modes'].map(sel => [sel, r(document.querySelector(sel))]);
            return [...document.querySelectorAll('.corner .buttons > *')].filter(el => el.offsetParent)
              .flatMap(el => others.filter(([, o]) => over(r(el), o)).map(([sel]) => `${el.className} under ${sel}`));
          });
          expect(hits, `${lang} ${state}`).toEqual([]);
          // A click at the top of the turn button is the turn button's, not the pill's
          const b = await page.locator(TURN).boundingBox();
          expect(await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('button')?.className,
            [b.x + b.width / 2, b.y + 1])).toBe('turn-open');
          if (touch) await page.screenshot({ path: `${SHOTS}/arg-768-${lang}-${state}.png` });
        }
        await page.locator(TURN).click();   // back off for the next language
      }
      expect(errors).toEqual([]);
    });
  });
}

// On a desktop, light and dark, off and on: the whole screen and the corner close up, saved for review.
for (const [look, kind] of [['arg', 'light'], ['blatimme', 'dark']]) {
  test(`on a desktop the button sits after north, off and pressed, ${kind} (${look})`, async ({ page }) => {
    const errors = watchErrors(page);
    mkdirSync(SHOTS, { recursive: true });
    await open(page, `?theme=${look}`);
    await expect(page.locator('html')).toHaveAttribute('data-theme', look);
    const north = await page.locator('.north-open').boundingBox(), turn = await page.locator(TURN).boundingBox();
    expect(turn.y).toBeCloseTo(north.y, 0);
    expect(turn.x - (north.x + north.width)).toBeCloseTo(6, 0);   // the row's 6 px gap
    for (const state of ['off', 'on']) {
      if (state === 'on') await page.locator(TURN).click();
      await page.mouse.move(200, 300);   // the pointer over the legend, away from the button and the buildings' hover card
      await page.screenshot({ path: `${SHOTS}/${look}-desktop-${state}.png` });
      await page.locator('.corner').screenshot({ path: `${SHOTS}/${look}-desktop-${state}-corner.png` });
    }
    // The tooltip on keyboard focus, pressed, in English and Swedish: the corner and the space under it
    for (const lang of ['en', 'sv']) {
      if (lang === 'sv') await page.locator('.lang [data-lang="sv"]').click();
      await page.locator('.north-open').focus();
      await page.keyboard.press('Tab');
      await expect(page.locator(TURN)).toBeFocused();
      const c = await page.locator('.corner').boundingBox();
      await page.screenshot({ path: `${SHOTS}/${look}-desktop-focus-${lang}.png`,
        clip: { x: c.x - 120, y: c.y, width: c.width + 120, height: c.height + 70 } });
    }
    await page.locator(TURN).blur();
    // In forced colours (Windows High Contrast) the pressed button still looks pressed: the system's highlight
    await page.emulateMedia({ forcedColors: 'active' });
    const fill = sel => page.evaluate(s => getComputedStyle(document.querySelector(s)).backgroundColor, sel);
    expect(await fill(TURN)).not.toBe(await fill('.north-open'));
    await page.locator('.corner').screenshot({ path: `${SHOTS}/${look}-desktop-forced-corner.png` });
    await page.emulateMedia({ forcedColors: 'none' });
    expect(errors).toEqual([]);
  });
}
