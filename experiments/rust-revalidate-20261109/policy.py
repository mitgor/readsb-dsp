"""Pure progress policy: alignment is not a computation heartbeat."""
import copy
def assess(s,previous,now):
 previous=previous or {};same=previous.get('snapshot',{}).get('started_unix')==s['started_unix'];old=previous.get('snapshot',{}) if same else {};clocks={}
 for name,key in [('work','completed'),('iq','iq_packets'),('alignment','aligned')]:
  changed=not same or s[key]>old.get(key,-1);clocks['last_'+name+'_progress']=now if changed else previous.get('last_'+name+'_progress',now)
 reasons=[];notes=[];grace=now-s['started_unix']<60
 if not grace:
  if now-s['updated_unix']>25:reasons.append('stale_coordinator_status')
  if not s['threads_alive']:reasons.append('input_thread_failure')
  if now-clocks['last_work_progress']>45:reasons.append('worker_completion_stall' if now-clocks['last_iq_progress']<15 else 'upstream_iq_input_stall')
  if now-clocks['last_alignment_progress']>45:notes.append('alignment_not_advancing')
  if s['pending']>4:reasons.append('worker_queue_overflow')
  if s['processing_s']>=2.7:reasons.append('three_second_budget_margin')
  if same and s['receiver_pid']==old.get('receiver_pid') and any(s['samples'][k]>old.get('samples',{}).get(k,s['samples'][k]) for k in s['samples']):reasons.append('stock_sample_loss_increased')
 if now-s['feed_updated_unix']>10 or not s['stock_connected'] or not s['fr24_routed']:reasons.append('relay_unhealthy')
 if not s['asynchronous'] or s['holdback_s']!=0:reasons.append('unexpected_relay_mode')
 if not s['fr24_connected']:reasons.append('fr24_disconnected')
 if s['capture_error'] or s['capture_cap']!=5000000000:reasons.append('capture_unhealthy')
 if s['temperature_c']>=80:reasons.append('overtemperature')
 if not all(s['protected_pids'].values()):reasons.append('protected_service_not_running')
 if s['late_stock_duplicates'] or s['cache_evictions'] or s['outbox_overflow']:reasons.append('async_transport_fault')
 return dict(**clocks,snapshot=copy.deepcopy(s),reasons=reasons,notes=notes,startup_grace=grace)
