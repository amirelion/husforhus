// Search: what a query finds in search/index.json and the address shards
// (pipeline/s14_search.py), ranked, and the words each row and state shows. Pure, so node --test checks
// it (web/test/search.test.mjs); app.js draws the list and flies to a pick.
import { fold } from './fold.js';

const KIND_ORDER = { district: 0, building: 1, occupant: 1.5, street: 2 };

// The index with every name folded once (fold.js: the same rules as the pipeline's), ready for searching.
export function prepare(index) {
  return {
    settings: index.settings, examples: index.examples || [], addressed: index.addressed || 0,
    districts: index.districts.map(([name, n, box], i) => ({ kind: 'district', name, n, box, i, f: fold(name) })),
    aliases: index.aliases.map(([name, ds]) => ({ name, ds, f: fold(name) })),
    outside: index.outside.map(name => ({ name, f: fold(name) })),
    streets: index.streets.map(([name, n, ds, shard], i) => ({ kind: 'street', name, n, ds, shard, i, f: fold(name) })),
    buildings: index.buildings.map(([name, gid, d, en]) => ({ kind: 'building', name, gid, d, en, f: fold(name),
      fe: en ? fold(en) : '' })),
    // the names people use for the best-known buildings ("Slottet", "Royal Palace"), each pointing at a card's name
    baliases: (index.baliases || []).map(([name, gid]) => ({ name, gid, f: fold(name) })),
    // what is inside a building ("Nobelprismuseet" in Börshuset, "Historiska museet" on a footprint with no named
    // card): Swedish, English and other names, and the stadsdel for a footprint search has no building row for
    occupants: (index.occupants || []).map(([sv, en, gid, alt = [], d = -1]) => ({ sv, en, gid, d, f: fold(sv),
      fe: fold(en), fa: alt.map(fold) })),
  };
}

// What the query asks: too short, a year alone (or a decade, "1930s", "1930-talet"), a number alone, a street and a
// number (an optional letter; the first of two numbers, "12-14", without the second's letter; "nr" before it and a
// floor after it, "3 tr", read past), or text.
export function parse(q, min = 2) {
  const f = fold(q);
  if (f.replace(/ /g, '').length < min) return { kind: 'short', f };
  const y = f.match(/^(\d{4})(?: ?(?:s|tal|talet))?$/);
  if (y && +y[1] >= 1000 && +y[1] <= 2100) return { kind: 'year', f, year: +y[1] };
  if (/^\d{1,4}(?: \d{1,4})?( ?[a-z])?$/.test(f)) return { kind: 'number', f };
  const m = f.match(/^(.*\D) (\d{1,4})(?: \d{1,4}(?: ?[a-z])?| ?([a-z]))?(?: \d{1,2} ?(?:tr|trappa|trappor))?$/);
  if (m) {
    return { kind: 'address', f, street: m[1].trim().replace(/ (?:nr|no)$/, ''), number: String(+m[2]),
      letter: (m[3] || '').toUpperCase() };
  }
  return { kind: 'text', f };
}

// How well a folded name matches a folded query: 0 exact, 1 prefix, 2 the start of a word inside, 3 anywhere; -1 none.
export function score(name, q) {
  if (!q) return -1;
  if (name === q) return 0;
  if (name.startsWith(q)) return 1;
  if (name.includes(' ' + q)) return 2;
  return name.includes(q) ? 3 : -1;
}

// An exact start with the right accents ranks first, so "Hammarby sjö" lands on the right name.
const accented = (name, raw) => raw && name.toLowerCase().startsWith(raw.trim().toLowerCase());

function rank(rows) {
  return rows.sort((a, b) => a.s - b.s || KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || (b.n || 1) - (a.n || 1)
    || a.label.localeCompare(b.label, 'sv'));
}

function cap(rows, { max_rows: maxRows = 8, max_per_kind: perKind = 4 } = {}) {
  const per = {}, out = [];
  for (const r of rows) {
    per[r.kind] = (per[r.kind] || 0) + 1;
    if (per[r.kind] <= perKind && out.length < maxRows) out.push(r);
  }
  return out;
}

// Text: stadsdelar (by their own name or an everyday one), named buildings (by their Swedish name, English label or
// another name people use), streets. Ranked by match, then district before building before street, then size, then
// alphabetically. A match on the English label alone ranks a little after the same match on a Swedish name, and
// buildings that share a name and a stadsdel (a school's wings) are one row.
export function textRows(P, q, raw = '') {
  const rows = [];
  const add = (row, s, name) => { if (s >= 0) rows.push({ ...row, s: s - (accented(name, raw) ? 0.5 : 0) }); };
  for (const d of P.districts) add({ kind: 'district', label: d.name, n: d.n, box: d.box, d: d.i }, score(d.f, q), d.name);
  const seen = new Set();
  for (const a of P.aliases) {
    const s = score(a.f, q);
    if (s < 0) continue;
    for (const i of a.ds) {
      const d = P.districts[i];
      if (!seen.has(i)) add({ kind: 'district', label: d.name, n: d.n, box: d.box, d: i, via: a.name }, s, a.name);
      seen.add(i);
    }
  }
  for (const b of P.buildings) {
    const s = score(b.f, q), se = b.fe ? score(b.fe, q) : -1;
    const best = s >= 0 && (se < 0 || s <= se) ? s : se;
    const byEn = best === se && best !== s;
    if (best >= 0) add({ kind: 'building', label: b.name, gid: b.gid, d: b.d, en: b.en, byEn }, best + (byEn ? 0.25 : 0), byEn ? b.en : b.name);
  }
  const byGid = new Map(P.buildings.map(b => [b.gid, b]));
  for (const a of P.baliases) {
    const b = byGid.get(a.gid), s = score(a.f, q);
    if (b && s >= 0) add({ kind: 'building', label: b.name, gid: b.gid, d: b.d, en: b.en, via: a.name }, s, a.name);
  }
  // an institution inside a building: found by any of its names, picked as the building, after an exact building
  // name; on a footprint whose card has no name it stands alone ("Historiska museet", no "in ...")
  for (const o of P.occupants || []) {
    const b = byGid.get(o.gid);
    const s = score(o.f, q), se = score(o.fe, q), sa = o.fa.map(f => score(f, q)).filter(x => x >= 0);
    const all = [s, se, ...sa].filter(x => x >= 0);
    if (!all.length) continue;
    const best = Math.min(...all);
    add({ kind: 'occupant', label: o.sv, sv: o.sv, en: o.en, building: b ? b.name : '', gid: o.gid, d: b ? b.d : o.d },
      best, best === s ? o.sv : best === se ? o.en : '');
  }
  for (const st of P.streets) add({ kind: 'street', label: st.name, n: st.n, ds: st.ds, shard: st.shard, street: st.name }, score(st.f, q), st.name);
  // a stadsdel found by its everyday name and by its own, or buildings of one name in one stadsdel: once, the better match
  const best = new Map();
  for (const r of rows) {
    const key = r.kind === 'occupant' ? `o${r.gid}\u0000${r.label}` : r.kind === 'building' ? `b${r.label}\u0000${r.d}` : r.kind === 'district' ? `d${r.d}` : `s${r.label}`;
    if (!best.has(key) || r.s < best.get(key).s) best.set(key, r);
  }
  return cap(rank([...best.values()]), P.settings);
}

// Up to four streets for the street part of an address: exact, then prefix, then the start of a word inside.
export function streetsFor(P, q, n = 4) {
  return P.streets.map(st => ({ st, s: score(st.f, q) })).filter(x => x.s >= 0 && x.s <= 2)
    .sort((a, b) => a.s - b.s || b.st.n - a.st.n || a.st.name.localeCompare(b.st.name, 'sv')).slice(0, n).map(x => x.st);
}

const num = s => { const m = String(s).match(/^(\d+)([A-Z]?)$/); return m ? [+m[1], m[2]] : [0, '']; };

// On one street's numbers ([[number, gid, stadsdel], ...]): the number with its letter, else the bare number (or any
// letter of it), else the nearest on the same side (same parity), else the nearest at all. `near` says the asked
// number (with its letter) is not in the list: "no. 5B isn't in our list" when only 5 is.
export function findNumber(pairs, number, letter = '') {
  if (!pairs?.length) return null;
  const want = +number;
  const own = pairs.find(p => p[0] === number + letter);
  if (own) return { pair: own, near: null };
  const exact = pairs.find(p => p[0] === number) || pairs.find(p => num(p[0])[0] === want);
  if (exact) return { pair: exact, near: letter ? number + letter : null };
  const dist = p => Math.abs(num(p[0])[0] - want);
  const by = list => list.slice().sort((a, b) => dist(a) - dist(b) || num(a[0])[0] - num(b[0])[0])[0];
  const same = pairs.filter(p => num(p[0])[0] % 2 === want % 2);
  return { pair: by(same.length ? same : pairs), near: String(want), side: same.length > 0 };
}

// Address mode: one row per street that has the number (or a near one), at most four.
export async function addressRows(P, parsed, loadShard) {
  const rows = [];
  for (const st of streetsFor(P, parsed.street)) {
    const shard = await loadShard(st.shard);
    const hit = findNumber(shard?.[st.name], parsed.number, parsed.letter);
    if (!hit) continue;
    const [n, gid, d] = hit.pair;
    rows.push({ kind: 'address', label: `${st.name} ${n}`, gid, d, street: st.name, near: hit.near, side: hit.side });
  }
  return rows.slice(0, 4);
}

// Levenshtein distance, giving up past `max`.
export function edits(a, b, max = 2) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let low = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      low = Math.min(low, cur[j]);
    }
    if (low > max) return max + 1;
    prev = cur;
  }
  return prev[b.length];
}

// A near miss: the one street, stadsdel, building name, other name or English label within max_edits of the query,
// the closest (then the biggest street); null if none. A building near by its English label is offered by its own
// name, so the Swedish page never shows the label. `street` says whether it is a street's name.
export function didYouMean(P, q) {
  return nearest(P, q)?.name ?? null;
}

function nearest(P, q) {
  const max = P.settings?.max_edits ?? 2;
  let best = null;
  const consider = (name, f, n, street = false) => {
    const e = edits(f, q, max);
    if (e <= max && (!best || e < best.e || (e === best.e && n > best.n))) best = { name, e, n, street };
  };
  for (const st of P.streets) consider(st.name, st.f, st.n, true);
  for (const d of P.districts) consider(d.name, d.f, d.n);
  for (const b of P.buildings) consider(b.name, b.f, 1);
  for (const a of P.baliases) consider(a.name, a.f, 1);
  for (const b of P.buildings) if (b.fe) consider(b.name, b.fe, 1);    // offered by its card's name, in either language
  return best;
}

// Swedish writes "the" as an ending: "slottet", "stadshuset", "kyrkan". A text query that finds nothing tries once
// more without it ("slott", "stadshus", "kyrka"), before saying what to try instead.
export function bare(f) {
  return ['et', 'en', 'n', 't'].filter(end => f.endsWith(end) && f.length - end.length >= 3).map(end => f.slice(0, -end.length));
}

// The whole search: { rows, message } where message is { id, vars } for web/i18n (or null).
export async function search(P, raw, loadShard) {
  const parsed = parse(raw, P.settings?.min_chars ?? 2);
  if (parsed.kind === 'short') return { rows: [], message: null };
  if (parsed.kind === 'year') return { rows: [], message: { id: 'search.year', vars: { year: parsed.year } } };
  if (parsed.kind === 'number') return { rows: [], message: { id: 'search.number' } };
  // a neighbouring municipality: the map stops at its border, but the city's streets named after it still show
  const out = P.outside.find(o => o.f === parsed.f);
  if (out) return { rows: textRows(P, parsed.f, raw), message: { id: 'search.outside', vars: { place: out.name } } };
  let rows = [];
  if (parsed.kind === 'address') rows = await addressRows(P, parsed, loadShard);
  if (!rows.length) rows = textRows(P, parsed.f, raw);
  for (const f of parsed.kind === 'text' && !rows.length ? bare(parsed.f) : []) {
    rows = textRows(P, f, '');
    if (rows.length) break;
  }
  if (rows.length) return { rows, message: null };
  // a street's near miss keeps the asked number, so taking the suggestion searches the address
  const near = nearest(P, parsed.kind === 'address' ? parsed.street : parsed.f);
  const guess = near && (parsed.kind === 'address' && near.street
    ? `${near.name} ${parsed.number}${parsed.letter}` : near.name);
  return { rows: [], message: guess ? { id: 'search.didyoumean', vars: { name: guess }, suggest: guess }
    : { id: 'search.none', vars: { q: raw.trim() } } };
}

const count = (n, T) => (n === 1 ? T('search.buildings.one') : T('search.buildings', { n: T.num(n) }));

// The row's two lines: the name and a muted line with its kind, where it is and its size.
export function rowText(row, P, T) {
  const dist = i => P.districts[i]?.name;
  const parts = [T(`search.kind.${row.kind}`)];
  if (row.kind === 'district') {
    if (row.via) parts.push(T('search.via', { name: row.via }));
    parts.push(count(row.n, T));
  } else if (row.kind === 'street') {
    const ds = row.ds.map(dist).filter(Boolean);
    if (ds.length) parts.push(ds.slice(0, 2).join(', ') + (ds.length > 2 ? ` +${ds.length - 2}` : ''));
    parts.push(count(row.n, T));
  } else {
    if (row.kind === 'building' && row.via) parts.push(`“${row.via}”`);           // found by another name
    else if (row.kind === 'building' && row.en && T.lang === 'en' && row.byEn) parts.push(`“${row.en}”`);
    if (dist(row.d)) parts.push(dist(row.d));
    if (row.near) parts.push(T(row.side ? 'search.near.side' : 'search.near', { n: row.near }));
  }
  const own = row.kind === 'occupant' && (T.lang === 'en' ? row.en || row.sv : row.sv);
  const main = !own ? row.label : row.building ? T('search.in', { name: own, building: row.building }) : own;
  return { main, sub: parts.join(' · ') };
}
