/* SPDX-License-Identifier: GPL-3.0-or-later
 * In-process adapter to pinned mgrone/stream1090, preserving its repair,
 * confidence, trust, phase suppression and final-block behavior unchanged.
 * Upstream copyright and license are retained in upstream/.
 */
#include "native.h"
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <chrono>
#include "upstream/Global.hpp"
#include "upstream/RawInputFormat.hpp"
#include "upstream/SampleStream.hpp"
#include "upstream/InputReaderBase.hpp"
using NativeSampler = Sampler_2_4_to_8_0_Mhz;
struct EmptyPipeline { static constexpr bool isEmpty = true; };
class MemoryReader : public InputReaderBase<IQ_UINT8_RTL_SDR, NativeSampler::InputBufferSize, EmptyPipeline> {
    const uint8_t *data; size_t remaining; bool ended = false;
    int64_t deadline; bool expired = false;
    static int64_t nowUs() { return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
    uint8_t tail[2*NativeSampler::InputBufferSize];
public:
    MemoryReader(EmptyPipeline &pipeline, const uint8_t *p, size_t n, uint32_t timeout)
      : InputReaderBase(pipeline), data(p), remaining(n), deadline(timeout ? nowUs()+timeout : 0) {}
    void readMagnitude(int32_t *out) {
        constexpr size_t block = sizeof(tail);
        if (remaining >= block) { this->processBlock(data, out); data += block; remaining -= block; }
        else {
            std::memcpy(tail,data,remaining);std::memset(tail+remaining,0,block-remaining);
            remaining=0;ended=true;this->processBlock(tail,out);
        }
    }
    bool eof() {
        if (ended) return true;
        if (deadline && nowUs() >= deadline) { expired=true;return true; }
        return false;
    }
    bool timedOut() const {return expired;}
};
struct BufferedHandler {
    stream1090_native_event *events; uint32_t capacity, count=0; int64_t first;
    bool overflow=false;
    void handleShort(uint64_t, uint64_t) {}
    void handleLong(uint64_t at, const Bits128 &frame) {
        // Trust for all formats is still processed inside DemodCore. Only DF17
        // is exported, matching the production rescue branch's admission scope.
        if ((frame.high() >> 43) != 17) return;
        if (count == capacity) { overflow=true;return; }
        auto &e=events[count++]; e.ticks=first*5 + int64_t(MLAT::sampleIndexToMlatTime<8>(at));
        auto hi=frame.high();auto lo=frame.low();
        for (int i=0;i<6;++i)e.message[i]=uint8_t(hi>>(40-8*i));
        for (int i=0;i<8;++i)e.message[i+6]=uint8_t(lo>>(56-8*i));
    }
};
extern "C" int stream1090_native_decode_timeout_us(const uint8_t *iq,uint32_t samples,int64_t first,
    stream1090_native_event *events,uint32_t capacity,uint32_t *count,uint32_t timeout_us) {
    if (count) *count=0;
    if (!iq || !events || !count || !capacity || !samples || first<0 || first>(INT64_MAX-int64_t(samples)*5-100000)/5) return -1;
    try {
        EmptyPipeline pipeline;MemoryReader input(pipeline,iq,size_t(samples)*2,timeout_us);
        auto stream=std::make_unique<SampleStream<NativeSampler>>();
        BufferedHandler handler{events,capacity,0,first};
        stream->read(input,handler);
        if(input.timedOut())return -4;
        if(handler.overflow)return -2;
        *count=handler.count;return 0;
    } catch (...) { return -3; }
}

extern "C" int stream1090_native_decode(const uint8_t *iq,uint32_t samples,int64_t first,
    stream1090_native_event *events,uint32_t capacity,uint32_t *count) {
    return stream1090_native_decode_timeout_us(iq,samples,first,events,capacity,count,0);
}
extern "C" uint32_t stream1090_native_event_size() {return sizeof(stream1090_native_event);}
