## 1. Inventory the As-Built Capability

- [x] 1.1 Verify the public canary, alarm sink, paging, watchdog, triage, deploy, backup, and DR paths against current `main` sources.
- [x] 1.2 Compare shipped behavior with `PLAN.md` and record every material gap as a non-normative limitation.
- [x] 1.3 Check neighboring canonical specs and keep their MCP, daemon-runtime, and community-loop contracts out of this capability.

## 2. Backfill Canonical Requirements

- [x] 2.1 Draft six as-built requirements with executable scenarios and source ownership.
- [x] 2.2 Replace the destructive Windows PID liveness probe and the Layer-2 sleeper subprocess with non-destructive platform querying and deterministic timeout injection; reserve full-file execution for external CI.
- [x] 2.3 Strict-validate the active change.
- [ ] 2.4 Add a path-filtered Windows CI job and observe it execute `tests/test_uptime_canary_layer2.py` externally.
- [ ] 2.5 Run focused canary, paging, watchdog, triage, deploy, backup, and DR regression tests; do not run `tests/test_uptime_canary_layer2.py` through Codex on Windows.
- [ ] 2.6 Sync the new capability into `openspec/specs/uptime-and-alarms/spec.md` and verify strict validation of all specs.
- [ ] 2.7 Archive the completed change after proving sync idempotence.
