"""mcbuild - Minecraft build design-to-delivery kit (site data -> design in code -> verified Litematica schematic,
offline 3D preview, real-client paste test, release package). See the skill's SKILL.md and references/.

Names are imported lazily, so `mcb doctor` can run (and say what to install) before numpy/Pillow exist.
"""
import importlib

_EXPORTS = {
    'parse': 'registry', 'make': 'registry', 'State': 'registry', 'AIR': 'registry', 'facts': 'registry', 'in_tag': 'registry',
    'tag_members': 'registry', 'zh_name': 'registry', 'display_name': 'registry', 'properties': 'registry', 'known': 'registry',
    'OFFSET': 'registry', 'OPPOSITE': 'registry', 'CW': 'registry', 'CCW': 'registry', 'HORIZONTAL': 'registry',
    'Build': 'build', 'Frame': 'build', 'get_project': 'project',
}
_MODULES = ('shapes', 'nature')
__all__ = list(_EXPORTS) + list(_MODULES)


def __getattr__(name):
    if name in _MODULES:
        return importlib.import_module(f'.{name}', __name__)
    mod = _EXPORTS.get(name)
    if mod is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    m = importlib.import_module(f'.{mod}', __name__)
    return getattr(m, 'current' if name == 'get_project' else name)
