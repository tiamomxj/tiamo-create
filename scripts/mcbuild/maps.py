"""Flat images: top-down site maps with coordinates (to locate things), and quick orthographic drawings of a design
(top view, four elevations, every floor layer) — fast feedback without a browser.

Colours come from the vanilla textures of the client jar (average of the faces' textures, biome tint applied),
falling back to the game's map colours.
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .registry import AIR, State, facts, version
from .util import HOME, client_jar, log, cjk_font, latin_font

_ASSETS = {}
def font(size=13):
    """A font that can draw the labels (Chinese-capable when the system has one; i18n.image_lang() picks English
    labels otherwise)."""
    for p in (cjk_font(), latin_font()):
        if p:
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)               # Pillow >= 10.1: scalable built-in font
    except TypeError:
        return ImageFont.load_default()


def assets():
    v = version()
    if v not in _ASSETS:
        jar = client_jar(v)
        if jar is None:
            _ASSETS[v] = None
        else:
            from .vendor.atlas.assets import Assets
            try:
                _ASSETS[v] = Assets(jar, HOME / 'assets' / v)
            except (OSError, ValueError) as e:
                log('cannot use the client jar', jar, e)
                _ASSETS[v] = None
    return _ASSETS[v]


def _map_rgb(st):
    c = facts(st).map_color
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255) if c else None


_COLOR_CACHE = {}


def state_colors(states, view='top', biome='minecraft:plains'):
    """{State: (r, g, b)} — average texture colour of the faces seen from `view` ('top' or 'side')."""
    A = assets()
    out = {}
    for st in states:
        key = (st, view, biome)
        if key in _COLOR_CACHE:
            out[st] = _COLOR_CACHE[key]; continue
        c = None
        if st != AIR and A is not None:
            try:
                faces = A.faces(st.nbt())
                want = ('up',) if view == 'top' else ('north', 'south', 'east', 'west')
                acc, wsum = np.zeros(3), 0.0
                for verts, normal, uv, tile, cull, tinted in faces:
                    n = tuple(np.rint(normal).astype(int))
                    d = {(0, 1, 0): 'up', (0, -1, 0): 'down', (0, 0, -1): 'north', (0, 0, 1): 'south', (-1, 0, 0): 'west', (1, 0, 0): 'east'}.get(n)
                    if d not in want:
                        continue
                    area = float(np.ptp(verts, axis=0).prod() / max(1e-6, np.ptp(verts, axis=0).max()))
                    col = np.array(A.averages.get(tile, [.5, .5, .5]))
                    if tinted and st.short not in ('cherry_leaves', 'azalea_leaves', 'flowering_azalea_leaves', 'pale_oak_leaves'):
                        col = col * np.array(A.tint(st.nbt(), biome))
                    acc += col * max(area, 0.05); wsum += max(area, 0.05)
                if wsum:
                    c = tuple(int(v) for v in np.clip(acc / wsum * 255, 0, 255))
            except Exception:
                c = None
        if c is None:
            c = _map_rgb(st) or (255, 0, 255) if st != AIR else (0, 0, 0)
        if st.short == 'water':
            c = (63, 118, 228)
        _COLOR_CACHE[key] = c
        out[st] = c
    return out


# ------------------------------------------------------------------ site maps
def top_layer(site, box=None, ignore=('air', 'plant', 'light')):
    """(height[z,x], state index grid[z,x], states list) of the top visible surface (plants ignored)."""
    from .terrain import kind
    m = site.lut(lambda st: 0 if kind(st) in ignore else 1).astype(bool)
    if box is not None:
        x0, z0, x1, z1 = box
        sl = np.s_[:, z0 - site.Z0:z1 - site.Z0, x0 - site.X0:x1 - site.X0]
    else:
        x0, z0 = site.X0, site.Z0
        sl = np.s_[:, :, :]
    m = m[sl]; ids = site.IDS[sl]
    has = m.any(0)
    top = m.shape[0] - 1 - np.argmax(m[::-1], axis=0)
    zz, xx = np.indices(has.shape)
    tid = ids[top, zz, xx]
    return np.where(has, top + site.Y0, site.Y0 - 1), np.where(has, tid, 0xFFFFFFFF), (x0, z0)


def render_map(site, out, box=None, scale=3, grid=16, label_every=32, marks=(), boxes=(), polys=(), cells=(), title=None,
               water_depth=True, shade=True):
    """Top-down map with coordinate grid. box = (x0, z0, x1, z1) world (exclusive).
    marks: [{'x','z','label','color'}]; boxes: [{'x0','z0','x1','z1','label','color'}]; polys: [{'pts':[(x,z)],'color','label'}]
    cells: [{'cells': [(x,z)...], 'color': (r,g,b,a)}] translucent fills."""
    hgt, tid, (x0, z0) = top_layer(site, box)
    D, W = hgt.shape
    used = [int(v) for v in np.unique(tid) if v != 0xFFFFFFFF]
    states = {i: site.state_of(i) for i in used}
    col = state_colors(set(states.values()))
    img = np.zeros((D, W, 3), np.float32)
    for i, st in states.items():
        img[tid == i] = col[st]
    if water_depth:
        from .terrain import kind
        ground = site.heightmap(lambda st: kind(st) == 'solid')
        if box is not None:
            ground = ground[box[1] - site.Z0:box[3] - site.Z0, box[0] - site.X0:box[2] - site.X0]
        depth = (hgt - ground).clip(0, 12)
        wmask = np.isin(tid, [i for i, st in states.items() if st.short == 'water'])
        img[wmask] *= (1 - depth[wmask, None] * 0.045)
    if shade:
        hs = np.zeros((D, W), np.float32)
        hs[1:, :] += (hgt[1:, :] - hgt[:-1, :]).clip(-3, 3) * 0.06
        hs[:, 1:] += (hgt[:, 1:] - hgt[:, :-1]).clip(-3, 3) * 0.03
        img *= (1 + hs)[..., None]
    img[tid == 0xFFFFFFFF] = (24, 24, 28)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W * scale, D * scale), Image.NEAREST).convert('RGBA')
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = font(12 if scale < 6 else 14)
    P = lambda x, z: ((x - x0) * scale, (z - z0) * scale)
    for c in cells:
        for (x, z) in c['cells']:
            px, pz = P(x, z)
            d.rectangle([px, pz, px + scale - 1, pz + scale - 1], fill=tuple(c.get('color', (255, 255, 0, 90))))
    if grid:
        for x in range(x0 - x0 % grid + grid, x0 + W, grid):
            strong = label_every and x % label_every == 0
            d.line([P(x, z0), P(x, z0 + D)], fill=(255, 255, 0, 150) if strong else (255, 255, 255, 55), width=1)
            if strong:
                d.text((P(x, z0)[0] + 2, 2), str(x), fill=(255, 255, 0, 255), font=f)
        for z in range(z0 - z0 % grid + grid, z0 + D, grid):
            strong = label_every and z % label_every == 0
            d.line([P(x0, z), P(x0 + W, z)], fill=(255, 255, 0, 150) if strong else (255, 255, 255, 55), width=1)
            if strong:
                d.text((2, P(x0, z)[1] + 2), str(z), fill=(255, 255, 0, 255), font=f)
    for b in boxes:
        c = tuple(b.get('color', (255, 60, 60)))
        d.rectangle([P(b['x0'], b['z0']), P(b['x1'], b['z1'])], outline=c + (255,), width=2)
        if b.get('label'):
            d.text((P(b['x0'], b['z0'])[0] + 3, P(b['x0'], b['z0'])[1] + 2), b['label'], fill=c + (255,), font=f,
                   stroke_width=2, stroke_fill=(0, 0, 0, 255))
    for pl in polys:
        c = tuple(pl.get('color', (40, 140, 255)))
        pts = [P(x + .5, z + .5) for x, z in pl['pts']]
        if len(pts) > 1:
            d.line(pts + [pts[0]], fill=c + (255,), width=2)
        if pl.get('label'):
            d.text(pts[0], pl['label'], fill=c + (255,), font=f, stroke_width=2, stroke_fill=(0, 0, 0, 255))
    for m in marks:
        c = tuple(m.get('color', (255, 40, 40)))
        px, pz = P(m['x'] + .5, m['z'] + .5)
        r = max(4, scale)
        d.ellipse([px - r, pz - r, px + r, pz + r], outline=c + (255,), width=3)
        if m.get('label'):
            d.text((px + r + 2, pz - 8), m['label'], fill=c + (255,), font=f, stroke_width=2, stroke_fill=(0, 0, 0, 255))
    im = Image.alpha_composite(im, ov)
    if title:
        d2 = ImageDraw.Draw(im)
        d2.rectangle([0, 0, im.width, 22], fill=(0, 0, 0, 160))
        d2.text((6, 3), title, fill=(255, 255, 255, 255), font=font(14))
    im.convert('RGB').save(out)
    return out


def height_image(site, out, box=None, scale=2):
    hgt, tid, _ = top_layer(site, box)
    lo, hi = np.percentile(hgt[hgt > site.Y0 - 1], [2, 98]) if (hgt > site.Y0 - 1).any() else (0, 1)
    n = ((hgt - lo) / max(1, hi - lo)).clip(0, 1)
    rgb = np.stack([n * 230 + 20, (1 - abs(n - .5) * 2) * 160 + 60, (1 - n) * 220 + 20], -1)
    Image.fromarray(rgb.astype(np.uint8)).resize((rgb.shape[1] * scale, rgb.shape[0] * scale), Image.NEAREST).save(out)


# ------------------------------------------------------------------ design drawings
def _grid_of(build, with_terrain=True, margin=1):
    bb = build.bbox()
    (x0, y0, z0), (x1, y1, z1) = bb
    x0 -= margin; z0 -= margin; x1 += margin; z1 += margin
    sx, sy, sz = x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1
    states = [AIR]; index = {AIR: 0}
    g = np.zeros((sy, sz, sx), np.int32)
    isb = np.zeros((sy, sz, sx), bool)
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            for y in range(y0, y1 + 1):
                p = (x, y, z)
                st = build.cells.get(p)
                if st is None:
                    if not with_terrain:
                        continue
                    st = build.world(p)
                else:
                    isb[y - y0, z - z0, x - x0] = st != AIR
                if st == AIR:
                    continue
                i = index.get(st)
                if i is None:
                    i = index[st] = len(states); states.append(st)
                g[y - y0, z - z0, x - x0] = i
    return g, isb, states, (x0, y0, z0)


def design_drawings(build, out_dir, scale=None, with_terrain=True, layers=True):
    """Top view, N/E/S/W elevations and per-layer plans of the design -> PNG files; returns the paths."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    g, isb, states, (x0, y0, z0) = _grid_of(build, with_terrain)
    if not scale:
        scale = int(max(4, min(24, 960 // max(g.shape[1], g.shape[2], g.shape[0]))))
    top = state_colors(states, 'top'); side = state_colors(states, 'side')
    ctop = np.array([top[s] for s in states], np.float32); cside = np.array([side[s] for s in states], np.float32)
    sy, sz, sx = g.shape
    files = []
    f = font(13)

    def save(arr, name, label, xs=None, ys=None):
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).resize((arr.shape[1] * scale, arr.shape[0] * scale), Image.NEAREST)
        d = ImageDraw.Draw(im)
        for k in range(0, arr.shape[1] + 1):
            d.line([(k * scale, 0), (k * scale, im.height)], fill=(0, 0, 0) if k % 5 == 0 else (60, 60, 60), width=1)
        for k in range(0, arr.shape[0] + 1):
            d.line([(0, k * scale), (im.width, k * scale)], fill=(0, 0, 0) if k % 5 == 0 else (60, 60, 60), width=1)
        canvas = Image.new('RGB', (im.width + 60, im.height + 50), (245, 243, 238))
        canvas.paste(im, (50, 30))
        d = ImageDraw.Draw(canvas)
        d.text((50, 6), label, fill=(20, 20, 20), font=f)
        if xs is not None:
            for k, v in enumerate(xs):
                if v % 5 == 0:
                    d.text((50 + k * scale, im.height + 32), str(v), fill=(90, 90, 90), font=font(10))
        if ys is not None:
            for k, v in enumerate(ys):
                if v % 5 == 0:
                    d.text((4, 30 + k * scale), str(v), fill=(90, 90, 90), font=font(10))
        p = out_dir / name
        canvas.save(p); files.append(p)

    # top view: first non-air from above, shaded by depth below the top of the bbox
    occ = g != 0
    has = occ.any(0)
    t = sy - 1 - np.argmax(occ[::-1], axis=0)
    zz, xx = np.indices(has.shape)
    arr = ctop[g[t, zz, xx]] * (0.55 + 0.45 * (t / max(1, sy - 1)))[..., None]
    arr[~has] = (250, 250, 250)
    from .i18n import ti
    save(arr, 'plan-top.png', ti('draw.top', x0=x0, x1=x0 + sx - 1, z0=z0, z1=z0 + sz - 1), list(range(x0, x0 + sx)), list(range(z0, z0 + sz)))
    # elevations: looking from outside toward the build
    views = {'north': (lambda a: a, 1, False), 'south': (lambda a: a[:, ::-1, :], 1, True),
             'west': (lambda a: a.transpose(0, 2, 1), 2, False), 'east': (lambda a: a.transpose(0, 2, 1)[:, ::-1, :], 2, True)}
    zh = {d: ti('draw.' + d) for d in ('north', 'south', 'west', 'east')}
    for side_name, (tr, _, flip) in views.items():
        a = tr(g)                       # [y, depth, width]
        o = a != 0
        hit = o.any(1)
        k = np.argmax(o, axis=1)        # first along depth
        yy, ww = np.indices(hit.shape)
        img = cside[a[yy, k, ww]] * (1 - 0.35 * (k / max(1, a.shape[1] - 1)))[..., None]
        img[~hit] = (250, 250, 250)
        img = img[::-1]                 # y up
        # a viewer facing south has east on the left, facing west has south on the left: flip those two
        if side_name in ('north', 'east'):
            img = img[:, ::-1]
        widths = list(range(x0, x0 + sx)) if side_name in ('north', 'south') else list(range(z0, z0 + sz))
        if side_name in ('north', 'east'):
            widths = widths[::-1]
        save(img, f'elev-{side_name}.png', zh[side_name], widths, list(range(y0 + sy - 1, y0 - 1, -1)))
    if layers:
        ys = [y for y in range(sy) if isb[y].any()]
        tiles = []
        for y in ys:
            a = ctop[g[y]].copy()
            a[g[y] == 0] = (250, 250, 250)
            below = g[y - 1] if y > 0 else np.zeros_like(g[y])
            a[(g[y] == 0) & (below != 0)] = (205, 205, 205)
            im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((sx * 6, sz * 6), Image.NEAREST)
            tile = Image.new('RGB', (im.width + 8, im.height + 22), (245, 243, 238))
            tile.paste(im, (4, 18))
            ImageDraw.Draw(tile).text((4, 2), f'Y={y0 + y}', fill=(20, 20, 20), font=font(12))
            tiles.append(tile)
        if tiles:
            cols = max(1, min(6, int(math.sqrt(len(tiles)) + 1)))
            tw, th = tiles[0].size
            sheet = Image.new('RGB', (cols * tw, math.ceil(len(tiles) / cols) * th), (245, 243, 238))
            for i, t in enumerate(tiles):
                sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
            p = out_dir / 'layers.png'
            sheet.save(p); files.append(p)
    return files
