# mcbuild toolkit reference

`scripts/mcbuild` (Python 3.10+, numpy, Pillow; optional: scipy, zstandard + Java 17+ for Voxy, JDK 21 for the
in-game harness, Playwright for screenshots - see setup.md). Data per game version in `mcbuild/data/<version>/`.

## Contents
1. CLI
2. project.toml keys
3. Design API: Build, Frame, composites
4. shapes / nature
5. Blocks: registry, facts, tags
6. Terrain: Site
7. Camera, analysis, maps
8. Export / verify / preview / world / ingame modules
9. Snippets

## 1 · CLI  (`python <skill>/scripts/mcb.py [-p PROJECT] <cmd>`)

| cmd | does | outputs |
|---|---|---|
| `doctor [--brief] [--json]` | what works here + saved profile + exact fixes | stdout |
| `config [set\|add\|remove\|unset KEY VALUE] [--keys]` | show / change the player profile (~/.mcbuild/config.json) | config.json |
| `fetch client\|litematica\|jdk --version V [--yes] [--mirror bmclapi]` | download missing game files (asks for --yes) | MCBUILD_HOME/versions, mods |
| `selftest [--keep] [--shots]` | offline end-to-end check of the kit | stdout |
| `init [DIR] --name N --id ID --source S --lang zh\|en --images …` | new project from templates | project.toml, design.py, input/ |
| `find-data [--dir D…] [--scan auto\|D…] [--remember] [--json]` | game folders, Voxy/Bobby caches, saves (+player pos), Xaero waypoints, schematics, screenshots | stdout |
| `site [--scale]` | read `[site]` → grid | artifacts/site.npz, site-palette.json, site-map.png, site-height.png |
| `map --box=x0,z0,x1,z1 --scale --grid --mark=x,z,txt --rect=… --design --out` | top-down map with coordinates | png |
| `analyze --box=… --footprint WxD --top N` | heights/water/builds/flat candidates | analysis.json, analysis-map.png |
| `style --box=x0,y0,z0,x1,y1,z1 --name N` | reference build statistics | style-N.json/.png, style-N-drawings/ |
| `camera set --f3 TEXT [--image I --fov F]` | camera straight from F3 / F3+C data | camera.json, camera-overlay.png |
| `camera fit\|render\|outline\|ray` | screenshot camera (spec: artifacts/camera-spec.json) | camera.json, camera-overlay.png, plot.json, plot-map.png |
| `design [--no-drawings]` | run design.py, rules pass, cache | design.npz, design-summary.json, drawings/ |
| `draw [--no-terrain]` | drawings only | drawings/plan-top, elev-*, layers.png |
| `export` | default Create .nbt; optional format=litematic or schem=true | release/*.nbt, export-report.json |
| `verify [--strict]` | acceptance checks | verification.json, verify-maps.json |
| `materials` | survival list | materials.json/.csv, materials-by-part.json |
| `preview [--shots]` | offline page (+ headless shots of all views) | preview/index.html, views.json, shots/ |
| `shots VIEW[@day][@cut][@ctx][@h] … --width --height` | screenshots; VIEW = preset or `cam=x,y,z:tx,ty,tz:fov` | shots/*.png |
| `ingame [--no-run] [--modes …] [--showcase]` | real-client paste test (opens the game) | ingame/ingame-report.json + png, release/*展示存档.zip or *showcase-world.zip |
| `release` | deliverables + guide (使用说明.md / README.md) | release/ |
| `all [--ingame] [--no-shots]` | design → export → verify → materials → preview(+shots) → (ingame) → release | |
| `video init\|narrate\|check\|stills\|mix\|render` | making-of video (video.md) | video/, release/*.mp4 |
| `blocks QUERY` | search ids / English or Chinese names, show properties + light/collision | stdout |
| `facts --version V` | regenerate per-state facts from the game (new version) | data/V/facts.json.gz |

Negative numbers after an option need `=` (`--box=-420,-330,-200,-150`).

## 2 · project.toml

Local default: `[export] format = "create"`, `target_version = "1.20.1"`, `loader = "Forge"`, `create_version = "6.0.8"`.
Keep `[project] version` at the bundled registry version. See [create-blueprints.md](create-blueprints.md).
`mode`, `max_region`, `region_penalty` only affect Litematica; Create exports design cells in one structure box.

`[project]` name, id, version, lang (zh|en), author · `[site]` source, server, dimension, store, voxy_jar, world,
schematic, origin, margin, box, ground_y, water_y, biome, top, layers, base · `[design]` script, origin, turns (free
keys, read by design.py) · `[export]` mode (site|portable), file, name, author, description (`{x} {y} {z}`
placeholders), region_penalty, part_names, schem, max_region, target_version · `[verify]` spawnproof, spawnproof_strict, spawnproof_scope (build|area),
walk_start, walk_targets, walk_swim, max_step, max_drop, allow_floating · `[preview]` title, subtitle, eyebrow,
lead, front, context, below, above, box, grow_to_neighbours, views (list of {name,label,pos,target,fov,cut} or
{eye,yaw,pitch,fov,compare}), stats, mat_note, context_label, outline_label · `[ingame]` views ({name,label,pos
(eye),target,time,fov}), modes · `[release]` notes, folder, zip.

## 3 · Design API

```python
from mcbuild import Build, AIR, get_project, shapes, nature, parse, facts, in_tag
P = get_project()                       # current project (cfg, site(), art, input, path())
B = Build(P.site(), P.name)             # cells: {(x,y,z): State}, part: {(x,y,z): str}, cur, notes
F = B.frame((x, y, z), turns=0, mirror=None)
```
- Local axes before rotation: +x east, +y up, +z south. `turns` = clockwise quarter turns (positions **and**
  states: facing, axis, rotation, connections, rail shapes …). `mirror='x'|'z'` flips before turning.
- `F.put(lx,ly,lz, spec, part=None)` · `F.fill(a, b, spec, part, only_empty=False, hollow=False)` (inclusive) ·
  `F.clear(a, b)` (AIR = remove terrain) · `F.get` (design cell) · `F.at` (design or terrain) · `F.terrain` ·
  `F.remove` (forget a cell) · `F.ground(lx, lz)` (local y of the terrain surface block; build on `+1`) ·
  `F.water_top(lx, lz)` · `F.w(...)` / `F.local(...)` / `F.dir('north')` conversions.
- `spec` strings: `'oak_stairs[facing=east,half=top]'` — missing properties take the game defaults; invalid
  names/values raise immediately. Use local facings; they rotate with the frame.
- Composites: `F.door(lx,ly,lz, facing, hinge='left', wood='oak')` (facing = direction you look walking in),
  `F.double_door`, `F.bed((x,y,z), facing, color)`, `F.tall(lx,ly,lz, 'rose_bush')`, `F.chest_pair(lx,ly,lz, facing)`,
  `F.hanging_lantern(lx,ly,lz, chain=1)`, `F.bamboo(lx,ly,lz,h)`, `F.on_ground(lx,lz, spec, dy=1, soil=None)`.
- `B.cur = 'part'` sets the part for following placements; parts name sub-regions (`[export] part_names`).
- `B.notes.append('…')` → design-summary and the guide.
- The kit runs `B.resolve()` (stairs shapes, pane/fence/wall/gate connections, waterlogging from real water,
  leaf distance, snowy grass) after the script; you may call it yourself before reading states.
- design.py must leave a module-level `B` (or define `build(project) -> Build`).

## 4 · shapes / nature

`shapes`: `box, walls, floor, line, line_cells, polyline, pattern, mix, pixel_circle(d), disc_cells(r),
ring_cells(r, t), disc, ring, cylinder(base, r, h, hollow), sphere, dome, ellipse_disc, gable_roof(x0,z0,x1,z1,y,
stairs, ridge='x', overhang, cap, gable, under), hip_roof(..., cap, fill), pyramid_roof, shed_roof, flat_roof,
stair_flight(start, direction, rise, stairs, support, clear), spiral_stair, ladder, window_grid, arch,
foundation(F, cells_xz, top_ly, spec, extra), pillar_down(F, lx, lz, top_ly, spec), level_pad(F, x0,z0,x1,z1, ly,
top, fill, clear_h, blend), path(F, pts, spec, width), scatter(F, x0,z0,x1,z1, rng, density, choices, soil)`.
`nature`: `palm(F, lx, lz, height, lean, fronds, part)`, `round_tree(F, lx, lz, height, radius, rng, log, leaf)`,
`conifer`, `bush`, `bamboo_clump(F, spots, heights)`, `flowers(F, spots, rng, kinds)` — all stand on the terrain.

## 5 · Blocks

`parse(spec)`, `make(name, props)`, `State` (`.name .short .props .get(k) .has(k) .with_(**kw) .key() .nbt()`),
`AIR`, `properties(name)`, `known(name)`, `display_name(id, 'zh'|'en')` (`zh_name` = Chinese), `in_tag(st,
'minecraft:logs')`, `tag_members(tag)`. Old ids from older saves (`grass`, `chain`) map to current ones.
`facts(st)` — computed by the game for that exact state: `lum` (light), `opacity`, `opaque` (full opaque cube),
`full_cube`, `solid`, `replaceable`, `spawnable` (zombie can spawn on it), `water/lava/source`, `boxes`
(collision boxes), `top`, `face_full(d)`, `face_center(d)`, `face_rigid(d)`, `light_blocks(d)`, `map_color`,
`hardness`, `item`, `be` (block-entity id), `classes` (Java class chain, e.g. `'StairsBlock'`, `'PlantBlock'`).

## 6 · Terrain: `P.site()` → `Site`

`world(x,y,z)` → State (AIR outside / unknown) · `kind(st)` → air | water | lava | plant | light | solid ·
`ground_top(x,z)` (highest solid incl. trees/builds) · `terrain_top(x,z)` (ignores vegetation) · `water_top(x,z)` ·
`is_water` · `biome_at` · `contains` · `known` · `box` · `heightmap(test)` and `lut(fn)` (vectorised over the
grid) · `palette_states()`. Helpers in terrain.py: `is_natural(st)`, `is_vegetation(st)`, `discover()`.

## 7 · Camera, analysis, maps

`camera.Camera(yaw, pitch, fov, eye, W, H)` `.project(P)` `.ray(u, v)`; `camera.fit(pairs, W, H, init)` →
(cam, {rmsPx…}); `site_points(site, names, box)`; `match(cam, spots, candidates)`; `raycast(site, cam, u, v)`;
`columns_in_polygon(site, cam, poly)`; `stroke_polygon(img, rgb)`; `render_site(site, cam)`.
`analyze.find_builds(site, box)`, `flat_spots(site, (w, d), box)`, `style_report(P, box6, name)`.
`maps.render_map(site, out, box, scale, grid, label_every, marks, boxes, polys, cells, title)`,
`maps.design_drawings(build, out_dir)`, `maps.state_colors(states, view)`.

## 8 · Other modules

`create.export_create(build, path, target='1.20.1')`, `create.check_create_file(path, expect_dv=3465)`:
Create structure NBT writer and independent format checker. Default CLI output is Create; legacy functions below remain optional.

`schematic.export_litematic(build, path, mode, name, author, description, penalty, part_names, max_size)`,
`read_litematic`, `litematic_cells`, `write_schem`, `read_schem`, `read_structure`, `read_any` ·
`light.block_light(grid, states)`, `sky_light` · `verify.verify(P)`, `verify.Walker` · `preview.build_preview(P)`,
`auto_views`, `shoot` · `world.write_world(dir, site, build, name, spawn)` (vanilla save) ·
`ingame.run_ingame(P, run, modes, showcase)` · `harness.ensure(version)`, `dump_facts(version)` ·
`nbt.load/save/dumps/loads` (typed NBT) · `compat` (target versions: `DATA_VERSIONS`, `first_version`,
`missing_blocks`) · `i18n.t(key)` (deliverable strings), `i18n.lang()` · `browser.shoot(html, out, w, h, views)`
(Python/Node Playwright) · `util` (profile-aware discovery: `game_dirs`, `client_jar`, `find_java`) ·
`config.get/set_value` (profile).

## 9 · Snippets

```python
# heights around a spot (in a scratch script or design.py)
S = P.site()
for z in range(z0, z1):
    print(z, [S.ground_top(x, z) - 60 for x in range(x0, x1)])
# local positions of walk targets for project.toml
F = Build(None).frame((-389, 63, -298), turns=0); print(F.w(0, 1, 0))
# one palette for the whole build
PAL = {'wall': 'oak_planks', 'roof': 'dark_oak_stairs'}; F.fill(a, b, PAL['wall'])
# ring windows
ring, inner = shapes.pixel_circle(9)
for u, v in ring: F.put(12, v, 1 + u, 'dark_oak_planks')
```
