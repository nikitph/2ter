// Vrukshali digital twin: a satellite-aligned, walkable 3D model of the resort with design tools.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { TransformControls } from './vendor/TransformControls.js';
import { PointerLockControls } from './vendor/PointerLockControls.js';
import { Sky } from './vendor/Sky.js';
import { M, CATALOG, PALMS, BROADLEAF } from './models.js';
import * as T from './textures.js';

const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const IMG_W = 804, IMG_H = 922;
const STORE = 'vrukshali-twin-v1';
const DEG = Math.PI / 180;

/* ------------------------------------------------------------------ */
/* persistence & scale                                                */
/* ------------------------------------------------------------------ */
let stored = null;
try { stored = JSON.parse(localStorage.getItem(STORE)); } catch { stored = null; }
let S = stored?.S ?? 0.3; // metres per satellite pixel (calibrate with the measure tool)
const W = IMG_W * S, H = IMG_H * S;
const px2w = (px, py) => [(px - IMG_W / 2) * S, (py - IMG_H / 2) * S];
const w2px = (x, z) => [x / S + IMG_W / 2, z / S + IMG_H / 2];
$('brandSub').textContent = `Telavadi · satellite-aligned · ${S.toFixed(3)} m/px`;

// Gentle hillside on the dry grassland to the west; the resort itself is flat.
function heightAt(x, z) {
  const [px, py] = w2px(x, z);
  const a = clamp((290 - px) / 290, 0, 1);
  if (a <= 0) return 0;
  const b = smooth(330, 540, py);
  const n = Math.sin(px * 0.031) * Math.cos(py * 0.023);
  return (Math.pow(a, 1.35) * 15 + n * a * 2.5) * b;
}

/* ------------------------------------------------------------------ */
/* renderer, cameras, controls                                        */
/* ------------------------------------------------------------------ */
const canvas = $('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, stencil: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.85;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();

const persp = new THREE.PerspectiveCamera(45, 1, 0.3, 8000);
const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -2000, 4000);
const walkCam = new THREE.PerspectiveCamera(70, 1, 0.1, 8000);
let camera = persp, view = 'orbit';

const orbit = new OrbitControls(persp, canvas);
orbit.enableDamping = true; orbit.dampingFactor = 0.08;
orbit.maxPolarAngle = 1.5; orbit.minDistance = 2; orbit.maxDistance = 800;
orbit.zoomToCursor = true;

const ORTHO_H = 320;
ortho.up.set(0, 0, -1);
const plan = new OrbitControls(ortho, canvas);
plan.enableRotate = false; plan.screenSpacePanning = true; plan.zoomToCursor = true;
plan.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
plan.minZoom = 0.4; plan.maxZoom = 20;
plan.enabled = false;

const walk = new PointerLockControls(walkCam, document.body);
const keys = {};

function resize() {
  const w = innerWidth, h = innerHeight, a = w / h;
  renderer.setSize(w, h);
  persp.aspect = walkCam.aspect = a;
  persp.updateProjectionMatrix(); walkCam.updateProjectionMatrix();
  Object.assign(ortho, { left: (-ORTHO_H * a) / 2, right: (ORTHO_H * a) / 2, top: ORTHO_H / 2, bottom: -ORTHO_H / 2 });
  ortho.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

/* ------------------------------------------------------------------ */
/* sky, sun, fog                                                      */
/* ------------------------------------------------------------------ */
const sky = new Sky();
sky.scale.setScalar(20000);
scene.add(sky);
const U = sky.material.uniforms;
U.turbidity.value = 4.5; U.rayleigh.value = 1.1; U.mieCoefficient.value = 0.004; U.mieDirectionalG.value = 0.82;
const skyScene = new THREE.Scene();
const skyEnv = new Sky(); skyEnv.scale.setScalar(10000); skyEnv.material = sky.material; skyScene.add(skyEnv);
const pmrem = new THREE.PMREMGenerator(renderer);
let envRT = null;

const sun = new THREE.DirectionalLight('#fff3df', 3);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -140, right: 140, top: 140, bottom: -140, near: 1, far: 900 });
sun.shadow.bias = -0.0002; sun.shadow.normalBias = 0.06;
scene.add(sun, sun.target);
const hemi = new THREE.HemisphereLight('#e4eeff', '#cbb88f', 0.9);
const moon = new THREE.DirectionalLight('#8fa8ff', 0);
moon.position.set(-200, 300, -100);
scene.add(hemi, moon);
scene.fog = new THREE.Fog('#e6e3d8', 500, 3000);

const lampLights = Array.from({ length: 10 }, () => {
  const l = new THREE.PointLight('#ffc477', 0, 16, 2);
  scene.add(l);
  return l;
});

let dayF = 1, timeH = 10.5;
const sunDir = new THREE.Vector3();
function setTime(h, env = true) {
  timeH = h;
  const th = (Math.PI * (h - 6.1)) / 12.2;
  sunDir.set(Math.cos(th), Math.sin(th) * 0.95, 0.4 * Math.max(0.25, Math.sin(th))).normalize();
  U.sunPosition.value.copy(sunDir);
  dayF = smooth(-0.06, 0.2, sunDir.y);
  const warm = 1 - smooth(0.05, 0.45, sunDir.y);
  sun.color.setRGB(1, 0.95 - warm * 0.3, 0.88 - warm * 0.5);
  sun.intensity = 3.0 * smooth(0, 0.18, sunDir.y);
  hemi.intensity = 0.12 + 0.9 * dayF;
  moon.intensity = 0.35 * (1 - dayF);
  renderer.toneMappingExposure = 0.6 + 0.35 * dayF;
  const fog = new THREE.Color('#1a2232').lerp(new THREE.Color('#e3b88e'), smooth(-0.05, 0.08, sunDir.y)).lerp(new THREE.Color('#e6e3d8'), smooth(0.08, 0.4, sunDir.y));
  scene.fog.color.copy(fog);
  M.lampGlass.emissiveIntensity = (1 - dayF) * 4;
  M.water.emissiveIntensity = 0.25 + (1 - dayF) * 1.4;
  const names = [[6.5, 'Dawn'], [8.5, 'Golden hour'], [11.5, 'Morning'], [15, 'Midday'], [17, 'Afternoon'], [18.4, 'Golden hour'], [19.2, 'Dusk'], [99, 'Night']];
  const hh = Math.floor(h), mm = Math.round((h - hh) * 60) % 60;
  $('timeLbl').textContent = `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')} · ${names.find(([t]) => h < t)[1]}`;
  $('sunIc').textContent = dayF > 0.5 ? (sunDir.y < 0.3 ? '🌅' : '☀️') : '🌙';
  if (env) updateEnv();
}
let envTimer = 0;
function updateEnv() {
  clearTimeout(envTimer);
  envTimer = setTimeout(() => {
    envRT?.dispose();
    envRT = pmrem.fromScene(skyScene);
    // reflections only on shiny surfaces; global env lighting washes out the flat-shaded look
    for (const m of [M.water, M.steel, M.glass]) { m.envMap = envRT.texture; m.needsUpdate = true; }
  }, 60);
}

/* ------------------------------------------------------------------ */
/* ground from the satellite image                                    */
/* ------------------------------------------------------------------ */
const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = 'assets/satellite.webp'; });
const satCanvas = document.createElement('canvas');
satCanvas.width = IMG_W; satCanvas.height = IMG_H;
const satCtx = satCanvas.getContext('2d', { willReadFrequently: true });
satCtx.drawImage(img, 0, 0, IMG_W, IMG_H);
// The screenshot carries a Google Maps pin and place label. Clone nearby ground over both.
satCtx.drawImage(satCanvas, 496, 388, 280, 80, 496, 468, 280, 80);
satCtx.drawImage(satCanvas, 438, 370, 64, 92, 438, 460, 64, 92);
const pix = satCtx.getImageData(0, 0, IMG_W, IMG_H).data;
function sample(px, py, r = 1) {
  let R = 0, G = 0, B = 0, n = 0;
  for (let dy = -r; dy <= r; dy++)
    for (let dx = -r; dx <= r; dx++) {
      const x = clamp(Math.round(px + dx), 0, IMG_W - 1), y = clamp(Math.round(py + dy), 0, IMG_H - 1);
      const i = (y * IMG_W + x) * 4;
      R += pix[i]; G += pix[i + 1]; B += pix[i + 2]; n++;
    }
  return [R / n, G / n, B / n];
}
// border colour, used for the surrounding land so the imagery fades in seamlessly
const edge = [0, 0, 0];
for (let i = 0; i < 200; i++) {
  const t = i / 200, c = [sample(t * IMG_W, 2, 2), sample(t * IMG_W, IMG_H - 3, 2), sample(2, t * IMG_H, 2), sample(IMG_W - 3, t * IMG_H, 2)];
  for (const s of c) { edge[0] += s[0] / 800; edge[1] += s[1] / 800; edge[2] += s[2] / 800; }
}
const edgeColor = new THREE.Color().setRGB(edge[0] / 255, edge[1] / 255, edge[2] / 255, THREE.SRGBColorSpace);

const satTex = new THREE.CanvasTexture(satCanvas);
satTex.colorSpace = THREE.SRGBColorSpace; satTex.anisotropy = 8;
const detailTex = T.grassDetail();
const STENCIL = { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.NotEqualStencilFunc };
const SAND = new THREE.Color('#ece2c8');
const groundMat = new THREE.MeshStandardMaterial({ map: satTex, roughness: 1, ...STENCIL });
groundMat.onBeforeCompile = (sh) => {
  sh.uniforms.detailMap = { value: detailTex };
  sh.uniforms.detailRep = { value: new THREE.Vector2(W / 2.5, H / 2.5) };
  sh.uniforms.edgeCol = groundMat.userData.edgeCol = { value: SAND.clone() };
  sh.uniforms.satOn = groundMat.userData.satOn = { value: 0 };
  sh.fragmentShader = sh.fragmentShader
    .replace('#include <common>', '#include <common>\nuniform sampler2D detailMap; uniform vec2 detailRep; uniform vec3 edgeCol; uniform float satOn;')
    .replace('#include <map_fragment>', `#include <map_fragment>
      float d = texture2D(detailMap, vMapUv * detailRep).r;
      // classify the photo into a soft map palette: dry soil, crops, canopy, paved
      vec3 sc = pow(max(diffuseColor.rgb, 0.0), vec3(1.0 / 2.2));
      float lum = dot(sc, vec3(0.3, 0.59, 0.11)), gr = sc.g - sc.r;
      float sat = max(sc.r, max(sc.g, sc.b)) - min(sc.r, min(sc.g, sc.b));
      float canopy = (1.0 - smoothstep(0.2, 0.34, lum)) * smoothstep(-0.05, 0.02, gr);
      float crop = smoothstep(-0.01, 0.05, gr) * (1.0 - canopy);
      float paved = (1.0 - smoothstep(0.035, 0.09, sat)) * smoothstep(0.3, 0.5, lum) * (1.0 - canopy);
      vec3 st = vec3(0.93, 0.88, 0.77);
      st = mix(st, vec3(0.80, 0.87, 0.67), crop);
      st = mix(st, vec3(0.63, 0.79, 0.56), canopy);
      st = mix(st, vec3(0.87, 0.86, 0.83), paved);
      st *= 0.94 + 0.12 * smoothstep(0.15, 0.7, lum);
      vec3 stylised = pow(st, vec3(2.2));
      diffuseColor.rgb = mix(stylised, diffuseColor.rgb, satOn);
      diffuseColor.rgb *= mix(1.0, d * 2.0, mix(0.1, 0.28, satOn));
      float e = smoothstep(0.0, 0.05, min(min(vMapUv.x, 1.0 - vMapUv.x), min(vMapUv.y, 1.0 - vMapUv.y)));
      diffuseColor.rgb = mix(edgeCol, diffuseColor.rgb, e);`);
};
const gGeo = new THREE.PlaneGeometry(W, H, 200, 230);
gGeo.rotateX(-Math.PI / 2);
{
  const p = gGeo.attributes.position;
  for (let i = 0; i < p.count; i++) p.setY(i, heightAt(p.getX(i), p.getZ(i)));
  gGeo.computeVertexNormals();
}
const ground = new THREE.Mesh(gGeo, groundMat);
ground.receiveShadow = true;
scene.add(ground);
const outer = new THREE.Mesh(new THREE.PlaneGeometry(9000, 9000), new THREE.MeshStandardMaterial({ color: SAND, roughness: 1, ...STENCIL }));
outer.rotation.x = -Math.PI / 2; outer.position.y = -0.06; outer.receiveShadow = true;
scene.add(outer);

// Western Ghats on the horizon
{
  const hills = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: '#7d8f7a', roughness: 1, flatShading: true });
  let s = 7;
  const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 70; i++) {
    const a = r() * Math.PI * 2, d = 1400 + r() * 1300;
    const m = new THREE.Mesh(new THREE.ConeGeometry(160 + r() * 260, 70 + r() * 190, 6 + Math.floor(r() * 4)), mat);
    m.position.set(Math.cos(a) * d, -10, Math.sin(a) * d); m.rotation.y = r() * 3; m.scale.z = 0.6 + r() * 0.8;
    hills.add(m);
  }
  scene.add(hills);
}

/* ------------------------------------------------------------------ */
/* roads                                                              */
/* ------------------------------------------------------------------ */
function ribbon(ptsW, width, mat, { lift = 0.05, tile = 4, offset = 0, closed = false } = {}) {
  if (ptsW.length < 2) return null;
  const curve = new THREE.CatmullRomCurve3(ptsW.map(([x, z]) => new THREE.Vector3(x, 0, z)), closed, 'centripetal');
  const len = curve.getLength(), n = Math.max(2, Math.ceil(len / 1.2));
  const pts = curve.getSpacedPoints(n);
  const pos = [], uv = [], idx = [];
  for (let i = 0; i <= n; i++) {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(n, i + 1)];
    const tx = b.x - a.x, tz = b.z - a.z, tl = Math.hypot(tx, tz) || 1;
    const nx = -tz / tl, nz = tx / tl;
    for (const s of [-1, 1]) {
      const x = pts[i].x + nx * (offset + (s * width) / 2), z = pts[i].z + nz * (offset + (s * width) / 2);
      pos.push(x, heightAt(x, z) + lift, z);
      uv.push(s < 0 ? 0 : width / tile, (i / n) * (len / tile));
    }
    if (i < n) { const k = i * 2; idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, mat);
  m.receiveShadow = true;
  m.userData.samples = pts;
  m.userData.length = len;
  return m;
}
const ROADS = {
  main: { w: 7, px: [[318, -60], [345, 0], [372, 120], [410, 260], [440, 380], [462, 480], [482, 548], [522, 600], [582, 660], [650, 728], [720, 790], [800, 858], [880, 920]] },
  lane: { w: 4.5, px: [[476, 552], [420, 572], [360, 594], [286, 618]] },
  farm: { w: 3.5, px: [[436, 262], [520, 258], [600, 248], [650, 240]] },
};
const roadRoot = new THREE.Group();
scene.add(roadRoot);
const asphalt = new THREE.MeshStandardMaterial({ map: T.asphalt(), roughness: 0.9 });
const shoulderMat = new THREE.MeshStandardMaterial({ color: '#9b8466', roughness: 1 });
const lineMat = new THREE.MeshStandardMaterial({ color: '#f2f0e6', roughness: 0.7 });
const roadSamples = [];
for (const [k, r] of Object.entries(ROADS)) {
  const pts = r.px.map(([a, b]) => px2w(a, b));
  if (k === 'main') {
    roadRoot.add(ribbon(pts, r.w + 3, shoulderMat, { lift: 0.04 }));
    const m = ribbon(pts, r.w, asphalt, { lift: 0.07, tile: 6 });
    roadRoot.add(m);
    roadSamples.push({ pts: m.userData.samples, w: r.w });
    for (const s of [-1, 1]) roadRoot.add(ribbon(pts, 0.15, lineMat, { lift: 0.08, offset: s * (r.w / 2 - 0.3) }));
  } else {
    const m = ribbon(pts, r.w, k === 'lane' ? M.concrete : M.gravel, { lift: 0.06, tile: 3 });
    roadRoot.add(m);
    roadSamples.push({ pts: m.userData.samples, w: r.w });
  }
}
function distToRoads(x, z) {
  let best = Infinity;
  for (const r of roadSamples) for (const p of r.pts) best = Math.min(best, Math.hypot(p.x - x, p.z - z) - r.w / 2);
  return best;
}

/* ------------------------------------------------------------------ */
/* existing trees, derived from the satellite canopy                  */
/* ------------------------------------------------------------------ */
const treeRoot = new THREE.Group();
scene.add(treeRoot);
const trees = [];
// The plot spans both sides of the entrance lane: the villa block to the north and the camp to the south.
const DEFAULT_BOUNDARY_PX = [[138, 288], [396, 284], [424, 400], [444, 482], [462, 548], [505, 600], [560, 655], [625, 728], [690, 800], [740, 875], [712, 918], [330, 918], [305, 850], [282, 760], [275, 680], [268, 620], [205, 540], [140, 430]];
const V1_BOUNDARY_START_PX = [288, 628];
// villa runs north-south on the top tier, facing east onto the pool
const VILLA_PX = [173, 348], POOL_PX = [209, 349];
{
  let s = 4242;
  const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const STEP = 4.6;
  for (let z = -H / 2 + 2; z < H / 2 - 2; z += STEP)
    for (let x = -W / 2 + 2; x < W / 2 - 2; x += STEP) {
      const jx = x + (r() - 0.5) * STEP * 0.9, jz = z + (r() - 0.5) * STEP * 0.9;
      const [px, py] = w2px(jx, jz);
      const [R, G, B] = sample(px, py, 1);
      const lum = 0.3 * R + 0.59 * G + 0.11 * B;
      const fields = px > 476 && py < 530;
      const dry = px < 285 && py > 380;
      let tree = false;
      if (dry) tree = lum < 105 && r() < 0.18;
      else if (fields) tree = lum < 52 && G >= R * 0.95;
      else tree = lum < 78 && G >= R * 0.92 && r() < 0.8;
      if (!tree) continue;
      if (distToRoads(jx, jz) < 3) continue;
      const plantation = !dry && !fields;
      const palm = plantation ? r() < 0.82 : r() < 0.3;
      trees.push({ x: jx, z: jz, palm, v: Math.floor(r() * 3), s: (palm ? 0.85 : 0.7) + r() * 0.35, rot: r() * Math.PI * 2 });
    }
  const groups = {};
  for (const t of trees) (groups[`${t.palm ? 'p' : 'b'}${t.v}`] ||= []).push(t);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), v3 = new THREE.Vector3(), sc = new THREE.Vector3();
  for (const [key, list] of Object.entries(groups)) {
    const geo = (key[0] === 'p' ? PALMS : BROADLEAF)[+key[1]];
    const ti = new THREE.InstancedMesh(geo.trunk, M.bark, list.length);
    const ci = new THREE.InstancedMesh(geo.crown, key[0] === 'p' ? M.frondI : M.leavesI, list.length);
    const col = new THREE.Color();
    list.forEach((t, i) => {
      q.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, t.rot);
      t.matrix = m4.compose(v3.set(t.x, heightAt(t.x, t.z), t.z), q, sc.setScalar(t.s)).clone();
      ti.setMatrixAt(i, t.matrix); ci.setMatrixAt(i, t.matrix);
      ci.setColorAt(i, col.setHSL((key[0] === 'p' ? 0.29 : 0.3) + (r() - 0.5) * 0.06, 0.36 + r() * 0.14, (key[0] === 'p' ? 0.43 : 0.5) + (r() - 0.5) * 0.1, THREE.SRGBColorSpace));
      t.ims = [ti, ci]; t.i = i;
    });
    for (const im of [ti, ci]) { im.castShadow = true; im.receiveShadow = true; im.frustumCulled = false; treeRoot.add(im); }
  }
}
const ZERO = new THREE.Matrix4().makeScale(0, 0, 0);

/* ------------------------------------------------------------------ */
/* layout model                                                       */
/* ------------------------------------------------------------------ */
let uid = 1;
const nid = () => `i${Date.now().toString(36)}${(uid++).toString(36)}`;
function defaultLayout() {
  const it = (type, px, py, rot = 0, name) => { const [x, z] = px2w(px, py); return { id: nid(), type, x, z, rot: rot * DEG, ...(name ? { name } : {}) }; };
  const path = (pxs, width = 2, surface = 'gravel', lamps = true) => ({ id: nid(), pts: pxs.map(([a, b]) => px2w(a, b)), width, surface, lamps });
  return {
    v: 2, S,
    footprints: [],
    boundary: DEFAULT_BOUNDARY_PX.map(([a, b]) => px2w(a, b)),
    items: [
      it('gate', 446, 593, 200, 'Main gate'),
      it('reception', 418, 622, 190),
      it('parking', 352, 628, 18),
      it('courtyard', 452, 652, 0, 'Arrival courtyard'),
      it('bench', 430, 670, 0), it('bench', 474, 670, 0),
      it('villa', ...VILLA_PX, 90, 'Brick pool villa'),
      it('pool', ...POOL_PX, 90),
      it('dining', 440, 712, 0, 'Dining pavilion'),
      it('tent', 492, 706, -35, 'Tent cottage 1'),
      it('tent', 518, 742, -40, 'Tent cottage 2'),
      it('tent', 545, 778, -45, 'Tent cottage 3'),
      it('tent', 486, 784, 10, 'Tent cottage 4'),
      it('flowerbed', 478, 730, -35), it('flowerbed', 506, 765, -40),
      it('cottage', 318, 772, 10, 'Cottage A'),
      it('cottage', 354, 808, 5, 'Cottage B'),
      it('cottage', 398, 834, 0, 'Cottage C'),
      it('hammock', 585, 828, 30, 'Hammock grove'), it('hammock', 600, 846, 35), it('hammock', 572, 852, 28),
      it('firepit', 336, 868, 0, 'Campfire circle'),
      it('dome', 306, 846, 30), it('dome', 300, 884, 70), it('dome', 326, 900, 120), it('dome', 365, 895, 160),
      it('gazebo', 450, 870, 0, 'Yoga gazebo'),
      it('court', 612, 888, 35, 'Volleyball court'),
    ],
    paths: [
      path([[446, 600], [448, 635], [452, 668], [468, 700], [498, 728], [528, 760], [556, 800], [585, 840]], 2.4, 'pavers'),
      path([[452, 668], [420, 690], [400, 715], [395, 745], [372, 775], [372, 805], [410, 830], [450, 862], [400, 878], [350, 868]], 2, 'gravel'),
      path([[468, 700], [470, 760], [486, 776]], 1.6, 'gravel'),
    ],
    notes: [
      { id: nid(), ...Object.fromEntries([['x', px2w(232, 720)[0]], ['z', px2w(232, 720)[1]]]), text: 'Sunset viewpoint deck on the hillside? Clear line of sight west over the valley.' },
      { id: nid(), ...Object.fromEntries([['x', px2w(630, 790)[0]], ['z', px2w(630, 790)[1]]]), text: 'Road noise: plant a bamboo screen along the highway edge.' },
    ],
  };
}
let layout = stored?.items ? stored : defaultLayout();
layout.footprints ||= [];
if ((layout.v || 1) < 2) {
  // v1 had the villa and pool south of the lane; move them to where they really are
  const set = (type, [px, py]) => { const r = layout.items.find((i) => i.type === type); if (r) { [r.x, r.z] = px2w(px, py); r.rot = 90 * DEG; } };
  set('villa', VILLA_PX);
  set('pool', POOL_PX);
  const b0 = px2w(...V1_BOUNDARY_START_PX);
  if (layout.boundary?.length === 12 && Math.hypot(layout.boundary[0][0] - b0[0], layout.boundary[0][1] - b0[1]) < 0.5) layout.boundary = DEFAULT_BOUNDARY_PX.map(([a, b]) => px2w(a, b));
  layout.v = 2;
  try { localStorage.setItem(STORE, JSON.stringify(layout)); } catch { /* storage blocked */ }
}
layout.S = S;

/* ------------------------------------------------------------------ */
/* history & saving                                                   */
/* ------------------------------------------------------------------ */
const undoStack = [], redoStack = [];
function snapshot() { return JSON.stringify(layout); }
function pushHistory(prev = snapshot()) { undoStack.push(prev); if (undoStack.length > 80) undoStack.shift(); redoStack.length = 0; }
let saveTimer;
function save() {
  $('saved').textContent = 'Saving…';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(STORE, JSON.stringify(layout)); $('saved').textContent = 'Saved'; }
    catch { $('saved').textContent = 'Not saved (storage blocked)'; }
  }, 250);
}
function undo() { if (!undoStack.length) return toast('Nothing to undo'); redoStack.push(snapshot()); layout = JSON.parse(undoStack.pop()); afterLoad(); }
function redo() { if (!redoStack.length) return toast('Nothing to redo'); undoStack.push(snapshot()); layout = JSON.parse(redoStack.pop()); afterLoad(); }
function afterLoad() { layout.footprints ||= []; layout.notes ||= []; if (!find(selectedId)) select(null); rebuildAll(); save(); }
function commit(prev) { pushHistory(prev); rebuildAll(); save(); }
const find = (id) => id && (layout.items.find((i) => i.id === id) || layout.paths.find((p) => p.id === id) || layout.notes.find((n) => n.id === id) || layout.footprints.find((f) => f.id === id));
const kindOf = (id) => (layout.items.some((i) => i.id === id) ? 'item' : layout.paths.some((p) => p.id === id) ? 'path' : layout.notes.some((n) => n.id === id) ? 'note' : layout.footprints.some((f) => f.id === id) ? 'footprint' : null);

/* ------------------------------------------------------------------ */
/* building the scene from the layout                                 */
/* ------------------------------------------------------------------ */
const itemsRoot = new THREE.Group(), pathsRoot = new THREE.Group(), notesRoot = new THREE.Group(), boundaryRoot = new THREE.Group(), fpRoot = new THREE.Group();
scene.add(fpRoot);
const fpWall = new THREE.MeshStandardMaterial({ color: '#efe7d6', roughness: 0.9, flatShading: true });
const fpRoof = new THREE.MeshStandardMaterial({ color: '#c8704b', roughness: 0.85, flatShading: true });
// Detected footprints (e.g. from Microsoft MARS GeoJSON): extruded blocks you can keep, delete or swap for a catalog model.
function buildFootprint(rec) {
  if (!rec.pts || rec.pts.length < 3) return;
  const shape = new THREE.Shape(rec.pts.map(([x, z]) => new THREE.Vector2(x, -z)));
  let m;
  if (rec.kind === 'water') {
    m = new THREE.Mesh(new THREE.ShapeGeometry(shape), M.water);
    m.rotation.x = -Math.PI / 2;
    m.position.y = 0.2;
  } else {
    const geo = new THREE.ExtrudeGeometry(shape, { depth: rec.height || 3.5, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2);
    m = new THREE.Mesh(geo, [fpRoof, fpWall]);
    m.castShadow = m.receiveShadow = true;
    const [cx, cz] = centroid(rec.pts);
    m.position.y = heightAt(cx, cz);
  }
  m.userData.id = rec.id;
  fpRoot.add(m);
  objs.set(rec.id, m);
}
const centroid = (pts) => pts.reduce((a, [x, z]) => [a[0] + x / pts.length, a[1] + z / pts.length], [0, 0]);
scene.add(itemsRoot, pathsRoot, notesRoot, boundaryRoot);
const objs = new Map();
let lampSpots = [];
const PATH_MATS = { gravel: M.gravel, pavers: M.pavers, laterite: M.laterite };

function clearGroup(g) { while (g.children.length) g.remove(g.children[0]); }
function buildItem(rec) {
  const def = CATALOG[rec.type];
  if (!def) return;
  const g = def.build();
  g.position.set(rec.x, heightAt(rec.x, rec.z), rec.z);
  g.rotation.y = rec.rot || 0;
  g.traverse((o) => (o.userData.id = rec.id));
  itemsRoot.add(g);
  objs.set(rec.id, g);
  if (rec.type === 'lamp') lampSpots.push(new THREE.Vector3(rec.x, heightAt(rec.x, rec.z) + 2.8, rec.z));
  if (rec.type === 'gate') for (const s of [-1, 1]) lampSpots.push(new THREE.Vector3(rec.x + Math.cos(rec.rot) * 3.4 * s, 3.6, rec.z - Math.sin(rec.rot) * 3.4 * s));
}
function buildPath(rec) {
  const g = new THREE.Group();
  const m = ribbon(rec.pts, rec.width, PATH_MATS[rec.surface] || M.gravel, { lift: 0.09, tile: 1.6 });
  if (!m) return;
  g.add(m);
  for (const s of [-1, 1]) g.add(ribbon(rec.pts, 0.16, M.laterite, { lift: 0.14, offset: s * (rec.width / 2 + 0.08), tile: 0.6 }));
  if (rec.lamps) {
    const pts = m.userData.samples, len = m.userData.length;
    const every = 12, n = Math.floor(len / every);
    for (let k = 0; k <= n; k++) {
      const i = Math.min(pts.length - 1, Math.round(((k * every + 3) / len) * (pts.length - 1)));
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
      if (!a || !b) continue;
      const tl = Math.hypot(b.x - a.x, b.z - a.z) || 1, side = k % 2 ? 1 : -1;
      const x = pts[i].x + (-(b.z - a.z) / tl) * side * (rec.width / 2 + 0.6), z = pts[i].z + ((b.x - a.x) / tl) * side * (rec.width / 2 + 0.6);
      const l = CATALOG.lamp.build();
      l.position.set(x, heightAt(x, z), z);
      g.add(l);
      lampSpots.push(new THREE.Vector3(x, heightAt(x, z) + 2.8, z));
    }
  }
  g.traverse((o) => (o.userData.id = rec.id));
  g.userData.samples = m.userData.samples;
  g.userData.length = m.userData.length;
  pathsRoot.add(g);
  objs.set(rec.id, g);
}
function buildNote(rec) {
  const g = new THREE.Group();
  const y = heightAt(rec.x, rec.z);
  const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 3, 6), new THREE.MeshStandardMaterial({ color: '#c9962f' }));
  stick.position.y = 1.5;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.45, 12, 8), new THREE.MeshStandardMaterial({ color: '#e8b730', emissive: '#7a5200', emissiveIntensity: 0.4 }));
  head.position.y = 3.2;
  g.add(stick, head);
  g.position.set(rec.x, y, rec.z);
  g.traverse((o) => (o.userData.id = rec.id));
  notesRoot.add(g);
  objs.set(rec.id, g);
}

const boundaryMat = new THREE.MeshBasicMaterial({ color: '#ffd84a', transparent: true, opacity: 0.95, depthWrite: false });
const boundaryFill = new THREE.MeshBasicMaterial({ color: '#7cff9a', transparent: true, opacity: 0.08, depthWrite: false, side: THREE.DoubleSide });
const handleMat = new THREE.MeshBasicMaterial({ color: '#ffffff' });
const handleMidMat = new THREE.MeshBasicMaterial({ color: '#ffd84a', transparent: true, opacity: 0.7 });
let handles = [];
function rebuildBoundary() {
  clearGroup(boundaryRoot);
  handles = [];
  const b = layout.boundary;
  if (!b || b.length < 3) return;
  const loop = [...b, b[0]];
  for (let i = 0; i < b.length; i++) {
    const strip = ribbon([loop[i], loop[i + 1]], 0.7, boundaryMat, { lift: 0.35, tile: 1 });
    strip.renderOrder = 3; strip.receiveShadow = false;
    boundaryRoot.add(strip);
  }
  const shape = new THREE.Shape(b.map(([x, z]) => new THREE.Vector2(x, -z)));
  const fill = new THREE.Mesh(new THREE.ShapeGeometry(shape), boundaryFill);
  fill.rotation.x = -Math.PI / 2; fill.position.y = 0.3; fill.renderOrder = 2;
  boundaryRoot.add(fill);
  if (tool === 'boundary' && !redrawing) {
    b.forEach(([x, z], i) => {
      const h = new THREE.Mesh(new THREE.SphereGeometry(1.1, 14, 10), handleMat);
      h.position.set(x, heightAt(x, z) + 0.8, z); h.userData.vertex = i;
      boundaryRoot.add(h); handles.push(h);
      const [nx, nz] = b[(i + 1) % b.length];
      const m = new THREE.Mesh(new THREE.SphereGeometry(0.7, 10, 8), handleMidMat);
      m.position.set((x + nx) / 2, 0.8, (z + nz) / 2); m.userData.insertAfter = i;
      boundaryRoot.add(m); handles.push(m);
    });
  }
}

function rebuildAll() {
  clearGroup(itemsRoot); clearGroup(pathsRoot); clearGroup(notesRoot); clearGroup(fpRoot);
  objs.clear();
  lampSpots = [];
  layout.items.forEach(buildItem);
  layout.paths.forEach(buildPath);
  layout.notes.forEach(buildNote);
  layout.footprints.forEach(buildFootprint);
  rebuildBoundary();
  updateClearance();
  rebuildLabels();
  updateKPIs();
  reattach();
  renderInspector();
}

/* --- clear existing trees under buildings and paths --- */
function insideFootprint(rec, x, z, margin) {
  const def = CATALOG[rec.type];
  if (!def || def.small || def.tree) return false;
  const dx = x - rec.x, dz = z - rec.z, c = Math.cos(rec.rot || 0), s = Math.sin(rec.rot || 0);
  const lx = dx * c - dz * s, lz = dx * s + dz * c;
  return Math.abs(lx) < def.w / 2 + margin && Math.abs(lz) < def.d / 2 + margin;
}
function pointInPoly(x, z, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, zi] = poly[i], [xj, zj] = poly[j];
    if (zi > z !== zj > z && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}
const polyArea = (p) => Math.abs(p.reduce((a, [x, z], i) => { const [nx, nz] = p[(i + 1) % p.length]; return a + x * nz - nx * z; }, 0)) / 2;
const polyLen = (p, closed) => p.reduce((a, [x, z], i) => (i === p.length - 1 && !closed ? a : a + Math.hypot(p[(i + 1) % p.length][0] - x, p[(i + 1) % p.length][1] - z)), 0);
let treesKept = 0, canopyInPlot = 0;
function updateClearance() {
  const touched = new Set();
  treesKept = 0; canopyInPlot = 0;
  const pathSamples = [...pathsRoot.children].map((g) => ({ pts: g.userData.samples, w: find(g.userData.id ?? g.children[0]?.userData.id)?.width ?? 2 }));
  for (const t of trees) {
    let hide = layout.items.some((r) => insideFootprint(r, t.x, t.z, CATALOG[r.type].built ? 2.8 : 1.2)) || layout.footprints.some((f) => pointInPoly(t.x, t.z, f.pts));
    if (!hide)
      for (const p of pathSamples) {
        if (!p.pts) continue;
        for (let i = 0; i < p.pts.length; i += 2) if (Math.hypot(p.pts[i].x - t.x, p.pts[i].z - t.z) < p.w / 2 + 0.7) { hide = true; break; }
        if (hide) break;
      }
    if (t.hidden !== hide) {
      t.hidden = hide;
      for (const im of t.ims) { im.setMatrixAt(t.i, hide ? ZERO : t.matrix); touched.add(im); }
    }
    if (!hide && layout.boundary && pointInPoly(t.x, t.z, layout.boundary)) { treesKept++; canopyInPlot += t.palm ? 16 * t.s * t.s : 24 * t.s * t.s; }
  }
  touched.forEach((im) => (im.instanceMatrix.needsUpdate = true));
}

/* ------------------------------------------------------------------ */
/* labels                                                             */
/* ------------------------------------------------------------------ */
const labelRoot = $('labels');
let labels = [];
const CONTEXT = [
  { px: [405, 230], text: 'Main road · towards Telavadi' },
  { px: [660, 360], text: 'Neighbouring farmland' },
  { px: [140, 640], text: 'Dry hillside' },
  { px: [300, 450], text: 'Coconut grove' },
  { px: [478, 545], text: 'Junction · resort turn-off' },
];
function rebuildLabels() {
  labelRoot.innerHTML = '';
  labels = [];
  const add = (cls, html, pos, id) => {
    const el = document.createElement('div');
    el.className = `lbl ${cls}`;
    el.innerHTML = html;
    labelRoot.appendChild(el);
    labels.push({ el, pos, id, cls });
    if (id) el.onclick = () => { select(id); setTool('select'); };
    return el;
  };
  for (const c of CONTEXT) { const [x, z] = px2w(...c.px); add('ctx', c.text, new THREE.Vector3(x, heightAt(x, z) + 3, z)); }
  for (const r of layout.items) {
    const def = CATALOG[r.type];
    if (def.small || def.tree || r.type === 'flowerbed' || r.type === 'bench') continue;
    if (!r.name && !['villa', 'reception', 'dining'].includes(r.type)) continue;
    add('', r.name || def.name, new THREE.Vector3(r.x, heightAt(r.x, r.z) + (def.built ? 8 : 4), r.z), r.id);
  }
  for (const n of layout.notes) add('note', escapeHtml(n.text), new THREE.Vector3(n.x, heightAt(n.x, n.z) + 4.4, n.z), n.id);
  for (const f of layout.footprints) if (f.name) { const [x, z] = centroid(f.pts); add('', escapeHtml(f.name), new THREE.Vector3(x, heightAt(x, z) + (f.height || 3.5) + 3, z), f.id); }
  for (const m of measureLabels) labels.push(m);
}
const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const proj = new THREE.Vector3();
function updateLabels() {
  const show = layerOn.labels && view !== 'walk';
  for (const l of labels) {
    if (!show && l.cls !== 'measure') { l.el.style.display = 'none'; continue; }
    proj.copy(l.pos).project(camera);
    const dist = camera.position.distanceTo(l.pos);
    const zoomedOut = camera === ortho ? ortho.zoom < 1.6 : persp.position.distanceTo(orbit.target) > 240;
    const off = proj.z > 1 || Math.abs(proj.x) > 1.1 || Math.abs(proj.y) > 1.1 ||
      (l.cls === 'ctx' && !zoomedOut) || (l.cls === '' && camera === persp && dist > 330 && l.id !== selectedId);
    if (off) { l.el.style.display = 'none'; continue; }
    l.el.style.display = '';
    l.el.classList.toggle('sel', !!l.id && l.id === selectedId);
    l.el.style.transform = `translate(${((proj.x + 1) / 2) * innerWidth}px, ${((-proj.y + 1) / 2) * innerHeight}px) translate(-50%, -100%)`;
  }
}

/* ------------------------------------------------------------------ */
/* tools: select, add, path, measure, boundary, note                  */
/* ------------------------------------------------------------------ */
let tool = 'select', selectedId = null, addType = 'tent', ghost = null, ghostRot = 0, redrawing = false;
let draft = []; // points for path / measure / boundary redraw
const draftRoot = new THREE.Group();
scene.add(draftRoot);
let measureLabels = [];

const gizmo = new TransformControls(persp, canvas);
gizmo.showY = false; gizmo.setSize(0.85);
scene.add(gizmo);
let dragPrev = null;
gizmo.addEventListener('dragging-changed', (e) => {
  orbit.enabled = !e.value && view === 'orbit';
  plan.enabled = !e.value && view === 'plan';
  if (e.value) dragPrev = snapshot();
  else if (dragPrev) {
    const g = gizmo.object, rec = find(selectedId);
    if (g && rec) {
      rec.x = g.position.x; rec.z = g.position.z;
      if (kindOf(selectedId) === 'item') rec.rot = g.rotation.y;
      commit(dragPrev);
    }
    dragPrev = null;
  }
});
gizmo.addEventListener('objectChange', () => {
  const g = gizmo.object;
  if (!g) return;
  g.position.y = heightAt(g.position.x, g.position.z);
  drawOutline();
});
function reattach() {
  gizmo.detach();
  const k = kindOf(selectedId);
  if (tool === 'select' && (k === 'item' || k === 'note') && view !== 'walk') gizmo.attach(objs.get(selectedId));
  if (k === 'note') gizmo.setMode('translate');
  drawOutline();
}

const outline = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: '#ffd84a', depthTest: false, transparent: true }));
outline.renderOrder = 10;
scene.add(outline);
function rectPts(x, z, w, d, rot) {
  const c = Math.cos(rot), s = Math.sin(rot);
  return [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]].map(([lx, lz]) => new THREE.Vector3(x + lx * c + lz * s, heightAt(x, z) + 0.25, z - lx * s + lz * c));
}
function drawOutline() {
  let pts = [];
  if (tool === 'add' && ghost) {
    const def = CATALOG[addType];
    pts = rectPts(ghost.position.x, ghost.position.z, def.w, def.d, ghostRot);
    const ok = !layout.boundary || pointInPoly(ghost.position.x, ghost.position.z, layout.boundary);
    outline.material.color.set(ok ? '#7cff9a' : '#ff6b5a');
  } else if (selectedId && kindOf(selectedId) === 'item') {
    const g = objs.get(selectedId), def = CATALOG[find(selectedId).type];
    if (g) pts = rectPts(g.position.x, g.position.z, def.w, def.d, g.rotation.y);
    outline.material.color.set('#ffd84a');
  }
  outline.geometry.setFromPoints(pts);
  outline.visible = pts.length > 0;
}

function select(id) {
  selectedId = id;
  reattach();
  renderInspector();
}

function setTool(t) {
  if (tool === 'boundary' || t === 'boundary') { tool = t; redrawing = false; rebuildBoundary(); }
  tool = t;
  draft = []; drawDraft();
  if (ghost) { scene.remove(ghost); ghost = null; }
  if (t !== 'measure') { measureLabels.forEach((l) => l.el.remove()); measureLabels = []; rebuildLabels(); }
  document.querySelectorAll('.tool').forEach((b) => b.classList.toggle('on', b.dataset.tool === t));
  $('catalog').classList.toggle('show', t === 'add');
  if (t === 'add') makeGhost();
  if (t !== 'select') selectedId = null;
  reattach();
  renderInspector();
}
function makeGhost() {
  if (ghost) scene.remove(ghost);
  ghost = CATALOG[addType].build();
  ghost.traverse((o) => { if (o.isMesh) { o.castShadow = false; } });
  ghost.rotation.y = ghostRot;
  ghost.visible = false;
  scene.add(ghost);
  document.querySelectorAll('.cat').forEach((c) => c.classList.toggle('on', c.dataset.type === addType));
}

// draft visuals (path / measure / boundary redraw)
const draftMat = new THREE.MeshBasicMaterial({ color: '#1d1e22', transparent: true, opacity: 0.85, depthWrite: false });
const dotMat = new THREE.MeshBasicMaterial({ color: '#ffffff' });
let hoverPt = null;
function drawDraft() {
  clearGroup(draftRoot);
  const pts = hoverPt && draft.length ? [...draft, hoverPt] : draft;
  if (pts.length >= 2) {
    const closed = tool === 'boundary' || (tool === 'measure' && pts.length >= 3);
    const loop = closed ? [...pts, pts[0]] : pts;
    for (let i = 0; i < loop.length - 1; i++) {
      const s = ribbon([loop[i], loop[i + 1]], tool === 'path' ? currentPathWidth : 0.35, tool === 'path' ? M.gravel : draftMat, { lift: tool === 'path' ? 0.12 : 0.4, tile: 1.6 });
      if (tool !== 'path') s.renderOrder = 5;
      draftRoot.add(s);
    }
  }
  for (const [x, z] of draft) {
    const d = new THREE.Mesh(new THREE.SphereGeometry(0.5, 10, 8), dotMat);
    d.position.set(x, heightAt(x, z) + 0.5, z);
    draftRoot.add(d);
  }
  if (tool === 'measure') updateMeasureLabels(pts);
}
function updateMeasureLabels(pts) {
  measureLabels.forEach((l) => l.el.remove());
  measureLabels = [];
  const mk = (text, x, z) => {
    const el = document.createElement('div');
    el.className = 'lbl measure'; el.textContent = text;
    labelRoot.appendChild(el);
    measureLabels.push({ el, pos: new THREE.Vector3(x, heightAt(x, z) + 1.5, z), cls: 'measure' });
  };
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, az] = pts[i], [bx, bz] = pts[i + 1];
    mk(`${Math.hypot(bx - ax, bz - az).toFixed(1)} m`, (ax + bx) / 2, (az + bz) / 2);
  }
  labels = labels.filter((l) => l.cls !== 'measure').concat(measureLabels);
  renderInspector();
}

/* --- picking --- */
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
function setRay(e) {
  ndc.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(ndc, camera);
}
function groundHit(e) {
  setRay(e);
  const h = ray.intersectObject(ground, false)[0];
  if (h) return [h.point.x, h.point.z];
  const p = new THREE.Vector3();
  return ray.ray.intersectPlane(groundPlane, p) ? [p.x, p.z] : null;
}
function pickObject(e) {
  setRay(e);
  const hits = ray.intersectObjects([...itemsRoot.children, ...pathsRoot.children, ...notesRoot.children, ...fpRoot.children], true);
  for (const h of hits) if (h.object.userData.id && h.object.visible && h.object.material !== M.poolMask) return h.object.userData.id;
  return hits[0]?.object.userData.id ?? null;
}

let down = null, dragVertex = null, vertexPrev = null;
canvas.addEventListener('pointerdown', (e) => {
  if (view === 'walk') return;
  down = { x: e.clientX, y: e.clientY };
  if (tool === 'boundary' && !redrawing && e.button === 0) {
    setRay(e);
    const h = ray.intersectObjects(handles, false)[0];
    if (h) {
      vertexPrev = snapshot();
      if (h.object.userData.insertAfter !== undefined) {
        const i = h.object.userData.insertAfter;
        layout.boundary.splice(i + 1, 0, [h.object.position.x, h.object.position.z]);
        dragVertex = i + 1;
      } else dragVertex = h.object.userData.vertex;
      orbit.enabled = plan.enabled = false;
    }
  }
});
canvas.addEventListener('pointermove', (e) => {
  if (view === 'walk') return;
  if (dragVertex !== null) {
    const p = groundHit(e);
    if (p) { layout.boundary[dragVertex] = p; rebuildBoundary(); renderInspector(); }
    return;
  }
  if (tool === 'add' && ghost) {
    const p = groundHit(e);
    if (p) { ghost.visible = true; ghost.position.set(p[0], heightAt(p[0], p[1]), p[1]); drawOutline(); }
  }
  if ((tool === 'path' || tool === 'measure' || (tool === 'boundary' && redrawing)) && draft.length) {
    hoverPt = groundHit(e);
    drawDraft();
  }
});
canvas.addEventListener('pointerup', (e) => {
  if (view === 'walk' || !down) return;
  const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
  down = null;
  if (dragVertex !== null) {
    dragVertex = null;
    orbit.enabled = view === 'orbit'; plan.enabled = view === 'plan';
    commit(vertexPrev);
    return;
  }
  if (moved > 5 || e.button !== 0 || gizmo.dragging || gizmo.axis) return;
  const p = groundHit(e);
  if (tool === 'select') {
    select(pickObject(e));
  } else if (tool === 'add' && p) {
    const prev = snapshot();
    const rec = { id: nid(), type: addType, x: p[0], z: p[1], rot: ghostRot };
    layout.items.push(rec);
    commit(prev);
    toast(`Placed ${CATALOG[addType].name}`);
    if (!e.shiftKey) { setTool('select'); select(rec.id); }
  } else if ((tool === 'path' || tool === 'measure' || (tool === 'boundary' && redrawing)) && p) {
    draft.push(p);
    drawDraft();
  } else if (tool === 'note' && p) {
    const prev = snapshot();
    const rec = { id: nid(), x: p[0], z: p[1], text: 'New note' };
    layout.notes.push(rec);
    commit(prev);
    setTool('select');
    select(rec.id);
    setTimeout(() => $('noteText')?.select(), 30);
  }
});
canvas.addEventListener('dblclick', () => { if (tool === 'path' || (tool === 'boundary' && redrawing)) finishDraft(); });
let currentPathWidth = 2, currentPathSurface = 'gravel', currentPathLamps = true;
function finishDraft() {
  hoverPt = null;
  // a double-click also registers two clicks; drop duplicated end points
  draft = draft.filter((p, i) => i === 0 || Math.hypot(p[0] - draft[i - 1][0], p[1] - draft[i - 1][1]) > 0.5);
  if (tool === 'path' && draft.length >= 2) {
    const prev = snapshot();
    const rec = { id: nid(), pts: draft, width: currentPathWidth, surface: currentPathSurface, lamps: currentPathLamps };
    layout.paths.push(rec);
    draft = [];
    commit(prev);
    toast(`Path added · ${polyLen(rec.pts).toFixed(0)} m`);
    setTool('select'); select(rec.id);
  } else if (tool === 'boundary' && draft.length >= 3) {
    const prev = snapshot();
    layout.boundary = draft;
    draft = []; redrawing = false;
    commit(prev);
    toast(`Boundary set · ${(polyArea(layout.boundary) / 4046.86).toFixed(2)} acres`);
  }
  drawDraft();
}

/* ------------------------------------------------------------------ */
/* inspector & metrics                                                */
/* ------------------------------------------------------------------ */
const fmt = (n, d = 0) => n.toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d });
function renderInspector() {
  const el = $('inspector');
  const rec = find(selectedId), k = kindOf(selectedId);
  if (tool === 'select' && rec && k === 'item') {
    const def = CATALOG[rec.type];
    el.innerHTML = `
      <div class="title"><span class="ic">${def.icon}</span><div><div class="eyebrow">${def.name}</div><input type="text" id="iName" value="${escapeHtml(rec.name || '')}" placeholder="Name this ${def.name.toLowerCase()}"/></div></div>
      <div class="row"><span class="k">Position</span><span class="v">${rec.x.toFixed(1)}, ${rec.z.toFixed(1)} m</span></div>
      <div class="row"><span class="k">Rotation</span><span class="v"><input type="number" id="iRot" value="${Math.round(((rec.rot || 0) / DEG + 360) % 360)}" style="width:64px;text-align:right;font:inherit;border:1px solid var(--border);border-radius:6px;padding:2px 4px"/>°</span></div>
      <div class="row"><span class="k">Footprint</span><span class="v">${def.w} × ${def.d} m · ${fmt(def.w * def.d)} m²</span></div>
      ${def.guests ? `<div class="row"><span class="k">Sleeps</span><span class="v">${def.guests} guests · ${def.keys} key${def.keys > 1 ? 's' : ''}</span></div>` : ''}
      <div class="row"><span class="k">Rough cost</span><span class="v">₹${fmt(def.cost, def.cost < 1 ? 2 : 0)} L</span></div>
      <div class="row"><span class="k">Inside plot</span><span class="v">${pointInPoly(rec.x, rec.z, layout.boundary) ? 'Yes' : '<span style="color:#b5532f">No</span>'}</span></div>
      <div class="btns">
        <button class="btn ${gizmo.mode === 'translate' ? 'on' : ''}" id="iMove">Move <span class="faint">T</span></button>
        <button class="btn ${gizmo.mode === 'rotate' ? 'on' : ''}" id="iRotate">Rotate <span class="faint">R</span></button>
        <button class="btn" id="iFocus">Focus</button>
        <button class="btn" id="iDup">Duplicate</button>
        <button class="btn danger" id="iDel">Delete</button>
      </div>`;
    $('iName').onchange = (e) => { const prev = snapshot(); rec.name = e.target.value.trim(); commit(prev); };
    $('iRot').onchange = (e) => { const prev = snapshot(); rec.rot = (+e.target.value || 0) * DEG; commit(prev); };
    $('iMove').onclick = () => { setGizmoMode('translate'); };
    $('iRotate').onclick = () => { setGizmoMode('rotate'); };
    $('iFocus').onclick = () => focusOn(rec.x, rec.z, Math.max(def.w, def.d) * 2.2 + 12);
    $('iDup').onclick = duplicate;
    $('iDel').onclick = deleteSelected;
  } else if (tool === 'select' && rec && k === 'path') {
    el.innerHTML = `
      <div class="title"><span class="ic">🥾</span><div><div class="eyebrow">Garden path</div><b>${fmt(polyLen(rec.pts))} m long</b></div></div>
      <div class="row"><span class="k">Width</span><span class="v"><select id="pW">${[1.2, 1.6, 2, 2.4, 3, 4].map((w) => `<option ${w === rec.width ? 'selected' : ''}>${w}</option>`).join('')}</select></span></div>
      <div class="row"><span class="k">Surface</span><span class="v"><select id="pS">${['gravel', 'pavers', 'laterite'].map((s) => `<option ${s === rec.surface ? 'selected' : ''}>${s}</option>`).join('')}</select></span></div>
      <div class="row"><span class="k">Lamps every 12 m</span><span class="v"><input type="checkbox" id="pL" ${rec.lamps ? 'checked' : ''}/></span></div>
      <div class="row"><span class="k">Area</span><span class="v">${fmt(polyLen(rec.pts) * rec.width)} m²</span></div>
      <div class="btns"><button class="btn danger" id="iDel">Delete path</button></div>`;
    $('pW').onchange = (e) => { const prev = snapshot(); rec.width = +e.target.value; commit(prev); };
    $('pS').onchange = (e) => { const prev = snapshot(); rec.surface = e.target.value; commit(prev); };
    $('pL').onchange = (e) => { const prev = snapshot(); rec.lamps = e.target.checked; commit(prev); };
    $('iDel').onclick = deleteSelected;
  } else if (tool === 'select' && rec && k === 'footprint') {
    const area = polyArea(rec.pts);
    const built = Object.entries(CATALOG).filter(([, d]) => d.built || d.hard);
    el.innerHTML = `
      <div class="title"><span class="ic">${rec.kind === 'water' ? '💧' : '🧱'}</span><div><div class="eyebrow">Detected ${rec.kind}${rec.source ? ` · ${escapeHtml(rec.source)}` : ''}</div><input type="text" id="iName" value="${escapeHtml(rec.name || '')}" placeholder="Name it (e.g. staff quarters)"/></div></div>
      <div class="row"><span class="k">Footprint</span><span class="v">${fmt(area)} m²</span></div>
      ${rec.conf != null ? `<div class="row"><span class="k">Model confidence</span><span class="v">${Math.round(rec.conf * (rec.conf <= 1 ? 100 : 1))}%</span></div>` : ''}
      ${rec.kind !== 'water' ? `<div class="row"><span class="k">Height</span><span class="v"><input type="number" id="fH" value="${rec.height || 3.5}" step="0.5" style="width:64px;text-align:right;font:inherit;border:1px solid var(--border);border-radius:6px;padding:2px 4px"/> m</span></div>` : ''}
      <div class="row"><span class="k">Replace with</span><span class="v"><select id="fSwap"><option value="">choose…</option>${built.map(([k2, d]) => `<option value="${k2}">${d.icon} ${d.name}</option>`).join('')}</select></span></div>
      <div class="help" style="margin-top:6px">Swapping drops the catalog model on this footprint, aligned to its longest wall.</div>
      <div class="btns"><button class="btn" id="iFocus">Focus</button><button class="btn danger" id="iDel">Delete</button></div>`;
    $('iName').onchange = (e) => { const prev = snapshot(); rec.name = e.target.value.trim(); commit(prev); };
    if ($('fH')) $('fH').onchange = (e) => { const prev = snapshot(); rec.height = Math.max(0.5, +e.target.value || 3.5); commit(prev); };
    $('fSwap').onchange = (e) => {
      if (!e.target.value) return;
      const prev = snapshot();
      const [cx, cz] = centroid(rec.pts);
      let best = 0, rot = 0;
      rec.pts.forEach(([x, z], i) => { const [nx, nz] = rec.pts[(i + 1) % rec.pts.length], l = Math.hypot(nx - x, nz - z); if (l > best) { best = l; rot = -Math.atan2(nz - z, nx - x); } });
      const item = { id: nid(), type: e.target.value, x: cx, z: cz, rot, ...(rec.name ? { name: rec.name } : {}) };
      layout.items.push(item);
      layout.footprints.splice(layout.footprints.indexOf(rec), 1);
      commit(prev);
      select(item.id);
    };
    $('iFocus').onclick = () => { const [x, z] = centroid(rec.pts); focusOn(x, z, Math.sqrt(area) * 3 + 20); };
    $('iDel').onclick = deleteSelected;
  } else if (tool === 'select' && rec && k === 'note') {
    el.innerHTML = `
      <div class="title"><span class="ic">📌</span><div class="eyebrow">Note</div></div>
      <textarea id="noteText">${escapeHtml(rec.text)}</textarea>
      <div class="btns"><button class="btn" id="iFocus">Focus</button><button class="btn danger" id="iDel">Delete note</button></div>`;
    let prev = null;
    $('noteText').onfocus = () => (prev = snapshot());
    $('noteText').oninput = (e) => { rec.text = e.target.value; const l = labels.find((x) => x.id === rec.id); if (l) l.el.textContent = rec.text; save(); };
    $('noteText').onblur = () => { if (prev && prev !== snapshot()) pushHistory(prev); };
    $('iFocus').onclick = () => focusOn(rec.x, rec.z, 40);
    $('iDel').onclick = deleteSelected;
  } else if (tool === 'add') {
    const def = CATALOG[addType];
    el.innerHTML = `<div class="title"><span class="ic">${def.icon}</span><div><div class="eyebrow">Placing</div><b>${def.name}</b></div></div>
      <div class="row"><span class="k">Footprint</span><span class="v">${def.w} × ${def.d} m</span></div>
      ${def.guests ? `<div class="row"><span class="k">Sleeps</span><span class="v">${def.guests}</span></div>` : ''}
      <div class="help" style="margin-top:6px">Green outline = inside the plot. Existing trees under the footprint are cleared automatically.</div>`;
  } else if (tool === 'path') {
    el.innerHTML = `<div class="eyebrow">Draw a path</div>
      <div class="help">Click to add points along the route. <kbd>Enter</kbd> or double-click to finish, <kbd>Backspace</kbd> removes the last point, <kbd>Esc</kbd> cancels.</div>
      <div class="row" style="margin-top:8px"><span class="k">Width</span><span class="v"><select id="dW">${[1.2, 1.6, 2, 2.4, 3, 4].map((w) => `<option ${w === currentPathWidth ? 'selected' : ''}>${w}</option>`).join('')}</select> m</span></div>
      <div class="row"><span class="k">Surface</span><span class="v"><select id="dS">${['gravel', 'pavers', 'laterite'].map((s) => `<option ${s === currentPathSurface ? 'selected' : ''}>${s}</option>`).join('')}</select></span></div>
      <div class="row"><span class="k">Lamp posts</span><span class="v"><input type="checkbox" id="dL" ${currentPathLamps ? 'checked' : ''}/></span></div>
      <div class="row"><span class="k">Length so far</span><span class="v">${fmt(polyLen(draft), 1)} m</span></div>`;
    $('dW').onchange = (e) => { currentPathWidth = +e.target.value; drawDraft(); };
    $('dS').onchange = (e) => (currentPathSurface = e.target.value);
    $('dL').onchange = (e) => (currentPathLamps = e.target.checked);
  } else if (tool === 'measure') {
    const pts = hoverPt && draft.length ? [...draft, hoverPt] : draft;
    const total = polyLen(pts), area = pts.length >= 3 ? polyArea(pts) : 0;
    el.innerHTML = `<div class="eyebrow">Measure</div>
      <div class="help">Click points on the ground. Three or more points also give the enclosed area. <kbd>Esc</kbd> clears.</div>
      <div class="row" style="margin-top:8px"><span class="k">Distance</span><span class="v">${fmt(total, 1)} m</span></div>
      <div class="row"><span class="k">Area</span><span class="v">${area ? `${fmt(area)} m² · ${(area / 4046.86).toFixed(3)} ac` : '—'}</span></div>
      <div class="eyebrow" style="margin-top:12px">Calibrate scale</div>
      <div class="help">Measure something you know (a road width, a building) and enter its real length. The whole twin rescales to match.</div>
      <div class="btns"><input type="number" id="calIn" placeholder="real metres" step="0.1" style="width:110px;border:1px solid var(--border);border-radius:8px;padding:5px 8px;font:inherit"/><button class="btn primary" id="calBtn" ${draft.length < 2 ? 'disabled' : ''}>Apply</button></div>`;
    $('calBtn').onclick = () => {
      const real = +$('calIn').value, measured = polyLen(draft);
      if (!real || !measured) return toast('Measure a distance and enter its real length');
      calibrate(real / measured);
    };
  } else if (tool === 'boundary') {
    const b = layout.boundary || [];
    el.innerHTML = `<div class="eyebrow">Plot boundary</div>
      <div class="row"><span class="k">Area</span><span class="v">${fmt(polyArea(b))} m²</span></div>
      <div class="row"><span class="k"></span><span class="v">${(polyArea(b) / 4046.86).toFixed(2)} acres · ${(polyArea(b) / 10000).toFixed(2)} ha</span></div>
      <div class="row"><span class="k">Perimeter</span><span class="v">${fmt(polyLen(b, true))} m</span></div>
      <div class="help" style="margin-top:6px">${redrawing ? 'Click the corners of the plot in order. <kbd>Enter</kbd> to close it.' : 'Drag the white corners to adjust. Drag a yellow midpoint to add a corner. Alt-click a corner to remove it.'}</div>
      <div class="btns"><button class="btn" id="bRedraw">${redrawing ? 'Cancel redraw' : 'Redraw from scratch'}</button></div>`;
    $('bRedraw').onclick = () => { redrawing = !redrawing; draft = []; drawDraft(); rebuildBoundary(); renderInspector(); };
  } else if (tool === 'note') {
    el.innerHTML = `<div class="eyebrow">Notes</div><div class="help">Click anywhere to drop a note: ideas, problems, things to check on the next site visit.</div>`;
  } else {
    el.innerHTML = `<div class="eyebrow">Welcome</div>
      <div class="help">This is a 1:1 model of the resort built from the satellite image, with every structure from your photos. Click anything to select it, or use the tools on the left to plan changes.</div>
      <div class="help" style="margin-top:8px"><kbd>1</kbd> orbit · <kbd>2</kbd> plan · <kbd>3</kbd> walk &nbsp; <kbd>Ctrl Z</kbd> undo</div>`;
  }
}
function updateKPIs() {
  const plot = layout.boundary?.length >= 3 ? polyArea(layout.boundary) : 0;
  let keys = 0, guests = 0, built = 0, hard = 0, cost = 0;
  for (const r of layout.items) {
    const d = CATALOG[r.type];
    keys += d.keys || 0; guests += d.guests || 0; cost += d.cost || 0;
    if (d.built) built += d.w * d.d; else if (d.hard) hard += d.w * d.d;
  }
  for (const f of layout.footprints) if (f.kind !== 'water') built += polyArea(f.pts);
  let pathLen = 0, pathArea = 0;
  for (const p of layout.paths) { const l = polyLen(p.pts); pathLen += l; pathArea += l * p.width; cost += (l * p.width * (p.surface === 'pavers' ? 1800 : p.surface === 'laterite' ? 1400 : 600)) / 1e5; }
  hard += pathArea;
  const lamps = lampSpots.length;
  const green = plot ? Math.min(100, (canopyInPlot / plot) * 100) : 0;
  const cov = plot ? (built / plot) * 100 : 0;
  $('kpis').innerHTML = `
    <div class="kpi"><div class="k">Plot</div><div class="v">${(plot / 4046.86).toFixed(2)}<small> ac</small></div><div class="k">${fmt(plot)} m²</div></div>
    <div class="kpi"><div class="k">Rooms · guests</div><div class="v">${keys}<small> keys</small> ${guests}</div><div class="k">at full occupancy</div></div>
    <div class="kpi"><div class="k">Built-up</div><div class="v">${cov.toFixed(1)}<small>%</small></div><div class="meter"><i style="width:${Math.min(100, cov * 4)}%;background:${cov > 20 ? 'var(--terra)' : 'var(--green)'}"></i></div><div class="k">${fmt(built)} m² of plot</div></div>
    <div class="kpi"><div class="k">Canopy cover</div><div class="v">${green.toFixed(0)}<small>%</small></div><div class="meter"><i style="width:${green}%"></i></div><div class="k">${fmt(treesKept)} trees kept</div></div>
    <div class="kpi"><div class="k">Paths · lamps</div><div class="v">${fmt(pathLen)}<small> m</small></div><div class="k">${lamps} lamp posts</div></div>
    <div class="kpi"><div class="k">Rough capex</div><div class="v">₹${fmt(cost)}<small> L</small></div><div class="k">indicative only</div></div>`;
}

/* --- actions --- */
function setGizmoMode(m) { gizmo.setMode(m); gizmo.showX = gizmo.showZ = m === 'translate'; gizmo.showY = m === 'rotate'; renderInspector(); }
setGizmoMode('translate');
function deleteSelected() {
  const k = kindOf(selectedId);
  if (!k) return;
  const prev = snapshot();
  const arr = { item: layout.items, path: layout.paths, note: layout.notes, footprint: layout.footprints }[k];
  arr.splice(arr.findIndex((r) => r.id === selectedId), 1);
  selectedId = null;
  commit(prev);
  toast('Deleted · Ctrl+Z to undo');
}
function duplicate() {
  const rec = find(selectedId);
  if (!rec || kindOf(selectedId) !== 'item') return;
  const prev = snapshot();
  const def = CATALOG[rec.type];
  const copy = { ...rec, id: nid(), x: rec.x + def.w + 2, name: rec.name ? `${rec.name} (copy)` : undefined };
  layout.items.push(copy);
  commit(prev);
  select(copy.id);
}
function rotateSelected(deg) {
  const rec = find(selectedId);
  if (!rec || kindOf(selectedId) !== 'item') return;
  const prev = snapshot();
  rec.rot = (rec.rot || 0) + deg * DEG;
  commit(prev);
}
function calibrate(f) {
  const scale = (p) => [p[0] * f, p[1] * f];
  layout.boundary = layout.boundary.map(scale);
  layout.items.forEach((r) => { r.x *= f; r.z *= f; });
  layout.paths.forEach((p) => (p.pts = p.pts.map(scale)));
  layout.notes.forEach((n) => { n.x *= f; n.z *= f; });
  layout.S = S * f;
  try { localStorage.setItem(STORE, JSON.stringify(layout)); } catch { return toast('Storage is blocked, so calibration cannot be saved'); }
  toast(`Rescaled to ${layout.S.toFixed(3)} m/px. Reloading…`);
  setTimeout(() => location.reload(), 700);
}

/* ------------------------------------------------------------------ */
/* views & camera                                                     */
/* ------------------------------------------------------------------ */
let fly = null;
function focusOn(x, z, dist = 60) {
  if (view === 'plan') { plan.target.set(x, 0, z); ortho.position.set(x, 500, z); ortho.zoom = clamp(ORTHO_H / (dist * 1.6), 0.4, 20); ortho.updateProjectionMatrix(); return; }
  if (view !== 'orbit') setView('orbit');
  const dir = persp.position.clone().sub(orbit.target).normalize();
  const to = new THREE.Vector3(x, heightAt(x, z), z);
  fly = { t: 0, p0: persp.position.clone(), t0: orbit.target.clone(), p1: to.clone().addScaledVector(dir, dist), t1: to };
}
function setView(v) {
  if (v === view) return;
  if (document.pointerLockElement) walk.unlock();
  const focus = view === 'walk' ? walkCam.position.clone() : view === 'plan' ? plan.target.clone() : orbit.target.clone();
  view = v;
  document.querySelectorAll('.seg').forEach((b) => b.classList.toggle('on', b.dataset.view === v));
  orbit.enabled = v === 'orbit';
  plan.enabled = v === 'plan';
  if (v === 'orbit') {
    camera = persp;
    orbit.target.set(focus.x, heightAt(focus.x, focus.z), focus.z);
    if (persp.position.distanceTo(orbit.target) > 400 || persp.position.y < 2) persp.position.copy(orbit.target).add(new THREE.Vector3(40, 60, 90));
  } else if (v === 'plan') {
    camera = ortho;
    plan.target.set(focus.x, 0, focus.z);
    ortho.position.set(focus.x, 500, focus.z);
    ortho.lookAt(focus.x, 0, focus.z);
  } else {
    camera = walkCam;
    walkCam.position.set(focus.x, heightAt(focus.x, focus.z) + 1.65, focus.z);
    walkCam.rotation.set(0, Math.atan2(persp.position.x - orbit.target.x, persp.position.z - orbit.target.z), 0, 'YXZ');
    if (view === 'walk') hideOverlay();
  }
  gizmo.camera = camera;
  $('crosshair').style.display = v === 'walk' ? 'block' : 'none';
  $('walkHint').style.display = v === 'walk' ? 'block' : 'none';
  ['tools', 'catalog', 'side'].forEach((id) => ($(id).style.visibility = v === 'walk' ? 'hidden' : ''));
  reattach();
}
canvas.addEventListener('click', () => { if (view === 'walk' && !document.pointerLockElement) walk.lock(); });
walk.addEventListener('lock', () => ($('walkHint').style.display = 'none'));
walk.addEventListener('unlock', () => { if (view === 'walk') $('walkHint').style.display = 'block'; });

/* ------------------------------------------------------------------ */
/* UI wiring                                                          */
/* ------------------------------------------------------------------ */
$('catGrid').innerHTML = Object.entries(CATALOG).map(([k, d]) => `<button class="cat" data-type="${k}"><span class="ic">${d.icon}</span>${d.name}<span class="dim">${d.w}×${d.d} m</span></button>`).join('');
document.querySelectorAll('.cat').forEach((b) => (b.onclick = () => { addType = b.dataset.type; makeGhost(); renderInspector(); }));
document.querySelectorAll('.tool').forEach((b) => (b.onclick = () => setTool(b.dataset.tool)));
document.querySelectorAll('.seg').forEach((b) => (b.onclick = () => setView(b.dataset.view)));
$('timeIn').oninput = (e) => setTime(+e.target.value);

const layerOn = { satellite: false, trees: true, boundary: true, labels: true, paths: true };
document.querySelectorAll('[data-layer]').forEach((c) => (c.onchange = () => {
  layerOn[c.dataset.layer] = c.checked;
  if (groundMat.userData.satOn) {
    groundMat.userData.satOn.value = layerOn.satellite ? 1 : 0;
    groundMat.userData.edgeCol.value.copy(layerOn.satellite ? edgeColor : SAND);
  }
  outer.material.color.copy(layerOn.satellite ? edgeColor : SAND);
  treeRoot.visible = layerOn.trees;
  boundaryRoot.visible = layerOn.boundary;
  pathsRoot.visible = layerOn.paths;
}));

$('bUndo').onclick = undo;
$('bRedo').onclick = redo;
$('bExport').onclick = () => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(layout, null, 2)], { type: 'application/json' }));
  a.download = `vrukshali-layout-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
$('bImport').onclick = () => $('fileIn').click();
$('fileIn').onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const data = JSON.parse(await f.text());
    if (data.type === 'FeatureCollection' || data.type === 'Feature') { importGeoJSON(data, f.name); e.target.value = ''; return; }
    if (!Array.isArray(data.items) || !Array.isArray(data.paths)) throw new Error('not a layout');
    data.footprints ||= [];
    data.notes ||= [];
    pushHistory();
    layout = data;
    if (data.S && Math.abs(data.S - S) > 1e-6) { localStorage.setItem(STORE, JSON.stringify(layout)); location.reload(); return; }
    afterLoad();
    toast(`Loaded ${f.name}`);
  } catch { toast('That file is not a Vrukshali layout'); }
  e.target.value = '';
};
// GeoJSON from Microsoft MARS (or any GIS tool): buildings, roads, railways and water bodies.
// Coordinates may be lon/lat (needs the image centre, since the screenshot is north-up at a known
// scale) or image pixels (a CRS named "image-pixels", or values outside lon/lat range).
function importGeoJSON(data, fname) {
  const feats = data.type === 'Feature' ? [data] : data.features || [];
  const firstCoord = (g) => { let c = g?.coordinates; while (Array.isArray(c?.[0])) c = c[0]; return c; };
  const c0 = firstCoord(feats.find((f) => f.geometry)?.geometry);
  if (!c0) return toast('No geometries found in that GeoJSON');
  const crsName = String(data.crs?.properties?.name || '').toLowerCase();
  const pixels = crsName.includes('pixel') || Math.abs(c0[0]) > 180 || Math.abs(c0[1]) > 90;
  if (!pixels && !layout.geo) {
    const ans = prompt('These detections are in latitude/longitude. Enter the latitude, longitude of the centre of the satellite image (right-click that spot in Google Maps to copy it):', '');
    const m = ans && ans.match(/(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)/);
    if (!m) return toast('Import cancelled: the image centre is needed to place lat/lon data');
    layout.geo = { lat: +m[1], lon: +m[2] };
  }
  const toW = pixels ? ([x, y]) => px2w(x, y) : ([lon, lat]) => [(lon - layout.geo.lon) * 111320 * Math.cos(layout.geo.lat * DEG), -(lat - layout.geo.lat) * 110574];
  const ring = (r) => { const pts = r.map(toW); const a = pts[0], b = pts[pts.length - 1]; if (a && b && a[0] === b[0] && a[1] === b[1]) pts.pop(); return pts; };
  const prev = snapshot();
  let nb = 0, nw = 0, nr = 0;
  for (const f of feats) {
    const g = f.geometry, pr = f.properties || {};
    if (!g) continue;
    const cat = String(pr.category ?? pr.class ?? pr.label ?? pr.type ?? pr.name ?? '').toLowerCase();
    const conf = pr.confidence ?? pr.score ?? pr.probability;
    const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
    for (const p of polys) {
      const water = /water|pond|lake|pool|tank|river/.test(cat);
      layout.footprints.push({ id: nid(), kind: water ? 'water' : 'building', pts: ring(p[0]), height: +pr.height || (water ? 0 : 3.5), conf, source: pr.source || 'MARS' });
      water ? nw++ : nb++;
    }
    const lines = g.type === 'LineString' ? [g.coordinates] : g.type === 'MultiLineString' ? g.coordinates : [];
    for (const l of lines) {
      const rail = /rail/.test(cat);
      layout.paths.push({ id: nid(), pts: l.map(toW), width: +pr.width || (rail ? 3 : 4), surface: rail ? 'gravel' : 'laterite', lamps: false });
      nr++;
    }
  }
  commit(prev);
  toast(`Imported ${nb} buildings, ${nr} roads, ${nw} water bodies from ${fname}`);
}
$('bReset').onclick = () => {
  if (!confirm('Restore the default layout? Your current layout stays in undo history.')) return;
  pushHistory();
  layout = defaultLayout();
  afterLoad();
};
$('bShot').onclick = () => {
  renderer.render(scene, camera);
  const a = document.createElement('a');
  a.href = canvas.toDataURL('image/png');
  a.download = `vrukshali-${view}-${Date.now()}.png`;
  a.click();
};

/* --- reference photos --- */
const PHOTOS = [
  { src: 'assets/photo-tent.webp', type: 'tent', eye: [-5.5, 1.6, 11.5], look: [1.2, 2.8, 1.5], fov: 62 },
  { src: 'assets/photo-pool.webp', type: 'pool', eye: [-7.2, 1.5, 6.8], look: [1.5, 1.2, -4.5], fov: 66 },
  { src: 'assets/photo-courtyard.webp', type: 'courtyard', eye: [4.5, 1.6, 7.5], look: [-1.5, 1.0, -2], fov: 70 },
  { src: 'assets/photo-hammock.webp', type: 'hammock', eye: [0, 1.4, 4.2], look: [0, 1.4, -3], fov: 70 },
];
let activePhoto = -1;
$('thumbs').innerHTML = PHOTOS.map((p, i) => `<button class="thumb" data-i="${i}"><img src="${p.src}" alt=""/></button>`).join('');
document.querySelectorAll('.thumb').forEach((b) => (b.onclick = () => showPhoto(+b.dataset.i)));
function showPhoto(i) {
  if (activePhoto === i) return hideOverlay();
  const p = PHOTOS[i], rec = layout.items.find((r) => r.type === p.type);
  if (!rec) return toast(`There is no ${CATALOG[p.type].name.toLowerCase()} in the layout`);
  activePhoto = i;
  setView('orbit');
  const c = Math.cos(rec.rot || 0), s = Math.sin(rec.rot || 0), y = heightAt(rec.x, rec.z);
  const local = ([lx, ly, lz]) => new THREE.Vector3(rec.x + lx * c + lz * s, y + ly, rec.z - lx * s + lz * c);
  fly = { t: 0, p0: persp.position.clone(), t0: orbit.target.clone(), p1: local(p.eye), t1: local(p.look), fov: p.fov };
  $('overlay').src = p.src;
  $('compareRow').classList.add('show');
  $('compareIn').value = 35;
  $('overlay').style.opacity = 0.35;
  document.querySelectorAll('.thumb').forEach((b) => b.classList.toggle('on', +b.dataset.i === i));
}
function hideOverlay() {
  activePhoto = -1;
  $('overlay').style.opacity = 0;
  $('compareRow').classList.remove('show');
  document.querySelectorAll('.thumb').forEach((b) => b.classList.remove('on'));
  if (persp.fov !== 45) { persp.fov = 45; persp.updateProjectionMatrix(); }
}
$('compareIn').oninput = (e) => ($('overlay').style.opacity = e.target.value / 100);

/* --- keyboard --- */
addEventListener('keydown', (e) => {
  if (e.target.matches('input, textarea, select')) return;
  keys[e.code] = true;
  const k = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); redo(); return; }
  if ((e.ctrlKey || e.metaKey) && k === 'd') { e.preventDefault(); duplicate(); return; }
  if (view === 'walk' && ['w', 'a', 's', 'd'].includes(k)) return;
  if (k === '1') setView('orbit');
  else if (k === '2') setView('plan');
  else if (k === '3') setView('walk');
  else if (k === 'v') setTool('select');
  else if (k === 'a') setTool('add');
  else if (k === 'p') setTool('path');
  else if (k === 'm') setTool('measure');
  else if (k === 'b') setTool('boundary');
  else if (k === 'n') setTool('note');
  else if (k === 't') setGizmoMode('translate');
  else if (k === 'r') setGizmoMode('rotate');
  else if (k === 'q' || k === 'e') {
    const d = k === 'q' ? 15 : -15;
    if (tool === 'add' && ghost) { ghostRot += d * DEG; ghost.rotation.y = ghostRot; drawOutline(); }
    else rotateSelected(d);
  } else if (k === 'enter') finishDraft();
  else if (k === 'escape') {
    if (activePhoto >= 0) hideOverlay();
    else if (draft.length) { draft = []; hoverPt = null; drawDraft(); }
    else if (tool !== 'select') setTool('select');
    else select(null);
  } else if (k === 'delete' || k === 'backspace') {
    if (draft.length) { draft.pop(); drawDraft(); }
    else deleteSelected();
  }
});
addEventListener('keyup', (e) => (keys[e.code] = false));
// alt-click a boundary corner removes it
canvas.addEventListener('pointerdown', (e) => {
  if (tool !== 'boundary' || !e.altKey || redrawing || layout.boundary.length <= 3) return;
  setRay(e);
  const h = ray.intersectObjects(handles, false)[0];
  if (h && h.object.userData.vertex !== undefined) {
    dragVertex = null;
    const prev = snapshot();
    layout.boundary.splice(h.object.userData.vertex, 1);
    commit(prev);
  }
}, true);

let toastT;
function toast(msg) { const t = $('toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2200); }

/* ------------------------------------------------------------------ */
/* main loop                                                          */
/* ------------------------------------------------------------------ */
const clk = new THREE.Clock();
const focus = new THREE.Vector3();
let frame = 0;
function tick() {
  requestAnimationFrame(tick);
  const dt = Math.min(clk.getDelta(), 0.05);
  frame++;

  if (fly) {
    fly.t = Math.min(1, fly.t + dt / 1.4);
    const e = 1 - Math.pow(1 - fly.t, 3);
    persp.position.lerpVectors(fly.p0, fly.p1, e);
    orbit.target.lerpVectors(fly.t0, fly.t1, e);
    if (fly.fov) { persp.fov = 45 + (fly.fov - 45) * e; persp.updateProjectionMatrix(); }
    if (fly.t >= 1) fly = null;
  }
  if (view === 'orbit') orbit.update();
  if (view === 'plan') plan.update();
  if (view === 'walk' && walk.isLocked) {
    const sp = (keys.ShiftLeft || keys.ShiftRight ? 7 : 2.8) * dt;
    const f = (keys.KeyW ? 1 : 0) - (keys.KeyS ? 1 : 0), r = (keys.KeyD ? 1 : 0) - (keys.KeyA ? 1 : 0);
    if (f) walk.moveForward(f * sp);
    if (r) walk.moveRight(r * sp);
    const p = walkCam.position;
    p.y += (heightAt(p.x, p.z) + 1.65 - p.y) * 0.3;
  }

  // keep the shadow frustum centred on what you are looking at
  focus.copy(view === 'walk' ? walkCam.position : view === 'plan' ? plan.target : orbit.target);
  sun.target.position.copy(focus);
  sun.position.copy(focus).addScaledVector(sunDir, 400);
  if (view === 'orbit') {
    const d = persp.position.distanceTo(orbit.target);
    const half = clamp(d * 0.9, 60, 260);
    const sc = sun.shadow.camera;
    if (Math.abs(sc.right - half) > 5) { sc.left = sc.bottom = -half; sc.right = sc.top = half; sc.updateProjectionMatrix(); }
  }

  // warm light pools from the nearest lamps after dark
  if (frame % 20 === 0) {
    const night = 1 - dayF;
    const near = night > 0.05 ? lampSpots.map((p) => [p, p.distanceToSquared(focus)]).sort((a, b) => a[1] - b[1]).slice(0, lampLights.length) : [];
    lampLights.forEach((l, i) => {
      if (near[i] && pathsRoot.visible) { l.position.copy(near[i][0]); l.intensity = 22 * night; }
      else l.intensity = 0;
    });
  }

  M.water.map.offset.x += dt * 0.02;
  M.water.map.offset.y += dt * 0.013;
  M.ember.emissiveIntensity = 1.3 + Math.sin(performance.now() / 90) * 0.3 + Math.random() * 0.3;

  updateLabels();
  renderer.render(scene, camera);
}

/* ------------------------------------------------------------------ */
/* boot                                                               */
/* ------------------------------------------------------------------ */
const centre = layout.boundary.reduce((a, [x, z]) => [a[0] + x / layout.boundary.length, a[1] + z / layout.boundary.length], [0, 0]);
orbit.target.set(centre[0], 0, centre[1]);
persp.position.set(centre[0] + 75, 95, centre[1] + 125);
setTime(10.5);
rebuildAll();
renderInspector();
tick();
$('loading').style.opacity = 0;
setTimeout(() => $('loading').remove(), 700);
window.__twin = { layout: () => layout, setView, setTime, setTool, select, showPhoto, focusOn, persp, orbit };
