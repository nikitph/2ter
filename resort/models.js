// Parametric low-poly models for every placeable item. Each builder returns a Group whose
// origin is the item's ground centre with its front facing +Z. Units are metres.
import * as THREE from 'three';
import * as T from './textures.js';

/* ------------------------------------------------------------------ */
/* materials                                                          */
/* ------------------------------------------------------------------ */
const std = (o) => new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0, ...o });
export const M = {
  laterite: std({ map: T.laterite() }),
  brick: std({ map: T.brick() }),
  brickChevron: std({ map: T.brick(true) }),
  roof: std({ map: T.roofTiles(), roughness: 0.75 }),
  pavers: std({ map: T.pavers() }),
  gravel: std({ map: T.gravel(), roughness: 1 }),
  poolTiles: std({ map: T.poolTiles(), roughness: 0.3, side: THREE.BackSide }),
  poolTilesOut: std({ map: T.poolTiles(), roughness: 0.3 }),
  deck: std({ map: T.deckTiles(), roughness: 0.6 }),
  tentWall: std({ map: T.canvasFabric('#e7d68c') }),
  tentRoof: std({ map: T.canvasFabric('#a29a72'), side: THREE.DoubleSide }),
  scallop: std({ map: T.scallop(), alphaTest: 0.5, side: THREE.DoubleSide }),
  bark: std({ map: T.bark() }),
  frond: std({ map: T.frond(), alphaTest: 0.45, side: THREE.DoubleSide, roughness: 0.8 }),
  leaves: std({ map: T.leaves(), roughness: 0.9 }),
  thatch: std({ map: T.thatch(), roughness: 1 }),
  net: std({ map: T.net(), alphaTest: 0.4, side: THREE.DoubleSide }),
  wood: std({ map: T.wood() }),
  concrete: std({ map: T.concrete() }),
  cream: std({ color: '#efe6c8' }),
  plaster: std({ color: '#d9b77e' }),
  beige: std({ color: '#c8a46b' }),
  steel: std({ color: '#d6d9de', metalness: 0.85, roughness: 0.25 }),
  black: std({ color: '#1d1e22', roughness: 0.5 }),
  glass: std({ color: '#2a3442', metalness: 0.3, roughness: 0.15 }),
  darkWood: std({ color: '#3d2a1c' }),
  stone: std({ color: '#8f8a80' }),
  pot: std({ color: '#1c1c1c', roughness: 0.6 }),
  bush: std({ map: T.leaves(), color: '#9ccf7a' }),
  sand: std({ color: '#d8c49a', roughness: 1 }),
  white: std({ color: '#f4f4f0' }),
  lampGlass: std({ color: '#fff3cf', emissive: '#ffcc66', emissiveIntensity: 0 }),
  ember: std({ color: '#ff7a1a', emissive: '#ff5a00', emissiveIntensity: 1.5 }),
  water: new THREE.MeshStandardMaterial({ color: '#3fa9de', map: T.water(), transparent: true, opacity: 0.72, roughness: 0.05, metalness: 0.15, emissive: '#0c3c5c', emissiveIntensity: 0.25 }),
  poolMask: new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false, stencilWrite: true, stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp }),
};
export const TILE = { laterite: 1.6, brick: 1.9, brickChevron: 3.8, roof: 2, pavers: 1.6, gravel: 1.5, poolTiles: 0.8, poolTilesOut: 0.8, deck: 2.4, tentWall: 1.5, tentRoof: 1.5, wood: 1, concrete: 3, thatch: 1.5 };

/* ------------------------------------------------------------------ */
/* helpers                                                            */
/* ------------------------------------------------------------------ */
function worldUV(geo, w, h, d, tile) {
  // rescale BoxGeometry UVs so textures keep a constant real-world size
  const uv = geo.attributes.uv;
  const dims = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  for (let f = 0; f < 6; f++)
    for (let k = 0; k < 4; k++) {
      const i = f * 4 + k;
      uv.setXY(i, (uv.getX(i) * dims[f][0]) / tile, (uv.getY(i) * dims[f][1]) / tile);
    }
  return geo;
}
const tileOf = (m) => (Array.isArray(m) ? 2 : TILE[Object.keys(M).find((k) => M[k] === m)] ?? 0);
export function box(w, h, d, mat, x = 0, y = 0, z = 0, parent) {
  const g = new THREE.BoxGeometry(w, h, d);
  const t = tileOf(mat);
  if (t) worldUV(g, w, h, d, t);
  const m = new THREE.Mesh(g, mat);
  m.position.set(x, y + h / 2, z);
  m.castShadow = m.receiveShadow = true;
  parent?.add(m);
  return m;
}
export function cyl(rt, rb, h, mat, x = 0, y = 0, z = 0, parent, seg = 12) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat);
  m.position.set(x, y + h / 2, z);
  m.castShadow = m.receiveShadow = true;
  parent?.add(m);
  return m;
}
export function rod(a, b, r, mat, parent) {
  const A = new THREE.Vector3(...a), B = new THREE.Vector3(...b);
  const len = A.distanceTo(B);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, len, 8), mat);
  m.position.copy(A).add(B).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), B.sub(A).normalize());
  m.castShadow = true;
  parent?.add(m);
  return m;
}
const ni = (g) => (g.index ? g.toNonIndexed() : g);
export function mergeGeometries(list) {
  let vCount = 0, iCount = 0;
  for (const g of list) { vCount += g.attributes.position.count; iCount += g.index ? g.index.count : g.attributes.position.count; }
  const pos = new Float32Array(vCount * 3), nor = new Float32Array(vCount * 3), uv = new Float32Array(vCount * 2);
  const idx = new Uint32Array(iCount);
  let vo = 0, io = 0;
  for (const g of list) {
    const n = g.attributes.position.count;
    pos.set(g.attributes.position.array, vo * 3);
    if (g.attributes.normal) nor.set(g.attributes.normal.array, vo * 3);
    if (g.attributes.uv) uv.set(g.attributes.uv.array, vo * 2);
    if (g.index) for (let i = 0; i < g.index.count; i++) idx[io++] = g.index.array[i] + vo;
    else for (let i = 0; i < n; i++) idx[io++] = i + vo;
    vo += n;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  out.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  out.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  out.setIndex(new THREE.BufferAttribute(idx, 1));
  return out;
}
// Hip roof over a w×d rectangle with ridge along x. UVs are planar in metres.
export function hipRoofGeometry(w, d, h, tile = 2) {
  const hw = w / 2, hd = d / 2, rl = Math.max(0, hw - hd);
  const P = [[-hw, 0, -hd], [hw, 0, -hd], [hw, 0, hd], [-hw, 0, hd], [-rl, h, 0], [rl, h, 0]];
  const faces = [[3, 2, 5, 4], [1, 0, 4, 5], [2, 1, 5], [0, 3, 4]];
  const pos = [], uv = [];
  for (const f of faces) {
    const tri = f.length === 4 ? [[f[0], f[1], f[2]], [f[0], f[2], f[3]]] : [f];
    for (const t of tri)
      for (const i of t) {
        pos.push(...P[i]);
        const p = P[i];
        // project onto the slope: along-eave coordinate and up-slope distance
        const alongX = f.length === 4;
        uv.push((alongX ? p[0] : p[2]) / tile, (alongX ? Math.hypot(p[1], hd - Math.abs(p[2])) : Math.hypot(p[1], hw - Math.abs(p[0]))) / tile);
      }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.computeVertexNormals();
  return g;
}
function hipRoof(w, d, h, y, parent, mat = M.roof) {
  const m = new THREE.Mesh(hipRoofGeometry(w, d, h), mat);
  m.position.y = y; m.castShadow = m.receiveShadow = true;
  parent.add(m);
  // thin fascia board under the eaves
  box(w, 0.18, d, M.darkWood, 0, y - 0.18, 0, parent);
  return m;
}

/* ------------------------------------------------------------------ */
/* vegetation geometry (shared by instancing)                         */
/* ------------------------------------------------------------------ */
let vs = 99;
const vr = () => ((vs = (vs * 16807) % 2147483647) / 2147483647);

export function palmGeometry(height = 9, lean = 0.8, fronds = 15) {
  const trunk = new THREE.CylinderGeometry(0.15, 0.24, height, 8, 14, true);
  trunk.translate(0, height / 2, 0);
  const p = trunk.attributes.position, uv = trunk.attributes.uv;
  for (let i = 0; i < p.count; i++) {
    const t = p.getY(i) / height;
    p.setX(i, p.getX(i) + lean * t * t);
    // flare at the base like real coconut palms
    const flare = 1 + Math.max(0, 0.12 - t) * 6;
    p.setX(i, (p.getX(i) - lean * t * t) * flare + lean * t * t);
    p.setZ(i, p.getZ(i) * flare);
    uv.setY(i, (t * height) / 2.5);
  }
  trunk.computeVertexNormals();
  const nuts = [];
  for (let k = 0; k < 5; k++) {
    const s = new THREE.SphereGeometry(0.14, 6, 5);
    const a = (k / 5) * Math.PI * 2;
    s.translate(lean + Math.cos(a) * 0.25, height - 0.35, Math.sin(a) * 0.25);
    nuts.push(s);
  }
  const trunkAll = mergeGeometries([ni(trunk), ...nuts.map((n) => ni(n))]);

  const parts = [];
  for (let i = 0; i < fronds; i++) {
    const L = 3.6 + vr() * 1.4, Wd = L * 0.27;
    const g = new THREE.PlaneGeometry(L, Wd, 10, 1);
    g.translate(L / 2, 0, 0);
    g.rotateX(-Math.PI / 2 + (vr() - 0.5) * 0.9); // roll along spine
    const pa = g.attributes.position;
    const rise = 0.25 + vr() * 0.55, droop = 0.11 + vr() * 0.07;
    for (let k = 0; k < pa.count; k++) {
      const x = pa.getX(k);
      pa.setY(k, pa.getY(k) + x * rise - x * x * droop);
    }
    g.rotateY((i / fronds) * Math.PI * 2 + vr() * 0.3);
    g.translate(lean, height, 0);
    g.computeVertexNormals();
    parts.push(g);
  }
  return { trunk: trunkAll, crown: mergeGeometries(parts) };
}
export function broadleafGeometry(height = 6, radius = 3) {
  const trunk = new THREE.CylinderGeometry(0.18, 0.32, height * 0.55, 7);
  trunk.translate(0, height * 0.275, 0);
  const blobs = [];
  const n = 5 + Math.floor(vr() * 3);
  for (let i = 0; i < n; i++) {
    const b = new THREE.IcosahedronGeometry(radius * (0.45 + vr() * 0.35), 1);
    const p = b.attributes.position;
    for (let k = 0; k < p.count; k++) p.setXYZ(k, p.getX(k) * (1 + (vr() - 0.5) * 0.25), p.getY(k) * (0.8 + vr() * 0.2), p.getZ(k) * (1 + (vr() - 0.5) * 0.25));
    const a = (i / n) * Math.PI * 2;
    b.translate(Math.cos(a) * radius * 0.45, height * 0.62 + vr() * radius * 0.5, Math.sin(a) * radius * 0.45);
    b.computeVertexNormals();
    blobs.push(ni(b));
  }
  const top = new THREE.IcosahedronGeometry(radius * 0.6, 1);
  top.translate(0, height * 0.85, 0);
  blobs.push(ni(top));
  return { trunk: ni(trunk), crown: mergeGeometries(blobs) };
}
export const PALMS = [palmGeometry(9, 0.6), palmGeometry(11, 1.4), palmGeometry(7.5, 0.3, 13)];
export const BROADLEAF = [broadleafGeometry(6, 3), broadleafGeometry(8, 4), broadleafGeometry(4.5, 2.2)];

function palmMesh(v = 0, parent, x = 0, z = 0, rot = 0) {
  const g = new THREE.Group();
  const t = new THREE.Mesh(PALMS[v].trunk, M.bark), c = new THREE.Mesh(PALMS[v].crown, M.frond);
  t.castShadow = c.castShadow = true; t.receiveShadow = true;
  g.add(t, c); g.position.set(x, 0, z); g.rotation.y = rot;
  parent?.add(g);
  return g;
}
function treeMesh(v = 0, parent, x = 0, z = 0, s = 1) {
  const g = new THREE.Group();
  const t = new THREE.Mesh(BROADLEAF[v].trunk, M.bark), c = new THREE.Mesh(BROADLEAF[v].crown, M.leaves);
  t.castShadow = c.castShadow = true; c.receiveShadow = true;
  g.add(t, c); g.position.set(x, 0, z); g.scale.setScalar(s);
  parent?.add(g);
  return g;
}
function lantern(parent, x, y, z) {
  box(0.32, 0.06, 0.32, M.black, x, y, z, parent);
  box(0.24, 0.36, 0.24, M.lampGlass, x, y + 0.06, z, parent).castShadow = false;
  for (const [dx, dz] of [[-0.13, -0.13], [0.13, -0.13], [-0.13, 0.13], [0.13, 0.13]]) box(0.03, 0.36, 0.03, M.black, x + dx, y + 0.06, z + dz, parent);
  const cap = new THREE.Mesh(new THREE.ConeGeometry(0.26, 0.2, 4), M.black);
  cap.position.set(x, y + 0.52, z); cap.rotation.y = Math.PI / 4; parent.add(cap);
}
function picketRun(parent, a, b, y) {
  // cream picket fence between two points at deck height y
  const A = new THREE.Vector3(a[0], 0, a[1]), B = new THREE.Vector3(b[0], 0, b[1]);
  const len = A.distanceTo(B), n = Math.floor(len / 0.14);
  const geos = [];
  for (let i = 0; i <= n; i++) {
    const g = new THREE.BoxGeometry(0.06, 0.9, 0.05);
    g.translate(-len / 2 + (i / n) * len, y + 0.45, 0);
    geos.push(ni(g));
  }
  for (const h of [0.15, 0.8]) { const g = new THREE.BoxGeometry(len, 0.07, 0.07); g.translate(0, y + h, 0); geos.push(ni(g)); }
  const m = new THREE.Mesh(mergeGeometries(geos), M.cream);
  m.castShadow = true;
  m.position.copy(A).add(B).multiplyScalar(0.5);
  m.rotation.y = -Math.atan2(B.z - A.z, B.x - A.x);
  parent.add(m);
}

/* ------------------------------------------------------------------ */
/* builders                                                           */
/* ------------------------------------------------------------------ */
function tentCottage() {
  const g = new THREE.Group();
  const H = 1.2;
  box(7, H, 9, M.laterite, 0, 0, 0, g);
  box(7.2, 0.08, 9.2, M.darkWood, 0, H, 0, g);
  for (let k = 0; k < 6; k++) box(2.4, H - k * 0.2, 0.32, M.laterite, 0, 0, 4.66 + k * 0.32, g);
  for (const sx of [-1.3, 1.3]) {
    rod([sx, H + 0.95, 4.5], [sx, 1.0, 6.6], 0.03, M.steel, g);
    rod([sx, H + 0.4, 4.5], [sx, 0.45, 6.6], 0.02, M.steel, g);
    rod([sx, 0, 6.6], [sx, 1.0, 6.6], 0.03, M.steel, g);
    rod([sx, H, 4.6], [sx, H + 0.95, 4.6], 0.03, M.steel, g);
  }
  picketRun(g, [-3.4, 4.45], [-1.3, 4.45], H);
  picketRun(g, [1.3, 4.45], [3.4, 4.45], H);
  picketRun(g, [-3.45, 1.4], [-3.45, 4.45], H);
  picketRun(g, [3.45, 1.4], [3.45, 4.45], H);
  // canvas tent body
  box(6, 2.4, 5.6, M.tentWall, 0, H, -1.5, g);
  box(1.0, 2.0, 0.05, M.darkWood, -1.2, H, 1.32, g);
  box(1.4, 0.9, 0.05, M.glass, 1.3, H + 1.0, 1.32, g);
  // roof: gable running front-to-back, extending over the deck
  const wallTop = H + 2.4, ridge = wallTop + 1.4, hw = 3.9, z0 = -4.7, z1 = 4.3;
  const roofGeo = new THREE.BufferGeometry();
  const v = [-hw, wallTop - 0.2, z0, 0, ridge, z0, 0, ridge, z1, -hw, wallTop - 0.2, z0, 0, ridge, z1, -hw, wallTop - 0.2, z1,
    hw, wallTop - 0.2, z0, hw, wallTop - 0.2, z1, 0, ridge, z1, hw, wallTop - 0.2, z0, 0, ridge, z1, 0, ridge, z0];
  const slope = Math.hypot(hw, 1.6) / 1.5, len = (z1 - z0) / 1.5;
  const uv = [0, 0, slope, 0, slope, len, 0, 0, slope, len, 0, len, 0, 0, 0, len, slope, len, 0, 0, slope, len, slope, 0];
  roofGeo.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
  roofGeo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  roofGeo.computeVertexNormals();
  const roof = new THREE.Mesh(roofGeo, M.tentRoof);
  roof.castShadow = roof.receiveShadow = true;
  g.add(roof);
  // scalloped valance along both eaves and the front gable
  for (const sx of [-1, 1]) {
    const p = new THREE.Mesh(new THREE.PlaneGeometry(z1 - z0, 0.45), M.scallop);
    p.material.map.repeat.set(4, 1);
    p.position.set(sx * hw, wallTop - 0.42, (z0 + z1) / 2); p.rotation.y = Math.PI / 2;
    g.add(p);
  }
  const front = new THREE.Mesh(new THREE.PlaneGeometry(hw * 2, 0.45), M.scallop);
  front.position.set(0, wallTop - 0.42, z1); g.add(front);
  for (const sx of [-3.3, 3.3]) cyl(0.06, 0.06, wallTop - H, M.cream, sx, H, 4.1, g, 8);
  lantern(g, 0.6, wallTop - 0.9, 3.2);
  return g;
}

function villa() {
  const g = new THREE.Group();
  const W = 20, D = 8, H = 3.2;
  box(W + 0.3, 0.4, D + 0.3, M.laterite, 0, 0, 0, g);
  const walls = new THREE.Mesh(worldUV(new THREE.BoxGeometry(W, H, D), W, H, D, 1.9), [M.brick, M.brick, M.plaster, M.plaster, M.brickChevron, M.brick]);
  walls.position.y = H / 2 + 0.4; walls.castShadow = walls.receiveShadow = true;
  g.add(walls);
  // openings on the front façade
  box(1.6, 2.4, 0.08, M.glass, -2.5, 0.4, D / 2 + 0.02, g);
  box(1.8, 2.5, 0.06, M.darkWood, -2.5, 0.35, D / 2 + 0.01, g);
  for (const x of [3.5, 5.6, -7.5]) {
    box(1.5, 1.4, 0.06, M.darkWood, x, 1.3, D / 2 + 0.02, g);
    box(1.3, 1.2, 0.08, M.glass, x, 1.4, D / 2 + 0.03, g);
  }
  hipRoof(W + 1.6, D + 1.6, 2.4, H + 0.4, g);
  box(3, 1.6, 2.6, M.plaster, 2.5, H + 1.6, -1.2, g); // stair/tank room poking through the roof
  // beige concrete pergola
  box(0.45, 3.1, 0.45, M.beige, 9.2, 0, D / 2 + 2.4, g);
  box(0.5, 0.5, 2.9, M.beige, 9.2, 3.1, D / 2 + 1.0, g);
  box(5.2, 0.5, 0.5, M.beige, 7.0, 3.1, D / 2 + 2.4, g);
  return g;
}

function cottage(reception = false) {
  return () => {
    const g = new THREE.Group();
    const W = reception ? 9 : 7, D = 6, H = 2.8;
    box(W + 0.3, 0.45, D + 2.3, M.laterite, 0, 0, 1, g);
    box(W, H, D, M.brick, 0, 0.45, 0, g);
    box(1.0, 2.1, 0.06, M.darkWood, -0.8, 0.45, D / 2 + 0.02, g);
    box(1.3, 1.1, 0.07, M.glass, 1.6, 1.4, D / 2 + 0.02, g);
    box(1.2, 1.0, 0.07, M.glass, W / 2 + 0.02, 1.4, 0, g).rotation.y = Math.PI / 2;
    for (const x of [-W / 2 + 0.4, W / 2 - 0.4]) cyl(0.09, 0.09, H, M.darkWood, x, 0.45, D / 2 + 1.9, g, 8);
    hipRoof(W + 1.4, D + 3.4, 2.0, H + 0.45, g).position.z = 0.8;
    g.children[g.children.length - 1].position.z = 0.8;
    if (reception) {
      const s = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 0.8), new THREE.MeshStandardMaterial({ map: T.signText('Reception') }));
      s.position.set(0, H + 0.1, D / 2 + 2.25); g.add(s);
    }
    return g;
  };
}

function pool() {
  const g = new THREE.Group();
  const PW = 10, PD = 4.6, DW = 16, DD = 11, top = 0.14, depth = 1.4;
  // deck around the opening
  box(DW, top, (DD - PD) / 2, M.deck, 0, 0, -(PD / 2 + (DD - PD) / 4), g);
  box(DW, top, (DD - PD) / 2, M.deck, 0, 0, PD / 2 + (DD - PD) / 4, g);
  box((DW - PW) / 2, top, PD, M.deck, -(PW / 2 + (DW - PW) / 4), 0, 0, g);
  box((DW - PW) / 2, top, PD, M.deck, PW / 2 + (DW - PW) / 4, 0, 0, g);
  // coping
  for (const s of [-1, 1]) { box(PW + 0.6, 0.06, 0.3, M.stone, 0, top, s * (PD / 2 + 0.15), g); box(0.3, 0.06, PD, M.stone, s * (PW / 2 + 0.15), top, 0, g); }
  // basin (inside faces only) and a stencil mask that punches a hole in the ground
  const basin = new THREE.Mesh(worldUV(new THREE.BoxGeometry(PW, depth, PD), PW, depth, PD, 0.8), M.poolTiles);
  basin.position.y = top - depth / 2; basin.receiveShadow = true;
  g.add(basin);
  const mask = new THREE.Mesh(new THREE.PlaneGeometry(PW, PD), M.poolMask);
  mask.rotation.x = -Math.PI / 2; mask.position.y = top + 0.001; mask.renderOrder = -10;
  g.add(mask);
  const water = new THREE.Mesh(new THREE.PlaneGeometry(PW, PD), M.water);
  water.rotation.x = -Math.PI / 2; water.position.y = top - 0.12; water.renderOrder = 2;
  g.add(water);
  // raised jacuzzi at the back
  box(3.4, 0.6, 2.4, M.poolTilesOut, 3.2, top, -PD / 2 - 1.2, g);
  const jw = new THREE.Mesh(new THREE.PlaneGeometry(3.0, 2.0), M.water);
  jw.rotation.x = -Math.PI / 2; jw.position.set(3.2, top + 0.61, -PD / 2 - 1.2); g.add(jw);
  // ladder
  for (const x of [-3.6, -3.0]) {
    const pts = [];
    for (let i = 0; i <= 10; i++) { const a = (i / 10) * Math.PI; pts.push(new THREE.Vector3(x, top + 0.75 + Math.sin(a) * 0.25, PD / 2 + 0.25 - (1 - Math.cos(a)) * 0.3)); }
    pts.push(new THREE.Vector3(x, top - 0.8, PD / 2 - 0.4));
    const m = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 20, 0.025, 6), M.steel);
    m.castShadow = true; g.add(m);
    rod([x, 0, PD / 2 + 0.25], [x, top + 0.75, PD / 2 + 0.25], 0.025, M.steel, g);
  }
  // stone L-shaped lounge seat
  box(4, 0.45, 1.2, M.stone, -5.4, top, -PD / 2 - 2.2, g);
  box(1.2, 0.45, 2.6, M.stone, -6.9, top, -PD / 2 - 0.3, g);
  box(4, 0.5, 0.2, M.stone, -5.4, top + 0.45, -PD / 2 - 2.7, g);
  return g;
}

function courtyard() {
  const g = new THREE.Group();
  box(16, 0.06, 12, M.pavers, 0, 0, 0, g);
  const flowers = ['#e8418f', '#ff5d73', '#ffd23f', '#f0f0f0', '#c13bd6'];
  let k = 0;
  for (let i = 0; i < 6; i++)
    for (let j = 0; j < 4; j++) {
      if ((i + j) % 5 === 4) continue;
      const x = -2.4 + i * 0.85 + (j % 2) * 0.4, z = -1 + j * 0.8, s = 0.75 + ((k * 37) % 10) / 25;
      cyl(0.32 * s, 0.24 * s, 0.5 * s, M.pot, x, 0.06, z, g, 10);
      const b = new THREE.Mesh(new THREE.IcosahedronGeometry(0.4 * s, 1), M.bush);
      b.position.set(x, 0.06 + 0.5 * s + 0.3 * s, z); b.scale.y = 1.2; b.castShadow = true; g.add(b);
      if (k % 2 === 0) for (let f = 0; f < 5; f++) {
        const fl = new THREE.Mesh(new THREE.SphereGeometry(0.07, 5, 4), std({ color: flowers[(k + f) % 5] }));
        fl.position.set(x + Math.cos(f * 1.3) * 0.3 * s, b.position.y + 0.15 + (f % 2) * 0.12, z + Math.sin(f * 1.3) * 0.3 * s);
        g.add(fl);
      }
      k++;
    }
  cyl(1.3, 1.3, 0.5, M.laterite, 5, 0.06, -3.5, g, 16);
  treeMesh(2, g, 5, -3.5, 0.9);
  return g;
}

function gate() {
  const g = new THREE.Group();
  for (const x of [-3.4, 3.4]) {
    box(0.9, 2.9, 0.9, M.laterite, x, 0, 0, g);
    const cap = new THREE.Mesh(new THREE.ConeGeometry(0.85, 0.5, 4), M.roof);
    cap.position.set(x, 3.15, 0); cap.rotation.y = Math.PI / 4; cap.castShadow = true; g.add(cap);
    lantern(g, x, 3.4, 0);
  }
  const sign = T.signText('Vrukshali', 'Camping · Activities & more');
  const board = new THREE.Mesh(new THREE.BoxGeometry(6.2, 1.5, 0.14), [M.darkWood, M.darkWood, M.darkWood, M.darkWood, std({ map: sign }), std({ map: sign })]);
  board.position.set(0, 3.1, 0); board.castShadow = true; g.add(board);
  return g;
}

function hammock() {
  const g = new THREE.Group();
  palmMesh(0, g, -2.4, 0, 0.3);
  palmMesh(2, g, 2.4, 0, 2.1);
  const geo = new THREE.PlaneGeometry(3.2, 1.0, 16, 4);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i) / 1.6, y = p.getY(i);
    p.setXYZ(i, p.getX(i), -0.45 * (1 - x * x) - Math.abs(y) * 0 + 0, y * (0.8 + 0.2 * x * x));
    p.setY(i, p.getY(i) - 0.12 * (1 - (y / 0.5) ** 2) * (1 - x * x));
  }
  geo.computeVertexNormals();
  const h = new THREE.Mesh(geo, M.net);
  h.position.y = 1.1; h.castShadow = true; g.add(h);
  for (const s of [-1, 1]) {
    box(0.06, 0.06, 1.05, M.wood, s * 1.6, 1.07, 0, g);
    rod([s * 1.6, 1.1, 0.5], [s * 2.3, 1.45, 0], 0.012, M.black, g);
    rod([s * 1.6, 1.1, -0.5], [s * 2.3, 1.45, 0], 0.012, M.black, g);
  }
  return g;
}

function domeTent() {
  const g = new THREE.Group();
  const colors = ['#e9822f', '#3f8f5a', '#3b6fb6'];
  const c = colors[Math.floor(Math.random() * 3)];
  const dome = new THREE.Mesh(new THREE.SphereGeometry(1.6, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), std({ color: c, roughness: 0.7 }));
  dome.scale.y = 0.8; dome.castShadow = dome.receiveShadow = true; g.add(dome);
  const door = new THREE.Mesh(new THREE.CircleGeometry(0.6, 16, 0, Math.PI), std({ color: '#2a2a2a' }));
  door.position.set(0, 0.02, 1.57); g.add(door);
  for (const a of [0.6, -0.6]) {
    const pts = [];
    for (let i = 0; i <= 12; i++) { const t = (i / 12) * Math.PI; pts.push(new THREE.Vector3(Math.cos(t) * 1.62 * Math.cos(a), Math.sin(t) * 1.3, Math.cos(t) * 1.62 * Math.sin(a))); }
    g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 20, 0.02, 4), M.black));
  }
  return g;
}

function firepit() {
  const g = new THREE.Group();
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    const s = new THREE.Mesh(new THREE.DodecahedronGeometry(0.22, 0), M.stone);
    s.position.set(Math.cos(a) * 0.8, 0.12, Math.sin(a) * 0.8); s.rotation.set(i, i * 2, 0); s.castShadow = true; g.add(s);
  }
  for (let i = 0; i < 4; i++) { const l = cyl(0.07, 0.07, 1.1, M.wood, 0, 0.2, 0, g, 6); l.rotation.set(Math.PI / 2 - 0.5, (i * Math.PI) / 2, 0); }
  const e = new THREE.Mesh(new THREE.SphereGeometry(0.35, 8, 6), M.ember);
  e.position.y = 0.15; e.scale.y = 0.5; g.add(e);
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    const b = cyl(0.25, 0.25, 1.6, M.wood, Math.cos(a) * 3, 0.25, Math.sin(a) * 3, g, 10);
    b.rotation.set(Math.PI / 2, 0, 0); b.rotation.z = 0; b.rotation.order = 'YXZ'; b.rotation.y = -a + Math.PI / 2;
  }
  box(9, 0.03, 9, M.sand, 0, 0, 0, g).receiveShadow = true;
  return g;
}

function gazebo() {
  const g = new THREE.Group();
  cyl(3, 3, 0.35, M.wood, 0, 0, 0, g, 8);
  for (let i = 0; i < 8; i++) { const a = (i / 8) * Math.PI * 2 + Math.PI / 8; cyl(0.1, 0.1, 2.5, M.darkWood, Math.cos(a) * 2.7, 0.35, Math.sin(a) * 2.7, g, 8); }
  const roof = new THREE.Mesh(new THREE.ConeGeometry(3.8, 2.4, 8, 1), M.thatch);
  roof.position.y = 0.35 + 2.5 + 1.2; roof.rotation.y = Math.PI / 8; roof.castShadow = true; g.add(roof);
  box(1.6, 0.75, 0.9, M.wood, 0, 0.35, 0, g);
  return g;
}

function dining() {
  const g = new THREE.Group();
  const W = 14, D = 9, H = 3;
  box(W + 1, 0.5, D + 1, M.laterite, 0, 0, 0, g);
  box(W, 0.04, D, M.deck, 0, 0.5, 0, g);
  for (let i = 0; i < 5; i++) for (const z of [-D / 2 + 0.3, D / 2 - 0.3]) cyl(0.14, 0.14, H, M.darkWood, -W / 2 + 0.3 + (i * (W - 0.6)) / 4, 0.5, z, g, 8);
  hipRoof(W + 2, D + 2, 2.6, H + 0.5, g);
  for (let i = 0; i < 4; i++)
    for (let j = 0; j < 2; j++) {
      const x = -4.5 + i * 3, z = -1.8 + j * 3.6;
      box(1.6, 0.06, 0.9, M.wood, x, 1.25, z, g);
      cyl(0.05, 0.05, 0.72, M.black, x, 0.54, z, g, 6);
      for (const s of [-1, 1]) box(1.4, 0.45, 0.35, M.wood, x, 0.54, z + s * 0.8, g);
    }
  return g;
}

function court() {
  const g = new THREE.Group();
  box(16, 0.05, 9, M.sand, 0, 0, 0, g);
  for (const s of [-1, 1]) { box(16, 0.01, 0.06, M.white, 0, 0.05, s * 4.2, g); box(0.06, 0.01, 8.4, M.white, s * 7.9, 0.05, 0, g); }
  for (const z of [-4.6, 4.6]) cyl(0.04, 0.04, 2.45, M.steel, 0, 0, z, g, 6);
  const n = new THREE.Mesh(new THREE.PlaneGeometry(9.2, 0.9), M.net);
  n.rotation.y = Math.PI / 2; n.position.set(0, 2.0, 0); g.add(n);
  return g;
}

function parking() {
  const g = new THREE.Group();
  box(20, 0.05, 12, M.gravel, 0, 0, 0, g);
  for (let i = 0; i < 8; i++) box(0.12, 0.01, 4.8, M.white, -8.4 + i * 2.6, 0.05, -3.2, g);
  const colors = ['#c9ccd2', '#8a1f24', '#f2f2ee'];
  for (let i = 0; i < 3; i++) {
    const c = new THREE.Group();
    box(1.8, 0.7, 4.4, std({ color: colors[i], metalness: 0.4, roughness: 0.35 }), 0, 0.3, 0, c);
    box(1.6, 0.6, 2.2, M.glass, 0, 1.0, -0.2, c);
    for (const [x, z] of [[-0.85, 1.4], [0.85, 1.4], [-0.85, -1.4], [0.85, -1.4]]) { const w = cyl(0.33, 0.33, 0.24, M.black, x, 0.33, z, c, 12); w.rotation.z = Math.PI / 2; w.position.y = 0.33; }
    c.position.set(-7.1 + i * 2.6 * 2, 0, -3.2); g.add(c);
  }
  return g;
}

function lamp() {
  const g = new THREE.Group();
  box(0.3, 0.25, 0.3, M.black, 0, 0, 0, g);
  cyl(0.045, 0.06, 2.4, M.black, 0, 0.25, 0, g, 8);
  lantern(g, 0, 2.6, 0);
  return g;
}
function bench() {
  const g = new THREE.Group();
  box(1.8, 0.06, 0.45, M.wood, 0, 0.42, 0, g);
  box(1.8, 0.4, 0.05, M.wood, 0, 0.5, -0.22, g);
  for (const x of [-0.75, 0.75]) box(0.08, 0.42, 0.45, M.black, x, 0, 0, g);
  return g;
}
function flowerbed() {
  const g = new THREE.Group();
  box(4.2, 0.3, 1.6, M.laterite, 0, 0, 0, g);
  box(4, 0.05, 1.4, std({ color: '#6b3e2a', roughness: 1 }), 0, 0.3, 0, g);
  const cols = ['#c7362b', '#e7b62f', '#8d2a52', '#e46b2c'];
  for (let i = 0; i < 9; i++) {
    const b = new THREE.Mesh(new THREE.IcosahedronGeometry(0.28, 0), std({ color: cols[i % 4], flatShading: true }));
    b.position.set(-1.7 + (i % 5) * 0.85, 0.55, i < 5 ? -0.3 : 0.35); b.scale.y = 1.3; b.castShadow = true; g.add(b);
  }
  return g;
}

/* ------------------------------------------------------------------ */
/* catalog                                                            */
/* ------------------------------------------------------------------ */
// w/d = footprint used for tree clearing, built-up area and selection.
export const CATALOG = {
  tent: { name: 'Tent cottage', icon: '⛺', w: 7, d: 11, keys: 1, guests: 2, built: true, build: tentCottage, cost: 18 },
  villa: { name: 'Pool villa', icon: '🏡', w: 21.6, d: 9.6, keys: 3, guests: 8, built: true, build: villa, cost: 85 },
  cottage: { name: 'Brick cottage', icon: '🏠', w: 8.4, d: 9.4, keys: 1, guests: 3, built: true, build: cottage(false), cost: 22 },
  reception: { name: 'Reception', icon: '🛎️', w: 10.4, d: 9.4, built: true, build: cottage(true), cost: 20 },
  dining: { name: 'Dining pavilion', icon: '🍽️', w: 16, d: 11, built: true, build: dining, cost: 35 },
  pool: { name: 'Swimming pool', icon: '🏊', w: 16, d: 11, hard: true, build: pool, cost: 30 },
  courtyard: { name: 'Paved courtyard', icon: '🪴', w: 16, d: 12, hard: true, build: courtyard, cost: 8 },
  gate: { name: 'Entrance gate', icon: '⛩️', w: 8, d: 2, build: gate, cost: 4 },
  gazebo: { name: 'Thatch gazebo', icon: '🛖', w: 7, d: 7, built: true, build: gazebo, cost: 5 },
  hammock: { name: 'Hammock', icon: '🌴', w: 6, d: 2, build: hammock, cost: 0.3 },
  dome: { name: 'Camping tent', icon: '🏕️', w: 3.4, d: 3.4, keys: 1, guests: 2, build: domeTent, cost: 0.4 },
  firepit: { name: 'Campfire circle', icon: '🔥', w: 9, d: 9, hard: true, build: firepit, cost: 1 },
  court: { name: 'Sports court', icon: '🏐', w: 16, d: 9, hard: true, build: court, cost: 3 },
  parking: { name: 'Parking', icon: '🅿️', w: 20, d: 12, hard: true, build: parking, cost: 4 },
  flowerbed: { name: 'Flower bed', icon: '🌺', w: 4.2, d: 1.6, build: flowerbed, cost: 0.1 },
  lamp: { name: 'Lamp post', icon: '🏮', w: 0.6, d: 0.6, build: lamp, cost: 0.15, small: true },
  bench: { name: 'Bench', icon: '🪑', w: 1.8, d: 0.6, build: bench, cost: 0.1, small: true },
  palm: { name: 'Coconut palm', icon: '🌴', w: 1, d: 1, tree: true, build: () => palmMesh(Math.floor(Math.random() * 3)), cost: 0.05, small: true },
  tree: { name: 'Shade tree', icon: '🌳', w: 1.5, d: 1.5, tree: true, build: () => treeMesh(Math.floor(Math.random() * 3)), cost: 0.05, small: true },
};
