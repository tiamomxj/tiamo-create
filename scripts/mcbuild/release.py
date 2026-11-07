"""Collect the deliverables into release/ and write the player's guide (使用说明.md / README.md, project language)."""
from __future__ import annotations
import shutil, zipfile
from pathlib import Path
from .registry import version
from .i18n import t, direction
from .util import log, read_json


def guide(P, rep, ver, ig, files, removes=0):
    pc = P.cfg.get('preview', {})
    rc = P.cfg.get('release', {})
    mode = rep.get('mode', 'site')
    is_create = rep.get('format') == 'create'
    ox, oy, oz = rep['origin']
    sx, sy, sz = rep['enclosingSize']
    L = [f'# {P.name}', '']
    if pc.get('lead'):
        L += [pc['lead'], '']
    L += [f"## {t('rel.files')}", '']
    for f, what in files:
        L.append(f'- `{f}`: {what}' if P.lang != 'zh' else f'- `{f}`：{what}')
    L += ['', f"## {t('rel.place')}", '']
    if is_create:
        L += create_placement(P, rep, removes)
    elif mode == 'site':
        L += ['- ' + t('rel.site1', x=ox, y=oy, z=oz), '- ' + t('rel.site2', sx=sx, sy=sy, sz=sz, n=len(rep['regions']))]
    else:
        front = direction(pc.get('front', 'south'))
        L += ['- ' + t('rel.portable1', sx=sx, sy=sy, sz=sz, front=front), '- ' + t('rel.portable2')]
    if not is_create and removes:
        L += ['- ' + t('rel.paste_all', n=removes), '- ' + t('rel.survival_all')]
    elif not is_create:
        L += ['- ' + t('rel.paste_nonair'), '- ' + t('rel.survival')]
    from .compat import is_older
    if is_create:
        L += [f"- Minecraft Java {rep['targetVersion']} · {rep.get('loader', 'Forge')} · Create {rep.get('createVersion', '6.0.8')} · DataVersion {rep['dataVersion']}."]
    elif is_older(rep.get('targetVersion'), version()):
        ren = ', '.join(f"{a.split(':')[1]} → {b.split(':')[1]}" for a, b in (rep.get('renamed') or {}).items())
        L += ['- ' + t('rel.version_target', t=rep['targetVersion'], dv=rep['dataVersion'], renamed=t('rel.renamed', list=ren) if ren else '')]
    else:
        L += ['- ' + t('rel.version_note', v=version())]
    if rc.get('notes'):
        L += ['', f"## {t('rel.notes')}", ''] + [f'- {n}' for n in rc['notes']]
    L += ['', f"## {t('rel.checks')}", '']
    if ver:
        f = ver.get('file', {})
        if is_create:
            L.append(f"- Create NBT: {f.get('cellsDecoded')} cells, {f.get('paletteStatesValidated')} palette states, "
                     f"{f.get('tileEntities')} block entities; DataVersion {rep['dataVersion']}.")
            L.append('- 未在 Forge + Create 客户端内实际加载或使用蓝图炮测试。' if P.lang == 'zh'
                     else '- Not tested by loading or printing in a Forge + Create client.')
        else:
            L.append('- ' + t('rel.chk_file', r=f.get('regions'), c=f.get('cellsDecoded'), s=f.get('paletteStatesValidated'), v=version(),
                              te=f.get('tileEntities'), rs='' if f.get('regions') == 1 else 's', tes='y' if f.get('tileEntities') == 1 else 'ies'))
        L.append('- ' + t('rel.chk_rules', n=ver.get('rules', {}).get('problems', '?')))
        sp = ver.get('spawnProofing')
        if sp:
            L.append('- ' + t('rel.chk_spawn', n=sp['spawnableSurfaces'], d=sp['darkSurfaces']))
        if ver.get('walk'):
            tg = ver['walk']['targets']
            L.append('- ' + t('rel.chk_walk', a=sum(tg.values()), b=len(tg)))
        for w in ver.get('warnings', []):
            L.append('- ' + t('rel.chk_warn', check=w['check'], count=w.get('count', ''), blocks=w.get('blocks', '')))
    if ig:
        names = {'none': t('rel.mode_none'), 'with_non_air': 'With non-air', 'all': 'All'}
        parts = []
        for k, v in ig.items():
            if k.startswith('paste_'):
                m = k[k.find('(') + 1:-1] if '(' in k else k[6:]
                parts.append(t('rel.mismatch', mode=names.get(m, m), n=v['cellsMismatched']))
        L.append('- ' + t('rel.chk_ingame', v=version(), parts=t('rel.join').join(parts)))
    return '\n'.join(L) + '\n'


def create_placement(P, rep, removes):
    origin = ' '.join(map(str, rep['origin']))
    size = ' × '.join(map(str, rep['enclosingSize']))
    if P.lang == 'zh':
        lines = [
            '- 将 `.nbt` 文件放进实际游戏实例的 `schematics/` 文件夹（与该实例的 `mods/` 同级）。',
            '- 在 Create 蓝图桌中选择该文件，制作蓝图；手持蓝图调整位置、旋转和镜像后确认。',
            f'- 蓝图尺寸：{size}。原始设计包围盒最小角：`{origin}`；使用真实场地时，对齐此位置并保持原方向。',
            '- 生存模式可将已定位的蓝图放入蓝图炮，供应材料和火药；以蓝图炮生成的材料检查表为最终依据。',
            '- 默认选择不替换蓝图空气的模式。空气不需要材料，未设计的地形没有复制进蓝图。',
            '- 若使用替换空气的模式，整个包围盒中蓝图为空气的位置都可能被清除，不限于明确设计的清理格子。',
            '- 容器为空，机器配置、实体、超强力胶和多方块机器逻辑未导出；蓝图文件格式并不自动赋予机器功能。',
        ]
        if removes:
            lines.append(f'- 此设计明确需要清理 {removes} 个原有方块；建议按预览手动清理，再用不替换空气的模式施工。')
    else:
        lines = [
            '- Put the `.nbt` file in the actual game instance\'s `schematics/` folder, beside `mods/`.',
            '- Select the file at a Create Schematic Table, create a schematic, then hold it to position/rotate/mirror and confirm.',
            f'- Size: {size}. Original design bounding-box minimum: `{origin}`; align this corner without rotation for a real-site build.',
            '- In survival, put the positioned schematic into a Schematicannon and supply materials and gunpowder. Its checklist is authoritative.',
            '- Use a mode that does not replace schematic air. Untouched terrain is not copied into the blueprint.',
            '- Replacing air can clear every air position inside the entire bounding box, including positions never explicitly designed.',
            '- Containers are empty; machine configuration, entities, Super Glue and multiblock machine logic are not exported.',
        ]
        if removes:
            lines.append(f'- The design requires clearing {removes} existing blocks; clear these manually before printing without replacing air.')
    return lines


def clearing_count(P):
    """Design AIR cells that remove a non-air terrain block (trees, cut ground). Such builds must be pasted with
    Litematica's `All` mode: `With non-air` skips the schematic's air cells and leaves those blocks in place."""
    from .registry import AIR
    B = P.design()
    if B.site is None:
        return 0
    return sum(1 for p, st in B.cells.items() if st == AIR and B.world(p) != AIR)


def release(P):
    rd = P.release_dir
    rd.mkdir(exist_ok=True)
    rep = read_json(P.art / 'export-report.json') or read_json(P.art / 'litematic-report.json')
    if rep is None:
        raise SystemExit('run `mcb export` first')
    ver = read_json(P.art / 'verification.json')
    is_create = rep.get('format') == 'create'
    if is_create and (not ver or ver.get('status') != 'PASS'):
        raise SystemExit('Create release requires `mcb verify` to PASS after the latest export')
    ig = None if is_create else read_json(P.art / 'ingame' / 'ingame-report.json')
    label = (f"Create 蓝图（Java {rep['targetVersion']}，{rep.get('loader', 'Forge')}，Create {rep.get('createVersion', '6.0.8')}）"
             if P.lang == 'zh' else f"Create blueprint (Java {rep['targetVersion']}, {rep.get('loader', 'Forge')}, Create {rep.get('createVersion', '6.0.8')})")
    files = [(rep['file'], label if is_create else t('rel.f_litematic', v=rep.get('targetVersion', version())))]
    schem = (rd / rep['file']).with_suffix('.schem')
    if schem.exists():
        files.append((schem.name, t('rel.f_schem')))
    prev = P.art / 'preview' / 'index.html'
    if prev.exists():
        name = t('file.preview', name=P.name)
        shutil.copy2(prev, rd / name)
        files.append((name, t('rel.f_preview')))
    if (P.art / 'materials.csv').exists():
        name = t('file.materials')
        shutil.copy2(P.art / 'materials.csv', rd / name)
        files.append((name, t('rel.f_materials')))
    shots = sorted((P.art / 'ingame').glob('*.png')) if ig else sorted((P.art / 'shots').glob('*.png'))
    if shots:
        sd = rd / t('file.shots')
        if sd.exists():
            shutil.rmtree(sd)
        sd.mkdir()
        for s in shots:
            shutil.copy2(s, sd / s.name)
        files.append((sd.name + '/', t('rel.f_shots_ingame' if ig else 'rel.f_shots_preview', n=len(shots))))
    for extra in sorted(rd.glob('*.zip')) + sorted(rd.glob('*.mp4')):
        if extra.suffix == '.zip' and not extra.stem.endswith(('展示存档', 'showcase-world')):
            continue
        files.append((extra.name, t('rel.f_showcase') if extra.suffix == '.zip' else t('rel.f_video')))
    removes = clearing_count(P) if is_create or rep.get('mode', 'site') == 'site' else 0
    gname = t('file.guide')
    (rd / gname).write_text(guide(P, rep, ver, ig, files, removes), encoding='utf-8')
    if P.cfg.get('release', {}).get('zip', False):
        zp = rd.parent / t('file.bundle', id=P.id)
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in rd.rglob('*'):
                if f.is_file():
                    z.write(f, f.relative_to(rd))
        log('ZIP', zp)
    log('RELEASE', rd, [f for f, _ in files] + [gname])
    return rd
