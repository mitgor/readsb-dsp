"""Reconstruct paired already-consumed I/Q for packet replay, no live capture."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from rescue.pipeline_v3 import BackendV3
p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();meta=json.loads(a.manifest.read_text());b=BackendV3()
with a.output.open('wb') as f:
 f.write(struct.pack('<Q',len(meta['files'])))
 for row in meta['files']:
  path=a.input/row['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['source_sha256'];offset,core,iq=next(b.iq_blocks(path));assert offset==row['offset_4msps'] and core==row['core'] and len(iq)==row['samples'];f.write(struct.pack('<qq',len(iq),core));f.write(iq.astype('<c8').tobytes())
print(hashlib.sha256(a.output.read_bytes()).hexdigest())
