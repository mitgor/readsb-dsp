import argparse,datetime,html,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();O=a.output;s=json.loads((O/'summary.json').read_text());timeline=json.loads((O/'timeline.json').read_text())
text='''# October 27 FR24 hits drop: change and cause review

Reviewed 30 October 2026. All narrative times below are **Europe/Berlin (CET, UTC+1)**. The saved timeline also contains UTC. Working receiver, feeder, routing, decoder, gain and collection were unchanged during this review.

## Assessment

**We made a material delivery-path change on October 27: restored FR24 from direct stock to the delayed combined stock/DSP relay. That is the main local candidate, but the evidence does not yet establish it as the cause.** The cloud drop occurs after the return, with no matching collapse in local reception or feeder input. Upload filtering, persistent source-quality treatment and cloud accounting remain possible downstream mechanisms. Do not assume an independent FR24 failure, nor blame a specific DSP method without the controlled cloud comparison.

The first very low chart point is **14:00 Berlin (13:00 UTC)**: 33,071 hits and 5,130 positions. The preceding 13:00 Berlin point is already depressed: 477,695 hits and 81,459 positions. Chart labels do not establish the exact onset minute or interval start/end.

## What changed on October 27

| Berlin time | Change | Relevance and evidence |
|---|---|---|
| Around 01:29 | Existing relay failed on a quiet/read timeout; fallback selected direct stock | Contemporaneous capture/recovery documentation. This left the morning feed on stock; not the afternoon collapse itself. |
| 11:09–11:15 | Dashboard switches, per-method CPU measurement and new bounded far-range RF recorder | First web preflight failed and was restored. Final DSP runtime started 11:14:52. Existing readsb and FR24 PIDs remained unchanged. Initial recording threshold 230 nm, 5 GB cap, 12-hour saves. Capture traffic does not enter FR24. |
| 12:14 | First relay-repair attempt | Readiness assertion failed; activation rolled back to direct stock. Backup timestamp is an activation-start proxy, not proof of exact route-switch completion. |
| **12:16** | **Successful return: stock 30005 -> combined 31005** | Main delivery-path change (`03c69d5`); original stock plus validated energy/timing/soft/matched/coherent extras and existing three-second holdback. Neural, Broad CRC, header/SIC remained excluded. Sequence/acquisition switches remained off. |
| 12:18–12:22 | Deliberate relay crash, sustained-stop and restart tests | Several brief relay interruptions and FR24 reconnects; automatic stock fallback/combined return verified. Relevant to a possible persistent source-selection change. They do not establish a continuing outage. |
| Around 12:23–12:24 | Contemporaneous steady relay audit | 26,484 original stock records checked, zero missing, 853 extra records. Does not cover interrupted connections or every later minute. |
| 12:52 | Capture threshold 230 -> 200 nm | Recorder-only change (`6628a8f`). Readsb, DSP, relay and FR24 PIDs unchanged. No gain/feed change. |
| **13:00–14:00 chart labels** | **Cloud statistics collapse** | Exact onset within/between buckets unresolved. The 14:00 point is already extremely low. |
| Around 14:28 | Local-track holdover/external RF capture triggers | Recorder-only (`b7fbd2c`); same feeder/decoder PIDs. Its timing is a weaker fit than relay return: earlier chart point was already depressed. Unresolved bucket semantics prevent assigning an exact onset relative to this change. |
| 16:12–16:14 | Saved RF/Beast transfer and verified Pi deletion | Occurs well after the initial collapse; archive offload does not change live decoding. |
| Around 16:50 | Synchronized stock/DSP journals for RF bursts | Recorder-only (`3076281`), after the initial collapse. |
| Later afternoon/evening | Offline neural training; isolated C pulse and coherent experiments | These candidate outputs were not added to FR24. Neural cascade deployment, Rust ports and Stream1090 integration occurred later and cannot initiate this October 27 event. |

Git commit timestamps are not deployment timestamps. The machine-readable timeline uses saved activation/runtime observations and explicitly labels backup-name timestamp proxies.

## New checks in this review

**Configuration:** compared six incident-era archived feeder configurations against the October 25 stock backup. Every non-host byte is identical. Only input host/port differs in later combined-feed copies. Sharing key, receiver type (`beast-tcp`), MLAT settings and other local feeder options are unchanged. This does not prove the server-downloaded configuration was unchanged: it is a separate configuration channel.

**Historical health:** gain is 38.6 dB in all available 10:00–15:00 UTC samples. Hourly average CPU idle is approximately 49–61%, with almost no I/O wait. Temperature averages are roughly 57.6–63.7 C. Mean signal/noise change with traffic but show no persistent reception collapse. Wi-Fi transmit errors and transmit drops are zero in those RRD samples; receive drops are around one/second before and after, without a corresponding step. These averages cannot exclude short stalls, one-core bottlenecks, transient interference or WAN/UDP loss beyond the host.

**Traffic-normalized change:** comparing 05:00–11:00 UTC with 13:00–21:00 UTC, the FR24-hit/local-message index falls from 0.2810 to 0.02190 (**92.2%**); the FR24-position/local-position index falls from 0.6294 to 0.03453 (**94.5%**). Counters have different definitions: these are change indices, not measured packet-loss fractions. A simple two-level log-index fit selects the 13:00 UTC chart point for both metrics; it is descriptive, not a causal test or sub-hour timing estimate.

**Feeder input:** the same FR24 process received 3,192,291 additional messages between 11:52:04 and 13:28:04 UTC, approximately 554/s. Both snapshots report connected links. A local receiver-input stoppage lasting the entire interval is incompatible with that progression; intermittent loss is not excluded.

**Thirty-second uploads:** an already-saved October 28 trace contains 314 send events, median spacing 30.0146 s, starting 12:32:53 UTC. Current startup logs show `30s/30s`, mode 1 and filtering enabled. No retained October 27 uploader configuration proves a transition from five to thirty seconds. That transition remains an important question, not an established change we made. Local INI files contain no send-interval change.

**Pre-existing stock quality warning (BEL7PJ):** the October 26 stock capture contained 2,330 CRC-valid DF17 records for the audited aircraft. Its recorded positions differed from the user-exported FR24 track by about 212–245 nm, and the snapshots recorded NIC/NACp zero. Independent CPR decoding matched the local snapshots within 0.1 nm for 568 of 570 compared points. Thus most of the displacement is represented in the saved stock bits, rather than explained by a plotting-only error or necessarily by our additional DSP. This does not establish physical ground truth: the external track lacks sensor provenance, and original stock pre-output error correction cannot be excluded. It establishes a reason to investigate stock source quality as well as extras. The discrepancy predates the drop, and no FR24 penalty is proven. Direct stock retains these stock messages, so failure to recover would not by itself distinguish persistent backend state from questionable stock input.

## Competing explanations

| Explanation | Assessment |
|---|---|
| Restoring combined feeding affected freshness, data quality or subsequent overlap selection | **Leading local candidate.** Correct temporal order; adds approximately three seconds versus direct stock and adds DSP packets. But the delay already existed on the successful October 26 feed. Existing packet audits and short direct-stock test do not demonstrate the mechanism. |
| FR24 upload suppression/source selection or statistics/configuration changed | **Leading downstream possibilities.** Strong local/cloud divergence and explicit overlap-filter messages. Could be independent, or a response to our input. Backend history is required to distinguish them. |
| Gain, antenna/SDR reception or sustained whole-host CPU overload | **Poor fit for the magnitude and persistence.** Fixed gain, healthy message/position rates, spare CPU and feeder input progress. Does not eliminate every transient RF issue. |
| Capture threshold/holdover/data offload | **Weak fit.** Recorder-only code; protected service PIDs unchanged, no host saturation. Later offload/journal changes are too late to initiate the collapse. |
| Neural/Rust/new pulse decoder bug introduced that day | **Not supported as the initiating change.** Neural forwarding was off; pulse experiments were quarantined; the cited later deployments were not active at onset. Existing classical DSP extras still require causal testing. |
| New 30s uploader setting on October 27 | **Unknown.** Thirty-second cadence is verified after the drop; its earlier value is missing. Do not claim it caused the drop or was unchanged before onset. |
| Wrong local sharing key/receiver mode/MLAT setting | **No change found in archived incident configurations.** Another remote device using the same key, or a server-side receiver configuration change, cannot be excluded from local evidence. |

The previously completed partial forensic review found 95,759 stock/98,599 actual relay records in declared-complete burst cores, zero missing stock, and 2,840 CRC-valid extras without flagged coarse track discrepancies. That reduces common transport/error concerns but is sampled, partly later data and not independent waveform truth for every historical extra.

The October 30 combined/direct-stock/combined comparison found no sustained local send/filter recovery during its short direct-stock condition. Startup increases settled after about 90 seconds. This argues against a simple immediate local-parser failure, but cannot rule out persistent server quality state or slow cloud-statistics recovery. Local `sent X,Y` fields and overlap counts must not be treated as packet totals or a documented filtering percentage.

## Research and source limits

FR24's official T-Feed manual discusses its own decoding/validation pipeline and third-party decoder consistency. This supports checking data freshness/quality, not asserting an undocumented account penalty. Firsthand forum logs demonstrate continuous receiver input coexisting with low reported hits; another firsthand report documents a 30s/30s configuration. These establish possible behavior, not the cause in this account. Community moderator interpretations of overlap filtering are not vendor confirmation of statistics accounting.

- Official manual: https://www.flightradar24.com/blog/wp-content/uploads/2023/02/fr24feed-manual.pdf
- Firsthand 30-second configuration: https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/225434-send-interval-question
- Firsthand input/statistics mismatch: https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/223825-dump1090-collecting-messages-flightradar24-com-reporting-online-no-data/page2

The original October 27 journal and per-minute feeder upload configuration are not retained. Browser access to the existing signed-in FR24 tab failed during this review; no fresh cloud result is inferred. All historical cloud values come from the previously verified chart extraction, whose sums equal daily totals.

## How to identify the cause next

1. Finish the already-running 12-hour **direct-stock** cloud comparison at 20:00 Berlin, retaining its automatic restoration and protected pipeline. Compare complete cloud hours against local traffic and surrounding days. Do not decide from startup bursts or an unfinished hour.
2. If direct stock recovers materially, a complete-hour **stock-only plus the same three-second delay** control separates relay freshness from DSP extras. If delayed stock remains healthy while combined drops, test admitted extras by source under the existing rollback controls. First review the completed baseline; no new live condition is started by this report.
3. If direct stock does not recover, relay removal is not an immediate cure. Ask FR24 to check historical source-selection/quality, overlap suppression, duplicate-key sessions, stats aggregation and downloaded sender configuration around **October 27 11:00–14:00 UTC**, including any mode/send-interval changes and the previously recorded stock position inconsistency for ICAO 44ce62 on October 26. Persistent state could still have been triggered locally; do not dismiss it.
4. Independently finish the low-latency prototype's complete-pipeline fresh-RF and isolated-FR24 validation. Avoid combining its activation with the causal comparison, which would change multiple factors at once.

No FR24 support message was sent. No service restart, routing change, model/method/gain change or recorder flush was performed in this review.
'''
(O/'report.md').write_text(text)
rows=''.join('<tr><td>'+html.escape(r['utc'])+'</td><td>'+html.escape(r['berlin'])+'</td><td>'+html.escape(r['action'])+'</td><td>'+html.escape(r['evidence_kind'])+'</td></tr>' for r in timeline)
(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>October 27 FR24 cause review</title><main style="max-width:1150px;margin:2em auto;padding:20px;font:17px/1.6 system-ui"><pre style="white-space:pre-wrap">'+html.escape(text)+'</pre><h2>Exact evidence timeline</h2><table border="1" cellspacing="0" cellpadding="8"><tr><th>UTC</th><th>Berlin</th><th>Observation</th><th>Evidence</th></tr>'+rows+'</table></main>')
print('Cause report generated.')
