# Host-independent monitor contract diagnosis

September 19, 2026 UTC. Read-only diagnosis against current main
`bcac8d1a250350ff48da2cfda3bd428831d361ea`, isolated branch
`codex/hostless-revert-acceptance`. No runtime change, account interaction,
workflow mutation, probe dispatch, restart, or production write.

## Fresh authoritative evidence

`gh pr view 3869 --json state,mergeCommit,body` confirms the executor-liveness
patch merged as `10daee27e8cdb88a192bf691947a79471b25b591`. Its stated scope
expressly leaves the separate private revert-evidence mismatch unresolved.

`gh run list --workflow uptime-canary.yml --limit 4 --json
databaseId,status,conclusion,createdAt,headSha` and
`gh run view 35411401518 --log` establish the latest completed scheduled run:
September 19 at 01:03 UTC, workflow source above, terminal failure.
Its actual combined observation is:

- handshake=0, tool=0, activity=0, revert=5, wiki=0;
- current executor heartbeat age 1.1 seconds, alive, no active work;
- revert diagnostic: status has no evidence block;
- separate Layer-2 exit 13, browser-load error.

The first five values are independent measurements. They do not prove a
platform-wide outage or justify restarting a retired fleet. They also do not
prove the complete hostless-monitoring capability.

## Revert probe: incompatible scope, not a missing sign-in

`scripts/revert_loop_canary.py:fetch_status_activity_tail` requests unscoped
`get_status`, then requires `evidence.activity_log_tail`. Its classifier looks
for fantasy scene-commit REVERT strings inherited from the April incident.

`tinyassets/api/status.py:get_status` deliberately returns a no-home platform
projection for the named canary principal. The projection includes private-free
daemon observations, not another user's private activity log. Only the later
universe-scoped branch returns that evidence, after the metadata permission gate.
Current `runs.py`, assigned-queue consumer, and agent-turn journal do not emit
the legacy scene REVERT vocabulary as their generic execution-health contract.

Therefore fixing a parser cannot manufacture the missing observation. Granting
the canary access to a user's universe, inventing an empty activity tail, or
declaring every arbitrary user workflow failure a platform outage are all wrong
shapes. In particular, users can intentionally build failing workflows, and
their provider exhaustion does not authorize platform operators to pause them.

## Layer-2: unavailable execution prerequisites remain separate

The `layer2-probe` job in `.github/workflows/uptime-canary.yml` installs Python
only, then invokes the browser probe. Its comment promises absent-browser SKIP,
but no such preflight branch exists in `scripts/uptime_canary_layer2.py`.
`_real_browser_probe` invokes `scripts/claude_chat.py ask`; that harness requires
Playwright plus a signed-in visible Claude browser reached on local CDP port
9222 and documents a human-host setup step. Any subprocess failure maps to 13.

The completed job proves exit 13; it does not expose the concrete subprocess
reason in stdout, and the run has no artifacts. Thus no claim is made that
Claude.ai itself was unavailable. A missing browser/persona should be reported
as unavailable observation, not green, but honest classification alone does not
provide a host-independent rendered proof.

## Narrow pre-build decision

Repair the existing scheduled probe result and alarm contract first: a missing
required observation is unknown, never green or a measured platform outage.
Observed handshake, tool, current-executor and wiki failures remain red even if
another observation is unavailable. Only measured Layer-1 reds count toward
the incident threshold; a whole workflow failure is not such evidence. The
existing alarm sink already has an unknown/no-mutation guard, but the combiner
collapses revert exit 5 into red, and historical threshold logic treats any
prior workflow failure as red. A Layer-2-only failure can therefore contaminate
the Layer-1 threshold. Unknown must remain visible in the scheduled summary
and keep full acceptance open, not be skipped into a green result.

Inventory found an existing deploy receipt, current-coordinator liveness and
private agent-runtime health, not an existing public scheduled execution-quality
receipt under current canary authority. `check_primitive_exists.py action
get_status` confirms the existing handle. No new MCP action, public projection,
storage schema or canary authority is proposed for this first repair. A future
busy-but-broken observation first needs a defined authoritative engine-owned
failure signal and review; tenant workflow quality remains the owner's policy.

Separately, rendered Layer-2 proof needs an authorized user acceptance session.
PLAN permits infrastructure canaries but forbids infrastructure from invoking
an LLM or acting as a universe; installing a provider persona on the scheduled
runner is therefore not the proposed repair. The absent scheduled capability
must be diagnosed as unavailable without executing the browser harness. This
does not replace rendered acceptance or permit reopening the held second-user
onboarding attempt. Browser transport redesign remains out of scope.

No capability is marked complete. The next safe action is the bounded shape
review of this observation contract, while other builders continue deployable
work. The current canaries remain visibly unresolved until real evidence exists.

## Local verification

September 19, Windows Python 3.14, isolated worktree at the source above:
`python -m pytest -q tests/test_revert_loop_canary.py
tests/test_current_executor_liveness.py tests/test_last_activity_canary.py
--tb=short --show-capture=no` completed with **82 passed**. These are baseline
regressions, not deployed or rendered acceptance proof.
