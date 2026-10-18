// The map once it stands still: #loading gone, and, in a build with terrain, the terrain in and risen to the
// relief the page wants (web/app.js: the ground rises over about a second after it arrives, and the camera rides on
// it). With the GPU drawing (playwright.config.mjs, macOS) "loaded" comes seconds sooner than with SwiftShader, so a
// test that measures the camera or takes a "before" screenshot must wait for this, not only for #loading.
import { expect } from '@playwright/test';

export async function settled(page) {
  await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
  await expect.poll(() => page.evaluate(() => {
    const t = window.__dbg.terrain();
    if (!t.source) return true;                                   // a build without terrain
    if (t.state === 'failed') return true;
    return t.state === 'ready' && Math.abs(t.relief - window.__dbg.relief) < 1e-6;
  }), { timeout: 30_000 }).toBe(true);
}
