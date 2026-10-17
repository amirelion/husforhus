// The corner credit (Plan 4b, Task 9; spec §4.5, §6.2): the sources' own words from sources.yml `corner` (through
// stockholm.json attribution), each once, then "Sources", which opens About at its full credits. A part with a url
// links there (© OpenStreetMap contributors to its copyright page, as the OSMF asks); the others open About too.
// Pure, tested by node --test (web/test/credits.test.mjs).

export function cornerParts(attribution, lang) {
  const seen = new Set(), out = [];
  for (const a of attribution || []) {
    const text = a.corner?.[lang] || a.corner?.en;
    if (!text || seen.has(text)) continue;
    seen.add(text);
    out.push({ text, href: a.corner.url || '#about/sources' });
  }
  return out;
}

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// The line's HTML: the parts, then the link to About's sources (T('credit.sources')).
export function cornerHtml(attribution, T) {
  const link = p => (p.href.startsWith('#')
    ? `<a href="${esc(p.href)}">${esc(p.text)}</a>`
    : `<a href="${esc(p.href)}" target="_blank" rel="noopener">${esc(p.text)}</a>`);
  return [...cornerParts(attribution, T.lang).map(link), `<a href="#about/sources">${esc(T('credit.sources'))}</a>`]
    .join(' · ');
}
