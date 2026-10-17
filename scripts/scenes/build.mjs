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
  's04': { title: { en: 'The great fire of 1625', sv: 'Stora branden 1625' }, year: 1625, sensitive: false },
  's07-kristina-lock': { title: { en: "Queen Kristina's lock, 1637–1642", sv: 'Drottning Kristinas sluss 1637–1642' }, year: 1642, sensitive: false },
  'tre-kronor-1697': { title: { en: 'Tre Kronor burns, 1697', sv: 'Tre Kronor brinner 1697' }, year: 1697, sensitive: false, ready: true },
  's10-olympics-1912': { title: { en: 'The Stockholm Olympics, 1912', sv: 'Olympiska spelen i Stockholm 1912' }, year: 1912, sensitive: true, ready: true },
  's11': { title: { en: 'The Stockholm Exhibition, 1930', sv: 'Stockholmsutställningen 1930' }, year: 1930, sensitive: false },
  's12': { title: { en: 'The clearance of Klara, 1952–1977', sv: 'Klararivningarna 1952–1977' }, year: 1952, sensitive: false },
};

// ready: shown in the Stories list (web/scene-player.js lists only these).

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
// until empty = the end); height_m per part, ";"-separated. footprint "ship" is the Vasa's hull, drawn along the route.
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
    if (geom === 'ship') return { ...o, ship: { length_m: 69, beam_m: 12 } };
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
      caption: { en: r.caption_en, sv: r.caption_sv },
      sources: (r.sources ?? r.caption_source ?? '').split(';').map((s) => s.trim()).filter(Boolean),
    };
  });
  const scene = { id, title: meta.title, year: meta.year, sensitive: meta.sensitive, beats };
  if (meta.ready) scene.ready = true;
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
        overlays.push({ type: 'marker', at: [Number(p.lat), Number(p.lon)], label: { en: p[o.markers], sv: p[o.markers] } });
      }
    }
  }
  overlays.push(...ghostOverlays(dir, id));
  if (overlays.length) scene.overlays = overlays;
  return scene;
}

export function buildAll(root = REPO) {
  const out = path.join(root, 'web', 'scenes');
  fs.mkdirSync(out, { recursive: true });
  const index = [];
  for (const id of Object.keys(SCENES)) {
    const scene = buildScene(id, root);
    fs.writeFileSync(path.join(out, `${id}.json`), JSON.stringify(scene, null, 2) + '\n');
    index.push({ id, title: scene.title, year: scene.year, beats: scene.beats.length, ...(scene.ready && { ready: true }) });
  }
  fs.writeFileSync(path.join(out, 'index.json'), JSON.stringify({ scenes: index }, null, 2) + '\n');
  return index;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  for (const s of buildAll()) console.log(`${s.id}: ${s.beats} beats`);
}
