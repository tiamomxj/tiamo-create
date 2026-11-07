"""Survival material list: items (not block states) needed for the design's own blocks, with in-game names in the
project language, stack counts and notes for things that need silk touch / shears / a tool, or cannot be obtained in
survival."""
from __future__ import annotations
import csv
from collections import Counter
from .registry import AIR, facts, zh_name, max_stack, in_tag
from .i18n import t, block_name

SPECIAL = {
    'water': {'water_bucket': 1}, 'lava': {'lava_bucket': 1}, 'water_cauldron': {'cauldron': 1, 'water_bucket': 1},
    'lava_cauldron': {'cauldron': 1, 'lava_bucket': 1}, 'powder_snow_cauldron': {'cauldron': 1, 'powder_snow_bucket': 1},
    'powder_snow': {'powder_snow_bucket': 1}, 'tall_seagrass': {'seagrass': 1}, 'kelp_plant': {'kelp': 1},
    'cave_vines_plant': {'glow_berries': 1}, 'twisting_vines_plant': {'twisting_vines': 1}, 'weeping_vines_plant': {'weeping_vines': 1},
    'bamboo_sapling': {'bamboo': 1}, 'big_dripleaf_stem': {'big_dripleaf': 1}, 'attached_pumpkin_stem': {'pumpkin_seeds': 1},
    'attached_melon_stem': {'melon_seeds': 1}, 'redstone_wire': {'redstone': 1}, 'tripwire': {'string': 1},
    'pitcher_crop': {'pitcher_pod': 1}, 'torchflower_crop': {'torchflower_seeds': 1},
    'fire': {}, 'soul_fire': {}, 'nether_portal': {}, 'end_portal': {}, 'end_gateway': {}, 'bubble_column': {},
    'moving_piston': {}, 'piston_head': {}, 'frosted_ice': {}, 'air': {}, 'cave_air': {}, 'void_air': {},
}
POTTED_RENAME = {'azalea_bush': 'azalea', 'flowering_azalea_bush': 'flowering_azalea'}
SILK = {'grass_block', 'mycelium', 'podzol', 'ice', 'packed_ice', 'bookshelf', 'chiseled_bookshelf', 'turtle_egg', 'bee_nest',
        'sculk', 'sculk_vein', 'sculk_catalyst', 'sculk_shrieker', 'sculk_sensor', 'calibrated_sculk_sensor', 'amethyst_cluster',
        'large_amethyst_bud', 'medium_amethyst_bud', 'small_amethyst_bud', 'brown_mushroom_block', 'red_mushroom_block',
        'mushroom_stem', 'glass', 'glass_pane', 'gilded_blackstone', 'snow', 'clay', 'melon', 'sea_lantern', 'glowstone'}
SILK_TAGS = ('minecraft:coral_blocks', 'minecraft:corals', 'minecraft:wall_corals')
SILK_OR_CRAFT = {'glass', 'glass_pane', 'snow', 'clay', 'melon', 'sea_lantern', 'glowstone', 'bookshelf'}
SHEARS = {'short_grass', 'tall_grass', 'fern', 'large_fern', 'dead_bush', 'seagrass', 'vine', 'glow_lichen', 'hanging_roots', 'cobweb',
          'nether_sprouts', 'pale_hanging_moss', 'short_dry_grass', 'tall_dry_grass', 'bush', 'twisting_vines', 'weeping_vines'}
TOOL = {'farmland': 'mat.farmland', 'dirt_path': 'mat.dirt_path', 'stripped_': 'mat.stripped'}
CREATIVE = {'bedrock', 'barrier', 'light', 'structure_block', 'structure_void', 'jigsaw', 'command_block', 'chain_command_block',
            'repeating_command_block', 'spawner', 'trial_spawner', 'vault', 'reinforced_deepslate', 'budding_amethyst',
            'end_portal_frame', 'petrified_oak_slab', 'frogspawn', 'test_block', 'test_instance_block', 'debug_stick'}


def items_for(st):
    """Items one block state costs in survival (Litematica-style counting)."""
    s = st.short
    if st == AIR:
        return {}
    if st.get('half') == 'upper' or st.get('part') == 'head':
        return {}
    if s in SPECIAL:
        return dict(SPECIAL[s])
    if s.startswith('potted_'):
        plant = s[len('potted_'):]
        return {'flower_pot': 1, POTTED_RENAME.get(plant, plant): 1}
    item = facts(st).item.split(':', 1)[1]
    if item == 'air':
        return {s: 1}
    n = 1
    if s.endswith('_slab') and st.get('type') == 'double':
        n = 2
    for prop in ('candles', 'pickles', 'eggs', 'flower_amount', 'segment_amount', 'layers'):
        if st.has(prop):
            n = int(st.get(prop))
    if 'MultifaceBlock' in facts(st).classes or 'MultifaceGrowthBlock' in facts(st).classes:
        n = max(1, sum(st.get(d) == 'true' for d in ('north', 'south', 'east', 'west', 'up', 'down')))
    return {item: n}


def note_for(item):
    if item in CREATIVE:
        return t('mat.creative')
    for k, v in TOOL.items():
        if item == k or (k.endswith('_') and item.startswith(k)):
            return t(v)
    if item in SHEARS or in_tag(item, 'minecraft:leaves'):
        return t('mat.shears')
    if item in SILK_OR_CRAFT:
        return None
    if item in SILK or any(in_tag(item, t) for t in SILK_TAGS):
        return t('mat.silk')
    return None


def material_list(states):
    c = Counter()
    for st in states:
        for k, v in items_for(st).items():
            c[k] += v
    out = []
    for item, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])):
        ms = max_stack(item)
        if ms == 1:
            stacks = t('mat.unstackable', n=n)
        elif n < ms:
            stacks = ''
        else:
            q, r = divmod(n, ms)
            stacks = t('mat.stacks', q=q, s='' if q == 1 else 's') + (f' + {r}' if r else '') + (t('mat.per_stack', ms=ms) if ms != 64 else '')
        out.append({'item': item, 'name': block_name(item), 'zh': zh_name(item), 'count': n, 'stacks': stacks, 'maxStack': ms,
                    'note': note_for(item)})
    return out


def write(build, out_dir, by_part=True):
    from .util import write_json
    blocks = [st for st in build.cells.values() if st != AIR]
    ml = material_list(blocks)
    write_json(out_dir / 'materials.json', ml)
    with open(out_dir / 'materials.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh)
        w.writerow(t('mat.csv').split(','))
        for m in ml:
            w.writerow([m['name'], m['item'], m['count'], m['stacks'], m['note'] or ''])
    parts = {}
    if by_part:
        groups = {}
        for p, st in build.cells.items():
            if st != AIR:
                groups.setdefault(build.part.get(p, 'main'), []).append(st)
        parts = {k: material_list(v) for k, v in groups.items()}
        write_json(out_dir / 'materials-by-part.json', parts)
    return ml, parts
