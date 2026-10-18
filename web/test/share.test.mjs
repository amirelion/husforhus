import test from 'node:test';
import assert from 'node:assert/strict';
import { SITE, shareText, shareLink, parseAt, findLayer } from '../share.js';

const at = { x: 12.345, z: -67.891, zoom: 420.4 };

test('a named building links by its name when search finds it again', () => {
  const text = shareText({ name: 'Börshuset', addr: 'Stortorget 2' }, {});
  assert.equal(text, 'Börshuset');
  assert.equal(shareLink({ text, resolves: true, ...at }), `${SITE}?q=B%C3%B6rshuset`);
});

test('a building without a name links by its first address', () => {
  const text = shareText({ addr: 'Västerlånggatan 7', addrn: 3 }, {});
  assert.equal(text, 'Västerlånggatan 7');
  assert.equal(shareLink({ text, resolves: true, ...at }), `${SITE}?q=V%C3%A4sterl%C3%A5nggatan%207`);
});

test('a text search does not find back links to the point and zoom instead', () => {
  assert.equal(shareLink({ text: 'Huset', resolves: false, ...at }), `${SITE}?at=12.3,-67.9,420`);
  assert.equal(shareLink({ text: '', resolves: true, ...at }), `${SITE}?at=12.3,-67.9,420`);
});

test('a private house links by its address only, never a name', () => {
  assert.equal(shareText({ name: 'Villa X', addr: 'Gränd 1' }, { private: true }), 'Gränd 1');
  assert.equal(shareText({ name: 'Villa X' }, { private: true }), '');
});

test('?at= reads back, and nonsense is refused', () => {
  assert.deepEqual(parseAt('12.3,-67.9,420'), { x: 12.3, z: -67.9, zoom: 420 });
  assert.equal(parseAt('1,2'), null);
  assert.equal(parseAt('a,b,c'), null);
  assert.equal(parseAt(null), null);
  assert.equal(parseAt('1,2,-5'), null);
});

test('?layer= finds a context layer by id and ignores unknown or empty ids', () => {
  const layers = [{ id: 'residents' }, { id: 'ports' }];
  assert.equal(findLayer(layers, 'ports'), layers[1]);
  assert.equal(findLayer(layers, 'nope'), null);
  assert.equal(findLayer(layers, null), null);
  assert.equal(findLayer([], 'ports'), null);
});
