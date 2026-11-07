"""Language of the deliverables (guide, preview page, materials list, drawings, map labels, video data).

The language comes from project.toml `[project] lang`, else the profile / MCBUILD_LANG, else the system locale.
Supported: 'zh' (简体中文) and 'en' (English); anything else falls back to English. Command-line logs are English.
Block and item names come from the game's own zh_cn / en_us translations (bundled per version).
"""
from __future__ import annotations
import locale, os

SUPPORTED = ('zh', 'en')
_STATE = {'lang': None}


def normalize(lang):
    lang = (lang or '').lower().replace('-', '_')
    if lang.startswith('zh'):
        return 'zh'
    return 'en' if lang else None


def default_lang():
    from . import config
    v = normalize(config.get('lang'))
    if v:
        return v
    for env in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        if os.environ.get(env):
            return normalize(os.environ[env]) or 'en'
    try:
        loc = locale.getlocale()[0] or ''
        if not loc and os.name == 'nt':
            import ctypes
            loc = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), '')
        return 'zh' if 'zh' in loc.lower() or 'chinese' in loc.lower() else 'en'
    except Exception:
        return 'en'


def set_lang(lang):
    _STATE['lang'] = normalize(lang) or default_lang()


def lang():
    if _STATE['lang'] is None:
        _STATE['lang'] = default_lang()
    return _STATE['lang']


def image_lang():
    """Language for text drawn into PNG images: Chinese needs a CJK font on this machine."""
    if lang() == 'zh':
        from .util import cjk_font
        return 'zh' if cjk_font() else 'en'
    return lang()


def t(key, _lang=None, **kw):
    row = S.get(key)
    if row is None:
        return key.format(**kw) if kw else key
    s = row[0] if (_lang or lang()) == 'zh' else row[1]
    return s.format(**kw) if kw else s


def ti(key, **kw):
    """t() in the language used for text inside images."""
    return t(key, image_lang(), **kw)


def block_name(item_or_block, _lang=None):
    from .registry import display_name
    return display_name(item_or_block, _lang or lang())


DIRS = {'north': ('北', 'north'), 'south': ('南', 'south'), 'east': ('东', 'east'), 'west': ('西', 'west'),
        'se': ('东南', 'south-east'), 'sw': ('西南', 'south-west'), 'nw': ('西北', 'north-west'), 'ne': ('东北', 'north-east')}


def direction(d, _lang=None):
    z, e = DIRS.get(d, (d, d))
    return z if (_lang or lang()) == 'zh' else e


# key: (中文, English)
S = {
    # ---- preview views and page
    'view.overview': ('全景', 'Overview'),
    'view.corner': ('{d}看', 'From the {d}'),
    'view.front': ('正面', 'Front'),
    'view.cut': ('第 {n} 层剖视', 'Floor {n} cut-away'),
    'view.top': ('俯视', 'Top'),
    'view.eye': ('人视', 'Eye level'),
    'view.shot': ('截图同视角（可对比原图）', 'Your screenshot view (compare)'),
    'view.night': ('{label}（夜）', '{label} (night)'),
    'view.dusk': ('{label}（黄昏）', '{label} (dusk)'),
    'page.title': ('{name} · 方块预览', '{name} · block preview'),
    'page.eyebrow': ('JAVA {v} · LITEMATICA 投影', 'JAVA {v} · LITEMATICA SCHEMATIC'),
    'page.matnote': ('按生存模式需要准备的物品：门、床、双格植物算一个，水按水桶计。不含投影区域里按原地形保留的方块。',
                     'Items to gather in survival: doors, beds and tall plants count once, water counts as buckets. '
                     'Terrain kept as it is inside the schematic regions is not included.'),
    'page.context': ('周边地形', 'Surroundings'),
    'page.gallery': ('游戏内实拍 · 原版 {v} 客户端，用 Litematica 粘贴本投影后截图',
                     'In-game shots · vanilla {v} client after pasting this schematic with Litematica'),
    'stat.file': ('投影文件', 'Schematic'),
    'stat.origin': ('放置原点', 'Placement origin'),
    'stat.size': ('投影外框', 'Bounding box'),
    'stat.regions': ('子区域', 'Sub-regions'),
    'stat.regions_v': ('{n} 个', '{n}'),
    'stat.blocks': ('建筑方块', 'Blocks'),
    'stat.blocks_v': ('{n} 个', '{n}'),
    'stat.spawn': ('防刷怪', 'Spawn-proofing'),
    'stat.spawn_ok': ('{n} 处可站表面全部有光', 'all {n} standable surfaces lit'),
    'stat.spawn_dark': ('{n} 处可站表面，{d} 处偏暗', '{n} standable surfaces, {d} dark'),
    'stat.walk': ('动线检查', 'Walk test'),
    'stat.walk_v': ('{a}/{b} 个目标可走到', '{a}/{b} targets reachable'),
    'ui.views': ('视角', 'Views'),
    'ui.light': ('光照与显示', 'Light & display'),
    'ui.time': ('时间', 'Time'),
    'ui.time_aria': ('时间：夜晚到白天', 'Time: night to day'),
    'ui.day': ('白天', 'Day'), 'ui.dusk': ('黄昏', 'Dusk'), 'ui.evening': ('入夜', 'Evening'), 'ui.night': ('夜晚', 'Night'),
    'ui.plot': ('地块范围（蓝线）', 'Plot outline (blue)'),
    'ui.cut': ('剖切', 'Cut'), 'ui.cut_aria': ('剖切高度', 'Cut height'), 'ui.full': ('完整', 'Full'),
    'ui.layer': ('只看这一层（施工用）', 'This layer only (for building)'),
    'ui.data': ('投影数据', 'Schematic data'),
    'ui.materials': ('材料清单', 'Materials'),
    'ui.gallery': ('游戏内实拍', 'In-game shots'),
    'ui.close': ('关闭', 'Close'),
    'ui.canvas': ('三维方块预览，可拖动旋转', '3D block preview, drag to rotate'),
    'ui.shot_alt': ('原截图', 'Original screenshot'),
    'ui.wipe': ('◀ 原截图 ｜ 建成后 ▶', '◀ screenshot | built ▶'),
    'ui.hint': ('左键拖动旋转 · 右键拖动平移 · 滚轮缩放　|　方块模型与贴图取自本机原版客户端，这不是游戏截图',
                'Left-drag to orbit · right-drag to pan · wheel to zoom  |  models and textures come from your own vanilla '
                'client - this is not a game screenshot'),
    'ui.hint_plain': ('左键拖动旋转 · 右键拖动平移 · 滚轮缩放　|　本机没有原版客户端：方块用地图颜色和碰撞形状显示',
                      'Left-drag to orbit · right-drag to pan · wheel to zoom  |  no vanilla client on this machine: '
                      'blocks are shown with map colours and collision shapes'),
    'ui.loading': ('正在载入方块与地形…', 'Loading blocks and terrain…'),
    # ---- materials
    'mat.creative': ('生存不可获得', 'not obtainable in survival'),
    'mat.farmland': ('放泥土后用锄头耕', 'place dirt, then till it with a hoe'),
    'mat.dirt_path': ('在草方块上用锹右键', 'use a shovel on grass'),
    'mat.stripped': ('用斧头右键原木', 'use an axe on the log'),
    'mat.shears': ('需剪刀（或精准采集）', 'needs shears (or Silk Touch)'),
    'mat.silk': ('需精准采集', 'needs Silk Touch'),
    'mat.unstackable': ('{n} 个（不可堆叠）', '{n} (unstackable)'),
    'mat.stacks': ('{q} 组', '{q} stack{s}'),
    'mat.per_stack': ('（每组 {ms}）', ' ({ms} per stack)'),
    'mat.csv': ('物品,ID,数量,组数,备注', 'Item,ID,Count,Stacks,Note'),
    # ---- drawings / maps
    'draw.top': ('俯视（北在上）x {x0}..{x1}  z {z0}..{z1}', 'Top view (north up)  x {x0}..{x1}  z {z0}..{z1}'),
    'draw.north': ('北立面（从北往南看）', 'North elevation (looking south)'),
    'draw.south': ('南立面（从南往北看）', 'South elevation (looking north)'),
    'draw.west': ('西立面（从西往东看）', 'West elevation (looking east)'),
    'draw.east': ('东立面（从东往西看）', 'East elevation (looking west)'),
    'map.site': ('{name} · 地形 {kind}  x {x0}..{x1} z {z0}..{z1}', '{name} · terrain {kind}  x {x0}..{x1} z {z0}..{z1}'),
    'map.plot': ('截图里圈出的范围（蓝）', 'Area outlined in the screenshot (blue)'),
    'map.analysis': ('场地分析：红=已有建筑  绿=平地候选', 'Site analysis: red = existing builds, green = flat candidates'),
    'map.build': ('建筑{id}{under} {n}块 {names}', 'Build {id}{under} {n} blocks {names}'),
    'map.underground': ('(地下)', ' (underground)'),
    'map.spot': ('候选{i} Y{y} 土方{cf}', 'Spot {i} Y{y} earthwork {cf}'),
    'list.sep': ('、', ', '),
    'style.title': ('参考建筑方块统计 · {n} 块 · 框 {box}', 'Reference build · {n} blocks · box {box}'),
    'role.structure': ('主体/墙体', 'Structure / walls'), 'role.stairs': ('楼梯', 'Stairs'), 'role.slabs': ('台阶/半砖', 'Slabs'),
    'role.thin': ('栅栏/墙/玻璃板', 'Fences / walls / panes'), 'role.glass': ('玻璃', 'Glass'),
    'role.doors': ('门/活板门', 'Doors / trapdoors'), 'role.lights': ('光源', 'Lights'), 'role.plants': ('植物/树叶', 'Plants / leaves'),
    'role.deco': ('其他装饰', 'Other decoration'),
    # ---- export / schematic
    'export.desc': ('{name}。放置原点（Litematica 放置位置）X={{x}} Y={{y}} Z={{z}}，不旋转、不镜像。',
                    '{name}. Placement origin (Litematica placement position) X={{x}} Y={{y}} Z={{z}}, no rotation, no mirror.'),
    'export.desc_site': ('区域内未改动的格子按原地形复制。', ' Unchanged cells inside the regions are copied from the original terrain.'),
    'region.etc': ('等', ' etc.'),
    'part.main': ('主体', 'Main'),
    # ---- in-game test
    'ingame.save': ('{name} · 实测', '{name} · test'),
    'file.showcase': ('{id}-展示存档.zip', '{id}-showcase-world.zip'),
    # ---- release
    'file.preview': ('{name}-预览.html', '{name}-preview.html'),
    'file.materials': ('材料清单.csv', 'materials.csv'),
    'file.shots': ('截图', 'screenshots'),
    'file.guide': ('使用说明.md', 'README.md'),
    'file.bundle': ('{id}-交付包.zip', '{id}-delivery.zip'),
    'file.video': ('{name}-制作过程.mp4', '{name}-making-of.mp4'),
    'file.srt': ('{name}-制作过程.srt', '{name}-making-of.srt'),
    'file.cover': ('{name}-封面.jpg', '{name}-cover.jpg'),
    'rel.files': ('文件', 'Files'),
    'rel.place': ('放置', 'Placement'),
    'rel.notes': ('设计说明', 'Design notes'),
    'rel.checks': ('检查结果', 'Checks'),
    'rel.f_litematic': ('Litematica 投影（Java {v}，Version 7）', 'Litematica schematic (Java {v}, version 7)'),
    'rel.f_schem': ('Sponge 原理图（WorldEdit / FAWE / Axiom 用）', 'Sponge schematic (WorldEdit / FAWE / Axiom)'),
    'rel.f_preview': ('离线三维预览，双击用浏览器打开（拖动旋转、剖切、昼夜、材料清单）',
                      'offline 3D preview - open it in a browser (orbit, cut-away, day/night, materials)'),
    'rel.f_materials': ('生存备料清单（Excel 可直接打开）', 'survival materials list (opens in Excel / Sheets)'),
    'rel.f_shots_ingame': ('游戏内实拍（{n} 张）', 'in-game screenshots ({n})'),
    'rel.f_shots_preview': ('预览截图（{n} 张）', 'preview screenshots ({n})'),
    'rel.f_showcase': ('展示存档（解压到 saves 文件夹）', 'showcase world (unzip into your saves folder)'),
    'rel.f_video': ('制作过程视频', 'making-of video'),
    'rel.site1': ('放置原点：**X={x} Y={y} Z={z}**（Litematica「放置设置」里的位置），**不旋转、不镜像**。投影已经和实际地形对齐。',
                  'Placement origin: **X={x} Y={y} Z={z}** (the position in Litematica\'s placement settings), **no rotation, no '
                  'mirror**. The schematic is already aligned with the real terrain.'),
    'rel.site2': ('投影外框 {sx} × {sy} × {sz}，共 {n} 个子区域；框内没改动的格子按原地形复制，所以不会出现大片“多余方块”的提示。',
                  'Bounding box {sx} × {sy} × {sz}, {n} sub-regions; untouched cells inside the boxes are copied from the terrain, '
                  'so Litematica does not flag large areas as "extra blocks".'),
    'rel.portable1': ('这是不绑定地点的投影：用 Litematica 放到你想要的位置即可（外框 {sx} × {sy} × {sz}，正面朝{front}）。',
                      'This schematic is not tied to a place: put it wherever you like with Litematica (bounding box '
                      '{sx} × {sy} × {sz}, front facing {front}).'),
    'rel.portable2': ('需要换朝向时用 Litematica 的旋转 / 镜像，方块朝向会一起转。',
                      'To change the orientation use Litematica\'s rotate / mirror; block facings turn with it.'),
    'rel.paste_all': ('**创造模式粘贴**：先在 Litematica 配置 → Generic → `pasteReplaceBehavior` 选 **All**，再粘贴。这个设计要清除 {n} 格原有方块'
                      '（树木、要挖掉的土石），只有 All 会把投影里的空气也放下去；With non-air 会跳过这些格子（建筑本身能放上，但树叶、'
                      '土块会留在里面），默认 None 还会漏掉所有替换地表的格子。All 会把区域里的格子恢复成读取地形时的样子，'
                      '粘贴前用 Litematica 的“验证投影”看一眼，确认这块地之后没有别人新盖的东西。',
                      '**Creative paste**: first set Litematica Configs → Generic → `pasteReplaceBehavior` to **All**, then paste. '
                      'This design clears {n} existing blocks (trees, earth to dig out); only All places the schematic\'s air '
                      'cells. With non-air skips them (the build lands, but leaves and earth stay inside it), and the default '
                      'None also skips every cell that replaces terrain. All resets the region to the terrain as it was read - '
                      'check with Litematica\'s schematic verifier first that nobody has built there since.'),
    'rel.survival_all': ('**生存手搭**：按材料清单备料；投影显示为“错误方块 / 多余方块”的格子是需要先挖掉或替换的（包括要清掉的树）。',
                         '**Survival**: gather the materials list; cells Litematica shows as "wrong block" / "extra block" must be '
                         'dug out or replaced first (including the trees to clear).'),
    'rel.paste_nonair': ('**创造模式粘贴**：先在 Litematica 配置 → Generic → `pasteReplaceBehavior` 选 **With non-air**（默认 None 只往空气里放，'
                         '会漏掉替换地表、水下或需要清空的格子），再用粘贴（/ 打印机）。',
                         '**Creative paste**: first set Litematica Configs → Generic → `pasteReplaceBehavior` to **With non-air** '
                         '(the default None only places into air and skips cells that replace ground, water or plants), then paste '
                         '(or use a printer).'),
    'rel.survival': ('**生存手搭**：按材料清单备料；投影显示为“错误方块”的格子是需要先挖掉或替换的。',
                     '**Survival**: gather the materials list; cells Litematica shows as "wrong block" must be dug out or '
                     'replaced first.'),
    'rel.chk_file': ('文件：{r} 个子区域、{c} 格逐一解码，{s} 种方块状态全部是 {v} 的合法状态，方块实体 {te} 个。',
                     'File: {r} sub-region{rs}, {c} cells decoded one by one, all {s} block states valid in {v}, {te} block entit{tes}.'),
    'rel.chk_rules': ('规则：楼梯形状、玻璃板/栅栏/墙连接、门床成对、植物土壤、灯具支撑等 {n} 处问题。',
                      'Rules: {n} problems (stair shapes, pane/fence/wall connections, door and bed pairs, plant soil, light supports).'),
    'rel.chk_spawn': ('防刷怪：{n} 处可站表面，{d} 处方块光为 0。', 'Spawn-proofing: {n} standable surfaces, {d} with block light 0.'),
    'rel.chk_walk': ('动线：{a}/{b} 个地点能从入口走到（按游戏碰撞箱模拟，台阶高度 ≤ 0.6）。',
                     'Walk test: {a}/{b} places reachable from the entrance (simulated with the game\'s collision boxes, steps ≤ 0.6).'),
    'rel.chk_warn': ('注意：{check} — {count} {blocks}', 'Note: {check} - {count} {blocks}'),
    'rel.chk_ingame': ('游戏内实测（原版 {v} 客户端 + Litematica 粘贴后逐格比对）：{parts}。',
                       'Real-client test (vanilla {v} client, pasted with Litematica, every cell compared): {parts}.'),
    'rel.mode_none': ('默认 None（只往空气里放）', 'default None (air only)'),
    'rel.mismatch': ('{mode}：{n} 格不一致', '{mode}: {n} cells differ'),
    'rel.join': ('；', '; '),
    'rel.version_target': ('游戏版本：这个投影是给 Java {t} 做的（DataVersion {dv}）{renamed}；只用了 {t} 里已有的方块。',
                           'Game version: this schematic is made for Java {t} (DataVersion {dv}){renamed}; it only uses blocks that exist in {t}.'),
    'rel.renamed': ('，改名方块按旧名写入：{list}', ', renamed blocks written with their old ids: {list}'),
    'rel.version_note': ('游戏版本：方块数据按 Java {v}。更新的版本可以直接加载（Litematica 会自动转换）；更早的版本请确认用到的方块在你的版本里已经存在。',
                         'Game version: block data is Java {v}. Newer game versions load it directly (Litematica converts it); '
                         'for older versions make sure every block used exists in your version.'),
    # ---- video data
    'vid.brand': ('{name} · 制作过程', '{name} · making-of'),
    'vid.tag': ('MINECRAFT JAVA {v} · 制作记录', 'MINECRAFT JAVA {v} · MAKING-OF'),
    'vid.source': ('数据来源', 'Data source'), 'vid.box': ('读取范围', 'Area read'),
    'vid.builds': ('已有建筑', 'Existing builds'), 'vid.builds_v': ('{n} 处', '{n}'),
    'vid.ground': ('地面高度', 'Ground height'),
    'vid.decode': ('逐格解码投影文件', 'Schematic decoded cell by cell'), 'vid.cells': ('{n} 格', '{n} cells'),
    'vid.states': ('方块状态全部合法', 'All block states valid'), 'vid.kinds': ('{n} 种', '{n} kinds'),
    'vid.rules': ('连接 / 楼梯 / 支撑规则', 'Connections / stairs / supports'), 'vid.problems': ('{n} 处问题', '{n} problems'),
    'vid.lit': ('可站表面全部有光', 'Every standable surface lit'), 'vid.places': ('{n} 处', '{n}'),
    'vid.walk': ('动线全部走得到', 'Every place reachable'),
    'vid.paste_check': ('真实客户端粘贴比对', 'Real-client paste check'), 'vid.diff': ('{n} 格不一致', '{n} cells differ'),
    'vid.origin': ('原点 {o}', 'Origin {o}'), 'vid.palette': ('配色', 'Palette'),
    'vid.blocks': ('个方块', 'blocks'), 'vid.place_origin': ('放置原点', 'Placement origin'),
    'vid.no_rotate': ('不旋转', 'no rotation'), 'vid.no_mirror': ('不镜像', 'no mirror'),
    'vid.paste': ('粘贴选 {mode}', 'Paste with {mode}'), 'vid.schematic': ('投影', 'Schematic'),
    'vid.anywhere': ('放到任意位置；可在 Litematica 里旋转 / 镜像', 'place it anywhere; rotate / mirror in Litematica'),
    'vid.credit': ('mcbuild 设计与制作', 'designed and built with mcbuild'),
    'src.voxy': ('Voxy 本地缓存', 'Voxy cache'), 'src.anvil': ('存档', 'World save'), 'src.schematic': ('原理图', 'Schematic'),
    'src.flat': ('平地（无地点）', 'Flat ground (no site)'), 'src.none': ('无地点', 'No site'),
}
