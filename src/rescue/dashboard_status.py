"""Small dashboard view; full RF/research status remains at status.json."""
FIELDS=('updated_unix','started_unix','health','counts','distance','method_metrics',
 'method_switches','pipeline_methods','stream1090','workers','capture_transport',
 'input','archive','logging_enabled','async_output','cpu_budget')
def compact_status(status):
    return {key:status[key] for key in FIELDS if key in status}
