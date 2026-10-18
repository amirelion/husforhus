// What a report must be (POST /api/report), and the checks on an uploaded photo. Pure: tested by src/test/worker.test.mjs.

export const KINDS = ['year_or_detail', 'photo', 'other', 'general'];
export const STATUSES = ['new', 'in-progress', 'accepted', 'fixed', 'wontfix', 'published'];
export const CLOSED = ['fixed', 'wontfix', 'published'];
export const MAX_PHOTO = 10 * 1024 * 1024;
export const MIN_FILL_MS = 3000;
const EMAIL = /^[^\s@<>()",;:]+@[^\s@<>()",;:]+\.[A-Za-z]{2,}$/;

const str = (v, max) => (typeof v === 'string' ? v.trim().slice(0, max) : '');
const yes = v => v === true || v === 'true' || v === 'on' || v === '1';

// The building reference the card sends, cut to what it shows; null for a general report.
function building(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const gid = Number(raw.gid);
  if (!Number.isInteger(gid) || gid < 0) return null;
  return { gid, name: str(raw.name, 200), address: str(raw.address, 200), district: str(raw.district, 100),
    year: str(raw.year, 100), source: str(raw.source, 300), version: str(raw.version, 40),
    private: raw.private === true, link: str(raw.link, 300) };
}

// { errors: [...], report } — `photo` is the uploaded File/Blob or null.
export function validateReport(raw, photo) {
  const errors = [];
  const kind = KINDS.includes(raw?.kind) ? raw.kind : null;
  if (!kind) errors.push('kind');
  const b = building(raw?.building);
  if (kind === 'general' && b) errors.push('building');
  if (kind && kind !== 'general' && !b) errors.push('building');
  const message = typeof raw?.message === 'string' ? raw.message.trim() : '';
  if (message.length < 10 || message.length > 2000) errors.push('message');
  const email = str(raw?.email, 254);
  if (!EMAIL.test(email)) errors.push('email');
  const lang = raw?.lang === 'sv' ? 'sv' : 'en';
  const credit = str(raw?.photo_credit, 100);
  const consentOwn = yes(raw?.consent_own), consentLicence = yes(raw?.consent_licence);
  if (kind === 'photo' && !photo) errors.push('photo');
  if (photo) {
    if (kind !== 'photo') errors.push('photo');
    if (b?.private) errors.push('private');                  // a private house's card has no photo
    if (!consentOwn || !consentLicence) errors.push('consent');
    if (!credit) errors.push('photo_credit');
    if (photo.size > MAX_PHOTO) errors.push('photo_size');
  }
  return { errors, report: { kind, building: b, message, email, lang,
    photo_credit: photo ? credit : '', consent_own: photo ? consentOwn : false, consent_licence: photo ? consentLicence : false } };
}

// The photo's type from its first bytes (never from what the sender says): jpeg, png, webp or null.
export function sniff(bytes) {
  const b = bytes;
  if (b.length > 3 && b[0] === 0xFF && b[1] === 0xD8 && b[2] === 0xFF) return 'jpeg';
  if (b.length > 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4E && b[3] === 0x47) return 'png';
  if (b.length > 12 && ascii(b, 0, 4) === 'RIFF' && ascii(b, 8, 4) === 'WEBP') return 'webp';
  return null;
}
const ascii = (b, at, n) => String.fromCharCode(...b.subarray(at, at + n));

// Whether the image still carries metadata that can hold a place or a camera: a JPEG APP1 segment (EXIF, XMP),
// a PNG eXIf chunk, a WebP EXIF chunk. The page re-encodes every photo, so a clean one has none.
export function hasExif(bytes, type) {
  const b = bytes;
  if (type === 'jpeg') {
    let i = 2;
    while (i + 4 <= b.length) {
      if (b[i] !== 0xFF) return true;            // not a marker where one must be: refuse what we cannot read
      const m = b[i + 1];
      if (m === 0xFF) { i++; continue; }         // fill byte
      if (m === 0xDA || m === 0xD9) return false; // start of scan / end: no more headers
      if (m === 0xE1) return true;
      if (m >= 0xD0 && m <= 0xD7) { i += 2; continue; }
      i += 2 + ((b[i + 2] << 8) | b[i + 3]);
    }
    return false;
  }
  if (type === 'png') {
    for (let i = 8; i + 8 <= b.length;) {
      const len = ((b[i] << 24) >>> 0) + (b[i + 1] << 16) + (b[i + 2] << 8) + b[i + 3];
      const t = ascii(b, i + 4, 4);
      if (t === 'eXIf') return true;
      if (t === 'IEND') return false;
      i += 12 + len;
    }
    return false;
  }
  if (type === 'webp') {
    for (let i = 12; i + 8 <= b.length;) {
      const t = ascii(b, i, 4), len = b[i + 4] + (b[i + 5] << 8) + (b[i + 6] << 16) + (b[i + 7] << 24 >>> 0);
      if (t === 'EXIF' || t === 'XMP ') return true;
      i += 8 + len + (len & 1);
    }
    return false;
  }
  return true;
}

// "Accept" on a report (POST /api/admin/reports/:id/accept): what the change is. The page's form checks the same
// (web/admin/accept.js); pipeline/contributions.py checks it once more against the building.
export const CHANGES = ['year', 'main_address', 'name', 'photo', 'none'];
export const YEAR_VALUE = /^(\d{4})(?:-(\d{4}))?$/;
// Text that looks like an email address or a phone number: never in a public note or a value.
export const EMAIL_LIKE = /[^\s@]+@[^\s@]+\.[A-Za-z]{2,}/;
export const PHONE_LIKE = /(?:\+|\b0)\d[\d\s-]{6,}\d/;

// The map point of a report's link (?at=<x>,<z>,<zoom>), or null.
export function pointOf(link) {
  try {
    const v = (new URL(link).searchParams.get('at') || '').split(',').map(Number);
    return v.length === 3 && v.every(Number.isFinite) ? { x: v[0], z: v[1] } : null;
  } catch { return null; }
}

// { errors: [...], contribution } for the accept form's body and the report (row() shape).
export function validateContribution(raw, r) {
  const errors = [];
  const kind = CHANGES.includes(raw?.kind) ? raw.kind : null;
  if (!kind) errors.push('kind');
  const note = typeof raw?.public_note === 'string' ? raw.public_note.trim() : '';
  if (!note || note.length > 200 || /[\r\n]/.test(note)) errors.push('public_note');
  let value = typeof raw?.value === 'string' ? raw.value.trim() : '';
  if (kind && kind !== 'none' && !r.building) errors.push('building');
  if (kind === 'year') {
    const m = value.match(YEAR_VALUE);
    if (!m || (m[2] && +m[2] < +m[1]) || +m[1] < 1000 || +(m[2] || m[1]) > new Date().getUTCFullYear()) errors.push('value');
  } else if (kind === 'main_address') {
    if (!value || value.length > 200) errors.push('value');
  } else if (kind === 'name') {
    if (!value || value.length > 120 || /[\r\n]/.test(value)) errors.push('value');
    if (r.building?.private) errors.push('private');
  } else if (kind === 'photo') {
    if (!r.photo_key || !r.consent_own || !r.consent_licence || !r.photo_credit) errors.push('photo');
    if (r.building?.private) errors.push('private');
    value = r.photo_credit || '';             // the credit the sender gave under CC BY 4.0
  } else value = '';
  if (EMAIL_LIKE.test(note) || PHONE_LIKE.test(note) || (kind !== 'photo' && (EMAIL_LIKE.test(value) || PHONE_LIKE.test(value)))) {
    errors.push('personal');
  }
  const point = r.building ? pointOf(r.building.link) : null;
  return { errors, contribution: { kind, value, public_note: note, replaces_register: kind === 'year' && raw?.replaces_register === true,
    gid: r.building ? r.building.gid : null, data_version: r.building?.version || null, x: point?.x ?? null, z: point?.z ?? null } };
}
