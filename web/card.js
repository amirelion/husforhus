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
const SRC = { [YSRC.RAA]: 'raa', [YSRC.RAA_OLD]: 'raa_old', [YSRC.WIKIDATA]: 'wikidata', [YSRC.OSM]: 'osm' };
const EST_FLAGS = [YFLAG.AREA, YFLAG.ESTIMATE, YFLAG.PERIOD];
export const isEstimate = b => EST_FLAGS.includes(b.yflag);

// The big line in the card's header band.
export function yearLine(b, periodLabel, T) {
  if (b.yflag === YFLAG.UNKNOWN) return T('card.unknown');
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
  if (b.yflag === YFLAG.UNKNOWN) return T('card.src.unknown');
  if (b.yflag === YFLAG.PERIOD) return b.private ? T('card.private.period') : T('card.src.period');
  if (b.private) {
    const how = b.ysrc === YSRC.ESTIMATE ? 'estimate' : b.ysrc === YSRC.RAA_AREA ? 'area' : SRC[b.ysrc];
    return [how && T(`card.private.${how}`), T('card.private.rule')].filter(Boolean).join(' · ');
  }
  if (b.ysrc === YSRC.CURATED) {
    return T(card?.cellars ? 'card.src.curated.cellars' : 'card.src.curated', { span: span(b.yearFrom, b.yearTo) });
  }
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
