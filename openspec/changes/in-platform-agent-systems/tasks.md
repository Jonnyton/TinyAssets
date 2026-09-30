# Tasks: in-platform-agent-systems

## 1. Build
- [ ] 1.1 Add `universe_file` and `universe_files` connector read targets: admin-only, no-follow, bounded. Add bridge `listFiles` and `readFile`.
- [ ] 1.2 Add the `app_event` event type (a named filter is required), `run_graph operation="emit_event"` with admission, and bridge `emit`.
- [ ] 1.3 Add the `publish` ask: validation, digest pins, a tab the platform writes. The answer path re-checks the digests, publishes the branches plus one definition, and is idempotent.
- [ ] 1.4 Update the served guidance: the `systems` and `interfaces` chapters name files, `emit`, the publish ask, and install-by-name.

## 2. Prove
- [ ] 2.1 Test through the real handlers and the shipped bridge, including cross-user refusals and the changed-after-shown refusal.
- [ ] 2.2 Mutation-check the admin gate, the path checks, the filter floor, the digest re-check and the served-cannot-answer rule.
- [ ] 2.3 Run a gpt-6-astra refute round on cross-user reach and consent.
- [ ] 2.4 Deploy and run `python scripts/deployed_sha.py --assert-contains <sha>`. The lead re-runs the naive request, and a second account installs.

## 3. Land
- [ ] 3.1 Sync the deltas into the three specs, then archive.
