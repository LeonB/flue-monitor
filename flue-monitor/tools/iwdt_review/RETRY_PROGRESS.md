# Retry progress investigation — 2026-11-03

Local only; no production, PR, or device changes. Reproduce with
`python3 flue-monitor/tools/iwdt_review/probe_retry_progress.py` from repository root.
Artifacts: `.cache/iwdt-retry-progress/` under the firmware project.

## Ordinary handler interleavings

Reused the existing 224-scenario / 407950-run matrix, including SDK/deployed
positive controls. All scenario expectations passed. The proposal accounted
for 220 scenarios / 359946 runs. Instrumentation counts accepted transition
feeds separately from tick feeds, and retries which accepted at least one feed
in that iteration. It does not change modeled timing.

Proposal maxima: two transition feeds (enable also feeds its short stage),
one fed retry. Normal and tick/expiry sweeps had at most 168 retries. Stall
scenarios reached 106370 retries, but zero fed retries; they retain their
explicit panic/reset expectations. No model-deadline outcome occurred in the
proposal matrix. Thus there is no observed recurring feed-without-completion
path in these ordinary scenarios. This bounded sweep is not a proof that no
such hardware interleaving exists, nor a reason alone to remove the bound.

## Artificial readback fault, separately

Injected a permanently false return from the WPROTECT-read helper while actual
register protection, stage writes and feed acceptance retain their normal
behavior. This deliberately violates the accurate-readback assumption; it is
not an observed silicon fault or a handler/WPROTECT counterexample.

With a scaled software bound of 20000 model cycles: ABORT at cycle 20143,
228 accepted feeds and 228 fed retries. With the loop bound removed: 45976
accepted feeds / fed retries, no completion or watchdog reset by the model's
4000001-cycle horizon (reported DEADLOCK by the harness). This is a repeating
feed/false-verification path: each iteration refreshes the timer, so the
hardware watchdog cannot be relied on to terminate it. The finite run alone
is not an infinite-execution proof. The original 1<<30 bound was not simulated
for its full duration; the scaled probe verifies the termination mechanism.
Trace `read WPROTECT=open` describes actual modeled register state, while the
injected function deliberately returns false.

## Decision

Keep the current retry bound and PR unchanged. Its demonstrated role here is
bounded failure handling when verification persistently fails after accepted
feeds. We have not demonstrated that ordinary handler interleavings require
it. No need to replace abort with assert or refactor the enable/disable paths
on the strength of this investigation.
