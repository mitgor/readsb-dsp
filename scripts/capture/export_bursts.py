#!/usr/bin/env python3
"""Export closed v2 RF bursts and synchronized packet references locally."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from rescue.ledger_verify import verify_ledger,ledger_frames
from rescue.wire import BeastParser
p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
with tarfile.open(a.archive) as tar:
 manifest=json.load(tar.extractfile('manifest.json'));assert manifest['schema'] in ('far-capture-v2','far-capture-v3')
 for name,meta in manifest['files'].items():
  h=hashlib.sha256();stream=tar.extractfile(name)
  while b:=stream.read(1048576):h.update(b)
  if h.hexdigest()!=meta['sha256']:raise ValueError('Archive checksum mismatch: '+name)
 coverage=verify_ledger(tar);begins={};ends={}
 for line in tar.extractfile('ledger.jsonl'):
  r=json.loads(line)
  if r['record']=='rf_burst_begin':begins[r['burst_id']]=r
  if r['record']=='rf_burst_end':ends[r['burst_id']]=r
 parsed=ledger_frames(tar);stock=parsed['stock'];unified=parsed['unified'];exported=[]
 for ident,b in begins.items():
  if ident not in ends:continue
  end=ends[ident];lo=b['sample_start']*5+2398;hi=end['sample_end']*5+2398
  stem=ident
  if not all(c.isdigit() or c=='-' for c in stem):raise ValueError('Invalid burst ID')
  rawfile=a.output/(stem+'.uc8');metafile=a.output/(stem+'.json')
  if metafile.exists() or rawfile.exists():raise ValueError('Refusing to overwrite exported burst')
  data=tar.extractfile(b['rf_file']);data.seek(b['rf_byte_start']);raw=data.read((end['sample_end']-b['sample_start'])*2);rawfile.write_bytes(raw)
  refs={}
  for name,rows in [('stock',stock),('unified',unified)]:
   chosen=[r for r in rows if r['epoch']==b['epoch'] and lo-30*12000000<=r['ticks_12mhz']<hi+8*12000000]
   wire=b''.join(bytes.fromhex(r['wire_hex']) for r in chosen);target=a.output/(stem+'.'+name+'.beast');target.write_bytes(wire);refs[name]=dict(file=target.name,sha256=hashlib.sha256(wire).hexdigest(),records=len(chosen))
  meta=dict(schema='rf-burst-export-v1',source_archive=a.archive.name,begin=b,end=end,rf_file=rawfile.name,iq_sha256=hashlib.sha256(raw).hexdigest(),sample_rate=2400000,iq_format='uc8',sample_count=len(raw)//2,core_ticks_12mhz=[lo,hi],packet_references=refs,reference_time_rule='(receiver_ticks_12mhz - 2398 - sample_start*5) / 12000000',training_eligible=False,stock_decoder_corrections_unknown=True,method_annotations='See source ledger; annotations are not authoritative output',streams_complete=end['streams_complete'])
  metafile.write_text(json.dumps(meta,indent=2)+'\n');exported.append(meta)
 print(json.dumps(dict(exported_bursts=len(exported),coverage=coverage,output=str(a.output)),indent=2))
