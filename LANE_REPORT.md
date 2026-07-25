# Control Station Canonical-Handle Reconciliation

Date: 2026-07-25
Branch: `codex/osx-control-station`
Rebased base: `origin/main` at `8ec01ab34802f349d4ca97527c0aaed0633da11c`
Fold commit: recorded in this branch's git history

Authority: `openspec/specs/live-mcp-connector-surface/spec.md`, especially
“Remote Streamable-HTTP MCP Endpoint” and “Canonical Advertised Handle Set.”
The invariant derives the visible set from the middleware-filtered live
registration (`mcp.list_tools(run_middleware=True)`), not from a copied list.
`scripts/mcp_public_canary.py::CANONICAL_HANDLES` independently agrees with the
observed set.

## Surfaces found

The public `tinyassets.universe_server` FastMCP server owns these instruction
surfaces:

1. `FastMCP(..., instructions=...)` in `tinyassets/universe_server.py`.
   It names `converse`, `get_status`, and the `control_station` prompt; it now
   preserves relay-first opening, status-as-evidence, universe isolation, and
   thin-relay behavior without a tool-count claim.
2. Registered prompt `control_station`: wrapper/description in
   `tinyassets/universe_server.py`, body `_CONTROL_STATION_PROMPT` in
   `tinyassets/api/prompts.py`. This was the main contradictory catalog and
   routing surface; it now catalogs every live advertised handle and no hidden
   fat tool.
3. Registered prompt `meet_universe`: wrapper/description in
   `tinyassets/universe_server.py`, body `_MEET_UNIVERSE_PROMPT` in
   `tinyassets/api/prompts.py`. Its registered description now agrees with its
   relay-first `converse` body; hidden brain-write and engine-action calls were
   removed.
4. Registered prompt `extension_guide`: description/body in
   `tinyassets/universe_server.py`. Existing-workflow inspect/edit/run guidance
   now uses `read_graph` / `write_graph` / `run_graph`; new registration is
   named as a residual gap.
5. Registered prompt `branch_design_guide`: wrapper/description in
   `tinyassets/universe_server.py`, body `_BRANCH_DESIGN_GUIDE` in
   `tinyassets/api/branches.py`. It now uses executable canonical examples with
   required branch/run identifiers and reports missing authoring/run controls.

The Claude plugin runtime copies of the three canonical source files are
generated deployment mirrors, not independent authoring surfaces. They were
refreshed with `python packaging/claude-plugin/build_plugin.py` and verified
byte-identical to the canonical files.

`tinyassets/mcp_server.py` was also located. It is a separate local daemon-file
FastMCP server with its own registered tools (`get_status`, `get_progress`,
`add_note`, etc.), not the public `universe_server.py` endpoint governed by the
live-connector spec, so its instruction string was intentionally excluded from
the seven-handle invariant and left unchanged.

The external onboarding change directory
`openspec/changes/repair-first-contact-onboarding/` and its branch were not
edited.

## Red/green invariant evidence

- RED, before production edits:
  `python -m pytest tests/test_mcp_instruction_surfaces.py -q`
  → `1 failed, 1 passed`. `prompt:control_station` claimed hidden tools
  `community_change_context`, `extensions`, `gates`, `goals`, `universe`, and
  `wiki`.
- Review-driven RED:
  the same file produced `2 failed, 2 passed` for the stale
  `meet_universe` description and branch reads missing `branch_id`/`graph_id`.
- Parameter-completeness RED:
  the generalized graph-target test produced `1 failed, 3 passed` for a run
  read missing `run_id`/`graph_id`. It now covers semantic companions for
  read-goal/branch/run and write-goal/branch/request examples.
- GREEN invariant:
  `python -m pytest tests/test_mcp_instruction_surfaces.py -q`
  → `4 passed` (12 upstream FastMCP/Python 3.14 deprecation warnings).
- GREEN post-rebase touched-test run on Windows:
  `python -m pytest tests/test_continue_branch.py
  tests/test_control_station_degraded_mode.py
  tests/test_goals_discoverability.py
  tests/test_mcp_instruction_surfaces.py
  tests/test_node_reuse_discovery.py tests/test_persona.py
  tests/test_universe_server_framing.py
  tests/test_universe_server_metadata.py -q`
  → `101 passed` (12 upstream deprecation warnings).
- GREEN post-rebase lint:
  `python -m ruff check` on every touched canonical, generated, and test file
  → `All checks passed!`
- GREEN post-rebase packaging:
  `python packaging/claude-plugin/build_plugin.py`
  → staged 267 files; `Import probe: probe-ok`.
- Independent read-only review found three parameter/description defects during
  iteration; all were fixed test-first. Final re-review: no remaining blockers.

## Old routing row → canonical mapping

| Old control-station row | Canonical route | Result |
|---|---|---|
| See what is happening (`inspect`) | `get_status`; `read_graph target="graph"` for a universe | Mapped |
| Design/build a new workflow (`build_branch`) | No advertised create target | Residual: new workflow creation |
| Edit/refine a workflow (`patch_branch`) | Read with `read_graph target="branch" branch_id=...`; write with `write_graph target="branch" branch_id=... changes_json=...` | Mapped |
| Create/remix/copy a skill | Existing branch: `write_graph target="branch" branch_id=... changes_json=...` | Partial; new-branch skill authoring is residual |
| Pick up/continue/resume from a run | Discover/read with `read_graph target="runs"` then `read_graph target="run" run_id=...` | Partial; resume-from-run is residual |
| Surgical single-item branch change | One-op `changes_json` through `write_graph target="branch" branch_id=... changes_json=...` | Mapped |
| Run/execute a workflow | `run_graph branch_def_id=...` | Mapped |
| Review live community PRs | No advertised review-context handle | Residual |
| Inspect/list a registered workflow | Known branch: `read_graph target="branch" branch_id=...`; current universe overview: `read_graph target="graph"` | Partial; global branch enumeration is residual |
| Declare what a workflow is for | `write_graph target="goal" name=...` | Mapped |
| Find existing Goals/prior art | `read_graph target="goals" query=...` (or omit query to list Goals) | Mapped |
| Bind a workflow to a Goal | No advertised binding route | Residual |
| See who built for a Goal | `read_graph target="goal" goal_id=...` | Mapped |
| Compare workflows on a Goal | No advertised leaderboard route | Residual |
| Find reusable nodes (`common_nodes` / `search_nodes`) | Inspect known candidates with `read_graph target="branch" branch_id=...` | Partial; global/cross-Goal search is residual |
| Submit collaborative input | `write_graph target="request" text=... idempotency_key=...` | Mapped |
| Give direct daemon guidance | Same request route plus `directed_daemon_id` and `directed_daemon_instruction` | Mapped |
| Capture daemon memory | No advertised route | Residual |
| Search/list daemon memory | No advertised route | Residual |
| Review/promote daemon memory | No advertised route | Residual |
| Check daemon-memory status | No advertised route | Residual |
| Query world state | No advertised route | Residual |
| Read produced output | Run output: `read_graph target="run" run_id=...` | Partial; general non-run output read is residual |
| Browse canon documents | Known/shared page: `read_page page=...`; search: `read_page query=...` | Partial; canon enumeration is residual |
| Browse uploaded source documents | No advertised route | Residual |
| Read an uploaded source document | No advertised route | Residual |
| Create a new/additional universe | `write_graph target="universe"` | Mapped |
| Switch active universe | Pass explicit `graph_id` on scoped calls | Partial; persistent active-universe switch is residual |
| Pause/resume daemon | No advertised control route | Residual |
| Read reference knowledge (`read` / `search` / `list`) | `read_page page=...` / `read_page query=...` | Partial; list/enumeration is residual |
| Save reference/how-to notes | `write_page page=... content=...` | Mapped |
| Promote a wiki draft | No advertised route | Residual |
| Check wiki health/lint | No advertised route | Residual |

Additional old instruction routes were reconciled as follows:

- Defect/change filing: `write_page kind="bug|patch_request|feature|design"`.
- Private identity/canon writes: relay through `converse`; never write the
  universe’s brain from the connector.
- Visual branch/run reads: canonical `read_graph` targets with required IDs.
- Cross-universe re-anchoring: explicit graph IDs through canonical reads.
- New-node reuse: inspect known branches before inventing; do not claim global
  search completeness.

## Named residual gaps for retire-legacy blockers

1. New BranchDefinition / standalone node registration and new-branch skill
   creation.
2. Global branch enumeration, global node search, and cross-Goal common-node
   discovery.
3. Resume-from-run/continue, wait, stream, cancel, and field-only run-output
   controls.
4. Community PR/change-review context.
5. Goal bind and Goal leaderboard/compare operations.
6. Daemon-memory capture, search/list, review, promote, and status.
7. World-state query and general non-run output reads.
8. Canon enumeration; uploaded-source list/read.
9. Persistent active-universe switch.
10. Daemon pause/resume/control and dedicated treasury/ledger summary.
11. Wiki `list` enumeration, promote, lint, and bug cosign.
12. Engine assignment/power-source configuration.

These gaps remain capabilities of hidden legacy dispatchers in some cases, but
the prompts now state the advertised-surface limitation instead of instructing
the model to call a non-advertised tool.

## Deploy-time acceptance (Hard Rule 11)

This is a public MCP-surface change. Before final acceptance after deployment,
run the public canary with `--assert-handles` and complete a rendered chatbot
conversation through the live connector following the `ui-test` skill. Those
are deploy-time steps and were not performed in this branch-only lane.

The independent reviewer accidentally created
`C:\Users\Jonathan\AppData\Roaming\TinyAssets\u-01kyddzjt5w0db227y9g5mtmfg`
while probing an invalid route. The exact path was verified; deletion was
attempted but blocked by the execution policy, so the isolated local probe
directory remains and should be removed by the host.

## Opus 5 ADAPT fold

### Gate-gaming reversal

The branch had changed
`tests/test_universe_server_framing.py::test_extensions_tool_description_points_to_prompts_for_rules`
from:

```python
assert len(tool.description or "") < 900
```

to:

```python
assert len(tool.description or "") < 2200
```

The fold restores the original `< 900` assertion. The current `extensions`
description is 1,948 characters and is unchanged by this lane, so the restored
assertion remains red exactly as it does on `origin/main`. That is baseline
debt owned by the separate main-red lane; this fold does not trim the
description or move the threshold.

### Runtime response-payload paths found and fixed

The static prompt fix was insufficient because canonical handles delegate to
legacy implementation functions whose result envelopes contained model-facing
tool guidance. The fold traced the seven advertised handles through their
delegates and reconciled these response paths:

- `read_page`: wiki search completeness warnings now use `read_page query`,
  `read_page changed_since`, and `read_page page`; draft/ingest/supersede
  results state the promotion gap; filed-issue results use `read_page category`;
  duplicate filings state that cosigning is not exposed; truncated reads no
  longer advertise the retired offset call and state the continuation gap.
- `get_status`: missing-universe caveats and next steps now use
  `read_graph target="graphs"` and `write_graph target="universe"` with the
  requested `graph_id`.
- `read_graph target="graph"`: `cross_surface_hint.paths` now contains only
  canonical graph/page reads and explicitly states that global workflow
  enumeration is unavailable.
- `converse`: the newborn-no-engine hold no longer emits
  `universe action=set_engine`; it states that engine assignment is unavailable
  on advertised handles and points the user to the host's internal surface.
- `write_graph target="request"`: queue-monitor guidance now uses
  `read_graph target="graph"`; oversized private prose routes through
  `converse`, not `add_canon`.
- `run_graph` and delegated run envelopes: queued/resumed/version-run results
  now use `read_graph target="run"` and state the wait/cancel gaps; failure
  suggestions use executable canonical branch reads or name host-only
  approval gaps; resume and child-receipt reclamation payloads no longer name
  `resume_run` or `attach_existing_child_run`.
- Delegated branch/evaluation/Goal/market/selector/canonical responses:
  valid edits are expressed as `changes_json` operations through `write_graph`;
  Goal reads/search/create use `read_graph`/`write_graph`; Goal binding,
  selector binding, leaderboard/gates, approval, branch publication,
  standalone-node creation, and related admin actions are stated as
  unavailable through advertised handles.
- Hidden source/canon and engine/daemon helper envelopes were also reconciled
  so a later canonical route cannot revive stale guidance.
- Effector, goal-pool, and universe-bundle payloads now state the internal
  consent/gate/soul-learning gaps instead of advertising `extensions`,
  `gates`, or `universe` calls. Cross-author mutation, canonical selection,
  Goal binding, premise/canon learning, and node rollback guidance likewise
  use canonical handles where executable and explicit gaps otherwise.

A response-oriented AST sweep found no remaining runtime strings that instruct
clients to call a retired tool or standalone legacy action. The only legacy
action-shaped tokens left in response text are operation names such as
`add_node` and `update_node`, explicitly carried as supported `changes_json`
data under the canonical `write_graph` handle.

### Extended invariant and mutation evidence

`tests/test_mcp_instruction_surfaces.py` now:

- extracts any syntactic `<name> action=` or `<name> target=` routing head
  before consulting registered names, closing the M3/M7 retirement blind spot;
- detects retired call syntax, natural-language routes, standalone actions,
  and structured `*_action` fields even after legacy deregistration;
- fails routing examples when their handle or first parameter is invalid, or
  required graph companion arguments are missing;
- recursively inspects text nested in response dict/list envelopes;
- scans non-docstring runtime literals and joined f-strings across canonical
  API delegates, effectors, producers, runs, compiler, and bundle paths;
- exercises real `read_page` query and genuinely truncated-page responses,
  `get_status`, and `read_graph` results, plus delegated converse engine-hold
  and selector error envelopes.

Fresh evidence on 2026-07-25, Windows / Python 3.14:

- RED before production edits:
  `python -m pytest tests/test_mcp_instruction_surfaces.py -q` failed on the
  live `read_page` response (`wiki action=search`).
- GREEN after the fold: the invariant file reports `18 passed`.
- Parameterized mutation checks rejected 10/10 injected routes, including
  unknown `foo_graph target=`, retired `extensions action=` after simulated
  deregistration, `wiki(action=...)`, natural `wiki list/write`,
  `list_node_versions`, `add_canon`, and structured
  `reclaim_action=attach_existing_child_run`.
- All 19 modified test files excluding the two baseline reds they contain:
  `534 passed, 2 deselected`; expanded relevant coverage including run
  recursion checks reports `572 passed, 4 deselected`.
- The four baseline reds reproduced alone:
  the required restored `<900` assertion (1,948 actual), plus the unchanged
  pre-existing `test_get_run_output_text_channel` assertion that expects the
  literal word `workflow` while `origin/main` emits
  `Output from tinyassets 'Recipe tracker'`, plus two recursion-limit tests
  that fail at unchanged `_invoke_graph` database-setup lines before reaching
  this lane's changed recursion-limit guidance. The database-setup failure
  cause is not changed by this lane.
- Focused post-rebase product coverage: `374 passed` across the invariant,
  wiki, evaluation, run, branch, effector, goal-pool, and canon paths.
- Ruff: all 53 changed Python files outside known baseline-error files pass.
  Full changed-file Ruff reports 64 pre-existing E501 mojibake separator-line
  errors across canonical `api/market.py` (7), `api/runs.py` (3),
  `effectors/github_pr.py` (5), and `runs.py` (17), duplicated in their plugin
  mirrors. Linting those four `origin/main` blobs reproduces all 32 canonical
  errors. No assertion or lint rule was weakened.
- Plugin runtime build: import probe `probe-ok`.
- SHA-256 mirror parity: all 21 changed canonical runtime Python files,
  including `tinyassets/universe_server.py`, are byte-identical to their plugin
  runtime copies.

LANE_RESULT: done - ADAPT folded; runtime payload guidance and invariant reconciled, with pre-existing baseline reds disclosed.
