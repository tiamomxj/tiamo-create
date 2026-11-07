"""Write a vanilla Java save holding the site terrain (optionally with the design already placed = showcase world).

Chunks cover the site box (stone below it, air above), real biomes per 4x4x4 cell, block entities from the
game's facts, heightmaps; everything outside is void (flat generator with an air layer) so the save stays small.
Game rules freeze time/weather/mobs for clean screenshots.
"""
from __future__ import annotations
import io, math, struct, time, zlib
from pathlib import Path
import numpy as np
from . import nbt
from .nbt import Compound as C, List as L, String as S, Int as I, Byte as B, Long as G, Float as F, IntArray as IA, LongArray as LA, Short as SH
from .registry import AIR, facts, version
from .terrain import MISSING
from .util import data_dir, meta, log


def _packed(a, bits):
    a = np.asarray(a, np.uint64).ravel(); per = 64 // bits
    out = np.zeros(math.ceil(len(a) / per) * per, np.uint64); out[:len(a)] = a
    out = np.bitwise_or.reduce(out.reshape(-1, per) << (np.arange(per, dtype=np.uint64)[None, :] * np.uint64(bits)), axis=1)
    return LA(out.view(np.int64))


def write_world(out: Path, site, build=None, name='mcbuild test', spawn=None, margin_chunks=1, game_type=1, day_time=1000,
                min_y=-64, height=384):
    out = Path(out)
    (out / 'region').mkdir(parents=True, exist_ok=True)
    dv = meta(version())['data_version']
    x0, y0, z0, x1, y1, z1 = site.box
    if build is not None and build.cells:
        (bx0, by0, bz0), (bx1, by1, bz1) = build.bbox()
        x0, z0, x1, z1 = min(x0, bx0), min(z0, bz0), max(x1, bx1 + 1), max(z1, bz1 + 1)
    cx0, cz0 = (x0 >> 4) - margin_chunks + 1, (z0 >> 4) - margin_chunks + 1
    cx1, cz1 = ((x1 - 1) >> 4) + margin_chunks - 1, ((z1 - 1) >> 4) + margin_chunks - 1
    # global palette over site states + design states
    states, index = [AIR], {AIR: 0}

    def sid(st):
        i = index.get(st)
        if i is None:
            i = index[st] = len(states); states.append(st)
        return i
    used, sts = site.palette_states()
    lut = np.zeros((max(used) + 2) if used else 2, np.int32)
    for i, st in zip(used, sts):
        lut[i] = sid(st)
    stone = sid(_stone())
    world = lut[np.where(site.IDS == MISSING, len(lut) - 1, site.IDS).astype(np.int64)]
    world[site.IDS == MISSING] = 0
    if build is not None:
        for (x, y, z), st in build.cells.items():
            if site.contains(x, y, z):
                world[y - site.Y0, z - site.Z0, x - site.X0] = sid(st)
    extra = {p: st for p, st in (build.cells.items() if build is not None else []) if not site.contains(*p)}
    bnames = {int(k): v for k, v in site.biome_names.items()} if site.biome_names else {}
    nbt_states = [C({'Name': S(s.name), **({'Properties': C({k: S(v) for k, v in s[1]})} if s[1] else {})}) for s in states]
    be_ids = [facts(s).be if s != AIR else None for s in states]
    transparent = np.array([s == AIR or not facts(s).boxes for s in states], bool)
    default_biome = bnames.get(int(np.bincount(site.biomes.ravel()).argmax()), 'minecraft:plains') if bnames else 'minecraft:plains'
    total = 0

    def chunk(cx, cz):
        a = np.zeros((height, 16, 16), np.int32)
        bio = np.full((height // 4, 4, 4), -1, np.int32)
        sy0 = site.Y0 - min_y
        a[0:max(0, sy0)] = stone
        xs, zs = cx * 16 - site.X0, cz * 16 - site.Z0
        xa, xb = max(0, xs), min(site.W, xs + 16)
        za, zb = max(0, zs), min(site.D, zs + 16)
        if xa < xb and za < zb:
            ya, yb = max(0, -sy0), min(site.H, height - sy0)
            a[sy0 + ya:sy0 + yb, za - zs:zb - zs, xa - xs:xb - xs] = world[ya:yb, za:zb, xa:xb]
            if bnames:
                for qy in range((sy0 + ya) // 4, (sy0 + yb + 3) // 4):
                    for qz in range(4):
                        for qx in range(4):
                            wy, wz, wx = qy * 4 + 2 - sy0, zs + qz * 4 + 2, xs + qx * 4 + 2
                            if 0 <= wy < site.H and 0 <= wz < site.D and 0 <= wx < site.W:
                                bio[qy, qz, qx] = int(site.biomes[wy, wz, wx])
        for (x, y, z), st in extra.items():
            if x >> 4 == cx and z >> 4 == cz and min_y <= y < min_y + height:
                a[y - min_y, z & 15, x & 15] = sid(st)
        secs = []
        for sy in range(min_y // 16, (min_y + height) // 16):
            k = sy - min_y // 16
            slab = a[k * 16:(k + 1) * 16]
            u, inv = np.unique(slab, return_inverse=True)
            d = C({'palette': L([nbt_states[int(b)] for b in u], 10)})
            if len(u) > 1:
                d['data'] = _packed(inv, max(4, (len(u) - 1).bit_length()))
            bq = bio[k * 4:(k + 1) * 4]
            names = [bnames.get(int(v), default_biome) if v >= 0 else default_biome for v in bq.ravel()]
            bu = sorted(set(names))
            bd = C({'palette': L([S(n) for n in bu], 8)})
            if len(bu) > 1:
                bd['data'] = _packed([bu.index(n) for n in names], max(1, (len(bu) - 1).bit_length()))
            secs.append(C({'Y': B(sy), 'block_states': d, 'biomes': bd}))
        occ = a != 0
        highest = np.where(occ.any(axis=0), height - np.argmax(occ[::-1], axis=0), 0)
        solid = occ & ~transparent[a]
        motion = np.where(solid.any(axis=0), height - np.argmax(solid[::-1], axis=0), 0)
        bes = []
        for yy, zz, xx in zip(*np.nonzero(a)):
            b = be_ids[a[yy, zz, xx]]
            if b:
                bes.append(C({'id': S(b), 'x': I(cx * 16 + int(xx)), 'y': I(int(yy) + min_y), 'z': I(cz * 16 + int(zz)), 'keepPacked': B(0)}))
        hb = max(1, (height).bit_length())
        d = C({'DataVersion': I(dv), 'xPos': I(cx), 'zPos': I(cz), 'yPos': I(min_y // 16), 'Status': S('minecraft:full'),
               'LastUpdate': G(0), 'InhabitedTime': G(0), 'isLightOn': B(0), 'sections': L(secs, 10), 'block_entities': L(bes, 10),
               'fluid_ticks': L([], 10), 'block_ticks': L([], 10), 'PostProcessing': L([L([], 2) for _ in range(height // 16)], 9),
               'Heightmaps': C({'WORLD_SURFACE': _packed(highest, hb), 'MOTION_BLOCKING': _packed(motion, hb),
                                'MOTION_BLOCKING_NO_LEAVES': _packed(motion, hb), 'OCEAN_FLOOR': _packed(motion, hb)}),
               'structures': C({'starts': C({}), 'References': C({})})})
        return zlib.compress(nbt.dumps(d), 6)

    for rx in range(cx0 >> 5, (cx1 >> 5) + 1):
        for rz in range(cz0 >> 5, (cz1 >> 5) + 1):
            header = bytearray(8192); body = bytearray(); sector = 2; count = 0
            for lz in range(32):
                for lx in range(32):
                    cx, cz = rx * 32 + lx, rz * 32 + lz
                    if not (cx0 <= cx <= cx1 and cz0 <= cz <= cz1):
                        continue
                    payload = chunk(cx, cz)
                    payload = struct.pack('>I', len(payload) + 1) + b'\x02' + payload
                    n = math.ceil(len(payload) / 4096); idx = lx + lz * 32
                    header[idx * 4:idx * 4 + 4] = bytes([(sector >> 16) & 255, (sector >> 8) & 255, sector & 255, n])
                    header[4096 + idx * 4:4100 + idx * 4] = struct.pack('>I', int(time.time()))
                    body.extend(payload); body.extend(bytes(n * 4096 - len(payload))); sector += n; count += 1
            if count:
                (out / 'region' / f'r.{rx}.{rz}.mca').write_bytes(bytes(header) + bytes(body)); total += count
    level = nbt.load(data_dir(version()) / 'world-template.dat')
    d = level['Data']
    d['LevelName'] = S(name); d['GameType'] = I(game_type); d['allowCommands'] = B(1); d['Difficulty'] = B(0)
    d['DayTime'] = G(day_time); d['Time'] = G(0); d['LastPlayed'] = G(int(time.time() * 1000)); d['WasModded'] = B(0)
    for k in ('Player', 'WanderingTraderId'):
        d.pop(k, None)
    sx, sy, sz = spawn or ((x0 + x1) // 2, site.ground_top((x0 + x1) // 2, (z0 + z1) // 2) + 1, (z0 + z1) // 2)
    d['spawn'] = C({'pos': IA([sx, sy, sz]), 'pitch': F(0), 'yaw': F(180), 'dimension': S('minecraft:overworld')})
    d['DataPacks'] = C({'Enabled': L([S('vanilla')], 8), 'Disabled': L([], 8)})
    d['raining'] = B(0); d['thundering'] = B(0); d['clearWeatherTime'] = I(2147483647)
    gr = d.get('game_rules')
    if gr is not None:
        for k in ('advance_time', 'advance_weather', 'spawn_mobs', 'spawn_patrols', 'spawn_phantoms', 'spawn_wandering_traders', 'mob_griefing'):
            gr['minecraft:' + k] = B(0)
        gr['minecraft:random_tick_speed'] = I(0)
    w = d['WorldGenSettings']; w['generate_features'] = B(0); w['bonus_chest'] = B(0)
    w['dimensions']['minecraft:overworld']['generator'] = C({'type': S('minecraft:flat'), 'settings': C({
        'features': B(0), 'lakes': B(0), 'biome': S('minecraft:plains'), 'structure_overrides': L([], 8),
        'layers': L([C({'block': S('minecraft:air'), 'height': I(1)})], 10)})})
    nbt.save(out / 'level.dat', level)
    log('WORLD', out, 'chunks', total, 'states', len(states))
    return out


def _stone():
    from .registry import parse
    return parse('stone')
