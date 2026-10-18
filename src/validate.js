// What a report must be (POST /api/report), and the checks on an uploaded photo. Pure: tested by src/test/worker.test.mjs.

export const KINDS = ['year_or_detail', 'photo', 'other', 'general'];
export const STATUSES = ['new', 'in-progress', 'fixed', 'wontfix', 'published'];
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
