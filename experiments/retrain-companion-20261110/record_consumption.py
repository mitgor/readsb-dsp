"""Durably mark exactly consumed labels without editing earlier ledgers."""
from pathlib import Path
import json,os,hashlib,datetime,collections
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/retrain-20261110'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 tmp=p.with_suffix(p.suffix+'.tmp')
 with tmp.open('w') as f:json.dump(d,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 tmp.replace(p);fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
d=json.loads((O/'learning-ledger-pretraining.json').read_text());meta=json.loads((O/'prepared-data.json').read_text());used={(r['epoch'],r['sample_start'],r['target_hex']):r for r in meta['new_examples']};counts=collections.Counter()
for r in d['records']:
 key=r['epoch'],r['sample_start'],r['target_hex'];u=used.get(key)
 if r.get('status')=='qualified_split_eligible_pending_trigger':
  if u:
   assert u['split']==r['proposed_split'];r.update(status='consumed_by_companion_trial',consumed_run='retrain-20261110',training_admitted=u['split']=='train',validation_consumed=u['split']=='validation');counts['consumed_'+u['split']]+=1
  else:r.update(status='preparation_alignment_quarantine',training_admitted=False,reason='Frozen preamble-only preparation alignment gate failed; not consumed');counts['preparation_quarantine']+=1
 if r.get('evaluation_only') and u:
  history=list(r.get('evaluation_history',[]))
  for x in [r.get('evaluated_candidate_run'),'retrain-20261110']:
   if x and x not in history:history.append(x)
  r.update(evaluation_history=history,evaluated_candidate_run='retrain-20261110');counts['evaluated_test']+=1
assert counts['consumed_train']==503 and counts['consumed_validation']==197
before=d['coverage'];d.update(since_last_completed_training='retrain-20261110',coverage_before_training=before,coverage={k:{'windows':0,'aircraft':0,'utc_hours':0,'bands':{}} for k in ['train','validation']},training_consumption_manifest='prepared-data.json',training_consumption_sha256=sha(O/'prepared-data.json'),previous_ledger_sha256=sha(O/'learning-ledger-pretraining.json'),benchmark_status='Mac validation complete; protected Pi repeats in progress; no production promotion');d['coverage']['test']=before['test'];save(O/'learning-ledger.json',d)
ready={'coverage':d['coverage'],'trigger':False,'training_completed':'retrain-20261110','consumed':dict(counts),'shortfall':{'train_windows':500,'validation_windows':100},'policy':'Await genuinely new labels after this completed fit; do not retrain consumed examples.'};save(O/'readiness-after-training.json',ready)
save(R/'results/learning-latest.json',{'schema':'learning-latest-v1','ledger':str((O/'learning-ledger.json').relative_to(R)),'ledger_sha256':sha(O/'learning-ledger.json'),'readiness':str((O/'readiness-after-training.json').relative_to(R)),'readiness_sha256':sha(O/'readiness-after-training.json'),'summary':str((O/'training-contract.json').relative_to(R)),'training_trigger':False,'last_completed_training':'retrain-20261110','status':'fit_completed_pi_validation_in_progress_no_model_deployed','updated_unix':datetime.datetime.now().timestamp()})
print(dict(counts))
