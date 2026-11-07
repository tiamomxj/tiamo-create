// Headless screenshots of a preview page (Node.js fallback; the kit prefers Python Playwright, see browser.py).
// node shoot.cjs <html> <outdir> <width> <height> view[@day][@cut][@ctx][@h] ...
//   view: preset name, or cam=x,y,z:tx,ty,tz:fov ; day 0..1 ; cut = Y ; ctx 0 hides surroundings ; h hides the panel
const path = require('path');
const { pathToFileURL } = require('url');
const pw = process.env.MCBUILD_PLAYWRIGHT || path.join(process.env.APPDATA || '', 'npm/node_modules/playwright');
const { chromium } = require(pw);
const GPU = [process.platform === 'win32' ? '--use-angle=d3d11' : process.platform === 'darwin' ? '--use-angle=metal' : '--use-angle=vulkan',
  '--enable-gpu', '--ignore-gpu-blocklist'];
const SOFT = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

async function launch() {   // GPU when WebGL works there (~5x faster), SwiftShader otherwise
  for (const opts of [{ channel: 'chromium', args: GPU }, { args: GPU }, { args: SOFT }]) {
    let b;
    try { b = await chromium.launch(opts); } catch (e) { continue; }
    const p = await b.newPage();
    const ok = await p.evaluate(() => { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); });
    await p.close();
    if (ok) return b;
    await b.close();
  }
  throw new Error('no headless Chromium with WebGL (npx playwright install chromium)');
}

(async () => {
  const [html, outdir, W, H, ...views] = process.argv.slice(2);
  const browser = await launch();
  const page = await browser.newPage({ viewport: { width: +W, height: +H }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.type() + ': ' + m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  const t0 = Date.now();
  await page.goto(pathToFileURL(path.resolve(html)).href);
  await page.waitForFunction(() => window.__ready || document.body.dataset.error, null, { timeout: 300000 });
  const info = await page.evaluate(() => ({ ready: window.__ready, error: document.body.dataset.error }));
  console.log('loaded in', Date.now() - t0, 'ms', JSON.stringify(info));
  let n = 0;
  for (const spec of views) {
    const [name, day, cut, ctx, hidepanel] = spec.split('@');
    await page.evaluate(([nm, d, c, x, hp]) => {
      if (nm.startsWith('cam=')) {
        const [pos, tgt, fov] = nm.slice(4).split(':').map(v => v.split(',').map(Number));
        window.viewer.setCamera(pos, tgt, fov ? fov[0] : 60);
      } else window.viewer.setPreset(nm);
      if (d) { const el = document.getElementById('day'); el.value = Math.round(+d * 100); el.dispatchEvent(new Event('input')); }
      if (c) window.viewer.setCut(+c);
      if (x === '0') window.viewer.showContext(false);
      document.querySelector('aside').style.display = hp === 'h' ? 'none' : '';
      document.getElementById('hint').style.display = hp === 'h' ? 'none' : '';
    }, [name, day, cut, ctx, hidepanel]);
    await page.waitForTimeout(500);
    await page.evaluate(() => window.viewer.render());
    const file = (name.startsWith('cam=') ? 'cam' + (n++) : spec.replace(/[@.:=,]/g, '_')) + '.png';
    await page.screenshot({ path: path.join(outdir, file) });
    console.log('shot', file);
    await page.evaluate(() => { window.viewer.showContext(true); window.viewer.setCut(1e4); });
  }
  if (errors.length) console.log('console:\n' + errors.slice(0, 20).join('\n'));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
