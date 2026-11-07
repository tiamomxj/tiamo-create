// Frame capture for the making-of video with Node.js Playwright (fallback; the kit prefers Python Playwright,
// see mcbuild/browser.py). Run from the project's video/ folder.
//   node render.cjs check                         -> run renderFrame every 0.2 s and report script errors
//   node render.cjs stills <out_dir> t1 t2 ...    -> PNG stills at the given times (seconds)
//   node render.cjs segment <out.mp4> <f0> <f1>   -> frames [f0, f1) piped into ffmpeg (H.264, crf 17)
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');
const { spawn } = require('child_process');
const pw = process.env.MCBUILD_PLAYWRIGHT || path.join(process.env.APPDATA || '', 'npm/node_modules/playwright');
const { chromium } = require(pw);
const FFMPEG = process.env.MCBUILD_FFMPEG || 'ffmpeg';
const FPS = 30;
const GPU = [process.platform === 'win32' ? '--use-angle=d3d11' : process.platform === 'darwin' ? '--use-angle=metal' : '--use-angle=vulkan',
  '--enable-gpu', '--ignore-gpu-blocklist', '--allow-file-access-from-files'];
const SOFT = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--allow-file-access-from-files'];

async function launch() {
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
  const [mode, out, ...rest] = process.argv.slice(2);
  const browser = await launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(pathToFileURL(path.join(process.cwd(), 'stage.html')).href);
  await page.waitForFunction(() => window.__stageReady, null, { timeout: 300000 });
  if (mode === 'check') {
    const total = await page.evaluate(() => window.stageInfo.total);
    const bad = await page.evaluate(total => { const o = []; for (let t = 0; t <= total; t += 0.2) { try { window.renderFrame(t); } catch (e) { o.push(t.toFixed(1) + ': ' + e.message); } } return o; }, total);
    console.log('checked', Math.round(total / 0.2), 'frames; errors:', bad.length); bad.slice(0, 20).forEach(b => console.log(b));
  } else if (mode === 'stills') {
    fs.mkdirSync(out, { recursive: true });
    for (const ts of rest) {
      const t = parseFloat(ts);
      await page.evaluate(t => window.renderFrame(t), t);
      await page.screenshot({ path: path.join(out, `t${t.toFixed(2).padStart(7, '0')}.png`) });
    }
    console.log('stills', rest.length);
  } else if (mode === 'segment') {
    const [f0, f1] = rest.map(Number);
    const ff = spawn(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-r', String(FPS), out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    for (let f = f0; f < f1; f++) {
      await page.evaluate(t => window.renderFrame(t), f / FPS);
      const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if ((f - f0) % 300 === 0) console.log(`[${path.basename(out)}] frame ${f} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
  }
  if (errors.length) console.log('PAGE ERRORS:\n' + [...new Set(errors)].slice(0, 20).join('\n'));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
