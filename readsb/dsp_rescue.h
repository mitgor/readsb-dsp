/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef READSB_DSP_RESCUE_H
#define READSB_DSP_RESCUE_H
struct mag_buf;
struct modesMessage;
void dspRescueInit(void);
void dspRescueBegin(const struct mag_buf *mag);
void dspRescueCapture(struct mag_buf *out, const struct mag_buf *last, const unsigned char *raw, unsigned n);
void dspRescueStock(const struct modesMessage *mm);
void dspRescueProcess(const struct mag_buf *mag);
void dspRescueCleanup(void);
#endif
