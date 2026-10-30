"""Reproducible read-only October27 incident review. Private inputs stay private."""
import argparse,collections,datetime,hashlib,json,math,re,statistics,subprocess,tarfile
from pathlib import Path
from zoneinfo import ZoneInfo
p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();R=a.data_root;O=a.output;O.mkdir(parents=True,exist_ok=True);inputs=[]
def load(rel):
 f=R/rel;inputs.append(dict(path=rel,sha256=hashlib.sha256(f.read_bytes()).hexdigest()));return json.loads(f.read_text())
def write(name,x):(O/name).write_text(json.dumps(x,indent=2)+'\n')
def iso(t):return datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
cloud=load('results/fr24-cloud-20261030/hourly-comparison.json');rows=[r for r in cloud if r['utc'].startswith('2026-10-27')];metrics={}
for key,local in [('fr24_hits','local_accepted'),('fr24_positions','positions')]:
 ratios=[math.log(r[key]/r['local_rate_integrals'][local]) for r in rows];fits=[]
 for split in range(5,20):
  sse=sum(sum((v-statistics.mean(group))**2 for v in group) for group in (ratios[:split],ratios[split:]));fits.append(dict(split_chart_hour=split,log_ratio_sse=sse))
 pre=[r for r in rows if 5<=int(r['utc'][11:13])<12];post=[r for r in rows if 13<=int(r['utc'][11:13])<22]
 before=sum(r[key] for r in pre)/sum(r['local_rate_integrals'][local] for r in pre);after=sum(r[key] for r in post)/sum(r['local_rate_integrals'][local] for r in post)
 metrics[key]=dict(pre_hours_utc='05–11',post_hours_utc='13–21',pre_cloud_per_local=before,post_cloud_per_local=after,relative_decline=1-after/before,best_descriptive_split=sorted(fits,key=lambda r:r['log_ratio_sse'])[:3],policy='Different counter definitions: ratio is an index of change, not a packet delivery fraction. Descriptive fit does not establish exact onset, significance or causation.')
rrd=load('results/fr24-oct27-cause-20261030/rrd-history.json');hourly=[]
for hour in range(24):
 summary=dict(chart_hour_utc=hour,berlin_hour=(hour+1)%24)
 for name,data in rrd['rrd'].items():
  values=[v for t,v in data['rows'] if datetime.datetime.fromtimestamp(t-1,datetime.timezone.utc).strftime('%Y-%m-%dT%H')==f'2026-10-27T{hour:02}']
  summary[name]=[dict(mean=statistics.mean(v[c] for v in values if v[c] is not None),min=min(v[c] for v in values if v[c] is not None),max=max(v[c] for v in values if v[c] is not None),points=sum(v[c] is not None for v in values)) if any(v[c] is not None for v in values) else None for c in range(len(data['columns']))]
 hourly.append(summary)
# Compare complete effective config and non-host bytes internally. Never output
# keys, key hashes, coordinates, passwords, or whole raw configurations.
archive=R/'incidents/fr24-drop-20261027/private/live-20261030/pi-source-config-backups-rrd.tar';inputs.append(dict(path=str(archive.relative_to(R)),sha256=hashlib.sha256(archive.read_bytes()).hexdigest()));configs=[]
with tarfile.open(archive) as t:
 blobs={m.name:t.extractfile(m).read() for m in t if m.isfile() and m.name.endswith('fr24feed.ini')}
base=blobs['var/backups/adsb-feed-20261025/fr24feed.ini']
def parse(raw):
 result={}
 for line in raw.decode().splitlines():
  m=re.match(r'^\s*([\w-]+)\s*=\s*(.*?)\s*$',line)
  if m:result[m[1]]=m[2].strip('"')
 return result
def nonhost(raw):return re.sub(rb'^host\s*=.*$',b'host=REDACTED_ROUTE',raw,flags=re.M)
bcfg=parse(base)
for name,raw in blobs.items():
 if '20260930' in name:continue # before readsb migration, outside incident baseline
 cfg=parse(raw);configs.append(dict(archive_member=name,changed_key_names=sorted(k for k in set(cfg)|set(bcfg) if cfg.get(k)!=bcfg.get(k)),all_nonhost_bytes_equal=nonhost(raw)==nonhost(base),sharing_key_equal=cfg.get('fr24key')==bcfg.get('fr24key'),receiver=cfg.get('receiver'),host=cfg.get('host'),mlat=cfg.get('mlat')))
# Commit dates and exact object ids are provenance, never deployment timestamps.
commits=[]
raw=subprocess.check_output(['git','-C',str(R),'log','--all','--since=2026-10-27T00:00:00+01:00','--until=2026-10-28T00:00:00+01:00','--format=%H%x09%aI%x09%s'],text=True)
for line in raw.splitlines():
 sha,date,title=line.split('\t',2);commits.append(dict(commit=sha,commit_date=date,title=title))
timeline=[]
def event(t,action,kind,source):
 dt=datetime.datetime.fromtimestamp(t,datetime.timezone.utc);timeline.append(dict(utc=dt.isoformat(),berlin=dt.astimezone(ZoneInfo('Europe/Berlin')).isoformat(),action=action,evidence_kind=kind,source=source))
for rel,label in [('results/dashboard-capture-20261027/pi-first-attempt-audit.json','Dashboard deployment first attempt failed lighttpd preflight; rollout restored'),('results/dashboard-capture-20261027/pi-audit.json','Dashboard/method switches and 230nm far RF capture activation audit began'),('results/relay-recovery-20261027/first-attempt.json','First relay repair attempt; readiness assertion failed and direct-stock route restored'),('results/relay-recovery-20261027/activation.json','Successful relay repair activation began; FR24 stock30005 -> combined31005, existing3s holdback')]:
 d=load(rel);event(d['started_unix'],label,'saved activation timestamp',rel)
d=load('results/dashboard-capture-20261027/pi-final-verification.json');event(d['status']['started_unix'],'Final dashboard-era DSP runtime start; readsb/FR24 preserved','runtime start', 'results/dashboard-capture-20261027/pi-final-verification.json')
d=load('results/relay-recovery-20261027/recovery-test.json')
for row in d['trace']:event(row['unix'],'Controlled sustained-outage recovery observation: '+row['host']+', relay PID '+str(row['relay_pid']),'saved test trace','results/relay-recovery-20261027/recovery-test.json')
d=load('results/relay-recovery-20261027/steady-audit.json');event(d['unix'],'60s steady audit:26,484 stock /0 missing /853 CRC-valid extra records','saved audit timestamp','results/relay-recovery-20261027/steady-audit.json')
protected=[]
for rel,label in [('results/capture-threshold-200-20261027/activation.json','Lower far RF/packet capture230->200nm'),('results/capture-triggers-20261027/activation.json','Local holdover/external capture triggers, recorder only'),('results/burst-ledger-20261027/activation.json','Synchronized burst stock/DSP journal capture')]:
 d=load(rel);timestamp=int(d['backup'].rsplit('-',1)[1])/1e9;event(timestamp,label,'backup-directory timestamp (activation start proxy)',rel);protected.append(dict(source=rel,comparison_available=('pids_before' in d and 'pids_after' in d),pids_equal=(d['pids_before']==d['pids_after']) if 'pids_before' in d and 'pids_after' in d else None,before=d.get('pids_before'),after=d.get('pids_after')))
for row in rows:
 if 10<=int(row['utc'][11:13])<=15:
  t=datetime.datetime.fromisoformat(row['utc'].replace('Z','+00:00')).timestamp();event(t,f"FR24 chart point:hits={row['fr24_hits']},positions={row['fr24_positions']}",'chart label; bucket start/end unresolved','results/fr24-cloud-20261030/cloud-hourly.json')
timeline.sort(key=lambda r:r['utc'])
upload=load('results/fr24-consistency-20261028/upload-history.json');upload_evidence=dict(first_saved_send_utc=iso(upload['sent'][0]['unix']),median_gap_s=upload['median_send_log_gap_s'],max_gap_s=upload['max_send_log_gap_s'],sent_events=upload['sent_events'],overlap_events=upload['overlap_events'],policy='Already30s by Oct28. No Oct27 cadence/configuration transition is retained, so no5->30s change is established.')
bel=load('results/bel7pj-track-20261028/summary.json')
stock_quality={k:bel[k] for k in ['flight','icao','date','local_utc_interval','position_separation_nm','stock_crc_valid_df17','nic_counts','nacp_counts','independent_cpr_snapshot_matches_within_0_1nm','independent_cpr_vs_snapshot_matched','limits']}
summary=dict(pre_existing_stock_quality=stock_quality,metrics=metrics,config_comparison=configs,oct27_commits=commits,protected_pid_comparison=protected,upload_cadence=upload_evidence,findings=['Cloud/local divergence persists after normalizing observed traffic; largest descriptive hourly break is13UTC chart point for both metrics','Input counter progresses ~554messages/s across11:52–13:28UTC; not uninterrupted minute-by-minute proof','Gain38.6dB across observed10–15UTC; average idle~49–61% and no sustained host saturation','Only host key/effective input route differs in incident-period feeder backups; key and MLAT unchanged','Neural was off and excluded from the Oct27 feeder policy; later neural/Rust/Stream1090 changes cannot initiate the Oct27 drop','Restored delayed combined route is the principal local candidate; pre-existing good Oct26 combined feeding and current short stock bypass weaken a simple universal delay-only explanation','No specific root cause proven; long direct-stock cloud result and FR24 historical filtering/configuration records remain needed'],working_setup_changes='none',browser_check='Existing FR24 tab could be listed but could not be read; no fresh cloud result asserted')
write('summary.json',summary);write('timeline.json',timeline);write('historical-health-hourly.json',hourly);write('input-manifest.json',inputs)
print(json.dumps(dict(configurations_checked=len(configs),incident_configs_nonhost_identical=all(r['all_nonhost_bytes_equal'] for r in configs),metrics=metrics,timeline_events=len(timeline)),indent=2))
