// A tile's culling bounds once its buildings stand on the terrain. The vertex shader (app.js VERT) lifts each
// building by its ground times the relief and hangs its walls' skirts below it, so three.js's own bounds, taken from
// the unlifted positions, would let a tile on a hill be culled at the screen's edge and missed by the 1 x 1 pick
// frustum. web/test/bounds.test.mjs lifts a fixture tile's vertices as the shader does and checks they stay inside.
import { Sphere } from './vendor/three.core.js';

// How far the box reaches under the tile's lowest lifted ground, in decimetres: a skirt ends 2 m under the terrain at
// its corner and half the cell's range further down (VERT), so 60 m holds a corner 30 m down a drawn slope (sized for
// the old 3x top; the Hills slider's top is now 2.5x, decided 2026-10-16).
export const SKIRT_DM = 600;

// geometry: the tile's BufferGeometry (decimetres, the mesh's own units); m: web/worker.js build's gMin, gMax and top
// (decimetres); terrain: config.terrain, whose reliefMax is the most relief the viewer offers (undefined: flat).
export function liftBounds(geometry, m, terrain) {
  const R = terrain?.reliefMax ?? 0;
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  box.min.y = Math.min(0, m.gMin * R) - SKIRT_DM;
  box.max.y = Math.max(0, m.gMax * R) + m.top;
  geometry.boundingSphere = box.getBoundingSphere(new Sphere());
  return geometry;
}
