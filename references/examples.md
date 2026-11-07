# Worked examples (inputs → decisions → outcome)

Real jobs done with this kit (names and places made generic).

## 1 · Fishing hut - screenshot with a drawn circle + "match my house"
- Inputs: a plot screenshot with a blue circle (no F3), a photo of the player's house; a multiplayer server.
- Data: the Voxy cache of that server (`source = "voxy"`, box 352×128×320).
- Locate: camera fitted on 8 lanterns visible in the screenshot (rms ≈ 2 px) → blue stroke back-projected onto the
  terrain → 600+ plot columns; build placed on the plot's visual centre, pier into deep water. (With F3+C text this
  step would have been one command.)
- Style: `style` statistics of the house (gray concrete frame, white concrete/quartz walls, dark oak trims, round
  windows, black glass panes, end-rod bars, chains + lanterns); deliberate deviation: meadow roof garden.
- Result: 2,308 blocks, 23 sub-regions (k-d), verify PASS, in-game 0 mismatches (With non-air / All), preview with
  screenshot wipe, making-of video. The verifier also found one of the player's own lanterns under the porch
  foundation - reported instead of silently replaced.

## 2 · Lighthouse - "on the cape north-west of my house", no coordinates, no style
- Data: a fresh Voxy read (160×128×128).
- Locate: `analyze` → the player's house (biggest cluster: white/gray concrete, quartz, dark oak), a neighbour's
  build on the cape's west end, mineshafts flagged underground; the open-sea point = a sand spit (height table from
  `ground_top`).
- Style: none given → archetype (red/white bands, copper cap) that reads from the house and the sea.
- Verification caught three real flaws: dark hollow roof (→ `hip_roof(fill=…)`), door facing shallow water after
  rotation (→ face the dry spit), gallery too narrow to walk (→ wider deck ring). In-game: With non-air / All 0 of
  3,047 cells mismatched, 9 screenshots, showcase save.

## 3 · Pagoda in a cherry grove - screenshot + "Chinese style", trees in the way
- Data: Voxy cache, large box (416×160×416); the screenshot's minimap showed the player's coordinates.
- Design: octagonal 7-storey pagoda, plaza levelled with blended margins, archway and stone paths, 23 trees removed
  and 3 transplanted. Clearances → the guide says paste with **All** (With non-air left 9,225 cells of leaves/earth).
- Result: ~26k cells, verify PASS (11 walk targets up to the top floor), in-game 0 mismatches with All.

## 4 · Garden pavilion - no site, named style (Chinese garden)
- Data: `source = "flat"`; portable schematic; `turns = 1` to test rotation (bridge to the west).
- Design: elliptical pond (clay bed, contained water, rim), double-eave hip roof on red columns, zigzag bridge on
  posts, stone lanterns, cherry/birch/bamboo, lily pads.
- Verification: 46 dark rim stones → stone lanterns all round the pond; then PASS.

## 5 · Starter cottage - the template (`mcb init` → `mcb all`)
- Caught during development: a lantern hanging from nothing, a floating leaf, then a dark attic once a ceiling was
  added - all fixed in `templates/design.py`. `mcb selftest` builds it in Chinese and English on every install.
