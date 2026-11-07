"""__NAME__ — design script (runs on any site; replace everything below with the real design).

Local axes before rotation: +x = east, +y = up, +z = south; local (0, 0, 0) = project.toml [design] origin.
Design in a canonical orientation (here: entrance on the local south side) and turn the whole thing with
[design] turns — positions AND block states (stairs, doors, logs …) rotate together.
Run: mcb design  (rules pass + drawings)  →  mcb export / verify / preview
"""
import random
from mcbuild import Build, AIR, get_project, shapes, nature

P = get_project()
D = P.cfg.get('design', {})
B = Build(P.site(), P.name)
F = B.frame(tuple(D.get('origin', (0, 65, 0))), turns=D.get('turns', 0))
G = F.ground                                   # G(lx, lz) = local y of the terrain surface block

# ---- palette: one place to restyle the whole build
PAL = {
    'base': 'cobblestone', 'wall': 'oak_planks', 'post': 'stripped_spruce_log[axis=y]', 'beam': 'stripped_spruce_log[axis=x]',
    'floor': 'spruce_planks', 'roof': 'dark_oak_stairs', 'roof_cap': 'dark_oak_slab[type=bottom]', 'gable': 'oak_planks',
    'glass': 'glass_pane', 'door': 'spruce', 'light': 'lantern', 'path': 'dirt_path', 'fence': 'spruce_fence',
}
W, Dp, H = 9, 7, 4                             # footprint (x, z) and wall height

# ---- base & floor: fit to the terrain (foundation down to the real ground)
B.cur = 'house'
shapes.foundation(F, [(x, z) for x in range(W) for z in range(Dp)], 0, PAL['base'])
F.fill((0, 0, 0), (W - 1, 0, Dp - 1), PAL['base'])
F.fill((1, 0, 1), (W - 2, 0, Dp - 2), PAL['floor'])
F.clear((1, 1, 1), (W - 2, H, Dp - 2))         # interior air (removes terrain inside)
# ---- walls with corner posts
shapes.walls(F, (0, 1, 0), (W - 1, H, Dp - 1), PAL['wall'])
for x, z in [(0, 0), (W - 1, 0), (0, Dp - 1), (W - 1, Dp - 1)]:
    F.fill((x, 1, z), (x, H, z), PAL['post'])
F.fill((0, H, 0), (W - 1, H, 0), PAL['beam']); F.fill((0, H, Dp - 1), (W - 1, H, Dp - 1), PAL['beam'])
# ---- openings: door in the middle of the south wall, windows
F.door(W // 2, 1, Dp - 1, 'north', 'left', wood=PAL['door'])   # entered from the south walking north
F.put(W // 2, 0, Dp, f"{PAL['roof']}[facing=north,half=bottom]")  # step
for x in (2, W - 3):
    F.fill((x, 2, Dp - 1), (x, 3, Dp - 1), PAL['glass']); F.fill((x, 2, 0), (x, 3, 0), PAL['glass'])
F.fill((0, 2, 2), (0, 3, Dp - 3), PAL['glass']); F.fill((W - 1, 2, 2), (W - 1, 3, Dp - 3), PAL['glass'])
# ---- roof (ridge along x) with filled gables
shapes.gable_roof(F, 0, 0, W - 1, Dp - 1, H + 1, PAL['roof'], ridge='x', overhang=1, gable=PAL['gable'])
# ---- interior: ceiling (attic floor), light hanging from it, basic furniture
F.fill((1, H, 1), (W - 2, H, Dp - 2), PAL['floor'])
F.hanging_lantern(W // 2, H - 1, Dp // 2, chain=0)
F.put(W // 2, H + 1, Dp // 2, PAL['light'])                  # dark attics spawn mobs: light them too
F.bed((1, 1, 1), 'south', 'red')
F.put(W - 2, 1, 1, 'crafting_table'); F.put(W - 3, 1, 1, 'furnace[facing=south]')
F.chest_pair(W - 2, 1, 3, 'west')
F.put(W // 2 + 2, 1, Dp - 2, PAL['light'])
# ---- outside: path to the door, lantern post, a tree and flowers (only on grass)
B.cur = 'garden'
shapes.path(F, [(W // 2, Dp + 1), (W // 2, Dp + 6)], PAL['path'], width=1)
F.on_ground(W // 2 + 2, Dp + 2, PAL['fence']); F.put(W // 2 + 2, G(W // 2 + 2, Dp + 2) + 2, Dp + 2, PAL['light'])
nature.round_tree(F, -4, Dp + 3, height=5, radius=2.5, part='tree')
rng = random.Random(7)
nature.flowers(F, [(x, z) for x in range(-2, W + 2) for z in range(Dp + 1, Dp + 6) if rng.random() < 0.12 and x != W // 2],
               rng, part='garden')
B.notes.append("Starter example: oak cottage, entrance on the south side. Replace with the real design (write notes in the player's language).")
