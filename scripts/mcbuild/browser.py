"""Headless Chromium for preview screenshots and making-of video frames.

Backends, in order: Python Playwright (`pip install playwright` + `python -m playwright install chromium`), then a
Node.js Playwright install (web/shoot.cjs, video/render.cjs). WebGL runs on the GPU when the platform allows it
(ANGLE: D3D11 on Windows, Metal on macOS, Vulkan on Linux) and falls back to SwiftShader (CPU) otherwise.

    python -m mcbuild.browser segment <video_dir> <out.mp4> <f0> <f1>      (used by `mcb video render` workers)
"""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
from .util import IS_WIN, IS_MAC, KIT, find_node, find_playwright, python_playwright, log

GPU_ARGS = (['--use-angle=d3d11'] if IS_WIN else ['--use-angle=metal'] if IS_MAC else ['--use-angle=vulkan', '--enable-features=Vulkan']) \
    + ['--enable-gpu', '--ignore-gpu-blocklist']
SOFT_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']
HAS_WEBGL = "() => { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); }"


def backend():
    """'python' | 'node' | None."""
    if python_playwright():
        return 'python'
    if find_node() and find_playwright():
        return 'node'
    return None


def install_hint():
    py = Path(sys.executable).name
    return f'{py} -m pip install playwright && {py} -m playwright install chromium'


def launch(p, extra=()):
    """A Chromium (Python Playwright handle) whose WebGL works: GPU first, SwiftShader second."""
    last = None
    for kw in ({'channel': 'chromium', 'args': GPU_ARGS + list(extra)}, {'args': GPU_ARGS + list(extra)},
               {'args': SOFT_ARGS + list(extra)}):
        try:
            b = p.chromium.launch(**kw)
        except Exception as e:                    # channel not installed, no GPU process ...
            last = e
            continue
        pg = b.new_page()
        ok = pg.evaluate(HAS_WEBGL)
        pg.close()
        if ok:
            return b
        b.close()
    raise RuntimeError(f'no headless Chromium with WebGL ({last}); try: {install_hint()}')


SHOT_JS = """([nm, d, c, x, hp]) => {
  if (nm.startsWith('cam=')) {
    const [pos, tgt, fov] = nm.slice(4).split(':').map(v => v.split(',').map(Number));
    window.viewer.setCamera(pos, tgt, fov ? fov[0] : 60);
  } else window.viewer.setPreset(nm);
  if (d) { const el = document.getElementById('day'); el.value = Math.round(+d * 100); el.dispatchEvent(new Event('input')); }
  if (c) window.viewer.setCut(+c);
  if (x === '0') window.viewer.showContext(false);
  document.querySelector('aside').style.display = hp === 'h' ? 'none' : '';
  document.getElementById('hint').style.display = hp === 'h' ? 'none' : '';
}"""


def shoot_python(html, out_dir, width, height, views):
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    files, errors = [], []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={'width': int(width), 'height': int(height)}, device_scale_factor=1)
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(Path(html).resolve().as_uri())
        page.wait_for_function('() => window.__ready || document.body.dataset.error', timeout=300000)
        info = page.evaluate('() => ({ready: window.__ready, error: document.body.dataset.error})')
        log('page loaded', info)
        if info.get('error'):
            raise RuntimeError('preview page error: ' + info['error'])
        n = 0
        for spec in views:
            parts = (spec.split('@') + [''] * 5)[:5]
            page.evaluate(SHOT_JS, parts)
            page.wait_for_timeout(500)
            page.evaluate('() => window.viewer.render()')
            name = ('cam' + str(n)) if parts[0].startswith('cam=') else ''.join('_' if ch in '@.:=,' else ch for ch in spec)
            n += parts[0].startswith('cam=')
            f = out_dir / f'{name}.png'
            page.screenshot(path=str(f))
            files.append(f)
            log('shot', f.name)
            page.evaluate('() => { window.viewer.showContext(true); window.viewer.setCut(1e4); }')
        b.close()
    if errors:
        log('console errors:', *errors[:10])
    return files


def shoot_node(html, out_dir, width, height, views):
    node, pw = find_node(), find_playwright()
    cmd = [node, str(KIT / 'web' / 'shoot.cjs'), str(html), str(out_dir), str(width), str(height), *views]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env=dict(os.environ, MCBUILD_PLAYWRIGHT=str(pw)), timeout=900)
    print(r.stdout[-3000:], r.stderr[-2000:])
    return sorted(Path(out_dir).glob('*.png'))


def shoot(html, out_dir, width, height, views):
    """Screenshots of a preview page; [] (with a hint) when no browser backend exists."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    be = backend()
    if be == 'python':
        try:
            return shoot_python(html, out_dir, width, height, views)
        except Exception as e:
            log('Python Playwright failed:', e)
            if not (find_node() and find_playwright()):
                log('fix:', install_hint())
                return []
            log('trying Node Playwright ...')
    if find_node() and find_playwright():
        return shoot_node(html, out_dir, width, height, views)
    log('skipping screenshots: no Playwright. Install with:', install_hint())
    return []


# ------------------------------------------------------------------ making-of video frames
def video_python(vdir, mode, out, args, ffmpeg=None):
    """mode check | stills <dir> t... | segment <out.mp4> f0 f1   (same as video/render.cjs)."""
    from playwright.sync_api import sync_playwright
    vdir = Path(vdir)
    FPS = 30
    errors = []
    with sync_playwright() as p:
        b = launch(p, ['--allow-file-access-from-files'])
        page = b.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.goto((vdir / 'stage.html').resolve().as_uri())
        page.wait_for_function('() => window.__stageReady', timeout=300000)
        if mode == 'check':
            total = page.evaluate('() => window.stageInfo.total')
            bad = page.evaluate("""total => { const o = []; for (let t = 0; t <= total; t += 0.2) {
                try { window.renderFrame(t); } catch (e) { o.push(t.toFixed(1) + ': ' + e.message); } } return o; }""", total)
            log('checked', round(total / 0.2), 'frames; errors:', len(bad))
            for x in bad[:20]:
                log(x)
        elif mode == 'stills':
            od = vdir / out; od.mkdir(parents=True, exist_ok=True)
            for ts in args:
                t = float(ts)
                page.evaluate('t => window.renderFrame(t)', t)
                page.screenshot(path=str(od / f't{t:07.2f}.png'))
            log('stills', len(args))
        elif mode == 'segment':
            f0, f1 = int(args[0]), int(args[1])
            ff = subprocess.Popen([ffmpeg or 'ffmpeg', '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'mjpeg',
                                   '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-r', str(FPS),
                                   str(out)], stdin=subprocess.PIPE)
            for f in range(f0, f1):
                page.evaluate('t => window.renderFrame(t)', f / FPS)
                ff.stdin.write(page.screenshot(type='jpeg', quality=95))
                if (f - f0) % 300 == 0:
                    log(f'[{Path(out).name}] frame {f}')
            ff.stdin.close()
            if ff.wait() != 0:
                raise SystemExit('ffmpeg failed while encoding ' + str(out))
        b.close()
    if errors:
        log('PAGE ERRORS:', *sorted(set(errors))[:20])


if __name__ == '__main__':                          # worker entry for parallel video segments
    sys.stdout.reconfigure(encoding='utf-8')
    _, mode, vd, out, *rest = sys.argv
    video_python(vd, mode, out, rest, os.environ.get('MCBUILD_FFMPEG'))
