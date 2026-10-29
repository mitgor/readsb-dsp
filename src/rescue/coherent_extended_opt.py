"""Exact-policy extended selector; Rust is primary when installed, C is retained."""
import ctypes as C
from pathlib import Path
import numpy as np
from .pipeline_v3 import BackendV3

_LIB=None

def library():
    global _LIB
    if _LIB is None:
        rust=Path(__file__).with_name('_acquisition_rust.so')
        lib=C.CDLL(str(rust if rust.exists() else Path(__file__).with_name('_pipeline_extended_neon.so')))
        lib._deadsb_backend='rust' if rust.exists() else 'c'
        arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS')
        lib.rescue_extended_select_neon.argtypes=[arr(np.float32),C.c_int64,C.c_int64,
            C.c_double,C.c_double,C.c_double,C.c_int,arr(np.int64),arr(np.float64)]
        lib.rescue_extended_select_neon.restype=C.c_int64
        _LIB=lib
    return _LIB

class ExtendedNeonBackend(BackendV3):
    def extended(self,power,core,budget=16):
        if type(budget) is not int or not 1<=budget<=256:
            raise ValueError('Invalid extended candidate budget')
        power=np.ascontiguousarray(power,np.float32)
        ids=np.empty(budget,np.int64);score=np.empty(budget,np.float64)
        count=library().rescue_extended_select_neon(power,len(power),core,
            self.on,self.off,self.norm,budget,ids,score)
        if count==-2:
            # The reference uses SciPy for equal-priority local maxima.
            return super().extended(power,core,budget)
        if count<0 or count>budget:raise ValueError('Native extended selection failed')
        return ids[:count],score[:count]

def backend_status():
    return library()._deadsb_backend
