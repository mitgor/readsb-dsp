/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef READSB_STREAM1090_INCREMENTAL_H
#define READSB_STREAM1090_INCREMENTAL_H
#include "native.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Isolated research API. One context per CURRENT logical window, not one per
 * chunk. Keep all guard/admission checks outside this decoder. Raw candidates
 * are NOT feeder-ready. If any call fails, quarantine the complete window.
 * No zero padding at chunk boundaries. finish() reproduces the batch EOF block.
 * Chunks must be contiguous, once-only and supplied in sample-clock order.
 * Caller must destroy/reset the context on any receiver epoch change.
 * No concurrent calls on one context. Bound: at most 4,802,400 input samples.
 * Return codes: -1 invalid input, -2 output overflow, -3 exception,
 * -4 per-call deadline, -5 gap/order/length/closed/previous-failure.
 * Failure poisons the context; output count is zero on failure. */
void *stream1090_incremental_create(int64_t first_sample,uint32_t expected_samples);
int stream1090_incremental_feed(void *context,const uint8_t *iq,uint32_t samples,
    int64_t first_sample,struct stream1090_native_event *events,uint32_t capacity,
    uint32_t *count,uint32_t timeout_us);
int stream1090_incremental_finish(void *context,struct stream1090_native_event *events,
    uint32_t capacity,uint32_t *count,uint32_t timeout_us);
void stream1090_incremental_destroy(void *context);
uint32_t stream1090_incremental_event_size(void);
#ifdef __cplusplus
}
#endif
#endif
