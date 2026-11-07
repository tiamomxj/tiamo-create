"""Geometry helpers on a Frame (all coordinates local, inclusive corners, specs are block-state strings or States).

Massing:     box, walls, floor, line, polyline
Round:       pixel_circle, disc, ring, cylinder, sphere, dome, ellipse_disc
Roofs:       gable_roof, hip_roof, shed_roof, pyramid_roof, flat_roof
Circulation: stair_flight, spiral_stair, ladder
Openings:    window_grid, arch
Terrain:     foundation, pillar_down, level_pad, path, scatter
Patterns:    pattern(f, cells, choose) — per-cell choice for texture mixes (e.g. 70% stone bricks, 30% mossy)
"""
from __future__ import annotations
import math, random
from .registry import AIR, OFFSET, CW, CCW, OPPOSITE


# ------------------------------------------------------------------ massing
def box(f, a, b, spec, part=None, hollow=False, only_empty=False):
    f.fill(a, b, spec, part, only_empty=only_empty, hollow=hollow)


def walls(f, a, b, spec, part=None):
    """Four vertical walls of the box a..b (no floor / ceiling)."""
    (x0, y0, z0), (x1, y1, z1) = a, b
    f.fill((x0, y0, z0), (x1, y1, z0), spec, part); f.fill((x0, y0, z1), (x1, y1, z1), spec, part)
    f.fill((x0, y0, z0), (x0, y1, z1), spec, part); f.fill((x1, y0, z0), (x1, y1, z1), spec, part)


def floor(f, a, b, y, spec, part=None):
    f.fill((a[0], y, a[1]), (b[0], y, b[1]), spec, part)


def line(f, p, q, spec, part=None):
    """3D Bresenham-style line (every step moves along the dominant axis)."""
    for c in line_cells(p, q):
        f.put(*c, spec, part)


def line_cells(p, q):
    (x0, y0, z0), (x1, y1, z1) = p, q
    n = max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    if n == 0:
        return [tuple(p)]
    return [(round(x0 + (x1 - x0) * t / n), round(y0 + (y1 - y0) * t / n), round(z0 + (z1 - z0) * t / n)) for t in range(n + 1)]


def polyline(f, pts, spec, part=None, closed=False):
    pts = list(pts) + ([pts[0]] if closed else [])
    for a, b in zip(pts, pts[1:]):
        line(f, a, b, spec, part)


def pattern(f, cells, choose, part=None):
    """Place choose(lx, ly, lz) (a spec or None) at each cell — for weathering / texture mixes."""
    for c in cells:
        s = choose(*c)
        if s is not None:
            f.put(*c, s, part)


def mix(rng, weighted):
    """weighted = [('stone_bricks', 6), ('mossy_stone_bricks', 2), ('cracked_stone_bricks', 1)] -> chooser."""
    specs, w = zip(*weighted)
    return lambda *_: rng.choices(specs, w)[0]


# ------------------------------------------------------------------ round shapes
def pixel_circle(d):
    """Pixel circle of diameter d: (ring, inner) sets of (du, dv) offsets in 0..d-1 (centre at (d-1)/2)."""
    r_out, r_in = d / 2, d / 2 - 1
    c = (d - 1) / 2
    ring, inner = set(), set()
    for u in range(d):
        for v in range(d):
            dd = (u - c) ** 2 + (v - c) ** 2
            if dd <= r_out ** 2:
                (inner if dd <= r_in ** 2 else ring).add((u, v))
    return ring, inner


def disc_cells(r):
    """Offsets (du, dv) of a filled disc of radius r centred on a block (r may be fractional, e.g. 3.5)."""
    n = math.ceil(r)
    return {(u, v) for u in range(-n, n + 1) for v in range(-n, n + 1) if u * u + v * v <= r * r + r * 0.8}


def ring_cells(r, thickness=1):
    outer = disc_cells(r)
    inner = disc_cells(r - thickness) if r - thickness > 0 else set()
    return outer - inner


def disc(f, center, r, spec, part=None, axis='y'):
    _plane(f, center, disc_cells(r), spec, part, axis)


def ring(f, center, r, spec, part=None, thickness=1, axis='y'):
    _plane(f, center, ring_cells(r, thickness), spec, part, axis)


def _plane(f, center, offs, spec, part, axis):
    cx, cy, cz = center
    for u, v in offs:
        if axis == 'y':
            f.put(cx + u, cy, cz + v, spec, part)
        elif axis == 'x':
            f.put(cx, cy + u, cz + v, spec, part)
        else:
            f.put(cx + u, cy + v, cz, spec, part)


def cylinder(f, base, r, h, spec, part=None, hollow=False, thickness=1):
    cells = ring_cells(r, thickness) if hollow else disc_cells(r)
    for dy in range(h):
        _plane(f, (base[0], base[1] + dy, base[2]), cells, spec, part, 'y')


def sphere(f, center, r, spec, part=None, hollow=False, thickness=1, upper_only=False):
    cx, cy, cz = center
    n = math.ceil(r)
    for x in range(-n, n + 1):
        for y in range(0 if upper_only else -n, n + 1):
            for z in range(-n, n + 1):
                d = math.sqrt(x * x + y * y + z * z)
                if d <= r + 0.3 and (not hollow or d > r - thickness + 0.3):
                    f.put(cx + x, cy + y, cz + z, spec, part)


def dome(f, center, r, spec, part=None, thickness=1):
    sphere(f, center, r, spec, part, hollow=True, thickness=thickness, upper_only=True)


def ellipse_disc(f, center, rx, rz, spec, part=None):
    cx, cy, cz = center
    for x in range(-math.ceil(rx), math.ceil(rx) + 1):
        for z in range(-math.ceil(rz), math.ceil(rz) + 1):
            if (x / (rx + 0.4)) ** 2 + (z / (rz + 0.4)) ** 2 <= 1:
                f.put(cx + x, cy, cz + z, spec, part)


# ------------------------------------------------------------------ roofs
def _slab_for(stairs):
    from .registry import known
    base = stairs.split('[')[0]
    cand = base[:-len('_stairs')] + '_slab' if base.endswith('_stairs') else None
    return f'{cand}[type=bottom]' if cand and known(cand) else None


def gable_roof(f, x0, z0, x1, z1, y, stairs, ridge='x', overhang=1, cap=None, gable=None, under=None, part=None):
    """Stair-stepped gable roof over the wall rectangle x0..x1 / z0..z1, lowest course at height y.
    ridge='x': ridge runs along x, slopes face north/south ('z': ridge along z). One course per block of rise.
    cap: ridge block for an odd width (default: the matching bottom slab); gable: wall block filling the gable
    triangles at the two ends; under: block placed under every upper course (closed roof mass).
    Returns the y of the top course."""
    if ridge == 'x':
        n0, n1, r0, r1, ends = z0 - overhang, z1 + overhang, x0 - overhang, x1 + overhang, (x0, x1)
        P = lambda a, yy, r: (r, yy, a)
        face_lo, face_hi = 'south', 'north'
    else:
        n0, n1, r0, r1, ends = x0 - overhang, x1 + overhang, z0 - overhang, z1 + overhang, (z0, z1)
        P = lambda a, yy, r: (a, yy, r)
        face_lo, face_hi = 'east', 'west'
    width = n1 - n0 + 1
    courses = width // 2
    for k in range(courses):
        yy, lo, hi = y + k, n0 + k, n1 - k
        for r in range(r0, r1 + 1):
            f.put(*P(lo, yy, r), f'{stairs}[facing={face_lo},half=bottom]', part)
            f.put(*P(hi, yy, r), f'{stairs}[facing={face_hi},half=bottom]', part)
            if under and k > 0:
                f.put(*P(lo, yy - 1, r), under, part)
                f.put(*P(hi, yy - 1, r), under, part)
        if gable:
            for a in range(lo + 1, hi):
                for r in ends:
                    f.put(*P(a, yy, r), gable, part)
    top = y + courses - 1
    if width % 2:
        top = y + courses
        c = cap or _slab_for(stairs) or f'{stairs}[facing={face_lo},half=bottom]'
        for r in range(r0, r1 + 1):
            f.put(*P(n0 + courses, top, r), c, part)
            if under and courses > 0:
                f.put(*P(n0 + courses, top - 1, r), under, part)
    return top


def hip_roof(f, x0, z0, x1, z1, y, stairs, overhang=1, cap=None, part=None, fill=None):
    """Hipped roof: concentric stair rings rising one block per course until the footprint closes.
    fill: block for the inside of every ring (solid roof — avoids a dark hollow attic where mobs spawn).
    Returns the y above the last course."""
    xa, za, xb, zb = x0 - overhang, z0 - overhang, x1 + overhang, z1 + overhang
    k = 0
    while xa <= xb and za <= zb:
        yy = y + k
        if fill and xb - xa >= 2 and zb - za >= 2:
            f.fill((xa + 1, yy, za + 1), (xb - 1, yy, zb - 1), fill, part)
        if xa == xb or za == zb:
            for x in range(xa, xb + 1):
                for z in range(za, zb + 1):
                    f.put(x, yy, z, cap or _slab_for(stairs) or f'{stairs}[facing=south,half=bottom]', part)
            break
        for x in range(xa, xb + 1):
            f.put(x, yy, za, f'{stairs}[facing=south,half=bottom]', part)
            f.put(x, yy, zb, f'{stairs}[facing=north,half=bottom]', part)
        for z in range(za + 1, zb):
            f.put(xa, yy, z, f'{stairs}[facing=east,half=bottom]', part)
            f.put(xb, yy, z, f'{stairs}[facing=west,half=bottom]', part)
        xa += 1; za += 1; xb -= 1; zb -= 1; k += 1
    return y + k


def pyramid_roof(f, x0, z0, x1, z1, y, stairs, overhang=1, cap=None, part=None, fill=None):
    return hip_roof(f, x0, z0, x1, z1, y, stairs, overhang, cap, part, fill)


def shed_roof(f, x0, z0, x1, z1, y, stairs, rise_toward='north', overhang=1, part=None):
    """Mono-pitch roof rising one block per course toward `rise_toward`."""
    xs = range(x0 - overhang, x1 + overhang + 1)
    zs = range(z0 - overhang, z1 + overhang + 1)
    if rise_toward in ('north', 'south'):
        order = list(zs) if rise_toward == 'south' else list(zs)[::-1]
        for k, z in enumerate(order):
            for x in xs:
                f.put(x, y + k, z, f'{stairs}[facing={rise_toward},half=bottom]', part)
    else:
        order = list(xs) if rise_toward == 'east' else list(xs)[::-1]
        for k, x in enumerate(order):
            for z in zs:
                f.put(x, y + k, z, f'{stairs}[facing={rise_toward},half=bottom]', part)


def flat_roof(f, x0, z0, x1, z1, y, spec, rim=None, overhang=0, part=None):
    f.fill((x0 - overhang, y, z0 - overhang), (x1 + overhang, y, z1 + overhang), spec, part)
    if rim:
        walls(f, (x0 - overhang, y + 1, z0 - overhang), (x1 + overhang, y + 1, z1 + overhang), rim, part)


# ------------------------------------------------------------------ circulation
def stair_flight(f, start, direction, rise, stairs, support=None, clear=3, part=None):
    """Straight flight going up `rise` blocks: first step at `start` (feet level y0 = start y), one block forward
    and one up per step, facing `direction` (the way you walk up). Clears `clear` blocks of headroom above every
    step and optionally fills `support` under each step down to start y - 1. Returns the landing cell."""
    dx, _, dz = OFFSET[direction]
    x, y, z = start
    for k in range(rise):
        f.put(x, y + k, z, f'{stairs}[facing={direction},half=bottom]', part)
        for h in range(1, clear + 1):
            f.put(x, y + k + h, z, AIR, part)
        if support:
            for yy in range(y, y + k):
                f.put(x, yy, z, support, part)
        x += dx; z += dz
    return (x, y + rise, z)


def spiral_stair(f, center, y0, y1, step, core=None, r=1, part=None):
    """Spiral of slabs/stairs around a core column (step = spec of a full step such as a bottom slab sequence)."""
    cx, _, cz = center
    ring_ = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    for i, y in enumerate(range(y0, y1)):
        du, dv = ring_[i % 8]
        f.put(cx + du * r, y, cz + dv * r, step, part)
        if core:
            f.put(cx, y, cz, core, part)


def ladder(f, x, y0, y1, z, facing, part=None):
    for y in range(y0, y1 + 1):
        f.put(x, y, z, f'ladder[facing={facing}]', part)


# ------------------------------------------------------------------ openings
def window_grid(f, wall_cells, spec, part=None):
    for c in wall_cells:
        f.put(*c, spec, part)


def arch(f, x0, x1, y_spring, z, spec, part=None, axis='x', clear_inside=True):
    """Round arch spanning x0..x1 (inclusive) at plane z, springing at y_spring: carves the opening (AIR) and
    rings it with spec. axis='z' spans along z at plane x."""
    w = x1 - x0 + 1
    r = w / 2
    cx = (x0 + x1) / 2
    for i in range(w):
        u = x0 + i
        h = math.sqrt(max(0.0, r * r - (u - cx) ** 2))
        top = y_spring + int(round(h))
        for y in range(y_spring, top + 1):
            p = (u, y, z) if axis == 'x' else (z, y, u)
            if clear_inside:
                f.put(*p, AIR, part)
        p = (u, top + 1, z) if axis == 'x' else (z, top + 1, u)
        f.put(*p, spec, part)


# ------------------------------------------------------------------ terrain fitting
def foundation(f, cells_xz, top_ly, spec, part='foundation', extra=0):
    """Fill each (lx, lz) column from the terrain surface (+1) up to top_ly - 1 (so the floor at top_ly sits on it).
    extra = how many blocks below the surface to also replace (anchoring on slopes)."""
    n = 0
    for lx, lz in cells_xz:
        for ly in range(f.ground(lx, lz) + 1 - extra, top_ly):
            f.put(lx, ly, lz, spec, part); n += 1
    return n


def pillar_down(f, lx, lz, top_ly, spec, part=None, through_water=True):
    """Column from top_ly down to just above the terrain surface (the sea bed when standing in water)."""
    g = f.ground(lx, lz)
    for ly in range(top_ly, g, -1):
        f.put(lx, ly, lz, spec, part)
    return top_ly - g


def level_pad(f, x0, z0, x1, z1, ly, top='grass_block', fill='dirt', clear_h=12, part='terrain', blend=0):
    """Grade a rectangle to a flat pad whose surface block is at ly: cut everything above (clear_h blocks) and fill
    below down to the existing ground. blend > 0 adds a sloped margin of that many blocks."""
    for lx in range(x0 - blend, x1 + blend + 1):
        for lz in range(z0 - blend, z1 + blend + 1):
            dx = max(x0 - lx, 0, lx - x1); dz = max(z0 - lz, 0, lz - z1)
            d = max(dx, dz)
            g = f.ground(lx, lz)
            target = ly if d == 0 else round(ly + (g - ly) * d / (blend + 1))
            for y in range(target + 1, max(g, target) + clear_h):
                if f.terrain(lx, y, lz) != AIR:
                    f.put(lx, y, lz, AIR, part)
            for y in range(min(g, target), target):
                f.put(lx, y, lz, fill, part)
            f.put(lx, target, lz, top, part)


def path(f, pts, spec, width=1, part='path', replace_surface=True):
    """A path through local (lx, lz) points following the terrain: replaces the surface block (or lays on top)."""
    done = set()
    for a, b in zip(pts, pts[1:]):
        for x, _, z in line_cells((a[0], 0, a[1]), (b[0], 0, b[1])):
            for u in range(-(width // 2), width - width // 2):
                for v in range(-(width // 2), width - width // 2):
                    c = (x + u, z + v)
                    if c in done:
                        continue
                    done.add(c)
                    g = f.ground(*c)
                    f.put(c[0], g if replace_surface else g + 1, c[1], spec, part)
    return done


def scatter(f, x0, z0, x1, z1, rng, density, choices, soil=('grass_block',), part=None, avoid=None):
    """Random plants on the terrain surface. choices: list of (spec or callable(rng)->spec, weight); tall plants
    given as 'tall:rose_bush'. Only places where the surface block is in `soil` and the cell above is free."""
    specs, w = zip(*choices)
    n = 0
    for lx in range(x0, x1 + 1):
        for lz in range(z0, z1 + 1):
            if rng.random() >= density or (avoid and avoid(lx, lz)):
                continue
            g = f.ground(lx, lz)
            if f.terrain(lx, g, lz).short not in soil or f.get(lx, g + 1, lz) not in (None, AIR):
                continue
            s = rng.choices(specs, w)[0]
            s = s(rng) if callable(s) else s
            if s.startswith('tall:'):
                f.tall(lx, g + 1, lz, s[5:], part)
            else:
                f.put(lx, g + 1, lz, s, part)
            n += 1
    return n
