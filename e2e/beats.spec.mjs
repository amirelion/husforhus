// Every beat of the stories marked ready (web/scenes/index.json), rendered headless at desktop and phone size: the
// beat's target projects into the middle third of the screen, the camera looks down on it at 25° or more, and the
// faint-city legend is up. Each beat is saved to data/test-results/beats/<id>-<beat>-<size>.png for review.
// Reduced motion, so each beat's camera is in place at once and nothing autoplays.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';

const index = JSON.parse(fs.readFileSync(new URL('../web/scenes/index.json', import.meta.url)));
const ready = index.scenes.filter(s => s.ready);
const SIZES = { desktop: { width: 1280, height: 800 }, phone: { width: 390, height: 844 } };
const OUT = 'data/test-results/beats';

test('six stories are ready', () => {
  expect(ready.map(s => s.id).sort()).toEqual(['metro-1950', 'metro-vallingby', 's04', 's07-kristina-lock', 's10-olympics-1912', 's11', 'tre-kronor-1697', 'vasa-1628']);
});

for (const s of ready) {
  for (const [size, viewport] of Object.entries(SIZES)) {
    test(`${s.id} at ${size}: every beat's target is in the middle of the frame`, async ({ page }) => {
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.setViewportSize(viewport);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      // Scenes are off in the shipped config: on in this page's copy of it.
      let origin = null;
      await page.route('**/stockholm.json', async route => {
        const r = await route.fetch();
        const config = await r.json();
        config.features = { ...config.features, scenes: true };
        origin = config.origin;
        await route.fulfill({ response: r, json: config });
      });
      const scene = await (await page.request.get(`scenes/${s.id}.json`)).json();
      await page.goto(`/?scene=${s.id}`);
      await expect(page.locator('#loading')).toBeHidden({ timeout: 60_000 });
      if (scene.sensitive) await page.locator('.sp-warn-go').click();
      await expect(page.locator('.sp-cinema')).toBeVisible();
      await expect(page.locator('.sp-legend')).toHaveText("Faint: today's city, for orientation");
      fs.mkdirSync(OUT, { recursive: true });
      for (let i = 0; i < scene.beats.length; i++) {
        if (i) await page.keyboard.press('ArrowRight');
        await expect(page.locator('.sp-count')).toContainText(`${i + 1} / ${scene.beats.length}`);
        await page.waitForTimeout(1200);   // the ground and tiles settle under the camera
        const v = await page.evaluate(async ([t, origin]) => {
          const { toLocal } = await import('./scene-player.js');
          const { camera, surfaceAt } = window.__dbg;
          const [x, z] = toLocal(t.lat, t.lon, origin);
          const p = camera.position.clone().set(x, surfaceAt(x, z), z);
          const down = Math.atan2(camera.position.y - p.y, Math.hypot(camera.position.x - x, camera.position.z - z)) * 180 / Math.PI;
          p.project(camera);
          return { x: p.x, y: p.y, down };
        }, [scene.beats[i].target, origin]);
        const w = `${s.id} beat ${i + 1} (${size})`;
        expect(Math.abs(v.x), `${w}: across`).toBeLessThanOrEqual(1 / 3);
        expect(Math.abs(v.y), `${w}: up and down`).toBeLessThanOrEqual(1 / 3);
        expect(v.down, `${w}: degrees below the horizon`).toBeGreaterThanOrEqual(25);
        await page.screenshot({ path: `${OUT}/${s.id}-${i + 1}-${size}.png` });
      }
      expect(errors).toEqual([]);
    });
  }
}
