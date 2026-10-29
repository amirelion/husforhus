// After a deploy, or when visitors report a map that does not load: opens the live site in a fresh browser as a phone
// and as a desktop, waits for every tile, and fails on any script from another address, any error thrown on the page,
// or a city that does not finish loading. A real browser, not curl: Cloudflare adds its Web Analytics beacon only to
// pages a browser asks for, and it can do so from a dashboard setting with no deploy. On 2026-10-29 that beacon,
// blocked by the page's own policy, stopped the tiles on phones (decisions.md D67).
//   node scripts/check_live.mjs [--url https://husforhus.se/]
// Prints one line per device and exits with code 1 if either has a problem.
import { chromium, devices } from '@playwright/test';

const args = process.argv.slice(2);
const i = args.indexOf('--url');
const base = i >= 0 ? args[i + 1] : 'https://husforhus.se/';
const browser = await chromium.launch();
let failed = false;
for (const device of ['Pixel 7', 'Desktop Chrome']) {
  const page = await (await browser.newContext({ ...devices[device] })).newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // A fresh query string, so no cache answers for the page itself.
  await page.goto(`${base}?check=${Date.now()}`);
  const loaded = await page.waitForFunction(() => document.getElementById('loading').hidden, null, { timeout: 120000 })
    .then(() => true, () => false);
  const { foreign, progress } = await page.evaluate(() => ({
    foreign: [...document.scripts].filter(s => s.src && !s.src.startsWith(location.origin + '/')).map(s => s.src),
    progress: document.getElementById('progress')?.textContent ?? null }));
  const ok = loaded && progress === '100' && !foreign.length && !errors.length;
  failed ||= !ok;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${device}: loaded ${loaded}, progress ${progress}, ` +
    `other sites' scripts ${JSON.stringify(foreign)}, page errors ${JSON.stringify(errors)}`);
}
await browser.close();
process.exit(failed ? 1 : 0);
