## Context

The controller correctly refuses to steal live claims and correctly treats any non-empty unresolved `Depends` cell as a start blocker. The failure is upstream: refinery workers have been writing umbrella rows whose `Depends` cells include gates required only for final delivery (load proof, rendered acceptance, deployment, organic use). On 2026-08-01 the run reached 24 attempts, 41 refinable candidates, and zero completed implementation slices. The process remained alive, but it was producing coordination PRs rather than delivery.

## Goals / Non-Goals

**Goals:**

- Make the refinery describe the next executable slice, not the whole legacy change.
- Preserve collision, host-authority, review, and one-PR safety boundaries.
- Reject a `PARTIAL` refinery continuation unless its merged coordination change actually exposes claimable work in the assigned change boundary.
- Keep honest blockers while routing to a concrete autonomous prerequisite-removal slice when one exists.

**Non-Goals:**

- Let a refinery worker edit product code before normal claim admission.
- Treat host-only work, live foreign claims, or unresolved security decisions as executable.
- Automatically rewrite every existing `STATUS.md` row in one migration.
- Change cloud execution, public MCP behavior, or provider routing.

## Decisions

### 1. Preserve the two-stage refinery boundary

The refinery remains coordination-only. It analyzes the existing OpenSpec change and lands a reviewed row; the controller then performs ordinary current-main collision checking and claim admission before a fresh worker edits product files. This retains the safety boundary while fixing what the row represents.

Alternative considered: let the refinery worker immediately implement the slice. Rejected because the worker was dispatched without a durable implementation claim and could race another provider.

### 2. Model one row as one immediately next slice

The refinery brief will state that `Depends` contains only prerequisites that must land before the exact next slice can begin. Tests, review, deployment, rendered acceptance, and organic-use proof that happen after implementation remain in OpenSpec tasks or concise acceptance text. They do not block admission to earlier code work.

Alternative considered: change `claim_check.py` to interpret prose heuristically. Rejected because semantic guessing would silently weaken real blockers. The coordination producer must write the existing schema correctly.

### 3. Require autonomous blocker routing before `BLOCKED`

The refinery must inspect unchecked tasks for a slice of at most 12 tasks, preferably fewer. If that slice has a prerequisite, it must look for the shortest non-overlapping autonomous prerequisite-removal slice. `BLOCKED` remains valid only when both the direct slice and every concrete autonomous prerequisite slice are unavailable due to a live claim, host-only authority, policy/review gate, or unresolved dependency.

Alternative considered: keep walking every untracked change and record its complete blocker list. Rejected because it grows coordination state without opening execution capacity.

### 4. Validate refinery continuation from current-main claimability

After a refinery returns `PARTIAL` and its PR is verified merged, the supervisor will inspect current main. At least one `CLAIMABLE` row must overlap the assigned OpenSpec change boundary. Otherwise the result becomes an invalid refinery continuation and does not masquerade as a delivery handoff.

The validation is structural and deterministic: it uses classification plus symmetric file-atom overlap. It does not infer whether prose sounds actionable.

### 5. Make restart and merge-receipt intent durable before external work

Resume clears and persists the prior terminal timestamp before result recovery can call GitHub. The watchdog retains an explicit restart marker until the selected supervisor process is created and preserves a discovered unfinished run instead of overriding it with a fresh-run decision. Accepted verified `MERGED` and `PARTIAL` results both consume their canonical PR receipt for the bounded run; replay suppression preserves an existing failure strike for `PARTIAL` rather than laundering the budget through coordination.

## Risks / Trade-offs

- **Agent still chooses an over-broad slice** → The prompt gives exact row semantics and the controller rejects non-claimable continuations; independent review remains required.
- **A legitimate final-evidence-only change has no code slice** → It may remain honestly blocked or host-owned; the controller moves to a different candidate.
- **A concurrent provider creates an overlapping claim after refinery analysis** → Normal current-main admission rechecks collisions before product edits.
- **Existing bad rows remain blocked** → Subsequent refinery passes correct them incrementally; no unsafe bulk migration is attempted.

## Migration Plan

1. Land the prompt, continuation validator, regression tests, and canonical rule.
2. Restart the local watchdog/controller on the merged main head without stopping the tray permanently.
3. Observe a refinery coordination merge followed by a normally admitted implementation or prerequisite-removal worker.
4. Roll back by reverting the PR; the older coordination-only behavior is safe but low-throughput.

## Open Questions

None for this bounded recovery. A later throughput calibration may tune slice size from measured cycle time.
