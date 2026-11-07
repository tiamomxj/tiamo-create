"""mcb - command line for the build kit.   python <skill>/scripts/mcb.py <command> [-p PROJECT] ...

First time on a machine:  doctor (what works here) -> config (remember game folder, language ...)
Typical flow:  init -> find-data -> site -> map / analyze / style / camera -> design (+ draw) -> export -> verify ->
               materials -> preview (+ shots) -> ingame -> release        (`mcb all` runs design ... release)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .util import log, write_json, read_json, KIT


def _project(a):
    from .project import Project
    return Project(a.project)


def _ints(s, n=None):
    v = [int(float(x)) for x in str(s).replace(',', ' ').split()]
    if n and len(v) != n:
        raise SystemExit(f'need {n} numbers: {s}')
    return v


# ------------------------------------------------------------------ setup commands
def cmd_doctor(a):
    from .doctor import doctor
    ok = doctor(version=a.version, as_json=a.json, brief=a.brief)
    if a.strict and not ok:
        sys.exit(1)


def cmd_config(a):
    from . import config as C
    if a.keys:
        for k, (t, d) in C.KEYS.items():
            log(f'  {k:<13} {t.__name__:<5} {d}')
        return
    if a.action is None:
        cfg = C.load()
        log(f'profile: {C.FILE}' + ('' if C.FILE.exists() else '  (not created yet)'))
        print(json.dumps(cfg, ensure_ascii=False, indent=1) if cfg else '  (empty - everything is discovered automatically)')
        return
    if a.action == 'set':
        if not a.value:
            raise SystemExit('usage: mcb config set KEY VALUE')
        val = ' '.join(a.value)
        if a.key == 'client_jars' and not val.lstrip().startswith('{'):      # `set client_jars PATH`: version from the jar
            from .util import _jar_version
            ver = _jar_version(val)
            if not ver:
                raise SystemExit(f'{val} is not a vanilla client jar (no version.json inside)')
            cur = dict(C.load().get('client_jars') or {}); cur[ver] = val
            log('client_jars', C.set_value('client_jars', cur))
            return
        if a.key == 'lang':
            from .i18n import normalize
            val = normalize(val) or val
        log(a.key, '=', C.set_value(a.key, val))
    elif a.action == 'add':
        val = ' '.join(a.value)
        if a.key in ('game_dirs', 'mod_jars') and not Path(val).exists():
            raise SystemExit(f'path does not exist: {val}')
        log(a.key, '=', C.add_value(a.key, val))
    elif a.action == 'remove':
        log(a.key, '=', C.remove_value(a.key, ' '.join(a.value)))
    elif a.action == 'unset':
        C.unset(a.key)
        log('unset', a.key)


def cmd_fetch(a):
    from .fetch import fetch_client, fetch_mods, fetch_jdk_hint
    if a.what == 'client':
        fetch_client(a.version, yes=a.yes, mirror=a.mirror)
    elif a.what == 'litematica':
        fetch_mods(a.version, yes=a.yes)
    elif a.what == 'jdk':
        fetch_jdk_hint()


def cmd_selftest(a):
    from .selftest import selftest
    sys.exit(0 if selftest(keep=a.keep, shots=a.shots) else 1)


# ------------------------------------------------------------------ project commands
def cmd_init(a):
    from .scaffold import init_project
    init_project(Path(a.dir) if a.dir else None, name=a.name, pid=a.id, source=a.source, images=a.images,
                 template=a.template, version=a.version, lang=a.lang)


def cmd_find_data(a):
    from .terrain import discover
    from .util import game_dirs, scan_for_game_dirs
    roots = None
    if a.dir:
        from .util import _expand
        roots = [g for d in a.dir for g in (_expand(Path(d)) or [Path(d)])]
    if a.scan:
        found = scan_for_game_dirs([Path(p) for p in a.scan] if a.scan != ['auto'] else None)
        log('== scan found', len(found), 'game folder(s)')
        for f in found:
            log('  ', f)
        if a.remember:
            from . import config as C
            for f in found:
                C.add_value('game_dirs', str(f))
            log('remembered in the profile (game_dirs)')
        from .util import _expand
        roots = [g for f in found for g in (_expand(f) or [f])] + list(roots or [])
    d = discover(roots)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1)); return
    if not d['gameDirs']:
        log('No game folder found. Ask the player for it (in game: Options > Resource Packs > Open Pack Folder, then go one '
            'folder up), then `mcb config add game_dirs <folder>` - or try `mcb find-data --scan auto`.')
        return
    log('== Game folders')
    for g in d['gameDirs']:
        mods = [k for k in ('litematica', 'voxy', 'bobby', 'xaero', 'distantHorizons') if g.get(k)]
        log(f"  {g['path']}  [{g.get('version') or '?'}] saves {g['saves']}" + (f"  mods: {', '.join(mods)}" if mods else ''))
    if d['voxy']:
        log('== Voxy caches (servers / worlds visited with Voxy; exact blocks)')
        for v in d['voxy']:
            log(f"  {v['server']:<28} {v['dimHash'][:10]}  {v['sizeMB']:>8} MB  {v['store']}")
    if d['bobby']:
        log('== Bobby chunk caches (servers; read as source = "anvil", world = <folder>)')
        for b in d['bobby'][:30]:
            log(f"  {b['server']:<28} {b['dimension']:<24} {b['regions']:>4} regions  {b['folder']}")
    log('== Singleplayer saves (newest first)')
    for s in d['saves'][:30]:
        log(f"  {s['name']:<28} {s.get('version', '?'):<10} player {s.get('playerPos', '-')}  {s['folder']}")
    if d['waypoints']:
        log('== Xaero waypoints (names like home / base / 家 locate "my house")')
        for w in d['waypoints'][:60]:
            log(f"  [{w['world']}/{w['dim']}] {w['name']}: {w['x']} {w['y']} {w['z']}")
    if d['schematics']:
        log('== Litematica schematics folders')
        for s in d['schematics']:
            log(f"  {s['folder']}  {s['count']} files, newest: {', '.join(s['recent'][:5])}")
    if d['screenshots']:
        import time
        log('== Newest screenshots (F2) - the player may mean one of these')
        for s in d['screenshots'][:8]:
            log(f"  {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['mtime']))}  {s['file']}")


def cmd_site(a):
    P = _project(a)
    site = P.extract_site()
    from .maps import render_map, height_image
    from .i18n import ti
    x0, y0, z0, x1, y1, z1 = site.box
    render_map(site, P.art / 'site-map.png', scale=a.scale,
               title=ti('map.site', name=P.name, kind=site.source.get('kind'), x0=x0, x1=x1, z0=z0, z1=z1))
    height_image(site, P.art / 'site-height.png')
    log('SITE', site.source, 'box', site.box, '->', P.art / 'site-map.png')


def cmd_map(a):
    P = _project(a)
    site = P.site()
    from .maps import render_map
    box = tuple(_ints(a.box, 4)) if a.box else None
    marks = []
    for m in a.mark or []:
        parts = m.split(',')
        marks.append({'x': int(parts[0]), 'z': int(parts[1]), 'label': ','.join(parts[2:]) if len(parts) > 2 else ''})
    boxes = []
    for b in a.rect or []:
        parts = b.split(',')
        boxes.append({'x0': int(parts[0]), 'z0': int(parts[1]), 'x1': int(parts[2]), 'z1': int(parts[3]), 'label': ','.join(parts[4:])})
    cells = []
    if a.design:
        B = P.design()
        cells.append({'cells': list({(x, z) for (x, y, z), st in B.cells.items()}), 'color': (255, 60, 60, 110)})
    out = P.path(a.out or 'artifacts/map.png')
    render_map(site, out, box, a.scale, a.grid, a.label_every, marks, boxes, (), cells, a.title)
    log('MAP', out)


def cmd_analyze(a):
    P = _project(a)
    from .analyze import analyze
    analyze(P, box=tuple(_ints(a.box, 4)) if a.box else None, footprint=_ints(a.footprint.replace('x', ' '), 2) if a.footprint else None,
            top=a.top, pad_y=a.pad_y)


def cmd_style(a):
    P = _project(a)
    from .analyze import style_report
    style_report(P, tuple(_ints(a.box, 6)), a.name or 'reference')


def cmd_camera(a):
    P = _project(a)
    from . import camera as C
    from PIL import Image
    if a.action == 'set':                       # straight from F3 data: no fitting needed
        text = a.f3 or (Path(a.f3_file).read_text(encoding='utf-8') if a.f3_file else '')
        W, H = 1920, 1080
        img_rel = a.image
        if img_rel:
            W, H = Image.open(P.path(img_rel)).size
        cam, f = C.from_f3(text, W, H, a.fov)
        C.save(cam, P.art / 'camera.json', {'fit': {'source': 'f3', 'dimension': f['dimension'], 'target': f['target']},
                                            'image': img_rel})
        log('CAMERA from F3', cam.to_json(), 'targeted block', f['target'], '-> artifacts/camera.json')
        if img_rel and P.cfg.get('site', {}).get('source') not in (None, 'flat', 'none') and (P.art / 'site.npz').exists():
            site = P.site()
            ov = C.render_site(site, cam, 0.5)
            Image.blend(ov, Image.open(P.path(img_rel)).convert('RGB').resize(ov.size), 0.45).save(P.art / 'camera-overlay.png')
            log('OVERLAY', P.art / 'camera-overlay.png', '(terrain should line up with the screenshot; if not, check the fov)')
        return
    site = P.site()
    if a.action == 'fit':
        spec = read_json(P.path(a.spec))
        img = Image.open(P.path(spec['image']))
        W, H = img.size
        init = spec['init']                         # [yaw, pitch, fov, ex, ey, ez]
        pairs = []
        if spec.get('pairs'):
            pairs = [((u, v), tuple(w)) for (u, v), w in spec['pairs']]
        if spec.get('spots'):                       # pixel spots matched to block types near the init camera
            cand = C.site_points(site, set(spec.get('match', ['lantern', 'torch'])), box=spec.get('box'))
            cam0 = C.Camera(init[0], init[1], init[2], tuple(init[3:6]), W, H)
            for uv, w, d in C.match(cam0, spec['spots'], cand):
                pairs.append((uv, w))
                log(f'  spot {uv} -> {[round(v, 1) for v in w]}  ({d:.1f}px at init)')
        cam, info = C.fit(pairs, W, H, init, eye_sigma=spec.get('eye_sigma', 1.0))
        C.save(cam, P.art / 'camera.json', {'fit': info, 'image': spec['image']})
        ov = C.render_site(site, cam, 0.5).resize((W // 2, H // 2))
        Image.blend(ov, img.convert('RGB').resize((W // 2, H // 2)), 0.45).save(P.art / 'camera-overlay.png')
        log('CAMERA', cam.to_json(), info, '-> artifacts/camera.json, camera-overlay.png')
    elif a.action == 'render':
        cam = C.load(P.art / 'camera.json')
        img = Image.open(P.path(read_json(P.art / 'camera.json')['image']))
        ov = C.render_site(site, cam, 0.5)
        Image.blend(ov, img.convert('RGB').resize(ov.size), 0.45).save(P.art / 'camera-overlay.png')
        log('OVERLAY', P.art / 'camera-overlay.png')
    elif a.action == 'outline':
        cam = C.load(P.art / 'camera.json')
        cj = read_json(P.art / 'camera.json')
        img = Image.open(P.path(cj['image']))
        if a.poly:
            poly = [tuple(map(float, p.split(','))) for p in a.poly]
        else:
            rgb = tuple(int(a.color.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
            poly = C.stroke_polygon(img, rgb, a.tol)
            if not poly:
                raise SystemExit('no stroke of that colour found in the screenshot; give the pixel polygon with --poly u,v ...')
        cols = C.columns_in_polygon(site, cam, poly, occlusion=not a.no_occlusion)
        write_json(P.art / 'plot.json', {'camera': cam.to_json(), 'polygonScreen': poly, 'columns': cols})
        xs = [c[0] for c in cols]; zs = [c[1] for c in cols]
        log('PLOT', len(cols), 'columns', 'x', min(xs), max(xs), 'z', min(zs), max(zs), '-> artifacts/plot.json')
        from .maps import render_map
        from .i18n import ti
        render_map(site, P.art / 'plot-map.png', (min(xs) - 24, min(zs) - 24, max(xs) + 25, max(zs) + 25), 8, 8, 16,
                   cells=[{'cells': [(c[0], c[1]) for c in cols], 'color': (40, 140, 255, 120)}], title=ti('map.plot'))
    elif a.action == 'ray':
        cam = C.load(P.art / 'camera.json')
        for s in a.px or [f'{cam.W / 2},{cam.H / 2}']:
            u, v = map(float, s.split(','))
            hit = C.raycast(site, cam, u, v)
            log(f'  px ({u:.0f},{v:.0f}) ->', hit, site.world(*hit[0]).key() if hit else '')


def cmd_design(a):
    P = _project(a)
    B = P.design(rerun=True)
    if not a.no_drawings:
        from .maps import design_drawings
        files = design_drawings(B, P.art / 'drawings', scale=a.scale)
        log('DRAWINGS', P.art / 'drawings', [f.name for f in files])
    from .verify import support_problem  # noqa: F401  (import check)
    s = read_json(P.art / 'design-summary.json')
    log('TOP BLOCKS', ', '.join(f'{k}×{v}' for k, v in s['top'][:15]))
    log('PARTS', s['parts'])


def cmd_draw(a):
    P = _project(a)
    from .maps import design_drawings
    files = design_drawings(P.design(), P.art / 'drawings', scale=a.scale, with_terrain=not a.no_terrain)
    log('DRAWINGS', [str(f) for f in files])


def cmd_export(a):
    P = _project(a)
    from .schematic import export_litematic, write_schem
    from .i18n import t
    from . import config
    B = P.design()
    ec = P.cfg.get('export', {})
    fmt = ec.get('format', 'create')
    if fmt not in ('create', 'litematic'):
        raise SystemExit('export.format must be "create" or "litematic"')
    if fmt == 'create':
        from .create import export_create
        target = ec.get('target_version') or '1.20.1'
        filename = ec.get('file') or f'{P.id}-{target}.nbt'
        if Path(filename).name != filename or Path(filename).suffix != '.nbt':
            raise SystemExit('Create export.file must be a filename ending in .nbt')
        path = P.release_dir / filename
        rep = export_create(B, path, target=target, name=P.name,
                            create_version=ec.get('create_version', '6.0.8'), loader=ec.get('loader', 'Forge'))
        write_json(P.art / 'export-report.json', rep)
        (P.art / 'verification.json').unlink(missing_ok=True)
        log('CREATE', rep['file'], 'origin', rep['origin'], 'size', rep['enclosingSize'],
            'blocks', rep['totalBlocks'], 'for', target, f"(DataVersion {rep['dataVersion']})")
        if ec.get('schem'):
            log('SCHEM', write_schem(path.with_suffix('.schem'), B, name=P.name, target=target))
        return
    kind = B.site.source.get('kind') if B.site is not None else 'none'
    mode = ec.get('mode') or ('site' if kind in ('voxy', 'anvil', 'schematic') else 'portable')
    path = P.release_dir / P.litematic_name
    desc = ec.get('description') or (t('export.desc', name=P.name) + (t('export.desc_site') if mode == 'site' else ''))
    author = ec.get('author') or P.cfg['project'].get('author') or config.get('author') or 'mcbuild'
    trace = []
    target = ec.get('target_version') or None
    rep = export_litematic(B, path, mode, name=ec.get('name', P.name), author=author,
                           description=desc, penalty=ec.get('region_penalty', 20), part_names=ec.get('part_names', {}),
                           max_size=ec.get('max_region') or None, trace=trace, target=target)
    write_json(P.art / 'litematic-report.json', rep)
    rep['format'] = 'litematic'
    write_json(P.art / 'export-report.json', rep)
    (P.art / 'verification.json').unlink(missing_ok=True)
    write_json(P.art / 'kd-trace.json', trace, indent=None)
    log('LITEMATIC', rep['file'], 'mode', mode, 'origin', rep['origin'], 'size', rep['enclosingSize'], 'regions', len(rep['regions']),
        'blocks', rep['totalBlocks'], 'for', rep['targetVersion'], f"(DataVersion {rep['dataVersion']})" + (f", renamed {rep['renamed']}" if rep['renamed'] else ''))
    for r in rep['regions']:
        cp = sum(r['copiedFromWorld'].values())
        log(f"   {r['name']:<24} {r['min']} {r['size']} blocks {r['blocks']} TE {r['tileEntities']} copied {cp}")
    if ec.get('schem'):
        sp = path.with_suffix('.schem')
        info = write_schem(sp, B, name=P.name, target=target)
        log('SCHEM', sp.name, info)


def cmd_verify(a):
    P = _project(a)
    from .verify import verify
    R = verify(P)
    if R['status'] != 'PASS' and a.strict:
        sys.exit(1)


def cmd_materials(a):
    P = _project(a)
    from .materials import write
    ml, parts = write(P.design(), P.art)
    for m in ml[:60]:
        log(f"  {m['name']:<12} {m['count']:>6}  {m['stacks']}  {m['note'] or ''}")
    log('MATERIALS', len(ml), 'items ->', P.art / 'materials.csv')


def cmd_preview(a):
    P = _project(a)
    from .preview import build_preview
    out = build_preview(P, shots=a.shots)
    log('PREVIEW', out)


def cmd_shots(a):
    P = _project(a)
    from .preview import shoot
    shoot(P, a.views or None, P.path(a.out) if a.out else None, a.width, a.height)


def cmd_ingame(a):
    P = _project(a)
    from .ingame import run_ingame
    run_ingame(P, run=not a.no_run, modes=a.modes, showcase=a.showcase)


def cmd_release(a):
    P = _project(a)
    from .release import release
    release(P)


def cmd_all(a):
    P = _project(a)
    a.no_drawings = False; a.scale = 0; a.strict = False; a.shots = not a.no_shots; a.views = None; a.out = None
    cmd_design(a); cmd_export(a)
    from .verify import verify
    R = verify(P)
    cmd_materials(a); cmd_preview(a)
    if a.ingame:
        a.no_run = False; a.modes = None; a.showcase = False
        cmd_ingame(a)
    cmd_release(a)
    log('ALL DONE', 'verify', R['status'])


def cmd_video(a):
    P = _project(a)
    from . import videokit as V
    if a.action == 'init':
        V.init(P, overwrite_scenes=a.reset)
    elif a.action == 'narrate':
        V.narrate(P)
    elif a.action == 'check':
        V.check(P)
    elif a.action == 'stills':
        V.stills(P, a.times)
    elif a.action == 'mix':
        V.mix(P)
    elif a.action == 'render':
        V.render(P, a.workers)


def cmd_facts(a):
    from .harness import dump_facts
    dump_facts(a.version)


def cmd_blocks(a):
    """Search block ids / in-game names (zh or en); show properties and facts."""
    from .registry import block_names, display_name, properties, parse, facts, set_version
    set_version(a.version)
    q = a.query.lower()
    hits = [n for n in block_names() if q in n or q in display_name(n, 'zh') or q in display_name(n, 'en').lower()]
    for n in hits[:a.limit]:
        st = parse(n)
        f = facts(st)
        log(f"{n:<42} {display_name(n, 'en'):<26} {display_name(n, 'zh'):<10} light {f.lum:<2} {'solid' if f.boxes else 'no-collision'}  {properties(n)}")
    if len(hits) > a.limit:
        log(f'... {len(hits)} matches')


def main(argv=None):
    from .util import default_version
    dv = default_version()
    ap = argparse.ArgumentParser(prog='mcb', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-p', '--project', default='.', help='project folder (with project.toml); default: current folder')
    sub = ap.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('doctor', help='what works on this machine (Python packages, game folders, Java, textures, screenshots ...)')
    c.add_argument('--version', default=dv); c.add_argument('--json', action='store_true')
    c.add_argument('--brief', action='store_true', help='profile + one-line capabilities, fast'); c.add_argument('--strict', action='store_true')
    c.set_defaults(fn=cmd_doctor)
    c = sub.add_parser('config', help='show or change the saved profile (~/.mcbuild/config.json)')
    c.add_argument('action', nargs='?', choices=['set', 'add', 'remove', 'unset']); c.add_argument('key', nargs='?'); c.add_argument('value', nargs='*')
    c.add_argument('--keys', action='store_true', help='list the known keys'); c.set_defaults(fn=cmd_config)
    c = sub.add_parser('fetch', help='download what this machine lacks (asks for --yes): client jar (textures) or Litematica + MaLiLib')
    c.add_argument('what', choices=['client', 'litematica', 'jdk']); c.add_argument('--version', default=dv)
    c.add_argument('--yes', action='store_true', help='really download (without it: only show what would be downloaded)')
    c.add_argument('--mirror', choices=['mojang', 'bmclapi'], help='client: download source (bmclapi = mirror for mainland China)')
    c.set_defaults(fn=cmd_fetch)
    c = sub.add_parser('selftest', help='offline end-to-end check of the kit on a temporary project')
    c.add_argument('--keep', action='store_true'); c.add_argument('--shots', action='store_true'); c.set_defaults(fn=cmd_selftest)

    c = sub.add_parser('init', help='new project'); c.add_argument('dir', nargs='?', help='folder (default: <projects_dir>/<id>)')
    c.add_argument('--name'); c.add_argument('--id')
    c.add_argument('--source', default='flat', choices=['voxy', 'anvil', 'schematic', 'flat', 'none'])
    c.add_argument('--images', nargs='*', default=[]); c.add_argument('--template', default='basic'); c.add_argument('--version', default=dv)
    c.add_argument('--lang', help='zh or en (default: profile / system language)'); c.set_defaults(fn=cmd_init)
    c = sub.add_parser('find-data', help='list game folders, Voxy/Bobby caches, saves, waypoints, schematics, screenshots')
    c.add_argument('--json', action='store_true'); c.add_argument('--dir', nargs='*', help='only look in these game folders')
    c.add_argument('--scan', nargs='*', help='also search these folders (or "auto": home + drives) for .minecraft folders')
    c.add_argument('--remember', action='store_true', help='save scan results in the profile'); c.set_defaults(fn=cmd_find_data)
    c = sub.add_parser('site', help='read [site] -> artifacts/site.npz + maps'); c.add_argument('--scale', type=int, default=3); c.set_defaults(fn=cmd_site)
    c = sub.add_parser('map', help='top-down map (coordinate grid, marks)')
    c.add_argument('--box', help='x0,z0,x1,z1'); c.add_argument('--scale', type=int, default=4); c.add_argument('--grid', type=int, default=16)
    c.add_argument('--label-every', type=int, default=32); c.add_argument('--mark', action='append', help='x,z,label')
    c.add_argument('--rect', action='append', help='x0,z0,x1,z1,label'); c.add_argument('--design', action='store_true', help='overlay the design footprint')
    c.add_argument('--title'); c.add_argument('--out'); c.set_defaults(fn=cmd_map)
    c = sub.add_parser('analyze', help='site analysis: heights / water / existing builds / flat candidates'); c.add_argument('--box', help='x0,z0,x1,z1')
    c.add_argument('--footprint', help='WxD: find spots for this footprint'); c.add_argument('--top', type=int, default=6)
    c.add_argument('--pad-y', type=int, default=None); c.set_defaults(fn=cmd_analyze)
    c = sub.add_parser('style', help='block statistics and palette of a reference build'); c.add_argument('--box', required=True, help='x0,y0,z0,x1,y1,z1 (inclusive)')
    c.add_argument('--name'); c.set_defaults(fn=cmd_style)
    c = sub.add_parser('camera', help='screenshot camera: set (from F3) / fit / render / outline / ray')
    c.add_argument('action', choices=['set', 'fit', 'render', 'outline', 'ray'])
    c.add_argument('--f3', help='set: F3+C text or the XYZ/Facing lines'); c.add_argument('--f3-file', help='set: file holding that text')
    c.add_argument('--image', help='set: the screenshot (project-relative path)'); c.add_argument('--fov', type=float, default=70.0)
    c.add_argument('--spec', default='artifacts/camera-spec.json'); c.add_argument('--color', default='#2a7bff'); c.add_argument('--tol', type=int, default=90)
    c.add_argument('--poly', nargs='*'); c.add_argument('--px', nargs='*', default=[]); c.add_argument('--no-occlusion', action='store_true')
    c.set_defaults(fn=cmd_camera)
    c = sub.add_parser('design', help='run design.py -> rules pass -> cache + drawings'); c.add_argument('--no-drawings', action='store_true')
    c.add_argument('--scale', type=int, default=0); c.set_defaults(fn=cmd_design)
    c = sub.add_parser('draw', help='drawings only'); c.add_argument('--scale', type=int, default=0); c.add_argument('--no-terrain', action='store_true'); c.set_defaults(fn=cmd_draw)
    c = sub.add_parser('export', help='write a Create .nbt blueprint (or optional .litematic/.schem)'); c.set_defaults(fn=cmd_export)
    c = sub.add_parser('verify', help='acceptance checks'); c.add_argument('--strict', action='store_true'); c.set_defaults(fn=cmd_verify)
    c = sub.add_parser('materials', help='survival materials list'); c.set_defaults(fn=cmd_materials)
    c = sub.add_parser('preview', help='offline 3D preview page'); c.add_argument('--shots', action='store_true', help='also take headless screenshots'); c.set_defaults(fn=cmd_preview)
    c = sub.add_parser('shots', help='headless screenshots of the preview page'); c.add_argument('views', nargs='*'); c.add_argument('--out')
    c.add_argument('--width', type=int, default=1600); c.add_argument('--height', type=int, default=900); c.set_defaults(fn=cmd_shots)
    c = sub.add_parser('ingame', help='real-client paste test + game screenshots (opens a Minecraft window)'); c.add_argument('--no-run', action='store_true')
    c.add_argument('--modes', nargs='*'); c.add_argument('--showcase', action='store_true', help='also zip the pasted showcase world'); c.set_defaults(fn=cmd_ingame)
    c = sub.add_parser('release', help='collect the deliverables'); c.set_defaults(fn=cmd_release)
    c = sub.add_parser('all', help='design -> export -> verify -> materials -> preview -> release'); c.add_argument('--ingame', action='store_true')
    c.add_argument('--no-shots', action='store_true'); c.set_defaults(fn=cmd_all)
    c = sub.add_parser('video', help='making-of video: init / narrate / check / stills / mix / render')
    c.add_argument('action', choices=['init', 'narrate', 'check', 'stills', 'mix', 'render']); c.add_argument('times', nargs='*')
    c.add_argument('--workers', type=int, default=4); c.add_argument('--reset', action='store_true', help='init: overwrite scenes.js')
    c.set_defaults(fn=cmd_video)
    c = sub.add_parser('facts', help='(new game version) dump block facts from the game code'); c.add_argument('--version', default=dv); c.set_defaults(fn=cmd_facts)
    c = sub.add_parser('blocks', help='look up block ids / names / properties'); c.add_argument('query'); c.add_argument('--limit', type=int, default=40)
    c.add_argument('--version', default=dv); c.set_defaults(fn=cmd_blocks)
    a = ap.parse_args(argv)
    a.fn(a)
