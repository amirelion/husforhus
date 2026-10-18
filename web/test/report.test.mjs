import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { kindsFor, buildingRef, refRows, formHtml, payload, fitSize, errorText } from '../report.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');
const text = html => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

const BORS = buildingRef({ gid: 12, b: { private: 0 }, card: { name: 'Börshuset', addr: 'Stortorget 2' }, district: 'Gamla stan',
  version: 'v20261017', year: '1778', source: 'Heritage register (RAÄ): built 1778', link: 'https://husforhus.se/?at=1.0,2.0,400' });
const HOUSE = buildingRef({ gid: 40, b: { private: 1 }, card: { addr: 'Villavägen 3' }, district: 'Bromma', version: 'v1',
  year: '1950s', source: 'x' });

test('the building reference is what the card shows', () => {
  assert.deepEqual(BORS, { gid: 12, name: 'Börshuset', address: 'Stortorget 2', district: 'Gamla stan', year: '1778',
    source: 'Heritage register (RAÄ): built 1778', version: 'v20261017', private: false, link: 'https://husforhus.se/?at=1.0,2.0,400' });
  assert.equal(HOUSE.private, true);
  // a card that hides a private house's address sends none
  assert.equal(buildingRef({ gid: 1, b: { private: 1 }, card: { addr: 'Villavägen 3' }, hideAddress: true }).address, '');
});

test('a card offers three kinds, a private house no photo, About only a suggestion', () => {
  assert.deepEqual(kindsFor(BORS), ['year_or_detail', 'photo', 'other']);
  assert.deepEqual(kindsFor(HOUSE), ['year_or_detail', 'other']);
  assert.deepEqual(kindsFor(null), ['general']);
});

test("the card's form is prefilled with its building, read-only, in English and Swedish", () => {
  const html = formHtml(BORS, EN);
  const t = text(html);
  for (const s of ['Something wrong?', 'Name Börshuset', 'Address Stortorget 2', 'District Gamla stan', 'Year shown 1778',
    'Source shown Heritage register (RAÄ): built 1778', 'Reference building 12, data v20261017',
    'Wrong or missing year or detail', 'Add a photo', 'Something else', 'This is my own photo',
    'I give Hus för hus the right to use it under CC BY 4.0, credited as:']) assert.ok(t.includes(s), s);
  // the reference is text in a list, never a field the reader can edit
  assert.ok(!/<input[^>]+value="Börshuset"/.test(html) && !html.includes('name="building'));
  assert.match(html, /<input id="report-email" name="email" type="email" required/);
  assert.match(html, /<textarea id="report-message" name="message" rows="5" required minlength="10" maxlength="2000"/);
  assert.match(html, /class="report-hp" aria-hidden="true"><label>[^<]+<input name="website" type="text" tabindex="-1"/);
  const sv = text(formHtml(BORS, SV));
  for (const s of ['Något som inte stämmer?', 'Fel eller saknat år eller uppgift', 'Lägg till ett foto', 'Något annat',
    'Det här är mitt eget foto', 'Jag ger Hus för hus rätt att använda det under CC BY 4.0, med namnet:', 'byggnad 12, data v20261017'])
    assert.ok(sv.includes(s), s);
});

test("a private house's form has no upload", () => {
  const html = formHtml(HOUSE, EN);
  assert.ok(!html.includes('type="file"'));
  assert.ok(!html.includes('Add a photo'));
});

test('About\'s form is a suggestion with no building', () => {
  const html = formHtml(null, EN);
  assert.ok(text(html).includes('Suggest something'));
  assert.match(html, /<input type="hidden" name="kind" value="general">/);
  assert.ok(!html.includes('report-ref') && !html.includes('type="file"'));
  assert.ok(text(formHtml(null, SV)).includes('Föreslå något'));
});

test('what the form sends', () => {
  const p = payload({ kind: 'year_or_detail', message: '  It was 1776.  ', email: ' a@example.org ', website: '', consent_own: true },
    BORS, 'sv', 4210.6);
  assert.deepEqual(p, { kind: 'year_or_detail', building: BORS, message: 'It was 1776.', email: 'a@example.org', lang: 'sv',
    website: '', elapsed: 4211 });
  const photo = payload({ kind: 'photo', message: 'x', email: 'a@example.org', photo_credit: ' A. Reader ', consent_own: true,
    consent_licence: false }, BORS, 'en', 9000);
  assert.equal(photo.photo_credit, 'A. Reader');
  assert.equal(photo.consent_own, true);
  assert.equal(photo.consent_licence, false);
  assert.equal(payload({ kind: 'general', message: 'x', email: 'e' }, null, 'en', 1).building, null);
});

test('photos are shrunk to 2048 px on their longest side, never enlarged', () => {
  assert.deepEqual(fitSize(4096, 3072), [2048, 1536]);
  assert.deepEqual(fitSize(3000, 6000), [1024, 2048]);
  assert.deepEqual(fitSize(800, 600), [800, 600]);
});

test("the Worker's answers read as sentences", () => {
  assert.match(errorText(EN, 429), /an hour/);
  assert.match(errorText(EN, 400, ['exif']), /JPEG, PNG or WebP/);
  assert.match(errorText(EN, 400, ['consent']), /both boxes/);
  assert.match(errorText(SV, 400, ['email']), /markerade/);
  assert.match(errorText(EN, 0), /could not be sent/);
  assert.equal(EN('report.thanks', { ref: 'HFH-123' }), 'Thanks: reference HFH-123. We may write to you at this address.');
  assert.ok(refRows(null, EN).length === 0);
});
