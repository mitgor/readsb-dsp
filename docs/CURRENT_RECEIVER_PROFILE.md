# Working receiver integration profile (28 October 2026)

This is the non-secret part of the configuration used to evaluate the DSP
rescue ideas. The working Raspberry Pi 5 does **not** install this independent
`readsb-dsp` distribution. It runs stock readsb with a separate rescue
pipeline, and FR24 reads the guarded union stream. The package here remains off
by default and has its own `--dsp-rescue` shadow and output flags.
The live receiver dashboards still belong to the original receiver installation.
The new deadsb dsp source distribution includes its own optional loopback dashboard
and CPU governor; neither is automatically deployed by this repository.

| Component | Working receiver setting |
| --- | --- |
| SDR | One RTL-SDR on device 0, fixed gain 38.6 dB, PPM 0 |
| Stock readsb | Mode S/ADS-B at 2.4 MS/s, maximum configured range 450 nm |
| Beast stock output | `127.0.0.1:30005` |
| Guarded union output | `127.0.0.1:31005` |
| FR24 input | Beast TCP at `127.0.0.1:31005`; MLAT off |
| Stock receiver ownership | readsb alone owns the SDR; the rescue pipeline uses a read-only I/Q tap |

The receiver coordinates, FR24 sharing key, network credentials, and aircraft
captures are intentionally absent. The add-on's native output mode does not use
this separate relay or its policy gates, so these settings are **context for
comparison**, not an installation recipe for this package. In particular,
do not start a second RTL-SDR reader while the working readsb is running.
