// The Worker (src/worker.js) in Miniflare with a local D1 and R2: run with `npm run test:worker`.
// GitHub and the Access certs are mocked (outboundService); nothing leaves the machine.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { hasExif, sniff } from '../validate.js';

const TEAM = 'team.example.com', AUD = 'test-aud';
const issues = [];
let mf, keys;

const b64url = buf => Buffer.from(buf).toString('base64url');
async function jwt(payload, key = keys.privateKey, kid = 'k1') {
  const h = b64url(JSON.stringify({ alg: 'RS256', kid })), p = b64url(JSON.stringify(payload));
  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(`${h}.${p}`));
  return `${h}.${p}.${b64url(sig)}`;
}
const goodToken = () => jwt({ aud: [AUD], iss: `https://${TEAM}`, email: 'owner@example.org', exp: Math.floor(Date.now() / 1000) + 600 });

before(async () => {
  keys = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]),
    hash: 'SHA-256' }, true, ['sign', 'verify']);
  const jwk = { ...(await crypto.subtle.exportKey('jwk', keys.publicKey)), kid: 'k1' };
  mf = new Miniflare(convertV4MiniflareOptions({
    modules: [{ type: 'ESModule', path: 'src/worker.js' }, { type: 'ESModule', path: 'src/report.js' },
      { type: 'ESModule', path: 'src/admin.js' }, { type: 'ESModule', path: 'src/access.js' },
      { type: 'ESModule', path: 'src/validate.js' }],
    compatibilityDate: '2026-09-30',
    d1Databases: ['REPORTS'], r2Buckets: ['PHOTOS'],
    bindings: { ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, GITHUB_TOKEN: 'test-token' },
    serviceBindings: { ASSETS: () => new Response('the static site') },
    outboundService: async req => {
      const u = new URL(req.url);
      if (u.host === TEAM && u.pathname === '/cdn-cgi/access/certs') return Response.json({ keys: [jwk] });
      if (u.host === 'api.github.com') {
        issues.push({ url: req.url, auth: req.headers.get('authorization'), body: await req.json() });
        return Response.json({ html_url: 'https://github.com/amirelion/husforhus/issues/7' }, { status: 201 });
      }
      return new Response('blocked', { status: 599 });
    },
  }));
  const db = await mf.getD1Database('REPORTS');
  const sql = readFileSync('src/migrations/0001_reports.sql', 'utf8').replace(/--.*$/gm, '');
  for (const stmt of sql.split(';').map(s => s.trim()).filter(Boolean)) await db.prepare(stmt).run();
});
after(() => mf?.dispose());

let ipN = 0;
const ip = () => `203.0.113.${++ipN}`;
const BORS = { gid: 12, name: 'Börshuset', address: 'Stortorget 2', district: 'Gamla stan', year: '1778',
  source: 'Heritage register (RAÄ): built 1778', version: 'v20261017', private: false, link: 'https://husforhus.se/?at=1,2,3' };
const base = o => ({ kind: 'year_or_detail', building: BORS, message: 'The year should be 1776, see the plaque.',
  email: 'reader@example.org', lang: 'en', elapsed: 5000, ...o });
const post = (body, from = ip()) => mf.dispatchFetch('http://localhost/api/report', { method: 'POST',
  headers: { 'content-type': 'application/json', 'CF-Connecting-IP': from }, body: JSON.stringify(body) });
// Encoded by Node's own Request (Miniflare's fetch does not take Node's FormData), sent as bytes.
async function multipart(report, photo, from = ip()) {
  const form = new FormData();
  form.set('report', JSON.stringify(report));
  form.set('photo', new Blob([photo], { type: 'image/jpeg' }), 'p.jpg');
  const req = new Request('http://localhost/', { method: 'POST', body: form });
  return mf.dispatchFetch('http://localhost/api/report', { method: 'POST', body: await req.arrayBuffer(),
    headers: { 'content-type': req.headers.get('content-type'), 'CF-Connecting-IP': from } });
}
const admin = async (path, init = {}) => mf.dispatchFetch(`http://localhost/api/admin/${path}`, { ...init,
  headers: { 'Cf-Access-Jwt-Assertion': await goodToken(), ...(init.body ? { 'content-type': 'application/json' } : {}), ...init.headers } });
const rows = async () => (await (await mf.getD1Database('REPORTS')).prepare('SELECT * FROM reports ORDER BY id').all()).results;

// A JPEG's headers: SOI, an optional APP1 (EXIF), a quantisation table, the scan.
const CLEAN = Uint8Array.from([0xFF, 0xD8, 0xFF, 0xDB, 0x00, 0x04, 0x00, 0x00, 0xFF, 0xDA, 0x00, 0x02, 0x11, 0x22, 0xFF, 0xD9]);
const EXIF = Uint8Array.from([0xFF, 0xD8, 0xFF, 0xE1, 0x00, 0x08, 0x45, 0x78, 0x69, 0x66, 0x00, 0x00, ...CLEAN.slice(2)]);
const photoReport = o => base({ kind: 'photo', photo_credit: 'A. Reader', consent_own: true, consent_licence: true, ...o });

test('pages that are not /api/* are the static assets', async () => {
  assert.equal(await (await mf.dispatchFetch('http://localhost/')).text(), 'the static site');
  assert.equal((await mf.dispatchFetch('http://localhost/api/nothing')).status, 404);
});

test('a valid report is stored as new, without the IP, and gets a reference', async () => {
  const r = await post(base());
  assert.equal(r.status, 201);
  const { reference } = await r.json();
  const stored = (await rows()).at(-1);
  assert.equal(reference, `HFH-${stored.id}`);
  assert.equal(stored.status, 'new');
  assert.ok(stored.created_at);
  assert.deepEqual(JSON.parse(stored.building), BORS);
  assert.ok(!JSON.stringify(stored).includes('203.0.113.'));
});

test('validation: kind, message length, email, building', async () => {
  const fields = async b => { const r = await post(b); assert.equal(r.status, 400); return (await r.json()).fields; };
  assert.ok((await fields(base({ kind: 'nope' }))).includes('kind'));
  assert.ok((await fields(base({ message: 'too short' }))).includes('message'));
  assert.ok((await fields(base({ message: 'x'.repeat(2001) }))).includes('message'));
  assert.ok((await fields(base({ email: 'not-an-email' }))).includes('email'));
  assert.ok((await fields(base({ email: '' }))).includes('email'));
  assert.ok((await fields(base({ building: null }))).includes('building'));            // a card kind needs its building
  assert.ok((await fields(base({ kind: 'general' }))).includes('building'));           // a suggestion has none
  assert.equal((await post(base({ kind: 'general', building: null }))).status, 201);
  assert.ok((await fields(photoReport())).includes('photo'));                          // "Add a photo" needs a photo
});

test('the honeypot and a form sent in under 3 s are told it worked, and nothing is stored', async () => {
  const n = (await rows()).length;
  for (const b of [base({ website: 'http://spam.example.com' }), base({ elapsed: 800 }), base({ elapsed: undefined })]) {
    const r = await post(b);
    assert.equal(r.status, 200);
    assert.match((await r.json()).reference, /^HFH-\d+$/);
  }
  assert.equal((await rows()).length, n);
});

test('at most 5 reports an hour from one connection', async () => {
  const from = ip();
  for (let i = 0; i < 5; i++) assert.equal((await post(base(), from)).status, 201);
  assert.equal((await post(base(), from)).status, 429);
  assert.equal((await post(base(), ip())).status, 201);                                // another connection is not held
});

test('a photo is stored in R2 under its report; never for a private house; both consents needed', async () => {
  const r = await multipart(photoReport(), CLEAN);
  assert.equal(r.status, 201);
  const id = Number((await r.json()).reference.slice(4));
  const row = (await rows()).find(x => x.id === id);
  assert.equal(row.photo_key, `reports/${id}/photo.jpg`);
  assert.equal(row.consent_own, 1);
  assert.ok(await (await mf.getR2Bucket('PHOTOS')).get(row.photo_key));
  assert.equal((await mf.dispatchFetch(`http://localhost/api/photos/${id}`)).status, 404);     // not public before publishing

  const refuse = async (report, photo = CLEAN) => { const x = await multipart(report, photo); assert.equal(x.status, 400); return (await x.json()).fields; };
  assert.ok((await refuse(photoReport({ building: { ...BORS, private: true } }))).includes('private'));
  assert.ok((await refuse(photoReport({ consent_own: false }))).includes('consent'));
  assert.ok((await refuse(photoReport({ consent_licence: false }))).includes('consent'));
  assert.ok((await refuse(photoReport(), new TextEncoder().encode('GIF89a not a photo'))).includes('photo_type'));
});

test('a JPEG that still has an EXIF (APP1) segment is refused', async () => {
  assert.equal(hasExif(EXIF, sniff(EXIF)), true);
  assert.equal(hasExif(CLEAN, sniff(CLEAN)), false);
  const r = await multipart(photoReport(), EXIF);
  assert.equal(r.status, 400);
  assert.deepEqual((await r.json()).fields, ['exif']);
});

test('admin endpoints refuse a request without a valid Access token', async () => {
  const bad = [undefined, 'garbage', await jwt({ aud: ['other'], iss: `https://${TEAM}`, exp: 4e9 }),
    await jwt({ aud: [AUD], iss: `https://${TEAM}`, exp: 1 }),
    await jwt({ aud: [AUD], iss: `https://${TEAM}`, exp: 4e9 }, (await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5',
      modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign'])).privateKey)];
  for (const token of bad) {
    for (const [path, method] of [['reports', 'GET'], ['reports/1', 'POST'], ['reports/1/publish', 'POST']]) {
      const r = await mf.dispatchFetch(`http://localhost/api/admin/${path}`, { method,
        headers: { 'content-type': 'application/json', ...(token ? { 'Cf-Access-Jwt-Assertion': token } : {}) },
        body: method === 'POST' ? '{}' : undefined });
      assert.equal(r.status, 403, `${method} ${path} with ${token ? 'a bad' : 'no'} token`);
    }
  }
  assert.equal(issues.length, 0);
});

test('admin: list, filter, change status and note', async () => {
  const { reports } = await (await admin('reports?kind=general')).json();
  assert.ok(reports.length >= 1 && reports.every(r => r.kind === 'general'));
  const id = reports[0].id;
  const r = await admin(`reports/${id}`, { method: 'POST', body: JSON.stringify({ status: 'in-progress', note: 'looking' }) });
  assert.equal((await r.json()).report.status, 'in-progress');
  assert.equal((await (await admin('reports?status=in-progress')).json()).reports[0].note, 'looking');
  assert.equal((await admin(`reports/${id}`, { method: 'POST', body: JSON.stringify({ status: 'lost' }) })).status, 400);
});

test('publishing creates a GitHub issue without the email; the photo only when asked', async () => {
  const id = Number((await (await multipart(photoReport(), CLEAN)).json()).reference.slice(4));
  let r = await admin(`reports/${id}/publish`, { method: 'POST', body: JSON.stringify({ include_photo: false }) });
  assert.equal(r.status, 200);
  const rep = (await r.json()).report;
  assert.equal(rep.status, 'published');
  assert.equal(rep.issue_url, 'https://github.com/amirelion/husforhus/issues/7');
  let issue = issues.at(-1);
  assert.equal(issue.url, 'https://api.github.com/repos/amirelion/husforhus/issues');
  assert.equal(issue.auth, 'Bearer test-token');
  assert.ok(!JSON.stringify(issue.body).includes('reader@example.org'));
  assert.ok(!JSON.stringify(issue.body).includes('@'));
  assert.match(issue.body.body, /Börshuset/);
  assert.match(issue.body.body, /The year should be 1776/);
  assert.ok(!issue.body.body.includes('/api/photos/'));
  assert.equal((await mf.dispatchFetch(`http://localhost/api/photos/${id}`)).status, 404);

  r = await admin(`reports/${id}/publish`, { method: 'POST', body: JSON.stringify({ include_photo: true }) });
  issue = issues.at(-1);
  assert.match(issue.body.body, new RegExp(`/api/photos/${id}\\)`));
  assert.match(issue.body.body, /A\. Reader, CC BY 4\.0/);
  assert.ok(!JSON.stringify(issue.body).includes('reader@example.org'));
  assert.equal((await mf.dispatchFetch(`http://localhost/api/photos/${id}`)).status, 200);
});

test('the daily cron blanks emails of reports closed more than 12 months ago, and only those', async () => {
  const db = await mf.getD1Database('REPORTS');
  const ins = (closed) => db.prepare(`INSERT INTO reports (created_at, kind, message, email, lang, status, closed_at)
    VALUES ('2024-01-01T00:00:00Z', 'general', 'an old suggestion', 'old@example.org', 'en', ?, ?) RETURNING id`)
    .bind(closed ? 'fixed' : 'new', closed).first();
  const old = (await ins('2025-01-01T00:00:00.000Z')).id, recent = (await ins('2026-06-01T00:00:00.000Z')).id, open = (await ins(null)).id;
  const worker = await mf.getWorker();
  await worker.scheduled({ cron: '17 3 * * *', scheduledTime: new Date('2026-10-18T03:17:00Z') });
  const email = async id => (await db.prepare('SELECT email FROM reports WHERE id = ?').bind(id).first()).email;
  assert.equal(await email(old), '');
  assert.equal(await email(recent), 'old@example.org');
  assert.equal(await email(open), 'old@example.org');
});
