"""Screenshot camera: recover where a screenshot was taken from, then map image pixels to world blocks.

Minecraft camera: yaw 0 = looking south (+z), 90 = west; pitch + = looking down; fov = vertical degrees
(options default 70; the screenshot's effective fov also depends on dynamic FOV / zoom mods, so fit it).
eye = feet + 1.62. If the screenshot shows the F3 screen, read XYZ / Facing (yaw, pitch) directly instead -
`from_f3()` accepts the F3 lines or the text F3+C copies (`/execute in minecraft:overworld run tp @s x y z yaw pitch`).

    cam = Camera(yaw, pitch, fov, eye, W, H)
    uv, depth = cam.project(points)            # world -> pixels
    hit = raycast(site, cam, u, v)              # pixel -> first solid block
    fit(pairs, W, H, init)                      # least squares from (pixel, world point) correspondences
    columns_in_polygon(site, cam, poly)         # outline drawn on the screenshot -> ground columns
"""
from __future__ import annotations
import json, math, re
from dataclasses import dataclass, asdict
import numpy as np


@dataclass
class Camera:
    yaw: float
    pitch: float
    fov: float
    eye: tuple
    W: int = 1920
    H: int = 1080

    def basis(self):
        y, p = math.radians(self.yaw), math.radians(self.pitch)
        f = np.array([-math.sin(y) * math.cos(p), -math.sin(p), math.cos(y) * math.cos(p)])
        r = np.array([-math.cos(y), 0.0, -math.sin(y)])
        u = np.cross(r, f)
        return f, r, u

    @property
    def focal(self):
        return (self.H / 2) / math.tan(math.radians(self.fov) / 2)

    def project(self, P):
        P = np.atleast_2d(np.asarray(P, float))
        f, r, u = self.basis()
        dv = P - np.asarray(self.eye, float)
        z = dv @ f
        zs = np.where(np.abs(z) < 1e-6, 1e-6, z)
        return np.stack([self.W / 2 + self.focal * (dv @ r) / zs, self.H / 2 - self.focal * (dv @ u) / zs], 1), z

    def ray(self, px, py):
        f, r, u = self.basis()
        d = f * self.focal + r * (px - self.W / 2) - u * (py - self.H / 2)
        return np.asarray(self.eye, float), d / np.linalg.norm(d)

    def to_json(self):
        d = asdict(self); d['eye'] = [float(v) for v in self.eye]
        return d

    @classmethod
    def from_json(cls, d):
        return cls(d['yaw'], d['pitch'], d['fov'], tuple(d['eye']), d.get('W', 1920), d.get('H', 1080))

    def target(self, dist=40.0):
        f, _, _ = self.basis()
        return [float(v) for v in np.asarray(self.eye) + f * dist]


def fit(pairs, W, H, init, fit_eye=True, eye_sigma=1.0, bounds=None):
    """pairs = [((u, v), (x, y, z)), ...]; init = (yaw, pitch, fov, ex, ey, ez).
    The eye is softly tied to init (eye_sigma blocks) — set it from the player's known position when possible."""
    uv = np.array([p[0] for p in pairs], float)
    P = np.array([p[1] for p in pairs], float)
    e0 = np.array(init[3:6], float)

    def cam_of(q):
        return Camera(q[0], q[1], q[2], tuple(e0 + (q[3:6] if fit_eye else 0)), W, H)

    def res(q):
        c = cam_of(q)
        pr, _ = c.project(P)
        r = (pr - uv).ravel()
        if fit_eye:
            r = np.concatenate([r, q[3:6] / eye_sigma * 10])
        return r

    q0 = np.array([init[0], init[1], init[2], 0, 0, 0], float)
    try:
        from scipy.optimize import least_squares
        lo = [init[0] - 30, -90, 20, -8, -8, -8] if bounds is None else bounds[0]
        hi = [init[0] + 30, 90, 140, 8, 8, 8] if bounds is None else bounds[1]
        q = least_squares(res, q0, bounds=(lo, hi)).x
    except ImportError:                                       # plain Gauss-Newton fallback
        q = q0.copy()
        for _ in range(60):
            r0 = res(q); J = np.zeros((len(r0), 6))
            for k in range(6):
                d = np.zeros(6); d[k] = 1e-4
                J[:, k] = (res(q + d) - r0) / 1e-4
            step = np.linalg.lstsq(J, -r0, rcond=None)[0]
            q += step
            if np.abs(step).max() < 1e-6:
                break
    c = cam_of(q)
    pr, _ = c.project(P)
    err = np.linalg.norm(pr - uv, axis=1)
    return c, {'rmsPx': float(np.sqrt((err ** 2).mean())), 'maxPx': float(err.max()), 'perPair': err.round(1).tolist()}


def site_points(site, names, offset=(0.5, 0.3, 0.5), box=None):
    """World points of every block whose short name is in `names` (e.g. lanterns, torches) — fit candidates."""
    want = [int(k) for k, v in site._pal.items() if v['Name'].split(':', 1)[1] in names]
    y, z, x = np.nonzero(np.isin(site.IDS, want))
    P = np.stack([x + site.X0 + offset[0], y + site.Y0 + offset[1], z + site.Z0 + offset[2]], 1)
    if box is not None:
        x0, z0, x1, z1 = box
        P = P[(P[:, 0] >= x0) & (P[:, 0] < x1) & (P[:, 2] >= z0) & (P[:, 2] < z1)]
    return P


def match(cam, spots, candidates):
    """Pair each pixel spot with the nearest projected candidate point (in front of the camera)."""
    pr, z = cam.project(candidates)
    out = []
    for s in spots:
        d = np.linalg.norm(pr - np.asarray(s, float), axis=1)
        d[z <= 0.3] = 1e9
        i = int(np.argmin(d))
        out.append(((float(s[0]), float(s[1])), tuple(float(v) for v in candidates[i]), float(d[i])))
    return out


def solid_mask(site):
    from .terrain import kind
    return site.lut(lambda st: 1 if kind(st) in ('solid', 'light') else 0).astype(bool)


def raycast(site, cam, px, py, max_dist=400, mask=None):
    """First solid block hit by the ray through pixel (px, py): ((x, y, z), face normal) or None. Voxel DDA."""
    mask = solid_mask(site) if mask is None else mask
    o, d = cam.ray(px, py)
    cell = np.floor(o).astype(int)
    step = np.sign(d).astype(int)
    tmax = np.where(d != 0, ((cell + (step > 0)) - o) / np.where(d == 0, 1, d), np.inf)
    tdelta = np.where(d != 0, np.abs(1 / np.where(d == 0, 1, d)), np.inf)
    normal = None
    t = 0.0
    while t < max_dist:
        x, y, z = cell
        if site.contains(x, y, z) and mask[y - site.Y0, z - site.Z0, x - site.X0]:
            return (int(x), int(y), int(z)), normal
        k = int(np.argmin(tmax))
        t = tmax[k]
        cell[k] += step[k]
        tmax[k] += tdelta[k]
        normal = [0, 0, 0]; normal[k] = -int(step[k])
    return None


def columns_in_polygon(site, cam, poly, box=None, occlusion=True):
    """Ground columns whose surface centre projects inside the screen polygon (and is visible, if occlusion)."""
    from .terrain import kind
    hgt = site.heightmap(lambda st: kind(st) == 'solid')
    zz, xx = np.indices(hgt.shape)
    P = np.stack([xx + site.X0 + 0.5, hgt + 1.0, zz + site.Z0 + 0.5], -1).reshape(-1, 3)
    sp, z = cam.project(P)
    inside = points_in_polygon(sp, poly) & (z > 0)
    idx = np.nonzero(inside)[0]
    mask = solid_mask(site) if occlusion else None
    cols = []
    for i in idx:
        zi, xi = divmod(int(i), hgt.shape[1])
        x, zw, h = int(xi + site.X0), int(zi + site.Z0), int(hgt[zi, xi])
        if box is not None and not (box[0] <= x < box[2] and box[1] <= zw < box[3]):
            continue
        if occlusion:
            hit = raycast(site, cam, *sp[i], mask=mask)
            if hit is None or abs(hit[0][0] - x) + abs(hit[0][2] - zw) > 1:
                continue
        cols.append((x, zw, h, site.world(x, h, zw).short))
    return cols


def stroke_polygon(img, rgb, tol=60, bins=180, exclude=None):
    """A closed outline drawn on the screenshot in colour `rgb` -> polygon (screen px), by angular medians around
    the stroke's centroid. exclude = optional boolean mask of pixels to ignore (HUD, chat)."""
    a = np.asarray(img.convert('RGB')).astype(int)
    d = np.abs(a - np.array(rgb)).sum(-1)
    m = d < tol
    if exclude is not None:
        m &= ~exclude
    ys, xs = np.nonzero(m)
    if len(xs) < 20:
        return None
    cx, cy = xs.mean(), ys.mean()
    ang = np.arctan2(ys - cy, xs - cx); rad = np.hypot(xs - cx, ys - cy)
    poly = []
    for k in range(bins):
        lo, hi = -math.pi + k * 2 * math.pi / bins, -math.pi + (k + 1) * 2 * math.pi / bins
        sel = (ang >= lo) & (ang < hi)
        if sel.sum() > 3:
            rr = float(np.median(rad[sel])); am = (lo + hi) / 2
            poly.append((cx + rr * math.cos(am), cy + rr * math.sin(am)))
    return poly


def render_site(site, cam, scale=0.5, colors=None):
    """Quick point-splat render of the terrain from the camera (for overlay checks against the screenshot)."""
    from PIL import Image
    from .maps import state_colors
    from .terrain import kind
    solid = site.lut(lambda st: 1 if kind(st) != 'air' else 0).astype(bool)
    used, states = site.palette_states()
    col = colors or state_colors(states)
    lut = np.zeros((max(used) + 2 if used else 2, 3), np.float32)
    for i, st in zip(used, states):
        lut[i] = col[st]
    ids = np.where(site.IDS == 0xFFFFFFFF, len(lut) - 1, site.IDS).astype(np.int64)
    pts, cols = [], []
    for dx, dy, dz, shade in [(0, 1, 0, 1.0), (1, 0, 0, .8), (-1, 0, 0, .8), (0, 0, 1, .65), (0, 0, -1, .65), (0, -1, 0, .5)]:
        nb = np.zeros_like(solid)
        src, dst = [slice(None)] * 3, [slice(None)] * 3
        for ax, dd in zip((2, 0, 1), (dx, dy, dz)):
            if dd == 1:
                dst[ax] = slice(0, -1); src[ax] = slice(1, None)
            elif dd == -1:
                dst[ax] = slice(1, None); src[ax] = slice(0, -1)
        nb[tuple(dst)] = solid[tuple(src)]
        y, z, x = np.nonzero(solid & ~nb)
        pts.append(np.stack([x + site.X0 + .5 + dx * .5, y + site.Y0 + .5 + dy * .5, z + site.Z0 + .5 + dz * .5], 1))
        cols.append(lut[ids[y, z, x]] * shade)
    P, C = np.concatenate(pts), np.concatenate(cols)
    w, h = int(cam.W * scale), int(cam.H * scale)
    sp, zc = cam.project(P)
    sp *= scale
    F = cam.focal * scale
    m = zc > 0.3
    sx, sy, zc, c = sp[m, 0], sp[m, 1], zc[m], C[m]
    size = np.clip(np.ceil(F / zc * 1.05), 1, 40).astype(int)
    ok = (sx > -40) & (sx < w + 40) & (sy > -40) & (sy < h + 40)
    sx, sy, zc, c, size = sx[ok], sy[ok], zc[ok], c[ok], size[ok]
    order = np.argsort(-zc)
    sx, sy, c, size = sx[order], sy[order], c[order], size[order]
    img = np.full((h, w, 3), (150, 190, 230), np.float32)
    for s in np.unique(size):
        mm = size == s
        bx = (sx[mm] - s / 2).astype(int); by = (sy[mm] - s / 2).astype(int); cc = c[mm]
        for ox in range(s):
            for oy in range(s):
                xx, yy = bx + ox, by + oy
                k = (xx >= 0) & (xx < w) & (yy >= 0) & (yy < h)
                img[yy[k], xx[k]] = cc[k]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def save(cam, path, extra=None):
    d = cam.to_json()
    d.update(extra or {})
    from .util import write_json
    write_json(path, d)


def load(path):
    return Camera.from_json(json.loads(open(path, encoding='utf-8').read()))


def points_in_polygon(pts, poly):
    """Even-odd rule, vectorised: which of pts [(u, v)] lie inside the polygon [(u, v), ...]."""
    pts = np.asarray(pts, float)
    poly = np.asarray(poly, float)
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    xj, yj = poly[-1]
    for xi, yi in poly:
        cross = (yi > y) != (yj > y)
        with np.errstate(divide='ignore', invalid='ignore'):
            xc = (xj - xi) * (y - yi) / (yj - yi) + xi
        inside ^= cross & (x < xc)
        xj, yj = xi, yi
    return inside


def _wrap(a):
    a = math.fmod(float(a), 360.0)
    return a - 360 if a > 180 else a + 360 if a <= -180 else a


def parse_f3(text):
    """Position / view from what the player can copy out of the game:
    * F3+C clipboard: `/execute in minecraft:overworld run tp @s -281.50 64.00 -209.50 113.25 36.00`
    * F3 screen lines: `XYZ: -281.500 / 64.00000 / -209.500`, `Facing: ... (113.2 / 36.0)`, `Targeted Block: -280, 63, -205`
    -> {'feet': (x, y, z), 'yaw', 'pitch', 'dimension', 'target': (x, y, z) or None}; missing parts are None."""
    t = text.replace('\\n', '\n')                     # literal "\n" typed on a command line
    out = {'feet': None, 'yaw': None, 'pitch': None, 'dimension': None, 'target': None}
    num = r'(-?\d+(?:\.\d+)?)'
    m = re.search(r'execute\s+in\s+([\w:./-]+)\s+run\s+tp\s+@s\s+' + r'\s+'.join([num] * 5), t)
    if m:
        out['dimension'] = m.group(1)
        out['feet'] = tuple(float(m.group(k)) for k in (2, 3, 4))
        out['yaw'], out['pitch'] = _wrap(m.group(5)), float(m.group(6))
    m = re.search(r'XYZ:\s*' + num + r'\s*/\s*' + num + r'\s*/\s*' + num, t)
    if m and out['feet'] is None:
        out['feet'] = tuple(float(v) for v in m.groups())
    m = re.search(r'Facing:[^(\n]*(?:\([^)\n]*\)[^(\n]*)?\(\s*' + num + r'\s*/\s*' + num + r'\s*\)', t)
    if m and out['yaw'] is None:
        out['yaw'], out['pitch'] = _wrap(m.group(1)), float(m.group(2))
    m = re.search(r'Targeted Block:\s*' + num + r'\s*,\s*' + num + r'\s*,\s*' + num, t)
    if m:
        out['target'] = tuple(int(float(v)) for v in m.groups())
    if out['dimension'] is None:
        m = re.search(r'(minecraft:(?:overworld|the_nether|the_end))', t)
        out['dimension'] = m.group(1) if m else None
    return out


def from_f3(text, W=1920, H=1080, fov=70.0):
    """Camera of a screenshot taken where the F3 data says (eye = feet + 1.62; fov from the player's options)."""
    f = parse_f3(text)
    if f['feet'] is None or f['yaw'] is None:
        raise SystemExit('could not read a position and a facing from that text: paste the F3+C text '
                         '(/execute in ... run tp @s x y z yaw pitch) or the XYZ and Facing lines of the F3 screen')
    x, y, z = f['feet']
    return Camera(f['yaw'], f['pitch'], float(fov), (x, y + 1.62, z), W, H), f
