"""Minimal typed NBT (Java Edition, big-endian) reader/writer — round-trips tag types.

Python values map to tags: dict -> Compound, str -> String, bool/int -> Int (wrap: Byte/Short/Long), float -> Double
(wrap: Float), list -> List (element tag inferred or List(tag, items)), numpy int64 -> LongArray, int32 -> IntArray,
int8/bytes -> ByteArray. read()/load() return the wrapper types so a modified file keeps its exact tag types.
"""
from __future__ import annotations
import gzip, io, struct, zlib
import numpy as np


class Byte(int): tag = 1
class Short(int): tag = 2
class Int(int): tag = 3
class Long(int): tag = 4
class Float(float): tag = 5
class Double(float): tag = 6
class String(str): tag = 8


class Compound(dict):
    tag = 10


class List(list):
    tag = 9

    def __init__(self, items=(), elem=None):
        super().__init__(items)
        self.elem = elem


class _Arr(np.ndarray):
    def __new__(cls, data):
        return np.asarray(data, dtype=cls.dtype_).view(cls)


class ByteArray(_Arr):
    tag, dtype_ = 7, np.int8


class IntArray(_Arr):
    tag, dtype_ = 11, np.int32


class LongArray(_Arr):
    tag, dtype_ = 12, np.int64


def tag_of(v):
    t = getattr(v, 'tag', None)
    if t is not None:
        return t
    if isinstance(v, bool):
        return 1
    if isinstance(v, (int, np.integer)):
        return 3
    if isinstance(v, (float, np.floating)):
        return 6
    if isinstance(v, str):
        return 8
    if isinstance(v, dict):
        return 10
    if isinstance(v, (list, tuple)):
        return 9
    if isinstance(v, (bytes, bytearray)):
        return 7
    if isinstance(v, np.ndarray):
        return {np.dtype(np.int64): 12, np.dtype(np.int32): 11, np.dtype(np.int8): 7}.get(v.dtype, 12)
    raise TypeError(f'no NBT tag for {type(v)}')


def _w_payload(out, t, v):
    if t == 1:
        out.write(struct.pack('>b', int(v)))
    elif t == 2:
        out.write(struct.pack('>h', int(v)))
    elif t == 3:
        out.write(struct.pack('>i', int(v)))
    elif t == 4:
        out.write(struct.pack('>q', int(v)))
    elif t == 5:
        out.write(struct.pack('>f', float(v)))
    elif t == 6:
        out.write(struct.pack('>d', float(v)))
    elif t == 7:
        b = bytes(v) if isinstance(v, (bytes, bytearray)) else np.asarray(v, np.int8).tobytes()
        out.write(struct.pack('>i', len(b))); out.write(b)
    elif t == 8:
        b = str(v).encode('utf-8')
        out.write(struct.pack('>H', len(b))); out.write(b)
    elif t == 9:
        elem = getattr(v, 'elem', None)
        if elem is None:
            elem = tag_of(v[0]) if len(v) else 0
        out.write(struct.pack('>bi', elem, len(v)))
        for x in v:
            _w_payload(out, elem, x)
    elif t == 10:
        for k, x in v.items():
            tt = tag_of(x)
            out.write(struct.pack('>b', tt)); _w_payload(out, 8, k); _w_payload(out, tt, x)
        out.write(b'\x00')
    elif t == 11:
        a = np.asarray(v, '>i4'); out.write(struct.pack('>i', len(a))); out.write(a.tobytes())
    elif t == 12:
        a = np.asarray(v, np.int64).astype('>i8'); out.write(struct.pack('>i', len(a))); out.write(a.tobytes())
    else:
        raise ValueError(t)


def dumps(root: dict, name='') -> bytes:
    out = io.BytesIO()
    out.write(b'\x0a'); _w_payload(out, 8, name); _w_payload(out, 10, root)
    return out.getvalue()


def save(path, root: dict, name='', compress='gzip'):
    data = dumps(root, name)
    if compress == 'gzip':
        data = gzip.compress(data, 6)
    elif compress == 'zlib':
        data = zlib.compress(data, 6)
    with open(path, 'wb') as fh:
        fh.write(data)


class _R:
    def __init__(self, b):
        self.b, self.i = b, 0

    def take(self, n):
        s = self.b[self.i:self.i + n]; self.i += n
        return s

    def un(self, fmt):
        n = struct.calcsize(fmt)
        v = struct.unpack_from(fmt, self.b, self.i); self.i += n
        return v[0]


def _r_payload(r, t):
    if t == 1:
        return Byte(r.un('>b'))
    if t == 2:
        return Short(r.un('>h'))
    if t == 3:
        return Int(r.un('>i'))
    if t == 4:
        return Long(r.un('>q'))
    if t == 5:
        return Float(r.un('>f'))
    if t == 6:
        return Double(r.un('>d'))
    if t == 7:
        n = r.un('>i'); return ByteArray(np.frombuffer(r.take(n), np.int8))
    if t == 8:
        n = r.un('>H'); return String(r.take(n).decode('utf-8', errors='replace'))
    if t == 9:
        et = r.un('>b'); n = r.un('>i')
        return List([_r_payload(r, et) for _ in range(n)], et)
    if t == 10:
        out = Compound()
        while True:
            tt = r.un('>b')
            if tt == 0:
                return out
            k = _r_payload(r, 8)
            out[str(k)] = _r_payload(r, tt)
    if t == 11:
        n = r.un('>i'); return IntArray(np.frombuffer(r.take(4 * n), '>i4').astype(np.int32))
    if t == 12:
        n = r.un('>i'); return LongArray(np.frombuffer(r.take(8 * n), '>i8').astype(np.int64))
    raise ValueError(f'bad tag {t}')


def loads(data: bytes):
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    elif data[:1] == b'\x78':
        try:
            data = zlib.decompress(data)
        except zlib.error:
            pass
    r = _R(data)
    t = r.un('>b')
    if t != 10:
        raise ValueError('root tag must be a compound')
    name = _r_payload(r, 8)
    return _r_payload(r, 10), str(name)


def load(path):
    with open(path, 'rb') as fh:
        return loads(fh.read())[0]


def plain(v):
    """Strip wrapper types (for printing / JSON)."""
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [plain(x) for x in v]
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return float(v)
    if isinstance(v, str):
        return str(v)
    return v
