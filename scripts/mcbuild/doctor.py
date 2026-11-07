"""`mcb doctor`: what this machine can do, what the profile already knows, and the exact fix for anything missing.
Fast and read-only; run it first in every new environment and paste its summary into your plan."""
from __future__ import annotations
import importlib, json, platform, sys
from pathlib import Path
from . import config
from .util import (HOME, IS_WIN, IS_MAC, KIT, bundled_versions, client_jar, cjk_font, find_ffmpeg, find_java, find_mod_jars,
                   find_node, find_playwright, game_dirs, java_home, launcher_roots, log, python_playwright)


def _ver(mod):
    try:
        m = importlib.import_module(mod)
        return getattr(m, '__version__', None) or getattr(m, 'VERSION', None) or 'installed'
    except Exception:
        return None


def _pip(pkgs):
    return f'{Path(sys.executable).name} -m pip install {pkgs}'


def _edge_tts_version():
    """edge-tts version the video tool would use: <MCBUILD_HOME>/pylib first (pip --target), then site-packages."""
    for d in sorted((HOME / 'pylib').glob('edge_tts-*.dist-info')):
        return d.name[len('edge_tts-'):-len('.dist-info')]
    try:
        from importlib.metadata import version
        return version('edge-tts')
    except Exception:
        return None


def _jdk_hint():
    if IS_WIN:
        return 'winget install EclipseAdoptium.Temurin.21.JDK'
    if IS_MAC:
        return 'brew install --cask temurin@21'
    return 'sudo apt install openjdk-21-jdk   (Fedora: sudo dnf install java-21-openjdk-devel)'


def _ffmpeg_hint():
    if IS_WIN:
        return f'winget install Gyan.FFmpeg   (or {_pip("imageio-ffmpeg")})'
    if IS_MAC:
        return 'brew install ffmpeg'
    return f'sudo apt install ffmpeg   (or {_pip("imageio-ffmpeg")})'


def _py_browser():
    """Path of the Chromium that Python Playwright would launch, if installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        return exe if exe and Path(exe).exists() else None
    except Exception:
        return None


def _has_display():
    if IS_WIN or IS_MAC:
        return True
    import os
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def collect(version, brief=False):
    from .util import guess_version
    R = {'python': platform.python_version(), 'platform': f'{platform.system()} {platform.release()} ({platform.machine()})',
         'kit': str(KIT.parent.parent), 'home': str(HOME), 'profile': config.load(), 'profileFile': str(config.FILE),
         'bundledVersions': bundled_versions(), 'version': version, 'checks': {}, 'fixes': []}
    C = R['checks']
    py_ok = sys.version_info >= (3, 10)
    np_v, pil_v = _ver('numpy'), _ver('PIL')
    toml_ok = sys.version_info >= (3, 11) or _ver('tomli')
    C['core'] = {'ok': bool(py_ok and np_v and pil_v and toml_ok), 'numpy': np_v, 'Pillow': pil_v,
                 'what': 'design, export, verify, materials, drawings, maps'}
    if not C['core']['ok']:
        R['fixes'].append(('core', 'Python 3.10+ and: ' + _pip('-r "' + str(KIT.parent / 'requirements.txt') + '"')))
    if version not in R['bundledVersions']:
        R['fixes'].append(('version', f'no bundled block data for {version} - use {", ".join(R["bundledVersions"])} '
                                      '(schematics load in newer game versions) or see references/setup.md'))
    jar = client_jar(version) if version in R['bundledVersions'] else None
    C['textures'] = {'ok': bool(jar), 'clientJar': str(jar) if jar else None,
                     'what': 'textured previews & accurate map colours' if jar else 'previews use flat map colours (still usable)'}
    if not jar:
        R['fixes'].append(('textures', f'`mcb fetch client --version {version}` (≈30 MB from Mojang; ask first), or play {version} '
                                       'once in a launcher, or `mcb config set client_jars <path to the jar>`'))
    gds = list(game_dirs())
    C['gameDirs'] = {'ok': bool(gds), 'count': len(gds),
                     'dirs': [{'path': str(g), 'version': guess_version(g)} for g in gds[:12]],
                     'launchers': sorted({lbl for lbl, _ in launcher_roots()})}
    if not gds:
        R['fixes'].append(('gameDirs', 'no game folder known: ask the player (Options > Resource Packs > Open Pack Folder, one '
                                       'folder up), then `mcb config add game_dirs <folder>`; not needed for portable builds'))
    jv, jmaj = find_java(17)
    zstd = _ver('zstandard')
    C['voxy'] = {'ok': bool(jv and zstd), 'java': jv, 'javaMajor': jmaj, 'zstandard': zstd, 'what': 'read Voxy caches of servers'}
    if not zstd:
        R['fixes'].append(('voxy', _pip('zstandard') + '  (only for Voxy caches)'))
    if not jv:
        R['fixes'].append(('voxy', f'Java 17+ for Voxy caches: {_jdk_hint()} - or `mcb config set java <java executable>`'))
    # screenshots
    ppw = python_playwright()
    browser = _py_browser() if (ppw and not brief) else None
    node, npw = (find_node(), find_playwright()) if not (ppw and (browser or brief)) else (None, None)
    shots_ok = bool(ppw and (browser or brief)) or bool(node and npw)
    C['screenshots'] = {'ok': shots_ok, 'pythonPlaywright': bool(ppw), 'browser': browser, 'node': node,
                        'nodePlaywright': str(npw) if npw else None, 'what': 'headless shots of the preview (you can look at the design)'}
    if not shots_ok:
        R['fixes'].append(('screenshots', _pip('playwright') + f' && {Path(sys.executable).name} -m playwright install chromium'
                           if not ppw else f'{Path(sys.executable).name} -m playwright install chromium'))
    # in-game test
    jdk = java_home(21)
    from .harness import litematica_jars
    mods = [p.name for p in litematica_jars(version)]           # the jars the harness would use for this version
    lit = any('litematica' in m.lower() for m in mods)
    mal = any('malilib' in m.lower() for m in mods)
    disp = _has_display()
    C['ingame'] = {'ok': bool(jdk and lit and mal and disp), 'jdk': jdk, 'modJars': mods[:6], 'display': disp,
                   'what': 'real-client Litematica paste test + game screenshots (opens a game window 2-5 min)'}
    if not jdk:
        R['fixes'].append(('ingame', f'JDK 21 for the in-game test: {_jdk_hint()}'))
    if not (lit and mal):
        R['fixes'].append(('ingame', f'Litematica + MaLiLib jars: `mcb fetch litematica --version {version}` (Modrinth; ask first) '
                                     'or `mcb config add mod_jars <jar>`'))
    # video
    ff = find_ffmpeg(required=False)
    tts = _edge_tts_version()
    scipy = _ver('scipy')
    tts_ok = bool(tts) and tuple(int(x) for x in tts.split('.')[:3] if x.isdigit()) >= (7, 3, 1)
    C['video'] = {'ok': bool(ff and tts_ok and scipy and shots_ok), 'ffmpeg': ff, 'edgeTts': tts, 'scipy': scipy, 'what': 'making-of video (optional)'}
    if not C['video']['ok']:
        need = [] if ff else [_ffmpeg_hint()]
        need += [] if tts_ok else [_pip('-U "edge-tts>=7.3.1"') + ('' if not tts else f'  (found {tts}; older versions get HTTP 403)')]
        need += [] if scipy else [_pip('scipy')]
        if need:
            R['fixes'].append(('video', '; '.join(need)))
    font = cjk_font()
    C['cjkFont'] = {'ok': bool(font), 'font': font, 'what': 'Chinese text inside images (else labels fall back to English)'}
    return R


def doctor(version=None, as_json=False, brief=False):
    from .util import default_version
    version = version or default_version()
    R = collect(version, brief)
    if as_json:
        print(json.dumps(R, ensure_ascii=False, indent=1, default=str))
        return R['checks']['core']['ok']
    C = R['checks']
    mark = lambda ok: '[ok]' if ok else '[--]'
    log(f"mcbuild doctor - Python {R['python']} on {R['platform']} - game data {', '.join(R['bundledVersions'])} (project version {version})")
    prof = R['profile']
    log(f"profile {R['profileFile']}" + ('' if prof else '  (empty: nothing saved yet - see references/intake.md)'))
    for k, v in prof.items():
        log(f'   {k}: {json.dumps(v, ensure_ascii=False)}')
    rows = [('core', 'design / export / verify'), ('textures', 'textured previews'), ('gameDirs', 'game folders'),
            ('voxy', 'Voxy caches'), ('screenshots', 'preview screenshots'), ('ingame', 'in-game paste test'),
            ('video', 'making-of video'), ('cjkFont', 'Chinese labels in images')]
    for key, label in rows:
        c = C[key]
        detail = ''
        if key == 'core':
            detail = f"numpy {c['numpy']}, Pillow {c['Pillow']}"
        elif key == 'textures':
            detail = c['clientJar'] or c['what']
        elif key == 'gameDirs':
            detail = (f"{c['count']} found" + (': ' + '; '.join(f"{d['path']} [{d['version'] or '?'}]" for d in c['dirs'][:3]) if c['dirs'] else '')
                      + (f" (launchers: {', '.join(c['launchers'])})" if c['launchers'] else ''))
        elif key == 'voxy':
            detail = f"java {c['javaMajor'] or '-'} {c['java'] or ''}, zstandard {c['zstandard'] or '-'}"
        elif key == 'screenshots':
            detail = ('Python Playwright' + (f" ({c['browser']})" if c['browser'] else '') if c['pythonPlaywright'] and (c['browser'] or brief)
                      else f"Node Playwright {c['nodePlaywright']}" if c['nodePlaywright'] else 'no Playwright')
        elif key == 'ingame':
            detail = f"JDK {c['jdk'] or '-'}, mods {', '.join(c['modJars']) or '-'}" + ('' if c['display'] else ', no display')
        elif key == 'video':
            detail = f"ffmpeg {'yes' if c['ffmpeg'] else '-'}, edge-tts {c['edgeTts'] or '-'}, scipy {c['scipy'] or '-'}"
        elif key == 'cjkFont':
            detail = c['font'] or '-'
        if brief and key in ('cjkFont',):
            continue
        log(f'{mark(c["ok"])} {label:<26} {detail}')
    can = [label for key, label in rows if C[key]['ok'] and key != 'cjkFont']
    cannot = [label for key, label in rows if not C[key]['ok'] and key not in ('cjkFont', 'gameDirs')]
    log('READY: ' + ', '.join(can) + (f'   |   NOT YET: {", ".join(cannot)}' if cannot else ''))
    if R['fixes']:
        log('fixes (ask the user before installing or downloading anything):')
        for k, f in R['fixes']:
            log(f'   {k}: {f}')
    return C['core']['ok']
