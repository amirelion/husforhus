// Every module the page loads parses: node --check on web/*.js. The other unit tests import single modules, so a
// broken app.js (two imports of one name after a merge, 2026-10-18) passed them all and only the browser saw it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const WEB = fileURLToPath(new URL('..', import.meta.url));
for (const f of readdirSync(WEB).filter(f => f.endsWith('.js'))) {
  test(`web/${f} parses`, () => {
    assert.doesNotThrow(() => execFileSync(process.execPath, ['--check', `${WEB}${f}`], { stdio: 'pipe' }));
  });
}
