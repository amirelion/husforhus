// WGS84 <-> SWEREF 99 18 00 (EPSG:3011), Gauss-Krüger on GRS80 after Lantmäteriet's formulas (well under 1 mm here),
// and the map's local frame (metres from config.origin, x east, z south; pipeline/city.py to_local). Replaces
// upstream's Amsterdam-only RD approximation (fromLatLon/toLatLon). Pure, tested by node --test (web/test/sweref.test.mjs).
const A = 6378137, F = 1 / 298.257222101, LON0 = 18 * Math.PI / 180, K0 = 1, FE = 150000;
const E2 = F * (2 - F), N = F / (2 - F), AH = A / (1 + N) * (1 + N * N / 4 + N ** 4 / 64);
const B = [N / 2 - 2 * N * N / 3 + 5 * N ** 3 / 16 + 41 * N ** 4 / 180, 13 * N * N / 48 - 3 * N ** 3 / 5 + 557 * N ** 4 / 1440,
  61 * N ** 3 / 240 - 103 * N ** 4 / 140, 49561 * N ** 4 / 161280];
const D = [N / 2 - 2 * N * N / 3 + 37 * N ** 3 / 96 - N ** 4 / 360, N * N / 48 + N ** 3 / 15 - 437 * N ** 4 / 1440,
  17 * N ** 3 / 480 - 37 * N ** 4 / 840, 4397 * N ** 4 / 161280];

export function toSweref(lat, lon) {
  const p = lat * Math.PI / 180, dl = lon * Math.PI / 180 - LON0;
  const Ast = E2, Bst = (5 * E2 * E2 - E2 ** 3) / 6, Cst = (104 * E2 ** 3 - 45 * E2 ** 4) / 120, Dst = 1237 * E2 ** 4 / 1260;
  const s = Math.sin(p), ps = p - s * Math.cos(p) * (Ast + Bst * s * s + Cst * s ** 4 + Dst * s ** 6);
  const xi = Math.atan(Math.tan(ps) / Math.cos(dl)), eta = Math.atanh(Math.cos(ps) * Math.sin(dl));
  let x = xi, y = eta;
  B.forEach((b, i) => { const k = 2 * (i + 1); x += b * Math.sin(k * xi) * Math.cosh(k * eta); y += b * Math.cos(k * xi) * Math.sinh(k * eta); });
  return [FE + K0 * AH * y, K0 * AH * x];   // [easting, northing]
}

export function fromSweref(e, n) {
  const xi = n / (K0 * AH), eta = (e - FE) / (K0 * AH);
  let x = xi, y = eta;
  D.forEach((d, i) => { const k = 2 * (i + 1); x -= d * Math.sin(k * xi) * Math.cosh(k * eta); y -= d * Math.cos(k * xi) * Math.sinh(k * eta); });
  const ps = Math.asin(Math.sin(x) / Math.cosh(y)), dl = Math.atan(Math.sinh(y) / Math.cos(x));
  const As = E2 + E2 ** 2 + E2 ** 3 + E2 ** 4, Bs = -(7 * E2 ** 2 + 17 * E2 ** 3 + 30 * E2 ** 4) / 6,
    Cs = (224 * E2 ** 3 + 889 * E2 ** 4) / 120, Ds = -4279 * E2 ** 4 / 1260;
  const s = Math.sin(ps), c = Math.cos(ps);
  const p = ps + s * c * (As + Bs * s * s + Cs * s ** 4 + Ds * s ** 6);
  return [p * 180 / Math.PI, (LON0 + dl) * 180 / Math.PI];   // [lat, lon]
}

export const latLonToLocal = (lat, lon, origin) => { const [e, n] = toSweref(lat, lon); return [e - origin[0], -(n - origin[1])]; };
export const localToLatLon = (x, z, origin) => fromSweref(x + origin[0], origin[1] - z);
