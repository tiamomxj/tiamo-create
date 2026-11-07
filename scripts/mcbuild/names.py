"""In-game names of blocks, items and biomes, read from the player's own game files (nothing of Mojang's text is
shipped with the kit):

  * English (en_us) from the vanilla client jar of the version;
  * Chinese (zh_cn) and every other language from the launcher's asset store (`assets/indexes` + `assets/objects`,
    which every launcher keeps next to its game folders);
  * cached per version in <MCBUILD_HOME>/names/<version>.json.gz.

Without game files the ids are turned into readable names ("oak_planks" -> "Oak Planks") and other languages fall
back to them, so everything keeps working - only the names are plainer.
"""
from __future__ import annotations
import gzip, json, time
from functools import lru_cache
from pathlib import Path

KEEP = ('block.minecraft.', 'item.minecraft.', 'biome.minecraft.')


def _asset_dirs():
    from .util import instance_roots
    from . import config
    out = []
    roots = list(instance_roots())
    for g in config.get('game_dirs', []):                  # an instance folder inside .minecraft/versions/<name>
        g = Path(g)
        roots += [g, g.parent.parent] if g.parent.name == 'versions' else [g]
    for root in roots:
        for cand in (root / 'assets', root / 'meta' / 'assets', root / 'Install' / 'assets', root.parent / 'assets'):
            if (cand / 'indexes').is_dir() and cand not in out:
                out.append(cand)
    return out


def _lang_from_assets(code):
    for ad in _asset_dirs():
        for idx in sorted((ad / 'indexes').glob('*.json'), key=lambda p: -p.stat().st_mtime):
            try:
                h = json.loads(idx.read_text(encoding='utf-8'))['objects'][f'minecraft/lang/{code}.json']['hash']
            except (OSError, ValueError, KeyError):
                continue
            p = ad / 'objects' / h[:2] / h
            if p.exists():
                try:
                    return json.loads(p.read_text(encoding='utf-8')), str(idx)
                except (OSError, ValueError):
                    continue
    return None, None


def _lang_from_jar(version, code='en_us'):
    import zipfile
    from .util import client_jar
    jar = client_jar(version)
    if jar is None:
        return None, None
    try:
        with zipfile.ZipFile(jar) as z:
            return json.loads(z.read(f'assets/minecraft/lang/{code}.json')), str(jar)
    except (OSError, KeyError, ValueError):
        return None, None


def build(version, codes=('en_us', 'zh_cn')):
    """Collect the name tables from this machine's game files (also used to refresh the cache)."""
    out, sources = {}, {}
    for code in codes:
        table, src = _lang_from_jar(version, code) if code == 'en_us' else (None, None)
        if table is None:
            table, src = _lang_from_assets(code)
        out[code] = {k: v for k, v in (table or {}).items() if k.startswith(KEEP)}
        sources[code] = src
    return {'version': version, 'built': int(time.time()), 'sources': sources, **out}


@lru_cache(maxsize=None)
def tables(version):
    """{'en_us': {...}, 'zh_cn': {...}} for a version, from the cache or freshly built; empty tables when unavailable."""
    from .util import HOME, data_json
    bundled = data_json(version, 'names.json')           # maintainers may bundle names for private use
    if bundled:
        return bundled
    cache = HOME / 'names' / f'{version}.json.gz'
    if cache.exists():
        try:
            d = json.loads(gzip.decompress(cache.read_bytes()).decode('utf-8'))
            fresh = time.time() - d.get('built', 0) < 7 * 86400
            if all(d.get(c) for c in ('en_us', 'zh_cn')) or fresh:
                return d
        except (OSError, ValueError):
            pass
    d = build(version)
    if any(d.get(c) for c in ('en_us', 'zh_cn')):
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(gzip.compress(json.dumps(d, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 6))
    return d


def readable(short):
    """'oak_planks' -> 'Oak Planks' (used when no game files are available)."""
    return ' '.join(w.upper() if w in ('tnt',) else w.capitalize() for w in short.split('_'))
