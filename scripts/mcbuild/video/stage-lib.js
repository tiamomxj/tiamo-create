// mcbuild making-of video stage library. Every frame is a pure function of time t: window.renderFrame(t).
// Load order in stage.html: timeline.js, data.js, ../artifacts/preview/scene.js, page.js, viewer.bundle.js,
// stage-lib.js, scenes.js.  Scenes register with STAGE.scene(id, build(root, s), draw(t, s, opacity)).
(function () {
  'use strict';
  const TL = window.TIMELINE;
  const W = 1920, H = 1080;
  const layers = document.getElementById('layers');
  const V = () => window.viewer;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const ease = t => (t = clamp(t), t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const eout = t => (t = clamp(t), 1 - Math.pow(1 - t, 3));
  const ramp = (t, a, d = .5) => clamp((t - a) / d);
  const win = (t, a, b, din = .45, dout = .45) => Math.min(ramp(t, a, din), 1 - ramp(t, b - dout, dout));
  const lines = id => TL.lines.filter(l => l.scene === id);
  const L = n => TL.lines[n].start;                        // global line index -> start time
  const LE = n => TL.lines[n].start + TL.lines[n].dur;
  const F = (n, k) => TL.lines[n].subs[Math.min(k, TL.lines[n].subs.length - 1)].start;
  const SL = (id, k = 0) => { const ls = lines(id); return ls.length ? ls[Math.min(k, ls.length - 1)].start : SC(id).start; };   // k-th line of a scene
  const SC = id => TL.scenes.find(s => s.id === id);
  const fmt = n => Math.round(n).toLocaleString('en-US');
  const lerp3 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
  function mix(a, b, u) {
    if (Array.isArray(a)) return a.map((x, i) => mix(x, b[i], u));
    if (a && typeof a === 'object') { const o = {}; for (const k in a) o[k] = mix(a[k], b[k], u); return o; }
    return lerp(a, b, u);
  }
  function kf(t, keys) {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 0; i < keys.length - 1; i++) {
      const [t0, v0] = keys[i], [t1, v1] = keys[i + 1];
      if (t <= t1) return mix(v0, v1, ease((t - t0) / Math.max(1e-6, t1 - t0)));
    }
    return keys[keys.length - 1][1];
  }
  function el(tag, attrs = {}, parent, html) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'style') Object.assign(e.style, v); else if (k === 'class') e.className = v; else e.setAttribute(k, v);
    }
    if (html !== undefined) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  }
  function show(e, o, tx = 0, ty = 0, s = 1) {
    e.style.opacity = o;
    e.style.transform = `translate(${tx}px,${ty}px) scale(${s})`;
    e.style.visibility = o <= 0.002 ? 'hidden' : 'visible';
  }
  const pop = (e, t, t0, d = .55, dy = 22) => { const u = eout(ramp(t, t0, d)); show(e, u, 0, dy * (1 - u)); return u; };
  const IMGS = [];
  function img(src, attrs = {}, parent) { const e = el('img', { src, ...attrs }, parent); IMGS.push(e); return e; }
  function chip(parent, text, x, y, cls = 'chip', extra = {}) {
    return el('div', { class: cls, style: { left: x + 'px', top: y + 'px', opacity: 0, ...extra } }, parent, text);
  }
  const dark = r => { el('div', { class: 'darkbg' }, r); el('div', { class: 'gridbg' }, r); };

  // ---------------------------------------------------------------- 3D director (reuses the preview engine)
  let gl = null; const post = [];
  const use3D = (p, o) => { if (o > 0.002 && (!gl || o > gl.o)) gl = { ...p, o }; };
  function apply3D() {
    const c = document.getElementById('view');
    if (!gl) { c.style.opacity = 0; return; }
    const v = V();
    v.showContext(gl.context !== false); v.showBuild(gl.build !== false); v.showOutline(!!gl.outline);
    v.setDay(gl.day ?? 1);
    v.setCut(gl.cut ?? 1e4, gl.cutBottom ?? -1e4);
    if (gl.buildCut !== undefined) v.setBuildCut(gl.buildCut, gl.buildCutBottom ?? -1e4);
    v.setFog(gl.fogNear ?? 160, gl.fogFar ?? 520);
    v.setWaterOpacity(gl.waterOpacity ?? 1);
    if (gl.eye) v.setEye(gl.eye, gl.yaw, gl.pitch, gl.fov ?? 70); else v.setCamera(gl.pos, gl.target, gl.fov ?? 50);
    if (gl.bg) v.scene.background = new v.THREE.Color(gl.bg);
    if (gl.hook) gl.hook(v);
    v.camera.updateMatrixWorld();
    v.render();
    c.style.opacity = gl.o;
  }
  function toScreen(p) {
    const v = V(); const q = new v.THREE.Vector3(p[0], p[1], p[2]).project(v.camera);
    return [(q.x + 1) / 2 * W, (1 - q.y) / 2 * H, q.z];
  }
  function anchorLabel(e, p, o, dx = 0, dy = -70) {
    post.push(() => {
      const [x, y, z] = toScreen(p);
      if (z > 1 || o <= 0.002) { show(e, 0); return; }
      e.style.left = (x + dx) + 'px'; e.style.top = (y + dy) + 'px';
      show(e, o, 0, 0, 1);
    });
  }
  function label3D(parent, text) {
    const wrap = el('div', { class: 'abs', style: { opacity: 0 } }, parent);
    el('div', { class: 'chip', style: { position: 'relative', transform: 'translate(-50%,0)', left: 0, top: 0 } }, wrap, text);
    el('div', { style: { position: 'absolute', left: '-7px', top: '66px', width: '14px', height: '14px', borderRadius: '50%', background: '#fff', boxShadow: '0 0 0 5px rgba(255,255,255,.3)' } }, wrap);
    el('div', { style: { position: 'absolute', left: '-1px', top: '52px', width: '2px', height: '16px', background: 'rgba(255,255,255,.9)' } }, wrap);
    return wrap;
  }
  // orbit helper: camera on a circle around `c` (radius r, height h) at angle a (degrees, 0 = from +x)
  const orbit = (c, r, h, a) => ({ pos: [c[0] + Math.cos(a * Math.PI / 180) * r, c[1] + h, c[2] + Math.sin(a * Math.PI / 180) * r], target: c });

  // ---------------------------------------------------------------- scenes + frame loop
  const scenes = [];
  function scene(id, build, draw) {
    if (!SC(id)) return null;                               // scene not in the narration: skip
    const root = el('div', { class: 'scene' }, layers);
    const s = { id, root, data: SC(id), draw };
    build(root, s); scenes.push(s); return s;
  }
  const subs = TL.lines.flatMap(l => l.subs);
  window.renderFrame = function (t) {
    const hud = { progress: document.getElementById('progress'), chapter: document.getElementById('chapter'), sub: document.getElementById('sub'),
                  fade: document.getElementById('fade'), brand: document.getElementById('brand') };
    gl = null; post.length = 0;
    const first = TL.scenes[0].id, last = TL.scenes[TL.scenes.length - 1].id;
    for (const s of scenes) {
      const d = s.data, a = s.id === first ? -1 : d.start - 0.5, b = s.id === last ? TL.total + 1 : d.end + 0.55;
      const o = s.id === first ? 1 - ramp(t, b - 0.5, 0.5) : win(t, a, b, 0.5, 0.5);
      if (o <= 0.001) { s.root.style.display = 'none'; continue; }
      s.root.style.display = 'block'; s.root.style.opacity = o;
      s.draw(t, s, o);
    }
    apply3D();
    for (const fn of post) fn();
    hud.progress.style.width = (W * clamp(t / TL.total)) + 'px';
    const sc = TL.scenes.find(x => t >= x.start - 0.3 && t < x.end + 0.4);
    if (sc && sc.title) { hud.chapter.textContent = sc.title; hud.chapter.style.opacity = win(t, sc.start - 0.3, sc.end + 0.4, 0.4, 0.4); } else hud.chapter.style.opacity = 0;
    hud.brand.style.opacity = sc && sc.title ? 1 : 0;
    let cur = null; for (const x of subs) if (t >= x.start - 0.04 && t < x.end + 0.1) cur = x;
    if (cur) { if (hud.sub.textContent !== cur.text) hud.sub.textContent = cur.text; hud.sub.style.opacity = Math.min(ramp(t, cur.start - 0.04, 0.1), 1); } else hud.sub.style.opacity = 0;
    hud.fade.style.opacity = Math.max(1 - ramp(t, 0, 0.9), ramp(t, TL.total - 1.6, 1.5));
  };
  window.stageInfo = { total: TL.total, fps: 30 };
  window.STAGE = { W, H, TL, D: window.VIDEO_DATA || {}, V, clamp, lerp, lerp3, ease, eout, ramp, win, L, LE, F, SL, SC, lines, fmt, mix, kf,
                   el, show, pop, img, chip, dark, use3D, toScreen, anchorLabel, label3D, orbit, scene };
  window.addEventListener('load', async () => {
    await new Promise(res => { const c = () => window.__ready ? res() : setTimeout(c, 50); c(); });
    // complete is also true for images that already failed: never wait for those (a missing picture must not block the video)
    await Promise.all(IMGS.map(i => i.complete ? null : new Promise(res => { i.onload = i.onerror = res; })));
    await Promise.all(IMGS.map(i => i.decode ? i.decode().catch(() => null) : null));
    window.renderFrame(0);
    window.__stageReady = true;
  });
})();
