"""Site analysis and reference-style analysis.

analyze():      terrain heights / slope / water depth, existing player builds (clusters of non-natural blocks),
                vegetation, biome mix, and — given a footprint — the best flat spots (least cut & fill, no water,
                no existing builds). -> artifacts/analysis.json + analysis-map.png
find_builds():  clusters of player-placed blocks (used to locate "my house", neighbours, roads, and to grow the
                preview box so neighbours are shown whole)
style_report(): block statistics of a reference build grouped by role + swatches + top view / elevations of it.
"""
from __future__ import annotations
import json, math
from collections import Counter
from pathlib import Path
import numpy as np
from .registry import AIR, facts, zh_name, in_tag, is_stairs, is_slab, is_pane_like, is_fence, is_wall, is_door, is_trapdoor
from .terrain import kind, is_natural, is_vegetation, MISSING
from .util import log, write_json
from .i18n import t, ti, block_name, image_lang


def _label(mask):
    try:
        from scipy.ndimage import label
        lab, n = label(mask)
        return lab, n
    except ImportError:                       # BFS fallback
        lab = np.zeros(mask.shape, np.int32); n = 0
        for z, x in zip(*np.nonzero(mask)):
            if lab[z, x]:
                continue
            n += 1; st = [(z, x)]; lab[z, x] = n
            while st:
                a, b = st.pop()
                for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    c, d = a + da, b + db
                    if 0 <= c < mask.shape[0] and 0 <= d < mask.shape[1] and mask[c, d] and not lab[c, d]:
                        lab[c, d] = n; st.append((c, d))
        return lab, n


def find_builds(site, box=None, min_blocks=25, gap=2):
    """Clusters of player-placed (non-natural) blocks. box = (x0, z0, x1, z1) world, exclusive."""
    built = site.lut(lambda st: 0 if is_natural(st) else 1).astype(bool)
    if box is not None:
        x0, z0, x1, z1 = box
        built = built[:, max(0, z0 - site.Z0):max(0, z1 - site.Z0), max(0, x0 - site.X0):max(0, x1 - site.X0)]
        ox, oz = max(x0, site.X0), max(z0, site.Z0)
    else:
        ox, oz = site.X0, site.Z0
    cols = built.sum(0)
    mask = cols > 0
    if gap:
        from numpy.lib.stride_tricks import sliding_window_view
        pad = np.pad(mask, gap)
        mask_d = sliding_window_view(pad, (2 * gap + 1, 2 * gap + 1)).any(axis=(2, 3))
    else:
        mask_d = mask
    lab, n = _label(mask_d)
    surf = site.heightmap(lambda st: kind(st) == 'solid' and not is_vegetation(st) and is_natural(st))
    if box is not None:
        surf = surf[max(0, z0 - site.Z0):max(0, z1 - site.Z0), max(0, x0 - site.X0):max(0, x1 - site.X0)]
    out = []
    for k in range(1, n + 1):
        sel = (lab == k) & mask
        cnt = int(cols[sel].sum())
        if cnt < min_blocks:
            continue
        zz, xx = np.nonzero(sel)
        ys = np.nonzero(built[:, sel].any(1))[0]
        y1w = int(ys.max() + site.Y0)
        out.append({'x0': int(xx.min() + ox), 'z0': int(zz.min() + oz), 'x1': int(xx.max() + ox), 'z1': int(zz.max() + oz),
                    'y0': int(ys.min() + site.Y0), 'y1': y1w, 'blocks': cnt, 'columns': int(sel.sum()),
                    'underground': bool(y1w < float(np.median(surf[sel])) - 2)})
    out.sort(key=lambda b: -b['blocks'])
    for i, b in enumerate(out):
        b['id'] = i + 1
        b['top'] = _top_blocks(site, (b['x0'], b['y0'], b['z0'], b['x1'], b['y1'], b['z1']))[:8]
    return out


def _top_blocks(site, box6, natural=False):
    x0, y0, z0, x1, y1, z1 = box6
    sub = site.IDS[y0 - site.Y0:y1 - site.Y0 + 1, z0 - site.Z0:z1 - site.Z0 + 1, x0 - site.X0:x1 - site.X0 + 1]
    vals, cnts = np.unique(sub, return_counts=True)
    c = Counter()
    for v, n in zip(vals, cnts):
        if v == MISSING:
            continue
        st = site.state_of(int(v))
        if st == AIR or (not natural and is_natural(st)):
            continue
        c[st.short] += int(n)
    return [[k, n, block_name(k)] for k, n in c.most_common()]


def flat_spots(site, footprint, box=None, top=6, avoid_builds=True, max_water=0.0, pad_y=None):
    """Best (w x d) rectangles: lowest earthwork (cut + fill to the median ground), no water/builds.
    Returns [{x0, z0, x1, z1, padY, cutFill, std, water, trees}] sorted by score."""
    w, d = footprint
    ground = site.heightmap(lambda st: kind(st) == 'solid' and not is_vegetation(st) and is_natural(st))
    water = site.lut(lambda st: 1 if kind(st) == 'water' else 0).any(0)
    built = site.lut(lambda st: 0 if is_natural(st) else 1).any(0)
    veg = site.lut(lambda st: 1 if is_vegetation(st) and kind(st) == 'solid' else 0).any(0)
    if box is not None:
        x0, z0, x1, z1 = box
        sl = np.s_[z0 - site.Z0:z1 - site.Z0, x0 - site.X0:x1 - site.X0]
        ground, water, built, veg = ground[sl], water[sl], built[sl], veg[sl]
        ox, oz = x0, z0
    else:
        ox, oz = site.X0, site.Z0
    from numpy.lib.stride_tricks import sliding_window_view as win
    if ground.shape[0] < d or ground.shape[1] < w:
        return []
    G = win(ground.astype(np.float32), (d, w))
    med = np.median(G, axis=(2, 3)) if pad_y is None else np.full(G.shape[:2], pad_y, np.float32)
    cutfill = np.abs(G - med[..., None, None]).sum(axis=(2, 3))
    std = G.std(axis=(2, 3))
    wf = win(water, (d, w)).mean(axis=(2, 3))
    bf = win(built, (d, w)).any(axis=(2, 3))
    vf = win(veg, (d, w)).mean(axis=(2, 3))
    score = cutfill / (w * d) + 4 * wf + 0.8 * vf
    if avoid_builds:
        score = np.where(bf, np.inf, score)
    score = np.where(wf > max_water, np.inf, score)
    out = []
    taken = np.zeros_like(score, bool)
    order = np.argsort(score, axis=None)
    for idx in order:
        zi, xi = np.unravel_index(idx, score.shape)
        if not np.isfinite(score[zi, xi]):
            break
        if taken[zi, xi]:
            continue
        out.append({'x0': int(xi + ox), 'z0': int(zi + oz), 'x1': int(xi + ox + w - 1), 'z1': int(zi + oz + d - 1),
                    'padY': int(round(float(med[zi, xi]))), 'cutFill': int(cutfill[zi, xi]), 'std': round(float(std[zi, xi]), 2),
                    'water': round(float(wf[zi, xi]), 2), 'trees': round(float(vf[zi, xi]), 2), 'score': round(float(score[zi, xi]), 3)})
        taken[max(0, zi - d):zi + d, max(0, xi - w):xi + w] = True
        if len(out) >= top:
            break
    return out


def analyze(P, box=None, footprint=None, top=6, pad_y=None):
    site = P.site()
    if box is None:
        x0, _, z0, x1, _, z1 = site.box
        box = (x0, z0, x1, z1)
    builds = find_builds(site, box)
    ground = site.heightmap(lambda st: kind(st) == 'solid' and not is_vegetation(st))
    x0, z0, x1, z1 = box
    g = ground[z0 - site.Z0:z1 - site.Z0, x0 - site.X0:x1 - site.X0]
    wat = site.lut(lambda st: 1 if kind(st) == 'water' else 0).any(0)[z0 - site.Z0:z1 - site.Z0, x0 - site.X0:x1 - site.X0]
    gy, gx = np.gradient(g.astype(np.float32))
    slope = np.hypot(gx, gy)
    biomes = Counter()
    if site.biome_names:
        vals, cnts = np.unique(site.biomes, return_counts=True)
        for v, c in zip(vals, cnts):
            biomes[site.biome_names.get(str(int(v)), '?')] += int(c)
    res = {'box': box, 'ground': {'min': int(g[g > site.Y0 - 1].min()) if (g > site.Y0 - 1).any() else None, 'max': int(g.max()),
                                  'median': float(np.median(g))},
           'waterFraction': round(float(wat.mean()), 3), 'slopeMean': round(float(slope.mean()), 2),
           'steepFraction': round(float((slope > 1.0).mean()), 3), 'biomes': dict(biomes.most_common(6)), 'builds': builds}
    marks, rects = [], []
    for b in builds[:20]:
        names = ti('list.sep').join(block_name(x[0], image_lang()) for x in b['top'][:3])
        rects.append({'x0': b['x0'], 'z0': b['z0'], 'x1': b['x1'] + 1, 'z1': b['z1'] + 1,
                      'label': ti('map.build', id=b['id'], under=ti('map.underground') if b['underground'] else '', n=b['blocks'], names=names),
                      'color': (150, 150, 150) if b['underground'] else (255, 70, 70)})
    if footprint:
        spots = flat_spots(site, footprint, box, top, pad_y=pad_y)
        res['spots'] = {'footprint': footprint, 'candidates': spots}
        for i, s in enumerate(spots, 1):
            rects.append({'x0': s['x0'], 'z0': s['z0'], 'x1': s['x1'] + 1, 'z1': s['z1'] + 1,
                          'label': ti('map.spot', i=i, y=s['padY'], cf=s['cutFill']), 'color': (60, 220, 90)})
    write_json(P.art / 'analysis.json', res)
    from .maps import render_map
    W = box[2] - box[0]
    scale = max(2, min(8, 1400 // max(1, W)))
    render_map(site, P.art / 'analysis-map.png', box, scale, 16, 32, (), rects, title=ti('map.analysis'))
    log('ANALYZE', f"ground {res['ground']}  water {res['waterFraction']}  steep {res['steepFraction']}  biomes {res['biomes']}")
    for b in builds[:12]:
        log(f"  build {b['id']}{' (underground - maybe a mineshaft)' if b['underground'] else ''}: x {b['x0']}..{b['x1']} z {b['z0']}..{b['z1']} "
            f"y {b['y0']}..{b['y1']}  {b['blocks']} blocks  " + ', '.join(f'{x[0]}×{x[1]}' for x in b['top'][:5]))
    for i, s in enumerate(res.get('spots', {}).get('candidates', []), 1):
        log(f"  spot {i}: x {s['x0']}..{s['x1']} z {s['z0']}..{s['z1']}  pad Y {s['padY']}  earthwork {s['cutFill']}  water {s['water']}  trees {s['trees']}")
    log('->', P.art / 'analysis.json', P.art / 'analysis-map.png')
    return res


ROLE_ORDER = ['structure', 'stairs', 'slabs', 'thin', 'glass', 'doors', 'lights', 'plants', 'deco']   # labels: i18n 'role.*'


def role_of(st):
    f = facts(st)
    s = st.short
    if f.lum > 0:
        return 'lights'
    if is_vegetation(st) or kind(st) == 'plant':
        return 'plants'
    if is_stairs(st):
        return 'stairs'
    if is_slab(st):
        return 'slabs'
    if is_pane_like(st) or is_fence(st) or is_wall(st):
        return 'thin'
    if 'glass' in s:
        return 'glass'
    if is_door(st) or is_trapdoor(st):
        return 'doors'
    if f.full_cube:
        return 'structure'
    return 'deco'


def style_report(P, box6, name='reference'):
    """Block statistics of a reference build (inclusive box) -> json + swatch chart + drawings."""
    from PIL import Image, ImageDraw
    from .maps import state_colors, font, design_drawings
    from .build import Build
    site = P.site()
    x0, y0, z0, x1, y1, z1 = box6
    roles = {r: Counter() for r in ROLE_ORDER}
    states = {}
    B = Build(site, name)
    for y in range(y0, y1 + 1):
        for z in range(z0, z1 + 1):
            for x in range(x0, x1 + 1):
                st = site.world(x, y, z)
                if st == AIR or is_natural(st):
                    continue
                roles[role_of(st)][st.short] += 1
                states.setdefault(st.short, st)
                B.cells[(x, y, z)] = st; B.part[(x, y, z)] = name
    total = sum(sum(c.values()) for c in roles.values())
    rep = {'box': box6, 'blocks': total, 'roles': {r: [[k, n, block_name(k)] for k, n in c.most_common()] for r, c in roles.items() if c},
           'roleLabels': {r: t('role.' + r) for r in ROLE_ORDER}}
    write_json(P.art / f'style-{name}.json', rep)
    col = state_colors(list(states.values()), 'side')
    rows = [(r, k, n) for r in ROLE_ORDER for k, n in roles[r].most_common(8)]
    f = font(14)
    H = 34 + 26 * len(rows) + 20 * len([r for r in ROLE_ORDER if roles[r]])
    im = Image.new('RGB', (760, H), (247, 245, 240))
    d = ImageDraw.Draw(im)
    d.text((14, 8), ti('style.title', n=total, box=box6), fill=(30, 30, 30), font=f)
    yy = 34
    mx = max((n for _, _, n in rows), default=1)
    last = None
    for r, k, n in rows:
        if r != last:
            d.text((14, yy), ti('role.' + r), fill=(120, 90, 60), font=f); yy += 20; last = r
        c = col[states[k]]
        d.rectangle([24, yy + 2, 44, yy + 22], fill=c, outline=(60, 60, 60))
        d.text((54, yy + 3), f'{block_name(k, image_lang())}  {k}', fill=(30, 30, 30), font=font(13))
        w = int(320 * n / mx)
        d.rectangle([400, yy + 6, 400 + w, yy + 18], fill=c)
        d.text((406 + w, yy + 3), str(n), fill=(60, 60, 60), font=font(12))
        yy += 26
    im.save(P.art / f'style-{name}.png')
    files = design_drawings(B, P.art / f'style-{name}-drawings', scale=8, with_terrain=False, layers=False) if B.cells else []
    log('STYLE', name, total, 'blocks →', P.art / f'style-{name}.png', [p.name for p in files])
    for r in ROLE_ORDER:
        if roles[r]:
            log(f'  {r}: ' + ', '.join(f'{k}×{n}' for k, n in roles[r].most_common(6)))
    return rep
