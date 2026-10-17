// Turns one binary tile into an extruded mesh. Positions stay in decimetres from the tile origin.
import { ShapeUtils, Vector2 } from './vendor/three.core.js';
import { parse, ATTR_FLOATS } from './tile.js';

// Exported for web/test/worker.test.mjs; the page only talks to the worker through messages.
export function build(t) {
  let nVert = 0, nIdx = 0;
  for (let r = 0; r < t.hole.length; r++) {
    const n = t.vertStart[r + 1] - t.vertStart[r];
    // Walls: 4 vertices and 6 indices per edge. Roof: n vertices and one triangle per vertex, plus 2h - 2 for a
    // ring with h holes, so 3n indices plus 6 per ring always suffice.
    nVert += n * 5; nIdx += n * 9 + 6;
  }
  const pos = new Int16Array(nVert * 3), bld = new Uint16Array(nVert), idx = new Uint32Array(nIdx);
  let v = 0, k = 0;
  for (let b = 0; b < t.nB; b++) {
    for (let p = t.partStart[b]; p < t.partStart[b + 1]; p++) {
      const roof = Math.round(t.height[p] * 10);   // decimetres
      const r0 = t.ringStart[p], r1 = t.ringStart[p + 1];
      const shapes = []; // one roof per exterior ring: a MultiPolygon part has several (contract C4)
      // Walls
      for (let r = r0; r < r1; r++) {
        const s = t.vertStart[r], e = t.vertStart[r + 1], n = e - s;
        const ring = [];
        for (let i = 0; i < n; i++) {
          const a = s + i, c = s + ((i + 1) % n);
          const ax = t.xz[2 * a], az = t.xz[2 * a + 1], cx = t.xz[2 * c], cz = t.xz[2 * c + 1];
          pos.set([ax, 0, az, cx, 0, cz, cx, roof, cz, ax, roof, az], v * 3);
          bld.fill(b, v, v + 4);
          idx.set([v, v + 1, v + 2, v, v + 2, v + 3], k);
          v += 4; k += 6;
          ring.push(new Vector2(ax, az));
        }
        if (!t.hole[r]) shapes.push({ contour: ring, holes: [] });
        else if (shapes.length) shapes[shapes.length - 1].holes.push(ring);
      }
      // Roofs
      for (const { contour, holes } of shapes) {
        const roofStart = v;
        for (const pt of contour.concat(...holes)) { pos.set([pt.x, roof, pt.y], v * 3); bld[v] = b; v++; }
        for (const tri of ShapeUtils.triangulateShape(contour, holes)) {
          idx.set([roofStart + tri[0], roofStart + tri[1], roofStart + tri[2]], k); k += 3;
        }
      }
    }
  }
  // Per-building lookup, ATTR_FLOATS each (web/tile.js): the vertex shader lifts the building by ground * uRelief.
  const attr = new Float32Array(t.nB * ATTR_FLOATS);
  let gMin = Infinity, gMax = -Infinity, top = 0;
  for (let b = 0; b < t.nB; b++) {
    attr.set([t.year[b], t.period[b] + 16 * t.yflag[b], t.floors[b], t.gid[b],
      t.lay0[b] & 0xffff, t.lay0[b] >>> 16, t.lay1[b] & 0xffff, t.lay1[b] >>> 16, t.ground[b], 0, 0, 0], b * ATTR_FLOATS);
    gMin = Math.min(gMin, t.ground[b]); gMax = Math.max(gMax, t.ground[b]);
  }
  for (let p = 0; p < t.height.length; p++) top = Math.max(top, Math.round(t.height[p] * 10));
  // gMin, gMax and top (decimetres) give app.js the tile's culling box (web/bounds.js); 0 for an empty tile.
  return { pos: pos.subarray(0, v * 3), bld: bld.subarray(0, v), idx: idx.subarray(0, k), attr, origin: t.origin, nB: t.nB,
    gMin: t.nB ? gMin : 0, gMax: t.nB ? gMax : 0, top };
}

self.onmessage = ({ data: { buf, id } }) => {
  const m = build(parse(buf));
  self.postMessage({ id, ...m }, [m.pos.buffer, m.bld.buffer, m.idx.buffer, m.attr.buffer]);
};
