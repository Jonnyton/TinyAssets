## Review — workflow model-authority correction at `0325b840`

Read-only, no dispatch, no tests run, no provider calls. Source reasoning only.

---

## 1. What the code actually constrains

Four facts decide this design; everything else follows.

**(a) The aggregate budget already exists and is already provider-agnostic *in identity*.**
`provider_work_receipt_id` hashes `(universe_id, work_item_kind, work_item_id)` only — no provider (`tinyassets/provider_work_authority.py:1418-1429`), and the table enforces `UNIQUE (universe_id, work_item_kind, work_item_id)` (`tinyassets/storage/provider_work_authority.py:174`). Aggregate arithmetic sums *all* reservations for one receipt, charging settled rows at actuals and unsettled at reserved maxima, excluding `cancelled_before_launch`, against `receipt.max_invocations/max_tokens/max_cost_microunits`. Requirement 1 ("ONE aggregate work budget/immutable subject/claim") is **already satisfied structurally**. No new work ID, no per-node receipt, no separate table is needed for it.

**(b) The receipt record is nevertheless welded to one provider's binding.**
`binding_id TEXT NOT NULL` + `FOREIGN KEY → provider_work_bindings`, plus `binding_generation`/`binding_digest` `NOT NULL` (`storage/...:161-176`), and the dataclass carries `provider`, `credential_reference_digest`, `parent_binding_*` (`provider_work_authority.py:486-522`). `reserve_invocation` validates *that* binding is `ACTIVE` on every attempt. Bindings are provider-keyed by construction (`ProviderWorkBindingRoot(owner, universe, provider)`, `:109-119`; index `(owner_user_id, universe_id, provider, state)`, `storage:158-159`).

**(c) The reservation carries no provider and no model at all.**
`ProviderInvocationReservation` (`:912-934`) has receipt/claim/key/ordinal/operation/role/token/cost/actuals — nothing member-shaped. `ProviderInvocationCarrier.provider` therefore reads `self._receipt.provider` (`:1177-1179`).

**(d) So the router has nothing to select with.**
`cfg = replace(cfg, selected_model=getattr(served_authority, "selected_model", None))` (`providers/router.py:654`) and `chain = [invocation_carrier.provider]` (`:728`). On the carrier path `served_authority` is `None`, so selection is unconditionally cleared and the chain is the receipt's single provider. This is the exact seam where workflow selection dies — not in `_current_serving_authority`.

---

## 2. Decision: typed aggregate work authority. Reject the structural-anchor receipt.

The brief asks me to contrast the two. They are **not** symmetric, because per-attempt member facts on the reservation are required in *both* — that is not the axis. The axis is whether the receipt keeps naming an anchor binding.

**Structural-anchor receipt + per-attempt member facts — REJECT.** It avoids a table rebuild, and that is its only advantage. It keeps three hard dependencies on an unrelated credential:

1. `reserve_invocation` requires `receipt.binding_id`'s binding `ACTIVE`. Revoke the anchor's credential and *every* attempt fails, including one for an independently authorized member. This directly contradicts `connection-model-authority.md:78` ("Do not consult revoked primary custody before checking another accepted child") and the stated capability.
2. `_validate_receipt_parent` asserts `receipt.credential_reference_digest == assignment.credential_reference_digest` and `receipt.provider == assignment.provider == self._provider` (`foreground_run_provider.py:429-438`). Under a manifest, `assignment.credential_reference_digest` is the anchor's.
3. Aggregate ceilings are lifted from the anchor's binding (`foreground_run_provider.py:307-310, 362-364`), so a member with a *smaller* authorized ceiling is bounded by the anchor's larger one.

That is precisely "keep depending on anchor custody merely to satisfy old fields" (brief §4) and it hides provider dependence. Rejected on the brief's own criterion.

**Typed aggregate work authority — ADOPT.** The receipt's aggregate subject becomes the *assignment manifest*, which is a real signed artifact with a real digest and generation — not a fictional provider and not a manifest digest dressed as a credential.

---

## 3. Smallest honest representation

### `ProviderUniverseWorkReceipt` → **schema_version 4**

Add exactly two fields; make five existing fields conditionally absent.

| field | v1–v3 | v4 `authority_scope="provider"` | v4 `authority_scope="manifest"` |
|---|---|---|---|
| `authority_scope` | absent → read back as `"provider"` | `"provider"` | `"manifest"` |
| `manifest_digest` | absent → `None` | `None` | required, non-empty |
| `provider`, `binding_id`, `binding_generation`, `binding_digest`, `binding_revocation_generation`, `credential_reference_digest`, `parent_binding_*` | as today | as today | **`None`** — not the anchor's, not a placeholder |
| `assignment_generation`, `assignment_digest` | as today | as today | as today — already the correct aggregate fence |
| `max_invocations/max_tokens/max_cost_microunits`, `allowed_operations/roles`, `execution_subject`, lineage | unchanged | unchanged | unchanged |

`__post_init__` must reject `authority_scope="manifest"` with any member-shaped field non-`None`, and reject `"provider"` with `manifest_digest` set. Under manifest scope the aggregate ceiling is the manifest's signed constraint if present, else `min` over accepted members' binding ceilings — **never a union of maxima**.

**A work binding does *not* gain an aggregate variant.** `ProviderWorkBinding` stays v1, per-provider, per-custody, untouched. Any "aggregate binding" would have to put something non-provider in the provider-keyed identity — a fiction the brief forbids. The aggregate subject is the manifest; the manifest is not a binding.

### `ProviderInvocationReservation` → **schema_version 3**

Adds the per-attempt member and model facts (all `None`/`""` on v1/v2 read-back):

- `provider`, `member_binding_id`, `member_binding_generation`, `member_binding_digest`, `member_binding_revocation_generation`, `credential_reference_digest` — the accepted-member fence and its own custody
- `assignment_generation`, `assignment_digest`, `manifest_digest` — the fence as of reserve
- `model_id` (`""` = provider default; reuses `_native_default`'s existing empty-string convention at `providers/model_selection.py:145-161`, so no new sentinel), `model_scope` ∈ legacy/explicit/discovered, `executor_class`
- `discovery_source_digest`, `cost_caps`, `context_tokens` — the model/cost evidence, `None` when `model_scope == "legacy"`

This is where requirement 3 is satisfied, and it is the right home for an additional reason: the row becomes self-describing, so crash recovery can settle an orphaned `launch_started` attempt bound to the exact member without reconstructing anything.

### Carrier

`ProviderInvocationCarrier.provider` reads the reservation when scope is manifest; add `selected_model` exposing the sealed per-attempt facts. **No seal change is needed** — `_provider_invocation_carrier_payload` already serializes `reservation.to_dict()` (`:1291-1305`), so new fields are sealed for free. `_mint_provider_invocation_carrier`'s `exact` tuple (`:1359-1377`) gains: under `"provider"`, `reservation.provider == receipt.provider`; under `"manifest"`, `reservation.provider` non-empty and `reservation.manifest_digest == receipt.manifest_digest`.

---

## 4. Required SQL migration

**Reservations — additive `ALTER TABLE` only, no rebuild.** Add nullable `provider TEXT`, `member_binding_id TEXT`, `model_id TEXT` as queryable columns plus index `(receipt_id, member_binding_id)` for the per-member sum; everything else rides in `record_json`, as settlement facts already do. The precedent is exact and idempotent: `_ensure_invocation_settlement_columns` (`storage/...:218-234`).

**Receipts — table rebuild required, unavoidable.** SQLite has no `ALTER COLUMN`; dropping `NOT NULL` from five columns and relaxing the binding FK needs create-copy-drop-rename inside one transaction with `PRAGMA foreign_keys=OFF`/restore. Do not dodge this by writing anchor values into those columns for manifest receipts — that *is* the rejected option.

**Legacy readers fail closed today, verified.** `ProviderUniverseWorkReceipt.from_dict` resolves an unknown `schema_version` to `_FIELDS_V3` and then requires exact set equality (`:732-739`) — a v4 payload read by an older binary raises `ValueError`, it does not partially parse. Same for reservations: `_FIELDS_V1 if version == 1 else _FIELDS_V2` (`:1078-1080`) rejects a v3 payload. Preserve both properties; add no permissive default.

---

## 5. Transaction and lock ordering

Existing order is `provider_assignment_admission().shared(universe_dir)` → `store.connection()` → `BEGIN IMMEDIATE` (`foreground_run_provider.py:265-267, 495-497`). Keep it, and:

1. **Outside** both locks: `prepare_selected_model` / `prepare_selected_model_async` — it performs network discovery. Its own docstring already states this contract (`model_selection.py:96-99, 123-126`); it returns a `recheck` callable (`:243`).
2. **Inside** `BEGIN IMMEDIATE`, before `reserve_invocation`: re-read the assignment, revalidate the exact member via `_current_selected_member_authority`, then call `recheck()` (`assert_discovery_snapshot_current`). Snapshot, then revalidate under the fence — requirement 2.
3. Never hold the SQLite read transaction or a thread-owned admission lock across the discovery await.
4. Credential snapshot (`snapshot_llm_subscription_credential`, `foreground_run_provider.py:526-530`) uses the **reservation's** member custody, not `custody` from the anchor path.

---

## 6. Budget arithmetic (aggregate AND member)

- **Aggregate** (unchanged code path): `Σ charged_invocations < receipt.max_invocations`; `Σ charged_tokens + req.max_tokens ≤ receipt.max_tokens`; same for cost. Settled rows charge actuals, unsettled charge reserved maxima, `cancelled_before_launch` is excluded.
- **Member** (new, same rows): `req.max_tokens ≤ member_binding.max_tokens`, `req.max_cost ≤ member_binding.max_cost`, and `Σ charged_invocations WHERE member_binding_id = X < member_binding.max_invocations`. Computable from the reservations table with the new index — no second budget store, no per-node receipt.
- **Pre-launch refusals must not charge.** Member refusal, budget refusal or slot refusal has to settle `CANCELLED_BEFORE_LAUNCH` so the existing exclusion applies. This is what makes multi-member traversal affordable without inflating `max_invocations` — and it matches the already-reviewed sealed launch allowance in `connection-model-authority.md:113-128`. Reuse that decision; do not invent a second one.
- The per-attempt share `receipt.max_tokens // receipt.max_invocations` (`foreground_run_provider.py:508-516`) stays as the aggregate slice; the member ceiling is a separate `min`, not a replacement.

---

## 7. Replay, settlement, revocation

- **Replay is a pre-build blocker as written.** `reserve_invocation`'s idempotent-replay comparison checks only `max_tokens`/`max_cost_microunits` against the request. With v3 it must also compare `provider`, the member binding identity tuple, and `model_id` — otherwise a retry on the same `invocation_key` silently returns a reservation minted for a *different* member.
- **Arm-time revalidation.** `arm_launch` today validates the receipt's binding. Under manifest scope it must validate `reservation.member_binding_id` at both reserve and arm. Anchor revocation must not participate.
- **Settlement stays bound to the exact attempt** — `settle()` already routes through the sealed reservation (`:1217-1242`) and the router's `settle_carrier` already guards double-settle (`router.py:613-646`). No change needed; this seam is reusable as-is.
- **Recovery.** `release_run_claim` already cancels `state='reserved'` at terminal run (`storage/...:2403-2460`). Extend the sweep to settle stranded `launch_started` rows `INDETERMINATE` — the v3 row now names its own member, so this needs no reconstruction.

---

## 8. Seams reusable unchanged vs. genuinely new authority semantics

**Reuse unchanged** — do not copy, do not re-derive:
- `_current_selected_member_authority` and `_current_bound_member_authority` (`provider_serving_binding.py:850-919`). The landed inventory correction already exercises them for exactly this purpose (`:1214-1235`).
- `_current_serving_authority`'s manifest refusal (`:826-829`) — keep it, for legacy callers only.
- The carrier seal/consume/one-use machinery (`:1244-1259`, `1291-1403`).
- `prepare_selected_model` + its `recheck` callable, `SelectedModel.cost_upper_bound`/`affordable_output` (`model_selection.py:47-81`), and `order_models` policy enforcement.
- Settlement ownership and router settle-once.
- Aggregate reservation arithmetic.

**Genuinely new authority semantics** (and only these): receipt `authority_scope`/`manifest_digest`; reservation member+model fields; carrier provider/selection derivation; per-member budget arithmetic; the receipts-table rebuild.

**Call-site changes that are *not* new authority:**
- `declared - {assignment.provider}` (`foreground_run_provider.py:283`, `:474`) and `declared_providers - {assignment.provider}` (`background_served_provider.py`) must become "⊆ the accepted member set" under a manifest. This is what unblocks mixed-provider parallel nodes.
- `_validate_receipt_parent` (`:416-441`) splits: aggregate fence (assignment generation/digest/manifest digest, subject, principal/actor/universe/work id) stays on the receipt; the member comparison moves to the reservation inside `_authorize_attempt`. Lines 429 and 432-433 are the anchor dependence and must not survive under manifest scope.
- Router `:654` must take selection from `served_authority.selected_model` **or** `invocation_carrier.selected_model`, never from caller `cfg`; the `:669` provider-match check needs a carrier-side twin.

---

## 9. Structured disagreements

**DISAGREE_EVIDENCE — "The work-level receipt/claim remains the aggregate invocation/token/cost budget and immutable subject fence" (`workflow-selection-correction.md:80-82`) cannot hold while the receipt keeps its binding.** The receipt row is `NOT NULL`-bound to one provider binding with an FK (`storage/provider_work_authority.py:169-176`), and `reserve_invocation` requires that binding `ACTIVE` on every attempt. So "each invocation selects a currently accepted member under that same work budget" (`:83-85`) is unreachable without changing the receipt. The doc states the goal but does not name the decision that gates it. Pre-build blocker.

**DISAGREE_EVIDENCE — "Both workflow wrappers pass only the one-use invocation carrier to the router, not validated model selection … Do not replace the carrier with a caller-made authority" (`:63-66`).** The prohibition is right. The diagnosis is incomplete in a way that matters: the carrier *cannot* carry selection today because it derives every provider-shaped fact from the receipt (`:1177-1207`) and the reservation has no member or model fields (`:912-934`). The fix belongs on the reservation, and it costs nothing at the seal boundary because the seal already covers `reservation.to_dict()` (`:1291-1305`). Without naming this, an implementer will reasonably reach for the caller-made authority the doc forbids.

**DISAGREE_CONCERN — `max_invocations=len(nodes)` (`foreground_run_provider.py:361`) versus retries and multi-member traversal.** `_call_index` increments per attempt (`:482-484`), so each retry mints a fresh `invocation_key` and ordinal. One retry exhausts a run sized at one invocation per node; trying member B after member A fails costs two. The fix is the pre-launch-cancel rule in §6 plus the sealed launch allowance, **not** inflating `max_invocations` — multiplying per-node allowances is explicitly forbidden. Blocker for the mixed-provider gate specifically; harmless for single-provider runs.

**DISAGREE_CONCERN — native explicit models are out of reach and the capability statement will over-read.** `_selection_definition` refuses any provider not prefixed `api_key_http:` (`model_selection.py:180-181`) and `_native_default` requires `model_id == ""` (`:145-161`). "Select Opus for this node" on a subscription provider is not deliverable by this correction under any representation chosen here. `workflow-selection-correction.md:73-76` already says so; it needs to stay said, loudly, when this lands — otherwise a green suite reads as the full capability. Not a blocker on this design; a scope truth.

**AGREE — keep `_current_serving_authority`'s manifest refusal (`:826-829`) as a legacy fail-closed boundary.** Do not erase it globally. New callers get a manifest branch; the legacy branch keeps refusing.

**AGREE — the landed inventory correction at `0325b840` (`provider_serving_binding.py:1195-1239`) does what it claims.** It re-reads the binding after taking admission, iterates accepted members via the existing validator, accepts any still-current one without touching the anchor's credential, issues no receipt and performs no remote discovery, and rolls back its read transaction. It is an internal caller correction, correctly scoped, and it is not workflow selection.

**AGREE — requirement 1 needs no new storage.** Receipt identity and the `UNIQUE` constraint already forbid per-node receipts under invented work IDs.

---

## 10. Readiness

**The correction design is ready to implement as specified in §3–§7 of this review — not as specified in the change document.** `workflow-selection-correction.md:78-94` states the right goals and the right prohibitions but leaves the two decisions that determine the outcome open: whether the receipt keeps an anchor binding, and where member/model facts live. Those are answered above. The three items in §9 marked pre-build blockers (receipt scope, reservation replay comparison, invocation accounting under traversal) must be settled in the spec before code, not discovered during it.

**What this review does NOT prove.** I ran nothing: no tests, no ruff, no Linux oracle, no canary, no live or deployed evidence, no provider calls. I did not reproduce the two `test_run_provider_session.py` foreground-manifest failures — I read the seams they fail at and the claimed failure path is consistent with the source. I read the cited seams, not the whole 14k lines of the eight files. This reviews a design that does not exist yet and approves no unimplemented code; nothing here authorizes merging or deploying PR #3832, which stays draft. No user workflow, default, grant, credential or project was read or changed. This consumes the owner's one authorized additional review; I dispatched no sub-agent and will not.

VERDICT: ADAPT
