"""Shared paths and environment discovery: game folders of every common launcher on Windows / macOS / Linux, Java,
vanilla client jars, Playwright, ffmpeg and fonts.

Everything the user told us (game folders, Java, language ...) lives in the profile (config.py) and wins over
discovery. Discovery only looks at well-known launcher folders - it never crawls whole drives unless asked
(`mcb find-data --scan`). User folders are only ever read; the kit writes inside MCBUILD_HOME and the project.
"""
from __future__ import annotations
import glob, gzip, json, os, re, shutil, subprocess, sys, zipfile
from functools import lru_cache
from pathlib import Path
from . import config

KIT = Path(__file__).resolve().parent                 # .../scripts/mcbuild
DATA = KIT / 'data'
HOME = config.HOME                                    # profile + shared caches (harness, assets, downloads)
DEFAULT_VERSION = '1.21.11'
IS_WIN = os.name == 'nt'
IS_MAC = sys.platform == 'darwin'
IS_LINUX = not IS_WIN and not IS_MAC
EXE = '.exe' if IS_WIN else ''


def log(*a):
    print(*a, flush=True)


def read_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding='utf-8'))


def write_json(p, obj, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent, default=_default), encoding='utf-8')
    return p


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, Path):
        return str(o)
    return str(o)


# ------------------------------------------------------------------ bundled game data
def bundled_versions():
    return sorted(p.name for p in DATA.iterdir() if p.is_dir() and (p / 'meta.json').exists())


def default_version():
    v = config.get('version')
    return v if v and (DATA / v).is_dir() else DEFAULT_VERSION


def data_dir(version=DEFAULT_VERSION) -> Path:
    d = DATA / version
    if not d.is_dir():
        raise SystemExit(f'No block data for Minecraft {version} (bundled: {", ".join(bundled_versions())}). Use a bundled '
                         f'version - schematics from it load in newer game versions - or add data for {version} '
                         f'(references/setup.md, "Other game versions").')
    return d


def data_path(version, name) -> Path:
    """Path of a bundled data file, accepting a gzipped copy (name.gz)."""
    p = data_dir(version) / name
    if not p.exists() and p.with_name(name + '.gz').exists():
        return p.with_name(name + '.gz')
    return p


def data_json(version, name, default=None):
    p = data_path(version, name)
    if not p.exists():
        return default
    raw = p.read_bytes()
    if p.name.endswith('.gz'):
        raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8'))


def meta(version=DEFAULT_VERSION):
    return read_json(data_dir(version) / 'meta.json', {})


# ------------------------------------------------------------------ launcher & game folders
def _is_game_dir(p: Path) -> bool:
    return p.is_dir() and any((p / d).exists() for d in ('saves', 'options.txt', 'mods', '.voxy', 'schematics', 'screenshots'))


def launcher_roots():
    """[(label, folder)] where launchers keep game folders or instances on this OS (only those that exist)."""
    h = Path.home()
    out = []

    def add(label, p):
        p = Path(p)
        if p.is_dir() and all(p != q for _, q in out):
            out.append((label, p))
    if IS_WIN:
        ad = Path(os.environ.get('APPDATA') or h / 'AppData' / 'Roaming')
        add('Minecraft Launcher', ad / '.minecraft')
        for label, sub in (('Prism Launcher', 'PrismLauncher'), ('PolyMC', 'PolyMC'), ('MultiMC', 'MultiMC'), ('ATLauncher', 'ATLauncher'),
                           ('GDLauncher', 'gdlauncher_next'), ('GDLauncher', 'gdlauncher_carbon/data'), ('Modrinth App', 'ModrinthApp'),
                           ('Modrinth App', 'com.modrinth.theseus'), ('SKLauncher', '.sklauncher')):
            add(label, ad / sub)
        add('CurseForge', h / 'curseforge' / 'minecraft')
        add('Minecraft', h / '.minecraft')
    elif IS_MAC:
        sup = h / 'Library' / 'Application Support'
        add('Minecraft Launcher', sup / 'minecraft')
        for label, sub in (('Prism Launcher', 'PrismLauncher'), ('PolyMC', 'PolyMC'), ('MultiMC', 'MultiMC'), ('ATLauncher', 'ATLauncher'),
                           ('GDLauncher', 'gdlauncher_next'), ('GDLauncher', 'gdlauncher_carbon/data'), ('Modrinth App', 'ModrinthApp'),
                           ('Modrinth App', 'com.modrinth.theseus')):
            add(label, sup / sub)
        add('CurseForge', h / 'Documents' / 'curseforge' / 'minecraft')
        add('Minecraft', h / '.minecraft')
    else:
        share = Path(os.environ.get('XDG_DATA_HOME') or h / '.local' / 'share')
        add('Minecraft Launcher', h / '.minecraft')
        add('Minecraft Launcher (Flatpak)', h / '.var/app/com.mojang.Minecraft/.minecraft')
        for label, sub in (('Prism Launcher', 'PrismLauncher'), ('PolyMC', 'PolyMC'), ('MultiMC', 'multimc'), ('ATLauncher', 'ATLauncher'),
                           ('Modrinth App', 'ModrinthApp'), ('Modrinth App', 'com.modrinth.theseus')):
            add(label, share / sub)
        add('Prism Launcher (Flatpak)', h / '.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher')
        add('GDLauncher', h / '.config' / 'gdlauncher_carbon' / 'data')
        add('GDLauncher', h / '.config' / 'gdlauncher_next')
    for p in _launcher_config_dirs():
        add('launcher setting', p)
    return out


def _launcher_config_dirs():
    """Game folders the player registered in launcher settings (HMCL game-directory list, PCL folder list)."""
    out = []
    hm = Path(os.environ.get('APPDATA') or Path.home()) / '.hmcl' / 'config' / 'user-game-directories.json' if IS_WIN else \
        Path.home() / '.hmcl' / 'config' / 'user-game-directories.json'
    try:
        for d in json.loads(hm.read_text(encoding='utf-8')).get('directories', []):
            if d.get('path'):
                out.append(Path(d['path']))
    except (OSError, ValueError, AttributeError):
        pass
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\PCL') as k:
                v, _ = winreg.QueryValueEx(k, 'LaunchFolders')
            for item in str(v).split('|'):            # "name>D:\path\.minecraft\|name2>..."
                if '>' in item:
                    out.append(Path(item.split('>', 1)[1]))
        except OSError:
            pass
    return [p for p in out if p.is_dir()]


def _expand(root: Path):
    """A game root plus the instances below it (HMCL/PCL version isolation, Prism/MultiMC/ATLauncher/GDLauncher
    instances, Modrinth profiles, CurseForge instances)."""
    out = [root] if _is_game_dir(root) else []
    pats = ['versions/*', 'instances/*', 'instances/*/.minecraft', 'instances/*/minecraft', 'instances/*/instance',
            'profiles/*', 'Instances/*']
    for pat in pats:
        for p in sorted(root.glob(pat)):
            if _is_game_dir(p) and p not in out:
                out.append(p)
    return out


@lru_cache(maxsize=None)
def instance_roots():
    """Folders that may hold game directories: the user's configured ones first, then launcher defaults."""
    roots = []
    for p in config.get('game_dirs', []):
        p = Path(p).expanduser()
        if p.is_dir() and p not in roots:
            roots.append(p)
    for _, p in launcher_roots():
        if p not in roots:
            roots.append(p)
    return tuple(roots)


@lru_cache(maxsize=None)
def game_dirs():
    """Every game directory found (configured ones first): folders with saves / mods / .voxy / schematics."""
    out = []
    for root in instance_roots():
        for g in _expand(root):
            if g not in out:
                out.append(g)
        # a configured instance folder (e.g. .minecraft/versions/MyPack) is a game dir itself
        if root not in out and _is_game_dir(root):
            out.append(root)
    return tuple(out)


def guess_version(g):
    """Minecraft version of a game folder from launcher metadata (Prism/MultiMC, Modrinth, CurseForge, ATLauncher,
    HMCL/PCL version folders); None when unknown."""
    import re
    g = Path(g)
    plain = re.compile(r'^\d+\.\d+(\.\d+)?$')
    for f in (g.parent / 'mmc-pack.json', g / 'mmc-pack.json'):          # Prism / MultiMC / PolyMC
        try:
            for c in json.loads(f.read_text(encoding='utf-8')).get('components', []):
                if c.get('uid') == 'net.minecraft':
                    return c.get('version')
        except (OSError, ValueError, AttributeError):
            pass
    for f in (g / 'profile.json', g / 'minecraftinstance.json', g / 'instance.json'):   # Modrinth / CurseForge / ATLauncher
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            v = d.get('game_version') or (d.get('metadata') or {}).get('game_version') or d.get('gameVersion') or \
                (d.get('baseModLoader') or {}).get('minecraftVersion') or d.get('minecraftVersion')
            if v:
                return str(v)
        except (OSError, ValueError, AttributeError):
            pass
    try:                                                                  # HMCL / PCL isolated version folder
        d = json.loads((g / f'{g.name}.json').read_text(encoding='utf-8'))
        for p in d.get('patches', []):
            if p.get('id') == 'game' and p.get('version'):
                return p['version']
        for k in ('clientVersion', 'inheritsFrom', 'id'):
            v = d.get(k)
            if v and plain.match(str(v)):
                return v
    except (OSError, ValueError, AttributeError):
        pass
    vs = sorted(p.name for p in (g / 'versions').glob('*') if plain.match(p.name)) if (g / 'versions').is_dir() else []
    return vs[-1] if len(vs) == 1 else None


def scan_for_game_dirs(roots=None, max_depth=4, limit=4000):
    """Bounded search for .minecraft-like folders (for portable launchers such as HMCL / PCL kept anywhere).
    roots default to the home folder (Desktop, Downloads, Documents, games folders) and, on Windows, drive roots."""
    if roots is None:
        h = Path.home()
        roots = [h / d for d in ('Desktop', 'Downloads', 'Documents', 'Games', 'games', 'Applications')] + [h]
        if IS_WIN:
            import string
            roots += [Path(f'{c}:/') for c in string.ascii_uppercase if c not in 'AB' and Path(f'{c}:/').exists()]
    skip = {'windows', 'program files', 'program files (x86)', 'programdata', '$recycle.bin', 'system volume information',
            'node_modules', '.git', 'appdata', 'library', 'proc', 'sys', 'dev', 'usr', 'bin', 'lib', 'snap', 'site-packages',
            '.cache', '.gradle', '.m2', '.npm', 'cache', 'temp', 'tmp', 'saves', 'mods', 'versions', 'assets', 'libraries'}
    found, seen = [], 0
    for r in roots:
        stack = [(Path(r), 0)]
        while stack and seen < limit * 25:
            p, d = stack.pop()
            try:
                entries = list(os.scandir(p))
            except OSError:
                continue
            for e in entries:
                seen += 1
                if not e.is_dir(follow_symlinks=False):
                    continue
                q = Path(e.path)
                if e.name == '.minecraft' or e.name == 'minecraft' and _is_game_dir(q):
                    if q not in found:
                        found.append(q)
                    continue
                if d + 1 < max_depth and e.name.lower() not in skip and not (e.name.startswith('.') and e.name != '.minecraft'):
                    stack.append((q, d + 1))
            if len(found) >= 50:
                break
    return found


def find_mod_jars(pattern_any, exclude=(), version=None):
    """Mod jars (by lower-case substring) from the profile's mod_jars, our download folder and every mods folder."""
    hits = []
    cands = [Path(p) for p in config.get('mod_jars', [])]
    for v in ([version] if version else []) + ['']:
        d = HOME / 'mods' / v if v else HOME / 'mods'
        cands += sorted(d.glob('*.jar'))
    for g in game_dirs():
        cands += [Path(p) for p in glob.glob(str(g / 'mods' / '*.jar'))]
    for p in cands:
        n = p.name.lower()
        if p.is_file() and any(s in n for s in pattern_any) and not any(e in n for e in exclude) and p not in hits:
            hits.append(p)
    return hits


# ------------------------------------------------------------------ Java
def _java_version(exe):
    exe = Path(exe)
    rel = exe.parent.parent / 'release'                 # every modern JDK/JRE ships this file: no process needed
    try:
        m = re.search(r'JAVA_VERSION="(\d+)(?:\.(\d+))?', rel.read_text(encoding='utf-8', errors='replace'))
        if m:
            major = int(m.group(1))
            return int(m.group(2) or 0) if major == 1 else major
    except OSError:
        pass
    try:
        r = subprocess.run([str(exe), '-version'], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return 0
    m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
    if not m:
        return 0
    major = int(m.group(1))
    return int(m.group(2) or 0) if major == 1 else major


def _java_candidates():
    exe = 'java' + EXE
    h = Path.home()
    cands = []

    def home(p):
        if p:
            p = Path(p)
            cands.append(p if p.name.lower().startswith('java') and p.is_file() else p / 'bin' / exe)
    for key in ('java', 'jdk'):
        home(config.get(key))
    home(os.environ.get('JAVA_HOME'))
    w = shutil.which('java')
    if w:
        cands.append(Path(w))
    pats = [str(h / '.jdks/*/bin'), str(h / '.gradle/jdks/*/bin'), str(h / '.gradle/jdks/*/Contents/Home/bin'),
            str(h / '.sdkman/candidates/java/*/bin')]
    if IS_WIN:
        ad = Path(os.environ.get('APPDATA') or h / 'AppData/Roaming')
        lad = Path(os.environ.get('LOCALAPPDATA') or h / 'AppData/Local')
        for pf in {os.environ.get('ProgramFiles', 'C:/Program Files'), os.environ.get('ProgramW6432', 'C:/Program Files'),
                   os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')}:
            for vendor in ('Java', 'Eclipse Adoptium', 'Eclipse Foundation', 'Microsoft', 'Zulu', 'BellSoft', 'Amazon Corretto',
                           'Semeru', 'OpenJDK', 'GraalVM', 'Oracle'):
                pats.append(str(Path(pf) / vendor / '*' / 'bin'))
        pats += [str(ad / '.minecraft/runtime/*/windows-x64/*/bin'), str(ad / '.minecraft/runtime/*/*/*/bin'),
                 str(lad / 'Packages/Microsoft.4297127D64EC6_8wekyb3d8bbwe/LocalCache/Local/runtime/*/windows-x64/*/bin'),
                 'C:/Program Files (x86)/Minecraft Launcher/runtime/*/windows-x64/*/bin', str(ad / 'PrismLauncher/java/*/bin'),
                 str(ad / 'ModrinthApp/meta/java_versions/*/bin'), str(ad / 'com.modrinth.theseus/meta/java_versions/*/bin'),
                 str(h / 'curseforge/minecraft/Install/runtime/*/windows-x64/*/bin'), str(ad / '.hmcl/java/*/bin'),
                 str(ad / '.hmcl/java/*/*/bin')]
        try:                                            # Java list that PCL keeps in the registry
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\PCL') as k:
                v, _ = winreg.QueryValueEx(k, 'LaunchArgumentJavaAll')
            for j in json.loads(v or '[]'):
                if j.get('Path'):
                    cands.append(Path(j['Path']) / exe)
        except (OSError, ValueError, TypeError):
            pass
    elif IS_MAC:
        sup = h / 'Library/Application Support'
        pats += ['/Library/Java/JavaVirtualMachines/*/Contents/Home/bin', str(h / 'Library/Java/JavaVirtualMachines/*/Contents/Home/bin'),
                 '/opt/homebrew/opt/openjdk*/bin', '/usr/local/opt/openjdk*/bin', '/opt/homebrew/opt/openjdk*/libexec/openjdk.jdk/Contents/Home/bin',
                 str(sup / 'minecraft/runtime/*/mac-os*/*/jre.bundle/Contents/Home/bin'), str(sup / 'PrismLauncher/java/*/bin'),
                 str(sup / 'PrismLauncher/java/*/Contents/Home/bin'), str(sup / 'ModrinthApp/meta/java_versions/*/bin'),
                 str(sup / 'ModrinthApp/meta/java_versions/*/Contents/Home/bin')]
    else:
        share = Path(os.environ.get('XDG_DATA_HOME') or h / '.local/share')
        pats += ['/usr/lib/jvm/*/bin', '/usr/lib64/jvm/*/bin', '/opt/java/*/bin', '/opt/jdk*/bin', '/opt/*jdk*/bin',
                 str(h / '.minecraft/runtime/*/linux/*/bin'), str(share / 'PrismLauncher/java/*/bin'),
                 str(share / 'ModrinthApp/meta/java_versions/*/bin')]
    # portable launchers often keep Java next to their game folder (…/HMCL/Java/jdk-21/bin, …/PCL/runtime/…)
    for g in config.get('game_dirs', []):
        g = Path(g)
        for up in list(g.parents)[:4]:
            for name in ('Java', 'java', 'runtime', 'jre', 'JDK', 'jdk'):
                pats += [str(up / name / '*' / 'bin'), str(up / name / 'bin')]
    for pat in pats:
        cands += [Path(p) / exe for p in glob.glob(pat)]
    out = []
    for c in cands:
        try:
            c = c.resolve()
        except OSError:
            continue
        if c.is_file() and c not in out:
            out.append(c)
    return out


@lru_cache(maxsize=None)
def java_list():
    """[(exe, major, is_jdk)] of every Java found, in priority order (profile, JAVA_HOME, PATH, known folders)."""
    out = []
    for c in _java_candidates():
        v = _java_version(c)
        if v:
            out.append((str(c), v, (c.parent / ('javac' + EXE)).exists()))
    return tuple(out)


@lru_cache(maxsize=None)
def find_java(min_major=17, prefer_major=None, need_jdk=False):
    """(exe, major) of a java >= min_major; prefers exactly prefer_major and the user's own choice (profile)."""
    best = None
    for rank, (exe, v, jdk) in enumerate(java_list()):
        if v < min_major or (need_jdk and not jdk):
            continue
        score = (prefer_major is None or v == prefer_major, jdk, -rank)
        if best is None or score > best[0]:
            best = (score, exe, v)
    return (best[1], best[2]) if best else (None, 0)


def java_home(min_major=21):
    """JDK home for Gradle/Loom (javac needed); exactly 21 preferred."""
    exe, _ = find_java(min_major, prefer_major=21, need_jdk=True)
    return str(Path(exe).parent.parent) if exe else None


# ------------------------------------------------------------------ game jars
def _jar_version(p):
    try:
        with zipfile.ZipFile(p) as z:
            v = json.loads(z.read('version.json'))
        return v.get('id') or v.get('name')
    except Exception:
        return None


def client_jar(version=DEFAULT_VERSION):
    """Vanilla client jar of `version` (block models + textures for previews and maps). Profile, our download
    folder, Loom caches, then every launcher layout. None if this machine has no copy (use `mcb fetch client`)."""
    cands = []
    cj = config.get('client_jars', {}) or {}
    if cj.get(version):
        cands.append(Path(cj[version]))
    if os.environ.get('MCBUILD_CLIENT_JAR'):
        cands.append(Path(os.environ['MCBUILD_CLIENT_JAR']))
    cands.append(HOME / 'versions' / version / 'client.jar')
    gh = Path(os.environ.get('GRADLE_USER_HOME') or Path.home() / '.gradle')
    cands.append(gh / 'caches' / 'fabric-loom' / version / 'minecraft-client.jar')
    for root in instance_roots():
        cands += [root / 'versions' / version / f'{version}.jar',
                  root / 'libraries' / 'com' / 'mojang' / 'minecraft' / version / f'minecraft-{version}-client.jar',
                  root / 'meta' / 'versions' / version / f'{version}.jar', root / 'Install' / 'versions' / version / f'{version}.jar']
    for root in instance_roots():                       # instance jars under other names (HMCL/PCL copy the client)
        cands += [Path(p) for p in glob.glob(str(root / 'versions' / '*' / '*.jar'))]
    seen = set()
    for c in cands:
        if c in seen or not c.is_file():
            continue
        seen.add(c)
        try:
            if c.stat().st_size < 10_000_000:
                continue
        except OSError:
            continue
        if _jar_version(c) == version:
            return c
    return None


# ------------------------------------------------------------------ browsers, node, ffmpeg
def python_playwright():
    """True when the Python Playwright package is importable (its browser may still need installing)."""
    import importlib.util
    return importlib.util.find_spec('playwright') is not None


def find_node():
    n = config.get('node')
    return n if n and Path(n).exists() else shutil.which('node')


@lru_cache(maxsize=None)
def find_playwright():
    """Folder of the Node.js Playwright package (global install), or None."""
    cands = []
    if os.environ.get('MCBUILD_PLAYWRIGHT'):
        cands.append(Path(os.environ['MCBUILD_PLAYWRIGHT']))
    cands.append(HOME / 'node_modules' / 'playwright')
    if IS_WIN and os.environ.get('APPDATA'):
        cands.append(Path(os.environ['APPDATA']) / 'npm/node_modules/playwright')
    cands += [Path('/usr/local/lib/node_modules/playwright'), Path('/opt/homebrew/lib/node_modules/playwright'),
              Path('/usr/lib/node_modules/playwright')]
    for c in cands:
        if (c / 'package.json').exists():
            return c
    if shutil.which('npm'):
        try:
            r = subprocess.run(['npm', 'root', '-g'], capture_output=True, text=True, timeout=30, shell=IS_WIN)
            c = Path(r.stdout.strip()) / 'playwright'
            if (c / 'package.json').exists():
                return c
        except Exception:
            pass
    return None


def find_ffmpeg(required=True):
    cands = [config.get('ffmpeg'), shutil.which('ffmpeg')]
    try:
        import imageio_ffmpeg                           # pip install imageio-ffmpeg ships a static ffmpeg
        cands.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    cands += ['C:/ffmpeg/bin/ffmpeg.exe', 'C:/Program Files/ffmpeg/bin/ffmpeg.exe', '/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg',
              '/usr/bin/ffmpeg']
    for c in cands:
        if c and Path(c).is_file():
            return str(c)
    if required:
        raise SystemExit('ffmpeg not found: install it (winget install ffmpeg / brew install ffmpeg / apt install ffmpeg), '
                         'or `pip install imageio-ffmpeg`, or `mcb config set ffmpeg <path>`.')
    return None


# ------------------------------------------------------------------ fonts (labels on maps and drawings)
@lru_cache(maxsize=None)
def cjk_font():
    """A font file that can draw Chinese, or None."""
    cands = ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/msyh.ttf', 'C:/Windows/Fonts/simhei.ttf', 'C:/Windows/Fonts/Deng.ttf',
             'C:/Windows/Fonts/simsun.ttc', '/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Light.ttc',
             '/System/Library/Fonts/Hiragino Sans GB.ttc', '/Library/Fonts/Arial Unicode.ttf',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
             '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf',
             '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', '/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc',
             '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf']
    for c in cands:
        if Path(c).exists():
            return c
    if shutil.which('fc-match'):
        try:
            r = subprocess.run(['fc-match', '-f', '%{file}', ':lang=zh'], capture_output=True, text=True, timeout=10)
            if r.stdout.strip() and Path(r.stdout.strip()).exists() and 'dejavu' not in r.stdout.lower():
                return r.stdout.strip()
        except Exception:
            pass
    return None


@lru_cache(maxsize=None)
def latin_font():
    for c in ['C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/arial.ttf', '/System/Library/Fonts/Helvetica.ttc',
              '/System/Library/Fonts/SFNS.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/dejavu/DejaVuSans.ttf']:
        if Path(c).exists():
            return c
    return None


# ------------------------------------------------------------------ processes
def run(cmd, cwd=None, env=None, log_file=None, check=True, timeout=None):
    """Run a command, streaming output to a log file when given; returns CompletedProcess."""
    e = dict(os.environ, **(env or {}))
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w', encoding='utf-8', errors='replace') as fh:
            r = subprocess.run(cmd, cwd=cwd, env=e, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)
    else:
        r = subprocess.run(cmd, cwd=cwd, env=e, timeout=timeout)
    if check and r.returncode != 0:
        raise SystemExit(f'command failed ({r.returncode}): {" ".join(map(str, cmd))}' + (f'\nlog: {log_file}' if log_file else ''))
    return r
