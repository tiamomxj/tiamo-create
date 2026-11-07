"""Offline 3D preview page (single HTML): vanilla block models/textures from the client jar (or, without one, block
shapes in map colours), game-accurate light, the build on its real surroundings, automatic camera presets, materials,
stats, optional screenshot comparison and in-game gallery - in the project language. Headless screenshots of the page
go through browser.py (Playwright).
"""
from __future__ import annotations
import base64, gzip, io, json, math, os, subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from .registry import AIR, facts, version, zh_name
from .util import KIT, HOME, client_jar, log, read_json, write_json
from .i18n import t, direction, lang

WEB = KIT / 'web'
DIRS = ['east', 'west', 'up', 'down', 'south', 'north']
TRANSLUCENT_SUFFIX = ('_stained_glass', '_stained_glass_pane')
NO_TINT = {'cherry_leaves', 'azalea_leaves', 'flowering_azalea_leaves', 'pale_oak_leaves'}   # vanilla BlockColors leaves them untinted


# ------------------------------------------------------------------ boxes & views
def scene_box(P, B):
    pc = P.cfg.get('preview', {})
    if pc.get('box'):
        return tuple(pc['box'])
    (x0, y0, z0), (x1, y1, z1) = B.bbox()
    m = pc.get('context', 40)
    box = [x0 - m, y0 - pc.get('below', 14), z0 - m, x1 + m + 1, y1 + pc.get('above', 18), z1 + m + 1]
    if B.site is not None:
        sx0, sy0, sz0, sx1, sy1, sz1 = B.site.box
        clamp = lambda b: [max(b[0], sx0), max(b[1], sy0), max(b[2], sz0), min(b[3], sx1), min(b[4], sy1), min(b[5], sz1)]
        box = clamp(box)
        grow = pc.get('grow_to_neighbours', 64)
        if grow and B.site.source.get('kind') not in ('flat', 'none'):
            # show neighbouring player builds whole instead of slicing them at the box edge
            from .analyze import find_builds
            for b in find_builds(B.site, (box[0] - grow, box[2] - grow, box[3] + grow, box[5] + grow), min_blocks=40):
                if b['underground']:
                    continue
                inside = b['x1'] >= box[0] and b['x0'] < box[3] and b['z1'] >= box[2] and b['z0'] < box[5]
                if inside and b['x0'] >= box[0] - grow and b['x1'] < box[3] + grow and b['z0'] >= box[2] - grow and b['z1'] < box[5] + grow:
                    box = [min(box[0], b['x0'] - 2), min(box[1], b['y0'] - 2), min(box[2], b['z0'] - 2),
                           max(box[3], b['x1'] + 3), max(box[4], b['y1'] + 4), max(box[5], b['z1'] + 3)]
            box = clamp(box)
    return tuple(int(v) for v in box)


def floor_levels(B, maxn=3):
    """Y levels with lots of walkable floor (design blocks with two free cells above) — for cut-away views."""
    cnt = {}
    for (x, y, z), st in B.cells.items():
        if st == AIR or facts(st).top != 1.0:
            continue
        if B.getw((x, y + 1, z)) == AIR or not facts(B.getw((x, y + 1, z))).boxes:
            if not facts(B.getw((x, y + 2, z))).boxes:
                cnt[y] = cnt.get(y, 0) + 1
    if not cnt:
        return []
    top = max(cnt.values())
    levels = sorted(y for y, c in cnt.items() if c >= max(6, 0.18 * top))
    out = []
    for y in levels:
        if not out or y - out[-1] >= 3:
            out.append(y)
    return out[:maxn]


def _obstruction(B, a, b, samples=48):
    """How much terrain (not the design) blocks the sight line a -> b: solid 1, plants/leaves 0.4 per sample."""
    if B.site is None:
        return 0.0
    from .terrain import kind
    tot = 0.0
    for k in range(1, samples):
        t = k / samples
        p = (int(math.floor(a[0] + (b[0] - a[0]) * t)), int(math.floor(a[1] + (b[1] - a[1]) * t)), int(math.floor(a[2] + (b[2] - a[2]) * t)))
        if p in B.cells:
            continue
        st = B.site.world(*p)
        k_ = kind(st)
        if k_ in ('solid', 'light'):
            tot += 0.4 if facts(st).is_a('LeavesBlock') else 1.0
        elif k_ == 'plant':
            tot += 0.4
    return tot


def _sight(B, pos, targets):
    return sum(_obstruction(B, pos, t) for t in targets)


def _natural_ground(B, x, z):
    """Column whose top block is natural ground (not a player build, tree or water) -> its y, else None."""
    if B.site is None:
        return 0
    from .terrain import is_natural, is_vegetation
    g = B.site.ground_top(x, z)
    st = B.site.world(x, g, z)
    if not is_natural(st) or is_vegetation(st) or B.site.is_water(x, g + 1, z):
        return None
    return g


def _clutter(B, pos, radius=12, step=3):
    """Share of the ground under a camera covered by other player builds (they would fill the foreground)."""
    if B.site is None:
        return 0.0
    from .terrain import is_natural
    n = hit = 0
    for dx in range(-radius, radius + 1, step):
        for dz in range(-radius, radius + 1, step):
            x, z = int(math.floor(pos[0] + dx)), int(math.floor(pos[2] + dz))
            if not B.site.contains(x, B.site.Y0, z):
                continue
            n += 1
            g = B.site.ground_top(x, z)
            hit += not is_natural(B.site.world(x, g, z))
    return hit / n if n else 0.0


def auto_views(P, B):
    pc = P.cfg.get('preview', {})
    (x0, y0, z0), (x1, y1, z1) = B.bbox(include_air=False) or B.bbox()
    cx, cy, cz = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2, (z0 + z1 + 1) / 2
    s = max(x1 - x0 + 1, z1 - z0 + 1, (y1 - y0 + 1) * 1.4)
    d = s * 1.05 + 14
    front = pc.get('front', 'south')
    fv = {'south': (0, 1), 'north': (0, -1), 'east': (1, 0), 'west': (-1, 0)}[front]
    corners = {'se': (1, 1, direction('se')), 'sw': (-1, 1, direction('sw')), 'nw': (-1, -1, direction('nw')), 'ne': (1, -1, direction('ne'))}
    tgt = [round(cx, 2), round(y0 + (y1 - y0) * 0.35, 2), round(cz, 2)]
    probes = [(cx, y0 + (y1 - y0) * f, cz) for f in (0.15, 0.5, 0.9)]
    cpos = {k: [round(cx + sx * d * 0.72, 2), round(y1 + d * 0.42, 2), round(cz + sz * d * 0.72, 2)] for k, (sx, sz, _) in corners.items()}
    # front-facing corners first, but a corner whose sight line is blocked (neighbour's roof, hill, trees) drops back
    order = sorted(corners, key=lambda k: (round(_sight(B, cpos[k], probes) / 3 + _clutter(B, cpos[k]) * 4),
                                           -(corners[k][0] * fv[0] + corners[k][1] * fv[1])))
    views = []
    for i, k in enumerate(order):
        sx, sz, zh = corners[k]
        views.append({'name': 'overview' if i == 0 else k, 'label': t('view.overview') if i == 0 else t('view.corner', d=zh), 'pos': cpos[k],
                      'target': tgt, 'fov': 50})
    ftgt = [round(cx, 2), round(y0 + (y1 - y0) * 0.4, 2), round(cz, 2)]
    best = None
    for rf in (1.0, 0.8, 1.25):
        for da in (0, 10, -10, 20, -20):
            a = math.atan2(fv[1], fv[0]) + math.radians(da)
            fx, fz = cx + math.cos(a) * d * rf, cz + math.sin(a) * d * rf
            g = B.ground_top(int(math.floor(fx)), int(math.floor(fz))) if B.site is not None else y0 - 1
            fy = max(y0 + 6, g + 4)
            pos = (fx, fy, fz)
            score = _sight(B, pos, [ftgt, (cx, y0 + 1, cz), (cx, y1, cz)]) + _clutter(B, pos) * 3 + abs(da) / 40 + abs(rf - 1)
            if best is None or score < best[0]:
                best = (score, pos)
    views.append({'name': 'front', 'label': t('view.front'), 'pos': [round(v, 2) for v in best[1]], 'target': ftgt, 'fov': 50})
    for n, y in enumerate(floor_levels(B), 1):
        sx, sz = (fv[0] or 0.6), (fv[1] or 0.6)
        views.append({'name': f'cut{n}', 'label': t('view.cut', n=n), 'pos': [round(cx + sx * d * 0.45, 2), round(y + d * 0.65, 2), round(cz + sz * d * 0.45, 2)],
                      'target': [round(cx, 2), y + 1, round(cz, 2)], 'fov': 50, 'cut': y + 2.5})
    views.append({'name': 'top', 'label': t('view.top'), 'pos': [round(cx, 2), round(y1 + s * 1.6 + 20, 2), round(cz + 0.01, 2)],
                  'target': [round(cx, 2), y0, round(cz, 2)], 'fov': 40})
    vc = P.cfg.get('verify', {})
    # eye-level view: on the ground, out on the approach side (walk start, else the front), far enough to see it whole
    if vc.get('walk_start'):
        dx_, dz_ = vc['walk_start'][0] + .5 - cx, vc['walk_start'][2] + .5 - cz
    else:
        dx_, dz_ = fv
    n_ = math.hypot(dx_, dz_) or 1
    r0 = math.hypot(x1 - x0 + 1, z1 - z0 + 1) / 2 + max(8, s * 0.35)
    base = math.atan2(dz_, dx_)
    etgt = [round(cx, 2), round(y0 + (y1 - y0) * 0.45, 2), round(cz, 2)]
    best = None
    for rf in (1.0, 0.85, 1.2, 1.4, 0.7):
        for da in (0, 15, -15, 30, -30, 45, -45):
            a = base + math.radians(da)
            ex, ez = cx + math.cos(a) * r0 * rf, cz + math.sin(a) * r0 * rf
            gx, gz = int(math.floor(ex)), int(math.floor(ez))
            gy = _natural_ground(B, gx, gz) if B.site is not None else y0 - 1
            if gy is None or (gx, gy + 1, gz) in B.cells:
                continue
            eye = (ex, gy + 1 + 1.62, ez)
            score = _sight(B, eye, [etgt, (cx, y0 + 1, cz), (cx, y1, cz)]) + abs(da) / 60 + abs(rf - 1) * 0.5
            if best is None or score < best[0]:
                best = (score, eye)
    if best:
        ex, ey, ez = best[1]
        views.append({'name': 'eye', 'label': t('view.eye'), 'pos': [round(ex, 2), round(ey, 2), round(ez, 2)], 'target': etgt, 'fov': 70})
    cam = read_json(P.art / 'camera.json')
    if cam:
        views.append({'name': 'shot', 'label': t('view.shot'), 'eye': cam['eye'], 'yaw': cam['yaw'], 'pitch': cam['pitch'],
                      'fov': cam['fov'], 'compare': True, 'wide': True})
    custom = pc.get('views', [])
    names = {v['name'] for v in custom}
    views = [v for v in views if v['name'] not in names] + custom
    if len(views) % 2 == 1:
        views[-1]['wide'] = True
    return views


# ------------------------------------------------------------------ scene
def _assets():
    """Client-jar models and textures, or the plain stand-in (shapes in map colours) when there is no client jar."""
    from .maps import assets
    A = assets()
    if A is None:
        from .plainassets import PlainAssets
        log(f'no vanilla {version()} client jar on this machine: preview uses block shapes in map colours '
            f'(`mcb fetch client --version {version()}` gives real textures)')
        A = PlainAssets(HOME / 'assets' / 'plain')
    return A


def bake_scene(P, B, before=False, box=None):
    from .light import tables, block_light, sky_light
    from .vendor.atlas.assets import face_vertices, NORMALS, rotation
    site = B.site
    box = box or scene_box(P, B)
    X0, Y0, Z0, X1, Y1, Z1 = box
    sx, sy, sz = X1 - X0, Y1 - Y0, Z1 - Z0
    states, index = [AIR], {AIR: 0}

    def sid(st):
        i = index.get(st)
        if i is None:
            i = index[st] = len(states); states.append(st)
        return i

    grid = np.zeros((sy, sz, sx), np.int32)
    if site is not None:
        from .terrain import MISSING
        a = [max(X0, site.X0), max(Y0, site.Y0), max(Z0, site.Z0)]
        b = [min(X1, site.X0 + site.W), min(Y1, site.Y0 + site.H), min(Z1, site.Z0 + site.D)]
        if all(a[k] < b[k] for k in range(3)):
            sub = site.IDS[a[1] - site.Y0:b[1] - site.Y0, a[2] - site.Z0:b[2] - site.Z0, a[0] - site.X0:b[0] - site.X0]
            dst = grid[a[1] - Y0:b[1] - Y0, a[2] - Z0:b[2] - Z0, a[0] - X0:b[0] - X0]
            for v in np.unique(sub):
                st = AIR if v == MISSING else site.state_of(int(v))
                dst[sub == v] = sid(st)
    build = np.zeros(grid.shape, np.uint8)
    if not before:
        for (x, y, z), st in B.cells.items():
            if X0 <= x < X1 and Y0 <= y < Y1 and Z0 <= z < Z1:
                grid[y - Y0, z - Z0, x - X0] = sid(st)
                build[y - Y0, z - Z0, x - X0] = 1 if st != AIR else 0
    A = _assets()
    biome = 'minecraft:plains'
    if site is not None and site.biome_names:
        vals, cnts = np.unique(site.biomes, return_counts=True)
        biome = site.biome_names.get(str(int(vals[np.argmax(cnts)])), biome)
    opaque = np.array([st != AIR and facts(st).opaque for st in states], bool)
    solid = grid != 0
    op = opaque[grid]
    hidden = np.ones(grid.shape, bool)
    for ax in range(3):
        for sgn in (1, -1):
            nb = np.zeros(grid.shape, bool)
            src = [slice(None)] * 3; dst = [slice(None)] * 3
            if sgn == 1:
                dst[ax] = slice(0, -1); src[ax] = slice(1, None)
            else:
                dst[ax] = slice(1, None); src[ax] = slice(0, -1)
            nb[tuple(dst)] = op[tuple(src)]
            if ax == 0 and sgn == -1:
                nb[0] = True                          # never show the underside of the box
            hidden &= nb
    visible = solid & ~hidden
    y, z, x = np.nonzero(visible)
    sids = grid[y, z, x]
    tabs = tables(states)
    sky = sky_light(grid, states, tabs)
    blk = block_light(grid, states, tabs)
    light = (sky.clip(0, 15).astype(np.uint8) << 4) | blk.clip(0, 15).astype(np.uint8)
    full_atlas = Image.open(A.atlas_path).convert('RGBA')
    tiles, tile_index = [], {}

    def tile(t):
        if t not in tile_index:
            tile_index[t] = len(tiles)
            cx_, cy_ = (t % 64) * 18 + 1, (t // 64) * 18 + 1
            tiles.append(full_atlas.crop((cx_, cy_, cx_ + 16, cy_ + 16)))
        return tile_index[t]

    def boxf(a, b, tex):
        a = np.array(a, np.float32) / 16; b = np.array(b, np.float32) / 16
        out = []
        for d, n in NORMALS.items():
            t = tex.get(d, tex.get('side')) if isinstance(tex, dict) else tex
            xx, yy, zz = a * 16; XX, YY, ZZ = b * 16
            u, v, U, V = np.array({'up': [xx, zz, XX, ZZ], 'down': [xx, 16 - ZZ, XX, 16 - zz], 'north': [16 - XX, 16 - YY, 16 - xx, 16 - yy],
                                   'south': [xx, 16 - YY, XX, 16 - yy], 'west': [zz, 16 - YY, ZZ, 16 - yy], 'east': [16 - ZZ, 16 - YY, 16 - zz, 16 - yy]}[d]) / 16
            uv = np.array([[u, V], [U, V], [U, v], [u, v]], np.float32)
            cull = d if ((d == 'down' and a[1] == 0) or (d == 'up' and b[1] == 1) or (d == 'west' and a[0] == 0) or (d == 'east' and b[0] == 1)
                         or (d == 'north' and a[2] == 0) or (d == 'south' and b[2] == 1)) else None
            out.append((np.array(face_vertices(d, a, b), np.float32), np.array(n, np.float32), uv, A.tiles.get('minecraft:block/' + t, 0), cull, False))
        return out

    def special(st):
        s = st.short
        if s.endswith('_bed'):
            wool = s[:-4] + '_wool'
            f = boxf((0, 3, 0), (16, 9, 16), {'side': wool, 'down': 'oak_planks'}) + boxf((0, 0, 0), (3, 3, 3), 'oak_planks') \
                + boxf((13, 0, 13), (16, 3, 16), 'oak_planks') + boxf((13, 0, 0), (16, 3, 3), 'oak_planks') + boxf((0, 0, 13), (3, 3, 16), 'oak_planks')
            if st.get('part') == 'head':
                f += boxf((2, 9, 1), (14, 11, 6), 'white_wool')
            rot = {'north': 0, 'east': 90, 'south': 180, 'west': 270}[st.get('facing')]
            m = rotation('y', -rot)
            return [((v - .5) @ m.T + .5, m @ n, uv, t, c, tt) for v, n, uv, t, c, tt in f]
        if s in ('chest', 'trapped_chest'):
            return boxf((1, 0, 1), (15, 14, 15), {'side': 'oak_planks', 'up': 'stripped_oak_log', 'down': 'oak_planks'})
        if s.endswith('copper_chest'):
            base = s.replace('_chest', '').replace('waxed_', '') or 'copper'
            base = 'copper_block' if base == 'copper' else base
            return boxf((1, 0, 1), (15, 14, 15), base)
        if s == 'ender_chest':
            return boxf((1, 0, 1), (15, 14, 15), 'obsidian')
        if s == 'decorated_pot':
            return boxf((1, 0, 1), (15, 16, 15), 'terracotta')
        if s.endswith('shulker_box'):
            col = s[:-len('_shulker_box')] if s != 'shulker_box' else 'purple'
            return boxf((0, 0, 0), (16, 16, 16), f'{col}_concrete' if col else 'purpur_block')
        if s == 'bubble_column':
            return A.faces({'Name': 'minecraft:water', 'Properties': {'level': '0'}})
        if s.endswith(('_sign', '_banner', '_head', '_skull')) or s in ('bell', 'conduit'):
            return []
        return None

    models = {}
    for i in sorted(set(int(v) for v in np.unique(sids))):
        st = states[i]
        faces = A.faces(st.nbt())
        plain = getattr(A, 'plain', False)
        sp = special(st) if not plain and (st.name in A.unsupported or st.short.endswith(('_bed', '_sign', '_banner', '_head', '_skull', 'shulker_box', 'copper_chest'))
                                           or st.short in ('chest', 'trapped_chest', 'ender_chest', 'bubble_column', 'decorated_pot', 'bell', 'conduit')) else None
        if sp is not None:
            faces = sp
        quads = []
        for verts, normal, uv, t, cull, tinted in faces:
            col_t = list(A.tint(st.nbt(), biome)) if tinted and (plain or st.short not in NO_TINT) else None
            quads.append({'v': np.round(np.asarray(verts) * 16, 3).ravel().tolist(), 'uv': np.round(np.asarray(uv) * 16, 3).ravel().tolist(),
                          'n': np.round(np.asarray(normal), 4).tolist(), 't': tile(t), 'c': DIRS.index(cull) if cull else -1,
                          'tint': [round(c, 4) for c in col_t] if col_t else None})
        s = st.short
        group = 'translucent' if (s.endswith(TRANSLUCENT_SUFFIX) or s in ('water', 'ice', 'tinted_glass', 'slime_block', 'honey_block')) else 'cutout'
        same = s if (s == 'glass' or s.endswith('_stained_glass') or s in ('water', 'ice', 'tinted_glass')) else None
        models[i] = {'key': st.key(), 'q': quads, 'opaque': bool(opaque[i]), 'group': group, 'same': same,
                     'emit': int(facts(st).lum), 'water': s == 'water' or st.get('waterlogged') == 'true'}
    n = len(tiles); cols = 16; rows = (n + cols - 1) // cols
    atlas = Image.new('RGBA', (cols * 16, max(1, rows) * 16))
    for k, im in enumerate(tiles):
        atlas.paste(im, ((k % cols) * 16, (k // cols) * 16))
    buf = io.BytesIO(); atlas.save(buf, 'PNG')
    vox = np.stack([x + X0, y + Y0, z + Z0, sids, build[y, z, x]], 1).astype('<i4')

    def pack(a):
        return base64.b64encode(gzip.compress(np.ascontiguousarray(a).tobytes(), 9)).decode()

    log('scene', 'box', box, 'visible voxels', len(sids), 'states', len(states), 'atlas tiles', n, '(plain colours)' if getattr(A, 'plain', False) else '')
    return {'box': [X0, Y0, Z0, sx, sy, sz], 'states': [s.key() for s in states], 'models': {str(k): v for k, v in models.items()},
            'opaque': [bool(o) for o in opaque], 'atlas': base64.b64encode(buf.getvalue()).decode(), 'atlasSize': list(atlas.size),
            'voxels': pack(vox), 'grid': pack(grid.astype('<u2')), 'light': pack(light), 'buildBlocks': int((build == 1).sum()),
            'plain': bool(getattr(A, 'plain', False))}


# ------------------------------------------------------------------ page
def outline_quads(P, B):
    plot = read_json(P.art / 'plot.json')
    if not plot or B.site is None:
        return []
    cols = {(c[0], c[1]) for c in plot['columns']}
    quads, w = [], 0.32
    for (x, z) in cols:
        h = B.site.ground_top(x, z) + 1.04
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + dx, z + dz) in cols:
                continue
            if dx == 1:
                quads.append([x + 1 - w, h, z, x + 1, h, z + 1])
            elif dx == -1:
                quads.append([x, h, z, x + w, h, z + 1])
            elif dz == 1:
                quads.append([x, h, z + 1 - w, x + 1, h, z + 1])
            else:
                quads.append([x, h, z, x + 1, h, z + w])
    return quads


def _jpeg_b64(path, width):
    im = Image.open(path).convert('RGB')
    aspect = im.width / im.height
    im = im.resize((width, round(width / aspect)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=84)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode(), aspect


def page_data(P, B, views):
    pc = P.cfg.get('preview', {})
    rep = read_json(P.art / 'export-report.json') or read_json(P.art / 'litematic-report.json') or {}
    ver = read_json(P.art / 'verification.json') or {}
    mats = read_json(P.art / 'materials.json') or []
    blocks = sum(1 for st in B.cells.values() if st != AIR)
    stats = []
    if rep:
        stats += [[t('stat.file'), f'<code>{rep["file"]}</code>'], [t('stat.origin'), f'<code>{" ".join(map(str, rep["origin"]))}</code>'],
                  [t('stat.size'), ' × '.join(map(str, rep['enclosingSize']))], [t('stat.regions'), t('stat.regions_v', n=len(rep["regions"]))]]
    stats.append([t('stat.blocks'), t('stat.blocks_v', n=f'{blocks:,}')])
    if ver.get('spawnProofing'):
        sp = ver['spawnProofing']
        stats.append([t('stat.spawn'), t('stat.spawn_ok', n=sp['spawnableSurfaces']) if not sp['darkSurfaces']
                      else t('stat.spawn_dark', n=sp['spawnableSurfaces'], d=sp['darkSurfaces'])])
    if ver.get('walk'):
        tg = ver['walk']['targets']
        stats.append([t('stat.walk'), t('stat.walk_v', a=sum(tg.values()), b=len(tg))])
    stats += pc.get('stats', [])
    page = {
        'title': pc.get('title', P.name), 'subtitle': pc.get('subtitle', ''),
        'eyebrow': pc.get('eyebrow', f"Create {rep.get('createVersion', '')} · Java {rep.get('targetVersion', version())}"
                          if rep.get('format') == 'create' else t('page.eyebrow', v=version())), 'lead': pc.get('lead', ''),
        'views': views, 'stats': stats, 'materials': mats,
        'matNote': pc.get('mat_note', t('page.matnote')),
        'contextLabel': pc.get('context_label', t('page.context')), 'outline': outline_quads(P, B), 'outlineLabel': pc.get('outline_label'),
        'cutRange': [B.bbox()[0][1] - 1, B.bbox()[1][1] + 1],
    }
    cam = read_json(P.art / 'camera.json')
    if cam and cam.get('image') and P.path(cam['image']).exists():
        page['shot'], page['shotAspect'] = _jpeg_b64(P.path(cam['image']), 1600)
    gal = []
    ig = read_json(P.art / 'ingame' / 'ingame-report.json')
    labels = {v['name']: v.get('label', v['name']) for v in (read_json(P.art / 'ingame' / 'ingame-config.json') or {}).get('views', [])}
    if ig:
        for name in ig.get('screenshots', []):
            p = P.art / 'ingame' / name
            if p.exists():
                src, _ = _jpeg_b64(p, 1280)
                gal.append({'label': labels.get(p.stem, p.stem), 'src': src})
    page['gallery'] = gal
    if gal:
        page['galleryTitle'] = t('page.gallery', v=version())
    page['lang'] = lang()
    page['ui'] = {k[3:]: t(k) for k in UI_KEYS}
    return page


def build_preview(P, shots=False, before=False):
    B = P.design()
    views = auto_views(P, B)
    scene = bake_scene(P, B, before=before)
    page = page_data(P, B, views)
    if scene.get('plain'):
        page['hint'] = t('ui.hint_plain')
    out_dir = P.art / 'preview'; out_dir.mkdir(exist_ok=True)
    tpl = (WEB / 'index.html').read_text(encoding='utf-8')
    js = (WEB / 'viewer.bundle.js').read_text(encoding='utf-8')
    sc = 'window.SCENE=' + json.dumps(scene, separators=(',', ':')) + ';'
    pg = 'window.PAGE=' + json.dumps(page, ensure_ascii=False, separators=(',', ':')) + ';'
    html = (tpl.replace('/*TITLE*/', t('page.title', name=P.name)).replace('<html lang="zh-CN">', f'<html lang="{"zh-CN" if lang() == "zh" else "en"}">')
            .replace('/*SCENE*/', sc.replace('</', '<\\/'))
            .replace('/*PAGE*/', pg.replace('</', '<\\/')).replace('/*BUNDLE*/', js.replace('</script', '<\\/script')))
    name = 'scene-before.html' if before else 'index.html'
    target = out_dir / name
    target.write_text(html, encoding='utf-8')
    # separate data files for the making-of video stage (video/stage.html loads them next to the bundle)
    (out_dir / ('scene-before.js' if before else 'scene.js')).write_text(sc, encoding='utf-8')
    if not before:
        (out_dir / 'page.js').write_text(pg, encoding='utf-8')
    write_json(out_dir / 'views.json', views)
    log('preview html', target, round(target.stat().st_size / 1e6, 2), 'MB', 'views', [v['name'] for v in views])
    if shots:
        shoot(P)
    return target


# ------------------------------------------------------------------ headless screenshots
UI_KEYS = ['ui.views', 'ui.light', 'ui.time', 'ui.time_aria', 'ui.day', 'ui.dusk', 'ui.evening', 'ui.night', 'ui.plot', 'ui.cut',
           'ui.cut_aria', 'ui.full', 'ui.layer', 'ui.data', 'ui.materials', 'ui.gallery', 'ui.close', 'ui.canvas', 'ui.shot_alt',
           'ui.wipe', 'ui.hint', 'ui.loading']


def shoot(P, views=None, out_dir=None, width=1600, height=900, html=None):
    """Screenshots of the preview page (Python or Node Playwright, see browser.py); [] when no browser is available."""
    from .browser import shoot as _shoot
    html = Path(html or P.art / 'preview' / 'index.html')
    out_dir = Path(out_dir or P.art / 'shots')
    if not views:
        views = [v['name'] for v in read_json(P.art / 'preview' / 'views.json', [])]
    return _shoot(html, out_dir, width, height, views)
