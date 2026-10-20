// What's new: About's second tab, a short history of the map from web/news.json (hand-written, newest first, in both
// languages; docs-public/CHANGELOG.md keeps the full detail). Pure, tested by node --test (web/test/news.test.mjs);
// app.js puts tabsHtml into About's dialog, switches the tabs and runs the actions.

export const TABS = ['about', 'news'];
export const KINDS = ['feature', 'data'];
// localStorage: the newest entry's date this device has seen ('YYYY-MM-DD').
export const NEWS_KEY = 'hfh-news';
// An entry's action uses only links the map already understands: a section of About, the metro or plaques switch
// (?metro=1, ?plaques=1), or one of the Stories, Quests and Walk buttons' own openers.
export const ABOUT_SECTIONS = ['years', 'accuracy', 'limits', 'privacy', 'sources', 'contact', 'thanks'];
export const OPENERS = ['stories', 'quests', 'walk'];
export const isAction = a => typeof a === 'string' && (OPENERS.includes(a) || a === '?metro=1' || a === '?plaques=1'
  || ABOUT_SECTIONS.some(s => a === `#about/${s}`));

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// "2026-10-20" → "20 October 2026" / "20 oktober 2026".
export function newsDate(iso, lang) {
  const [y, m, d] = String(iso).split('-').map(Number);
  return new Intl.DateTimeFormat(lang === 'sv' ? 'sv-SE' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric',
    timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, d)));
}

export const newestDate = entries => entries?.[0]?.date || '';
// The dot on the About button: an entry newer than the one this device saw last. A first visit (nothing stored) has
// none, since everything is new then.
export const showDot = (entries, seen) => !!seen && newestDate(entries) > seen;

// The tab a key moves to (arrows wrap, Home and End go to the ends), or null for any other key.
export function nextTab(key, current) {
  const i = TABS.indexOf(current), n = TABS.length;
  const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: n - 1 }[key];
  return to === undefined ? null : TABS[(to + n) % n];
}

function actionHtml(a, T) {
  if (OPENERS.includes(a)) return `<button type="button" class="news-action" data-open="${a}">${esc(T(`news.action.${a}`))}</button>`;
  const label = a.startsWith('#about/') ? T('news.action.about', { section: T(`about.nav.${a.slice(7)}`) })
    : T(a === '?metro=1' ? 'news.action.metro' : 'news.action.plaques');
  return `<a class="news-action" href="${esc(a)}">${esc(label)}</a>`;
}

// The timeline. can(action): whether this build has what the action opens (no metro data, no Tunnelbanan link).
export function newsHtml(entries, T, can = () => true) {
  const L = o => o?.[T.lang] || o?.en || '';
  return `<h2 id="news-title">${esc(T('news.title'))}</h2>
    <ol class="news">${(entries || []).map(e => `<li>
      <p class="news-meta"><time datetime="${esc(e.date)}">${esc(newsDate(e.date, T.lang))}</time>
        <span class="news-kind">${esc(T(`news.kind.${e.kind}`))}</span></p>
      <h3>${esc(L(e.title))}</h3>
      <p>${esc(L(e.text))}</p>
      ${isAction(e.action) && can(e.action) ? `<p>${actionHtml(e.action, T)}</p>` : ''}</li>`).join('')}</ol>`;
}

// About's dialog: the two tabs and their panels; `about` is aboutHtml's page, unchanged.
export function tabsHtml({ about, news, T, tab = 'about' }) {
  const body = { about, news };
  return `<div class="about-tabs" role="tablist" aria-label="${esc(T('news.tabs'))}">${TABS.map(t => `<button type="button"
      role="tab" id="about-tab-${t}" data-tab="${t}" aria-controls="about-panel-${t}" aria-selected="${t === tab}"
      tabindex="${t === tab ? 0 : -1}">${esc(T(`news.tab.${t}`))}</button>`).join('')}</div>
    ${TABS.map(t => `<div role="tabpanel" id="about-panel-${t}" aria-labelledby="about-tab-${t}"${t === tab ? '' : ' hidden'}>
      ${body[t]}</div>`).join('')}`;
}
