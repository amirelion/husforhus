// POST /api/report: a report from the map's form, stored in D1 (REPORTS) with its photo in R2 (PHOTOS).
// No IP address is stored: the rate limit keys on a salted hash of it held only in this isolate's memory for an hour.
import { validateReport, sniff, hasExif, MIN_FILL_MS } from './validate.js';

export const LIMIT = 5, WINDOW_MS = 3600_000;
let SALT = null;                                           // per isolate, never stored: the hashes cannot be reversed
const seen = new Map();                                    // hash → times of this hour's stored reports

export const json = (body, status = 200) => new Response(JSON.stringify(body), { status,
  headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' } });

async function connection(request) {
  SALT ??= crypto.getRandomValues(new Uint8Array(16));
  const ip = request.headers.get('CF-Connecting-IP') || '';
  const data = new Uint8Array([...SALT, ...new TextEncoder().encode(ip)]);
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(x => x.toString(16).padStart(2, '0')).join('');
}
function recent(hash, now) {
  const times = (seen.get(hash) || []).filter(t => now - t < WINDOW_MS);
  if (times.length) seen.set(hash, times); else seen.delete(hash);
  return times;
}
function remember(hash, now) {
  if (seen.size > 50_000) for (const [h] of seen) if (!recent(h, now).length) seen.delete(h);
  seen.set(hash, [...recent(hash, now), now]);
}

// The report's fields and photo, from a JSON body or a multipart one (field `report` as JSON, file `photo`).
async function read(request) {
  const type = request.headers.get('content-type') || '';
  if (type.startsWith('application/json')) return { raw: await request.json(), photo: null };
  if (type.startsWith('multipart/form-data')) {
    const form = await request.formData();
    const photo = form.get('photo');
    return { raw: JSON.parse(form.get('report') || '{}'), photo: photo && typeof photo !== 'string' && photo.size ? photo : null };
  }
  return null;
}

export async function handleReport(request, env, now = Date.now()) {
  if (request.method !== 'POST') return json({ error: 'method' }, 405);
  let body;
  try { body = await read(request); } catch { body = null; }
  if (!body || typeof body.raw !== 'object' || !body.raw) return json({ error: 'body' }, 400);
  const { raw, photo } = body;
  // A bot: the hidden field filled, or the form sent faster than a person can. It is told it worked; nothing is kept.
  if (raw.website || !(Number(raw.elapsed) >= MIN_FILL_MS)) return json({ reference: `HFH-${1000 + (now % 9000)}` });
  const hash = await connection(request);
  if (recent(hash, now).length >= LIMIT) return json({ error: 'rate' }, 429);
  const { errors, report } = validateReport(raw, photo);
  let bytes = null, type = null;
  if (photo && !errors.length) {
    bytes = new Uint8Array(await photo.arrayBuffer());
    type = sniff(bytes);
    if (!type) errors.push('photo_type');
    else if (hasExif(bytes, type)) errors.push('exif');
  }
  if (errors.length) return json({ error: 'invalid', fields: errors }, 400);
  const row = await env.REPORTS.prepare(`INSERT INTO reports (created_at, kind, building, message, email, lang, photo_credit,
      consent_own, consent_licence, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new') RETURNING id`)
    .bind(new Date(now).toISOString(), report.kind, report.building ? JSON.stringify(report.building) : null, report.message,
      report.email, report.lang, report.photo_credit, report.consent_own ? 1 : 0, report.consent_licence ? 1 : 0).first();
  if (bytes) {
    const key = `reports/${row.id}/photo.${type === 'jpeg' ? 'jpg' : type}`;
    await env.PHOTOS.put(key, bytes, { httpMetadata: { contentType: `image/${type}` } });
    await env.REPORTS.prepare('UPDATE reports SET photo_key = ?, photo_type = ? WHERE id = ?').bind(key, `image/${type}`, row.id).run();
  }
  remember(hash, now);
  return json({ reference: `HFH-${row.id}` }, 201);
}

// GET /api/photos/:id: a report's photo, only once the owner published it with "include photo".
export async function publicPhoto(env, id) {
  const r = await env.REPORTS.prepare('SELECT photo_key FROM reports WHERE id = ? AND photo_public = 1').bind(id).first();
  const obj = r?.photo_key && await env.PHOTOS.get(r.photo_key);
  if (!obj) return json({ error: 'not found' }, 404);
  return new Response(obj.body, { headers: { 'content-type': obj.httpMetadata?.contentType || 'image/jpeg',
    'cache-control': 'public, max-age=86400', 'x-content-type-options': 'nosniff' } });
}
