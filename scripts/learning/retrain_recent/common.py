"""Frozen local experiment paths; never opens a receiver connection."""
import sys,json,hashlib,os
from pathlib import Path
ROOT=Path(os.environ.get("ADSB_NEURAL_DATA_ROOT",str(Path(__file__).resolve().parents[3]))).resolve()
OUT=ROOT/'results/retrain-companion-20261029';WORK=ROOT/'data/transfer/retrain-companion-20261029';RUNTIME=WORK/'runtime';RAW=ROOT/'data/raw/retrain-recent-20261029'
sys.path[:0]=[str(RUNTIME/'src'),str(ROOT/'reference')]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,indent=2,default=lambda x:x.item() if hasattr(x,"item") else str(x))+'\n')
