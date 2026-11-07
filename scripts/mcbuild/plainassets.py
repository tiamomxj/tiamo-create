"""Stand-in for the client-jar assets when this machine has no vanilla client (cloud sandbox, game installed on
another computer ...): every block is drawn from facts the kit ships - its collision boxes (a cross for plants, a thin
post for torches, a flat sheet for rails and wires) in the game's own map colour - so the 3D preview still shows
shapes, heights, openings, light and night correctly. `mcb fetch client` (or a local game install) brings back the
real models and textures.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image
from .registry import facts, from_nbt
from .vendor.atlas.assets import face_vertices, NORMALS

TRANSLUCENT = ('glass', 'glass_pane', 'ice', 'water', 'slime_block', 'honey_block', 'tinted_glass')
FIXED = {'water': (0.25, 0.45, 0.9), 'lava': (0.95, 0.45, 0.1), 'glass': (0.82, 0.9, 0.95), 'glass_pane': (0.82, 0.9, 0.95),
         'ice': (0.62, 0.75, 0.98), 'grass_block': (0.45, 0.66, 0.27), 'short_grass': (0.42, 0.62, 0.25),
         'tall_grass': (0.42, 0.62, 0.25), 'fern': (0.38, 0.58, 0.25), 'torch': (1.0, 0.85, 0.4), 'wall_torch': (1.0, 0.85, 0.4),
         'lantern': (0.95, 0.75, 0.35), 'soul_lantern': (0.45, 0.85, 0.9), 'air': (0, 0, 0)}
UV = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float32)


def _rgb(st):
    s = st.short
    if s in FIXED:
        return FIXED[s]
    if s.endswith('_leaves'):
        return (0.30, 0.55, 0.22) if s != 'cherry_leaves' else (0.95, 0.70, 0.80)
    if s.endswith(('_stained_glass', '_stained_glass_pane')):
        c = facts(st).map_color
        return tuple(((c >> k) & 255) / 255 for k in (16, 8, 0)) if c else (0.8, 0.85, 0.9)
    c = facts(st).map_color
    if not c:
        return (0.62, 0.62, 0.62)
    r, g, b = ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255
    return (r, g, b)


def _box_faces(a, b, tile):
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    out = []
    for d, n in NORMALS.items():
        cull = d if ((d == 'down' and a[1] <= 0) or (d == 'up' and b[1] >= 1) or (d == 'west' and a[0] <= 0) or (d == 'east' and b[0] >= 1)
                     or (d == 'north' and a[2] <= 0) or (d == 'south' and b[2] >= 1)) else None
        out.append((np.array(face_vertices(d, a, b), np.float32), np.array(n, np.float32), UV, tile, cull, True))
    return out


def _cross(h, tile):
    out = []
    for (x0, z0, x1, z1) in ((0.15, 0.15, 0.85, 0.85), (0.15, 0.85, 0.85, 0.15)):
        v = np.array([(x0, 0, z0), (x1, 0, z1), (x1, h, z1), (x0, h, z0)], np.float32)
        n = np.cross(v[1] - v[0], v[3] - v[0]); n = n / np.linalg.norm(n)
        out.append((v, n.astype(np.float32), UV, tile, None, True))
        out.append((v[::-1].copy(), (-n).astype(np.float32), UV, tile, None, True))
    return out


class PlainAssets:
    plain = True

    def __init__(self, out_dir):
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        self.tiles = {'missingno': 0}
        self.unsupported = set()
        self.averages = {0: [0.94, 0.94, 0.94], 1: [0.94, 0.94, 0.94]}
        self.alphas = {0: True, 1: False}
        self.colormaps = {}
        rng = np.random.default_rng(7)
        noise = rng.random((16, 16)) * 0.14 + 0.86          # a little grain so flat faces read as blocks
        noise[[0, 15], :] *= 0.9; noise[:, [0, 15]] *= 0.9
        rgb = (np.stack([noise] * 3, -1) * 255).astype(np.uint8)
        t0 = Image.fromarray(np.concatenate([rgb, np.full((16, 16, 1), 255, np.uint8)], -1), 'RGBA')
        t1 = t0.copy(); t1.putalpha(120)
        atlas = Image.new('RGBA', (64 * 18, 18))
        for idx, im in enumerate((t0, t1)):
            x, y = idx * 18 + 1, 1
            atlas.paste(im, (x, y))
            atlas.paste(im.crop((0, 0, 1, 16)), (x - 1, y)); atlas.paste(im.crop((15, 0, 16, 16)), (x + 16, y))
            atlas.paste(im.crop((0, 0, 16, 1)), (x, y - 1)); atlas.paste(im.crop((0, 15, 16, 16)), (x, y + 16))
        self.atlas_path = out_dir / 'plain-atlas.png'
        atlas.save(self.atlas_path)
        self.width, self.height = atlas.size
        self.id = 'plain'

    def faces(self, state):
        return self._faces(state['Name'], tuple(sorted(state.get('Properties', {}).items())))

    @lru_cache(maxsize=16384)
    def _faces(self, name, props):
        st = from_nbt({'Name': name, 'Properties': dict(props)})
        s = st.short
        if s in ('air', 'cave_air', 'void_air', 'structure_void', 'light', 'barrier'):
            return ()
        tile = 1 if (s.endswith(TRANSLUCENT) or s.endswith('_stained_glass') or s.endswith('_stained_glass_pane')) else 0
        if s in ('water', 'lava', 'bubble_column'):
            h = 1 if int(dict(props).get('level', '0')) >= 8 else 0.875
            return tuple(_box_faces((0, 0, 0), (1, h, 1), 1 if s != 'lava' else 0))
        f = facts(st)
        if f.boxes:
            out = []
            for bx in f.boxes:
                a, b = (min(1.0, max(0.0, v)) for v in bx[:3]), (min(1.5, max(0.0, v)) for v in bx[3:])
                out += _box_faces(tuple(a), tuple(b), tile)
            return tuple(out)
        if 'Torch' in ''.join(f.classes) or s.endswith(('torch', 'end_rod', 'lightning_rod')):
            return tuple(_box_faces((7 / 16, 0, 7 / 16), (9 / 16, 10 / 16, 9 / 16), 0))
        if s.endswith(('rail', 'redstone_wire', 'tripwire')) or 'Carpet' in ''.join(f.classes) or s.endswith(('_carpet', 'lily_pad', 'leaf_litter')):
            return tuple(_box_faces((0, 0, 0), (1, 1 / 16, 1), 0))
        if s.endswith(('_sign', '_banner', '_head', '_skull', 'button', 'lever', 'tripwire_hook')):
            return tuple(_box_faces((0.25, 0.25, 0.25), (0.75, 0.75, 0.75), 0))
        tall = 1.0 if s.startswith(('tall_', 'large_')) or s in ('sugar_cane', 'bamboo_sapling') else 0.8
        return tuple(_cross(tall, 0))

    def tint(self, state, biome):
        return _rgb(from_nbt(state))

    def top(self, state, biome):
        faces = self.faces(state)
        return 0, list(self.tint(state, biome)), float(max((f[0][:, 1].max() for f in faces), default=1.0))

    def opaque(self, state):
        return facts(from_nbt(state)).opaque

    def metadata(self):
        return {'id': 'plain', 'source': None, 'tiles': 2, 'width': self.width, 'height': self.height, 'columns': 64, 'cell': 18,
                'unsupported': [], 'plain': True}
