## Context

`_custody_reference_digest` hashes the record digest into the reference. Every authority record pins that reference: the custody row, the candidate and assignment `credential_reference_digest`, the work binding, the manifest digest and the receipt. When the bytes change, the reference changes, and renewal (`renew_accepted_source`, then `_reconnect_manifest`, then `bind_serving_provider`) republishes the whole chain. A probe of one refresh showed the agent revision, the assignment generation and digest, both members' binding generations and digests, the manifest digest, and the custody generation and reference all moving.

## Decision

Split identity from bytes at the custody layer. Receipts and bindings stay exactly as they are.

- **Reference digest v2**: `canonical({schema_version: 2, reference_id, owner_user_id, universe_id, service, generation})`. It contains no record digest.
- **Byte pin**: `llm_credential_custody.record_digest`, unchanged in meaning. `current_llm_subscription_custody` and `snapshot_llm_subscription_credential` keep refusing when the stored bytes' digest differs from the pin. Nothing launches on bytes nobody pinned.
- **Carry-forward**, only for a PLATFORM refresh (`refresh_before_launch`) of the exact pinned document. It is a single transition held under the refresh locks and the exclusive vault admission:
  1. Re-read the stored record.
  2. Require the locked record's digest to equal the custody pin.
  3. Spend the refresh token.
  4. Write the new bytes.
  5. In the same exclusive hold, compare-and-swap the custody row's `record_digest` from the old pin to the new one. The fence is `reference_id`, `generation`, `reference_digest` and the old `record_digest`, and the row must match the v2 formula exactly, so an intervening consent renewal can never be mistaken for this rotation. The depositor row must name the owner.
  6. Release.

  Readers never see bytes that disagree with the pin. A carry that succeeds bypasses `renew_accepted_source`. A carry that cannot apply falls back to renewal, as today: a v1 row, a moved pin, a fence mismatch, or an account change.
- **Account continuity**: the platform spent the refresh token of the exact pinned document at the issuer that minted it, so the lineage holds by construction. As a belt, the carry also requires the new document's identity-token `iss`/`sub` to be equal to the old document's wherever the new one carries them. `tokens.account_id` is not compared, because `_rebuild` copies every non-token key across unchanged, so it cannot differ. A mutation that deleted that comparison stayed green.
- **Disk adoption** (`adopt_newer_on_disk_document`) always renews. A CLI-rotated document in the materialized home cannot be tied to the pinned document: a document mixing account B's tokens with account A's retained identity token passes every freshness check (Codex shape review).
- **Owner deposit**: the deposit and its adoption always take a new generation, so they void in-flight receipts by design.
- **Byte checks kept explicit**: `current_llm_subscription_custody` compares the stored bytes' digest with the pin; the launch snapshot compares it before copying and again after, comparing the copied bytes' digest with the pin directly, because under v2 the reference no longer covers the bytes.
- **Migration**: v1 rows keep verifying. Custody reads and snapshots recompute both formulas from the stored row, require an exact match with the stored reference, and return that stored reference unchanged. Carry-forward requires an exact v2 match. A v1 row's first rotation renews, and the adoption then writes v2. Connection-grant custody keeps the v1 formula and is out of scope.
- **Acknowledged**: native-selection evidence keys `source_digest` on the reference, so it may survive an approved rotation for its existing five-minute window. It no longer attests exact bytes, and current-custody admission still refuses unpinned bytes.

## Why not carry receipts forward at each check

About 15 sites compare receipts, bindings and reservations to the current assignment. A lineage relation consulted at every one of them is a larger authority surface, and a missed site would silently keep voiding. Keeping the reference stable changes one module and two call sites.

## Risks

- Account identity is read from our own stored identity token, unverified. That is enough here, because both documents are ours and a rotation cannot change the issuer that minted it. A document with no readable identity renews.
- The in-memory custody object held by an in-flight launch still carries the old `_record_digest`. A launch that races a rotation between custody resolution and snapshot refuses with "credential changed before launch snapshot", unchanged from today.
