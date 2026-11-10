/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef READSB_STREAM1090_NATIVE_H
#define READSB_STREAM1090_NATIVE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Timestamp uses the executable's 12 MHz window-relative convention plus
 * first_sample*5. Apply the independently measured stock alignment downstream.
 * This is NOT dspStreamPhase's first-bit timestamp convention. */
struct stream1090_native_event { int64_t ticks; uint8_t message[14]; };
/* Decode one finite 2.4 MS/s UC8 window with eight phases, upstream repairs
 * and trust rules. State resets per call, matching the deployed child process.
 * No I/O, threads, signal handlers, SDR, network or callbacks into live readsb.
 * Returns 0 on success, -1 on invalid arguments, -2 on output overflow,
 * -3 on allocation/other exception. Reject all output on nonzero status.
 * Partial final input block is zero-padded exactly as upstream stdin.
 * No whole-readsb live deadline or pending-queue integration is provided. */
int stream1090_native_decode(const uint8_t *iq, uint32_t samples,
    int64_t first_sample, struct stream1090_native_event *events,
    uint32_t capacity, uint32_t *count);
/* Bounded variant: wall deadline checked between ~3.4 ms input blocks.
 * timeout_us=0 disables it. -4 rejects ALL output after deadline expiry. */
int stream1090_native_decode_timeout_us(const uint8_t *iq, uint32_t samples,
    int64_t first_sample, struct stream1090_native_event *events,
    uint32_t capacity, uint32_t *count, uint32_t timeout_us);
uint32_t stream1090_native_event_size(void);
#ifdef __cplusplus
}
#endif
#endif
