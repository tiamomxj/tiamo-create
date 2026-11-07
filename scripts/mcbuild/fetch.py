"""`mcb fetch`: download what this machine lacks, from the official sources, into MCBUILD_HOME only.

  client      vanilla client jar of a version (block models + textures for previews) - Mojang (piston-meta / piston-data)
  litematica  Litematica + MaLiLib for the real-client paste test - Modrinth
  jdk         prints how to install a JDK 21 on this OS (no download)

Without --yes nothing is downloaded: the command prints what it would fetch (source, size, destination) so the agent
can ask the user first. Files are checked against the hashes published by the source.
"""
from __future__ import annotations
import hashlib, json, sys, urllib.parse, urllib.request
from pathlib import Path
from .util import HOME, log

UA = {'User-Agent': 'mcbuild/2.0 (minecraft-build-design agent skill)'}
MANIFEST = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
MIRRORS = {'bmclapi': 'https://bmclapi2.bangbang93.com'}      # community mirror used by HMCL/PCL (mainland China)


def _mirror(url, mirror):
    if not mirror or mirror == 'mojang':
        return url
    base = MIRRORS[mirror]
    for host in ('https://piston-meta.mojang.com', 'https://piston-data.mojang.com', 'https://launchermeta.mojang.com',
                 'https://launcher.mojang.com'):
        if url.startswith(host):
            return base + url[len(host):]
    return url


def get_json(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def download(url, dest, sha1=None, sha512=None, size=None, timeout=60):
    """Stream url -> dest (via dest.part), verify the hash, then move into place. Returns dest."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.part')
    h1, h5, n = hashlib.sha1(), hashlib.sha512(), 0
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r, open(part, 'wb') as fh:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            fh.write(b); h1.update(b); h5.update(b); n += len(b)
            if size and n % (8 << 20) < (1 << 16):
                log(f'  {n / 1e6:.0f} / {size / 1e6:.0f} MB')
    if (sha1 and h1.hexdigest() != sha1) or (sha512 and h5.hexdigest() != sha512) or (size and n != size):
        part.unlink(missing_ok=True)
        raise SystemExit(f'download of {url} failed verification (size or hash mismatch) - nothing was kept')
    part.replace(dest)
    return dest


def _sha1(p):
    h = hashlib.sha1()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def fetch_client(version, yes=False, mirror=None):
    dest = HOME / 'versions' / version / 'client.jar'
    try:
        man = get_json(_mirror(MANIFEST, mirror))
    except OSError as e:
        raise SystemExit(f'cannot reach the version manifest ({e}). Behind a firewall in mainland China? add `--mirror bmclapi`.')
    entry = next((v for v in man['versions'] if v['id'] == version), None)
    if entry is None:
        raise SystemExit(f'Mojang has no version {version!r}')
    d = get_json(_mirror(entry['url'], mirror))['downloads']['client']
    if dest.exists() and _sha1(dest) == d['sha1']:
        log('already there:', dest); return dest
    src = _mirror(d['url'], mirror)
    log(f"Minecraft {version} client jar: {d['size'] / 1e6:.1f} MB from {urllib.parse.urlsplit(src).netloc} -> {dest}")
    if not yes:
        log('Nothing downloaded. Ask the user, then run again with --yes.')
        sys.exit(2)
    download(src, dest, sha1=d['sha1'], size=d['size'])
    log('saved', dest, '(used for block models and textures only; previews and maps now look like the game)')
    return dest


def _modrinth_file(slug, version):
    q = urllib.parse.urlencode({'loaders': json.dumps(['fabric']), 'game_versions': json.dumps([version])})
    vs = get_json(f'https://api.modrinth.com/v2/project/{slug}/version?{q}')
    if not vs:
        raise SystemExit(f'Modrinth has no Fabric build of {slug} for Minecraft {version}')
    vs.sort(key=lambda v: (v.get('version_type') == 'release', v.get('date_published', '')), reverse=True)
    v = vs[0]
    f = next((f for f in v['files'] if f.get('primary')), v['files'][0])
    return v['version_number'], f


def fetch_mods(version, yes=False):
    plan = []
    for slug in ('litematica', 'malilib'):
        try:
            num, f = _modrinth_file(slug, version)
        except OSError as e:
            raise SystemExit(f'cannot reach api.modrinth.com ({e})')
        plan.append((slug, num, f, HOME / 'mods' / version / f['filename']))
    for slug, num, f, dest in plan:
        log(f"{slug} {num}: {f['size'] / 1e6:.1f} MB from Modrinth -> {dest}" + ('  (already there)' if dest.exists() else ''))
    if not yes:
        log('Nothing downloaded. Ask the user, then run again with --yes.')
        sys.exit(2)
    for slug, num, f, dest in plan:
        if not dest.exists():
            download(f['url'], dest, sha512=f['hashes'].get('sha512'), sha1=f['hashes'].get('sha1'), size=f.get('size'))
    log('saved in', HOME / 'mods' / version, '- used only by the in-game test harness, never copied into your game')


def fetch_jdk_hint():
    from .doctor import _jdk_hint
    log('Install a JDK 21 (needed only for `mcb ingame` and `mcb facts`):')
    log('  ', _jdk_hint())
    log('then `mcb doctor` should find it; or `mcb config set jdk <JDK folder>`.')
