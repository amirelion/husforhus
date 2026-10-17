import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const SCRIPT = fileURLToPath(new URL('./make-og.mjs', import.meta.url));

test('make-og refuses HFH_PORT 8642 before loading Playwright', () => {
  const r = spawnSync(process.execPath, [SCRIPT], { env: { ...process.env, HFH_PORT: '8642' }, encoding: 'utf8' });
  assert.equal(r.status, 2);
  assert.match(r.stderr, /8642/);
});
