// The report form ("Something wrong?" on a card, "Suggest something" in About): what it shows and what it sends to
// POST /api/report (src/worker.js). Pure, tested by node --test (web/test/report.test.mjs); report-form.js runs it.

export const API = '/api/report';
export const MAX_PX = 2048;               // the longest side of a photo after the page re-encodes it
export const MAX_BYTES = 10 * 1024 * 1024;
export const TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// The kinds a form offers: a card's three (no photo on a private house's card), or About's suggestion.
export function kindsFor(ref) {
  if (!ref) return ['general'];
  return ref.private ? ['year_or_detail', 'other'] : ['year_or_detail', 'photo', 'other'];
}

// The building as its card shows it: the name, the address unless the card hides it, the district, the year and
// the source line, the data version (gids change between versions) and the map link.
export function buildingRef({ gid, b, card = {}, district = '', version = '', year = '', source = '', link = '', hideAddress = false }) {
  return { gid, name: card?.name || '', address: hideAddress ? '' : card?.addr || '', district, year, source, version,
    private: !!b?.private, link };
}

// The read-only lines the form shows for its building.
export function refRows(ref, T) {
  if (!ref) return [];
  return [['name', ref.name], ['address', ref.address], ['district', ref.district], ['year', ref.year], ['source', ref.source],
    ['id', T('report.ref.id.value', { gid: ref.gid, version: ref.version })]]
    .filter(([, v]) => v).map(([k, v]) => [T(`report.ref.${k}`), v]);
}

export function formHtml(ref, T) {
  const kinds = kindsFor(ref);
  const rows = refRows(ref, T);
  const kindInputs = kinds.map((k, i) => `<label class="report-kind"><input type="radio" name="kind" value="${k}"${i ? '' : ' checked'}>
    ${esc(T(`report.kind.${k}`))}</label>`).join('');
  const photo = kinds.includes('photo') ? `
    <fieldset class="report-photo" hidden>
      <legend>${esc(T('report.photo.title'))}</legend>
      <label for="report-file">${esc(T('report.photo'))}</label>
      <input id="report-file" name="photo" type="file" accept="${TYPES.join(',')}" aria-describedby="report-file-note">
      <p id="report-file-note" class="report-note">${esc(T('report.photo.note'))}</p>
      <label for="report-credit">${esc(T('report.credit'))}</label>
      <input id="report-credit" name="photo_credit" type="text" maxlength="100" autocomplete="name">
      <label class="report-check"><input type="checkbox" name="consent_own"> ${esc(T('report.consent.own'))}</label>
      <label class="report-check"><input type="checkbox" name="consent_licence">
        ${T('report.consent.licence', { name: '<span class="report-credit-name"></span>' })}</label>
    </fieldset>` : '';
  return `
    <button type="button" class="about-close report-close" aria-label="${esc(T('report.close'))}">×</button>
    <form class="report-form" novalidate>
      <h2 id="report-title">${esc(T(ref ? 'report.title.card' : 'report.title.general'))}</h2>
      ${rows.length ? `<section class="report-ref" aria-labelledby="report-ref-title"><h3 id="report-ref-title">${esc(T('report.building'))}</h3>
        <dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl></section>` : ''}
      ${kinds.length > 1 ? `<fieldset class="report-kinds"><legend>${esc(T('report.kind'))}</legend>${kindInputs}</fieldset>`
        : `<input type="hidden" name="kind" value="${kinds[0]}">`}
      ${photo}
      <label for="report-message">${esc(T('report.message'))}</label>
      <textarea id="report-message" name="message" rows="5" required minlength="10" maxlength="2000"
        aria-describedby="report-message-note"></textarea>
      <p id="report-message-note" class="report-note">${esc(T('report.message.note'))}</p>
      <label for="report-email">${esc(T('report.email'))}</label>
      <input id="report-email" name="email" type="email" required maxlength="254" autocomplete="email" aria-describedby="report-email-note">
      <p id="report-email-note" class="report-note">${esc(T('report.email.note'))}</p>
      <div class="report-hp" aria-hidden="true"><label>${esc(T('report.hp'))}<input name="website" type="text" tabindex="-1" autocomplete="off"></label></div>
      <p class="report-status" role="status" aria-live="polite"></p>
      <p class="report-actions"><button type="submit" class="report-send">${esc(T('report.send'))}</button>
        <button type="button" class="report-cancel">${esc(T('report.cancel'))}</button></p>
    </form>`;
}

// What the form sends: its fields, the building reference and how long the form was open (bots fill it at once).
export function payload(fields, ref, lang, elapsed) {
  const kind = fields.kind;
  const photo = kind === 'photo';
  return { kind, building: ref || null, message: String(fields.message || '').trim(), email: String(fields.email || '').trim(),
    lang, website: fields.website || '', elapsed: Math.round(elapsed),
    ...(photo ? { photo_credit: String(fields.photo_credit || '').trim(), consent_own: !!fields.consent_own,
      consent_licence: !!fields.consent_licence } : {}) };
}

// A photo's size after re-encoding: the longest side at most `max`.
export function fitSize(w, h, max = MAX_PX) {
  const s = Math.min(1, max / Math.max(w, h));
  return [Math.max(1, Math.round(w * s)), Math.max(1, Math.round(h * s))];
}

// The sentence for the Worker's answer (or a failure to reach it).
export function errorText(T, status, fields = []) {
  if (status === 429) return T('report.error.rate');
  if (fields.includes('exif') || fields.includes('photo_type')) return T('report.error.photo');
  if (fields.includes('consent') || fields.includes('photo_credit')) return T('report.error.consent');
  if (status === 400) return T('report.error.invalid');
  return T('report.error.network');
}
