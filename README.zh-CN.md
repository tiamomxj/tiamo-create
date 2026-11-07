# Minecraft 建筑设计 → Create 蓝图

用于 AI 编程代理的 Agent Skill：设计 Minecraft 建筑，输出 **Create `.nbt` 蓝图**、离线 3D 预览、
材料清单和放置说明。默认目标：**Minecraft Java 1.20.1 / Forge / Create 6.0.8**。

基于 [yimeng-YM/minecraft-build-design](https://github.com/yimeng-YM/minecraft-build-design)，
保留原作者 yimeng-YM 的署名、MIT 许可证和第三方声明。此版本增加 Create 导出器、校验和交付流程。

## 功能与安装

- 根据风格、尺寸、坐标或截图设计房屋、桥梁、亭子、城堡和景观。
- 读取存档、Bobby、Voxy 或区域蓝图作为场地；也支持可移动建筑。
- 输出 gzip 压缩的原版结构 `.nbt`，通过 Create 蓝图桌加载。
- 附独立 HTML 3D 预览、材料 CSV、中文或英文放置说明。
- 检查文件、坐标、方块实体、版本兼容、支撑、照明和通路。
- 可选保留 `.litematic` 和 Sponge `.schem` 导出。

需要支持 Agent Skills、能执行 Python 的代理，以及 Python 3.10+。
把仓库目录放进代理技能目录，文件夹名保持 `minecraft-build-design`。
例如 Codex 的 `~/.codex/skills/minecraft-build-design/`，或代理支持的 `.agents/skills/`。

```bash
python -m pip install -r scripts/requirements.txt
python scripts/mcb.py doctor --brief
python scripts/mcb.py selftest
```

如果缓存目录不可写，将 `MCBUILD_HOME` 设置为可写目录。可选依赖仅在相关功能需要时安装。

## 使用

对代理说：“设计一座 15×15 的中式亭子，输出 Create 蓝图、预览和材料清单。”

```bash
python scripts/mcb.py init ./demo --name "Create Cottage" --id CreateCottage --source flat --lang zh
python scripts/mcb.py -p ./demo all --no-shots
```

成果位于 `demo/release/`。把 `.nbt` 放入实际游戏实例的 `schematics/`（与 `mods/` 同级），
在 Create 蓝图桌选择文件，手持定位并确认，再用蓝图炮施工。
默认不替换蓝图空气；需要时先按预览手动清理地形。替换空气可能清除整个包围盒的空气位置。
实际材料需求以蓝图炮检查表为准。

## 默认配置与限制

```toml
[export]
format = "create"
target_version = "1.20.1"
loader = "Forge"
create_version = "6.0.8"
```

`[project] version` 保留内置数据版本 1.21.11；`target_version` 决定输出版本，1.20.1 的 DataVersion 为 3465。
导出映射旧方块名称并拒绝目标版本不存在的方块。
`format = "litematic"` 选择原投影输出，`schem = true` 附加 Sponge 文件。

当前设计器支持内置原版建筑方块，不包含 Create 模组方块数据或机械逻辑。
容器为空，不导出库存、机器配置、实体或超强力胶。
已完成离线自检，尚未在 1.20.1 Forge + Create 6.0.8 客户端导入或用蓝图炮施工验证。
原 Fabric/Litematica 游戏测试器不能验证 Create，Create 模式下拒绝运行。

详细说明：[SKILL.md](SKILL.md)、[Create 蓝图](references/create-blueprints.md)、[设计 API](references/api.md)。

## 验证与许可证

`python scripts/mcb.py selftest` 包含 7 项检查，覆盖中英文交付、预览、负坐标、稀疏空气、方块实体、
旧名称、新版方块拒绝、损坏文件和可选 Litematica 导出。

MIT；见 [LICENSE.txt](LICENSE.txt) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
非 Mojang 或 Microsoft 官方产品。
