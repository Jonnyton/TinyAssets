# Ideas Index

Top-level map for idea capture, triage, and shipping traceability.

## Core

- [INBOX.md](INBOX.md)
- [PIPELINE.md](PIPELINE.md)
- [SHIPPED.md](SHIPPED.md)

## Idea Documents

Substantial ideas captured as their own dated file. This list is the only thing
that makes them reachable from the session-start scan, so every one of them is
listed here with its current state. Triage detail — review gates, next home,
owner — lives in the matching [PIPELINE.md](PIPELINE.md) row.

- [2026-07-15-democratized-compute-stack.md](2026-07-15-democratized-compute-stack.md)
  — harness→lithography creation ladder with four claim levels (designed /
  vendor-built / locally built / recursively self-hosted). Parent of the two
  below. **State:** host-approved direction plus a hard `$0` MVP constraint; no
  implementation authority, declared Claude-family review gate unmet, 6 open
  questions. Partly overtaken: the platform primitives it assumed are now spec'd
  as `openspec/specs/hardware-creation` and `pooled-training-ownership`
  (implemented in `tinyassets/paid_market/{shuttle,fabrication,pool}.py`), so
  what remains open is the product-proof layer, not the primitive layer.
- [2026-07-15-user-built-model-foundry.md](2026-07-15-user-built-model-foundry.md)
  — TinyAssets as an algorithm-agnostic training substrate: users define
  arbitrary architectures and train from random initialization, bounded by
  budget rather than a model menu. Carries the proof ladder and the
  scale-ready / resource-blocked honesty rule. **State:** host-approved
  principle plus the `$0` MVP constraint; implementation authority none until a
  specification is approved, `PLAN.md` foldback still owed, review gate unmet,
  4 of 5 open decisions unresolved. Its funding/contribution half is spec'd as
  `openspec/specs/pooled-training-ownership` and `paid-market-training`.
- [2026-07-15-conversational-cookbook-device.md](2026-07-15-conversational-cookbook-device.md)
  — two-screen voice-first kitchen appliance as the first physical artifact of
  the stack above; zero-purchase MVP-0 is a split-screen browser simulator.
  **State:** current default first-device candidate, superseding
  `docs/specs/2026-07-15-riscv-fpga-vertical-proof.md` (that spec self-marks
  paused). No implementation authority, review gate unmet, 3 of 4 open
  questions unresolved.
- [2026-07-19-agent-village-command-center.md](2026-07-19-agent-village-command-center.md)
  — phone-accessible live map of every agent working the repo, with universe
  sky-islands, a world/commons zoom, and a hire-an-agent flow. **State:**
  **shipped** as `command_center/` via PR #1489, 37 tests in
  `tests/command_center/`; recorded in [SHIPPED.md](SHIPPED.md). The document's
  own header still reads "design awaiting approval" and is stale. Deliberately
  deferred inside the shipped slice: market-rate/hosted compute hiring ships as
  a labeled-disabled affordance, and real daemon-roster creation waits on
  platform roster writes — both depend on the compute-market work in the
  democratized-compute idea above.

## Rules

- Capture raw thoughts quickly in `INBOX.md`.
- Triage and deduplicate in `PIPELINE.md`.
- An idea too large for an inbox bullet may be captured as its own dated file,
  `ideas/YYYY-MM-DD-<slug>.md`. It becomes reachable only when it is also listed
  under "Idea Documents" above with its current state and carries a
  `PIPELINE.md` row holding any review gate it declares. A dated file linked
  from neither is invisible to the session-start scan and is not build
  authority — it is a draft on disk.
- Promote larger ideas into `docs/exec-plans/active/`.
- Record landed results in `SHIPPED.md`.
- Provenance citations must resolve. When recording an idea's origin, cite a
  file and entry that exists on `origin/main`; a citation pointing at an entry
  that was never committed is a dead end for the next reader.
