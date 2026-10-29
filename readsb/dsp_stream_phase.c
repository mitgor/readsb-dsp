/* SPDX-License-Identifier: GPL-3.0-or-later
 * Native readsb adaptation of the 2.4-to-8 MHz magnitude interpolator and
 * eight-phase rolling Manchester/CRC idea in mgrone/stream1090, commit
 * 2189bdaca1d62d5e88600b21a281ccc5c18012f2 (GPL-3.0-or-later).
 * Repair paths are bounded and require a caller-supplied prior-stock ICAO
 * check. The stream1090 ICAO cache is not copied; readsb's guard owns trust.
 */
#include "dsp_stream_phase.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

struct phase_lane {
    uint64_t high, low;
    uint32_t crc;
    uint32_t difference[128];
};

struct phase_fix { uint32_t syndrome; uint8_t a, b, c, bits; };
static struct phase_fix fixes[2048];
static uint32_t deltas[112];
static int fixes_ready;

static uint32_t frame_crc(const uint8_t row[14]) {
    uint32_t crc = 0;
    for (int b = 0; b < 112; ++b) {
        unsigned top = (crc >> 23) ^ ((row[b/8] >> (7-b%8)) & 1);
        crc = (crc << 1) & 0xffffff;
        if (top) crc ^= 0xfff409;
    }
    return crc;
}

static void flip(uint8_t row[14], unsigned bit) {
    row[bit/8] ^= (uint8_t)(1u << (7-bit%8));
}

/* The rolling register uses a different syndrome basis from the ordinary
 * 112-bit CRC function. Derive each bit's delta in that exact basis. */
static uint32_t rolling_delta(unsigned bit) {
    uint64_t high = 0, low = 0;
    uint32_t crc = 0;
    for (unsigned i = 0; i < 128; ++i) {
        crc ^= (high >> 63) ? 0x3935ea : 0;
        crc = (crc << 1) | (uint32_t)((low >> 15) & 1);
        crc ^= (crc >> 24) ? 0x1fff409 : 0;
        high = (high << 1) | (low >> 63);
        low = (low << 1) | (i == bit);
    }
    return crc;
}

static void add_fix(uint32_t syndrome, unsigned a, unsigned b,
                    unsigned c, unsigned bits) {
    unsigned slot = (syndrome * 2654435761u) & 2047;
    while (fixes[slot].syndrome && fixes[slot].syndrome != syndrome)
        slot = (slot+1) & 2047;
    if (fixes[slot].syndrome) { fixes[slot].bits = 0; return; }
    fixes[slot] = (struct phase_fix){syndrome, (uint8_t)a, (uint8_t)b,
                                      (uint8_t)c, (uint8_t)bits};
}

static void init_fixes(void) {
    if (fixes_ready) return;
    for (unsigned b = 0; b < 112; ++b) deltas[b] = rolling_delta(b);
    /* Pinned Stream1090 uses DF17ErrorTableExperimental (933 patterns), not
     * its older conservative DF17ErrorTable. Exclude all DF header bits. */
    for (unsigned b = 5; b < 112; ++b) add_fix(deltas[b], b, 0, 0, 1);
    for (unsigned b = 5; b < 111; ++b)
        add_fix(deltas[b]^deltas[b+1], b, b+1, 0, 2);
    for (unsigned b = 5; b < 110; ++b)
        add_fix(deltas[b]^deltas[b+1]^deltas[b+2], b, b+1, b+2, 3);
    for (unsigned gap = 2; gap <= 7; ++gap)
        for (unsigned b = 5+gap; b < 112; ++b)
            add_fix(deltas[b]^deltas[b-gap], b, b-gap, 0, 2);
    fixes_ready = 1;
}

static const struct phase_fix *lookup_fix(uint32_t syndrome) {
    unsigned slot = (syndrome * 2654435761u) & 2047;
    while (fixes[slot].syndrome) {
        if (fixes[slot].syndrome == syndrome)
            return fixes[slot].bits ? &fixes[slot] : NULL;
        slot = (slot+1) & 2047;
    }
    return NULL;
}

static uint32_t address(const uint8_t row[14]) {
    return ((uint32_t)row[1] << 16) | ((uint32_t)row[2] << 8) | row[3];
}
static int known(const uint8_t *bitmap, uint32_t addr) {
    return addr && (bitmap[addr >> 3] & (1u << (addr & 7)));
}

static unsigned erasure_solve(const struct phase_lane *lane, int64_t p,
                              uint32_t syndrome, uint8_t row[14]) {
    uint8_t candidates[24];
    float confidence[24];
    int count = 0;
    /* Upstream indexes frameBit from the newest (LSB) end and ranks raw
     * absolute magnitude difference. Descending b preserves its tie order. */
    for (int b = 111; b >= 5; --b) {
        unsigned index = (unsigned)((p/8 - 127 + b) & 127);
        float c = (float)lane->difference[index];
        if (count == 24 && c >= confidence[23]) continue;
        int j = count < 24 ? count++ : 23;
        for (; j > 0 && confidence[j-1] > c; --j) {
            confidence[j] = confidence[j-1]; candidates[j] = candidates[j-1];
        }
        confidence[j] = c; candidates[j] = (uint8_t)b;
    }
    uint32_t pivot[24] = {0}, masks[24] = {0}, used = 0;
    for (int i = 0; i < count; ++i) {
        uint32_t value = deltas[candidates[i]], mask = 1u << i;
        for (int bit = 23; bit >= 0; --bit) {
            if (!(value & (1u << bit))) continue;
            if (!(used & (1u << bit))) {
                used |= 1u << bit; pivot[bit] = value; masks[bit] = mask;
                break;
            }
            value ^= pivot[bit]; mask ^= masks[bit];
        }
    }
    uint32_t residual = syndrome, solution = 0;
    for (int bit = 23; bit >= 0; --bit) {
        if (!(residual & (1u << bit))) continue;
        if (!(used & (1u << bit))) return 0;
        residual ^= pivot[bit]; solution ^= masks[bit];
    }
    unsigned bits = (unsigned)__builtin_popcount(solution);
    if (!bits || bits > 5) return 0;
    for (int i = 0; i < count; ++i) if (solution & (1u << i)) flip(row, candidates[i]);
    return bits;
}

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

static void scan(const uint8_t *iq, unsigned samples, int64_t first_sample,
                 int64_t new_sample, dsp_phase_emit_repair emit, void *ctx,
                 const uint8_t *known_icao_bitmap,
                 int64_t deadline_us) {
    if (!iq || !emit || samples < 320) return;
    if (known_icao_bitmap) init_fixes();
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
            int32_t first = ring[p & 15], second = ring[q & 15];
            uint32_t bit = first > second;
            if (known_icao_bitmap) {
                unsigned index = (unsigned)((p/8) & 127);
                s->difference[index] = (uint32_t)abs(first-second);
            }
            uint32_t crc = s->crc ^ ((s->high >> 63) ? 0x3935ea : 0);
            crc = (crc << 1) | (uint32_t)((s->low >> 15) & 1);
            crc ^= (crc >> 24) ? 0x1fff409 : 0;
            s->high = (s->high << 1) | (s->low >> 63);
            s->low = (s->low << 1) | bit;
            s->crc = crc;
            if (p < first_output + 8*127 || (s->high >> 59) != 17) continue;
            /* The 112-bit frame occupies the high part of the 128-bit window. */
            int64_t bit_start = p - 127*8;
            if (p < new_sample*10/3) continue;
            uint8_t row[14];
            extract(s, row);
            if ((row[0] >> 3) != 17) continue;
            if (!crc) { emit(row, bit_start, 0, 0, ctx); continue; }
            if (!known_icao_bitmap) continue;
            const struct phase_fix *fix = lookup_fix(crc);
            if (fix) {
                flip(row, fix->a);
                if (fix->bits == 2) flip(row, fix->b);
                if (fix->bits == 3) { flip(row, fix->b); flip(row, fix->c); }
                if (!frame_crc(row) && known(known_icao_bitmap, address(row))) {
                    emit(row, bit_start, fix->bits, 1, ctx);
                    continue;
                }
                flip(row, fix->a);
                if (fix->bits == 2) flip(row, fix->b);
                if (fix->bits == 3) { flip(row, fix->b); flip(row, fix->c); }
            }
            /* Stream1090's erasure repair requires the *raw* address to be
             * trusted, before solving. This also bounds solver load. */
            if (!known(known_icao_bitmap, address(row))) continue;
            unsigned corrected = erasure_solve(s, p, crc, row);
            if (corrected && !frame_crc(row) && known(known_icao_bitmap, address(row)))
                emit(row, bit_start, corrected, 2, ctx);
        }
    }
}

void dspStreamPhaseRepair(const uint8_t *iq, unsigned samples, int64_t first_sample,
                          int64_t new_sample, dsp_phase_emit_repair emit, void *ctx,
                          const uint8_t *known_icao_bitmap,
                          int64_t deadline_us) {
    scan(iq, samples, first_sample, new_sample, emit, ctx,
         known_icao_bitmap, deadline_us);
}

struct clean_context { dsp_phase_emit emit; void *ctx; };
static void clean_callback(const uint8_t row[14], int64_t bit_sample,
                           unsigned corrected, unsigned kind, void *opaque) {
    struct clean_context *c = opaque;
    (void)corrected; (void)kind;
    c->emit(row, bit_sample, c->ctx);
}

void dspStreamPhase(const uint8_t *iq, unsigned samples, int64_t first_sample,
                    int64_t new_sample, dsp_phase_emit emit, void *ctx,
                    int64_t deadline_us) {
    if (!emit) return;
    struct clean_context c = {emit, ctx};
    scan(iq, samples, first_sample, new_sample, clean_callback, &c,
         NULL, deadline_us);
}
