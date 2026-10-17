// The launch video's raw clips, recorded from the real viewer with Playwright's recordVideo: each clip its own file,
// landscape 1920×1080 and portrait 1080×1350, driven by scripted camera moves through window.__dbg. Needs Node 22+,
// `npm ci`, `npx playwright install chromium` and a server of this checkout, on any port but 8642:
//   python3 scripts/serve.py 8653
//   node scripts/record/clips.mjs [out] [--url http://127.0.0.1:8653/] [--clips timeline,hills] [--formats landscape]
//   out        the folder the videos go to (default /tmp/hfh-clips); never a folder inside this repository
//   --url      the running site (default http://127.0.0.1:$HFH_PORT/, HFH_PORT 8653)
//   --clips    a comma list of clips (default: all, see CLIPS below and scripts/record/README.md)
//   --formats  landscape, portrait or both (default landscape,portrait)
// Writes <out>/<nn>-<clip>-<format>.webm. The video starts when the page starts loading: the seconds before the clip's
// first frame are written to <out>/<nn>-<clip>-<format>.json (`trimStart`), and when ffmpeg is on the PATH the file is
// cut there and kept as .webm. The cursor is hidden; a drawn one shows only for the clicks and drags that matter.
import { mkdirSync, renameSync, writeFileSync, rmSync, realpathSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

function usage(message) {
  console.error(`clips.mjs: ${message}`);
  process.exit(2);
}
const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  const v = args[i + 1];
  if (v === undefined || v.startsWith('--')) usage(`${name} needs a value`);
  args.splice(i, 2);
  return v;
};
const PORT = Number(process.env.HFH_PORT) || 8653;
if (PORT === 8642) usage('8642 is the preview server of the main checkout: pick another HFH_PORT');
const base = opt('--url', `http://127.0.0.1:${PORT}/`);
let basePort;
try { basePort = new URL(base).port; } catch { usage(`--url is not a URL: "${base}"`); }
if (basePort === '8642') usage('8642 is the preview server of the main checkout: pick another --url');
const clipNames = opt('--clips', '');
const formatNames = opt('--formats', 'landscape,portrait').split(',');
if (args.some(a => a.startsWith('--'))) usage(`unknown option ${args.find(a => a.startsWith('--'))}`);
if (args.length > 1) usage('one out folder at most');
const out = path.resolve(args[0] || '/tmp/hfh-clips');
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const inside = (dir, root) => { const r = path.relative(root, dir); return !r.startsWith('..') && !path.isAbsolute(r); };
const realOr = p => { try { return realpathSync(p); } catch { return p; } };
if (inside(out, REPO) || inside(realOr(path.dirname(out)), realOr(REPO))) usage(`${out} is inside the repository: pick a folder outside it`);

const FORMATS = { landscape: { width: 1920, height: 1080 }, portrait: { width: 1080, height: 1350 } };
for (const f of formatNames) if (!Object.hasOwn(FORMATS, f)) usage(`unknown format "${f}" (known: landscape, portrait)`);

// ---------- In the page: the drawn cursor and the camera moves ----------
// Added before the page's own scripts. Real mouse events drive the app; the drawn cursor only follows them.
function recorderInit() {
  addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent = `*, *::before, *::after { cursor: none !important; }
      #rec-cursor { position: fixed; z-index: 2147483647; left: 0; top: 0; width: 22px; height: 22px; pointer-events: none;
        transition: opacity .25s, transform .12s; opacity: 0; }
      #rec-cursor.down { transform: scale(.85); }`;
    document.head.append(style);
    const c = document.createElement('div');
    c.id = 'rec-cursor';
    c.innerHTML = '<svg viewBox="0 0 22 22" width="22" height="22"><path d="M3 2l0 16 4.5-4 3 6.5 3-1.4-3-6.4 6-.2z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.body.append(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX - 3 + 'px'; c.style.top = e.clientY - 2 + 'px'; }, true);
    addEventListener('mousedown', () => c.classList.add('down'), true);
    addEventListener('mouseup', () => c.classList.remove('down'), true);
  });
  const ease = k => (k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2);
  const frames = (ms, step) => new Promise(resolve => {
    const t0 = performance.now();
    const tick = now => { const k = Math.min(1, (now - t0) / ms); step(k); k < 1 ? requestAnimationFrame(tick) : resolve(); };
    requestAnimationFrame(tick);
  });
  window.__rec = {
    cursor(on) { const c = document.getElementById('rec-cursor'); if (c) c.style.opacity = on ? 1 : 0; },
    // Turns the camera round its target by `degrees` (and its distance by `zoom`, 0.9 = 10 % closer) in `ms`.
    orbit(ms, degrees, zoom = 1, linear = false) {
      const { camera, controls } = window.__dbg;
      const off = camera.position.clone().sub(controls.target);
      const r0 = Math.hypot(off.x, off.z), a0 = Math.atan2(off.x, off.z), y0 = off.y;
      return frames(ms, k => {
        const e = linear ? k : ease(k), a = a0 + (degrees * Math.PI / 180) * e, s = 1 + (zoom - 1) * e;
        camera.position.set(controls.target.x + r0 * s * Math.sin(a), controls.target.y + y0 * s, controls.target.z + r0 * s * Math.cos(a));
        camera.lookAt(controls.target);
      });
    },
    // A building's centre on screen, or null when it is behind the camera.
    screenOf(x, z) {
      const { camera, surfaceAt } = window.__dbg;
      const v = new camera.position.constructor(x, surfaceAt(x, z) + 6, z).project(camera);
      if (v.z > 1) return null;
      return [Math.round((v.x + 1) / 2 * innerWidth), Math.round((1 - v.y) / 2 * innerHeight)];
    },
    // The flight lasts 1.4 s; a flight that another move cancelled never calls back, so 3 s is the most it waits.
    flyTo: (x, z, distance) => new Promise(resolve => { window.__dbg.flyTo(x, z, resolve, distance); setTimeout(resolve, 3000); }),
  };
}

// ---------- Helpers on the Node side ----------
const wait = ms => new Promise(r => setTimeout(r, ms));
async function settle(page) {
  const at = () => page.evaluate(() => { const p = window.__dbg.camera.position; return `${Math.round(p.x)},${Math.round(p.y)},${Math.round(p.z)}`; });
  for (let i = 0; i < 100; i++) { const a = await at(); await wait(300); if (a === await at()) return; }
}
// Moves the drawn cursor in, so a click is seen, and hides it after.
async function visibleClick(page, x, y, { hold = 0 } = {}) {
  const vp = page.viewportSize();
  await page.mouse.move(vp.width * 0.62, vp.height * 0.78);
  await page.evaluate(() => window.__rec.cursor(true));
  await page.mouse.move(x, y, { steps: 30 });
  await wait(250);
  await page.mouse.down(); await wait(90 + hold); await page.mouse.up();
}
const hideCursor = page => page.evaluate(() => window.__rec.cursor(false));
async function centreOf(locator) {
  const b = await locator.boundingBox();
  if (!b) throw new Error('not on screen');
  return [b.x + b.width / 2, b.y + b.height / 2, b];
}
// Every card of the build ({gid: card}), from the 64 shards (as e2e/card.spec.mjs reads them).
const cards = page => page.evaluate(async () => {
  const { version } = await (await fetch('data/current.json')).json();
  const shards = await Promise.all([...Array(64).keys()].map(async k =>
    (await fetch(`data/${version}/cards/${String(k).padStart(2, '0')}.json`)).json()));
  return Object.assign({}, ...shards);
});
const goHome = (page, h) => page.evaluate(h => window.__dbg.goHome(h), h);

// ---------- The clips ----------
// Places are local metres (x east, z south; Stortorget is 0, 0), framed as scripts/look.mjs's views are.
const CLIPS = {
  // 1. The film plays the city's growth from the first year to today over Gamla stan and the Norrström, the camera
  //    slowly turning.
  timeline: {
    seconds: 15, query: '?film=13',
    async run(page) {
      await goHome(page, { x: 0, z: -220, azimuth: 205, elevation: 30, span: 1700 });
      await settle(page);
      await page.evaluate(() => { window.__dbg.uniforms.uYear.value = 1e4; });   // at "today", so the film starts again
      await page.evaluate(() => window.__dbg.startPlay());
      await page.evaluate(() => window.__rec.orbit(14500, 28, 0.82));
    },
  },
  // 2. The Hills slider dragged from flat to 2.5× with the camera low at Söder's cliffs (Skinnarviksberget and
  //    Mariaberget from Riddarfjärden).
  hills: {
    seconds: 12,
    async run(page) {
      const has = await page.evaluate(() => !!window.__dbg.terrain().source);
      if (!has) console.warn('  hills: this build has no terrain; the slider is not there');
      await page.evaluate(() => window.__dbg.chooseRelief(0));
      await goHome(page, { x: -860, z: 620, azimuth: 195, elevation: 7, span: 1000 });
      await settle(page);
      await page.locator('.look-open').click();
      const range = page.locator('#relief-range');
      if (!has || !(await range.count())) { await page.evaluate(() => window.__rec.orbit(11000, 10)); return; }
      await range.scrollIntoViewIfNeeded();
      const [, y, b] = await centreOf(range);
      const max = Number(await range.getAttribute('max'));
      await visibleClick(page, b.x + 3, y, { hold: 0 }).catch(() => {});
      // the drag itself: from flat (left end) to the top (right end) in 8 s
      await page.mouse.move(b.x + 3, y);
      await page.mouse.down();
      const steps = 160;
      for (let i = 1; i <= steps; i++) { await page.mouse.move(b.x + 3 + (b.width - 6) * i / steps, y); await wait(8000 / steps); }
      await page.mouse.up();
      await hideCursor(page);
      const relief = await page.evaluate(() => window.__dbg.relief);
      if (Math.abs(relief - max) > 1e-6) console.warn(`  hills: the slider ended at ${relief}, not ${max}`);
      await wait(2500);
    },
  },
  // 3. Three Gamla stan building cards with photos, each clicked open in turn.
  cards: {
    seconds: 18,
    async run(page) {
      const all = await cards(page);
      const gids = await page.evaluate(ids => ids.map(Number)
        .map(g => window.__dbg.building(g)).filter(b => Math.hypot(b.x, b.z) < 450)
        .sort((a, b) => Math.hypot(a.x, a.z) - Math.hypot(b.x, b.z)).slice(0, 3).map(b => b.gid),
        Object.keys(all).filter(g => all[g].photo));
      if (gids.length < 3) console.warn(`  cards: ${gids.length} Gamla stan buildings with a photo in this build`);
      await goHome(page, { x: 0, z: 0, azimuth: 200, elevation: 35, span: 900 });
      await settle(page);
      for (const gid of gids) {
        const b = await page.evaluate(g => window.__dbg.building(g), gid);
        await page.evaluate(() => window.__dbg.pinCard(-1, 0, 0));
        await page.evaluate(([x, z]) => window.__rec.flyTo(x, z, 330), [b.x, b.z]);
        await wait(300);
        const at = await page.evaluate(([x, z]) => window.__rec.screenOf(x, z), [b.x, b.z]);
        if (at) await visibleClick(page, at[0], at[1]);
        if (await page.evaluate(() => window.__dbg.pinned) !== gid) await page.evaluate(([g, p]) => window.__dbg.pinCard(g, ...p), [gid, at || [400, 300]]);
        await hideCursor(page);
        await page.locator('#card.pinned .photo img').waitFor({ timeout: 5000 }).catch(() => console.warn(`  cards: no photo shown for ${gid}`));
        await page.evaluate(() => window.__rec.orbit(4000, 8));
      }
    },
  },
  // 4. Search: "Götgatan" typed, the camera flies there and the card of a building on it opens.
  search: {
    seconds: 12,
    async run(page) {
      await goHome(page, { x: 0, z: 300, azimuth: 190, elevation: 35, span: 2200 });
      await settle(page);
      const box = page.locator('input[type=search]:not(.filter):visible, [role=search] input:visible').first();
      let spot = null;
      if (await box.count()) {
        const [x, y] = await centreOf(box);
        await visibleClick(page, x, y);
        await hideCursor(page);
        await box.pressSequentially('Götgatan', { delay: 140 });
        await wait(500);
        await page.keyboard.press('Enter');
        await wait(1800);
      } else {
        // The viewer has no place search yet (index.html's About says so): fly to the street's name instead.
        console.warn('  search: the viewer has no search box; flying to the Götgatan street name instead');
        spot = await page.evaluate(() => {
          const l = window.__dbg.labels.filter(l => /^Götgatan$/i.test(l.L.name)).sort((a, b) => b.len - a.len)[0];
          return l ? [l.x, l.z] : null;
        });
        if (!spot) { console.warn('  search: no Götgatan in this build; flying to Södermalm'); spot = [300, 1300]; }
        await wait(1200);
        await page.evaluate(([x, z]) => window.__rec.flyTo(x, z, 420), spot);
      }
      await wait(400);
      const vp = page.viewportSize();
      const gid = await page.evaluate(([x, y]) => window.__dbg.pick(x, y), [vp.width / 2, vp.height / 2]);
      if (typeof gid === 'number' && gid >= 0 && await page.evaluate(() => window.__dbg.pinned) < 0) {
        await page.evaluate(([g, x, y]) => window.__dbg.pinCard(g, x, y), [gid, vp.width / 2, vp.height / 2]);
      }
      await page.evaluate(() => window.__rec.orbit(6000, 12, 0.92));
    },
  },
  // 5. The Blå timmen look chosen in the Look panel, then a slow orbit over the water.
  bluehour: {
    seconds: 10,
    async run(page) {
      await goHome(page, { x: 150, z: -60, azimuth: 120, elevation: 18, span: 1300 });
      await settle(page);
      await page.locator('.look-open').click();
      const look = page.locator('#look [data-look="blatimme"]');
      const [x, y] = await centreOf(look);
      await visibleClick(page, x, y);
      await hideCursor(page);
      await wait(400);
      await page.keyboard.press('Escape');
      await page.evaluate(() => window.__rec.orbit(8500, 40, 1, true));
    },
  },
  // 6. The history scene ?scene=vasa-1628: past its warning, three beats.
  scene: {
    seconds: 15, query: '?scene=vasa-1628',
    async run(page) {
      const go = page.locator('.sp-warn-go');
      if (await go.isVisible().catch(() => false)) { const [x, y] = await centreOf(go); await visibleClick(page, x, y); }
      await hideCursor(page);
      await page.locator('.sp-cinema').waitFor({ state: 'visible', timeout: 10000 });
      for (let beat = 0; beat < 3; beat++) {
        if (beat) await page.keyboard.press('ArrowRight');
        await wait(5000);
      }
    },
  },
};
const names = clipNames ? clipNames.split(',') : Object.keys(CLIPS);
for (const n of names) if (!Object.hasOwn(CLIPS, n)) usage(`unknown clip "${n}" (known: ${Object.keys(CLIPS).join(', ')})`);

// ---------- Recording ----------
const { chromium } = await import('@playwright/test');
mkdirSync(out, { recursive: true });
const hasFfmpeg = (() => { try { execFileSync('ffmpeg', ['-version'], { stdio: 'ignore' }); return true; } catch { return false; } })();
const launch = () => chromium.launch({ args: ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'] });
let failed = 0;
for (const name of names) {
  const clip = CLIPS[name], nn = String(Object.keys(CLIPS).indexOf(name) + 1).padStart(2, '0');
  for (const format of formatNames) {
    const size = FORMATS[format], file = `${nn}-${name}-${format}`;
    const tmp = path.join(out, `.tmp-${file}`);
    const browser = await launch();   // a browser of its own for each video, so one stalled page cannot hold up the next
    const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1, recordVideo: { dir: tmp, size } });
    await context.addInitScript(recorderInit);
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const t0 = Date.now();
    let trimStart = 0;
    try {
      console.log(`${file}: ${clip.seconds} s`);
      await page.goto(new URL(clip.query || '', base).href);
      await page.locator('#loading').waitFor({ state: 'hidden', timeout: 90_000 });
      trimStart = (Date.now() - t0) / 1000;
      const started = Date.now();
      // a clip that stalls (a page that stops drawing) fails after a minute past its length, rather than hanging
      let timer;
      await Promise.race([clip.run(page), new Promise((_, no) => { timer = setTimeout(() => no(new Error('stalled')), clip.seconds * 1000 + 60_000); })])
        .finally(() => clearTimeout(timer));
      const left = clip.seconds * 1000 - (Date.now() - started);
      if (left > 0) await wait(left);
    } catch (e) {
      failed++;
      console.error(`  ${file} failed: ${e.message.split('\n')[0]}`);
    }
    if (errors.length) { failed++; console.error(`  page errors: ${errors.join(' | ')}`); }
    const video = page.video();
    await context.close();
    await browser.close();
    const raw = await video.path();
    const dest = path.join(out, `${file}.webm`);
    if (hasFfmpeg) {
      execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', String(trimStart), '-i', raw, '-t', String(clip.seconds), '-c:v', 'libvpx-vp9', '-b:v', '12M', dest]);
      trimStart = 0;
    } else renameSync(raw, dest);
    rmSync(tmp, { recursive: true, force: true });
    writeFileSync(path.join(out, `${file}.json`), JSON.stringify({ clip: name, format, ...size, seconds: clip.seconds, trimStart }, null, 2) + '\n');
  }
}
console.log(`${failed ? 'Done with problems' : 'Done'}: ${out}${hasFfmpeg ? '' : ' (no ffmpeg: cut each video at its .json trimStart)'}`);
process.exit(failed ? 1 : 0);
