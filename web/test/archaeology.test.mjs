import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { archaeologySection, BR_REGISTER } from '../archaeology.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const REPORT = n => `https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/?BR=${n}`;
const BR = { medieval: true, felled: [1676], credit: 'Stadsmuseet i Stockholm',
  inv: [{ from: 1988, to: 1988, report: REPORT(492) }, { from: 2003, to: 2003 }] };

test('archaeologySection in English: the facts, the report and the credit', () => {
  const html = archaeologySection(BR, EN, esc);
  assert.match(html, /<h4>Building archaeology<\/h4>/);
  assert.match(html, /<li>Medieval walls documented here<\/li>/);
  assert.match(html, /<li>Timber dated by tree rings: felled 1676<\/li>/);
  assert.match(html, /<li>Investigated 1988, 2003<\/li>/);
  assert.ok(html.includes(`<a href="${REPORT(492)}" target="_blank" rel="noopener">Report</a>`));
  assert.ok(html.includes(`<a href="${BR_REGISTER}" target="_blank" rel="noopener">Stadsmuseet i Stockholm</a>`));
});

test('archaeologySection in Swedish', () => {
  const html = archaeologySection(BR, SV, esc);
  assert.match(html, /<h4>Byggnadsarkeologi<\/h4>/);
  assert.match(html, /<li>Medeltida murar har dokumenterats här<\/li>/);
  assert.match(html, /<li>Virke daterat med årsringar: fällt 1676<\/li>/);
  assert.match(html, /<li>Undersökt 1988, 2003<\/li>/);
  assert.match(html, />Rapport<\/a>/);
  assert.match(html, />Stadsmuseet i Stockholm<\/a>/);
});

test('only the facts a record has; a span of years; several reports name their years; years shown once', () => {
  const html = archaeologySection({ credit: 'Stadsmuseet i Stockholm', inv: [
    { from: 2012, to: 2013, report: REPORT(303) }, { from: 2012, to: 2013, report: REPORT(458) }, {}] }, EN, esc);
  assert.doesNotMatch(html, /Medieval|tree rings/);
  assert.match(html, /<li>Investigated 2012–2013<\/li>/);
  assert.match(html, />Report 2012–2013<\/a> · <a/);
  assert.equal(html.match(/>Report 2012–2013</g).length, 2);
});

test('a report that is not https to Digitala Stadsmuseet is not linked', () => {
  const html = archaeologySection({ credit: 'Stadsmuseet i Stockholm',
    inv: [{ from: 1988, to: 1988, report: 'javascript:alert(1)' }, { from: 1990, to: 1990, report: 'http://digitalastadsmuseet.stockholm.se/x' }] }, EN, esc);
  assert.doesNotMatch(html, /class="reports"/);
});

test('nothing without records, and nothing on a private house', () => {
  assert.equal(archaeologySection(undefined, EN, esc), '');
  assert.equal(archaeologySection({ inv: [] }, EN, esc), '');
  assert.equal(archaeologySection(BR, EN, esc, true), '');
});
