"""Native Stream1090 with unchanged admission and same-window executable fallback."""
import ctypes
import hashlib
import json
import os
import resource
import subprocess
import time
from collections import Counter
from pathlib import Path
from .stream1090_compare import compare, parse_avr, valid_df17
from .streaming import CORE, HALO, TOTAL

class Event(ctypes.Structure):
    _fields_=[('ticks',ctypes.c_int64),('message',ctypes.c_uint8*14)]

class Stream1090Method:
    def __init__(self,binary,timeout_s=1.0,backend_config='/etc/default/adsb-stream1090-native.json',fallback_marker='/run/adsb-rescue/stream1090-native-fallback.json'):
        self.binary=Path(binary)
        if not self.binary.is_file() or not os.access(self.binary,os.X_OK):
            raise FileNotFoundError(f'Stream1090 binary is unavailable: {binary}')
        self.timeout_s=timeout_s;self.config_path=Path(backend_config);self.marker=Path(fallback_marker)
        self.count=Counter();self.last_alignment={};self.last_error=None;self.last_wall_s=0.
        self.library=None;self.library_sha256=None;self.events=(Event*16384)()
        self.config_key=None;self.disabled_key=None;self.native_error=None
        self.backend='executable';self.requested_backend='executable'

    def _disable(self,reason):
        self.disabled_key=self.config_key;self.native_error=str(reason);self.count['native_failures']+=1
        try:
            tmp=self.marker.with_name(self.marker.name+'.tmp')
            tmp.write_text(json.dumps({'unix':time.time(),'reason':self.native_error,'pid':os.getpid(),'fallback':'executable'}))
            tmp.replace(self.marker)
        except OSError:self.count['fallback_marker_errors']+=1

    def _select(self):
        if not self.config_path.exists():
            self.requested_backend='executable';return False
        try:
            data=self.config_path.read_bytes();key=hashlib.sha256(data).hexdigest();self.config_key=key
            cfg=json.loads(data);self.requested_backend=cfg['backend']
            if cfg['backend']=='executable':return False
            if cfg['backend']!='native':raise ValueError('Unknown Stream1090 backend')
            if self.disabled_key==key:return False
            if self.library is None:
                p=Path(cfg['library']);digest=hashlib.sha256(p.read_bytes()).hexdigest()
                if digest!=cfg['library_sha256']:raise ValueError('Native library checksum mismatch')
                lib=ctypes.CDLL(str(p));lib.stream1090_native_event_size.restype=ctypes.c_uint32
                if lib.stream1090_native_event_size()!=ctypes.sizeof(Event):raise ValueError('Native event ABI mismatch')
                fn=lib.stream1090_native_decode_timeout_us
                fn.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64,ctypes.POINTER(Event),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32];fn.restype=ctypes.c_int
                self.library=lib;self.library_sha256=digest
            elif cfg['library_sha256']!=self.library_sha256:
                raise ValueError('Library change requires guarded service activation')
            return True
        except (OSError,ValueError,KeyError,TypeError,AttributeError) as e:
            self._disable('configuration/load: '+str(e));return False

    def _executable(self,raw,first,remaining):
        self.backend='executable';self.count['executable_calls']+=1
        r=subprocess.run([str(self.binary),'-s','2.4','-u','8'],input=raw,capture_output=True,timeout=remaining,check=True)
        return list(parse_avr(r.stdout,first))

    def _native(self,raw,first):
        n=ctypes.c_uint32();self.count['native_calls']+=1
        # Reserve half the original timeout for same-window executable fallback.
        budget=max(1,int(min(.5,self.timeout_s*.5)*1e6))
        rc=self.library.stream1090_native_decode_timeout_us(raw,TOTAL,first,self.events,len(self.events),ctypes.byref(n),budget)
        if rc or n.value>len(self.events):raise ValueError(f'Native status {rc}, count {n.value}')
        rows=[]
        for i in range(n.value):
            e=self.events[i];msg=bytes(e.message).hex();t=int(e.ticks)
            if not valid_df17(msg) or not first*5<=t<first*5+(TOTAL+20000)*5:
                raise ValueError('Invalid native candidate')
            rows.append((t,msg))
        self.backend='native';self.count['native_successes']+=1;return rows

    def decode(self,raw,first,frames):
        if len(raw)!=TOTAL*2:
            self.count['invalid_rf_windows']+=1;return [],0.
        start=(first+HALO)*5;end=start+CORE*5
        before=resource.getrusage(resource.RUSAGE_CHILDREN);cpu=time.thread_time();began=time.monotonic()
        try:
            if self._select():
                try:candidates=self._native(raw,first)
                except (OSError,ValueError,TypeError,ctypes.ArgumentError) as e:
                    self._disable('decode: '+str(e));self.count['same_window_fallbacks']+=1
                    candidates=self._executable(raw,first,max(.01,self.timeout_s-(time.monotonic()-began)))
            else:candidates=self._executable(raw,first,self.timeout_s)
            stock=[(r['ticks'],r['message_hex']) for r in frames if start-60000<=r['ticks']<end+60000]
            alignment,extras=compare(candidates,stock);self.last_alignment=alignment
            self.count['processed_rf_seconds']+=1;self.count['raw_df17']+=len(candidates)
            if not alignment['aligned']:
                self.count['unaligned_rf_seconds']+=1;return [],self._cpu_since(before,cpu)
            self.count['aligned_rf_seconds']+=1
            rows=[{'source':'stream1090','message_hex':m,'ticks':t} for t,m in extras if start<=t<end]
            self.count['outside_core']+=len(extras)-len(rows);self.count['calibrated_nonstock_candidates']+=len(rows)
            self.last_error=None;return rows,self._cpu_since(before,cpu)
        except (OSError,subprocess.SubprocessError,ValueError) as e:
            self.last_error=repr(e);self.count['decoder_errors']+=1;return [],self._cpu_since(before,cpu)
        finally:self.last_wall_s=time.monotonic()-began

    @staticmethod
    def _cpu_since(before,cpu):
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        return max(0.,after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime)+max(0.,time.thread_time()-cpu)

    def report(self):
        return dict(enabled=True,binary=str(self.binary),backend=self.backend,requested_backend=self.requested_backend,
                    library_sha256=self.library_sha256,native_disabled_reason=self.native_error,
                    counts=dict(self.count),last_alignment=self.last_alignment,last_error=self.last_error,
                    last_wall_s=self.last_wall_s,timeout_s=self.timeout_s,cpu_scope='calling thread plus decoder child CPU')
