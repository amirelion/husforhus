// The north button (index.html .north-open, app.js North): the map turns to face north, the short way round, in about
// half a second, and at once for a viewer who asks for less motion. North-up is azimuth 0 in the local frame (x east,
// z south): OrbitControls' theta is atan2(x, z) of the camera's offset from the target, so at 0 the camera stands
// south of the place and looks north. Only the azimuth changes; app.js keeps the place, the zoom and the tilt. Pure,
// so node --test can check it.
export const TURN_MS = 500;
const TAU = 2 * Math.PI;

// Into (-π, π]: both ends are one direction, and π stands for it. Never -0.
export const wrapAngle = a => (a - TAU * Math.ceil((a - Math.PI) / TAU)) || 0;

// The signed turn from `from` to `to` that is at most half a turn.
export const shortestTurn = (from, to = 0) => wrapAngle(to - from);

// A turn to north that starts at `now` (ms) from azimuth `from`. Already north, or calm (prefers-reduced-motion), it is
// over at once.
export function northTurn(from, now, { calm = false } = {}) {
  from = wrapAngle(from);
  const delta = shortestTurn(from);
  return { from, delta, t0: now, dur: calm || Math.abs(delta) < 1e-9 ? 0 : TURN_MS };
}

// The azimuth `turn` has at `now`, eased in and out like a flight (app.js stepFlight). The end is exactly 0. A frame
// stamped before the turn began (the render loop's time is the frame's start) is its start.
export function turnAt(turn, now) {
  const k = turn.dur > 0 ? Math.max(0, (now - turn.t0) / turn.dur) : 1;
  if (k >= 1) return { theta: 0, done: true };
  const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
  return { theta: turn.from + turn.delta * e, done: false };
}

// The needle's CSS rotation in degrees, clockwise: at azimuth π/2 the camera stands east of the place and looks west,
// so north is to the right of the screen. A tenth of a degree, so a still map writes no new style.
export const needleDeg = theta => Math.round(wrapAngle(theta) * 1800 / Math.PI) / 10 || 0;
