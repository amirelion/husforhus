// The City Museum's building-archaeology register (s02_stadsmuseet's card `br`): the pinned card's "Building
// archaeology" section. Pure functions, tested by node --test. The facts are ours, built from the register's fields
// and categories (pipeline/stadsmuseet.py facts): never the museum's descriptions. The register dates parts and
// investigations, never the house, so nothing here touches the building's year, period or colour.
export const BR_REGISTER = 'https://stadsarkeologisktregister.stockholm.se/';
const REPORT = /^https:\/\/digitalastadsmuseet\.stockholm\.se\//;

// One investigation's years: "1988", or "2012–2013".
const span = e => (e.from === e.to ? String(e.from) : `${e.from}–${e.to}`);

// The card's section, or '' when the building has none (or is a private house: s03 leaves `br` off it already).
export function archaeologySection(br, T, esc, isPrivate = false) {
  if (!br?.inv?.length || isPrivate) return '';
  const years = [...new Set(br.inv.filter(e => e.from).map(span))];
  const facts = [
    br.medieval && T('card.br.medieval'),
    br.felled?.length && T('card.br.felled', { years: br.felled.join(', ') }),
    years.length && T('card.br.inv', { years: years.join(', ') }),
  ].filter(Boolean);
  // a "Report" link per record whose report is in Digitala Stadsmuseet; with more than one, each names its years
  const reports = br.inv.filter(e => typeof e.report === 'string' && REPORT.test(e.report));
  const label = e => (reports.length > 1 && e.from ? `${T('card.br.report')} ${span(e)}` : T('card.br.report'));
  return `
    <section class="archaeology"><h4>${esc(T('card.br'))}</h4>
      ${facts.length ? `<ul>${facts.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}
      ${reports.length ? `<p class="reports">${reports.map(e =>
        `<a href="${esc(e.report)}" target="_blank" rel="noopener">${esc(label(e))}</a>`).join(' · ')}</p>` : ''}
      <p class="credit"><a href="${BR_REGISTER}" target="_blank" rel="noopener">${esc(br.credit || 'Stadsmuseet i Stockholm')}</a></p></section>`;
}
