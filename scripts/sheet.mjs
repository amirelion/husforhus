// A comparison sheet for the owner's look reviews: screenshots side by side in a grid, each with a caption, saved as one
// PNG (the M4 review; the default look's four sheets were made the same way by hand). Needs Node 22+ (Playwright's
// browser); no server.
//   node scripts/sheet.mjs --out data/look/m4/sheet-relief.png [--cols 2] [--title "Flat or relief"] \
//        data/look/m4/arg-hero-desktop-reliefoff.png=Flat data/look/m4/arg-hero-desktop-reliefon.png=Relief
// Each argument after the options is a PNG, optionally followed by =caption (default: its file name). A missing file,
// a folder, no file at all, no --out or an option without its value stops the script with exit code 2 before
// Playwright loads (imported only after the checks, like scripts/look.mjs, so the checks work without node_modules, as
// in CI). The sheet is drawn at twice its CSS size, so the screenshots in it stay sharp.
import { existsSync, mkdirSync, readFileSync, statSync } from 'node:fs';
import { basename, dirname } from 'node:path';

function usage(message) {
  console.error(`sheet.mjs: ${message}`);
  process.exit(2);
}
const args = process.argv.slice(2);
const OPTS = ['--out', '--cols', '--title'];
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  const v = args[i + 1];
  if (v === undefined || v.startsWith('--')) usage(`${name} needs a value`);
  return v;
};
const files = args.filter((a, i) => !OPTS.includes(a) && !OPTS.includes(args[i - 1]));
const out = opt('--out', '');
const cols = Math.max(1, Number(opt('--cols', '2')) || 2);
const title = opt('--title', '');
if (!out) usage('--out is required');
if (!files.length) usage('no screenshots given');
const items = files.map(f => {
  const at = f.lastIndexOf('.png=');
  const [path, caption] = at >= 0 ? [f.slice(0, at + 4), f.slice(at + 5)] : [f, basename(f)];
  if (!existsSync(path)) usage(`no such file: ${path}`);
  if (!statSync(path).isFile()) usage(`not a file: ${path}`);
  return { path, caption };
});
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const html = `<!doctype html><meta charset="utf-8"><style>
  body { margin: 0; padding: 24px; background: #fff; color: #15232b; font: 600 18px system-ui, sans-serif; }
  h1 { margin: 0 0 16px; font-size: 24px; }
  .grid { display: grid; grid-template-columns: repeat(${cols}, 1fr); gap: 18px; }
  figure { margin: 0; } img { display: block; width: 100%; border: 1px solid #c8cfd3; }
  figcaption { margin-top: 6px; }
</style>${title ? `<h1>${esc(title)}</h1>` : ''}<div class="grid">${items.map(it => `<figure>
  <img src="data:image/png;base64,${readFileSync(it.path).toString('base64')}"><figcaption>${esc(it.caption)}</figcaption>
</figure>`).join('')}</div>`;

mkdirSync(dirname(out), { recursive: true });
const { chromium } = await import('@playwright/test');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 48 + cols * 820, height: 600 }, deviceScaleFactor: 2 });
await page.setContent(html);
await page.waitForFunction(() => [...document.images].every(i => i.complete));
await page.screenshot({ path: out, fullPage: true });
await browser.close();
console.log(out);
