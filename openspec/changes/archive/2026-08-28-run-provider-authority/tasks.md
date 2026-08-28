## 1. RunProviderSession

- [x] 1.1 Failing tests first: a foreground run of a one-node `prompt_template` branch launches the
      ACTIVE serving provider exactly once and produces exactly one succeeded carrier reservation;
      an N-node branch produces N distinct carriers/reservations and refuses the N+1th; missing,
      stale, revoked or cross-universe authority yields ZERO provider calls and ZERO effects.
- [x] 1.2 Freeze the branch subject at admission (definition + immutable version/content digest),
      then lazily issue one run receipt/claim on the first actual provider attempt as a run-class
      child work binding derived from the ACTIVE serving binding, using the existing
      `work_item_kind="run"` in `storage/provider_work_authority.py`. Provider-free and mock runs
      require no serving binding and create no receipt.
- [x] 1.3 Replace the static `UniverseContext` closure in `api/runs.py::_bind_run_provider_call`
      with a session that mints a FRESH pid-bound one-use carrier per provider attempt.
- [x] 1.4 Generic carrier reservation settlement: reserve → arm → success/failed/
      cancelled_before_launch/indeterminate, releasing unused reservation; terminal run releases the
      claim and cancels unarmed reservations.
- [x] 1.5 Fail closed on every mismatch in design.md § Binding; never fall back to ambient providers.
- [x] 1.6 Regression proof: ordinary mock-backed runs complete without provider authority or a run
      receipt, while a refused real provider attempt still fails the run with
      `permission_denied:provider_not_bound`.

## 2. Evidence

- [x] 2.1 Ruff + the touched suites, including `tests/test_requester_owned_provider_execution.py`
      (its two "must hold without served authority" tests describe the OLD reachability; update them
      to assert the new lane holds for an UNAUTHORIZED context and admits an authorized run).
- [x] 2.2 Plugin mirror parity.
- [x] 2.3 Live proof after deploy: the founder's own branch `8ab6516d50c5` runs, the run reads back
      `succeeded`, and exactly one authenticated X POST happens.
      **Proven live 2026-08-28 UTC** through the webapp (`tinyassets.io/mcp/app`) as the founder,
      not via MCP. Branch `X Hello World via Codex v2` = `8ab6516d50c5`, run `578790eb1a4c41db`,
      terminal `completed`, `POST https://api.x.com/2/tweets` → **201 Created**, tweet id
      `2093135439029059608`, `x-access-level: read-write-directmessages`. Exactly one POST.
      Prior attempts that day failed at X's own auth layer (403 `x-access-level: read`, then 401
      after the token was regenerated) — never at the provider-authority lane this change owns,
      which is what makes the 201 a clean proof of THIS requirement.
