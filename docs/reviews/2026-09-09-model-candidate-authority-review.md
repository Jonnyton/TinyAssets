# Candidate authority pre-build review

September9, 2026. Claude read-only review of source939931a9 and the proposed
authority seam, exit0 after284s. Verdict ADAPT; not schema/API/rollout approval.

## Lead disposition / next build gate

Accept a candidate manifest extending existing serving assignments and bindings,
one shared validator for execution/readiness, and separate preference order from
signed membership/spend constraints. Keep legacy v1 assignment digests unchanged.
The fixed two-attempt limit must not become a two-model product restriction;
resolve it with the authorized finite candidate set and existing resource bounds.
Do not mint a fresh carrier merely to bypass consumed authority.

The five pre-build blockers below remain to resolve against source and tests
before schema or authorization changes. In particular, inventory all unassign,
failed-assignment and disconnect paths; validate manifest/digest readback and
publication replay equality; specify attempt counting and in-flight generation
semantics. Preference reorder is not revocation. Access/constraint changes are.

The review's initial CLI restriction is a staging limit, not acceptance of the
owner's complete requirement: explicit selection of any discovered supported
CLI model still needs a request-local model override, independently distinguished
from legacy ignored definition.model fields. Do not enable those old fields
accidentally or claim source-only switching satisfies model selection.

Likewise, automatic discovery must be able to add eligible models without a
platform release, within an owner's already accepted connection/cost/privacy
scope. A manually curated provider-definition list is not the final catalogue.

## Independent verdict

Review complete. Findings first, then the one shape I recommend, then blockers and verdict.

## Assessment of authority-seam.md and design.md

**AGREE** with the reverified constraints. The code confirms each one:

- One assignment row per universe is structural, not incidental. The table's primary key is the universe id at `tinyassets/provider_assignment.py:956`, so a candidate set cannot be extra assignment rows.
- Per-fallback rebinding would be durable and carrier-breaking. Rebinding bumps the assignment generation, re-signs the binding, and updates the agent binding's provider_ref at `tinyassets/provider_serving_binding.py:560`. That revision bump would invalidate the in-flight carrier at the exact-agent check in `tinyassets/provider_assignment.py:1210`.
- Candidate bindings already have a home without any provider-work schema change. Serving binding ids are derived from owner, universe, provider name and class at `tinyassets/provider_work_authority.py:1591`. Every distinct provider name, including each api_key_http definition id, already yields a distinct serving-class binding.
- Custody for siblings on one connection is shared and idempotent. Re-adopting the same grant record returns the existing custody tuple, and only a real rotation bumps its generation, at `tinyassets/credential_vault.py:1204`. Two models on one connection therefore share one custody row and both fail together on rotation, which is correct.

**DISAGREE_CONCERN** with signing candidate order into the manifest. Design decision 1 says a preference change affects subsequent inference, not a running call. If order is inside the signed manifest, every reorder becomes a new assignment generation and a re-sign of every candidate binding, which invalidates in-flight turns. Order is not an authority property. Once every member's identity and cost constraints are signed, any order among members spends only what the owner already authorized. Sign the accepted set and constraints; keep order in the versioned policy.

**DISAGREE_EVIDENCE** with an unstated assumption that the existing served path can traverse more than two candidates. The per-request invocation cap is two, defined at `tinyassets/provider_assignment.py:29`, and it is consumed per request carrier regardless of binding at `tinyassets/providers/router.py:919`. A three-candidate fallback dies on the third attempt with a held error. This must be resolved before build.

**DISAGREE_CONCERN** with a third copy of the chain. The authorize function inlines its own copy of the chain that `_current_serving_authority` also implements. Adding candidate resolution to both separately, or in a new helper, would create drift between the powered and unpowered predicates, which the seam document itself forbids.

## Recommended shape

**Storage.** Two additive changes in the same SQLite database the assignment already uses. No change to the provider-work binding schema or the custody schema.

```
provider_assignments  (+2 columns, migrated in ensure_provider_assignment_schema)
  manifest_digest     TEXT    NOT NULL DEFAULT ''
  policy_generation   INTEGER NOT NULL DEFAULT 0   -- evidence only, never live-compared

provider_assignment_candidates  (new)
  universe_id, assignment_generation, position     PRIMARY KEY
  provider                         TEXT NOT NULL   -- 'claude-code' | 'codex' | 'api_key_http:<def-id>'
  binding_id                       TEXT NOT NULL   -- provider_work_binding_id(..., class='serving')
  binding_generation, binding_digest
  credential_reference_id, credential_reference_generation, credential_reference_digest
  constraints_json                 TEXT NOT NULL DEFAULT '{}'   -- metered flag + price ceiling
  candidate_digest                 TEXT NOT NULL
  UNIQUE (universe_id, assignment_generation, provider)
```

Manifest digest is computed over the sorted set of candidate identities: provider, binding id, custody tuple, and constraints. It must not include binding generation or binding digest, because those are only known after issue and the binding itself is signed with the assignment digest. This mirrors how the primary already works today. Position 0 is the primary and must equal the assignment row field for field; that check is enforced on every read.

Assignment digest gains a version branch. Empty manifest digest keeps the exact schema-version-1 payload at `tinyassets/provider_assignment.py:991`, so every stored legacy digest and every legacy binding's signed assignment digest remains valid. Non-empty manifest digest uses schema version 2 with the manifest digest as one more key. Because candidate bindings are issued with that version-2 assignment digest, each candidate binding commits to the accepted set it was issued under. Stale child rows cannot resurrect authority, since a leftover binding from an older generation fails the generation and digest equality in step 5 below.

**Publication transaction.** Extend `bind_serving_provider` with an optional tuple of accepted fallback provider names. Empty tuple publishes exactly today's path with no child rows, which is what keeps legacy pins fixed. Non-empty runs the same two-phase sequence over N candidates:

1. Resolve every candidate through the existing open-serving context or the subscription service map. Reject any candidate that carries a model field for a subscription CLI provider. Reject duplicates by provider name.
2. Pending phase, one transaction: adopt custody for all N, compute the manifest digest and version-2 assignment digest, write the deny-all pending row plus N child rows with placeholder binding digests, commit.
3. Ready phase, one transaction: re-read live custody for all N and verify each live grant, issue or rebind each candidate binding with the pending assignment digest, update the agent binding's provider_ref only if the primary changed, write the ready row and N child rows with actual binding generation and digest, assert every candidate's signed assignment digest equals the ready row's, commit.
4. Any failure writes the failed assignment as today. The replay early return must also compare the requested candidate set to the stored children, else fall through to rebind.

**Per-attempt validation in authorize.** Add one parameter, an attempt token of assignment generation, position, and provider name. All three must match the child row. The sequence is:

1. Carrier, source, role and operation checks, unchanged.
2. Exact agent check, unchanged.
3. Assignment anchor, structural only: ready state, owner equals principal, provider_ref equals assignment binding id. No custody read here.
4. Candidate resolution. Position 0 or empty manifest digest uses the assignment row itself, unchanged. Otherwise load children for that generation, recompute and compare the manifest digest, verify child 0 equals the assignment row, refuse any position above 0 when the manifest digest is empty.
5. Candidate binding: existing validate call with the candidate's binding id, generation, digest and provider, plus assignment generation and assignment digest equality against the binding.
6. Candidate custody: exact tuple against the child row, then live grant verification for HTTP or subscription custody for CLI. The primary's custody is never consulted when position is above 0.
7. Yield the authority for the candidate's provider and binding. Budget reservation then keys on the candidate binding, so each candidate has its own concurrency ceiling. Add position and assignment generation to the yielded authority for receipts.

Steps 3 through 6 should live in `_current_serving_authority` with the same candidate parameter, and authorize should call it instead of keeping its inline copy. The unpowered predicate then iterates candidates in policy order and returns the first that passes, plus a secret-free per-candidate status list.

**Primary revocation.** Grant revocation is a live fact detected in step 6, and the assignment row stays ready. So a revoked primary fails only at position 0 and independently authorized fallbacks proceed. Only an explicit unassign or a new generation tears down the manifest, which is the intended owner action.

**Generations.** Three counters, each with one job. Assignment generation changes when the accepted set, primary, or any constraint changes, and it invalidates in-flight turns fail-closed exactly as a rebind does today. Policy generation changes on reorder or per-turn current choice, is captured once at turn start, and is never live-compared inside authority. Binding revision on the carrier changes only when provider_ref changes, so adding or removing a fallback does not bump it, but the next attempt in an in-flight turn still fails on the assignment generation mismatch, which is the correct fail-closed outcome.

**Selection precedence.** The explicit saved choice is the primary and changes only through the owner's bind call. A per-turn current choice is a policy input that must name a manifest member or it is refused. Absent any choice, policy orders subscription and local members first, then eligible HTTP members. A per-turn failure never writes anything durable.

## Pre-build blockers and verdict

1. **Per-request invocation cap.** Decide whether authority-held attempts consume the cap and raise it to accepted-set size plus one, or cap manifest size at the current limit. Either way, a candidate refused at authorize time must not consume an invocation.
2. **Replay branch equality.** The early return in bind must include manifest equality, or a fallback change silently no-ops.
3. **Model on subscription CLI candidates.** Publication must reject a model field for claude-code and codex in this slice. HTTP models arrive only as definition-backed provider names with their own grant, so no connection-plus-model identity scheme is introduced.
4. **Read-side digest verification.** The store verifies the assignment digest on write only. The candidate path must recompute the version-2 digest and manifest digest on every read, since child rows are a second table.
5. **Unassign and disconnect paths.** Confirm every path that writes failed or unassigned also revokes or ignores child rows and their bindings, so nothing outside bind can leave a ready row with a mismatched manifest.

VERDICT: ADAPT. The proposed direction is sound and the seam is the right one. Adopt it with order moved out of the signed manifest, the candidate chain factored into one shared validator, and the five blockers above resolved before schema or API work.
