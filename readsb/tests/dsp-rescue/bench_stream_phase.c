/* SPDX-License-Identifier: GPL-3.0-or-later
 * Offline, read-only UC8 CPU benchmark. No SDR, socket, or feeder access. */
#define _POSIX_C_SOURCE 200809L
#include "../../dsp_stream_phase.h"
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define RATE 2400000
#define HALO 600
static uint64_t counts[3];
static void found(const uint8_t row[14], int64_t bit_sample, unsigned corrected,
                  unsigned kind, void *ctx) {
    (void)row; (void)bit_sample; (void)corrected; (void)ctx;
    if (kind < 3) counts[kind]++;
}
static void found_clean(const uint8_t row[14], int64_t bit_sample, void *ctx) {
    found(row, bit_sample, 0, 0, ctx);
}
static double seconds(clockid_t id) {
    struct timespec t; clock_gettime(id,&t);
    return t.tv_sec+t.tv_nsec*1e-9;
}
int main(int argc, char **argv) {
    if (argc != 3 && argc != 4) {
        fprintf(stderr,"usage: %s sample.uc8 known-icao-bitmap clean|repair\n",argv[0]);
        return 2;
    }
    int fd=open(argv[1],O_RDONLY), bf=open(argv[2],O_RDONLY);
    if (fd<0 || bf<0) { perror("open"); return 1; }
    struct stat st; if (fstat(fd,&st) || st.st_size < 4*RATE) return 1;
    uint8_t *iq=mmap(NULL,(size_t)st.st_size,PROT_READ,MAP_PRIVATE,fd,0);
    uint8_t *bitmap=mmap(NULL,1u<<21,PROT_READ,MAP_PRIVATE,bf,0);
    if (iq==MAP_FAILED || bitmap==MAP_FAILED) { perror("mmap"); return 1; }
    unsigned windows=(unsigned)(st.st_size/(2*RATE))-1;
    double cpu0=seconds(CLOCK_PROCESS_CPUTIME_ID), wall0=seconds(CLOCK_MONOTONIC);
    for (unsigned i=0;i<windows;i++) {
        const uint8_t *start=iq+(size_t)i*2*RATE;
        if (argc==4 && !strcmp(argv[3],"clean"))
            dspStreamPhase(start,RATE+2*HALO,(int64_t)i*RATE,
                           (int64_t)i*RATE+HALO,found_clean,NULL,INT64_MAX);
        else
            dspStreamPhaseRepair(start,RATE+2*HALO,(int64_t)i*RATE,
                                 (int64_t)i*RATE+HALO,found,NULL,bitmap,INT64_MAX);
    }
    double cpu=seconds(CLOCK_PROCESS_CPUTIME_ID)-cpu0;
    printf("{\"rf_seconds\":%u,\"cpu_seconds\":%.4f,\"wall_seconds\":%.4f,\"core_fraction\":%.4f,\"clean\":%"PRIu64",\"table\":%"PRIu64",\"erasure\":%"PRIu64"}\n",
           windows,cpu,seconds(CLOCK_MONOTONIC)-wall0,cpu/windows,
           counts[0],counts[1],counts[2]);
    return 0;
}
