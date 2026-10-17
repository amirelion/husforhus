// Draw calls, triangles and frame rate at the home view and from 20 km, read from the ?debug=1 statistics
// (window.__dbg.stats() in web/app.js), and the most calls from 30 km, the farthest the camera goes (controls.maxDistance:
// the whole city in view), over twelve directions (`farthest`, the final review's VIEWER-5). Needs Node 22+ and a
// server of this checkout, on any port but 8642:
//   python3 scripts/serve.py 8653
//   node scripts/measure.mjs [--url http://127.0.0.1:8653/] [--phone] [--label tile1500]
// Prints one JSON object. Headless frame rates are not meaningful; draw calls and triangles are.
// HFH_PORT is read as playwright.config.mjs reads it (default 8653). HFH_PORT=8642 or a --url on 8642 (the owner's preview
// of the main checkout) stops the script with exit code 2 before Playwright loads (imported after the check, like
// scripts/look.mjs, so the check works without node_modules, as in CI). It measures once the terrain stands at the
// page's relief (scripts/lib/terrain-wait.mjs); a city that does not load in 120 s, a terrain that failed to load (at
// once) or one that does not stand in 60 s prints {error, errors} instead and exits with code 1. A build without
// terrain is measured flat, and the script says so on stderr.
import { pageProblem, waitForTerrain } from './lib/terrain-wait.mjs';

function usage(message) {
  console.error(`measure.mjs: ${message}`);
  process.exit(2);
}
const args = process.argv.slice(2);
const opt = (name, fallback) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : fallback; };
const phone = args.includes('--phone');
const PORT = Number(process.env.HFH_PORT) || 8653;
if (PORT === 8642) usage('8642 is the preview server of the main checkout: pick another HFH_PORT');
const base = opt('--url', `http://127.0.0.1:${PORT}/`);
let url;
try { url = new URL(base); } catch { usage(`--url is not a URL: "${base}"`); }
if (url.port === '8642') usage('8642 is the preview server of the main checkout: pick another --url');
url.searchParams.set('debug', '1');

const { chromium } = await import('@playwright/test');
const browser = await chromium.launch();
const context = await browser.newContext(phone
  ? { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true }
  : { viewport: { width: 1600, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (pageProblem(m.type(), m.text())) errors.push(m.text()); });
page.on('requestfailed', r => errors.push(`${r.url()}: ${r.failure()?.errorText}`));

await page.goto(url.href);
let waiting = 'city', terrain;
try {
  await page.locator('#loading').waitFor({ state: 'hidden', timeout: 120_000 });
  // The terrain arrives after the first frame and rises; measure once it stands (or the build has none).
  waiting = 'terrain';
  terrain = await waitForTerrain(page, [opt('--label', ''), phone ? 'phone' : 'desktop'].filter(Boolean).join(' '));
} catch (e) {
  const error = waiting === 'city' ? 'the city did not finish loading' : e.message;
  console.error(JSON.stringify({ error, errors }, null, 1));
  await browser.close();
  process.exit(1);
}
if (terrain.source && terrain.state !== 'ready') errors.push(`terrain ${terrain.state}`);
if (!terrain.source) console.error('measure.mjs: this build has no terrain; it is measured flat');
const sample = async () => {
  await page.waitForTimeout(3000); // labels, land and water arrive after the first frame; fps needs samples
  return page.evaluate(() => window.__dbg.stats());
};
const home = await sample();
await page.evaluate(() => window.__dbg.viewAt(20000));
const overview = await sample();
const farthest = await page.evaluate(async () => {
  const D = window.__dbg, ctl = D.controls, cam = D.camera, t = ctl.target;
  const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  let worst = null;
  for (const polar of [0.001, 0.6, 1.1]) {
    for (let k = 0; k < 4; k++) {
      const az = k * Math.PI / 2;
      cam.position.set(t.x + Math.sin(polar) * Math.sin(az), t.y + Math.cos(polar), t.z + Math.sin(polar) * Math.cos(az));
      ctl.update();
      D.viewAt(40000);   // clamped to controls.maxDistance
      await frame();
      await frame();
      const s = D.stats();
      if (!worst || s.calls > worst.calls) worst = { ...s, polar, azimuth: k * 90, dist: cam.position.distanceTo(t) };
    }
  }
  return worst;
});
console.log(JSON.stringify({ label: opt('--label', ''), url: url.href, device: phone ? 'phone 390x844 @3x' : 'desktop 1600x1000',
  home, overview, farthest, errors }, null, 1));
await browser.close();
