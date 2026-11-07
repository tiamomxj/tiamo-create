"""Game-version compatibility: design with the bundled block data, deliver for the player's version.

`[export] target_version = "1.21.1"` (any Java version from 1.20.1 up to the bundled one):
  * the schematic gets that version's DataVersion, so Litematica on that version reads it without upgrade warnings;
  * blocks renamed since then are written under their old names (iron_chain -> chain, short_grass -> grass);
  * `mcb verify` fails on blocks the target version does not have (they would paste as air) and names the version
    that introduced them.
Newer targets (26.x …) need nothing: Litematica converts older schematics on load. Readers always map old names to
new ones, so older saves and schematics read correctly as sites or style references.
"""
from __future__ import annotations
import re
from functools import lru_cache

# DataVersion per release (checked against the client jars of 1.20.1, 1.20.4, 1.21, 1.21.1, 1.21.5, 1.21.11).
DATA_VERSIONS = {'1.20': 3463, '1.20.1': 3465, '1.20.2': 3578, '1.20.3': 3698, '1.20.4': 3700, '1.20.5': 3837,
                 '1.20.6': 3839, '1.21': 3953, '1.21.1': 3955, '1.21.2': 4080, '1.21.3': 4082, '1.21.4': 4189,
                 '1.21.5': 4325, '1.21.6': 4435, '1.21.7': 4438, '1.21.8': 4440, '1.21.9': 4554, '1.21.10': 4556,
                 '1.21.11': 4671}
OLD_NAMES = {'minecraft:grass': 'minecraft:short_grass', 'minecraft:chain': 'minecraft:iron_chain'}   # old -> current


def vkey(v):
    """'1.21.11' -> (1, 21, 11); '26.1' -> (26, 1); snapshots and odd strings sort by their numbers."""
    return tuple(int(x) for x in re.findall(r'\d+', str(v))[:3]) or (0,)


@lru_cache(maxsize=None)
def history(base):
    from .util import data_json
    return data_json(base, 'history.json') or {'since': {}, 'renamed': {}, 'oldest': base}


@lru_cache(maxsize=None)
def _first(base):
    out = {}
    for ver, names in history(base)['since'].items():
        for n in names:
            out[n] = ver
    for new, (old, ver) in history(base)['renamed'].items():
        out.setdefault(new, None)
    return out


def first_version(short, base):
    """First game version that has this block (None: already in the oldest tracked version)."""
    return _first(base).get(short.split(':')[-1])


def is_older(target, base):
    return bool(target) and vkey(target) < vkey(base)


def write_renames(target, base):
    """{current name: name in the target version} for blocks renamed after the target."""
    if not is_older(target, base):
        return {}
    return {'minecraft:' + new: 'minecraft:' + old for new, (old, ver) in history(base)['renamed'].items()
            if vkey(target) < vkey(ver)}


def data_version(target, base, default):
    if not is_older(target, base):
        return default
    if target not in DATA_VERSIONS:
        raise SystemExit(f'unknown target_version {target!r}; known: {", ".join(DATA_VERSIONS)}')
    return DATA_VERSIONS[target]


def missing_blocks(states, target, base):
    """[(block id, version that added it)] for design blocks the target version does not have."""
    if not is_older(target, base):
        return []
    oldest = history(base).get('oldest', '1.20.1')
    if vkey(target) < vkey(oldest):
        raise SystemExit(f'target_version {target} is older than {oldest}, the oldest version this kit can check')
    out = {}
    for st in states:
        v = first_version(st.short, base)
        if v and vkey(v) > vkey(target):
            out[st.short] = v
    return sorted(out.items())


def current_name(name):
    """Map an old block id (read from an older save or schematic) to the bundled version's id."""
    return OLD_NAMES.get(name, name)
