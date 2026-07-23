What surprised me: the deploy workflow already had nearly all facts needed for a release receipt; the gap was mostly that none of them were written into a machine-readable runtime artifact.

Pattern worth capturing: release observability should be deploy-published and status-read-only. That keeps `get_status` safe while still making live drift checkable by chatbots and local tools.

One thing I would do differently: start by adding the deploy workflow structure test before editing YAML, because this repo already has strong workflow-contract tests and they make the intended step ordering explicit.

## 2026-07-23 — MCPB staged catalog parity

What surprised me: the bundle already staged the canonical runtime correctly; the install break was entirely in stale manifest metadata and the absence of a semantic packaging gate.

Pattern worth capturing: package validation should compare the artifact’s declared catalog with middleware-visible behavior from the staged artifact itself. Comparing source constants or relying on a schema validator leaves room for silent product drift.

One thing I would do differently: identify the `--skip-probe` plus `--validate` escape path in the first red test, because a semantic gate is incomplete while the official validator can bypass it.

## 2026-07-23 — PR #1574 research archive

What surprised me: current main already had an independently approved paid-market
consumer of one research slice while the source reports themselves remained only
on a stale draft branch. Approval of a consumer must not be generalized into
approval of its source lane or architectural amendments.

Pattern worth capturing: archive dated research with its review verdict adjacent,
stamp the exact evidence checkpoint, and keep living design/coordination files out
of the archival commit. `ADAPT` is durable evidence and a gate, not a synonym for
approval.

One thing I would do differently: build the source-to-archive hash manifest before
creating the STATUS claim so the mechanical-copy proof and permitted header drift
are explicit from the first increment.

## 2026-07-23 — Provider-attempt receipt specification

What surprised me: the router already carries provider/model/family evidence, so the hard part is not provider discovery; it is preserving call-local attribution across the string bridge, retry waves, and the separate learning call.

Pattern worth capturing: an audit envelope needs two orthogonal terminal fields when fallback exists — how output completed (`outcome`) and why routing stopped (`route_condition`). Combining them makes missing-router fallback and exhausted-chain fallback ambiguous.

One thing I would do differently: model synthetic fallback and missing-router behavior before drafting the first enum list, because that boundary exposed the only internal contradiction found by the consistency pass.

## 2026-07-23 — rollback-safe full-volume restore

What surprised me: extracting with `--strip-components=1` into a `mktemp`
directory preserves file contents but silently replaces the Docker volume
root's access mode with `0700` unless ownership and mode are copied explicitly.

Pattern worth capturing: recovery tooling must fail closed at every discovery
boundary—archive metadata, Docker mountpoint resolution, and consumer
enumeration—before the first live rename.

One thing I would do differently: model the directory metadata and Docker
enumeration failure paths in the first test batch, alongside corrupt archives
and rename rollback.
