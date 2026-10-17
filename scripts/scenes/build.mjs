#!/usr/bin/env node
// Build web/scenes/<id>.json and web/scenes/index.json from scenes/<id>/*.csv.
// Usage: node scripts/scenes/build.mjs   (Node 20+, no dependencies)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(HERE, '..', '..');
const DEFAULT_DURATION_S = 8;

// Per-scene metadata the CSVs don't carry. sensitive: shows a warning and never autoplays
// (history-scenes.md lists s10 beat 5 / the marathon death; Vasa and Tre Kronor state deaths too).
export const SCENES = {
  'vasa-1628': { title: { en: 'The Vasa sinks, 1628', sv: 'Vasa sjunker 1628' }, year: 1628, sensitive: true, ready: true },
  's04': { title: { en: 'The great fire of 1625', sv: 'Stora branden 1625' }, year: 1625, sensitive: false, ready: true },
  's07-kristina-lock': { title: { en: "Queen Kristina's lock, 1637–1642", sv: 'Drottning Kristinas sluss 1637–1642' }, year: 1642, sensitive: false, ready: true },
  'tre-kronor-1697': { title: { en: 'Tre Kronor burns, 1697', sv: 'Tre Kronor brinner 1697' }, year: 1697, sensitive: false, ready: true },
  's10-olympics-1912': { title: { en: 'The Stockholm Olympics, 1912', sv: 'Olympiska spelen i Stockholm 1912' }, year: 1912, sensitive: true, ready: true },
  's11': { title: { en: 'The Stockholm Exhibition, 1930', sv: 'Stockholmsutställningen 1930' }, year: 1930, sensitive: false, ready: true },
  's12': { title: { en: 'The clearance of Klara, 1952–1977', sv: 'Klararivningarna 1952–1977' }, year: 1952, sensitive: false, ready: true },
  'metro-vallingby': { title: { en: 'Vällingby: a town around a station, 1950–1954', sv: 'Vällingby: en stad kring en station 1950–1954' },
    year: 1950, sensitive: false, layers: ['metro'], ready: true },
  'metro-1950': { title: { en: 'The first metro, 1 October 1950', sv: 'Den första tunnelbanan, 1 oktober 1950' },
    year: 1950, sensitive: false, layers: ['metro'], ready: true },
};

// ready: shown in the Stories list (web/scene-player.js lists only these).
// layers: map layers the player shows during the story whatever the legend says (LAYERS; web/app.js storyLayers).
export const LAYERS = ['metro'];

// WKT POLYGON / MULTIPOLYGON in lon/lat to rings of [lat, lon] (outer rings only; holes are not used).
export function parseWkt(wkt) {
  const m = /^\s*(MULTI)?POLYGON\s*\((.*)\)\s*$/i.exec(wkt || '');
  if (!m) throw new Error(`not a POLYGON or MULTIPOLYGON: "${String(wkt).slice(0, 40)}"`);
  const rings = m[1] ? m[2].split(/\)\s*\)\s*,\s*\(\s*\(/) : [m[2]];
  return rings.map((r) => r.replace(/[()]/g, '').split(',').map((pt) => {
    const [lon, lat] = pt.trim().split(/\s+/).map(Number);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) throw new Error(`bad WKT point "${pt}"`);
    return [lat, lon];
  }));
}

// The story's lost buildings (ghosts.csv): an extruded shape per row from from_beat to until_beat (both 1-based,
// until empty = the end); height_m per part, ";"-separated. footprint "ship" is the Vasa's hull, drawn along the route;
// its sinks_in_beat (1-based) is the beat in which it goes under.
export function ghostOverlays(dir, id) {
  const file = path.join(dir, 'ghosts.csv');
  if (!fs.existsSync(file)) return [];
  return readCsv(file).filter((r) => r.from_beat).map((r) => {
    const w = `${id}/ghosts.csv ${r.name}`;
    const geom = r.geometry ?? r.footprint;
    const heights = r.height_m.split(';').map((h) => num(h.trim(), w));
    const o = { type: 'ghost', label: { en: r.name, sv: r.name }, from: num(r.from_beat, w), heights,
      confidence: r.geometry_confidence || r.confidence };
    if (r.until_beat) o.until = num(r.until_beat, w);
    if (geom === 'ship') {
      const ship = { length_m: 69, beam_m: 12 };
      if (r.sinks_in_beat) ship.sinks_in_beat = num(r.sinks_in_beat, w);
      return { ...o, ship };
    }
    o.rings = parseWkt(geom);
    if (o.rings.length !== heights.length) throw new Error(`${w}: ${o.rings.length} parts but ${heights.length} heights`);
    return o;
  });
}

// Overlay files per scene: route lines and closed outlines (both emitted as type "route").
const OVERLAYS = {
  'vasa-1628': [{ file: 'route.csv', label: { en: "Vasa's route, 10 August 1628", sv: 'Vasas färdväg 10 augusti 1628' }, markers: 'place' }],
  's10-olympics-1912': [{ file: 'route.csv', label: { en: 'Marathon route, 14 July 1912', sv: 'Maratonbanan 14 juli 1912' }, markers: 'name' }],
  's11': [{ file: 'site.csv', label: { en: 'Exhibition grounds (approximate)', sv: 'Utställningsområdet (ungefärligt)' }, closed: true }],
};

export function parseCsv(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); field = '';
      if (row.some((f) => f !== '')) rows.push(row);
      row = [];
    } else field += c;
  }
  row.push(field);
  if (row.some((f) => f !== '')) rows.push(row);
  const [head, ...body] = rows;
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h.trim(), (r[i] ?? '').trim()])));
}

const readCsv = (file) => parseCsv(fs.readFileSync(file, 'utf8'));
const num = (v, what) => {
  const n = Number(v);
  if (v === '' || !Number.isFinite(n)) throw new Error(`${what}: not a number: "${v}"`);
  return n;
};

export function buildScene(id, root = REPO) {
  const meta = SCENES[id];
  if (!meta) throw new Error(`unknown scene ${id}`);
  const dir = path.join(root, 'scenes', id);
  const seconds = new Map();
  for (const r of readCsv(path.join(dir, 'narration.csv'))) {
    const s = Number(r.target_seconds);
    if (r.target_seconds !== '' && Number.isFinite(s)) seconds.set(r.beat, Math.max(seconds.get(r.beat) ?? 0, s));
  }
  const beats = readCsv(path.join(dir, 'beats.csv')).map((r) => {
    const w = `${id} beat ${r.beat}`;
    return {
      n: num(r.beat, w),
      camera: { lat: num(r.camera_lat, w), lon: num(r.camera_lon, w), height_m: num(r.camera_height_m, w) },
      target: { lat: num(r.target_lat, w), lon: num(r.target_lon, w) },
      duration_s: seconds.get(r.beat) || DEFAULT_DURATION_S,
      // timeline_year (optional): the year the timeline shows in this beat, else the scene's year
      ...(r.timeline_year ? { year: num(r.timeline_year, w) } : {}),
      caption: { en: r.caption_en, sv: r.caption_sv },
      sources: (r.sources ?? r.caption_source ?? '').split(';').map((s) => s.trim()).filter(Boolean),
      ...(r.photo_file ? { photo_file: r.photo_file, photo_caption: { en: r.photo_caption_en, sv: r.photo_caption_sv } } : {}),
    };
  });
  const scene = { id, title: meta.title, year: meta.year, sensitive: meta.sensitive, beats };
  if (meta.ready) scene.ready = true;
  if (meta.layers) {
    const bad = meta.layers.filter((l) => !LAYERS.includes(l));
    if (bad.length) throw new Error(`${id}: unknown layer(s) ${bad.join(', ')} (known: ${LAYERS.join(', ')})`);
    scene.layers = [...meta.layers];
  }
  const overlays = [];
  for (const o of OVERLAYS[id] ?? []) {
    const pts = readCsv(path.join(dir, o.file));
    const coords = pts.map((p) => [num(p.lat, `${id}/${o.file}`), num(p.lon, `${id}/${o.file}`)]);
    if (o.closed) coords.push([...coords[0]]);
    overlays.push({ type: 'route', coords, label: o.label });
    if (o.markers) {
      const seen = new Set();
      for (const p of pts) {
        const key = `${p.lat},${p.lon}`;
        if (seen.has(key)) continue;
        seen.add(key);
        // a row with its own label_en/label_sv keeps that label on the map in every beat it is in view
        if (p.label_en) overlays.push({ type: 'marker', at: [Number(p.lat), Number(p.lon)], label: { en: p.label_en, sv: p.label_sv || p.label_en }, always: true });
        else overlays.push({ type: 'marker', at: [Number(p.lat), Number(p.lon)], label: { en: p[o.markers], sv: p[o.markers] } });
      }
    }
  }
  overlays.push(...ghostOverlays(dir, id));
  if (overlays.length) scene.overlays = overlays;
  return scene;
}

// ---------- Photos from Wikimedia Commons ----------
const COMMONS_API = 'https://commons.wikimedia.org/w/api.php';
export const USER_AGENT = 'HusForHus/1.0 (+https://github.com/amirelion/husforhus)';
const THUMB_W = 800;
const stripHtml = (s) => String(s ?? '').replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();

// Open licences only: public domain, CC0, CC BY and CC BY-SA (any version). extmetadata.License is Commons' code
// ("pd", "cc0", "cc-by-4.0", "cc-by-sa-3.0"); anything with NC or ND, or any other licence, is refused.
export function checkLicence(meta) {
  const code = stripHtml(meta?.License?.value).toLowerCase();
  const name = stripHtml(meta?.LicenseShortName?.value);
  if (!code) return { ok: false, reason: 'no licence in the file metadata' };
  if (code === 'pd' || code.startsWith('pd-')) return { ok: true, licence: 'Public domain' };
  if (code === 'cc0' || code.startsWith('cc0-') || code.startsWith('cc-zero')) return { ok: true, licence: 'CC0' };
  if (/^cc-by(-sa)?(-\d+(\.\d+)?)?([a-z-]*)?$/.test(code) && !/-(nc|nd)\b/.test(code)) return { ok: true, licence: name || code.toUpperCase() };
  return { ok: false, reason: `licence "${name || code}" is not public domain, CC0, CC BY or CC BY-SA` };
}
export function photoAuthor(meta) {
  const a = stripHtml(meta?.Artist?.value);
  return !a || /^(ingen uppgift|unknown|okänd|okänt|anonymous|anonym)/i.test(a) ? 'unknown author' : a;
}

// One Commons file: its metadata, the licence check, and an 800 px thumbnail (or the original, if narrower) saved
// as img/<sha1>.<ext> under outDir, skipped when already there. Returns { photo } or { reason }.
// fetchFn is injectable for the tests; every request runs one after the other.
export async function resolvePhoto(file, outDir, fetchFn = fetch) {
  const title = file.startsWith('File:') ? file : `File:${file}`;
  const q = new URLSearchParams({ action: 'query', titles: title, prop: 'imageinfo', iiprop: 'url|sha1|size|extmetadata',
    iiurlwidth: String(THUMB_W), format: 'json', formatversion: '2' });
  let info;
  try {
    const r = await fetchFn(`${COMMONS_API}?${q}`, { headers: { 'User-Agent': USER_AGENT } });
    if (!r.ok) return { reason: `Commons API answered HTTP ${r.status}` };
    const page = (await r.json())?.query?.pages?.[0];
    info = page?.imageinfo?.[0];
    if (!info) return { reason: 'no such file on Commons' };
  } catch (e) { return { reason: `Commons API failed: ${e.message}` }; }
  const lic = checkLicence(info.extmetadata);
  if (!lic.ok) return { reason: lic.reason };
  if (!/^[0-9a-f]{40}$/.test(info.sha1 ?? '')) return { reason: 'no sha1 in the file metadata' };
  const url = info.thumburl || info.url;
  const ext = (path.extname(new URL(url).pathname).slice(1) || 'jpg').toLowerCase();
  if (!['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return { reason: `unexpected image type .${ext}` };
  const name = `${info.sha1}.${ext}`;
  const dest = path.join(outDir, 'img', name);
  if (!fs.existsSync(dest)) {
    try {
      const r = await fetchFn(url, { headers: { 'User-Agent': USER_AGENT } });
      if (!r.ok) return { reason: `thumbnail download answered HTTP ${r.status}` };
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, Buffer.from(await r.arrayBuffer()));
    } catch (e) { return { reason: `thumbnail download failed: ${e.message}` }; }
  }
  return { photo: { src: `img/${name}`, width: info.thumbwidth || info.width, height: info.thumbheight || info.height,
    credit: { author: photoAuthor(info.extmetadata), licence: lic.licence, page: info.descriptionurl, file: title } } };
}

// Turns each beat's photo_file into a photo (or drops it, saying why). Returns the reasons, for the build's log.
export async function addPhotos(scene, outDir, fetchFn = fetch) {
  const problems = [];
  for (const b of scene.beats) {
    if (!b.photo_file) continue;
    const { photo_file: file, photo_caption: caption } = b;
    delete b.photo_file; delete b.photo_caption;
    if (!caption?.en || !caption?.sv) { problems.push(`${scene.id} beat ${b.n}: ${file}: no photo, caption missing in EN or SV`); continue; }
    const r = await resolvePhoto(file, outDir, fetchFn);
    if (r.photo) b.photo = { ...r.photo, caption };
    else problems.push(`${scene.id} beat ${b.n}: ${file}: no photo, ${r.reason}`);
  }
  return problems;
}

// A ready story should carry photos (scenes/README.md, "What a story needs"): a warning, not an error, below 2.
export const MIN_PHOTOS = 2;
export function photoWarnings(scene) {
  if (!scene.ready) return [];
  const n = scene.beats.filter((b) => b.photo || b.photo_file).length;
  return n < MIN_PHOTOS ? [`warning: ${scene.id} is ready but only ${n} beat(s) have a photo (aim for 3–5, at least ${MIN_PHOTOS})`] : [];
}

export async function buildAll(root = REPO, fetchFn = fetch) {
  const out = path.join(root, 'web', 'scenes');
  fs.mkdirSync(out, { recursive: true });
  const index = [];
  for (const id of Object.keys(SCENES)) {
    const scene = buildScene(id, root);
    for (const p of await addPhotos(scene, out, fetchFn)) console.warn(p);
    for (const p of photoWarnings(scene)) console.warn(p);
    fs.writeFileSync(path.join(out, `${id}.json`), JSON.stringify(scene, null, 2) + '\n');
    index.push({ id, title: scene.title, year: scene.year, beats: scene.beats.length, ...(scene.ready && { ready: true }) });
  }
  fs.writeFileSync(path.join(out, 'index.json'), JSON.stringify({ scenes: index }, null, 2) + '\n');
  return index;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  for (const s of await buildAll()) console.log(`${s.id}: ${s.beats} beats`);
}
