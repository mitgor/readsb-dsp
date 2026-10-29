/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Include the implementation to test private, bounded streaming/guard state. */
#include "../../dsp_rescue.c"
#include <assert.h>
struct _Modes Modes;
static struct modesMessage test_mm;
static unsigned sends;
void lockReader(void) {}
void unlockReader(void) {}
struct modesMessage *netGetMM(struct messageBuffer *b) { (void)b; memset(&test_mm, 0, sizeof(test_mm)); return &test_mm; }
int decodeModesMessage(struct modesMessage *mm) { return checksum(mm->msg) ? -2 : 0; }
void netUseMessage(struct modesMessage *mm) { (void)mm; sends++; }
void netDrainMessageBuffers(void) {}

static const uint8_t example[14] = {0x8d,0x40,0x62,0x1d,0x58,0xc3,0x82,0xd6,0x90,0xc8,0xac,0x28,0x63,0xa7};
static unsigned phase_hits;
static int64_t phase_time;
static unsigned repair_hits, table_hits, erasure_hits;
static void phase_found(const uint8_t row[14], int64_t bit_sample, void *ctx) {
    (void)ctx;
    assert(!memcmp(row, example, 14));
    phase_hits++;
    phase_time = bit_sample;
}
static uint8_t phase_known[1u << 21];
static uint8_t phase_unknown[1u << 21];
static void phase_recovered(const uint8_t row[14], int64_t bit_sample,
                            unsigned bits, unsigned kind, void *ctx) {
    (void)bit_sample; (void)ctx;
    assert(!memcmp(row, example, 14));
    repair_hits++;
    if (kind==1 && bits==1) table_hits++;
    if (kind==2) erasure_hits++;
}
static void phase_signal(uint8_t *iq, int n, int start, const uint8_t row[14]) {
    memset(iq,128,2*n);
    for (int i=start-4; i<start+300; i++) {
        double t=(i-start)/2.4;
        int on=(t>=0 && t<.5) || (t>=1 && t<1.5) ||
               (t>=3.5 && t<4) || (t>=4.5 && t<5);
        int bit=(int)(t-8);
        if (t>=8 && bit<112) {
            int value=(row[bit/8]>>(7-bit%8))&1;
            on |= value ? t-8-bit<.5 : t-8-bit>=.5;
        }
        if (on) iq[2*i]=210;
    }
}
static void phase_decoder(void) {
    const int start=1200, split=1400, history=326, n=3000;
    uint8_t *iq=malloc(2*n); assert(iq);
    phase_signal(iq,n,start,example);
    phase_hits=0;
    dspStreamPhase(iq,split,0,0,phase_found,NULL,monotonic_us()+1000000);
    assert(phase_hits==0); /* frame is cut off in this block */
    dspStreamPhase(iq+2*(split-history),n-split+history,split-history,
                   split,phase_found,NULL,monotonic_us()+1000000);
    assert(phase_hits>=1 && phase_hits<=3);
    assert(llabs(phase_time-(int64_t)(start*10/3+64))<=8);
    uint8_t damaged[14]; memcpy(damaged,example,14);
    damaged[66/8] ^= 1u << (7-66%8);
    phase_signal(iq,n,start,damaged);
    repair_hits=table_hits=erasure_hits=0;
    phase_known[0x40621d >> 3] |= 1u << (0x40621d & 7);
    dspStreamPhaseRepair(iq,n,0,0,phase_recovered,NULL,phase_unknown,
                         monotonic_us()+1000000);
    assert(repair_hits==0);
    dspStreamPhaseRepair(iq,n,0,0,phase_recovered,NULL,phase_known,
                         monotonic_us()+1000000);
    assert(repair_hits>=1 && table_hits>=1);
    free(iq);
}
static struct rescue_event event(int64_t t) {
    struct rescue_event e = {.ticks=t, .sys=1000}; memcpy(e.msg, example, 14); return e;
}
static void reset(void) { memset(&R,0,sizeof(R)); memset(&Modes,0,sizeof(Modes)); Modes.dsp_rescue=1; Modes.nfix_crc=1; sends=0; }
static void stock(int64_t t) {
    struct modesMessage mm={.timestamp=t,.msgtype=17}; memcpy(mm.msg,example,14); dspRescueStock(&mm);
}
static void guards(void) {
    reset(); struct rescue_event e=event(24000000);
    assert(!checksum(example));
    assert(!guarded(&e)); // no stock identity
    stock(e.ticks+2000); assert(!guarded(&e)); // future identity cannot seed
    stock(e.ticks-12000000); assert(guarded(&e));
    stock(e.ticks-1); assert(!guarded(&e)); // duplicate of stock
    reset(); stock(e.ticks-31*12000000LL); assert(!guarded(&e)); // expired
    reset(); stock(e.ticks-12000000);
    R.accepted[0]=e; R.accepted_count=1; R.accepted_at=1;
    assert(!guarded(&e)); // cross-method duplicate
    R.accepted[0].msg[5]^=1; assert(!guarded(&e)); // same-time conflict
    reset(); stock(e.ticks-12000000); R.stock[0].corrected=1;
    assert(!guarded(&e)); // repaired stock cannot establish identity
    reset(); stock(12000000);
    assert(R.clean_stock_icao[0x40621d >> 3] & (1u << (0x40621d & 7)));
    rebuild_clean_stock_bitmap(32 * 12000000LL);
    assert(!(R.clean_stock_icao[0x40621d >> 3] & (1u << (0x40621d & 7))));
    reset(); struct modesMessage repaired={.timestamp=12000000,.msgtype=17,.correctedbits=1};
    memcpy(repaired.msg,example,14); dspRescueStock(&repaired);
    assert(!(R.clean_stock_icao[0x40621d >> 3] & (1u << (0x40621d & 7))));
    reset(); stock(e.ticks-12000000); R.pending[0]=e; R.pending_count=1;
    release_pending(monotonic_us()+1000000); assert(R.extras[0]==1 && sends==0);
    reset(); stock(e.ticks-12000000); R.pending[0]=e; R.pending_count=1; Modes.dsp_rescue_output=1;
    release_pending(monotonic_us()+1000000); assert(sends==1 && R.forwarded==1);
    reset(); stock(e.ticks-12000000); e.corrected=3; R.pending[0]=e; R.pending_count=1; Modes.dsp_rescue_output=1;
    release_pending(monotonic_us()+1000000); assert(sends==0 && R.shadow_only_repair==1);
    reset(); stock(e.ticks-12000000); e.method=4; e.corrected=1; R.pending[0]=e; R.pending_count=1; Modes.dsp_rescue_output=1;
    release_pending(monotonic_us()+1000000); assert(sends==0 && R.shadow_only_repair==1);
    assert(R.research_count==1 && R.accepted_count==0);
    R.pending[0]=e; R.pending_count=1;
    release_pending(monotonic_us()+1000000); assert(R.extras[4]==1);
    e.method=0; e.corrected=0; R.pending[0]=e; R.pending_count=1;
    release_pending(monotonic_us()+1000000); assert(sends==1 && R.extras[0]==1);
    reset(); stock(e.ticks-12000000); R.pending[0]=e; R.pending_count=1;
    release_pending(0); assert(!R.pending_count && !sends && R.budget_drops==1);
    struct mag_buf mag={.sampleTimestamp=2000,.length=100,.dropped=1};
    dspRescueBegin(&mag); assert(!R.stock_count && !R.accepted_count && !R.pending_count);
    assert(R.expected==2500 && R.valid_from==400);
    reset(); Modes.sdr_type=SDR_RTLSDR; Modes.first_free_buffer=3;
    uint8_t iq[200]={0}; mag.rescue_iq=iq; R.pending_count=1;
    dspRescueProcess(&mag);
    assert(R.backlog==1 && !R.pending_count && !R.cpu_us);
}
static void weak_bits(void) {
    float iq[2*504]={0}; uint8_t row[14];
    for (int b=0;b<112;b++) {
        int bit=(example[b/8]>>(7-b%8))&1;
        int at=32+4*b+(bit?0:2);
        iq[2*at]=iq[2*(at+1)]=1;
    }
    for (int b=65;b<=66;b++) {
        int at=32+4*b, bit=(example[b/8]>>(7-b%8))&1;
        for(int q=0;q<4;q++) iq[2*(at+q)]=((q<2)==bit)?.65f:.7f;
    }
    assert(soft(iq,0,row)==2 && !memcmp(row,example,14));
    Modes.nfix_crc=0; assert(!soft(iq,0,row)); Modes.nfix_crc=1;
    /* A third weak error in the protected header must never be guessed. */
    int at=32+4*8, bit=(example[1]>>7)&1;
    for(int q=0;q<4;q++) iq[2*(at+q)]=((q<2)==bit)?.65f:.7f;
    assert(!soft(iq,0,row));
}
static void buffers(void) {
    reset(); Modes.trailing_samples=326; Modes.sdr_type=SDR_IFILE;
    Modes.dsp_rescue_budget_us=50000;
    unsigned capacity=16384;
    uint8_t *raw=malloc(2*capacity), *prev=malloc(2*(capacity+326));
    uint8_t *next=malloc(2*(capacity+326));
    assert(raw && prev && next);
    for (unsigned i=0;i<2*capacity;i++) raw[i]=(i*17+11)%256;
    struct mag_buf last={.rescue_iq=prev,.sampleTimestamp=0,.length=capacity};
    struct mag_buf out={.rescue_iq=next,.sampleTimestamp=capacity*5,.length=capacity};
    memset(prev,44,2*(capacity+326));
    dspRescueCapture(&out,&last,raw,capacity);
    assert(!memcmp(next,prev+2*capacity,652));
    assert(!memcmp(next+652,raw,2*capacity));
    out.dropped=1; dspRescueCapture(&out,&last,raw,capacity);
    for(int i=0;i<652;i++) assert(next[i]==127);
    /* Short chunks, all three resampling phases and continuous boundaries. */
    for (unsigned phase=0;phase<3;phase++) for(unsigned n=64;n<16000;n=n*2+1) {
        out.sampleTimestamp=(capacity+phase)*5; out.length=n;
        dspRescueBegin(&out); dspRescueProcess(&out);
    }
    /* Global-phase resampling agrees when one physical window is described
     * using different input origins. This catches block-length modulo-3 drift. */
    out.length=capacity; out.dropped=0;
    for (int phase=0;phase<3;phase++) {
        int64_t base=123456+phase, first=(base+100)*5/3;
        resample(&out,first,100,base);
        float reference[200]; memcpy(reference,R.iq,sizeof(reference));
        /* Shift the origin and data pointer by 3 input samples (5 outputs). */
        struct mag_buf shifted=out; shifted.rescue_iq+=6;
        resample(&shifted,first,100,base+3);
        for(int k=0;k<200;k++) assert(reference[k]==R.iq[k]);
    }
    free(raw); free(prev); free(next);
}
int main(void) { guards(); weak_bits(); buffers(); phase_decoder(); puts("native DSP guards, weak bits, capture, phase decoder, streaming bounds: OK"); }
