"""Synthetic known-CRC packets, weak-bit repair and Gaussian negative controls."""
import argparse,json,struct,subprocess
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.work.resolve();rng=np.random.default_rng(20261029)
packet=bytes.fromhex('8d40621d58c382d690c8ac2863a7');bits=np.unpackbits(np.frombuffer(packet,np.uint8));windows=[];seeds=[]
for j in range(64):
 z=np.zeros(480,np.complex128);z[[0,1,4,5,14,15,18,19]]=1
 for bit in range(112):z[32+4*bit+(0 if bits[bit] else 2):32+4*bit+(0 if bits[bit] else 2)+2]=1
 # Weak swapped decisions remain below the established repair confidence gate.
 for bit in ([50] if 48<=j<56 else [50,70] if j>=56 else []):
  q=32+4*bit;z[q:q+4]=.09;correct=0 if bits[bit] else 2;z[q+correct:q+correct+2]=.09;z[q+2-correct:q+2-correct+2]=.11
 frequency=[-90000.,-70000.,-25000.,0.,20000.,55000.,90000.][j%7];z*=np.exp(1j*(2*np.pi*frequency*(np.arange(480)-240)/4e6+j*.19));z+=rng.normal(0,1e-4,480)+1j*rng.normal(0,1e-4,480)
 full=np.zeros(496,np.complex64);full[8:488]=z;windows.append(full);seeds.append(frequency if j%4 else np.nan)
for j in range(64):windows.append((rng.normal(0,.01,496)+1j*rng.normal(0,.01,496)).astype(np.complex64));seeds.append(np.nan)
x=np.stack(windows).astype('<c8');z=x[:,8:488];power=(np.abs(z)**2).reshape(-1,120,4)[:,8:];left=power[:,:,:2].sum(2);right=power[:,:,2:].sum(2);l=(left-right).astype('<f8');c=(np.abs(left-right)/(left+right+np.float32(1e-9))).astype('<f8');f=np.asarray(seeds,dtype='<f8');fixture=w/'controls.bin';fixture.write_bytes(struct.pack('<Q',len(x))+x.tobytes()+f.tobytes()+l.tobytes()+c.tobytes());report={}
for iterations in [1,2,4]:
 samples={}
 for variant in ['c','rust']:
  out=w/(variant+'-control.out');info=json.loads(subprocess.check_output([str(w/(variant+'-bench')),str(fixture),'1',str(iterations),str(out)],text=True));b=out.read_bytes();at=2*len(x)*112*8;rows=np.frombuffer(b,'u1',len(x)*14,at).reshape(-1,14);at+=len(x)*14;flips=np.frombuffer(b,'i1',len(x)*2,at).reshape(-1,2);at+=len(x)*2;valid=np.frombuffer(b,'u1',len(x),at)
  assert valid[:48].all(),'clean packet failed';assert not valid[64:].any(),'noise accepted'
  for k in np.flatnonzero(valid[:64]):assert rows[k].tobytes()==packet,'wrong synthetic payload'
  samples[variant]={'clean_valid':int(valid[:48].sum()),'weak_valid':int(valid[48:64].sum()),'negative_valid':int(valid[64:].sum()),'repairs':int(np.count_nonzero(flips[:64,0]>=0)),'rows_hex_signature':[rows[i].tobytes().hex() for i in range(64)],'valid_signature':valid.tolist(),'flip_signature':flips[:64].tolist()}
 assert samples['c']==samples['rust'],'synthetic decision mismatch';report[str(iterations)]={k:v for k,v in samples['rust'].items() if not k.endswith('signature')}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
