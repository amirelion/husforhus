import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { archaeologySection, BR_REGISTER } from '../archaeology.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// a report's own page in the archive (the ?BR=<n> address shows the archive's first page for every number)
const REPORT = n => `https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/Dokument/DOK_1/SSM_DOK_${n}.pdf.info`;
const BR = { medieval: true, felled: [1676], credit: 'Stadsmuseet i Stockholm',
  inv: [{ from: 1988, to: 1988, report: REPORT(492) }, { from: 2003, to: 2003 }] };

test('archaeologySection in English: the facts, the investigations in one line, one link and the credit', () => {
  const html = archaeologySection(BR, EN, esc);
  assert.match(html, /<h4>Building archaeology<\/h4>/);
  assert.match(html, /<li>Medieval walls documented here<\/li>/);
  assert.match(html, /<li>Timber dated by tree rings: felled 1676<\/li>/);
  assert.match(html, /<li>Investigated 2 times, 1988–2003<\/li>/);
  assert.ok(html.includes(`<a href="${REPORT(492)}" target="_blank" rel="noopener">The latest report (1988), in the City Museum's archive</a>`));
  assert.equal(html.match(/class="reports"/g).length, 1);
  assert.ok(html.includes(`<a href="${BR_REGISTER}" target="_blank" rel="noopener">Stadsmuseet i Stockholm</a>`));
});

test('archaeologySection in Swedish', () => {
  const html = archaeologySection(BR, SV, esc);
  assert.match(html, /<h4>Byggnadsarkeologi<\/h4>/);
  assert.match(html, /<li>Medeltida murar har dokumenterats här<\/li>/);
  assert.match(html, /<li>Virke daterat med årsringar: fällt 1676<\/li>/);
  assert.match(html, /<li>Undersökt 2 gånger, 1988–2003<\/li>/);
  assert.match(html, />Den senaste rapporten \(1988\), i Stadsmuseets arkiv<\/a>/);
  assert.match(html, />Stadsmuseet i Stockholm<\/a>/);
});

test('one investigation reads as its year or span; of several reports only the latest is linked', () => {
  const one = archaeologySection({ credit: 'Stadsmuseet i Stockholm', inv: [{ from: 2012, to: 2013, report: REPORT(303) }] }, EN, esc);
  assert.doesNotMatch(one, /Medieval|tree rings/);
  assert.match(one, /<li>Investigated 2012–2013<\/li>/);
  const many = archaeologySection({ credit: 'Stadsmuseet i Stockholm', inv: [
    { from: 1961, to: 1961, report: REPORT(1) }, { from: 2019, to: 2019, report: REPORT(2) }, { from: 1997, to: 1997, report: REPORT(3) }, {}] }, EN, esc);
  assert.match(many, /<li>Investigated 4 times, 1961–2019<\/li>/);
  assert.equal(many.match(/<a href="https:\/\/digitalastadsmuseet/g).length, 1);
  assert.ok(many.includes(`<a href="${REPORT(2)}"`));
  assert.match(many, /The latest report \(2019\)/);
});

test('a link that is not a report page in the archive is not shown', () => {
  const html = archaeologySection({ credit: 'Stadsmuseet i Stockholm', inv: [
    { from: 1988, to: 1988, report: 'javascript:alert(1)' },
    { from: 1990, to: 1990, report: 'http://digitalastadsmuseet.stockholm.se/x.info' },
    { from: 1991, to: 1991, report: 'https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5004-Dokument-och-publikationer/?BR=12' }] }, EN, esc);
  assert.doesNotMatch(html, /class="reports"/);
});

test('nothing without records, and nothing on a private house', () => {
  assert.equal(archaeologySection(undefined, EN, esc), '');
  assert.equal(archaeologySection({ inv: [] }, EN, esc), '');
  assert.equal(archaeologySection(BR, EN, esc, true), '');
});
