"""Bounded tmpfs-only batch mirror and exact-window DSP comparison ledger."""
import json,os,time
from collections import Counter
from pathlib import Path
from .streaming import Batch

class Spool:
    def __init__(self,path):
        self.path=Path(path)
        if not str(self.path).startswith('/run/') and not os.environ.get('RESCUE_TEST_TMPFS'):
            raise ValueError('IQ mirror must use /run tmpfs')
        self.count=Counter();self.path.mkdir(parents=True,exist_ok=True)
    def active(self):
        try:return time.time()-(self.path/'enabled').stat().st_mtime<5
        except OSError:return False
    def heartbeat(self):
        self.path.mkdir(parents=True,exist_ok=True);(self.path/'enabled').touch()
    def _drop(self,meta):
        for suffix in ('.uc8','.whole.uc8','.json'):(meta.parent/(meta.stem+suffix)).unlink(missing_ok=True)
    def publish(self,batch):
        if not self.active():return
        try:
            pending=sorted(self.path.glob('batch-*.json'))
            while len(pending)>=20:self._drop(pending.pop(0));self.count['batches_shed']+=1
            # Clean only this transport's orphaned files after interrupted writes.
            for item in self.path.glob('batch-*'):
                try:
                    if time.time()-item.stat().st_mtime>10:item.unlink(missing_ok=True)
                except FileNotFoundError:pass
            stem=f'batch-{time.monotonic_ns():020d}'
            (self.path/(stem+'.uc8')).write_bytes(batch.raw)
            if batch.whole_raw is not None:(self.path/(stem+'.whole.uc8')).write_bytes(batch.whole_raw)
            record={k:getattr(batch,k) for k in ('epoch','first','wall','bounds','raw_start','queued')}
            record['whole']=batch.whole_raw is not None
            tmp=self.path/(stem+'.tmp');tmp.write_text(json.dumps(record));tmp.replace(self.path/(stem+'.json'))
            self.count['published_batches']+=1
        except OSError:self.count['publish_errors']+=1 # Never block or fail DSP.
    def take(self):
        pending=sorted(self.path.glob('batch-*.json'))
        for meta in pending:
            try:
                row=json.loads(meta.read_text());stem=meta.stem
                raw=(self.path/(stem+'.uc8')).read_bytes()
                whole=(self.path/(stem+'.whole.uc8')).read_bytes() if row.pop('whole') else None
                row['bounds']=tuple(row['bounds']);batch=Batch(**row,raw=raw,whole_raw=whole)
            except (OSError,ValueError,TypeError):self.count['read_errors']+=1;continue
            finally:self._drop(meta)
            self.count['received_batches']+=1;return batch
        return None
    def base_path(self,epoch,first):return self.path/f'base-{epoch}-{first}.json'
    def publish_base(self,epoch,first,record):
        if not self.active():return
        try:
            path=self.base_path(epoch,first);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,separators=(',',':')));tmp.replace(path)
            old=sorted(self.path.glob('base-*.json'),key=lambda p:p.stat().st_mtime)
            for p in old[:-40]:p.unlink(missing_ok=True)
        except OSError:self.count['base_publish_errors']+=1
    def base(self,epoch,first):
        try:return json.loads(self.base_path(epoch,first).read_text())
        except (OSError,ValueError):return None
