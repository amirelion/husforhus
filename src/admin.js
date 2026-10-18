// /api/admin/*: the owner's triage (web/admin/), behind Cloudflare Access and checked again here (access.js).
import { verifyAccess } from './access.js';
import { json } from './report.js';
import { STATUSES, CLOSED, KINDS } from './validate.js';

export const REPO = 'amirelion/husforhus';
const KIND_TITLE = { year_or_detail: 'Wrong or missing year or detail', photo: 'Photo', other: 'Something else', general: 'Suggestion' };

const row = r => r && { ...r, building: r.building ? JSON.parse(r.building) : null, reference: `HFH-${r.id}`,
  consent_own: !!r.consent_own, consent_licence: !!r.consent_licence, photo_public: !!r.photo_public };

// The GitHub issue for a report: its kind, the building reference and the message. Never the email.
export function issueFor(r, { photoUrl = '' } = {}) {
  const b = r.building;
  const what = b ? (b.name || b.address || `building ${b.gid}`) : 'general';
  const lines = [`**Kind:** ${KIND_TITLE[r.kind] || r.kind}`, `**Reference:** HFH-${r.id}`];
  if (b) {
    lines.push('', '**Building**', `- gid ${b.gid} in data ${b.version || '?'}`);
    for (const [k, label] of [['name', 'Name'], ['address', 'Address'], ['district', 'District'], ['year', 'Year shown'],
      ['source', 'Source shown'], ['link', 'Map']]) if (b[k]) lines.push(`- ${label}: ${b[k]}`);
  }
  lines.push('', '**Message**', '', ...r.message.split('\n').map(l => `> ${l}`));
  if (photoUrl) lines.push('', `![Photo for HFH-${r.id}](${photoUrl})`, '', `Photo: ${r.photo_credit}, CC BY 4.0 (granted by the sender).`);
  return { title: `${KIND_TITLE[r.kind] || r.kind}: ${what} (HFH-${r.id})`, body: lines.join('\n') };
}

async function one(env, id) {
  return row(await env.REPORTS.prepare('SELECT * FROM reports WHERE id = ?').bind(id).first());
}

export async function handleAdmin(request, env, url) {
  if (!await verifyAccess(request, env)) return json({ error: 'access' }, 403);
  // A POST must be JSON: a cross-site form cannot send that without a preflight, which nothing here answers.
  if (request.method === 'POST' && !(request.headers.get('content-type') || '').startsWith('application/json')) {
    return json({ error: 'content-type' }, 415);
  }
  const path = url.pathname.slice('/api/admin/'.length);
  if (path === 'reports' && request.method === 'GET') {
    const where = [], args = [];
    const status = url.searchParams.get('status'), kind = url.searchParams.get('kind');
    if (STATUSES.includes(status)) { where.push('status = ?'); args.push(status); }
    if (KINDS.includes(kind)) { where.push('kind = ?'); args.push(kind); }
    const { results } = await env.REPORTS.prepare(`SELECT * FROM reports ${where.length ? `WHERE ${where.join(' AND ')}` : ''}
      ORDER BY id DESC LIMIT 500`).bind(...args).all();
    return json({ reports: results.map(row) });
  }
  const m = path.match(/^reports\/(\d+)(\/photo|\/publish)?$/);
  if (!m) return json({ error: 'not found' }, 404);
  const id = Number(m[1]), r = await one(env, id);
  if (!r) return json({ error: 'not found' }, 404);
  if (!m[2] && request.method === 'GET') return json({ report: r });
  if (m[2] === '/photo' && request.method === 'GET') {
    const obj = r.photo_key && await env.PHOTOS.get(r.photo_key);
    if (!obj) return json({ error: 'not found' }, 404);
    return new Response(obj.body, { headers: { 'content-type': r.photo_type || 'image/jpeg', 'cache-control': 'private, no-store' } });
  }
  if (request.method !== 'POST') return json({ error: 'method' }, 405);
  const body = await request.json().catch(() => ({}));
  if (!m[2]) {
    const status = body.status ?? r.status, note = typeof body.note === 'string' ? body.note.slice(0, 4000) : r.note;
    if (!STATUSES.includes(status)) return json({ error: 'status' }, 400);
    await setStatus(env, id, status, note, r);
    return json({ report: await one(env, id) });
  }
  // publish
  if (!env.GITHUB_TOKEN) return json({ error: 'no token' }, 500);
  const withPhoto = body.include_photo === true && !!r.photo_key && !r.building?.private;
  const issue = issueFor(r, { photoUrl: withPhoto ? `${url.origin}/api/photos/${id}` : '' });
  const gh = await fetch(`https://api.github.com/repos/${REPO}/issues`, { method: 'POST', body: JSON.stringify(issue),
    headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: 'application/vnd.github+json',
      'x-github-api-version': '2022-11-28', 'user-agent': 'husforhus-reports', 'content-type': 'application/json' } });
  if (!gh.ok) return json({ error: 'github', status: gh.status }, 502);
  const { html_url: issueUrl } = await gh.json();
  await env.REPORTS.prepare('UPDATE reports SET issue_url = ?, photo_public = ? WHERE id = ?').bind(issueUrl, withPhoto ? 1 : 0, id).run();
  await setStatus(env, id, 'published', r.note, r);
  return json({ report: await one(env, id) });
}

async function setStatus(env, id, status, note, was) {
  const closed = CLOSED.includes(status) ? (CLOSED.includes(was.status) && was.closed_at) || new Date().toISOString() : null;
  await env.REPORTS.prepare('UPDATE reports SET status = ?, note = ?, closed_at = ? WHERE id = ?').bind(status, note, closed, id).run();
}

// The daily cron: a report closed more than 12 months ago keeps everything but the sender's email.
export async function forgetEmails(env, now = Date.now()) {
  const before = new Date(now);
  before.setUTCFullYear(before.getUTCFullYear() - 1);
  return (await env.REPORTS.prepare("UPDATE reports SET email = '' WHERE closed_at IS NOT NULL AND closed_at < ? AND email != ''")
    .bind(before.toISOString()).run()).meta.changes;
}
