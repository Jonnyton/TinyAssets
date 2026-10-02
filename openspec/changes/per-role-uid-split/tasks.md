## 1. Design (this change)

- [ ] 1.1 Proposal, design and spec delta; uid map agreed with agent-loop and openshell-spike.
- [ ] 1.2 Cross-family security refute of the design (launcher surface, D2-D4).

## 2. Build (Codex implements; deploy-incident reviews and verifies)

- [ ] 2.1 `Dockerfile`: users and groups 1002 `ta-broker`, 1003 `ta-engine`, group 1100 `ta-work`.
- [ ] 2.2 `tinyassets/role_launcher.py`: root launcher with a static kind/argv table, a
      `SO_PEERCRED` check, `SCM_RIGHTS` fd passing, and capability drop on spawn; unit tests in the
      Linux oracle.
- [ ] 2.3 Entrypoint and compose: start as root with `cap_add: [SETUID, SETGID, CHOWN]`; the
      launcher starts the broker (1002) and the daemon (1001); the deploy validator's capability
      assertions are updated.
- [ ] 2.4 Volume migration (D4) under the exclusive layout lock, idempotent, with the temporary
      1001 read ACL on the vault directory.
- [ ] 2.5 Spawn sites go through the launcher client (`provider-cli`, `engine-mcp`,
      `node-sandbox`, `workspace-worker`).
- [ ] 2.6 `start_broker`: start the supervisor when the uids are distinct, and refuse otherwise.
- [ ] 2.7 Oracle proofs: a 1003 child gets EACCES on `owner.json`; the provider jail works under
      1003 with group workspace access.
- [ ] 2.8 Prod verification: per-role uids in `ps`, the broker serves one owner stream, and the
      measured RSS per stream; `deployed_sha` and canary.
- [ ] 2.9 Spec sync and archive.
