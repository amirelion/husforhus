// The boats drawn on the map (web/ferries.js says where each one is): every hull in one InstancedMesh and every wake
// in a second, so all the boats together cost two draw calls. The hulls are low-poly models to scale, lit by the
// map's one sun like the buildings' walls, in the look's paint (ferries.js PAINT); a wake is a soft, lighter plume
// behind a boat that is moving, fading as it slows into a pier. Both fade into the sky at the municipality's edge and
// into the fog like the water (app.js hands over the shared uniforms and the edge fade's GLSL). Boats float on the
// water at y 0 (the sea and Mälaren are one level, so the drawn water is at 0 at any relief) and grow with the camera's
// distance, up to four times, so one stays a few pixels long when the map is zoomed out.
// app.js calls step() every frame: it returns at once while the boats are hidden (the switch off, a year before
// Today, the film or a story), and under reduced motion the boats stand still, without wakes, each on a run of its
// route (ferries.js calmTime). The pick pass hides the group (app.js pick), so a boat is never hovered or clicked.
// Tested through the pure parts (web/test/ferries.test.mjs) and in the browser (e2e/ferries.spec.mjs).
import { KINDS, routePlan, boatAt, calmTime, boatScale, boatModels, wakeModel, PAINT, PARTS } from './ferries.js';
import { SHADING } from './themes.js';

const glf = x => (Number.isInteger(x) ? x.toFixed(1) : String(x));
const WAKE_ALPHA = 0.55;   // a wake's opacity at the stern, at full speed

const HULL_VERT = /* glsl */`
  in float aPart;     // per vertex: 0 hull, 1 upper works, 2 windows, 3 the ships' band (ferries.js PARTS)
  in float aModel;    // per vertex: 0 the ferry's model, 1 the ship's
  in float aKind;     // per boat: which model it is
  in float aAlpha;    // per boat: 0 out of sight past an edge end, 1 shown
  uniform vec3 uPaint[4];
  out vec3 vWorld;
  out vec3 vColour;
  out float vAlpha;
  void main() {
    // the other kind's triangles go off screen, so each boat draws only its own model
    if (abs(aModel - aKind) > 0.5 || aAlpha < 0.004) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
    vec4 w = modelMatrix * instanceMatrix * vec4(position, 1.0);
    vWorld = w.xyz;
    vColour = uPaint[int(aPart + 0.5)];
    vAlpha = aAlpha;
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;
const hullFrag = fade => /* glsl */`
  precision highp float;
  uniform vec3 uFogColor, uSun;
  uniform vec2 uFog;
  ${fade}
  in vec3 vWorld;
  in vec3 vColour;
  in float vAlpha;
  out vec4 outColor;
  void main() {
    // flat faces lit like the buildings' walls (app.js FRAG): n faces the camera, so it is the outward normal
    vec3 n = normalize(cross(dFdx(vWorld), dFdy(vWorld)));
    float light = n.y > 0.9 ? 1.04 : ${glf(SHADING.wallMin)} + ${glf(SHADING.wallLit)} * max(dot(n, uSun), 0.0);
    vec3 c = vColour * light;
    c = mix(uFogColor, c, fadeAt(vWorld.xz));
    c = mix(c, uFogColor, smoothstep(uFog.x, uFog.y, length(vWorld - cameraPosition)));
    outColor = vec4(c, vAlpha);
  }
`;
const WAKE_VERT = /* glsl */`
  in float aT;        // 0 at the stern, 1 at the tail
  in float aSide;     // -1 to 1 across
  in float aAlpha;    // per boat: its wake's strength (its speed, and its fade at an edge)
  out vec3 vWorld;
  out float vAlpha;
  void main() {
    if (aAlpha < 0.004) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
    vec4 w = modelMatrix * instanceMatrix * vec4(position, 1.0);
    vWorld = w.xyz;
    // soft: strongest at the stern and along the middle, gone at the tail and the edges
    vAlpha = aAlpha * pow(1.0 - aT, 1.6) * (1.0 - aSide * aSide * 0.85);
    gl_Position = projectionMatrix * viewMatrix * w;
  }
`;
const wakeFrag = fade => /* glsl */`
  precision highp float;
  uniform vec3 uFogColor, uWake;
  uniform vec2 uFog;
  ${fade}
  in vec3 vWorld;
  in float vAlpha;
  out vec4 outColor;
  void main() {
    vec3 c = mix(uFogColor, uWake, fadeAt(vWorld.xz));
    c = mix(c, uFogColor, smoothstep(uFog.x, uFog.y, length(vWorld - cameraPosition)));
    outColor = vec4(c, vAlpha);
  }
`;

// routes: ferries.js parseFerries; uniforms: app.js's shared ones (the fog, the sky, the sun, the edge fade); fadeGlsl:
// the grid and edge-fade GLSL that declares fadeAt (app.js GRID_GLSL + FADE_GLSL); look(): the look's id; calm: the
// reduced-motion query.
export function makeFerries(THREE, { routes, uniforms, fadeGlsl, look, calm }) {
  const plans = routes.map(routePlan);
  // calm: the moment this boat stands still at under reduced motion
  const boats = plans.flatMap(plan => Array.from({ length: plan.boats }, (_, i) => ({ plan, i, calm: calmTime(plan, i) })));
  const n = boats.length;
  const shared = { uFog: uniforms.uFog, uFogColor: uniforms.uFogColor, uSun: uniforms.uSun, uFade: uniforms.uFade,
    uGridO: uniforms.uGridO, uGridN: uniforms.uGridN, uCell: uniforms.uCell };

  const m = boatModels();
  const hullGeo = new THREE.BufferGeometry();
  hullGeo.setAttribute('position', new THREE.BufferAttribute(m.position, 3));
  hullGeo.setAttribute('aPart', new THREE.BufferAttribute(m.part, 1));
  hullGeo.setAttribute('aModel', new THREE.BufferAttribute(m.model, 1));
  const kindAttr = new THREE.InstancedBufferAttribute(Float32Array.from(boats, b => (b.plan.route.kind === 'ship' ? 1 : 0)), 1);
  const hullAlpha = new THREE.InstancedBufferAttribute(new Float32Array(n), 1);
  hullAlpha.setUsage(THREE.DynamicDrawUsage);
  hullGeo.setAttribute('aKind', kindAttr);
  hullGeo.setAttribute('aAlpha', hullAlpha);
  const paint = PARTS.map(() => new THREE.Color());
  // Transparent so a boat can fade at an edge end; it writes depth like any solid, and draws after the water's names.
  const hullMat = new THREE.ShaderMaterial({ glslVersion: THREE.GLSL3, vertexShader: HULL_VERT, fragmentShader: hullFrag(fadeGlsl),
    uniforms: { ...shared, uPaint: { value: paint } }, side: THREE.DoubleSide, transparent: true });
  const hulls = new THREE.InstancedMesh(hullGeo, hullMat, n);
  hulls.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  hulls.renderOrder = 3;
  hulls.frustumCulled = false;   // the boats move every frame, all over the city: one bounding sphere would be stale
  hulls.name = 'boats';

  const w = wakeModel();
  const wakeGeo = new THREE.BufferGeometry();
  wakeGeo.setAttribute('position', new THREE.BufferAttribute(w.position, 3));
  wakeGeo.setAttribute('aT', new THREE.BufferAttribute(w.t, 1));
  wakeGeo.setAttribute('aSide', new THREE.BufferAttribute(w.side, 1));
  wakeGeo.setIndex(new THREE.BufferAttribute(w.index, 1));
  const wakeAlpha = new THREE.InstancedBufferAttribute(new Float32Array(n), 1);
  wakeAlpha.setUsage(THREE.DynamicDrawUsage);
  wakeGeo.setAttribute('aAlpha', wakeAlpha);
  const wakeColour = new THREE.Color();
  // On the water, under the boats and the water's names: no depth written, nudged towards the camera so it never
  // flickers with the water it lies on.
  const wakeMat = new THREE.ShaderMaterial({ glslVersion: THREE.GLSL3, vertexShader: WAKE_VERT, fragmentShader: wakeFrag(fadeGlsl),
    uniforms: { ...shared, uWake: { value: wakeColour } }, transparent: true, depthWrite: false, side: THREE.DoubleSide,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const wakes = new THREE.InstancedMesh(wakeGeo, wakeMat, n);
  wakes.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  wakes.renderOrder = 1;
  wakes.frustumCulled = false;
  wakes.name = 'wakes';

  const group = new THREE.Group();
  group.add(wakes, hulls);
  group.visible = false;

  function retheme() {
    const p = PAINT[look()] || PAINT.arg;
    PARTS.forEach((k, i) => paint[i].set(p[k]));
    wakeColour.set(p.wake);
  }
  retheme();

  // Where each boat was drawn last (for __dbg and the tests).
  const last = boats.map(() => null);
  let frozen = null;
  const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0), P = new THREE.Vector3(),
    S = new THREE.Vector3();
  // t: seconds (the page's clock); dist: the camera's distance to its target; show: whether the boats are on the map.
  function step(t, dist, show) {
    group.visible = show;
    if (!show) return;
    const still = calm.matches;
    boats.forEach((b, k) => {
      // the boost first: the boat keeps to its right by as much more as it is drawn larger
      const kind = KINDS[b.plan.route.kind], s = boatScale(dist, kind.length);
      const at = boatAt(b.plan, b.i, still ? b.calm : frozen ?? t, s);
      last[k] = { route: b.plan.route.id, i: b.i, kind: b.plan.route.kind, x: at.x, z: at.z, heading: at.heading,
        alpha: at.alpha, speed: still ? 0 : at.speed, scale: s };
      // three.js turns about +y anticlockwise seen from above, from +x towards -z: the bow (+x) along the heading
      Q.setFromAxisAngle(Y, -at.heading);
      M.compose(P.set(at.x, 0, at.z), Q, S.set(s, s, s));
      hulls.setMatrixAt(k, M);
      hullAlpha.array[k] = at.alpha;
      // the wake starts at the stern and lies just above the water
      const [len, width] = kind.wake, back = kind.length * 0.46 * s;
      M.compose(P.set(at.x - Math.cos(at.heading) * back, 0.15 * s, at.z - Math.sin(at.heading) * back), Q,
        S.set(len * s, 1, width * s));
      wakes.setMatrixAt(k, M);
      wakeAlpha.array[k] = still ? 0 : WAKE_ALPHA * at.alpha * at.speed;
    });
    hulls.instanceMatrix.needsUpdate = wakes.instanceMatrix.needsUpdate = true;
    hullAlpha.needsUpdate = wakeAlpha.needsUpdate = true;
  }

  return { group, step, retheme,
    // freeze(t): draw every boat as at time t until freeze(null), for tests that compare two screenshots
    freeze: t => { frozen = t ?? null; },
    get count() { return n; },
    get visible() { return group.visible; },
    get positions() { return last.map(p => p && { ...p }); },
    get routes() { return routes.map(r => ({ id: r.id, ref: r.ref, name: r.name, kind: r.kind, ends: r.ends, length: r.length })); } };
}
