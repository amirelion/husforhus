// Boats on the map (web/ferries.js, web/ferries-layer.js): the city's ferries and the Baltic ships on their routes, on by
// default but only at Today. The data has no ferries.json yet, so every test serves a fixture (e2e/fixtures/ferries.json,
// five routes on the water round Gamla stan, Slussen and Skeppsholmen) and switches features.ferries on in
// stockholm.json. Covered: the boats at Today and not for an earlier year, the film or a story; the Look panel's
// "Boats" switch (remembered, no dot while on, its hint that they show at Today, its Swedish name); About's line that
// they are not live, only while the map has boats; boats that arrive while a panel is open; no boats without drawn
// water; the pick pass (a boat over a building never hides the building from a click); reduced motion; draw calls.
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { settled } from './settled.mjs';

const FIXTURE = readFileSync(new URL('./fixtures/ferries.json', import.meta.url), 'utf8');
const BOATS = 8;   // two on each of the three ferry lines (each 1 km or longer), one on each ship lane

// hold(): a promise ferries.json waits for, so a test can open a panel before the boats arrive.
async function withBoats(page, { scenes = false, hold = () => null } = {}) {
  await page.route('**/ferries.json', async r => {
    await hold();
    await r.fulfill({ contentType: 'application/json', body: FIXTURE });
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

test('a boat over a building never takes the click: the pick pass leaves the boats out', async ({ page }) => {
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
        await frame();
        await frame();
        out.push({ calls: D.stats().calls, boats: D.ferries.visible, scale: Math.max(...D.ferries.positions.map(p => p.scale)) });
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
