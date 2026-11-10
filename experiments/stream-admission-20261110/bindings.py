"""Test-only bindings; no SDR, transport, production configuration or feeder."""
import ctypes
class Event(ctypes.Structure):
    _fields_=[('ticks',ctypes.c_int64),('message',ctypes.c_uint8*14)]
class Decoder:
    def __init__(self,batch,incremental):
        self.batch=ctypes.CDLL(str(batch));self.inc=ctypes.CDLL(str(incremental));self.buf=(Event*16384)()
        f=self.batch.stream1090_native_decode_timeout_us
        f.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64,ctypes.POINTER(Event),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32];f.restype=ctypes.c_int
        self.inc.stream1090_incremental_create.argtypes=[ctypes.c_int64,ctypes.c_uint32];self.inc.stream1090_incremental_create.restype=ctypes.c_void_p
        f=self.inc.stream1090_incremental_feed;f.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64,ctypes.POINTER(Event),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32];f.restype=ctypes.c_int
        f=self.inc.stream1090_incremental_finish;f.argtypes=[ctypes.c_void_p,ctypes.POINTER(Event),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32];f.restype=ctypes.c_int
        self.inc.stream1090_incremental_destroy.argtypes=[ctypes.c_void_p];self.inc.stream1090_incremental_event_size.restype=ctypes.c_uint32
        assert self.inc.stream1090_incremental_event_size()==ctypes.sizeof(Event)
    def rows(self,n):return [(int(self.buf[i].ticks),bytes(self.buf[i].message).hex()) for i in range(n)]
    def whole(self,raw,first):
        n=ctypes.c_uint32();rc=self.batch.stream1090_native_decode_timeout_us(raw,len(raw)//2,first,self.buf,len(self.buf),ctypes.byref(n),0);assert rc==0,(rc,n.value);return self.rows(n.value)
    def begin(self,first,total):
        ctx=self.inc.stream1090_incremental_create(first,total);assert ctx;return ctx
    def feed(self,ctx,raw,first):
        n=ctypes.c_uint32();rc=self.inc.stream1090_incremental_feed(ctx,raw,len(raw)//2,first,self.buf,len(self.buf),ctypes.byref(n),0);assert rc==0,(rc,n.value);return self.rows(n.value)
    def finish(self,ctx):
        n=ctypes.c_uint32();rc=self.inc.stream1090_incremental_finish(ctx,self.buf,len(self.buf),ctypes.byref(n),0);assert rc==0,(rc,n.value);return self.rows(n.value)
    def close(self,ctx):self.inc.stream1090_incremental_destroy(ctx)
