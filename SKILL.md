---
name: minecraft-build-design
description: >-
  Design Minecraft Java buildings from terrain, coordinates, screenshots or a style brief and deliver Create .nbt
  blueprints, an offline 3D preview, materials and placement instructions. Use for Minecraft 建筑设计、Create 蓝图、
  机械动力蓝图、房屋、桥梁、城堡、亭子和地形改造. Defaults to Minecraft 1.20.1 Forge + Create 6.0.8.
  Not for mod development, Bedrock Edition or functional Create machine engineering.
license: MIT (LICENSE.txt; third-party notices in THIRD_PARTY_NOTICES.md)
metadata:
  version: "2.0.0-create-local"
  author: "yimeng-YM"
  repository: "https://github.com/yimeng-YM/minecraft-build-design"
  toolkit: "mcbuild"
  local_variant: "Create .nbt output; Minecraft 1.20.1 Forge + Create 6.0.8"
---

# Minecraft 建筑设计 → Create 蓝图

将建筑设计交付为 **Create 使用的压缩结构 `.nbt` 蓝图**，附离线 3D 预览、材料 CSV 和放置说明。
默认目标为 **Minecraft Java 1.20.1 / Forge / Create 6.0.8**。这是 Create 蓝图修改版。

## 环境与输出格式

`<skill>` 指本文件所在目录。工具需要 Python 3.10+、numpy、Pillow。
使用可用的 Python 执行 `python <skill>/scripts/mcb.py <command> -p <项目绝对路径>`。
如果系统没有 `python` 命令，使用已有 Python 可执行文件的绝对路径（包括代理自带的运行时）。
首次执行 `mcb doctor --brief` 查看环境和已有玩家资料，`mcb selftest` 验证完整流程。
文件与缓存放入可写项目目录；必要时将 `MCBUILD_HOME` 设置为项目内的缓存目录。

新项目模板默认 `[export] format = "create"`、`target_version = "1.20.1"`、`loader = "Forge"`、
`create_version = "6.0.8"`。默认版本已确认，不重复询问；玩家更改目标时覆盖这些配置。
`[project] version` 是内置方块注册表版本（1.21.11），不要改成缺少内置数据的 1.20.1。
导出版本由 `target_version` 控制，1.20.1 的 DataVersion 为 3465；更名方块映射为旧名称，不存在的方块拒绝输出。
Create 使用原版 StructureTemplate gzip NBT，不能通过更改 `.schem`/`.litematic` 后缀获得。
详见 [references/create-blueprints.md](references/create-blueprints.md)。

## 需求、场地与设计

已有信息足够就开始；关键内容缺失时一次问清建筑类型、规模、风格、生存/创造、位置和地形来源。
问题模板见 [references/intake.md](references/intake.md)。位置优先 F3+C、带 F3 的截图或坐标；没有场地则做可移动蓝图。
地形可以来自存档、Bobby、Voxy 或区域蓝图；只读玩家存档、缓存、模组和服务器。
可选依赖只在功能需要时安装，尊重当前任务中已有授权。

1. `mcb init <项目绝对路径> --name 名称 --id AsciiId --source anvil|voxy|schematic|flat|none --lang zh|en`。
   将附件复制进 `input/`，在 `artifacts/brief.md` 写下位置、数据、尺寸、风格、朝向、版本、交付物和默认选择。
2. 有场地时设置 `[site]`，执行 `site`、`map`、`analyze` 确定地面、入口、已有建筑和保留区域。
   定位见 [references/site-and-location.md](references/site-and-location.md)，风格见 [references/style.md](references/style.md)。
3. `design.py` 用 `B = Build(P.site())`、`F = B.frame(origin, turns)` 和统一材料表；旋转同时处理位置和方块状态。
   API 见 [references/api.md](references/api.md)，设计见 [references/design-guide.md](references/design-guide.md)。
4. `design → export → verify → preview`，查看平面/立面/3D 预览并修复形体、支撑、照明和通行问题。
   有截图能力时用 `preview --shots` 看整体、入口、眼平、剖面、夜景；没有 Playwright 时仍可提供 HTML 和绘图。
5. `mcb verify` 必须 PASS：检查 NBT、坐标、调色板、方块实体、设计一致性、方块版本，以及建筑连接/支撑/照明/通路。
   按实际执行的结果报告验证范围。

Create 默认只导出设计格子，不把未改动地形作为施工材料；局部坐标从零开始，世界原点写入
`artifacts/export-report.json`。未设置的格子在 Create 蓝图世界中视为空气，其施工影响见专用参考。
当前 `Build` 只支持内置原版方块；输出 Create 文件不等于能设计可工作的 Create 机器。
没有模组方块状态、机器方块实体、转速/应力/物流数据时不臆造机械功能，改用玩家提供的机器蓝图或必要数据。

## 交付与放置

`materials → preview → release` 生成 `release/<id>-1.20.1.nbt`、离线 HTML、材料 CSV 和中文/英文放置说明，
可用时附截图。`release` 要求本次导出后验证 PASS。材料 CSV 是建筑估算，蓝图炮检查表为施工依据。
只有玩家要求时用 `format = "litematic"` 或 `schem = true` 输出其他格式。

使用 **实际实例的 `schematics/` → Create 蓝图桌 → 手持定位 → 蓝图炮** 流程，说明尺寸、包围盒最小角和目标版本。
默认不替换蓝图空气；若需要清理地形，建议按预览手动清理。替换空气会影响整个包围盒的空气位置，
不能声称只清理明确指定的格子。`mcb release` 自动生成这些说明。
玩家要求复制到游戏目录时使用新文件名，避免覆盖已有蓝图。回复给出主要文件链接、方案、位置和检查结果。

没有 Create 实机导入/施工测试就明确说明。原来的 `mcb ingame` 是 Fabric/Litematica 测试器，
不能证明 Forge/Create 兼容，Create 模式下会拒绝运行。容器为空，不导出库存、机器配置、实体和超强力胶。
视频为可选功能，不能把模拟预览冒充游戏录像。大建筑分成独立项目/蓝图并列出各自原点；
`max_region` 只用于 Litematica，不会自动拆分 Create 文件。
