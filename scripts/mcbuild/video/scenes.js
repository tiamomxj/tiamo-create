// Generic making-of chapters. They read window.VIDEO_DATA (written by `mcb video init`) and the narration timeline,
// so they work unchanged for any project; edit/add scenes for project-specific moments (camera fit, a design change,
// a comparison). A scene only appears if its id is in video/script.py. Helpers: see stage-lib.js (window.STAGE).
(function () {
  const S = window.STAGE, D = S.D, { el, img, chip, pop, show, kf, win, ramp, eout, ease, SL, use3D, dark, orbit, scene } = S;
  const U = D.ui || {};   // labels in the project language (written by `mcb video init`)
  const B = D.build || {};
  const C = B.center || [0, 64, 0];
  const R = Math.max(20, (B.radius || 20) * 2.4);

  // ---------------------------------------------------------------- opening: title over the best picture
  scene('opening', (r, s) => {
    s.bg = img(D.hero, { class: 'cover' }, r);
    el('div', { class: 'full', style: { background: 'linear-gradient(90deg,rgba(6,8,12,.84) 0%,rgba(6,8,12,.45) 42%,rgba(6,8,12,0) 72%)' } }, r);
    const tb = el('div', { class: 'abs', style: { left: '140px', top: '300px' } }, r);
    s.t1 = el('div', { class: 'tag', style: { background: 'rgba(233,200,143,.16)', color: '#e9c88f', border: '1px solid rgba(233,200,143,.4)' } }, tb, U.tag || `MINECRAFT JAVA ${D.version}`);
    s.t2 = el('div', { style: { fontSize: '150px', fontWeight: 800, letterSpacing: '.06em', marginTop: '26px', lineHeight: 1.1 } }, tb, D.title || '');
    s.t3 = el('div', { style: { fontSize: '30px', letterSpacing: '.36em', color: '#cdd7df', marginTop: '16px' } }, tb, D.subtitle || '');
    s.t4 = el('div', { style: { fontSize: '46px', color: '#f5efe4', marginTop: '50px', fontWeight: 600 } }, tb, D.tagline || '');
  }, (t, s) => {
    const k = ramp(t, 0, s.data.end + 1);
    s.bg.style.transform = `scale(${1.04 + 0.08 * k})`;
    [s.t1, s.t2, s.t3, s.t4].forEach((e, i) => pop(e, t, 0.35 + i * 0.35, 0.9, 26));
  });

  // ---------------------------------------------------------------- the request: input images + brief
  scene('request', (r, s) => {
    dark(r);
    s.cards = (D.inputs || []).slice(0, 2).map((src, i, a) => {
      const w = a.length === 1 ? 1100 : 820, x = a.length === 1 ? 410 : 90 + i * 900;
      const c = el('div', { class: 'card', style: { left: x + 'px', top: '150px', width: w + 'px', height: (w * 9 / 16) + 'px' } }, r);
      img(src, { class: 'contain', style: { left: 0, top: 0, width: '100%', height: '100%', objectFit: 'cover' } }, c);
      return c;
    });
    s.chips = (D.brief || []).slice(0, 5).map((txt, i) => chip(r, txt, 120 + (i % 2) * 860, (D.inputs || []).length ? 690 + Math.floor(i / 2) * 76 : 260 + i * 90, 'chip dark'));
  }, (t, s) => {
    s.cards.forEach((c, i) => pop(c, t, s.data.start + 0.2 + i * 0.5, 0.7, 30));
    s.chips.forEach((c, i) => pop(c, t, SL('request', Math.min(i, 3)) + 0.3 + i * 0.25, 0.5));
  });

  // ---------------------------------------------------------------- site data: the real terrain map
  scene('site', (r, s) => {
    dark(r);
    s.map = img(D.siteMap, { class: 'contain', style: { left: '80px', top: '120px', width: '1100px', height: '840px' } }, r);
    s.info = el('div', { class: 'dcard', style: { left: '1240px', top: '200px', width: '600px', padding: '30px 36px', opacity: 0 } }, r,
      (D.siteFacts || []).map(([k, v]) => `<div class="h-label" style="margin-top:14px">${k}</div><div style="font-size:40px;font-weight:700" class="num">${v}</div>`).join(''));
  }, (t, s) => {
    const u = ramp(t, s.data.start - 0.4, s.data.end - s.data.start + 1);
    show(s.map, eout(ramp(t, s.data.start - 0.2, 0.8)), 0, 0, 1 + 0.06 * u);
    pop(s.info, t, SL('site', 1) - 0.2, 0.6);
  });

  // ---------------------------------------------------------------- locating: camera overlay / plot / analysis
  scene('locate', (r, s) => {
    dark(r);
    s.pics = (D.locateImages || []).slice(0, 2).map((src, i, a) => img(src, { class: 'contain', style: {
      left: (a.length === 1 ? 260 : 60 + i * 920) + 'px', top: '150px', width: (a.length === 1 ? 1400 : 880) + 'px', height: '780px', opacity: 0 } }, r));
    s.origin = chip(r, `${U.origin || 'Origin'} ${(D.origin || []).join(' ')}`, 760, 900, 'chip', { background: '#e0a640' });
  }, (t, s) => {
    s.pics.forEach((p, i) => pop(p, t, SL('locate', i) - 0.2, 0.7, 24));
    pop(s.origin, t, SL('locate', 2) - 0.2, 0.5);
  });

  // ---------------------------------------------------------------- style: reference stats or the palette
  scene('style', (r, s) => {
    dark(r);
    if (D.styleImage) s.pic = img(D.styleImage, { class: 'contain', style: { left: '80px', top: '140px', width: '1000px', height: '800px', opacity: 0 } }, r);
    s.pal = el('div', { class: 'dcard', style: { left: D.styleImage ? '1140px' : '560px', top: '170px', width: '700px', padding: '30px 36px', opacity: 0 } }, r,
      `<div class="h-label">${U.palette || 'Palette'}</div>` + (D.palette || []).slice(0, 8).map(([zh, rgb, n]) =>
        `<div class="row" style="margin-top:16px"><div class="sw" style="background:rgb(${rgb.join(',')})"></div><div style="font-size:32px;flex:1">${zh}</div><div class="num" style="font-size:28px;color:#9fb0c0">${n}</div></div>`).join(''));
  }, (t, s) => {
    if (s.pic) pop(s.pic, t, s.data.start, 0.7);
    pop(s.pal, t, SL('style', 0) + 0.6, 0.7);
  });

  // ---------------------------------------------------------------- design: the build rises layer by layer
  scene('design', (r, s) => {
    s.label = chip(r, '', 80, 960, 'chip dark');
  }, (t, s, o) => {
    const t0 = s.data.start, t1 = s.data.end;
    const u = ramp(t, t0 + 0.4, (t1 - t0) * 0.75);
    const y = B.y0 - 1 + (B.y1 - B.y0 + 2) * ease(u);
    const c = [C[0], Math.min(C[1], Math.max(B.y0 + 2, y - 2)), C[2]];          // look at the rising top
    use3D({ ...orbit(c, R, R * 0.45, 30 + 70 * ramp(t, t0, t1 - t0 + 1)), buildCut: y, fov: 45 }, o);
    s.label.textContent = u < 1 ? `Y = ${Math.floor(y)}` : `${S.fmt(D.blocks || 0)} ${U.blocks || 'blocks'}`;
    show(s.label, Math.min(o, eout(ramp(t, t0 + 0.4, 0.5))));
  });

  // ---------------------------------------------------------------- verification checklist
  scene('verify', (r, s) => {
    dark(r);
    s.rows = (D.checks || []).map(([title, value], i) => {
      const row = el('div', { class: 'row abs', style: { left: '220px', top: (190 + i * 108) + 'px', opacity: 0 } }, r);
      el('div', { class: 'check' }, row, '✓');
      el('div', { style: { fontSize: '38px', fontWeight: 600, width: '760px' } }, row, title);
      el('div', { class: 'num', style: { fontSize: '40px', color: '#e8c88f', fontWeight: 700 } }, row, value);
      return row;
    });
  }, (t, s) => {
    const n = s.rows.length, t0 = s.data.start + 0.3, t1 = s.data.end - 1;
    s.rows.forEach((row, i) => pop(row, t, t0 + (t1 - t0) * i / Math.max(1, n), 0.5, 18));
  });

  // ---------------------------------------------------------------- preview / in-game: orbit, day to night
  scene('preview', (r, s) => {
    s.shots = (D.ingame || []).slice(0, 3).map(src => img(src, { class: 'cover', style: { opacity: 0 } }, r));
  }, (t, s, o) => {
    const t0 = s.data.start, t1 = s.data.end, half = t0 + (t1 - t0) * 0.55;
    const day = 1 - 0.85 * ramp(t, t0 + (t1 - t0) * 0.3, (t1 - t0) * 0.3);
    use3D({ ...orbit(C, R * 0.9, R * 0.35, 200 + 60 * ramp(t, t0, t1 - t0)), day, fov: 50 }, o * (1 - ramp(t, half, 0.6)));
    s.shots.forEach((e, i) => { const a = half + i * (t1 - half) / Math.max(1, s.shots.length); e.style.opacity = win(t, a, a + (t1 - half) / Math.max(1, s.shots.length) + 0.4, 0.5, 0.5); e.style.transform = `scale(${1.02 + 0.04 * ramp(t, a, 5)})`; });
  });

  // ---------------------------------------------------------------- ending: how to place it
  scene('ending', (r, s) => {
    s.bg = img(D.endImage || D.hero, { class: 'cover' }, r);
    el('div', { class: 'full', style: { background: 'linear-gradient(90deg,rgba(6,8,12,.85) 0%,rgba(6,8,12,.45) 55%,rgba(6,8,12,.15) 100%)' } }, r);
    s.info = el('div', { class: 'dcard', style: { left: '120px', top: '260px', width: '1100px', padding: '36px 44px', opacity: 0 } }, r,
      D.mode === 'site'
        ? `<div class="h-label">${U.placeOrigin || 'Placement origin'}  X · Y · Z</div><div class="num mono" style="font-size:92px;font-weight:700;margin:4px 0 20px;white-space:nowrap">${(D.origin || []).join(' · ')}</div>
           <div class="row" style="gap:14px"><span class="tag" style="background:#2b3a4c;font-size:28px">${U.noRotate || 'no rotation'}</span><span class="tag" style="background:#2b3a4c;font-size:28px">${U.noMirror || 'no mirror'}</span><span class="tag" style="background:#2fa36b;font-size:28px">${U.paste || 'Paste: With non-air'}</span></div>`
        : `<div class="h-label">${U.schematic || 'Schematic'}</div><div style="font-size:60px;font-weight:700;margin:8px 0 18px">${D.file || ''}</div><div style="font-size:32px;color:#c9d4de">${U.anywhere || ''}</div>`);
    s.end = el('div', { class: 'abs', style: { left: 0, width: '1920px', top: '360px', textAlign: 'center', opacity: 0 } }, r,
      `<div style="font-size:140px;font-weight:800;letter-spacing:.06em">${D.title || ''}</div><div style="font-size:30px;letter-spacing:.36em;color:#cdd7df;margin-top:12px">${D.subtitle || ''}</div>
       <div style="font-size:24px;color:#9fb0c0;margin-top:60px;letter-spacing:.08em">Minecraft Java ${D.version} · Litematica · ${U.credit || ''}</div>`);
  }, (t, s) => {
    s.bg.style.transform = `scale(${1.03 + 0.05 * ramp(t, s.data.start, 8)})`;
    const lastLine = SL('ending', 99);
    show(s.info, eout(ramp(t, s.data.start, 0.7)) * (1 - ramp(t, lastLine - 0.5, 0.5)));
    pop(s.end, t, lastLine - 0.2, 0.9, 20);
  });
})();
