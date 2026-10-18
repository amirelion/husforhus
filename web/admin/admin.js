// The owner's triage page (/admin): lists reports from /api/admin/reports, opens one, changes its status and note,
// replies from the owner's own mail client, publishes it as a GitHub issue (never with the email) and accepts it as
// data for the next release (accept.js). The API never returns the email: only the Reply link (`reply`) carries it.
import { acceptFormHtml, readAccept, showFields, addressesFor } from './accept.js';

const STATUSES = ['new', 'in-progress', 'accepted', 'fixed', 'wontfix', 'published'];
const KIND = { year_or_detail: 'Year or detail', photo: 'Photo', other: 'Something else', general: 'Suggestion' };
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const say = t => { $('#msg').textContent = t; };

async function api(path, body) {
  const r = await fetch(`/api/admin/${path}`, body ? { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body) } : {});
  if (!r.ok) throw new Error(r.status === 403 ? 'Not signed in through Cloudflare Access.' : `Error ${r.status}`);
  return r.json();
}
const what = r => (r.building ? r.building.name || r.building.address || `building ${r.building.gid}` : '—');

let current = null;
async function list() {
  const f = new FormData($('#filters'));
  const q = new URLSearchParams([...f].filter(([, v]) => v));
  try {
    const { reports } = await api(`reports?${q}`);
    $('#list tbody').innerHTML = reports.map(r => `<tr data-id="${r.id}" ${r.id === current ? 'aria-current="true"' : ''}>
      <td><button type="button">${esc(r.reference)}</button></td><td>${esc(r.created_at.slice(0, 10))}</td>
      <td>${esc(KIND[r.kind] || r.kind)}</td><td>${esc(what(r))}</td><td>${esc(r.status)}</td></tr>`).join('')
      || '<tr><td colspan="5">No reports.</td></tr>';
    say(`${reports.length} report${reports.length === 1 ? '' : 's'}`);
  } catch (e) { say(e.message); }
}

function detailHtml(r) {
  const b = r.building;
  const rows = b ? [['Name', b.name], ['Address', b.address], ['District', b.district], ['Year shown', b.year],
    ['Source shown', b.source], ['Building', `gid ${b.gid}, data ${b.version}`]].filter(([, v]) => v) : [];
  return `<h2>${esc(r.reference)} · ${esc(KIND[r.kind] || r.kind)}</h2>
    <dl><dt>Received</dt><dd>${esc(r.created_at)}</dd><dt>Email</dt><dd>${r.reply ? 'kept (use Reply)' : '<i>deleted</i>'}</dd>
      <dt>Language</dt><dd>${esc(r.lang)}</dd>
      ${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}
      ${b?.link ? `<dt>Map</dt><dd><a href="${esc(b.link)}" target="_blank" rel="noopener">Open on the map</a></dd>` : ''}
      ${r.issue_url ? `<dt>Issue</dt><dd><a href="${esc(r.issue_url)}" target="_blank" rel="noopener">${esc(r.issue_url)}</a></dd>` : ''}</dl>
    ${b?.private ? '<p class="warn">A private house: do not publish details that identify the home.</p>' : ''}
    <blockquote>${esc(r.message)}</blockquote>
    ${r.photo_key ? `<figure><img src="/api/admin/reports/${r.id}/photo" alt="Photo sent with ${esc(r.reference)}">
      <figcaption>${esc(r.photo_credit)} · own photo: ${r.consent_own ? 'yes' : 'no'} · CC BY 4.0: ${r.consent_licence ? 'yes' : 'no'}</figcaption></figure>` : ''}
    <form id="edit">
      <label>Status <select name="status">${STATUSES.map(s => `<option${s === r.status ? ' selected' : ''}>${s}</option>`).join('')}</select></label>
      <p><label>Note (private)<br><textarea name="note" rows="3">${esc(r.note)}</textarea></label></p>
      <div class="actions"><button type="submit">Save</button>
        ${r.reply ? `<a href="${esc(r.reply)}">Reply</a>` : ''}</div>
    </form>
    <div class="actions">
      <button type="button" id="publish">Publish as GitHub issue</button>
      ${r.status === 'accepted' || r.status === 'fixed' ? '' : '<button type="button" id="accept-open">Accept</button>'}
      ${r.photo_key && !b?.private ? '<label><input type="checkbox" id="with-photo"> include photo</label>' : ''}
    </div>
    <div id="accept-slot"></div>`;
}

async function openAccept(r, d) {
  const b = r.building;
  let addresses = b ? await addressesFor(b.gid, b.version).catch(() => []) : [];
  if (b?.address && addresses.includes(b.address)) addresses = [b.address, ...addresses.filter(a => a !== b.address)];
  const slot = d.querySelector('#accept-slot');
  slot.innerHTML = acceptFormHtml(r, addresses);
  const form = slot.querySelector('#accept');
  showFields(form);
  form.querySelector('[name=kind]').onchange = () => showFields(form);
  slot.querySelector('#accept-cancel').onclick = () => { slot.innerHTML = ''; };
  form.onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(form));
    const { errors, body } = readAccept(f);
    if (errors.length) { say(`Check: ${errors.join(', ')}`); return; }
    try {
      const res = await api(`reports/${r.id}/accept`, body);
      say(`${r.reference} accepted${res.commented ? '; the GitHub issue has a comment' : ''}.`);
      await list(); await open(r.id);
    } catch (err) { say(err.message); }
  };
}

async function open(id) {
  current = id;
  document.querySelectorAll('#list tr[data-id]').forEach(tr => tr.setAttribute('aria-current', String(+tr.dataset.id === id)));
  try {
    const { report: r } = await api(`reports/${id}`);
    const d = $('#detail');
    d.hidden = false;
    d.innerHTML = detailHtml(r);
    d.querySelector('#edit').onsubmit = async e => {
      e.preventDefault();
      const f = new FormData(e.target);
      try { await api(`reports/${id}`, { status: f.get('status'), note: f.get('note') }); say(`${r.reference} saved.`); await list(); }
      catch (err) { say(err.message); }
    };
    const acc = d.querySelector('#accept-open');
    if (acc) acc.onclick = () => openAccept(r, d);
    d.querySelector('#publish').onclick = async () => {
      if (!confirm(`Publish ${r.reference} as a public GitHub issue? The email is never included.`)) return;
      try {
        await api(`reports/${id}/publish`, { include_photo: !!d.querySelector('#with-photo')?.checked });
        say(`${r.reference} published.`); await list(); await open(id);
      } catch (err) { say(err.message); }
    };
  } catch (e) { say(e.message); }
}

$('#filters').addEventListener('change', list);
$('#list').addEventListener('click', e => { const tr = e.target.closest('tr[data-id]'); if (tr) open(+tr.dataset.id); });
list();
