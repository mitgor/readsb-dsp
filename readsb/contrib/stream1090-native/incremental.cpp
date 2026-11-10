/* SPDX-License-Identifier: GPL-3.0-or-later
 * Incremental finite-window adapter to pinned mgrone/stream1090.
 * Repair/trust, phase order, sample blocks and terminal EOF behavior unchanged.
 */
#include "incremental.h"
#include <chrono>
#include <cstring>
#include <memory>
#include "upstream/Global.hpp"
#include "upstream/RawInputFormat.hpp"
#include "upstream/InputReaderBase.hpp"
#include "incremental_stream.hpp"
namespace {
using S=Sampler_2_4_to_8_0_Mhz;
int64_t nowUs() {return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
struct Empty {static constexpr bool isEmpty=true;};
struct Handler {
    stream1090_native_event *out=nullptr;uint32_t cap=0,n=0,total=0;int64_t first;
    bool overflow=false;
    explicit Handler(int64_t f):first(f){}
    void bind(stream1090_native_event *p,uint32_t c) {out=p;cap=c;n=0;overflow=false;}
    void handleShort(uint64_t,uint64_t){}
    void handleLong(uint64_t at,const Bits128& frame) {
        if((frame.high()>>43)!=17)return;
        if(n==cap || total==16384) {overflow=true;return;}
        auto& e=out[n++];++total;e.ticks=first*5+int64_t(MLAT::sampleIndexToMlatTime<8>(at));
        auto hi=frame.high(),lo=frame.low();
        for(int i=0;i<6;++i)e.message[i]=uint8_t(hi>>(40-8*i));
        for(int i=0;i<8;++i)e.message[i+6]=uint8_t(lo>>(56-8*i));
    }
};
struct Context {
    int64_t first;uint32_t expected,received=0,pending=0;bool closed=false;int failed=0;
    Empty pipeline;InputReaderBase<IQ_UINT8_RTL_SDR,S::InputBufferSize,Empty> frontend;
    Handler handler;IncrementalSampleStream<S,Handler> stream;
    uint8_t tail[2*S::InputBufferSize];
    Context(int64_t f,uint32_t n):first(f),expected(n),frontend(pipeline),handler(f),stream(handler){}
    int reject(int rc) {failed=rc;return rc;}
    int block(const uint8_t *raw,int64_t deadline) {
        if(deadline && nowUs()>=deadline)return reject(-4);
        stream.processBlock(frontend,raw);
        if(handler.overflow)return reject(-2);
        return 0;
    }
};
}
extern "C" void *stream1090_incremental_create(int64_t first,uint32_t expected) {
    if(!expected || expected>4802400 || first<0 || first>(INT64_MAX-int64_t(expected)*5-100000)/5)return nullptr;
    try{return new Context(first,expected);}catch(...){return nullptr;}
}
extern "C" int stream1090_incremental_feed(void *opaque,const uint8_t *iq,uint32_t samples,
    int64_t first,stream1090_native_event *events,uint32_t cap,uint32_t *count,uint32_t timeout) {
    if(count)*count=0;
    auto *c=static_cast<Context*>(opaque);
    if(!c)return -1;
    if(!count || !events || !cap || !iq || !samples)return c->reject(-1);
    if(c->closed || c->failed || first!=c->first+c->received || samples>c->expected-c->received)return c->reject(-5);
    c->handler.bind(events,cap);const int64_t deadline=timeout?nowUs()+timeout:0;
    try {
        uint32_t left=samples;
        while(left) {
            if(!c->pending && left>=S::InputBufferSize) {
                int rc=c->block(iq,deadline);if(rc)return rc;
                iq+=2*S::InputBufferSize;left-=S::InputBufferSize;c->received+=S::InputBufferSize;
            } else {
                uint32_t n=std::min<uint32_t>(left,S::InputBufferSize-c->pending);
                std::memcpy(c->tail+2*c->pending,iq,2*n);iq+=2*n;left-=n;c->pending+=n;c->received+=n;
                if(c->pending==S::InputBufferSize) {
                    int rc=c->block(c->tail,deadline);if(rc)return rc;c->pending=0;
                }
            }
        }
        *count=c->handler.n;return 0;
    }catch(...){return c->reject(-3);}
}
extern "C" int stream1090_incremental_finish(void *opaque,stream1090_native_event *events,
    uint32_t cap,uint32_t *count,uint32_t timeout) {
    if(count)*count=0;auto *c=static_cast<Context*>(opaque);if(!c)return -1;
    if(!count || !events || !cap)return c->reject(-1);
    if(c->closed || c->failed || c->received!=c->expected)return c->reject(-5);
    c->handler.bind(events,cap);const int64_t deadline=timeout?nowUs()+timeout:0;
    try {
        std::memset(c->tail+2*c->pending,0,2*(S::InputBufferSize-c->pending));
        int rc=c->block(c->tail,deadline);if(rc)return rc;
        c->closed=true;*count=c->handler.n;return 0;
    }catch(...){return c->reject(-3);}
}
extern "C" void stream1090_incremental_destroy(void *p){delete static_cast<Context*>(p);}
extern "C" uint32_t stream1090_incremental_event_size(){return sizeof(stream1090_native_event);}
