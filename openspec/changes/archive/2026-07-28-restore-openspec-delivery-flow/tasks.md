## 1. Review Gate

- [x] 1.1 Obtain and fold a Claude opposite-provider review of the research, proposal, design, delta spec, and task ceiling before implementation.

## 2. Inspector

- [x] 2.1 Add failing focused tests for change/task inventory, STATUS ownership, finish-first ranking, JSON parity, and read-only behavior.
- [x] 2.2 Implement the stdlib-only `scripts/openspec_flow.py` audit and named change-admission modes until the focused tests pass.

## 3. Cross-Provider Policy

- [x] 3.1 Add the bounded delta-first admission and finish-first rules to `openspec/config.yaml`, `AGENTS.md`, and the canonical OpenSpec skill.
- [x] 3.2 Sync provider skill mirrors and pass skill validation and cross-provider drift checks.

## 4. Verification and Foldback

- [x] 4.1 Run focused tests, strict OpenSpec validation, Ruff, diff checks, and an exact-diff independent review; adapt all blocking findings.
- [x] 4.2 Sync the delta into the main spec, archive this change, and retire its STATUS row in the landing lane.
