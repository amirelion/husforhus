// Playwright for the report form against the Worker itself: `wrangler dev` serves web/ as the assets with
// src/worker.js in front, a fresh local D1 and R2 under data/wrangler-e2e (never the cloud). `npm run test:e2e:worker`.
import { defineConfig, devices } from '@playwright/test';

const PORT = Number(process.env.HFH_WORKER_PORT) || 8788;
const STATE = 'data/wrangler-e2e';

export default defineConfig({
  testDir: 'e2e/worker',
  timeout: 120_000,
  retries: process.env.CI ? 1 : 0,
  outputDir: 'data/test-results-worker',
  reporter: 'list',
  use: { baseURL: `http://127.0.0.1:${PORT}/`, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1400, height: 900 } } }],
  webServer: {
    command: `rm -rf ${STATE} && CI=1 npx wrangler d1 migrations apply REPORTS --local --persist-to ${STATE}`
      + ` && npx wrangler dev --port ${PORT} --ip 127.0.0.1 --assets web --persist-to ${STATE}`,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
    timeout: 90_000,
  },
});
