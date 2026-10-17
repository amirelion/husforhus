// Samfundet S:t Erik's blue plaques (s15_plaques' plaques.json), behind config.features.plaques and the legend's switch: the pinned card's
// plaque section and the markers' positions. Pure functions, tested by node --test. A plaque's text is Swedish
// (Stockholmskällan); its credit always reads "Samfundet S:t Erik, CC BY 4.0".
export const PLAQUE_LICENCE = 'https://creativecommons.org/licenses/by/4.0/';

// gid -> its plaques (a building may carry more than one).
export function plaquesByGid(list) {
  const by = new Map();
  for (const p of list || []) {
    if (!by.has(p.gid)) by.set(p.gid, []);
    by.get(p.gid).push(p);
  }
  return by;
}

// The card's section for a building's plaques, or '' when it has none.
export function plaqueSection(plaques, T, esc) {
  if (!plaques?.length) return '';
  // in English only: a note that the text below is Swedish
  const note = T.lang === 'en' ? `<p class="plaque-note" lang="en">${esc(T('card.plaque.note'))}</p>` : '';
  return plaques.map(p => `
    <section class="plaque" lang="sv"><h4>${esc(T('card.plaque'))}${p.year ? ` · ${esc(p.year)}` : ''}</h4>
      ${note}${p.name ? `<p class="plaque-name">${esc(p.name)}</p>` : ''}<p>${esc(p.text)}</p>
      <p class="credit"><a href="https://stockholmskallan.stockholm.se/post/${+p.id}" target="_blank" rel="noopener">${
        esc(T('card.plaque.source'))}</a> · <a href="${PLAQUE_LICENCE}" target="_blank" rel="noopener">${esc(p.credit)}</a></p></section>`).join('');
}
