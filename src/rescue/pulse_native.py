"""Explicit opt-in native implementation of the frozen pulse discriminant."""
import ctypes as C
from pathlib import Path
import numpy as np
_LIB=None
def scores(power,starts,model):
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_pulse_discriminant.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS')
  lib.rescue_pulse_discriminant.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,arr(np.float64),C.c_double,arr(np.float32),arr(np.float32)];lib.rescue_pulse_discriminant.restype=C.c_int;_LIB=lib
 power=np.ascontiguousarray(power,np.float32);starts=np.ascontiguousarray(starts,np.int64);weights=np.ascontiguousarray(model['weights'],np.float64)
 if power.ndim!=1 or starts.ndim!=1 or weights.shape!=(8,):raise ValueError('Invalid pulse kernel dimensions')
 logits=np.empty((len(starts),112),np.float32);conf=np.empty_like(logits)
 if _LIB.rescue_pulse_discriminant(power,len(power),starts,len(starts),weights,model['bias'],logits,conf):raise ValueError('Invalid pulse kernel bounds or values')
 return logits,conf

def bank_scores(power,starts,models):
 """Shared input reads for the experimental multi-template bank."""
 global _LIB
 power=np.ascontiguousarray(power,np.float32);starts=np.ascontiguousarray(starts,np.int64)
 if power.ndim!=1 or starts.ndim!=1 or not 1<=len(models)<=8:raise ValueError('Invalid pulse bank dimensions')
 if _LIB is None:scores(power,np.empty(0,np.int64),models[0])
 f=_LIB.rescue_pulse_bank
 arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS')
 f.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,arr(np.float64),arr(np.float64),C.c_int64,arr(np.float32),arr(np.float32)];f.restype=C.c_int
 weights=np.ascontiguousarray([m['weights'] for m in models],np.float64);bias=np.ascontiguousarray([m['bias'] for m in models],np.float64)
 if weights.shape!=(len(models),8):raise ValueError('Invalid bank weights')
 logits=np.empty((len(starts),len(models),112),np.float32);conf=np.empty_like(logits)
 if f(power,len(power),starts,len(starts),weights,bias,len(models),logits,conf):raise ValueError('Invalid pulse bank bounds or values')
 return logits,conf
