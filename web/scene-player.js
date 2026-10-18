// The history-scene player (prototypes/scene-player/, built into the viewer). A scene (web/scenes/<id>.json, from
// scripts/scenes/build.mjs) is a list of beats: each beat sets a camera and a target in lat/lon, a duration and a
// caption in EN and SV. Playing a scene sets the timeline to the scene's year (app.js's own setHandle, so later
// buildings go exactly as they do on the timeline), flies the camera beat by beat, and draws the scene's overlays:
// a route as a line on the ground or water, with a marker moving along it during the beats that follow it, and
// markers as labelled points. Exit (or Esc) puts the camera, the years and the panels back as they were.
// Opened from the Stories button (next to Look) or with ?scene=<id>.
// Everything that needs the map comes in through mountScenePlayer's options; the top of this file is pure, so
// web/test/scene-player.test.mjs runs it under node.

export const DEFAULT_BEAT_S = 8;   // a beat without duration_s (the prototype's default)
export const PREV_RESTART_S = 1.5; // Previous restarts the beat after this much of it, else goes a beat back
const ON_ROUTE_M = 80;             // a beat whose target is this close to a route moves its marker
// The story's lost buildings (ghosts.csv): one warm sandstone on every look, roofs lighter than walls, dark edges.
export const GHOST = { roof: '#e0b27a', wall: '#b9844e', edge: '#5a3a1c' };
// Is a ghost (from/until, 1-based beats) up at beat i (0-based)?
export const ghostShown = (o, i) => i + 1 >= o.from && (o.until == null || i + 1 <= o.until);
// The Vasa's hull in its own frame, metres: bow towards +x, beam across z.
export function hullOutline(L = 69, B = 12) {
  const h = L / 2, b = B / 2;
  return [[-h, -b * 0.8], [-h + 4, -b], [h - 14, -b], [h - 4, -b * 0.45], [h, 0], [h - 4, b * 0.45], [h - 14, b], [-h + 4, b], [-h, b * 0.8]];
}

// ---------- Timing ----------
export const beatDuration = b => (Number.isFinite(b?.duration_s) && b.duration_s > 0 ? b.duration_s : DEFAULT_BEAT_S);
// Each beat's duration and start, and the scene's length, in seconds.
export function timing(beats) {
  const durations = beats.map(beatDuration), offsets = [];
  let t = 0;
  for (const d of durations) { offsets.push(t); t += d; }
  return { durations, offsets, total: t };
}
export const playedS = (tm, beat, elapsed) => tm.offsets[beat] + Math.min(Math.max(0, elapsed), tm.durations[beat]);
export const remainingS = (tm, beat, elapsed) => Math.max(0, tm.total - playedS(tm, beat, elapsed));
export const fmtClock = s => { const c = Math.max(0, Math.ceil(s)); return `${Math.floor(c / 60)}:${String(c % 60).padStart(2, '0')}`; };
export const prevBeat = (beat, elapsed) => (elapsed > PREV_RESTART_S ? beat : Math.max(0, beat - 1));
export const clampBeat = (i, n) => Math.max(0, Math.min(n - 1, i));
// The camera's flight into a beat: half the beat, at most 3 s, eased in and out.
export const flightS = d => Math.min(3, d * 0.5);
export const ease = k => (k <= 0 ? 0 : k >= 1 ? 1 : k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2);

// ---------- Coordinates ----------
// WGS84 lat/lon to SWEREF 99 18 00 (EPSG:3011, config.crs), Gauss-Krüger as Lantmäteriet gives it: GRS80, central
// meridian 18°, scale 1, false easting 150 000 m. Returns [easting, northing] in metres.
const GRS80_A = 6378137, GRS80_F = 1 / 298.257222101;
export function toSweref1800(lat, lon) {
  const f = GRS80_F, e2 = f * (2 - f), n = f / (2 - f);
  const aRoof = GRS80_A / (1 + n) * (1 + n * n / 4 + n ** 4 / 64);
  const A = e2, B = (5 * e2 ** 2 - e2 ** 3) / 6, C = (104 * e2 ** 3 - 45 * e2 ** 4) / 120, D = 1237 * e2 ** 4 / 1260;
  const beta = [n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16 + 41 * n ** 4 / 180, 13 * n ** 2 / 48 - 3 * n ** 3 / 5 + 557 * n ** 4 / 1440,
    61 * n ** 3 / 240 - 103 * n ** 4 / 140, 49561 * n ** 4 / 161280];
  const rad = Math.PI / 180, phi = lat * rad, dl = (lon - 18) * rad, s = Math.sin(phi) ** 2;
  const phiS = phi - Math.sin(phi) * Math.cos(phi) * (A + B * s + C * s * s + D * s ** 3);
  const xi = Math.atan(Math.tan(phiS) / Math.cos(dl)), eta = Math.atanh(Math.cos(phiS) * Math.sin(dl));
  let N = xi, E = eta;
  beta.forEach((b, i) => {
    const k = 2 * (i + 1);
    N += b * Math.sin(k * xi) * Math.cosh(k * eta);
    E += b * Math.cos(k * xi) * Math.sinh(k * eta);
  });
  return [150000 + aRoof * E, aRoof * N];
}
// The viewer's local frame (pipeline/city.py to_local): x east of config.origin, z south of it.
export function toLocal(lat, lon, origin) {
  const [e, n] = toSweref1800(lat, lon);
  return [e - origin[0], -(n - origin[1])];
}

// ---------- Routes ----------
// A polyline in local [x, z]: its length along each vertex, and the nearest point on it to p as { s, d }.
export function polyline(pts) {
  const at = [0];
  for (let i = 1; i < pts.length; i++) at.push(at[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return { pts, at, length: at[at.length - 1] };
}
export function nearestOn(line, p) {
  let best = { s: 0, d: Infinity };
  for (let i = 1; i < line.pts.length; i++) {
    const [ax, az] = line.pts[i - 1], [bx, bz] = line.pts[i], dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz;
    const k = L2 ? Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - az) * dz) / L2)) : 0;
    const d = Math.hypot(p[0] - (ax + k * dx), p[1] - (az + k * dz));
    if (d < best.d) best = { s: line.at[i - 1] + k * Math.sqrt(L2), d };
  }
  return best;
}
export function pointAt(line, s) {
  const { pts, at } = line;
  if (pts.length === 1 || s <= 0) return pts[0];
  for (let i = 1; i < pts.length; i++) {
    if (s <= at[i]) {
      const k = (s - at[i - 1]) / ((at[i] - at[i - 1]) || 1);
      return [pts[i - 1][0] + k * (pts[i][0] - pts[i - 1][0]), pts[i - 1][1] + k * (pts[i][1] - pts[i - 1][1])];
    }
  }
  return pts[pts.length - 1];
}
// For each beat, where the route's marker runs during it: { from, to } in metres along the route, or null for a
// beat whose target is off the route. A beat runs from where the last beat on the route ended (its own point for
// the first) to its own target, so the marker never jumps backwards.
export function routeLegs(line, targets, near = ON_ROUTE_M) {
  let last = null;
  return targets.map(t => {
    const p = nearestOn(line, t);
    if (p.d > near) return null;
    const from = last == null ? p.s : last;
    last = Math.max(from, p.s);
    return { from, to: last };
  });
}

// ---------- The player ----------
const STR = {
  en: { stories: 'Stories', exit: 'Exit', exitScene: 'Exit scene', play: 'Play', pause: 'Pause', prev: 'Previous beat',
    next: 'Next beat', beat: n => `Beat ${n}`, left: s => `${s} remaining`, source: 'Source', player: 'Scene player',
    captionLang: 'Caption language', beats: n => `${n} beats`, cont: 'Continue', skip: 'Skip',
    warn: 'This story tells of people who died. It shows only places, dates and short captions.',
    faint: "Faint: today's city, for orientation", min: m => `${m} min`, sensitive: 'Mentions deaths',
    done: 'Story complete', replay: 'Replay story', toMap: 'Back to map' },
  sv: { stories: 'Berättelser', exit: 'Avsluta', exitScene: 'Avsluta scenen', play: 'Spela', pause: 'Pausa',
    prev: 'Föregående', next: 'Nästa', beat: n => `Del ${n}`, left: s => `${s} kvar`, source: 'Källa',
    player: 'Scenspelare', captionLang: 'Språk för texten', beats: n => `${n} delar`, cont: 'Fortsätt', skip: 'Hoppa över',
    warn: 'Berättelsen handlar om människor som dog. Den visar bara platser, datum och korta texter.',
    faint: 'Svagt: dagens stad, för orientering', min: m => `${m} min`, sensitive: 'Nämner dödsfall',
    done: 'Berättelsen är slut', replay: 'Spela igen', toMap: 'Tillbaka till kartan' },
};
// "Photo: <author>, <licence>, Wikimedia Commons" (Foto in Swedish).
// The timeline's year in beat i: the beat's own year (beats.csv timeline_year), else the scene's.
export const beatYear = (scene, i) => scene.beats[i]?.year ?? scene.year;
// The map layers a story shows whatever the legend says (scene.layers, e.g. ["metro"]); only the known ones.
export const STORY_LAYERS = ['metro'];
export const sceneLayers = scene => (scene?.layers || []).filter(l => STORY_LAYERS.includes(l));
export const photoCredit = (c, lang) => `${lang === 'sv' ? 'Foto' : 'Photo'}: ${c.author}, ${c.licence}, Wikimedia Commons`;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// opts: THREE, scene, camera, controls, origin (config.origin), surfaceAt(x, z), calm (the reduced-motion query),
// lang() (the page's language), setLang(l) or null when the switch is off, year: { save(), set(y), restore(saved) },
// layers(list) (the map layers to force on during a story, [] at exit), stopFlight(), button (the Stories button), base (the scenes' folder, default 'scenes/').
// The scene asked for by ?scene=<id>, or null; never while the city config keeps scenes off (features.scenes).
export function askedScene(enabled, search) {
  return enabled ? new URLSearchParams(search).get('scene') || null : null;
}

export function mountScenePlayer(opts) {
  const { THREE, camera, controls, origin, surfaceAt, calm, button } = opts;
  const base = opts.base || 'scenes/';
  const S = () => STR[opts.lang() === 'sv' ? 'sv' : 'en'];
  const L = o => (o && (o[opts.lang()] || o.en)) || '';
  const ackSensitive = new Set();   // "Continue" on the warning, remembered until the page reloads (as the prototype)

  // The Stories list, below its button.
  const list = document.createElement('div');
  list.id = 'stories';
  list.className = 'sp-stories';
  list.hidden = true;
  list.innerHTML = '<ul></ul>';
  button.after(list);
  button.setAttribute('aria-controls', 'stories');
  button.setAttribute('aria-expanded', 'false');

  // The warning and the cinema overlay.
  const root = document.createElement('div');
  root.className = 'sp';
  root.innerHTML = `
<section class="sp-warning" role="dialog" aria-modal="true" aria-labelledby="sp-warn-title" hidden>
  <div class="sp-warn-card"><h2 id="sp-warn-title"></h2><p class="sp-warn-text"></p>
    <div class="sp-row"><button class="sp-pill sp-dark sp-warn-skip"></button><button class="sp-pill sp-warn-go"></button></div></div>
</section>
<section class="sp-cinema" hidden>
  <div class="sp-top">
    <button class="sp-pill sp-exit"></button>
    <div class="sp-lang" role="group" hidden><button data-lang="en">EN</button><button data-lang="sv">SV</button></div>
  </div>
  <div class="sp-year" aria-live="polite"></div>
  <div class="sp-bottom">
    <div class="sp-beat">
      <div class="sp-text">
        <p class="sp-caption" aria-live="polite"></p>
        <p class="sp-source"></p>
      </div>
      <figure class="sp-photo" hidden>
        <img alt="" decoding="async">
        <figcaption><span class="sp-photo-cap"></span> <a class="sp-photo-credit" target="_blank" rel="noopener"></a></figcaption>
      </figure>
    </div>
    <div class="sp-progress"><div class="sp-fill"></div></div>
    <div class="sp-controls">
      <button class="sp-prev">⏮&#xFE0E;</button>
      <button class="sp-play"></button>
      <button class="sp-next">⏭&#xFE0E;</button>
      <span class="sp-count"></span>
    </div>
    <p class="sp-legend"></p>
    <div class="sp-end" hidden><strong class="sp-end-title"></strong>
      <button class="sp-pill sp-dark sp-replay"></button><button class="sp-pill sp-tomap"></button></div>
  </div>
</section>
<div class="sp-pins" aria-hidden="true"></div>`;
  document.body.append(root);
  const $ = c => root.querySelector(c);
  const cinema = $('.sp-cinema'), warning = $('.sp-warning'), pins = $('.sp-pins');
  const capEl = $('.sp-caption'), progEl = $('.sp-progress'), playEl = $('.sp-play'), langEl = $('.sp-lang');

  let index = null;
  const loadIndex = () => (index ??= fetch(`${base}index.json`).then(r => r.json()).then(j => j.scenes || []));
  const reduced = () => calm.matches;

  // state: the scene, its timing and overlays; saved: the map as it was before the scene
  let st = null, saved = null, raf = 0, returnFocus = null;

  // ---------- Stories list ----------
  // Each card's details come from the scene file itself (cached): its first caption as a lead-in, its length, its warning.
  const details = new Map();
  const loadDetails = id => details.get(id) || details.set(id, fetch(`${base}${encodeURIComponent(id)}.json`)
    .then(r => r.json()).catch(() => null)).get(id);
  // The titles and years show at once; each card's lead-in, length and warning follow when its file has loaded.
  async function renderList() {
    const scenes = (await loadIndex()).filter(s => s.ready), s = S(), ul = list.querySelector('ul');
    const card = (x, d) => {
      const meta = [x.year];
      if (d?.beats?.length) meta.push(s.min(Math.max(1, Math.round(timing(d.beats).total / 60))), s.beats(d.beats.length));
      const lead = d?.beats?.[0] ? L(d.beats[0].caption) : '';
      return `<li><button data-id="${esc(x.id)}"><span class="sp-card-title">${esc(L(x.title))}</span>
      ${lead ? `<span class="sp-card-lead">${esc(lead)}</span>` : ''}
      <span class="sp-yr">${meta.map(esc).join(' · ')}</span>
      ${d?.sensitive ? `<span class="sp-card-warn" title="${esc(s.warn)}">⚠&#xFE0E; ${esc(s.sensitive)}</span>` : ''}</button></li>`;
    };
    const draw = all => {
      const focused = list.contains(document.activeElement) && document.activeElement.dataset.id;
      ul.innerHTML = scenes.map((x, i) => card(x, all[i])).join('');
      if (focused) ul.querySelector(`[data-id="${CSS.escape(focused)}"]`)?.focus();
    };
    draw([]);
    draw(await Promise.all(scenes.map(x => loadDetails(x.id))));
  }
  function showList(on) {
    list.hidden = !on;
    button.setAttribute('aria-expanded', String(on));
    if (on) renderList().then(() => list.querySelector('button')?.focus()).catch(e => console.warn('No stories', e));
  }
  button.textContent = S().stories;
  button.onclick = () => showList(list.hidden);
  list.onclick = e => { const b = e.target.closest('button[data-id]'); if (b) { showList(false); ackSensitive.add(b.dataset.id); open(b.dataset.id, button); } };
  list.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); showList(false); button.focus(); } });
  document.addEventListener('pointerdown', e => { if (!list.hidden && !list.contains(e.target) && e.target !== button) showList(false); });

  // ---------- Open, warn, start, exit ----------
  async function open(id, from = null) {
    let scene;
    try {
      const r = await fetch(`${base}${encodeURIComponent(id)}.json`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      scene = await r.json();
    } catch (e) { console.warn(`Scene ${id} did not load`, e); return; }
    if (!scene.beats?.length) return;
    if (st) exit(false);
    returnFocus = from || document.activeElement;
    save();
    if (scene.sensitive && !ackSensitive.has(scene.id)) warn(scene);
    else start(scene);
  }
  function save() {
    saved = { pos: camera.position.clone(), target: controls.target.clone(), year: opts.year.save(),
      enabled: controls.enabled, damping: controls.enableDamping };
    opts.stopFlight();
    controls.enabled = false;        // no drag, zoom or arrow keys move the map under the scene
    controls.enableDamping = false;  // nor a drag's remaining glide
    document.body.classList.add('scene-on');
  }
  function warn(scene) {
    const s = S();
    $('#sp-warn-title').textContent = L(scene.title);
    $('.sp-warn-text').textContent = s.warn;
    $('.sp-warn-go').textContent = s.cont;
    $('.sp-warn-skip').textContent = s.skip;
    $('.sp-warn-go').onclick = () => { ackSensitive.add(scene.id); warning.hidden = true; start(scene); };
    $('.sp-warn-skip').onclick = () => exit();
    warning.hidden = false;
    $('.sp-warn-skip').focus();   // Skip is the default (prototype)
  }
  function start(scene) {
    const tm = timing(scene.beats);
    const local = p => { const [x, z] = toLocal(p.lat, p.lon, origin); return [x, z]; };
    st = { scene, tm, beat: 0, year: beatYear(scene, 0), elapsed: 0, playing: false, last: 0, from: null,
      targets: scene.beats.map(b => local(b.target)), cams: scene.beats.map(b => [...local(b.camera), b.camera.height_m]) };
    addOverlays(scene);
    opts.layers?.(sceneLayers(scene));
    opts.year.set(beatYear(scene, 0));
    opts.faint?.(true);   // what the year hides stays as a faint, flat today's city (app.js)
    const u = new URL(location.href); u.searchParams.set('scene', scene.id); history.replaceState(history.state, '', u);
    cinema.hidden = false;
    cinema.setAttribute('aria-label', `${S().player}: ${L(scene.title)}`);
    progEl.innerHTML = '<div class="sp-fill"></div>' + tm.offsets.map((o, i) =>
      `<button class="sp-tick" data-i="${i}" style="left:${(o / tm.total) * 100}%"></button>`).join('');
    staticText();
    go(0);
    setPlaying(!reduced());   // reduced motion: no autoplay, the viewer steps through (prototype)
    playEl.focus();
    raf = requestAnimationFrame(frame);
  }
  // restoreFocus: false when a new scene replaces this one
  function exit(restoreFocus = true) {
    cancelAnimationFrame(raf);
    removeOverlays();
    opts.layers?.([]);
    opts.faint?.(false);
    st = null;
    cinema.hidden = true;
    warning.hidden = true;
    if (saved) {
      opts.stopFlight();
      camera.position.copy(saved.pos);
      controls.target.copy(saved.target);
      camera.lookAt(controls.target);
      controls.enabled = saved.enabled;
      controls.enableDamping = saved.damping;
      opts.year.restore(saved.year);
      saved = null;
    }
    document.body.classList.remove('scene-on');
    const u = new URL(location.href);
    if (u.searchParams.has('scene')) { u.searchParams.delete('scene'); history.replaceState(history.state, '', u); }
    if (restoreFocus && returnFocus?.isConnected) returnFocus.focus();
  }

  // ---------- Beats ----------
  function go(i) {
    const n = st.scene.beats.length;
    st.beat = clampBeat(i, n);
    st.elapsed = 0;
    st.from = { pos: camera.position.clone(), target: controls.target.clone() };
    st.legFrom = null;
    $('.sp-end').hidden = true;
    const y = beatYear(st.scene, st.beat);
    if (y !== st.year) { st.year = y; opts.year.set(y); }   // the map's own buildings for the beat's year
    paint();
    progress();
  }
  function paint() {
    const b = st.scene.beats[st.beat], s = S();
    const write = () => {
      $('.sp-year').textContent = beatYear(st.scene, st.beat);
      capEl.textContent = L(b.caption);
      $('.sp-source').textContent = b.sources?.length ? `${s.source}: ${b.sources.join('; ')}` : '';
      showPhoto(b.photo);
      capEl.classList.remove('sp-fading');
    };
    if (reduced()) write();
    else { capEl.classList.add('sp-fading'); setTimeout(() => st && write(), 250); }
  }
  // The beat's photo card: served from the site itself (scenes/img/, built by scripts/scenes/build.mjs).
  function showPhoto(p) {
    const fig = $('.sp-photo'), img = fig.querySelector('img'), a = $('.sp-photo-credit');
    fig.hidden = !p;
    if (!p) { img.removeAttribute('src'); return; }
    img.src = `${base}${p.src}`;
    if (p.width && p.height) { img.width = p.width; img.height = p.height; }
    img.alt = L(p.caption);
    $('.sp-photo-cap').textContent = L(p.caption);
    a.textContent = photoCredit(p.credit, opts.lang());
    a.href = p.credit.page;
  }
  function staticText() {
    const s = S();
    $('.sp-exit').textContent = `✕ ${s.exit}`;
    $('.sp-legend').textContent = s.faint;
    $('.sp-exit').setAttribute('aria-label', s.exitScene);
    $('.sp-prev').setAttribute('aria-label', s.prev);
    $('.sp-next').setAttribute('aria-label', s.next);
    langEl.hidden = !opts.setLang;
    langEl.setAttribute('aria-label', s.captionLang);
    langEl.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.lang === opts.lang())));
    progEl.querySelectorAll('.sp-tick').forEach((el, i) => el.setAttribute('aria-label', s.beat(i + 1)));
    setPlaying(st.playing);
  }
  function showEnd() {
    const s = S();
    $('.sp-end-title').textContent = s.done;
    $('.sp-replay').textContent = `↻ ${s.replay}`;
    $('.sp-tomap').textContent = s.toMap;
    $('.sp-end').hidden = false;
    $('.sp-replay').focus();
  }
  function progress() {
    const { tm, beat, elapsed } = st;
    $('.sp-fill').style.width = `${(playedS(tm, beat, elapsed) / tm.total) * 100}%`;
    $('.sp-count').textContent = `${beat + 1} / ${tm.durations.length} · ${S().left(fmtClock(remainingS(tm, beat, elapsed)))}`;
    progEl.querySelectorAll('.sp-tick').forEach((el, i) => el.classList.toggle('done', i <= beat));
  }
  function setPlaying(on) {
    if (!st) return;
    const end = st.beat === st.tm.durations.length - 1 && st.elapsed >= st.tm.durations[st.beat];
    if (on && end) go(0);   // ▶ on the last beat's end plays the scene again
    st.playing = on;
    st.last = performance.now();
    playEl.textContent = on ? '\u23F8\uFE0E' : '\u25B6\uFE0E';   // text-style ⏸ / ▶, not emoji
    playEl.setAttribute('aria-label', on ? S().pause : S().play);
    progress();
  }

  // ---------- The frame: time, camera, overlays ----------
  const v3 = new THREE.Vector3();
  function frame(now) {
    if (!st) return;
    // at most a quarter second a frame: a stalled frame (the faint city's shaders compiling) never skips a beat
    const dt = Math.min(0.25, (now - st.last) / 1000);
    st.last = now;
    if (st.playing) {
      st.elapsed += dt;
      const d = st.tm.durations[st.beat];
      if (st.elapsed >= d) {
        if (st.beat === st.tm.durations.length - 1) { st.elapsed = d; setPlaying(false); showEnd(); }   // stops on its last beat
        else go(st.beat + 1);
      }
      progress();
    }
    placeCamera();
    placeOverlays();
    raf = requestAnimationFrame(frame);
  }
  function placeCamera() {
    const [cx, cz, h] = st.cams[st.beat], [tx, tz] = st.targets[st.beat];
    const toT = v3.set(tx, surfaceAt(tx, tz), tz).clone();
    const toP = new THREE.Vector3(cx, surfaceAt(cx, cz) + h, cz);
    const k = reduced() ? 1 : ease(st.elapsed / flightS(st.tm.durations[st.beat]));
    controls.target.lerpVectors(st.from.target, toT, k);
    camera.position.lerpVectors(st.from.pos, toP, k);
    camera.lookAt(controls.target);
  }

  // Routes: a ribbon on the ground or water, its points every 15 m so it follows the terrain; markers and the route's
  // moving marker are page elements placed over the map each frame.
  let overlays = [];
  function addOverlays(scene) {
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#1e625d';
    for (const o of scene.overlays || []) {
      if (o.type === 'route' && o.coords?.length > 1) {
        const line = polyline(o.coords.map(([la, lo]) => toLocal(la, lo, origin)));
        const mesh = new THREE.Mesh(ribbon(line, 7), new THREE.MeshBasicMaterial({ color: accent, transparent: true,
          opacity: 0.85, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -4 }));
        mesh.renderOrder = 20;
        opts.scene.add(mesh);
        const dot = document.createElement('div');
        dot.className = 'sp-mover';
        dot.title = L(o.label);
        pins.append(dot);
        overlays.push({ kind: 'route', mesh, line, dot, legs: routeLegs(line, st.targets) });
      } else if (o.type === 'marker' && o.at) {
        const at = toLocal(o.at[0], o.at[1], origin);
        const el = document.createElement('div');
        el.className = o.always ? 'sp-pin sp-always' : 'sp-pin';
        el.innerHTML = `<span class="sp-pin-dot"></span><span class="sp-pin-label">${esc(L(o.label))}</span>`;
        pins.append(el);
        overlays.push({ kind: 'marker', at, el, always: !!o.always });
      } else if (o.type === 'ghost') {
        overlays.push(o.ship ? ship(o) : ghost(o));
      }
    }
  }
  const ghostMats = () => {
    const side = { side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1 };
    return [new THREE.MeshBasicMaterial({ color: GHOST.roof, ...side }), new THREE.MeshBasicMaterial({ color: GHOST.wall, ...side }),
      new THREE.LineBasicMaterial({ color: GHOST.edge })];
  };
  // An outline in local [x, z] standing from below its lowest ground to h above it (ExtrudeGeometry: groups 0 the
  // caps, 1 the walls). Returns the meshes and the top's height.
  function prism(pts, h, mats, base) {
    const shape = new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, -z)));
    const g = new THREE.ExtrudeGeometry(shape, { depth: h + 2, bevelEnabled: false });
    g.rotateX(-Math.PI / 2);   // the shape's y becomes -z, its depth y
    g.translate(0, base - 2, 0);
    return [new THREE.Mesh(g, mats.slice(0, 2)), new THREE.LineSegments(new THREE.EdgesGeometry(g, 20), mats[2])];
  }
  function label(o) {
    const el = document.createElement('div');
    el.className = 'sp-pin sp-ghost';
    el.innerHTML = `<span class="sp-pin-label">${esc(L(o.label))}</span>`;
    pins.append(el);
    return el;
  }
  function ghost(o) {
    const group = new THREE.Group(), mats = ghostMats();
    let top = 0, cx = 0, cz = 0, n = 0;
    o.rings.forEach((ring, k) => {
      const pts = ring.map(([la, lo]) => toLocal(la, lo, origin));
      if (pts.length > 2 && pts[0][0] === pts.at(-1)[0] && pts[0][1] === pts.at(-1)[1]) pts.pop();
      const base = Math.min(...pts.map(([x, z]) => surfaceAt(x, z)));
      group.add(...prism(pts, o.heights[k], mats, base));
      top = Math.max(top, base + o.heights[k]);
      for (const [x, z] of pts) { cx += x; cz += z; n++; }
    });
    group.renderOrder = 10;
    opts.scene.add(group);
    return { kind: 'ghost', o, group, mats, el: label(o), at: [cx / n, cz / n], top };
  }
  // The Vasa: a hull and three masts as thin lines, riding the route's marker (else at the beat's target).
  function ship(o) {
    const group = new THREE.Group(), mats = ghostMats();
    const [hull, mast1, mast2, mast3] = o.heights;
    group.add(...prism(hullOutline(o.ship.length_m, o.ship.beam_m), hull, mats, 0));
    const m = [[22, mast1], [2, mast2], [-24, mast3]].flatMap(([x, h]) => [x, hull, 0, x, h, 0]);
    const mg = new THREE.BufferGeometry();
    mg.setAttribute('position', new THREE.Float32BufferAttribute(m, 3));
    const mastMat = new THREE.LineBasicMaterial({ color: GHOST.edge });
    group.add(new THREE.LineSegments(mg, mastMat));
    group.renderOrder = 10;
    opts.scene.add(group);
    mats.push(mastMat);
    if (o.ship.sinks_in_beat) for (const m of mats) m.transparent = true;   // it fades as it goes under
    return { kind: 'ship', o, group, mats, el: label(o), top: Math.max(mast1, mast2, mast3) };
  }
  function ribbon(line, width) {
    const pos = [], idx = [], step = 15;
    const samples = [];
    for (let s = 0; s < line.length; s += step) samples.push(pointAt(line, s));
    samples.push(line.pts[line.pts.length - 1]);
    samples.forEach((p, i) => {
      const a = samples[Math.max(0, i - 1)], b = samples[Math.min(samples.length - 1, i + 1)];
      const dx = b[0] - a[0], dz = b[1] - a[1], l = Math.hypot(dx, dz) || 1, nx = -dz / l * width / 2, nz = dx / l * width / 2;
      const y = surfaceAt(p[0], p[1]) + 1.5;
      pos.push(p[0] + nx, y, p[1] + nz, p[0] - nx, y, p[1] - nz);
      if (i) { const j = 2 * i; idx.push(j - 2, j - 1, j, j - 1, j + 1, j); }
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    return g;
  }
  function screenAt(x, z, lift = 2) {
    v3.set(x, surfaceAt(x, z) + lift, z).project(camera);
    if (v3.z > 1 || Math.abs(v3.x) > 1.2 || Math.abs(v3.y) > 1.2) return null;
    return [(v3.x + 1) / 2 * innerWidth, (1 - v3.y) / 2 * innerHeight];
  }
  const put = (el, p) => {
    el.hidden = !p;
    if (p) el.style.transform = `translate(${p[0].toFixed(1)}px, ${p[1].toFixed(1)}px)`;
  };
  function placeOverlays() {
    const [tx, tz] = st.targets[st.beat];
    for (const o of overlays) {
      if (o.kind === 'route') {
        const leg = o.legs[st.beat];
        if (!leg) { o.dot.hidden = true; continue; }
        const k = reduced() ? 1 : Math.min(1, st.elapsed / st.tm.durations[st.beat]);
        const p = pointAt(o.line, leg.from + (leg.to - leg.from) * k);
        put(o.dot, screenAt(p[0], p[1]));
      } else if (o.kind === 'ghost' || o.kind === 'ship') {
        const on = ghostShown(o.o, st.beat);
        o.group.visible = on;
        if (on && o.kind === 'ship') placeShip(o);
        put(o.el, on ? screenAt(o.at[0], o.at[1], o.top - (o.sunk ?? 0) - surfaceAt(o.at[0], o.at[1]) + 6) : null);
      } else {
        put(o.el, screenAt(o.at[0], o.at[1]));
        // the marker at this beat's target carries its label (or every beat, when it asks to); the others are points
        o.el.classList.toggle('sp-here', o.always || Math.hypot(o.at[0] - tx, o.at[1] - tz) < ON_ROUTE_M);
      }
    }
  }
  function placeShip(o) {
    const route = overlays.find(r => r.kind === 'route'), leg = route?.legs[st.beat];
    let p = st.targets[st.beat], dir = [1, 0];
    if (leg) {
      const k = reduced() ? 1 : Math.min(1, st.elapsed / st.tm.durations[st.beat]), s = leg.from + (leg.to - leg.from) * k;
      p = pointAt(route.line, s);
      const a = pointAt(route.line, Math.max(0, s - 20)), b = pointAt(route.line, Math.min(route.line.length, s + 20));
      if (Math.hypot(b[0] - a[0], b[1] - a[1]) > 1) dir = [b[0] - a[0], b[1] - a[1]];
    }
    // In the beat it sinks in (sinks_in_beat), over the beat's second half it settles below the water and fades
    // (at once with reduced motion).
    let k = 0;
    if (o.o.ship.sinks_in_beat === st.beat + 1) k = reduced() ? 1 : Math.min(1, Math.max(0, 2 * st.elapsed / st.tm.durations[st.beat] - 1));
    o.sunk = k * (o.o.heights[0] + 6);
    for (const m of o.mats) m.opacity = 1 - 0.75 * k;
    o.group.position.set(p[0], surfaceAt(p[0], p[1]) - o.sunk, p[1]);
    o.group.rotation.y = -Math.atan2(dir[1], dir[0]);   // the bow (+x) along the route
    o.at = p;
  }
  function removeOverlays() {
    for (const o of overlays) {
      if (o.mesh) { opts.scene.remove(o.mesh); o.mesh.geometry.dispose(); o.mesh.material.dispose(); }
      if (o.group) {
        opts.scene.remove(o.group);
        o.group.traverse(c => { c.geometry?.dispose(); if (c.material && !Array.isArray(c.material)) c.material.dispose(); });
        o.mats.forEach(m => m.dispose());
      }
    }
    overlays = [];
    pins.textContent = '';
  }

  // ---------- Controls and keys ----------
  playEl.onclick = () => setPlaying(!st.playing);
  $('.sp-next').onclick = () => go(st.beat + 1);
  $('.sp-prev').onclick = () => go(prevBeat(st.beat, st.elapsed));
  $('.sp-exit').onclick = () => exit();
  $('.sp-replay').onclick = () => { go(0); setPlaying(true); };
  $('.sp-tomap').onclick = () => exit();
  progEl.onclick = e => { const b = e.target.closest('.sp-tick'); if (b) go(+b.dataset.i); };
  langEl.onclick = e => {
    const b = e.target.closest('[data-lang]');
    if (!b || !opts.setLang) return;
    opts.setLang(b.dataset.lang);   // the page's own switch: the panels follow too
    button.textContent = S().stories;
    staticText();
    paint();                        // redraws the beat without restarting its time (prototype)
    progress();
  };
  // Capture phase: while a scene or its warning is up, its keys are its own and the map's (N, the arrows) wait.
  addEventListener('keydown', e => {
    if (!saved) return;
    if (e.key === 'Tab') return;
    if (e.key === 'Escape') { e.preventDefault(); exit(); }
    else if (st && !cinema.hidden) {
      if (e.key === 'ArrowRight') go(st.beat + 1);
      else if (e.key === 'ArrowLeft') go(st.beat - 1);
      // Space always toggles, even on a focused button (whose own click is cancelled on keyup)
      else if (e.key === ' ') { e.preventDefault(); if (!e.repeat) setPlaying(!st.playing); }
      else if (e.key !== 'Enter') return e.stopImmediatePropagation();
      else return;
    } else return;
    e.stopImmediatePropagation();
  }, true);
  addEventListener('keyup', e => { if (e.key === ' ' && st && !cinema.hidden) e.preventDefault(); }, true);

  button.hidden = !opts.enabled;
  const asked = askedScene(opts.enabled, location.search);
  if (asked) open(asked);

  return { open, exit, get state() { return st && { id: st.scene.id, beat: st.beat, playing: st.playing }; } };
}
