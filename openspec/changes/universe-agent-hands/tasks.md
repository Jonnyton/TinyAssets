# Tasks

Vertical slices. Each one is runnable and testable on its own; ship in order.
Findings become failing tests, not documents.

## 1. Prove the mechanism (blocks everything below)

- [x] 1.1 **PASS** (live, daemon container, 2026-08-07). Two probe servers:
      `granted` via `--mcp-config`, `withheld` via a project-tier `.mcp.json` in
      the cwd. Result: `mcp__granted__universe_probe` callable, returned
      `SENTINEL-GRANTED`; `withheld` absent. `--strict-mcp-config` holds.
- [x] 1.2 **PASS** — with the real 45-entry deny list (minus `mcp__*`), the
      complete reachable surface is `ToolSearch`, `AskUserQuestion`, `WebFetch`,
      `mcp__granted__universe_probe`. No Bash, no filesystem, no Grep/Glob. The
      2026-07-03 host leak stays closed.
- [x] 1.3 **DISCOVERED, load-bearing:** MCP tools arrive **deferred** —
      `ToolSearch` is the only way to load their schemas. Denying `ToolSearch`
      (as the current list does) makes a granted MCP server INVISIBLE: run 2 saw
      only `AskUserQuestion` + `WebFetch`. So `ToolSearch` must be REMOVED from
      the deny list, and `mcp__*` replaced by `--strict-mcp-config`. Both edits
      are security-relevant and must land together.
- [ ] 1.4 Test that `ToolSearch` cannot surface a DENIED tool (deny must beat
      load). This is the assumption that makes 1.3 safe; unverified assumptions
      of this shape are how the deny list rotted in the first place.
- [ ] 1.5 Drop the 7 deny entries that match no known tool — `MultiEdit`,
      `NotebookRead`, `LS`, `SlashCommand`, `ReportFindings`, `DesignSyncTool`,
      `ReadMcpResourceDirTool` (CLI warns "matches no known tool"). Then add a
      test that FAILS when a deny name stops matching, so the next rename is
      caught instead of silently un-denying a live tool.
- [ ] 1.6 Decide `AskUserQuestion`: reachable today and not denied, but a
      headless Slack turn has nobody to ask. Deny it, or route it to the chat
      surface as a real question.

## 2. The universe MCP server

- [ ] 2.1 `tinyassets/universe_agent_tools.py`: a stdio MCP server bound to ONE
      universe at construction. No tool takes a universe id.
- [x] 2.2 **DONE** — `tinyassets/universe_agent_tools.py`: `UniverseWorkspace`
      + `list_files`/`read_file`/`write_file`/`delete_file`, containment via
      `Path.resolve()` + `is_relative_to` (never a string prefix). Atomic
      temp+replace write. `.credentials` is RESERVED — containment alone is not
      enough, since the provider vault lives INSIDE the workspace and a confined
      agent could otherwise read its own credentials and quote them into chat.
- [x] 2.3 **DONE** — 21 tests, both directions. Mutation-probed: containment
      always-true reds 5 escape tests; refuse-everything reds 12 accept tests.
      Symlink escape verified on LINUX (skips on Windows): read AND write
      refused, in-workspace symlinks still resolve, sibling-prefix
      (`u-test-evil` vs `u-test`) refused with the string-prefix trap asserted
      explicitly in the test.
- [ ] 2.4 Platform tools delegating to the existing surface — `agent`,
      `agent_binding`, `automation`, `connection`, `branch`, `goal`. Thin
      wrappers over `write_graph`/`read_graph`; no new authority logic.

## 3. Wire it into the turn

- [ ] 3.1 `_sandboxed_config` / `_sandbox_cli_args` gain the MCP config path and
      `--strict-mcp-config` when the turn is granted tools.
- [ ] 3.2 Tier decides the grant: FOUNDER gets the server, everything else gets
      none. Enforced where the config is built, before the subprocess starts.
- [ ] 3.3 Mutation-probe 3.2: force a non-founder tier and assert the turn is
      launched with NO `--mcp-config`. Deleting the check must turn this red.
- [ ] 3.4 The turn's system prompt tells it what it can now do. It has hands; it
      must know.

## 4. Retire the guesser

- [ ] 4.1 Delete `extract_learning` + `commit_learning` and their call site.
- [ ] 4.2 Verify the founder gate survives the deletion — 3.2/3.3 is its
      replacement. Codex confirmed the old `if` was ALSO what justified
      `api/wiki.py:2523-2541` skipping the ACL gate, so losing it silently costs
      two layers.
- [ ] 4.3 Regression test for the live incident: a turn saying "build me an
      OpenClaw agent" must NOT rewrite `body.md`. This is the bug that motivated
      the change; it gets an executable memory.
- [ ] 4.4 Soul writes append/merge with provenance instead of replacing
      (`soul_edit.py:252`).

## 5. Harness templates

- [ ] 5.1 Seed file-sets for OpenClaw / Hermes / Claude Code / Codex shapes.
      Data, not platform code.
- [ ] 5.2 `create_agent` takes an optional template that seeds the folder; the
      agent can then edit, mix, or replace it.

## 6. Live proof (the testing round)

- [ ] 6.1 Through the real Slack connector, as a user: ask it to build an
      automation. It builds one, says what it built, and the automation exists.
- [ ] 6.2 Ask it to create a Hermes-shaped agent. The agent exists and its
      folder carries the Hermes layout.
- [ ] 6.3 Ask it to change something about itself via the patch automation. A
      real PR opens against the platform.
- [ ] 6.4 A non-founder in the same channel gets conversation only — no tools,
      no writes. Verified live, not just unit-tested.
- [ ] 6.5 Log the rendered session to `output/user_sim_session.md`.
