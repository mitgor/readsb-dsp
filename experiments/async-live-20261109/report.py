from pathlib import Path
import json,hashlib,html,subprocess,urllib.request
R=Path(__file__).resolve().parents[2];D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/async-live-20261109/final');O=R/'validation/async-live-20261109';O.mkdir(parents=True,exist_ok=True)
j=json.loads((D/'observation.private.json').read_text());m=j['results'];f=json.loads((D/'final-feed.json').read_text());h=json.loads((D/'final-health.json').read_text());g=json.loads((D/'final-guard.json').read_text());assert h['rollback_active'] and not h['rollback_occurred'] and h['fr24_feed']=='connected' and not g['reasons']
summary=dict(production_asynchronous=True,SIC_enabled=False,stock_holdback_s=f['holdback_s'],dedup_history_s=f['dedup_history_s'],max_extra_age_s=f['max_extra_age_s'],fr24_connected=True,receiver_feeder_collector_adsbx_pids_unchanged=True,automatic_rollback_enabled=True,RF_cap_bytes=5000000000,observation={k:m[k] for k in ['observed_seconds','comparison_edge_seconds_excluded','stock_records','stock_missing','unique_extra_records','duplicate_extras','extras_matching_stock_within_120us','stock_socket_arrival_delta_median_s','stock_socket_arrival_delta_p95_s','cpu_core_equivalents','sample_loss_before','sample_loss_after']},guard_processing_s=g['processing_s'],tests=dict(glue_mac=9,glue_pi=9,completion_mac=2,completion_pi=2,rollback_mac=2,recorded_native_extra_parity='319/319'),limitations=['Short live transport/health check; no FR24 cloud-credit or distant-reception comparison.','Five seconds excluded at each observation edge; extra packet total applies to that interior interval.','Socket arrival delta includes local observer scheduling and can be negative for individual packets; not antenna-to-cloud latency.','Startup expired 46 unaligned pending batches; count remained stable after startup. One legacy grouped outbox message was rejected during cutover.','Activation briefly reconnected relay consumers and restarted only the relay and DSP coordinator.'])
(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
md=f'''# Asynchronous relay enabled — SIC disabled

Production now forwards stock immediately and publishes validated extras independently from energy, timing, soft, matched, coherent, neural, pulse, sequence, acquisition and Stream1090. One shared five-second transmission cache removes cross-source duplicates without suppressing later repeated transmissions. Broad CRC remains quarantined; header remains off.

readsb, FR24, ADS-B Exchange and the RF collector retained their process IDs. The DSP coordinator and relay restarted for cutover; a relay-only restart then applied burst-queue hardening. Consumers briefly reconnected. Gain remains 38.6 dB; models, native libraries and collection policy are unchanged. RF cap remains 5,000,000,000 bytes. CRC RAM was saved by the coordinator's ordinary shutdown; no recorder flush or archive deletion was forced.

## Live verification

| Check | Result |
|---|---:|
| Observation duration | {m['observed_seconds']:.1f} s |
| Stock records compared | {m['stock_records']:,} |
| Missing stock records | {m['stock_missing']} |
| Additional output records | {m['unique_extra_records']:,} |
| Duplicate extras | {m['duplicate_extras']} |
| Extras also present in stock within 120 µs | {m['extras_matching_stock_within_120us']} |
| Median stock socket arrival difference | {m['stock_socket_arrival_delta_median_s']*1000:.1f} ms |
| p95 stock socket arrival difference | {m['stock_socket_arrival_delta_p95_s']*1000:.1f} ms |
| DSP coordinator plus workers | {m['cpu_core_equivalents']['adsb-rescue-shadow']:.2f} CPU s/s |
| Relay | {m['cpu_core_equivalents']['adsb-rescue-feed']:.2f} CPU s/s |
| Current processing safety proxy | {g['processing_s']:.2f} s, below 2.7 s threshold |
| Stock sample-loss increase | {m['sample_loss_after']-m['sample_loss_before']} |

The socket comparison excludes five seconds at each RF edge. CPU is measured during this live traffic interval, not an idle-host language benchmark, total board power or a paired CPU saving claim. Stock timing is a local socket observation, not RF-to-FR24-cloud delay. Stock received/relayed byte totals also match in the running relay. Each already-received TCP chunk is enqueued together, without a timer, preventing a burst from filling client queues before writers run. All ten enabled producer methods have relayed packets.

The deployable relay retained 319/319 recorded native-test extras with byte-identical stock and no duplicates before cutover. Nine glue and two completion tests passed on both Mac and Pi; two rollback tests passed on Mac. These are integration checks, not prospective distant-range validation. Forty-six pending admission batches expired while initial alignment warmed up; this count stabilized. One old-format grouped message was rejected during cutover.

## Rollback

The persistent ten-second guard is enabled and healthy. It checks feeder/stock freshness, method switches, collection cap/errors, sample loss, producer/cache overflow, late-stock duplicate races, protected processes and the three-second budget with a 300 ms margin. It restores the saved previous profile and entrypoints if unhealthy, without overwriting unrelated human changes. Existing stock fallback/automatic DSP routing recovery remains enabled.

Manual rollback on the Pi:

```sh
sudo python3 /var/lib/adsb-async-live-20261109/guard.py --restore
```

Private checksum-verified evidence, configuration backups and status snapshots are preserved on the Mac. No raw RF, receiver coordinates or credentials are published here.
'''
(O/'report.md').write_text(md);(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Asynchronous relay activation</title><style>body{font:17px/1.5 system-ui;background:#101b29;color:#e2ebf4;max-width:1000px;margin:32px auto;padding:20px}pre{white-space:pre-wrap;font:inherit}</style><pre>'+html.escape(md)+'</pre>')
remote='/usr/share/adsb-rescue/async-live-20261109';subprocess.run(['ssh','adsb-rpi','sudo','mkdir','-p',remote],check=True);pub={}
for n in ['report.html','summary.json']:
 raw=(O/n).read_bytes();subprocess.run(['ssh','adsb-rpi','sudo','tee',remote+'/'+n],input=raw,stdout=subprocess.DEVNULL,check=True);sha=hashlib.sha256(raw).hexdigest();assert hashlib.sha256(urllib.request.urlopen('http://192.168.2.195/neural-rescue/async-live-20261109/'+n).read()).hexdigest()==sha;pub[n]=sha
(O/'publication.json').write_text(json.dumps(pub,indent=2)+'\n');print(json.dumps(summary))
