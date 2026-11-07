"""Shared Fabric/Loom harness (one per game version, under <MCBUILD_HOME>/harness/<version>).

* dump_facts(): per-block-state facts from the game's own code -> data/<version>/facts.json.gz
* run_ingame(): real-client Litematica paste test + screenshots, configured by a JSON file

The harness is copied from scripts/mcbuild/harness the first time and re-synced when the template changes.
Loom's first setup downloads/decompiles Minecraft (several minutes); later runs reuse ~/.gradle caches.
"""
from __future__ import annotations
import hashlib, os, re, shutil
from pathlib import Path
from .util import KIT, HOME, DEFAULT_VERSION, meta, data_dir, java_home, find_mod_jars, run, log, write_json

TEMPLATE = KIT / 'harness'


def harness_dir(version=DEFAULT_VERSION) -> Path:
    return HOME / 'harness' / version


def _sync(src: Path, dst: Path):
    for p in src.rglob('*'):
        q = dst / p.relative_to(src)
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
        elif not q.exists() or hashlib.sha1(q.read_bytes()).digest() != hashlib.sha1(p.read_bytes()).digest():
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)


def litematica_jars(version=None):
    """Litematica + MaLiLib (newest of each) from the profile, `mcb fetch litematica` or the player's mods folders."""
    def pick(paths):
        # jars are named <mod>-fabric-<minecraft version>-<mod version>.jar: only the game version under test fits
        if version:
            exact = [p for p in paths if re.search(rf'-fabric-{re.escape(version)}-', p.name)]
            paths = exact or [p for p in paths if not re.search(r'-fabric-\d+\.\d+(\.\d+)?-', p.name)]
        return max(paths, key=lambda p: (_mod_version(p.name), p.stat().st_mtime)) if paths else None
    lit = pick([p for p in find_mod_jars(['litematica-fabric'], version=version) if 'printer' not in p.name.lower()])
    mal = pick(find_mod_jars(['malilib-fabric'], version=version))
    return [p for p in (lit, mal) if p]


def _mod_version(name):
    """(0, 26, 14) from 'litematica-fabric-1.21.11-0.26.14.jar' - newest mod version wins, not the newest file date."""
    m = re.search(r'-fabric-\d+\.\d+(?:\.\d+)?-(\d+(?:\.\d+)*)', name)
    return tuple(int(x) for x in m.group(1).split('.')) if m else ()


def _clean_name(name):
    m = re.search(r'((?:litematica|malilib)-fabric-[A-Za-z0-9._+-]+\.jar)$', name)
    return m.group(1) if m else re.sub(r'[^A-Za-z0-9._+-]', '', name) or 'mod.jar'


def ensure(version=DEFAULT_VERSION, with_litematica=True) -> Path:
    h = harness_dir(version)
    _sync(TEMPLATE, h)
    m = meta(version).get('harness')
    if not m:
        raise SystemExit(f'data/{version}/meta.json has no harness versions (loom / yarn / loader / fabric_api)')
    jh = java_home(21)
    if not jh:
        from .doctor import _jdk_hint
        raise SystemExit(f'a JDK 21 is needed (Loom/Gradle): {_jdk_hint()} - or `mcb config set jdk <JDK folder>`')
    props = [f'org.gradle.jvmargs=-Xmx1G', 'org.gradle.parallel=false', f'org.gradle.java.home={Path(jh).as_posix()}',
             f'loom_version={m["loom"]}', f'minecraft_version={version}', f'yarn_mappings={m["yarn"]}',
             f'loader_version={m["loader"]}', f'fabric_version={m["fabric_api"]}']
    (h / 'gradle.properties').write_text('\n'.join(props) + '\n', encoding='utf-8')
    libs = h / 'libs'
    libs.mkdir(exist_ok=True)
    if with_litematica:
        # Copy under plain ASCII names: launcher folders often prefix mods with 【…】, and Loom silently drops
        # such files from the dev runtime (they compile, then NoClassDefFoundError at run time).
        jars = {_clean_name(j.name): j for j in litematica_jars(version)}
        for old in libs.glob('*.jar'):
            if old.name not in jars:
                old.unlink()
        for name, j in jars.items():
            if not (libs / name).exists():
                shutil.copy2(j, libs / name)
    return h


def gradle(version, *args, log_file=None, timeout=None):
    h = harness_dir(version)
    exe = str(h / ('gradlew.bat' if os.name == 'nt' else 'gradlew'))
    if os.name != 'nt':
        os.chmod(exe, 0o755)
    return run([exe, '--no-daemon', '--console=plain', *args], cwd=h, log_file=log_file, timeout=timeout)


def dump_tags(version=DEFAULT_VERSION):
    """Vanilla block tags (data/minecraft/tags/block in the client jar) with '#' references resolved -> tags.json."""
    import json, zipfile
    from .util import client_jar
    jar = client_jar(version)
    if jar is None:
        raise SystemExit(f'no {version} client jar on this machine: `mcb fetch client --version {version}`')
    raw = {}
    with zipfile.ZipFile(jar) as z:
        for n in z.namelist():
            if n.startswith('data/minecraft/tags/block/') and n.endswith('.json'):
                raw['minecraft:' + n[len('data/minecraft/tags/block/'):-5]] = json.loads(z.read(n))['values']

    def resolve(t, seen=()):
        out = set()
        for v in raw.get(t, []):
            v = v['id'] if isinstance(v, dict) else v
            if v.startswith('#'):
                if v[1:] not in seen:
                    out |= resolve(v[1:], seen + (t,))
            else:
                out.add(v)
        return out
    tags = {t: sorted(resolve(t)) for t in sorted(raw)}
    out = data_dir(version) / 'tags.json'
    out.write_text(json.dumps(tags, separators=(',', ':')), encoding='utf-8')
    log('tags', len(tags), '→', out)
    return out


def dump_facts(version=DEFAULT_VERSION):
    dump_tags(version)
    h = ensure(version, with_litematica=False)
    out = data_dir(version) / 'facts.json.gz'
    log('dumpFacts ->', out, '(the first Loom setup takes several minutes)')
    gradle(version, 'runDumpFacts', f'-PfactsOut={out.as_posix()}', log_file=h / 'dumpFacts.log')
    log('facts', out, round(out.stat().st_size / 1e6, 2), 'MB')
    return out


def run_ingame(cfg: dict, version=DEFAULT_VERSION, log_file=None):
    """cfg keys: save, schematicDir, schematicFile, origin, modes, expected, outDir, forceload, views, fov, gamma ..."""
    h = ensure(version, with_litematica=True)
    if not list((h / 'libs').glob('*litematica*.jar')):
        raise SystemExit(f'no Litematica + MaLiLib jars for {version}: `mcb fetch litematica --version {version}` or '
                         '`mcb config add mod_jars <jar>` - the in-game test needs them')
    cfg_path = write_json(Path(cfg['outDir']) / 'ingame-config.json', cfg)
    return gradle(version, 'runVerifyClient', f'-PmcbuildConfig={cfg_path.as_posix()}', log_file=log_file or Path(cfg['outDir']) / 'client.log')
