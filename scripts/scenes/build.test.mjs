import test from 'node:test';
import assert from 'node:assert/strict';
import { SCENES, buildScene, parseCsv } from './build.mjs';

// Greater Stockholm, generous enough for the marathon's turn at Sollentuna.
const BOX = { latMin: 59.2, latMax: 59.55, lonMin: 17.75, lonMax: 18.3 };
const inStockholm = (lat, lon) => lat >= BOX.latMin && lat <= BOX.latMax && lon >= BOX.lonMin && lon <= BOX.lonMax;

test('csv parser handles quotes, commas and doubled quotes', () => {
  assert.deepEqual(parseCsv('a,b\n"x, y","say ""hi"""\n'), [{ a: 'x, y', b: 'say "hi"' }]);
});

test('all 7 scenes parse', () => {
  assert.equal(Object.keys(SCENES).length, 7);
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

test('only the three launch stories are ready, in the index too', async () => {
  const { buildAll } = await import('./build.mjs');
  const ready = Object.entries(SCENES).filter(([, m]) => m.ready).map(([id]) => id).sort();
  assert.deepEqual(ready, ['s10-olympics-1912', 'tre-kronor-1697', 'vasa-1628']);
  assert.ok(buildAll);
});

test('WKT polygons parse to [lat, lon] rings', async () => {
  const { parseWkt } = await import('./build.mjs');
  assert.deepEqual(parseWkt('POLYGON((18 59, 18.1 59, 18.1 59.1, 18 59))'), [[[59, 18], [59, 18.1], [59.1, 18.1], [59, 18]]]);
  assert.equal(parseWkt('MULTIPOLYGON(((18 59, 18.1 59, 18 59.1, 18 59)), ((18 59, 18.1 59, 18 59.1, 18 59)))').length, 2);
  assert.throws(() => parseWkt('to be traced'));
});
