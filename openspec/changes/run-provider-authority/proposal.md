# Foreground runs need their own provider authority

## Why
On prod `8cbf9769` every LLM-bearing node in a user-started run fails in ~150 ms with
`permission_denied:provider_not_bound`. Public `run_branch` / `run_branch_version` LLM nodes are
unreachable **for every user**, not just the founder. Effect-only and `source_code` branches are
unaffected, which hid it: the agent's own Slack push lane used effect-only branches.

Live evidence (founder's universe, 2026-08-26): a correct one-node branch — `prompt_template`,
`effects: ["authenticated_external_call"]`, canonical `llm_policy {"preferred": {"provider": "codex"}}`,
real `x:posting` connection/grant, consent granted, `runnable: true` — failed on runs
`9195110bbbed418e`, `e81519ac30f24530`, `4e6e58608a8446fb`.

Mechanism: `api/runs.py::_bind_run_provider_call` builds a `UniverseContext` with `universe_dir` +
config and **no** authority carrier and **no** `provider_request`. `providers/router.py:465`
classifies any context without `provider_invocation` as a served turn and demands a
`provider_request`, so the call is held before policy, credentials, serving selection or consent are
ever examined.

History (Codex, cross-family): the run binding landed `9c326385` (2026-08-09) and `04eb0f60`
(2026-08-11) flipped the run tests to "must hold without served authority". Removing ambient
authority was intended and correct; **not replacing it with a foreground-run authority lane was an
unintended reachability regression.**

## What changes
A founder-initiated run gets a durable, server-owned run authority — never a served request
capability — from which the executor mints ONE pid-bound, one-use `ProviderInvocationCarrier` per
provider attempt. `work_item_kind="run"` already exists in `storage/provider_work_authority.py`; this
change completes that dormant lane.

## Non-goals
Branch schema, the X connection/grant, outbound consent, effect dispatch and the public MCP handles
are unchanged. Cross-author/public branch composition stays out until delegated branch authority is
explicitly carried.
