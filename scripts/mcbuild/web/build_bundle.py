"""Rebuild viewer.bundle.js after editing main.js (maintainers only; needs esbuild + three in a node_modules folder).
usage: python build_bundle.py [node_modules_dir]   (or set MCBUILD_NODE_MODULES; default: web/node_modules after
`npm i three esbuild` in this folder)"""
import os, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
BANNER = ('/*! mcbuild preview viewer (MIT) | includes three.js r185, Copyright 2010-2025 three.js authors, MIT License, '
          'https://github.com/mrdoob/three.js/blob/dev/LICENSE */\n')
cands = [sys.argv[1]] if len(sys.argv) > 1 else []
cands += [os.environ.get('MCBUILD_NODE_MODULES', ''), str(HERE / 'node_modules')]
for nm in cands:
    nm = Path(nm) if nm else None
    if nm and (nm / 'three').is_dir():
        exe = next((p for p in [nm / '.bin' / ('esbuild.cmd' if os.name == 'nt' else 'esbuild'), nm / '@esbuild/win32-x64/esbuild.exe',
                                nm / '.bin/esbuild'] if p.exists()), None)
        if exe:
            subprocess.run([str(exe), str(HERE / 'main.js'), '--bundle', '--format=iife', '--minify', '--target=es2020',
                            '--legal-comments=none', f'--outfile={HERE / "viewer.bundle.js"}'], check=True, env=dict(os.environ, NODE_PATH=str(nm)))
            out = HERE / 'viewer.bundle.js'
            out.write_text(BANNER + out.read_text(encoding='utf-8'), encoding='utf-8')
            print('bundled with', nm); sys.exit(0)
sys.exit('needs a node_modules folder with three and esbuild: run `npm i three esbuild` in web/')
