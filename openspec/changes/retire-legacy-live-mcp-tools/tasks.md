## 1. Migration evidence gates

- [ ] 1.1 Land and externally accept `reconcile-external-connector-manifests`; verify every supported manifest and submission packet names only its intended canonical or reviewed-directory surface.
- [ ] 1.2 Record the host-approved supported-client matrix and telemetry observation window in a durable retirement-evidence artifact before evaluating call data.
- [ ] 1.3 Collect hidden-name call telemetry for the full predeclared window; prove zero calls or identify and migrate every caller of `universe`, `community_change_context`, `extensions`, `goals`, `gates`, and `wiki`.
- [ ] 1.4 Complete and record a rendered chatbot conversation through canonical handles for every host in the approved client matrix.
- [ ] 1.5 Obtain independent interface/security review of the evidence and explicit host approval for the breaking removal.

## 2. Fresh ownership and caller inventory

- [ ] 2.1 Refresh `origin/main`, run provider-context and worktree scans, and rerun file-collision checks before claiming runtime files; resolve or depend on the owners observed in PRs #1560, #1550, #1549, #1493, #1478, #1467, #1466, #1465, and #1464.
- [ ] 2.2 Confirm PR #1561 remains limited to the separate legacy stdio server and PR #1553 remains limited to directory authorization; exclude `tinyassets/mcp_server.py` and `tinyassets/directory_server.py` from this change.
- [ ] 2.3 Inventory every repository import and direct Python caller of `universe`, `community_change_context`, `extensions`, `goals`, `gates`, and `wiki`; record a preserve-or-explicitly-migrate decision and focused coverage for each wrapper.

## 3. Failing contract and execution proofs

- [ ] 3.1 Add a failing contract test that inspects `universe_server.mcp` with listing middleware bypassed and requires the registered tool set to equal exactly the seven canonical handles.
- [ ] 3.2 Add failing canary tests showing that either an extra handle or missing `get_status` produces exit code 4 and names the precise drift.
- [ ] 3.3 Add a failing authenticated in-process MCP test that runs a deterministic no-provider branch through registered `run_graph`, extracts its durable run identifier, and reads the same run back through MCP `read_graph(target="run")` without stubbing registration, run creation, or run read-back.
- [ ] 3.4 Mutation-check the three new proofs: reintroducing one hidden registration, permitting missing `get_status`, or bypassing durable run creation must make the corresponding test fail.

## 4. Live registration retirement

- [ ] 4.1 Remove exactly the six legacy `_register_structured_tool` registrations from `tinyassets/universe_server.py` while preserving wrapper functions unless task 2.3 proves and tests an explicit caller migration.
- [ ] 4.2 Remove `_DeprecatedToolVisibility`, the legacy-name set, and dead registration-only state; add no compatibility alias or alternate hidden dispatch path.
- [ ] 4.3 Make the public canary compare against one exact seven-name set with required `get_status`; rename inaccurate internal `assert_five_handles*` identifiers without aliases while preserving the existing `--assert-handles` CLI.
- [ ] 4.4 Update the packaged runtime mirror and verify byte parity without changing the intentional `tinyassets/directory_server.py` reviewed surface.
- [ ] 4.5 Replace the canonical registered-tool metadata owner with the exact seven-row table; leave no retired-tool metadata residue.

## 5. Verification and review

- [ ] 5.1 Run the exact-registry, public-canary, authenticated MCP round-trip, structured-envelope, anonymous-challenge, and wrapper-caller focused suites on a clean current-main base.
- [ ] 5.2 Run plugin build/mirror parity, scoped Ruff, and strict validation of every active OpenSpec change.
- [ ] 5.3 Obtain an independent diff review that checks the exact six-name removal, absence of hidden dispatch alternatives, canonical behavior preservation, and directory/stdio scope boundaries.
- [ ] 5.4 Run and freshness-stamp the applicable §14 concurrent-client/load proof against the seven-handle server; if the existing harness does not cover this MCP change, add bounded simultaneous `tools/list` plus run/read sessions and prove no registry drift, cross-session leakage, or duplicate run creation.

## 6. Deploy, acceptance, and spec sync

- [ ] 6.1 Deploy the reviewed build and run `scripts/mcp_public_canary.py --assert-handles` against `https://tinyassets.io/mcp`; record the exact seven-name result and deployed source SHA.
- [ ] 6.2 Complete final rendered-chatbot `ui-test` acceptance through the live connector and save the prompt/result plus trace or screenshot evidence.
- [ ] 6.3 Check for post-fix organic user evidence; if none exists, record that explicitly and leave a concise STATUS watch item instead of claiming proven clean use.
- [ ] 6.4 Verify rollback to the prior image is available; if rollback occurs, record that hidden registrations returned and reopen the retirement gate before claiming green.
- [ ] 6.5 After implementation and acceptance evidence land, sync this delta into `openspec/specs/live-mcp-connector-surface/spec.md`, archive the change, and retire its STATUS claim in the same landing lane.
