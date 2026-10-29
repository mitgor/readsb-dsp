"""Isolated pair-lag carrier experiment; production coherent library is untouched."""
import ctypes as C
from pathlib import Path

import numpy as np

from .coherent_fast import library as reference_library

_LIB = None


def pair_windows(iq, starts):
    global _LIB
    iq = np.ascontiguousarray(iq, np.complex64)
    starts = np.ascontiguousarray(starts, np.int64)
    if iq.ndim != 1 or starts.ndim != 1 or len(starts) > 4096 or np.any(starts < 0) or np.any(starts + 480 > len(iq)):
        raise ValueError('Invalid pair-coherent window bounds')
    if _LIB is None:
        lib = C.CDLL(str(Path(__file__).with_name('_coherent_pair.so')))
        lib.rescue_coherent.argtypes = reference_library().rescue_coherent.argtypes
        lib.rescue_coherent.restype = C.c_int
        if lib.rescue_coherent_init():
            raise RuntimeError('Invalid CRC table')
        _LIB = lib
    n = len(starts)
    out = [np.empty((n, 112), np.float64), np.empty((n, 112), np.float64),
           np.empty(n, np.uint8), np.empty(n, np.float64), np.empty(n, np.int32),
           np.empty((n, 14), np.uint8), np.empty((n, 2), np.int8), np.empty(n, np.uint8)]
    if _LIB.rescue_coherent(iq.view(np.float32), len(iq), starts, n, *out):
        raise ValueError('Pair-coherent bounds check failed')
    out[-1] = out[-1].astype(bool)
    return tuple(out)
