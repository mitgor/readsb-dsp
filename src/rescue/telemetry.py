"""Distance attribution and bounded, twelve-hour training archives."""
import base64,gzip,hashlib,json,math,os,time,random,ctypes
from collections import Counter,defaultdict
from pathlib import Path
BINS=('0-50','50-100','100-150','150-180','180-200','200-250','250+','unknown')
def distance_nm(lat,lon,origin):
    a,b,c,d=map(math.radians,(*origin,lat,lon))
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 3440.065*2*math.asin(min(1,math.sqrt(h)))
def distance_bin(distance):
    if distance is None or not math.isfinite(distance) or distance<0:return 'unknown'
    for edge,name in zip((50,100,150,180,200,250),BINS):
        if distance<edge:return name
    return '250+'
class DistanceStats:
    def __init__(self):self.bins={b:Counter() for b in BINS};self.total=Counter()
    def record(self,source,distance):
        if source not in ('stock_df17','energy_extra','timing_extra','soft_extra','matched_extra','coherent_extra','sequence_extra','acquisition_extra','pulse_extra','header_extra','sic_extra','neural_extra','crc_research_extra'):raise ValueError(source)
        self.bins[distance_bin(distance)][source]+=1;self.total[source]+=1
    def report(self):
        out={}
        for b,counts in self.bins.items():
            row={s:counts[s] for s in ('stock_df17','energy_extra','timing_extra','soft_extra','matched_extra','coherent_extra','sequence_extra','acquisition_extra','pulse_extra','header_extra','sic_extra','neural_extra','crc_research_extra')}
            row['neural_extra_percent_of_stock']=100*row['neural_extra']/row['stock_df17'] if row['stock_df17'] else None
            out[b]=row
        return dict(bins_nm=out,total=dict(self.total),denominator='CRC-valid stock DF17 in processed, aligned I/Q windows only; research CRC candidates stay separate from feeder-eligible extras; all use the same stock-only position-age rule')
class MemoryPins:
    """Reference-count locked heap pages shared by immutable compressed blobs."""
    def __init__(self):
        self.page=os.sysconf('SC_PAGESIZE');self.pages=Counter()
        self.libc=ctypes.CDLL(None,use_errno=True)
        self.libc.mlock.argtypes=[ctypes.c_void_p,ctypes.c_size_t];self.libc.mlock.restype=ctypes.c_int
        self.libc.munlock.argtypes=[ctypes.c_void_p,ctypes.c_size_t];self.libc.munlock.restype=ctypes.c_int
        self.address=ctypes.pythonapi.PyBytes_AsString;self.address.argtypes=[ctypes.py_object];self.address.restype=ctypes.c_void_p
    def addresses(self,blob):
        pointer=self.address(blob);return range(pointer//self.page*self.page,(pointer+len(blob)+self.page-1)//self.page*self.page,self.page)
    def pin(self,blob):
        touched=[]
        for page in self.addresses(blob):
            if not self.pages[page] and self.libc.mlock(page,self.page):
                for previous in touched:
                    if not self.pages[previous]:self.libc.munlock(previous,self.page)
                return False
            touched.append(page)
        for page in touched:self.pages[page]+=1
        return True
    def unpin(self,blob):
        for page in self.addresses(blob):
            self.pages[page]-=1
            if not self.pages[page]:self.libc.munlock(page,self.page);del self.pages[page]

class Archive:
    """Never flush early because RAM is full. Skip collection instead.
    No automatic deletion of existing archives; stop disk writes at retention cap.
    """
    def __init__(self,directory,ram_limit=64*1024**2,disk_limit=512*1024**2,interval=43200,lock_memory=False,enabled=True):
        self.enabled=enabled
        self.pins=MemoryPins() if lock_memory and enabled else None
        self.directory=Path(directory);self.ram_limit=ram_limit;self.disk_limit=disk_limit;self.interval=interval
        self.parts=[];self.reservoir={};self.offered=Counter();self.random=random.Random();self.bytes=0;self.skipped=Counter();self.next_flush=time.time()+interval;self.saved=0;self.last_error=None;self.files=[dict(name=p.name,bytes=p.stat().st_size) for p in sorted(self.directory.glob("batch-*.jsonl.gz"))]
    def add(self,record,raw=None):
        if not self.enabled:return False
        if raw is not None:record={**record,'iq_uc8_base64':base64.b64encode(raw).decode(),'iq_sha256':hashlib.sha256(raw).hexdigest()}
        blob=gzip.compress((json.dumps(record,separators=(',',':'))+'\n').encode(),compresslevel=3,mtime=0)
        key=None;index=None;old=0
        if record.get('record')=='training_window':
            # Algorithm R independently per provenance/distance stratum. Keep
            # late-day examples as well as early traffic, bounded at 128/stratum.
            key=(record['label_provenance'],distance_bin(record.get('distance_nm')))
            self.offered[key]+=1;rows=self.reservoir.setdefault(key,[])
            if len(rows)>=128:
                index=self.random.randrange(self.offered[key])
                if index>=128:self.skipped['reservoir_not_selected']+=1;return False
                old=len(rows[index])
        if self.bytes+len(blob)-old>self.ram_limit:self.skipped['ram_cap']+=1;return False
        if self.pins and not self.pins.pin(blob):self.skipped['memory_lock_failed']+=1;return False
        if key is not None and index is not None and self.pins:self.pins.unpin(self.reservoir[key][index])
        if key is None:self.parts.append(blob)
        elif index is None:self.reservoir[key].append(blob)
        else:self.reservoir[key][index]=blob
        self.bytes+=len(blob)-old;return True
    def flush(self,status,force=False):
        if not self.enabled:return False
        now=time.time()
        if not force and now<self.next_flush:return False
        # One task-owned batch, at most twice daily; no continuous SD I/Q.
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            summary=gzip.compress((json.dumps({'record':'statistics','status':status})+'\n').encode(),mtime=0)
            occupied=sum(p.stat().st_size for p in self.directory.glob('batch-*.jsonl.gz'))
            if occupied+self.bytes+len(summary)>self.disk_limit:
                self.last_error='archive_disk_cap';self.next_flush=now+self.interval;return False
            stamp=time.time_ns();target=self.directory/f'batch-{stamp}.jsonl.gz';temporary=target.with_suffix('.partial')
            with temporary.open('xb') as out:
                for blob in self.parts:out.write(blob)
                for rows in self.reservoir.values():
                    for blob in rows:out.write(blob)
                out.write(summary);out.flush();os.fsync(out.fileno())
            temporary.replace(target);self.files.append(dict(name=target.name,bytes=target.stat().st_size))
            if self.pins:
                for blob in self.parts:self.pins.unpin(blob)
                for rows in self.reservoir.values():
                    for blob in rows:self.pins.unpin(blob)
            self.parts.clear();self.reservoir.clear();self.offered.clear();self.bytes=0;self.saved+=1;self.last_error=None
        except OSError as e:self.last_error=str(e)
        self.next_flush=now+self.interval;return self.last_error is None
    def report(self):return dict(enabled=self.enabled,ram_lock_enabled=self.pins is not None,locked_page_bytes=len(self.pins.pages)*self.pins.page if self.pins else 0,files=list(self.files),retained_training_windows=sum(map(len,self.reservoir.values())),sampling="128-window uniform reservoir per label/distance stratum per flush interval",compressed_ram_bytes=self.bytes,ram_cap_bytes=self.ram_limit,skipped=dict(self.skipped),next_flush_unix=self.next_flush,saved_batches=self.saved,error=self.last_error)
