# Create 蓝图：Minecraft 1.20.1 Forge + Create 6.0.8

默认成果为 `.nbt`。依据 Create 官方
[SchematicExport.java](https://github.com/Creators-of-Create/Create/blob/mc1.20.1/dev/src/main/java/com/simibubi/create/content/schematics/SchematicExport.java)，
Create 使用 `StructureTemplate.save` 和 `NbtIo.writeCompressed`。蓝图炮空气处理见
[SchematicannonBlockEntity.java](https://github.com/Creators-of-Create/Create/blob/mc1.20.1/dev/src/main/java/com/simibubi/create/content/schematics/cannon/SchematicannonBlockEntity.java)。

## NBT 结构

gzip 压缩，Java 大端 NBT，根标签是 Compound；没有 Sponge 的 `Schematic` 包装层：

| 字段 | 类型 | 内容 |
|---|---|---|
| `DataVersion` | Int | 1.20.1 为 3465 |
| `size` | List[Int] | `[宽, 高, 深]`，三项正整数 |
| `palette` | List[Compound] | `Name` 字符串，可选 `Properties` 字符串映射 |
| `blocks` | List[Compound] | `pos: List[Int]`、`state: Int`，需要时附 `nbt: Compound` |
| `entities` | List[Compound] | 当前为空，不导出实体或胶水 |

位置相对包围盒最小角，状态为调色板下标。显式设计空气保留，未指定格子省略，但 Create 蓝图世界视其为空气。
方块实体使用对应 `id` 和局部 `x,y,z`；不写 1.20.5 后的 `components`，容器无库存、机器无配置。

## 配置与命令

新建项目默认 `[export] format = "create"`、`target_version = "1.20.1"`、`loader = "Forge"`、`create_version = "6.0.8"`。
旧项目设置相同配置后重新 `design → export → verify → preview → materials → release`。
`[project] version` 保留内置注册表版本；`export.target_version` 决定输出版本。
`mcbuild.create.export_create` 映射 `iron_chain → chain`、`short_grass → grass` 等名称并拒绝 1.20.1 不存在的方块。
版本检查依赖内置注册表和方块历史，不能代替目标客户端的实机检查。

`artifacts/export-report.json` 是当前输出报告，包含格式、文件、世界原点、尺寸、方块数和版本。
Create 为单结构包围盒，仅输出设计，不复制无关场地；`mode`、`max_region`、`region_penalty` 只用于
`format = "litematic"`，不会将 Create 拆分。需拆分时做独立项目并记录每个原点。

## 使用与施工边界

1. `.nbt` 放入实际游戏实例 `schematics/`，与 `mods/` 同级。
2. 在 Create 蓝图桌中选择文件并制作蓝图；手持调整位置并确认。场地蓝图的包围盒最小角对齐说明书原点。
3. 把已定位蓝图放入蓝图炮，供应材料和火药。CSV 为建筑估算，实际施工以蓝图炮检查表为准。
4. 默认用不替换空气的模式。需要清理时建议人工清理；替换空气可能清除整个包围盒所有蓝图空气位置，
   包括从未明确设计的格子，不能将它描述为只清除明确设计的树/泥土。

文件格式正确不保证蓝图炮自动放置所有方块，液体或复杂多方块可能需人工处理。
当前设计器只支持内置原版方块；没有 Create 机器的方块状态、方块实体和机械逻辑数据，
不检查应力、转速、物流、电路或胶水，不承诺机器功能。

## 验证

离线检查 gzip、标签类型、坐标范围/重复、调色板索引、方块实体、设计一致性、建筑支撑/照明/通路及版本。
`mcb selftest` 覆盖中英文交付、预览、负坐标、稀疏空气、容器、旧名称、不合法下标、新版方块拒绝和旧格式回归。
原 `mcb ingame` 使用 Fabric + Litematica，Create 模式明确拒绝；未在 1.20.1 Forge + Create 6.0.8 客户端
导入/施工时必须说明未进行实机验证。
