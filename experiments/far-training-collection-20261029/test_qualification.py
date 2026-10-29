"""One real RF/stock payload end-to-end fixture; synthetic range, never training data."""
import json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from rescue.far_capture import Recorder,CORRECTION,wire
from rescue.far_training import FarTraining
from rescue.merge import parse_readsb
def main():
 D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/data/transfer/retrain-companion-20261029/prepared');binary=Path('/Users/mit/Documents/Codex/2026-09-30/i-have-a-flightradar24-service-on/work/adsb-neural/readsb-reference/readsb');case=next(c for c in json.loads((D/'cases.json').read_text()) if c['holdout'] and c['rf_seconds']>1);source=D/case['file'];cmd=[str(binary),'--device-type','ifile','--ifile',str(source),'--iformat','UC8','--raw','--mlat','--no-fix','--no-fix-df'];process=subprocess.run(cmd,capture_output=True,text=True,check=True);frame=next(f for f in parse_readsb(process.stdout) if len(f['message_hex'])==28 and f['message_hex'].startswith('8d') and .01<f['seconds']<case['rf_seconds']-.01)
 with tempfile.TemporaryDirectory(prefix='adsb-training-fixture-') as temp:
  temp=Path(temp);rec=Recorder(temp/'captures');rec.cfg['continuous_capture']=False;rec.training=FarTraining(rec);rec.iq(case['epoch'],case['sample_start'],case['unix'],source.read_bytes());event=case['unix']+frame['seconds'];rec.positions[frame['message_hex'][2:8]]=[(event-1,190.,dict(available_unix=event-1,nic=8,nac_p=9,mlat_fields=[],tisb_fields=[],test_fixture_range=True))];tick=case['sample_start']*5+round(frame['seconds']*12e6);row=dict(message_hex=frame['message_hex'],ticks_12mhz=tick+CORRECTION,signal_byte=30,kind=51);row['wire_hex']=wire(row).hex();rec.frame(row);rec.drain();assert rec.training.count['saved']==1;rec.flush(force=True);rec.writer.join();archive=next((temp/'captures').glob('*.tar'));(temp/'raw').mkdir();out=temp/'qualified.jsonl.gz';result=subprocess.run([sys.executable,str(ROOT/'scripts/collection/qualify_far_training.py'),str(archive),'--readsb',str(binary),'--raw-root',str(temp/'raw'),'--output',str(out)],capture_output=True,text=True,check=True);report=json.loads(result.stdout);assert report['counts']['qualified']==1;print(json.dumps(dict(test='Original real RF and independently decoded same-transmission stock; synthetic 190nm metadata; fixture destroyed and never used for training',qualified=1,archive_format='far-capture-v3',readsb_sha256=report.get('readsb_sha256')),indent=2))

if __name__=='__main__':main()
