// Fleet Command — a strategy-game view of a TruckX fleet.
// Everything here is simulated: roads, trucks, ELD hours, AI dashcam events.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

/* ------------------------------------------------------------------ */
/* utilities                                                          */
/* ------------------------------------------------------------------ */
let seed = 11;
const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const rand = (a, b) => a + Math.random() * (b - a);
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const $ = (id) => document.getElementById(id);
const fmtHM = (h) => { h = Math.max(0, h); const m = Math.round(h * 60); return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`; };

/* ------------------------------------------------------------------ */
/* renderer / camera                                                  */
/* ------------------------------------------------------------------ */
const canvas = $('world');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color('#f6f4ef');

const VIEW = 120;
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -600, 1200);
camera.position.set(90, 100, 90);
camera.zoom = 0.55;

const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 0, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.screenSpacePanning = false;
controls.minZoom = 0.5;
controls.maxZoom = 6;
controls.minPolarAngle = 0.45;
controls.maxPolarAngle = 1.15;
controls.zoomToCursor = true;
controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };

function resize() {
  const w = innerWidth, h = innerHeight, a = w / h;
  renderer.setSize(w, h);
  camera.left = (-VIEW * a) / 2; camera.right = (VIEW * a) / 2;
  camera.top = VIEW / 2; camera.bottom = -VIEW / 2;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

/* ------------------------------------------------------------------ */
/* lights                                                             */
/* ------------------------------------------------------------------ */
scene.add(new THREE.HemisphereLight('#ffffff', '#e8dfcf', 1.7));
const sun = new THREE.DirectionalLight('#fffaf0', 2.3);
sun.position.set(-50, 120, 70);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
Object.assign(sun.shadow.camera, { left: -170, right: 170, top: 170, bottom: -170, near: 1, far: 400 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.04;
scene.add(sun, sun.target);

/* ------------------------------------------------------------------ */
/* geometry helpers                                                   */
/* ------------------------------------------------------------------ */
const MATS = new Map();
function mat(color, extra) {
  const key = color + (extra ? JSON.stringify(extra) : '');
  if (!MATS.has(key)) MATS.set(key, new THREE.MeshStandardMaterial({ color, roughness: 0.9, metalness: 0, flatShading: true, ...extra }));
  return MATS.get(key);
}
// box whose *bottom* sits at y
function box(w, h, d, color, x = 0, y = 0, z = 0, parent = scene) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));
  m.position.set(x, y + h / 2, z);
  m.castShadow = true; m.receiveShadow = true;
  parent.add(m);
  return m;
}
function cyl(rt, rb, h, color, x, y, z, parent = scene, seg = 12) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat(color));
  m.position.set(x, y + h / 2, z);
  m.castShadow = true; m.receiveShadow = true;
  parent.add(m);
  return m;
}

/* ------------------------------------------------------------------ */
/* ground, water, hills                                               */
/* ------------------------------------------------------------------ */
const ground = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), mat('#f2eee5'));
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

const water = new THREE.Mesh(new THREE.PlaneGeometry(200, 600), new THREE.MeshStandardMaterial({ color: '#cfe4ef', roughness: 0.4 }));
water.rotation.x = -Math.PI / 2;
water.position.set(-190, 0.03, 0);
water.receiveShadow = true;
scene.add(water);
box(1.2, 0.5, 600, '#e3dccd', -90, 0, 0); // seawall

function hill(x, z, r, steps, color = '#f3dcb8') {
  for (let k = 0; k < steps; k++) {
    const rr = r - k * (r / (steps + 1.2));
    const c = new THREE.Color(color).offsetHSL(0, 0, k * 0.012);
    const m = new THREE.Mesh(new THREE.CylinderGeometry(rr * 0.97, rr, 3, 14), mat('#' + c.getHexString()));
    m.position.set(x, k * 3 + 1.5, z);
    m.rotation.y = k * 0.2;
    m.castShadow = m.receiveShadow = true;
    scene.add(m);
  }
}
hill(-30, -120, 48, 6);
hill(80, -125, 36, 5);
hill(150, -40, 30, 4);

/* ------------------------------------------------------------------ */
/* road network                                                       */
/* ------------------------------------------------------------------ */
const NODES = {
  YARD: [-48, 26], PORT: [-48, -30], JCT: [0, -30], DC: [48, -30],
  CUST: [48, 26], TOWN: [0, 26], FUEL: [0, -2],
};
const EDGES = [
  ['YARD', 'PORT'], ['PORT', 'JCT'], ['JCT', 'DC'], ['DC', 'CUST'],
  ['CUST', 'TOWN'], ['TOWN', 'YARD'], ['TOWN', 'JCT'],
];
const DECOR_ROADS = [[[48, -30], [200, -30]], [[48, 26], [48, 200]], [[0, 26], [0, 200]], [[-48, 26], [-48, 120]]];
const ROAD_W = 6;
const roadSegs = [];
const dashMatrices = [];

function road(a, b, color = '#d6dae2') {
  const dx = b[0] - a[0], dz = b[1] - a[1], len = Math.hypot(dx, dz);
  const yaw = -Math.atan2(dz, dx);
  const m = new THREE.Mesh(new THREE.BoxGeometry(len + ROAD_W, 0.14, ROAD_W), mat(color));
  m.position.set((a[0] + b[0]) / 2, 0.07, (a[1] + b[1]) / 2);
  m.rotation.y = yaw;
  m.receiveShadow = true;
  scene.add(m);
  roadSegs.push([a, b]);
  const o = new THREE.Object3D();
  for (let d = ROAD_W / 2 + 1.5; d < len - ROAD_W / 2 - 1; d += 3.4) {
    o.position.set(a[0] + (dx * d) / len, 0.15, a[1] + (dz * d) / len);
    o.rotation.set(0, yaw, 0);
    o.updateMatrix();
    dashMatrices.push(o.matrix.clone());
  }
}
EDGES.forEach(([a, b]) => road(NODES[a], NODES[b]));
DECOR_ROADS.forEach(([a, b]) => road(a, b));
{
  const dashes = new THREE.InstancedMesh(new THREE.BoxGeometry(1.7, 0.02, 0.22), mat('#ffffff'), dashMatrices.length);
  dashMatrices.forEach((m, i) => dashes.setMatrixAt(i, m));
  scene.add(dashes);
}

function distToRoad(x, z) {
  let best = Infinity;
  for (const [a, b] of roadSegs) {
    const dx = b[0] - a[0], dz = b[1] - a[1];
    const t = clamp(((x - a[0]) * dx + (z - a[1]) * dz) / (dx * dx + dz * dz), 0, 1);
    best = Math.min(best, Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz));
  }
  return best;
}

/* ------------------------------------------------------------------ */
/* lane paths                                                         */
/* ------------------------------------------------------------------ */
function buildPath(ids, lane = 1.4) {
  const P = ids.map((id) => new THREE.Vector2(...NODES[id]));
  const n = P.length, R = 6;
  const raw = [], marks = [];
  const push = (v) => { if (!raw.length || raw[raw.length - 1].distanceTo(v) > 1e-3) raw.push(v.clone()); };
  const corners = P.map((p1, i) => {
    const p0 = P[(i - 1 + n) % n], p2 = P[(i + 1) % n];
    const d0 = p0.clone().sub(p1).normalize(), d2 = p2.clone().sub(p1).normalize();
    return { a: p1.clone().addScaledVector(d0, R), p: p1, b: p1.clone().addScaledVector(d2, R) };
  });
  corners.forEach((c, i) => {
    for (let k = 0; k <= 10; k++) {
      const t = k / 10, u = 1 - t;
      push(new THREE.Vector2(u * u * c.a.x + 2 * u * t * c.p.x + t * t * c.b.x, u * u * c.a.y + 2 * u * t * c.p.y + t * t * c.b.y));
      if (k === 5) marks[i] = raw.length - 1;
    }
    const nx = corners[(i + 1) % n].a, len = c.b.distanceTo(nx);
    for (let d = 1; d < len; d += 1) push(c.b.clone().lerp(nx, d / len));
  });
  const N = raw.length;
  const pts = raw.map((p, i) => {
    const t = raw[(i + 1) % N].clone().sub(raw[(i - 1 + N) % N]).normalize();
    return new THREE.Vector2(p.x - t.y * lane, p.y + t.x * lane); // right-hand traffic
  });
  const cum = [0];
  for (let i = 1; i <= N; i++) cum.push(cum[i - 1] + pts[i % N].distanceTo(pts[i - 1]));
  const total = cum[N];
  return {
    pts, cum, total, ids,
    markS: Object.fromEntries(ids.map((id, i) => [id, cum[marks[i]]])),
    at(s, out = new THREE.Vector3()) {
      s = ((s % total) + total) % total;
      let lo = 0, hi = N;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (cum[mid] <= s) lo = mid; else hi = mid; }
      const a = pts[lo], b = pts[(lo + 1) % N], f = (s - cum[lo]) / (cum[lo + 1] - cum[lo] || 1);
      return out.set(a.x + (b.x - a.x) * f, 0, a.y + (b.y - a.y) * f);
    },
  };
}

const PLACES = {
  YARD: { name: 'Sacramento Yard', code: 'YARD-01' },
  PORT: { name: 'Port of Oakland', code: 'PORT' },
  DC: { name: 'Reno DC', code: 'DC-07' },
  CUST: { name: 'Tahoe Foods', code: 'CUST-12' },
  FUEL: { name: 'Fuel stop · Exit 42', code: 'FUEL' },
};

const ROUTES = [
  { path: buildPath(['YARD', 'PORT', 'JCT', 'DC', 'CUST', 'TOWN']), stops: { YARD: 'yard', PORT: 'pickup', CUST: 'drop' }, kind: 'container' },
  { path: buildPath(['YARD', 'TOWN', 'FUEL', 'JCT', 'PORT']), stops: { YARD: 'drop', FUEL: 'fuel', PORT: 'pickup' }, kind: 'container' },
  { path: buildPath(['CUST', 'DC', 'JCT', 'FUEL', 'TOWN']), stops: { DC: 'pickup', CUST: 'drop', FUEL: 'fuel' }, kind: 'reefer' },
  { path: buildPath(['YARD', 'TOWN', 'CUST', 'DC', 'JCT', 'PORT']), stops: { DC: 'pickup', PORT: 'drop', YARD: 'yard' }, kind: 'dry' },
];

/* ------------------------------------------------------------------ */
/* scenery: buildings, facilities, trees                              */
/* ------------------------------------------------------------------ */
const blocked = []; // [x0,z0,x1,z1] rectangles to keep trees out
const block = (x, z, w, d) => blocked.push([x - w / 2, z - d / 2, x + w / 2, z + d / 2]);
const labelsPlaces = [];

function building(x, z, w, d, h, wall = '#ffffff', roof = '#4f7cf0', parent = scene) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  box(w, h, d, wall, 0, 0, 0, g);
  box(w + 0.4, 0.5, d + 0.4, roof, 0, h, 0, g);
  parent.add(g);
  return g;
}
function windows(g, w, d, h, rows = 2, color = '#6d93f5') {
  for (let r = 0; r < rows; r++)
    for (let x = -w / 2 + 1.5; x < w / 2 - 1; x += 2.2) box(1.2, 0.8, 0.1, color, x, 1.2 + r * 1.8, d / 2 + 0.03, g);
}

// --- Yard / HQ
{
  const g = building(-72, 44, 14, 9, 6, '#ffffff', '#3d6df2');
  windows(g, 14, 9, 6, 2);
  box(4, 1.2, 0.2, '#3d6df2', -4.5, 6.6, 4.6, g);
  box(26, 0.1, 18, '#e2e5eb', -66, 0.05, 28);
  for (let i = 0; i < 5; i++) box(0.25, 0.02, 8, '#ffffff', -78 + i * 4.5, 0.12, 28);
  block(-70, 36, 34, 30);
  labelsPlaces.push({ ...PLACES.YARD, pos: new THREE.Vector3(-72, 9, 44) });
}
// --- Port: containers, gantry crane, ship
{
  const cols = ['#e46c4f', '#3f7dd1', '#f1b34a', '#46b38a', '#9b7be0', '#e7e1d6'];
  box(30, 0.1, 26, '#e3e0d8', -72, 0.05, -46);
  for (let r = 0; r < 4; r++)
    for (let c = 0; c < 3; c++) {
      const h = 1 + Math.floor(rnd() * 3);
      for (let k = 0; k < h; k++) box(6, 1.4, 2.2, cols[Math.floor(rnd() * cols.length)], -76 + c * 7, k * 1.45, -54 + r * 3);
    }
  const crane = new THREE.Group(); crane.position.set(-86, 0, -40);
  ['#2f6bff'].forEach((c) => {
    box(0.6, 14, 0.6, c, -2, 0, -4, crane); box(0.6, 14, 0.6, c, -2, 0, 4, crane);
    box(0.6, 14, 0.6, c, 3, 0, -4, crane); box(0.6, 14, 0.6, c, 3, 0, 4, crane);
    box(18, 1, 1, c, -4, 14, -4, crane); box(18, 1, 1, c, -4, 14, 4, crane);
    box(2.5, 1.6, 9, '#ffffff', -6, 13.4, 0, crane);
  });
  scene.add(crane);
  const ship = new THREE.Group(); ship.position.set(-104, 0, -40);
  box(12, 3, 44, '#33415c', 0, -0.5, 0, ship);
  box(12.4, 0.5, 44.4, '#e5484d', 0, -0.2, 0, ship);
  box(8, 5, 6, '#ffffff', 0, 2.5, 17, ship);
  for (let z = -18; z < 12; z += 2.4) for (let k = 0; k < 2; k++) box(9, 1.3, 2.2, cols[Math.floor(rnd() * cols.length)], 0, 2.5 + k * 1.35, z, ship);
  scene.add(ship);
  block(-74, -46, 34, 30);
  labelsPlaces.push({ ...PLACES.PORT, pos: new THREE.Vector3(-74, 7, -50) });
}
// --- Distribution center
{
  const g = building(72, -48, 30, 16, 7, '#ffffff', '#3d6df2');
  for (let x = -12; x <= 12; x += 3.4) box(2.2, 3, 0.2, '#5d6b85', x, 0.2, 8.05, g);
  for (let x = -10; x <= 10; x += 6) box(2, 1.2, 2, '#dfe5f0', x, 7.5, -2, g);
  box(34, 0.1, 10, '#e2e5eb', 72, 0.05, -35);
  block(72, -44, 36, 30);
  labelsPlaces.push({ ...PLACES.DC, pos: new THREE.Vector3(72, 10, -48) });
}
// --- Customer warehouse
{
  const g = building(72, 44, 20, 14, 6, '#ffffff', '#16a36a');
  for (let x = -7; x <= 7; x += 3.5) box(2.2, 2.6, 0.2, '#5d6b85', x, 0.2, -7.05, g);
  box(5, 1.4, 0.2, '#16a36a', 0, 6.7, 7.1, g);
  box(24, 0.1, 8, '#e2e5eb', 72, 0.05, 33);
  block(72, 40, 26, 24);
  labelsPlaces.push({ ...PLACES.CUST, pos: new THREE.Vector3(72, 9, 44) });
}
// --- Fuel stop
{
  const g = new THREE.Group(); g.position.set(12, 0, -2);
  box(9, 0.6, 12, '#ffffff', 0, 4.4, 0, g);
  box(9.2, 0.25, 12.2, '#e5484d', 0, 4.2, 0, g);
  for (const [x, z] of [[-3.5, -5], [3.5, -5], [-3.5, 5], [3.5, 5]]) box(0.4, 4.2, 0.4, '#e9ecf1', x, 0, z, g);
  for (const z of [-3, 0, 3]) box(0.8, 1.5, 0.6, '#3d4559', 0, 0, z, g);
  box(5, 3, 6, '#fff7e8', 9, 0, 0, g);
  box(5.4, 0.4, 6.4, '#e5484d', 9, 3, 0, g);
  box(0.4, 9, 0.4, '#c9ced8', 6, 0, -7, g);
  box(2.6, 1.6, 0.4, '#e5484d', 6, 8.2, -7, g);
  scene.add(g);
  block(17, -2, 22, 18);
  labelsPlaces.push({ ...PLACES.FUEL, pos: new THREE.Vector3(14, 10, -6) });
}
// --- Weigh station
{
  const g = new THREE.Group(); g.position.set(24, 0, -40);
  box(16, 0.18, 4, '#cfd3db', 0, 0, 0, g);
  box(3, 3, 3, '#ffffff', 0, 0, -4.5, g);
  box(3.4, 0.35, 3.4, '#f1b34a', 0, 3, -4.5, g);
  box(0.3, 5, 0.3, '#c9ced8', -9, 0, -3, g);
  box(3.4, 1.5, 0.2, '#16a36a', -9, 4.6, -3, g);
  scene.add(g);
  block(24, -41, 20, 10);
  labelsPlaces.push({ name: 'Weigh station', code: 'BYPASS', pos: new THREE.Vector3(24, 6, -44) });
}
// --- Town (left quadrant)
{
  const roofs = ['#f08a6c', '#7aa2f7', '#f2c36b', '#89cfb3'];
  for (let i = 0; i < 12; i++) {
    const x = -38 + (i % 4) * 8.5 + rnd() * 2, z = -18 + Math.floor(i / 4) * 11 + rnd() * 2;
    const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = rnd() < 0.5 ? 0 : Math.PI / 2;
    box(4.6, 2.6, 4, '#ffffff', 0, 0, 0, g);
    const roof = new THREE.Mesh(new THREE.ConeGeometry(3.6, 2, 4), mat(roofs[i % 4]));
    roof.position.y = 3.6; roof.rotation.y = Math.PI / 4; roof.scale.z = 0.85; roof.castShadow = true;
    g.add(roof);
    scene.add(g);
  }
  // LTE tower that every ELD and dashcam talks to
  const t = new THREE.Group(); t.position.set(-30, 0, 16);
  box(0.5, 16, 0.5, '#c9ced8', 0, 0, 0, t);
  for (const a of [0, 2.1, 4.2]) { const p = box(0.35, 1.6, 0.9, '#ffffff', Math.cos(a) * 0.7, 13.5, Math.sin(a) * 0.7, t); p.rotation.y = -a; }
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.45, 10, 8), new THREE.MeshBasicMaterial({ color: '#ff4d4f' }));
  beacon.position.y = 16.5; t.add(beacon);
  scene.add(t);
  t.userData.beacon = beacon;
  window.__tower = t;
  block(-24, -2, 40, 40);
  labelsPlaces.push({ name: 'Cell tower', code: 'LTE', pos: new THREE.Vector3(-30, 19, 16) });
}
// --- Farmland (right quadrant)
{
  const colors = ['#cfe7b8', '#e8deb0', '#bfe0b0'];
  for (let i = 0; i < 9; i++) box(24, 0.25, 2.4, colors[i % 3], 28, 0, -16 + i * 3.6);
  const barn = building(30, 18, 8, 6, 4, '#e46c4f', '#f6f4ef');
  barn.rotation.y = 0.2;
  block(28, 0, 30, 44);
}

// --- trees
{
  const crownGeo = new THREE.IcosahedronGeometry(1, 0);
  const crowns = ['#a9dcc8', '#93d2bb', '#bfe6d4'];
  let placed = 0, tries = 0;
  while (placed < 170 && tries++ < 6000) {
    const x = (rnd() - 0.5) * 300, z = (rnd() - 0.5) * 300;
    if (x < -88) continue;
    if (distToRoad(x, z) < 6.5) continue;
    if (blocked.some(([x0, z0, x1, z1]) => x > x0 && x < x1 && z > z0 && z < z1)) continue;
    const s = 1.4 + rnd() * 1.4;
    cyl(0.25, 0.32, 1.6, '#ebe6dc', x, 0, z, scene, 6);
    const c = new THREE.Mesh(crownGeo, mat(crowns[placed % 3]));
    c.scale.set(s, s * 1.15, s);
    c.position.set(x, 1.4 + s, z);
    c.rotation.y = rnd() * 3;
    c.castShadow = true;
    scene.add(c);
    placed++;
  }
}

// --- geofences around facilities
const fences = {};
for (const [id, pos] of Object.entries({ YARD: [-62, 34], PORT: [-66, -42], DC: [62, -42], CUST: [62, 36], FUEL: [6, -2] })) {
  const r = id === 'FUEL' ? 11 : 20;
  const pts = [];
  for (let i = 0; i <= 96; i++) pts.push(new THREE.Vector3(Math.cos((i / 96) * Math.PI * 2) * r, 0.25, Math.sin((i / 96) * Math.PI * 2) * r));
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color: '#2f6bff', dashSize: 1.2, gapSize: 1, transparent: true, opacity: 0.35 }));
  line.computeLineDistances();
  line.position.set(pos[0], 0, pos[1]);
  const disc = new THREE.Mesh(new THREE.CircleGeometry(r, 64), new THREE.MeshBasicMaterial({ color: '#2f6bff', transparent: true, opacity: 0.0, depthWrite: false }));
  disc.rotation.x = -Math.PI / 2; disc.position.set(pos[0], 0.2, pos[1]);
  scene.add(line, disc);
  fences[id] = { line, disc, active: 0 };
}

/* ------------------------------------------------------------------ */
/* vehicles                                                           */
/* ------------------------------------------------------------------ */
const logoTex = (() => {
  const c = document.createElement('canvas'); c.width = 512; c.height = 96;
  const x = c.getContext('2d');
  x.fillStyle = '#ffffff'; x.fillRect(0, 0, 512, 96);
  x.fillStyle = '#2f6bff'; x.font = '900 64px Inter, system-ui, sans-serif'; x.textBaseline = 'middle';
  x.fillText('Truck', 20, 50);
  x.fillStyle = '#19c3a0'; x.fillText('X', 20 + x.measureText('Truck').width, 50);
  x.fillStyle = '#8a93a3'; x.font = '600 26px Inter, system-ui, sans-serif'; x.fillText('AI-safe fleet', 300, 52);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
})();
const logoMat = new THREE.MeshBasicMaterial({ map: logoTex });

const wheelGeo = new THREE.CylinderGeometry(0.45, 0.45, 0.32, 12);
function wheel(g, x, z, r = 1) {
  const w = new THREE.Mesh(wheelGeo, mat('#2a2d33'));
  w.rotation.x = Math.PI / 2; w.position.set(x, 0.45 * r, z); w.scale.setScalar(r); w.castShadow = true;
  g.add(w);
}
function makeTractor(color) {
  const g = new THREE.Group();
  box(3.6, 0.35, 1.15, '#3a3f4a', 1.2, 0.35, 0, g);
  box(1.45, 1.45, 1.38, color, 2.0, 0.7, 0, g);
  box(0.75, 0.8, 1.24, color, 3.05, 0.65, 0, g);
  box(1.05, 0.45, 1.3, new THREE.Color(color).offsetHSL(0, 0, 0.08).getStyle(), 1.85, 2.15, 0, g);
  box(0.06, 0.5, 1.2, '#26314a', 2.74, 1.45, 0, g);
  box(0.7, 0.42, 1.4, '#26314a', 2.25, 1.5, 0, g);
  box(0.12, 0.32, 1.32, '#eceef2', 3.45, 0.55, 0, g);
  box(0.06, 0.18, 0.28, '#ffe08a', 3.42, 1.0, 0.42, g);
  box(0.06, 0.18, 0.28, '#ffe08a', 3.42, 1.0, -0.42, g);
  cyl(0.09, 0.09, 1.9, '#c3c8d2', 1.15, 0.7, 0.62, g, 6);
  cyl(0.09, 0.09, 1.9, '#c3c8d2', 1.15, 0.7, -0.62, g, 6);
  // dashcam dot on windshield
  const cam = new THREE.Mesh(new THREE.SphereGeometry(0.08, 6, 6), new THREE.MeshBasicMaterial({ color: '#19c3a0' }));
  cam.position.set(2.79, 1.85, 0); g.add(cam);
  for (const z of [0.6, -0.6]) { wheel(g, -0.1, z); wheel(g, 0.45, z); wheel(g, 2.85, z * 0.95); }
  return g;
}
function makeTrailer(kind, color) {
  const g = new THREE.Group();
  box(5.6, 0.25, 0.9, '#3a3f4a', -2.9, 0.6, 0, g);
  if (kind === 'container') {
    const c = pick(['#e46c4f', '#3f7dd1', '#f1b34a', '#46b38a']);
    box(6.2, 1.75, 1.4, c, -2.7, 0.85, 0, g);
    for (let x = -5.5; x < 0.3; x += 0.55) box(0.06, 1.6, 1.44, new THREE.Color(c).offsetHSL(0, 0, -0.06).getStyle(), x, 0.92, 0, g);
  } else {
    box(6.4, 1.85, 1.42, '#ffffff', -2.8, 0.85, 0, g);
    box(6.42, 0.18, 1.44, color, -2.8, 1.0, 0, g);
    for (const side of [1, -1]) {
      const p = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 0.68), logoMat);
      p.position.set(-2.8, 1.85, side * 0.72); p.rotation.y = side > 0 ? 0 : Math.PI;
      g.add(p);
    }
    if (kind === 'reefer') box(0.35, 1.1, 1.1, '#d5d9e1', 0.55, 1.2, 0, g);
  }
  for (const z of [0.6, -0.6]) { wheel(g, -4.7, z); wheel(g, -5.3, z); }
  box(0.15, 0.6, 0.15, '#9aa1ad', -1.2, 0.2, 0.45, g);
  box(0.15, 0.6, 0.15, '#9aa1ad', -1.2, 0.2, -0.45, g);
  return g;
}
function makeCar(color) {
  const g = new THREE.Group();
  box(2.5, 0.6, 1.2, color, 0, 0.3, 0, g);
  box(1.3, 0.5, 1.05, '#ffffff', -0.15, 0.9, 0, g);
  box(1.32, 0.3, 1.07, '#2c3549', -0.15, 1.0, 0, g);
  for (const z of [0.55, -0.55]) { wheel(g, 0.8, z, 0.7); wheel(g, -0.8, z, 0.7); }
  return g;
}

const DRIVERS = [
  ['Maria Reyes', '#2f6bff'], ['James Carter', '#16a36a'], ['Aisha Khan', '#e8960c'], ['Dmitri Volkov', '#7c5cff'],
  ['Luis Ortega', '#e5484d'], ['Priya Nair', '#0ea5b7'], ['Tom Becker', '#d9467a'], ['Keisha Brown', '#3d6df2'],
  ['Wei Zhang', '#16a36a'], ['Sam Okafor', '#e8960c'], ['Elena Petrova', '#7c5cff'], ['Jake Miller', '#0ea5b7'],
];
const RELIEF = ['Nora Lindqvist', 'Omar Haddad', 'Grace Kim', 'Diego Santos', 'Hannah Cole', 'Ravi Patel'];
const MAKES = ['Freightliner Cascadia', 'Volvo VNL 860', 'Kenworth T680', 'Peterbilt 579', 'International LT'];
const CAB_COLORS = ['#f4c430', '#2f6bff', '#ffffff', '#e5484d', '#16a36a', '#f08a3c'];
const CARGO = ['Electronics', 'Produce', 'Auto parts', 'Paper goods', 'Beverages', 'Apparel', 'Frozen foods', 'Building supply'];

const vehicles = [];
const trucks = [];

function addTruck(i, routeIdx, s0) {
  const route = ROUTES[routeIdx];
  const color = CAB_COLORS[i % CAB_COLORS.length];
  const tractor = makeTractor(color);
  const trailer = makeTrailer(route.kind, color);
  scene.add(tractor, trailer);
  const [name, avatar] = DRIVERS[i];
  const t = {
    id: `TX-${101 + i}`, i, route, s: s0, v: 0, base: rand(7.2, 8.6), front: 3.5, back: 6.2,
    tractor, trailer, fwd: new THREE.Vector3(1, 0, 0), pos: new THREE.Vector3(), wait: 0, dwell: 0, dwellKind: null, dwellAt: null,
    driver: name, avatar, make: MAKES[i % MAKES.length], vin: String(1000 + Math.floor(Math.random() * 9000)),
    driveLeft: rand(3.5, 10.5), shiftLeft: rand(5, 13), cycleLeft: rand(25, 62), breakLeft: rand(2, 7.5),
    fuel: rand(45, 95), score: Math.round(rand(88, 99)), engine: 'OK', loaded: Math.random() < 0.6, load: null,
    alarm: 0, boost: 0, hosWarned: false, puffT: Math.random(), isTruck: true,
    log: [rand(0.25, 0.35), rand(0.05, 0.12), rand(0.25, 0.4)],
  };
  if (t.loaded) t.load = newLoad(t, 'PORT');
  tractor.traverse((o) => (o.userData.truck = t));
  trailer.traverse((o) => (o.userData.truck = t));
  trucks.push(t);
  vehicles.push(t);
}
function newLoad(t, from) {
  const dropId = Object.entries(t.route.stops).find(([, k]) => k === 'drop')[0];
  return {
    bol: String(88000 + Math.floor(Math.random() * 999)), cargo: pick(CARGO), lb: Math.round(rand(18, 43)) * 1000,
    trailer: `TR-${10 + Math.floor(Math.random() * 40)}`, from: PLACES[from]?.name ?? 'Origin', to: PLACES[dropId].name, dropId,
    startS: t.s,
  };
}

[[0, 0], [1, 0], [2, 0], [3, 1], [4, 1], [5, 1], [6, 2], [7, 2], [8, 2], [9, 3], [10, 3], [11, 3]].forEach(([i, r], k, arr) => {
  const sameRoute = arr.filter(([, rr]) => rr === r);
  const idx = sameRoute.findIndex(([ii]) => ii === i);
  addTruck(i, r, (ROUTES[r].path.total / sameRoute.length) * idx + 10);
});
const CAR_COLORS = ['#c7cbd3', '#9fb7e8', '#f2b8a0', '#a8d8c4', '#ffffff', '#5d6b85', '#f3d58a'];
for (let i = 0; i < 12; i++) {
  const route = ROUTES[i % ROUTES.length];
  const g = makeCar(CAR_COLORS[i % CAR_COLORS.length]);
  scene.add(g);
  vehicles.push({ route, s: (route.path.total / 3) * Math.floor(i / 4) + route.path.total / 6, v: 0, base: rand(8.5, 10.5), front: 1.3, back: 1.3, car: g, fwd: new THREE.Vector3(1, 0, 0), pos: new THREE.Vector3(), wait: 0, dwell: 0, alarm: 0, boost: 0 });
}

// selection ring
const selRing = new THREE.Mesh(new THREE.RingGeometry(4.6, 5.2, 64), new THREE.MeshBasicMaterial({ color: '#2f6bff', transparent: true, opacity: 0.85, depthWrite: false }));
selRing.rotation.x = -Math.PI / 2; selRing.visible = false;
scene.add(selRing);

// pulse rings for events
const pulses = [];
function pulse(pos, color) {
  const m = new THREE.Mesh(new THREE.RingGeometry(1, 1.35, 48), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 1, depthWrite: false, side: THREE.DoubleSide }));
  m.rotation.x = -Math.PI / 2; m.position.copy(pos).setY(0.3);
  scene.add(m);
  pulses.push({ m, t: 0 });
}

// exhaust puffs
const puffGeo = new THREE.IcosahedronGeometry(0.35, 0);
const puffs = [];
function puff(p) {
  const m = new THREE.Mesh(puffGeo, new THREE.MeshStandardMaterial({ color: '#ffffff', transparent: true, opacity: 0.7, flatShading: true }));
  m.position.copy(p);
  scene.add(m);
  puffs.push({ m, t: 0 });
}

/* ------------------------------------------------------------------ */
/* simulation                                                         */
/* ------------------------------------------------------------------ */
const CLOCK_RATE = 60; // sim seconds per real second at 1×
let simSpeed = 1;
let clock = 6 * 3600 + 10 * 60;
let delivered = 31, late = 1;
const tmpA = new THREE.Vector3(), tmpB = new THREE.Vector3(), tmpC = new THREE.Vector3();

function crossed(prev, next, a, T) {
  const p = ((prev % T) + T) % T, n = ((next % T) + T) % T;
  return p <= n ? a > p && a <= n : a > p || a <= n;
}

function stepVehicles(dt) {
  // desired speeds with simple car-following
  for (const v of vehicles) {
    let want = v.dwell > 0 ? 0 : v.base * (v.boost > 0 ? 1.18 : 1);
    if (v.dwell <= 0) {
      for (const o of vehicles) {
        if (o === v) continue;
        tmpA.subVectors(o.pos, v.pos);
        const along = tmpA.dot(v.fwd);
        if (along <= 0 || along > 22) continue;
        const lat = Math.abs(tmpA.x * v.fwd.z - tmpA.z * v.fwd.x);
        if (lat > 1.7 || v.fwd.dot(o.fwd) < 0.2) continue;
        const clear = along - v.front - o.back;
        want = Math.min(want, clear < 1 ? 0 : o.v + (clear - 1) * 0.9);
      }
      if (want < 0.3) v.wait += dt; else v.wait = 0;
      if (v.wait > 5) want = v.base * 0.5; // never gridlock
    }
    v.want = Math.max(0, want);
  }
  for (const v of vehicles) {
    v.v += clamp(v.want - v.v, -14 * dt, 3.2 * dt);
    if (v.v < 0) v.v = 0;
    const prev = v.s;
    v.s += v.v * dt;
    if (v.dwell > 0) {
      v.dwell -= dt;
      if (v.dwell <= 0 && v.isTruck) endDwell(v);
    }
    if (v.isTruck && v.dwell <= 0) {
      for (const [id, kind] of Object.entries(v.route.stops)) {
        if (crossed(prev, v.s, v.route.path.markS[id], v.route.path.total)) startDwell(v, id, kind);
      }
    }
    v.boost -= dt; v.alarm -= dt;

    // pose
    const P = v.route.path;
    if (v.car) {
      P.at(v.s - 1.2, tmpA); P.at(v.s + 1.2, tmpB);
      v.pos.addVectors(tmpA, tmpB).multiplyScalar(0.5);
      v.fwd.subVectors(tmpB, tmpA).normalize();
      v.car.position.copy(v.pos);
      v.car.rotation.y = Math.atan2(-v.fwd.z, v.fwd.x);
    } else {
      P.at(v.s, tmpA); P.at(v.s + 2.8, tmpB); P.at(v.s - 5.0, tmpC);
      v.fwd.subVectors(tmpB, tmpA).normalize();
      v.pos.copy(tmpA);
      v.tractor.position.copy(tmpA);
      v.tractor.rotation.y = Math.atan2(-v.fwd.z, v.fwd.x);
      v.trailer.position.copy(tmpA);
      v.trailer.rotation.y = Math.atan2(-(tmpA.z - tmpC.z), tmpA.x - tmpC.x);
      v.puffT -= dt * (0.6 + v.v / 6);
      if (v.puffT < 0) {
        v.puffT = 0.55;
        tmpB.set(1.15, 2.7, 0.62).applyAxisAngle(THREE.Object3D.DEFAULT_UP, v.tractor.rotation.y).add(v.pos);
        puff(tmpB);
      }
    }
  }
}

function startDwell(t, id, kind) {
  if (kind === 'fuel' && t.fuel > 55) return;
  t.dwellAt = id; t.dwellKind = kind;
  t.dwell = kind === 'fuel' ? 2.5 : kind === 'yard' ? 3 : rand(4, 6);
  if (fences[id]) fences[id].active++;
  if (kind === 'drop' && t.loaded) { delivered++; t.loaded = false; toast(`<span style="color:var(--green)">✓</span> ${t.id} delivered BOL ${t.load.bol} to ${PLACES[id].name} · on time`); bump(4); }
}
function endDwell(t) {
  const id = t.dwellAt, kind = t.dwellKind;
  if (fences[id]) fences[id].active--;
  t.dwellAt = null; t.dwellKind = null;
  if (kind === 'pickup') { t.loaded = true; t.load = newLoad(t, id); bump(2); }
  if (kind === 'fuel') { t.fuel = 100; }
  if ((kind === 'yard' || kind === 'drop') && id === 'YARD') {
    t.breakLeft = 8;
    if (t.driveLeft < 4) {
      const old = t.driver;
      t.driver = RELIEF.shift(); RELIEF.push(old);
      t.driveLeft = 11; t.shiftLeft = 14; t.hosWarned = false; t.log = [0.3, 0.1, 0.02];
      toast(`🔁 ${t.id} driver relay at Sacramento Yard — ${t.driver} takes the wheel`);
      if (selected === t) refreshCard(true);
    }
  }
}

function stepHOS(dt) {
  const h = (dt * CLOCK_RATE) / 3600;
  for (const t of trucks) {
    const driving = t.dwell <= 0 && t.v > 0.5;
    t.shiftLeft = Math.max(0, t.shiftLeft - h);
    t.cycleLeft = Math.max(0, t.cycleLeft - h);
    if (driving) {
      t.driveLeft = Math.max(0, t.driveLeft - h);
      t.breakLeft = Math.max(0, t.breakLeft - h);
      t.fuel = Math.max(8, t.fuel - h * 9);
      t.log[2] += h / 24;
    }
    if (!t.hosWarned && t.driveLeft < 0.6) { t.hosWarned = true; raise(t, EVENTS.find((e) => e.k === 'hos')); }
    t.score = Math.min(99, t.score + dt * 0.01);
  }
}

/* ------------------------------------------------------------------ */
/* events: AI dashcam + ELD                                           */
/* ------------------------------------------------------------------ */
const EVENTS = [
  { k: 'brake', title: 'Harsh braking', sev: 'red', src: 'AI dashcam · road', meta: () => `−0.${Math.floor(rand(42, 61))}g at ${Math.floor(rand(52, 63))} mph`, clip: true, w: 3, moving: true, box: 'VEHICLE 9m', warn: true },
  { k: 'phone', title: 'Phone use detected', sev: 'red', src: 'AI dashcam · driver', meta: () => `Handheld for ${Math.floor(rand(4, 11))}s · in-cab alert played`, clip: true, w: 2, moving: true, box: 'PHONE', warn: true, cabin: true },
  { k: 'tail', title: 'Following too close', sev: 'amber', src: 'AI dashcam · road', meta: () => `${rand(0.8, 1.4).toFixed(1)}s headway at ${Math.floor(rand(56, 64))} mph`, clip: true, w: 3, moving: true, box: 'VEHICLE 14m', warn: true },
  { k: 'speed', title: 'Speeding', sev: 'amber', src: 'GPS + posted limits', meta: () => `${Math.floor(rand(69, 74))} in a 65 zone`, clip: true, w: 2, moving: true },
  { k: 'drowsy', title: 'Drowsiness — repeated yawning', sev: 'amber', src: 'AI dashcam · driver', meta: () => '3 yawns in 6 min · suggest break', clip: true, w: 1, moving: true, cabin: true },
  { k: 'stop', title: 'Rolling stop', sev: 'amber', src: 'AI dashcam · road', meta: () => `${Math.floor(rand(5, 9))} mph through stop sign`, clip: true, w: 1, moving: true, box: 'STOP SIGN' },
  { k: 'hos', title: 'HOS: under 40 min drive time', sev: 'blue', src: 'ELD · FMCSA', meta: () => 'Suggest relay at Sacramento Yard', w: 0 },
  { k: 'dvir', title: 'DVIR defect reported', sev: 'blue', src: 'ELD · DVIR', meta: () => pick(['Trailer marker light out', 'Mud flap damaged', 'Left mirror cracked', 'Tire tread 4/32"']), w: 1 },
  { k: 'idle', title: 'Excess idling', sev: 'blue', src: 'Engine bus · J1939', meta: () => `${Math.floor(rand(11, 19))} min idle · ~0.${Math.floor(rand(3, 6))} gal`, w: 2, dwelling: true },
  { k: 'fault', title: 'Engine fault code', sev: 'amber', src: 'Engine bus · J1939', meta: () => pick(['P0299 turbo underboost', 'SPN 3226 NOx sensor', 'P0128 coolant temp low']), w: 1, fault: true },
];
const alerts = [];
let nextEvent = 3;

function maybeEvent(dt) {
  nextEvent -= dt;
  if (nextEvent > 0) return;
  nextEvent = rand(4, 8);
  const pool = EVENTS.flatMap((e) => Array(e.w).fill(e));
  for (let tries = 0; tries < 10; tries++) {
    const e = pick(pool), t = pick(trucks);
    if (e.moving && (t.dwell > 0 || t.v < 4)) continue;
    if (e.dwelling && t.dwell <= 0) continue;
    raise(t, e);
    return;
  }
}

function raise(t, e) {
  const color = { red: '#e5484d', amber: '#e8960c', blue: '#2f6bff' }[e.sev];
  pulse(t.pos, color);
  setTimeout(() => pulse(t.pos, color), 350);
  t.alarm = e.sev === 'blue' ? 0 : 4;
  if (e.k === 'brake') t.v *= 0.3;
  if (e.k === 'speed') t.boost = 4;
  if (e.fault) t.engine = 'Fault';
  if (e.sev === 'red') t.score -= 3; else if (e.sev === 'amber') t.score -= 1;
  const a = { t, e, meta: e.meta(), time: clockStr(clock), resolved: false, born: performance.now() };
  alerts.unshift(a);
  if (alerts.length > 40) alerts.pop();
  renderAlerts(a);
}

function renderAlerts(fresh) {
  const ul = $('alertList');
  if (fresh) {
    const li = document.createElement('li');
    li.className = 'alert';
    const act = fresh.e.clip ? 'View clip' : fresh.e.k === 'hos' || fresh.e.k === 'dvir' ? 'Open log' : 'Locate';
    li.innerHTML = `<span class="sev ${fresh.e.sev}"></span><div><b>${fresh.e.title}</b><div class="meta">${fresh.t.id} · ${fresh.t.driver.split(' ')[0]} · ${fresh.meta}</div><div class="src">${fresh.time} · ${fresh.e.src}</div></div><button class="act">${act}</button>`;
    li.onclick = () => { fresh.resolved = true; li.classList.add('resolved'); select(fresh.t, fresh); renderAlerts(); };
    fresh.li = li;
    ul.prepend(li);
    while (ul.children.length > 40) ul.lastChild.remove();
  }
  const open = alerts.filter((a) => !a.resolved);
  const n = open.length;
  $('alertTitle').textContent = n ? `${n} open alert${n > 1 ? 's' : ''}` : 'No open alerts';
  $('shield').classList.toggle('hot', open.some((a) => a.e.sev === 'red'));
  $('badge').textContent = n; $('badge').classList.toggle('show', n > 0);
  const red = open.filter((a) => a.e.sev === 'red').length;
  $('alertSub').textContent = n ? `${red} safety-critical · auto-coaching queued for ${new Set(open.map((a) => a.t.driver)).size} drivers` : 'Watching 12 dashcams and 12 ELDs across I-80, I-5 and the yard';
}
// alerts age out (auto-coached) after a while so the list stays alive
setInterval(() => {
  const now = performance.now();
  let changed = false;
  for (const a of alerts) if (!a.resolved && now - a.born > 45000) { a.resolved = true; a.li?.classList.add('resolved'); changed = true; }
  if (changed) renderAlerts();
}, 2000);

/* ------------------------------------------------------------------ */
/* HUD                                                                */
/* ------------------------------------------------------------------ */
const clockStr = (s, sec) => {
  s = Math.floor(s) % 86400;
  const h = String(Math.floor(s / 3600)).padStart(2, '0'), m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  return sec ? `${h}:${m}:${String(s % 60).padStart(2, '0')}` : `${h}:${m}`;
};
const ICONS = {
  yard: '<path d="M3 21V9l9-5 9 5v12"/><path d="M8 21v-7h8v7"/>',
  load: '<path d="M4 7h16v13H4z"/><path d="M9 3h6v4H9z"/><path d="M12 11v5m-2.5-2.5L12 16l2.5-2.5"/>',
  transit: '<path d="M3 7h11v9H3z"/><path d="M14 10h4l3 3v3h-7"/><circle cx="7" cy="17" r="1.6"/><circle cx="17" cy="17" r="1.6"/>',
  unload: '<path d="M4 7h16v13H4z"/><path d="M9 3h6v4H9z"/><path d="M12 16v-5m-2.5 2.5L12 11l2.5 2.5"/>',
  done: '<path d="M5 12l4 4 10-10"/>',
};
const STAGES = [['yard', 'At yard'], ['load', 'Loading'], ['transit', 'In transit'], ['unload', 'Unloading'], ['done', 'Delivered']];
$('stages').innerHTML = STAGES.map(([k, l], i) => `<div class="stage"><div class="ic" id="st${i}"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${ICONS[k]}</svg></div><div class="lbl">${l}</div><div class="val" id="sv${i}">–</div></div>`).join('');
function bump(i) { const el = $('st' + i); el.classList.add('bump'); setTimeout(() => el.classList.remove('bump'), 260); }

function updateHUD() {
  $('clock').textContent = clockStr(clock);
  const atYard = trucks.filter((t) => t.dwell > 0 && t.dwellAt === 'YARD').length;
  const loading = trucks.filter((t) => t.dwell > 0 && t.dwellKind === 'pickup').length;
  const unloading = trucks.filter((t) => t.dwell > 0 && t.dwellKind === 'drop').length;
  const transit = trucks.filter((t) => t.dwell <= 0 && t.loaded);
  const lb = transit.reduce((s, t) => s + t.load.lb, 0);
  const dead = trucks.filter((t) => t.dwell <= 0 && !t.loaded).length;
  $('sv0').textContent = `${atYard} trucks`;
  $('sv1').textContent = `${loading} docks`;
  $('sv2').textContent = `${transit.length} · ${Math.round(lb / 1000)}k lb`;
  $('sv3').textContent = `${unloading} docks`;
  $('sv4').textContent = `${delivered} loads`;
  const ontime = ((delivered - late) / delivered) * 100;
  $('flowBig').textContent = `${ontime.toFixed(1)}% on-time today`;
  $('flowSm').textContent = `${delivered} delivered · ${late} late · ${dead} deadheading`;
  const moving = trucks.filter((t) => t.v > 0.5).length;
  $('fleetSub').textContent = `${moving}/12 trucks rolling · 12 AI dashcams`;
  const safety = trucks.reduce((s, t) => s + t.score, 0) / trucks.length;
  $('kSafety').textContent = Math.round(safety);
  $('kSafety').style.color = safety > 90 ? 'var(--green)' : safety > 84 ? 'var(--amber)' : 'var(--red)';
  $('kHos').innerHTML = `${trucks.filter((t) => t.driveLeft > 0).length}<small>/12</small>`;
  $('kMpg').textContent = (7.2 + Math.sin(clock / 900) * 0.25).toFixed(1);
  $('kIdle').innerHTML = `${(2.8 + Math.sin(clock / 1300) * 0.6).toFixed(1)}<small>%</small>`;
}

/* --- world labels --- */
const labelRoot = $('labels');
for (const p of labelsPlaces) {
  p.el = document.createElement('div');
  p.el.className = 'place';
  p.el.innerHTML = `${p.name} <span class="mono">${p.code}</span>`;
  labelRoot.appendChild(p.el);
}
for (const t of trucks) {
  t.tag = document.createElement('div');
  t.tag.className = 'tag';
  t.tag.onclick = () => select(t);
  labelRoot.appendChild(t.tag);
}
const proj = new THREE.Vector3();
function place(el, v) {
  proj.copy(v).project(camera);
  const x = ((proj.x + 1) / 2) * innerWidth, y = ((-proj.y + 1) / 2) * innerHeight;
  const off = x < -80 || y < -40 || x > innerWidth + 80 || y > innerHeight + 40;
  el.style.display = off ? 'none' : '';
  if (!off) el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`;
}
function updateLabels(frame) {
  const showPlaces = camera.zoom < 2.6;
  for (const p of labelsPlaces) { if (showPlaces) place(p.el, p.pos); else p.el.style.display = 'none'; }
  for (const t of trucks) {
    proj.copy(t.pos).setY(4.8);
    place(t.tag, proj);
    if (frame % 6 === 0) {
      const alarm = t.alarm > 0, dock = t.dwell > 0;
      const cls = alarm ? 'alarm' : dock ? 'dock' : t.driveLeft < 1 || t.boost > 0 ? 'warn' : '';
      t.tag.className = `tag${selected === t ? ' sel' : ''}${alarm ? ' alarm' : ''}`;
      t.tag.innerHTML = `<span class="d ${cls}"></span>${t.id} <span class="hos">${fmtHM(t.driveLeft)}</span>`;
    }
  }
}
// labels are positioned via transform from (0,0)
document.head.insertAdjacentHTML('beforeend', '<style>.tag,.place{left:0;top:0;transform-origin:0 0}</style>');

/* --- toast --- */
let toastTimer;
function toast(html) {
  const el = $('toast');
  el.innerHTML = html;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

/* ------------------------------------------------------------------ */
/* selection, truck card, dashcam                                     */
/* ------------------------------------------------------------------ */
let selected = null, following = false, camView = 'road';
const camCanvas = $('dashcam');
const camRenderer = new THREE.WebGLRenderer({ canvas: camCanvas, antialias: true });
camRenderer.setPixelRatio(1);
camRenderer.setSize(480, 270, false);
const dashCam = new THREE.PerspectiveCamera(68, 16 / 9, 0.1, 800);

function select(t, alert) {
  selected = t;
  following = true;
  $('card').classList.add('open');
  refreshCard(true);
  flyTo(t.pos, Math.max(camera.zoom, 2.2));
  const ev = $('camEvent'), bx = $('camBox');
  ev.classList.remove('show'); bx.classList.remove('show', 'warn');
  if (alert && alert.e.clip) {
    setCamView(alert.e.cabin ? 'cabin' : 'road');
    ev.textContent = `${alert.e.title.toUpperCase()} · ${alert.time}`;
    ev.classList.add('show');
    if (alert.e.box) { bx.classList.add('show'); bx.classList.toggle('warn', !!alert.e.warn); $('camBoxLbl').textContent = alert.e.box; }
    clearTimeout(select._t);
    select._t = setTimeout(() => { ev.classList.remove('show'); bx.classList.remove('show'); }, 5000);
  } else if (alert) {
    toast(`${alert.e.title} — ${alert.t.id}: ${alert.meta}`);
  }
}
function deselect() {
  selected = null; following = false;
  $('card').classList.remove('open');
  flyTo(controls.target.clone(), 1.1);
}
$('cClose').onclick = deselect;
$('cFollow').onclick = () => { following = !following; $('cFollow').textContent = following ? 'Following' : 'Follow truck'; };
$('cMsg').onclick = () => selected && toast(`💬 Sent to ${selected.driver.split(' ')[0]} via in-cab tablet: “Take your 30 at the next stop — thanks!”`);
document.querySelectorAll('.camtabs button').forEach((b) => (b.onclick = () => setCamView(b.dataset.v)));
function setCamView(v) {
  camView = v;
  document.querySelectorAll('.camtabs button').forEach((b) => b.classList.toggle('on', b.dataset.v === v || (v === 'cabin' && b.dataset.v === 'road')));
  $('camLbl').textContent = { road: 'ROAD · LIVE', cabin: 'DRIVER · LIVE', chase: 'CHASE · SIM', sky: 'DRONE · SIM' }[v];
}

function ring(label, val, max, color) {
  const f = clamp(val / max, 0, 1), C = 2 * Math.PI * 22;
  return `<div class="ring"><svg viewBox="0 0 56 56"><circle cx="28" cy="28" r="22" fill="none" stroke="#eef0f3" stroke-width="6"/><circle cx="28" cy="28" r="22" fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${C * f} ${C}" transform="rotate(-90 28 28)"/><text x="28" y="31" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-size="10.5" font-weight="800" fill="#172033">${fmtHM(val)}</text></svg><div class="rl">${label}</div></div>`;
}
function refreshCard(full) {
  const t = selected;
  if (!t) return;
  if (full) {
    $('cAvatar').textContent = t.driver.split(' ').map((w) => w[0]).join('');
    $('cAvatar').style.background = t.avatar;
    $('cName').textContent = t.driver;
    $('cSub').textContent = `${t.id} · ${t.make}`;
    $('cVin').textContent = `VIN …${t.vin}`;
    $('cFollow').textContent = following ? 'Following' : 'Follow truck';
  }
  const hosColor = (v, warn) => (v < warn ? 'var(--red)' : v < warn * 2.5 ? 'var(--amber)' : 'var(--blue)');
  $('cRings').innerHTML = ring('Drive', t.driveLeft, 11, hosColor(t.driveLeft, 1)) + ring('Shift', t.shiftLeft, 14, hosColor(t.shiftLeft, 1)) + ring('Cycle', t.cycleLeft, 70, '#19c3a0') + ring('Break in', t.breakLeft, 8, hosColor(t.breakLeft, 0.5));
  const [off, sb, dr] = t.log, on = Math.max(0, 1 - off - sb - dr) * 0.4;
  $('cDutyBar').innerHTML = `<i style="width:${off * 100}%;background:#cfd5df"></i><i style="width:${sb * 100}%;background:#9aa8c7"></i><i style="width:${dr * 100}%;background:var(--green)"></i><i style="width:${on * 100}%;background:var(--amber)"></i>`;
  const status = t.dwell > 0 ? (t.dwellKind === 'fuel' ? 'On duty · fueling' : t.dwellKind === 'yard' ? 'On duty · yard' : 'On duty · at dock') : t.v < 0.5 ? 'Driving · stopped' : 'Driving';
  $('cDuty').textContent = status;
  $('cDuty').style.color = t.dwell > 0 ? 'var(--amber)' : 'var(--green)';
  const mph = Math.round(t.v * 8);
  $('cSpeed').textContent = `${mph} mph`;
  $('cSpeed').style.color = mph > 66 ? 'var(--red)' : '';
  $('cFuel').textContent = `${Math.round(t.fuel)}%`;
  $('cScore').textContent = Math.round(t.score);
  $('cScore').style.color = t.score > 90 ? 'var(--green)' : t.score > 84 ? 'var(--amber)' : 'var(--red)';
  $('cEngine').textContent = t.engine;
  $('cEngine').style.color = t.engine === 'OK' ? 'var(--green)' : 'var(--amber)';
  if (t.loaded && t.load) {
    const L = t.load, P = t.route.path;
    const target = P.markS[L.dropId];
    const pos = ((t.s % P.total) + P.total) % P.total;
    const startPos = ((L.startS % P.total) + P.total) % P.total;
    const tot = (target - startPos + P.total) % P.total || P.total;
    const left = (target - pos + P.total) % P.total;
    const prog = clamp(1 - left / tot, 0, 1);
    $('cBol').textContent = `BOL ${L.bol}`;
    $('cRoute').textContent = `${L.from} → ${L.to}`;
    $('cCargo').textContent = `${L.cargo} · ${L.lb.toLocaleString()} lb · ${L.trailer}`;
    const miles = Math.round(left * 1.1);
    $('cMiles').textContent = `${miles} mi`;
    $('cEta').textContent = `ETA ${clockStr(clock + (left / 7.8) * CLOCK_RATE * 1.4)}`;
    $('cBar').style.width = `${prog * 100}%`;
  } else {
    $('cBol').textContent = 'Empty';
    $('cRoute').textContent = 'Deadhead → next pickup';
    $('cCargo').textContent = 'Trailer empty · reloading soon';
    $('cMiles').textContent = '';
    $('cEta').textContent = '';
    $('cBar').style.width = '0%';
  }
}

function updateDashcam() {
  const t = selected;
  if (!t) return;
  const P = t.route.path;
  const eye = new THREE.Vector3(), look = new THREE.Vector3();
  if (camView === 'road') {
    P.at(t.s + 3.3, eye).setY(2.15);
    P.at(t.s + 26, look).setY(1.4);
    dashCam.fov = 68;
  } else if (camView === 'cabin') {
    P.at(t.s + 3.3, eye).setY(2.2);
    P.at(t.s + 1.2, look).setY(1.6);
    // look slightly to the side, like a driver-facing lens
    const side = new THREE.Vector3(-t.fwd.z, 0, t.fwd.x).multiplyScalar(-0.35);
    look.add(side);
    dashCam.fov = 95;
  } else if (camView === 'chase') {
    P.at(t.s - 16, eye).setY(6.5);
    P.at(t.s + 8, look).setY(1.5);
    dashCam.fov = 55;
  } else {
    eye.copy(t.pos).add(new THREE.Vector3(14, 34, 14));
    look.copy(t.pos);
    dashCam.fov = 45;
  }
  dashCam.updateProjectionMatrix();
  dashCam.position.copy(eye);
  dashCam.lookAt(look);
  // hide our own rig in the in-cab views
  const own = camView === 'road' || camView === 'cabin';
  t.tractor.visible = !own;
  selRing.visible = false;
  camRenderer.render(scene, dashCam);
  t.tractor.visible = true;
  $('camTime').textContent = clockStr(clock, true);
  $('camSpd').textContent = `${Math.round(t.v * 8)} MPH`;
  $('camGps').textContent = `${(38.58 + t.pos.z * -0.002).toFixed(4)}N ${(121.49 - t.pos.x * 0.002).toFixed(4)}W`;
}

/* --- camera fly-to --- */
let fly = null;
function flyTo(target, zoom) {
  fly = { from: controls.target.clone(), to: target.clone(), z0: camera.zoom, z1: zoom, t: 0 };
}
const ease = (x) => 1 - Math.pow(1 - x, 3);

/* --- picking --- */
const ray = new THREE.Raycaster();
let down = null;
canvas.addEventListener('pointerdown', (e) => (down = [e.clientX, e.clientY]));
canvas.addEventListener('pointerup', (e) => {
  if (!down) return;
  const moved = Math.hypot(e.clientX - down[0], e.clientY - down[1]);
  down = null;
  if (moved > 5) { if (following) { following = false; $('cFollow').textContent = 'Follow truck'; } return; }
  ray.setFromCamera(new THREE.Vector2((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1), camera);
  const hits = ray.intersectObjects(trucks.flatMap((t) => [t.tractor, t.trailer]), true);
  if (hits.length) select(hits[0].object.userData.truck);
});

/* --- controls --- */
const speedBtns = [...document.querySelectorAll('#speed button')];
let lastSpeed = 1;
function setSpeed(s) {
  if (s > 0) lastSpeed = s;
  simSpeed = s;
  speedBtns.forEach((b) => b.classList.toggle('on', +b.dataset.s === s));
}
speedBtns.forEach((b) => (b.onclick = () => setSpeed(+b.dataset.s)));
addEventListener('keydown', (e) => {
  if (e.code === 'Space') { e.preventDefault(); setSpeed(simSpeed ? 0 : lastSpeed); }
  if (e.code === 'Escape') deselect();
  if (e.key === '1') setSpeed(1);
  if (e.key === '2') setSpeed(4);
  if (e.key === '3') setSpeed(12);
});
$('bell').onclick = () => {
  const first = alerts.find((a) => !a.resolved);
  if (first) first.li.click();
  else toast('All clear — no open alerts');
};

/* ------------------------------------------------------------------ */
/* main loop                                                          */
/* ------------------------------------------------------------------ */
const clk = new THREE.Clock();
let frame = 0, intro = 0;
function tick() {
  requestAnimationFrame(tick);
  const rdt = Math.min(clk.getDelta(), 0.05);
  const dt = rdt * simSpeed;
  frame++;

  // intro sweep
  if (intro < 1) {
    intro = Math.min(1, intro + rdt / 2.6);
    camera.zoom = 0.55 + (1.25 - 0.55) * ease(intro);
    camera.updateProjectionMatrix();
  }

  // sub-step physics so 12× stays stable
  const steps = Math.ceil(dt / 0.02);
  for (let i = 0; i < steps; i++) stepVehicles(dt / steps);
  stepHOS(dt);
  maybeEvent(dt);
  clock += dt * CLOCK_RATE;

  // fx
  for (let i = pulses.length - 1; i >= 0; i--) {
    const p = pulses[i];
    p.t += rdt;
    const k = p.t / 1.4;
    p.m.scale.setScalar(1 + k * 9);
    p.m.material.opacity = 1 - k;
    if (k >= 1) { scene.remove(p.m); p.m.geometry.dispose(); p.m.material.dispose(); pulses.splice(i, 1); }
  }
  for (let i = puffs.length - 1; i >= 0; i--) {
    const p = puffs[i];
    p.t += dt;
    p.m.position.y += dt * 1.6;
    p.m.scale.setScalar(1 + p.t * 2.2);
    p.m.material.opacity = 0.6 * (1 - p.t / 1.4);
    if (p.t > 1.4) { scene.remove(p.m); p.m.material.dispose(); puffs.splice(i, 1); }
  }
  for (const f of Object.values(fences)) {
    const target = f.active > 0 ? 0.09 + Math.sin(performance.now() / 300) * 0.03 : 0;
    f.disc.material.opacity += (target - f.disc.material.opacity) * 0.1;
    f.line.material.opacity = f.active > 0 ? 0.8 : 0.3;
  }
  window.__tower.userData.beacon.visible = Math.floor(performance.now() / 600) % 2 === 0;

  // camera
  if (fly) {
    fly.t = Math.min(1, fly.t + rdt / 1.1);
    const e = ease(fly.t);
    const dest = selected && following ? selected.pos : fly.to;
    const nt = fly.from.clone().lerp(dest, e);
    camera.position.add(nt.clone().sub(controls.target));
    controls.target.copy(nt);
    camera.zoom = fly.z0 + (fly.z1 - fly.z0) * e;
    camera.updateProjectionMatrix();
    if (fly.t >= 1) fly = null;
  } else if (selected && following) {
    const d = selected.pos.clone().sub(controls.target).multiplyScalar(0.12);
    controls.target.add(d);
    camera.position.add(d);
  }
  controls.update();

  if (selected) {
    selRing.position.copy(selected.pos).setY(0.25);
    selRing.rotation.z += rdt * 0.6;
    if (frame % 15 === 0) refreshCard(false);
    if (frame % 2 === 0) updateDashcam();
    selRing.visible = true;
  } else selRing.visible = false;

  updateLabels(frame);
  if (frame % 10 === 0) updateHUD();
  renderer.render(scene, camera);
}
updateHUD();
tick();
