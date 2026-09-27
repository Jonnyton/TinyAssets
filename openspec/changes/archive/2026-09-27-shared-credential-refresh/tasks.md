## Tasks

- [x] 1. Add `tinyassets/credential_refresh.py`: the `refresh_credential(...)`
      primitive (thread lock, file lock, vault hold before the spend, re-read
      inside the locks, write under the hold) plus `RefreshRejected` /
      `RefreshUnavailable`.
- [x] 2. Rewire `ConnectionTokens._refresh_locked` onto the primitive, leaving the
      `oauth2` observable behaviour unchanged.
- [x] 3. Add `llm_subscription_credential_record(...)`, one builder stamping
      `deposited_at` and `last_refresh`.
- [x] 4. Add the subscription refresh: read the stored document's freshness, spend
      at the device-flow token endpoint with its client id, write back atomically.
- [x] 5. Renew the accepted source after a write so the provider binding follows
      the rotated record.
- [x] 6. Call the refresh before launch on the served and run launch paths, ahead
      of custody resolution.
- [x] 7. Recover a rotation the CLI made on disk: adopt a materialized home's
      document into the vault when its stamp is strictly newer. NOT from the
      launch copy -- that copy is sealed `0o400` and bound read-only into the
      jail, so it cannot hold a rotation (pinned by
      `test_the_sealed_launch_copy_cannot_hold_a_rotation`).
- [x] 8. Replace the stale-overwrite in `ensure_codex_home_from_vault` with the
      same newest-wins rule, keeping an owner's re-deposit landing on disk.
- [x] 9. Type a terminal refusal as `ProviderAuthenticationError` at the launch
      path, keeping transport failures transient.
- [x] 9b. Make a sign-in failure advance the turn: only a CAPACITY exhaustion
      did, so the fallback chain excluded auth exactly as suspected
      (`agent_turn_coordinator._next_after_signin`).
- [x] 10. Tests: two concurrent launches spend the refresh token once; a rotation
      made during a run is persisted; a stale copy never overwrites a newer one;
      an "already used" refusal falls back to the next allowed model in the same
      turn; no secret appears in any result, log or exception.
