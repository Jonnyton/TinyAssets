---
status: active
---

# `extensions action=author_patch_notes` — MCP Wrapper

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Implements Step 1 of Task #66 migration path.
**Builds on:** Task #66 TypedPatchNotes dataclass (canonical construction surface); Task #53 route-back verdict (consumer); Task #69 storage-auth refactor (orthogonal — this action is read-only).
**Scope:** MCP action signature + validation flow. No code changes; no schema changes.

---

## 1. Recommendation summary

Add `extensions action=author_patch_notes` as the canonical construction surface for typed PatchNotes (#66). **Server-side construction:** chatbot supplies field values via MCP args; server constructs `PatchNotes` dataclass via `from_dict()`, validates per #66 §3, computes `patch_notes_id` content-hash, returns serialized form. Action is **read-only** (no persistent state writes).

**Top tradeoff axis:** **single-source-of-truth validation vs. cross-consumer redundancy.** Server-side construction wins because every consumer (route-back gate, sub-branch invocation, contribution event emit) gets validated payloads from one place. Chatbot-side construction would force every consumer to re-validate.

---

## 2. Action signature

```
extensions action=author_patch_notes
  summary <required, ≤200 chars>            # PatchNotes.summary
  rationale <required, markdown>             # PatchNotes.rationale
  affected_files_json <list[str]> = "[]"    # PatchNotes.affected_files
  tests_added_json <list[str]> = "[]"       # PatchNotes.tests_added
  evidence_run_id <optional str>             # PatchNotes.evidence_run_id
  evidence_refs_json <list[dict]> = "[]"    # PatchNotes.evidence_refs (typed)
  extra_json <dict> = "{}"                   # PatchNotes.extra
```

Returns success:

```json
{
  "patch_notes_id": "<12-char SHA-256 prefix>",
  "patch_notes": {<full serialized PatchNotes JSON>},
  "validation_status": "validated"
}
```

Returns rejection:

```json
{
  "error": "<human-readable summary>",
  "field_errors": {
    "summary": "exceeds 200 chars (got 312)",
    "evidence_refs[0].kind": "must be one of {wiki_page, node_def, branch_version, github_pr, run_artifact}"
  },
  "validation_status": "rejected"
}
```

`field_errors` is field-by-field with concrete reasons. Chatbots render these directly to the user without parsing free-text errors — better UX than monolithic strings.

### `*_json` suffix naming follows existing convention

`extensions action=patch_branch changes_json=...` and `extensions action=build_branch spec_json=...` already use the `*_json` suffix for list/dict args. This action follows the convention: `affected_files_json`, `tests_added_json`, `evidence_refs_json`, `extra_json`.

### Server-set `author_actor_id` — identity-spoofing prevention

The chatbot does NOT supply `author_actor_id`. The server reads `_current_actor()` and assigns it. Per #66 §2, `author_actor_id` is required (no anonymous default). Setting it server-side:

- Prevents identity-spoofing — chatbot can't pass `author_actor_id="someone_else"` to fake authorship.
- Matches existing patterns: `goals action=propose` reads `_current_actor()` for `goal.author`.
- Server is the authoritative identity source; chatbot supplies values but server attests provenance.

---

## 3. Tradeoff vs alternatives

| Axis | Server-side construction (recommended) | Chatbot-side construction |
|---|---|---|
| **Validation site** | One place (this action) | Three places (route-back gate, sub-branch invocation, ledger emit) |
| **Validation coherence as PatchNotes evolves** | One file to update | Three sites each maintaining own validation |
| **patch_notes_id consistency** | Server-computed, deterministic | Each consumer recomputes; risk of divergence on serialization round-trips |
| **Identity-spoofing surface** | Closed (server-set actor_id) | Open (chatbot constructs JSON with arbitrary actor_id) |
| **Chatbot-side payload size** | Smaller (chatbot sends fields, gets back hash + JSON) | Larger (chatbot owns JSON construction + serialization) |
| **First-use validation feedback** | Field-by-field structured errors | Per-consumer error messages (varies by call site) |

Server-side wins on every axis that matters at scale. Chatbot-side has only "no MCP round-trip needed" as a notional advantage — but in practice gates already require MCP calls; one extra call to author the patch_notes is amortized.

---

## 4. Validation flow

Per #66 §3, the two-layer discipline:

### Strict-at-emit (this action)

Server-side action handler:

1. Parse + decode JSON args (existing `patch_branch` pattern reuses this; see `_action_extensions_patch_branch` lines neighbor 6804).
2. Validate JSON shapes (e.g., `evidence_refs_json` decodes to list of dicts; reject malformed JSON with field-error).
3. Construct `EvidenceRef` instances from `evidence_refs_json` entries — `EvidenceRef.__post_init__` validates `kind` Literal + non-empty `id` + non-empty `cited_by`.
4. Set `author_actor_id = _current_actor()` server-side.
5. Construct `PatchNotes(...)`. `__post_init__` enforces #66 §3 rules (summary length, required fields, evidence_refs validity); auto-computes `patch_notes_id`.
6. Catch `ValueError` → translate to `field_errors` dict, return structured rejection.

### Strict-at-consume (downstream consumers)

When route-back gate, sub-branch invocation, or contribution event emit receives a PatchNotes payload, it MUST re-validate via `PatchNotes.from_dict()` per #66 §3 "two-layer discipline." Even though this action validated at construction, payloads cross trust boundaries (chatbot → engine, run → run, network → daemon) and may be tampered with or corrupted in transit. Re-validation at consumers is non-negotiable.

### Composition with #69 storage-auth (orthogonal)

`author_patch_notes` is **read-only**: constructs + validates + returns; no persistent state writes. Therefore does NOT need storage-auth check from #69. Distinguishes from write-side actions like `set_canonical_branch` which DO need storage-auth. Read-only authorization (no auth required to call) is correct here.

This is a useful boundary marker: write-side surfaces gate on storage-auth; pure-construction surfaces (like this) do not. Future surfaces can be classified by the same rule.

---

## 5. Composition with sibling proposals

### Task #66 PatchNotes — canonical construction surface

This action is the canonical construction surface for the dataclass; chatbots do NOT directly instantiate `PatchNotes`. Action handler imports from the location #66 §2 specified:

```python
from workflow.evaluation.patch_notes import PatchNotes, EvidenceRef
```

Future v2 of PatchNotes (per #66 §6 forward-compat) flows through this action without signature change — new fields land as optional args + new dataclass fields land at #66's update; this action's signature inherits via dataclass introspection or explicit args added at the same time.

### Task #53 route-back — consumer

Chatbot-side flow:
1. Chatbot calls `extensions action=author_patch_notes` once with the patch's content.
2. Server returns `{patch_notes_id, patch_notes, validation_status: "validated"}`.
3. Chatbot passes the `patch_notes` JSON into the gate evaluator's invocation per the route-back protocol.
4. Gate evaluator deserializes via `PatchNotes.from_dict(patch_notes)` (strict-at-consume per #66 §3), uses for routing decision per #53 §3 fallback chain.

The action does NOT trigger route-back execution — it only constructs the payload. Route-back invocation is a separate gate-side decision.

### Task #69 storage-auth — read-only orthogonal

As noted in §4: this action does not write persistent state, so storage-auth checks do not apply. Pure-construction surfaces are read-only; write-side surfaces gate on storage-auth.

### Task #48 contribution ledger — no event emitted

Per Q3 (rejection telemetry), `author_patch_notes` does NOT emit a `contribution_event`. Per #48's value-creating-only discipline:

- Successful PatchNotes construction is value-preparation, not value-creation. The PatchNotes flowing into a gate may LATER trigger `feedback_provided` events at the gate cite-time (#48 surface 5), but author_patch_notes itself emits nothing.
- Rejected calls similarly emit nothing — failures aren't ledger-eligible. Chatbots can render the `field_errors` to the user; the user retries.

---

## 6. Migration plan

### Step 0 — ship the action

`extensions action=author_patch_notes` lands. Existing chatbot patterns continue using opaque-dict path for route-back invocations (per #53 v1 + #67 §9 v2-amend backward-compat).

### Step 1 — gate evaluators preferentially consume PatchNotes

Route-back gate evaluators inspect incoming payload type:
- If incoming payload deserializes via `PatchNotes.from_dict()` → use typed path (cycle-detection via `notes.route_history`, evidence-refs via `notes.evidence_refs`, etc.).
- Otherwise (legacy opaque dict) → fall through to existing logic.

Backward-compat: chatbot can ship before or after gate updates. Mixed environments work.

### Step 2 — deprecation pressure

Once typed coverage > 80% of route-back invocations (telemetry via opt-in metric on the gate handler), emit deprecation warning when an opaque dict is consumed. Two-week sunset window. After sunset, opaque path raises structured error directing chatbot authors to `extensions action=author_patch_notes`.

### Rollback safety

If Step 0 surfaces a regression, drop the action handler. PatchNotes dataclass (per #66) stays; the typed flow falls back to chatbot-side construction (alternative path noted in §3 trade-off). No data loss; route-back behavior unchanged.

---

## 7. Open questions

1. **JSON args naming convention** — `*_json` suffix follows existing pattern (`changes_json`, `spec_json`). RECOMMENDED + closed per lead pre-draft note.

2. **`evidence_refs.cited_by` source** — chatbot-supplied (chatbot knows which evaluator is citing). RECOMMENDED + closed per lead pre-draft note.

3. **Rejected calls + ledger telemetry** — no event emitted. Read-only ledger discipline. RECOMMENDED + closed per lead pre-draft note.

4. **Idempotency** — pure function, deterministic `patch_notes_id`, no side-effects. RECOMMENDED + closed per lead pre-draft note.

5. **(Truly open) Forward-compat on `extra` field deserialization.** When a chatbot supplies `extra_json` with a key the future PatchNotes has lifted to a typed field (e.g., v2 promotes "priority" from extra to typed), how does this action handle deserialization? RECOMMENDED: passthrough — this action deserializes whatever the dataclass accepts; PatchNotes versions handle their own forward-compat per #66 §6 (extra dict + INFO-level warning for unknown keys).

6. **(Truly open) Authorization tier — public read or actor-required?** Today `goals action=propose` requires authenticated actor (since `_current_actor()` reads request context). This action sets `author_actor_id` from the same source. Anonymous calls would set `author_actor_id="anonymous"` — but #66 §2 forbids anonymous (required field). Recommend: action requires authenticated actor; reject anonymous calls with `validation_status: "rejected", error: "authentication required"` before construction. Closes the identity-spoofing-prevention loop AND ensures #66's no-anonymous invariant is enforced upstream of dataclass construction.

---

## 8. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No schema changes.** PatchNotes is in-memory + JSON-serialized in existing `metadata_json` columns per #66.
- **No new MCP tool.** Extends existing `extensions` tool with a new action.
- **No PatchNotes dataclass changes.** Per Task #66 §2 the dataclass is the canonical shape; this proposal only adds a construction surface for it.
- **No gate-evaluator updates.** The consumer-side preferential-typed-payload path is Step 1 of migration; ships separately.
- **No batch construction.** "Author 5 patch_notes in one call" is not supported; each call constructs one PatchNotes. Future feature if real volume emerges.

---

## 9. References

- Builds on: `docs/design-notes/2026-04-25-typed-patch-notes-spec.md` (Task #66) — provides the dataclass this action constructs.
- Consumed by: `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (Task #53 + #67 v2 amend §9) — route-back gates consume the PatchNotes payload this action produces.
- Migration sequencing: this action is Step 1 of #66 §6 4-step migration.
- Orthogonal (no auth check): `docs/design-notes/2026-04-25-storage-auth-refactor-proposal.md` (Task #69) — read-only actions don't gate on storage-auth.
- Orthogonal (no ledger event): `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48) — read-only construction doesn't emit events.
- Existing dispatch pattern reference: `tinyassets/universe_server.py:6804` (`extensions` action dispatch dict). New action registers alongside `build_branch`, `patch_branch`, etc.
- Existing JSON-arg pattern reference: `_action_extensions_patch_branch` (`changes_json` decode), `_action_extensions_build_branch` (`spec_json` decode).
- Authentication source pattern: `goals action=propose` reads `_current_actor()` for `goal.author`; this action does the same for `author_actor_id`.
- Convention adherence: `docs/design-notes/2026-04-25-design-proposal-pattern-convention.md` — this proposal follows the 5-move recipe (investigate → tradeoff → recommend → opens → SHIP).
