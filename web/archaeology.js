// The City Museum's building-archaeology register (s02_stadsmuseet's card `br`): the pinned card's "Building
// archaeology" section. Pure functions, tested by node --test. The facts are ours, built from the register's fields
// and categories (pipeline/stadsmuseet.py facts): never the museum's descriptions. The register dates parts and
// investigations, never the house, so nothing here touches the building's year, period or colour.
export const BR_REGISTER = 'https://stadsarkeologisktregister.stockholm.se/';
const REPORT = /^https:\/\/digitalastadsmuseet\.stockholm\.se\/fotoweb\/archives\/5004-[^\s"'<>?#]+\.info$/;

// The card's section, or '' when the building has none (or is a private house: s03 leaves `br` off it already).
// Short on purpose (owner, 2026-10-20): the facts, the investigations in one line, and one link, to the latest report.
export function archaeologySection(br, T, esc, isPrivate = false) {
  if (!br?.inv?.length || isPrivate) return '';
  const dated = br.inv.filter(e => e.from);
  const first = Math.min(...dated.map(e => e.from)), last = Math.max(...dated.map(e => e.to || e.from));
  const inv = !dated.length ? ''
    : dated.length === 1 ? T('card.br.inv', { years: first === last ? String(first) : `${first}–${last}` })
    : T('card.br.invMany', { n: br.inv.length, from: first, to: last });
  const facts = [
    br.medieval && T('card.br.medieval'),
    br.felled?.length && T('card.br.felled', { years: br.felled.join(', ') }),
    inv,
  ].filter(Boolean);
  // the latest record that has a report page; undated ones count as oldest
  const latest = br.inv.filter(e => typeof e.report === 'string' && REPORT.test(e.report))
    .sort((a, b) => (b.to || b.from || 0) - (a.to || a.from || 0))[0];
  const year = latest && (latest.to || latest.from);
  return `
    <section class="archaeology"><h4>${esc(T('card.br'))}</h4>
      ${facts.length ? `<ul>${facts.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}
      ${latest ? `<p class="reports"><a href="${esc(latest.report)}" target="_blank" rel="noopener">${
        esc(year ? T('card.br.latest', { year }) : T('card.br.report'))}</a></p>` : ''}
      <p class="credit"><a href="${BR_REGISTER}" target="_blank" rel="noopener">${esc(br.credit || 'Stadsmuseet i Stockholm')}</a></p></section>`;
}
