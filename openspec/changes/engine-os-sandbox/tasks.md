# Tasks — universe engine OS sandbox

## 1. Freeze the seam and policy

- [x] 1.1 Audit every universe engine call and every local provider subprocess launch; record them in `design.md`.
- [x] 1.2 Specify the fixed namespace, mount, environment, failure, and Windows-development policies.
- [ ] 1.3 Run provider-context build checkpoint and re-check active file claims before touching source/tests.

## 2. RED: executable sandbox contract

- [ ] 2.1 Add focused tests for exact bwrap construction, minimal environment, and forbidden host mounts.
- [ ] 2.2 Add a fail-closed test proving an unavailable Linux probe refuses before provider invocation.
- [ ] 2.3 Add provider tests proving both Claude launch methods are wrapped and the tool denylist remains present.
- [ ] 2.4 Add a real-bwrap Linux escape test: outside secret unreadable, universe workspace writable.
- [ ] 2.5 Run the focused tests and record the expected failures before production code exists.

## 3. GREEN: fixed wrapper beneath existing controls

- [ ] 3.1 Implement `tinyassets/sandbox/engine.py` with fixed mounts, namespaces, sanitized environment, and explicit non-Linux development behavior.
- [ ] 3.2 Integrate the wrapper into `ClaudeProvider.complete` and `complete_json` without changing `_sandbox_cli_args` or the denylist.
- [ ] 3.3 Add the pre-routing Linux functional-probe gate to `_sandboxed_config` so the whole turn fails closed.
- [ ] 3.4 Run focused tests, then provider/universe/sandbox regression suites and Ruff.

## 4. Mutation and independent review

- [ ] 4.1 Revert the implementation in the worktree, run the focused tests, and record that each security regression goes red; restore the commit and re-run green.
- [ ] 4.2 Commit the final implementation and capture base/head SHAs.
- [ ] 4.3 Obtain Claude-family review that explicitly cites this brief, `universe_intelligence.py`, `providers/base.py`, both CLI providers, `api/branches.py`, the relay design note, and the reviewed base/head SHAs.
- [ ] 4.4 Resolve all blocking review findings and repeat focused/full verification if the SHA changes.

## 5. Draft publication only

- [ ] 5.1 Sync the accepted requirement into the canonical spec only when the change is ready to land; do not archive in this draft lane.
- [ ] 5.2 Push `feat/converse-os-sandbox` and open a DRAFT PR; include exact verification, cross-family verdict, rollout/auth prerequisite, and the verbatim proposed STATUS change.
- [ ] 5.3 Do not merge, deploy, or claim live acceptance.
