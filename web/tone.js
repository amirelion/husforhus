// Colour helpers shared by the legend, the histogram and the card. Colours are sRGB hex, used as they are
// (app.js turns three.js colour management off), so these match the shader's arithmetic.
export const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
export const hex = c => '#' + c.map(v => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0')).join('');
export const luma = c => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
export const rgba = (h, a) => `rgba(${rgb(h).map(v => Math.round(v * 255)).join(',')},${a})`;

// Estimate style (area, estimate and period-only dates): ESTIMATE_MIX[0] towards the colour's own luminance, then
// ESTIMATE_MIX[1] towards `to`, the look's estimateTo (black in every look: darkening keeps an estimate apart from
// both its period colour and the pale range fade, which lightening did not in Ärg; web/test/themes.test.mjs). The
// vertex shader in app.js uses the same two numbers (web/test/tone.test.mjs checks them).
export const ESTIMATE_MIX = [0.4, 0.25];
export function estimateTone(h, to = '#000000') {
  const c = rgb(h), l = luma(c), t = rgb(to);
  return hex(c.map(v => v + (l - v) * ESTIMATE_MIX[0]).map((v, i) => v + (t[i] - v) * ESTIMATE_MIX[1]));
}

// The CSS background of a "Year unknown" chip: the look's flat colour, or on a hatched look (D29) the same fine
// diagonal hatch as the map, its lines a little wider than the map's (30% against 25%) so they read at 12 px. At -45deg
// they rise from bottom left to top right, as the map's stripes do from the home view (roofs at about 27 degrees,
// walls seen face on at 45). The card's band uses it too.
export const unknownFill = th => (th.unknownHatch
  ? `repeating-linear-gradient(-45deg, ${th.unknownHatch} 0 1.5px, ${th.unknown} 1.5px 5px)` : th.unknown);

// Black or white text, whichever has the higher WCAG contrast on the background (Plan 4a: the luma threshold put white
// on Classic's Funkis band at 3.92:1 and on Ärg's Stenstaden at 3.81:1, where black reads at 5.35 and 5.51).
const relLum = h => { const c = rgb(h).map(v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
export const inkOn = h => ((relLum(h) + 0.05) / 0.05 >= 1.05 / (relLum(h) + 0.05) ? '#000000' : '#ffffff');

// sRGB channel (0..1) to linear light.
export const lin = c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

// OKLab (Björn Ottosson, 2020) from linear sRGB: [L, a, b] with L in 0..1.
export function oklabLin([r, g, b]) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
}

// OKLab from sRGB hex. Used to check that neighbouring periods differ in lightness, not only in hue (spec §4.8).
export const oklab = h => oklabLin(rgb(h).map(lin));
