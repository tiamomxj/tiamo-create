"""Block light and sky light on a voxel grid, following the vanilla engine closely enough for spawn-proofing checks
and preview shading: emission and opacity from the game's facts, max(1, opacity) loss per step, opaque full cubes
stop light, and slabs/stairs-like blocks ("sided transparency") stop it only through their full faces.

grid: int array [y, z, x] of indices into `states`. Returns int16 arrays of the same shape.
"""
from __future__ import annotations
import numpy as np
from .registry import AIR, facts

# axis order of the grid is (y, z, x); direction -> (axis, step)
DIRS = {'up': (0, 1), 'down': (0, -1), 'south': (1, 1), 'north': (1, -1), 'east': (2, 1), 'west': (2, -1)}
OPP = {'up': 'down', 'down': 'up', 'south': 'north', 'north': 'south', 'east': 'west', 'west': 'east'}


def tables(states):
    n = len(states)
    emit = np.zeros(n, np.int16); cost = np.ones(n, np.int16); skyop = np.zeros(n, np.int16)
    occl = {d: np.zeros(n, bool) for d in DIRS}
    for i, st in enumerate(states):
        if st == AIR:
            continue
        f = facts(st)
        emit[i] = f.lum
        op = 15 if f.opaque else f.opacity
        cost[i] = max(1, op)
        skyop[i] = op
        for d in DIRS:
            occl[d][i] = f.light_blocks(d)
    return emit, cost, skyop, occl


def _shift(a, axis, step, fill=0):
    """out[p] = a[p - step along axis] (value arriving from the neighbour behind)."""
    out = np.full_like(a, fill)
    src = [slice(None)] * 3; dst = [slice(None)] * 3
    if step > 0:
        dst[axis] = slice(1, None); src[axis] = slice(0, -1)
    else:
        dst[axis] = slice(0, -1); src[axis] = slice(1, None)
    out[tuple(dst)] = a[tuple(src)]
    return out


def _relax(L, base, cost_g, occ_g, iters=15):
    allowed = {}
    for d, (axis, step) in DIRS.items():
        # light moving in direction d enters p from q = p - step: blocked by q's face d or p's opposite face
        allowed[d] = ~(_shift(occ_g[d], axis, step, False) | occ_g[OPP[d]])
    for _ in range(iters):
        M = L.copy()
        for d, (axis, step) in DIRS.items():
            src = _shift(L, axis, step, 0)
            np.maximum(M, np.where(allowed[d], src - cost_g, 0), out=M)
        np.maximum(M, base, out=M)
        if np.array_equal(M, L):
            break
        L = M
    return L


def block_light(grid, states, tabs=None):
    emit, cost, _, occl = tabs or tables(states)
    base = emit[grid]
    occ_g = {d: occl[d][grid] for d in DIRS}
    return _relax(base.copy(), base, cost[grid], occ_g).clip(0, 15)


def sky_light(grid, states, tabs=None, top_open=True):
    """Sky light (15 = open sky). Straight-down columns lose only the opacity of the blocks they pass, then spread."""
    emit, cost, skyop, occl = tabs or tables(states)
    H = grid.shape[0]
    op = skyop[grid]
    occ_up = occl['up'][grid]; occ_down = occl['down'][grid]
    S = np.zeros(grid.shape, np.int16)
    col = np.full(grid.shape[1:], 15 if top_open else 0, np.int16)
    for y in range(H - 1, -1, -1):
        if y < H - 1:
            col = np.where(occ_down[y + 1] | occ_up[y], 0, col)
        col = np.maximum(col - op[y], 0)
        S[y] = col
    occ_g = {d: occl[d][grid] for d in DIRS}
    return _relax(S.copy(), S, cost[grid], occ_g).clip(0, 15)
