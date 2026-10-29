#!/usr/bin/env python3
"""Verify bounded far-capture archives; optionally export verified packet windows.

Stock frames are observations, not automatic labels. DSP predictions stay
quarantined; split by aircraft and RF interval before any model training.
"""
import argparse,hashlib,json,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--export-packets',type=Path);a=p.parse_args()
with tarfile.open(a.archive,'r:') as tar:
 manifest=json.load(tar.extractfile('manifest.json'));members=tar.getmembers();allowed={'continuous.uc8','packets.uc8','stock.beast','packets.jsonl','segments.jsonl','manifest.json'}
 if manifest.get('schema') in ('far-capture-v2','far-capture-v3'):allowed.update(('stock-full.beast','unified.beast','ledger.jsonl'))
 if manifest.get('schema')=='far-capture-v3':allowed.update(('training.uc8','training.jsonl'))
 if set(manifest['files'])!=allowed-{'manifest.json'}:raise ValueError('Manifest member mismatch')
 if len(members)!=len(allowed) or {m.name for m in members}!=allowed or any(not m.isfile() for m in members):raise ValueError('Unexpected archive members')
 for name,meta in manifest['files'].items():
  stream=tar.extractfile(name);h=hashlib.sha256();size=0
  while True:
   b=stream.read(1024**2)
   if not b:break
   h.update(b);size+=len(b)
  if size!=meta['bytes'] or h.hexdigest()!=meta['sha256']:raise ValueError('Checksum mismatch: '+name)
 packets=0;raw=0
 for line in tar.extractfile('packets.jsonl'):
  row=json.loads(line);packets+=1
  if row['raw_available']:
   name=row['iq_file']
   if name not in ('continuous.uc8','packets.uc8'):raise ValueError('Invalid IQ reference')
   stream=tar.extractfile(name);stream.seek(row['iq_byte_offset']);b=stream.read(row['iq_bytes'])
   if len(b)!=row['iq_bytes'] or hashlib.sha256(b).hexdigest()!=row['iq_sha256']:raise ValueError('Packet IQ checksum mismatch')
   raw+=1
   if a.export_packets:
    a.export_packets.mkdir(parents=True,exist_ok=True);stem=f'{a.archive.stem}-{packets:08d}';(a.export_packets/(stem+'.uc8')).write_bytes(b);(a.export_packets/(stem+'.json')).write_text(json.dumps(row,indent=2))
 coverage=None
 if manifest.get('schema') in ('far-capture-v2','far-capture-v3') and manifest.get('packet_ledger') is not None:
  import sys
  sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
  from rescue.ledger_verify import verify_ledger
  coverage=verify_ledger(tar)
 print(json.dumps(dict(packet_ledger=coverage,archive=str(a.archive),verified=True,packets=packets,packets_with_iq=raw,manifest=manifest),indent=2))
