// The social link preview (web/index.html og:image): the viewer at its hero view (web/app.js goHome: Gamla stan and
// Söder), Ärg look, legend folded, 1200×630, with the title and dek overlaid in the look's own font (--font).
// Needs Node 22+, Playwright, a city build in web/data and a server of this checkout on any port but 8642:
//   python3 scripts/serve.py 8653
//   HFH_PORT=8653 node scripts/og/make-og.mjs [--out web/og.png]
// Writes web/og.png (shipped by build_dist.py with the rest of web/). Page errors stop the run with exit code 1.
import { pageProblem, waitForTerrain } from '../lib/terrain-wait.mjs';

const usage = msg => { console.error(`make-og.mjs: ${msg}`); process.exit(2); };
const PORT = Number(process.env.HFH_PORT) || 8653;
if (PORT === 8642) usage('8642 is the preview server of the main checkout: pick another HFH_PORT');
const i = process.argv.indexOf('--out');
if (i !== -1 && !process.argv[i + 1]) usage('--out needs a file');
const OUT = i === -1 ? 'web/og.png' : process.argv[i + 1];

const { chromium } = await import('@playwright/test');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (pageProblem(m.type(), m.text())) errors.push(m.text()); });

await page.goto(`http://127.0.0.1:${PORT}/?theme=arg`);
await page.locator('#loading').waitFor({ state: 'hidden', timeout: 120_000 });
await page.waitForFunction(() => window.__dbg.stats().tiles === window.__dbg.stats().tilesTotal);
await waitForTerrain(page, 'og');
await page.evaluate(() => window.__dbg.goHome());
await page.evaluate(() => {
  const h = document.querySelector('.sheet-handle');
  if (h?.getAttribute('aria-expanded') === 'true') h.click();
});
await page.waitForTimeout(2500); // the camera, labels and ground settle

// Only the map and the title: every control hidden, the masthead redrawn larger in the look's font.
await page.evaluate(() => {
  for (const el of document.body.children) {
    if (!['scene'].includes(el.id) && !el.classList.contains('veil')) el.style.visibility = 'hidden';
  }
  const card = document.createElement('div');
  card.style.cssText = 'position:fixed;left:40px;top:36px;padding:22px 30px 24px;border-radius:14px;font-family:var(--font),sans-serif;color:var(--ink,#111);background:color-mix(in srgb, var(--bg,#e6e8ea) 88%, transparent);box-shadow:0 4px 24px rgba(0,0,0,.12)';
  card.innerHTML = '<div style="font-size:88px;font-weight:800;letter-spacing:-0.035em;line-height:.9">Hus för hus</div>'
    + '<div style="margin-top:14px;font-size:32px;font-weight:500;color:var(--ink,#111);opacity:.78">Stockholm, building by building</div>';
  document.body.append(card);
});
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: OUT });
await browser.close();
if (errors.length) { console.error('make-og.mjs:', errors); process.exit(1); }
console.log(`make-og.mjs: wrote ${OUT}`);
