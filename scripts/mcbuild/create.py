"""Create blueprints: gzip-compressed Java StructureTemplate NBT, not Sponge NBT.

Only design cells are exported. Untouched terrain is not a construction material;
unspecified positions inside the bounding box are air in Create's schematic level.
"""
from __future__ import annotations
import math
from pathlib import Path
from . import nbt
from .nbt import Compound as C, List as L, Int as I, String as S
from .registry import AIR, facts, from_nbt, version
from .compat import DATA_VERSIONS, missing_blocks, write_renames


def export_create(build, path, target='1.20.1', name='build', create_version='6.0.8', loader='Forge'):
    if target not in DATA_VERSIONS:
        raise SystemExit(f'unknown Create target_version {target!r}; choose a supported Java release')
    if not build.cells:
        raise SystemExit('the design is empty')
    missing = missing_blocks(set(build.cells.values()), target, version())
    if missing:
        raise SystemExit(f'blocks unavailable in Minecraft {target}: ' + ', '.join(f'{b} (since {v})' for b, v in missing))
    rename = write_renames(target, version())
    lo, hi = build.bbox()
    size = [hi[k] - lo[k] + 1 for k in range(3)]
    palette, index = [AIR], {AIR: 0}
    blocks, tile_count = [], 0
    from .schematic import nbt_state
    for p, st in sorted(build.cells.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        if st not in index:
            index[st] = len(palette)
            palette.append(st)
        pos = [p[k] - lo[k] for k in range(3)]
        entry = C({'pos': L([I(v) for v in pos], 3), 'state': I(index[st])})
        bid = facts(st).be if st != AIR else None
        if bid:
            # Empty inventories/default block-entity configuration; no 1.20.5+ components.
            entry['nbt'] = C({'id': S(bid), **{k: I(v) for k, v in zip('xyz', pos)}})
            tile_count += 1
        blocks.append(entry)
    root = C({'DataVersion': I(DATA_VERSIONS[target]), 'size': L([I(v) for v in size], 3),
              'palette': L([nbt_state(st, rename) for st in palette], 10),
              'blocks': L(blocks, 10), 'entities': L([], 10)})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nbt.save(path, root, compress='gzip')
    nonair = sum(st != AIR for st in build.cells.values())
    real_site = build.site is not None and build.site.source.get('kind') in ('anvil', 'voxy', 'schematic')
    return {'file': path.name, 'format': 'create', 'mode': 'portable', 'siteAligned': real_site,
            'origin': list(lo), 'max': list(hi), 'enclosingSize': size, 'totalBlocks': nonair,
            'totalVolume': math.prod(size), 'designCells': len(blocks), 'dataVersion': DATA_VERSIONS[target],
            'targetVersion': target, 'createVersion': create_version, 'loader': loader, 'renamed': rename,
            'regions': [{'name': name, 'min': list(lo), 'size': size, 'blocks': nonair,
                         'tileEntities': tile_count, 'copiedFromWorld': {}}]}


def check_create_file(path, expect_dv=None):
    """Decode the structure independently of the exporter and validate typed tags/cells/entities."""
    path = Path(path)
    with path.open('rb') as stream:
        assert stream.read(2) == b'\x1f\x8b', 'Create blueprint must be gzip-compressed NBT'
    root = nbt.load(path)
    assert nbt.tag_of(root['DataVersion']) == 3, 'DataVersion must be TAG_Int'
    if expect_dv is not None:
        assert int(root['DataVersion']) == expect_dv, ('DataVersion', root['DataVersion'], expect_dv)
    size = root['size']
    assert nbt.tag_of(size) == 9 and size.elem == 3 and len(size) == 3, 'size must be List[Int] of length 3'
    size = list(map(int, size))
    assert all(v > 0 for v in size), ('invalid size', size)
    for key in ('palette', 'blocks', 'entities'):
        assert nbt.tag_of(root[key]) == 9 and root[key].elem == 10, f'{key} must be List[Compound]'
    assert not root['entities'], 'this exporter does not generate entities or Create glue'
    palette = []
    for entry in root['palette']:
        assert nbt.tag_of(entry['Name']) == 8, 'palette Name must be TAG_String'
        props = {str(k): str(v) for k, v in entry.get('Properties', {}).items()}
        assert all(nbt.tag_of(v) == 8 for v in entry.get('Properties', {}).values()), 'block properties must be strings'
        st = from_nbt({'Name': str(entry['Name']), 'Properties': props})
        assert st.props == {**st.props, **props} and len(props) == len(st.props), ('partial/invalid state', st.key())
        palette.append(st)
    assert palette and palette[0] == AIR, 'palette[0] must be air'
    world, tiles = {}, 0
    for block in root['blocks']:
        pos = block['pos']
        assert nbt.tag_of(pos) == 9 and pos.elem == 3 and len(pos) == 3, 'pos must be List[Int] of length 3'
        p = tuple(map(int, pos))
        assert all(0 <= p[k] < size[k] for k in range(3)), ('out-of-bounds position', p, size)
        assert p not in world, ('duplicate position', p)
        assert nbt.tag_of(block['state']) == 3, 'state must be TAG_Int'
        i = int(block['state'])
        assert 0 <= i < len(palette), ('invalid palette index', p, i)
        st = palette[i]
        world[p] = st
        wanted = facts(st).be if st != AIR else None
        data = block.get('nbt')
        assert bool(data) == bool(wanted), ('block entity presence mismatch', p, st.key())
        if wanted:
            assert nbt.tag_of(data) == 10 and str(data['id']) == wanted, ('block entity id mismatch', p)
            assert tuple(int(data[k]) for k in 'xyz') == p, ('block entity position mismatch', p)
            assert all(nbt.tag_of(data[k]) == 3 for k in 'xyz') and nbt.tag_of(data['id']) == 8
            tiles += 1
    assert world, 'empty structure'
    assert [max(p[k] for p in world) + 1 for k in range(3)] == size, 'size differs from design extent'
    return world, {'format': 'create', 'regions': 1, 'cellsDecoded': len(world),
                   'nonAir': sum(st != AIR for st in world.values()), 'paletteStatesValidated': len(palette),
                   'tileEntities': tiles, 'enclosingSize': size, 'dataVersion': int(root['DataVersion'])}
