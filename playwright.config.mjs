// Playwright for the viewer (Plan 1, Task 20). Serves web/ with scripts/serve.py (no-store, so a run never sees
// stale code). Plan 3: on its own port (HFH_PORT, default 8653), never 8642, where the owner's preview serves the main
// checkout; and always its own server, so a run tests the tree it was started in.
import { defineConfig, devices } from '@playwright/test';

const PORT = Number(process.env.HFH_PORT) || 8653;
if (PORT === 8642) throw new Error('8642 is the preview server of the main checkout: pick another HFH_PORT');

export default defineConfig({
  testDir: 'e2e',
  // e2e/worker runs against `wrangler dev` (playwright.worker.config.mjs), not this static server.
  testIgnore: 'worker/**',
  timeout: 120_000,
  // scripts/serve.py takes a burst of module requests now (Server.request_queue_size); before that, macOS reset
  // connections beyond a backlog of 5. Every run starts its own server (webServer, below), so none predates the fix.
  // CI still retries once.
  retries: process.env.CI ? 1 : 0,
  outputDir: 'data/test-results',
  reporter: 'list',
  use: { baseURL: `http://127.0.0.1:${PORT}/`, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1400, height: 900 } } }],
  webServer: {
    command: `python3 scripts/serve.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
