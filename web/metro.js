// Tunnelbanan (s16_metro's metro.json), behind config.features.metro and the legend's "Tunnelbanan" switch: what shows
// at the timeline's year, the switch's memory and URL, and the station card. Pure functions, tested by node --test
// (web/test/metro.test.mjs). Our own muted line colours, never SL's styling, logo or type; no station images at all
// (station art, HD 2016-04-04 Ö 849-15: docs/research/2026-10-16-tunnelbanan.md §8).

// Off by default, remembered per device (hfh-metro: 'on' | 'off') and kept in the URL while on (?metro=1), as the
// plaques switch is (web/panel.js).
export const METRO_PARAM = 'metro';
export const METRO_KEY = 'hfh-metro';
export const metroOnFrom = (search, stored) => new URLSearchParams(search).get(METRO_PARAM) === '1' || stored === 'on';
export function metroHref(href, on) {
  const u = new URL(href);
  if (on) u.searchParams.set(METRO_PARAM, '1'); else u.searchParams.delete(METRO_PARAM);
  return u.toString();
}

// A muted green, red and blue, mid-tone so each reads on the light looks' land and on Blå timmen's dark land
// (contrast checked against every look in web/test/metro.test.mjs).
export const LINE_COLOURS = { green: '#3f8f5e', red: '#c0503f', blue: '#3b78c2' };

const yearOf = d => (d ? +d.slice(0, 4) : Infinity);
// Shown at a timeline year: opened in that year or before, not closed by then. At Today (today: an ISO date),
// whatever is open on that day.
const shown = (item, year, today) => (today
  ? !!item.opened && item.opened <= today && !(item.closed && item.closed <= today)
  : yearOf(item.opened) <= year && !(item.closed && yearOf(item.closed) <= year));

// What the map draws at the timeline's year: { segments, stations, never }. `today` (an ISO date) when the timeline is
// at Today: then everything open shows, and Kymlinge (never opened) as a dashed ring, at Today only.
export function metroAt(metro, year, today = null) {
  const segments = (metro?.segments || []).filter(g => shown(g, year, today));
  const stations = (metro?.stations || []).filter(s => !s.never && shown(s, year, today));
  const never = today ? (metro?.stations || []).filter(s => s.never) : [];
  return { segments, stations, never };
}

const LINE_NAME = { en: { green: 'Green line', red: 'Red line', blue: 'Blue line' },
  sv: { green: 'Gröna linjen', red: 'Röda linjen', blue: 'Blå linjen' } };

// The station's small card: its name, lines, the date it opened, its earlier names, and its Wikidata item.
export function stationCard(s, T, esc) {
  const lang = T.lang === 'sv' ? 'sv' : 'en';
  const date = d => new Date(`${d}T12:00:00Z`).toLocaleDateString(lang === 'sv' ? 'sv-SE' : 'en-GB',
    { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  const lines = s.lines.map(l => `<span class="metro-line"><i style="background:${LINE_COLOURS[l]}"></i>${esc(LINE_NAME[lang][l])}</span>`).join('');
  const opened = s.never ? T('metro.never') : T('metro.opened', { date: date(s.opened) })
    + (s.closed ? ` · ${T('metro.closed', { date: date(s.closed) })}` : '');
  const names = (s.names || []).map(n => T('metro.formerly', { name: n.name, from: n.from.slice(0, 4), to: n.to.slice(0, 4) }));
  return `<button class="card-close" aria-label="${esc(T('card.close'))}">×</button>
    <h3 id="card-title">${esc(s.never ? T('metro.neverName', { name: s.name }) : s.name)}</h3>
    <p class="metro-lines">${lines}</p><p>${esc(opened)}</p>
    ${names.map(n => `<p class="metro-formerly">${esc(n)}</p>`).join('')}
    ${s.wikidata ? `<p class="credit"><a href="https://www.wikidata.org/wiki/${esc(s.wikidata)}" target="_blank" rel="noopener">${
      esc(T('metro.wikidata'))}</a></p>` : ''}`;
}
