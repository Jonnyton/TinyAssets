# Reset integration decision pending (2026-09-19)

Root approved the bounded existing-fence integration on 2026-09-19. The additive
canonical storage remains dark until integrated tests and exact-head review.
This approval does not expand destructive reset authority to existing home DBs.

## Existing behavior, verified against this tree

- `scoped_reset._inspect_root_runs` blocks unknown root tables and owner queued
  or running runs. It does **not** cancel or interrupt those runs. A free run
  guard does not prove an orphan and cannot relax this refusal.
- `apply_test_identity_reset` acquires the existing exclusive maintenance
  barrier, revalidates the exact reviewed plan and filesystem identity, and
  creates a durable `scoped_reset_leases` fence plus operation/journal.
- It stages the home before atomically deleting planned author rows and setting
  `scoped_reset_operations.commit_witness=1`. Only then does it delete staged
  home data and finish the operation.
- `_recover_locked` restores staged home data for a pre-witness interruption;
  for a committed witness it finishes deletion and completes the operation.
- `prepare_service_writer_barrier` recovers first, then grants the shared
  service-writer barrier. Recovery ambiguity fails closed.
- Root run history is explicitly preserved by reset. Canonical conversation
  admissions are currently unclassified, so even an empty initialized table
  blocks reset. Merely adding the name to the allowlist is insufficient: the
  pending pair-write/flag crash window could restore cleared history later.
- Baseline `_walk_home_without_following:951-970` refuses every home `.db`
  (including `.conversation_memory.db` and its recognized SQLite sidecars).
  Preserve that refusal. A committed projection therefore remains reset-blocked,
  just as ordinary legacy conversation storage already was. The new root table
  must not break previously-supported empty/non-database homes, but this slice
  does not authorize deleting additional classes of home operational store.

## Approved smallest integration; implementation in progress

1. Canonical storage scopes take the **existing shared maintenance barrier**
   before the author writer, with bounded acquisition, and reject unresolved
   reset recovery. No separate lock manager or generation is introduced. No
   home directory is created by this fence.
2. Classify the new table only alongside an explicit, content-free reset-plan
   action: expire canonical conversation payloads for the exact reviewed owner
   and home. Preserve only scoped key/digest/run correlation identity; null
   intent, captured context and frozen terminal, replace `selection_json` with
   `{}`, clear the old conversation turn number, and mark
   `projection_state='expired'`. Selection mappings/install details are not
   necessary for conflict detection and must not survive by default.
   The action does not alter preserved run inputs/output or launch work.
3. After author reset commit/witness, but **before** staged home deletion and
   successful receipt completion, execute an idempotent runs-DB expiry under the
   same exclusive maintenance barrier. Recovery's committed-witness path repeats
   this action before cleanup. The operation already contains the home id and
   owner fingerprint; compare the existing `_principal_digest` of candidate
   owners scoped to that home. Do not introduce a raw identity in the journal or
   infer another user's identity from an unverified home.
4. Do not expire before the author witness: a pre-commit reset can roll back and
   must preserve the original conversation. A post-witness failure leaves the
   operation incomplete, and existing startup recovery blocks serving until
   expiry/cleanup finishes. A second DB transaction is deliberately a recoverable
   step, not claimed to be cross-database atomic.
5. Keep active-run blockers, exact plan validation, link protections, content-free
   evidence and reset's existing authority intact. No reset of real users is
   authorized for verification; tests use isolated temporary stores only.

## Required acceptance before activation

- New table with no affected records does not permanently disable valid reset.
- Queued/running canonical run still refuses reset; no cancellation side effect.
- Pending terminal without a home database expires on successful reset;
  same-key replay after a home recreation cannot restore old history or execute.
- A committed projection retains the baseline explicit home-database refusal;
  no new conversation-store deletion allowlist is introduced for this feature.
- Unrelated owner's admission stays byte-identical.
- Faults before witness restore original home/payloads; faults after witness but
  before expiry recover to expired. The pair-write/flag crash case remains
  protected by baseline home-database refusal, not a new destructive adapter.
- Two processes show reset excludes new admission/projection and bounds waits.
- Existing reset regression suite and Windows/Linux canonical storage cohort
  stay green. Exact-head independent review covers this irreversible behavior.

Approval is bounded to this existing reset authority; broad home-store reset
support would need its own separately reviewed contract and is not implemented.
