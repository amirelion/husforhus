import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initialCollapsed, LEGEND_KEY } from '../panel.js';

test('the stored choice is kept under hfh-legend', () => {
  assert.equal(LEGEND_KEY, 'hfh-legend');
});

test('a stored choice beats the screen size', () => {
  for (const phone of [true, false]) {
    for (const wide of [true, false]) {
      assert.equal(initialCollapsed({ stored: 'collapsed', phone, wide }), true, `collapsed phone=${phone} wide=${wide}`);
      assert.equal(initialCollapsed({ stored: 'open', phone, wide }), false, `open phone=${phone} wide=${wide}`);
    }
  }
});

test('without a stored choice a phone starts collapsed', () => {
  assert.equal(initialCollapsed({ stored: null, phone: true, wide: false }), true);
  assert.equal(initialCollapsed({ stored: null, phone: true, wide: true }), true);
});

test('without a stored choice a narrow desktop starts collapsed and a wide one open', () => {
  assert.equal(initialCollapsed({ stored: null, phone: false, wide: false }), true);
  assert.equal(initialCollapsed({ stored: null, phone: false, wide: true }), false);
});

test('an unknown, empty or missing stored value falls back to the defaults', () => {
  for (const stored of ['', 'yes', 'COLLAPSED', 'true', undefined, 0, {}]) {
    assert.equal(initialCollapsed({ stored, phone: false, wide: true }), false, `wide ${String(stored)}`);
    assert.equal(initialCollapsed({ stored, phone: false, wide: false }), true, `narrow ${String(stored)}`);
    assert.equal(initialCollapsed({ stored, phone: true, wide: true }), true, `phone ${String(stored)}`);
  }
});
