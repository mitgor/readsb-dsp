/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Exercise the private rolling-CRC basis and bounded erasure solver. */
#include "../../dsp_stream_phase.c"
#include <assert.h>
#include <stdio.h>

static const uint8_t example[14] = {
    0x8d,0x40,0x62,0x1d,0x58,0xc3,0x82,0xd6,0x90,0xc8,0xac,0x28,0x63,0xa7
};

int main(void) {
    init_fixes();
    int patterns=0, ambiguous=0;
    for (unsigned i=0;i<2048;i++) if (fixes[i].syndrome) {
        if (fixes[i].bits) patterns++; else ambiguous++;
    }
    assert(patterns==933 && ambiguous==0);
    assert(frame_crc(example)==0);
    const struct phase_fix *fix = lookup_fix(deltas[66]);
    assert(fix && fix->bits==1 && fix->a==66);
    struct phase_lane lane = {0};
    const int errors[3] = {40,66,90};
    uint8_t row[14]; memcpy(row,example,14);
    for (int b=0;b<112;b++) {
        lane.difference[b]=1000;
    }
    uint32_t syndrome=0;
    for (int j=0;j<3;j++) {
        int b=errors[j];
        flip(row,b); syndrome ^= deltas[b];
        lane.difference[b]=1;
    }
    assert(frame_crc(row)!=0);
    unsigned n=erasure_solve(&lane,127*8,syndrome,row);
    assert(n==3 && !memcmp(row,example,14) && frame_crc(row)==0);
    puts("phase rolling CRC and three-bit erasure: OK");
}
