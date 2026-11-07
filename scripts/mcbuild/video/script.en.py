"""Narration for the making-of video - REWRITE the lines for this project (first person, short sentences, every
line matches something visible on screen). Scene ids must exist in scenes.js; drop a scene by deleting its entry.
Each line is a list of fragments (the subtitle switches between fragments, keep each under ~42 characters). A fragment
may be (spoken text, subtitle text): numbers and coordinates spoken as words, shown as digits.
Never put personal data (server address, player names) in spoken text: it is sent to Microsoft's TTS service.
"""
VOICE = 'en-US-AriaNeural'
RATE = '+0%'

SCRIPT = [
    ('opening', '', [
        ['This is __TITLE__.', 'Here is how it was designed.'],
    ]),
    ('request', '01 · The request', [
        ['It started with one sentence and a screenshot.', 'I turned it into a short brief:', 'where, what, how big, which style.'],
    ]),
    ('site', '02 · The real terrain', [
        ['Then I read the real blocks of this area', 'from the game data on your computer.'],
        ['Ground, water and the builds around it', 'are all on this map.'],
    ]),
    ('locate', '03 · Where it goes', [
        ['Next, where exactly to build.'],
        ['Comparing the map and the heights,', 'I picked the best spot.'],
        [('The origin goes right here.', 'The origin goes right here.')],
    ]),
    ('style', '04 · Style', [
        ['For the style,', 'I kept to a small palette.'],
    ]),
    ('design', '05 · Design', [
        ['The whole design is written as code,', 'every block on a real coordinate.'],
        ['From the foundation, layer by layer,', 'up to the roof.'],
    ]),
    ('verify', '06 · Checks', [
        ['After exporting the schematic,', 'I checked every single cell:'],
        ['block states, connections,', 'lighting and walkways are all fine.'],
    ]),
    ('preview', '07 · Preview', [
        ['Finally I pasted it in the real game', 'and looked at it by day and by night.'],
    ]),
    ('ending', '', [
        ['The schematic and the preview page', 'are in the release folder.'],
        ['Enjoy building it!'],
    ]),
]
