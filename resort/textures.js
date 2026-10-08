// Procedural canvas textures. Everything is drawn at load time, so the twin needs no texture downloads.
import * as THREE from 'three';

let s = 1234567;
const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);

function canvas(w, h = w) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return [c, c.getContext('2d')];
}
function tex(c, repeat = 1, srgb = true) {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat, repeat);
  t.anisotropy = 8;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
function noise(x, w, h, amt, base) {
  const img = x.getImageData(0, 0, w, h), d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (r() - 0.5) * amt;
    d[i] = Math.max(0, Math.min(255, d[i] + n * (base?.[0] ?? 1)));
    d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + n * (base?.[1] ?? 1)));
    d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + n * (base?.[2] ?? 1)));
  }
  x.putImageData(img, 0, 0);
}
const hsl = (h, sat, l) => `hsl(${h},${sat}%,${l}%)`;

export function asphalt() {
  const [c, x] = canvas(256);
  x.fillStyle = '#4a4b4e'; x.fillRect(0, 0, 256, 256);
  noise(x, 256, 256, 38);
  for (let i = 0; i < 260; i++) { x.fillStyle = `rgba(${r() < 0.5 ? '255,255,255' : '0,0,0'},${r() * 0.12})`; x.fillRect(r() * 256, r() * 256, 2, 2); }
  return tex(c);
}
export function concrete() {
  const [c, x] = canvas(256);
  x.fillStyle = '#a9a69e'; x.fillRect(0, 0, 256, 256);
  noise(x, 256, 256, 26);
  x.strokeStyle = 'rgba(60,55,50,.25)'; x.lineWidth = 1.5;
  x.beginPath(); x.moveTo(0, 128); x.lineTo(256, 128); x.stroke();
  for (let i = 0; i < 40; i++) { x.fillStyle = `rgba(120,95,70,${r() * 0.12})`; x.beginPath(); x.arc(r() * 256, r() * 256, r() * 14, 0, 7); x.fill(); }
  return tex(c);
}
export function laterite() {
  const [c, x] = canvas(512);
  x.fillStyle = '#6b3a2a'; x.fillRect(0, 0, 512, 512);
  const bw = 128, bh = 64;
  for (let row = 0; row < 8; row++)
    for (let col = -1; col < 5; col++) {
      const ox = (row % 2) * (bw / 2);
      x.fillStyle = hsl(10 + r() * 10, 45 + r() * 15, 34 + r() * 10);
      x.fillRect(col * bw + ox + 3, row * bh + 3, bw - 6, bh - 6);
      for (let k = 0; k < 40; k++) { // laterite pores
        x.fillStyle = `rgba(40,15,10,${0.25 + r() * 0.4})`;
        x.beginPath(); x.arc(col * bw + ox + 6 + r() * (bw - 12), row * bh + 6 + r() * (bh - 12), 0.6 + r() * 2.4, 0, 7); x.fill();
      }
    }
  noise(x, 512, 512, 18);
  return tex(c);
}
export function brick(chevron = false) {
  const [c, x] = canvas(512);
  x.fillStyle = '#d8cbb8'; x.fillRect(0, 0, 512, 512);
  const bw = 64, bh = 21;
  for (let row = 0; row < 25; row++)
    for (let col = -1; col < 9; col++) {
      const ox = (row % 2) * (bw / 2);
      let l = 30 + r() * 12, h = 8 + r() * 10, sat = 45 + r() * 15;
      if (chevron) {
        // lighter bricks forming a horizontal band of chevrons, like the villa wall
        const cx = (col * bw + ox + bw / 2) % 256, band = Math.abs(row - 12);
        if (band < 6 && Math.abs(((cx / 256) * 12 + band) % 4 - 2) < 0.6) { l = 70 + r() * 8; sat = 25; h = 35; }
      }
      x.fillStyle = hsl(h, sat, l);
      x.fillRect(col * bw + ox + 2, row * bh + 2, bw - 4, bh - 4);
    }
  noise(x, 512, 512, 20);
  return tex(c);
}
export function roofTiles() {
  const [c, x] = canvas(256);
  x.fillStyle = '#8a3b22'; x.fillRect(0, 0, 256, 256);
  for (let row = 0; row < 8; row++)
    for (let col = 0; col < 8; col++) {
      const g = x.createLinearGradient(0, row * 32, 0, row * 32 + 32);
      const l = 42 + r() * 10;
      g.addColorStop(0, hsl(16, 60, l - 12)); g.addColorStop(0.75, hsl(18, 62, l)); g.addColorStop(1, hsl(16, 55, l - 18));
      x.fillStyle = g;
      x.beginPath();
      x.roundRect(col * 32 + (row % 2) * 16 - 16 + 1, row * 32 + 1, 30, 31, [0, 0, 10, 10]);
      x.fill();
    }
  noise(x, 256, 256, 14);
  return tex(c);
}
export function pavers() {
  const [c, x] = canvas(256);
  x.fillStyle = '#7d6a5a'; x.fillRect(0, 0, 256, 256);
  const u = 16;
  // basket weave: pairs of bricks alternate direction every 32px cell
  for (let i = 0; i < 8; i++)
    for (let j = 0; j < 8; j++)
      for (let k = 0; k < 2; k++) {
        x.fillStyle = hsl(15 + r() * 12, 25 + r() * 15, 52 + r() * 12);
        if ((i + j) % 2 === 0) x.fillRect(i * 32 + 1, j * 32 + k * u + 1, 30, u - 2);
        else x.fillRect(i * 32 + k * u + 1, j * 32 + 1, u - 2, 30);
      }
  noise(x, 256, 256, 16);
  return tex(c);
}
export function gravel() {
  const [c, x] = canvas(256);
  x.fillStyle = '#8c8279'; x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 3000; i++) {
    const l = 30 + r() * 50;
    x.fillStyle = hsl(20 + r() * 20, 8 + r() * 10, l);
    x.beginPath(); x.ellipse(r() * 256, r() * 256, 1 + r() * 2.2, 1 + r() * 1.6, r() * 3, 0, 7); x.fill();
  }
  return tex(c);
}
export function poolTiles() {
  const [c, x] = canvas(256);
  x.fillStyle = '#1b4f9c'; x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 32; i++)
    for (let j = 0; j < 32; j++) { x.fillStyle = hsl(215 + r() * 10, 70, 32 + r() * 14); x.fillRect(i * 8 + 0.5, j * 8 + 0.5, 7, 7); }
  return tex(c);
}
export function deckTiles() {
  const [c, x] = canvas(256);
  for (let row = 0; row < 8; row++) {
    for (let k = 0; k < 2; k++) {
      const y = row * 32;
      const g = x.createLinearGradient(0, y, 256, y);
      for (let t = 0; t <= 1; t += 0.1) g.addColorStop(t, hsl(25 + r() * 10, 35 + r() * 20, 68 + r() * 12));
      x.fillStyle = g; x.fillRect(k * 128 + (row % 2) * 64, y, 128, 32);
    }
    x.fillStyle = 'rgba(80,60,40,.25)'; x.fillRect(0, row * 32, 256, 1);
  }
  noise(x, 256, 256, 10);
  return tex(c);
}
export function canvasFabric(color = '#a39a6e') {
  const [c, x] = canvas(128);
  x.fillStyle = color; x.fillRect(0, 0, 128, 128);
  noise(x, 128, 128, 16);
  x.strokeStyle = 'rgba(0,0,0,.08)';
  for (let i = 0; i < 128; i += 4) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i, 128); x.stroke(); }
  return tex(c);
}
export function scallop() {
  // dark-green valance with scalloped edge and white piping (alpha in canvas)
  const [c, x] = canvas(256, 64);
  x.fillStyle = '#5f6b3a';
  x.beginPath(); x.moveTo(0, 0); x.lineTo(256, 0); x.lineTo(256, 30);
  for (let i = 8; i >= 0; i--) x.quadraticCurveTo(i * 32 + 16, 64, i * 32, 30);
  x.closePath(); x.fill();
  x.strokeStyle = '#efe9d8'; x.lineWidth = 3;
  x.beginPath(); x.moveTo(0, 30); for (let i = 0; i < 8; i++) x.quadraticCurveTo(i * 32 + 16, 62, i * 32 + 32, 30); x.stroke();
  const t = tex(c); t.repeat.set(1, 1);
  return t;
}
export function bark() {
  const [c, x] = canvas(64, 256);
  const g = x.createLinearGradient(0, 0, 64, 0);
  g.addColorStop(0, '#5b4a3c'); g.addColorStop(0.5, '#8a7663'); g.addColorStop(1, '#5b4a3c');
  x.fillStyle = g; x.fillRect(0, 0, 64, 256);
  for (let y = 0; y < 256; y += 6 + r() * 6) { x.fillStyle = `rgba(40,30,22,${0.35 + r() * 0.3})`; x.fillRect(0, y, 64, 1.5 + r() * 2); }
  noise(x, 64, 256, 20);
  return tex(c);
}
export function frond() {
  // a single coconut frond: spine along x, leaflets on both sides, drawn with alpha
  const [c, x] = canvas(512, 128);
  x.clearRect(0, 0, 512, 128);
  x.strokeStyle = '#6f7d34'; x.lineWidth = 4;
  x.beginPath(); x.moveTo(0, 64); x.lineTo(512, 64); x.stroke();
  for (let i = 8; i < 500; i += 7) {
    const t = i / 512, len = 56 * Math.sin(Math.PI * Math.min(1, t * 1.15)) + 6;
    for (const side of [-1, 1]) {
      x.strokeStyle = hsl(70 + r() * 25, 45 + r() * 20, 24 + r() * 16);
      x.lineWidth = 3 + r() * 1.5;
      x.beginPath(); x.moveTo(i, 64);
      x.quadraticCurveTo(i + 10, 64 + side * len * 0.5, i + 20 + r() * 6, 64 + side * len);
      x.stroke();
    }
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}
export function leaves() {
  const [c, x] = canvas(256);
  x.fillStyle = '#2f5a24'; x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 900; i++) {
    x.fillStyle = hsl(85 + r() * 40, 35 + r() * 30, 18 + r() * 26);
    x.beginPath(); x.ellipse(r() * 256, r() * 256, 3 + r() * 5, 1.5 + r() * 2.5, r() * 3, 0, 7); x.fill();
  }
  return tex(c, 1);
}
export function grassDetail() {
  const [c, x] = canvas(256);
  x.fillStyle = '#808080'; x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 4000; i++) { const v = 90 + r() * 90; x.fillStyle = `rgb(${v},${v},${v})`; x.fillRect(r() * 256, r() * 256, 1, 2 + r() * 3); }
  return tex(c, 1, false);
}
export function thatch() {
  const [c, x] = canvas(256);
  x.fillStyle = '#9c7c45'; x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2500; i++) {
    x.strokeStyle = hsl(35 + r() * 10, 40 + r() * 20, 30 + r() * 30);
    const px = r() * 256, py = r() * 256;
    x.beginPath(); x.moveTo(px, py); x.lineTo(px + (r() - 0.5) * 4, py + 10 + r() * 14); x.stroke();
  }
  return tex(c);
}
export function net() {
  const [c, x] = canvas(128);
  x.clearRect(0, 0, 128, 128);
  x.strokeStyle = '#4a5068'; x.lineWidth = 2.2;
  for (let i = -128; i < 256; i += 10) {
    x.beginPath(); x.moveTo(i, 0); x.lineTo(i + 128, 128); x.stroke();
    x.beginPath(); x.moveTo(i + 128, 0); x.lineTo(i, 128); x.stroke();
  }
  return tex(c, 1);
}
export function wood() {
  const [c, x] = canvas(128);
  x.fillStyle = '#8a5a34'; x.fillRect(0, 0, 128, 128);
  for (let y = 0; y < 128; y += 2) { x.fillStyle = `rgba(60,35,18,${r() * 0.35})`; x.fillRect(0, y, 128, 1); }
  noise(x, 128, 128, 14);
  return tex(c);
}
export function signText(text, sub) {
  const [c, x] = canvas(1024, 256);
  const g = x.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, '#5a3820'); g.addColorStop(1, '#3e2614');
  x.fillStyle = g; x.fillRect(0, 0, 1024, 256);
  x.strokeStyle = '#c9a46a'; x.lineWidth = 8; x.strokeRect(14, 14, 996, 228);
  x.fillStyle = '#f3e3c0'; x.textAlign = 'center'; x.textBaseline = 'middle';
  x.font = 'italic 700 110px Georgia, serif'; x.fillText(text, 512, sub ? 112 : 128);
  if (sub) { x.font = '600 38px Georgia, serif'; x.fillStyle = '#d8bf8e'; x.fillText(sub, 512, 200); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}
export function water() {
  // soft caustic-like ripples; scrolled every frame for motion
  const [c, x] = canvas(256);
  x.fillStyle = '#8fd3f4'; x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 140; i++) {
    x.strokeStyle = `rgba(255,255,255,${0.08 + r() * 0.22})`; x.lineWidth = 1 + r() * 2.5;
    x.beginPath(); const px = r() * 256, py = r() * 256;
    x.ellipse(px, py, 8 + r() * 22, 4 + r() * 10, r() * 3, 0, Math.PI * (1 + r()));
    x.stroke();
  }
  return tex(c, 2);
}
