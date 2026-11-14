# IWDT v3 host review

Run from the repository root:

```sh
python3 flue-monitor/tools/iwdt_review/run_review.py
python3 flue-monitor/tools/test_iwdt_transition.py
```

The bounded runner writes generated host C, binaries and `review-results.json`
to `/tmp/flue-iwdt-v3-review`. Run one instance at a time. It never contacts a
device. The candidate is loaded from `cmake/iwdt_transition.c.inc`; the deployed
patch is frozen in `deployed_iwdt_transition.c.inc` as a negative control.
`proposal_iwdt_transition.c.inc` and the proposal document preserve the review
context, not an alternate build input. The older settle proposal is historical.

The corrected model uses an active watchdog stage with its own counter, so a
stage0 register write cannot extend an already-active stage1. Every model
binary checks that property before a sweep. C shared accesses yield separately;
handler cleanup and rendezvous loads are split. Scheduler order is varied.
Ordinary cases require OK and no short-stage/max0 or stage1 invariant violation.
Hung cores must reset. Exhausted budget/deadline cases must panic. Stalls are
separate fault-injection tests: visible panic/reset is allowed and recorded,
never represented as healthy operation. No result classifier drops resets.

This is not an instruction emulator or a formal proof. APB/DRAM visibility is
ordered/coherent, time is parameterized/scaled, some handler operations remain
grouped, and cross-products are sampled. Weak ordering and actual latency need
hardware/platform evidence. More runs do not remove these assumptions.

Latest built candidate (not deployed):
`.cache/watchdog-diagnostics/3e34ad72c0f1c367/` under the project; see the top of `flue-monitor/CLAUDE.md` for the exact path.
224 scenarios, 407950 runs, all explicit expectations passed. In stall cases
770 panics and 658 resets occurred as visible failure responses; normal/tick
cases had none. Baseline CPU0 deployed patch retains 14 bad final outcomes.
