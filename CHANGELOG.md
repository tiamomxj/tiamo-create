# Changelog

## Create blueprint variant — 2026-11-07

- Default output: gzip StructureTemplate `.nbt` for Minecraft 1.20.1 Forge + Create 6.0.8.
- Added independent NBT checks, version-aware export, Create placement guides and offline previews.
- Added 7-check offline selftest coverage and cross-platform GitHub Actions.
- Preserved optional Litematica and Sponge outputs and upstream MIT attribution.
- No Forge/Create client import or Schematicannon print test has been performed.

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).
The version is also recorded in `SKILL.md` (`metadata.version`); release tags are `vX.Y.Z`.

## [2.0.0] - 2026-10-27

First public release. (1.x was a private prototype tied to one machine.)

### Added
- Works with any agent that supports Agent Skills (`SKILL.md` per agentskills.io; no agent-specific tool names) and
  on Windows, macOS and Linux with Python 3.10+.
- Intake step: `mcb doctor --brief` shows what the saved player profile already knows, then the agent asks one short
  round of questions (templates in `references/intake.md`): F3+C text or an F3 screenshot for the spot, the in-game
  "Open Pack Folder" / "Open World Folder" buttons for paths. Answers are kept in `~/.mcbuild/config.json`.
- `mcb doctor` (works before numpy is installed), `mcb config`, `mcb selftest`, `mcb fetch client|litematica|jdk`
  (downloads only with `--yes`, hash-checked; `--mirror bmclapi` for mainland China), `mcb camera set --f3`
  (exact screenshot camera from F3 data, no fitting), `mcb find-data --scan`.
- Game-folder discovery for the official launcher, Prism/MultiMC/PolyMC, CurseForge, Modrinth App, ATLauncher,
  GDLauncher, and the folder lists of HMCL and PCL; Java discovery across vendors and launcher runtimes.
- Terrain from Bobby chunk caches and bare region folders; old block ids (`grass`, `chain`) read correctly.
- `[export] target_version` (1.20.1 and newer): target DataVersion, old ids for renamed blocks, and `verify` fails
  on blocks the target version does not have.
- Deliverables in Chinese or English (`[project] lang`): guide, preview page, materials list, drawings, video labels.
- Preview without a client jar: block shapes in map colours. Screenshots through Python or Node Playwright with
  per-OS GPU flags and a software fallback.
- CI: spec validation and selftest on Windows, macOS and Linux (Python 3.10 and 3.14); release packaging with
  SHA-256 checksums.

### Changed
- Block, item and biome names are read from the player's own game files at run time (cached per version) instead of
  being shipped.
- Bundled game data is gzipped (8.5 MB → 0.5 MB); release zip under 1 MB.
- Command-line messages are English; deliverables follow the project language.

### Removed
- Hard-coded machine paths and the dependencies on `nbtlib` and `matplotlib`.

### Fixed
- The in-game test could pick a Litematica jar built for another game version.
- The making-of video stage waited forever when a picture (e.g. the site map of a flat project) was missing.

[2.0.0]: https://github.com/yimeng-YM/minecraft-build-design/releases/tag/v2.0.0
