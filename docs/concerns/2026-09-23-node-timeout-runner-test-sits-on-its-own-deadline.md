# A node-timeout runner test sits on its own wait deadline

September 23, 2026, measured on Windows at `1f121719` + the queued-deadline lane.

`tests/test_node_timeout.py::test_runner_emits_node_timeout_event_and_marks_run_failed`
calls `wait_for(outcome.run_id, timeout=5.0)` on a run that takes **4.4–5.5s**,
so the assertion budget straddles the observed duration. It failed once during
this lane's work and then passed 3/3; the unchanged tree at HEAD measured
5.06s / 4.85s and 3/3 passes, and the changed tree measured 4.70s / 4.41s —
i.e. slightly *faster*. The flake is pre-existing and unrelated to the change
that surfaced it.

The run itself is correct in every sample: status `failed`, error `Node
timeout: Node 'slow' exceeded 0s timeout`. Only the harness wait is marginal.

Not fixed here: raising the bound belongs with whoever owns the ~5s fixed cost,
and the interesting question is *why* a run whose node times out at 0.1s with a
0.5s provider takes ~5s at all. That fixed cost is unexplained and is the thing
worth investigating — the timeout value is the symptom. Do not "fix" this by
raising `timeout=5.0` alone without establishing where the 5 seconds goes.

Reproduce: run the test in isolation with `-p no:randomly`, several times.

## Re-measured after the worker-entry deadline guard (73e92e2d)

The round-2 correction adds a wrapper closure and one `time.monotonic()` call
to every `_run_with_timeout` submit, so the fair question is whether it pushed
this marginal test closer to its own bound. It did not: 3/3 passes at
**4.81s / 4.63s / 4.73s**, in line with the changed tree's earlier 4.70s/4.41s
and still under the unchanged tree's 5.06s/4.85s. The guard's cost is not
measurable here.

This does not retire the concern. The bound still straddles the observed range,
and the ~5s fixed cost is still unexplained — that remains the thing worth
investigating, not the timeout value.
