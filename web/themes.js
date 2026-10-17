// Looks: ?theme=arg|kalk|blatimme|paper, or the Look switcher (web/look.js, web/switcher.js). Ärg is the default
// (D28, web/look.js DEFAULT_LOOK): city.py's PERIODS colours and styles.css's :root tokens are its (contract C1).
// `name` is the look's name in the switcher; app.js's string table translates it where it needs translating.
// app.js applies the scene colours, label colours, font and period palette, and copies `ui` onto the CSS custom
// properties in styles.css. Every palette steps in lightness between neighbouring periods (OKLab ΔL ≥ 4); the
// three Stockholm looks also pass colour-vision and contrast checks (web/test/themes.test.mjs). Palettes come from
// the 2026-10-15 identity research (docs/roadmap.md, item 1). estimateTo is the colour estimates mix towards after
// losing saturation (web/tone.js estimateTone and the vertex shader): black in every look, so an estimate reads darker
// and duller than its period and never like the pale range fade. hoverTo is the hover mix: black on light grounds,
// white on the dark one. `unknown` is the colour of buildings with no year yet. A look with `unknownHatch` draws them with a fine
// diagonal hatch in that colour (D29): on the map (app.js FRAG), on the legend chip and a card's band (web/tone.js
// unknownFill). Terrain (Plan 3): land is the ground's colour where it is flat; reliefShade is how much the sun shades
// a slope (see SHADING; kept low where water is pale, so shaded land never nears the water's colour); quay is the
// colour of the walls where land meets water, stone wherever they stand over 3 m. `floors` is the
// Floors mode's ramp (Plan 4a): four colours from 1 floor to 40 and more on a log scale, for the shader and the legend
// alike; each stays clear of the look's land and sky, and they step in lightness, lighter to darker on a light ground
// and the reverse on the dark one (web/test/themes.test.mjs).
export const THEMES = {
  // Ärg (patina): building age read like copper roofs ageing. Verdigris for the old city, darkening through the
  // 19th century, then warm copper for the modern city; ink-dark Baltic water makes the islands read at a glance.
  // "Year unknown" is a pale warm neutral with a darker hatch (D29), so the city reads as a light model with the
  // dated buildings in colour. Pale alone it looks like p1/p2 to red- and green-blind viewers (ΔE 2.5–3.5; 2.0–4.6
  // for the hatch's mean tone, which far buildings take); the hatch line (ΔE 9.4 from it in every vision) tells it
  // apart, and shows from the home view on. It is ΔE 10.4 from land, 7.3 from the maquette.
  arg: {
    name: 'Ärg',
    sky: '#d9dfe3', land: '#e9e8e5', water: '#0e2433', maquette: '#dfdedb', unknown: '#c9c6c0', unknownHatch: '#aca8a1',
    quay: '#c6c4bf', reliefShade: 0.5,
    labelInk: '#3a464d', labelHalo: 'rgba(233,232,229,0.85)', waterInk: '#b9d3e0',
    estimateTo: '#000000', hoverTo: '#000000', font: 'Albert Sans',
    floors: ['#d6c6a8', '#c08a58', '#8d4d2b', '#4b2214'],
    ui: { '--bg': '#d9dfe3', '--ink': '#15232b', '--muted': '#56636b', '--panel': '#f6f6f4', '--line': '#c8cfd3', '--accent': '#1e625d' },
    periods: ['#8ed3d0', '#72c3c1', '#5ab2b3', '#47a0a5', '#3c8e97', '#387b88', '#3c6778', '#465262', '#87503d', '#aa6446', '#cf7b50', '#e49f75'],
  },
  // Kalkfärg (limewash): the pigments Stockholm put on its walls, in the order it used them (Cramér, Stadsmuseet):
  // earth colours until the 1910s, the first green houses in the 1920s, cooler modern colours after.
  kalk: {
    name: 'Kalkfärg',
    sky: '#dbe5e9', land: '#f0eae1', water: '#97afb9', maquette: '#eae4d9', unknown: '#caced3',
    quay: '#d6c7a1', reliefShade: 0.25,
    labelInk: '#4b443d', labelHalo: 'rgba(240,234,225,0.85)', waterInk: '#26404c',
    estimateTo: '#000000', hoverTo: '#000000', font: 'Familjen Grotesk',
    floors: ['#c3cfdb', '#7d97b0', '#3f5e7e', '#1b2a44'],
    ui: { '--bg': '#dbe5e9', '--ink': '#1f1a17', '--muted': '#5f5850', '--panel': '#faf7f2', '--line': '#ddd5c9', '--accent': '#33485c' },
    periods: ['#501912', '#7d241a', '#a14e2b', '#bc7d2f', '#d7bb74', '#d19936', '#669f72', '#3c8888', '#3b6d89', '#435177', '#4b355b', '#9d69c1'],
  },
  // Blå timmen (blue hour): a navy winter afternoon (21 December, 15:30). Warm for the old city, cold and pale for
  // the new, rising steadily in lightness; candle-amber accent.
  blatimme: {
    name: 'Blå timmen',
    sky: '#121d30', land: '#182233', water: '#1f3f61', maquette: '#283040', unknown: '#4c5666',
    quay: '#4c4a4b', reliefShade: 0.35,
    labelInk: '#c9d6e8', labelHalo: 'rgba(24,34,51,0.85)', waterInk: '#8fb4dc',
    estimateTo: '#000000', hoverTo: '#ffffff', font: 'Inter',
    floors: ['#46536f', '#7d8db0', '#bfc8df', '#fff1cf'],
    ui: { '--bg': '#121d30', '--ink': '#eef2f7', '--muted': '#9fb0c6', '--panel': '#1a2740', '--line': '#2b3a55', '--accent': '#ffc861' },
    periods: ['#861118', '#992502', '#a24203', '#ad5800', '#b86d02', '#c28209', '#c79916', '#c3b244', '#aacf79', '#8ae6c7', '#bfe8ff', '#f9f2d8'],
  },
  // Upstream's white model under a pale sky, for comparison; city.py's palette until Ärg became the default (D28;
  // its p11 #4a2b7a keeps the lightness step).
  paper: {
    name: 'Classic',
    sky: '#e4e8ea', land: '#f4f3ef', water: '#b5c7c6', maquette: '#efeee9', unknown: '#c3c6c8',
    quay: '#b4b2ac', reliefShade: 0.1,
    labelInk: '#50565b', labelHalo: 'rgba(244,243,239,0.85)', waterInk: '#3c6875',
    estimateTo: '#000000', hoverTo: '#000000', font: 'Schibsted Grotesk',
    floors: ['#c9d5db', '#7da8bf', '#2b5c8c', '#0d1a40'],
    ui: { '--bg': '#e4e8ea', '--ink': '#000000', '--muted': '#5d6266', '--panel': '#ffffff', '--line': '#cfd5d8', '--accent': '#1d5aa6' },
    periods: ['#4a1410', '#8c1c13', '#c0462b', '#d97a2b', '#e5b13a', '#b9a93a', '#8e9f3c', '#3f8f6b', '#2c7391', '#3a4f9a', '#4a2b7a', '#8f3f7a'],
  },
};

// How app.js TERRAIN_FRAG lights the ground and its walls: the shader interpolates these, and web/test/themes.test.mjs
// checks every look's land, quay and water with them, so a change here moves both. A slope is land × clamp(1 +
// reliefShade · (n·sun − sun.y), 1 − dark · reliefShade, 1 + light · reliefShade): flat ground is exactly land, a
// slope facing the sun up to `light` of reliefShade lighter, one facing away up to `dark` of it darker. A wall is quay
// × (wallMin + wallLit · max(n·sun, 0)), lit like the buildings' walls. sun: the one low afternoon sun from the
// south-west that the buildings and the ground share (app.js uSun, normalised there).
export const SHADING = { dark: 0.6, light: 0.3, wallMin: 0.66, wallLit: 0.34, sun: [-0.55, 0.55, 0.62] };
