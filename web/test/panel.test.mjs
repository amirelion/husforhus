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

import { photoOnlyFrom, photoOnlyHref, markPhotos, PHOTO_FLOAT } from '../panel.js';

test('the photo switch reads ?photos=1 and nothing else as on', () => {
  assert.equal(photoOnlyFrom('?photos=1'), true);
  assert.equal(photoOnlyFrom('?theme=natt&photos=1'), true);
  for (const s of ['', '?photos=0', '?photos=', '?photos=true', '?photo=1']) assert.equal(photoOnlyFrom(s), false, s);
});

test('the photo switch writes and clears ?photos and keeps the other parameters', () => {
  const on = photoOnlyHref('https://x.se/?theme=natt#about', true);
  assert.equal(on, 'https://x.se/?theme=natt&photos=1#about');
  assert.equal(photoOnlyFrom(new URL(on).search), true);
  assert.equal(photoOnlyHref(on, false), 'https://x.se/?theme=natt#about');
  assert.equal(photoOnlyHref('https://x.se/', false), 'https://x.se/');
});

test('markPhotos flags exactly the photo gids and clears the rest', () => {
  const attr = new Float32Array(3 * 12);
  [7, 8, 9].forEach((g, b) => { attr[b * 12 + 3] = g; attr[b * 12 + PHOTO_FLOAT] = 1; });
  assert.equal(markPhotos(attr, 3, new Set([8])), 1);
  assert.deepEqual([0, 1, 2].map(b => attr[b * 12 + PHOTO_FLOAT]), [0, 1, 0]);
  assert.equal(attr[1 * 12 + 3], 8);                     // the gid is untouched
});

test('the plaques switch is off by default, on from ?plaques=1 or a stored "on"', async () => {
  const { plaquesOnFrom, PLAQUE_KEY, PLAQUE_PARAM } = await import('../panel.js');
  assert.equal(PLAQUE_KEY, 'hfh-plaques');
  assert.equal(PLAQUE_PARAM, 'plaques');
  assert.equal(plaquesOnFrom('', null), false);
  assert.equal(plaquesOnFrom('?plaques=0', 'off'), false);
  assert.equal(plaquesOnFrom('?plaques=true', null), false);
  assert.equal(plaquesOnFrom('?plaques=1', null), true);
  assert.equal(plaquesOnFrom('?plaques=1', 'off'), true);
  assert.equal(plaquesOnFrom('', 'on'), true);
  assert.equal(plaquesOnFrom('?photos=1', 'yes'), false);
});

test('the plaques switch writes and clears ?plaques and keeps the other parameters', async () => {
  const { plaquesHref } = await import('../panel.js');
  assert.equal(plaquesHref('https://x.se/?photos=1#about', true), 'https://x.se/?photos=1&plaques=1#about');
  assert.equal(plaquesHref('https://x.se/?plaques=1&lang=sv', false), 'https://x.se/?lang=sv');
  assert.equal(plaquesHref('https://x.se/?plaques=1', true), 'https://x.se/?plaques=1');
});

test('the quests-and-walks switch is on by default; only a stored "off" turns it off', async () => {
  const { questsOnFrom, QUESTS_KEY } = await import('../panel.js');
  assert.equal(QUESTS_KEY, 'hfh-quests-walks');
  for (const stored of [null, undefined, '', 'on', 'yes']) assert.equal(questsOnFrom(stored), true, String(stored));
  assert.equal(questsOnFrom('off'), false);
});
