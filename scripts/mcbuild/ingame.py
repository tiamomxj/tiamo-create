"""Real-client acceptance test: vanilla save with the site terrain -> the user's own Litematica pastes the delivered
schematic (each paste mode) -> every schematic cell compared with the world -> vanilla screenshots.
Opens a Minecraft window for a few minutes (Fabric client gametest); nothing touches the user's own saves.
"""
from __future__ import annotations
import math, shutil, zipfile
from pathlib import Path
from .util import log, read_json, write_json
from .registry import version
from .i18n import t


def look(pos, target):
    dx, dy, dz = (target[k] - pos[k] for k in range(3))
    yaw = math.degrees(math.atan2(-dx, dz))
    pitch = math.degrees(-math.atan2(dy, math.hypot(dx, dz)))
    return round(yaw, 2), round(pitch, 2)


def views_for(P):
    """In-game views: [ingame].views from project.toml, else the preview presets (no cut-away ones) + night shots."""
    ic = P.cfg.get('ingame', {})
    if ic.get('views'):
        out = []
        for v in ic['views']:
            if 'yaw' not in v:
                v = dict(v); v['yaw'], v['pitch'] = look(v['pos'], v['target'])
                v['pos'] = [v['pos'][0], v['pos'][1] - 1.62, v['pos'][2]]
            out.append(v)
        return out
    pv = read_json(P.art / 'preview' / 'views.json', [])
    out = []
    for k, v in enumerate(pv):
        if v.get('cut') or v['name'] == 'top':
            continue
        if v.get('eye'):
            e = v['eye']; out.append({'name': f'{k:02d}-{v["name"]}', 'label': v.get('label', v['name']), 'pos': [e[0], e[1] - 1.62, e[2]],
                                      'yaw': v['yaw'], 'pitch': v['pitch'], 'fov': v.get('fov', 70)})
        else:
            yaw, pitch = look(v['pos'], v['target'])
            out.append({'name': f'{k:02d}-{v["name"]}', 'label': v.get('label', v['name']), 'pos': [v['pos'][0], v['pos'][1] - 1.62, v['pos'][2]],
                        'yaw': yaw, 'pitch': pitch, 'fov': min(110, max(30, v.get('fov', 70)))})
    night = [dict(v, name=v['name'] + '-night', label=t('view.night', label=v['label']), time=18000) for v in out
             if v['name'].endswith(('overview', 'eye', 'front'))][:2]
    dusk = [dict(v, name=v['name'] + '-dusk', label=t('view.dusk', label=v['label']), time=12600) for v in out
            if v['name'].endswith('overview')][:1]
    return out + dusk + night


def expected_cells(P, rep):
    from .schematic import litematic_cells
    ox, oy, oz = rep['origin']
    lines = [f'{x + ox} {y + oy} {z + oz} {st.key()}' for (x, y, z), st in litematic_cells(P.release_dir / rep['file']).items()]
    p = P.art / 'ingame' / 'expected-cells.txt'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return p, len(lines)


def run_ingame(P, run=True, modes=None, showcase=False):
    rep = read_json(P.art / 'export-report.json')
    if (rep and rep.get('format') == 'create') or P.cfg.get('export', {}).get('format', 'create') == 'create':
        raise SystemExit('Create .nbt requires a Forge + Create test in the target game; the bundled Litematica/Fabric harness cannot test it')
    from . import harness
    from .world import write_world
    B = P.design()
    site = B.site
    rep = read_json(P.art / 'litematic-report.json')
    if rep is None:
        raise SystemExit('run `mcb export` first')
    if site is None:
        raise SystemExit('the in-game paste test needs terrain ([site]); portable builds can skip it')
    from .compat import is_older
    if is_older(rep.get('targetVersion'), P.version):
        raise SystemExit(f"the in-game test runs Minecraft {P.version}; this schematic is for {rep['targetVersion']} - test it in the "
                         f"player's own game instead")
    h = harness.ensure(P.version, with_litematica=True)
    save = f'mcbuild-{P.id}'
    save_dir = h / 'run' / 'saves' / save
    if save_dir.exists():
        shutil.rmtree(save_dir)                       # our own generated test save
    (ox, oy, oz) = rep['origin']
    sx, sy, sz = rep['enclosingSize']
    vc = P.cfg.get('verify', {})
    spawn = vc.get('walk_start') or [ox + sx // 2, oy + sy, oz - 4]
    write_world(save_dir, site, None, t('ingame.save', name=P.name), spawn)
    exp, n = expected_cells(P, rep)
    views = views_for(P)
    out = P.art / 'ingame'
    for f in out.glob('*.png'):
        f.unlink()
    for f in ('ingame-report.json', 'FAILED.txt'):
        if (out / f).exists():
            (out / f).unlink()
    x0, z0 = ox - 16, oz - 16
    x1, z1 = ox + sx + 16, oz + sz + 16
    cfg = {'save': save, 'schematicDir': str(P.release_dir), 'schematicFile': rep['file'], 'origin': rep['origin'],
           'modes': modes or P.cfg.get('ingame', {}).get('modes', ['default', 'with_non_air', 'all']), 'expected': str(exp),
           'outDir': str(out), 'forceload': [x0, z0, x1, z1], 'views': views, 'fov': 70, 'gamma': 0.5, 'settle': 60}
    write_json(out / 'ingame-config.json', cfg)
    log('INGAME', 'save', save_dir, 'cells', n, 'views', len(views))
    if not run:
        return cfg
    log('starting the real client (a Minecraft window opens and closes itself after a few minutes) ...')
    harness.run_ingame(cfg, P.version, log_file=out / 'client.log')
    res = read_json(out / 'ingame-report.json')
    if res is None:
        fail = out / 'FAILED.txt'
        raise SystemExit('client test failed: ' + (fail.read_text(encoding='utf-8')[:2000] if fail.exists() else 'see client.log'))
    for k, v in res.items():
        if k.startswith('paste_'):
            log(f"  {k}: checked {v['cellsChecked']} cells, mismatched {v['cellsMismatched']}  {v['mismatchKinds'] if v['cellsMismatched'] else ''}")
    log('  screenshots', len(res.get('screenshots', [])), '->', out, ' status', res['status'])
    if showcase:
        zp = P.release_dir / t('file.showcase', id=P.id)
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in save_dir.rglob('*'):
                if f.is_file() and f.name != 'session.lock':
                    z.write(f, Path(save) / f.relative_to(save_dir))
        log('  showcase world', zp)
    return res
