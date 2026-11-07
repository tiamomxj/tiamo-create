"""Rotate / mirror block states the way the game does (StructureTemplate placement).

turns = clockwise quarter turns seen from above (north -> east -> south -> west).
mirror = 'x' flips east<->west (front-back for a north-south axis), 'z' flips north<->south.
Handled properties: facing, axis, rotation (16-step), north/east/south/west (booleans, wall shapes, redstone sides),
rail shape, orientation (crafter/jigsaw), hinge / chest type / stair shape under mirroring.
"""
from __future__ import annotations
from functools import lru_cache
from .registry import State, make, CW, OPPOSITE

H = ('north', 'east', 'south', 'west')


def rot_dir(d, turns):
    if d not in CW:
        return d
    for _ in range(turns % 4):
        d = CW[d]
    return d


def mirror_dir(d, axis):
    if axis == 'x' and d in ('east', 'west'):
        return OPPOSITE[d]
    if axis == 'z' and d in ('north', 'south'):
        return OPPOSITE[d]
    return d


def _rail(shape, f):
    """Rail shapes are pairs of directions ('north_south', 'ascending_east', 'south_east')."""
    if shape.startswith('ascending_'):
        return 'ascending_' + f(shape[len('ascending_'):])
    a, b = shape.split('_')
    a, b = f(a), f(b)
    order = {'north': 0, 'south': 1, 'east': 2, 'west': 3}
    if order[a] > order[b] and not (a in ('north', 'south') and b in ('north', 'south')):
        a, b = b, a
    cand = f'{a}_{b}'
    return cand if cand in RAIL_SHAPES else f'{b}_{a}'


RAIL_SHAPES = {'north_south', 'east_west', 'ascending_east', 'ascending_west', 'ascending_north', 'ascending_south',
               'south_east', 'south_west', 'north_west', 'north_east'}


def _transform(st: State, f, mirror_axis=None, rot16=None):
    p = st.props
    out = dict(p)
    if 'facing' in p:
        out['facing'] = f(p['facing'])
    if 'axis' in p and p['axis'] in ('x', 'z') and f('east') in ('north', 'south'):
        out['axis'] = 'z' if p['axis'] == 'x' else 'x'
    if 'rotation' in p and rot16 is not None:
        out['rotation'] = str(rot16(int(p['rotation'])) % 16)
    sides = [d for d in H if d in p]
    if len(sides) == 4:
        for d in H:
            out[f(d)] = p[d]
    if 'shape' in p and p['shape'] in RAIL_SHAPES:
        out['shape'] = _rail(p['shape'], f)
    if 'orientation' in p:
        a, b = p['orientation'].split('_')
        out['orientation'] = f'{f(a)}_{f(b)}'
    if mirror_axis:
        if 'hinge' in p:
            out['hinge'] = {'left': 'right', 'right': 'left'}[p['hinge']]
        if st.short in ('chest', 'trapped_chest') and p.get('type') in ('left', 'right'):
            out['type'] = {'left': 'right', 'right': 'left'}[p['type']]
        if 'shape' in p and p['shape'] in ('inner_left', 'inner_right', 'outer_left', 'outer_right'):
            out['shape'] = {'inner_left': 'inner_right', 'inner_right': 'inner_left',
                            'outer_left': 'outer_right', 'outer_right': 'outer_left'}[p['shape']]
    return make(st.name, out)


@lru_cache(maxsize=None)
def rotate_state(st: State, turns: int) -> State:
    turns %= 4
    if not turns or not st[1]:
        return st
    return _transform(st, lambda d: rot_dir(d, turns), rot16=lambda r: r + 4 * turns)


@lru_cache(maxsize=None)
def mirror_state(st: State, axis: str) -> State:
    if not axis or not st[1]:
        return st
    rot16 = (lambda r: (16 - r)) if axis == 'x' else (lambda r: (8 - r))
    return _transform(st, lambda d: mirror_dir(d, axis), mirror_axis=axis, rot16=rot16)


def rotate_vec(lx, lz, turns):
    """Local (x, z) offset -> world offset after `turns` clockwise quarter turns."""
    for _ in range(turns % 4):
        lx, lz = -lz, lx
    return lx, lz
