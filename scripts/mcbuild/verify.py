"""Acceptance checks for the delivered schematic and the design behind it. Writes artifacts/verification.json.

File      own pure-Python bit unpacking of every region, header/metadata consistency, every palette state valid for
          the game version, no overlapping regions, tile entities = exactly the block-entity blocks (ids from facts).
Design    every design cell exported exactly once; copied cells equal the terrain (site mode) / air (portable).
Rules     connections, stair shapes, wall posts, door/bed/double-plant pairs, leaf decay, block support (torches,
          lanterns, plants on soil, carpets, ladders, doors, rails, signs …), gravity blocks, water/lava containment.
Site      design cells that would destroy player-placed blocks; floating parts not connected to the ground.
Light     block light >= 1 on every spawnable surface of the build (hostile mobs spawn at block light 0 since 1.18).
Walk      player BFS on half-block sub-columns using the game's collision boxes (stairs, slabs, carpets, fences,
          ladders/vines climbable, doors/gates/trapdoors openable): start -> every named target.
"""
from __future__ import annotations
import json
from collections import Counter, deque
from pathlib import Path
import numpy as np
from . import nbt
from .registry import (AIR, OFFSET, OPPOSITE, HORIZONTAL, facts, in_tag, from_nbt, make, is_stairs, is_pane_like, is_fence,
                       is_wall, is_fence_gate, is_door, is_trapdoor, is_bed, is_leaves, is_log, version)
from .rules import stair_shape, pane_connects, fence_connects, wall_state
from .terrain import kind, is_natural
from .util import meta, read_json, write_json, log


def _nb(p, d):
    o = OFFSET[d]
    return (p[0] + o[0], p[1] + o[1], p[2] + o[2])


# ------------------------------------------------------------------ independent decode
def _unpack_py(longs, n, bits):
    mask = (1 << bits) - 1
    words = [int(w) & 0xFFFFFFFFFFFFFFFF for w in longs]
    out = [0] * n
    for i in range(n):
        start = i * bits; wi = start >> 6; sh = start & 63
        v = words[wi] >> sh
        if sh + bits > 64:
            v |= words[wi + 1] << (64 - sh)
        out[i] = v & mask
    return out


def check_file(path, expect_origin=None, expect_dv=None):
    m = meta(version())
    root = nbt.load(path)
    assert int(root['Version']) == m.get('litematic_version', 7), ('Version', root['Version'])
    assert int(root['MinecraftDataVersion']) == (expect_dv or m['data_version']), ('DataVersion', root['MinecraftDataVersion'])
    md = root['Metadata']
    for k, t in [('Name', 8), ('Author', 8), ('Description', 8), ('RegionCount', 3), ('TotalVolume', 3), ('TotalBlocks', 3),
                 ('TimeCreated', 4), ('TimeModified', 4), ('EnclosingSize', 10)]:
        assert k in md and nbt.tag_of(md[k]) == t, ('metadata', k)
    regions = root['Regions']
    assert int(md['RegionCount']) == len(regions)
    from .util import data_json
    be_types = set(data_json(version(), 'registries.json')['minecraft:block_entity_type']['entries'])
    world, tiles = {}, {}
    tot_blocks = tot_vol = 0
    maxc = [-10 ** 9] * 3
    states = set()
    for name, r in regions.items():
        pos = [int(r['Position'][k]) for k in 'xyz']; size = [int(r['Size'][k]) for k in 'xyz']
        assert all(s > 0 for s in size) and all(p >= 0 for p in pos), ('region box', name, pos, size)
        pal = []
        for e in r['BlockStatePalette']:
            props = {k: str(v) for k, v in e.get('Properties', {}).items()}
            st = from_nbt({'Name': str(e['Name']), 'Properties': props})        # raises on invalid states
            assert st.props == {**st.props, **props} and len(props) == len(st.props), ('partial state', st.key())
            pal.append(st); states.add(st)
        assert pal[0] == AIR, 'palette[0] must be air'
        bits = max(2, (len(pal) - 1).bit_length())
        vol = size[0] * size[1] * size[2]
        longs = r['BlockStates']
        assert len(longs) == (vol * bits + 63) // 64, ('BlockStates length', name)
        idx = _unpack_py(longs, vol, bits)
        assert max(idx) < len(pal)
        for y in range(size[1]):
            for z in range(size[2]):
                for x in range(size[0]):
                    p = (pos[0] + x, pos[1] + y, pos[2] + z)
                    assert p not in world, ('overlapping regions', name, p)
                    st = pal[idx[(y * size[2] + z) * size[0] + x]]
                    world[p] = st
                    tot_blocks += st != AIR
                    for k in range(3):
                        maxc[k] = max(maxc[k], p[k] + 1)
        tot_vol += vol
        for te in r['TileEntities']:
            p = (pos[0] + int(te['x']), pos[1] + int(te['y']), pos[2] + int(te['z']))
            assert str(te['id']) in be_types, ('unknown block entity', te['id'])
            assert p not in tiles, ('duplicate tile entity', p)
            tiles[p] = str(te['id'])
        for k in ('Entities', 'PendingBlockTicks', 'PendingFluidTicks'):
            assert k in r
    assert tot_blocks == int(md['TotalBlocks']) and tot_vol == int(md['TotalVolume']), 'metadata totals'
    assert [int(md['EnclosingSize'][k]) for k in 'xyz'] == maxc, ('EnclosingSize', maxc)
    for p, st in world.items():
        want = facts(st).be if st != AIR else None
        got = tiles.get(p)
        assert want == got, ('tile entity mismatch', p, st.key(), want, got)
    return world, {'regions': len(regions), 'cellsDecoded': len(world), 'nonAir': tot_blocks, 'paletteStatesValidated': len(states),
                   'tileEntities': len(tiles), 'enclosingSize': maxc}


# ------------------------------------------------------------------ support rules
SOIL_DEFAULT = ('minecraft:dirt',)


def support_problem(st, at, p):
    """Return a short reason if `st` at p could not stay there in vanilla, else None."""
    f = facts(st)
    s = st.short
    below = at(_nb(p, 'down'))
    fb = facts(below)
    cls = f.classes
    if 'FallingBlock' in cls or 'ColoredFallingBlock' in cls or 'ConcretePowderBlock' in cls:
        if below == AIR or facts(below).replaceable or kind(below) in ('water', 'lava'):
            return 'falls'
    if is_door(st):
        if st.get('half') == 'lower' and not fb.face_full('up'):
            return 'door needs a solid block below'
        return None
    if 'TallPlantBlock' in cls and st.get('half') == 'upper':
        return None
    if s in ('cactus',):
        return None if below.short in ('cactus',) or in_tag(below, 'minecraft:sand') else 'cactus needs sand'
    if s == 'sugar_cane':
        if below.short == 'sugar_cane':
            return None
        if not (in_tag(below, 'minecraft:dirt') or in_tag(below, 'minecraft:sand')):
            return 'sugar cane soil'
        wet = any(kind(at(_nb(_nb(p, 'down'), d))) == 'water' or at(_nb(_nb(p, 'down'), d)).get('waterlogged') == 'true' for d in HORIZONTAL)
        return None if wet else 'sugar cane needs water next to its soil'
    if s == 'bamboo' or s == 'bamboo_sapling':
        return None if below.short == 'bamboo' or in_tag(below, 'minecraft:bamboo_plantable_on') else 'bamboo soil'
    if s in ('dead_bush', 'short_dry_grass', 'tall_dry_grass'):
        return None if (in_tag(below, 'minecraft:sand') or in_tag(below, 'minecraft:dirt') or in_tag(below, 'minecraft:terracotta')) else 'dry plant soil'
    if s in ('azalea', 'flowering_azalea'):
        return None if in_tag(below, 'minecraft:azalea_grows_on') else 'azalea soil'
    if s in ('brown_mushroom', 'red_mushroom'):
        return None if fb.solid_block else 'mushroom needs a solid block'
    if s == 'lily_pad':
        return None if kind(below) == 'water' else 'lily pad needs water'
    if s in ('seagrass', 'tall_seagrass', 'kelp', 'kelp_plant', 'sea_pickle') or 'CoralBlock' in cls or 'CoralParentBlock' in cls \
            or 'CoralFanBlock' in cls or 'DeadCoralBlock' in cls or 'DeadCoralParentBlock' in cls:
        if s in ('kelp', 'kelp_plant') and below.short in ('kelp', 'kelp_plant'):
            return None
        if s == 'tall_seagrass' and st.get('half') == 'upper':
            return None
        if 'WallFan' in ''.join(cls) or 'WallFanBlock' in cls:
            return None
        return None if fb.face_center('up') or fb.face_full('up') else 'needs a solid floor'
    if s == 'cocoa':
        return None if in_tag(at(_nb(p, st.get('facing'))), 'minecraft:jungle_logs') else 'cocoa needs a jungle log'
    if 'PlantBlock' in cls and 'TallSeagrassBlock' not in cls:
        if s in ('leaf_litter',):
            return None if fb.face_full('up') else 'needs a full top face'
        if 'TallPlantBlock' in cls or 'FlowerbedBlock' in cls or 'FlowerBlock' in cls or 'ShortPlantBlock' in cls \
                or 'SaplingBlock' in cls or 'FernBlock' in cls or 'PlantBlock' in cls:
            if 'CropBlock' in cls or 'StemBlock' in cls:
                return None if below.short == 'farmland' else 'crop needs farmland'
            if 'NetherFungusBlock' in cls or 'FungusBlock' in cls or 'RootsBlock' in cls:
                return None
            if 'LilyPadBlock' in cls or 'PropaguleBlock' in cls:
                return None
            return None if (in_tag(below, 'minecraft:dirt') or below.short == 'farmland') else f'plant soil ({below.short})'
    if s in ('torch', 'soul_torch', 'redstone_torch', 'copper_torch'):
        return None if fb.face_center('up') else 'torch needs support below'
    if 'WallTorchBlock' in cls or 'WallRedstoneTorchBlock' in cls:
        back = at(_nb(p, OPPOSITE[st.get('facing')]))
        return None if facts(back).face_full(st.get('facing')) else 'wall torch needs a solid wall'
    if 'LanternBlock' in cls:
        if st.get('hanging') == 'true':
            return None if facts(at(_nb(p, 'up'))).face_center('down') else 'hanging lantern needs support above'
        return None if fb.face_center('up') else 'lantern needs support below'
    if 'CandleBlock' in cls or s == 'sea_pickle':
        return None if fb.face_center('up') else 'needs support below'
    if 'CarpetBlock' in cls or s in ('moss_carpet', 'pale_moss_carpet'):
        return None if below != AIR else 'carpet over air'
    if 'LadderBlock' in cls:
        back = at(_nb(p, OPPOSITE[st.get('facing')]))
        return None if facts(back).face_full(st.get('facing')) else 'ladder needs a wall behind'
    if 'AbstractRailBlock' in cls or 'RailBlock' in cls or 'PoweredRailBlock' in cls or 'DetectorRailBlock' in cls:
        return None if fb.face_rigid('up') else 'rail support'
    if 'AbstractPressurePlateBlock' in cls or 'PressurePlateBlock' in cls or 'WeightedPressurePlateBlock' in cls:
        return None if (fb.face_rigid('up') or fb.face_center('up')) else 'pressure plate support'
    if ('ButtonBlock' in cls or 'LeverBlock' in cls) and st.has('face'):
        face = st.get('face')
        d = 'down' if face == 'floor' else 'up' if face == 'ceiling' else OPPOSITE[st.get('facing')]
        att = at(_nb(p, d))
        return None if facts(att).face_full(OPPOSITE[d]) else 'button/lever needs a full face'
    if 'SignBlock' in cls or 'BannerBlock' in cls:
        return None if facts(below).solid else 'sign/banner needs a solid block below'
    if 'WallSignBlock' in cls or 'WallBannerBlock' in cls:
        return None if facts(at(_nb(p, OPPOSITE[st.get('facing')]))).solid else 'wall sign/banner needs a solid wall'
    return None


# ------------------------------------------------------------------ walkability
class Walker:
    """BFS over half-block sub-columns. Standing heights = tops of collision intervals with >= 1.8 headroom."""

    def __init__(self, at, box, swim=False, max_step=0.6, max_drop=3.0):
        self.at, self.box = at, box
        self.swim, self.max_step, self.max_drop = swim, max_step, max_drop
        self._cols = {}
        x0, y0, z0, x1, y1, z1 = box
        self.y0, self.y1 = y0, y1

    def _cell_boxes(self, st):
        f = facts(st)
        if is_door(st) or is_fence_gate(st) or is_trapdoor(st) or in_tag(st, 'minecraft:climbable'):
            return []
        return f.boxes

    def column(self, sx, sz):
        key = (sx, sz)
        if key in self._cols:
            return self._cols[key]
        x, i = divmod(sx, 2); z, j = divmod(sz, 2)
        u0, u1, v0, v1 = i * .5, i * .5 + .5, j * .5, j * .5 + .5
        iv, climb, water = [], set(), set()
        for y in range(self.y0, self.y1):
            st = self.at((x, y, z))
            if st == AIR:
                continue
            if in_tag(st, 'minecraft:climbable'):
                climb.add(y)
            if facts(st).water and not facts(st).boxes:
                water.add(y)
            for b in self._cell_boxes(st):
                if b[3] - .01 > u0 and b[0] + .01 < u1 and b[5] - .01 > v0 and b[2] + .01 < v1:
                    iv.append((y + b[1], y + b[4]))
        iv.sort()
        merged = []
        for a, b in iv:
            if merged and a <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        stands = []
        for k, (a, b) in enumerate(merged):
            ceil = merged[k + 1][0] if k + 1 < len(merged) else self.y1 + 4
            if ceil - b >= 1.8 - 1e-6 and not (int(b) in water and not self.swim):
                stands.append((round(b, 4), ceil))
        for y in sorted(climb | (water if self.swim else set())):
            for h in (y, y + 1):
                ceil = min([a for a, _ in merged if a >= h - 1e-6], default=self.y1 + 4)
                if ceil - h >= 1.8 - 1e-6 and all(abs(h - s) > 1e-6 for s, _ in stands):
                    stands.append((float(h), ceil))
        res = {'stands': sorted(stands), 'climb': climb, 'water': water}
        self._cols[key] = res
        return res

    def nodes_at_cell(self, x, y, z):
        out = []
        for i in (0, 1):
            for j in (0, 1):
                sx, sz = 2 * x + i, 2 * z + j
                for h, _ in self.column(sx, sz)['stands']:
                    if y - 0.55 <= h < y + 1.0:
                        out.append((sx, sz, h))
        return out

    def bfs(self, start_nodes):
        x0, y0, z0, x1, y1, z1 = self.box
        seen = set(start_nodes)
        q = deque(start_nodes)
        while q:
            sx, sz, h = q.popleft()
            col = self.column(sx, sz)
            ceil_here = next((c for s, c in col['stands'] if abs(s - h) < 1e-6), h + 2)
            cell_y = int(np.floor(h + 1e-6))
            # vertical moves on ladders / vines (and in water when swimming)
            cx, cz = sx // 2, sz // 2
            for s, c in col['stands']:
                if abs(s - h) <= 1.0 + 1e-6 and abs(s - h) > 1e-6 and (
                        (int(np.floor(min(s, h) + 1e-6)) in col['climb']) or (self.swim and int(np.floor(min(s, h))) in col['water'])):
                    n = (sx, sz, s)
                    if n not in seen:
                        seen.add(n); q.append(n)
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, nz = sx + dx, sz + dz
                if not (2 * x0 <= nx < 2 * x1 and 2 * z0 <= nz < 2 * z1):
                    continue
                for s, c in self.column(nx, nz)['stands']:
                    if s - h > self.max_step + 1e-6 or h - s > self.max_drop + 1e-6:
                        continue
                    if max(h, s) + 1.8 > min(ceil_here, c) + 1e-6:
                        continue
                    n = (nx, nz, s)
                    if n not in seen:
                        seen.add(n); q.append(n)
        return seen


# ------------------------------------------------------------------ main
def verify(project, strict=True):
    P = project
    build = P.design()
    site = build.site
    cfg = P.cfg.get('verify', {})
    rep = read_json(P.art / 'export-report.json') or read_json(P.art / 'litematic-report.json')
    if rep is None:
        raise SystemExit('run `mcb export` first')
    lit = P.release_dir / rep['file']
    R = {'errors': [], 'warnings': []}

    # ---- file
    if rep.get('format') == 'create':
        from .create import check_create_file
        world_rel, finfo = check_create_file(lit, expect_dv=rep.get('dataVersion'))
        assert len(world_rel) == len(build.cells), 'Create blueprint cell count differs from design'
    else:
        world_rel, finfo = check_file(lit, expect_dv=rep.get('dataVersion'))
    ox, oy, oz = rep['origin']
    W = {(x + ox, y + oy, z + oz): st for (x, y, z), st in world_rel.items()}
    R['file'] = finfo
    log('FILE_OK', finfo)

    # ---- design equality
    missing = [(p, st.key(), W.get(p) and W.get(p).key()) for p, st in build.cells.items() if W.get(p) != st]
    if missing:
        R['errors'].append({'check': 'design cells differ in the file', 'count': len(missing), 'examples': missing[:10]})
    copied = 0
    for p, st in W.items():
        if p not in build.cells:
            want = (site.world(*p) if (site is not None and rep.get('mode', 'site') == 'site') else AIR)
            if st != want:
                R['errors'].append({'check': 'copied cell differs from terrain', 'pos': p, 'got': st.key(), 'want': want.key()})
                break
            copied += st != AIR
    R['file'].update({'designCells': len(build.cells), 'copiedWorldBlocks': copied, 'origin': [ox, oy, oz]})

    def at(p):
        """Final world after placing the design (the file's own cells were already compared above)."""
        st = build.cells.get(p)
        if st is not None:
            return st
        return site.world(*p) if site is not None else AIR

    blocks = {p: st for p, st in build.cells.items() if st != AIR}

    # ---- vanilla rules + support
    problems = []
    for p, st in blocks.items():
        if is_pane_like(st) or is_fence(st):
            fn = pane_connects if is_pane_like(st) else fence_connects
            for d in HORIZONTAL:
                if (st.get(d) == 'true') != bool(fn(st, at(_nb(p, d)), d)):
                    problems.append(('connection', p, st.short, d))
        if is_wall(st) and wall_state(at, p, st) != st:
            problems.append(('wall shape', p))
        if is_stairs(st) and st.get('shape') != stair_shape(at, p, st):
            problems.append(('stair shape', p, st.get('shape'), stair_shape(at, p, st)))
        if is_door(st):
            o = at(_nb(p, 'up' if st.get('half') == 'lower' else 'down'))
            if o.short != st.short or o.get('facing') != st.get('facing') or o.get('hinge') != st.get('hinge') or o.get('half') == st.get('half'):
                problems.append(('door pair', p))
        elif is_bed(st):
            d = st.get('facing') if st.get('part') == 'foot' else OPPOSITE[st.get('facing')]
            o = at(_nb(p, d))
            if o.short != st.short or o.get('part') == st.get('part') or o.get('facing') != st.get('facing'):
                problems.append(('bed pair', p))
        elif st.get('half') in ('lower', 'upper') and not is_trapdoor(st) and not is_stairs(st):
            o = at(_nb(p, 'up' if st.get('half') == 'lower' else 'down'))
            if o.short != st.short or o.get('half') == st.get('half'):
                problems.append(('double block pair', p, st.short))
        if is_leaves(st) and st.get('persistent') == 'false' and st.get('distance') == '7':
            problems.append(('leaves will decay (no log within 6)', p))
        why = support_problem(st, at, p)
        if why:
            problems.append(('support', p, st.short, why))
        if st.short in ('water', 'lava'):
            for d in ('north', 'south', 'east', 'west', 'down'):
                if at(_nb(p, d)) == AIR:
                    problems.append((f'{st.short} leaks', p, d))
    if problems:
        kinds = Counter(pr[0] if pr[0] != 'support' else 'support: ' + pr[3] for pr in problems)
        R['errors'].append({'check': 'vanilla rules / support', 'count': len(problems), 'kinds': dict(kinds), 'examples': problems[:25]})
    R['rules'] = {'buildBlocksChecked': len(blocks), 'problems': len(problems)}
    log('RULES', R['rules'])

    # ---- target game version: every block must exist there
    from .compat import missing_blocks, is_older
    target = rep.get('targetVersion')
    if is_older(target, version()):
        miss = missing_blocks({st for st in build.cells.values() if st != AIR}, target, version())
        R['targetVersion'] = {'version': target, 'dataVersion': rep.get('dataVersion'), 'renamed': rep.get('renamed'), 'missing': miss}
        if miss:
            R['errors'].append({'check': f'blocks that do not exist in Minecraft {target} (they would paste as air) - replace them',
                                'count': len(miss), 'blocks': [f'{b} (since {v})' for b, v in miss]})

    # ---- site: destroyed player blocks, floating parts
    if site is not None:
        destroyed = Counter()
        for p, st in build.cells.items():
            t = site.world(*p)
            if t != AIR and not is_natural(t) and t != st:
                destroyed[t.short] += 1
        if destroyed:
            R['warnings'].append({'check': 'design replaces player-placed blocks in the world', 'count': sum(destroyed.values()),
                                  'blocks': dict(destroyed.most_common(20))})
        R['site'] = {'replacedPlayerBlocks': sum(destroyed.values())}
    comp = _components(blocks)
    floating = []
    for c in comp:
        anchored = False
        for p in c:
            for d in OFFSET:
                q = _nb(p, d)
                if q in blocks:
                    continue
                t = at(q)
                if t != AIR and q not in build.cells and (kind(t) in ('solid', 'light') or
                                                          (kind(t) == 'water' and blocks[p].short in ('lily_pad', 'frogspawn'))):
                    anchored = True; break
            if anchored:
                break
        if not anchored:
            xs, ys, zs = zip(*c)
            floating.append({'cells': len(c), 'min': [min(xs), min(ys), min(zs)], 'max': [max(xs), max(ys), max(zs)]})
    if floating and not cfg.get('allow_floating', False):
        R['warnings'].append({'check': 'parts not connected to the ground (floating)', 'parts': floating[:10]})
    R['structure'] = {'components': len(comp), 'floating': len(floating)}

    # ---- light / spawn-proofing
    from .light import block_light
    (bx0, by0, bz0), (bx1, by1, bz1) = build.bbox(include_air=False) or build.bbox()
    m = 16
    box = (bx0 - m, by0 - 4, bz0 - m, bx1 + m + 1, by1 + 6, bz1 + m + 1)
    grid, states, origin = _grid(at, box)
    L = block_light(grid, states)
    scope = cfg.get('spawnproof_scope', 'build')
    surfaces, dark = [], []
    cand = blocks.keys() if scope == 'build' else [(x, y, z) for x in range(bx0, bx1 + 1) for z in range(bz0, bz1 + 1) for y in range(by0, by1 + 1)]
    for p in cand:
        st = at(p)
        if st == AIR or not facts(st).spawnable:
            continue
        a1, a2 = _nb(p, 'up'), _nb(_nb(p, 'up'), 'up')
        if not (_spawn_clear(at(a1)) and _spawn_clear(at(a2), head=True)):
            continue
        lv = int(L[a1[1] - box[1], a1[2] - box[2], a1[0] - box[0]])
        surfaces.append([p[0], p[1], p[2], lv])
        if lv < 1:
            dark.append(p)
    R['spawnProofing'] = {'scope': scope, 'spawnableSurfaces': len(surfaces), 'darkSurfaces': len(dark), 'dark': dark[:30]}
    if dark and cfg.get('spawnproof', True):
        (R['errors'] if strict and cfg.get('spawnproof_strict', True) else R['warnings']).append(
            {'check': 'dark spawnable surfaces (block light 0)', 'count': len(dark), 'examples': dark[:15]})
    log('LIGHT', {k: v for k, v in R['spawnProofing'].items() if k != 'dark'})

    # ---- walk
    walk = cfg.get('walk_targets') or {}
    reach_cells = []
    if cfg.get('walk_start'):
        wbox = (bx0 - 12, by0 - 6, bz0 - 12, bx1 + 13, by1 + 6, bz1 + 13)
        Wk = Walker(at, wbox, swim=cfg.get('walk_swim', False), max_step=cfg.get('max_step', 0.6), max_drop=cfg.get('max_drop', 3.0))
        s = cfg['walk_start']
        start = Wk.nodes_at_cell(*s)
        if not start:
            R['errors'].append({'check': 'walk start is not a standable cell', 'start': s})
        else:
            seen = Wk.bfs(start)
            cells = {(sx // 2, int(np.floor(h + 1e-6)), sz // 2) for sx, sz, h in seen}
            res = {}
            for name, t in walk.items():
                res[name] = any((sx // 2, sz // 2) == (t[0], t[2]) and t[1] - 0.55 <= h < t[1] + 1.0 for sx, sz, h in seen)
            R['walk'] = {'start': s, 'reachableCells': len(cells), 'targets': res}
            bad = [k for k, v in res.items() if not v]
            if bad:
                R['errors'].append({'check': 'unreachable walk targets', 'targets': bad})
            reach_cells = sorted(cells)
            log('WALK', R['walk'])
    write_json(P.art / 'verify-maps.json', {'surfaces': surfaces, 'reach': [list(c) for c in reach_cells],
                                            'targets': {k: list(v) for k, v in walk.items()}}, indent=None)
    R['status'] = 'PASS' if not R['errors'] else 'FAIL'
    write_json(P.art / 'verification.json', R)
    log('VERIFY', R['status'], f"errors={len(R['errors'])} warnings={len(R['warnings'])}")
    for e in R['errors']:
        log('  ERROR', json.dumps(e, ensure_ascii=False, default=str)[:400])
    for w in R['warnings']:
        log('  WARN ', json.dumps(w, ensure_ascii=False, default=str)[:400])
    return R


def _spawn_clear(st, head=False):
    if st == AIR:
        return True
    f = facts(st)
    if f.boxes or f.water or f.lava:
        return False
    if in_tag(st, 'minecraft:prevent_mob_spawning_inside'):
        return False
    return True


def _grid(at, box):
    x0, y0, z0, x1, y1, z1 = box
    states, index = [AIR], {AIR: 0}
    g = np.zeros((y1 - y0, z1 - z0, x1 - x0), np.int32)
    for y in range(y0, y1):
        for z in range(z0, z1):
            for x in range(x0, x1):
                st = at((x, y, z))
                if st == AIR:
                    continue
                i = index.get(st)
                if i is None:
                    i = index[st] = len(states); states.append(st)
                g[y - y0, z - z0, x - x0] = i
    return g, states, (x0, y0, z0)


N26 = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dy, dz) != (0, 0, 0)]


def _components(blocks):
    """26-connected components (blocks touching by an edge or corner count as connected, e.g. leaning trunks)."""
    left = set(blocks)
    out = []
    while left:
        s = left.pop()
        comp = [s]; q = [s]
        while q:
            p = q.pop()
            for dx, dy, dz in N26:
                n = (p[0] + dx, p[1] + dy, p[2] + dz)
                if n in left:
                    left.remove(n); comp.append(n); q.append(n)
        out.append(comp)
    return out
