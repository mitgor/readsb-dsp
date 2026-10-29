"""Live shadow defaults. Changes require only a shadow-worker restart."""
import json
DEFAULTS=dict(energy=True,crc=True,timing=True,soft=True,matched=True,coherent=False,header=False,sic=False,neural=False,pulse=False)
def settings(path=None):
    supplied=json.loads(path.read_text()) if path and path.exists() else {}
    if not isinstance(supplied,dict) or set(supplied)-set(DEFAULTS) or any(type(v) is not bool for v in supplied.values()):
        raise ValueError('Pipeline config requires known method names and boolean values')
    result={**DEFAULTS,**supplied}
    if not result['energy']:raise ValueError('Energy decoding is required for sample-clock alignment')
    return result
