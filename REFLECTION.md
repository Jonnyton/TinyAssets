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

## 2026-07-23 — hardened DR drill evidence

- **What surprised me:** the first live drill failure was not a restore failure
  at all; `curl -sf` erased the provider response before provisioning, and the
  previous PASS ordering could have hidden a later cleanup failure.
- **Pattern worth capturing:** recovery evidence is a state machine, not a
  collection of successful steps. Bind one artifact by digest across every
  boundary, encode path metadata crossing workflow protocols, and publish PASS
  only after cleanup reaches its terminal success state.
- **What I would do differently:** model provider API failures and resource
  deletion as explicit tested states in the first proposal, including request
  timeouts and adversarial output fields, instead of adding them after the
  happy path is sketched.

## 2026-07-23 — provider-inventory DR selection

- **What surprised me:** once API diagnostics became truthful, the next outage
  was provider inventory drift rather than restore logic; a retired base-image
  slug stopped the drill before it could test recovery.
- **Pattern worth capturing:** provider inventory should be resolved from a
  bounded, schema-validated catalog before any mutation, with pagination and
  the resolved identity retained in terminal evidence.
- **What I would do differently:** include pagination, exact provider field
  semantics, permission prerequisites, and provenance in the first selector
  design instead of treating a large first page as the whole catalog.

## 2026-07-23 — bootstrap checkout ownership

- **What surprised me:** the obvious exact-path `safe.directory` fix still
  granted root trust to a service-user-writable repository; independent review
  also exposed the separate interrupted-clone rerun path.
- **Pattern worth capturing:** privilege-sensitive convergence must model every
  ownership state, including partial prior runs. Run repository tools as the
  current owner instead of weakening their trust guard, then validate immutable
  identity before a privileged installer consumes it.
- **What I would do differently:** enumerate fresh, completed-repeat, and
  interrupted-repeat ownership states before drafting the first design, and
  treat a security guard failure as a boundary signal rather than an obstacle
  to bypass.

## 2026-07-23 — DR runtime-image pin

- **What surprised me:** a daemon-only Compose start still validates required
  image interpolation across the complete compose model, while the fresh-host
  template correctly leaves that image empty.
- **Pattern worth capturing:** recovery inputs need distinct authorities and
  evidence names. The provider base image comes from bounded live inventory;
  the daemon runtime image comes from validated immutable production
  configuration; neither should be conflated or sourced from a mutable tag.
- **What I would do differently:** model Compose interpolation and the
  quoted/unquoted environment grammar in the first DR test matrix, and design
  the minimal nonsecret configuration transfer before the first live run.

## 2026-07-23 — DR fresh-env startup truth

- **What surprised me:** a successful Compose command and a green GitHub job
  both concealed a red recovery outcome—the container restart-looped because
  interpolation did not populate its env file, and the probe step emitted red
  outputs before ending on a successful shell command.
- **Pattern worth capturing:** recovery workflows need two truth checks:
  resource/service evidence must reach the process boundary, and structured
  red evidence must be followed by an explicit terminal failure. Cleanup tools
  should verify resource identity, not trust a numeric ID alone.
- **What I would do differently:** test failed-step `if: always()` semantics
  and container-visible environment separately from Compose model validation
  before the first live drill.

## 2026-07-23 — shared in-node enqueue caps

- **What surprised me:** boundary tests aimed at lock correctness also exposed
  authority bugs in run scope, universe identity, private visibility, and
  corrupt-history handling.
- **Pattern worth capturing:** concurrency proof must test the authority used
  to choose the lock, budget, and target—not only the atomicity of the lock.
- **What I would do differently:** map cap scope, physical storage identity,
  and request authority before the first implementation pass, then make those
  boundaries the first independent security-review checklist.
