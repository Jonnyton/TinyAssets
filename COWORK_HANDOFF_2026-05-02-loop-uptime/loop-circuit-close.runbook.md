# Closing the loop circuit — runbook (run AFTER live MCP is restored)

This is the substrate-level wiring that makes `wiki action=file_bug` auto-trigger the canonical investigation branch. Today on prod, `WORKFLOW_BUG_INVESTIGATION_GOAL_ID` is empty, so `workflow/bug_investigation.py:is_auto_trigger_enabled()` returns False and the wiki→branch transition is open-circuit. The code is already wired correctly — only configuration is missing.

## Prerequisite

Live MCP at `https://tinyassets.io/mcp` returns 200 (or any non-502). Verify:

```bash
curl -sSI https://tinyassets.io/mcp | head -3
```

## Step 1 — Confirm `change_loop_v1` exists in production universe

The branch must already be authored (`fd5c66b1d87d`) and be present in the universe SQLite. Confirm via MCP:

```
extensions action=describe_branch branch_def_id=fd5c66b1d87d
```

Expected: returns the branch graph. If not, the loop content needs to be re-authored (separate task — this runbook assumes it exists).

## Step 2 — Create or find the `bug_investigation` Goal

```
goals action=propose name=bug_investigation description="Auto-investigate filed bugs/features/designs from wiki action=file_bug. Canonical branch produces patch packet."
```

Returns `{goal_id: "<G>"}`. If a goal with this name already exists, use `goals action=list` to find its ID.

## Step 3 — Bind change_loop_v1 to the Goal

```
goals action=bind goal_id=<G> branch_def_id=fd5c66b1d87d
```

## Step 4 — Mark canonical

```
goals action=set_canonical goal_id=<G> branch_def_id=fd5c66b1d87d
```

This makes change_loop_v1 the canonical investigation branch for the Goal. Future binds without conflict only change the canonical; binding others to compete is fine — set_canonical decides.

## Step 5 — Set the env var on the droplet

The daemon reads `WORKFLOW_BUG_INVESTIGATION_GOAL_ID` at import time (`workflow/bug_investigation.py:24`). Set it via the atomic env helper:

```bash
ssh root@<droplet>
printf '%s' '<G>' | sudo bash /tmp/install-workflow-env.sh set WORKFLOW_BUG_INVESTIGATION_GOAL_ID
sudo systemctl restart workflow-daemon
```

Or via deploy-prod.yml: add `WORKFLOW_BUG_INVESTIGATION_GOAL_ID` as a repo secret and have deploy-prod's "Deploy new image" step inject it the same way `WORKFLOW_CODEX_AUTH_JSON_B64` is injected today (lines ~210-225).

## Step 6 — Verify auto-trigger is enabled

```
get_status
```

Look for any field indicating `bug_investigation_auto_trigger=true` (if absent, this becomes a follow-up patch — the daemon should expose this in get_status caveats so chatbots know auto-trigger is live).

Alternative verify: file a low-stakes test bug and watch the dispatcher event:

```
wiki action=file_bug component=test severity=P3 title="loop circuit smoke test" repro="trigger the auto-investigation pipeline" observed="" expected="auto-queued investigation run with patch packet returned" kind=bug
```

Expected response includes `Investigation` section with `dispatcher_request_id` or `investigation_run_id`. If you see only `bug_id` + `path` and no `Investigation`, the env var didn't take effect (probably daemon needs another restart or the goal_id is wrong).

## Step 7 — End-to-end smoke

Once auto-trigger is verified, file a real patch request:

```
wiki action=file_bug component=mcp severity=P2 kind=feature title="ChatGPT connector should auto-cosign similar bugs"
  repro="" observed="ChatGPT users find their bug already filed but cannot add their own context"
  expected="When file_bug returns similar_found, the connector should auto-call cosign_bug with the user's session context as attestation"
```

Watch the run progress. The canonical branch should:
1. Take the bug payload as input
2. Investigator pool runs (Claude + Codex)
3. Gate-1 review against PLAN.md and project criteria
4. If approved, coding team builds PR
5. Gate-2 ships to main / rejects / revises
6. Observation gate checks landed-evidence over time

If any stage breaks, that's the next substrate patch lane. Capture the run_id in `output/user_sim_session.md`.

## Validation that the loop is "running 24/7"

After the substrate is wired, the loop is "running 24/7" when:

- `community-loop-watch.yml` (every 15 min, GH Actions) reports `overall=green` consistently
- `uptime-canary.yml` (every 5 min) hasn't opened a `p0-outage` issue in 24h
- `wiki action=list category=bugs` shows new patch requests being added by chatbot users
- For at least one of those patch requests, you can trace: filed → investigated → reviewed → built → merged → observed-clean — entirely without you typing in chat

That's when "we just simulate users and watch the platform evolve itself" becomes the working state.
