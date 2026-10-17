// Binary formats shared with the pipeline. No three.js here, so node --test can import it.

export const MAGIC = 0x31484648; // 'HFH1', little-endian

// Tile v1 (pipeline/s03_tiles.py pack_tile). Every array starts on a 4-byte boundary.
// header  u32 magic, nB, nP, nR, nV; f32 originX, originZ
// B       u32 gid[nB]; i16 year[nB]; u8 yflag[nB]; u8 period[nB]; u8 floors[nB]; i16 ground[nB] (dm);
//         u32 lay0[nB]; u32 lay1[nB]; u32 partStart[nB+1]
// P       f32 height[nP]; u32 ringStart[nP+1]
// R       u32 vertStart[nR+1]; u8 hole[nR]
// V       i16 xz[2*nV], decimetres from the tile origin
export function parse(buf) {
  const h = new DataView(buf);
  const magic = h.getUint32(0, true);
  if (magic !== MAGIC) throw new Error(`not a v1 tile (magic 0x${magic.toString(16)})`);
  const nB = h.getUint32(4, true), nP = h.getUint32(8, true), nR = h.getUint32(12, true), nV = h.getUint32(16, true);
  const origin = [h.getFloat32(20, true), h.getFloat32(24, true)];
  let o = 28;
  const take = (Type, n) => { const a = new Type(buf, o, n); o += Math.ceil(n * Type.BYTES_PER_ELEMENT / 4) * 4; return a; };
  const t = {
    nB, nP, nR, nV, origin,
    gid: take(Uint32Array, nB), year: take(Int16Array, nB), yflag: take(Uint8Array, nB),
    period: take(Uint8Array, nB), floors: take(Uint8Array, nB), ground: take(Int16Array, nB),
    lay0: take(Uint32Array, nB), lay1: take(Uint32Array, nB), partStart: take(Uint32Array, nB + 1),
    height: take(Float32Array, nP), ringStart: take(Uint32Array, nP + 1),
    vertStart: take(Uint32Array, nR + 1), hole: take(Uint8Array, nR), xz: take(Int16Array, 2 * nV),
  };
  if (o !== buf.byteLength) throw new Error(`tile is ${buf.byteLength} bytes, layout says ${o}`);
  return t;
}

// The per-building lookup texture web/worker.js builds from a tile and app.js's vertex shader reads: floats per
// building, three RGBA texels: [year, period + 16*yflag, floors, global id], [layer bits in four 16-bit words],
// [ground (decimetres, RH 2000), 0, 0, 0].
export const ATTR_FLOATS = 12;

// attrs.bin: one fixed 24-byte record per gid.
// u16 h_dm, u8 fsrc, u8 yflag, i16 year, i16 year_from, i16 year_to, u8 ysrc, u8 rating, f32 x, f32 z,
// u8 floors, u8 period, u8 private, u8 pad
export const ATTR_STRIDE = 24;
export function readAttrs(view, gid, stride = ATTR_STRIDE) {
  const o = gid * stride;
  return {
    gid,
    height: view.getUint16(o, true) / 10,
    fsrc: view.getUint8(o + 2),
    yflag: view.getUint8(o + 3),
    year: view.getInt16(o + 4, true),
    yearFrom: view.getInt16(o + 6, true),
    yearTo: view.getInt16(o + 8, true),
    ysrc: view.getUint8(o + 10),
    rating: view.getUint8(o + 11),
    x: view.getFloat32(o + 12, true),
    z: view.getFloat32(o + 16, true),
    floors: view.getUint8(o + 20),
    period: view.getUint8(o + 21),
    private: view.getUint8(o + 22),   // 1 for a private house: only its decade is published
  };
}
