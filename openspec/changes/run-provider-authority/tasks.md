## 1. RunProviderSession

- [ ] 1.1 Failing tests first: a foreground run of a one-node `prompt_template` branch launches the
      ACTIVE serving provider exactly once and produces exactly one succeeded carrier reservation;
      an N-node branch produces N distinct carriers/reservations and refuses the N+1th; missing,
      stale, revoked or cross-universe authority yields ZERO provider calls and ZERO effects.
- [ ] 1.2 Create the run authority at admission: freeze the branch subject (definition + immutable
      version/content digest) and issue one run receipt/claim as a run-class child work binding
      derived from the ACTIVE serving binding, using the existing `work_item_kind="run"` in
      `storage/provider_work_authority.py`.
- [ ] 1.3 Replace the static `UniverseContext` closure in `api/runs.py::_bind_run_provider_call`
      with a session that mints a FRESH pid-bound one-use carrier per provider attempt.
- [ ] 1.4 Generic carrier reservation settlement: reserve → arm → success/failed/
      cancelled_before_launch/indeterminate, releasing unused reservation; terminal run releases the
      claim and cancels unarmed reservations.
- [ ] 1.5 Fail closed on every mismatch in design.md § Binding; never fall back to ambient providers.

## 2. Evidence

- [ ] 2.1 Ruff + the touched suites, including `tests/test_requester_owned_provider_execution.py`
      (its two "must hold without served authority" tests describe the OLD reachability; update them
      to assert the new lane holds for an UNAUTHORIZED context and admits an authorized run).
- [ ] 2.2 Plugin mirror parity.
- [ ] 2.3 Live proof after deploy: the founder's own branch `8ab6516d50c5` runs, the run reads back
      `succeeded`, and exactly one authenticated X POST happens.
