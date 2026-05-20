# External-write Phase 2 — real-write authority (draft concept)

**Status:** draft / concept. Not a vetted spec. Descendant of PR-122
Phase 1; tracks the requirements that must be satisfied before the
GitHub PR substrate effector (and any future sink) may actually invoke
``gh pr create`` / equivalent side-effect.

**Why this doc exists.** PR-122 Phase 1 round-3 (PR #955) deliberately
cut the effector to dry-run-only at the code level. Round-2's
"idempotency_ack" public string was a self-mintable authority gate, and
Phase 1 had no idempotency store to back the ack's stated risk —
Codex's round-2 verdict (PR #955, 2026-05-20T06:46Z) caught both. Phase
2 must ship real authority before any real write fires.

Per the project's minimal-primitives doctrine, we will not ship a
half-baked authority surface. This doc captures the requirements; a
follow-on PR-122 Phase 2 will implement.

## 1. Capability-token problem

The core invariant: **a branch-authored output cannot mint authority.**
A workflow branch is user-composable; anything the branch sets in its
output state is, by construction, user-controllable. A capability key
embedded in run state is therefore equivalent to no key at all.

Two viable shapes for Phase 2:

### Option A — daemon-side env-sourced token

The host configures `WORKFLOW_GITHUB_PR_CAPABILITY` (or similar) at
daemon startup. The token is read by the effector at the moment of
invocation and is **never** echoed into the merged run state the branch
sees. The branch knows that effects=[github_pull_request] *requests* a
write; whether the daemon honors it depends on host config the branch
cannot observe.

Pros: simple, consistent with existing env-driven provider auth.
Cons: per-destination scope is awkward (one token for all repos),
revocation requires daemon restart.

### Option B — per-run capability minted by the run controller

The run controller (which knows the user identity + the branch's
declared destinations) mints a short-lived capability token at run
start, holds it in a controller-private side-channel (not in the
TypedDict reducer-merged state), and hands it to the effector at
completion time. Branch outputs never see the token.

Pros: per-destination scoping; revocable per-run; aligns with the
capacity-grant / control-intent / executor-backend split.
Cons: more plumbing; needs a side-channel store that survives
checkpoint resume.

**Recommendation:** Phase 2 prototype with Option A (env-sourced) to
land real writes quickly; design Option B in parallel and migrate when
per-destination scoping becomes load-bearing (paid-market, multi-tenant
daemons).

## 2. Idempotency store

Before invoking `gh pr create`, the effector must answer:

1. **Does a remote branch with this deterministic head_branch already
   exist?** Query `gh api repos/{owner}/{repo}/branches/{name}`. If
   yes, look up the open PR for that branch and return its
   ``pr_url`` / ``pr_number`` as evidence rather than creating a new
   one.
2. **Does our local idempotency store have a prior run that already
   produced a PR for this packet's `idempotency_hint`?** Keyed by
   `(universe_id, idempotency_hint)`. If yes, return the recorded
   ``pr_url`` / ``pr_number`` from the prior run.

Storage: a per-universe SQLite table `external_write_receipts` with
columns ``(idempotency_hint, sink, evidence_json, run_id, created_at)``.
Indexed on `(idempotency_hint, sink)`.

Mutation contract: writes are **append-only with last-write-wins on
the same hint** so retried runs can update if a stale receipt is
detected. Reads return the most recent receipt.

## 3. Per-destination consent surface

The user must explicitly grant: *"this universe's effectors may write
to repo `owner/name`"*. Without that grant, even with capability token
present, the effector returns dry-run.

Where the grant lives:

- A per-universe consent table `effector_consents`, columns
  ``(sink, destination, granted_at, granted_by, revoked_at)``. Reads
  filter `revoked_at IS NULL`.
- Surfaced via an MCP action (`extensions action=grant_effector_consent`
  or similar) that requires interactive user confirmation in the
  chatbot — the chatbot composes the consent request; the daemon
  records the grant.
- Revocation: `extensions action=revoke_effector_consent` flips
  `revoked_at`. Future invocations dry-run.

The packet's `destination` field (added in Phase 2) must match a
granted row exactly. No wildcard grants in v1; that's a Phase 3
refinement once we see real grant-list shape.

## 4. Phase 1 → Phase 2 migration checklist

When Phase 2 lands the changes above:

- [ ] Re-introduce `_invoke_gh_pr_create` (or equivalent) in
      ``workflow/effectors/github_pr.py``.
- [ ] Add the capability-token check (Option A or B; pick at landing).
- [ ] Add the idempotency-store check before any `gh pr create` call.
- [ ] Add the `effector_consents` table + migration.
- [ ] Add MCP actions to grant/revoke consent.
- [ ] Update `drafts/concepts/external-write-packet-shape.md` to add
      the `destination` field.
- [ ] Migrate ``WORKFLOW_EXTERNAL_WRITE_ENABLED`` from "Phase-2 hook
      signal" to "actual write enable" (or retire entirely if Option B
      makes it redundant).
- [ ] Keep the runtime quarantine helper
      (``_quarantine_branch_authored_external_write_keys``) — it is
      independent of the authority gate and remains correct.

## Reference

- PR #955 (PR-122 Phase 1, branch
  ``claude/pr-122-phase-1-effects-attribute-github-pr-effector``).
- Codex round-2 verdict on PR #955, comment timestamp
  2026-05-20T06:46:08Z — the design driver for this doc.
- ``drafts/concepts/external-write-packet-shape.md`` — the canonical
  packet shape Phase 2 extends.
- AGENTS.md hard rule #8 (fail loudly, never silently) — informs why
  receipts are system-authoritative.
- Project memory:
  ``project_minimal_primitives_principle.md`` (don't ship half-baked
  primitives).
