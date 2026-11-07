"""`mcb init`: new project folder from the templates. The player's images and files are copied into input/ right away
(chat attachments often live in temporary folders that are cleaned up later)."""
from __future__ import annotations
import re, shutil
from pathlib import Path
from .util import KIT, log, default_version
from . import config, i18n

TPL = KIT / 'templates'


def init_project(dest: Path | None, name=None, pid=None, source='flat', images=(), template='basic', version=None, lang=None):
    version = version or default_version()
    lang = i18n.normalize(lang) or i18n.default_lang()
    if dest is None:
        base = config.get('projects_dir')
        if not base:
            raise SystemExit('give a project folder (`mcb init <folder>`), or remember a default once: '
                             '`mcb config set projects_dir <folder>`')
        stem = pid or re.sub(r'[^A-Za-z0-9]+', '', name or '') or 'Build'
        dest = Path(base).expanduser() / stem
        k = 2
        while dest.exists() and any(dest.iterdir()):
            dest = Path(base).expanduser() / f'{stem}{k}'; k += 1
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f'folder exists and is not empty: {dest}')
    dest.mkdir(parents=True, exist_ok=True)
    name = name or dest.name
    pid = pid or (re.sub(r'[^A-Za-z0-9]+', '', dest.name) or 'Build')
    i18n.set_lang(lang)
    toml = (TPL / 'project.toml').read_text(encoding='utf-8')
    for k, v in {'__NAME__': name, '__ID__': pid, '__SOURCE__': source, '__VERSION__': version, '__LANG__': lang,
                 '__AUTHOR__': config.get('author') or 'mcbuild', '__MAIN__': i18n.t('part.main')}.items():
        toml = toml.replace(k, v.replace('\\', '\\\\').replace('"', '\\"'))
    (dest / 'project.toml').write_text(toml, encoding='utf-8')
    design = (TPL / 'design.py' if template == 'basic' else TPL / f'design-{template}.py').read_text(encoding='utf-8')
    (dest / 'design.py').write_text(design.replace('__NAME__', name), encoding='utf-8')
    for d in ('input', 'artifacts', 'release', '.cache'):
        (dest / d).mkdir(exist_ok=True)
    for i, img in enumerate(images, 1):
        p = Path(img)
        if p.exists():
            q = dest / 'input' / (f'image{i}' + p.suffix.lower())
            shutil.copy2(p, q)
            log('copied input ->', q)
        else:
            log('file not found (chat attachments may have been cleaned up already):', img)
    log('new project', dest, f'(source={source}, version={version}, lang={lang})')
    log('next: set [site] in project.toml (data source + area) -> mcb site -> analyse / locate -> write design.py -> mcb design')
    return dest
