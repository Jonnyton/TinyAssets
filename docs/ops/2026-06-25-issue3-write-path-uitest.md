# Issue 3 Write-Path `ui-test` Runbook

Purpose: reproduce the live connector's bare "No approval received" failure for `write_graph target=request`, then A/B test whether marking `write_graph.openWorldHint=false` removes the client-side approval gate. This is a host-watched `ui-test` flow through a real chatbot connector session, not a direct MCP call.

Reference: `.agents/skills/ui-test/SKILL.md`. Follow its proof standard: type normal user prompts into the rendered ChatGPT or Claude.ai UI, use the installed Workflow connector at `https://tinyassets.io/mcp`, read the rendered response, and capture the transcript. Do not bypass the chatbot by calling MCP directly.

## Evidence To Capture

For both A and B runs, record:

- Date/time with timezone.
- Client: ChatGPT Developer Mode or Claude.ai.
- Connector endpoint shown in the client: `https://tinyassets.io/mcp`.
- Deployed release/SHA if the client or `read_graph target=status` visibly reports it.
- Exact user prompt.
- Any approval dialog text, including whether Approve can be clicked.
- Final rendered assistant response.
- Screenshot or screen recording path.
- Full copied transcript path.

Suggested artifact paths:

- Short shared log: `output/user_sim_session.md`.
- Full baseline transcript: `output/issue3-write-path-baseline-2026-06-25.md`.
- Full B-run transcript: `output/issue3-write-path-openworld-false-2026-06-25.md`.

## A. Reproduce Baseline Failure

Use the currently deployed connector before deploying this branch.

1. Open exactly one visible chatbot tab, per `ui-test` tab hygiene.
2. Confirm the Workflow connector is available in that conversation and points at `https://tinyassets.io/mcp`.
3. Start a fresh conversation or one with no cached per-tool approval for `write_graph`.
4. Send this prompt:

   ```text
   i added the workflow builder connector. can you use it to submit a request to workflow? request text: issue3 baseline check - please queue a tiny request asking the daemon to confirm the write path is reachable.
   ```

5. If the client shows an approval dialog for Workflow or `write_graph`, capture it before clicking anything.
6. Try the normal user action once: approve the tool call if the client allows it.
7. Capture the final rendered result. The baseline symptom is a bare `No approval received` with no useful server-side explanation.
8. Copy the full transcript into the baseline artifact and add a short entry to `output/user_sim_session.md`.

## B. Test `write_graph.openWorldHint=false`

Deploy only the branch that changes `write_graph.openWorldHint` to `false`. Do not change anonymous write policy, server authorization, or wiki/gates/extensions tool hints for this A/B.

1. Use the same client family as the baseline when possible.
2. Reset the `write_graph` approval state if the client has cached an allow/deny decision. If reset is not available, use a new conversation plus a client/account state where the Workflow connector is installed but `write_graph` has not already been approved.
3. Confirm the connector still points at `https://tinyassets.io/mcp`.
4. Send the same shape of user prompt with a B-run marker:

   ```text
   i added the workflow builder connector. can you use it to submit a request to workflow? request text: issue3 openworld false check - please queue a tiny request asking the daemon to confirm the write path is reachable.
   ```

5. Capture any approval dialog. If no dialog appears, capture the rendered tool-use/result transcript.
6. Expected pass condition: the client no longer fails closed with bare `No approval received`; the request either queues successfully or returns a normal Workflow/server validation response.
7. Expected fail condition: the same bare `No approval received` appears before any visible server result. If that happens, treat it as connector/client-side BUG-034-class behavior and file upstream with both transcripts.
8. Copy the full transcript into the B-run artifact and add a short entry to `output/user_sim_session.md`.

## Post-Deploy Canary

This is a live MCP tool surface change. After deploy, the host must run:

```powershell
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles
```

This runbook intentionally does not run the live canary from the development worktree.

## Follow-up: `write_page` (conditional on B-run result)

This A/B deliberately flips only `write_graph.openWorldHint` to isolate the
variable. As of this branch, `write_page` is the **only canonical write handle
still advertising `openWorldHint=true`** (`workflow/universe_server.py:722`).
If the hypothesis is wrong, the wiki write is arguably genuinely open-world (a
shared/public discovery commons), so the asymmetry is defensible and nothing
changes.

But if the B-run **confirms** that flipping `openWorldHint` to `false` is what
clears the bare "No approval received" gate, then `write_page` is exposed to the
exact same failure and MUST get the same flip across **every surface that
advertises the handle**, not just the universe server:

- `workflow/universe_server.py` (canonical) + its plugin mirror
- `workflow/directory_server.py` (the directory/discovery MCP surface) + its
  plugin mirror — this is the surface the prior reviewer flagged as easy to miss
- `chatgpt-app-submission.json`
- `tests/test_universe_server_five_handles.py` **and**
  `tests/test_directory_server.py`

followed by the same post-deploy `--assert-handles` canary. Do not close Issue 3
as fully fixed until `write_page`'s status is resolved one way or the other.
