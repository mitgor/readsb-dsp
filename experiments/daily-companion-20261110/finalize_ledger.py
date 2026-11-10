from pathlib import Path
import json,gzip,hashlib,os,datetime,collections,html
import numpy as np
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/daily-20261110'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
 with p.open('w') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
b=json.loads((O/'receiver-before.private.json').read_text());a=json.loads((O/'receiver-after.private.json').read_text());checks={k:b[k]==a[k] for k in ['pids','methods','workers','model_sha256','logging_enabled','samples','gain_db','source_hashes','configs','trial']};assert all(checks.values()),checks;assert a['capture']['config']['disk_limit_bytes']==5000000000
addresses={};historical_payloads=set();sources=[]
for folder,names in [(R/'data/transfer/improvement-20261027/raw',['learning-test','learning-validation','learning-train']),(R/'data/transfer/retrain-companion-20261029/prepared',['test','validation','train'])]:
 for name in names:
  p=folder/(name+'.npz');d=np.load(p);split=name.removeprefix('learning-')
  for x in d['icao']:
   s=str(x).lower();assert s not in addresses or addresses[s]==split;addresses[s]=split
  historical_payloads.update(bytes(x).hex() for x in d['truth']);sources.append(dict(path=str(p.relative_to(R)),sha256=sha(p)))
old=json.loads((R/'results/daily-20261109/learning-ledger.json').read_text());prior=old['records'];iqseen={v['iq_sha256'] for v in prior};eventseen={(v['epoch'],v['sample_start'],v['target_hex']) for v in prior};records=[];counts=collections.Counter()
archive_by_name={Path(x['local']).name:x for x in json.loads((O/'combined-input-manifest.json').read_text())['files']}
for p in sorted(O.glob('*.qualified.jsonl.gz')):
 q=json.loads(Path(str(p)+'.qualification.json').read_text());assert q['readsb_sha256']=='9f8a23dad7bf881cffd024e966bb868c2e1c3cc0ff6d198601cb56b249a93b9d';archive=archive_by_name[p.name.removesuffix('.qualified.jsonl.gz')]
 for l in gzip.open(p,'rt'):
  r=json.loads(l);assert r['training_eligible'] is True and r['source']=='stock' and r['distance_nm']>=180
  icao=r['target_hex'][2:8];bucket=int(hashlib.sha256(icao.encode()).hexdigest()[:8],16)%10;split=addresses.get(icao,'train' if bucket<7 else 'validation' if bucket<9 else 'test');counts['qualified_new']+=1
  row={k:r[k] for k in ('epoch','sample_start','sample_count','iq_sha256','target_hex','distance_nm','event_unix')};dup=r['iq_sha256'] in iqseen or (r['epoch'],r['sample_start'],r['target_hex']) in eventseen or r['target_hex'] in historical_payloads
  row.update(icao=icao,proposed_split=split,status='duplicate' if dup else 'qualified_pending_cross_split_rf_audit',duplicate=dup,training_admitted=False,qualification_sha256=sha(Path(str(p)+'.qualification.json')),archive_sha256=archive['sha256'],qualified_file_sha256=sha(p))
  iqseen.add(r['iq_sha256']);eventseen.add((r['epoch'],r['sample_start'],r['target_hex']));records.append(row)
# Explicit same-epoch RF overlap audit between new ICAO splits and prior qualified rows.
allrows=prior+records;conflict_ids=set()
for i,r in enumerate(allrows):
 for j,s in enumerate(allrows[:i]):
  if r['epoch']==s['epoch'] and r['sample_start']<s['sample_start']+s['sample_count'] and s['sample_start']<r['sample_start']+r['sample_count'] and r['proposed_split']!=s['proposed_split']:conflict_ids.update((i,j))
# Older source RF intervals are excluded conservatively, even where split metadata is absent.
oldcases=json.loads((R/'data/transfer/retrain-companion-20261029/prepared/cases.json').read_text());overlaps_old=0
for i,r in enumerate(allrows):
 if i<len(prior):continue
 if r['duplicate']:counts['duplicate_excluded']+=1;continue
 if i in conflict_ids:r['status']='cross_split_rf_overlap_quarantine';counts['rf_overlap_excluded']+=1;continue
 if any(c['epoch']==r['epoch'] and r['sample_start']<c['sample_start']+c['sample_count'] and c['sample_start']<r['sample_start']+r['sample_count'] for c in oldcases):r['status']='historical_source_rf_overlap_quarantine';counts['historical_rf_overlap_excluded']+=1;overlaps_old+=1;continue
 split=r['proposed_split'];r['status']='fixed_icao_test_evaluation_only' if split=='test' else 'qualified_split_eligible_pending_trigger';r['evaluation_only']=split=='test';r['cross_split_rf_audit']='passed';counts['new_unique_'+split]+=1
# Pin new test RF globally so future qualifying/training cannot consume it.
held=[dict(epoch=r['epoch'],sample_start=r['sample_start'],sample_count=r['sample_count']) for r in records if r.get('evaluation_only')];dest=R/'data/raw/long-validation-daily-qualification-holdout-20261110';dest.mkdir(exist_ok=True)
p=dest/'reserved-intervals.json';assert not p.exists();save(p,dict(schema='long-validation-v1',evaluation_only=True,captures=held,policy='Fixed ICAO test holdout, label confirmation only; no model evaluation or fitting.'))
train=[r for r in allrows if r.get('status')=='qualified_split_eligible_pending_trigger' and r['proposed_split']=='train'];val=[r for r in allrows if r.get('status')=='qualified_split_eligible_pending_trigger' and r['proposed_split']=='validation'];test=[r for r in allrows if r.get('evaluation_only')]
def coverage(rows):return dict(windows=len(rows),aircraft=len({r['icao'] for r in rows}),utc_hours=len({int(r['event_unix']//3600) for r in rows}),bands=dict(collections.Counter('180-200' if r['distance_nm']<200 else '200-250' if r['distance_nm']<250 else '250+' for r in rows)))
coverage_result={s:coverage(v) for s,v in [('train',train),('validation',val),('test',test)]};trigger=bool(len(train)>=500 and coverage_result['train']['aircraft']>=10 and coverage_result['train']['utc_hours']>=3 and len(val)>=100 and coverage_result['validation']['aircraft']>=3)
ledger=dict(schema='daily-learning-ledger-v1',since_last_completed_training='daily-20261104',records=allrows,counts=dict(counts),coverage=coverage_result,split_sources=sources,previous_ledger_sha256=sha(R/'results/daily-20261109/learning-ledger.json'),historical_source_intervals_sha256=sha(R/'data/transfer/retrain-companion-20261029/prepared/cases.json'),policy='Fixed historical ICAOs, historical payload/RF exclusions, IQ/transmission deduplication, cross-split RF audit. All unverified CRC and continuous RF remain quarantined. No training admitted without trigger and complete model protocol.');save(O/'learning-ledger.json',ledger)

readiness={'coverage':coverage_result,'trigger':trigger,'counts':dict(counts),'shortfall':{'train_windows':max(0,500-len(train)),'validation_windows':max(0,100-len(val))}};save(O/'readiness.json',readiness);print(json.dumps(readiness,indent=2))
