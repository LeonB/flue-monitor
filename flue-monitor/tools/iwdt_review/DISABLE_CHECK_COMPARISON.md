# Final disable read-back comparison

Only the final disable branch differs: its three register predicates become
`ok = true`. The pre-write idle check, long-write verification, post-write idle
check, retry cycle bound and enable failure behavior are unchanged. Production
sources and the published PR were not modified.

Reproduce:

```sh
python3 flue-monitor/tools/iwdt_review/compare_disable_check.py
python3 flue-monitor/tools/iwdt_review/probe_disable_check_fault.py
```

Both variants meet all explicit expectations in the existing matrix: 224
scenarios / 407950 runs each, zero failed expectations. This includes original
SDK/deployed negative controls; zero failed expectations does not mean that
intentional timeout/stall scenarios have no watchdog faults. Stalls, hung cores,
tick scheduling, both transition directions and cores retain their prior oracles.

Under this model's ordering and ownership assumptions, no need for the final
disable check was demonstrated. The experiment does not show that the read-back
is essential to the normal synchronization protocol.

A separate synthetic probe changes stage0 to40 immediately after C stores max=0.
Current code aborts; without the check, the transition returns with a bad final
state. This deliberately violates the ordinary model assumptions. It establishes
lost diagnostic coverage only, not a plausible or observed hardware failure and
not an independent justification for retaining the check. The no-expiry calibration
shortcut is removed in this probe so the model actually checks its final state.

The check is therefore a defensive postcondition, a candidate for removal if
maintainers accept the ordering/ownership argument. This finding does not justify
removing the pre-write idle check, software retry bound, or enable failure path.
Those changes affect watchdog liveness and require separate fault scenarios.

Artifacts: .cache/iwdt-disable-check-comparison/, including generated variant,
per-variant model source/binaries, complete result matrices and fault traces.
No hardware access, flash or PR change was performed for this comparison.
