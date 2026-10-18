// The triage page's "Accept" form (web/admin/accept.js).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { changesFor, acceptFormHtml, readAccept, addressesFor } from '../admin/accept.js';

const B = { gid: 12, address: 'Stortorget 2', version: 'v20261017', private: false };
const R = { id: 5, reference: 'HFH-5', building: B, photo_key: '', consent_own: false, consent_licence: false, photo_credit: '' };

test('the changes a report can make', () => {
  assert.deepEqual(changesFor(R), ['year', 'main_address', 'name', 'none']);
  assert.deepEqual(changesFor({ ...R, photo_key: 'k', consent_own: true, consent_licence: true }), ['year', 'main_address', 'name', 'photo', 'none']);
  assert.deepEqual(changesFor({ ...R, building: { ...B, private: true }, photo_key: 'k', consent_own: true, consent_licence: true }),
    ['year', 'main_address', 'none']);
  assert.deepEqual(changesFor({ ...R, building: null }), ['none']);
});

test('the form: the address select from the map data, a required one-line note, no email field', () => {
  const html = acceptFormHtml(R, ['Stortorget 2', 'Källargränd 1']);
  assert.match(html, /<option>Stortorget 2<\/option><option>Källargränd 1<\/option>/);
  assert.match(html, /name="public_note" maxlength="200" required/);
  assert.match(html, /name="name" maxlength="120"/);
  assert.match(html, /name="replaces_register"/);
  assert.ok(!/<input[^>]*name="replaces_register"[^>]*checked/.test(html));     // default off
  assert.ok(!html.includes('@'));
  assert.match(acceptFormHtml(R, []), /no addresses found/);
});

test('readAccept: year, range, address, name, note', () => {
  const ok = f => readAccept({ public_note: 'Seen on the plaque.', ...f });
  assert.deepEqual(ok({ kind: 'year', year: '1938' }), { errors: [], body: { kind: 'year', value: '1938', public_note: 'Seen on the plaque.', replaces_register: false } });
  assert.equal(ok({ kind: 'year', year: '1938-1939', replaces_register: 'on' }).body.replaces_register, true);
  assert.deepEqual(ok({ kind: 'year', year: '38' }).errors, ['value']);
  assert.deepEqual(ok({ kind: 'year', year: '1939-1938' }).errors, ['value']);
  assert.equal(ok({ kind: 'main_address', main_address: 'Källargränd 1', replaces_register: 'on' }).body.replaces_register, false);
  assert.deepEqual(ok({ kind: 'name', name: 'x'.repeat(121) }).errors, ['value']);
  assert.deepEqual(ok({ kind: 'none' }).body.value, '');
  assert.deepEqual(readAccept({ kind: 'none', public_note: '' }).errors, ['public_note']);
  assert.deepEqual(readAccept({ kind: 'none', public_note: 'x'.repeat(201) }).errors, ['public_note']);
});

test('addressesFor: the gid\'s addresses across the version\'s search shards', async () => {
  const files = {
    '/data/v20261017/search/index.json': { streets: [['Stortorget', 3, [0], 's'], ['Källargränd', 1, [0], 'k'], ['Svartmangatan', 1, [0], 's']] },
    '/data/v20261017/search/addr/s.json': { Stortorget: [['2', 12, 0], ['3', 13, 0]], Svartmangatan: [['1', 14, 0]] },
    '/data/v20261017/search/addr/k.json': { 'Källargränd': [['1', 12, 0]] },
  };
  const asked = [];
  const got = await addressesFor(12, 'v20261017', async u => { asked.push(u); return files[u] ?? null; });
  assert.deepEqual(got.sort(), ['Källargränd 1', 'Stortorget 2']);
  assert.equal(asked.filter(u => u.endsWith('/s.json')).length, 1);
  assert.deepEqual(await addressesFor(12, '../etc', async () => { throw new Error('no fetch'); }), []);
});
