/* Test-only buffered callback around the unchanged native readsb port. */
#include "dsp_stream_phase.h"
#include <stdint.h>
#include <string.h>
#include <stddef.h>
struct phase_event { int64_t ticks; uint8_t message[14]; };
struct output { struct phase_event *rows; uint32_t capacity, count; };
static void emit(const uint8_t message[14], int64_t bit_sample, void *opaque) {
    struct output *o = opaque;
    if (o->count < o->capacity) {
        o->rows[o->count].ticks = (bit_sample - 64) * 3 / 2;
        memcpy(o->rows[o->count].message, message, 14);
    }
    ++o->count;
}
uint32_t phase_scan(const uint8_t *raw, uint32_t samples, int64_t first,
                    int64_t new_sample, struct phase_event *rows, uint32_t capacity) {
    struct output o = {rows, capacity, 0};
    dspStreamPhase(raw, samples, first, new_sample, emit, &o, INT64_MAX);
    return o.count;
}
uint32_t phase_event_size(void) { return sizeof(struct phase_event); }
