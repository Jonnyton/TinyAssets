## Context

This change records and hardens the as-built credential-vault write seam after
cross-family review of the macOS vault-clobber fix. The boundary accepts a list
of validated records and writes one process-local JSON file through a fixed
sibling temporary path.

## Goals / Non-Goals

**Goals:**

- Preserve unrelated credentials during a one-record deposit.
- Match logical slots using the selectors consumed by current resolvers.
- Prevent shadowed VCS rotations and uncleanable same-slot duplicates.
- Preserve sibling fields across partial subscription deposits.
- Keep materialized Codex auth synchronized with a changed vault blob.
- Make intentional VCS capability narrowing visible without exposing secrets.
- State the bulk, empty, malformed-file, and concurrency boundaries exactly.

**Non-Goals:**

- Add cross-process locking, compare-and-swap, versioning, or a unique temporary
  filename.
- Add a social-credential resolver or infer account identity from unread fields.
- Add a repair path that overwrites a malformed existing vault.

## Decisions

- A one-record write to an existing vault is a read-modify-write upsert. Empty
  and two-or-more-record payloads remain exact replacement operations.
- Logical matching uses normalized effective service. API-key aliases share
  their resolved environment-variable slot; social and subscription records use
  one slot per service; VCS records additionally require exact destination and
  an overlapping normalized purpose set.
- Every match is collapsed to one record at the first matching position.
  Non-subscription types replace the whole slot. Subscription matches are
  field-merged in stored first-record precedence. When incoming fields target a
  Claude or Codex resolver alias family, stored members of that family are
  removed before incoming fields are applied, so a lower-priority incoming alias
  cannot be shadowed by a higher-priority stored alias.
- Malformed existing JSON fails the single-record write before the temporary
  file is written. This preserves fail-loud behavior rather than silently
  healing or discarding unreadable secret state.
- A non-empty Codex `auth_json_b64` value is decoded and compared with the
  materialized `auth.json`; differing bytes are replaced atomically even when a
  partial upsert preserves the configured Codex home.
- Every write summary includes a collapsed-record count and non-secret
  descriptors for VCS purpose selectors removed by an overlapping upsert.

## Risks / Trade-offs

- [Risk] Concurrent one-record deposits can lose an unrelated racing update
  because the operation is read-modify-write. → Keep the existing explicit
  no-serialization contract and do not claim a deterministic winner.
- [Risk] A single-purpose VCS rotation replaces an overlapping multi-purpose
  record and can remove its other purpose. → Prefer removal of the old token
  over silently retaining a shadowing compromised credential; callers that need
  both purposes must deposit both selectors, and removed purpose slots are
  reported in the write summary.
- [Risk] Social service-scoped matching supports one stored slot per service.
  → Do not invent unread identity selectors; expand the contract only when a
  concrete social resolver defines them.
