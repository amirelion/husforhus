// Tunnelbanan drawn on the map (web/metro.js decides what shows at a year): each segment a flat ribbon slightly above
// the ground in its line's colour, each station a small ring, with its name when the camera comes close; Kymlinge
// (never opened) a dashed ring, at Today only. update() runs every few frames: it follows the timeline's year (so
// Play grows the lines in step), the relief, and keeps the ribbon about the same width on screen.
import { metroAt, LINE_COLOURS } from './metro.js';

const LIFT_M = 3;                 // above the ground
const NAMES_WITHIN = 3000;        // camera distance (m) under which the station names show

function ringTexture(THREE, colour, fill, dashed) {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const ctx = c.getContext('2d');
  ctx.lineWidth = 10;
  ctx.fillStyle = fill; ctx.strokeStyle = colour;
  if (dashed) ctx.setLineDash([11, 8]);
  ctx.beginPath(); ctx.arc(32, 32, 24, 0, Math.PI * 2);
  if (!dashed) ctx.fill();
  ctx.stroke();
  return new THREE.CanvasTexture(c);
}

function nameTexture(THREE, text, ink, halo) {
  const c = document.createElement('canvas'), ctx = c.getContext('2d');
  const font = '600 26px system-ui, sans-serif';
  ctx.font = font;
  c.width = Math.ceil(ctx.measureText(text).width) + 16; c.height = 40;
  ctx.font = font; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
  ctx.lineWidth = 6; ctx.strokeStyle = halo; ctx.strokeText(text, 8, 20);
  ctx.fillStyle = ink; ctx.fillText(text, 8, 20);
  const t = new THREE.CanvasTexture(c);
  t.userData = { aspect: c.width / c.height };
  return t;
}

export function makeMetroLayer(THREE, { metro, surfaceAt, camera, theme, T }) {
  const group = new THREE.Group();
  const ribbons = metro.segments.map(g => {
    const geo = new THREE.BufferGeometry();
    const n = g.track.length;
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 6), 3));
    const idx = [];
    for (let i = 0; i < n - 1; i++) idx.push(2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 1, 2 * i + 3, 2 * i + 2);
    geo.setIndex(idx);
    const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: LINE_COLOURS[g.line], side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    mesh.renderOrder = 1; mesh.frustumCulled = false; mesh.visible = false;
    mesh.userData = { segment: g };
    group.add(mesh);
    return mesh;
  });
  let rings = [], names = [];
  function build() {
    for (const o of [...rings, ...names]) { group.remove(o); o.material.map.dispose(); o.material.dispose(); }
    const th = theme();
    rings = metro.stations.map(s => {
      const m = new THREE.Sprite(new THREE.SpriteMaterial({ map: ringTexture(THREE, LINE_COLOURS[s.lines[0]] || '#888888',
        th.land, !!s.never), sizeAttenuation: false, depthTest: false }));
      m.scale.set(0.014, 0.014, 1); m.renderOrder = 4; m.visible = false; m.userData = { station: s };
      group.add(m);
      return m;
    });
    names = metro.stations.map(s => {
      const tex = nameTexture(THREE, s.never ? T('metro.neverName', { name: s.name }) : s.name, th.labelInk, th.labelHalo);
      const m = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, sizeAttenuation: false, depthTest: false }));
      m.center.set(-0.08, 0.5);
      m.scale.set(0.022 * tex.userData.aspect, 0.022, 1); m.renderOrder = 4; m.visible = false; m.userData = { station: s };
      group.add(m);
      return m;
    });
  }
  build();

  let shownStations = new Set(), shownSegments = new Set();
  function update(year, today, dist) {
    const at = metroAt(metro, year, today);
    shownSegments = new Set(at.segments.map(g => g.id));
    shownStations = new Set([...at.stations, ...at.never].map(s => s.name));
    const half = Math.min(60, Math.max(5, dist * 0.004));
    for (const r of ribbons) {
      const g = r.userData.segment, on = shownSegments.has(g.id);
      r.visible = on;
      if (!on) continue;
      const p = g.track, a = r.geometry.attributes.position;
      for (let i = 0; i < p.length; i++) {
        const [x0, z0] = p[Math.max(0, i - 1)], [x1, z1] = p[Math.min(p.length - 1, i + 1)];
        const len = Math.hypot(x1 - x0, z1 - z0) || 1, nx = -(z1 - z0) / len * half, nz = (x1 - x0) / len * half;
        const [x, z] = p[i], y = surfaceAt(x, z) + LIFT_M;
        a.setXYZ(2 * i, x + nx, y, z + nz); a.setXYZ(2 * i + 1, x - nx, y, z - nz);
      }
      a.needsUpdate = true;
    }
    const near = dist < NAMES_WITHIN;
    for (let i = 0; i < rings.length; i++) {
      const s = rings[i].userData.station, on = shownStations.has(s.name);
      rings[i].visible = on;
      if (on) rings[i].position.set(s.x, surfaceAt(s.x, s.z) + LIFT_M + 1, s.z);
      const d = Math.hypot(s.x - camera.position.x, s.z - camera.position.z);
      names[i].visible = on && near && d < dist * 2.5;
      if (names[i].visible) names[i].position.copy(rings[i].position);
    }
  }
  // The station whose ring is under the pointer (within a few pixels), or null.
  const v = new THREE.Vector3();
  function stationAt(px, py, w, h, slack = 12) {
    let best = null, bd = slack;
    for (const r of rings) {
      if (!r.visible) continue;
      v.copy(r.position).project(camera);
      if (v.z > 1) continue;
      const d = Math.hypot((v.x + 1) / 2 * w - px, (1 - v.y) / 2 * h - py);
      if (d < bd) { bd = d; best = r.userData.station; }
    }
    return best;
  }
  return { group, update, stationAt, retheme: build,
    get shownStations() { return [...shownStations]; }, get shownSegments() { return [...shownSegments]; },
    get namesShown() { return names.filter(n => n.visible).map(n => n.userData.station.name); } };
}
