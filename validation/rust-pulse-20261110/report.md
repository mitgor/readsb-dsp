# Rust pulse-discriminant validation — November 10, 2026

Ported the frozen eight-tap pulse discriminant and 1–8-model bank to Rust. Candidate selection, model weights/bias, ordered FP64 accumulation, FP32 outputs, normalization, partial-write/error behavior and unchanged CRC/header/address guards are retained. No new bank, model or algorithm is enabled by this port.

On the current Pi5/Cortex-A76, all logits/confidences are bit-exact against both rebuilt C and the exact live C library. Rebuilt/live C ELFs have identical SHA-256. Validation covers 3,840 chronological historical power windows spread across24 RF seconds, 58 numerical/error/bounds/partial-write controls and 6 model-bank controls. Cases include zero/subnormal/large power, overflow, random weights, invalid preamble/late bit inputs, nonfinite model values and empty batches. Bank results also match independent scalar calls. The unchanged packet logic yields identical signatures for 250 valid window outputs; these are not unique full-pipeline additions.

Nine counterbalanced target trials, 50 calls per mode, measure CPU seconds per 3,840-window batch, including identical Python allocation/FFI overhead:

| Library | Median CPU seconds |
|---|---:|
| c | 0.01041440 |
| rust | 0.01099401 |
| actual | 0.01037116 |

Rust costs **6.01% more pulse-batch CPU** versus actual C (5.35% versus rebuilt C paired trials). Mac was approximately neutral. This is **not a CPU-saving result**. The pulse batch is a small component; no whole-Pi/energy claim follows.

Complete current native pipeline replay over24 RF seconds, including already active Rust sequence/coherent/acquisition and enabled neural/DSP branches, matches every raw candidate, accepted packet, alignment audit and admission decision. The 369 native extras and prior403-extra native+unchanged-Stream union are preserved, with zero added or lost packets. Native-worker CPU was 0.554237 seconds/RF-second for C and 0.555557 for Rust in one sequential pass each; these are descriptive and insufficient for a precise overall cost claim.

RF is already-consumed historical regression data, not fresh prospective validation. Only ten >=180nm stock opportunities from three aircraft exist; no range-improvement or training-label claim. Experimental outputs stay quarantined.

Target work ran nice19/core3/CPUQuota35%, finite, with protected receiver/feeder/collector/Stream/source/model/config/gain/switch/loss fingerprints unchanged. A conservative summed-child RSS bound below1GiB was independently monitored because the kernel lacks an effective memory controller. Maximum recorded test RSS: 981.1MiB. No SDR/mirror access, candidate injection, service restart, forced flush or persistent archive deletion during validation.

Full source, temporary compiler, original/port libraries, model/RF inputs, controls, outputs and journals were checksum-verified and fsynced on Mac before exact owned tmpfs cleanup. Deployment is separately documented under pulse-rust-activation-20261110. Activation follows the user's explicit request if parity and live stability pass, not a claim of greater efficiency.
