// The terrain end to end: lifted buildings picked where they stand, a hill hiding what stands behind it in the
// pick pass, the flat fallback, the draw-call budget, the Hills slider and its memory, the camera on the ground,
// reduced motion and the names' depth test. Runs on whatever web/data/current.json points at (the fixture in CI, the
// city locally).
import { test, expect } from '@playwright/test';

function watchErrors(page, expected = () => false) {
  const errors = [];
  const add = e => { if (!expected(e)) errors.push(e); };
  page.on('pageerror', e => add(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') add(`console: ${m.text()} (${m.location().url})`); });
  page.on('response', r => { if (r.status() >= 400) add(`HTTP ${r.status()}: ${r.url()}`); });
  return errors;
}
const cityConfig = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  return (await fetch(`data/${version}/stockholm.json`)).json();
});
const terrain = page => page.evaluate(() => window.__dbg.terrain());
// The flat land (land.bin.gz): fetched only for a build without terrain, or once the terrain has failed.
function watchLand(page) {
  const land = { requested: 0, status: [] };
  const isLand = u => new URL(u).pathname.endsWith('/land.bin.gz');
  page.on('request', r => { if (isLand(r.url())) land.requested++; });
  page.on('response', r => { if (isLand(r.url())) land.status.push(r.status()); });
  return land;
}
// Loaded, the terrain in and risen to the slider's relief (window.__dbg.relief, the number asked for; 0 is flat). A
// terrain that failed is final: the wait ends there and the test fails at once, not after 60 s.
async function risen(page) {
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  const stands = async () => {
    const t = await terrain(page), r = await page.evaluate(() => window.__dbg.relief);
    return t.state === 'failed' ? 'failed' : t.state === 'ready' && Math.abs(t.relief - r) < 1e-6;
  };
  await expect.poll(stands, { timeout: 60_000 }).not.toBe(false);
  expect(await stands(), 'the terrain failed to load').toBe(true);
}
// ... and every tile in too.
async function settled(page) {
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect.poll(() => page.evaluate(() => { const s = window.__dbg.stats(); return s.tiles === s.tilesTotal; }),
    { timeout: 60_000 }).toBe(true);
  await risen(page);
}
const frames = (page, n = 2) => page.evaluate(n => new Promise(done => {
  const step = k => (k ? requestAnimationFrame(() => step(k - 1)) : done());
  step(n);
}), n);

// The pick pass draws the ground as nothing (id 0) with depth: a building behind a hill cannot be hovered or clicked.
// The test looks for one: a building, a camera 900 m off at 50 m over the ground, and a ridge the CPU heightfield says
// rises between them; flat, the same pixel must pick that building (so nothing else stands in the way), and from
// straight above with the relief on it must pick as itself (so it is the hill that hides it). At the slider's top
// (2.5x), as the camera test is: at the 1x default the fixture's hills are low enough that a small change in the
// City's data could leave none to find, and a build with terrain that has no such building fails (ALIGNMENT-4).
test('a hill hides the building behind it in the pick pass', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/?relief=2.5');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await settled(page);
  // the ground itself picks as nothing (-1): straight down from 300 m onto land 200 m from every building's centre
  const bare = await page.evaluate(async n => {
    const D = window.__dbg, cam = D.camera, ctl = D.controls;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const all = [];
    for (let g = 0; g < n; g++) all.push(D.building(g));
    for (const b of all) {
      for (let k = 0; k < 8; k++) {
        const x = b.x + 250 * Math.sin(k * Math.PI / 4), z = b.z + 250 * Math.cos(k * Math.PI / 4), y = D.surfaceAt(x, z);
        if (y < 5 || all.some(o => Math.hypot(o.x - x, o.z - z) < 200)) continue;
        ctl.target.set(x, y, z);
        cam.position.set(x, y + 300, z + 0.01);
        ctl.update();
        await frame();
        return { x, z, ground: y, id: D.pick(innerWidth / 2, innerHeight / 2) };
      }
    }
    return null;
  }, config.stats.buildings);
  expect(bare, 'no land 200 m from every building in this build').not.toBeNull();
  expect(bare.id, `straight down onto the ground at (${bare.x}, ${bare.z})`).toBe(-1);
  const found = await page.evaluate(async n => {
    const D = window.__dbg, cam = D.camera, ctl = D.controls;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const gids = [];
    for (let g = 0; g < n; g += Math.max(1, Math.floor(n / 2000))) gids.push(g);
    const at = (b, R) => ({ x: b.x, y: (R ? D.surfaceAt(b.x, b.z) : 0) + Math.min(b.height, 8) / 2, z: b.z });
    const screen = p => {
      const v = cam.position.clone().set(p.x, p.y, p.z).project(cam);
      return [(v.x + 1) / 2 * innerWidth, (1 - v.y) / 2 * innerHeight];
    };
    for (const g of gids) {
      const b = D.building(g);
      for (let k = 0; k < 8; k++) {
        const a = k * Math.PI / 4, cx = b.x + 900 * Math.sin(a), cz = b.z + 900 * Math.cos(a);
        const A = at(b, true), cy = D.surfaceAt(cx, cz) + 50;
        let ridge = false;
        for (let s = 0.1; s < 0.85 && !ridge; s += 0.02) {
          const px = cx + (A.x - cx) * s, pz = cz + (A.z - cz) * s, py = cy + (A.y - cy) * s;
          if (D.surfaceAt(px, pz) > py + 5) ridge = true;
        }
        if (!ridge) continue;
        // first from straight above, where nothing can hide it: the lifted building must pick as itself there
        ctl.target.set(b.x, A.y, b.z);
        cam.position.set(b.x, A.y + 300, b.z + 1);
        ctl.update();
        await frame();
        const above = D.pick(...screen(A));
        ctl.target.set(b.x, D.surfaceAt(b.x, b.z), b.z);
        cam.position.set(cx, cy, cz);
        ctl.update();
        await frame();
        const hidden = D.pick(...screen(at(b, true)));
        const R = D.relief;
        D.setRelief(0, false);
        ctl.target.set(b.x, 0, b.z);
        cam.position.set(cx, 50, cz);
        ctl.update();
        await frame();
        const flat = D.pick(...screen(at(b, false)));
        D.setRelief(R, false);
        await frame();
        if (flat === g) return { g, above, hidden, flat };
      }
    }
    return null;
  }, config.stats.buildings);
  expect(found, 'a building in this build that stands behind a hill from 900 m at 2.5x').not.toBeNull();
  expect(found.flat).toBe(found.g);
  expect(found.above).toBe(found.g);    // drawn and picked where it stands: so the hill, not a missing lift, hides it
  expect(found.hidden).not.toBe(found.g);
  // what the pixel picks instead is the hill (nothing, -1) or another building, never an id the ground made up
  expect(found.hidden === -1 || (found.hidden >= 0 && found.hidden < config.stats.buildings), `hidden ${found.hidden}`)
    .toBe(true);
  expect(errors).toEqual([]);
});

// Buildings are lifted onto their ground in the vertex shader: the building on the highest ground must be drawn and
// picked where it stands, seen from 300 m straight above, and again moved to 20 px inside the screen's left edge,
// where the pick pass's 1 x 1 frustum and the tile's culling box both meet it off-centre.
test('a lifted building is picked from straight above and at the edge of the screen', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await settled(page);
  const r = await page.evaluate(async n => {
    const D = window.__dbg, cam = D.camera, ctl = D.controls;
    ctl.enableDamping = false;   // the view stays where the test puts it
    // 30 frames: the target, put on the ground, settles there (it rides on the ground a quarter of the way per frame)
    const settle = async () => { for (let k = 0; k < 30; k++) await new Promise(done => requestAnimationFrame(done)); };
    const at = P => cam.position.clone().set(P.x, P.y, P.z);
    const screen = P => {
      const v = at(P).project(cam);
      return [(v.x + 1) / 2 * innerWidth, (1 - v.y) / 2 * innerHeight];
    };
    // the twenty buildings on the highest ground, of at least 6 m; the first whose centre lies on its own roof is used
    const high = [];
    for (let g = 0; g < n; g++) {
      const b = D.building(g);
      if (b.height >= 6) high.push({ g, b, s: D.surfaceAt(b.x, b.z) });
    }
    high.sort((a, c) => c.s - a.s);
    for (const { g, b, s } of high.slice(0, 20)) {
      const P = { x: b.x, y: s + b.height / 2, z: b.z };
      ctl.target.set(P.x, s, P.z);
      cam.position.set(P.x, s + 300, P.z + 1);
      ctl.update();
      await settle();
      if (D.pick(...screen(P)) !== g) continue;
      // move the view (camera and target together) by the offset from the point that shows 20 px inside the left
      // edge, at the building's depth, to the building; again once the target has settled on the new ground
      for (let k = 0; k < 4 && Math.abs(screen(P)[0] - 20) > 1; k++) {
        const q = at(P).project(cam);
        q.x = 40 / innerWidth - 1;
        const shift = at(P).sub(q.unproject(cam));
        cam.position.add(shift);
        ctl.target.add(shift);
        ctl.update();
        await settle();
      }
      const [ex, ey] = screen(P);
      return { g, high: s, edgeX: Math.round(ex), atEdge: D.pick(ex, ey) };
    }
    return null;
  }, config.stats.buildings);
  expect(r, 'none of the twenty buildings on the highest ground picked as itself from straight above').not.toBeNull();
  expect(r.high).toBeGreaterThan(5);
  expect(Math.abs(r.edgeX - 20)).toBeLessThanOrEqual(5);
  expect(r.atEdge).toBe(r.g);
  expect(errors).toEqual([]);
});

test('a terrain file that fails leaves the flat map, with a warning and no failure message', async ({ page }) => {
  const errors = watchErrors(page, e => /terrain\.bin\.gz/.test(e));
  const warnings = [];
  page.on('console', m => { if (m.type() === 'warning') warnings.push(m.text()); });
  await page.route('**/terrain.bin.gz', route => route.fulfill({ status: 404, body: 'Not found' }));
  const land = watchLand(page);
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect.poll(async () => (await terrain(page)).state, { timeout: 30_000 }).toBe('failed');
  await expect.poll(() => land.status, { timeout: 30_000, message: 'the flat land loads instead' }).toContain(200);
  await frames(page, 10);
  expect((await terrain(page)).relief).toBe(0);
  expect(await page.evaluate(() => window.__dbg.stats().terrainChunks)).toBe(0);
  // the flat land and water have no fog: the far plane stays at 60 km, where the terrain would follow the distance
  expect(await page.evaluate(() => window.__dbg.camera.far)).toBe(60_000);
  expect(warnings.some(w => w.startsWith('The terrain did not load'))).toBe(true);
  await page.locator('.look-open').click();
  const slider = page.locator('#look [data-relief]'), def = String(config.terrain.relief);
  await expect(slider).toHaveValue(def);   // the choice, not the map
  await expect(slider).toHaveAttribute('aria-disabled', 'true');
  await expect(page.locator('#relief-note')).toHaveText("The ground's heights did not load");
  await expect(page.locator('#look .relief-row')).toHaveCSS('opacity', '0.45');   // dimmed, as the legend's switches
  // disabled: moving it changes nothing and is not remembered, from the keyboard or a click on its far end (force:
  // Playwright itself waits on aria-disabled; a visitor can still reach the dimmed slider)
  await slider.focus();
  await page.keyboard.press('End');
  await expect(slider).toHaveValue(def);
  const box = await slider.boundingBox();
  await page.mouse.click(box.x + box.width - 2, box.y + box.height / 2);
  await expect(slider).toHaveValue(def);
  expect(await page.evaluate(() => [window.__dbg.relief, localStorage.getItem('hfh-relief')]))
    .toEqual([config.terrain.relief, null]);
  expect((await terrain(page)).relief).toBe(0);
  expect(errors).toEqual([]);
});

// The two give-up tests below place their checks from the moment the page asked (its 30 s timer starts then), read
// from a stamp the page sets in the page's own (fake) time: Playwright's clock keeps running in real time, and on the
// whole city the software frames between the ask and a check take a second or more of it, so a fixed
// fast-forward from "now" could pass 30 s. The early check is made 28 s after the ask, and proven to be before 30 s.
async function stampTerrainAsk(page, what) {
  await page.addInitScript(what => {
    if (what === 'worker') {
      const W = window.Worker;
      window.Worker = class extends W {
        constructor(url, ...rest) {
          super(url, ...rest);
          if (String(url).includes('terrain-worker')) window.__terrainAsked ??= Date.now();
        }
      };
    } else {
      const f = window.fetch;
      window.fetch = function (input, init) {
        if (String(input?.url ?? input).endsWith('terrain.bin.gz')) window.__terrainAsked ??= Date.now();
        return f.call(this, input, init);
      };
    }
  }, what);
}
const sinceAsked = page => page.evaluate(() => Date.now() - window.__terrainAsked);

// web/terrain.js askWorker: a terrain worker that never answers is given up on after WORKER_TIMEOUT_MS (30 s, run on
// Playwright's clock), so the map does not stay with its water but no land.
test('a terrain worker that never answers is given up on: the flat land loads and the map stays flat', async ({ page }) => {
  const errors = watchErrors(page);
  const warnings = [];
  page.on('console', m => { if (m.type() === 'warning') warnings.push(m.text()); });
  await page.route('**/terrain-worker.js', route => route.fulfill({ contentType: 'text/javascript', body: '// silent\n' }));
  const land = watchLand(page);
  await page.clock.install();
  await stampTerrainAsk(page, 'worker');
  const hung = page.waitForEvent('worker', { predicate: w => w.url().endsWith('/terrain-worker.js'), timeout: 60_000 });
  await page.goto('/');
  test.skip(!(await cityConfig(page)).terrain, 'this build has no terrain');
  await hung;
  await frames(page);
  expect((await terrain(page)).state).toBe('loading');
  expect(land.requested).toBe(0);
  await page.clock.fastForward(Math.max(0, 28_000 - await sinceAsked(page)));
  expect((await terrain(page)).state).toBe('loading');   // not given up on too early ...
  expect(await sinceAsked(page)).toBeLessThan(30_000);   // ... which was before the 30 s
  await page.clock.fastForward(3_000);
  await expect.poll(async () => (await terrain(page)).state, { timeout: 10_000 }).toBe('failed');
  await expect.poll(() => land.status, { timeout: 30_000, message: 'the flat land loads instead' }).toContain(200);
  expect((await terrain(page)).relief).toBe(0);
  expect(warnings.filter(w => w.startsWith('The terrain did not load'))).toHaveLength(1);
  expect(errors).toEqual([]);
});

// web/terrain.js withTimeout: a download of terrain.bin.gz that stalls is stopped after FETCH_TIMEOUT_MS (30 s, run on
// Playwright's clock), so the map does not stay with its water but no land.
test('a terrain download that stalls is given up on: the flat land loads and the map stays flat', async ({ page }) => {
  const errors = watchErrors(page, e => /terrain\.bin\.gz/.test(e));
  const warnings = [];
  page.on('console', m => { if (m.type() === 'warning') warnings.push(m.text()); });
  await page.route('**/terrain.bin.gz', () => {});   // asked for, never answered
  const land = watchLand(page);
  await page.clock.install();
  await stampTerrainAsk(page, 'download');
  const asked = page.waitForRequest(r => new URL(r.url()).pathname.endsWith('/terrain.bin.gz'), { timeout: 60_000 });
  await page.goto('/');
  test.skip(!(await cityConfig(page)).terrain, 'this build has no terrain');
  await asked;
  await frames(page);
  expect((await terrain(page)).state).toBe('loading');
  expect(land.requested).toBe(0);
  // while the ground is on its way the map is flat, and the line under the slider says so (VIEWER-3)
  await page.locator('.look-open').click();
  await expect(page.locator('#relief-note')).toHaveText('Loading the ground…');
  await expect(page.locator('#look [data-relief]')).not.toHaveAttribute('aria-disabled', 'true');
  await page.clock.fastForward(Math.max(0, 28_000 - await sinceAsked(page)));
  expect((await terrain(page)).state).toBe('loading');   // not given up on too early ...
  expect(await sinceAsked(page)).toBeLessThan(30_000);   // ... which was before the 30 s
  await page.clock.fastForward(3_000);
  await expect.poll(async () => (await terrain(page)).state, { timeout: 10_000 }).toBe('failed');
  await expect.poll(() => land.status, { timeout: 30_000, message: 'the flat land loads instead' }).toContain(200);
  expect((await terrain(page)).relief).toBe(0);
  await expect(page.locator('#relief-note')).toHaveText("The ground's heights did not load");
  expect(warnings.filter(w => w.startsWith('The terrain did not load'))).toHaveLength(1);
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  expect(errors).toEqual([]);
});

// The farthest the camera goes is 30 km (controls.maxDistance): there the whole city is in view, every tile, chunk, shore
// and wall group and the water (285 calls on the whole city at the worst angle, VIEWER-5); and viewAt clamps beyond it.
test('draw calls stay under 300 with the terrain, at home, from 20 km and from 30 km, the farthest', async ({ page }) => {
  const land = watchLand(page);
  await page.goto('/?debug=1');
  test.skip(!(await cityConfig(page)).terrain, 'this build has no terrain');
  await settled(page);
  expect(land.requested, 'with the terrain in, the flat land is never fetched').toBe(0);
  await frames(page, 4);
  const home = await page.evaluate(() => window.__dbg.stats());
  await page.evaluate(() => window.__dbg.viewAt(20000));
  await frames(page, 6);
  const far = await page.evaluate(() => window.__dbg.stats());
  // the farthest: 30 km, from straight down and tilted round the compass (a tilt shows the most at once)
  const farthest = await page.evaluate(async () => {
    const D = window.__dbg, ctl = D.controls, cam = D.camera, t = ctl.target;
    const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const out = [];
    for (const polar of [0.001, 0.6, 1.1]) {
      for (let k = 0; k < 4; k++) {
        const az = k * Math.PI / 2;
        cam.position.set(t.x + Math.sin(polar) * Math.sin(az), t.y + Math.cos(polar), t.z + Math.sin(polar) * Math.cos(az));
        ctl.update();
        D.viewAt(40000);   // clamped to controls.maxDistance
        await frame();
        await frame();
        out.push({ calls: D.stats().calls, dist: Math.round(cam.position.distanceTo(t)) });
      }
    }
    return out;
  });
  expect(home.calls).toBeLessThan(300);
  expect(far.calls).toBeLessThan(300);
  expect(far.terrainFar).toBe(far.terrainChunks);   // from 20 km every chunk draws its 40 m level
  for (const f of farthest) {
    expect(f.dist).toBeLessThanOrEqual(30_000);
    expect(f.calls).toBeLessThan(300);
  }
});

// The Hills slider as the page shows it, read in one go (on the whole city every round trip waits for a frame): its
// value, what it reads out, the value shown beside it and the line under it.
const sliderUi = page => page.evaluate(() => {
  const s = document.querySelector('#look [data-relief]');
  return [s.value, s.getAttribute('aria-valuetext'), document.getElementById('relief-value').textContent,
    document.getElementById('relief-note').textContent];
});

// The Hills slider (decided 2026-10-16), in the Look panel's Ground row: the ground at true height by default,
// scaled from flat (0) to the build's top (2.5) in steps of 0.5, with its value and a line saying what the map shows.
// It follows the relief however it changes, and moves with the keyboard while the map keeps its own arrow keys off it.
// At 0 the ground is flat and the camera's target back at sea level; the value is remembered on the device (the next
// two tests reload with it).
test('the ground rises after the first frame; the Hills slider scales it, from the keyboard too, and is remembered', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await risen(page);
  expect([config.terrain.relief, config.terrain.reliefMax]).toEqual([1, 2.5]);   // true heights; the slider's top
  expect(await terrain(page)).toMatchObject({ state: 'ready', relief: 1, source: config.terrain.source });
  expect((await page.evaluate(() => window.__dbg.stats())).terrainChunks).toBeGreaterThan(0);
  // where the map is: the target's and the camera's place (the ride moves only their heights)
  const where = () => page.evaluate(() => {
    const t = window.__dbg.controls.target, c = window.__dbg.camera.position;
    return [t.x, t.z, c.x, c.z];
  });
  const moved = (a, b) => Math.max(...a.map((v, i) => Math.abs(v - b[i])));

  await page.locator('.look-open').click();
  const slider = page.locator('#look [data-relief]');
  expect(await page.evaluate(() => {
    const row = document.querySelector('#look .look-relief'), s = row.querySelector('[data-relief]');
    return { role: row.getAttribute('role'), by: row.getAttribute('aria-labelledby'),
      title: document.getElementById('relief-title').textContent, type: s.type, range: [s.min, s.max, s.step],
      describedBy: s.getAttribute('aria-describedby') };
  })).toEqual({ role: 'group', by: 'relief-title', title: 'Ground', type: 'range', range: ['0', '2.5', '0.5'],
    describedBy: 'relief-note' });
  await expect(slider).toHaveAccessibleName('Hills');
  await expect(page.locator('#relief-value')).toBeVisible();
  expect(await sliderUi(page)).toEqual(['1', '1×', '1×', 'Ground heights true to scale']);
  // the slider, its value and its line follow the relief however it changes (app.js setRelief), not only from a move
  await page.evaluate(() => window.__dbg.setRelief(0, false));
  expect(await sliderUi(page)).toEqual(['0', 'Flat', 'Flat', 'Ground drawn flat']);
  await page.evaluate(() => window.__dbg.setRelief(2, false));
  expect(await sliderUi(page)).toEqual(['2', '2×', '2×', 'Ground heights exaggerated 2×']);
  await page.evaluate(() => window.__dbg.setRelief(1, false));
  expect(await sliderUi(page)).toEqual(['1', '1×', '1×', 'Ground heights true to scale']);
  expect(await page.evaluate(() => localStorage.getItem('hfh-relief'))).toBeNull();   // none of that was a choice

  // the keyboard: an arrow moves it a step, Home and End to its ends; the map stays where it is meanwhile. What the
  // slider shows after each move is recorded in the page, after the panel's own handler (one read at the end: on the
  // whole city every round trip waits for a frame).
  await slider.focus();
  const before = await where();
  await page.evaluate(() => {
    window.__moves = [];
    document.addEventListener('input', e => {
      const s = e.target;
      window.__moves.push([s.value, s.getAttribute('aria-valuetext'), document.getElementById('relief-value').textContent,
        document.getElementById('relief-note').textContent]);
    });
  });
  for (const key of ['ArrowRight', 'ArrowLeft', 'ArrowLeft', 'ArrowUp', 'End', 'ArrowDown', 'Home']) {
    await page.keyboard.press(key);
  }
  expect(await page.evaluate(() => window.__moves)).toEqual([
    ['1.5', '1.5×', '1.5×', 'Ground heights exaggerated 1.5×'],   // ArrowRight
    ['1', '1×', '1×', 'Ground heights true to scale'],              // ArrowLeft
    ['0.5', '0.5×', '0.5×', 'Ground heights reduced to 0.5×'],      // ArrowLeft
    ['1', '1×', '1×', 'Ground heights true to scale'],              // ArrowUp
    ['2.5', '2.5×', '2.5×', 'Ground heights exaggerated 2.5×'],     // End
    ['2', '2×', '2×', 'Ground heights exaggerated 2×'],              // ArrowDown
    ['0', 'Flat', 'Flat', 'Ground drawn flat'],                      // Home
  ]);
  await expect(slider).toBeFocused();
  // a language change redraws the panel and keeps the focus on the slider, with its Swedish name and strings (S4; the
  // language buttons are hidden in some builds, so the hidden button is pressed from the page)
  await page.evaluate(() => document.querySelector('.lang [data-lang="sv"]').click());
  await expect(slider).toBeFocused();
  await expect(slider).toHaveAccessibleName('Höjder');
  expect(await sliderUi(page)).toEqual(['0', 'Platt', 'Platt', 'Marken visas platt']);
  await page.evaluate(() => document.querySelector('.lang [data-lang="en"]').click());
  await expect(slider).toBeFocused();
  await expect(slider).toHaveAccessibleName('Hills');
  await frames(page, 4);
  expect(moved(await where(), before)).toBeLessThan(0.01);   // no arrow moved the map
  // ... which the same arrow does once the focus is off the slider (Escape gives it back to the Look button)
  await page.keyboard.press('Escape');
  await expect(page.locator('.look-open')).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await frames(page, 4);
  expect(moved(await where(), before)).toBeGreaterThan(5);
  // the relief follows the slider down to flat, remembered as the number; flat, the camera's target is back at sea
  // level wherever it is
  await expect.poll(async () => (await terrain(page)).relief).toBe(0);
  expect(await page.evaluate(() => localStorage.getItem('hfh-relief'))).toBe('0');
  await expect.poll(() => page.evaluate(() => Math.abs(window.__dbg.controls.target.y)), { timeout: 5_000 }).toBeLessThan(0.05);
  expect(errors).toEqual([]);
});

// A link's ?relief= beats the remembered value: a number is that relief, clamped to the slider's top (off and on are
// relief.test.mjs's). Moving the slider outranks the link it was made on: ?relief= leaves the address, so a reload
// keeps the move, remembered as the number.
test('a link\'s ?relief= sets the Hills slider until it is moved, which drops it from the address', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/?relief=9');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await risen(page);
  expect((await terrain(page)).relief).toBe(config.terrain.reliefMax);
  await page.goto('/?relief=1.5&theme=kalk');
  await risen(page);
  expect((await terrain(page)).relief).toBe(1.5);
  await page.locator('.look-open').click();
  expect(await sliderUi(page)).toEqual(['1.5', '1.5×', '1.5×', 'Ground heights exaggerated 1.5×']);
  expect(new URL(page.url()).search).toBe('?relief=1.5&theme=kalk');
  await page.locator('#look [data-relief]').focus();
  await page.keyboard.press('ArrowRight');
  expect(await sliderUi(page)).toEqual(['2', '2×', '2×', 'Ground heights exaggerated 2×']);
  expect(new URL(page.url()).search).toBe('?theme=kalk');
  expect(await page.evaluate(() => localStorage.getItem('hfh-relief'))).toBe('2');
  await page.reload();
  await risen(page);
  expect((await terrain(page)).relief).toBe(2);
  expect(errors).toEqual([]);
});

// The relief switch before the slider remembered 'off' or 'on': off stays flat, on is now the default (1x).
test('a device that remembered the old relief switch keeps flat for off and gets the default for on', async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() => {   // before the first load only, so the reload below reads what the test sets
    if (sessionStorage.getItem('seeded')) return;
    sessionStorage.setItem('seeded', '1');
    localStorage.setItem('hfh-relief', 'off');
  });
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await risen(page);
  await frames(page, 10);
  expect((await terrain(page)).relief).toBe(0);
  await page.evaluate(() => localStorage.setItem('hfh-relief', 'on'));
  await page.reload();
  await risen(page);
  expect((await terrain(page)).relief).toBe(config.terrain.relief);
  await page.locator('.look-open').click();
  await expect(page.locator('#look [data-relief]')).toHaveValue(String(config.terrain.relief));
  expect(errors).toEqual([]);
});

// On a touch screen the Hills slider takes a tap a little outside what is drawn, as the corner buttons do: a
// 44 px band, over the heading above it and the line under it (which take no tap); its row keeps its 24 px.
test('on a touch screen the Hills slider takes a tap in a 44 px band, its row at the same drawn size', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const errors = watchErrors(page);
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await risen(page);
  expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
  await page.locator('.look-open').tap();
  const slider = page.locator('#look [data-relief]');
  await expect(slider).toHaveValue('1');
  const hit = await slider.evaluate(s => {
    const r = s.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    const at = dy => document.elementFromPoint(x, y + dy) === s;
    return { height: Math.round(r.height), row: Math.round(s.parentElement.getBoundingClientRect().height),
      above: at(-21), below: at(21), farAbove: at(-24), farBelow: at(24) };
  });
  expect(hit).toEqual({ height: 44, row: 24, above: true, below: true, farAbove: false, farBelow: false });
  // a real touch at the far end, 18 px under the slider's middle: the top of the scale
  const box = await slider.boundingBox();
  await page.touchscreen.tap(box.x + box.width - 2, box.y + box.height / 2 + 18);
  await expect(slider).toHaveValue('2.5');
  await expect.poll(async () => (await terrain(page)).relief).toBe(2.5);
  expect(errors).toEqual([]);
  await context.close();
});

// A phone held sideways (VIEWER-1): the Look popover is taller than a 360 px screen with the Ground row, so it scrolls
// (max-height and overflow, styles.css), and the Hills slider and its line can be scrolled into view and used there.
test('on a landscape phone the Look panel scrolls to the Hills slider and its line', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 740, height: 360 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const errors = watchErrors(page);
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await risen(page);
  await page.locator('.look-open').tap();
  const panel = page.locator('#look'), slider = page.locator('#look [data-relief]'), note = page.locator('#relief-note');
  const inside = await panel.evaluate(p => {
    const r = p.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom, scrolls: p.scrollHeight > p.clientHeight, overflow: getComputedStyle(p).overflowY };
  });
  expect(inside.bottom).toBeLessThanOrEqual(360);          // the panel itself stays on the screen ...
  expect(inside).toMatchObject({ scrolls: true, overflow: 'auto' });   // ... and scrolls
  await note.scrollIntoViewIfNeeded();
  for (const el of [slider, note]) {
    const box = await el.boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(inside.top);
    expect(box.y + box.height).toBeLessThanOrEqual(Math.min(360, inside.bottom) + 0.5);
  }
  await expect(note).toHaveText('Ground heights true to scale');
  const box = await slider.boundingBox();
  await page.touchscreen.tap(box.x + box.width - 2, box.y + box.height / 2);
  await expect(slider).toHaveValue('2.5');
  await expect.poll(async () => (await terrain(page)).relief).toBe(2.5);
  expect(errors).toEqual([]);
  await context.close();
});

// A short desktop window (1280 x 400): the popover's top sits lower there (about 165 px), and it still ends on the screen
// and scrolls to the Ground row (the scoped re-review of VIEWER-1).
test('in a short desktop window the Look popover ends on the screen and scrolls to the Hills slider', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 400 } });
  const page = await context.newPage();
  const errors = watchErrors(page);
  await page.goto('/');
  test.skip(!(await cityConfig(page)).terrain, 'this build has no terrain');
  await risen(page);
  await page.locator('.look-open').click();
  const panel = await page.locator('#look').evaluate(p => ({ bottom: p.getBoundingClientRect().bottom,
    scrolls: p.scrollHeight > p.clientHeight }));
  expect(panel.bottom).toBeLessThanOrEqual(400);
  expect(panel.scrolls).toBe(true);
  await page.locator('#relief-note').scrollIntoViewIfNeeded();
  const note = await page.locator('#relief-note').boundingBox();
  expect(note.y + note.height).toBeLessThanOrEqual(Math.min(400, panel.bottom) + 0.5);
  expect(errors).toEqual([]);
  await context.close();
});

// A build without terrain (stockholm.json with no terrain block, as in older builds or a city without heights): the flat
// land and water, no Ground row, the far plane at 60 km and the state 'flat', with no error (ALIGNMENT-3).
test('a build without terrain draws the flat map with no Ground row', async ({ page }) => {
  const errors = watchErrors(page);
  const land = watchLand(page);
  let terrainAsked = 0;
  page.on('request', r => { if (new URL(r.url()).pathname.endsWith('/terrain.bin.gz')) terrainAsked++; });
  await page.route('**/stockholm.json', async route => {
    const res = await route.fetch();
    const cfg = await res.json();
    delete cfg.terrain;
    await route.fulfill({ response: res, json: cfg });
  });
  await page.goto('/');
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect.poll(() => land.status, { timeout: 30_000, message: 'the flat land loads' }).toContain(200);
  await frames(page, 6);
  expect(await terrain(page)).toMatchObject({ state: 'flat', relief: 0, chunks: 0 });
  expect(await page.evaluate(() => window.__dbg.camera.far)).toBe(60_000);
  await page.locator('.look-open').click();
  await expect(page.locator('#look .look-card').first()).toBeVisible();
  expect(await page.locator('#look [data-relief], #relief-title').count()).toBe(0);
  expect(terrainAsked).toBe(0);
  expect(errors).toEqual([]);
});

// The camera on the ground (app.js followGround). Flights land on it. Then three scenes, found on this build's own
// terrain and kept inside the controls' tilt limit (0.47π: a camera pushed under its target is lifted by the controls
// themselves, which would hide a missing floor): (a) the floor keeps the camera 20 m over a hill that rises in front
// of it, (b) its ring keeps it 20 m over a cliff that rises beside it, (c) the ride moves target and camera together
// when the relief changes, so the tilt and the distance stay. Every frame drawn meanwhile looks at the target, the
// frames a lift happens in included. The scenes need steep ground: a rise of over 50 m within 190 m and within 30 m.
// They were written when 2.5x was the default; at today's 1x the fixture's steepest rises are 48.5 m and 28 m
// (scene (a) then fails; the whole city's are 88 m and 61 m), so the test asks for the slider's top, 2.5x (121 m and
// 70 m on the fixture), and (c) lays it flat from there.
test('the camera rides on the ground: flights land on it, the floor and its ring keep it clear, aimed at the target', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/?relief=2.5');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await settled(page);
  // the building on the highest ground: its flight must end with the target on the ground there
  const r = await page.evaluate(n => new Promise(done => {
    const D = window.__dbg;
    let best = null;
    for (let g = 0; g < n; g++) {
      const b = D.building(g), s = D.surfaceAt(b.x, b.z);
      if (!best || s > best.s) best = { g, s, x: b.x, z: b.z };
    }
    D.flyTo(best.x, best.z, () => requestAnimationFrame(() => {
      const t = D.controls.target, c = D.camera.position;
      done({ high: best.s, target: t.y - D.surfaceAt(t.x, t.z), clearance: c.y - D.surfaceAt(c.x, c.z) });
    }), 300);
  }), config.stats.buildings);
  expect(r.high).toBeGreaterThan(5);
  expect(Math.abs(r.target)).toBeLessThan(0.5);
  expect(r.clearance).toBeGreaterThan(19);

  // from here on, for every frame drawn: how far the view looks off the target, in degrees
  await page.evaluate(() => {
    const D = window.__dbg, scene = D.labelGroup.parent;
    window.__offAim = 0;
    scene.onBeforeRender = (renderer, s, camera) => {
      const to = D.controls.target.clone().sub(camera.position);
      window.__offAim = Math.max(window.__offAim, camera.getWorldDirection(to.clone()).angleTo(to) * 180 / Math.PI);
    };
  });
  // The steepest rise of the ground over `run` metres, from a point of the grid in one of the floor ring's eight
  // directions.
  const steepest = run => page.evaluate(([run, T]) => {
    const S = window.__dbg.surfaceAt, x1 = T.x0 + (T.nx - 1) * T.cell, z1 = T.z0 + (T.nz - 1) * T.cell;
    const step = Math.max(T.cell, (x1 - T.x0) / 300);
    let best = null;
    for (let x = T.x0 + 400; x < x1 - 400; x += step) {
      for (let z = T.z0 + 400; z < z1 - 400; z += step) {
        for (let k = 0; k < 8; k++) {
          const dx = Math.cos(k * Math.PI / 4), dz = Math.sin(k * Math.PI / 4), rise = S(x + run * dx, z + run * dz) - S(x, z);
          if (!best || rise > best.rise) best = { x, z, dx, dz, rise };
        }
      }
    }
    return best;
  }, [run, config.terrain]);
  // places the target on the ground at `t` and the camera at `c` (x, z and a height over the target's ground); gives
  // the camera's height as placed, before any frame
  const place = (t, c) => page.evaluate(([t, c]) => {
    const D = window.__dbg, y = D.surfaceAt(t.x, t.z);
    D.controls.target.set(t.x, y, t.z);
    D.camera.position.set(c.x, y + c.up, c.z);
    D.controls.update();
    return D.camera.position.y;
  }, [t, c]);
  const camera = () => page.evaluate(() => {
    const D = window.__dbg, c = D.camera.position, t = D.controls.target;
    return { x: c.x, y: c.y, z: c.z, ground: D.surfaceAt(c.x, c.z), dist: c.distanceTo(t), polar: D.controls.getPolarAngle() };
  });

  // (a) A hill rises between the target at its foot and the camera, 190 m off at 30 m over the target (a tilt of 81°):
  // the floor lifts the camera to 20 m over the hill.
  const hill = await steepest(190);
  expect(hill.rise, 'a hill rising over 50 m within 190 m').toBeGreaterThan(50);
  await place(hill, { x: hill.x + 190 * hill.dx, z: hill.z + 190 * hill.dz, up: 30 });
  await frames(page, 4);
  const a = await camera();
  expect(a.y - a.ground).toBeGreaterThanOrEqual(19.9);

  // (b) A cliff rises right beside the camera, which stands on the low ground at its foot, 25 m up, looking away
  // across the low ground: the ground under it alone would leave it there; the ring (30 m out) lifts it to 20 m over
  // the cliff.
  const cliff = await steepest(30);
  const b0 = await page.evaluate(q => {
    const S = window.__dbg.surfaceAt;
    let ring = -Infinity;
    for (let k = 0; k < 8; k++) ring = Math.max(ring, S(q.x + 30 * Math.cos(k * Math.PI / 4), q.z + 30 * Math.sin(k * Math.PI / 4)));
    const tx = q.x - 190 * q.dx, tz = q.z - 190 * q.dz, under = S(q.x, q.z), ty = S(tx, tz);
    return { tx, tz, under, ring, up: Math.max(under + 25, ty + 35) - ty };   // at least 35 m over the target: inside the tilt limit
  }, cliff);
  expect(b0.ring - b0.under, 'a cliff rising over 50 m within 30 m').toBeGreaterThan(50);
  const y0 = await place({ x: b0.tx, z: b0.tz }, { x: cliff.x, z: cliff.z, up: b0.up });
  expect(y0, 'the camera starts well under the ring\'s floor').toBeLessThan(b0.ring + 20 - 30);
  await frames(page, 4);
  const b = await camera();
  expect(b.dist).toBeLessThan(600);   // so the ring stays at 30 m
  expect(b.y).toBeGreaterThanOrEqual(b0.ring + 20 - 0.1);

  // (c) The relief laid flat: target and camera ride down together, so the tilt and the distance stay as they were.
  await place({ x: hill.x + 190 * hill.dx, z: hill.z + 190 * hill.dz }, { x: hill.x + 190 * hill.dx + 150, z: hill.z + 190 * hill.dz, up: 200 });
  await frames(page, 4);
  const c0 = { ...(await camera()), target: await page.evaluate(() => window.__dbg.controls.target.y) };
  await page.evaluate(() => window.__dbg.chooseRelief(0));   // as the slider moved to Flat
  await expect.poll(() => page.evaluate(() => {
    const D = window.__dbg, t = D.controls.target;
    return D.terrain().relief === 0 && Math.abs(t.y - D.surfaceAt(t.x, t.z)) <= 0.001;
  }), { timeout: 30_000 }).toBe(true);
  const c1 = { ...(await camera()), target: await page.evaluate(() => window.__dbg.controls.target.y) };
  expect(c0.target - c1.target).toBeGreaterThan(5);
  expect(c1.polar).toBeCloseTo(c0.polar, 6);
  expect(c1.dist).toBeCloseTo(c0.dist, 3);

  expect(await page.evaluate(() => window.__offAim)).toBeLessThan(0.2);
  expect(errors).toEqual([]);
});

// The near and far planes follow the distance once the terrain is in (app.js followGround): near 2% of it (2 m to
// 400 m), far 4.5 times it (at least 4 km), each changed only when it is 10% off.
test('the near and far planes follow the distance: from 60 m, at home and from 30 km', async ({ page }) => {
  await page.goto('/');
  test.skip(!(await cityConfig(page)).terrain, 'this build has no terrain');
  await settled(page);
  const planes = async d => {
    await page.evaluate(d => (d ? window.__dbg.viewAt(d) : window.__dbg.goHome()), d);
    await frames(page, 4);
    return page.evaluate(() => {
      const D = window.__dbg, c = D.camera;
      return { near: c.near, far: c.far, dist: c.position.distanceTo(D.controls.target) };
    });
  };
  const close = await planes(60);
  expect(close).toMatchObject({ near: 2, far: 4000 });
  const home = await planes(0);
  expect(Math.abs(home.near / (0.02 * home.dist) - 1)).toBeLessThan(0.1);
  expect(Math.abs(home.far / (4.5 * home.dist) - 1)).toBeLessThan(0.1);
  const far = await planes(30_000);
  expect(far.near).toBe(400);
  expect(Math.abs(far.far / (4.5 * far.dist) - 1)).toBeLessThan(0.1);
});

// Names stand where they are drawn (app.js labelY) and three.js culls them like everything else: looking along a hill,
// every name whose middle shows on screen is drawn, and none that lies wholly behind the camera.
test('names on a hill are drawn where they show, and culled behind the camera', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await settled(page);
  await expect.poll(() => page.evaluate(() => window.__dbg.labels.length), { timeout: 30_000 }).toBeGreaterThan(0);
  const r = await page.evaluate(async T => {
    const D = window.__dbg, S = D.surfaceAt;
    const frame = () => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
    const x1 = T.x0 + (T.nx - 1) * T.cell, z1 = T.z0 + (T.nz - 1) * T.cell;
    const hills = D.labels.filter(l => !l.L.water && l.x > T.x0 && l.x < x1 && l.z > T.z0 && l.z < z1 && S(l.x, l.z) > 30)
      .sort((a, b) => S(b.x, b.z) - S(a.x, a.z)).slice(0, 10);
    for (const h of hills) {
      // a name on the hill at the middle of the view, from 120 m off and 25 m over it
      const y = S(h.x, h.z);
      D.controls.target.set(h.x, y, h.z);
      D.camera.position.set(h.x + 120, y + 25, h.z);
      D.controls.update();
      for (let k = 0; k < 8; k++) await frame();   // updateLabels runs every sixth frame
      const shown = D.labels.filter(l => l.mesh?.visible && !l.L.water), drawn = new Set();
      for (const l of shown) l.mesh.onBeforeRender = () => drawn.add(l);
      await frame();
      const cam = D.camera, ahead = cam.getWorldDirection(cam.position.clone());
      const out = { name: h.L.name, onScreen: 0, onHill: 0, behind: 0, wrong: [] };
      for (const l of shown) {
        if (!l.mesh.visible) continue;
        const p = cam.position.clone().set(l.x, S(l.x, l.z) + 0.6, l.z), along = p.clone().sub(cam.position).dot(ahead);
        const v = p.clone().project(cam);
        if (along > 0 && Math.abs(v.x) < 0.9 && Math.abs(v.y) < 0.9) {
          out.onScreen++;
          if (S(l.x, l.z) > 30) out.onHill++;
          if (!drawn.has(l)) out.wrong.push(`${l.L.name}: on screen, not drawn`);
        }
        if (along < -l.mesh.scale.x) {
          out.behind++;
          if (drawn.has(l)) out.wrong.push(`${l.L.name}: behind the camera, drawn`);
        }
      }
      if (out.onHill && out.behind) return out;
    }
    return null;
  }, config.terrain);
  expect(r, 'a view along a hill with names on it, and names behind the camera too').not.toBeNull();
  expect(r.wrong).toEqual([]);
  expect(errors).toEqual([]);
});

test('with reduced motion the ground is there at once; names keep their depth test unless ?labels=top; ?edgebuildings=1', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  const page = await context.newPage();
  await page.goto('/');
  const config = await cityConfig(page);
  test.skip(!config.terrain, 'this build has no terrain');
  await page.waitForFunction(() => ['ready', 'failed'].includes(window.__dbg?.terrain().state), null, { timeout: 60_000 });
  expect((await terrain(page)).state, 'the terrain failed to load').toBe('ready');
  expect((await terrain(page)).relief).toBe(config.terrain.relief);
  // a move of the slider is at once too: flat in the same task, no easing (S2)
  expect(await page.evaluate(() => { window.__dbg.chooseRelief(0); return window.__dbg.terrain().relief; })).toBe(0);
  await page.evaluate(() => window.__dbg.chooseRelief(1));
  await page.evaluate(() => localStorage.removeItem('hfh-relief'));
  await expect.poll(() => page.evaluate(() => window.__dbg.labels.filter(l => l.mesh).length), { timeout: 15_000 })
    .toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__dbg.labels.find(l => l.mesh).mesh.material.depthTest)).toBe(true);
  // the ride is at once too: a target lifted 50 m off the ground (and the camera with it) is back on it a frame later
  const gap = await page.evaluate(() => new Promise(done => {
    const D = window.__dbg, t = D.controls.target;
    t.y += 50;
    D.camera.position.y += 50;
    requestAnimationFrame(() => requestAnimationFrame(() => done(Math.abs(t.y - D.surfaceAt(t.x, t.z)))));
  }));
  expect(gap).toBeLessThanOrEqual(0.001);
  expect(await page.evaluate(() => window.__dbg.uniforms.uEdgeBuildings.value)).toBe(0);
  await page.goto('/?labels=top&edgebuildings=1');
  await expect.poll(() => page.evaluate(() => window.__dbg.labels.filter(l => l.mesh).length), { timeout: 60_000 })
    .toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__dbg.labels.find(l => l.mesh).mesh.material.depthTest)).toBe(false);
  expect(await page.evaluate(() => window.__dbg.uniforms.uEdgeBuildings.value)).toBe(1);
  await context.close();
});
