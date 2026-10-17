// The relief (Plan 3) and its Hills slider (decided 2026-10-16, D40): how high the ground is drawn, from 0 (flat) to
// the build's maximum (stockholm.json terrain.reliefMax, 2.5), 1 being the true heights and the default
// (terrain.relief). Pure, so it can be tested without a browser; app.js eases uRelief towards it and the Look panel
// (web/switcher.js) shows the slider with its value and its honesty line.
//
// ?relief= wins (a shared link shows what its sender saw), then the visitor's remembered value (localStorage
// hfh-relief, the number, written only when they move the slider, which also takes ?relief= out of the address, so
// a reload keeps the move), then the city's default. ?relief=off is flat, ?relief=on the default and a number that
// value, snapped to the slider's step (so its thumb, its value, its line and the map agree: ?relief=0.2 is flat) and
// clamped to 0..the maximum. The switch before the slider stored 'off' and 'on': they read as 0 and the default.
export const RELIEF_KEY = 'hfh-relief';
export const RELIEF_STEP = 0.5;
export const RELIEF_MAX = 2.5;   // when a build's config names no maximum (city.TERRAIN relief_max is the source)

const clamp = (x, max) => Math.min(max, Math.max(0, x));
const snap = x => Math.round(x / RELIEF_STEP) * RELIEF_STEP;
// One setting, from the address or the store: a relief, or null when it says nothing usable.
function parse(v, def, max) {
  if (v === 'off') return 0;
  if (v === 'on') return clamp(def, max);
  const x = typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN;
  return Number.isFinite(x) ? clamp(snap(x), max) : null;
}
export function initialRelief(search, stored, def, max = RELIEF_MAX) {
  return parse(new URLSearchParams(search).get('relief'), def, max) ?? parse(stored, def, max) ?? clamp(def, max);
}

// What the slider shows, and the line under it, round the relief to a tenth (a link may ask for 1.23). Swedish writes
// the decimal comma.
const tenth = scale => Math.round(scale * 10) / 10;
const num = (k, lang) => (lang === 'sv' ? String(k).replace('.', ',') : String(k));

// The slider's visible value: "Flat" at 0, else the factor ("1×", "1.5×").
export function reliefValue(scale, lang = 'en') {
  const k = tenth(scale);
  return k === 0 ? (lang === 'sv' ? 'Platt' : 'Flat') : `${num(k, lang)}×`;
}

// The line under the slider says what the map shows now (D1: every claim honest): drawn flat at 0, true to scale at
// 1, the heights reduced under 1 and exaggerated over it, or not loaded at all (state 'failed', app.js terrainState;
// the slider is then disabled). While the terrain is on its way ('flat' until it is asked for, then 'loading') the
// map is flat whatever the slider says, so the line says the ground is loading (the final review's VIEWER-3; the
// Ground row exists only in a build with terrain, so 'flat' there always means not loaded yet).
const NOTES = {
  en: { failed: "The ground's heights did not load", loading: 'Loading the ground…', flat: 'Ground drawn flat',
    true: 'Ground heights true to scale', reduced: n => `Ground heights reduced to ${n}×`,
    scaled: n => `Ground heights exaggerated ${n}×` },
  sv: { failed: 'Markhöjderna kunde inte laddas', loading: 'Laddar marken…', flat: 'Marken visas platt',
    true: 'Markhöjder i verklig skala', reduced: n => `Markhöjder i skala ${n}`, scaled: n => `Markhöjder överdrivna ${n} gånger` },
};
export function reliefNote(scale, lang = 'en', state = 'ready') {
  const s = NOTES[lang] || NOTES.en, k = tenth(scale), n = num(k, NOTES[lang] ? lang : 'en');
  if (state === 'failed') return s.failed;
  if (state === 'flat' || state === 'loading') return s.loading;
  if (k === 0) return s.flat;
  if (k === 1) return s.true;
  return k < 1 ? s.reduced(n) : s.scaled(n);
}

// From a to b as t goes from 0 to 1, eased in and out (smoothstep); t is clamped.
export function ease(a, b, t) {
  const k = Math.min(1, Math.max(0, t));
  return a + (b - a) * k * k * (3 - 2 * k);
}
