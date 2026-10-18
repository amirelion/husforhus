// Walks: a route through the buildings with a story, for the interests, start and distance the walker picks.
// Ported from upstream's web/app.js (Walks, 7c41cfc and 6d64a76) and lifted out of it, so the planning is city-neutral and
// tested: a stop is { id, x, z, kinds: [interest ids], score, ... } in local metres. The stops are chosen greedily by
// score per metre added and ordered by 2-opt; distances are straight lines times DETOUR (no routing service: Google
// Maps, opened by the walker, gives the walking route). Pure, tested by node --test (web/test/walk.test.mjs).
export const DETOUR = 1.3, WALK_KMH = 4.5, STOP_MIN = 3, MAX_STOPS = 20, MIN_STOPS = 4, GOOGLE_LEG = 9;

const dist = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
const pathLen = pts => { let d = 0; for (let i = 1; i < pts.length; i++) d += dist(pts[i - 1], pts[i]); return d; };
// A stop counts once per chosen interest it carries; nothing chosen takes every stop.
export const stopScore = (p, chosen) => {
  const hit = (p.kinds || []).filter(k => !chosen.length || chosen.includes(k)).length;
  return hit ? (p.score ?? 1) + 0.5 * (hit - 1) : 0;
};

function planWithGap(stops, { kinds = [], km, loop, stops: asked }, start, gap) {
  const budget = km * 1000 / DETOUR;
  const S = { x: start[0], z: start[1], start: true };
  let cand = stops.map(p => ({ ...p, score: stopScore(p, kinds) }))
    .filter(p => p.score > 0 && dist(p, S) <= (loop ? budget / 2 : budget));
  // A closer stop merges into the higher scored one (one place with two entries is one stop).
  cand.sort((a, b) => b.score - a.score);
  cand = cand.filter((p, i) => !cand.slice(0, i).some(q => dist(p, q) < 25));
  const route = loop ? [S, S] : [S];
  // upstream allowed a one-way walk one stop more than asked (cap + 1); here the count is a cap either way
  const max = asked || MAX_STOPS;
  while (route.length - (loop ? 2 : 1) < max) {
    let best = null;
    const len = pathLen(route);
    for (const c of cand) {
      if (route.includes(c) || route.some(r => !r.start && dist(r, c) < gap)) continue;
      for (let i = 0; i < route.length; i++) {
        const next = route[i + 1];
        if (!next && loop) continue;
        const add = next ? dist(route[i], c) + dist(c, next) - dist(route[i], next) : dist(route[i], c);
        if (len + add > budget) continue;
        const ratio = c.score / (add + gap);
        if (!best || ratio > best.ratio) best = { c, i, ratio };
      }
    }
    if (!best) break;
    route.splice(best.i + 1, 0, best.c);
  }
  for (let improved = true; improved;) {    // 2-opt over the stops between the fixed ends
    improved = false;
    const last = loop ? route.length - 2 : route.length - 1;
    for (let i = 1; i < last; i++) for (let j = i + 1; j <= last; j++) {
      const a = route[i - 1], b = route[i], c = route[j], d = route[j + 1];
      const before = dist(a, b) + (d ? dist(c, d) : 0), after = dist(a, c) + (d ? dist(b, d) : 0);
      if (after < before - 1) { route.splice(i, j - i + 1, ...route.slice(i, j + 1).reverse()); improved = true; }
    }
  }
  return { start: S, stops: route.filter(p => !p.start), loop, route, length: pathLen(route) * DETOUR };
}

// The widest spacing that loses no stop: a long walk goes somewhere instead of circling one square.
function planAtLength(stops, prefs, start) {
  const wide = Math.min(400, Math.max(30, prefs.km * 1000 / DETOUR / ((prefs.stops || MAX_STOPS) * 2.2)));
  const plans = [wide, wide / 2, wide / 4, 25].map(g => planWithGap(stops, prefs, start, g));
  const most = Math.max(...plans.map(p => p.stops.length));
  return plans.find(p => p.stops.length >= most);
}

// A walk with one or two stops is not a walk: the distance grows (up to four times) until there are a few, and the
// plan says so (stretched).
export function planWalk(stops, prefs, start) {
  const available = stops.filter(p => stopScore(p, prefs.kinds || []) > 0).length;
  const want = Math.min(prefs.stops || MIN_STOPS, available);
  let w = planAtLength(stops, prefs, start);
  for (let k = 1.25; w.stops.length < want && k <= 4.01; k += 0.25) {
    w = { ...planAtLength(stops, { ...prefs, km: prefs.km * k }, start), stretched: true };
  }
  return w;
}

export const walkMinutes = w => Math.round(w.length / 1000 / WALK_KMH * 60 + w.stops.length * STOP_MIN);

// One Google Maps directions link (it takes at most GOOGLE_LEG waypoints: a longer walk sends the best ones, in walking
// order). latLon(p) gives [lat, lon]. Opening it is the walker's choice; nothing is sent before.
export function walkMapsUrl(w, latLon) {
  const ll = p => latLon(p).map(v => v.toFixed(6)).join(',');
  let stops = w.stops;
  const max = w.loop ? GOOGLE_LEG : GOOGLE_LEG + 1;
  if (stops.length > max) {
    const keep = new Set([...stops].sort((a, b) => b.score - a.score).slice(0, max));
    stops = stops.filter(p => keep.has(p));
  }
  const dest = w.loop ? w.start : stops[stops.length - 1];
  const via = w.loop ? stops : stops.slice(0, -1);
  const u = new URL('https://www.google.com/maps/dir/');
  u.searchParams.set('api', '1');
  u.searchParams.set('origin', ll(w.start));
  u.searchParams.set('destination', ll(dest || w.start));
  if (via.length) u.searchParams.set('waypoints', via.map(ll).join('|'));
  u.searchParams.set('travelmode', 'walking');
  return u.toString();
}
