"""Launcher: python <skill>/scripts/mcb.py <command> [-p project] ...  (same as python -m mcbuild with PYTHONPATH set).
Run `python <skill>/scripts/mcb.py doctor` first on a new machine: it works even before numpy/Pillow are installed."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
try:
    sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
if sys.version_info < (3, 10):
    sys.exit(f'mcbuild needs Python 3.10 or newer (this is {sys.version.split()[0]}).')
from mcbuild.cli import main

try:
    main()
except ModuleNotFoundError as e:
    if e.name in ('numpy', 'PIL', 'tomli', 'zstandard', 'scipy', 'playwright', 'edge_tts'):
        here = os.path.dirname(os.path.abspath(__file__))
        req = 'requirements.txt' if e.name in ('numpy', 'PIL', 'tomli') else 'requirements-optional.txt'
        sys.exit(f'missing Python package {e.name!r}. Install it (ask the user first):\n'
                 f'  "{sys.executable}" -m pip install -r "{os.path.join(here, req)}"\n'
                 f'`mcb doctor` lists everything this machine needs.')
    raise
