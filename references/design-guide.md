# Design guide: typologies, composition, terrain fit, liveability

## Contents
1. Working method
2. Typology checklists
3. Composition and detail
4. Fitting the terrain (patterns)
5. Light, circulation, interiors
6. Landscape around the build
7. Survival practicality

## 1 · Working method

1. Program → footprint: list spaces with sizes (storey height 4–5 blocks incl. floor; corridors ≥ 2 wide in big
   builds; doors 1×2 or 2×3 for grand entrances; stairs rise 1 per step — a 4-block storey needs 4 steps + landing).
2. Massing first (boxes, roof forms) and check it from far away and from the user's viewpoint (`mcb design` drawings,
   `mcb preview --shots`). Only then façades, then interior, then landscape.
3. Work in parts (`B.cur = 'wing-west'`): sub-regions, materials-by-part and error reports follow them.
4. Every round: drawings + 4–6 preview shots (overview, front, eye level, cut-aways, night). Look for: flat walls,
   blocky silhouette, roof too heavy from above, entrance unclear, dark corners, floating bits.
5. `mcb verify` is part of the loop, not the end — its errors are design feedback.

## 2 · Typology checklists

| Typology | Must have | Good to have |
|---|---|---|
| House / cottage | entrance with step + light, living, kitchen (crafting, furnace/smoker, cauldron), beds, storage, windows on 2+ sides | porch, chimney, attic (lit!), garden, path to road |
| Hut / cabin (fishing, hunting) | compact, purpose gear (barrels, smoker, composter), bed, view to the activity | deck, boat landing, fire pit |
| Tower / lighthouse / watchtower | stair or ladder to every level (walk test!), light at top, railing on balconies, windows staggered | gallery wide enough to walk (≥ 1 free ring), cap with finial |
| Bridge | span supports to the bed/ground, railings, lighting along it, ramps/stairs at both ends ≤ 1 per step | piers with cutwaters, lanterns on posts |
| Pavilion / gazebo / garden | open sides with railing, roof with overhang, seating, path | pond (contained water), zigzag bridge, rocks, trees |
| Shop / market / tavern | counter, display (shelves, item frames are entities → skip), storage, signboard area | outdoor seating, awnings |
| Farm / barn / stable | crop plots on farmland next to water (within 4), lighting against mobs, fences with gates | hay storage, composters, animal pens |
| Castle / wall / gate | wall walk ≥ 2 wide with crenellations, gatehouse, towers at corners, stairs to the walk | moat, banners (entities — skip), courtyard |
| Temple / church / hall | axis and symmetry, entrance hierarchy, tall interior, windows with rhythm | apse, bell tower, stained glass |
| Statue / sculpture | silhouette from main viewpoints, base/plinth, scale vs. surroundings | lighting at night, contrast with background |
| Landscape / terrain | grade with blends (`level_pad(blend=)`), natural materials mix, water bodies contained | paths, planting groups, rocks |
| Interior only | furniture clearance (1 free row in front), lighting, storage access | ceiling detail, rugs (carpets) |
Redstone machines, entity-based decoration (item frames, armor stands, paintings), sign text: out of scope or skip.

## 3 · Composition and detail

- One main volume + secondary volumes + small elements (hierarchy). Avoid equal-sized boxes.
- Roofs: overhang 1 (small) or 2 (big/stylised); stair roofs with full courses; caps with slabs; check corner stair
  shapes (the rules pass computes vanilla `inner/outer` shapes).
- Walls: base course (darker, 1 high), frame (posts at corners and every 3–5 blocks), infill, top beam; windows
  recessed or framed; sills/lintels with stairs/slabs/trapdoors.
- Rhythm and symmetry where the typology expects it (temples, halls); asymmetry for homes and huts.
- Pixel circles: `shapes.pixel_circle(d)` (d ≥ 7 reads round; 5 is a rounded square).
- Framing views: openings that frame the sea/mountain; a "portal" element (gate, pergola) creates depth.
- From the user's viewpoint (screenshot camera): the first thing they will see — make it read well there.

## 4 · Fitting the terrain (patterns)

| Situation | Pattern | Kit |
|---|---|---|
| Gentle slope | floor 1 above the highest ground point, foundation down to real ground per column | `shapes.foundation(F, cells, 0, PAL['base'])` |
| Steeper slope | terraces / split levels; retaining walls; stairs between levels | `level_pad`, `stair_flight` |
| Need a flat yard | cut & fill to a pad with a blended margin | `shapes.level_pad(..., blend=3)` |
| Shore / water | plinth or stilts down to the bed; deck 1 above water; ladders for swimming | `pillar_down`, `F.water_top()` |
| Over water | piles every 3–4 blocks, beams, boat landing one step lower | pier pattern from the hut |
| Cliff / hill top | anchor on rock, railings at edges, views outward | `F.terrain()` to test the rock |
| Trees on site | keep them (work around) or remove explicitly with AIR clearances | `F.clear` |
| Neighbours | keep distance ≥ 3, don't overwrite their blocks (verify warns), align to their axes when close | `mcb analyze` |
Plants only on proper soil (`F.on_ground(..., soil=('grass_block',))`); waterlogging is set automatically where the
design overlaps real water; never leave a water source with an open side (verify checks).

## 5 · Light, circulation, interiors

- Hostile mobs spawn at block light 0 (since 1.18) on any full-top surface with 2 free blocks above — inside, on
  roofs, attics, decks, garden rims. Light sources every ~8–10 blocks of walkable surface; hidden lights (under
  carpets? no — under slabs/trapdoors, in floors as froglights with glass, behind leaves). `verify` lists dark cells.
- Every room/target reachable from the entrance (`walk_targets`); doorways not blocked by furniture; stair heads
  have 3 free blocks of headroom; ladders need a wall behind and an opening above.
- Interiors: storey height 4–5, furniture from blocks (stairs = chairs, trapdoors = tables/shelves, barrels, lecterns,
  shelves), keep a free path 1 wide; beds 2 long; chests in pairs with `F.chest_pair`.

## 6 · Landscape around the build

Paths that follow the ground (`shapes.path`), lanterns on posts along them, planting groups of 3–5 with variety
(`nature.flowers`, `scatter`), trees placed to frame views (not to block the entrance), rocks to anchor corners.
Keep landscaping as separate parts so the user can skip them.

## 7 · Survival practicality

- Materials list (`mcb materials`) flags silk-touch / shears / creative-only items; prefer craftable blocks.
- Large builds: staged schematics or part-by-part regions; mention scaffolding needs for tall parts.
- Avoid gravity blocks (sand, gravel, concrete powder) without support; avoid fire hazards (wood next to lava/campfires).
