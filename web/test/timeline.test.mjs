import { test } from 'node:test';
import assert from 'node:assert/strict';
import { placeLabels, labelAt, stepYear } from '../timeline.js';

const xOf = y => (y - 1100) / (2026 - 1100) * 1000;     // a 1000 px timeline from 1100 to Today
const measure = s => s.length * 6;

test('labels take priority, stay inside the canvas and never overlap', () => {
  const items = [
    { name: 'Stockholms slott', year: 1754, timeline: 1 }, { name: 'Storkyrkan', year: 1306, timeline: 1 },
    { name: 'Kungliga Operan', year: 1898, timeline: 2 }, { name: 'Nordiska museet', year: 1907, timeline: 3 },
    { name: 'Stockholms stadshus', year: 1923, timeline: 1 }, { name: 'Avicii Arena', year: 1989, timeline: 1 },
    { name: 'Vasamuseet', year: 1990, timeline: 3 },
  ];
  const placed = placeLabels(items, { xOf, width: 1000, measure });
  // Avicii Arena (1989, priority 1) would touch Stockholms stadshus (1923, priority 1, placed first by its year)
  assert.deepEqual(placed.map(p => p.name), ['Storkyrkan', 'Stockholms slott', 'Stockholms stadshus']);
  for (let i = 1; i < placed.length; i++) assert.ok(placed[i].x0 >= placed[i - 1].x1 + 8);
  assert.ok(placed.every(p => p.x0 >= 0 && p.x1 <= 1000));
  // Today's end: a label is pushed left to stay inside
  const end = placeLabels([{ name: 'Waterfront', year: 2025, timeline: 1 }], { xOf, width: 1000, measure })[0];
  assert.equal(end.x1, 1000);
  // a narrow phone timeline keeps fewer, never a label wider than the canvas
  assert.ok(placeLabels(items, { xOf: y => xOf(y) * 0.36, width: 360, measure }).length < placed.length);
  assert.deepEqual(placeLabels([{ name: 'x'.repeat(200), year: 1500, timeline: 1 }], { xOf, width: 1000, measure }), []);
});

test('labelAt finds the label under the pointer in the label strip only', () => {
  const placed = [{ name: 'A', x0: 100, x1: 160 }, { name: 'B', x0: 300, x1: 340 }];
  assert.equal(labelAt(placed, 130, 8).name, 'A');
  assert.equal(labelAt(placed, 98, 8).name, 'A');            // a little slack around the text
  assert.equal(labelAt(placed, 130, 40), null);              // lower down the pointer drags a handle
  assert.equal(labelAt(placed, 200, 8), null);
});

test('stepYear follows the slider keys and stays within its bounds', () => {
  const s = { value: 1900, min: 1100, max: 2025 };
  assert.equal(stepYear('ArrowRight', s), 1901);
  assert.equal(stepYear('ArrowLeft', { ...s, shift: true }), 1890);
  assert.equal(stepYear('PageUp', s), 1910);
  assert.equal(stepYear('Home', s), 1100);
  assert.equal(stepYear('End', s), 2025);
  assert.equal(stepYear('ArrowUp', { ...s, value: 2025 }), 2025);
  assert.equal(stepYear('Enter', s), null);
});
