"""Making-of video: narration (edge-tts, word-timed subtitles) → stage (HTML, pure function of time, reusing the
preview engine) → frames (Playwright, parallel segments) → H.264 + synthesized music bed + loudness → mp4/srt/cover.

mcb video init       copy stage files into <project>/video, write data.js from the project's artifacts
mcb video narrate    script.py → audio/lineNN.mp3 + timeline.json/js   (needs edge-tts >= 7.3.1)
mcb video check      run every 0.2 s of the timeline, report script errors
mcb video stills t…  PNG stills to video/stills (look at every chapter!)
mcb video render     mix audio, render segments in parallel, encode → release/<name>-making-of.mp4 (+ .srt, cover)
                     (file names and on-screen labels follow the project language)
"""
from __future__ import annotations
import asyncio, glob, json, math, os, runpy, shutil, subprocess, sys, wave
from pathlib import Path
import numpy as np
from .util import KIT, HOME, log, read_json, write_json, find_node, find_playwright, find_ffmpeg, python_playwright
from .registry import version, AIR
from .i18n import t, block_name, lang

SRC = KIT / 'video'
LINE_GAP, SCENE_GAP, HEAD, TAIL = 0.42, 0.95, 1.6, 3.2


def duration(path, ff=None):
    """Seconds of an audio file: ffprobe next to ffmpeg when present, else decoded length."""
    ff = ff or find_ffmpeg()
    probe = Path(ff).with_name('ffprobe' + Path(ff).suffix)
    if probe.exists():
        r = subprocess.run([str(probe), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                           capture_output=True, text=True, check=True)
        return float(r.stdout.strip())
    raw = subprocess.run([ff, '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'], capture_output=True, check=True).stdout
    return len(raw) / 4 / 48000


def vdir(P):
    d = P.root / 'video'
    d.mkdir(exist_ok=True)
    return d


def rel(P, p):
    return os.path.relpath(p, vdir(P)).replace('\\', '/')


# ------------------------------------------------------------------ data for the generic scenes
def video_data(P):
    from .maps import state_colors
    B = P.design()
    rep = read_json(P.art / 'export-report.json') or read_json(P.art / 'litematic-report.json') or {}
    is_create = rep.get('format') == 'create'
    ver = read_json(P.art / 'verification.json') or {}
    ig = {} if is_create else read_json(P.art / 'ingame' / 'ingame-report.json') or {}
    pc = P.cfg.get('preview', {}); vc = P.cfg.get('video', {})
    ingame = [] if is_create else sorted((P.art / 'ingame').glob('*.png'))
    shots = sorted((P.art / 'shots').glob('*.png'))
    pick = lambda files, keys: next((f for k in keys for f in files if k in f.stem), files[0] if files else None)
    hero = pick(ingame, ['overview']) or pick(shots, ['overview'])
    end = pick(ingame, ['night', 'dusk']) or hero
    inputs = [p for p in sorted(P.input.glob('*')) if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')][:2]
    brief = vc.get('brief') or []
    bp = P.art / 'brief.md'
    if not brief and bp.exists():
        brief = [l.strip('-* ').strip() for l in bp.read_text(encoding='utf-8').splitlines() if l.strip().startswith(('-', '*'))][:5]
    site = B.site
    facts_ = []
    if site is not None:
        kind = site.source.get('kind', '?')
        facts_ += [[t('vid.source'), t('src.' + kind)],
                   [t('vid.box'), f'{site.W} × {site.D} × {site.H}']]
    an = read_json(P.art / 'analysis.json')
    if an:
        facts_ += [[t('vid.builds'), t('vid.builds_v', n=len([b for b in an['builds'] if not b.get('underground')]))],
                   [t('vid.ground'), f"{an['ground']['min']}–{an['ground']['max']}"]]
    locate = [p for p in [P.art / 'camera-overlay.png', P.art / 'plot-map.png', P.art / 'analysis-map.png'] if p.exists()][:2]
    style = sorted(P.art.glob('style-*.png'))
    blocks = B.blocks()
    from collections import Counter
    top = Counter(st for st in blocks.values()).most_common(40)
    seen, pal = set(), []
    cols = state_colors([st for st, _ in top], 'side')
    for st, n in top:
        if st.short in seen:
            continue
        seen.add(st.short)
        pal.append([block_name(st.short), list(cols[st]), n])
        if len(pal) >= 8:
            break
    (x0, y0, z0), (x1, y1, z1) = B.bbox(include_air=False) or B.bbox()
    checks = []
    if ver.get('file'):
        checks.append([t('vid.decode'), t('vid.cells', n=f"{ver['file']['cellsDecoded']:,}")])
        checks.append([t('vid.states'), t('vid.kinds', n=ver['file']['paletteStatesValidated'])])
    if 'rules' in ver:
        checks.append([t('vid.rules'), t('vid.problems', n=ver['rules']['problems'])])
    if ver.get('spawnProofing'):
        checks.append([t('vid.lit'), t('vid.places', n=ver['spawnProofing']['spawnableSurfaces'])])
    if ver.get('walk'):
        tg = ver['walk']['targets']; checks.append([t('vid.walk'), f'{sum(tg.values())}/{len(tg)}'])
    for k, v in ig.items():
        if k.startswith('paste_') and 'non_air' in k:
            checks.append([t('vid.paste_check'), t('vid.diff', n=v['cellsMismatched'])])
    from .release import clearing_count
    paste_mode = 'All' if rep.get('mode', 'site') == 'site' and clearing_count(P) else 'With non-air'
    ui = {'tag': t('vid.tag', v=version()), 'origin': t('vid.origin', o='').strip(), 'palette': t('vid.palette'),
          'blocks': t('vid.blocks'), 'placeOrigin': t('vid.place_origin'), 'noRotate': t('vid.no_rotate'), 'noMirror': t('vid.no_mirror'),
          'paste': t('vid.paste', mode=paste_mode), 'schematic': t('vid.schematic'), 'anywhere': t('vid.anywhere'),
          'credit': t('vid.credit')}
    if is_create:
        ui.update(tag=f"Create {rep.get('createVersion', '6.0.8')} · Java {rep['targetVersion']}",
                  schematic='Create 蓝图' if lang() == 'zh' else 'Create blueprint',
                  paste='蓝图炮：不替换空气' if lang() == 'zh' else 'Schematicannon: do not replace air')
    return {
        'title': pc.get('title', P.name), 'subtitle': pc.get('subtitle', ''), 'brand': t('vid.brand', name=P.name), 'ui': ui, 'lang': lang(),
        'tagline': vc.get('tagline', ''), 'version': version(), 'mode': rep.get('mode', 'site'), 'origin': rep.get('origin', []),
        'file': rep.get('file', ''), 'blocks': len(blocks),
        'hero': rel(P, hero) if hero else '', 'endImage': rel(P, end) if end else '',
        'inputs': [rel(P, p) for p in inputs], 'brief': brief,
        'siteMap': next((rel(P, f) for f in (P.art / 'analysis-map.png', P.art / 'site-map.png', P.art / 'drawings' / 'plan-top.png') if f.exists()), ''),
        'siteFacts': facts_, 'locateImages': [rel(P, p) for p in locate], 'styleImage': rel(P, style[0]) if style else '',
        'palette': pal, 'checks': checks, 'ingame': [rel(P, p) for p in ingame if 'night' not in p.stem][:3],
        'build': {'y0': y0, 'y1': y1, 'center': [(x0 + x1 + 1) / 2, (y0 + y1) / 2, (z0 + z1 + 1) / 2],
                  'radius': max(x1 - x0 + 1, z1 - z0 + 1, y1 - y0 + 1) / 2},
    }


def init(P, overwrite_scenes=False):
    d = vdir(P)
    for f in ('stage.html', 'stage-lib.js', 'render.cjs'):
        shutil.copy2(SRC / f, d / f)
    shutil.copy2(KIT / 'web' / 'viewer.bundle.js', d / 'viewer.bundle.js')
    if overwrite_scenes or not (d / 'scenes.js').exists():
        shutil.copy2(SRC / 'scenes.js', d / 'scenes.js')
    if not (d / 'script.py').exists():
        tpl = SRC / ('script.zh.py' if lang() == 'zh' else 'script.en.py')
        (d / 'script.py').write_text(tpl.read_text(encoding='utf-8').replace('__TITLE__', P.name), encoding='utf-8')
    if not (P.art / 'preview' / 'scene.js').exists():
        from .preview import build_preview
        build_preview(P)
    data = video_data(P)
    (d / 'data.js').write_text('window.VIDEO_DATA=' + json.dumps(data, ensure_ascii=False) + ';', encoding='utf-8')
    log('VIDEO', d, '- edit script.py (narration) and scenes.js (pictures), then narrate -> check -> stills -> render')


# ------------------------------------------------------------------ narration
def _edge_tts():
    for p in (HOME / 'pylib',):
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        import edge_tts
        return edge_tts
    except ImportError:
        raise SystemExit(f'the narration needs edge-tts >= 7.3.1 (older versions get HTTP 403): '
                         f'{Path(sys.executable).name} -m pip install -U "edge-tts>=7.3.1"')


def narrate(P):
    edge_tts = _edge_tts()
    d = vdir(P)
    cfg = runpy.run_path(str(d / 'script.py'))
    script = cfg['SCRIPT']
    voice = cfg.get('VOICE', 'zh-CN-XiaoxiaoNeural' if lang() == 'zh' else 'en-US-AriaNeural')
    rate = cfg.get('RATE', '+6%' if lang() == 'zh' else '+0%')
    audio = d / 'audio'; audio.mkdir(exist_ok=True)
    ff = find_ffmpeg()

    async def synth(text, out):
        com = edge_tts.Communicate(text, voice, rate=rate, boundary='WordBoundary')
        words = []
        with open(out, 'wb') as fh:
            async for ch in com.stream():
                if ch['type'] == 'audio':
                    fh.write(ch['data'])
                elif ch['type'] in ('WordBoundary', 'SentenceBoundary'):
                    words.append({'t': ch['offset'] / 1e7, 'd': ch['duration'] / 1e7, 'w': ch['text']})
        return words

    cache = read_json(audio / 'cache.json', {})
    tl = {'voice': voice, 'rate': rate, 'scenes': [], 'lines': []}
    t, n = HEAD, 0
    for si, (scene, title, lines) in enumerate(script):
        if si:
            t += SCENE_GAP - LINE_GAP
        s0 = t
        for line in lines:
            frags = [(f, f) if isinstance(f, str) else tuple(f) for f in line]
            tts = ''.join(a for a, _ in frags)
            out = audio / f'line{n:02d}.mp3'
            key = f'{voice}|{rate}|{tts}'
            if cache.get(out.name, {}).get('key') != key or not out.exists():
                cache[out.name] = {'key': key, 'words': asyncio.run(synth(tts, out))}
                write_json(audio / 'cache.json', cache)
            words, dur = cache[out.name]['words'], duration(out, ff)
            starts, pos = [], 0
            for a, _ in frags:
                cum, ts = 0, None
                for w in words:
                    idx = tts.find(w['w'], cum)
                    if idx < 0:
                        continue
                    cum = idx + len(w['w'])
                    if idx >= pos:
                        ts = w['t']; break
                starts.append(ts if ts is not None else pos / max(1, len(tts)) * dur)
                pos += len(a)
            starts[0] = 0.0
            subs = [{'text': b, 'start': round(t + starts[k], 3), 'end': round(t + (starts[k + 1] if k + 1 < len(frags) else dur), 3)}
                    for k, (a, b) in enumerate(frags)]
            tl['lines'].append({'n': n, 'scene': scene, 'file': out.name, 'start': round(t, 3), 'dur': round(dur, 3), 'tts': tts, 'subs': subs})
            t += dur + LINE_GAP; n += 1
        tl['scenes'].append({'id': scene, 'title': title, 'start': round(s0, 3), 'end': round(t - LINE_GAP, 3)})
        log(f'{scene:10s} {s0:7.2f} -> {t - LINE_GAP:7.2f}')
    tl['scenes'][-1]['end'] = round(t - LINE_GAP + TAIL, 3)
    tl['total'] = round(t - LINE_GAP + TAIL, 3)
    write_json(d / 'timeline.json', tl)
    (d / 'timeline.js').write_text('window.TIMELINE=' + json.dumps(tl, ensure_ascii=False) + ';', encoding='utf-8')
    log('TIMELINE', tl['total'], 's', n, 'lines')


# ------------------------------------------------------------------ frames
def _node(P, mode, *args, timeout=None):
    """Frame worker process: Python Playwright (mcbuild.browser) when installed, else Node + video/render.cjs."""
    env = dict(os.environ, MCBUILD_FFMPEG=find_ffmpeg(), PYTHONIOENCODING='utf-8')
    if python_playwright():
        env['PYTHONPATH'] = str(KIT.parent) + os.pathsep + env.get('PYTHONPATH', '')
        out, rest = (args[0], args[1:]) if args else ('-', ())
        return subprocess.Popen([sys.executable, '-m', 'mcbuild.browser', mode, str(vdir(P)), str(out), *map(str, rest)], cwd=vdir(P), env=env)
    node, pw = find_node(), find_playwright()
    if not node or not pw:
        from .browser import install_hint
        raise SystemExit('rendering video frames needs Playwright: ' + install_hint())
    env['MCBUILD_PLAYWRIGHT'] = str(pw)
    return subprocess.Popen([node, 'render.cjs', mode, *map(str, args)], cwd=vdir(P), env=env)


def check(P):
    _node(P, 'check').wait()


def stills(P, times):
    _node(P, 'stills', 'stills', *times).wait()


def mix(P, seed=20261021):
    from scipy.signal import fftconvolve, lfilter
    d = vdir(P)
    TL = read_json(d / 'timeline.json')
    SR = 48000
    N = int((TL['total'] + 0.5) * SR)
    rng = np.random.default_rng(seed)
    ff = find_ffmpeg()

    def decode(p):
        raw = subprocess.run([ff, '-v', 'error', '-i', str(p), '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'], capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.float32).astype(np.float64)
    voice = np.zeros(N)
    for l in TL['lines']:
        a = decode(d / 'audio' / l['file']); i = int(l['start'] * SR)
        voice[i:i + len(a)] += a[:max(0, N - i)]
    voice *= 0.89 / max(1e-9, np.abs(voice).max())
    t = np.arange(N) / SR
    mid = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    CH = [[48, 55, 59, 62, 64], [45, 52, 55, 59, 60], [41, 48, 52, 57, 60], [43, 50, 52, 57, 59]]
    BAR = 8.0

    def env(n, at, rl):
        e = np.ones(n); a = min(int(at * SR), n); r = min(int(rl * SR), n)
        e[:a] *= np.linspace(0, 1, a) ** 2; e[n - r:] *= np.linspace(1, 0, r) ** 1.5
        return e
    pad = np.zeros((N, 2))
    for b in range(int(np.ceil(TL['total'] / BAR)) + 1):
        s0 = int(b * BAR * SR)
        if s0 >= N:
            break
        Lb = min(int((BAR + 3.0) * SR), N - s0); tt = np.arange(Lb) / SR; e = env(Lb, 2.6, 3.4)
        for m in CH[b % 4]:
            for c, det in ((0, -4), (1, 5)):
                f = mid(m) * 2 ** (det / 1200)
                pad[s0:s0 + Lb, c] += (np.sin(2 * np.pi * f * tt + rng.uniform(0, 6.28)) + .22 * np.sin(4 * np.pi * f * tt)) * e * (0.55 if m < 50 else 0.42)
    a = np.exp(-2 * np.pi * 1500 / SR); pad = lfilter([1 - a], [1, -a], pad, axis=0)
    plk = np.zeros((N, 2))
    for k in range(int(TL['total'])):
        if rng.random() > 0.42:
            continue
        m = rng.choice(CH[int(k / BAR) % 4][2:]) + 12 + (12 if rng.random() < .35 else 0)
        s0 = int(k * SR); Lp = int(1.6 * SR)
        if s0 + Lp > N:
            break
        tt = np.arange(Lp) / SR
        w = (np.sin(2 * np.pi * mid(m) * tt) + .3 * np.sin(4 * np.pi * mid(m) * tt) * np.exp(-tt * 9)) * np.exp(-tt * 3.2) * (1 - np.exp(-tt * 400))
        pan = rng.uniform(.25, .75); plk[s0:s0 + Lp, 0] += w * (1 - pan); plk[s0:s0 + Lp, 1] += w * pan
    rms = lambda x: np.sqrt(np.mean(x ** 2) + 1e-12)
    pad *= 10 ** (-27 / 20) / rms(pad); plk *= 10 ** (-33 / 20) / rms(plk)
    music = pad + plk
    ir_t = np.arange(int(2.4 * SR)) / SR
    ir = rng.normal(0, 1, (len(ir_t), 2)) * np.exp(-ir_t * 2.6)[:, None]; ir /= np.sqrt((ir ** 2).sum(0))
    music = music * .78 + np.stack([fftconvolve(music[:, c], ir[:, c])[:N] for c in range(2)], 1) * .5
    fade = np.minimum(1, t / 3.0) * np.minimum(1, np.maximum(0, (TL['total'] - t) / 4.0))
    ve = np.abs(voice); att, relc = np.exp(-1 / (0.03 * SR)), np.exp(-1 / (0.6 * SR)); e = np.zeros(N); acc = 0.0
    for i in range(0, N, 64):
        x = ve[i:i + 64].max(); acc = x + (acc - x) * (att ** 64 if x > acc else relc ** 64); e[i:i + 64] = acc
    music *= (fade * (1 - .5 * np.clip(e / .05, 0, 1)))[:, None]
    m = music + voice[:, None]; m *= .97 / max(1e-9, np.abs(m).max())
    raw = d / 'mix_raw.wav'
    with wave.open(str(raw), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((m * 32767).astype('<i2').tobytes())
    subprocess.run([ff, '-y', '-v', 'error', '-i', str(raw), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', str(SR), str(d / 'mix.wav')], check=True)
    raw.unlink()

    def ts(x):
        h, r = divmod(x, 3600); mm, s = divmod(r, 60)
        return f'{int(h):02d}:{int(mm):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}'
    srt = [f'{i}\n{ts(s["start"])} --> {ts(s["end"])}\n{s["text"]}\n' for i, s in enumerate([s for l in TL['lines'] for s in l['subs']], 1)]
    P.release_dir.mkdir(exist_ok=True)
    (P.release_dir / t('file.srt', name=P.name)).write_text('\n'.join(srt), encoding='utf-8')
    log('MIX', d / 'mix.wav', round(N / SR, 1), 's')


def render(P, workers=4):
    d = vdir(P)
    TL = read_json(d / 'timeline.json')
    if TL is None:
        raise SystemExit('run `mcb video narrate` first')
    if not (d / 'mix.wav').exists() or (d / 'mix.wav').stat().st_mtime < (d / 'timeline.json').stat().st_mtime:
        mix(P)
    frames = int(math.ceil(TL['total'] * 30))
    out = d / 'out'; out.mkdir(exist_ok=True)
    step = math.ceil(frames / workers)
    procs, segs = [], []
    for k in range(workers):
        f0, f1 = k * step, min(frames, (k + 1) * step)
        if f0 >= f1:
            break
        seg = out / f'seg{k}.mp4'; segs.append(seg)
        procs.append(_node(P, 'segment', seg, f0, f1))
    for p in procs:
        if p.wait() != 0:
            raise SystemExit('rendering a video segment failed')
    (out / 'list.txt').write_text(''.join(f"file '{s.name}'\n" for s in segs), encoding='utf-8')
    final = P.release_dir / t('file.video', name=P.name)
    ff = find_ffmpeg()
    subprocess.run([ff, '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(out / 'list.txt'), '-i', str(d / 'mix.wav'),
                    '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30',
                    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-shortest', '-movflags', '+faststart', str(final)], check=True)
    subprocess.run([ff, '-y', '-v', 'error', '-ss', '4.5', '-i', str(final), '-frames:v', '1', '-q:v', '2',
                    str(P.release_dir / t('file.cover', name=P.name))], check=True)
    log('VIDEO', final, round(final.stat().st_size / 1e6, 1), 'MB')
