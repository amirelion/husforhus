// web/ferries.js: the boats' switch and when they show, ferries.json read into routes, where each boat is at any second
// (back and forth, a stop at each pier, out of sight past an edge) and which way it is heading, what its tooltip says,
// finding it under the pointer, how much they grow when zoomed out, each look's paint against its water, and the
// low-poly models.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { boatsOnFrom, boatsShown, parseFerries, pointAlong, headingAt, routePlan, runAt, runTime, boatAt, calmTime,
  boatScale, MAX_BOOST, KINDS, EDGE_WAIT_S, EDGE_FADE_M, PAINT, PARTS, boatModels, wakeModel, hullShape, headingFor,
  routeLine, boatTitle, boatInfo, boatHtml, orList, segmentDistance, boatUnder, HIT_PX, placeName, SV_PLACES } from '../ferries.js';
import { makeT } from '../i18n.js';
import { THEMES } from '../themes.js';
import { rgb } from '../tone.js';

const I18N = Object.fromEntries(['en', 'sv'].map(l => [l, JSON.parse(readFileSync(new URL(`../i18n/${l}.json`, import.meta.url), 'utf8'))]));
const EN = makeT(I18N, 'en'), SV = makeT(I18N, 'sv');

// Small hand-made routes in local metres: an L-shaped ferry line between two piers (1200 m), a short ferry hop
// (300 m), and a ship lane from a pier out past the map's edge (3000 m).
const DATA = { version: 1, routes: [
  { id: 'r1', ref: '82', name: 'Line 82', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0], [800, 0], [800, 400]] },
  { id: 'r2', ref: '', name: 'Hop', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 100], [300, 100]] },
  { id: 'r3', ref: '', name: 'Lane', kind: 'ship', ends: ['pier', 'edge'], path: [[0, 0], [0, -3000]] },
] };
const [line, hop, lane] = parseFerries(DATA);

test('the switch is on unless this device switched it off', () => {
  assert.equal(boatsOnFrom(null), true);
  assert.equal(boatsOnFrom('on'), true);
  assert.equal(boatsOnFrom('off'), false);
  assert.equal(boatsOnFrom('anything'), true);
});

test('boats show at Today with the switch on, never for an earlier year, while the film plays or in a story', () => {
  const now = { on: true, year: 2025, yearMax: 2025 };
  assert.equal(boatsShown(now), true);
  assert.equal(boatsShown({ ...now, year: Infinity }), true);
  assert.equal(boatsShown({ ...now, year: 1990 }), false);
  assert.equal(boatsShown({ ...now, playing: true }), false);
  assert.equal(boatsShown({ ...now, story: true }), false);
  assert.equal(boatsShown({ ...now, on: false }), false);
});

test('ferries.json is read into routes; a route the viewer cannot sail is left out', () => {
  assert.deepEqual([line.length, hop.length, lane.length], [1200, 300, 3000]);
  assert.deepEqual(line.ends, ['pier', 'pier']);
  assert.deepEqual(lane.ends, ['pier', 'edge']);
  assert.equal(line.name, 'Line 82');
  assert.deepEqual(parseFerries(null), []);
  assert.deepEqual(parseFerries({ version: 2, routes: DATA.routes }), []);
  const odd = parseFerries({ version: 1, routes: [
    { id: 'a', kind: 'canoe', ends: ['pier', 'pier'], path: [[0, 0], [10, 0]] },    // an unknown kind
    { id: 'b', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0]] },             // one point
    { id: 'c', kind: 'ferry', ends: ['pier', 'pier'], path: [[5, 5], [5, 5]] },     // no length
    { id: 'd', kind: 'ferry', path: [[0, 0], [0, 0], [50, 0], ['x', 1]] },        // no ends: piers; repeats and junk go
  ] });
  assert.deepEqual(odd.map(r => r.id), ['d']);
  assert.deepEqual(odd[0].ends, ['pier', 'pier']);
  assert.deepEqual(odd[0].pts, [[0, 0], [50, 0]]);
});

test('a point along a route, and the route\'s direction there', () => {
  assert.deepEqual(pointAlong(line, 0), [0, 0]);
  assert.deepEqual(pointAlong(line, 400), [400, 0]);
  assert.deepEqual(pointAlong(line, 1000), [800, 200]);
  assert.deepEqual(pointAlong(line, -5), [0, 0]);
  assert.deepEqual(pointAlong(line, 9999), [800, 400]);
  assert.ok(Math.abs(headingAt(line, 400, 30)) < 1e-9);                         // east
  assert.ok(Math.abs(headingAt(line, 1000, 30) - Math.PI / 2) < 1e-9);          // +z, south
  const corner = headingAt(line, 800, 30);
  assert.ok(corner > 0.3 && corner < 1.3, 'turns smoothly through a corner');
});

test('a run speeds up out of a pier, keeps its speed, slows into the next; none at an edge', () => {
  const L = 1200, v = 16, total = (L + 60 + 60) / v;
  assert.deepEqual(runAt(0, L, v, 60, 60), { s: 0, speed: 0 });
  assert.equal(runAt(total, L, v, 60, 60).s, L);
  assert.equal(runAt(total, L, v, 60, 60).speed, 0);
  assert.equal(runAt(total / 2, L, v, 60, 60).speed, 1);
  let prev = -1;
  for (let t = 0; t <= total; t += 0.25) {
    const r = runAt(t, L, v, 60, 60);
    assert.ok(r.s >= prev && r.speed >= 0 && r.speed <= 1);
    prev = r.s;
  }
  assert.equal(runAt(0, 3000, 32, 300, 0).speed, 0);
  assert.equal(runAt((3000 + 300) / 32 - 0.01, 3000, 32, 300, 0).speed, 1);   // sails on at full speed past the edge
});

test('runTime is the run backwards: the seconds to cover a distance, on every part of the run', () => {
  for (const [L, v, r0, r1] of [[1200, 16, 60, 60], [3000, 32, 300, 0], [600, 32, 300, 0], [80, 16, 40, 40], [500, 16, 0, 60]]) {
    for (let s = 0; s <= L; s += L / 40) {
      const t = runTime(s, L, v, r0, r1);
      assert.ok(Math.abs(runAt(t, L, v, r0, r1).s - s) < 1e-6, `${L} m, ${s} m`);
    }
    assert.equal(runTime(-5, L, v, r0, r1), 0);
    assert.ok(Math.abs(runTime(L + 5, L, v, r0, r1) - (L + r0 + r1) / v) < 1e-9);
  }
});

test('a long ferry line has two boats half a round apart, a short one and a ship lane one', () => {
  const p = routePlan(line), h = routePlan(hop), s = routePlan(lane);
  assert.equal(p.boats, 2);
  assert.equal(h.boats, 1);
  assert.equal(s.boats, 1);
  assert.equal(p.period, 2 * KINDS.ferry.stop + 2 * (1200 + 120) / KINDS.ferry.speed);
  assert.equal(s.period, KINDS.ship.stop + EDGE_WAIT_S + 2 * (3000 + KINDS.ship.ramp) / KINDS.ship.speed);
  // the two boats on a line are never at the same place: they pass each other mid-line, each keeping to its right
  let closest = Infinity;
  for (let t = 0; t < p.period; t += 0.5) {
    const a = boatAt(p, 0, t), b = boatAt(p, 1, t);
    closest = Math.min(closest, Math.hypot(a.x - b.x, a.z - b.z));
  }
  assert.ok(closest > 2 * KINDS.ferry.offset - 1, `${closest}`);
  // drawn larger when zoomed out, they keep to their right by as much more, so their hulls still pass apart: on a
  // straight 1 km line the two pass a beam and more apart at true size and at the largest boost
  const km = routePlan(parseFerries({ version: 1, routes: [{ id: 'k', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0], [1000, 0]] }] })[0]);
  for (const scale of [1, MAX_BOOST]) {
    let near = Infinity;
    for (let t = 0; t < km.period; t += 0.25) {
      const a = boatAt(km, 0, t, scale), b = boatAt(km, 1, t, scale);
      near = Math.min(near, Math.hypot(a.x - b.x, a.z - b.z));
    }
    assert.ok(near >= KINDS.ferry.beam * scale + 4 * scale, `scale ${scale}: ${near}`);
  }
  // a hop shorter than two ramps shares it between them
  const tiny = routePlan(parseFerries({ version: 1, routes: [{ id: 't', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0], [80, 0]] }] })[0]);
  assert.deepEqual(tiny.ramps, [40, 40]);
});

// The distance from a point {x, z} to a polyline.
function distTo(pts, { x, z }) {
  let best = Infinity;
  for (let i = 1; i < pts.length; i++) {
    const [ax, az] = pts[i - 1], [bx, bz] = pts[i], dx = bx - ax, dz = bz - az;
    const k = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz)));
    best = Math.min(best, Math.hypot(x - ax - k * dx, z - az - k * dz));
  }
  return best;
}

test('a boat\'s place is a pure function of the time, moves smoothly and stays on its line', () => {
  const p = routePlan(line), step = 0.1;
  assert.deepEqual(boatAt(p, 0, 123.4), boatAt(p, 0, 123.4));
  assert.deepEqual(boatAt(p, 0, 50), boatAt(p, 0, 50 + p.period));          // round after round
  let prev = boatAt(p, 0, 0);
  for (let t = step; t < p.period * 1.5; t += step) {
    const b = boatAt(p, 0, t);
    // never much faster than its top speed: no jumps (the outside of a turn, its keep-right lane, is a little longer)
    assert.ok(Math.hypot(b.x - prev.x, b.z - prev.z) <= KINDS.ferry.speed * step * 1.3, `jumped at ${t.toFixed(1)}`);
    // on the line: within its offset of the L
    assert.ok(distTo(line.pts, b) <= KINDS.ferry.offset + 0.01, `off the line at ${t.toFixed(1)}`);
    prev = b;
  }
});

test('at a pier a boat stops, turns round and sets off the other way; it keeps to its right when under way', () => {
  const p = routePlan(hop), stop = KINDS.ferry.stop;
  // find a moment at the far pier: speed 0, at the end
  let t0 = null;
  for (let t = 0; t < p.period; t += 0.05) {
    const b = boatAt(p, 0, t);
    if (b.speed === 0 && Math.abs(b.x - 300) < 1e-6) { t0 = t; break; }
  }
  assert.ok(t0 !== null, 'it reaches the far pier');
  const arrive = boatAt(p, 0, t0 + 0.01), leave = boatAt(p, 0, t0 + stop - 0.02);
  assert.equal(arrive.alpha, 1);
  assert.ok(Math.abs(Math.cos(arrive.heading) - 1) < 1e-3, 'arrives heading east');
  assert.ok(Math.abs(Math.cos(leave.heading) + 1) < 1e-3, 'leaves heading west');
  const mid = boatAt(p, 0, t0 + stop + 9);   // under way westwards: its right is north (-z)
  assert.ok(mid.speed > 0 && Math.cos(mid.heading) < -0.99);
  assert.ok(mid.z < 100, 'keeps to its right');
});

test('at an edge end a ship fades out, waits out of sight and fades in again', () => {
  const p = routePlan(lane);
  const samples = [];
  for (let t = 0; t < p.period; t += 0.5) samples.push(boatAt(p, 0, t));
  const hidden = samples.filter(b => b.alpha === 0);
  assert.ok(hidden.length * 0.5 >= EDGE_WAIT_S - 1, 'out of sight for the wait');
  for (const b of hidden) assert.ok(Math.abs(b.z + 3000) < 1e-6, 'past the edge end');
  const fading = samples.filter(b => b.alpha > 0 && b.alpha < 1);
  assert.ok(fading.length > 4);
  for (const b of fading) assert.ok(-b.z > 3000 - EDGE_FADE_M - 1, 'fades only near the edge');
  assert.ok(samples.some(b => b.alpha === 1 && b.speed === 0), 'stands at its pier, whole');
});

test('under reduced motion each boat stands on a run of its own, whole, clear of its piers and lined up with its lane', () => {
  // straight routes of every shape the data has: a ferry line with two boats, a short hop, ship lanes out past the
  // edge either way round, a ship lane only 600 m long inside the map, and a ferry line from a pier to the edge
  const routes = parseFerries({ version: 1, routes: [
    { id: 'a', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0], [1600, 0]] },
    { id: 'b', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0], [0, 300]] },
    { id: 'c', kind: 'ship', ends: ['pier', 'edge'], path: [[0, 0], [3000, -3000]] },
    { id: 'd', kind: 'ship', ends: ['edge', 'pier'], path: [[0, -3000], [0, 0]] },
    { id: 'e', kind: 'ship', ends: ['pier', 'edge'], path: [[0, 0], [600, 0]] },
    { id: 'f', kind: 'ferry', ends: ['pier', 'edge'], path: [[0, 0], [-1700, 0]] },
  ] });
  for (const route of [...routes, line]) {
    const plan = routePlan(route), kind = KINDS[route.kind];
    const dir = Math.atan2(route.pts[route.pts.length - 1][1] - route.pts[0][1], route.pts[route.pts.length - 1][0] - route.pts[0][0]);
    const at = Array.from({ length: plan.boats }, (_, i) => boatAt(plan, i, calmTime(plan, i)));
    at.forEach((b, i) => {
      const what = `${route.id} boat ${i}`;
      assert.equal(b.alpha, 1, `${what}: whole, not fading or out of sight`);
      assert.ok(b.speed > 0, `${what}: on a run, not at a stop`);
      route.ends.forEach((e, k) => {
        const [x, z] = route.pts[k ? route.pts.length - 1 : 0];
        if (e === 'pier') assert.ok(Math.hypot(b.x - x, b.z - z) >= kind.length, `${what}: clear of its pier`);
      });
      // boat 0 sails out, boat 1 back; the L-shaped line is checked for the rest only
      if (route !== line) assert.ok(Math.cos(b.heading - dir) * (i ? -1 : 1) > 0.9999, `${what}: lined up with its lane`);
    });
    if (at.length === 2) assert.ok(Math.hypot(at[0].x - at[1].x, at[0].z - at[1].z) > 300, `${route.id}: apart`);
    assert.deepEqual(boatAt(plan, 0, calmTime(plan, 0)), at[0]);   // the same moment every time
  }
});

test('a boat grows with the camera\'s distance so it stays visible, up to four times, true size up close', () => {
  assert.equal(boatScale(500, 30), 1);
  assert.equal(boatScale(2500, 30), 1);
  assert.ok(boatScale(10000, 30) > 2 && boatScale(10000, 30) < MAX_BOOST);
  assert.equal(boatScale(30000, 30), MAX_BOOST);
  assert.equal(boatScale(20000, 190), 1);          // a ship is long enough as it is
  assert.ok(boatScale(30000, 190) > 1);
});

// WCAG relative luminance contrast.
const lum = h => rgb(h).map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)).reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

test('every look paints its boats to stand out on its water, with a lighter wake', () => {
  assert.deepEqual(Object.keys(PAINT).sort(), Object.keys(THEMES).sort());
  for (const [id, th] of Object.entries(THEMES)) {
    const p = PAINT[id];
    for (const k of [...PARTS, 'wake']) assert.match(p[k], /^#[0-9a-f]{6}$/, `${id} ${k}`);
    // the hull or the upper works reads against the water at a glance, and the other at least faintly
    const [a, b] = [contrast(p.hull, th.water), contrast(p.upper, th.water)].sort((x, y) => y - x);
    assert.ok(a >= 4.5, `${id}: ${a.toFixed(2)}`);
    assert.ok(b >= 1.5, `${id}: ${b.toFixed(2)}`);
    assert.ok(lum(p.wake) > lum(th.water), `${id}: the wake is lighter than the water`);
  }
});

test('the models: a 30 m ferry and a 190 m ship, waterline at 0, each vertex tagged with its part and model', () => {
  const m = boatModels();
  assert.equal(m.position.length % 9, 0);
  assert.equal(m.part.length, m.position.length / 3);
  assert.equal(m.model.length, m.part.length);
  for (const model of [0, 1]) {
    const xs = [], ys = [];
    for (let v = 0; v < m.model.length; v++) if (m.model[v] === model) { xs.push(m.position[3 * v]); ys.push(m.position[3 * v + 1]); }
    assert.equal(xs.length % 3, 0, 'whole triangles');
    const length = Math.max(...xs) - Math.min(...xs);
    assert.ok(Math.abs(length - [30, 190][model]) < 1e-6, `model ${model}: ${length}`);
    assert.ok(Math.min(...ys) < 0 && Math.max(...ys) > 0);
  }
  assert.ok([...m.part].every(p => p >= 0 && p < PARTS.length && Number.isInteger(p)));
  assert.ok([...m.part].some((p, v) => p === 3 && m.model[v] === 1), 'the ship has its dark band');
  const hull = hullShape(30, 7.5);
  assert.deepEqual(hull[4], [15, 0]);   // the bow
  const w = wakeModel(4);
  assert.equal(w.t[0], 0);
  assert.equal(w.t[w.t.length - 1], 1);
  assert.ok([...w.index].every(i => i < w.t.length));
});

// ---------- What a boat says ----------
// As s17_ferries writes them on 2026-10-20 (data/dev): a ferry line with its stops, one cut at the map's edge, a line
// known by name, and a ship lane out past the edge with its ports.
const SAYS = parseFerries({ version: 1, routes: [
  { id: 'r5981630', ref: '82', name: 'Djurgårdsfärjan 82', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0], [1600, 0]],
    stops: ['Slussen', 'Skeppsholmen', 'Allmänna gränd'] },
  { id: 'r7779528', ref: '89', name: 'Båt 89', kind: 'ferry', ends: ['pier', 'edge'], path: [[0, 0], [9000, 0]],
    stops: ['Klara Mälarstrand', 'Lilla Essingen', 'Ekensberg', 'Kungshättan', 'Tappström'] },
  { id: 'r11528943', ref: '', name: 'Cityline', kind: 'ferry', ends: ['pier', 'pier'], path: [[0, 0], [4000, 0]],
    stops: ['Nybroplan', 'Allmänna gränd', 'Masthamnen', 'Barnängsbryggan', 'Lumabryggan', 'Henriksdal'] },
  { id: 'r2545969', ref: '', name: 'Viking Line', kind: 'ship', ends: ['pier', 'edge'], path: [[0, 0], [4000, 0]],
    home: 'Stockholm', operator: 'Viking Line', dests: [{ to: 'Turku', via: ['Mariehamn', 'Långnäs'] },
      { to: 'Helsinki', via: ['Mariehamn'] }] },
] });
const [sl82, sl89, city, viking] = SAYS;

test('ferries.json\'s tooltip fields are read when there, names only, and an older file has none', () => {
  assert.deepEqual(sl82.stops, ['Slussen', 'Skeppsholmen', 'Allmänna gränd']);
  assert.deepEqual([viking.home, viking.operator, viking.dests.length], ['Stockholm', 'Viking Line', 2]);
  assert.deepEqual([line.stops, line.home, line.dests, line.operator], [[], '', [], '']);
  const [odd] = parseFerries({ version: 1, routes: [{ id: 'x', kind: 'ship', ends: ['pier', 'edge'], path: [[0, 0], [9, 0]],
    stops: [' A ', '', 7, 'B'], home: 5, operator: '  ', dests: [{ to: ' Turku ', via: ['', ' Mariehamn', null] }, { via: ['X'] }, 'Y', null] }] });
  assert.deepEqual(odd.stops, ['A', 'B']);
  assert.deepEqual([odd.home, odd.operator], ['', '']);
  assert.deepEqual(odd.dests, [{ to: 'Turku', via: ['Mariehamn'] }]);
  assert.deepEqual(parseFerries({ version: 1, routes: [{ kind: 'ferry', path: [[0, 0], [9, 0]], stops: ['Slussen'] }] })[0].stops, []);
});

test('a boat heads for the end it sails to: out along its path on the run out, back on the run back, the next run\'s at a stop', () => {
  for (const route of [hop, lane]) {
    const plan = routePlan(route), seen = new Set();
    for (let t = 0; t < plan.period; t += 0.25) {
      const b = boatAt(plan, 0, t), later = boatAt(plan, 0, t + 0.25);
      seen.add(b.toward);
      if (b.speed > 0 && later.speed > 0) {
        // under way: it gets nearer the end it heads for
        const [x, z] = route.pts[b.toward ? route.pts.length - 1 : 0];
        assert.ok(Math.hypot(later.x - x, later.z - z) < Math.hypot(b.x - x, b.z - z), `${route.id} at ${t}`);
      }
    }
    assert.deepEqual([...seen].sort(), [0, 1]);
  }
  // standing at a pier it says where it goes next: at the first pier the far end, at the far pier the first
  const plan = routePlan(hop);
  let first = null, far = null;
  for (let t = 0; t < plan.period && (first === null || far === null); t += 0.05) {
    const b = boatAt(plan, 0, t);
    if (b.speed !== 0) continue;
    if (Math.abs(b.x) < 1e-6) first = b; else if (Math.abs(b.x - 300) < 1e-6) far = b;
  }
  assert.equal(first.toward, 1);
  assert.equal(far.toward, 0);
});

test('where a boat is heading: a ferry\'s last stop or its first, a ship\'s destinations going out and home coming in', () => {
  assert.deepEqual(headingFor(sl82, 1), ['Allmänna gränd']);
  assert.deepEqual(headingFor(sl82, 0), ['Slussen']);
  assert.deepEqual(headingFor(sl89, 1), ['Tappström']);         // the line's end, past the map's edge
  assert.deepEqual(headingFor(viking, 1), ['Turku', 'Helsinki']);
  assert.deepEqual(headingFor(viking, 0), ['Stockholm']);
  assert.deepEqual(headingFor(line, 1), []);                     // an older file: nothing to say
  assert.deepEqual(headingFor({ ...viking, home: '' }, 0), []);
  assert.deepEqual(headingFor({ ...viking, dests: [] }, 1), []);
  // in Swedish the Finnish ports by their Swedish names
  assert.deepEqual(headingFor(viking, 1, 'sv'), ['Åbo', 'Helsingfors']);
  assert.deepEqual(headingFor(viking, 0, 'sv'), ['Stockholm']);
});

test('a loop that ends where it began (Sjöstadstrafiken) says no heading: it heads for the same pier either way', () => {
  const loop = { ...sl82, stops: ['Henriksdal', 'Barnängsbryggan', 'Lumabryggan', 'Henriksdal'] };
  assert.deepEqual(headingFor(loop, 1), []);
  assert.deepEqual(headingFor(loop, 0), []);
  assert.equal(routeLine(loop), 'Henriksdal – Barnängsbryggan – Lumabryggan – Henriksdal');   // the route still says it
  assert.deepEqual(boatInfo(loop, 1, EN), { title: 'Djurgårdsfärjan · line 82',
    route: 'Henriksdal – Barnängsbryggan – Lumabryggan – Henriksdal', heading: '', note: 'Real route, not a live position' });
});

test('the route in one line: the stops, or home, the ports on the way to every destination, and the destinations', () => {
  assert.equal(routeLine(sl82), 'Slussen – Skeppsholmen – Allmänna gränd');
  assert.equal(routeLine(viking), 'Stockholm – Mariehamn – Turku, Helsinki');   // Långnäs is on the way to Turku only
  assert.equal(routeLine({ ...viking, dests: [{ to: 'Tallinn', via: ['Mariehamn'] }] }), 'Stockholm – Mariehamn – Tallinn');
  assert.equal(routeLine({ ...viking, home: '', dests: [{ to: 'Tallinn', via: [] }] }), 'Tallinn');
  assert.equal(routeLine(line), '');
  assert.equal(routeLine({ ...viking, dests: [] }), '');
  // in Swedish: Åbo and Helsingfors, the ports that read the same left as they are
  assert.equal(routeLine(viking, 'sv'), 'Stockholm – Mariehamn – Åbo, Helsingfors');
  assert.equal(routeLine({ ...viking, dests: [{ to: 'Tallinn', via: ['Mariehamn'] }] }, 'sv'), 'Stockholm – Mariehamn – Tallinn');
  assert.equal(routeLine(sl82, 'sv'), 'Slussen – Skeppsholmen – Allmänna gränd');
  assert.equal(placeName('Turku', 'en'), 'Turku');
  assert.equal(placeName('Helsinki', 'sv'), 'Helsingfors');
  assert.equal(placeName('Mariehamn', 'sv'), 'Mariehamn');
  for (const [fi, sv] of Object.entries(SV_PLACES)) assert.notEqual(fi, sv);
});

test('the title: a ferry by its name and line number, a line known by name by its name, a ship by its operator', () => {
  assert.equal(boatTitle(sl82, EN), 'Djurgårdsfärjan · line 82');
  assert.equal(boatTitle(sl82, SV), 'Djurgårdsfärjan · linje 82');
  // a name that is only a word for a boat says nothing: the line number alone (SL's Båt 89)
  assert.equal(boatTitle(sl89, EN), 'Line 89');
  assert.equal(boatTitle(sl89, SV), 'Linje 89');
  assert.equal(boatTitle({ ...sl82, name: 'Färja 82' }, SV), 'Linje 82');
  // SL's commuter boats (Pendelbåt 80, 80X, 84) are called so in the page's language
  assert.equal(boatTitle({ ...sl82, ref: '80X', name: 'Pendelbåt 80X' }, EN), 'Commuter boat · line 80X');
  assert.equal(boatTitle({ ...sl82, ref: '80', name: 'Pendelbåt 80' }, SV), 'Pendelbåt · linje 80');
  assert.equal(boatTitle({ ...sl82, name: 'Pendelbåt' }, EN), 'Commuter boat · line 82');   // no number to drop
  assert.equal(boatTitle({ ...sl82, name: 'Djurgårdsbåt 82' }, EN), 'Djurgårdsbåt · line 82');   // a name, kept
  assert.equal(boatTitle({ ...sl82, name: 'Linje 182' }, EN), 'Linje 182 · line 82');       // a number, not the ref
  assert.equal(boatTitle({ ...sl82, name: '82' }, SV), 'Linje 82');
  assert.equal(boatTitle(city, EN), 'Cityline');
  assert.equal(boatTitle(viking, EN), 'Viking Line');
  assert.equal(boatTitle({ ...viking, operator: '', name: 'Silja Line' }, EN), 'Silja Line');
});

test('the tooltip in English and Swedish, and an older file\'s title and note only', () => {
  assert.deepEqual(boatInfo(sl82, 1, EN), { title: 'Djurgårdsfärjan · line 82', route: 'Slussen – Skeppsholmen – Allmänna gränd',
    heading: 'Heading for Allmänna gränd', note: 'Real route, not a live position' });
  assert.deepEqual(boatInfo(sl82, 0, SV), { title: 'Djurgårdsfärjan · linje 82', route: 'Slussen – Skeppsholmen – Allmänna gränd',
    heading: 'På väg mot Slussen', note: 'Riktig linje, inte var båten är just nu' });
  assert.equal(boatInfo(viking, 1, EN).heading, 'Heading for Turku or Helsinki');
  assert.equal(boatInfo(viking, 1, SV).heading, 'På väg mot Åbo eller Helsingfors');
  assert.equal(boatInfo(viking, 1, SV).route, 'Stockholm – Mariehamn – Åbo, Helsingfors');
  assert.equal(boatInfo(viking, 0, EN).heading, 'Heading for Stockholm');
  assert.deepEqual(boatInfo(hop, 1, EN), { title: 'Hop', route: '', heading: '', note: 'Real route, not a live position' });
  assert.notEqual(EN('boat.note'), SV('boat.note'));
  assert.equal(orList(['A', 'B', 'C'], 'en'), 'A, B, or C');
  assert.equal(orList(['Ropsten'], 'sv'), 'Ropsten');
});

test('the tooltip\'s HTML escapes every name and leaves out the lines it has nothing for', () => {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const html = boatHtml({ title: 'A <b> & B', route: '', heading: 'Heading for "C"', note: 'Note' }, esc);
  assert.equal(html, '<p class="boat-title">A &lt;b&gt; &amp; B</p><p class="boat-heading">Heading for &quot;C&quot;</p>' +
    '<p class="boat-note">Note</p>');
});

test('the boat under the pointer: the nearest hull whose reach takes the point, along its whole length', () => {
  assert.equal(segmentDistance(5, 5, [0, 0], [10, 0]), 5);
  assert.equal(segmentDistance(-3, 4, [0, 0], [10, 0]), 5);                 // past the stern: to its end
  assert.equal(segmentDistance(3, 4, [0, 0], [0, 0]), 5);                   // a boat seen end on
  const hulls = [{ k: 0, a: [100, 100], b: [300, 100], r: HIT_PX }, { k: 3, a: [100, 120], b: [140, 120], r: 30 }];
  assert.equal(boatUnder(hulls, 290, 108), 0);                              // near the bow of the long one
  assert.equal(boatUnder(hulls, 120, 112), 3);                              // nearer the second's line
  assert.equal(boatUnder(hulls, 200, 108), 0);                              // the second's reach ends near its bow
  assert.equal(boatUnder(hulls, 160, 125), 3);                              // past its bow, within its reach
  assert.equal(boatUnder(hulls, 200, 140), -1);
  assert.equal(boatUnder([], 0, 0), -1);
});
