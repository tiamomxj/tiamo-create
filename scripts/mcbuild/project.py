"""A build project: folder with project.toml + design script; artifacts/ (generated), release/ (deliverables),
input/ (user's images & files), .cache/.

The design script is plain Python that builds a `Build` named B (or defines build(project) -> Build). The kit runs
it, applies the vanilla rules pass, and caches the cells in artifacts/design.npz; later commands reuse the cache
while design.py / project.toml / site data are unchanged.
"""
from __future__ import annotations
import json, os, runpy, sys, time
try:
    import tomllib
except ModuleNotFoundError:                     # Python 3.10
    import tomli as tomllib
from pathlib import Path
import numpy as np
from .registry import AIR, parse, set_version
from .util import log, write_json, read_json, default_version
from . import i18n

_CURRENT = {}


def current() -> 'Project':
    p = _CURRENT.get('p')
    if p is None:
        root = Path(os.environ.get('MCBUILD_PROJECT', '.')).resolve()
        p = Project(root)
    return p


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        f = self.root / 'project.toml'
        if not f.exists():
            raise SystemExit(f'no project.toml in {self.root} - create a project with `mcb init <folder>`.')
        self.cfg = tomllib.loads(f.read_text(encoding='utf-8'))
        pj = self.cfg.setdefault('project', {})
        self.name = pj.get('name', self.root.name)
        self.id = pj.get('id') or ''.join(c for c in self.root.name if c.isalnum()) or 'Build'
        self.version = pj.get('version') or default_version()
        set_version(self.version)
        i18n.set_lang(pj.get('lang'))
        self.lang = i18n.lang()
        self.art = self.root / 'artifacts'; self.art.mkdir(exist_ok=True)
        self.release_dir = self.root / self.cfg.get('release', {}).get('folder', 'release')
        self.input = self.root / 'input'
        self.cache = self.root / '.cache'
        self._site = None
        self._design = None
        _CURRENT['p'] = self

    # ------------------------------------------------------------ paths
    def path(self, rel):
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    @property
    def litematic_name(self):
        ec = self.cfg.get('export', {})
        return ec.get('file') or f"{self.id}-{ec.get('target_version') or self.version}.litematic"

    # ------------------------------------------------------------ site
    def site(self):
        if self._site is None:
            from .terrain import Site, make_flat
            sc = self.cfg.get('site', {})
            if (self.art / 'site.npz').exists():
                self._site = Site.load(self.art)
            elif sc.get('source', 'flat') in ('flat', 'none'):
                self._site = self.extract_site()
            else:
                raise SystemExit('no terrain data yet - run `mcb site` first.')
        return self._site

    def extract_site(self):
        from .terrain import extract_voxy, extract_anvil, extract_schematic, make_flat, find_voxy_store, Site
        sc = self.cfg.get('site', {})
        src = sc.get('source', 'flat')
        box = sc.get('box')
        if src == 'voxy':
            jar = self.path(sc['voxy_jar']) if sc.get('voxy_jar') else None
            store = find_voxy_store(sc.get('server'), sc.get('dimension', 'overworld'), sc.get('store'), self.cache, jar)
            site = extract_voxy(store, _box6(box), self.cache, jar)
        elif src == 'anvil':
            site = extract_anvil(self.path(sc['world']), _box6(box), sc.get('dimension', 'overworld'))
        elif src == 'schematic':
            site = extract_schematic(self.path(sc['schematic']), tuple(sc.get('origin', (0, 0, 0))), sc.get('margin', 0))
        else:
            gy = sc.get('ground_y', 64)
            b = _box6(box) if box else (-64, gy - 16, -64, 64, gy + 48, 64)
            site = make_flat(b, gy, sc.get('top', 'grass_block[snowy=false]'), tuple(tuple(x) for x in sc.get('layers', [['dirt', 3]])),
                             sc.get('base', 'stone'), sc.get('water_y'), sc.get('biome', 'minecraft:plains'))
            if src == 'none':
                site.source['kind'] = 'none'
        site.save(self.art)
        self._site = site
        return site

    # ------------------------------------------------------------ design
    def design_inputs(self):
        files = [self.root / 'project.toml'] + sorted(self.root.glob('*.py'))
        files += [self.art / 'site.npz'] if (self.art / 'site.npz').exists() else []
        return max(f.stat().st_mtime for f in files if f.exists())

    def design(self, rerun=False):
        if self._design is not None and not rerun:
            return self._design
        cache = self.art / 'design.npz'
        if not rerun and cache.exists() and cache.stat().st_mtime >= self.design_inputs():
            self._design = self._load_design(cache)
            return self._design
        self._design = self.run_design()
        return self._design

    def run_design(self):
        from .build import Build
        script = self.path(self.cfg.get('design', {}).get('script', 'design.py'))
        if not script.exists():
            raise SystemExit(f'design script not found: {script}')
        sys.path.insert(0, str(self.root))
        old = os.getcwd()
        os.chdir(self.root)
        t0 = time.time()
        try:
            g = runpy.run_path(str(script), run_name='__design__')
        finally:
            os.chdir(old)
            if sys.path and sys.path[0] == str(self.root):
                sys.path.pop(0)
        B = g.get('B')
        if not isinstance(B, Build):
            if callable(g.get('build')):
                B = g['build'](self)
            else:
                B = next((v for v in g.values() if isinstance(v, Build)), None)
        if B is None:
            raise SystemExit('the design script made no Build (convention: a module-level variable B, or a function build(project) returning a Build)')
        n = B.resolve()
        self._save_design(B)
        s = B.summary()
        s['rulesChanged'] = n
        s['seconds'] = round(time.time() - t0, 2)
        s['notes'] = B.notes
        write_json(self.art / 'design-summary.json', s)
        log('DESIGN', f"blocks={s['blocks']} clearances={s['clearances']} size={s['size']} parts={len(s['parts'])} rules-fixed={n} ({s['seconds']}s)")
        return B

    def _save_design(self, B):
        keys, kidx = [], {}
        parts, pidx = [], {}
        pos = np.zeros((len(B.cells), 3), np.int32)
        sid = np.zeros(len(B.cells), np.int32)
        pid = np.zeros(len(B.cells), np.int32)
        for n, (p, st) in enumerate(B.cells.items()):
            pos[n] = p
            k = st.key()
            if k not in kidx:
                kidx[k] = len(keys); keys.append(k)
            sid[n] = kidx[k]
            pt = B.part.get(p, 'main')
            if pt not in pidx:
                pidx[pt] = len(parts); parts.append(pt)
            pid[n] = pidx[pt]
        np.savez_compressed(self.art / 'design.npz', pos=pos, sid=sid, pid=pid,
                            keys=np.array(json.dumps(keys)), parts=np.array(json.dumps(parts, ensure_ascii=False)),
                            notes=np.array(json.dumps(B.notes, ensure_ascii=False)))

    def _load_design(self, path):
        from .build import Build
        d = np.load(path)
        keys = [parse(k) for k in json.loads(str(d['keys']))]
        parts = json.loads(str(d['parts']))
        B = Build(self.site(), self.name)
        for p, s, q in zip(d['pos'].tolist(), d['sid'].tolist(), d['pid'].tolist()):
            t = tuple(p)
            B.cells[t] = keys[s]
            B.part[t] = parts[q]
        B.notes = json.loads(str(d['notes'])) if 'notes' in d else []
        return B


def _box6(box):
    """[x0, y0, z0, x1, y1, z1] (exclusive ends) from config."""
    if box is None:
        raise SystemExit('[site] in project.toml needs box = [x0, y0, z0, x1, y1, z1] (the area to read, end exclusive)')
    if len(box) != 6:
        raise SystemExit('box must be 6 numbers [x0, y0, z0, x1, y1, z1]')
    return tuple(int(v) for v in box)
