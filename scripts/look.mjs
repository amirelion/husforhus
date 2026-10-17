// Screenshots of each look variant (web/themes.js) at chosen views, on desktop and phone, for the owner's look reviews: M2
//, M3 and M4 (terrain, with the flat/relief, terrace, fade and exaggeration comparisons). Needs
// Node 22+ and a server of this checkout, on any port but 8642 (the owner's preview of the main checkout):
//   python3 scripts/serve.py 8653
//   node scripts/look.mjs [--url http://127.0.0.1:8653/] [--out data/look] [--looks arg,kalk]
//                         [--views hero,cliffs] [--estimates hidden] [--variants "relief=off,relief=on"]
//                         [--devices desktop] [--legend open]
//   --url        the running site (default http://127.0.0.1:$HFH_PORT/, HFH_PORT 8653)
//   --out        the folder the PNGs go to (default data/look)
//   --looks      a comma list of looks (default: every look in web/themes.js)
//   --views      a comma list of views (default hero,overview): hero; overview (12 km); far (20 km); gamlastan
//                (Stortorget from 900 m); cliffs (Söder's cliffs from Riddarfjärden); soder (the quays under Söder's
//                cliffs, Katarinahissen and Stadsgården, from Strömmen); south (Hammarbybacken and Henriksdalsberget);
//                quays (Skeppsbron and Riddarholmen up close); shore (Djurgården's natural south shore at Waldemarsudde);
//                lakes (Magelungen and Flaten, each at its own level); edge-east (Saltsjön towards Nacka); edge-ne
//                (Lilla Värtan towards Lidingö); streets (Södermalm's streets from a low angle at 1 km, where the
//                buildings in front hide names: the names sheet); pond (a pond in Norra Djurgården, its water against
//                its banks); crater (the block round gid 42975, on a 1 km sheet line in the south); and
//                pedestals-hasselby and pedestals-soder (houses beside a lower building in one cell: the terrace's
//                notch under them)
//   --estimates  hidden: render with the hide-estimates switch on (localStorage hfh-estimates) and add -noest to
//                each file name (default shown)
//   --variants   a comma list of URL settings, each rendered in turn (a&b sets two; an empty one is the plain map):
//                relief=off|on|<0 to 2.5 in steps of 0.5>, terrace=full|true|none, fade=<0 to 5000 metres>, edgebuildings=on|off|1|0,
//                labels=top. Each adds -<variant> to the file name, with = and & left out (relief=2.5&terrace=none ->
//                -relief2.5terracenone). Default: none
//   --devices    desktop, phone or both (default desktop,phone)
//   --legend     auto (default): the legend folded for the terrain views (cliffs to pedestals-soder), which it would
//                partly cover on a desktop, and as the page opened it for the others; open: open in every view
// An unknown look, view, device or variant setting, a value web/app.js would not take, an --estimates value other than
// shown or hidden, a --legend other than auto or open, or an option without its value stops the script with a message
// and exit code 2, before Playwright loads (it is imported only after the checks, so the checks also work where
// node_modules is not installed, as in CI's offline job) and before the out folder is created. So do HFH_PORT=8642 and
// a --url on 8642: HFH_PORT is read as playwright.config.mjs reads it, and nothing here aims at the owner's preview.
// Writes <out>/<theme>-<view>-<device>[-noest][-<variant>].png once the terrain stands at the variant's relief
// (scripts/lib/terrain-wait.mjs). A terrain that failed to load stops the run at once, and one that does not stand in
// 60 s stops it then, each with exit code 1, no PNG for that page and the page's errors so far printed; a build
// without terrain is said so once. Page errors, terrain warnings, requests to another origin and a relief the page
// did not apply are printed, and the run then ends with exit code 1. data/ is git-ignored: the images show City data.
import { mkdirSync } from 'node:fs';
import { THEMES } from '../web/themes.js';
import { RELIEF_MAX, RELIEF_STEP } from '../web/relief.js';
import { pageProblem, waitForTerrain } from './lib/terrain-wait.mjs';

// A bad option stops the run here, before anything else happens.
function usage(message) {
  console.error(`look.mjs: ${message}`);
  process.exit(2);
}
const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  const v = args[i + 1];
  if (v === undefined || v.startsWith('--')) usage(`${name} needs a value`);
  return v;
};
// The port as playwright.config.mjs reads it, and never 8642.
const PORT = Number(process.env.HFH_PORT) || 8653;
if (PORT === 8642) usage('8642 is the preview server of the main checkout: pick another HFH_PORT');
const base = opt('--url', `http://127.0.0.1:${PORT}/`);
let basePort;
try { basePort = new URL(base).port; } catch { usage(`--url is not a URL: "${base}"`); }
if (basePort === '8642') usage('8642 is the preview server of the main checkout: pick another --url');
const out = opt('--out', 'data/look');
const LOOKS = opt('--looks', Object.keys(THEMES).join(',')).split(',');
const VIEW_NAMES = opt('--views', 'hero,overview').split(',');
const ESTIMATES = opt('--estimates', 'shown');
const hideEst = ESTIMATES === 'hidden';
const VARIANTS = opt('--variants', '').split(',');
const DEVICE_NAMES = opt('--devices', 'desktop,phone').split(',');
const LEGEND = opt('--legend', 'auto');

// The settings web/app.js reads from the URL, each with the values it takes (web/relief.js initialRelief, app.js's
// TERRACE, terrain.js fadeWidth and FADE_MAX_M, uEdgeBuildings, LABELS_ON_TOP), and how a value goes into the URL:
// app.js reads edgebuildings=1 only, so on and off go in as 1 and 0.
const decimal = (v, lo, hi) => /^\d+(\.\d+)?$/.test(v) && Number(v) >= lo && Number(v) <= hi;
const SETTINGS = {
  // the Hills slider's range and step: 0 is flat, 1 the true heights; a value above the top or between the
  // steps would be clamped or snapped by the page (web/relief.js), so it is refused like an unknown one
  relief: { ok: v => v === 'off' || v === 'on' || (decimal(v, 0, RELIEF_MAX)
    && Math.abs(Number(v) / RELIEF_STEP - Math.round(Number(v) / RELIEF_STEP)) < 1e-9),
  says: `off, on or 0 to ${RELIEF_MAX} in steps of ${RELIEF_STEP}` },
  terrace: { ok: v => ['full', 'true', 'none'].includes(v), says: 'full, true or none' },
  fade: { ok: v => decimal(v, 0, 5000), says: 'a number of metres from 0 to 5000' },
  edgebuildings: { ok: v => ['on', 'off', '1', '0'].includes(v), says: 'on, off, 1 or 0', url: { on: '1', off: '0' } },
  labels: { ok: v => v === 'top', says: 'top' },
};

const DEVICES = {
  desktop: { viewport: { width: 1600, height: 1000 } },
  phone: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
};
// A view is a list of __dbg calls with their argument (an array is spread). Places are local metres (x east, z south)
// framed like the hero view (web/app.js goHome: the camera `span` back at `azimuth` degrees, 0 from the south, 90 from
// the east, `elevation` up).
const place = (x, z, azimuth, elevation, span) => [['goHome', { x, z, azimuth, elevation, span }]];
const ALL_VIEWS = {
  hero: [['goHome']],
  overview: [['goHome'], ['viewAt', 12000]],
  far: [['goHome'], ['viewAt', 20000]],
  gamlastan: [['flyTo', [0, 0, null, 900]]],        // Stortorget from 900 m: the old town fills the frame
  cliffs: place(-860, 600, 195, 14, 1700),          // Skinnarviksberget and Mariaberget from over Riddarfjärden
  soder: place(400, 690, 180, 18, 900),             // Katarinahissen and Stadsgården: quays under a cliff, from Strömmen
  south: place(1800, 2000, 300, 22, 4200),          // Hammarbybacken and Henriksdalsberget from the west-south-west
  quays: place(360, 40, 75, 24, 520),               // Skeppsbron's quay from over Saltsjön, Gamla stan behind it
  shore: place(2130, 164, 0, 15, 1200),             // Djurgården's natural south shore at Waldemarsudde, from Saltsjön
  // Magelungen (west, 21 m) and Flaten (east, 23 m), Drevviken (21 m) between them, from the north. They lie 7 km
  // apart east to west: 5500 m from (1800, 8000) left Flaten out of a desktop frame on the whole city.
  lakes: place(1750, 8600, 180, 40, 8500),
  'edge-east': place(4800, 400, 270, 20, 5000),     // where the municipality ends in Saltsjön, towards Nacka
  'edge-ne': place(1950, -3550, 230, 20, 4200),     // Lilla Värtan towards Lidingö
  // Södermalm's grid round Wollmar Yxkullsgatan from the west-south-west, low and close: the buildings in front hide
  // most names unless they are drawn over everything (?labels=top). The names sheet's view: from cliffs
  // and quays the two differed by a few hundred pixels.
  streets: place(-400, 1100, 255, 12, 1100),
  // The final review's places (2026-10-16): pond 41 (59.3655 N, 18.0777 E), which stood 2 m above its banks on m4b to
  // m4d; the block round gid 42975 (59.2633 N, 18.1060 E), a 9 m crater on m4 to m4d; and two places where houses
  // stand on a tall pedestal over the terrace's notch, cut for a lower building in the same 20 m cell (
  // VIEWER-6): Hässelby strand (the houses above Hässelbyverket's hall) and Mariaberget (from Riddarfjärden).
  pond: place(393, -4501, 200, 25, 450),
  crater: place(2021, 6882, 30, 25, 650),
  'pedestals-hasselby': place(-13963, -4175, 20, 18, 450),
  'pedestals-soder': place(-261, 678, 190, 16, 600),
};
// The views a desktop legend would partly cover, where it is folded (--legend auto).
const TERRAIN_VIEWS = new Set(['cliffs', 'soder', 'south', 'quays', 'shore', 'lakes', 'edge-east', 'edge-ne', 'streets',
  'pond', 'crater', 'pedestals-hasselby', 'pedestals-soder']);
// Own names only (Object.hasOwn): constructor or __proto__ is no view, look, device or setting.
const known = (table, name) => Object.hasOwn(table, name);
for (const v of VIEW_NAMES) if (!known(ALL_VIEWS, v)) usage(`unknown view "${v}" (known: ${Object.keys(ALL_VIEWS).join(', ')})`);
for (const t of LOOKS) if (!known(THEMES, t)) usage(`unknown look "${t}" (known: ${Object.keys(THEMES).join(', ')})`);
for (const d of DEVICE_NAMES) {
  if (!known(DEVICES, d)) usage(`unknown device "${d}" (known: ${Object.keys(DEVICES).join(', ')})`);
}
if (!['shown', 'hidden'].includes(ESTIMATES)) usage(`--estimates must be shown or hidden, not "${ESTIMATES}"`);
if (!['auto', 'open'].includes(LEGEND)) usage(`--legend must be auto or open, not "${LEGEND}"`);
for (const variant of VARIANTS) {
  const seen = new Set();
  for (const [k, v] of new URLSearchParams(variant)) {
    if (!known(SETTINGS, k)) usage(`unknown variant setting "${k}" in "${variant}" (known: ${Object.keys(SETTINGS).join(', ')})`);
    if (seen.has(k)) usage(`variant "${variant}" sets ${k} twice`);
    seen.add(k);
    if (!SETTINGS[k].ok(v)) usage(`variant "${variant}": ${k} must be ${SETTINGS[k].says}, not "${v}"`);
  }
}
mkdirSync(out, { recursive: true });

const { chromium } = await import('@playwright/test');
const browser = await chromium.launch();
const origin = new URL(base).origin;
const files = [];
let toldNoTerrain = false;
for (const theme of LOOKS) {
  for (const device of DEVICE_NAMES) {
    for (const variant of VARIANTS) {
      const context = await browser.newContext(DEVICES[device]);
      if (hideEst) await context.addInitScript(() => localStorage.setItem('hfh-estimates', 'hidden'));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('console', m => { if (pageProblem(m.type(), m.text())) errors.push(m.text()); });
      page.on('request', r => {
        const u = new URL(r.url());
        if (u.protocol !== 'data:' && u.protocol !== 'blob:' && u.origin !== origin) errors.push('external: ' + r.url());
      });
      const url = new URL(base);
      url.searchParams.set('theme', theme);
      for (const [k, v] of new URLSearchParams(variant)) url.searchParams.set(k, SETTINGS[k].url?.[v] ?? v);
      await page.goto(url.href);
      await page.locator('#loading').waitFor({ state: 'hidden', timeout: 120_000 });
      await page.waitForFunction(() => window.__dbg.stats().tiles === window.__dbg.stats().tilesTotal);
      // the terrain is in and has risen to the variant's relief, or this build has none
      let terrain;
      try {
        terrain = await waitForTerrain(page, [theme, device, variant].filter(Boolean).join(' '));
      } catch (e) {
        console.error(`look.mjs: ${e.message}`);
        if (errors.length) console.error(theme, device, variant, errors);   // what the page said on the way
        await browser.close();
        process.exit(1);
      }
      if (terrain.source && terrain.state !== 'ready') errors.push(`terrain ${terrain.state}`);
      if (!terrain.source && !toldNoTerrain) {
        console.error('look.mjs: this build has no terrain, so the relief, terrace and fade variants do nothing');
        toldNoTerrain = true;
      }
      const asked = new URLSearchParams(variant).get('relief');
      if (terrain.source && decimal(asked ?? '', 0, RELIEF_MAX) && Math.abs(terrain.wanted - Number(asked)) > 1e-6) {
        errors.push(`relief=${asked} was not applied: the page draws ${terrain.wanted}`);
      }
      // the legend as the page opened it (null where there is none), folded for the terrain views (--legend auto)
      const legendAtLoad = await page.evaluate(() =>
        document.querySelector('.sheet-handle')?.getAttribute('aria-expanded') ?? null);
      for (const view of VIEW_NAMES) {
        for (const step of ALL_VIEWS[view]) {
          await page.evaluate(([fn, arg]) => (Array.isArray(arg) ? window.__dbg[fn](...arg) : window.__dbg[fn](arg)), step);
        }
        if (legendAtLoad !== null) {
          const open = LEGEND === 'open' || (!TERRAIN_VIEWS.has(view) && legendAtLoad === 'true');
          await page.evaluate(open => {
            const h = document.querySelector('.sheet-handle');
            if ((h.getAttribute('aria-expanded') === 'true') !== open) h.click();
          }, open);
        }
        await page.waitForTimeout(2500); // labels and the ground under the target settle; label textures redraw
        const tag = variant ? `-${variant.replace(/[=&]/g, '')}` : '';
        const file = `${out}/${theme}-${view}-${device}${hideEst ? '-noest' : ''}${tag}.png`;
        await page.screenshot({ path: file });
        files.push(file);
      }
      if (errors.length) {
        console.error(theme, device, variant, errors);
        process.exitCode = 1;
      }
      await context.close();
    }
  }
}
await browser.close();
console.log(files.join('\n'));
