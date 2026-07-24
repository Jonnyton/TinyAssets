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

## 2026-07-23 — Operator-request contract refresh

What surprised me: the four-commit branch collapsed to one substantive OpenSpec commit after rebasing; every conflict was stale coordination, while current main independently preserved the unfixed runtime P1.

Pattern worth capturing: a planning-only PR should carry durable contract artifacts but no live spec-claim row. Runtime truth stays as a dated concern until a separate implementation lane produces evidence.

One thing I would do differently: compare the branch against current canonical capability owners before replaying coordination commits, because that makes it obvious which conflicts should resolve entirely to current main.

## 2026-07-23 — terminal deploy/rollback truth

What surprised me: structural workflow tests and actionlint both passed while an old rollback tail still mutated the image after terminal publication. Independent semantic review then found several cross-layer tuples that were individually valid-looking but jointly contradictory.

Pattern worth capturing: deployment truth needs one final-state invariant across shell outputs, the pure classifier, durable receipts, job exit status, and incident wording. Every dangerous path needs an executable cross-layer regression, not only syntax or token-order assertions.

One thing I would do differently: read the entire rendered step body immediately after the first green structural run, then derive tests from each post-publication mutation and each boundary-crossing tuple before asking for review.

## 2026-07-23 — fresh-host backup configuration

What surprised me: three active guides named three different rclone locations,
while the root-run unit never set the `HOME` override one guide relied on.

Pattern worth capturing: configuration truth spans the consumer, its service
identity, templates, and every runtime-linked runbook; checking only the
primary deploy guide leaves a believable but unusable path.

One thing I would do differently: start the contract test from the runtime's
actual environment and enumerate every linked guide before drafting the
write-set.

## 2026-07-23 — convergent host uptime installation

What surprised me: installing every unit was not sufficient for a fresh host;
the disk-rotation import closure and disabled-timer repair had independent
drift, while backup configuration required its own follow-up boundary.

Pattern worth capturing: a systemd installer should own units, executable
assets, configuration names, activation state, and rollback as one versioned
transaction. Existing content-addressed releases still need byte/mode checks.

One thing I would do differently: make the first fake systemd reject missing
units and inject a mid-stop failure, because permissive doubles hid the two
fresh-host rollback edges found later.
