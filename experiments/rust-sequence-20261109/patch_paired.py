"""Isolated shared-mode protocol, only changes sequence ABI between quiescent RF jobs."""
from pathlib import Path
import sys,shutil
D=Path(sys.argv[1]);assert str(D)=='/dev/shm/adsb-rust-sequence-20261109';shutil.copytree(D/'optimized',D/'paired');shutil.copy2(D/'build/rust.so',D/'paired/src/rescue/_sequence_rust.so');p=D/'paired/src/rescue/ring_transport.py';s=p.read_text();s=s.replace("self.data=ctx.RawArray", "self.sequence_mode=ctx.Value('i',0)\n  self.data=ctx.RawArray",1)
anchor=' decoder._ring_backend=b';assert anchor in s;s=s.replace(anchor,anchor+'''
 if role=='coherent':
  import ctypes as C
  from .pipeline_v3 import library
  c=library();r=C.CDLL(str(Path(__file__).with_name('_sequence_rust.so')))
  r.rescue_sequence_batch.argtypes=c.rescue_sequence_batch.argtypes;r.rescue_sequence_batch.restype=c.rescue_sequence_batch.restype
  if r.rescue_coherent_init():raise RuntimeError('CRC init failed')
  decoder._sequence_libraries=(c,r)
''',1)
anchor=' workers._DECODER._ring_backend.job=(slot,gen)';s=s.replace(anchor,anchor+'''
 if workers._ROLE=='coherent':workers._DECODER.decoder.sequence.native_library=workers._DECODER._sequence_libraries[workers._DECODER._ring_backend.ring.sequence_mode.value]
''',1);p.write_text(s)
