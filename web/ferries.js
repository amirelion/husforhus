// Boats on the map (spec 2026-10-20, feature 5): the city's ferries and the Baltic ships sail their real routes, read
// from web/data/<version>/ferries.json (s17_ferries; OpenStreetMap route=ferry inside the municipality). They are
// illustration, not live positions: a boat's place is a pure function of the time, so a test can ask where every boat is
// at any second. Each boat goes back and forth along its route, slows into a pier and stops there a while, turns round,
// and at an "edge" end (the lane leaves the map's water) fades out, waits out of sight and fades in again.
// Pure functions, tested by node --test (web/test/ferries.test.mjs); web/ferries-layer.js draws the boats and
// web/app.js decides when they show (on by default, at Today only).

// On by default, remembered per device (hfh-boats: 'on' | 'off'), never in the URL.
export const BOATS_KEY = 'hfh-boats';
export const boatsOnFrom = stored => stored !== 'off';

// Shown while the switch is on and the timeline is at Today; never while the film plays or a story runs.
export const boatsShown = ({ on, year, yearMax, playing = false, story = false }) =>
  !!on && year >= yearMax && !playing && !story;

// The two kinds of boat: a city ferry about 30 m long, a Baltic ship about 190 m. Speeds (m/s) are about four times the
// real ones (a city ferry makes some 4 m/s, a ship 8), so a boat visibly moves at the home view. stop: seconds at a
// pier; ramp: metres over which it slows into a pier or speeds up out of one; offset: metres it keeps to its own
// right of the line at true size, so two ferries on one line pass each other (boatAt scales it with the boat); wake:
// the wake's length and its width at the tail.
export const KINDS = {
  ferry: { length: 30, beam: 7.5, speed: 16, stop: 12, ramp: 60, offset: 6, wake: [70, 22] },
  ship: { length: 190, beam: 29, speed: 32, stop: 30, ramp: 300, offset: 0, wake: [260, 80] },
};
export const EDGE_WAIT_S = 40;    // out of sight past an "edge" end, before it comes back
export const EDGE_FADE_M = 300;   // it fades over this much of the route before an "edge" end
export const TWO_FERRIES_M = 1000; // a ferry line this long or longer has two boats; a ship lane always one

// ---------- Routes ----------
// ferries.json (version 1) -> the routes the map can sail: each with its path as a polyline (cumulative lengths), its
// two ends ('pier' or 'edge') and its kind. A route of an unknown kind, or with fewer than two points, is left out, so
// a newer file cannot break the viewer.
export function parseFerries(data) {
  if (!data || data.version !== 1 || !Array.isArray(data.routes)) return [];
  const out = [];
  for (const r of data.routes) {
    if (!r || !KINDS[r.kind] || !Array.isArray(r.path)) continue;
    const pts = r.path.filter(p => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]))
      .filter((p, i, a) => i === 0 || p[0] !== a[i - 1][0] || p[1] !== a[i - 1][1]);
    if (pts.length < 2) continue;
    const at = [0];
    for (let i = 1; i < pts.length; i++) at.push(at[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    const ends = [0, 1].map(i => (r.ends?.[i] === 'edge' ? 'edge' : 'pier'));
    out.push({ id: String(r.id ?? out.length), ref: String(r.ref ?? ''), name: String(r.name ?? ''), kind: r.kind, ends,
      pts, at, length: at[at.length - 1] });
  }
  return out;
}

// The point s metres along a route (clamped to its ends): a binary search over the cumulative lengths.
export function pointAlong(route, s) {
  const { pts, at, length } = route;
  if (s <= 0) return pts[0];
  if (s >= length) return pts[pts.length - 1];
  let lo = 1, hi = at.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (at[mid] < s) lo = mid + 1; else hi = mid; }
  const k = (s - at[lo - 1]) / ((at[lo] - at[lo - 1]) || 1);
  return [pts[lo - 1][0] + k * (pts[lo][0] - pts[lo - 1][0]), pts[lo - 1][1] + k * (pts[lo][1] - pts[lo - 1][1])];
}

// The route's direction at s, as an angle (atan2 of z over x), measured over a window (twice the boat's length, in
// boatAt), so a boat turns smoothly through the corners of a simplified line.
export function headingAt(route, s, window) {
  const a = pointAlong(route, s - window / 2), b = pointAlong(route, s + window / 2);
  if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6) {
    const [p, q] = [route.pts[0], route.pts[route.pts.length - 1]];
    return Math.atan2(q[1] - p[1], q[0] - p[0]);
  }
  return Math.atan2(b[1] - a[1], b[0] - a[0]);
}

// A number in [0, 1) from a route's id, so the routes do not all set out at the same moment.
export function hash01(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967296;
}

// How a route is sailed: a stop (or the wait out of sight) at each end and a run each way, the boats spread evenly
// over the round. A run speeds up over the ramp out of a pier and slows over the ramp into one (none at an edge, where
// the boat sails on out of sight), so it takes (length + both ramps) / speed.
export function routePlan(route) {
  const k = KINDS[route.kind], L = route.length;
  const ramps = route.ends.map(e => (e === 'pier' ? k.ramp : 0));
  const fit = Math.min(1, L / Math.max(1e-9, ramps[0] + ramps[1]));   // a short route: the ramps share it
  const r = ramps.map(x => x * fit);
  const waits = route.ends.map(e => (e === 'pier' ? k.stop : EDGE_WAIT_S));
  const sail = (L + r[0] + r[1]) / k.speed;
  return { route, kind: k, ramps: r, waits, sail, period: waits[0] + sail + waits[1] + sail,
    boats: route.kind === 'ferry' && L >= TWO_FERRIES_M ? 2 : 1, phase: hash01(route.id) };
}

// A run of length L at top speed v, speeding up over r0 and slowing over r1: the distance covered after t seconds, and
// the speed then as a share of v.
export function runAt(t, L, v, r0, r1) {
  const t0 = 2 * r0 / v, t1 = 2 * r1 / v, total = (L + r0 + r1) / v;
  t = Math.max(0, Math.min(total, t));
  if (t < t0) return { s: v * t * t / (2 * t0), speed: t / t0 };
  const left = total - t;
  if (left < t1) return { s: L - v * left * left / (2 * t1), speed: left / t1 };
  return { s: r0 + v * (t - t0), speed: 1 };
}

// The other way round: the seconds the same run takes to cover s metres (calmTime puts a boat at a place this way).
export function runTime(s, L, v, r0, r1) {
  const t0 = 2 * r0 / v, t1 = 2 * r1 / v, total = (L + r0 + r1) / v;
  s = Math.max(0, Math.min(L, s));
  if (s < r0) return Math.sqrt(2 * t0 * s / v);
  if (s > L - r1) return total - Math.sqrt(2 * t1 * (L - s) / v);
  return t0 + (s - r0) / v;
}

const smooth = k => (k <= 0 ? 0 : k >= 1 ? 1 : k * k * (3 - 2 * k));

// Boat i of a route at time t (seconds): where it is ({x, z}), where its bow points (heading, the angle of its
// direction, atan2 of z over x), how much of it shows (alpha: 0 out of sight past an edge end, fading near one) and
// its speed as a share of its top speed (0 at a stop: no wake). scale: how much larger than life the layer draws it
// (boatScale); its keep-right offset grows with it, so two ferries drawn four times as wide still pass apart.
export function boatAt(plan, i, t, scale = 1) {
  const { route, kind, ramps, waits, sail, period } = plan, L = route.length;
  let u = (((t + (plan.phase + i / plan.boats) * period) % period) + period) % period;
  const fade = s => (route.ends[0] === 'edge' ? smooth(s / EDGE_FADE_M) : 1) *
    (route.ends[1] === 'edge' ? smooth((L - s) / EDGE_FADE_M) : 1);
  const at = (s, back, speed) => {
    const fwd = headingAt(route, s, 2 * kind.length);
    const [x, z] = pointAlong(route, s), heading = back ? fwd + Math.PI : fwd;
    // keep to its own right of the line, less near the ends, so it still meets its pier
    const off = kind.offset * scale * Math.min(1, s / 100, (L - s) / 100), dx = Math.cos(heading), dz = Math.sin(heading);
    return { x: x - dz * off, z: z + dx * off, heading, alpha: fade(s), speed };
  };
  // a stop at end e (0 or 1): at a pier it turns round in the middle of the stop; past an edge it is out of sight
  const stop = (e, k) => {
    const s = e ? L : 0, arrive = headingAt(route, s, 2 * kind.length) + (e ? 0 : Math.PI);
    const turn = smooth((k - 0.2) / 0.6);
    const [x, z] = pointAlong(route, s);
    return { x, z, heading: arrive + Math.PI * turn, alpha: route.ends[e] === 'edge' ? 0 : 1, speed: 0 };
  };
  if (u < waits[0]) return stop(0, u / waits[0]);
  u -= waits[0];
  if (u < sail) { const r = runAt(u, L, kind.speed, ramps[0], ramps[1]); return at(r.s, false, r.speed); }
  u -= sail;
  if (u < waits[1]) return stop(1, u / waits[1]);
  u -= waits[1];
  const r = runAt(u, L, kind.speed, ramps[1], ramps[0]);
  return at(L - r.s, true, r.speed);
}

// Under reduced motion a boat stands still for good, so each one stands at a moment of its own rather than one shared
// moment, which could leave a ship turned across its quay, or a ferry out of sight past an edge, for as long as the
// page was open. That moment puts it on a run, clear of both ends (its own length from a pier, the fade's length from
// an edge, where the route is long enough for both): a lone boat in the middle of that stretch, two boats a third and
// two thirds along it, the second sailing back, so they stand apart.
export function calmTime(plan, i) {
  const { route, kind, ramps, waits, sail, period, boats } = plan, L = route.length;
  const [m0, m1] = route.ends.map(e => (e === 'edge' ? EDGE_FADE_M : kind.length));
  const [a, b] = m0 + m1 < L ? [m0, L - m1] : [0, L];
  const s = a + (b - a) * (i + 1) / (boats + 1);
  const u = i % 2 ? waits[0] + sail + waits[1] + runTime(L - s, L, kind.speed, ramps[1], ramps[0])
    : waits[0] + runTime(s, L, kind.speed, ramps[0], ramps[1]);
  return u - (plan.phase + i / boats) * period;
}

// How much larger than life a boat is drawn at a camera distance: enough that it stays a few pixels long when the
// map is zoomed out (about 0.8% of the distance), never more than four times its size, and true size up close.
export const MAX_BOOST = 4;
export const boatScale = (dist, length) => Math.min(MAX_BOOST, Math.max(1, dist * 0.008 / length));

// ---------- Colours ----------
// Each look's paint for the boats, chosen against its water (web/themes.js) and never any operator's livery or SL's
// styling: hull, upper works, windows, the ships' dark band at the waterline, and the wake (lighter than the water,
// drawn see-through). On the dark waters (Ärg, Blå timmen) the boats are light; on the pale ones (Kalk, Paper) their
// hulls are dark and their upper works white. Blå timmen's windows are lit. web/test/ferries.test.mjs checks the
// contrast.
export const PAINT = {
  arg: { hull: '#e2dbcd', upper: '#f7f5f0', windows: '#2b3a46', band: '#22303a', wake: '#a9c0cc' },
  kalk: { hull: '#2e3c45', upper: '#fbfaf6', windows: '#46565f', band: '#2a3740', wake: '#eef4f5' },
  blatimme: { hull: '#c9d2dc', upper: '#e8ecf1', windows: '#f2c66d', band: '#141d2b', wake: '#86a6c8' },
  paper: { hull: '#3c4a52', upper: '#ffffff', windows: '#4c5a62', band: '#2f3b42', wake: '#f6f9f8' },
};
export const PARTS = ['hull', 'upper', 'windows', 'band'];

// ---------- Models ----------
// A hull's outline seen from above, metres, bow towards +x: a square stern with its corners cut, straight sides, and a
// bow that narrows over the front `bow` share of its length. Convex, so a fan fills it.
export function hullShape(L, B, bow = 0.22) {
  const h = L / 2, b = B / 2;
  return [[-h, -b * 0.82], [-h + 0.05 * L, -b], [h - bow * L, -b], [h - bow * L * 0.4, -b * 0.6], [h, 0],
    [h - bow * L * 0.4, b * 0.6], [h - bow * L, b], [-h + 0.05 * L, b], [-h, b * 0.82]];
}

// One prism: the outline's walls from y0 to y1 and its top, as plain triangles, every vertex tagged with its part
// (PARTS) and its model (0 ferry, 1 ship).
function prism(out, outline, y0, y1, part, model, top = true) {
  const n = outline.length, push = (x, y, z) => { out.pos.push(x, y, z); out.part.push(part); out.model.push(model); };
  for (let i = 0; i < n; i++) {
    const [ax, az] = outline[i], [bx, bz] = outline[(i + 1) % n];
    push(ax, y0, az); push(bx, y0, bz); push(bx, y1, bz);
    push(ax, y0, az); push(bx, y1, bz); push(ax, y1, az);
  }
  if (!top) return;
  for (let i = 1; i < n - 1; i++) {
    push(outline[0][0], y1, outline[0][1]); push(outline[i][0], y1, outline[i][1]); push(outline[i + 1][0], y1, outline[i + 1][1]);
  }
}
const box = (x0, x1, b) => [[x0, -b], [x1, -b], [x1, b], [x0, b]];
// A deckhouse whose front is rounded: from x0 to x1, half as wide as b, its front narrowing over `nose` metres.
const house = (x0, x1, b, nose) => [[x0, -b], [x1 - nose, -b], [x1, -b * 0.45], [x1, b * 0.45], [x1 - nose, b], [x0, b]];

// Both boats in one geometry, low-poly and drawn to scale (metres, bow +x, the waterline at y 0, the hull reaching a
// little below it): the layer draws each instance's own model and drops the other one's triangles in the vertex
// shader, so every boat is one draw call. The ferry: a hull, a deckhouse with a band of windows, a wheelhouse. The ship:
// a dark band along the waterline under a white hull, a long superstructure with two bands of windows, a funnel.
export function boatModels() {
  const out = { pos: [], part: [], model: [] };
  const P = { hull: 0, upper: 1, windows: 2, band: 3 };
  // the ferry, 30 m by 7.5 m
  prism(out, hullShape(30, 7.5), -1.2, 1.5, P.hull, 0);
  const cabin = house(-11, 7.5, 2.9, 2.5);
  prism(out, cabin, 1.5, 2.3, P.upper, 0, false);
  prism(out, cabin, 2.3, 3.3, P.windows, 0, false);
  prism(out, cabin, 3.3, 3.7, P.upper, 0);
  const bridge = house(0, 5, 1.9, 1.2);
  prism(out, bridge, 3.7, 4.4, P.windows, 0, false);
  prism(out, bridge, 4.4, 4.9, P.upper, 0);
  // the ship, 190 m by 29 m
  const hull = hullShape(190, 29, 0.18);
  prism(out, hull, -3, 5, P.band, 1, false);
  prism(out, hull, 5, 13, P.upper, 1);
  const sup = house(-88, 56, 13, 14);
  prism(out, sup, 13, 20, P.upper, 1, false);
  prism(out, sup, 20, 23, P.windows, 1, false);
  prism(out, sup, 23, 32, P.upper, 1);
  const top = house(-40, 50, 11, 10);
  prism(out, top, 32, 34.5, P.windows, 1, false);
  prism(out, top, 34.5, 36, P.upper, 1);
  prism(out, box(-72, -54, 5), 36, 44, P.hull, 1);
  return { position: Float32Array.from(out.pos), part: Float32Array.from(out.part), model: Float32Array.from(out.model) };
}

// The wake: a soft plume behind the stern, in unit lengths (x from 0 at the stern to -1 at the tail, z across from -0.5
// to 0.5 of its width at the tail, a third of that at the stern). t runs 0 to 1 along it and side -1 to 1 across,
// so the fragment shader can fade it towards the tail and its edges. The layer scales it to each kind's wake.
export function wakeModel(steps = 8) {
  const position = [], t = [], side = [], index = [];
  for (let i = 0; i <= steps; i++) {
    const k = i / steps, w = 0.5 * (0.35 + 0.65 * Math.sqrt(k));
    for (const s of [-1, 0, 1]) { position.push(-k, 0, s * w); t.push(k); side.push(s); }
    if (i) {
      const a = 3 * (i - 1), b = 3 * i;
      index.push(a, b, a + 1, a + 1, b, b + 1, a + 1, b + 1, a + 2, a + 2, b + 1, b + 2);
    }
  }
  return { position: Float32Array.from(position), t: Float32Array.from(t), side: Float32Array.from(side),
    index: Uint16Array.from(index) };
}
