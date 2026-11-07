# Site data and locating the build

## Contents
1. Finding data (`mcb find-data`)
2. Sources: voxy · anvil (saves, Bobby, backups) · schematic · flat/none
3. Choosing the read box
4. Locating - by input type
5. Screenshot camera (set from F3, fit, overlay, outline, ray)
6. Site analysis (`mcb analyze`, `mcb map`)

## 1 · Finding data

`mcb find-data` looks in the game folders of the profile (`mcb config add game_dirs …`), the default folders of
common launchers on this OS (official, Prism/MultiMC/PolyMC, CurseForge, Modrinth, ATLauncher, GDLauncher), the
folder lists HMCL and PCL keep, and version-isolated instances inside them (`.minecraft/versions/<name>/`). It prints:
- **Game folders** with version and the relevant mods (Litematica, Voxy, Bobby, Xaero, Distant Horizons).
- **Voxy caches**: `<game>/.voxy/saves/<server or world>/<dimension-hash>/storage` with size. One folder per
  dimension; the kit picks the overworld from the stored biomes. Several instances can hold caches of the same
  server - the biggest overworld cache is usually the most complete.
- **Bobby caches**: `<game>/.bobby/<server>/…/<dimension>/` with region files - real chunks of servers.
- **Singleplayer saves** with name, version and the player's last position ("where I am standing").
- **Xaero waypoints**: names like 家 / home / base give coordinates directly.
- **Litematica schematics folders** (existing schematics can be style references or the site itself).
- **Newest screenshots** (F2) - "look at my last screenshot" without uploading.
`--dir <folder>` limits the search; `--scan auto` (or `--scan <folders>`) searches further for portable launcher
folders (bounded, ~10 s) and `--remember` saves what it finds; `--json` for scripts.

## 2 · Sources (`[site]` in project.toml)

| source | when | keys |
|---|---|---|
| `voxy` | a server (or world) the player visited with the Voxy mod | `server` (folder-name substring), `dimension`, `box`, optional `store`, `voxy_jar` |
| `anvil` | singleplayer save, downloaded map, server region backup, **Bobby** cache folder | `world` (save folder or a folder of `r.X.Z.mca`), `dimension`, `box` |
| `schematic` | the surroundings as .litematic/.schem/.nbt - e.g. an area the player saved with Litematica | `schematic`, `origin` (world position of the schematic's origin), `margin` |
| `flat` | no site: synthetic grass/dirt/stone at `ground_y` (+ optional `water_y`, `biome`) | `ground_y`, `box` optional |
| `none` | like flat, marked "no site" → portable export | `ground_y` |

Voxy: RocksDB + Zstd, position format 1 / section format 0; level-0 sections are 32³ exact block states (ids in
bits 27..46, biome in 47..55). A tiny read-only Java bridge (`vendor/atlas/bridge`) reads it with the RocksDB JNI
library found inside the installed Voxy jar (Java 17+, `zstandard`); it works while the game is running and never
touches lock files. Only explored chunks exist; "L0 sections 80 / 80" in `mcb site` means complete.

Anvil: Java 1.13+ worlds; ids renamed since (e.g. `grass` → `short_grass`, `chain` → `iron_chain`) are mapped to the
bundled version automatically. A Litematica area schematic has no world position inside the file - ask for the
selection's origin (Area Editor) and put it in `origin`.

## 3 · Choosing the read box

`box = [x0, y0, z0, x1, y1, z1]` (end exclusive; Voxy reads align to 32, anvil to 16 - slightly bigger is fine).
- Horizontal: the build footprint + 40–80 blocks (neighbours shown whole, camera checks need the features in the
  screenshot, previews need context). Up to ~400×400 is fine.
- Vertical: from below the deepest foundation / water bed (sea floor near y 40–50) to above the tallest neighbour.
- Re-run `mcb site` after changing the box; the design cache is invalidated automatically.

## 4 · Locating - by input type

| The player gives | Do |
|---|---|
| F3+C text (`/execute in … run tp @s x y z yaw pitch`) | `mcb camera set --f3 "<text>"`; the spot is where they look: `mcb camera ray` (screen centre) - with an image add `--image`, `--fov` |
| F3 screenshot | read XYZ, Facing (yaw / pitch) and "Targeted Block" from the image → `camera set --f3 "XYZ: … Facing: … (yaw / pitch)" --image …`; eye = feet + 1.62 |
| Coordinates | use them; still `mcb map --mark=x,z,label` to see what is there |
| Screenshot, nothing marked, no F3 | ask for F3 first (cheap). Otherwise fit the camera (§5), then `mcb camera ray --px=960,540` or the area the image emphasises |
| Screenshot with a drawn outline | camera (set or fit), then `mcb camera outline --color=#RRGGBB` (or `--poly=u,v …`) → `plot.json` columns + `plot-map.png` |
| Map screenshot (Xaero / JourneyMap / web map) | `mcb map` the same area at a similar scale and match shorelines, roads, roofs; map screenshots often show coordinates |
| "Next to / behind my house", "on that hill" | `mcb analyze`: builds list (top blocks show whose build is whose), waypoints, terrain; choose, confirm on a close-up map |
| A plot size only | `mcb analyze --footprint WxD` → flat candidates with earthwork; prefer spots near the player's builds/paths |
| Nothing | flat/none source, portable schematic; the player can rotate/mirror it in Litematica |

When two candidates are equally plausible and far apart, ask (show the map). Otherwise decide and explain.

## 5 · Screenshot camera (`mcb camera …`)

Model: yaw 0 = south (+z), 90 = west; pitch + = looking down; vertical fov; eye = feet + 1.62.
- **set** (preferred): from F3 data - exact position and angles; only the fov may need a correction (options
  default 70; dynamic FOV, sprinting and zoom mods change it). Check `camera-overlay.png`.
- **fit** (no F3): write `artifacts/camera-spec.json`
  ```json
  {"image": "input/image1.jpg", "init": [113, 36, 80, -274.5, 89.6, -209.5],
   "spots": [[993, 632], [768, 787], [603, 682]], "match": ["lantern", "torch"], "box": [-330, -260, -260, -170]}
  ```
  `init` = yaw, pitch, fov, eye x/y/z (a rough guess); `spots` = pixels of small distinctive blocks (lanterns,
  torches) matched to the nearest projected blocks of those types; or explicit `"pairs": [[[u, v], [x, y, z]], …]`
  (block corners, trunks, door tops). 6–10 well spread points; keep `eye_sigma` small when the eye is known.
  `mcb camera fit` → `camera.json` (rms px) + `camera-overlay.png` - coastlines and roofs must line up.
- **outline / ray** as above. A camera also becomes the preview's "screenshot view" with a before/after wipe, and an
  in-game screenshot from the same spot.

## 6 · Site analysis

`mcb analyze [--box=x0,z0,x1,z1] [--footprint WxD] [--pad-y Y]` → `analysis.json`, `analysis-map.png`:
- ground min/median/max, water fraction, steep fraction, biome mix;
- **builds**: clusters of player-placed blocks (bbox, y range, block count, top blocks; `underground` = probably a
  mineshaft). Natural vs placed uses the vanilla tags (dirt, sand, stone, logs, leaves, flowers …);
- **candidates** for a footprint: least cut-and-fill to the median height, no water, no builds, few trees.
`mcb map --box=… --scale 8 --grid 4 --mark=x,z,label --rect=x0,z0,x1,z1,label --design` for close-ups with
coordinates; heights can be printed with a few lines of Python on `P.site().ground_top(x, z)` (see api.md).
