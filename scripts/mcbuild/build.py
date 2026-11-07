"""The design being built: world cells -> State, tagged with a part name; local frames with rotation/mirroring.

    B = Build(site)                          # site: terrain.Site (or None for no known terrain)
    F = B.frame((x, y, z), turns=1)          # local (0,0,0) at world (x,y,z); design in a canonical orientation,
                                             # turns = clockwise quarter turns applied to positions AND states
    F.fill((0, 0, 0), (8, 4, 6), 'stone_bricks'); F.clear((1, 1, 1), (7, 3, 5))
    F.door(4, 1, 0, 'north')                  # composites take local coordinates and local facings
    F.put(3, F.ground(3, -2) + 1, -2, 'lantern')   # ground(): local y of the terrain surface block

Local axes before rotation: +x = east, +y = up, +z = south. AIR cells are explicit clearances (they will remove
terrain); cells never set keep the terrain. Parts name the pieces (used for sub-regions, materials, reports).
"""
from __future__ import annotations
from collections import Counter
from .registry import AIR, State, as_state, OFFSET, OPPOSITE, CW, CCW
from .rotate import rotate_state, mirror_state, rotate_vec


class Build:
    def __init__(self, site=None, name='build'):
        self.site = site
        self.name = name
        self.cells: dict[tuple, State] = {}
        self.part: dict[tuple, str] = {}
        self.cur = 'main'
        self.frames = []
        self.notes = []                       # free-form design notes collected for the report

    # ------------------------------------------------------------ world-level access
    def frame(self, origin=(0, 0, 0), turns=0, mirror=None, name=None):
        f = Frame(self, origin, turns, mirror, name)
        self.frames.append(f)
        return f

    def putw(self, p, spec, part=None):
        st = as_state(spec)
        p = (int(p[0]), int(p[1]), int(p[2]))
        self.cells[p] = st
        self.part[p] = part or self.cur

    def remove(self, p):
        """Forget a cell (it keeps whatever the terrain has)."""
        self.cells.pop(p, None)
        self.part.pop(p, None)

    def world(self, p) -> State:
        return self.site.world(*p) if self.site is not None else AIR

    def getw(self, p) -> State:
        """Final block at a world position: the design cell if set, else the terrain."""
        st = self.cells.get(p)
        return st if st is not None else self.world(p)

    def ground_top(self, x, z):
        if self.site is None:
            return 0
        return self.site.ground_top(x, z)

    def blocks(self):
        return {p: st for p, st in self.cells.items() if st != AIR}

    def bbox(self, include_air=True):
        ps = list(self.cells) if include_air else [p for p, st in self.cells.items() if st != AIR]
        if not ps:
            return None
        xs, ys, zs = zip(*ps)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def parts(self):
        return Counter(self.part.values())

    def resolve(self, **kw):
        from .rules import resolve
        return resolve(self, **kw)

    def summary(self):
        blocks = self.blocks()
        bb = self.bbox()
        return {'blocks': len(blocks), 'clearances': len(self.cells) - len(blocks), 'bbox': bb,
                'size': [bb[1][k] - bb[0][k] + 1 for k in range(3)] if bb else None,
                'parts': dict(self.parts()), 'top': Counter(st.short for st in blocks.values()).most_common(40)}


class Frame:
    """Local coordinate system on a Build: origin + clockwise quarter turns (+ optional mirror before turning)."""

    def __init__(self, build: Build, origin, turns=0, mirror=None, name=None):
        self.B = build
        self.origin = tuple(int(v) for v in origin)
        self.turns = turns % 4
        self.mirror = mirror                  # None | 'x' (flip local east/west) | 'z' (flip local north/south)
        self.name = name

    # ------------------------------------------------------------ coordinates
    def w(self, lx, ly, lz):
        if self.mirror == 'x':
            lx = -lx
        elif self.mirror == 'z':
            lz = -lz
        dx, dz = rotate_vec(lx, lz, self.turns)
        return self.origin[0] + dx, self.origin[1] + ly, self.origin[2] + dz

    def local(self, x, y, z):
        dx, dz = rotate_vec(x - self.origin[0], z - self.origin[2], -self.turns)
        if self.mirror == 'x':
            dx = -dx
        elif self.mirror == 'z':
            dz = -dz
        return dx, y - self.origin[1], dz

    def dir(self, d):
        """Local direction name -> world direction name."""
        if d in ('up', 'down'):
            return d
        if self.mirror == 'x' and d in ('east', 'west'):
            d = OPPOSITE[d]
        elif self.mirror == 'z' and d in ('north', 'south'):
            d = OPPOSITE[d]
        for _ in range(self.turns):
            d = CW[d]
        return d

    def st(self, spec) -> State:
        s = as_state(spec)
        if self.mirror:
            s = mirror_state(s, self.mirror)
        if self.turns:
            s = rotate_state(s, self.turns)
        return s

    # ------------------------------------------------------------ placement
    @property
    def cur(self):
        return self.B.cur

    @cur.setter
    def cur(self, v):
        self.B.cur = v

    def put(self, lx, ly, lz, spec, part=None):
        self.B.putw(self.w(lx, ly, lz), self.st(spec), part)

    def fill(self, a, b, spec, part=None, only_empty=False, hollow=False):
        (x0, y0, z0), (x1, y1, z1) = a, b
        st = self.st(spec)
        xa, xb = min(x0, x1), max(x0, x1)
        ya, yb = min(y0, y1), max(y0, y1)
        za, zb = min(z0, z1), max(z0, z1)
        for x in range(xa, xb + 1):
            for y in range(ya, yb + 1):
                for z in range(za, zb + 1):
                    if hollow and xa < x < xb and ya < y < yb and za < z < zb:
                        continue
                    p = self.w(x, y, z)
                    if only_empty and self.B.cells.get(p, AIR) != AIR:
                        continue
                    self.B.putw(p, st, part)

    def clear(self, a, b, part=None):
        self.fill(a, b, AIR, part)

    def get(self, lx, ly, lz):
        """Design cell at a local position (world-oriented state) or None."""
        return self.B.cells.get(self.w(lx, ly, lz))

    def at(self, lx, ly, lz):
        """Final block (design or terrain) at a local position."""
        return self.B.getw(self.w(lx, ly, lz))

    def remove(self, lx, ly, lz):
        self.B.remove(self.w(lx, ly, lz))

    def ground(self, lx, lz):
        """Local y of the terrain's top solid block in this column (ground surface block; build on ground + 1)."""
        x, _, z = self.w(lx, 0, lz)
        return self.B.ground_top(x, z) - self.origin[1]

    def water_top(self, lx, lz):
        if self.B.site is None:
            return None
        x, _, z = self.w(lx, 0, lz)
        t = self.B.site.water_top(x, z)
        return None if t is None else t - self.origin[1]

    def terrain(self, lx, ly, lz):
        """Terrain block (ignoring the design) at a local position."""
        return self.B.world(self.w(lx, ly, lz))

    # ------------------------------------------------------------ composites (local coordinates / facings)
    def door(self, lx, ly, lz, facing, hinge='left', wood='oak', part=None):
        """Two-block door. `facing` = vanilla facing = the direction a player looks when walking IN through it
        (e.g. a door in the north wall entered from outside has facing=south)."""
        self.put(lx, ly, lz, f'{wood}_door[facing={facing},half=lower,hinge={hinge}]', part)
        self.put(lx, ly + 1, lz, f'{wood}_door[facing={facing},half=upper,hinge={hinge}]', part)

    def double_door(self, lx, ly, lz, facing, wood='oak', part=None):
        """Double door: (lx, lz) is the left leaf for a player walking in (looking `facing`), hinges on the outer sides."""
        dx, _, dz = OFFSET[CW[facing]] if facing in CW else (1, 0, 0)
        self.door(lx, ly, lz, facing, 'left', wood, part)
        self.door(lx + dx, ly, lz + dz, facing, 'right', wood, part)

    def bed(self, foot, facing, color='white', part=None):
        fx, fy, fz = foot
        dx, _, dz = OFFSET[facing]
        self.put(fx, fy, fz, f'{color}_bed[facing={facing},part=foot]', part)
        self.put(fx + dx, fy, fz + dz, f'{color}_bed[facing={facing},part=head]', part)

    def tall(self, lx, ly, lz, name, part=None, **props):
        """Two-block plants and similar (half=lower/upper): tall_grass, large_fern, rose_bush, peony, lilac, sunflower..."""
        extra = ''.join(f',{k}={v}' for k, v in props.items())
        self.put(lx, ly, lz, f'{name}[half=lower{extra}]', part)
        self.put(lx, ly + 1, lz, f'{name}[half=upper{extra}]', part)

    def chest_pair(self, lx, ly, lz, facing, kind='chest', part=None):
        """Double chest whose front faces `facing`: (lx, lz) is the type=left half (the chest's own left); the other half
        goes one block clockwise of `facing` (vanilla ChestBlock.getFacing)."""
        dx, _, dz = OFFSET[CCW[facing]]
        self.put(lx, ly, lz, f'{kind}[facing={facing},type=left]', part)
        self.put(lx - dx, ly, lz - dz, f'{kind}[facing={facing},type=right]', part)

    def hanging_lantern(self, lx, ly, lz, chain=1, kind='lantern', part=None):
        """Lantern at ly hanging from `chain` iron chains above it."""
        self.put(lx, ly, lz, f'{kind}[hanging=true]', part)
        for k in range(1, chain + 1):
            self.put(lx, ly + k, lz, 'iron_chain[axis=y]', part)

    def bamboo(self, lx, ly, lz, h, part=None):
        for i in range(h):
            top = h - 1 - i
            leaves = 'large' if top < 2 else 'small' if top < 3 else 'none'
            self.put(lx, ly + i, lz, f'bamboo[age=1,leaves={leaves},stage=1]', part)

    def on_ground(self, lx, lz, spec, dy=1, part=None, soil=None):
        """Place spec on top of the terrain surface (optionally only if the surface block is in `soil`)."""
        g = self.ground(lx, lz)
        if soil is not None and self.terrain(lx, g, lz).short not in soil:
            return False
        self.put(lx, g + dy, lz, spec, part)
        return True
