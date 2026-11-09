#!/usr/bin/env python3
"""Reproduce the closed trial audit without touching receiver state."""
import json,math,re,statistics,datetime,hashlib,html,csv
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
PRIVATE=Path('/Users/mit/Documents/!project/adsb-neural-rescue/incidents/fr24-drop-20261027/native-fr24-20261107/review-20261109')
OUT=REPO/'validation/fr24-native-20261107';OUT.mkdir(exist_ok=True)
F=PRIVATE/'files';D=F/'var/lib/adsb-fr24-native-20261107-v4'
s=json.loads((D/'state.json').read_text());live=json.loads((F/'live.private.json').read_text());cloud=json.loads((HERE/'cloud-hourly.json').read_text());days={d['date']:d for d in cloud['days']}
start=s['measurement_start_unix'];end=s['restore_started_unix']
def utc(t):return datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
def epoch(d):return datetime.datetime.fromisoformat(d).replace(tzinfo=datetime.timezone.utc).timestamp()
rows=[json.loads(x) for x in (F/'run/adsb-fr24-native-20261107-v4/samples.jsonl').read_text().splitlines()]
native=[r for r in rows if r.get('native')];period=[r for r in rows if start<=r['unix']<end]
assert all(d['hits']==sum(d['hourly_hits']) and d['positions']==sum(d['hourly_positions']) for d in cloud['days'])
assert len({r['decoder_pid'] for r in period})==1
jrows=[json.loads(x) for x in (F/'journals/fr24feed.jsonl').read_text().splitlines()]
jrows=[r for r in jrows if start<=int(r['__REALTIME_TIMESTAMP'])/1e6<end]
sent=[int(r['__REALTIME_TIMESTAMP'])/1e6 for r in jrows if '[feed][i]sent ' in r.get('MESSAGE','')]
gaps=[b-a for a,b in zip(sent,sent[1:])]
def percentile(v,q):return sorted(v)[min(len(v)-1,int(q*(len(v)-1)))]
events={}
for key,pattern in [('stream_timeouts','syncing stream: timeout'),('disconnects','[feed][n]disconnected'),('overlap_filter_events','filtering out'),('sync_success','syncing stream result: 1')]:
 a=[r for r in jrows if pattern in r.get('MESSAGE','')];events[key]=dict(count=len(a),utc=[utc(int(r['__REALTIME_TIMESTAMP'])/1e6) for r in a] if len(a)<25 else None)
# Historical graph values: integrate finite intervals with explicit coverage. Metrics differ across decoders.
rrd=json.loads((PRIVATE/'rrd-history.json').read_text());rr={}
for name,text in rrd['rrd'].items():
 a=[(int(t),float(v)) for t,v in re.findall(r'^(\d+):\s+(\S+)',text,re.M)];step=statistics.median(b[0]-a[0] for a,b in zip(a,a[1:]));rr[name]=(a,step)
def integrate(name,a,b):
 arr,step=rr[name];total=coverage=0
 for t,v in arr:
  overlap=max(0,min(t,b)-max(t-step,a))
  if overlap and math.isfinite(v):total+=v*overlap;coverage+=overlap
 return dict(integrated=round(total),coverage_seconds=coverage,requested_seconds=b-a)
def value_at(t,key):
 before=[r for r in native if r['unix']<=t];after=[r for r in native if r['unix']>=t]
 if not before or not after:return None
 a,b=before[-1],after[0]
 if b['unix']-a['unix']>90:return None
 def val(r):
  d=r['native']
  for k in key:d=d[k]
  return d
 if b['unix']==a['unix']:return val(a)
 return val(a)+(val(b)-val(a))*(t-a['unix'])/(b['unix']-a['unix'])
hr=[]
for day,d in days.items():
 for h in range(24):
  t=epoch(day)+h*3600
  nominal=start<=t and t+3600<=end
  stable=nominal and not(day=='2026-11-07' and h==12)
  a=value_at(t,['messages']);b=value_at(t+3600,['messages'])
  poskeys=[['cpr','global_ok'],['cpr','local_ok']]
  av=[value_at(t,k) for k in poskeys];bv=[value_at(t+3600,k) for k in poskeys]
  hr.append(dict(utc=utc(t),date=day,hour=h,nominal_native_hour=nominal,conservative_native_hour=stable,cloud_hits=d['hourly_hits'][h],cloud_positions=d['hourly_positions'][h],native_accepted_delta=round(b-a) if a is not None and b is not None else None,native_cpr_success_delta=round(sum(bv)-sum(av)) if all(x is not None for x in av+bv) else None,rrd_accepted=integrate('local_accepted',t,t+3600),rrd_positions=integrate('positions',t,t+3600)))
comparisons=[]
for date in ['2026-11-05','2026-11-06']:
 for conservative in [False,True]:
  trial=[r for r in hr if r['conservative_native_hour']] if conservative else [r for r in hr if r['nominal_native_hour']]
  # Repeated baseline hour weights match the actual available trial hours, rather than comparing partial/full days.
  base=[next(r for r in hr if r['date']==date and r['hour']==x['hour']) for x in trial]
  record=dict(baseline_date=date,hours=len(trial),conservative=conservative)
  for label,field in [('hits','cloud_hits'),('positions','cloud_positions')]:
   a=sum(r[field] for r in trial);b=sum(r[field] for r in base);record[label]=dict(trial=a,baseline_same_hour_weighted=b,change_percent=100*(a/b-1))
  for metric in ['accepted','positions']:
   record['rrd_'+metric]=dict(trial=sum(r['rrd_'+metric]['integrated'] for r in trial),baseline=sum(r['rrd_'+metric]['integrated'] for r in base),trial_coverage_seconds=sum(r['rrd_'+metric]['coverage_seconds'] for r in trial),baseline_coverage_seconds=sum(r['rrd_'+metric]['coverage_seconds'] for r in base))
  comparisons.append(record)
source=(D/'trial.py').read_bytes();canonical=(HERE.parent/'trial.py').read_bytes();receipt=json.loads((PRIVATE/'transfer-receipt.private.json').read_text())
summary=dict(review_utc=receipt['collected_utc'],active_attempt='v4',result='aborted_early_and_restored',planned_hours=48,actual_measurement_hours=(end-start)/3600,measurement_start_utc=utc(start),health_rollback_utc=utc(end),restored_utc=utc(s['closed_unix']),health_failure=s['health_failure'],nominal_complete_native_hours=sum(r['nominal_native_hour'] for r in hr),conservative_chart_hours=sum(r['conservative_native_hour'] for r in hr),missing_planned_hours=13,cloud_data_available=True,cloud_daily_sum_checks=10,restoration_files_verified=len(live['config_restoration']),all_original_files_match=all(r['matches'] for r in live['config_restoration']),original_shadow_and_capture_pids_preserved={u:live['services'][u].splitlines()[0].split('=')[1]==str(s['before']['pids'][u]) for u in ['adsb-rescue-shadow','adsb-far-capture']},services=live['services'],fr24_connected=live['fr24']['feed_status']=='connected' and live['fr24']['rx_connected']=='1',rf_cap_bytes=live['capture']['disk_limit_bytes'],capture_error=live['capture']['error'],gain_db=s['options']['gain'],native_source_sha256=hashlib.sha256(source).hexdigest(),native_source_matches_canonical=source==canonical,health_samples=len(period),max_sample_gap_seconds=max(b['unix']-a['unix'] for a,b in zip(period,period[1:])),single_decoder_pid=True,native_last_counters=native[-1]['native'],native_first_counters=native[0]['native'],native_counter_bounds_utc=[utc(native[0]['unix']),utc(native[-1]['unix'])],uploader=dict(send_log_events=len(sent),median_interval_seconds=statistics.median(gaps),p95_interval_seconds=percentile(gaps,.95),max_interval_seconds=max(gaps),gaps_over45_seconds=sum(x>45 for x in gaps),**events),comparisons=comparisons,evidence=dict(bytes=receipt['bytes'],sha256=receipt['sha256'],members_verified=receipt['members_verified']),limitations=['Trial ended after35h on a feeder stream timeout; not a complete48h condition.','Native FR24/dump1090 demodulation and transport differ from readsb, so this is not a pure DSP on/off comparison.','Daily and matched-hour comparisons are observational; traffic/weather/weekend and receiver protocol differ.','Local message/CPR counters are not cloud credit or a packet-delivery denominator.','Chart UTC label start/end convention is unresolved; conservative analysis excludes first transition-adjacent label.','Minute health checks cannot exclude sub-minute connection loss; journal has15 stream timeouts and5 disconnections.','November8 23:00 and all November9 labels are not native exposure. November9 is partial.','Earlier60h readsb-stock trial aborted on October31 and is not complete.'])
assert summary['all_original_files_match'] and summary['fr24_connected'] and all(summary['original_shadow_and_capture_pids_preserved'].values())
assert summary['rf_cap_bytes']==5000000000 and summary['capture_error'] is None and summary['native_source_matches_canonical']
(OUT/'review-summary.json').write_text(json.dumps(summary,indent=2)+'\n');(OUT/'cloud-hourly.json').write_text(json.dumps(cloud,indent=2)+'\n');(OUT/'hourly-comparison.json').write_text(json.dumps(hr,indent=2)+'\n')
with (OUT/'hourly-comparison.csv').open('w') as f:
 w=csv.writer(f,lineterminator="\n");w.writerow(['UTC label','native nominal','native conservative','cloud hits','cloud positions','native accepted delta','native CPR success delta','RRD accepted','RRD position','RRD accepted coverage seconds'])
 for r in hr:w.writerow([r['utc'],r['nominal_native_hour'],r['conservative_native_hour'],r['cloud_hits'],r['cloud_positions'],r['native_accepted_delta'],r['native_cpr_success_delta'],r['rrd_accepted']['integrated'],r['rrd_positions']['integrated'],r['rrd_accepted']['coverage_seconds']])
lines=['# Official FR24 native receiver trial — closed review, 9 November 2026','', '**The stock decoder did not restore pre-drop FR24 hits/positions during the observed35-hour condition. The planned48-hour trial stopped early; this is not a complete48-hour result.**','',f"Measurement began7 November12:00UTC (13:00Berlin). On8 November23:00:01UTC the feeder logged `syncing stream: timeout`, followed by disconnect at23:00:02. The once/minute health monitor detected the disconnected link at23:00:29 and restored the original setup by{utc(s['closed_unix'])}. This was a feeder-link timeout, not evidence that the native demodulator failed. Other transient disconnects had reconnected before health sampling. No new condition was launched.",'','## Restoration verified','', 'All14 managed original paths match their saved state. Readsb, FR24, combined relay, ADSBx, DSP and RF collector are active; DSP/collector retain their original PIDs and are thawed. FR24 is connected through the restored configuration. Gain remains38.6dB and the RF cap remains5,000,000,000bytes. The collector reports no error. No forced buffer flush or archive deletion was performed.','', '## Cloud statistics read from signed-in browser','', '| UTC date | Condition | Aircraft | Positions | Hits | Maximum nm |','|---|---|---:|---:|---:|---:|']
for d in cloud['days']:
 condition={'2026-11-05':'Before trial','2026-11-06':'Before trial','2026-11-07':'Mixed: native from11:52; measure from12:00','2026-11-08':'Native until23:00, then restored','2026-11-09':'Restored; partial day'}[d['date']]
 lines.append(f"| {d['date']} | {condition} | {d['aircraft']:,} | {d['positions']:,} | {d['hits']:,} | {d['max_range_nm']} |")
lines+=['','The visible hourly chart was read through rendered SVG coordinates, using its displayed linear axis. Every daily hits/positions total equals the sum of its24 reconstructed hourly points (10 exact checks). November9 future zero points are not measured zero reception. No hidden app/session data or authenticated API was used.','', '## Matched UTC hours','', 'There are35 nominal complete native measurement hours:7 November12–23 and8 November00–22. A conservative34-hour chart-label comparison excludes7 November12 because the label boundary convention is unresolved. Each earlier date is weighted with the same hour list, including repeated morning/evening hours.','', '| Baseline date, same34-hour weights | Trial hits | Baseline hits | Change | Trial positions | Baseline positions | Change |','|---|---:|---:|---:|---:|---:|']
for c in comparisons:
 if c['conservative']:
  h=c['hits'];p=c['positions'];lines.append(f"| {c['baseline_date']} | {h['trial']:,} | {h['baseline_same_hour_weighted']:,} | {h['change_percent']:+.1f}% | {p['trial']:,} | {p['baseline_same_hour_weighted']:,} | {p['change_percent']:+.1f}% |")
lines+=['','These comparisons do not establish causality: they are not randomized or traffic-matched. Against October26 pre-drop cloud credit (10,153,060hits and1,748,894positions), November8 remained in the same low-count regime as the post-drop period. November8 was not a full native day; its23:00 hour is excluded from native matched-hour totals. No evidence supports an order-of-magnitude credit recovery after switching to official FR24 DVB-T input.','', '## Local reception, cadence and interruption evidence','', f"The same native decoder PID persisted throughout sampled exposure, with {len(period):,} health samples and maximum sample gap {summary['max_sample_gap_seconds']:.2f}s. Last native counters show {native[-1]['native']['messages']:,} accepted messages, {native[-1]['native']['cpr']['global_ok']:,} global CPR successes and zero samples dropped since decoder startup; these are not48-hour totals or FR24 cloud credit.",'',f"The journal contains {len(sent):,} `sent … AC` events during measurement: median interval {statistics.median(gaps):.3f}s,95th percentile {percentile(gaps,.95):.3f}s, maximum {max(gaps):.3f}s. There were {events['stream_timeouts']['count']} stream timeouts and {events['disconnects']['count']} disconnections, and {events['overlap_filter_events']['count']:,} overlap-filter log events. Configuration messages before/after measurement show30s/30s sending, maximum age15s and filtering enabled. Local feeder activity cannot prove which packets the cloud credits.",'', 'The CSV/JSON include local RRD integration, explicit finite-data coverage and interpolated native counter changes. RRD and native counter semantics differ across receiver implementations; ratios are not packet-loss rates. Native counter changes require bracketing samples within90seconds; missing boundary data remain null.','', '## Interpretation and next evidence','', 'The observation weakens the claim that the current readsb/DSP relay alone is sufficient to explain the persistent low credit: low cloud counts also occur with official native input bypassing it. It does not rule out earlier stream-quality/account effects, stock payload quality, backend overlap selection, or cadence/accounting policy. The remote timeout explains why this trial closed, not the original October27 drop.','', 'Keep the restored working pipeline unchanged. The most useful next evidence is FR24 support explaining receiver-side overlap filtering/cloud-credit policy and the account’s server-side changes around October27. No support message was sent automatically. A further controlled trial needs separate authorization and a predefined disconnection tolerance, rather than silently extending this incomplete condition.','', '## Preservation','', f"Closure evidence: {receipt['bytes']:,}bytes, SHA-256 `{receipt['sha256']}`, {receipt['members_verified']} verified members, including lifecycle state, exact source/config rollback records, RAM health samples, hourly checkpoints and trial-period journals. Full logs/configs remain in the private incident case because they contain the sharing key. This public report contains only redacted results. Earlier failed attempts and the aborted October31 trial are preserved and excluded."]
text='\n'.join(lines)+'\n';(OUT/'review-report.md').write_text(text)
# Simple self-contained static HTML: escape every source string and add a readable table layout.
parts=[];in_table=False;in_list=False
for line in lines:
 if line.startswith('|'):
  if set(line.replace('|','').replace('-','').replace(':','').strip())==set():continue
  if not in_table:parts.append('<table>');in_table=True
  cells=[c.strip() for c in line.strip('|').split('|')];tag='th' if cells[0] in ['UTC date','Baseline date, same34-hour weights'] else 'td';parts.append('<tr>'+''.join('<'+tag+'>'+html.escape(c)+'</'+tag+'>' for c in cells)+'</tr>');continue
 if in_table:parts.append('</table>');in_table=False
 if not line:continue
 if line.startswith('# '):parts.append('<h1>'+html.escape(line[2:])+'</h1>')
 elif line.startswith('## '):parts.append('<h2>'+html.escape(line[3:])+'</h2>')
 else:parts.append('<p>'+html.escape(line).replace('**','')+'</p>')
if in_table:parts.append('</table>')
page='<!doctype html><html lang="en"><meta charset="utf-8"><title>FR24 native trial: closed review</title><meta name="viewport" content="width=device-width"><style>body{background:#101b29;color:#e2ebf4;font:16px/1.55 system-ui;max-width:1200px;margin:32px auto;padding:0 20px}h1,h2{color:#bce3ff}table{border-collapse:collapse;display:block;overflow:auto;width:100%;font-size:14px}td,th{padding:9px;border:1px solid #405369;text-align:right}td:first-child,th:first-child{text-align:left}p{max-width:1100px}</style>'+''.join(parts)+'</html>'
(OUT/'review-report.html').write_text(page)
# Replace stale activation landing page while preserving its prior version.
for suffix in ['md','html']:
 old=OUT/('report.'+suffix);backup=OUT/('activation-report.'+suffix)
 if not backup.exists():backup.write_bytes(old.read_bytes())
 old.write_bytes((OUT/('review-report.'+suffix)).read_bytes())
print(json.dumps({'actual_hours':summary['actual_measurement_hours'],'restored':summary['all_original_files_match'],'cadence':summary['uploader']['median_interval_seconds'],'comparisons':comparisons},indent=2))
