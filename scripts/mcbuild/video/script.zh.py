"""Narration for the making-of video — REWRITE the lines for this project (first person, short sentences, every
line matches something visible on screen). Scene ids must exist in scenes.js; drop a scene by deleting its entry.
Each line is a list of fragments (subtitle switches between fragments, <= ~22 characters each). A fragment may be
(spoken text, subtitle text): numbers/coordinates read as Chinese words, shown as digits.
Never put personal data (server address, player names) in spoken text: it is sent to Microsoft's TTS service.
"""
VOICE = 'zh-CN-XiaoxiaoNeural'
RATE = '+6%'

SCRIPT = [
    ('opening', '', [
        ['这是__TITLE__。', '这个视频讲讲它是怎么设计出来的。'],
    ]),
    ('request', '01 · 需求', [
        ['起点是你的一句话和一张截图。', '我先把需求写成一份清单：', '在哪里、做什么、多大、什么风格。'],
    ]),
    ('site', '02 · 真实的地形', [
        ['接着从你电脑上的缓存里，', '读出这一带每一格的真实方块。'],
        ['地形、水面和周围的建筑，', '都在这张俯视图上。'],
    ]),
    ('locate', '03 · 定位', [
        ['然后确定建在哪里。'],
        ['我对照地图和高度，', '选了一块合适的位置。'],
        [('原点就定在这里。', '原点就定在这里。')],
    ]),
    ('style', '04 · 风格', [
        ['风格方面，', '我选了一套简单的配色。'],
    ]),
    ('design', '05 · 设计', [
        ['设计全部写在代码里，', '每个方块都放在真实坐标上。'],
        ['从地基一层层往上，', '直到屋顶。'],
    ]),
    ('verify', '06 · 验证', [
        ['导出投影以后，', '我逐格检查了一遍：'],
        ['方块状态、连接规则、', '灯光和动线都没有问题。'],
    ]),
    ('preview', '07 · 预览', [
        ['最后在真实的游戏里粘贴、截图，', '白天和夜晚都看过。'],
    ]),
    ('ending', '', [
        ['投影和预览网页都在交付文件夹里。'],
        ['希望你喜欢。'],
    ]),
]
