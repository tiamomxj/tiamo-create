"""Schematic files: Litematica .litematic (write/read), Sponge .schem v3 (write/read), vanilla structure .nbt (read).

Litematica v7 (1.21.x): BlockStates are packed CONTINUOUSLY across longs (not chunk-style long-aligned),
bits = max(2, ceil(log2(palette size))), index = (y * sizeZ + z) * sizeX + x, palette[0] = air.
Tile entities: minimal {id, x, y, z, components: {}} (region-relative) — accepted by Litematica 0.2x.

Site-fitted export (mode 'site'): the build's cells are partitioned into tight, non-overlapping boxes (k-d split
on the cost of copied terrain); inside a box every cell the design does not set is COPIED from the real terrain,
so Litematica's overlay only flags what really has to be placed/removed. Mode 'portable': no terrain, one box.
"""
from __future__ import annotations
import math, time
from pathlib import Path
import numpy as np
from . import nbt
from .nbt import Compound as C, List as L, Int as I, Long as G, String as S, LongArray as LA, IntArray as IA, Short as SH
from .registry import AIR, State, from_nbt, facts, make, version
from .util import meta


# ------------------------------------------------------------------ bit packing
def pack(values, bits):
    v = np.asarray(values, np.uint64).ravel()
    i = np.arange(len(v), dtype=np.uint64) * np.uint64(bits)
    wi = (i // np.uint64(64)).astype(np.int64); sh = i % np.uint64(64)
    out = np.zeros((len(v) * bits + 63) // 64, np.uint64)
    np.bitwise_or.at(out, wi, v << sh)
    cross = sh + np.uint64(bits) > np.uint64(64)
    np.bitwise_or.at(out, wi[cross] + 1, v[cross] >> (np.uint64(64) - sh[cross]))
    return out.view(np.int64)


def unpack(longs, n, bits):
    w = np.asarray(longs, np.int64).view(np.uint64)
    i = np.arange(n, dtype=np.uint64) * np.uint64(bits)
    wi = (i // np.uint64(64)).astype(np.int64); sh = i % np.uint64(64)
    mask = np.uint64((1 << bits) - 1)
    v = w[wi] >> sh
    cross = sh + np.uint64(bits) > np.uint64(64)
    nxt = np.zeros_like(v)
    idx = np.nonzero(cross)[0]
    nxt[idx] = w[wi[idx] + 1] << (np.uint64(64) - sh[idx])
    return ((v | nxt) & mask).astype(np.int64)


def nbt_state(st: State, rename=None):
    d = C({'Name': S((rename or {}).get(st.name, st.name))})
    if st[1]:
        d['Properties'] = C({k: S(v) for k, v in st[1]})
    return d


def xyz(v):
    return C({'x': I(v[0]), 'y': I(v[1]), 'z': I(v[2])})


def be_id(st: State):
    return facts(st).be if st != AIR else None


# ------------------------------------------------------------------ region planning
def plan_regions(cells, cost_at, penalty=20.0, trace=None, max_size=None):
    """k-d partition of the design positions into non-overlapping boxes.
    cost_at(lo, hi) -> np.float32 array [y, z, x] of the cost of copying each non-design cell in the bbox.
    A box is split on the axis plane that lowers the summed cost most, while that saves more than `penalty`."""
    P = np.array(sorted(cells), dtype=np.int64)
    lo0, hi0 = P.min(0), P.max(0)
    cost = cost_at(lo0, hi0)
    for (x, y, z) in P:
        cost[y - lo0[1], z - lo0[2], x - lo0[0]] = 0
    sat = np.zeros((cost.shape[0] + 1, cost.shape[1] + 1, cost.shape[2] + 1), np.float64)
    sat[1:, 1:, 1:] = cost.cumsum(0).cumsum(1).cumsum(2)

    def box_cost(lo, hi):
        (x0, y0, z0), (x1, y1, z1) = lo - lo0, hi - lo0 + 1
        s = sat
        return (s[y1, z1, x1] - s[y0, z1, x1] - s[y1, z0, x1] - s[y1, z1, x0]
                + s[y0, z0, x1] + s[y0, z1, x0] + s[y1, z0, x0] - s[y0, z0, x0])

    leaves = []

    def split(idx):
        Q = P[idx]
        lo, hi = Q.min(0), Q.max(0)
        c = box_cost(lo, hi)
        best = None
        for ax in range(3):
            order = np.argsort(Q[:, ax], kind='stable')
            vals = Q[order, ax]
            cut = np.nonzero(np.diff(vals))[0]
            if not len(cut):
                continue
            fmin = np.minimum.accumulate(Q[order], 0); fmax = np.maximum.accumulate(Q[order], 0)
            bmin = np.minimum.accumulate(Q[order][::-1], 0)[::-1]; bmax = np.maximum.accumulate(Q[order][::-1], 0)[::-1]
            for i in cut:
                t = box_cost(fmin[i], fmax[i]) + box_cost(bmin[i + 1], bmax[i + 1])
                if best is None or t < best[0]:
                    best = (t, ax, order[:i + 1], order[i + 1:])
        too_big = max_size and max(hi - lo + 1) > max_size
        if best is not None and (c - best[0] > penalty or too_big):
            if too_big and c - best[0] <= penalty:                # forced split on the longest axis, at the middle
                ax = int(np.argmax(hi - lo))
                mid = (lo[ax] + hi[ax]) // 2
                a, b = np.nonzero(Q[:, ax] <= mid)[0], np.nonzero(Q[:, ax] > mid)[0]
                if len(a) and len(b):
                    best = (None, ax, a, b)
            if trace is not None:
                trace.append({'lo': lo.tolist(), 'hi': hi.tolist(), 'cost': float(c), 'axis': int(best[1]),
                              'a': [P[idx[best[2]]].min(0).tolist(), P[idx[best[2]]].max(0).tolist()],
                              'b': [P[idx[best[3]]].min(0).tolist(), P[idx[best[3]]].max(0).tolist()]})
            split(idx[best[2]]); split(idx[best[3]])
        else:
            leaves.append({'cells': [tuple(map(int, q)) for q in Q], 'lo': [int(v) for v in lo], 'hi': [int(v) for v in hi],
                           'cost': float(c)})

    split(np.arange(len(P)))
    return leaves


def terrain_cost_fn(site):
    """Copy cost per cell: air 0, plants 0.3, anything else 1 (water, terrain, trees, builds)."""
    from .terrain import kind
    lut = site.lut(lambda st: {'air': 0, 'plant': 3}.get(kind(st), 10), np.uint8) if site is not None else None

    def cost_at(lo, hi):
        shape = (hi[1] - lo[1] + 1, hi[2] - lo[2] + 1, hi[0] - lo[0] + 1)
        out = np.zeros(shape, np.float32)
        if lut is None:
            return out
        # intersect with the site grid
        sx0, sy0, sz0 = site.X0, site.Y0, site.Z0
        x0, x1 = max(lo[0], sx0), min(hi[0] + 1, sx0 + site.W)
        y0, y1 = max(lo[1], sy0), min(hi[1] + 1, sy0 + site.H)
        z0, z1 = max(lo[2], sz0), min(hi[2] + 1, sz0 + site.D)
        if x0 < x1 and y0 < y1 and z0 < z1:
            out[y0 - lo[1]:y1 - lo[1], z0 - lo[2]:z1 - lo[2], x0 - lo[0]:x1 - lo[0]] = \
                lut[y0 - sy0:y1 - sy0, z0 - sz0:z1 - sz0, x0 - sx0:x1 - sx0].astype(np.float32) / 10
        return out
    return cost_at


# ------------------------------------------------------------------ litematic
def export_litematic(build, path, mode='site', name='build', author='mcbuild', description='', penalty=20.0,
                     part_names=None, max_size=None, trace=None, target=None):
    """Write the design as a .litematic. Returns a report dict (origin = Litematica placement position).
    target: game version the file is for (older than the bundled data: its DataVersion and old block names)."""
    from .compat import write_renames, data_version
    rename = write_renames(target, version())
    site = build.site if mode == 'site' else None
    part_names = part_names or {}
    cells = list(build.cells)
    if not cells:
        raise SystemExit('the design is empty')
    if mode == 'site' and site is not None:
        boxes = plan_regions(cells, terrain_cost_fn(site), penalty, trace, max_size)
    else:
        boxes = plan_regions(cells, lambda lo, hi: np.zeros((hi[1] - lo[1] + 1, hi[2] - lo[2] + 1, hi[0] - lo[0] + 1), np.float32),
                             penalty, trace, max_size)
    order = {p: i for i, p in enumerate(build.cells)}          # name parts in design order (stable tie-breaks)
    for b in boxes:
        parts = {}
        for p in sorted(b['cells'], key=order.__getitem__):
            k = build.part.get(p, 'main')
            parts[k] = parts.get(k, 0) + 1
        b['names'] = [k for k, _ in sorted(parts.items(), key=lambda kv: -kv[1])]
    lo = [min(b['lo'][k] for b in boxes) for k in range(3)]
    hi = [max(b['hi'][k] for b in boxes) for k in range(3)]

    def content(p):
        st = build.cells.get(p)
        if st is not None:
            return st
        return site.world(*p) if site is not None else AIR

    regions, used, report = C({}), set(), []
    total_blocks = total_volume = 0
    for b in sorted(boxes, key=lambda b: -math.prod(b['hi'][k] - b['lo'][k] + 1 for k in range(3))):
        (x0, y0, z0), (x1, y1, z1) = b['lo'], b['hi']
        sx, sy, sz = x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1
        palette, idx = [AIR], {AIR: 0}
        arr = np.zeros(sx * sy * sz, np.int64)
        tes, copied = [], {}
        for y in range(sy):
            for z in range(sz):
                for x in range(sx):
                    p = (x0 + x, y0 + y, z0 + z)
                    st = content(p)
                    if p not in build.cells and st != AIR:
                        copied[st.short] = copied.get(st.short, 0) + 1
                    i = idx.get(st)
                    if i is None:
                        i = idx[st] = len(palette); palette.append(st)
                    arr[(y * sz + z) * sx + x] = i
                    bid = be_id(st)
                    if bid:
                        tes.append(C({'x': I(x), 'y': I(y), 'z': I(z), 'id': S(bid), 'components': C({})}))
        bits = max(2, (len(palette) - 1).bit_length())
        rname = region_name(b['names'], used, part_names)
        nonair = int(np.count_nonzero(arr))
        regions[rname] = C({'Position': xyz([x0 - lo[0], y0 - lo[1], z0 - lo[2]]), 'Size': xyz([sx, sy, sz]),
                            'BlockStatePalette': L([nbt_state(s, rename) for s in palette], 10), 'BlockStates': LA(pack(arr, bits)),
                            'TileEntities': L(tes, 10), 'Entities': L([], 10), 'PendingBlockTicks': L([], 10),
                            'PendingFluidTicks': L([], 10)})
        total_blocks += nonair; total_volume += sx * sy * sz
        report.append({'name': rname, 'parts': b['names'], 'min': [x0, y0, z0], 'size': [sx, sy, sz], 'blocks': nonair,
                       'palette': len(palette), 'bits': bits, 'tileEntities': len(tes), 'copiedFromWorld': copied})
    now = int(time.time() * 1000)
    size = [hi[k] - lo[k] + 1 for k in range(3)]
    if '{' in description:
        description = description.format(x=lo[0], y=lo[1], z=lo[2], sx=size[0], sy=size[1], sz=size[2])
    m = meta(version())
    dv = data_version(target, version(), m['data_version'])
    md = C({'Name': S(name), 'Author': S(author), 'Description': S(description), 'RegionCount': I(len(regions)),
            'TotalVolume': I(total_volume), 'TotalBlocks': I(total_blocks), 'TimeCreated': G(now), 'TimeModified': G(now),
            'EnclosingSize': xyz(size)})
    root = C({'MinecraftDataVersion': I(dv), 'Version': I(m.get('litematic_version', 7)),
              'SubVersion': I(m.get('litematic_subversion', 1)), 'Metadata': md, 'Regions': regions})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    nbt.save(path, root)
    return {'file': Path(path).name, 'mode': mode, 'origin': lo, 'max': hi, 'enclosingSize': size, 'regions': report,
            'totalBlocks': total_blocks, 'totalVolume': total_volume, 'dataVersion': dv, 'targetVersion': target or version(),
            'renamed': rename, 'version': m.get('litematic_version', 7), 'designCells': len(cells)}


def region_name(names, used, part_names):
    base = []
    for n in names:
        key = n.split('@')[0]
        zh = part_names.get(key, key)
        if zh not in base:
            base.append(zh)
    from .i18n import t
    name = '+'.join(base[:3]) + (t('region.etc') if len(base) > 3 else '')
    k, out = 1, name
    while out in used:
        k += 1; out = f'{name} {k}'
    used.add(out)
    return out


def read_litematic(path):
    """-> {'meta': {...}, 'version', 'dataVersion', 'regions': [{name, pos, size, palette[State], index(np [y,z,x]),
    tiles}]} — positions normalised so negative sizes (Litematica allows them) are handled."""
    root = nbt.load(path)
    regions = []
    for rname, r in root['Regions'].items():
        pos = [int(r['Position'][k]) for k in 'xyz']; size = [int(r['Size'][k]) for k in 'xyz']
        for k in range(3):                        # negative size: region extends toward negative axis
            if size[k] < 0:
                pos[k] += size[k] + 1; size[k] = -size[k]
        pal = [from_nbt({'Name': str(e['Name']), 'Properties': {k: str(v) for k, v in e.get('Properties', {}).items()}})
               for e in r['BlockStatePalette']]
        bits = max(2, (len(pal) - 1).bit_length())
        vol = size[0] * size[1] * size[2]
        idx = unpack(r['BlockStates'], vol, bits).reshape(size[1], size[2], size[0])
        regions.append({'name': rname, 'pos': pos, 'size': size, 'palette': pal, 'index': idx, 'bits': bits,
                        'longs': len(r['BlockStates']), 'tiles': [nbt.plain(t) for t in r.get('TileEntities', [])]})
    return {'meta': nbt.plain(root['Metadata']), 'version': int(root['Version']), 'subVersion': int(root.get('SubVersion', 0)),
            'dataVersion': int(root.get('MinecraftDataVersion', 0)), 'regions': regions}


def litematic_cells(path_or_doc, skip_air=False):
    doc = read_litematic(path_or_doc) if not isinstance(path_or_doc, dict) else path_or_doc
    out = {}
    for r in doc['regions']:
        px, py, pz = r['pos']
        ys, zs, xs = np.indices(r['index'].shape)
        for y, z, x, i in zip(ys.ravel(), zs.ravel(), xs.ravel(), r['index'].ravel()):
            st = r['palette'][i]
            if skip_air and st == AIR:
                continue
            out[(px + int(x), py + int(y), pz + int(z))] = st
    return out


# ------------------------------------------------------------------ Sponge schematic v3 (WorldEdit / FAWE / Axiom)
def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def write_schem(path, build, origin=None, include_terrain=False, name='build', target=None):
    """Single box over the design; non-design cells are air (or the terrain if include_terrain). Offset = origin."""
    from .compat import write_renames, data_version
    rename = write_renames(target, version())
    (x0, y0, z0), (x1, y1, z1) = build.bbox()
    W, H, Ln = x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1
    pal, data, bes = {}, bytearray(), []
    for y in range(H):
        for z in range(Ln):
            for x in range(W):
                p = (x0 + x, y0 + y, z0 + z)
                st = build.cells.get(p)
                if st is None:
                    st = build.world(p) if include_terrain else AIR
                k = st.key()
                if st.name in rename:
                    k = rename[st.name] + k[len(st.name):]
                if k not in pal:
                    pal[k] = len(pal)
                data += _varint(pal[k])
                bid = be_id(st)
                if bid:
                    bes.append(C({'Pos': IA([x, y, z]), 'Id': S(bid), 'Data': C({})}))
    m = meta(version())
    sch = C({'Version': I(3), 'DataVersion': I(data_version(target, version(), m['data_version'])), 'Width': SH(W), 'Height': SH(H), 'Length': SH(Ln),
             'Offset': IA(list(origin or (x0, y0, z0))), 'Metadata': C({'Name': S(name), 'Date': G(int(time.time() * 1000)),
                                                                        'WEOffsetX': I(0), 'WEOffsetY': I(0), 'WEOffsetZ': I(0)}),
             'Blocks': C({'Palette': C({k: I(v) for k, v in pal.items()}), 'Data': nbt.ByteArray(np.frombuffer(bytes(data), np.uint8).view(np.int8)),
                          'BlockEntities': L(bes, 10)})})
    nbt.save(path, C({'Schematic': sch}))
    return {'file': Path(path).name, 'size': [W, H, Ln], 'palette': len(pal), 'blockEntities': len(bes)}


def read_schem(path):
    root = nbt.load(path)
    sch = root.get('Schematic', root)
    W, H, Ln = int(sch['Width']), int(sch['Height']), int(sch['Length'])
    blocks = sch.get('Blocks', sch)
    pal = {int(v): k for k, v in blocks['Palette'].items()}
    raw = np.asarray(blocks.get('Data', blocks.get('BlockData'))).view(np.uint8).tobytes()
    vals, i = [], 0
    while i < len(raw):
        v, s = 0, 0
        while True:
            b = raw[i]; i += 1
            v |= (b & 0x7F) << s; s += 7
            if not b & 0x80:
                break
        vals.append(v)
    out = {}
    from .registry import parse
    for n, v in enumerate(vals):
        y, rem = divmod(n, W * Ln); z, x = divmod(rem, W)
        out[(x, y, z)] = parse(pal[v])
    return out


def read_structure(path):
    """Vanilla structure-block .nbt."""
    root = nbt.load(path)
    pal = [from_nbt({'Name': str(e['Name']), 'Properties': {k: str(v) for k, v in e.get('Properties', {}).items()}})
           for e in root.get('palette', root.get('palettes', [[]])[0])]
    return {tuple(int(v) for v in b['pos']): pal[int(b['state'])] for b in root['blocks']}


def read_any(path):
    p = Path(path)
    if p.suffix == '.litematic':
        return litematic_cells(p)
    if p.suffix in ('.schem', '.schematic'):
        return read_schem(p)
    if p.suffix == '.nbt':
        return read_structure(p)
    raise SystemExit(f'unknown schematic format {p.suffix} (.litematic, .schem, .schematic, .nbt)')
