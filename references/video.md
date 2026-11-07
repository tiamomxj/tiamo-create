# Making-of video (optional deliverable)

3–6 minutes, 1080p30, narration in the project language with burned-in subtitles, built from this project's REAL
data and images (site map, analysis, camera overlay, style stats, the 3D scene rising layer by layer, verification
numbers, in-game screenshots). Only on request; it costs ~10–20 minutes of rendering. Needs (see `mcb doctor`):
Playwright (Python or Node), ffmpeg, scipy and edge-tts ≥ 7.3.1 - ask before installing any of them.

## Pipeline (`mcb video …`, files in `<project>/video/`)

1. `mcb video init` - copies `stage.html`, `stage-lib.js`, `render.cjs`, `viewer.bundle.js`, and (first time)
   `scenes.js` + `script.py` (Chinese or English template by project language); writes `data.js`
   (= `window.VIDEO_DATA`: title, origin, images that exist, palette, verification rows, in-game shots, build bbox,
   on-screen labels). Re-run after new artifacts (it never overwrites your scenes/script; `--reset` restores scenes.js).
2. Write `script.py` - `SCRIPT = [(scene_id, chapter_title, [line, …]), …]`, a line = list of fragments (the subtitle
   switches per fragment; ≤ ~22 Chinese characters or ~42 Latin characters), a fragment = text or `(spoken, shown)`
   (numbers read as words, shown as digits). First person, short sentences, every line has something on screen.
   **No personal data in spoken text** (it is sent to Microsoft's TTS service). Generic scene ids: opening, request,
   site, locate, style, design, verify, preview, ending - delete chapters that don't apply, add your own ids for
   project-specific moments. `VOICE` / `RATE` choose the edge-tts voice (defaults: zh-CN-XiaoxiaoNeural,
   en-US-AriaNeural).
3. `mcb video narrate` - edge-tts per line with word boundaries → subtitle times; `timeline.json/js` (line gap
   0.42 s, chapter gap 0.95 s). Cached per line text.
4. Edit `scenes.js` - scenes are `STAGE.scene(id, build(root, s), draw(t, s, opacity))`, pure functions of time.
   Helpers (`window.STAGE`): `SL(id, k)` start of the k-th line of a scene, `L/LE/F` by global line index, `ramp`,
   `win`, `kf(t, [[t0, v0], …])`, `pop`, `show`, `el`, `img`, `chip`, `dark`, `use3D({pos,target,fov,day,cut,buildCut,
   context,waterOpacity,eye/yaw/pitch,hook}, opacity)`, `orbit(center, r, h, angle)`, `label3D` + `anchorLabel` for
   labels pinned to 3D points, `toScreen`. Good shots: screenshot + camera convergence; outline flying from the
   screenshot onto the map; style bars; layer-by-layer build-up (`buildCut`); water made translucent to show piles;
   cut-away with labels; first-draft vs final comparison; k-d region boxes (`hook` adds wireframes); verification
   checklist; paste results; before/after wipe in the screenshot view; day→night. Labels come from `D.ui`.
5. `mcb video check` (runs every 0.2 s, reports script errors) and `mcb video stills 3 12.5 40 …` → `video/stills/`;
   look at a still in every chapter. Typical bugs: an opaque full-screen div hiding the 3D canvas, legends under the
   subtitles, labels off-screen, numbers wrapping, a 3D camera inside terrain, a comparison slider that doesn't match
   the narration ("left … right …" while the slider is not in the middle).
6. `mcb video render [--workers 4]` - mixes audio (voice + synthesized pad/plucks, ducking under the voice, reverb,
   fades, loudnorm −16 LUFS / −1.5 dBTP) → `mix.wav` + the `.srt`; renders frame segments in parallel (headless
   Chromium → JPEG → ffmpeg x264 crf 17), concatenates, muxes AAC 192k, faststart → the `.mp4` and a cover image in
   `release/`.
7. Check: duration, a contact sheet of ~16 frames, `ffmpeg -i final.mp4 -af ebur128 -f null -` (≈ −16 LUFS, peaks
   ≤ −1.5 dBFS). You cannot hear it - say so and ask the user to watch it once.
