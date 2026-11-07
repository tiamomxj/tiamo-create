"""Block states, validated against the official registry of one game version, plus per-state facts and tags.

* `State` is an immutable (name, ((k, v), ...)) tuple with the FULL, sorted property set; `make/parse` validate it.
* `facts(st)` exposes what the game itself computes for that state (light, opacity, collision boxes, solid faces,
  spawnability, fluid, block entity type, item, map colour) — dumped by the harness (`mcb facts`).
* `in_tag(st, 'minecraft:logs')` uses the vanilla block tags of the same version.

Only one game version is active per process (set_version); the default is 1.21.11.
"""
from __future__ import annotations
import gzip, json
from functools import lru_cache
from .util import data_dir, data_json, data_path, DEFAULT_VERSION
from .compat import OLD_NAMES

HORIZONTAL = ('north', 'east', 'south', 'west')
DIRECTIONS = ('down', 'up', 'north', 'south', 'west', 'east')          # bit order of the facts face masks
OFFSET = {'north': (0, 0, -1), 'south': (0, 0, 1), 'west': (-1, 0, 0), 'east': (1, 0, 0), 'up': (0, 1, 0), 'down': (0, -1, 0)}
OPPOSITE = {'north': 'south', 'south': 'north', 'east': 'west', 'west': 'east', 'up': 'down', 'down': 'up'}
CW = {'north': 'east', 'east': 'south', 'south': 'west', 'west': 'north'}     # clockwise seen from above
CCW = {v: k for k, v in CW.items()}

_V = {'version': DEFAULT_VERSION}


def set_version(v):
    if v != _V['version']:
        _V['version'] = v
        for f in (_reg, _facts, _tags, _defaults, _valid_states, parse, facts, _names, _items, _class_sets):
            f.cache_clear()


def version():
    return _V['version']


@lru_cache(maxsize=None)
def _reg():
    return data_json(_V['version'], 'blocks.json')


@lru_cache(maxsize=None)
def _facts():
    p = data_dir(_V['version']) / 'facts.json.gz'
    if not p.exists():
        return None
    with gzip.open(p, 'rt', encoding='utf-8') as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _class_sets():
    f = _facts()
    return [frozenset(c) for c in f['classes']] if f else []


@lru_cache(maxsize=None)
def _tags():
    return {k: frozenset(v) for k, v in (data_json(_V['version'], 'tags.json') or {}).items()}


@lru_cache(maxsize=None)
def _names():
    """{'zh_cn': {...}, 'en_us': {...}}: block / item / biome names read from the player's own game files (names.py)."""
    from .names import tables
    return tables(_V['version'])


@lru_cache(maxsize=None)
def _items():
    return data_json(_V['version'], 'items.json') or {}


def block_names():
    return list(_reg())


def known(name):
    if ':' not in name:
        name = 'minecraft:' + name
    return name in _reg()


@lru_cache(maxsize=None)
def _defaults(name):
    entry = _reg()[name]
    for s in entry['states']:
        if s.get('default'):
            return dict(s.get('properties', {}))
    return dict(entry['states'][0].get('properties', {}))


@lru_cache(maxsize=None)
def _valid_states(name):
    return {tuple(sorted(s.get('properties', {}).items())) for s in _reg()[name]['states']}


def properties(name):
    """{property: [allowed values]} for a block."""
    if ':' not in name:
        name = 'minecraft:' + name
    return {k: list(v) for k, v in _reg()[name].get('properties', {}).items()}


class State(tuple):
    """Immutable (name, ((k, v), ...)) with full, validated properties."""
    __slots__ = ()

    def __new__(cls, name, props):
        return super().__new__(cls, (name, tuple(sorted(props.items()))))

    @property
    def name(self):
        return self[0]

    @property
    def short(self):
        return self[0].split(':', 1)[1]

    @property
    def props(self):
        return dict(self[1])

    def get(self, k, default=None):
        return dict(self[1]).get(k, default)

    def has(self, k):
        return any(kk == k for kk, _ in self[1])

    def with_(self, **kw):
        p = self.props
        for k, v in kw.items():
            if k not in p:
                raise KeyError(f'{self.name} has no property {k}')
            p[k] = str(v).lower() if isinstance(v, bool) else str(v)
        return make(self.name, p)

    def key(self):
        if not self[1]:
            return self.name
        return self.name + '[' + ','.join(f'{k}={v}' for k, v in self[1]) + ']'

    def props_key(self):
        return ','.join(f'{k}={v}' for k, v in self[1])

    def nbt(self):
        out = {'Name': self.name}
        if self[1]:
            out['Properties'] = dict(self[1])
        return out

    def __repr__(self):
        return f'<{self.key()}>'


def make(name, props=None):
    if ':' not in name:
        name = 'minecraft:' + name
    name = OLD_NAMES.get(name, name)          # ids from older saves/schematics (chain, grass) -> current ids
    reg = _reg()
    if name not in reg:
        raise KeyError(f'unknown block {name} (game {_V["version"]})')
    full = dict(_defaults(name))          # copy: the cached defaults must never be mutated
    for k, v in (props or {}).items():
        if k not in full:
            raise KeyError(f'{name} has no property {k}; has {sorted(full)}')
        full[k] = str(v).lower() if isinstance(v, bool) else str(v)
    st = State(name, full)
    if st[1] not in _valid_states(name):
        raise ValueError(f'invalid state {st.key()}')
    return st


@lru_cache(maxsize=None)
def parse(spec: str) -> State:
    """'oak_stairs[facing=east,half=top]' -> State (missing properties take the block's defaults)."""
    spec = spec.strip()
    if '[' in spec:
        name, rest = spec.split('[', 1)
        props = dict(p.split('=', 1) for p in rest.rstrip(']').split(',') if p)
    else:
        name, props = spec, {}
    return make(name, {k.strip(): v.strip() for k, v in props.items()})


def as_state(spec):
    return spec if isinstance(spec, State) else parse(spec)


def from_nbt(d):
    """{'Name':..., 'Properties':{...}} -> State; unknown/invalid states raise."""
    return make(d['Name'], d.get('Properties', {}))


AIR = parse('air')
AIR_NAMES = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'})


# ------------------------------------------------------------------ facts (from the game's own code)
class Facts:
    __slots__ = ('lum', 'opacity', 'flags', 'full', 'center', 'rigid', 'cull', 'boxes', 'map_color', 'hardness',
                 'item', 'be', 'classes')

    def __init__(self, row, boxes, item, be, classes):
        (self.lum, self.opacity, self.flags, self.full, self.center, self.rigid, self.cull, _, self.map_color,
         self.hardness) = row
        self.boxes, self.item, self.be, self.classes = boxes, item, be, classes

    opaque = property(lambda s: bool(s.flags & 1))            # isOpaqueFullCube: blocks light & culls neighbours
    solid_block = property(lambda s: bool(s.flags & 2))
    full_cube = property(lambda s: bool(s.flags & 4))
    replaceable = property(lambda s: bool(s.flags & 8))
    spawnable = property(lambda s: bool(s.flags & 16))       # a zombie may spawn standing on it (light permitting)
    has_be = property(lambda s: bool(s.flags & 32))
    solid = property(lambda s: bool(s.flags & 64))
    burnable = property(lambda s: bool(s.flags & 128))
    water = property(lambda s: bool(s.flags & 256))          # fluid state is water (incl. waterlogged / seagrass)
    lava = property(lambda s: bool(s.flags & 512))
    source = property(lambda s: bool(s.flags & 1024))
    blocks_movement = property(lambda s: bool(s.flags & 2048))
    skylight = property(lambda s: bool(s.flags & 4096))
    air = property(lambda s: bool(s.flags & 8192))
    opaque_material = property(lambda s: bool(s.flags & 32768))   # isOpaque (solid material, may be partial)
    sided = property(lambda s: bool(s.flags & 65536))            # hasSidedTransparency: light uses its face shapes

    def light_blocks(self, d):
        """Does this block's face toward d stop light (vanilla shapesCoverFullCube, non-trivial blocks only)?"""
        return self.opaque_material and self.sided and self.face_cull(d)

    @property
    def collides(self):
        return bool(self.boxes)

    @property
    def top(self):
        """Highest collision surface inside the cell (0..1.5), None if no collision."""
        return max(b[4] for b in self.boxes) if self.boxes else None

    def face_full(self, d):
        return bool(self.full >> DIRECTIONS.index(d) & 1)

    def face_center(self, d):
        return bool(self.center >> DIRECTIONS.index(d) & 1)

    def face_rigid(self, d):
        return bool(self.rigid >> DIRECTIONS.index(d) & 1)

    def face_cull(self, d):
        return bool(self.cull >> DIRECTIONS.index(d) & 1)

    def is_a(self, cls):
        return cls in self.classes


@lru_cache(maxsize=None)
def facts(st: State) -> Facts:
    f = _facts()
    if f is None:
        raise SystemExit(f'data/{_V["version"]}/facts.json.gz is missing - generate it with `mcb facts --version {_V["version"]}`.')
    b = f['blocks'][st.name]
    row = b['states'][st.props_key()]
    return Facts(row, f['shapes'][row[7]], b['item'], b.get('be'), _class_sets()[b['class']])


def in_tag(st, tag):
    name = st.name if isinstance(st, State) else (st if ':' in st else 'minecraft:' + st)
    if ':' not in tag:
        tag = 'minecraft:' + tag
    return name in _tags().get(tag, ())


def tag_members(tag):
    if ':' not in tag:
        tag = 'minecraft:' + tag
    return sorted(_tags().get(tag, ()))


def display_name(name_or_item, lang='zh'):
    """In-game name of a block or item id ('minecraft:oak_log' or 'oak_log') in 'zh' or 'en'. Names come from the
    player's game files; without them: the English name, else a readable id ("Oak Log")."""
    from .names import readable
    s = name_or_item.split(':', 1)[-1]
    for code in (('zh_cn', 'en_us') if lang == 'zh' else ('en_us',)):
        z = _names().get(code) or {}
        v = z.get(f'block.minecraft.{s}') or z.get(f'item.minecraft.{s}')
        if v:
            return v
    return readable(s)


def zh_name(name_or_item):
    """Chinese display name of a block or item id (kept for older design scripts; see display_name)."""
    return display_name(name_or_item, 'zh')


def biome_name(biome, lang='zh'):
    from .names import readable
    s = biome.split(':', 1)[-1]
    for code in (('zh_cn', 'en_us') if lang == 'zh' else ('en_us',)):
        v = (_names().get(code) or {}).get(f'biome.minecraft.{s}')
        if v:
            return v
    return readable(s)


def max_stack(item):
    s = item.split(':', 1)[-1]
    comp = _items().get('minecraft:' + s, {}).get('components', {})
    return int(comp.get('minecraft:max_stack_size', 64))


# ------------------------------------------------------------------ classification (vanilla rules via classes/tags)
def is_air(st):
    return st.name in AIR_NAMES


def is_stairs(st):
    return facts(st).is_a('StairsBlock')


def is_slab(st):
    return facts(st).is_a('SlabBlock')


def is_pane_like(st):                     # glass panes and iron bars
    return facts(st).is_a('PaneBlock')


def is_fence(st):
    return facts(st).is_a('FenceBlock')


def is_wall(st):
    return facts(st).is_a('WallBlock')


def is_fence_gate(st):
    return facts(st).is_a('FenceGateBlock')


def is_door(st):
    return facts(st).is_a('DoorBlock')


def is_trapdoor(st):
    return facts(st).is_a('TrapdoorBlock')


def is_bed(st):
    return facts(st).is_a('BedBlock')


def is_leaves(st):
    return facts(st).is_a('LeavesBlock')


def is_log(st):                           # what leaves count as "log" for their distance
    return in_tag(st, 'minecraft:logs')


def is_full_cube(st):
    return facts(st).full_cube


def face_sturdy(st, toward):
    """Is the face of `st` pointing `toward` a full square (vanilla isSideSolidFullSquare)?"""
    return facts(st).face_full(toward)


def cannot_connect(st):                   # Block.cannotConnect
    return (is_leaves(st) or st.short in ('barrier', 'carved_pumpkin', 'jack_o_lantern', 'melon', 'pumpkin')
            or in_tag(st, 'minecraft:shulker_boxes'))


def light_emission(st):
    return facts(st).lum


def has_prop(st, k):
    return st.has(k)
