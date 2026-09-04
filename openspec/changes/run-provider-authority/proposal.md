# Foreground runs need their own provider authority

**Owner:** Patches, transferred from `resume` on 2026-09-03. The exact-provider
admission check returned `ALLOWED`; this is a continuation of the existing
single-intent change, not a fifth delivery lane.

## Why
On prod `8cbf9769` every LLM-bearing node in a user-started run fails in ~150 ms with
`permission_denied:provider_not_bound`. Public `run_branch` / `run_branch_version` LLM nodes are
unreachable **for every user**, not just the founder. Effect-only and `source_code` branches are
unaffected, which hid it: the agent's own Slack push lane used effect-only branches.

Live evidence is retained only as a capability receipt. On 2026-09-03 the
bound universe agent chose and ran its own prompt workflow after production was
updated. The run still failed at first provider use with
`permission_denied:provider_not_bound`; the selected provider was not invoked
and no effect was attempted. Private universe, branch, run, prompt, credential,
and destination details are intentionally omitted.

Mechanism: `api/runs.py::_bind_run_provider_call` builds a `UniverseContext` with `universe_dir` +
config and **no** authority carrier and **no** `provider_request`. `providers/router.py:465`
classifies any context without `provider_invocation` as a served turn and demands a
`provider_request`, so the call is held before policy, credentials, serving selection or consent are
ever examined.

The first implementation exposed a second live reachability failure after the
same universe refreshed its serving assignment. Run-class binding ids are
deterministic per owner/universe/provider. The old run-class row survived the
refresh, so issuing the current child returned `CONFLICT`; meanwhile serving
status correctly validated the refreshed parent. Every new prompt run was then
flattened to `permission_denied:provider_not_bound`. The run lane now reuses an
exact current child and transactionally rebinds a stale child from the current
serving seed before admitting the run.

History (Codex, cross-family): the run binding landed `9c326385` (2026-08-09) and `04eb0f60`
(2026-08-11) flipped the run tests to "must hold without served authority". Removing ambient
authority was intended and correct; **not replacing it with a foreground-run authority lane was an
unintended reachability regression.**

## What changes
A user-authorized run that actually calls a provider gets a durable, server-owned run authority —
never a served request capability — from which the executor mints ONE pid-bound, one-use
`ProviderInvocationCarrier` per provider attempt. Provider-free and explicitly mocked runs retain
their previous behavior and create no run receipt. `work_item_kind="run"` already exists in
`storage/provider_work_authority.py`; this change completes that dormant lane.

The selected provider may be subscription-backed or a registered open HTTP
provider. Subscription-backed calls use a sealed credential snapshot; open
providers keep their existing connection-grant custody and credential-blind
proxy path. The foreground authority lane must not reject a provider merely
because it is open after ordinary serving selection has already authorized it.

## Non-goals
Branch schema, the X connection/grant, outbound consent, effect dispatch and the public MCP handles
are unchanged. Cross-author/public branch composition stays out until delegated branch authority is
explicitly carried.
