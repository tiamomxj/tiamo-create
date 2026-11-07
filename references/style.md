# Style: where it comes from and how to turn it into a palette

## Contents
1. Decide the style source
2. Reference build in the world (`mcb style`)
3. Photos / screenshots / named styles
4. No style given
5. Palette rules and the PAL dict
6. Named-style palettes (1.21.11 blocks)

## 1 · Decide the source (write it in the brief)

| The user gives | Source | Note |
|---|---|---|
| "像我家 / 和旁边统一" + where it is | their build in the world → `mcb style` | quantify, then pick 1–2 signature elements |
| photos / screenshots of a style | read materials, proportions, roof form, signature details | confirm block IDs with `mcb blocks <词>` |
| a named style ("中式", "日式", "中世纪", "北欧", "现代", "蒸汽朋克" …) | palette table below + typology knowledge | adapt to the site's biome and neighbours |
| nothing | context → see §4 | say in the reply that it is your choice and how to change it (one PAL edit) |

## 2 · Reference build in the world

1. Find it: `mcb analyze` (builds with top blocks), or coordinates from the user / waypoints.
2. `mcb style --box=x0,y0,z0,x1,y1,z1 --name house` → `style-house.json/png` (block counts grouped by role:
   structure, stairs, slabs, fences/walls/panes, glass, doors/trapdoors, lights, plants, decoration; colour swatches)
   and `style-house-drawings/` (top view + 4 elevations of just the player-placed blocks).
3. Read the numbers, not the photo: on the fishing-hut job the "black frame" in the photo was gray concrete
   (2,369 vs 95 black), the "brick" was dark oak planks, the thin white bars were end rods.
4. Extract: main volume material(s), frame/trim, glass type, roof form, light source, signature elements
   (round windows, slats, chains with lanterns, planting). Reuse one or two signature elements at the new scale —
   unity, not a copy. Deliberate deviations (e.g. a green roof because they look at it from above) are fine if
   stated with the reason and how to revert.

## 3 · Photos and named styles

- From images, list per element: material colour/texture → candidate blocks (check textures in the preview),
  proportions (storey height 4–5 blocks, roof pitch = 1 per block with stairs, eave overhang 1–2).
- Named styles: use the table in §6 as a starting palette and the typology checklists in design-guide.md; adapt
  wood types to the biome (spruce in taiga, jungle/bamboo in jungle, acacia in savanna, mangrove in swamps).

## 4 · No style given

Derive, in this order: (1) the user's own nearby builds (materials of the biggest cluster in `mcb analyze`),
(2) the biome and terrain (desert → sandstone/terracotta; snowy → spruce, stone, deepslate roofs; plains/forest →
oak/spruce + cobblestone; beach → white/blue, birch, sandstone; jungle → jungle wood, mossy stone, bamboo),
(3) the typology's archetype (lighthouse → red/white bands; Chinese garden pavilion → red columns, dark tile roof),
(4) a neutral, timeless default: stone base + wood frame + plaster walls (calcite / white terracotta) + dark roof.
Keep it small: 2–3 main materials, 1 accent, 1 light source, 1–2 plants.

## 5 · Palette rules

- Put every material in one `PAL` dict at the top of design.py; refer to roles (`PAL['wall']`), never repeat IDs.
- Contrast hierarchy: base (darkest/heaviest) → walls (lightest, largest area) → frame/trim (mid/dark) → roof
  (dark or saturated) → accent (small amounts: window frames, lanterns, flowers).
- Texture breakup: mix 10–30% of a sibling block (stone bricks + mossy/cracked; planks + stripped log) using
  `shapes.pattern` / `shapes.mix`; do not randomise structural lines (corners, frames, eaves).
- Depth: every wall plane gets at least one offset element (frame proud by 1, recessed windows, beams, stairs as
  sills); flat 1-layer walls read as cardboard.
- Lighting fixtures are part of the style (lantern on chain vs end rods vs froglights vs candles).
- Check the palette in the preview at day and night and from the user's usual viewpoint.

## 6 · Named-style palettes

| Style | Base | Walls | Frame / trim | Roof | Glass / openings | Light | Plants / extras |
|---|---|---|---|---|---|---|---|
| 现代 Modern | smooth stone, gray concrete | white concrete, smooth quartz, calcite | gray/black concrete, dark oak | flat slab, green roof | black/gray stained glass panes, large openings | froglights, end rods, hidden lights | bamboo, palms, potted plants |
| 中式 Chinese | stone bricks, polished andesite | white terracotta / calcite, dark oak planks | stripped mangrove / crimson (red columns), dark oak | deepslate tile / blackstone stairs, curved corners | spruce trapdoor lattices, paper (white wool) | lanterns on chains, soul lanterns | cherry, bamboo, lily pads, rocks |
| 日式 Japanese | cobblestone, stone | white concrete / calcite panels | stripped spruce / dark oak posts | dark prismarine or deepslate tile, spruce eaves | spruce trapdoors (shoji), paper | lanterns, candles | cherry, azalea, moss, bamboo, gravel garden |
| 中世纪 Medieval | cobblestone, stone bricks | white/light gray wool or calcite infill | stripped dark oak / spruce timber frame | spruce / dark oak stairs, steep | glass panes with spruce trapdoor shutters | lanterns, torches | flowers in boxes, oak/spruce trees |
| 北欧 Nordic | stone, mossy cobble | spruce planks / logs | stripped spruce, dark oak | dark oak / spruce stairs, moss carpets on roof | glass panes | lanterns, campfires | spruce, ferns, moss |
| 地中海 Mediterranean | sandstone, smooth sandstone | white concrete / calcite | birch / stripped oak | terracotta (red) / granite stairs | blue stained glass accents, arches | lanterns | olive-like oak, flowers, pots |
| 沙漠 Desert | sandstone, cut sandstone | smooth sandstone, terracotta | chiseled sandstone, acacia | flat with parapets, domes | arches, iron bars | lanterns, torches | cactus, dead bush, palms |
| 哥特 Gothic | deepslate, polished blackstone | stone bricks, calcite | deepslate bricks, tuff | steep dark tile, spires | tall stained glass, iron bars | soul lanterns, candles | dark oak, vines |
| 蒸汽朋克 Steampunk | deepslate, bricks | copper (waxed), brown terracotta | iron blocks, chains, dark oak | copper stairs, domes | iron bars, glass | lanterns, redstone lamps | — |
| 奇幻 Fantasy | mossy stone, calcite | white/pink terracotta, prismarine | amethyst, quartz | colourful stairs, curved | tinted glass | froglights, sea lanterns | azalea, glow lichen |
| 乡村 Rustic / farm | cobblestone | oak / spruce planks | stripped oak logs | oak/spruce stairs, hay | glass panes, trapdoor shutters | lanterns, campfire | flowers, crops, hay bales |
| 海滨 Coastal | stone, sand | white concrete / birch | blue/cyan accents, spruce | dark oak or blue terracotta | glass | lanterns, sea lanterns | palms, seagrass, docks |

Use waxed copper so the colour does not weather; check new 1.21.x blocks (`mcb blocks copper`, `mcb blocks tuff`,
`mcb blocks pale`) for extra textures.
