# Pitfalls (all of these happened at least once)

## Environment
- Write multi-line Python/JS files with your file-editing tool; shell heredocs mangle backslashes and quotes.
- A `cd` in a shell command may persist between calls in some agents - use absolute paths and `-p <project>`.
- Windows consoles are often GBK: `scripts/mcb.py` switches its output to UTF-8; set `PYTHONIOENCODING=utf-8` when
  running modules another way.
- `python` may be missing on macOS/Linux (use `python3`) or point to an old version - `mcb doctor` shows which runs.
- Never call a module `site.py` (stdlib clash) - the kit uses `terrain.py`.
- Negative numbers after argparse options need `=`: `--box=-420,-330,-200,-150`.
- Uploaded files and chat attachments may live in temporary folders - `mcb init --images …` copies them at once.
- `math.floor` for world coordinates (`int(-281.5) == -281`).
- Don't copy kit files with a relative `cp … design.py` from inside the kit folder (it lands in the kit).
- Don't install packages, download files or open a game window without the user's OK; `mcb fetch` refuses without
  `--yes` for that reason.

## Finding the player's data
- Launchers with version isolation (HMCL, PCL, Prism, CurseForge, Modrinth …) keep `saves`, `mods`, `.voxy`,
  `schematics` per instance (`.minecraft/versions/<name>/`, `instances/<name>/minecraft`). The in-game "Open Pack
  Folder" trick always lands in the right one.
- Several instances may hold caches of the same server - `find-data` lists all; the kit takes the biggest overworld.
- Voxy/Bobby only hold visited chunks; reading works while the game runs.
- In a "built" world the ground under the player's builds is gone - don't take ground heights inside other builds.
- `ground_top` counts trees and builds; use `terrain_top` / `analyze` candidates for natural ground.
- A Litematica area schematic stores no world position: get the selection origin from the player.

## Design
- Defaults are the game's: `'lantern'` = standing, `'oak_door'` lower half etc. Composites (`F.door`, `F.bed`,
  `F.tall`, `F.chest_pair`) make pairs right. Door facing = direction you look walking in.
- Hollow roofs and attics are dark spawn rooms (fill roofs: `hip_roof(fill=…)`, light attics).
- Railings directly against a wall leave no walkway - the walk test finds it.
- Rotated designs: check that the entrance still faces dry land / the path (`turns`); the walk test finds it.
- Lily pads need water below; plants need dirt-tag soil; bamboo/sugar cane/cactus have their own rules.
- Leaning trunks touch diagonally - fine (26-connected), but cocoa needs a jungle log on its `facing` side.
- The rules pass may change states you set (connections, stair shapes, waterlogged) - that is intended.
- Players on older versions: set `[export] target_version`; new blocks (pale oak, resin, copper chests, shelves …)
  fail verify instead of silently pasting as air.

## Litematica
- Default paste `None` skips cells that replace terrain/water - tell players to use `With non-air`, or `All` when
  the design clears trees/terrain (`With non-air` skips air cells).
- Regions that cover lots of untouched terrain show as "extra blocks" - the site export copies terrain into regions
  and keeps boxes tight (k-d split); don't hand-make big boxes.
- No entities (item frames, armor stands, paintings), no sign text: unstable across versions.
- Mod jars in launcher folders can have names like `【投影】litematica-…jar`; Gradle/Loom silently drops such files
  from the dev runtime (NoClassDefFoundError in the in-game test) - the harness copies them under ASCII names.

## Preview / screenshots
- Custom ShaderMaterial in sRGB: `THREE.ColorManagement.enabled = false`, otherwise fog/sky go orange/brown.
- Cherry/azalea/pale-oak leaves are not biome-tinted (others are; spruce/birch have fixed tints).
- Entity-rendered blocks (beds, chests, signs, banners, heads, shulker boxes) have no block model - stand-ins.
- Any opaque full-screen div covers the WebGL canvas (video stage!).
- Some agents' built-in browsers cannot open `file://` pages - use `mcb shots` (headless Playwright) to look.
- Headless Chromium falls back to SwiftShader (slow) when the GPU is unavailable; the kit tries the GPU first
  (D3D11 / Metal / Vulkan via ANGLE).
- A camera placed by formula can sit inside a hill, a hedge or above a neighbour's roof - the auto views score sight
  lines and clutter, but always look at the shots.

## In-game test / Gradle
- Plain `java -cp` with the named Minecraft jar fails (package-private access across remapped packages) - game code
  runs through Fabric's launcher (preLaunch entrypoint, `runDumpFacts`).
- The first Loom setup downloads and remaps for minutes; `--no-daemon` keeps no background JVM.
- The test opens a real window; never run it without telling the user.

## Video
- edge-tts older than 7.3.1 gets HTTP 403.
- Narration text is sent to Microsoft's TTS service - no personal data (server address, names) in the spoken script.
- Music envelope must handle a last bar shorter than its attack (array broadcast error).
- You cannot hear the result - verify duration, loudness (−16 LUFS) and peaks, and ask the user to watch it.
