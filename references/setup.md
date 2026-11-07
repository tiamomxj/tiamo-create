# Setup: install, profile, downloads, sandboxes, game versions

## Contents
1. Requirements and install (Windows / macOS / Linux)
2. `mcb doctor` and `mcb selftest`
3. The profile (`mcb config`) and environment variables
4. Downloads (`mcb fetch`) - always ask first
5. Agents without the game on the machine (cloud sandboxes)
6. Other game versions
7. Troubleshooting

## 1 · Requirements

| Capability | Needs | Install |
|---|---|---|
| Core (design, export, verify, materials, drawings, maps, preview page) | Python 3.10+, numpy, Pillow (+ tomli on 3.10) | `python -m pip install -r scripts/requirements.txt` |
| Real textures in previews and maps | the vanilla client jar of the version | found automatically in launcher folders / Loom caches, or `mcb fetch client` |
| Read Voxy caches | `zstandard` + Java 17+ (any JRE, the game's own runtime works) | `python -m pip install zstandard` |
| Preview screenshots | Playwright + Chromium | `python -m pip install playwright` then `python -m playwright install chromium` (or a global Node.js Playwright) |
| Faster analysis / camera fit | scipy (optional; pure-numpy fallbacks exist) | `python -m pip install scipy` |
| Real-client paste test | JDK 21, Litematica + MaLiLib jars, a display | Windows `winget install EclipseAdoptium.Temurin.21.JDK`, macOS `brew install --cask temurin@21`, Linux `sudo apt install openjdk-21-jdk`; mods from the player's mods folder or `mcb fetch litematica` |
| Making-of video | ffmpeg, edge-tts ≥ 7.3.1, scipy, Playwright | `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg` (or `pip install imageio-ffmpeg`), `pip install "edge-tts>=7.3.1"` |

All optional packages are in `scripts/requirements-optional.txt`. Installing anything is the user's call: show the
command, say what it enables, and run it only after they agree. Prefer a virtual environment if they use one.

## 2 · `mcb doctor` and `mcb selftest`

`mcb doctor` prints, in a few seconds and without changing anything: the Python version, the saved profile, and one
line per capability (`[ok]` / `[--]`), then a READY list and the exact fixes. `--brief` skips slow probes, `--json`
returns everything for scripts. Paste its READY line into your plan - it tells you which steps are possible here
(e.g. no screenshots → judge from the drawings).

`mcb selftest` builds the starter project in Chinese and English on flat ground, exports, verifies, re-reads the
schematic, writes and re-reads a world save and parses F3 text. ~5 s, offline. Run it after installing or updating.

## 3 · Profile and environment variables

The profile (`~/.mcbuild/config.json`) remembers what the player told you. `mcb config` shows it,
`mcb config --keys` lists keys:

| Key | Meaning |
|---|---|
| `game_dirs` | game folders (`.minecraft` or launcher instance folders), most important first |
| `projects_dir` | default parent folder for `mcb init` without a folder |
| `lang` | `zh` or `en` - deliverables and image labels |
| `version` | default Minecraft version for new projects (must have bundled data) |
| `author` | written into schematic metadata |
| `launcher` | informational (HMCL, PCL, Prism, official, CurseForge, Modrinth …) |
| `java`, `jdk` | java executable (17+, Voxy) and JDK 21 home (in-game test), when not found automatically |
| `client_jars` | `{"1.21.11": "path/to/client.jar"}` - `mcb config set client_jars <jar>` detects the version |
| `mod_jars` | Litematica / MaLiLib jars for the in-game test |
| `ffmpeg`, `node` | executables, when not on PATH |
| `notes` | free-text facts about the player (servers, base location) that save questions later |

Environment variables override the file: `MCBUILD_HOME` (profile + caches folder), `MCBUILD_GAME_DIRS` (os.pathsep
separated), `MCBUILD_JAVA`, `MCBUILD_JAVA_HOME`, `MCBUILD_CLIENT_JAR`, `MCBUILD_FFMPEG`, `MCBUILD_NODE`,
`MCBUILD_LANG`. Shared caches live in `MCBUILD_HOME`: `harness/<version>` (in-game test), `assets/` (texture
atlas), `versions/` and `mods/` (downloads).

## 4 · Downloads (`mcb fetch`) - ask first

Without `--yes` the command only prints what it would download (source, size, destination) and exits with code 2.
Show that to the user; run again with `--yes` only after they agree. Files go into `MCBUILD_HOME` only and are
checked against the publisher's hashes.

- `mcb fetch client --version 1.21.11` - the vanilla client jar (≈ 30 MB) from Mojang (piston-meta / piston-data),
  used only for block models and textures. In mainland China add `--mirror bmclapi` (the BMCLAPI mirror HMCL and
  PCL use; the hash still comes from Mojang's manifest).
- `mcb fetch litematica --version 1.21.11` - Litematica + MaLiLib from Modrinth for the in-game test harness (never
  copied into the player's game).
- `mcb fetch jdk` - prints the JDK 21 install command for this OS (downloads nothing).

The in-game test itself downloads Minecraft, Fabric and Gradle into the user's Gradle cache the first time
(several hundred MB, several minutes) - mention it before the first `mcb ingame`.

## 5 · Agents without the game on the machine

Cloud sandboxes and agents running on another computer have no game folder. What still works: intake, portable
designs (`source = "flat"`/`"none"`), sites from uploaded files, export, verify, materials, release, drawings and the
preview page (block shapes in map colours unless `mcb fetch client` is allowed and the network permits it).
Ask the player to upload what you would otherwise read from disk:

- a singleplayer world → zip of the save folder (only `level.dat` + `region/` files around the spot are needed);
- a server area → the Litematica area schematic (+ its origin), or a Bobby / backup `region` folder;
- the spot → F3+C text or an F3 screenshot.

Hand back the `release/` folder (zip it with `[release] zip = true`) and tell them where to put the `.litematic`
(their `<game folder>/schematics/`). The real-client test cannot run without a display.

## 6 · Other game versions

- Bundled block data: **Java 1.21.11** (`scripts/mcbuild/data/1.21.11`). Every block state is validated against it.
- **Newer versions** (26.x and later): Litematica loads schematics from older data versions and converts them, so
  1.21.11 schematics paste fine; blocks added after 1.21.11 are simply not available to the design.
- **Older versions**: a schematic may contain blocks the game does not have (they paste as air) and Litematica may
  warn about the newer data version. Use only blocks that exist in the player's version (e.g. no pale oak/resin
  before 1.21.4, no copper chests/shelves/copper lanterns/iron_chain before 1.21.9, no cherry/bamboo wood before 1.20,
  `grass` instead of `short_grass` before 1.20.3) and tell the player which version the data targets.
- Adding a version (maintainers): `data/<ver>/` needs `blocks.json(.gz)`, `registries.json(.gz)`, `items.json(.gz)`
  from the server jar's report generator (`java -DbundlerMainClass=net.minecraft.data.Main -jar server.jar --reports`),
  `history.json` (first version of each newer block), `world-template.dat` (a neutral level.dat of a fresh save),
  `meta.json` (data version, litematic version, harness versions loom/yarn/loader/fabric_api), then
  `mcb facts --version <ver>` writes `tags.json` and `facts.json.gz` through the Fabric harness (JDK 21, versions
  that still have Yarn mappings). Check with `mcb blocks stone --version <ver>` and `mcb selftest`.

## 7 · Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `No module named numpy` / `PIL` | core packages missing → `python -m pip install -r scripts/requirements.txt` |
| `tomllib` / `tomli` error | Python 3.10 without tomli → same command (requirements include it) |
| Garbled Chinese on a Windows console | the launcher `scripts/mcb.py` switches stdout to UTF-8; when calling modules directly set `PYTHONIOENCODING=utf-8` |
| `no Voxy cache for server …` | game folder unknown → ask for it, `mcb config add game_dirs …`; or set `[site] store` |
| `RocksDB … not found` | the Voxy cache was copied out of its game folder → set `[site] voxy_jar` to the Voxy mod jar |
| `L0 sections 12 / 80` | the player never visited part of the box → smaller box or ask them to fly over it |
| Preview looks flat-coloured | no client jar → `mcb fetch client` (ask) or `mcb config set client_jars …` |
| `skipping screenshots` | no Playwright → install (ask) or judge from drawings |
| Screenshots black / WebGL error | GPU blocked in headless mode → the kit retries with SwiftShader automatically; update Playwright's Chromium |
| `mcb ingame` compile errors | Litematica version with a different API → use the version matching the game (`mcb fetch litematica`) |
| Labels in images are English although lang = zh | no Chinese font on this system (Linux: `apt install fonts-noto-cjk`) |
| Block names look like "Oak Planks" in a Chinese list | names are read from the player's own game files (client jar, launcher `assets/`); none on this machine → readable ids. Add the game folder to the profile, then delete `~/.mcbuild/names/` |
