# Minimal transition comparison

Reproduce: `python3 flue-monitor/tools/iwdt_review/compare_minimal.py`.
The alternative is `minimal_iwdt_transition.c.inc`: one shared C lock, a mode
flag, full timeout/feed before clearing the recovery budget, and tick feeds
respecting the flag. No handler-state polling, extra interrupt mask or read-back.

Same bounded model and parameter grid for both variants (both cores and
transition directions, both scheduling orders, APB costs 4/10, handler delays
480/2160):

| Variant | Runs | OK | Panic | Bad final state | Reset/abort/deadlock |
|---|---:|---:|---:|---:|---:|
| Minimal | 216032 | 193244 | 20644 | 2144 | 0 |
| v3 | 216032 | 216032 | 0 | 0 | 0 |

One concrete failing sleep-entry trace: core=0, order=0, apb=4, delay=480,
expiry offset=-1500, no tick injection. Cycle numbers are model time:

1. 1059: CPU0 handler clears INT_RAW; CPU1 handler is still in flight.
2. 1553–1577: CPU1 reads max=39, writes stage0=40 and feeds.
3. 1583: CPU0 transition opens WPROTECT.
4. 1584: CPU1 handler closes WPROTECT.
5. 1597–1627: CPU0's stage0=1600, stage1 and feed writes are blocked.
6. CPU0 clears the recovery budget and returns. Final state: stage0=40, max=0.

The C spinlock does not exclude the assembly handler. Reordering plus a mode
flag therefore does not close this route under the model's assumptions.

Artifacts: `.cache/iwdt-minimal-comparison/results.json`, generated C/binaries
and per-scenario traces. This is a model counterexample, not a measured hardware
schedule or a frequency estimate. The model assumes coherent DRAM and ordered
APB writes; costs are parameterized. It does not prove v3 correct on silicon.
