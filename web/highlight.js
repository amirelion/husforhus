// The building picked from search, marked on the building itself (a look change decided 2026-10-17, replacing a red
// ring on the ground): a thin outline along its edges in the look's accent colour, two gentle pulses when the camera
// arrives, then a quiet steady outline while its card is open; under prefers-reduced-motion, no pulse.
//
// The edges come from the building's own triangles in its tile mesh (the `bld` attribute names the building's row in
// the tile, whose attribute record holds its gid), so the outline follows any shape, not only a box. It hangs under
// the tile mesh (decimetres, as the tile's positions) and is lifted as the building shader lifts the building: its
// ground × uRelief. WebGL draws lines one pixel wide whatever is asked, so each edge is a quad turned to face the
// screen, a fixed number of pixels wide.

// pulseWidth(k): the outline's width in CSS pixels at k (0..1) through the arrival: two swells, back to the base.
export const BASE_PX = 2, SWELL_PX = 4, PULSE_MS = 1600, PULSES = 2;
export const pulseWidth = k => (k >= 1 || k <= 0 ? BASE_PX : BASE_PX + SWELL_PX * Math.sin(Math.PI * PULSES * k) ** 2);

// The quads for line segments [x0, y0, z0, x1, y1, z1, ...]: four corners each (end 0 or 1, side -1 or 1), two
// triangles. Pure, so node --test can check it.
export function quads(seg) {
  const n = seg.length / 6;
  const a = new Float32Array(n * 12), b = new Float32Array(n * 12), corner = new Float32Array(n * 8);
  const index = new Uint32Array(n * 6);
  for (let s = 0; s < n; s++) {
    for (let c = 0; c < 4; c++) {
      const v = s * 4 + c;
      a.set(seg.subarray(s * 6, s * 6 + 3), v * 3);
      b.set(seg.subarray(s * 6 + 3, s * 6 + 6), v * 3);
      corner[v * 2] = c >> 1;              // 0, 0, 1, 1: which end
      corner[v * 2 + 1] = c & 1 ? 1 : -1;  // -1, 1, -1, 1: which side
    }
    index.set([s * 4, s * 4 + 2, s * 4 + 1, s * 4 + 1, s * 4 + 2, s * 4 + 3], s * 6);
  }
  return { a, b, corner, index };
}

// The triangles of row `row` in a tile: positions (x, y, z per corner) from its indexed geometry.
export function trianglesOf(pos, bld, idx, row) {
  const out = [];
  for (let k = 0; k < idx.length; k += 3) {
    if (Math.round(bld[idx[k]]) !== row || Math.round(bld[idx[k + 1]]) !== row || Math.round(bld[idx[k + 2]]) !== row) continue;
    for (let j = 0; j < 3; j++) { const v = idx[k + j]; out.push(pos[v * 3], pos[v * 3 + 1], pos[v * 3 + 2]); }
  }
  return new Float32Array(out);
}

const VERT = /* glsl */`
  in vec3 pb;
  in vec2 corner;
  uniform float uRelief, uGround, uWidth;
  uniform vec2 uHalf;     // half the drawing buffer, in device pixels
  void main() {
    vec3 lift = vec3(0.0, uGround * uRelief, 0.0);
    vec4 va = modelViewMatrix * vec4(position + lift, 1.0), vb = modelViewMatrix * vec4(pb + lift, 1.0);
    // a little towards the camera, so an edge wins over the two faces it bounds
    va.xyz *= 0.997; vb.xyz *= 0.997;
    vec4 ca = projectionMatrix * va, cb = projectionMatrix * vb;
    vec2 sa = ca.xy / max(ca.w, 1e-3) * uHalf, sb = cb.xy / max(cb.w, 1e-3) * uHalf;
    vec2 d = sb - sa;
    vec2 n = length(d) > 1e-4 ? normalize(vec2(-d.y, d.x)) : vec2(0.0);
    vec4 c = corner.x < 0.5 ? ca : cb;
    c.xy += n * corner.y * 0.5 * uWidth / uHalf * c.w;
    gl_Position = c;
  }
`;
const FRAG = /* glsl */`
  precision highp float;
  uniform vec3 uColour;
  uniform float uAlpha;
  out vec4 outColor;
  void main() { outColor = vec4(uColour, uAlpha); }
`;

export function makeHighlight(THREE, { uRelief, attrFloats, renderer, reduced }) {
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3, vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false,
    side: THREE.DoubleSide,
    uniforms: { uRelief, uGround: { value: 0 }, uWidth: { value: BASE_PX }, uHalf: { value: new THREE.Vector2(1, 1) },
      uColour: { value: new THREE.Color() }, uAlpha: { value: 0.95 } },
  });
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), material);
  mesh.name = 'pick-outline';
  mesh.frustumCulled = false;
  mesh.renderOrder = 20;
  mesh.visible = false;
  let gid = -1, colour = '', segments = 0, pulseAt = -1, pulses = 0;
  const size = new THREE.Vector2();

  // Finds the building in the tile meshes; false if its tile is not on the map yet (show() is asked again later).
  function build(meshes) {
    for (const tile of meshes) {
      const attr = tile.userData.attr, n = tile.userData.nB;
      if (!attr) continue;
      for (let row = 0; row < n; row++) {
        if (attr[row * attrFloats + 3] !== gid) continue;
        const g = tile.geometry;
        const tri = trianglesOf(g.attributes.position.array, g.attributes.bld.array, g.index.array, row);
        const shape = new THREE.BufferGeometry();
        shape.setAttribute('position', new THREE.BufferAttribute(tri, 3));
        const edges = new THREE.EdgesGeometry(shape, 25);
        const q = quads(edges.attributes.position.array);
        shape.dispose(); edges.dispose();
        mesh.geometry.dispose();
        mesh.geometry = new THREE.BufferGeometry();
        mesh.geometry.setAttribute('position', new THREE.BufferAttribute(q.a, 3));
        mesh.geometry.setAttribute('pb', new THREE.BufferAttribute(q.b, 3));
        mesh.geometry.setAttribute('corner', new THREE.BufferAttribute(q.corner, 2));
        mesh.geometry.setIndex(new THREE.BufferAttribute(q.index, 1));
        segments = q.index.length / 6;
        material.uniforms.uGround.value = attr[row * attrFloats + 8];   // web/worker.js: the building's ground, dm
        tile.add(mesh);
        return true;
      }
    }
    return false;
  }

  return {
    mesh,
    // The pick (gid >= 0) or none (-1).
    show(g, meshes) {
      gid = g; pulseAt = -1; pulses = 0; segments = 0;
      mesh.removeFromParent();
      mesh.visible = false;
      if (g >= 0 && build(meshes)) mesh.visible = true;
    },
    // The camera has arrived: two gentle pulses, or none for a visitor who asked for less motion.
    pulse(now) {
      if (gid < 0) return;
      pulses = reduced() ? 0 : PULSES;
      pulseAt = pulses ? now : -1;
    },
    // Each frame: the width (and the pulse), the look's accent, and a tile that arrived after the pick.
    step(now, accent, meshes) {
      if (gid < 0) return;
      if (!mesh.parent && !build(meshes)) return;
      mesh.visible = true;
      if (accent !== colour) { colour = accent; material.uniforms.uColour.value.set(accent); }
      const k = pulseAt < 0 ? 1 : (now - pulseAt) / PULSE_MS;
      if (k >= 1) pulseAt = -1;
      const px = renderer.getPixelRatio();
      renderer.getDrawingBufferSize(size);
      material.uniforms.uHalf.value.set(size.x / 2, size.y / 2);
      material.uniforms.uWidth.value = pulseWidth(k) * px;
    },
    state: () => ({ gid, visible: mesh.visible, colour, segments, pulses, pulsing: pulseAt >= 0 }),
  };
}
