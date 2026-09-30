# Tasks: account-storage-quota

Design approval gates task 2 onward. Task 1 is read-only and gates the numbers.

## 1. Ground truth

- [ ] 1.1 Measure what each test account holds today on production, per store in
      D3, read-only. Record the numbers here. If either account is above 1 GiB,
      return Q1 to the founder before enforcing.

## 2. Shape

- [ ] 2.1 `usage_policy`: storage in GiB (free 2, paid 20), with
      `TINYASSETS_{FREE,PAID}_STORAGE_GIB`. Delete the MB variables,
      `_universe_quota_kwargs` and the pool's universe-quota predicate. Update
      `environment-variables.md`.
- [x] 2.2 `universe_owner.py`: add the `universe_owner` table, written in the creation
      transaction(s), a backfill from stored bindings only (D2), `owner_of`,
      `tier_of` and `usage`. Coordinate with the seats-per-account lane so there
      is a single resolver.
- [ ] 2.3 `storage_accounting.py`: the store registry, `measurements`, `pending`
      and `seq`; `reserve` / `commit` / `release` / `touch`; the
      fresh-before-refuse rule; the bounded unmeasured allowance; and the
      single-flight sweep.
- [ ] 2.4 Attribution queries for the shared stores (run records, checkpoints,
      uploads, branches, commons) and their idempotent indexes. Add the
      completeness guard test over a populated data directory.

## 3. Enforcement

- [ ] 3.1 Workspaces (D6): fitted reservation with credit for the replaced
      generation, measure-before-publish, `publish_generation` requires a
      reservation, and lease-release measurement plus crash-window
      reconciliation by `lease_id`.
- [ ] 3.2 Gate files, project memory, UI library, pages (universe, commons and
      daemon wiki), uploads (including cross-owner delivery charged to the
      receiver) and branch/version writes (D7). Add the at-quota check on
      write-capable jail calls. Call `touch` on each delete path.
- [ ] 3.3 Build the refusal record and message (D8) through `upgrade_sentence`,
      with no link on the top tier. Prove that reads, the vault, sessions, chat
      and run records are never refused.

## 4. Prove and land

- [ ] 4.1 Tests:
      - An empty free account creates a small workspace.
      - Delete, then retry, succeeds without a `touch`.
      - Concurrent admissions can't overshoot.
      - A write that lands mid-scan is still counted.
      - The unmeasured allowance is bounded.
      - A shared universe charges only its owner.
      - One account's bytes are summed across its universes.

      Mutation-check each gate. Run the concurrency tests in the Linux oracle
      container.
- [ ] 4.2 Run a gpt-6-astra refute via `peer-agents` from this worktree, at most
      3 rounds. Then deploy, confirm with
      `python scripts/deployed_sha.py --assert-contains <sha>`, and run a live
      `ui-test` on a free account: a refused write that shows the Upgrade link,
      then delete and retry.
- [ ] 4.3 Sync the deltas into `openspec/specs/`, archive this change, and
      update `PLAN.md`'s usage-limit section (the founder approves PLAN.md
      edits).
