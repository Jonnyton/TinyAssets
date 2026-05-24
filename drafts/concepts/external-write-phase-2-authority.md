# External-write Phase 2 — real-write authority

**Status:** **shipped in PR-122 Phase 2 Slice 1.** Branch:
``claude/pr-122-phase-2-authority-idempotency-consent``. This file
records the requirements and the as-shipped Slice-1 implementation
shape. Future slices (Option B capability, multi-sink, wildcard grants)
will update this document in-place rather than spawning new design
notes.

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

### Option A — daemon-side env-sourced token (JSON map)

The host configures a single env var
``WORKFLOW_GITHUB_PR_CAPABILITIES`` containing a JSON map of
``{"<owner>/<repo>": "<token>"}``. The effector reads the map at
invocation time and looks up the destination by exact string match.
The token is **never** echoed into the merged run state the branch
sees. The branch knows that ``effects=[github_pull_request]``
*requests* a write; whether the daemon honors it depends on host
config the branch cannot observe.

Round-2 refinement (Codex P1.2): an earlier shape used a
per-destination suffix env name
(``WORKFLOW_GITHUB_PR_CAPABILITY_REPO_<OWNER>_<REPO>`` with non-alnum
runs collapsed to ``_``). That encoding collapsed distinct repos —
``octo/my.repo`` and ``octo/my_repo`` and ``octo/my-repo`` all
mapped to the same env name and therefore the same token. The JSON
map keys the lookup by the literal destination string, so distinct
destinations cannot collide unless the host explicitly wires the
same value to both keys.

Pros: simple, single env var, host can audit the map at a glance,
collision-free.
Cons: per-destination scope across many repos requires re-rendering
the map; revocation requires daemon restart.

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
columns ``(idempotency_hint, sink, evidence_json, run_id,
created_at, status)``. Primary key ``(idempotency_hint, sink)``;
secondary index on ``(status, created_at)``.

Round-2 atomic-reservation contract (Codex P1.1):

The round-1 sequence ``lookup → invoke → write`` was non-atomic; two
concurrent threads could both observe "no receipt" and both invoke
``gh pr create``. Round-2 requires every writer to call
:func:`try_reserve_receipt` BEFORE invoking the external side-effect.
The reservation uses ``INSERT … ON CONFLICT DO NOTHING`` so SQLite's
row-level lock answers "is anyone else doing this right now?" in one
round-trip. The reservation lives in a ``status`` column with values:

* ``pending``   — reservation held; the external write is in flight.
* ``succeeded`` — receipt is final; future calls dedup-hit.
* ``failed``    — invocation failed; the row remains so the caller
                  can decide whether to retry under the same hint.

After the side-effect lands the writer calls
:func:`finalize_receipt` to update the row to ``succeeded`` with
final evidence. On failure the writer calls
:func:`release_reservation` so a retry can re-acquire the hint.

Stale ``pending`` reservations (writer died mid-flight, never
finalized) are auto-reclaimed by :func:`try_reserve_receipt` after a
configurable threshold (default 10 min). After that, any retry under
the same hint can re-reserve; worst case is one duplicate PR if the
prior PR actually landed before the writer crashed.

``database is locked`` / ``OperationalError`` from SQLite is NEVER
silently treated as a miss — round-1 did that and it compounded the
duplicate-PR leak. Round-2 surfaces it as a structured
``error_kind="receipt_store_locked"`` evidence record so the operator
sees the lock state explicitly rather than firing duplicates.

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

Slice-1 status (all checked items shipped in this slice):

- [x] Re-introduce `_invoke_gh_pr_create` in
      ``workflow/effectors/github_pr.py``.
- [x] Add the capability-token check (**Option A — env-sourced JSON
      map**; the env var is ``WORKFLOW_GITHUB_PR_CAPABILITIES``
      decoded as ``{"<owner>/<repo>": "<token>"}``). Round-2
      replaced the round-1 per-destination suffix encoding to close
      the punctuation-collision finding (Codex P1.2).
- [x] Add the idempotency-store check before any `gh pr create` call,
      using the atomic ``try_reserve_receipt`` / ``finalize_receipt``
      / ``release_reservation`` seam (round-2 fix for Codex P1.1).
      Storage: ``workflow/storage/external_write_receipts.py``.
- [x] Add the `effector_consents` table + migration. Storage:
      ``workflow/storage/effector_consents.py``.
- [x] Add MCP actions to grant/revoke/list consent on the ``extensions``
      surface. Dispatch: ``workflow/api/extensions_consent_actions.py``.
- [x] Update `drafts/concepts/external-write-packet-shape.md` to add
      the `destination` field (also documents the new Phase-2 dry-run
      evidence shape and the idempotency dedup-hit shape).
- [x] Keep the runtime quarantine helper
      (``_quarantine_branch_authored_external_write_keys``) — independent
      of the authority gate and still correct.

Deferred to follow-on slices (NOT in Slice 1):

- [ ] Option B (per-run controller-minted capability) — kept design-only
      in §1. Migrate when paid-market / multi-tenant capacity grants
      make per-run scoping load-bearing.
- [ ] Wildcard / org-level consent grants — kept exact-match for Slice
      1. Refine once the chatbot's grant-list surface shows real usage.
- [ ] Multi-sink generalization (twitter_post, discord_message, etc.).
      The receipts + consent storage layers are already sink-namespaced;
      adding a second sink is one effector module + one chatbot
      action-dispatch arm.
- [ ] Optional remote-branch lookup (``gh api repos/{owner}/{repo}/
      branches/{name}``) as a pre-check before invoking ``gh pr create``.
      Slice 1 relies on the local receipt store; a future slice can
      add the remote check for cases where the receipt was lost
      (e.g. universe DB restored from a backup older than the PR).
- [ ] ``WORKFLOW_EXTERNAL_WRITE_ENABLED`` is **kept as a Phase-1 signal**
      in Slice 1 — Phase-1-shaped packets (no ``destination``) still
      observe it via the ``mode="dry_run_phase_1"`` evidence label.
      Retire / repurpose when no Phase-1 packets remain in the wild.

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
