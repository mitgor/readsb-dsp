# Monitoring transport retries and incremental call budgets

Production relay/native guards now retry only HTTP transport failures, at most
three fresh full snapshots with 0.2/0.5-second backoffs. No cached healthy result
is accepted. Persistent failures still reach the existing two-strike watchdog;
health assertions, malformed JSON, and non-transient HTTP errors are not masked.
The arrival guard obtains this function from the native activation helper.

The former native per-call 100 ms elapsed deadline includes descheduling. The
new budget retains 100 ms of thread CPU and separately limits elapsed time to
one second. Code -4 identifies CPU exhaustion and -6 wall safety exhaustion.
Both poison the context and quarantine its partial output. The coordinator logs
thread CPU, elapsed time and sample count on any native call failure. Queue,
progress, packet-admission and receiver-health limits remain unchanged.

A Pi-only clock-interposition harness pauses the actual decoder process for
250 ms within a call. Old library returns -4; new library succeeds. A 1.1-second
pause still fails new code with -6. This demonstrates a scheduling sensitivity;
the original production error had no CPU/wall breakdown, so its exact cause
cannot be proved retrospectively. Future errors retain that distinction.

Run controls.py from this repository on Mac or Pi. It extracts the actual retry
function and Budget definition, testing bounded retries, persistent failures,
unmasked health/auth/JSON errors, CPU and wall limits. pi_test.py runs isolated
under nice19/core3/35% CPU/1 GiB with protected health checks. Saved-RF integration
uses half-speed input and must retain 79 extras (32 energy, 47 Stream1090) and
the 210-packet recorded complete-pipeline union. It proves parity on historical
RF, not fresh distant improvement or real-time throughput at a 35% quota.

Private results and deployment/rollback receipts live in the data workspace at
results/guard-timeout-reactivation-20261111. Raw RF and receiver configurations
must remain private. Activation uses the existing guarded mode commands; primary
readsb, FR24, ADSBx, far-capture, models, gain and collection limits stay unchanged.
