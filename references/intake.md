# Intake: ask once, ask little, remember the answers

## Contents
1. Why and when
2. Message templates (中文 / English)
3. Where the player finds things (any launcher)
4. Server terrain: which option they have
5. Launcher folders per OS (only when the player cannot open the folder)
6. Saving answers to the profile
7. Examples

## 1 · Why and when

A one-line answer from the player ("here's my F3+C text") replaces minutes of guessing: disk searches, screenshot
camera fitting, wrong-site rebuilds. So before heavy work:

1. `mcb doctor --brief` - the profile may already know the game folder, language, version and notes.
2. List what the request leaves open. Ask only what changes the result: location, world data, size, style. Skip
   anything with a sensible default (survival/creative → assume survival-friendly; deliverables → the default set).
3. One message, at most ~6 short numbered items, each with a default the player can accept with "ok".
4. After the reply, save stable facts (§6) and start. Don't ask again unless a wrong guess would waste the job.

## 2 · Message templates

Adapt, shorten, and drop items that are already answered. Keep the player's language.

**中文**

> 开工前确认几件事（不确定的可以直接说"你定"）：
> 1. **建在哪**：站在要建的位置看向那里，按 **F3+C**，把复制到的那行文字（`/execute in … run tp @s …`）发给我；
>    或者开着 F3 截一张图（F2）。没有固定地点也行，我做成可以随处放的投影。
> 2. **哪个世界**：单人存档的话，在"单人游戏 → 选中世界 → 编辑 → 打开世界文件夹"，把路径发我；服务器的话，你装了
>    Voxy 或 Bobby 吗？或者用 Litematica 框选那片区域另存为投影，并告诉我选区原点坐标。
> 3. **游戏文件夹**（只需一次）：游戏里"选项 → 资源包 → 打开资源包文件夹"，再往上一层就是；以及游戏版本（F3 左上角第一行）。
> 4. **建什么、多大、什么风格**：比如"两层小木屋，9×7，和我家风格一致"。默认：生存可建、中等大小。
> 5. **需要的交付**：默认给投影 + 三维预览网页 + 材料清单 + 使用说明；要不要游戏内实测截图 / 制作过程视频？

**English**

> A few quick questions before I start (say "your call" for any of them):
> 1. **Where**: stand on the spot, look at it and press **F3+C**, then paste the copied line
>    (`/execute in … run tp @s …`) - or send a screenshot taken with F3 open. No fixed place? I'll make a portable
>    schematic.
> 2. **Which world**: singleplayer → Singleplayer → select the world → Edit → Open World Folder, send me the path.
>    Server → do you have Voxy or Bobby installed? Or select the area with Litematica, save it as a schematic and tell
>    me the selection's origin coordinates.
> 3. **Game folder** (once): in game Options → Resource Packs → Open Pack Folder, then go up one folder; plus your
>    Minecraft version (first line of F3).
> 4. **What, how big, which style**: e.g. "two-storey cabin, 9×7, matching my house". Default: survival-friendly,
>    medium size.
> 5. **Deliverables**: by default schematic + 3D preview page + materials list + guide. Also an in-game test with
>    screenshots, or a making-of video?

## 3 · Where the player finds things (works with every launcher)

| Need | How the player gets it |
|---|---|
| Exact position + view | Press **F3+C** briefly in game (holding it ~10 s deliberately crashes the game) → the clipboard holds `/execute in minecraft:overworld run tp @s X Y Z YAW PITCH`. Paste it to you. Feed it to `mcb camera set --f3 "…"`. |
| Screenshot of the spot | F2 saves to `<game folder>/screenshots/`. With **F3 open**, the image shows XYZ, Facing (yaw/pitch), "Targeted Block" and the version. `mcb find-data` lists the newest screenshots. |
| The block they point at | F3 → right side "Targeted Block: x, y, z" (that is usually *the* spot). |
| Field of view | Options → FOV (default 70; "Quake Pro" = 110). Needed only with a screenshot. |
| Game folder | Options → Resource Packs → **Open Pack Folder** → one folder up. Launchers with version isolation (HMCL, PCL, Prism, CurseForge, Modrinth …) give the instance folder - that is the right one. |
| A singleplayer save | Singleplayer → select world → **Edit** → **Open World Folder**. |
| Game version / loader | F3 first line, e.g. `Minecraft 1.21.11 (1.21.11/fabric)`. |
| Installed mods | `<game folder>/mods` (Litematica + MaLiLib to paste; Voxy / Bobby for server terrain). |
| Their house's style | Coordinates of two opposite corners (F3 while standing there) → `mcb style --box=…`, or a few screenshots. |

## 4 · Server terrain: which option they have

| Player has | Gives you | `[site]` |
|---|---|---|
| **Voxy** mod (any server they flew over) | nothing - the cache is in their game folder | `source = "voxy"`, `server = "<address part>"` |
| **Bobby** mod (keeps server chunks) | nothing - `<game folder>/.bobby/<server>/…` | `source = "anvil"`, `world = "<folder with r.X.Z.mca>"` |
| **Litematica** only | Area selection around the spot (build + 40 blocks, from below ground to above trees) → *Save schematic*; the selection **origin** coordinates (shown in the Area Editor) | `source = "schematic"`, `schematic = "…"`, `origin = [x, y, z]` |
| Server owner access | a region backup (`world/region/*.mca` covering the area) | `source = "anvil"`, `world = "<folder>"` |
| Nothing of the above | coordinates (+ screenshots for style) | `source = "flat"` with `ground_y`, or `none` → portable |

Voxy and Bobby only know chunks the player has seen; ask them to fly around the area once if `mcb site` reports
missing sections.

## 5 · Launcher folders per OS

Only for when the player cannot open the folder themselves (`mcb find-data` already checks these).

| Launcher | Windows | macOS | Linux |
|---|---|---|---|
| Official | `%APPDATA%\.minecraft` | `~/Library/Application Support/minecraft` | `~/.minecraft` |
| Prism / MultiMC / PolyMC | `%APPDATA%\PrismLauncher\instances\<name>\minecraft` (MultiMC: next to its exe) | `~/Library/Application Support/PrismLauncher/instances/…` | `~/.local/share/PrismLauncher/instances/…` (Flatpak: `~/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/…`) |
| CurseForge | `%USERPROFILE%\curseforge\minecraft\Instances\<name>` | `~/Documents/curseforge/minecraft/Instances/<name>` | - |
| Modrinth App | `%APPDATA%\ModrinthApp\profiles\<name>` | `~/Library/Application Support/ModrinthApp/profiles/<name>` | `~/.local/share/ModrinthApp/profiles/<name>` |
| HMCL / PCL (portable) | `.minecraft` next to the launcher exe; version isolation → `.minecraft\versions\<name>` | same idea | same idea |

HMCL's and PCL's own folder lists are read automatically when present. Still nothing? `mcb find-data --scan auto`
searches home folders and drive roots (bounded, about 10 s) and `--remember` saves what it finds.

## 6 · Saving answers to the profile

```bash
mcb config add game_dirs "<game folder>"          # most important first
mcb config set lang zh                             # or en
mcb config set version 1.21.11
mcb config set launcher HMCL
mcb config set author "<their name for schematic metadata>"
mcb config set projects_dir "<where build projects go>"
mcb config add notes "server play.example.net has a Voxy cache; base at -360 64 -270"
```

The profile is a local JSON file (`~/.mcbuild/config.json`, or `$MCBUILD_HOME`). It stays on this machine; tell the
player what you saved. Notes are for facts that save questions next time - no passwords, no account data.

## 7 · Examples

- *"帮我在我家旁边盖个钓鱼小屋"* + a screenshot without F3, profile empty → ask items 1–3 (F3+C at the spot, which
  world, game folder), default the rest; one message.
- *"Design a medieval gatehouse, about 20 wide, I'll place it myself"* → no questions: `source = "flat"`, portable,
  medium size, medieval palette; state the defaults in the reply.
- Profile already has the game folder and a note "server X has Voxy" + the player pastes F3+C text → no questions;
  read the Voxy cache around those coordinates and start.
