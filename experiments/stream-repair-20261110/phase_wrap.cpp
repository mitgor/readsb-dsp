/* SPDX-License-Identifier: GPL-3.0-or-later; benchmark ABI only. */
#include "native.h"
extern "C" uint32_t phase_scan(const uint8_t *raw,uint32_t samples,int64_t first,
 int64_t,stream1090_native_event *rows,uint32_t capacity) {
 uint32_t count=0;
 return stream1090_native_decode(raw,samples,first,rows,capacity,&count)==0 ? count : capacity+1;
}
extern "C" uint32_t phase_event_size() {return sizeof(stream1090_native_event);}
