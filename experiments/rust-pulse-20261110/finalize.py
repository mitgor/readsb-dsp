"""Activation gate: exact target C/Rust outputs and protected full current replay."""
from pathlib import Path
import subprocess,json,statistics,base64,hashlib,os
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-pulse-20261110')
code=r'''
from pathlib import Path
import subprocess,json,base64
assert subprocess.run(['systemctl','is-active','--quiet','adsb-rust-pulse-20261110']).returncode!=0
D=Path('/dev/shm/adsb-rust-pulse-20261110');out={n:json.loads((D/n).read_text()) for n in ['benchmark.json','full-c.private.json','full-rust.private.json','protected.private.json']};out['candidate_b64']=base64.b64encode((D/'build/rust.so').read_bytes()).decode();out['model_b64']=base64.b64encode((D/'models/pulse-discriminant.json').read_bytes()).decode();print(json.dumps(out))
'''
x=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True));raw=base64.b64decode(x.pop('candidate_b64'));model=base64.b64decode(x.pop('model_b64'));(D/'target-results.private.json').write_text(json.dumps(x)+'\n');b=x['benchmark.json'];h=x['protected.private.json'];assert b['all_arrays_bit_exact'] and b['error_and_numeric_controls']>=58 and b['bank_controls']>=6;assert h['error'] is None and h['before']==h['after'];assert max(r['rss_kib'] for r in h['checks'])<1024*1024;assert hashlib.sha256(raw).hexdigest()==b['libraries']['rust'];assert hashlib.sha256(model).hexdigest()=='bd9abaa59413fda4506ffb8c66f86418a7c33bc16b6c6d0521e42e904931b4fe'
old=x['full-c.private.json'];new=x['full-rust.private.json'];assert len(old['cases'])==len(new['cases'])==24
for ref,row in zip(old['cases'],new['cases']):
 assert ref['file']==row['file']
 for key in ['candidates','accepted','audit','decisions']:assert ref[key]==row[key],(ref['file'],key)
proof=dict(parity_passed=True,safe_to_activate=True,windows=b['windows'],numeric_and_error_controls=b['error_and_numeric_controls'],bank_controls=b['bank_controls'],packet_window_outputs=b['packet_window_outputs'],packet_signature_sha256=b['packet_signature_sha256'],median_cpu_s=b['median_cpu_s'],median_CPU_change_vs_C_percent=statistics.median(100*(t['cpu_s']['rust']/t['cpu_s']['c']-1) for t in b['trials']),median_CPU_change_vs_actual_C_percent=statistics.median(100*(t['cpu_s']['rust']/t['cpu_s']['actual']-1) for t in b['trials']),libraries=b['libraries'],full_RF_seconds=24,full_native_extras=sum(len(r['accepted']) for r in old['cases']),all_raw_guarded_events_alignment_decisions_exact=True,no_lost_or_added_packets=True,full_worker_CPU_per_RF_second=dict(C=old['worker_cpu_s']/24,Rust=new['worker_cpu_s']/24),max_test_RSS_MiB=max(r['rss_kib'] for r in h['checks'])/1024,protected_unchanged=True,model_sha256=hashlib.sha256(model).hexdigest(),scope='Historical regression corpus, full current pipeline including Rust sequence/coherent/acquisition and enabled neural methods. Broad CRC remains quarantined. One sequential full-worker pass is not a precise CPU/energy comparison. User requested Rust activation if parity/stability pass; no CPU-saving claim is a gate.')
(D/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');(D/'candidate.so').write_bytes(raw)
for p in [D/'proof.json',D/'candidate.so',D/'target-results.private.json']:
 with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd);print(json.dumps(proof,indent=2))
