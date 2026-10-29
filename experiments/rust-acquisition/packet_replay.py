"""Quarantined candidate-to-packet parity through frozen coherent windows."""
import argparse,ctypes as C,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--decoder-root',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.work.resolve();sys.path.insert(0,str(a.decoder_root/'src'));from rescue.coherent_fast import native_windows
libs={}
for name in ['c','rust']:
 l=C.CDLL(str(w/(name+'.so')));l.rescue_extended_select_neon.argtypes=[C.c_void_p,C.c_int64,C.c_int64,C.c_double,C.c_double,C.c_double,C.c_int,C.c_void_p,C.c_void_p];l.rescue_extended_select_neon.restype=C.c_int64;libs[name]=l
report={'iq_fixture_sha256':hashlib.sha256((w/'iq-blocks.bin').read_bytes()).hexdigest(),'policy':'Same frozen coherent decoder applied to each selector output in this offline process. Raw CRC-valid window outputs, not new packets beyond the live pipeline; no forwarding.','budgets':{}}
for budget in [16,64,256]:
 signatures={'c':[],'rust':[]};count=0;decoded=0;repaired=0
 with (w/'iq-blocks.bin').open('rb') as f,(w/'blocks.bin').open('rb') as powerfile:
  blocks=struct.unpack('<Q',f.read(8))[0];powerblocks,on,off,norm=struct.unpack('<Qddd',powerfile.read(32));assert blocks==powerblocks
  for block in range(blocks):
   n,core=struct.unpack('<qq',f.read(16));iq=np.frombuffer(f.read(n*8),'<c8').copy();pn,pcore=struct.unpack('<qq',powerfile.read(16));power=np.frombuffer(powerfile.read(pn*4),'<f4').copy();assert pn==n and pcore==core;assert np.array_equal(power,iq.real*iq.real+iq.imag*iq.imag)
   values={};outputs={}
   for name,lib in libs.items():
    ids=np.empty(budget,np.int64);score=np.empty(budget,np.float64);got=lib.rescue_extended_select_neon(power.ctypes.data,n,core,on,off,norm,budget,ids.ctypes.data,score.ctypes.data);assert got>=0,'Field fallback not covered by this replay';values[name]=(ids[:got].copy(),score[:got].copy());outputs[name]=native_windows(iq,ids[:got])
    rows,flips,valid=outputs[name][-3:]
    for j in np.flatnonzero(valid):signatures[name].append((block,int(ids[j]),rows[j].tobytes().hex(),flips[j].tolist()))
   assert all(np.array_equal(x,y) for x,y in zip(values['c'],values['rust']))
   for x,y in zip(outputs['c'],outputs['rust']):assert np.array_equal(x,y,equal_nan=True)
   count+=len(values['c'][0]);decoded+=int(outputs['c'][-1].sum());repaired+=int(np.count_nonzero(outputs['c'][-1]&(outputs['c'][-2][:,0]>=0)))
 assert signatures['c']==signatures['rust'];report['budgets'][str(budget)]={'candidates':count,'crc_valid_window_outputs':decoded,'repaired_window_outputs':repaired,'packet_start_payload_repair_signature_sha256':hashlib.sha256(json.dumps(signatures['c']).encode()).hexdigest(),'exact_candidate_and_all_decoder_arrays':True}
report['decoder_sha256']=hashlib.sha256((a.decoder_root/'src/rescue/_coherent.so').read_bytes()).hexdigest();a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['budgets'],indent=2))
