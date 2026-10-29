/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Experimental bounded UC8 rescue. All decoding/state mutation runs on the
 * existing decode thread, after stock demodulation. No new threads or sockets. */
#include "readsb.h"
#include "dsp_rescue.h"
#include "dsp_rescue_coeffs.h"
#include "dsp_stream_phase.h"

void rescue_scores(const float *, int64_t, float *, double *);
int64_t rescue_header_ids(const float *, int64_t, const int64_t *, int64_t, int64_t *);
void rescue_baseline(const float *, int64_t, const int64_t *, int64_t, uint8_t *, uint8_t *);
int64_t rescue_dsp(const float *, int64_t, const int64_t *, int64_t,
                   const int64_t *, const float *, int, int, int64_t *, int64_t *, uint8_t *);

#define CHUNK 8192 /* 2.048ms at 4MS/s; bounded scratch and deadline checks */
#define CONTEXT 504
#define HISTORY 16384
#define PENDING 2048
#define CANDIDATES 2048
#define RETRIES 32 /* per 50ms of RF, no carry-over burst */

struct rescue_event {
    int64_t ticks, sys;
    double signal;
    uint8_t msg[14], method, corrected;
};
static struct {
    struct rescue_event stock[HISTORY], pending[PENDING], accepted[PENDING], research_accepted[PENDING];
    unsigned stock_at, stock_count, pending_count, accepted_at, accepted_count;
    unsigned research_at, research_count;
    int64_t expected, epoch, valid_from;
    unsigned retries;
    float iq[2 * (CHUNK + CONTEXT)], power[CHUNK + CONTEXT];
    double scores[CHUNK + CONTEXT];
    FILE *log;
    uint64_t buffers, backlog, deadlines, gaps, overflow, peaks, raw[5], extras[5];
    uint64_t duplicates, unknown, conflicts, budget_drops, forwarded, shadow_only_repair;
    uint64_t cpu_us;
    uint8_t clean_stock_icao[1u << 21]; /* fast prefilter; guard enforces 30 s */
    int64_t bitmap_rebuilt_tick;
} R;

static int64_t monotonic_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t) ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

static uint32_t checksum(const uint8_t *msg) {
    uint32_t crc = 0;
    for (int b = 0; b < 112; b++) {
        unsigned top = (crc >> 23) ^ ((msg[b / 8] >> (7 - b % 8)) & 1);
        crc = (crc << 1) & 0xffffff;
        if (top) crc ^= 0xfff409;
    }
    return crc;
}

static uint32_t address(const struct rescue_event *e) {
    return (e->msg[1] << 16) | (e->msg[2] << 8) | e->msg[3];
}

void dspRescueInit(void) {
    if (!Modes.dsp_rescue && (Modes.dsp_rescue_stream_phase || Modes.dsp_rescue_stream_phase_repair || Modes.dsp_rescue_output || Modes.dsp_rescue_log || Modes.dsp_rescue_budget_us)) {
        fprintf(stderr, "DSP rescue options require --dsp-rescue\n");
        exit(1);
    }
    if (Modes.dsp_rescue_stream_phase_repair && !Modes.dsp_rescue_stream_phase) {
        fprintf(stderr, "Phase repair requires --dsp-rescue-stream-phase\n");
        exit(1);
    }
    if (!Modes.dsp_rescue) return;
    if (Modes.net_only || (Modes.sdr_type != SDR_IFILE && Modes.sdr_type != SDR_RTLSDR)) {
        fprintf(stderr, "DSP rescue requires RTL-SDR or UC8 ifile input\n");
        exit(1);
    }
    if (Modes.dsp_rescue_log) {
        R.log = fopen(Modes.dsp_rescue_log, "w");
        if (!R.log) { perror("DSP audit log"); exit(1); }
        setvbuf(R.log, NULL, _IOFBF, 65536);
    }
    R.expected = -1;
    R.epoch = -1;
    fprintf(stderr, "DSP rescue: %s, native bounded energy/timing/soft/matched; no learned components\n",
            Modes.dsp_rescue_output ? "OUTPUT ENABLED (experimental)" : "shadow (no extra output)");
}

/* Called on the producer before it publishes out. The extra copy is absent
 * when disabled. Last buffer is immutable under the same SDR FIFO protocol. */
void dspRescueCapture(struct mag_buf *out, const struct mag_buf *last, const unsigned char *raw, unsigned n) {
    if (!Modes.dsp_rescue || !out->rescue_iq) return;
    unsigned h = Modes.trailing_samples;
    if (!out->dropped && last->rescue_iq && last->length >= h &&
            out->sampleTimestamp == last->sampleTimestamp + (int64_t) last->length * 5)
        memcpy(out->rescue_iq, last->rescue_iq + 2 * last->length, 2 * h);
    else
        memset(out->rescue_iq, 127, 2 * h);
    memcpy(out->rescue_iq + 2 * h, raw, 2 * n);
}

void dspRescueBegin(const struct mag_buf *mag) {
    if (!Modes.dsp_rescue) return;
    if (mag->dropped || mag->sampleTimestamp != R.expected) {
        R.stock_count = R.pending_count = R.accepted_count = R.research_count = 0;
        R.stock_at = R.accepted_at = R.research_at = 0;
        R.epoch = -1;
        R.valid_from = mag->sampleTimestamp / 5;
        memset(R.clean_stock_icao, 0, sizeof(R.clean_stock_icao));
        R.bitmap_rebuilt_tick = 0;
        R.gaps++;
    }
    R.expected = mag->sampleTimestamp + (int64_t) mag->length * 5;
}

static void mark_clean_stock_icao(uint32_t addr) {
    R.clean_stock_icao[addr >> 3] |= (uint8_t)(1u << (addr & 7));
}

/* A bitmap held for an entire receiver uptime would gradually admit random
 * noise headers as more addresses are seen. Rebuild it from recent clean
 * stock every five seconds; the exact 30-second guard remains authoritative. */
static void rebuild_clean_stock_bitmap(int64_t now) {
    memset(R.clean_stock_icao, 0, sizeof(R.clean_stock_icao));
    for (unsigned i = 0; i < R.stock_count; i++) {
        const struct rescue_event *s = &R.stock[(R.stock_at - 1 - i) % HISTORY];
        int64_t age = now - s->ticks;
        if (age > 30 * 12000000LL) break;
        if (age >= 0 && !s->corrected) mark_clean_stock_icao(address(s));
    }
    R.bitmap_rebuilt_tick = now;
}

void dspRescueStock(const struct modesMessage *mm) {
    if (!Modes.dsp_rescue || mm->msgtype != 17 || checksum(mm->msg)) return;
    struct rescue_event *e = &R.stock[R.stock_at++ % HISTORY];
    *e = (struct rescue_event) {.ticks = mm->timestamp, .corrected = mm->correctedbits};
    memcpy(e->msg, mm->msg, 14);
    if (R.stock_count < HISTORY) R.stock_count++;
    if (!R.bitmap_rebuilt_tick || e->ticks - R.bitmap_rebuilt_tick >= 5 * 12000000LL)
        rebuild_clean_stock_bitmap(e->ticks);
    else if (!mm->correctedbits)
        mark_clean_stock_icao(address(e));
}

/* A shared RF sample clock replaces the offline clock fit. Timestamp convention
 * is identical to stock (end bit 56, including its historical-buffer offset).
 * One buffer of deferral lets stock see packets spanning a buffer boundary. */
static int guarded(const struct rescue_event *e) {
    int identity = 0;
    uint32_t addr = address(e);
    for (unsigned i = 0; i < R.stock_count; i++) {
        const struct rescue_event *s = &R.stock[(R.stock_at - 1 - i) % HISTORY];
        int64_t dt = e->ticks - s->ticks;
        if (llabs(dt) <= 1440 && !memcmp(e->msg, s->msg, 14)) {
            R.duplicates++; return 0;
        }
        if (address(s) != addr) continue;
        if (llabs(dt) <= 48 && memcmp(e->msg, s->msg, 14)) {
            R.conflicts++; return 0;
        }
        if (!s->corrected && dt > 0 && dt <= 30 * 12000000LL) identity = 1;
    }
    for (unsigned i = 0; i < R.accepted_count; i++) {
        const struct rescue_event *s = &R.accepted[(R.accepted_at - 1 - i) % PENDING];
        if (llabs(e->ticks - s->ticks) <= 1440 && !memcmp(e->msg, s->msg, 14)) {
            R.duplicates++; return 0;
        }
        if (address(s) == addr && llabs(e->ticks - s->ticks) <= 48 && memcmp(e->msg, s->msg, 14)) {
            R.conflicts++; return 0;
        }
    }
    if (e->method == 4 && e->corrected) {
        for (unsigned i = 0; i < R.research_count; i++) {
            const struct rescue_event *s = &R.research_accepted[(R.research_at - 1 - i) % PENDING];
            if (llabs(e->ticks - s->ticks) <= 1440 && !memcmp(e->msg, s->msg, 14)) {
                R.duplicates++; return 0;
            }
        }
    }
    if (!identity) { R.unknown++; return 0; }
    return 1;
}

static void release_pending(int64_t deadline) {
    for (unsigned i = 0; i < R.pending_count; i++) {
        if (monotonic_us() >= deadline) { R.budget_drops += R.pending_count-i; break; }
        const struct rescue_event *e = &R.pending[i];
        int accept = guarded(e);
        if (accept) {
            R.extras[e->method]++;
            if (e->method == 4 && e->corrected) {
                R.research_accepted[R.research_at++ % PENDING] = *e;
                if (R.research_count < PENDING) R.research_count++;
            } else {
                R.accepted[R.accepted_at++ % PENDING] = *e;
                if (R.accepted_count < PENDING) R.accepted_count++;
            }
        }
        if (R.log) {
            fprintf(R.log, "{\"ticks\":%lld,\"method\":%u,\"corrected_bits\":%u,\"guarded\":%s,\"message\":\"",
                    (long long)e->ticks, e->method, e->corrected, accept ? "true" : "false");
            for (int b = 0; b < 14; b++) fprintf(R.log, "%02x", e->msg[b]);
            fputs("\"}\n", R.log);
        }
        if (!accept || !Modes.dsp_rescue_output) continue;
        /* New phase repairs have not passed an independent false-positive
         * check. Keep them shadow-only even when general DSP output is on.
         * readsb's correction counters also support at most two bits. */
        if ((e->method == 4 && e->corrected) || e->corrected > MODES_MAX_BITERRORS) {
            R.shadow_only_repair++; continue;
        }
        struct modesMessage *mm = netGetMM(&Modes.netMessageBuffer[0]);
        memcpy(mm->msg, e->msg, 14);
        mm->timestamp = e->ticks;
        mm->sysTimestamp = e->sys;
        mm->signalLevel = e->signal;
        if (decodeModesMessage(mm) < 0) continue;
        mm->correctedbits = e->corrected;
        Modes.stats_current.demod_accepted[e->corrected]++;
        netUseMessage(mm);
        R.forwarded++;
    }
    R.pending_count = 0;
    if (Modes.dsp_rescue_output) netDrainMessageBuffers();
}

static void candidate(const uint8_t *row, int method, unsigned corrected,
                      int64_t k, const struct mag_buf *mag, double signal) {
    R.raw[method]++;
    if (R.pending_count == PENDING) { R.overflow++; return; }
    struct rescue_event *e = &R.pending[R.pending_count++];
    /* k is the absolute 4MS/s start; all supported SDR paths use 12MHz ticks. */
    *e = (struct rescue_event) {
        .ticks = k * 3 + (int64_t)Modes.trailing_samples * 5 + 768,
        .method = method, .corrected = corrected, .signal = signal
    };
    e->sys = mag->sysTimestamp + (e->ticks - mag->sampleTimestamp) / 12000;
    memcpy(e->msg, row, 14);
}

struct phase_context { const struct mag_buf *mag; };
static void phase_candidate(const uint8_t row[14], int64_t bit_sample,
                            unsigned corrected, unsigned kind, void *opaque) {
    struct phase_context *ctx = opaque;
    (void)kind;
    /* Subtract the eight-microsecond preamble, then convert 8 MHz to 4 MHz.
     * readsb's timestamp convention is applied by candidate(). */
    candidate(row, 4, corrected, (bit_sample - 64) / 2, ctx->mag, 0);
}

/* Unique one/two-bit syndrome solution over <=6 weakest payload/parity bits.
 * DF, CA and ICAO remain untouched. Bounded 21 hypotheses. */
static unsigned soft(const float *iq, int s, uint8_t *row) {
    if (!Modes.nfix_crc) return 0; // Respect --no-fix.
    float confidence[6] = {1, 1, 1, 1, 1, 1};
    int weak[6] = {-1, -1, -1, -1, -1, -1};
    memset(row, 0, 14);
    for (int b = 0; b < 112; b++) {
        int j = 2 * (s + 32 + 4 * b);
        float v[4];
        for (int q = 0; q < 4; q++)
            v[q] = iq[j + 2*q] * iq[j + 2*q] + iq[j + 2*q + 1] * iq[j + 2*q + 1];
        float a = v[0] + v[1], z = v[2] + v[3];
        row[b/8] |= (a > z) << (7 - b%8);
        if (b < 32) continue;
        float c = fabsf(a-z) / (a+z+1.e-9f);
        if (c > .35f) continue;
        for (int q = 0; q < 6; q++) if (c < confidence[q]) {
            for (int r = 5; r > q; r--) { confidence[r] = confidence[r-1]; weak[r] = weak[r-1]; }
            confidence[q] = c; weak[q] = b; break;
        }
    }
    if ((row[0] >> 3) != 17 || !checksum(row)) return 0;
    uint8_t solution[14];
    unsigned found = 0, bits = 0;
    for (int a = 0; a < 6 && weak[a] >= 0; a++) {
        row[weak[a]/8] ^= 1 << (7-weak[a]%8);
        if (!checksum(row)) { memcpy(solution, row, 14); found++; bits=1; }
        for (int b = a+1; b < 6 && weak[b] >= 0; b++) {
            row[weak[b]/8] ^= 1 << (7-weak[b]%8);
            if (!checksum(row)) { memcpy(solution, row, 14); found++; bits=2; }
            row[weak[b]/8] ^= 1 << (7-weak[b]%8);
        }
        row[weak[a]/8] ^= 1 << (7-weak[a]%8);
    }
    if (found != 1) return 0;
    memcpy(row, solution, 14);
    return bits;
}

/* Global phase is essential: RTL blocks need not be multiples of three samples.
 * Process only real captured context; no synthetic edge padding is decoded. */
static void resample(const struct mag_buf *mag, int64_t first, int n, int64_t base) {
    for (int k = 0; k < n; k++) {
        int64_t time = (first+k)*3 + 51 - base*5;
        int phase = time % 5;
        float re=0, im=0;
        for (int j=phase; j<102; j+=5) {
            int64_t index=(time-j)/5;
            re += fir[j] * ((float)mag->rescue_iq[2*index]-127.5f);
            im += fir[j] * ((float)mag->rescue_iq[2*index+1]-127.5f);
        }
        R.iq[2*k] = re/128.f; R.iq[2*k+1] = im/128.f;
    }
}

void dspRescueProcess(const struct mag_buf *mag) {
    if (!Modes.dsp_rescue) return;
    R.buffers++;
    if (!mag->rescue_iq || mag->length < 64) { R.pending_count = 0; return; }
    lockReader();
    unsigned queued = (Modes.first_free_buffer - Modes.first_filled_buffer + MODES_MAG_BUFFERS) % MODES_MAG_BUFFERS;
    unlockReader();
    /* ifile is deliberately unthrottled; live backpressure discards rescue,
     * never waits or queues extra work ahead of stock. */
    if (Modes.sdr_type != SDR_IFILE && queued > 2) { R.backlog++; R.pending_count = 0; return; }
    int64_t began = monotonic_us();
    unsigned budget = Modes.dsp_rescue_budget_us;
    if (!budget) { budget = mag->length / 24; if (budget > 5000) budget = 5000; }
    int64_t deadline = began + budget;
    release_pending(deadline);
    int64_t base = mag->sampleTimestamp / 5 - Modes.trailing_samples;
    int64_t end = base + mag->length + Modes.trailing_samples;
    /* Own starts [base+32, base+length+32); > packet+FIR right context remains.
     * Skip artificial initial history and sample gaps. */
    int64_t first = (5*(base+32)+2)/3;
    int64_t valid_start = (5*(R.valid_from+32)+2)/3;
    if (first < valid_start) first = valid_start;
    int64_t stop = (5*(base+mag->length+32)+2)/3;
    int64_t safe_stop = (5*end-51)/3 - CONTEXT;
    if (stop > safe_stop) stop = safe_stop;
    for (int64_t at = first; at < stop; ) {
        if (monotonic_us() >= deadline) { R.deadlines++; break; }
        int core = (stop-at > CHUNK ? CHUNK : stop-at);
        int n = core+CONTEXT;
        resample(mag, at-8, n, base);
        rescue_scores(R.iq, n, R.power, R.scores);
        unsigned tried = 0;
        for (int s=8; s<core+8; s++) {
            if ((s & 63) == 0 && monotonic_us() >= deadline) break;
            if (R.scores[s] < .4 || R.scores[s] <= R.scores[s-1] || R.scores[s] < R.scores[s+1]) continue;
            R.peaks++;
            int64_t start=s, id;
            if (!rescue_header_ids(R.iq, n, &start, 1, &id)) continue;
            uint8_t row[14], valid;
            rescue_baseline(R.iq, n, &start, 1, row, &valid);
            int64_t k=at-8+s;
            double signal=0;
            for (int j=32; j<480; j++) signal+=R.power[s+j];
            /* Approximate normalized power, consistent with the UC8 full-scale
             * convention; interpolation can otherwise overshoot 1. */
            signal=fmin(signal/448 * (128.0/127.5) * (128.0/127.5), 1.0);
            if (valid) { candidate(row, 0, 0, k, mag, signal); s+=2; continue; }
            int64_t epoch=k/200000;
            if (epoch != R.epoch) { R.epoch=epoch; R.retries=0; }
            if (R.retries >= RETRIES || tried >= 8) { R.budget_drops++; continue; }
            R.retries++; tried++;
            int64_t ids[7], methods[7]; uint8_t rows[7*14];
            int64_t count = rescue_dsp(R.iq, n, &start, 1, shifts, weights, 1, 0, ids, methods, rows);
            if (count) {
                candidate(rows, 1, 0, k, mag, signal);
                s+=2; continue;
            }
            unsigned corrected = soft(R.iq, s, row);
            if (corrected) { candidate(row, 2, corrected, k, mag, signal); s+=2; continue; }
            count = rescue_dsp(R.iq, n, &start, 1, shifts, weights, 0, 1, ids, methods, rows);
            if (count) { candidate(rows, 3, 0, k, mag, signal); s+=2; }
        }
        at += core;
    }
    if (Modes.dsp_rescue_stream_phase && monotonic_us() < deadline) {
        struct phase_context ctx = {mag};
        dspStreamPhaseRepair(mag->rescue_iq, mag->length + Modes.trailing_samples,
                             base, base + Modes.trailing_samples,
                             phase_candidate, &ctx,
                             Modes.dsp_rescue_stream_phase_repair && Modes.nfix_crc ? R.clean_stock_icao : NULL,
                             deadline);
    }
    R.cpu_us += monotonic_us()-began;
}

void dspRescueCleanup(void) {
    if (!Modes.dsp_rescue) return;
    /* Do not release the last pending block without a following stock pass. */
    fprintf(stderr, "DSP rescue summary: {\"buffers\":%llu,\"work_us\":%llu,\"backlog_skips\":%llu,\"deadline_buffers\":%llu,\"discontinuities\":%llu,\"pending_overflow\":%llu,\"pending_tail\":%u,\"peaks\":%llu,\"retry_budget_skips\":%llu,\"duplicates\":%llu,\"unknown_identity\":%llu,\"conflicts\":%llu,\"raw\":[%llu,%llu,%llu,%llu,%llu],\"extras\":[%llu,%llu,%llu,%llu,%llu],\"shadow_only_repair\":%llu,\"forwarded\":%llu}\n",
        (unsigned long long)R.buffers, (unsigned long long)R.cpu_us,
        (unsigned long long)R.backlog, (unsigned long long)R.deadlines,
        (unsigned long long)R.gaps, (unsigned long long)R.overflow, R.pending_count,
        (unsigned long long)R.peaks, (unsigned long long)R.budget_drops,
        (unsigned long long)R.duplicates, (unsigned long long)R.unknown, (unsigned long long)R.conflicts,
        (unsigned long long)R.raw[0], (unsigned long long)R.raw[1], (unsigned long long)R.raw[2], (unsigned long long)R.raw[3], (unsigned long long)R.raw[4],
        (unsigned long long)R.extras[0], (unsigned long long)R.extras[1], (unsigned long long)R.extras[2], (unsigned long long)R.extras[3], (unsigned long long)R.extras[4],
        (unsigned long long)R.shadow_only_repair,
        (unsigned long long)R.forwarded);
    if (R.log && fclose(R.log)) perror("DSP audit log close");
    R.log=NULL;
}
