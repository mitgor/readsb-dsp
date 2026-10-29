#!/usr/bin/env python3
"""Mac-only independent no-fix qualification of v3 distant stock training snippets.
Leaves source archives intact. Never trains, enables a model or contacts receiver.
"""
import argparse,base64,collections,gzip,hashlib,json,subprocess,sys,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from rescue.far_training import valid_df17
from rescue.wire import BeastParser
from rescue.merge import parse_readsb
from rescue.research_reservations import load_reservations
p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--readsb',type=Path,required=True);p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();reserved,manifests=load_reservations(a.raw_root);counts=collections.Counter();examples=[]
with tarfile.open(a.archive) as tar:
 manifest=json.load(tar.extractfile('manifest.json'));assert manifest['schema']=='far-capture-v3'
 for name in ['training.uc8','training.jsonl']:
  stream=tar.extractfile(name);h=hashlib.sha256();size=0
  while blob:=stream.read(1024**2):h.update(blob);size+=len(blob)
  assert size==manifest['files'][name]['bytes'] and h.hexdigest()==manifest['files'][name]['sha256']
 for line in tar.extractfile('segments.jsonl'):
  r=json.loads(line)
  if r.get('record')=='continuous_segment':reserved[r['epoch']].append((r['sample_start'],r['sample_start']+r['sample_count']))
 rawfile=tar.extractfile('training.uc8')
 for line in tar.extractfile('training.jsonl'):
  r=json.loads(line);counts['offered']+=1
  if r.get('schema')!='far-stock-training-v1' or r.get('source')!='stock' or not valid_df17(r['target_hex']):counts['bad_provenance']+=1;continue
  frames=BeastParser().feed(bytes.fromhex(r.get('beast_wire_hex') or ''))
  if len(frames)!=1 or frames[0]['message_hex']!=r['target_hex'] or frames[0]['ticks_12mhz']-2398!=r['event_ticks']:counts['stock_clock_or_payload_mismatch']+=1;continue
  lo=r['sample_start'];hi=lo+r['sample_count']
  if any(start<hi and end>lo for start,end in reserved[r['epoch']]):counts['reserved_rf_overlap']+=1;continue
  q=r['position_quality']
  if not all(type(q.get(k)) in (int,float) and q[k]>=5 for k in ('nic','nac_p')) or q.get('mlat_fields') or q.get('tisb_fields') or q.get('available_unix',1e99)>r['event_unix'] or not 0<=r['event_unix']-r['position_unix']<=15:counts['position_quality_rejected']+=1;continue
  rawfile.seek(r['iq_byte_offset']);raw=rawfile.read(r['iq_bytes']);assert len(raw)==r['sample_count']*2 and hashlib.sha256(raw).hexdigest()==r['iq_sha256'];examples.append((r,raw))
combined=bytearray();mapping=[]
for r,raw in examples:
 combined.extend(bytes([127,128])*2400);at=len(combined)//2;combined.extend(raw);mapping.append((at,r,raw))
combined.extend(bytes([127,128])*2400)
with tempfile.TemporaryDirectory(prefix='adsb-far-qualify-') as temp:
 f=Path(temp)/'teacher.uc8';f.write_bytes(combined)
 cmd=[str(a.readsb),'--device-type','ifile','--ifile',str(f),'--iformat','UC8','--raw','--mlat','--no-fix','--no-fix-df'];result=subprocess.run(cmd,capture_output=True,text=True,timeout=120);assert result.returncode==0,result.stderr
 decoded=parse_readsb(result.stdout)
qualified=[];teacher_sha=hashlib.sha256(a.readsb.read_bytes()).hexdigest()
for at,r,raw in mapping:
 expected=at*5+r['event_ticks']-r['sample_start']*5
 matches=[v for v in decoded if v['message_hex']==r['target_hex'] and abs(round(v['seconds']*12e6)-expected)<=24]
 if not matches:counts['uncorrected_rf_not_confirmed']+=1;continue
 row=dict(r,record='training_window',label_provenance='stock_crc_assisted',training_eligible=True,verification_only=False,evaluation_only=False,iq_uc8_base64=base64.b64encode(raw).decode(),qualification=dict(method='same_transmission_stock_and_independent_uncorrected_readsb',readsb_sha256=teacher_sha,teacher_error_ticks=min(abs(round(v['seconds']*12e6)-expected) for v in matches)))
 qualified.append(row);counts['qualified']+=1;counts['qualified_180_200' if r['distance_nm']<200 else ('qualified_200_250' if r['distance_nm']<250 else 'qualified_250_plus')]+=1
# Label qualification is not permission to bypass aircraft/RF/payload/IQ split guards.
a.output.parent.mkdir(parents=True,exist_ok=True)
with gzip.open(a.output,'wt') as out:
 for r in qualified:out.write(json.dumps(r,separators=(',',':'))+'\n')
report=dict(readsb_sha256=teacher_sha,counts=counts,archive_sha256=hashlib.sha256(a.archive.read_bytes()).hexdigest(),output_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),reserved_manifests=manifests,policy='No-correction waveform confirmation plus original stock Beast at same exact sample clock. Future payload repetition/ICAO alone never labels. Existing training split exclusions still apply; no receiver change.')
Path(str(a.output)+'.qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
