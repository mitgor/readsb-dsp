"""Hold out every independently collected validation RF interval from future training."""
import hashlib,json
from collections import defaultdict
from pathlib import Path

def load_reservations(raw_root):
    intervals=defaultdict(list);manifests=[]
    for path in sorted(Path(raw_root).glob('long-validation-*/reserved-intervals.json')):
        blob=path.read_bytes();row=json.loads(blob)
        if row.get('schema')!='long-validation-v1' or row.get('evaluation_only') is not True:raise ValueError('Invalid validation reservation manifest')
        for capture in row['captures']:
            epoch=capture['epoch'];start=capture['sample_start'];count=capture['sample_count']
            if not all(type(x) is int for x in (epoch,start,count)) or epoch<=0 or start<0 or not 0<count<=36000000:raise ValueError('Invalid validation sample interval')
            intervals[epoch].append((start,start+count))
        manifests.append(dict(file=str(path),sha256=hashlib.sha256(blob).hexdigest(),intervals=len(row['captures'])))
    return intervals,manifests
