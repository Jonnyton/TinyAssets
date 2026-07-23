What surprised me: the deploy workflow already had nearly all facts needed for a release receipt; the gap was mostly that none of them were written into a machine-readable runtime artifact.

Pattern worth capturing: release observability should be deploy-published and status-read-only. That keeps `get_status` safe while still making live drift checkable by chatbots and local tools.

One thing I would do differently: start by adding the deploy workflow structure test before editing YAML, because this repo already has strong workflow-contract tests and they make the intended step ordering explicit.

## 2026-07-23 — MCPB staged catalog parity

What surprised me: the bundle already staged the canonical runtime correctly; the install break was entirely in stale manifest metadata and the absence of a semantic packaging gate.

Pattern worth capturing: package validation should compare the artifact’s declared catalog with middleware-visible behavior from the staged artifact itself. Comparing source constants or relying on a schema validator leaves room for silent product drift.

One thing I would do differently: identify the `--skip-probe` plus `--validate` escape path in the first red test, because a semantic gate is incomplete while the official validator can bypass it.
