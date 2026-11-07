"""Finishing pass: give every design cell the state the game itself would compute from its neighbours.

Litematica pastes states verbatim and its verifier compares them exactly, so a pane that the game would connect
but the schematic leaves unconnected shows up as "wrong state" and looks broken. Mirrors vanilla rules for:
stair shapes, pane / iron-bar / fence / wall / fence-gate connections, waterlogging from the real water,
leaf distance (BFS from logs), snowy grass/podzol/mycelium.
"""
from __future__ import annotations
from .registry import (AIR, OFFSET, OPPOSITE, CCW, HORIZONTAL, is_stairs, is_pane_like, is_fence, is_wall, is_fence_gate,
                       is_leaves, is_log, face_sturdy, cannot_connect, in_tag, facts)


def _nb(p, d):
    o = OFFSET[d]
    return (p[0] + o[0], p[1] + o[1], p[2] + o[2])


def stair_shape(get, p, st):
    """StairsBlock.getStairShape."""
    f, half = st.get('facing'), st.get('half')
    a = get(_nb(p, f))

    def different(dirn):
        n = get(_nb(p, dirn))
        return not is_stairs(n) or n.get('facing') != f or n.get('half') != half

    if is_stairs(a) and a.get('half') == half and a.get('facing') not in (f, OPPOSITE[f]) and different(OPPOSITE[a.get('facing')]):
        return 'outer_left' if a.get('facing') == CCW[f] else 'outer_right'
    b = get(_nb(p, OPPOSITE[f]))
    if is_stairs(b) and b.get('half') == half and b.get('facing') not in (f, OPPOSITE[f]) and different(b.get('facing')):
        return 'inner_left' if b.get('facing') == CCW[f] else 'inner_right'
    return 'straight'


def _gate_aligned(n, d):
    """FenceGateBlock.canWallConnect: the gate's facing axis is perpendicular to the connection direction."""
    if not is_fence_gate(n):
        return False
    return (n.get('facing') in ('north', 'south')) == (d in ('east', 'west'))


def pane_connects(st, n, d):
    return (not cannot_connect(n) and face_sturdy(n, OPPOSITE[d])) or is_pane_like(n) or is_wall(n)


def fence_connects(st, n, d):
    wooden = in_tag(st, 'minecraft:wooden_fences')
    matching = in_tag(n, 'minecraft:fences') and in_tag(n, 'minecraft:wooden_fences') == wooden
    return (not cannot_connect(n) and face_sturdy(n, OPPOSITE[d])) or matching or _gate_aligned(n, d)


def wall_connects(st, n, d):
    return in_tag(n, 'minecraft:walls') or (not cannot_connect(n) and face_sturdy(n, OPPOSITE[d])) or is_pane_like(n) or _gate_aligned(n, d)


def wall_state(get, p, st):
    above = get(_nb(p, 'up'))
    full_above = facts(above).face_full('down')
    sides = {}
    for d in HORIZONTAL:
        if not wall_connects(st, get(_nb(p, d)), d):
            sides[d] = 'none'
        elif full_above or (is_wall(above) and above.get(d) != 'none'):
            sides[d] = 'tall'
        else:
            sides[d] = 'low'
    n, s, e, w = (sides[k] for k in ('north', 'south', 'east', 'west'))
    if is_wall(above) and above.get('up') == 'true':
        up = True
    elif (n == s == e == w == 'none') or ((n == 'none') != (s == 'none')) or ((e == 'none') != (w == 'none')):
        up = True
    elif (n == 'tall' and s == 'tall') or (e == 'tall' and w == 'tall'):
        up = False
    else:
        up = in_tag(above, 'minecraft:wall_post_override') or facts(above).face_center('down')
    return st.with_(up=up, **sides)


def resolve(B, stairs=True, connections=True, waterlog=True, leaves=True, snowy=True):
    get = B.getw
    changed = 0

    def setp(p, new):
        nonlocal changed
        if B.cells[p] != new:
            B.cells[p] = new
            changed += 1

    if stairs:
        for p, st in list(B.cells.items()):
            if is_stairs(st):
                setp(p, st.with_(shape=stair_shape(get, p, st)))
    if connections:
        for p, st in list(B.cells.items()):
            if is_pane_like(st):
                setp(p, st.with_(**{d: pane_connects(st, get(_nb(p, d)), d) for d in HORIZONTAL}))
            elif is_fence(st):
                setp(p, st.with_(**{d: fence_connects(st, get(_nb(p, d)), d) for d in HORIZONTAL}))
        for p in sorted((p for p, st in B.cells.items() if is_wall(st)), key=lambda q: -q[1]):      # top-down: posts depend on the wall above
            setp(p, wall_state(get, p, B.cells[p]))
        for p, st in list(B.cells.items()):
            if is_fence_gate(st):
                axis_z = st.get('facing') in ('north', 'south')
                sides = ('west', 'east') if axis_z else ('north', 'south')
                setp(p, st.with_(in_wall=any(is_wall(get(_nb(p, d))) for d in sides)))
    if waterlog and B.site is not None:
        for p, st in list(B.cells.items()):
            if st.has('waterlogged') and st.get('waterlogged') == 'false' and B.site.is_water(*p):
                setp(p, st.with_(waterlogged='true'))
    if leaves:
        lv = {p for p, st in B.cells.items() if is_leaves(st)}
        dist = {p: 7 for p in lv}
        frontier = []
        for p in lv:
            for d in OFFSET:
                if is_log(get(_nb(p, d))):
                    dist[p] = 1; frontier.append(p); break
        while frontier:
            nxt = []
            for p in frontier:
                for d in OFFSET:
                    q = _nb(p, d)
                    if q in dist and dist[q] > dist[p] + 1:
                        dist[q] = dist[p] + 1; nxt.append(q)
            frontier = nxt
        for p in lv:
            setp(p, B.cells[p].with_(distance=min(7, dist[p])))
    if snowy:
        for p, st in list(B.cells.items()):
            if st.has('snowy') and st.short in ('grass_block', 'podzol', 'mycelium'):
                setp(p, st.with_(snowy=in_tag(get(_nb(p, 'up')), 'minecraft:snow')))
    return changed
