// "Accept" on a report (web/admin/admin.js): the small form that turns it into data for the next release. Pure but for
// addressesFor's fetch, tested by node --test (web/test/admin-accept.test.mjs). The Worker checks the same
// (src/validate.js validateContribution) and pipeline/contributions.py checks it against the building.
export const CHANGES = ['year', 'main_address', 'name', 'photo', 'none'];
const LABEL = { year: 'Year', main_address: 'Main address', name: 'Name', photo: 'Photo', none: 'No change to the data' };
const YEAR = /^(\d{4})(?:-(\d{4}))?$/;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// The changes this report can make: a photo only with its photo and both consents, a name or a photo never on a
// private house, nothing but "none" without a building.
export function changesFor(r) {
  if (!r.building) return ['none'];
  return CHANGES.filter(c => !(r.building.private && (c === 'name' || c === 'photo'))
    && !(c === 'photo' && !(r.photo_key && r.consent_own && r.consent_licence)));
}

// The form; `addresses` the building's addresses in its report's version (addressesFor), [] when none were found.
export function acceptFormHtml(r, addresses = []) {
  const changes = changesFor(r);
  return `<form id="accept" class="accept">
    <h3>Accept ${esc(r.reference)}</h3>
    <label>Change <select name="kind">${changes.map(c => `<option value="${c}">${LABEL[c]}</option>`).join('')}</select></label>
    <p data-for="year"><label>Year <input name="year" inputmode="numeric" pattern="\\d{4}(-\\d{4})?" placeholder="1938 or 1938-1939"></label>
      <label><input type="checkbox" name="replaces_register"> replaces a register year</label></p>
    <p data-for="main_address"><label>Main address <select name="main_address">${addresses.length
      ? addresses.map(a => `<option>${esc(a)}</option>`).join('') : '<option value="">(no addresses found in the map data)</option>'}</select></label></p>
    <p data-for="name"><label>Name <input name="name" maxlength="120"></label></p>
    <p data-for="photo">The photo, credited “${esc(r.photo_credit)}, CC BY 4.0, a reader's photo”.</p>
    <p><label>Public note (one line, shown on the card)<br><input name="public_note" maxlength="200" required></label></p>
    <div class="actions"><button type="submit">Accept</button><button type="button" id="accept-cancel">Cancel</button></div>
  </form>`;
}

// Show only the fields of the chosen change.
export function showFields(form) {
  const kind = form.querySelector('[name=kind]').value;
  for (const p of form.querySelectorAll('[data-for]')) p.hidden = p.dataset.for !== kind;
}

// { errors, body } from the form's fields ({kind, year, main_address, name, public_note, replaces_register}).
export function readAccept(f) {
  const kind = CHANGES.includes(f.kind) ? f.kind : null, errors = [];
  if (!kind) errors.push('kind');
  const note = String(f.public_note ?? '').trim();
  if (!note || note.length > 200 || /[\r\n]/.test(note)) errors.push('public_note');
  let value = '';
  if (kind === 'year') {
    value = String(f.year ?? '').trim();
    const m = value.match(YEAR);
    if (!m || (m[2] && +m[2] < +m[1])) errors.push('value');
  } else if (kind === 'main_address' || kind === 'name') {
    value = String(f[kind] ?? '').trim();
    if (!value || (kind === 'name' && value.length > 120)) errors.push('value');
  }
  return { errors, body: { kind, value, public_note: note, replaces_register: kind === 'year' && !!f.replaces_register } };
}

// The building's addresses ("Street 12") from the map's own search files for the report's version:
// /data/<version>/search/index.json names each street's shard, search/addr/<k>.json lists [number, gid, stadsdel].
export async function addressesFor(gid, version, fetchJson = u => fetch(u).then(r => (r.ok ? r.json() : null))) {
  if (!/^v\d{8}(-[a-z0-9]+)?$/.test(version || '')) return [];
  const base = `/data/${version}/search`;
  const index = await fetchJson(`${base}/index.json`).catch(() => null);
  const keys = [...new Set((index?.streets || []).map(s => s[3]))];
  const out = [];
  for (const shard of await Promise.all(keys.map(k => fetchJson(`${base}/addr/${k}.json`).catch(() => null)))) {
    for (const [street, rows] of Object.entries(shard || {})) {
      for (const [number, g] of rows) if (g === gid) out.push(`${street} ${number}`);
    }
  }
  return out;
}
