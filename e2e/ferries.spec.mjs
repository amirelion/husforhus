// Boats on the map (web/ferries.js, web/ferries-layer.js): the city's ferries and the Baltic ships on their routes, on by
// default but only at Today. The data has no ferries.json yet, so every test serves a fixture (e2e/fixtures/ferries.json,
// five routes on the water round Gamla stan, Slussen and Skeppsholmen) and switches features.ferries on in
// stockholm.json. Covered: the boats at Today and not for an earlier year, the film or a story; the Look panel's
// "Boats" switch (remembered, no dot while on, its hint that they show at Today, its Swedish name); About's line that
// they are not live, only while the map has boats; boats that arrive while a panel is open; no boats without drawn
// water; the pick pass (a boat over a building never hides the building from it); reduced motion; draw calls. And the
// boat's tooltip (web/boat-tip.js): hovering a boat names its line, its route and where it is heading, in English and
// Swedish, and goes when the pointer leaves; a click on a boat opens no building card behind it, but a building in
// front of a boat keeps its hover and its click, and a metro station's ring takes the click before a boat; up close a
// ship half behind the camera is still found; a tap on a phone shows it as a sheet, which takes a tap on it and closes
// (the modes and the timeline under it untouched), stands in for the legend's handle, and goes at a tap elsewhere, with
// the boats, or when a card is pinned; a ferries.json without stops gives the title.
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { settled } from './settled.mjs';

const FIXTURE = readFileSync(new URL('./fixtures/ferries.json', import.meta.url), 'utf8');
const BOATS = 8;   // two on each of the three ferry lines (each 1 km or longer), one on each ship lane

// hold(): a promise ferries.json waits for, so a test can open a panel before the boats arrive; body: another file.
async function withBoats(page, { scenes = false, hold = () => null, body = FIXTURE } = {}) {
  await page.route('**/ferries.json', async r => {
    await hold();
    await r.fulfill({ contentType: 'application/json', body });
  });
  await page.route('**/stockholm.json', async route => {
    const r = await route.fetch();
    const config = await r.json();
    config.features = { ...config.features, ferries: true, ...(scenes ? { scenes: true } : {}) };
    await route.fulfill({ response: r, json: config });
  });
}
async function open(page, query = '') {
  await page.goto('/' + query);
  await settled(page);
  await expect.poll(() => page.evaluate(() => window.__dbg.ferries?.count ?? 0)).toBe(BOATS);
}
async function openLook(page) {
  if (await page.locator('.look-open').getAttribute('aria-expanded') !== 'true') await page.locator('.look-open').click();
  await expect(page.locator('#look')).toBeVisible();
}
const visible = page => page.evaluate(() => window.__dbg.ferries.visible);
const yearMax = page => page.evaluate(() => fetch('data/current.json').then(r => r.json())
  .then(({ version }) => fetch(`data/${version}/stockholm.json`)).then(r => r.json()).then(c => c.yearMax));
const frames = (page, n = 2) => page.evaluate(n => new Promise(r => {
  const f = k => (k ? requestAnimationFrame(() => f(k - 1)) : r());
  f(n);
}), n);
const watchErrors = page => { const errors = []; page.on('pageerror', e => errors.push(e.message)); return errors; };

test('the boats sail at Today, hide for an earlier year and while the film plays, and come back', async ({ page }) => {
  const errors = watchErrors(page);
  await withBoats(page);
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  const routes = await page.evaluate(() => window.__dbg.ferries.routes);
  expect(routes.map(r => r.kind).sort()).toEqual(['ferry', 'ferry', 'ferry', 'ship', 'ship']);
  // they move: two moments a second apart
  const a = await page.evaluate(() => window.__dbg.ferries.positions);
  await page.waitForTimeout(1000);
  const b = await page.evaluate(() => window.__dbg.ferries.positions);
  expect(a.some((p, i) => p.speed > 0 && Math.hypot(p.x - b[i].x, p.z - b[i].z) > 1)).toBe(true);

  await page.evaluate(() => { window.__dbg.uniforms.uYear.value = 1950; });
  await expect.poll(() => visible(page)).toBe(false);
  // the switch still reads on, and its hint says why the map shows none
  await openLook(page);
  await expect(page.locator('#boats-on')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#boats-hint')).toHaveText('Shown at “Today”, hidden in the past.');
  await page.keyboard.press('Escape');
  const max = await yearMax(page);
  await page.evaluate(y => { window.__dbg.uniforms.uYear.value = y; }, max);
  await expect.poll(() => visible(page)).toBe(true);

  await page.locator('#play').click();                      // the film starts again from the past
  await expect.poll(() => visible(page)).toBe(false);
  await page.locator('#play').click();                      // paused in the past: still hidden
  await frames(page);
  expect(await visible(page)).toBe(false);
  expect(errors).toEqual([]);
});

test('a story hides the boats; Exit brings them back at Today', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await withBoats(page, { scenes: true });
  await open(page, '?scene=metro-1950');
  await expect(page.locator('.sp-cinema')).toBeVisible();
  await frames(page);
  expect(await visible(page)).toBe(false);
  // the story itself hides them, not only its year
  await page.evaluate(y => { window.__dbg.uniforms.uYear.value = y; }, await yearMax(page));
  await frames(page, 3);
  expect(await visible(page)).toBe(false);
  await page.locator('.sp-exit').click();
  await expect(page.locator('.sp-cinema')).toBeHidden();
  await expect.poll(() => visible(page)).toBe(true);
});

test('the Boats switch is on without lighting the dot; off hides them, lights the dot and is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  await withBoats(page);
  await open(page);
  await expect(page.locator('.look-dot')).toBeHidden();      // on is the default: nothing to point out
  await openLook(page);
  const sw = page.locator('#look #boats-on'), hint = page.locator('#look #boats-hint');
  await expect(sw).toHaveText('Boats');
  await expect(sw).toHaveAttribute('aria-pressed', 'true');
  await expect(hint).toBeVisible();
  await expect(sw).toHaveAttribute('aria-describedby', 'boats-hint');
  await sw.click();
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await expect(hint).toBeHidden();
  await expect.poll(() => visible(page)).toBe(false);
  expect(await page.evaluate(() => localStorage.getItem('hfh-boats'))).toBe('off');
  expect(new URL(page.url()).searchParams.has('boats')).toBe(false);   // never in the URL
  await page.keyboard.press('Escape');
  await expect(page.locator('.look-dot')).toBeVisible();     // a choice that differs from the default

  await page.reload();
  await settled(page);
  await expect.poll(() => page.evaluate(() => window.__dbg.ferries?.count ?? 0)).toBe(BOATS);
  expect(await visible(page)).toBe(false);
  await openLook(page);
  await expect(sw).toHaveAttribute('aria-pressed', 'false');
  await sw.click();
  await expect.poll(() => visible(page)).toBe(true);
  await expect(hint).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('hfh-boats'))).toBe('on');
  await page.keyboard.press('Escape');
  await expect(page.locator('.look-dot')).toBeHidden();
  expect(errors).toEqual([]);
});

// A build with the flag but without boats: the file missing, or written with no routes (s17_ferries when Overpass could
// not be reached). Neither the switch nor About's line on the boats appears.
for (const [what, reply] of [['without ferries.json', { status: 404, body: '' }],
  ['with a ferries.json that has no routes', { contentType: 'application/json', body: '{"version": 1, "routes": []}' }]]) {
  test(`${what} there is no switch, no boat and no word of them in About, and the map starts as before`, async ({ page }) => {
    const errors = watchErrors(page);
    let asked = false;
    await page.route('**/ferries.json', r => { asked = true; return r.fulfill(reply); });
    await page.route('**/stockholm.json', async route => {
      const r = await route.fetch();
      const config = await r.json();
      config.features = { ...config.features, ferries: true };
      await route.fulfill({ response: r, json: config });
    });
    const warned = [];
    page.on('console', m => { if (m.type() === 'warning') warned.push(m.text()); });
    await page.goto('/');
    await settled(page);
    await expect.poll(() => asked).toBe(true);
    if (reply.status === 404) await expect.poll(() => warned.join('\n')).toMatch(/The boats did not load/);
    await frames(page, 3);
    expect(await page.evaluate(() => window.__dbg.ferries)).toBeNull();
    await openLook(page);
    await expect(page.locator('#boats-on')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await page.locator('.about-open').click();
    await expect(page.locator('#about-limits')).toBeAttached();
    await expect(page.locator('#about-body')).not.toContainText('The boats are an illustration');
    expect(errors).toEqual([]);
  });
}

test('boats that arrive while a panel is open change nothing under the visitor; the next open shows the switch and About\'s line', async ({ page }) => {
  const errors = watchErrors(page);
  let release, gate;
  const hold = () => gate;
  const shut = () => { gate = new Promise(r => { release = r; }); };
  shut();
  await withBoats(page, { hold });
  // About, opened at its limits by a link: the boats come in, and the reader keeps their place
  await page.goto('/#about/limits');
  await settled(page);
  await expect(page.locator('#about')).toBeVisible();
  await expect(page.locator('#about-limits')).toBeFocused();
  await expect(page.locator('#about-body')).not.toContainText('The boats are an illustration');
  release();
  await expect.poll(() => page.evaluate(() => window.__dbg.ferries?.count ?? 0)).toBe(BOATS);
  await frames(page);
  await expect(page.locator('#about-limits')).toBeFocused();
  await expect(page.locator('#about-body')).not.toContainText('The boats are an illustration');
  await page.locator('#about .about-close').click();
  await page.locator('.about-open').click();
  await expect(page.locator('#about-body')).toContainText('The boats are an illustration');
  await page.locator('#about .about-close').click();

  // the Look panel, open with a switch focused: no row appears above it and it keeps the focus
  shut();
  await page.goto('/');
  await settled(page);
  await openLook(page);
  const photo = page.locator('#look #photo-only');
  await photo.focus();
  const before = await photo.boundingBox();
  release();
  await expect.poll(() => page.evaluate(() => window.__dbg.ferries?.count ?? 0)).toBe(BOATS);
  await frames(page);
  await expect(page.locator('#look')).toBeVisible();
  await expect(photo).toBeFocused();
  expect(await photo.boundingBox()).toEqual(before);
  await expect(page.locator('#look #boats-on')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await openLook(page);
  await expect(page.locator('#look #boats-on')).toHaveAttribute('aria-pressed', 'true');
  expect(errors).toEqual([]);
});

test('in Swedish the switch reads Båtar; About says, in both languages, that the boats are not live', async ({ page }) => {
  await withBoats(page);
  await open(page, '?lang=sv');
  await openLook(page);
  await expect(page.locator('#boats-on')).toHaveText('Båtar');
  await page.keyboard.press('Escape');
  await page.locator('.about-open').click();
  await expect(page.locator('#about-body')).toContainText('Båtarna är en illustration');
  await page.locator('#about .about-close').click();
  await page.locator('.lang [data-lang="en"]').click();
  await page.locator('.about-open').click();
  await expect(page.locator('#about-body')).toContainText('The boats are an illustration');
  await expect(page.locator('#about-body')).toContainText('they do not show where any boat is right now');
});

test('the pick pass leaves the boats out: a boat over a building never hides the building from it', async ({ page }) => {
  await withBoats(page);
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  // a tall dated building near Slussen, seen from straight above at 300 m
  const gid = await page.evaluate(() => {
    const D = window.__dbg;
    for (let g = 0; g < 80000; g++) {
      const b = D.building(g);
      if (b && b.yflag !== 7 && b.height > 15 && Math.hypot(b.x - 150, b.z - 250) < 250) return g;
    }
    return -1;
  });
  expect(gid).toBeGreaterThanOrEqual(0);
  const at = await page.evaluate(async g => {
    const D = window.__dbg, b = D.building(g), y = D.surfaceAt(b.x, b.z);
    D.ferries.freeze(30);
    D.controls.target.set(b.x, y, b.z);
    D.camera.position.set(b.x, y + 300, b.z + 0.5);
    D.controls.update();
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    // move every boat together so that the first one lies on the building's roof, 3 m above it (the group's own
    // transform: step() places each boat inside it)
    const p = D.ferries.positions[0];
    D.ferries.group.position.set(b.x - p.x, y + b.height + 3, b.z - p.z);
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const v = new D.camera.position.constructor(b.x, y + b.height, b.z).project(D.camera);
    return { x: Math.round((v.x + 1) / 2 * innerWidth), y: Math.round((1 - v.y) / 2 * innerHeight) };
  }, gid);
  // the boat is drawn there: its upper works, near white on Ärg (read straight after a render: the canvas keeps no
  // drawing buffer)
  const px = await page.evaluate(({ x, y }) => {
    const D = window.__dbg, gl = D.renderer.getContext(), k = D.renderer.getPixelRatio(), out = new Uint8Array(4);
    D.renderer.render(D.scene, D.camera);
    gl.readPixels(Math.round(x * k), Math.round((innerHeight - y) * k), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, out);
    return [...out.slice(0, 3)];
  }, at);
  expect(Math.min(...px), `the boat covers the roof (${px})`).toBeGreaterThan(225);
  // and the click finds the building under it
  expect(await page.evaluate(({ x, y }) => window.__dbg.pick(x, y), at)).toBe(gid);
  expect(await visible(page)).toBe(true);                     // shown again after the pick
  await page.evaluate(() => window.__dbg.ferries.group.position.set(0, 0, 0));
});

test('without the water (water.bin failed) the boats stay off the map rather than sail over the land', async ({ page }) => {
  await withBoats(page);
  await page.route('**/water.bin.gz', r => r.abort());
  await page.goto('/');
  await settled(page);
  await expect.poll(() => page.evaluate(() => window.__dbg.ferries?.count ?? 0)).toBe(BOATS);
  await frames(page, 3);
  expect(await visible(page)).toBe(false);
});

test('with reduced motion the boats stand still, without wakes', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await withBoats(page);
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  const a = await page.evaluate(() => window.__dbg.ferries.positions);
  await page.waitForTimeout(1200);
  const b = await page.evaluate(() => window.__dbg.ferries.positions);
  expect(b.map(p => [p.x, p.z, p.heading])).toEqual(a.map(p => [p.x, p.z, p.heading]));
  expect(b.every(p => p.speed === 0)).toBe(true);
  // every one standing whole on a run of its route (ferries.js calmTime), none out of sight or turning at a pier
  expect(b.map(p => p.alpha)).toEqual(b.map(() => 1));
});

test('the boats cost at most two draw calls, and the farthest view stays under 300', async ({ page }) => {
  await withBoats(page);
  await open(page, '?debug=1');
  await expect.poll(() => visible(page)).toBe(true);
  const calls = async () => { await frames(page, 3); return page.evaluate(() => window.__dbg.stats().calls); };
  const on = await calls();
  await page.evaluate(() => window.__dbg.setBoats(false));
  const off = await calls();
  expect(on - off).toBeGreaterThan(0);
  expect(on - off).toBeLessThanOrEqual(2);
  await page.evaluate(() => window.__dbg.setBoats(true));
  const farthest = await page.evaluate(async () => {
    const D = window.__dbg, ctl = D.controls, cam = D.camera, t = ctl.target;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const out = [];
    for (const polar of [0.001, 0.6, 1.1]) {
      for (let k = 0; k < 4; k++) {
        const az = k * Math.PI / 2;
        cam.position.set(t.x + Math.sin(polar) * Math.sin(az), t.y + Math.cos(polar), t.z + Math.sin(polar) * Math.cos(az));
        ctl.update();
        D.viewAt(40000);
        // the count once the view has settled: right after the jump the tiles and the ground are still swapping their
        // detail, and under a loaded test run two frames caught both at once (351 calls, 2026-10-20)
        let calls = -1, same = 0;
        for (let f = 0; f < 90 && same < 3; f++) {
          await frame();
          const c = D.stats().calls;
          same = c === calls ? same + 1 : 0;
          calls = c;
        }
        out.push({ calls, boats: D.ferries.visible, scale: Math.max(...D.ferries.positions.map(p => p.scale)) });
      }
    }
    return out;
  });
  for (const f of farthest) {
    expect(f.boats).toBe(true);
    expect(f.calls).toBeLessThan(300);
    expect(f.scale).toBeLessThanOrEqual(4);                     // grown to stay visible, but never more than four times
  }
});

// ---------- The boat's tooltip ----------
const tip = page => page.locator('#boat-tip');
// Holds the boats at a moment when boat i of route `id` is under way heading for end `toward` of its path, puts the
// camera straight above it, `dist` metres up, and says where it is on the screen (ferries-layer.js hullOnScreen).
async function aimAt(page, id, toward, { dist = 700, i = 0 } = {}) {
  return page.evaluate(async ({ id, toward, dist, i }) => {
    const D = window.__dbg, F = D.ferries;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const k = F.positions.findIndex(p => p && p.route === id && p.i === i);
    for (let t = 0; t < 900; t += 3) {
      F.freeze(t);
      await frame();
      const p = F.positions[k];
      if (p.toward === toward && p.speed > 0.5 && p.alpha === 1) break;
    }
    const p = F.positions[k];
    D.controls.target.set(p.x, 0, p.z);
    D.camera.position.set(p.x, dist, p.z + 1);
    D.controls.update();
    await frame();
    const h = F.hullOnScreen(k, innerWidth, innerHeight);
    return { k, x: Math.round(h.c[0]), y: Math.round(h.c[1]), r: h.r, toward: F.positions[k].toward };
  }, { id, toward, dist, i });
}
// A point near (x, y) with no boat under it.
const emptyNear = (page, { x, y }) => page.evaluate(({ x, y }) => {
  const F = window.__dbg.ferries;
  for (const [dx, dy] of [[0, 160], [160, 0], [-160, 0], [0, -160], [220, 220], [-220, -220]]) {
    if (!F.hitAt(x + dx, y + dy, innerWidth, innerHeight)) return { x: x + dx, y: y + dy };
  }
  return null;
}, { x, y });
const cursor = page => page.evaluate(() => document.getElementById('scene').style.cursor);

test('hovering a boat names its line, its route and where it is heading; it goes when the pointer leaves', async ({ page }) => {
  const errors = watchErrors(page);
  await withBoats(page);
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  const out = await aimAt(page, 'r9000001', 1);
  expect(out.toward).toBe(1);
  await page.mouse.move(out.x, out.y);
  await expect(tip(page)).toBeVisible();
  await expect(tip(page).locator('.boat-title')).toHaveText('Djurgårdsfärjan · line 82');
  await expect(tip(page).locator('.boat-route')).toHaveText('Slussen – Skeppsholmen – Allmänna gränd');
  await expect(tip(page).locator('.boat-heading')).toHaveText('Heading for Allmänna gränd');
  await expect(tip(page).locator('.boat-note')).toHaveText('Real route, not a live position');
  expect(await cursor(page)).not.toBe('pointer');             // a click on it opens nothing: no hand
  // the boat wins over the building behind it: no hover tint, no hover card
  expect(await page.evaluate(() => window.__dbg.uniforms.uHover.value)).toBe(-1);
  await expect(page.locator('#card')).toBeHidden();
  // beside the pointer, for pointer users only: hidden from a screen reader, never focused
  const box = await tip(page).boundingBox();
  expect(Math.abs(box.x - out.x)).toBeLessThan(40);
  expect(Math.abs(box.y - out.y)).toBeLessThan(box.height + 40);
  await expect(tip(page)).toHaveAttribute('aria-hidden', 'true');
  expect(await page.evaluate(() => document.getElementById('boat-tip').contains(document.activeElement))).toBe(false);

  const away = await emptyNear(page, out);
  await page.mouse.move(away.x, away.y);
  await expect(tip(page)).toBeHidden();

  // the same boat on its run back heads for the line's first stop
  const back = await aimAt(page, 'r9000001', 0);
  expect(back.toward).toBe(0);
  await page.mouse.move(back.x, back.y);
  await expect(tip(page).locator('.boat-heading')).toHaveText('Heading for Slussen');
  // and a ship sailing out names its destinations
  const ship = await aimAt(page, 'r9000004', 1, { dist: 1500 });
  await page.mouse.move(ship.x, ship.y);
  await expect(tip(page).locator('.boat-title')).toHaveText('Viking Line');
  await expect(tip(page).locator('.boat-route')).toHaveText('Stockholm – Mariehamn – Turku, Helsinki');
  await expect(tip(page).locator('.boat-heading')).toHaveText('Heading for Turku or Helsinki');
  // the pointer leaving the map takes it away too
  await page.mouse.move(5, 5);
  await expect(tip(page)).toBeHidden();
  await page.evaluate(() => window.__dbg.ferries.freeze(null));
  expect(errors).toEqual([]);
});

test('a click on a boat opens no building card behind it, though the pick pass finds the building there', async ({ page }) => {
  await withBoats(page);
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  const gid = await page.evaluate(() => {
    const D = window.__dbg;
    for (let g = 0; g < 80000; g++) {
      const b = D.building(g);
      if (b && b.yflag !== 7 && b.height > 15 && Math.hypot(b.x - 150, b.z - 250) < 250) return g;
    }
    return -1;
  });
  expect(gid).toBeGreaterThanOrEqual(0);
  // as in the pick pass's test: the first boat lies on the building's roof, seen from above
  const at = await page.evaluate(async g => {
    const D = window.__dbg, b = D.building(g), y = D.surfaceAt(b.x, b.z);
    D.ferries.freeze(30);
    D.controls.target.set(b.x, y, b.z);
    D.camera.position.set(b.x, y + 300, b.z + 0.5);
    D.controls.update();
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const p = D.ferries.positions[0];
    D.ferries.group.position.set(b.x - p.x, y + b.height + 3, b.z - p.z);
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const v = new D.camera.position.constructor(b.x, y + b.height, b.z).project(D.camera);
    return { x: Math.round((v.x + 1) / 2 * innerWidth), y: Math.round((1 - v.y) / 2 * innerHeight) };
  }, gid);
  await page.mouse.move(at.x, at.y);
  await expect(tip(page)).toBeVisible();
  await page.mouse.click(at.x, at.y);
  await frames(page, 4);
  expect(await page.evaluate(() => window.__dbg.pinned)).toBe(-1);
  await expect(page.locator('#card')).toBeHidden();
  await expect(tip(page)).toBeVisible();                      // the click keeps it
  expect(await page.evaluate(({ x, y }) => window.__dbg.pick(x, y), at)).toBe(gid);
  // with the boats switched off the same click pins the building
  await page.evaluate(() => window.__dbg.setBoats(false));
  await expect(tip(page)).toBeHidden();
  await page.mouse.click(at.x, at.y);
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned)).toBe(gid);
  await page.evaluate(() => { window.__dbg.ferries.group.position.set(0, 0, 0); window.__dbg.ferries.freeze(null); });
});

// Puts the first boat (Djurgårdsfärjan's) `ahead` metres in front of a tall building as the camera sees it (negative:
// behind it), `lift` metres up, the camera low, 120 m in front of the building and 40 m up; tries buildings until the
// pick pass finds that one at the boat's middle on the screen, where hitAt finds the boat. {g, x, y}, or null.
const boatByBuilding = (page, { ahead, lift }) => page.evaluate(async ({ ahead, lift }) => {
  const D = window.__dbg, F = D.ferries;
  const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  F.freeze(30);
  await frame();
  let tries = 0;
  for (let g = 0; g < 80000 && tries < 25; g++) {
    const b = D.building(g);
    if (!b || b.yflag === 7 || b.height < 18 || Math.hypot(b.x - 150, b.z - 250) > 700) continue;
    tries++;
    const y = D.surfaceAt(b.x, b.z);
    D.controls.target.set(b.x, y, b.z);
    D.camera.position.set(b.x, y + 40, b.z + 120);
    D.controls.update();
    const p = F.positions[0];
    F.group.position.set(b.x - p.x, D.surfaceAt(b.x, b.z + ahead) + lift, b.z + ahead - p.z);
    await frame();
    const h = F.hullOnScreen(0, innerWidth, innerHeight);
    if (!h) continue;
    const x = Math.round((h.a[0] + h.b[0]) / 2), sy = Math.round((h.a[1] + h.b[1]) / 2);
    if (D.pick(x, sy) === g && F.hitAt(x, sy, innerWidth, innerHeight)?.k === 0) return { g, x, y: sy };
  }
  return null;
}, { ahead, lift });

test('a building in front of a boat keeps its hover and its click; a boat in front of a building still wins', async ({ page }) => {
  const errors = watchErrors(page);
  await withBoats(page);
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  // the boat on the ground 60 m behind the building, seen low across it: the building hides it, so the building is
  // hovered and pinned there, though hitAt finds the boat's outline under the pointer
  const behind = await boatByBuilding(page, { ahead: -60, lift: 0 });
  expect(behind).not.toBeNull();
  await page.mouse.move(behind.x, behind.y);
  await expect.poll(() => page.evaluate(() => window.__dbg.uniforms.uHover.value)).toBe(behind.g);
  await expect(page.locator('#card')).toBeVisible();
  await expect(tip(page)).toBeHidden();
  await page.mouse.click(behind.x, behind.y);
  await expect.poll(() => page.evaluate(() => window.__dbg.pinned)).toBe(behind.g);
  await page.evaluate(() => window.__dbg.pinCard(-1));
  await page.mouse.move(5, 5);
  // the boat 60 m in front of a building, lifted so the building lies behind it on the pointer's ray: the boat wins
  const before = await boatByBuilding(page, { ahead: 60, lift: 22 });
  expect(before).not.toBeNull();
  await page.mouse.move(before.x, before.y);
  await expect(tip(page)).toBeVisible();
  await expect(tip(page).locator('.boat-title')).toHaveText('Djurgårdsfärjan · line 82');
  expect(await page.evaluate(() => window.__dbg.uniforms.uHover.value)).toBe(-1);
  await page.mouse.click(before.x, before.y);
  await frames(page, 4);
  expect(await page.evaluate(() => window.__dbg.pinned)).toBe(-1);
  await page.evaluate(() => { window.__dbg.ferries.group.position.set(0, 0, 0); window.__dbg.ferries.freeze(null); });
  expect(errors).toEqual([]);
});

test('a metro station\'s ring takes the click before a boat lying over it, and no boat tooltip promises otherwise', async ({ page }) => {
  await withBoats(page);
  await open(page, '?metro=1');
  await expect.poll(() => visible(page)).toBe(true);
  test.skip(!(await page.evaluate(() => (window.__dbg.metroLayer?.shownStations.length ?? 0) > 0)), 'this build has no metro.json');
  const at = await page.evaluate(async () => {
    const D = window.__dbg, F = D.ferries;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const ring = D.metroLayer.group.children.find(m => m.userData.station?.name === 'Slussen');
    F.freeze(30);
    D.controls.target.set(ring.position.x, D.surfaceAt(ring.position.x, ring.position.z), ring.position.z);
    D.camera.position.set(ring.position.x, D.controls.target.y + 900, ring.position.z + 1);
    D.controls.update();
    await frame();
    const p = F.positions[0];
    F.group.position.set(ring.position.x - p.x, 0, ring.position.z - p.z);    // the boat on the ring
    await frame();
    const v = ring.position.clone().project(D.camera);
    const x = Math.round((v.x + 1) / 2 * innerWidth), y = Math.round((1 - v.y) / 2 * innerHeight);
    const bow = F.hullOnScreen(0, innerWidth, innerHeight).b.map(Math.round);
    return { x, y, boat: F.hitAt(x, y, innerWidth, innerHeight)?.k ?? -1,
      station: D.metroLayer.stationAt(x, y, innerWidth, innerHeight)?.name ?? null,
      bow: { x: bow[0], y: bow[1], station: !!D.metroLayer.stationAt(bow[0], bow[1], innerWidth, innerHeight) } };
  });
  expect(at.boat).toBe(0);
  expect(at.station).toBe('Slussen');
  expect(at.bow.station).toBe(false);
  await page.mouse.move(at.bow.x, at.bow.y);                   // the boat's bow, clear of the ring: its tooltip
  await expect(tip(page)).toBeVisible();
  await page.mouse.move(at.x, at.y);                           // on the ring a click opens the station: no tooltip
  await expect(tip(page)).toBeHidden();
  await page.mouse.click(at.x, at.y);
  await expect(page.locator('#card.pinned.station h3')).toHaveText('Slussen');
  await page.evaluate(() => { window.__dbg.ferries.group.position.set(0, 0, 0); window.__dbg.ferries.freeze(null); });
});

test('up close, a ship whose stern is behind the camera is still found by the part of it on the screen', async ({ page }) => {
  await withBoats(page);
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  // Viking Line under way on open water; the camera 60 m from its middle (the closest the map comes), 45 degrees down,
  // lined up with the hull behind its stern, which is then behind the camera (the ship is 190 m long)
  const at = await page.evaluate(async () => {
    const D = window.__dbg, F = D.ferries;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const k = F.positions.findIndex(p => p && p.route === 'r9000004');
    for (let t = 0; t < 900; t += 3) {
      F.freeze(t);
      await frame();
      const p = F.positions[k];
      if (p.speed > 0.5 && p.alpha === 1 && p.x > 1800 && p.x < 3200) break;
    }
    const p = F.positions[k], dx = Math.cos(p.heading), dz = Math.sin(p.heading), r = 60 * Math.SQRT1_2;
    D.controls.target.set(p.x, 0, p.z);
    D.camera.position.set(p.x - dx * r, r, p.z - dz * r);
    D.controls.update();
    await frame();
    const V = D.camera.position.constructor;
    const stern = new V(p.x - dx * 95, 18, p.z - dz * 95).applyMatrix4(D.camera.matrixWorldInverse);
    const h = F.hullOnScreen(k, innerWidth, innerHeight);
    return { k, sternBehind: stern.z > -D.camera.near, dist: D.camera.position.distanceTo(D.controls.target),
      hull: !!h, x: h && Math.round(h.c[0]), y: h && Math.round(h.c[1]) };
  });
  expect(at.sternBehind).toBe(true);
  expect(at.dist).toBeLessThan(61);
  expect(at.hull).toBe(true);
  await page.mouse.move(at.x, at.y);
  await expect(tip(page).locator('.boat-title')).toHaveText('Viking Line');
  await page.evaluate(() => window.__dbg.ferries.freeze(null));
});

test('in Swedish the tooltip says linje, På väg mot and that the boat is not where it is drawn', async ({ page }) => {
  await withBoats(page);
  await open(page, '?lang=sv');
  await expect.poll(() => visible(page)).toBe(true);
  const out = await aimAt(page, 'r9000001', 1);
  await page.mouse.move(out.x, out.y);
  await expect(tip(page).locator('.boat-title')).toHaveText('Djurgårdsfärjan · linje 82');
  await expect(tip(page).locator('.boat-heading')).toHaveText('På väg mot Allmänna gränd');
  await expect(tip(page).locator('.boat-note')).toHaveText('Riktig linje, inte var båten är just nu');
  const ship = await aimAt(page, 'r9000005', 1, { dist: 1500 });
  await page.mouse.move(ship.x, ship.y);
  await expect(tip(page).locator('.boat-title')).toHaveText('Silja Line');
  await expect(tip(page).locator('.boat-heading')).toHaveText('På väg mot Åbo eller Helsingfors');   // Swedish names
  await expect(tip(page).locator('.boat-route')).toHaveText('Stockholm – Mariehamn – Åbo, Helsingfors');
  const home = await aimAt(page, 'r9000005', 0, { dist: 1500 });
  await page.mouse.move(home.x, home.y);
  await expect(tip(page).locator('.boat-heading')).toHaveText('På väg mot Stockholm');
});

test('a ferries.json without stops or ports still gives a boat its title and the note', async ({ page }) => {
  const old = JSON.parse(FIXTURE);
  for (const r of old.routes) { delete r.stops; delete r.home; delete r.dests; delete r.operator; }
  await withBoats(page, { body: JSON.stringify(old) });
  await open(page);
  await expect.poll(() => visible(page)).toBe(true);
  const out = await aimAt(page, 'r9000001', 1);
  await page.mouse.move(out.x, out.y);
  await expect(tip(page).locator('.boat-title')).toHaveText('Djurgårdsfärjan · line 82');
  await expect(tip(page).locator('.boat-note')).toHaveText('Real route, not a live position');
  await expect(tip(page).locator('.boat-route, .boat-heading')).toHaveCount(0);
  const ship = await aimAt(page, 'r9000004', 1, { dist: 1500 });
  await page.mouse.move(ship.x, ship.y);
  await expect(tip(page).locator('.boat-title')).toHaveText('Viking Line');
});

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('a tap on a boat shows its tooltip as a sheet, opens no building card, and goes at a tap elsewhere or with the boats', async ({ page }) => {
    const errors = watchErrors(page);
    await withBoats(page);
    await open(page);
    await expect.poll(() => visible(page)).toBe(true);
    const ship = await aimAt(page, 'r9000004', 1, { dist: 1500 });
    await page.touchscreen.tap(ship.x, ship.y);
    await expect(tip(page)).toBeVisible();
    await expect(tip(page).locator('.boat-title')).toHaveText('Viking Line');
    await expect(tip(page).locator('.boat-heading')).toHaveText('Heading for Turku or Helsinki');
    const box = await tip(page).boundingBox();
    expect(box.x).toBe(0);
    expect(box.width).toBe(390);
    expect(Math.round(box.y + box.height)).toBe(844);
    expect(await page.evaluate(() => window.__dbg.pinned)).toBe(-1);
    await expect(page.locator('#card')).toBeHidden();
    expect(await page.evaluate(() => window.__dbg.boatTip)).toMatchObject({ mode: 'tap' });

    const away = await emptyNear(page, ship);
    await page.touchscreen.tap(away.x, away.y);
    await expect(tip(page)).toBeHidden();

    // the sheet lies over the modes and the timeline: it takes a tap on it, which closes it, and nothing under it moves
    const state = () => page.evaluate(() => ({ year: window.__dbg.uniforms.uYear.value,
      modes: [...document.querySelectorAll('.modes button')].map(b => b.getAttribute('aria-pressed')) }));
    const inSheet = ({ x, y }) => page.evaluate(({ x, y }) => document.getElementById('boat-tip').contains(document.elementFromPoint(x, y)), { x, y });
    const was = await state();
    await page.touchscreen.tap(ship.x, ship.y);
    await expect(tip(page)).toBeVisible();
    const corner = { x: box.x + 30, y: box.y + box.height - 20 };   // over the timeline's Play button
    expect(await inSheet(corner)).toBe(true);
    await page.touchscreen.tap(corner.x, corner.y);
    await expect(tip(page)).toBeHidden();
    await frames(page, 4);
    expect(await state()).toEqual(was);
    expect(await visible(page)).toBe(true);
    await page.touchscreen.tap(ship.x, ship.y);
    await expect(tip(page)).toBeVisible();
    const mode = await page.evaluate(({ top }) => {      // a mode button under the sheet, not the one chosen
      const b = [...document.querySelectorAll('.modes button')].map(el => [el, el.getBoundingClientRect()])
        .find(([el, r]) => el.getAttribute('aria-pressed') !== 'true' && r.top > top && r.left > 0 && r.right < innerWidth);
      return b && { x: Math.round(b[1].left + b[1].width / 2), y: Math.round(b[1].top + b[1].height / 2) };
    }, { top: box.y });
    expect(mode).not.toBeNull();
    expect(await inSheet(mode)).toBe(true);
    await page.touchscreen.tap(mode.x, mode.y);
    await expect(tip(page)).toBeHidden();
    await frames(page, 4);
    expect(await state()).toEqual(was);

    // a card pinned another way (search, a walk's stop, a landmark: pinCard) takes the tooltip's place
    await page.touchscreen.tap(ship.x, ship.y);
    await expect(tip(page)).toBeVisible();
    const gid = await page.evaluate(() => { for (let g = 0; ; g++) if (window.__dbg.building(g).height > 10) return g; });
    await page.evaluate(g => window.__dbg.pinCard(g), gid);
    await expect(page.locator('#card.pinned')).toBeVisible();
    await expect(tip(page)).toBeHidden();
    await page.evaluate(() => window.__dbg.pinCard(-1));

    const ferry = await aimAt(page, 'r9000001', 0);
    await page.touchscreen.tap(ferry.x, ferry.y);
    await expect(tip(page).locator('.boat-heading')).toHaveText('Heading for Slussen');
    await page.evaluate(() => window.__dbg.setBoats(false));   // the boats hide: so does what a tap showed
    await expect(tip(page)).toBeHidden();
    await page.evaluate(() => { window.__dbg.setBoats(true); window.__dbg.ferries.freeze(null); });
    expect(errors).toEqual([]);
  });
});

test.describe('on a narrow phone', () => {
  test.use({ viewport: { width: 360, height: 780 }, isMobile: true, hasTouch: true });

  test('a long route\'s sheet stands in for the legend\'s handle instead of cutting through it', async ({ page }) => {
    const long = JSON.parse(FIXTURE);
    long.routes.find(r => r.id === 'r9000002').stops = ['Nybroplan', 'Allmänna gränd', 'Saltsjöqvarn', 'Finnboda hamn',
      'Kvarnholmen', 'Blockhusudden', 'Nacka strand', 'Lidingö/Dalénum', 'Frihamnen', 'Ropsten'];
    await withBoats(page, { body: JSON.stringify(long) });
    await open(page);
    await expect.poll(() => visible(page)).toBe(true);
    const handle = page.locator('.panel .sheet-handle');
    await expect(handle).toBeVisible();
    const hb = await handle.boundingBox();
    const boat = await aimAt(page, 'r9000002', 1);
    await page.touchscreen.tap(boat.x, boat.y);
    await expect(tip(page).locator('.boat-title')).toHaveText('Commuter boat · line 80');
    const box = await tip(page).boundingBox();
    expect(box.y).toBeLessThan(hb.y + hb.height);              // taller than its 156 px: it reaches the handle
    await expect(page.locator('.panel')).toBeHidden();
    const away = await emptyNear(page, boat);
    await page.touchscreen.tap(away.x, away.y);
    await expect(tip(page)).toBeHidden();
    await expect(handle).toBeVisible();
    await page.evaluate(() => window.__dbg.ferries.freeze(null));
  });
});
