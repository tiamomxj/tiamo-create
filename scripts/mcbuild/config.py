"""The user's profile: what we learned about this machine and this player, saved once and reused by every project.

Stored as JSON in <MCBUILD_HOME>/config.json (default ~/.mcbuild/config.json). Every key is optional; anything not
set is discovered automatically (see util.py) or asked for at intake. Environment variables override the file:

  MCBUILD_HOME        folder for the profile and shared caches (default ~/.mcbuild)
  MCBUILD_GAME_DIRS   extra game directories, separated by os.pathsep (';' on Windows, ':' elsewhere)
  MCBUILD_JAVA        java executable (17+, reads Voxy caches)      MCBUILD_JAVA_HOME  JDK 21 home (in-game test)
  MCBUILD_CLIENT_JAR  vanilla client jar (textures for previews)    MCBUILD_FFMPEG / MCBUILD_NODE
  MCBUILD_LANG        language of the deliverables (zh, en)
"""
from __future__ import annotations
import json, os
from pathlib import Path

HOME = Path(os.environ.get('MCBUILD_HOME') or (Path.home() / '.mcbuild')).expanduser()
FILE = HOME / 'config.json'

# key -> (type, description).  Shown by `mcb config --keys`.
KEYS = {
    'game_dirs': (list, 'game directories (a .minecraft folder or a launcher instance folder), most important first'),
    'projects_dir': (str, 'where new build projects are created'),
    'lang': (str, 'language of deliverables and image labels: zh or en'),
    'author': (str, 'author name written into schematics'),
    'version': (str, 'default Minecraft Java version for new projects'),
    'launcher': (str, 'launcher the player uses (HMCL, PCL, Prism, official, CurseForge, Modrinth ...) - informational'),
    'java': (str, 'java executable, 17+ (reads Voxy caches)'),
    'jdk': (str, 'JDK 21 home folder (real-client paste test)'),
    'client_jars': (dict, 'vanilla client jar per game version, e.g. {"1.21.11": "C:/.../1.21.11.jar"}'),
    'mod_jars': (list, 'Litematica + MaLiLib jars for the real-client test, if they are not in a known mods folder'),
    'ffmpeg': (str, 'ffmpeg executable (video only)'),
    'node': (str, 'node executable (only if Python Playwright is not installed)'),
    'notes': (list, 'facts worth remembering about the player (server names, where their base is ...)'),
}
_ENV = {'game_dirs': 'MCBUILD_GAME_DIRS', 'java': 'MCBUILD_JAVA', 'jdk': 'MCBUILD_JAVA_HOME', 'ffmpeg': 'MCBUILD_FFMPEG',
        'node': 'MCBUILD_NODE', 'lang': 'MCBUILD_LANG'}
_cache = {}


def load() -> dict:
    if 'cfg' not in _cache:
        try:
            _cache['cfg'] = json.loads(FILE.read_text(encoding='utf-8')) if FILE.exists() else {}
        except (OSError, ValueError) as e:
            print(f'warning: cannot read {FILE}: {e}', flush=True)
            _cache['cfg'] = {}
    return _cache['cfg']


def save(cfg: dict):
    HOME.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf-8')
    _cache['cfg'] = cfg


def get(key, default=None):
    """Value from the environment (if set), else the profile, else default."""
    env = _ENV.get(key)
    if env and os.environ.get(env):
        v = os.environ[env]
        return [p for p in v.split(os.pathsep) if p] if KEYS[key][0] is list else v
    v = load().get(key)
    return default if v in (None, '', [], {}) else v


def _coerce(key, value):
    typ = KEYS[key][0]
    if typ is str:
        return str(value)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if typ is list and not isinstance(value, list):
        value = [value]
    if typ is dict and not isinstance(value, dict):
        raise SystemExit(f'{key} must be a JSON object, e.g. {{"1.21.11": "path/to/client.jar"}}')
    return value


def set_value(key, value):
    if key not in KEYS:
        raise SystemExit(f'unknown key {key!r}; known: {", ".join(KEYS)}')
    cfg = dict(load())
    cfg[key] = _coerce(key, value)
    save(cfg)
    return cfg[key]


def add_value(key, value):
    if key not in KEYS or KEYS[key][0] not in (list, dict):
        raise SystemExit(f'`add` works on list keys: {", ".join(k for k, (t, _) in KEYS.items() if t is list)}')
    cfg = dict(load())
    cur = list(cfg.get(key) or [])
    if value not in cur:
        cur.append(value)
    cfg[key] = cur
    save(cfg)
    return cur


def remove_value(key, value):
    cfg = dict(load())
    cur = [v for v in (cfg.get(key) or []) if v != value]
    cfg[key] = cur
    save(cfg)
    return cur


def unset(key):
    cfg = dict(load())
    cfg.pop(key, None)
    save(cfg)
