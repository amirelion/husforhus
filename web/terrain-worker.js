// Builds the terrain's meshes off the main thread: terrain.bin and water.bin in, typed arrays out, which
// app.js wraps in three.js geometries. One message in ({terrain, water, chunkCells, fadeM}), one out. The shore cells
// and the quay walls come in groups of two by two chunks, each with its own index range, box and height bounds (hMax,
// hMin: see web/terrain.js), so they cull; each chunk carries the same bounds.
import { ShapeUtils, Vector2 } from './vendor/three.core.js';
import {
  chunkIndices, chunkVertices, edgeMesh, fadeField, heightTexture, parsePolygons, parseTerrain, wallMesh, waterMesh,
} from './terrain.js';

const triangulate = (contour, holes) => ShapeUtils.triangulateShape(contour.map(p => new Vector2(p.x, p.y)),
  holes.map(h => h.map(p => new Vector2(p.x, p.y))));

// Exported for web/test/terrain.test.mjs; the page only talks to the worker through messages. The terrain file must
// be the one made for this water: a level per polygon and a shore bit per vertex.
export function buildTerrain(terrain, water, { chunkCells, fadeM }) {
  const T = parseTerrain(terrain);
  const polys = parsePolygons(water);
  if (polys.length !== T.levels.length) throw new Error(`${T.levels.length} water levels for ${polys.length} water polygons`);
  const nVert = polys.reduce((n, poly) => n + poly.reduce((m, ring) => m + ring.length, 0), 0);
  if (nVert !== T.nShore) throw new Error(`${T.nShore} shore bits for ${nVert} water vertices`);
  const verts = chunkVertices(T, chunkCells);   // first: it refuses a chunk size the meshes cannot index
  const groupCells = 2 * chunkCells;
  return {
    grid: { x0: T.x0, z0: T.z0, cell: T.cell, nx: T.nx, nz: T.nz, waterZ: T.waterZ }, source: T.source,
    levels: T.levels, tex: heightTexture(T), fade: fadeField(T, fadeM),
    verts, chunks: chunkIndices(T, chunkCells),
    edge: edgeMesh(T, triangulate, groupCells), water: waterMesh(polys, T.levels, triangulate),
    walls: wallMesh(polys, T.levels, T.shore, T, groupCells),
  };
}

export const transferables = m => [m.levels.buffer, m.tex.buffer, m.fade.buffer, m.verts.buffer,
  m.edge.xz.buffer, m.edge.idx.buffer, m.water.xz.buffer, m.water.idx.buffer, m.water.level.buffer,
  m.walls.xz.buffer, m.walls.top.buffer, m.walls.level.buffer, m.walls.idx.buffer,
  ...m.chunks.flatMap(c => [c.lod0.buffer, c.lod1.buffer])];

self.onmessage = ({ data }) => {
  try {
    const m = buildTerrain(data.terrain, data.water, data);
    self.postMessage({ ok: true, ...m }, transferables(m));
  } catch (e) {
    self.postMessage({ ok: false, error: String(e?.message || e) });
  }
};
