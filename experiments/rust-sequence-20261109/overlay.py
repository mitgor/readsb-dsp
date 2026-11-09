"""Patch only an isolated copied loader; never a production path."""
from pathlib import Path
import sys
D=Path(sys.argv[1]);assert '/dev/shm/adsb-rust-sequence-' in str(D);p=D/'candidate/src/rescue/pipeline_v3.py';s=p.read_text();old='super().__init__(h,backend,threshold,budget);self.sequence.native_library=library()';assert old in s
new='''super().__init__(h,backend,threshold,budget);self.sequence.native_library=sequence_rust_library()
  h=np.asarray(h,np.complex128)
  if self.sequence.native_library.rescue_sequence_prepare(np.ascontiguousarray(h.real),np.ascontiguousarray(h.imag),self.sequence.templates,self.sequence.pre):raise RuntimeError('Rust sequence prepare failed')'''
s=s.replace(old,new,1);s+='''\n_SEQUENCE_RUST=None
def sequence_rust_library():
 global _SEQUENCE_RUST
 if _SEQUENCE_RUST is None:
  old=library();lib=C.CDLL(str(Path(__file__).with_name('_sequence_rust.so')))
  for name in ('rescue_sequence_batch','rescue_sequence_prepare'):
   f=getattr(lib,name);f.argtypes=getattr(old,name).argtypes;f.restype=getattr(old,name).restype
  if lib.rescue_coherent_init():raise RuntimeError('Invalid Rust sequence CRC tables')
  _SEQUENCE_RUST=lib
 return _SEQUENCE_RUST
''';p.write_text(s)
