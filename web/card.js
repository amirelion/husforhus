// Text for the building card. Pure functions over a building from readAttrs and its card shard entry
// (`card`: s03_tiles' card fields), tested by node --test. Every string comes from web/i18n through T (web/i18n.js
// makeT), so the card reads the same in English and Swedish; T.lang picks the decade's form and T.num the number format.
import { YFLAG, YSRC, FSRC, PROT } from './codes.js';

// "1950s" / "1950-talet"; a decade that starts a century prints as its ten years, "1900–1909" in both languages, since
// "1900s" and "1900-talet" read as the century as readily as the decade.
export const decade = (year, lang = 'en') => {
  const start = Math.floor(year / 10) * 10;
  return start % 100 === 0 ? `${start}–${start + 9}` : `${start}${lang === 'sv' ? '-talet' : 's'}`;
};
const span = (a, b) => (b && b !== a ? `${a}–${b}` : String(a));
// An estimate's "±N": the band around the year (year_from/year_to), which clamping to 1000..2026 may have cut on
// one side, so the larger side counts.
export const band = b => Math.max(b.year - b.yearFrom, b.yearTo - b.year);
// A source that said only the decade (a Wikidata or OSM "1640s": year = the decade start over a 10-year range). RAÄ's
// completion-year ranges have year = yearTo, so they never match.
export const decadeOnly = b => b.yflag === YFLAG.RANGE && b.year === b.yearFrom && b.yearTo === b.yearFrom + 9
  && b.yearFrom % 10 === 0;
const SRC = { [YSRC.RAA]: 'raa', [YSRC.RAA_OLD]: 'raa_old', [YSRC.WIKIDATA]: 'wikidata', [YSRC.OSM]: 'osm', [YSRC.READER]: 'reader',
  [YSRC.CITED]: 'cited', [YSRC.BYGGLOV]: 'bygglov' };
const EST_FLAGS = [YFLAG.AREA, YFLAG.ESTIMATE, YFLAG.PERIOD];
export const isEstimate = b => EST_FLAGS.includes(b.yflag);

// The big line in the card's header band. A building no period colours but a cited record dates all the same (its
// card's `yc`, citedShown) shows what the record gives, "≈ early 1600s", "≈ 1580–1649" (citedHead), not "Year unknown".
export function yearLine(b, periodLabel, T, yc) {
  if (b.yflag === YFLAG.UNKNOWN) return citedShown(b, yc) ? citedHead(yc, T) : T('card.unknown');
  // Period only, private house or not: the estimate's band is wider than a decade, so a decade would claim too much.
  if (b.yflag === YFLAG.PERIOD) return periodLabel || T('card.unknown');
  // A private house shows only its decade, whatever its yflag; an estimated or area-dated one says "≈".
  if (b.private) return (b.yflag === YFLAG.ESTIMATE || b.yflag === YFLAG.AREA ? '≈ ' : '') + decade(b.year, T.lang);
  if (decadeOnly(b)) return decade(b.year, T.lang);
  return b.yflag === YFLAG.AREA || b.yflag === YFLAG.ESTIMATE ? `≈ ${b.year}` : String(b.year);
}

// How the year is known: one unlabelled line under the band. A private house never shows more than its decade:
// its line names the source, then the decade rule, never a span or a band. A curated building rebuilt from new on
// older cellars says so (`card.cellars`); the year stays the standing building's.
export function sourceLine(b, T, card = {}) {
  // a cited span no map period holds 3/4 of (or an either pair's union): no colour, but the card says what the records
  // give (citedShown)
  if (b.yflag === YFLAG.UNKNOWN) return citedShown(b, card?.yc) ? citedLine(b, T, card.yc) : T('card.src.unknown');
  if (b.yflag === YFLAG.PERIOD) {
    if (b.ysrc === YSRC.CITED) return b.private ? T('card.private.cited.period') : citedLine(b, T, card?.yc);
    return b.private ? T('card.private.period') : T('card.src.period');
  }
  if (b.private) {
    if (b.ysrc === YSRC.BYGGLOV) return [permitLine(b, T), T('card.private.rule')].join(' · ');
    const how = b.ysrc === YSRC.ESTIMATE ? 'estimate' : b.ysrc === YSRC.RAA_AREA ? 'area' : SRC[b.ysrc];
    return [how && T(`card.private.${how}`), T('card.private.rule')].filter(Boolean).join(' · ');
  }
  if (b.ysrc === YSRC.CURATED) {
    return T(card?.cellars ? 'card.src.curated.cellars' : 'card.src.curated', { span: span(b.yearFrom, b.yearTo) });
  }
  // A reader's report the owner checked (pipeline/contributions.py): its reference and the owner's note, card `yrd`
  // (app.js links the line to the report's issue, `yrd.url`, when there is one).
  if (b.ysrc === YSRC.CITED) return citedLine(b, T, card?.yc);
  if (b.ysrc === YSRC.READER) return card?.yrd ? T('card.src.reader', { ref: card.yrd.ref, note: card.yrd.note }) : T('card.private.reader');
  if (b.ysrc === YSRC.BYGGLOV) return permitLine(b, T);
  if (b.ysrc === YSRC.RAA_AREA) return T('card.src.area');
  if (b.ysrc === YSRC.ESTIMATE) return T('card.src.estimate', { n: band(b) });
  const key = SRC[b.ysrc];
  if (!key) return '';
  if (decadeOnly(b)) {
    const d = decade(b.year, T.lang);
    if (!d.includes('–')) return T(`card.src.${key}.decade`, { decade: d });
  }
  return T(b.yflag === YFLAG.LONG ? `card.src.${key}.long` : `card.src.${key}`, { span: span(b.yearFrom, b.yearTo) });
}

// A building-permit year (pipeline/years_bygglov.py): the year the property's first permit was closed, from the City
// Archives' card index, "Building permit closed 1934 (Stadsarkivet)", never with "≈" (a record, not an estimate) and
// never with a span (the opening year is a parse of the case number). A private house names its decade instead, "Building
// permit closed in the 1930s (Stadsarkivet)", and "1900–1909" for a decade that starts a century. Nothing per card
// links the archive: its card pages show the property designation and the exact year (About links its information page).
export function permitLine(b, T) {
  if (!b.private) return T('card.src.bygglov', { year: b.yearTo });
  const d = decade(b.year, T.lang);
  return d.includes('–') ? T('card.private.bygglov.span', { span: d }) : T('card.private.bygglov', { decade: d });
}

// A cited record's line (pipeline/cited.py; card `yc`, its source `s`, its page `u`, `k` "rebuilt" for a new house
// that replaced an older one, `c` where the record says "about"), as §14 of the Gamla stan research words it: "Built
// 1855–1858 · KulturNav (ArkDes)", "Built in the 1640s · …", "Built about 1640, replacing an older house · …". A PERIOD
// row (the record gives only a century, a half-century or a span; its colour is the map period holding at least 3/4
// of it) says "≈", like every year the map shows in the estimate tone: "≈ built in the 1600s · …", or "≈ medieval
// origin · …" for a medieval one (no earlier bound than FLOOR_YEAR, or ending by MEDIEVAL_END: the records date the old
// fabric, which later rebuilds kept). A period no map period holds 3/4 of ships no year (no colour): its card carries
// the span, `a`..`z`, and says the same. Two sources that differ (an either pair, `e`: two readings {a, z, s, u},
// earliest first) read "Built in 1785 or 1798 (sources differ)", "≈ medieval origin, or built in the 1600s (sources
// differ)", each reading linked to its source; and `r`, the rebuilds and extensions the records name, and `o`, the other
// houses the footprint holds, make the pinned card's second line, "Rebuilt or extended 1780 and 1906 · Also part of
// this building: a house built 1804". app.js links each part (citedParts, citedMore) to its record.
const CITED_SRCS = ['kulturnav', 'wikipedia_sv', 'ssm_inventory', 'ssm_br', 'stockholm_stage'];
const FLOOR_YEAR = 1000;   // pipeline/yearrules.py: a row from it has no earlier bound ("medieval")
const MEDIEVAL_END = 1520; // the Swedish Middle Ages end with the 1520s; a span ending by then is medieval
const BUILT_MAX = 100;     // pipeline/cited.py: a span over 100 years is a period
// pipeline/cited.py century_like: a century or half-century (both ends on a 50-year boundary) or a span over BUILT_MAX
// years is a period, never a construction window; a reading from FLOOR_YEAR is one too ("medieval")
const periodLike = (a, z) => {
  const n = z - a + 1;
  return a === FLOOR_YEAR || n > BUILT_MAX || (n >= 50 && a % 50 === 0 && (z % 50 === 0 || z % 50 === 49));
};
const medieval = (a, z) => a === FLOOR_YEAR || z <= MEDIEVAL_END;
const srcName = (s, T) => T(CITED_SRCS.includes(s) ? `card.cited.src.${s}` : 'card.cited.src.none');
// When a span was, in the words its record uses (pipeline/cited.py stores each as a span): "1643", "1855–1858", "in
// the 1640s", "in the 1600s", "in the first half of the 1600s", "in the early 1600s" (c..c+24), "around the mid-1600s"
// (c+40..c+60), "in the late 1600s" (c+75..c+99), "in the 1600s–1700s" (two centuries), "between 1500 and the mid-1600s"
// (c..c+149), "in the late 1630s or early 1640s" (d+5..d+14), "about 1640" (`circa`, one year); any other span as its
// years. `year`: a year or a span takes the language's preposition too ("in 1785"; Swedish none), for a line that
// lists two.
function when(a, z, T, year = false, circa = false) {
  if (circa) return T('card.cited.when.about', { y: span(a, z) });
  const c = Math.floor(a / 100) * 100;
  if (a === c && z === c + 99) return T('card.cited.when.century', { c });
  if (a === c && z === c + 49) return T('card.cited.when.half1', { c });
  if (a === c + 50 && z === c + 99) return T('card.cited.when.half2', { c });
  if (a === c && z === c + 199) return T('card.cited.when.centuries', { a: c, b: c + 100 });
  if (a === c && z === c + 149) return T('card.cited.when.between', { c, d: c + 100 });
  if (a === c && z === c + 24) return T('card.cited.when.early', { c });
  if (a === c + 40 && z === c + 60) return T('card.cited.when.mid', { c });
  if (a === c + 75 && z === c + 99) return T('card.cited.when.late', { c });
  if (a % 10 === 5 && z === a + 9) return T('card.cited.when.decades', { a: a - 5, b: a + 5 });
  const d = a % 10 === 0 && z === a + 9 ? decade(a, T.lang) : '';
  if (d && !d.includes('–')) return T('card.cited.when.decade', { decade: d });
  return year ? T('card.cited.when.year', { y: span(a, z) }) : span(a, z);
}
// A phrase's leading preposition ("in", "på", "under", "around", "about"; '' before a year), and the phrase without
// it: two phrases in a row share it, "in 1785 or 1798", "på 1630-talet eller 1640-talet".
const lead = s => { const w = s.split(' ')[0]; return /\d/.test(w) ? '' : w; };
const bare = s => (lead(s) ? s.slice(lead(s).length + 1) : s);
// A template's {a} and {b} (or {list}) filled with parts: [{text, href?, title?}], the rest as plain text.
const MARK = { a: '\u0001', b: '\u0002', list: '\u0003' };
function parts(template, fills) {
  return template.split(/([\u0001-\u0003])/).flatMap(p => fills[p] || (p ? [{ text: p }] : []));
}
// A reading linked to its record, the source's name as its title; `prep`, its phrase's preposition, outside the link
// ("in [1785]", "in [the 1630s] or [the 1640s]").
const linked = (o, text, T, prep = '') => [...(prep ? [{ text: `${prep} ` }] : []),
  { text: prep ? text.slice(prep.length + 1) : text, href: o.u, title: srcName(o.s, T) }];
// True where the card's dating line is a cited one: the year is a cited record's, or none ships and the card carries
// what the records give (a span no map period holds 3/4 of, `a`..`z`, or an either pair). Never a private house's.
export function citedShown(b, yc) {
  if (b.private) return false;
  if (b.ysrc === YSRC.CITED) return true;
  return b.yflag === YFLAG.UNKNOWN && b.ysrc === YSRC.NONE && !!(yc?.e?.length === 2 || (yc?.a && yc?.z));
}
// The dating line as parts, each a record's link where it has one.
export function citedParts(b, T, yc) {
  if (yc?.e?.length === 2) {
    const [p, q] = yc.e;
    let key, a, z, pa = '', pz = '';
    if (periodLike(p.a, p.z) && medieval(p.a, p.z)) {
      // "≈ medieval origin, or built 1650", "…, or built in the 1600s": the other reading keeps its verb
      key = 'card.cited.either.medieval';
      a = T('card.cited.either.origin');
      z = when(q.a, q.z, T, false, q.c);
      pz = lead(z);
    } else {
      key = periodLike(p.a, p.z) || periodLike(q.a, q.z) ? 'card.cited.either.period' : 'card.cited.either';
      a = when(p.a, p.z, T, true, p.c);
      z = when(q.a, q.z, T, true, q.c);
      [pa, pz] = [lead(a), lead(z)];
      if (pa && pa === pz) [z, pz] = [bare(z), ''];
    }
    return parts(T(key, { a: MARK.a, b: MARK.b }), { [MARK.a]: linked(p, a, T, pa), [MARK.b]: linked(q, z, T, pz) });
  }
  // a span no year ships: read as the period the record gives
  const r = yc?.a && yc?.z ? { ...b, yflag: YFLAG.PERIOD, yearFrom: yc.a, yearTo: yc.z } : b;
  const src = srcName(yc?.s, T);
  const text = r.yflag === YFLAG.PERIOD && medieval(r.yearFrom, r.yearTo) ? T('card.cited.medieval', { src })
    : T(`card.cited.${r.yflag === YFLAG.PERIOD ? 'period' : yc?.k === 'rebuilt' ? 'rebuilt' : 'built'}`,
      { when: when(r.yearFrom, r.yearTo, T, false, yc?.c && r.yflag !== YFLAG.PERIOD), src });
  return [yc?.u ? { text, href: yc.u } : { text }];
}
export const citedLine = (b, T, yc) => citedParts(b, T, yc).map(p => p.text).join('');
// The header's big line for a building no period colours that a cited record dates all the same (yearLine): the
// record's span in its own words without the preposition, "≈ early 1600s", "≈ 1580–1649" (English drops "the"), or,
// for two readings, that the sources differ.
export function citedHead(yc, T) {
  if (yc?.e?.length === 2) return T('card.cited.head.either');
  return `≈ ${bare(when(yc.a, yc.z, T)).replace(/^the /, '')}`;
}
// Readings ({a, z, s, u, c?}, earliest first) as one linked list under a template's {list}: "1780 and 1906", "in the
// 1910s and the 1940s", each linked to its record; [] without any.
function citedList(rs, key, T) {
  if (!rs.length) return [];
  const first = lead(when(rs[0].a, rs[0].z, T, false, rs[0].c));
  const list = rs.flatMap((o, i) => {
    const w = when(o.a, o.z, T, false, o.c), shared = i && first && lead(w) === first;
    const sep = !i ? [] : [{ text: i === rs.length - 1 ? ` ${T('card.cited.and')} ` : ', ' }];
    return [...sep, ...linked(o, shared ? bare(w) : w, T, shared ? '' : lead(w))];
  });
  return parts(T(key, { list: MARK.list }), { [MARK.list]: list });
}
// The rebuilds, extensions and raised storeys the records name (`yc.r`): "Rebuilt or extended 1780 and 1906",
// "Rebuilt or extended in the 1900s and the 1940s", each year linked to its record; [] without any. They never set the
// year or the colour.
export const citedRebuilds = (yc, T) => citedList(Array.isArray(yc?.r) ? yc.r : [], 'card.cited.rebuilds', T);
// The other houses the footprint holds, which their records date on their own (`yc.o`): "Also part of this building: a
// house built 1804" ("…: houses built 1700 and 1785" for two); [] without any. Never the year or the colour.
export function citedAlso(yc, T) {
  const os = Array.isArray(yc?.o) ? yc.o : [];
  return citedList(os, os.length > 1 ? 'card.cited.also.more' : 'card.cited.also', T);
}
// The pinned card's second line: the rebuilds, then the other houses, " · " between.
export function citedMore(yc, T) {
  const r = citedRebuilds(yc, T), o = citedAlso(yc, T);
  return r.length && o.length ? [...r, { text: ' · ' }, ...o] : [...r, ...o];
}

// Where the building is: its first address, how many more it has, and its stadsdel, "Hornsgatan 30 (and 2
// more) · Södermalm"; '' when the card has neither. Addresses come from OpenStreetMap (s02_addresses), so a building
// without one shows only its stadsdel.
export function placeLine(card, T) {
  const addr = card?.addr ? (card.addrn > 1 ? T('card.address.more', { address: card.addr, n: card.addrn - 1 }) : card.addr) : '';
  return [addr, card?.dist || ''].filter(Boolean).join(' · ');
}

// A curated card's second line (§14 of the Gamla stan research): "Rebuilt 1757 · raised 1857", never with
// "≈"; '' without rebuilds. A rebuild never sets the year or the colour. A kind the strings do not hold is left out.
const REBUILD_KINDS = ['rebuilt', 'raised', 'extended'];
export function rebuildLine(card, T) {
  const parts = (card?.rebuilt || []).filter(([, kind]) => REBUILD_KINDS.includes(kind))
    .map(([year, kind]) => T(`card.rebuild.${kind}`, { year }));
  const line = parts.join(' · ');
  return line && line[0].toUpperCase() + line.slice(1);
}

export const heightLine = (b, T) => T('card.height.value', { m: T.num(b.height, 1) });
// A tower or spire measured in Lantmäteriet's laser scan (s02_towers): its top, whole metres; '' without one.
export const towerLine = (more, T) => (more && more.tower ? T('card.tower.value', { m: T.num(more.tower, 0) }) : '');

// "6 (OpenStreetMap)" or "≈ 6 (from its height)"; '' when the card leaves the row out (a church or a water tower whose
// floors come only from the height: s02_attributes' nofloors).
export function floorsLine(b, T, card = {}) {
  if (card.nofloors) return '';
  return T(b.fsrc === FSRC.HEIGHT ? 'card.floors.height' : 'card.floors.osm', { n: b.floors });
}

// The City Museum's class in words; '' for a building it has not rated (absence says nothing).
export const ratingLine = (rating, T) => (rating >= 1 && rating <= 3 ? T(`card.rating.${rating}`) : '');

// "State-listed building (statligt byggnadsminne) since 1935"; '' without legal protection.
export function protLine(card, T) {
  const p = card?.prot;
  if (![PROT.STATE, PROT.LISTED, PROT.CHURCH].includes(p)) return '';
  const what = T(`card.prot.${p}`);
  return card.since && p !== PROT.CHURCH ? T('card.prot.since', { what, year: card.since }) : what;
}

// A URL from one of stockholm.json's link templates (city.LINKS), every value encoded.
export const fillUrl = (tpl, vars) => String(tpl).replace(/\{(\w+)\}/g, (m, k) => encodeURIComponent(vars[k] ?? ''));

// The photo's credit as parts the card links: who took it, the work's title where the licence asks for
// it (CC 2.0–3.0), the licence (linked to its text) and Wikimedia Commons (linked to the file's page).
export function photoCredit(photo, T) {
  // a reader's photo (pipeline/contributions.py): the credit its sender gave, under the CC BY 4.0 they granted
  if (photo.rd) return [{ text: T('card.photo.reader', { by: photo.by }) }];
  const by = photo.by && photo.by !== 'unknown' ? photo.by : T('card.photo.unknown');
  const lic = { 'Public domain': T('card.photo.pd'), 'Public domain (Sweden)': T('card.photo.pd.se') }[photo.lic] || photo.lic;
  return [
    { text: `${T('card.photo')}: ${by}` },
    ...(photo.title ? [{ text: `“${photo.title}”` }] : []),
    { text: lic, href: photo.lu || '' },
    { text: 'Wikimedia Commons', href: photo.page },
  ];
}

// The excerpt in the page's language, or null: the card never shows a paragraph in the other language (it links
// that article instead).
export function extractFor(wiki, lang) {
  const e = wiki?.[lang];
  return e && e.t ? { lang, text: e.t, rev: e.r } : null;
}

// The "Read more" links: the RAÄ record (never for a private house; s03_tiles already leaves `raa` out), the
// Wikipedia article in the page's language, else in the other one, saying so, and the Wikidata item.
export function cardLinks(card, b, T, links) {
  const out = [];
  if (card.raa && !b.private) out.push({ text: T('card.link.raa'), href: fillUrl(links.raa, { id: card.raa }) });
  const wp = card.wp || [];
  const lang = wp.includes(T.lang) ? T.lang : wp[0];
  if (card.qid && lang) {
    out.push({ text: T(lang === T.lang ? 'card.link.wikipedia' : 'card.link.wikipedia.other'),
      href: fillUrl(links.wikipedia, { lang, qid: card.qid }) });
  }
  if (card.qid) out.push({ text: T('card.link.wikidata'), href: fillUrl(links.wikidata, { qid: card.qid }) });
  return out;
}

// Where About explains this card's year: a private house's decade rule (#about/privacy), or why no open
// record dates it (#about/years); null for every other card.
export function whyAnchor(b) {
  if (b.private) return 'privacy';
  return b.yflag === YFLAG.UNKNOWN ? 'years' : null;
}
