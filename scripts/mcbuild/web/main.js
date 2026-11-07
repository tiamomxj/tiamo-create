// mcbuild preview viewer: vanilla block models + textures, Minecraft-style smooth light & AO, offline single file.
// Reads window.SCENE (voxels, models, atlas, light) and window.PAGE (views, texts). Exposes window.viewer for
// headless screenshots and the making-of video stage.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

THREE.ColorManagement.enabled = false;   // everything stays in sRGB, like Minecraft's own pipeline
const S = window.SCENE;
const PAGE = window.PAGE || {};
const [X0, Y0, Z0, SX, SY, SZ] = S.box;
const DIRV = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
const AO_TAB = [0.52, 0.68, 0.84, 1.0];

async function inflate(b64, Type) {
  const bin = atob(b64), bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Type(await new Response(stream).arrayBuffer());
}

const canvas = document.querySelector('#view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, 1, 0.05, 4000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.12; controls.screenSpacePanning = true;
controls.maxDistance = 900; controls.minDistance = 1.5;

const uniforms = {
  map: { value: null }, daylight: { value: 1 }, alphaTest: { value: 0.5 }, opacity: { value: 1 },
  fogColor: { value: new THREE.Color('#bcd7ea') }, fogNear: { value: 160 }, fogFar: { value: 520 },
  skyTint: { value: new THREE.Color(1, 1, 1) },
};
const vert = `
attribute vec3 tint; attribute vec2 light;
varying vec2 vUv; varying vec3 vTint; varying vec2 vLight; varying float vDepth; varying float vY;
void main(){ vUv = uv; vTint = tint; vLight = light;
  vec4 w = modelMatrix * vec4(position, 1.0); vY = w.y;
  vec4 mv = viewMatrix * w; vDepth = -mv.z; gl_Position = projectionMatrix * mv; }`;
const frag = `
uniform sampler2D map; uniform float daylight, alphaTest, opacity, fogNear, fogFar, cutTop, cutBottom; uniform vec3 fogColor, skyTint;
varying vec2 vUv; varying vec3 vTint; varying vec2 vLight; varying float vDepth; varying float vY;
float curve(float l){ float b = l / (4.0 - 3.0 * l); return mix(b, 1.0 - pow(1.0 - b, 4.0), 0.55); }
void main(){
  if (vY > cutTop || vY < cutBottom) discard;
  vec4 t = texture2D(map, vUv);
  if (t.a < alphaTest) discard;
  float s = curve(vLight.x * daylight);
  float b = curve(vLight.y);
  vec3 lm = max(vec3(s) * skyTint, vec3(b) * vec3(1.0, 0.86, 0.66));
  lm = max(lm, vec3(0.035, 0.04, 0.06));
  vec3 c = t.rgb * vTint * lm;
  c = mix(c, fogColor, smoothstep(fogNear, fogFar, vDepth));
  gl_FragColor = vec4(c, t.a * opacity);
}`;

const cuts = { build: { cutTop: { value: 1e4 }, cutBottom: { value: -1e4 } }, context: { cutTop: { value: 1e4 }, cutBottom: { value: -1e4 } } };
const waterOpacity = { value: 1 };
function material(translucent, layer, water) {
  return new THREE.ShaderMaterial({
    uniforms: { ...uniforms, ...cuts[layer], ...(translucent ? { alphaTest: { value: 0.01 }, opacity: water ? waterOpacity : { value: 1 } } : {}) },
    vertexShader: vert, fragmentShader: frag, transparent: translucent, depthWrite: !translucent,
    side: translucent ? THREE.DoubleSide : THREE.FrontSide,
  });
}

const layers = { build: new THREE.Group(), context: new THREE.Group() };
scene.add(layers.build, layers.context);

async function build() {
  const grid = await inflate(S.grid, Uint16Array);
  const light = await inflate(S.light, Uint8Array);
  const vox = await inflate(S.voxels, Int32Array);
  const img = new Image(); img.src = 'data:image/png;base64,' + S.atlas; await img.decode();
  const tex = new THREE.Texture(img);
  tex.magFilter = THREE.NearestFilter; tex.minFilter = THREE.NearestFilter; tex.generateMipmaps = false;
  tex.flipY = false; tex.colorSpace = THREE.NoColorSpace; tex.needsUpdate = true;
  uniforms.map.value = tex;
  const [AW, AH] = S.atlasSize, TCOLS = AW / 16;
  const OPQ = Uint8Array.from(S.opaque, v => v ? 1 : 0);
  const models = S.models;
  const same = {}; for (const k in models) same[k] = models[k].same;

  const idx = (x, y, z) => { x -= X0; y -= Y0; z -= Z0; return (x < 0 || y < 0 || z < 0 || x >= SX || y >= SY || z >= SZ) ? -1 : (y * SZ + z) * SX + x; };
  const opaqueAt = (x, y, z) => { const i = idx(x, y, z); return i >= 0 && OPQ[grid[i]] === 1; };
  const lightAt = (x, y, z) => { const i = idx(x, y, z); return i < 0 ? 0xF0 : light[i]; };

  const buckets = {};
  const bucket = (layer, group, water) => (buckets[layer + group + (water ? 'w' : '')] ??= { layer, group, water, pos: [], uv: [], tint: [], light: [], index: [] });

  const p = [0, 0, 0], c = [0, 0, 0];
  for (let k = 0; k < vox.length; k += 5) {
    const x = vox[k], y = vox[k + 1], z = vox[k + 2], s = vox[k + 3], layer = vox[k + 4] ? 'build' : 'context';
    const m = models[s];
    if (!m) continue;
    const own = lightAt(x, y, z);
    for (const q of m.q) {
      if (q.c >= 0) {
        const d = DIRV[q.c], ni = idx(x + d[0], y + d[1], z + d[2]);
        if (ni >= 0) {
          const ns = grid[ni];
          if (OPQ[ns] === 1) continue;
          if (m.same && same[ns] === m.same) continue;
        }
      }
      const b = bucket(layer, m.group, m.group === 'translucent' && m.same === 'water');
      const base = b.pos.length / 3;
      const n = q.n;
      let ax = 0; if (Math.abs(n[1]) > Math.abs(n[ax])) ax = 1; if (Math.abs(n[2]) > Math.abs(n[ax])) ax = 2;
      const sg = n[ax] > 0 ? 1 : -1, aligned = Math.abs(n[ax]) > 0.99;
      const ia = (ax + 1) % 3, ja = (ax + 2) % 3;
      c[0] = c[1] = c[2] = 0;
      for (let v = 0; v < 4; v++) for (let a = 0; a < 3; a++) c[a] += q.v[v * 3 + a] / 64;
      const cw = [x + c[0], y + c[1], z + c[2]];
      const shade = n[0] * n[0] * 0.6 + n[2] * n[2] * 0.8 + n[1] * n[1] * (n[1] > 0 ? 1 : 0.5);
      const tint = q.tint || [1, 1, 1];
      const tx = (q.t % TCOLS) * 16, ty = Math.floor(q.t / TCOLS) * 16;
      const front = Math.floor(cw[ax] + 0.5 * sg);
      const ci = Math.floor(cw[ia]), cj = Math.floor(cw[ja]);
      const cell = [0, 0, 0];
      const at = (fa, fi, fj, fn) => { cell[ax] = fa; cell[ia] = fi; cell[ja] = fj; return fn(cell[0], cell[1], cell[2]); };
      let centerL = at(front, ci, cj, lightAt);
      if (at(front, ci, cj, opaqueAt)) centerL = own;
      for (let v = 0; v < 4; v++) {
        p[0] = x + q.v[v * 3] / 16; p[1] = y + q.v[v * 3 + 1] / 16; p[2] = z + q.v[v * 3 + 2] / 16;
        b.pos.push(p[0], p[1], p[2]);
        b.uv.push((tx + Math.min(15.99, Math.max(0.01, q.uv[v * 2]))) / AW, (ty + Math.min(15.99, Math.max(0.01, q.uv[v * 2 + 1]))) / AH);
        let ao = 1, sky = centerL >> 4, blk = centerL & 15;
        if (aligned) {
          const pi = p[ia], pj = p[ja];
          const oi = pi >= ci + 1 - 1e-3 ? ci + 1 : pi <= ci + 1e-3 ? ci - 1 : null;
          const oj = pj >= cj + 1 - 1e-3 ? cj + 1 : pj <= cj + 1e-3 ? cj - 1 : null;
          const s1 = oi !== null && at(front, oi, cj, opaqueAt), s2 = oj !== null && at(front, ci, oj, opaqueAt);
          const cr = oi !== null && oj !== null && at(front, oi, oj, opaqueAt);
          ao = AO_TAB[(s1 && s2) ? 0 : 3 - (s1 + s2 + cr)];
          let cnt = 1;
          if (oi !== null && !s1) { const l = at(front, oi, cj, lightAt); sky += l >> 4; blk += l & 15; cnt++; }
          if (oj !== null && !s2) { const l = at(front, ci, oj, lightAt); sky += l >> 4; blk += l & 15; cnt++; }
          if (oi !== null && oj !== null && !cr && !(s1 && s2)) { const l = at(front, oi, oj, lightAt); sky += l >> 4; blk += l & 15; cnt++; }
          sky /= cnt; blk /= cnt;
        }
        const f = shade * ao;
        b.tint.push(tint[0] * f, tint[1] * f, tint[2] * f);
        b.light.push(sky / 15, blk / 15);
      }
      b.index.push(base, base + 1, base + 2, base, base + 2, base + 3);
    }
  }
  let tris = 0;
  for (const b of Object.values(buckets)) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(b.pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(b.uv, 2));
    g.setAttribute('tint', new THREE.Float32BufferAttribute(b.tint, 3));
    g.setAttribute('light', new THREE.Float32BufferAttribute(b.light, 2));
    g.setIndex(new THREE.Uint32BufferAttribute(b.index, 1));
    g.computeBoundingSphere();
    const mesh = new THREE.Mesh(g, material(b.group === 'translucent', b.layer, b.water));
    mesh.renderOrder = b.group === 'translucent' ? 2 : 0;
    layers[b.layer].add(mesh);
    tris += b.index.length / 3;
  }
  return tris;
}

// ---------------------------------------------------------------- views
const D2R = Math.PI / 180;
const presets = {};
for (const v of (PAGE.views || [])) presets[v.name] = v;
function applyCam(v) {
  if (v.eye) {
    const y = v.yaw * D2R, pt = v.pitch * D2R;
    const f = [-Math.sin(y) * Math.cos(pt), -Math.sin(pt), Math.cos(y) * Math.cos(pt)];
    camera.position.set(...v.eye); controls.target.set(v.eye[0] + f[0] * 40, v.eye[1] + f[1] * 40, v.eye[2] + f[2] * 40);
  } else { camera.position.set(...v.pos); controls.target.set(...v.target); }
  camera.fov = v.fov || 50; camera.updateProjectionMatrix(); controls.update(); dirty = true;
}
function setPreset(name) {
  const v = presets[name]; if (!v) return;
  for (const c of Object.values(cuts)) { c.cutTop.value = v.cut ?? 1e4; c.cutBottom.value = -1e4; }
  applyCam(v);
  window.dispatchEvent(new CustomEvent('preset', { detail: { name, cut: v.cut } }));
}
const SKY = { day: new THREE.Color('#bcd7ea'), dusk: new THREE.Color('#e7a983'), night: new THREE.Color('#0b1426') };
const TINT = { day: new THREE.Color(1, 1, 1), dusk: new THREE.Color(1, 0.84, 0.72), night: new THREE.Color(0.52, 0.62, 1) };
function setDay(t) {           // 0 night .. 0.5 dusk .. 1 day
  const k = t > 0.5 ? (t - 0.5) * 2 : t * 2, a = t > 0.5 ? 'dusk' : 'night', b = t > 0.5 ? 'day' : 'dusk';
  const col = SKY[a].clone().lerp(SKY[b], k);
  uniforms.fogColor.value.copy(col); scene.background = col.clone();
  uniforms.skyTint.value.copy(TINT[a].clone().lerp(TINT[b], k));
  uniforms.daylight.value = 0.24 + 0.76 * Math.pow(t, 0.8);
  dirty = true;
}
let plotOutline = null;
function buildOutline() {
  if (!PAGE.outline || !PAGE.outline.length) return;
  const pos = [], index = [];
  for (const [x0, y, z0, x1, , z1] of PAGE.outline) {
    const b = pos.length / 3; pos.push(x0, y, z0, x1, y, z0, x1, y, z1, x0, y, z1); index.push(b, b + 2, b + 1, b, b + 3, b + 2);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(index);
  plotOutline = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0x1f7bff, side: THREE.DoubleSide, transparent: true, opacity: 0.92, depthWrite: false }));
  plotOutline.renderOrder = 3; scene.add(plotOutline);
}

let dirty = true;
controls.addEventListener('change', () => { dirty = true; });
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); dirty = true;
  }
}
function loop() { resize(); controls.update(); if (dirty) { renderer.render(scene, camera); dirty = false; } requestAnimationFrame(loop); }

window.viewer = {
  setPreset, setDay, presets,
  setCut(top, bottom = -1e4) { for (const c of Object.values(cuts)) { c.cutTop.value = top; c.cutBottom.value = bottom; } dirty = true; },
  setBuildCut(top, bottom = -1e4) { cuts.build.cutTop.value = top; cuts.build.cutBottom.value = bottom; dirty = true; },
  setContextCut(top, bottom = -1e4) { cuts.context.cutTop.value = top; cuts.context.cutBottom.value = bottom; dirty = true; },
  setCamera(pos, target, fov) { applyCam({ pos, target, fov: fov || camera.fov }); },
  setEye(eye, yaw, pitch, fov) { applyCam({ eye, yaw, pitch, fov }); },
  setFog(near, far) { uniforms.fogNear.value = near; uniforms.fogFar.value = far; dirty = true; },
  setWaterOpacity(v) { waterOpacity.value = v; dirty = true; },
  showBuild(v) { layers.build.visible = v; dirty = true; },
  showContext(v) { layers.context.visible = v; dirty = true; },
  showOutline(v) { if (plotOutline) plotOutline.visible = v; dirty = true; },
  render() { resize(); renderer.render(scene, camera); },
  scene, layers, THREE, camera, controls, box: S.box,
};
setDay(1);
build().then(tris => {
  buildOutline();
  const h = new URLSearchParams(location.hash.slice(1));
  setPreset(h.get('view') || (PAGE.views && PAGE.views[0] && PAGE.views[0].name));
  if (h.has('day')) setDay(+h.get('day'));
  if (h.has('ctx')) window.viewer.showContext(h.get('ctx') !== '0');
  window.__ready = { tris };
  document.body.classList.add('ready');
  window.dispatchEvent(new Event('scene-ready'));
}).catch(e => { console.error(e); document.body.dataset.error = e.message; });
loop();
