/* SPDX-License-Identifier: GPL-3.0-or-later
 * Native readsb adaptation of the 2.4-to-8 MHz magnitude interpolator and
 * eight-phase rolling Manchester/CRC idea in mgrone/stream1090, commit
 * 2189bdaca1d62d5e88600b21a281ccc5c18012f2 (GPL-3.0-or-later).
 * This intentionally supports only uncorrected DF17; repairs and the
 * stream1090 ICAO cache are not copied. readsb's rescue guard owns trust.
 */
#include "dsp_stream_phase.h"
#include <math.h>
#include <string.h>
#include <time.h>

struct phase_lane { uint64_t high, low; uint32_t crc; };

static int64_t phase_now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (int64_t)t.tv_sec * 1000000 + t.tv_nsec / 1000;
}

static int32_t magnitude(const uint8_t *iq, int64_t i) {
    int32_t re = ((int32_t)iq[2*i] * 2 - 255) * 64;
    int32_t im = ((int32_t)iq[2*i+1] * 2 - 255) * 64;
    return (int32_t)(sqrtf((float)(re*re + im*im)) * 256.f + .5f);
}

static void extract(const struct phase_lane *lane, uint8_t row[14]) {
    uint64_t a = lane->high >> 16;
    uint64_t b = (lane->low >> 16) | (lane->high << 48);
    for (int i = 0; i < 6; ++i) row[i] = (uint8_t)(a >> (40-8*i));
    for (int i = 0; i < 8; ++i) row[i+6] = (uint8_t)(b >> (56-8*i));
}

void dspStreamPhase(const uint8_t *iq, unsigned samples, int64_t first_sample,
                    int64_t new_sample, dsp_phase_emit emit, void *ctx,
                    int64_t deadline_us) {
    if (!iq || !emit || samples < 320) return;
    struct phase_lane lanes[8] = {{0}};
    int32_t ring[16] = {0};
    /* All triplets are aligned to the global RF clock, not the buffer edge. */
    int64_t g0 = first_sample / 3;
    if (3*g0 < first_sample) ++g0; /* ceil even for initial negative history */
    int64_t g1 = (first_sample + (int64_t)samples - 4) / 3;
    int64_t first_output = g0 * 10;
    for (int64_t g = g0; g <= g1; ++g) {
        if ((g & 127) == 0 && phase_now_us() >= deadline_us) return;
        int64_t at = 3*g - first_sample;
        int32_t x0 = magnitude(iq, at), x1 = magnitude(iq, at+1);
        int32_t x2 = magnitude(iq, at+2), x3 = magnitude(iq, at+3);
        int32_t v[10] = {
            (7*x0+x1)/8, (x0+x1)/2, (x0+7*x1)/8, x1,
            (5*x1+3*x2)/8, (x1+3*x2)/4, x2,
            (3*x2+x3)/4, (3*x2+5*x3)/8, x3
        };
        for (int r = 0; r < 10; ++r) {
            int64_t q = g*10+r;
            ring[q & 15] = v[r];
            if (q < first_output+4) continue;
            int64_t p = q-4;
            unsigned phase = (unsigned)(p & 7);
            struct phase_lane *s = &lanes[phase];
            uint32_t bit = ring[p & 15] > ring[q & 15];
            uint32_t crc = s->crc ^ ((s->high >> 63) ? 0x3935ea : 0);
            crc = (crc << 1) | (uint32_t)((s->low >> 15) & 1);
            crc ^= (crc >> 24) ? 0x1fff409 : 0;
            s->high = (s->high << 1) | (s->low >> 63);
            s->low = (s->low << 1) | bit;
            s->crc = crc;
            if (p < first_output + 8*127 || (s->high >> 59) != 17 || crc) continue;
            /* The 112-bit frame occupies the high part of the 128-bit window. */
            int64_t bit_start = p - 127*8;
            if (p < new_sample*10/3) continue;
            uint8_t row[14];
            extract(s, row);
            if ((row[0] >> 3) == 17) emit(row, bit_start, ctx);
        }
    }
}
