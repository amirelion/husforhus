import test from 'node:test';
import assert from 'node:assert/strict';
import { SCENES, buildScene, parseCsv } from './build.mjs';

// Greater Stockholm, generous enough for the marathon's turn at Sollentuna.
const BOX = { latMin: 59.2, latMax: 59.55, lonMin: 17.75, lonMax: 18.3 };
const inStockholm = (lat, lon) => lat >= BOX.latMin && lat <= BOX.latMax && lon >= BOX.lonMin && lon <= BOX.lonMax;

test('csv parser handles quotes, commas and doubled quotes', () => {
  assert.deepEqual(parseCsv('a,b\n"x, y","say ""hi"""\n'), [{ a: 'x, y', b: 'say "hi"' }]);
});

test('all 11 scenes parse', () => {
  assert.equal(Object.keys(SCENES).length, 11);
  for (const id of Object.keys(SCENES)) assert.ok(buildScene(id).beats.length > 0, id);
});

for (const id of Object.keys(SCENES)) {
  test(`${id}: beats are complete and in Stockholm`, () => {
    const s = buildScene(id);
    assert.ok(s.title.en && s.title.sv && Number.isInteger(s.year) && typeof s.sensitive === 'boolean');
    for (const b of s.beats) {
      const w = `${id} beat ${b.n}`;
      assert.ok(b.caption.en && b.caption.sv, `${w}: caption in both languages`);
      assert.ok(b.duration_s > 0, `${w}: positive duration`);
      assert.ok(inStockholm(b.camera.lat, b.camera.lon), `${w}: camera inside Stockholm`);
      assert.ok(inStockholm(b.target.lat, b.target.lon), `${w}: target inside Stockholm`);
      assert.ok(b.camera.height_m > 0, `${w}: camera above ground`);
    }
    for (const o of s.overlays ?? []) {
      if (o.type === 'ghost' && o.ship) continue;   // the Vasa rides the route
      const pts = o.type === 'route' ? o.coords : o.type === 'ghost' ? o.rings.flat() : [o.at];
      assert.ok(o.type !== 'route' || pts.length >= 2, `${id}: route has 2+ points`);
      for (const [lat, lon] of pts) assert.ok(inStockholm(lat, lon), `${id} ${o.type}: [${lat}, ${lon}] inside Stockholm`);
    }
  });
}

test('the three overlay scenes have their route or outline', () => {
  for (const id of ['vasa-1628', 's10-olympics-1912', 's11']) {
    assert.ok(buildScene(id).overlays.some((o) => o.type === 'route'), id);
  }
});

test('route: false: metro-kymlinge has its station marker and no route line', () => {
  const o = buildScene('metro-kymlinge').overlays;
  assert.deepEqual(o, [{ type: 'marker', at: [59.395, 17.965], label: { en: 'Kymlinge', sv: 'Kymlinge' } }]);
});

test('only the finished stories are ready, in the index too', async () => {
  const { buildAll } = await import('./build.mjs');
  const ready = Object.entries(SCENES).filter(([, m]) => m.ready).map(([id]) => id).sort();
  assert.deepEqual(ready, ['metro-1950', 'metro-blue-line', 'metro-kymlinge', 'metro-vallingby', 's04', 's07-kristina-lock', 's10-olympics-1912', 's11', 's12', 'tre-kronor-1697', 'vasa-1628']);
  assert.ok(buildAll);
});

test('layers: the two metro stories force the metro on; an unknown layer fails the build', async () => {
  for (const id of ['metro-vallingby', 'metro-1950', 'metro-blue-line', 'metro-kymlinge']) assert.deepEqual(buildScene(id).layers, ['metro'], id);
  assert.equal(buildScene('vasa-1628').layers, undefined, 'other stories leave the legend alone');
  const fs = await import('node:fs'), os = await import('node:os'), path = await import('node:path');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'layers-'));
  fs.mkdirSync(path.join(root, 'scenes', 'metro-1950'), { recursive: true });
  for (const f of ['beats.csv', 'narration.csv']) fs.copyFileSync(path.join('scenes', 'metro-1950', f), path.join(root, 'scenes', 'metro-1950', f));
  SCENES['metro-1950'].layers = ['trams'];
  try { assert.throws(() => buildScene('metro-1950', root), /unknown layer\(s\) trams/); }
  finally { SCENES['metro-1950'].layers = ['metro']; }
});

test('timeline_year: a beat carries its own year when the column is set', () => {
  assert.deepEqual(buildScene('metro-vallingby').beats.map((b) => b.year), [1950, 1951, 1951, 1952, 1953, 1954, 1954, 1955]);
  assert.ok(buildScene('vasa-1628').beats.every((b) => b.year === undefined), 'no column, no beat year');
});

test('WKT polygons parse to [lat, lon] rings', async () => {
  const { parseWkt } = await import('./build.mjs');
  assert.deepEqual(parseWkt('POLYGON((18 59, 18.1 59, 18.1 59.1, 18 59))'), [[[59, 18], [59, 18.1], [59.1, 18.1], [59, 18]]]);
  assert.equal(parseWkt('MULTIPOLYGON(((18 59, 18.1 59, 18 59.1, 18 59)), ((18 59, 18.1 59, 18 59.1, 18 59)))').length, 2);
  assert.throws(() => parseWkt('to be traced'));
});

// ---------- Photos ----------
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { checkLicence, photoAuthor, resolvePhoto, addPhotos, USER_AGENT } from './build.mjs';

const lic = (code, name = code) => ({ License: { value: code }, LicenseShortName: { value: name } });

test('licence check: public domain, CC0, CC BY and CC BY-SA pass', () => {
  assert.deepEqual(checkLicence(lic('pd', 'Public domain')), { ok: true, licence: 'Public domain' });
  assert.equal(checkLicence(lic('cc0', 'CC0')).licence, 'CC0');
  assert.equal(checkLicence(lic('cc-by-2.5', 'CC BY 2.5')).licence, 'CC BY 2.5');
  assert.equal(checkLicence(lic('cc-by-sa-4.0', 'CC BY-SA 4.0')).licence, 'CC BY-SA 4.0');
});

test('licence check: NC, ND, GFDL-only, other and missing licences fail with a reason', () => {
  for (const code of ['cc-by-nc-2.0', 'cc-by-nd-4.0', 'cc-by-nc-sa-3.0', 'gfdl', 'fal', 'arr']) {
    const r = checkLicence(lic(code));
    assert.equal(r.ok, false, code);
    assert.match(r.reason, /not public domain/, code);
  }
  assert.match(checkLicence({}).reason, /no licence/);
});

test('author: HTML is stripped and "ingen uppgift" reads as unknown', () => {
  assert.equal(photoAuthor({ Artist: { value: '<a href="x">Johannes Scherman</a>' } }), 'Johannes Scherman');
  assert.equal(photoAuthor({ Artist: { value: 'ingen uppgift' } }), 'unknown author');
  assert.equal(photoAuthor({}), 'unknown author');
});

// A fake Commons: one file per licence; counts requests and checks they run one at a time with our User-Agent.
function fakeCommons(files) {
  const log = { calls: 0, active: 0, maxActive: 0, agents: new Set() };
  const fetchFn = async (url, init) => {
    log.calls++; log.active++; log.maxActive = Math.max(log.maxActive, log.active);
    log.agents.add(init?.headers?.['User-Agent']);
    await new Promise((r) => setTimeout(r, 5));
    log.active--;
    const u = new URL(url);
    if (u.hostname === 'commons.wikimedia.org') {
      const title = u.searchParams.get('titles').slice(5);
      const f = files[title];
      const pages = [f ? { title, imageinfo: [{ sha1: f.sha1, thumburl: `https://upload.example/${f.sha1}.jpg`, thumbwidth: 800, thumbheight: 600,
        descriptionurl: `https://commons.wikimedia.org/wiki/File:${title}`, extmetadata: { ...lic(f.code, f.name), Artist: { value: f.artist } } }] } : { title, missing: true }];
      return new Response(JSON.stringify({ query: { pages } }));
    }
    return new Response(new Uint8Array([0xff, 0xd8, 0xff]));
  };
  return { fetchFn, log };
}

test('resolvePhoto: an open file is downloaded once into img/<sha1>.jpg; a refused one gets no photo and a reason', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'scenes-'));
  const { fetchFn, log } = fakeCommons({
    'Open.jpg': { sha1: 'a'.repeat(40), code: 'cc-by-sa-4.0', name: 'CC BY-SA 4.0', artist: 'A. Person' },
    'Closed.jpg': { sha1: 'b'.repeat(40), code: 'cc-by-nc-4.0', name: 'CC BY-NC 4.0', artist: 'B' },
  });
  const r = await resolvePhoto('Open.jpg', dir, fetchFn);
  assert.equal(r.photo.src, `img/${'a'.repeat(40)}.jpg`);
  assert.ok(fs.existsSync(path.join(dir, r.photo.src)));
  assert.deepEqual(r.photo.credit, { author: 'A. Person', licence: 'CC BY-SA 4.0', page: 'https://commons.wikimedia.org/wiki/File:Open.jpg', file: 'File:Open.jpg' });
  const calls = log.calls;
  await resolvePhoto('Open.jpg', dir, fetchFn);
  assert.equal(log.calls, calls + 1, 'cached: only the metadata is asked again');
  const no = await resolvePhoto('Closed.jpg', dir, fetchFn);
  assert.equal(no.photo, undefined);
  assert.match(no.reason, /CC BY-NC 4.0/);
  assert.match((await resolvePhoto('Missing.jpg', dir, fetchFn)).reason, /no such file/);
  assert.equal(log.maxActive, 1, 'one request at a time');
  assert.deepEqual([...log.agents], [USER_AGENT]);
});

test('addPhotos: the scene JSON carries src, caption and credit; refused files are dropped with a reason', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'scenes-'));
  const { fetchFn } = fakeCommons({ 'Open.jpg': { sha1: 'c'.repeat(40), code: 'pd', name: 'Public domain', artist: 'ingen uppgift' } });
  const scene = { id: 'x', beats: [
    { n: 1, photo_file: 'Open.jpg', photo_caption: { en: 'A stadium', sv: 'En arena' } },
    { n: 2, photo_file: 'Gone.jpg', photo_caption: { en: 'x', sv: 'x' } },
    { n: 3 },
  ] };
  const problems = await addPhotos(scene, dir, fetchFn);
  assert.deepEqual(scene.beats[0].photo.caption, { en: 'A stadium', sv: 'En arena' });
  assert.equal(scene.beats[0].photo.credit.author, 'unknown author');
  assert.equal(scene.beats[0].photo_file, undefined);
  assert.equal(scene.beats[1].photo, undefined);
  assert.deepEqual(problems, ['x beat 2: Gone.jpg: no photo, no such file on Commons']);
});

test('built scenes: every photo is a local image under web/scenes/img with caption, credit and an open licence', () => {
  for (const id of Object.keys(SCENES)) {
    const s = JSON.parse(fs.readFileSync(new URL(`../../web/scenes/${id}.json`, import.meta.url)));
    for (const b of s.beats) {
      if (!b.photo) continue;
      const w = `${id} beat ${b.n}`;
      assert.match(b.photo.src, /^img\/[0-9a-f]{40}\.(jpg|jpeg|png|gif|webp)$/, w);
      assert.ok(fs.existsSync(new URL(`../../web/scenes/${b.photo.src}`, import.meta.url)), `${w}: image file exists`);
      assert.ok(b.photo.caption.en && b.photo.caption.sv, `${w}: caption in both languages`);
      assert.ok(b.photo.credit.author, w);
      assert.match(b.photo.credit.licence, /^(Public domain|CC0|CC BY( |-SA |$))/, w);
      assert.match(b.photo.credit.page, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/, w);
    }
  }
});

test('the 1912 story: 6–8 sourced beats, photos on construction and marathon, the turning point labelled', () => {
  const s = JSON.parse(fs.readFileSync(new URL('../../web/scenes/s10-olympics-1912.json', import.meta.url)));
  assert.ok(s.beats.length >= 6 && s.beats.length <= 8);
  for (const b of s.beats) assert.ok(b.sources.length, `beat ${b.n} has a source`);
  assert.equal(s.beats[0].photo.credit.file, 'File:Stockholms stadion bygget 1911-12.jpg');
  assert.ok(s.beats.find((b) => b.photo?.credit.file === 'File:Marathon Stockholm 14 juli 1912.gif' && /marathon/i.test(b.caption.en)));
  const pano = s.beats.find((b) => b.photo?.credit.file === 'File:Stockholms stadion 1912 invigning panorama.jpg');
  assert.ok(!pano || /after 1912/.test(pano.photo.caption.en), 'the panorama carries its date doubt');
  const turn = s.overlays.find((o) => o.type === 'marker' && o.always);
  assert.equal(turn.label.en, 'Turning point at Sollentuna church, 20 km');
});

test('vasa beat 7 sees the wreck site, and the hull (the ghost ship) sinks in that beat', () => {
  const s = buildScene('vasa-1628');
  const ship = s.overlays.find((o) => o.type === 'ghost' && o.ship);
  assert.equal(ship.ship.sinks_in_beat, 7);
  assert.equal(s.overlays.filter((o) => o.ship || o.type === 'ship').length, 1, 'one ship');
  const wreck = s.overlays.find((o) => o.type === 'marker' && /^Wreck site/.test(o.label.en)).at;
  const b = s.beats[6];
  // within 2 km of the wreck, and not straight above it
  const d = Math.hypot((b.camera.lat - wreck[0]) * 111e3, (b.camera.lon - wreck[1]) * 56e3);
  assert.ok(d > 300 && d < 2000, `camera ${Math.round(d)} m from the wreck`);
});

test('a ready story with fewer than 2 photo beats gets a warning, not an error', async () => {
  const { photoWarnings } = await import('./build.mjs');
  const beat = (photo) => ({ n: 1, ...(photo && { photo: { src: 'img/x.jpg' } }) });
  assert.equal(photoWarnings({ id: 'x', ready: true, beats: [beat(true), beat()] }).length, 1);
  assert.match(photoWarnings({ id: 'x', ready: true, beats: [beat()] })[0], /^warning: x is ready but only 0/);
  assert.deepEqual(photoWarnings({ id: 'x', ready: true, beats: [beat(true), beat(true)] }), []);
  assert.deepEqual(photoWarnings({ id: 'x', beats: [beat()] }), [], 'not ready: no warning');
  for (const id of Object.keys(SCENES)) {
    const s = JSON.parse(fs.readFileSync(new URL(`../../web/scenes/${id}.json`, import.meta.url)));
    assert.deepEqual(photoWarnings(s), [], `${id}: ready stories carry photos`);
  }
});
