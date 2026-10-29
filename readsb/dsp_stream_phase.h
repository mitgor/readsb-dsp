/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DSP_STREAM_PHASE_H
#define DSP_STREAM_PHASE_H
#include <stdint.h>

/* Absolute 8 MHz sample position of the first bit (after the preamble). */
typedef void (*dsp_phase_emit)(const uint8_t msg[14], int64_t bit_sample, void *ctx);
/* kind: 0 clean, 1 fixed syndrome table, 2 confidence erasure. Repairs are
 * emitted only when known_icao_bitmap accepts the corrected ICAO. The caller's
 * existing packet guard remains authoritative. */
typedef void (*dsp_phase_emit_repair)(const uint8_t msg[14], int64_t bit_sample,
                                      unsigned corrected_bits, unsigned kind, void *ctx);

/* Independent eight-phase Manchester/rolling-CRC search over 2.4 MS/s UC8.
 * The input includes the readsb history before the new samples. The callback
 * only receives clean, uncorrected DF17 frames ending in the new samples. */
void dspStreamPhase(const uint8_t *iq, unsigned samples, int64_t first_sample,
                    int64_t new_sample, dsp_phase_emit emit, void *ctx,
                    int64_t deadline_us);
void dspStreamPhaseRepair(const uint8_t *iq, unsigned samples, int64_t first_sample,
                          int64_t new_sample, dsp_phase_emit_repair emit, void *ctx,
                          const uint8_t *known_icao_bitmap,
                          int64_t deadline_us);
#endif
