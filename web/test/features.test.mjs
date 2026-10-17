import { test } from 'node:test';
import assert from 'node:assert/strict';
import { withTry } from '../features.js';

const off = { scenes: false, layers: false, search: true };

test('?try= switches on the named features for this visit', () => {
  assert.deepEqual(withTry(off, '?try=stories'), { ...off, scenes: true });
  assert.deepEqual(withTry(off, '?try=stories,plaques'), { ...off, scenes: true, plaques: true });
  assert.deepEqual(withTry(off, '?lang=sv&try=Plaques'), { ...off, plaques: true });
});

test('anything else changes nothing, and the build\'s own switches are kept', () => {
  assert.deepEqual(withTry(off, ''), off);
  assert.deepEqual(withTry(off, '?try=layers,quests,energy,__proto__'), off);
  assert.deepEqual(withTry({ ...off, scenes: true }, '?try='), { ...off, scenes: true });
});
