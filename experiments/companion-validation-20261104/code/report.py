from common import *
import statistics,html,os
mac=[json.loads((OUT/f).read_text()) for f in ['mac.json','mac-2.json','mac-3.json']];pi=[json.loads((OUT/f'pi-{i}.json').read_text()) for i in [1,2,3]]
fields=['production_digest','previous_digest','candidate_digest','distance_bins','raw_baseline_losses','candidate_additions_beyond_production','candidate_additions_beyond_previous_best','stream_alignment']
checks={k:all(r[k]==mac[0][k] for r in mac+pi) for k in fields};assert all(checks.values()),checks
keys=['production_cpu_per_rf_second','previous_best_cpu_per_rf_second','candidate_bundle_cpu_per_rf_second','incremental_candidate_inference_cpu_per_rf_second','incremental_candidate_percent_of_production']
cpu={name:{k:{'median':statistics.median(r[k] for r in rows),'min':min(r[k] for r in rows),'max':max(r[k] for r in rows)} for k in keys} for name,rows in [('mac',mac),('pi',pi)]}
base=pi[0];health=json.loads((OUT/'pi-health.private.json').read_text());protected=json.loads((OUT/'protected-checks.json').read_text());assert not health['live_changed'] and all(protected.values());assert all(r['raw_baseline_losses']==0 for r in mac+pi)
summary={'candidate_sha256':base['candidate_sha256'],'diagnosis':'Original failure had29anchors below the unchanged100minimum, not a wandering clock. Expand only globally reserved evaluation RF and independently check each archive against the shared epoch clock.','alignment':base['stream_alignment'],'rf_seconds':base['rf_seconds'],'interior_rf_seconds':base['effective_rf_seconds'],'cases':len(base['cases']),'full_current_methods':base['baseline_methods'],'production_extras':base['production_extras'],'candidate_additions_beyond_production':base['candidate_additions_beyond_production'],'candidate_additions_beyond_previous_best':base['candidate_additions_beyond_previous_best'],'baseline_losses':0,'distance_bins':base['distance_bins'],'confirmed_far_aircraft':base['far_stock_aircraft'],'cpu':cpu,'parity':checks,'unit_tests_passed':6,'protected_checks':protected,'guard_health_samples':len(health['samples']),'model_deployed':False,'stock_only_fr24_unchanged':True,'cleanup':'Only owned tmpfs removed after checksum-verified durable Mac input/results backup. No persistent receiver archives deleted.','limitations':['18.4 RFseconds across six archives, one quality-confirmed aircraft beyond180nm: inadequate evidence of distant generalization.','Captured before frozen candidate; no post-freeze prospective evidence.','Per-burst complete stock/unified references; one incomplete group excluded. DSP annotations are best-effort provisional, conservatively masked, not an authoritative complete production-acceptance ledger.','Serial replay CPU includes repeated frontends and per-clip Stream1090 startup; excludes live ring transport, admission and statistics overhead; not measured live production CPU or electrical power.','Requested Pi MemoryMax1G; MemoryCurrent unavailable on kernel. Observed benchmark VmHWM191248KiB; no memory-controller enforcement claim.']};write(OUT/'summary.json',summary);write(OUT/'parity.json',checks)
bins=base['distance_bins'];ranges=['0-50','50-100','100-150','150-180','180-200','200-250','250+','unknown'];rows='\n'.join(f"| {b} | {bins.get(b,{}).get('production_extras',0)} | {bins.get(b,{}).get('candidate_beyond_production',0)} | {bins.get(b,{}).get('candidate_beyond_previous_best',0)} |" for b in ranges)
costrows='\n'.join(f"| {name} | {cpu['mac'][key]['median']:.4f} | {cpu['pi'][key]['median']:.4f} |" for name,key in [('Current production pipeline','production_cpu_per_rf_second'),('Production + previous best offline companion','previous_best_cpu_per_rf_second'),('Above + new frozen companion','candidate_bundle_cpu_per_rf_second'),('New companion inference alone','incremental_candidate_inference_cpu_per_rf_second')])
text=f'''# Frozen companion: complete pipeline replay on Mac and Pi — 4 November 2026

**Alignment checks now pass on both machines. The frozen companion added zero unique guarded transmissions beyond the complete enabled pipeline and zero beyond that pipeline plus the previous best offline companion. No baseline packets were lost. Keep the new companion offline.**

## Alignment diagnosis and correction

The initial2.10743-second sample contained only29shared Stream1090/stock packets. Their offsets were already stable (-1631to-1628ticks), but the comparison required at least100anchors. This was inadequate calibration coverage, not evidence of an unstable Stream1090 clock. The parser and production Stream1090 service were not changed.

The repaired offline workflow combines six original, immutable RF archives that were globally reserved for evaluation before training. It keeps the minimum100anchors, original MAD bound and sample-clock guards, and additionally requires every archive's measured offset to agree with the shared clock within24ticks. No artificial payload matches, forced offset, relaxed threshold or model tuning was used.

Expanded replay:256closed RF groups, **{base['rf_seconds']:.5f}RFseconds**, {base['effective_rf_seconds']:.5f}seconds after1msedge trimming at each end. One incomplete latest burst is excluded. Stream1090 supplies **163shared anchors**, medianoffset **-1629ticks (-135.75us at12MHz)**, globalMAD0ticks. Per-archive anchors26/27/38/28/15/29, all median-1629ticks and MAD0–1tick. Source/frame clocks and the companion hash stay fixed. All three Mac runs and all three Pi runs have identical accepted packet/timestamp signatures, distance bins and losses.

## Full enabled baseline and packet recovery

Current enabled methods: stock, energy, restricted CRC computation, timing, soft, matched, coherent with pair retry, original-first three-model neural cascade, and Stream1090. Broad-CRC outputs remain quarantined and do not count as feeder detections. Sequence, acquisition, pulse, header and SIC remain disabled. The prior best October29DSP companion is tested as a separate additional baseline, not silently counted as live.

The baseline is refreshed to current source/native policy: the Mac C coherent and pair kernels were rebuilt from copied live source, while Pi replay uses copies of the actual installed shared libraries and Stream1090 executable. Frozen candidate SHA256: {base['candidate_sha256']}. No retraining occurred in this validation.

Recovered extras beyond stock:

| Distance, nm | Current pipeline extras | New companion beyond current | New companion beyond previous best union |
|---|---:|---:|---:|
{rows}
| **All** | **192** | **0** | **0** |

Only one aircraft has quality-confirmed stock range beyond180nm in this RF, and the current pipeline already recovers two extras in180–200nm. There are no confirmed200+nm opportunities here. The supplied training experiment's two additional distant test-window reconstructions are not new field detections and cannot be added to this table. Original stock/valid outputs retain priority; raw baseline losses and additive union losses are zero on both machines.

Comparison masks cover the full current replay, the previous best replay, original recorded stock, actual unified relay output and conservative recorded provisional method annotations. Compact references retain exact multiplicity for1206stock and1410unified frame instances inside measured RF;2833causal-address queries agree with the originals. Reference compaction is a replay memory optimization, not payload deduplication or a change to production. Annotations remain best-effort and are not claimed to be a complete authoritative acceptance ledger or supervised labels.

## CPU, median of three identical-RF passes

CPU-seconds consumed per RF-second, summed serial algorithm replay:

| Bundle | Mac | Pi |
|---|---:|---:|
{costrows}

The new companion inference costs **{cpu['pi']['incremental_candidate_inference_cpu_per_rf_second']['median']:.4f}CPU-seconds/RF-second on Pi** (range{cpu['pi']['incremental_candidate_inference_cpu_per_rf_second']['min']:.4f}–{cpu['pi']['incremental_candidate_inference_cpu_per_rf_second']['max']:.4f}). That is approximately3.3%of one core, or0.82%of four cores, for this inference step alone after the previous-best cascade; roughly4.4%of the measured production algorithm CPU. Mac incremental inference median is0.0061CPU-seconds/RF-second.

Replay includes separate serial frontend work and launching Stream1090 for each short clip. The production shared ring, live scheduling, admission, statistics and transport overhead are not modeled by this CPU sum. Differences of small bundle timings include warmup/cache/order noise, so a lower Mac median for the previous-best bundle is not an optimization claim. These are not electrical-power measurements. With zero unique additions, no beneficial CPU-per-additional-detection ratio is established.

## Controls, protected execution and preservation

Six Stream1090 parser/comparison tests pass. Frozen training controls are retained: zero unexplained valid outputs in clean/noise checks,20,000noise windows per model, known secondary-interferer outputs explicitly accounted for, and zero exported packet/bit differences. All original waveform/source/model/reservation manifests are private and unchanged. The RF does not overlap any new training interval and is evaluation-only; it predates candidate freeze and is not post-freeze prospective evidence.

Pi replay ran only in an owned tmpfs directory using nice19, core3, CPUQuota35%, requested MemoryMax1G and a900-second finite unit.93health samples passed. Observed replay high-water RSS was191248KiB; the kernel did not expose MemoryCurrent, so MemoryMax enforcement is not claimed. The first cleanup stopped on a root-owned Python cache; remaining owned files were reverified against durable Mac backups and removed with established sudo. No persistent archives were removed during validation.

Protected PIDs, sources/libraries/models, configurations, method switches, gain38.6dB, capture cap5,000,000,000bytes and SDR loss/drop counters match. FR24 remained connected directly to stock30005 with valid timing. The24-hour trial's deadline remains4November18:10Berlin. No SDR opening, mirror use, service restart, flush, pipeline routing change or candidate deployment occurred.

All results and native binaries were checksum-copied back before temporary cleanup. Private results: results/companion-validation-20261104; RF/runtime/input and result TARs: data/transfer/companion-validation-20261104. The existing validated companions remain retained. More untouched distant RF with complete references is required before claiming reception improvement.
'''
# Normalize units/spacing in the narrative without changing numbers.
for x,y in [('initial2.10743','initial 2.10743'),('only29shared','only 29 shared'),('-1631to-1628ticks','-1631 to -1628 ticks'),('least100anchors','least 100 anchors'),('minimum100anchors','minimum 100 anchors'),('within24ticks','within 24 ticks'),('replay:256closed','replay: 256 closed'),('RFseconds',' RF seconds'),('after1msedge','after 1 ms edge'),('163shared','163 shared'),('medianoffset','median offset'),('globalMAD0ticks','global MAD 0 ticks'),('Per-archive anchors26','Per-archive anchors 26'),('all median-1629ticks','all median -1629 ticks'),('MAD0–1tick','MAD 0–1 tick'),('October29DSP','October 29 DSP'),('beyond180nm','beyond 180 nm'),('in180–200nm','in 180–200 nm'),('confirmed200+nm','confirmed 200+ nm'),('for1206stock and1410unified','for 1206 stock and 1410 unified'),('2833causal','2833 causal'),('CPU-seconds/RF-second',' CPU-seconds/RF-second'),('range0.','range 0.'),('3.3%of','3.3% of'),('or0.82%of','or 0.82% of'),('roughly4.4%of','roughly 4.4% of'),('is0.0061','is 0.0061'),('checks,20,000noise','checks, 20,000 noise'),('nice19, core3, CPUQuota35%','nice 19, core 3, CPUQuota 35%'),('a900-second','a 900-second'),('unit.93health','unit. 93 health'),('was191248KiB','was 191248 KiB'),('gain38.6dB','gain 38.6 dB'),('cap5,000,000,000bytes','cap 5,000,000,000 bytes'),('stock30005','stock 30005'),('The24-hour','The 24-hour'),('remains4November18:10Berlin','remains 4 November 18:10 Berlin')]:text=text.replace(x,y)
(OUT/'report.md').write_text(text);(OUT/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Companion validation: Mac and Pi</title><main style="font:17px/1.6 system-ui;max-width:1050px;margin:2em auto;padding:1em"><pre style="white-space:pre-wrap">'+html.escape(text)+'</pre></main>')
print(json.dumps({'parity':checks,'cpu':cpu,'new_extras':0,'new_far_extras':0},indent=2))
