# Export, verification, preview, in-game test, release

**Local Create variant:** default output is Create `.nbt` for Minecraft 1.20.1 Forge + Create 6.0.8.
Read [create-blueprints.md](create-blueprints.md) for export, placement and verification.
Litematica export/paste/in-game instructions below apply only to explicit `export.format = "litematic"`.
Shared design checks and previews remain available. Current report: `artifacts/export-report.json`.

## Contents
1. Export modes, Litematica facts, game versions
2. What `mcb verify` checks (and how to fix failures)
3. Preview page
4. Real-client test (`mcb ingame`) and showcase world
5. Release package and the reply

## 1 · Export

- `mode = "site"` (default when the terrain is real): the design cells are split into tight, non-overlapping boxes
  by a k-d partition that minimises copied terrain (`region_penalty` = cells you accept to save one region); inside
  each box, cells the design does not set are copied from the real terrain. Result: Litematica's overlay flags only
  real work, no pink "extra blocks" over water/meadows. Origin = Litematica placement position, no rotation/mirror.
- `mode = "portable"` (flat/none sources): design cells only; air cells inside the box don't replace anything with
  the default paste. Players may rotate/mirror in Litematica.
- File format: Litematica v7 / SubVersion 1 / MinecraftDataVersion of the target version; BlockStates packed
  continuously across longs; palette[0] = air; tile entities `{id,x,y,z,components:{}}` with ids from the game; no
  entities.
- `[export] target_version = "1.21.1"`: for players on an older version (1.20.1 or newer) - its DataVersion, old
  ids for renamed blocks, and `verify` fails on blocks that version lacks ([setup.md](setup.md) §6). Newer versions
  need nothing.
- `[export] schem = true` adds a Sponge v3 `.schem` (WorldEdit / FAWE / Axiom) of the design bbox.
- `max_region = 64` splits very large builds so Litematica stays responsive and materials per region make sense.
- Region names come from parts (`[export] part_names`); keep part names meaningful in the player's language.

**Paste modes** (`Litematica → Configs → Generic → pasteReplaceBehavior`): `None` (default) only places into air - it
skips cells that replace grass, water or plants or that must be cleared; `With non-air` places every non-air
schematic block (use this for site builds); `All` also writes the air cells - **required when the design removes
trees or cuts terrain** (`With non-air` skips air cells: the build lands, but leaves/earth stay inside it; `mcb
release` counts such clearances and switches the guide to All). Survival builders see such cells as "wrong block"
and must dig first. Tell the player this every time.

## 2 · Verification (`mcb verify` → verification.json)

| Check | Typical failure → fix |
|---|---|
| File decode, header, palette states valid, no overlaps, tile entities | kit bug or hand-edited states → report it, fix code |
| Design cells == file, copied cells == terrain | stale export → re-run `mcb export` |
| Target game version has every block | a block added later than `target_version` → pick another block |
| Connections (panes, bars, fences, walls), stair shapes, door/bed/double-plant pairs | placed after resolve or manual states → let the rules pass run, don't hand-set `north=true` |
| Leaf decay (`persistent=false` leaves without a log within 6) | use `persistent=true` for designed trees |
| Support: torches, lanterns (hanging needs a solid/chain above), candles, carpets, ladders (wall behind), doors (solid below), rails, plates, buttons, signs, plants on the right soil (dirt tag, sand for cactus, water for lily pads), gravity blocks | move/replace the block or add the support |
| Water/lava containment | close the open side (rim, wall, glass) |
| Dark spawnable surfaces (block light 0) | add lights (attics, roofs, decks, garden rims), or make the surface non-spawnable (bottom slabs, carpets, glass, leaves) |
| Walk: start → targets with game collision boxes (step ≤ 0.6, drops ≤ 3, ladders/vines climbable, doors/gates/trapdoors openable, 1.8 headroom) | doorway blocked, stair missing a step, too-narrow gallery, entrance facing water, ladder without opening |
| Floating parts (26-connected components not touching terrain) | intended (sky island → `allow_floating = true`) or a missing support |
| Design replaces player-placed blocks | move the design, or tell the player explicitly what will be replaced |

`walk_start`/`walk_targets` are world feet cells (the cell the player's feet are in). Compute them from local
coordinates with `F.w(...)` (api.md snippets). Verification takes seconds - run it every iteration.

## 3 · Preview page (`mcb preview [--shots]`)

One offline HTML file (three.js bundled, no network), in the project language: vanilla models and textures from the
client jar of that version (or block shapes in map colours when this machine has none), sky + block light computed
like the game, smooth lighting/AO, day–dusk–night slider, layer cut (whole build or one layer for building),
surroundings toggle, plot outline, materials list, stats from verify, in-game gallery (after `mcb ingame`), and a
before/after wipe for a screenshot camera. Views are automatic: overview from the clearest front corner (sight lines
and foreground clutter measured on the terrain), the other corners, a terrain-aware front view, cut-aways per floor,
top, eye level on natural ground; add/override with `[preview] views`. Neighbouring player builds that touch the
context box are included whole (`grow_to_neighbours`). Entity-rendered blocks get stand-ins (beds, chests) or are
hidden (signs, banners, heads). `mcb shots` renders views headless (Python or Node Playwright; GPU when available,
software otherwise).

## 4 · Real-client test (`mcb ingame`)

Ask first: it opens a Minecraft window for 2–5 minutes, and the very first run downloads Minecraft, Fabric and
Gradle into the user's Gradle cache. Needs JDK 21, Litematica + MaLiLib jars of the bundled version (from the
player's mods folders, `mcb config add mod_jars …`, or `mcb fetch litematica`) and a display. It builds a vanilla
save from the site grid (real biomes, block entities, frozen time/weather/mobs) inside `MCBUILD_HOME/harness/<version>`,
copies the mod jars there under ASCII names, launches the Fabric client gametest, lets Litematica read and paste the
delivered file in each mode, compares every schematic cell with the world, and takes screenshots from the preview
views (+ dusk/night). Expected: `All` = 0 mismatches, `With non-air` too unless the design clears terrain (then its
mismatches are all `air <- …`); `None` leaves the cells that replace terrain (normal). `--showcase` zips the pasted
save into `release/` (a walkable demo world). Not available for an older `target_version` (the harness runs the
bundled version) - the player tests in their own game then. Logs: `artifacts/ingame/client.log`.

## 5 · Release (`mcb release`) and the reply

`release/` (file names in the project language): schematic(s), the preview page, the materials CSV, screenshots
(in-game shots if available, else preview shots), optional showcase zip and video, and the guide (使用说明.md /
README.md: files, placement origin or portable note, paste mode, game version, checks, design notes from
`[release] notes`). `[release] zip = true` also writes one zip of the folder. In the reply: what/where/why, origin +
paste mode, verification and in-game results (numbers), deviations, what was not verified, links to files. Offer
to copy the .litematic into the player's `<game folder>/schematics/` (new file name, never overwrite).
