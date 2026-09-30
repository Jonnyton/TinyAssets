---
severity: P1
title: Nested provider waits can exhaust the reserve
filed: 2026-09-30
summary: A parent and child can hold all provider slots while a grandchild waits for a slot, with no slot-wait deadline to unwind the dependency.
---

Cross-family Claude review of PR #4136, merged-main code at 4454d904.
Verdict: DISAGREE_EVIDENCE. Static analysis; no end-to-end reproduction run.

`tinyassets/provider_admission.py` reserves headroom for `nested=True`, but
all nested depths share the same total ceiling. `run_graph` is a served tool
(`tinyassets/served_tools.py`); an agent child may invoke another graph, and
`tinyassets/providers/router.py` acquires a provider slot for each invocation.
With limit 2, an outer turn and its agent child can occupy both slots while
waiting for an agent grandchild that cannot acquire either. With default 6,
five outer holders plus one child produce the same shape. Active holders can
continue refreshing leases and polling their children. Removing the old wait
deadline removes its eventual refusal/unwind; user cancellation remains an
escape, not an autonomous completion path.

Needs a reproduction through the served nested-run path and a dependency-aware
execution design that preserves host memory safety and WAIT semantics. Do not
restore a refusal deadline or add a structural recursion cap as a workaround.
