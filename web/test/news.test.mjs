// web/news.json and web/news.js: What's new, About's second tab, in both languages.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { newsHtml, tabsHtml, newsDate, showDot, newestDate, nextTab, isAction, KINDS } from '../news.js';
import { aboutTarget } from '../about.js';
import { makeT } from '../i18n.js';

const load = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const NEWS = load('../news.json');
const TABLES = { en: load('../i18n/en.json'), sv: load('../i18n/sv.json') };
const EN = makeT(TABLES, 'en'), SV = makeT(TABLES, 'sv');
const text = html => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const LANGS = ['en', 'sv'];

test('news.json: well formed, both languages on every entry, valid dates newest first, the two kinds', () => {
  assert.ok(Array.isArray(NEWS) && NEWS.length >= 12 && NEWS.length <= 18, `${NEWS.length} entries`);
  NEWS.forEach((e, i) => {
    const at = `entry ${i} (${e.date})`;
    assert.deepEqual(Object.keys(e).filter(k => !['date', 'kind', 'title', 'text', 'action'].includes(k)), [], at);
    assert.match(e.date, /^\d{4}-\d{2}-\d{2}$/, at);
    assert.equal(new Date(`${e.date}T00:00:00Z`).toISOString().slice(0, 10), e.date, `${at}: a real day`);
    if (i) assert.ok(e.date <= NEWS[i - 1].date, `${at}: newest first`);
    assert.ok(KINDS.includes(e.kind), `${at}: kind ${e.kind}`);
    for (const k of ['title', 'text']) {
      assert.deepEqual(Object.keys(e[k]).sort(), LANGS, `${at}: ${k}`);
      for (const l of LANGS) assert.ok(typeof e[k][l] === 'string' && e[k][l].trim(), `${at}: ${k}.${l}`);
    }
    assert.notEqual(e.text.en, e.text.sv, `${at}: the Swedish is written, not copied`);
  });
  assert.ok(NEWS.at(-1).date >= '2026-10-14', 'from 2026-10-14 on');
});

test('news.json: no version strings, no addresses, actions only in the forms the map understands', () => {
  for (const e of NEWS) {
    const all = JSON.stringify(e);
    assert.doesNotMatch(all, /\bv20\d{2}/, e.date);           // v20261018-p4l and the like
    assert.doesNotMatch(all, /@/, e.date);
    assert.doesNotMatch(all, /\b(PR|s\d\d_)\w*|\.(py|js|json|csv|md)\b|\bHFH-\d/, e.date);   // no PRs, steps, files, refs
    if ('action' in e) assert.ok(isAction(e.action), `${e.date}: action ${e.action}`);
  }
  for (const ok of ['#about/sources', '#about/years', '?metro=1', '?plaques=1', 'stories', 'quests', 'walk']) assert.ok(isAction(ok), ok);
  for (const bad of ['#about/news', '#about', '?metro=0', 'https://example.org', 'javascript:alert(1)', '#scene', '', null]) {
    assert.ok(!isAction(bad), String(bad));
  }
});

test('the date in the page\'s language', () => {
  assert.equal(newsDate('2026-10-20', 'en'), '20 October 2026');
  assert.equal(newsDate('2026-10-20', 'sv'), '20 oktober 2026');
  assert.equal(newsDate('2026-01-01', 'en'), '1 January 2026');   // never a day early, whatever the time zone
});

test('the timeline: date, tag, title, text and action, in English and Swedish', () => {
  const entries = [{ date: '2026-10-17', kind: 'feature', title: { en: 'Tunnelbanan', sv: 'Tunnelbanan' },
    text: { en: 'The <metro>.', sv: 'Tunnelbanan.' }, action: '?metro=1' },
  { date: '2026-10-16', kind: 'data', title: { en: 'Years', sv: 'Årtal' }, text: { en: 'From registers.', sv: 'Från register.' },
    action: '#about/sources' },
  { date: '2026-10-15', kind: 'feature', title: { en: 'Stories', sv: 'Berättelser' }, text: { en: 'Eleven.', sv: 'Elva.' }, action: 'stories' }];
  const en = newsHtml(entries, EN);
  assert.match(en, /<time datetime="2026-10-17">17 October 2026<\/time>/);
  assert.match(text(en), /What's new on the map 17 October 2026 Feature Tunnelbanan The &lt;metro&gt;\. Show Tunnelbanan/);
  assert.match(en, /<a class="news-action" href="\?metro=1">Show Tunnelbanan<\/a>/);
  assert.match(en, /<a class="news-action" href="#about\/sources">Read more under Sources<\/a>/);
  assert.match(en, /<button type="button" class="news-action" data-open="stories">Open Stories<\/button>/);
  assert.match(text(en), /16 October 2026 Data Years/);
  const sv = text(newsHtml(entries, SV));
  assert.match(sv, /Nytt på kartan 17 oktober 2026 Funktion Tunnelbanan Tunnelbanan\. Visa Tunnelbanan/);
  assert.match(sv, /16 oktober 2026 Data Årtal Från register\. Läs mer under Källor/);
  assert.match(sv, /Öppna Berättelser/);
  // an action this build cannot run is left out; an action in no allowed form never renders
  assert.doesNotMatch(newsHtml(entries, EN, a => a !== '?metro=1'), /metro=1/);
  assert.doesNotMatch(newsHtml([{ ...entries[0], action: 'javascript:alert(1)' }], EN), /javascript|news-action/);
  // the real file renders whole in both languages, every action labelled
  for (const T of [EN, SV]) {
    const html = newsHtml(NEWS, T);
    assert.equal((html.match(/<li>/g) || []).length, NEWS.length);
    assert.equal((html.match(/class="news-action"/g) || []).length, NEWS.filter(e => e.action).length);
    assert.doesNotMatch(html, /news\.(action|kind)|about\.nav|\{\w+\}/);
  }
});

test('the tabs: a real tab list, the selected one in the tab order, its panel the only one shown', () => {
  const html = tabsHtml({ about: '<h2 id="about-title">A</h2>', news: '<h2>N</h2>', T: EN });
  assert.match(html, /role="tablist" aria-label="About the map"/);
  assert.match(html, /role="tab" id="about-tab-about" data-tab="about" aria-controls="about-panel-about" aria-selected="true"\s+tabindex="0">About</);
  assert.match(html, /id="about-tab-news" data-tab="news" aria-controls="about-panel-news" aria-selected="false"\s+tabindex="-1">What's new</);
  assert.match(html, /<div role="tabpanel" id="about-panel-about" aria-labelledby="about-tab-about">\s*<h2 id="about-title">A/);
  assert.match(html, /<div role="tabpanel" id="about-panel-news" aria-labelledby="about-tab-news" hidden>/);
  const news = tabsHtml({ about: '', news: '', T: SV, tab: 'news' });
  assert.match(news, /aria-selected="true"\s+tabindex="0">Nytt</);
  assert.match(news, /aria-selected="false"\s+tabindex="-1">Om kartan</);
  assert.match(news, /id="about-panel-about" aria-labelledby="about-tab-about" hidden>/);
});

test('arrow keys move between the tabs and wrap; Home and End go to the ends; other keys do nothing', () => {
  assert.equal(nextTab('ArrowRight', 'about'), 'news');
  assert.equal(nextTab('ArrowRight', 'news'), 'about');
  assert.equal(nextTab('ArrowLeft', 'about'), 'news');
  assert.equal(nextTab('Home', 'news'), 'about');
  assert.equal(nextTab('End', 'about'), 'news');
  assert.equal(nextTab('Enter', 'about'), null);
});

test('#about/news opens What\'s new; the other #about links keep their sections', () => {
  assert.equal(aboutTarget('#about/news'), 'news');
  assert.equal(aboutTarget('#about/sources'), 'sources');
  assert.equal(aboutTarget('#about'), '');
});

test('the dot: only for an entry newer than the one this device saw last, never on a first visit', () => {
  assert.equal(newestDate(NEWS), NEWS[0].date);
  assert.equal(showDot(NEWS, null), false);
  assert.equal(showDot(NEWS, '2026-10-01'), true);
  assert.equal(showDot(NEWS, NEWS[0].date), false);
  assert.equal(showDot([], '2026-10-01'), false);
});
