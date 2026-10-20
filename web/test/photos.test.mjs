import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { photoSlides, photoFigure, archiveCredit, slideLabel, ARCHIVE_PAGE } from '../photos.js';
import { makeT } from '../i18n.js';

const load = name => JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url), 'utf8'));
const TABLES = { en: load('en'), sv: load('sv') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const link = (href, text) => `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(text)}</a>`;
const PAGE = id => `https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5000-Alla-fotografier/Fotografier/${id}.jpg.info`;
const TODAY = { key: 'aaaaaaaaaaaaaaaa-800.jpg', w: 800, h: 600, by: 'A', lic: 'CC BY-SA 4.0', page: 'https://commons.wikimedia.org/w/index.php?curid=1' };
const OLD = { key: 'bbbbbbbbbbbbbbbb-800.jpg', w: 800, h: 600, y: 1905, by: 'Erik Larsson', page: PAGE('SSMF001') };
const UNDATED = { key: 'cccccccccccccccc-800.jpg', w: 800, h: 600, page: PAGE('SSMF002') };

test('slides: today first, then the archive; a failed file or a search link is left out', () => {
  const card = { photo: TODAY, arch: [OLD, UNDATED, { ...OLD, key: 'd', page: 'https://digitalastadsmuseet.stockholm.se/fotoweb/archives/5000-Alla-fotografier/?516=X' }] };
  assert.deepEqual(photoSlides(card).map(s => s.key), [TODAY.key, OLD.key, UNDATED.key]);
  assert.deepEqual(photoSlides(card, new Set([TODAY.key])).map(s => s.key), [OLD.key, UNDATED.key]);
  assert.deepEqual(photoSlides({}), []);
  assert.ok(ARCHIVE_PAGE.test(PAGE('SSMF001')));
});

test('credit: one line linked to the photo page, in both languages', () => {
  assert.deepEqual(archiveCredit(OLD, EN), [{ text: 'Photo: Erik Larsson, Stadsmuseet i Stockholm, CC BY 4.0', href: OLD.page }]);
  assert.deepEqual(archiveCredit(UNDATED, SV), [{ text: 'Fotograf okänd, Stadsmuseet i Stockholm, CC BY 4.0', href: UNDATED.page }]);
});

test('the year strip: Today, the years, Undated; the shown one is current', () => {
  const slides = photoSlides({ photo: TODAY, arch: [OLD, UNDATED] });
  assert.deepEqual(slides.map(s => slideLabel(s, EN)), ['Today', '1905', 'Undated']);
  assert.deepEqual(slides.map(s => slideLabel(s, SV)), ['I dag', '1905', 'Odaterat']);
  const html = photoFigure(slides, 1, EN, esc, link, () => 'alt');
  assert.match(html, /<nav class="years" aria-label="Photos through the years">/);
  assert.match(html, /<button type="button" data-slide="1" aria-current="true">1905<\/button>/);
  assert.match(html, /<span class="year">1905<\/span>/);
  assert.ok(html.includes(`src="data/photos/${OLD.key}"`) && html.includes(`href="${OLD.page}"`));
});

test('one photo: no strip; none: nothing', () => {
  const html = photoFigure(photoSlides({ arch: [OLD] }), 0, EN, esc, link, () => 'alt');
  assert.ok(!html.includes('class="years"') && html.includes('Erik Larsson'));
  assert.equal(photoFigure([], 0, EN, esc, link, () => ''), '');
  // an index past the end shows the last photo
  assert.match(photoFigure(photoSlides({ photo: TODAY, arch: [OLD] }), 9, EN, esc, link, () => ''), /aria-current="true">1905/);
});
