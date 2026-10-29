#!/usr/bin/env python3
"""Patch a disposable pinned source checkout only; no service changes."""
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
f=a.source/'sdr_rtlsdr.c';s=f.read_text()
if 'rescue_stream_samples' in s:raise SystemExit('Already patched')
# Accept the previous finite capture checkout, removing that inactive hook.
s=s.replace('#include "iq_tap.h"','').replace('    iq_capture_samples(buf, len, (unsigned) Modes.sample_rate);','')
needle='void rtlsdrCallback(unsigned char *buf, uint32_t len, void *ctx) {'
if s.count(needle)!=1 or s.count('#include "sdr_rtlsdr.h"')!=1:raise SystemExit('Unsupported source')
s=s.replace('#include "sdr_rtlsdr.h"','#include "sdr_rtlsdr.h"\n#include "stream_tap.h"')
s=s.replace(needle,needle+'\n    rescue_stream_samples(buf, len, (unsigned) Modes.sample_rate);')
(a.source/'stream_tap.h').write_bytes(Path(__file__).with_name('stream_tap.h').read_bytes());f.write_text(s)
