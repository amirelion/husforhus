// About: written from the build, in the page's language, so its numbers cannot drift from
// the data. Every number comes from stockholm.json (stats, accuracy, about, attribution: aboutTokens); every sentence
// from web/i18n by id. Pure, tested by node --test (web/test/about.test.mjs); app.js puts aboutHtml into the dialog and
// opens it at a section for a link to #about/<section>.

export const SECTIONS = ['years', 'accuracy', 'limits', 'privacy', 'sources', 'contact'];
const RECORD = ['curated', 'cited', 'raa', 'raa_old', 'wikidata', 'osm', 'reader'];
const SOURCE_ROWS = ['curated', 'cited', 'raa', 'raa_old', 'raa_area', 'wikidata', 'osm', 'reader', 'estimate', 'none'];
const AMSTERDAM = 'https://github.com/alexbarakov/amsterdam-by-building';
const PARIS = 'https://paris.bogachev.fr/';
const REPO = 'https://github.com/amirelion/husforhus';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const link = (href, text) => `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(text)}</a>`;
const sum = a => a.reduce((x, y) => x + y, 0);
// The summary's four kinds as the source table's rows (pipeline/report_accuracy.py KIND_SOURCES).
const KIND_SOURCES = [RECORD, ['raa_area'], ['estimate'], ['none']];

// `units` split in proportion to the counts by largest remainder, ties to the earlier count (report_accuracy.apportion).
function apportion(counts, units) {
  const total = sum(counts);
  if (!total) return counts.map(() => 0);
  const scaled = counts.map(c => c * units), floor = scaled.map(v => Math.floor(v / total));
  const order = counts.map((_, i) => i).sort((i, j) => (scaled[j] % total) - (scaled[i] % total) || i - j);
  for (const i of order.slice(0, units - sum(floor))) floor[i] += 1;
  return floor;
}

// Each source's share in tenths of a percent, as the accuracy page rounds them (report_accuracy.kind_shares):
// the kinds rounded together to 1000, then each kind's tenths split among its sources, so About and the page agree.
function sourceTenths(src) {
  const kinds = apportion(KIND_SOURCES.map(ks => sum(ks.map(k => src[k] || 0))), 1000), at = {};
  KIND_SOURCES.forEach((ks, i) => apportion(ks.map(k => src[k] || 0), kinds[i]).forEach((u, j) => { at[ks[j]] = u; }));
  return at;
}

// "30.1%" / "30,1 %" (Intl's own percent form per language).
export const pct = (x, lang, digits = 1) => new Intl.NumberFormat(lang === 'sv' ? 'sv-SE' : 'en',
  { style: 'percent', minimumFractionDigits: digits, maximumFractionDigits: digits }).format(x);

// The houses the map estimates: the accuracy table's measured house cells whose status is "estimate".
function houseCells(acc) {
  return (acc?.cells || []).filter(c => c.group === 'house' && c.status === 'estimate');
}

// Every value About's sentences take, formatted in T's language.
export function aboutTokens(config, T) {
  const s = config.stats, a = config.about || {}, acc = config.accuracy || {}, src = s.bySrc || {};
  const n = s.buildings, num = x => T.num(x), share = x => pct(x / Math.max(1, n), T.lang);
  const record = sum(RECORD.map(k => src[k] || 0));
  const withYear = n - (src.none || 0);
  // the counts the accuracy page gives (pipeline/report_accuracy.py): the test houses in the cells the map uses, from
  // by_true_period's exact counts; within one period weighted over those cells
  const cells = houseCells(acc), byPeriod = acc.by_true_period || [];
  const cellN = sum(byPeriod.map(r => r.n_estimate || 0)), right = sum(byPeriod.map(r => r.right_estimate || 0));
  const cellsN = sum(cells.map(c => c.n));
  const within = cellsN ? sum(cells.map(c => c.n * c.within_one)) / cellsN : 0;
  const ext = acc.external || {}, area = acc.area || {};
  const [y, m] = String(a.snapshot || '').split('-').map(Number);
  const snapshot = y && m ? new Intl.DateTimeFormat(T.lang === 'sv' ? 'sv-SE' : 'en', { month: 'long', year: 'numeric' })
    .format(new Date(Date.UTC(y, m - 1, 15))) : esc(a.snapshot || '');
  const v = String(config.version || '').match(/^v(\d{4})(\d{2})(\d{2})/);
  return {
    buildings: num(n), with_year: num(withYear), with_year_pct: share(withYear), record: num(record),
    area: num(src.raa_area || 0), estimated: num(src.estimate || 0), unknown: num(src.none || 0),
    exact: num(s.byFlag?.exact || 0), range: num(s.byFlag?.range || 0), long: num(s.byFlag?.long || 0),
    cited_period: num(a.citedPeriod || 0),
    private_cat: num(a.privateCategory || 0), private_dated: num(a.privateDated || 0), fewest: esc(a.fewestPrivateYears ?? ''),
    near: num(a.nearM ?? acc.near_m ?? 0), late: esc(a.lateYear ?? ''), min_cell: num(acc.min_cell ?? 0),
    min_right: pct(acc.min_right ?? 0, T.lang, 0), max_band: num(acc.max_band ?? 0),
    n: num(cellN), right_n: num(right), right: pct(cellN ? right / cellN : 0, T.lang, 0), within: pct(within, T.lang, 0),
    check_n: num(ext.n_all || 0), check_shown: num(ext.n_estimate || 0), check_right: num(ext.right_estimate || 0),
    check_new: num(ext.from_1990?.n_all || 0), area_n: num(area.n || 0), area_right: pct(area.right_period || 0, T.lang, 0),
    snapshot, gamla_n: num(a.gamla?.n || 0), gamla_dated: num(a.gamla?.dated || 0), floors_osm: num(s.floorsOsm || 0),
    rare: esc(a.rareArchitect ?? ''), maker: esc(a.maker || ''), contact: a.contact ? link(`mailto:${a.contact}`, a.contact) : '',
    repo: link(REPO, 'github.com/amirelion/husforhus'), version: esc(config.version || ''), date: v ? `${v[1]}-${v[2]}-${v[3]}` : '',
    // The terrain (stockholm.json `terrain`): the default relief, the Hills slider's top, where the heights
    // come from. T.num formats them in the page's language, so Swedish writes a decimal comma ("2,5"), English a point
    // ("2.5"); a whole number has no decimals ("2", not "2.0" or "2,0").
    relief: scaleNum(config.terrain?.relief ?? 1, T),
    relief_max: scaleNum(config.terrain?.reliefMax ?? 1, T),
    terrain_from: esc(T(config.terrain?.source === 'dtm' ? 'about.limits.terrain.dtm' : 'about.limits.terrain.contours')),
  };
}

// A relief factor in the page's language: 2.5 → "2.5" / "2,5", 2 → "2" (the slider moves in steps of 0.5).
const scaleNum = (x, T) => T.num(x, Number.isInteger(x) ? 0 : 1);

function cellTable(cells, config, T, withGroup) {
  const labels = config.accuracyLabels?.[T.lang] || config.accuracyLabels?.en || {};
  const en = config.accuracyLabels?.en || {};
  const group = g => labels.groups?.[g] || en.groups?.[g] || g;
  const era = e => labels.eras?.[e] || e;
  const head = [...(withGroup ? ['group'] : []), 'era', 'city', 'n', 'right', 'within', 'band', 'does'];
  const row = c => [
    ...(withGroup ? [esc(group(c.group))] : []), esc(era(c.era)), esc(T(c.inner ? 'about.acc.inner' : 'about.acc.outer')),
    T.num(c.n), c.right_period !== undefined ? pct(c.right_period, T.lang, 0) : '–',
    c.within_one !== undefined ? pct(c.within_one, T.lang, 0) : '–', c.band !== undefined ? `±${T.num(c.band)}` : '–',
    esc(T(`about.acc.status.${c.status}`)),
  ];
  return `<div class="table" tabindex="0"><table><thead><tr>${head.map(h => `<th>${esc(T(`about.acc.col.${h}`))}</th>`).join('')}</tr></thead>
    <tbody>${cells.map(c => `<tr>${row(c).map(x => `<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

// The whole About, as HTML for the dialog's <article>. howto: the drag hint in the page's language. The limits name
// the boats while config.features.ferries is set; app.js sets it from whether their routes loaded, not the build's flag.
export function aboutHtml(config, T, howto = '') {
  const k = aboutTokens(config, T), s = config.stats, a = config.about || {}, acc = config.accuracy || {};
  const P = (id, vars = k) => `<p>${T(id, vars)}</p>`;
  const h3 = (id, name) => `<h3 id="about-${name}" tabindex="-1">${esc(T(id))}</h3>`;
  const src = s.bySrc || {}, tenths = sourceTenths(src);
  const sourceRows = SOURCE_ROWS.map(r => `<tr><td>${esc(T(`about.src.${r}`))}</td><td>${T.num(src[r] || 0)}</td>
    <td>${pct(tenths[r] / 1000, T.lang)}</td></tr>`).join('');
  // every other cell: the house cells the map does not estimate (late houses, the old town) and the other types
  const shown = houseCells(acc), others = (acc.cells || []).filter(c => !shown.includes(c));
  // a build from before the `about` block: its sentences go rather than read "0 of the 0" or "before ,"
  const has = !!config.about;   // (and without accuracyLabels the other table, whose group names it holds)
  // the independent check is "too small to confirm" only while the accuracy page says it is not measured
  const check = ext => ext.status === 'measured' ? 'about.acc.check.measured' : 'about.acc.check';
  const ext = acc.external || {};
  // each source in the standard credit form, "Dataset: publisher, licence" (plus "processed"), in the page's language; a
  // build from before those lines keeps its one attribution text
  const sources = (config.attribution || []).map(x => {
    const line = x.credit?.[T.lang] || x.text;
    return `<li>${x.url ? link(x.url, line) : esc(line)}${x.licence_url ? ` (${link(x.licence_url, x.licence)})` : ''}</li>`;
  }).join('');
  return `
    <h2 id="about-title">${esc(T('about.title'))}</h2>
    <p class="lead">${T('about.lead', k)}</p>
    <nav class="about-nav" aria-label="${esc(T('about.nav'))}">${SECTIONS.map(n =>
      `<a href="#about/${n}" data-section="${n}">${esc(T(`about.nav.${n}`))}</a>`).join('')}</nav>
    <h3>${esc(T('about.use.title'))}</h3>
    <ul>${['play', 'range', 'period', 'floors', 'card', 'search', 'look'].map(i => `<li>${esc(T(`about.use.${i}`))}</li>`).join('')}
      ${howto ? `<li>${esc(howto)}</li>` : ''}</ul>
    ${h3('about.years.title', 'years')}
    ${P('about.years.lead')}
    <div class="table" tabindex="0"><table><thead><tr><th>${esc(T('about.table.source'))}</th><th>${esc(T('about.table.buildings'))}</th>
      <th>${esc(T('about.table.share'))}</th></tr></thead><tbody>${sourceRows}
      <tr class="total"><td>${esc(T('about.table.all'))}</td><td>${k.buildings}</td><td>${pct(1, T.lang)}</td></tr></tbody></table></div>
    ${P('about.years.kinds')}
    ${a.citedPeriod ? P('about.years.cited') : ''}
    ${has ? P('about.years.private') : ''}
    ${h3('about.acc.title', 'accuracy')}
    ${P('about.acc.how')}
    <p>${esc(T('about.acc.rule'))}</p>
    <ul>${['house', 'near', ...(has ? ['late'] : []), 'cell'].map(i => `<li>${T(`about.acc.rule.${i}`, k)}</li>`).join('')}</ul>
    ${P('about.acc.result')}
    <p>${esc(T('about.acc.houses'))}</p>
    ${cellTable(shown, config, T, false)}
    ${others.length && config.accuracyLabels ? `<details><summary>${esc(T('about.acc.others'))}</summary>${cellTable(others, config, T, true)}</details>` : ''}
    <p>${T(check(ext), k)}${ext.from_1990?.n_all && !ext.from_1990?.n_estimate ? ` ${T('about.acc.check.new', k)}` : ''}</p>
    ${acc.area?.n ? P('about.acc.area') : ''}
    ${h3('about.limits.title', 'limits')}
    <ul>${['standing', ...(has ? ['snapshot'] : []), 'one', ...(has ? ['gamla', 'new'] : []), 'height', 'colour', 'private',
      ...(config.terrain ? [config.terrain.relief === 1 ? 'terrain' : 'terrain.scaled'] : []),
      ...(config.features?.ferries ? ['boats'] : [])]
      .map(i => `<li>${T(`about.limits.${i}`, k)}</li>`).join('')}</ul>
    ${h3('about.privacy.title', 'privacy')}
    <p class="lead">${esc(T('about.privacy.lead'))}</p>
    ${P('about.privacy.shows')}
    <p>${T('about.privacy.never')}</p>
    <ul>${['who', 'ids', 'byggherre', 'year'].map(i => `<li>${esc(T(`about.privacy.never.${i}`))}</li>`).join('')}</ul>
    ${has ? P('about.privacy.private') : ''}
    ${a.privateAddresses === false ? P('about.privacy.private.address') : ''}
    ${P('about.privacy.why')}
    ${P('about.privacy.visit')}
    ${P('about.privacy.form')}
    ${P(a.contact ? 'about.privacy.hide' : 'about.privacy.hide.nocontact')}
    ${P(a.maker ? 'about.privacy.who' : 'about.privacy.who.nomaker')}
    ${h3('about.sources.title', 'sources')}
    <ul id="about-data">${sources}
      <li>${esc(T('about.sources.wikipedia'))}</li><li>${esc(T('about.sources.commons'))}</li>
      <li>${esc(T('about.sources.readers', { n: T.num(a.readers || 0) }))}</li></ul>
    <p>${esc(T('about.sources.odbl'))}</p>
    ${h3('about.thanks.title', 'thanks')}
    <p>${T('about.thanks.code', { amsterdam: link(AMSTERDAM, 'Amsterdam, building by building'),
      paris: link(PARIS, 'Paris, building by building') })}</p>
    <p>${esc(T('about.thanks.more'))}</p>
    ${h3('about.contact.title', 'contact')}
    ${a.maker ? P('about.contact.maker') : ''}
    ${a.contact ? P('about.contact.write') : ''}
    ${!a.maker && !a.contact ? P('about.contact.none') : ''}
    ${a.maker && !a.contact ? P('about.contact.none.contact') : ''}
    ${!a.maker && a.contact ? P('about.contact.none.maker') : ''}
    <p><button type="button" class="report-open">${esc(T('about.contact.suggest'))}</button></p>
    ${P('about.contact.code')}
    ${P('about.contact.data')}`;
}

// "#about/privacy" → "privacy"; "#about/news" → "news" (the What's new tab, web/news.js); "#about" → "";
// anything else → null.
export function aboutTarget(hash) {
  const m = String(hash || '').match(/^#about(?:\/([a-z]+))?$/);
  return m ? (m[1] && SECTIONS.concat('thanks', 'news').includes(m[1]) ? m[1] : '') : null;
}
