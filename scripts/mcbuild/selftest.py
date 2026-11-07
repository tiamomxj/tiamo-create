"""`mcb selftest`: offline end-to-end check of the kit, needing nothing but Python + numpy + Pillow.

Builds the starter project on flat ground in Chinese and in English (design -> export -> verify -> materials ->
release), re-reads the schematic independently, writes the site into a vanilla save and reads it back with the
world reader, and parses F3 text. Prints one line per check; exit code 0 when everything passed.
"""
from __future__ import annotations
import shutil, tempfile, time, traceback
from pathlib import Path
from .util import log


def selftest(keep=False, shots=False):
    import importlib.util, sys
    missing = [m for m in ('numpy', 'PIL') if importlib.util.find_spec(m) is None]
    if missing:
        req = Path(__file__).resolve().parent.parent / 'requirements.txt'
        log(f'SELFTEST NOT RUN - missing {", ".join(missing)}: "{sys.executable}" -m pip install -r "{req}"')
        return False
    results = []
    tmp = Path(tempfile.mkdtemp(prefix='mcbuild-selftest-'))

    def check(name, fn):
        t0 = time.time()
        try:
            info = fn()
            results.append((name, True, info))
            log(f'[ok] {name}  {info or ""}  ({time.time() - t0:.1f}s)')
        except BaseException as e:                                   # noqa: BLE001 - report everything
            results.append((name, False, repr(e)))
            log(f'[FAIL] {name}: {e!r}')
            traceback.print_exc()

    def data():
        from .registry import parse, facts, display_name, set_version
        from .util import default_version
        set_version(default_version())
        st = parse('oak_stairs[facing=east,half=top]')
        f = facts(st)
        assert f.boxes and display_name('oak_stairs', 'en') == 'Oak Stairs' and display_name('oak_stairs', 'zh') != 'oak_stairs'
        return f'{default_version()} data, {st.key()}'
    check('bundled block data', data)

    def project(lang):
        from .scaffold import init_project
        from .project import Project
        from . import cli
        d = tmp / f'cottage-{lang}'
        init_project(d, name='Selftest' if lang == 'en' else '自检小屋', pid=f'Selftest{lang.upper()}', source='flat', lang=lang)
        cli.main(['-p', str(d), 'design'])
        cli.main(['-p', str(d), 'export'])
        try:
            cli.main(['-p', str(d), 'release'])
        except SystemExit:
            pass
        else:
            raise AssertionError('Create release before verification was accepted')
        for cmd in (['verify'], ['materials'], ['release']):
            cli.main(['-p', str(d)] + cmd)
        P = Project(d)
        from .util import read_json
        ver = read_json(P.art / 'verification.json')
        assert ver['status'] == 'PASS', ver.get('errors')
        rep = read_json(P.art / 'export-report.json')
        from .schematic import read_any
        from .registry import AIR
        cells = {k: v for k, v in read_any(P.release_dir / rep['file']).items() if v != AIR}
        assert len(cells) == rep['totalBlocks'], (len(cells), rep['totalBlocks'])
        assert rep['format'] == 'create' and rep['dataVersion'] == 3465 and rep['file'].endswith('.nbt'), rep
        cli.main(['-p', str(d), 'preview'])
        cli.main(['-p', str(d), 'release'])
        guide = 'README.md' if lang == 'en' else '使用说明.md'
        assert (P.release_dir / guide).exists(), guide
        text = (P.release_dir / guide).read_text(encoding='utf-8')
        assert 'schematics/' in text and 'pasteReplaceBehavior' not in text
        assert list(P.release_dir.glob('*.html')), 'missing offline preview'
        from .videokit import video_data
        video = video_data(P)
        assert video['file'].endswith('.nbt') and 'Create' in video['ui']['schematic']
        try:
            cli.main(['-p', str(d), 'ingame'])
        except SystemExit as exc:
            assert 'Create' in str(exc)
        else:
            raise AssertionError('Create blueprint was sent to the Litematica harness')
        csvname = 'materials.csv' if lang == 'en' else '材料清单.csv'
        assert (P.release_dir / csvname).exists(), csvname
        if shots:
            cli.main(['-p', str(d), 'preview', '--shots'])
        return f'{len(cells)} blocks, verify PASS, {guide}'
    check('starter project (zh)', lambda: project('zh'))
    check('starter project (en)', lambda: project('en'))

    def create_roundtrip():
        from .build import Build
        from .registry import AIR, parse
        from .create import export_create, check_create_file
        from . import nbt
        from .terrain import make_flat
        site = make_flat((-16, 60, 6, -6, 70, 16), 64)
        site.source['kind'] = 'anvil'
        B = Build(site)
        B.putw((-12, 63, 9), 'stone')
        B.putw((-10, 64, 11), 'chest[facing=east]')
        B.putw((-11, 65, 10), 'chain[axis=y]')
        B.putw((-12, 66, 9), AIR)
        file = tmp / 'CreateRoundtrip.nbt'
        rep = export_create(B, file)
        cells, info = check_create_file(file, 3465)
        assert rep['origin'] == [-12, 63, 9] and rep['enclosingSize'] == [3, 4, 3]
        assert rep['siteAligned'] and not rep['regions'][0]['copiedFromWorld']
        assert {(p[0] - rep['origin'][0], p[1] - rep['origin'][1], p[2] - rep['origin'][2]): st
                for p, st in B.cells.items()} == cells
        assert info['tileEntities'] == 1 and len(cells) == 4
        root = nbt.load(file)
        assert 'minecraft:chain' in [str(s['Name']) for s in root['palette']]
        root['blocks'][0]['state'] = nbt.Int(-1)
        nbt.save(tmp / 'invalid-create.nbt', root)
        try:
            check_create_file(tmp / 'invalid-create.nbt', 3465)
        except AssertionError:
            pass
        else:
            raise AssertionError('invalid palette index was accepted')
        B.putw((-10, 65, 11), parse('pale_oak_planks'))
        try:
            export_create(B, tmp / 'unsupported.nbt')
        except SystemExit:
            pass
        else:
            raise AssertionError('block added after 1.20.1 was accepted')
        return 'negative origins, sparse air, block entities, old ids, corrupt index and newer-block rejection'
    check('Create format + compatibility', create_roundtrip)

    def legacy_export():
        from .project import Project
        from . import cli
        from .util import read_json
        d = tmp / 'cottage-en'
        cfg = d / 'project.toml'
        cfg.write_text(cfg.read_text(encoding='utf-8').replace('format = "create"', 'format = "litematic"'), encoding='utf-8')
        cli.main(['-p', str(d), 'export'])
        cli.main(['-p', str(d), 'verify'])
        P = Project(d)
        assert read_json(P.art / 'export-report.json')['format'] == 'litematic'
        assert read_json(P.art / 'verification.json')['status'] == 'PASS'
        return 'explicit Litematica export and verification still work'
    check('optional Litematica export', legacy_export)

    def world_roundtrip():
        from .terrain import make_flat, extract_anvil
        from .world import write_world
        from .registry import parse
        site = make_flat((0, 48, 0, 48, 96, 48), 63, water_y=None)
        site.IDS[70 - 48, 10, 20] = 0
        ids = dict(site._pal)
        ids[str(len(ids))] = parse('oak_log[axis=y]').nbt()
        site._pal = ids
        site.IDS[66 - 48, 5, 7] = len(ids) - 1
        write_world(tmp / 'world', site, None, 'selftest')
        back = extract_anvil(tmp / 'world', (0, 48, 0, 48, 96, 48))
        diff = sum(1 for y in range(50, 90) for z in range(0, 48, 3) for x in range(0, 48, 3)
                   if back.world(x, y, z) != site.world(x, y, z))
        assert diff == 0 and back.world(7, 66, 5).short == 'oak_log', diff
        return 'save written and read back identically'
    check('world writer + reader', world_roundtrip)

    def f3():
        from .camera import from_f3, points_in_polygon
        cam, f = from_f3('/execute in minecraft:overworld run tp @s 10.5 64 -3.5 450 30', 1920, 1080, 70)
        assert abs(cam.yaw - 90) < 1e-6 and abs(cam.eye[1] - 65.62) < 1e-6
        assert points_in_polygon([(0.5, 0.5), (2, 2)], [(0, 0), (1, 0), (1, 1), (0, 1)]).tolist() == [True, False]
        return 'F3+C text -> camera'
    check('F3 parsing', f3)

    ok = all(r[1] for r in results)
    log(('SELFTEST PASSED' if ok else 'SELFTEST FAILED') + f' - {sum(r[1] for r in results)}/{len(results)} checks; files: {tmp}')
    if not keep and ok:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok
