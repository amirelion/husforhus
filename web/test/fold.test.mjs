// web/fold.js: the search fold, pinned by the vectors pipeline/textfold.py is tested against too.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fold } from '../fold.js';

const VECTORS = JSON.parse(readFileSync(new URL('./fixtures/fold.json', import.meta.url), 'utf8'));

test('fold matches the vectors the pipeline is held to', () => {
  for (const [text, folded] of VECTORS) assert.equal(fold(text), folded, text);
});

test('fold is idempotent and takes anything', () => {
  for (const [, folded] of VECTORS) assert.equal(fold(folded), folded);
  assert.equal(fold(undefined), '');
  assert.equal(fold(30), '30');
});
