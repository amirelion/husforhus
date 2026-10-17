import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// A `}` with nothing open starts a qualified rule's prelude (CSS Syntax), which swallows the next rule: that is how
// the prefers-reduced-motion rule after the phone block was lost. Comments are blanked first, keeping line numbers.
test('styles.css closes only braces it opened', () => {
  const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '));
  let depth = 0;
  css.split('\n').forEach((line, i) => {
    for (const ch of line) {
      depth += ch === '{' ? 1 : ch === '}' ? -1 : 0;
      assert.ok(depth >= 0, `stray } on line ${i + 1}`);
    }
  });
  assert.equal(depth, 0, 'every { is closed');
});

// The first paint, before app.js runs, is the default look: styles.css's :root colour tokens are its `ui`
// tokens, --font is its font, and the color-scheme matches its ground, so there is no flash of another look.
test("styles.css's :root is the default look", async () => {
  const { THEMES } = await import('../themes.js');
  const { DEFAULT_LOOK } = await import('../look.js');
  const { luma, rgb } = await import('../tone.js');
  const th = THEMES[DEFAULT_LOOK];
  const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  const root = css.match(/:root\s*\{([^}]*)\}/)[1];
  const decl = Object.fromEntries([...root.matchAll(/([\w-]+)\s*:\s*([^;]+);/g)].map(m => [m[1], m[2].trim()]));
  for (const [k, v] of Object.entries(th.ui)) assert.equal(decl[k], v, k);
  assert.equal(decl['--font'], `"${th.font}"`);
  assert.equal(decl['color-scheme'], luma(rgb(th.ui['--bg'])) < 0.5 ? 'dark' : 'light');
});
