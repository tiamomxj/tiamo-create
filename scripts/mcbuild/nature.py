"""Planting on a Frame (local coordinates). Every tree stands on the terrain surface of its column.

Trees use persistent=true leaves by default (player-placed leaves never decay; the rules pass still sets the
vanilla distance). Plants check their soil so the verifier's support checks pass.
"""
from __future__ import annotations
import math, random

SOIL = ('grass_block', 'dirt', 'coarse_dirt', 'podzol', 'rooted_dirt', 'moss_block', 'mud', 'muddy_mangrove_roots', 'mycelium')
FLOWERS = ['dandelion', 'poppy', 'oxeye_daisy', 'cornflower', 'azure_bluet', 'allium', 'red_tulip', 'white_tulip', 'pink_tulip',
           'orange_tulip', 'lily_of_the_valley', 'blue_orchid']
TALL_FLOWERS = ['rose_bush', 'peony', 'lilac', 'sunflower']


def palm(f, lx, lz, height, lean=(0, 0), fronds=1.0, part=None, log='jungle_log[axis=y]',
         leaf='jungle_leaves[persistent=true]', coconuts=True):
    """Leaning palm: log trunk (shifted by `lean` twice), drooping leaf fronds, cocoa 'coconuts' under the crown."""
    if part:
        f.cur = part
    gy = f.ground(lx, lz) + 1
    dx, dz = lean
    x, z = lx, lz
    for i in range(height):
        if i in (height // 2, height - 2) and (dx or dz):
            x += dx; z += dz
        f.put(x, gy + i, z, log)
    top = gy + height
    f.put(x, top, z, leaf); f.put(x, top + 1, z, leaf)
    orth = [(1, 0), (2, 0), (3, 0), (3, -1), (4, -1), (4, -2)]     # (reach, drop) of a drooping frond
    diag = [(1, 0), (2, 0), (2, -1), (3, -1), (3, -2)]
    if fronds < 1:
        orth, diag = orth[:-1], diag[:-1]
    for fx, fz in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
        for k, drop in (diag if fx and fz else orth):
            f.put(x + fx * k, top + drop, z + fz * k, leaf)
    if coconuts and log.startswith('jungle_log'):
        for face, (cx, cz) in [('east', (-1, 0)), ('west', (1, 0)), ('south', (0, -1))]:
            f.put(x + cx, top - 1, z + cz, f'cocoa[age=2,facing={face}]')
    return x, top, z


def round_tree(f, lx, lz, height=6, radius=2.5, rng=None, log='oak_log[axis=y]', leaf='oak_leaves[persistent=true]', part=None,
               ragged=0.25):
    """Broadleaf tree (oak / birch / cherry / dark oak style): straight trunk + blobby crown with ragged edges."""
    rng = rng or random.Random(lx * 7919 + lz)
    if part:
        f.cur = part
    gy = f.ground(lx, lz) + 1
    for i in range(height):
        f.put(lx, gy + i, lz, log)
    cy = gy + height - 1
    n = math.ceil(radius)
    for x in range(-n, n + 1):
        for y in range(-1, n + 1):
            for z in range(-n, n + 1):
                d = math.sqrt(x * x + (y * 1.3) ** 2 + z * z)
                if d <= radius and not (x == 0 and z == 0 and y < 1):
                    if d > radius - 1 and rng.random() < ragged:
                        continue
                    f.put(lx + x, cy + y, lz + z, leaf)
    return cy


def conifer(f, lx, lz, height=9, log='spruce_log[axis=y]', leaf='spruce_leaves[persistent=true]', part=None):
    """Spruce-style cone: layered rings shrinking toward a pointed top."""
    if part:
        f.cur = part
    gy = f.ground(lx, lz) + 1
    for i in range(height - 1):
        f.put(lx, gy + i, lz, log)
    top = gy + height
    for k, y in enumerate(range(top, gy + 1, -1)):
        r = min(3, (k + 1) // 2) if k % 2 == 0 else max(1, (k + 1) // 2 - 1)
        if y >= top - 1:
            r = 0 if y == top else 1
        for x in range(-r, r + 1):
            for z in range(-r, r + 1):
                if abs(x) + abs(z) <= r + (1 if r >= 2 else 0) and (x or z or y >= gy + height - 1):
                    f.put(lx + x, y, lz + z, leaf)
    return top


def bush(f, lx, lz, leaf='oak_leaves[persistent=true]', size=1, part=None):
    gy = f.ground(lx, lz) + 1
    for x in range(-size, size + 1):
        for z in range(-size, size + 1):
            if abs(x) + abs(z) <= size:
                f.put(lx + x, gy, lz + z, leaf, part)
    f.put(lx, gy + 1, lz, leaf, part)


def bamboo_clump(f, spots, heights, part=None, soil=('grass_block', 'dirt', 'sand', 'gravel', 'podzol', 'moss_block', 'coarse_dirt')):
    for (lx, lz), h in zip(spots, heights):
        g = f.ground(lx, lz)
        if f.terrain(lx, g, lz).short in soil or f.get(lx, g, lz) is not None:
            f.bamboo(lx, g + 1, lz, h, part)


def flowers(f, spots, rng=None, kinds=None, part=None, soil=SOIL):
    """Plant flowers at (lx, lz) spots on grass; 'tall:' kinds become two-block plants."""
    rng = rng or random.Random(len(spots))
    kinds = kinds or FLOWERS
    n = 0
    for lx, lz in spots:
        g = f.ground(lx, lz)
        if f.terrain(lx, g, lz).short not in soil:
            continue
        k = rng.choice(kinds)
        if k.startswith('tall:') or k in TALL_FLOWERS:
            f.tall(lx, g + 1, lz, k.replace('tall:', ''), part)
        else:
            f.put(lx, g + 1, lz, k, part)
        n += 1
    return n
