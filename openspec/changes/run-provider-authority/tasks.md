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
- [x] 1.7 Reproduce the post-deploy failure synthetically and make a user-authorized
      foreground prompt run reach its exact ACTIVE serving provider once whether
      that provider is subscription-backed or a registered open HTTP provider;
      registration without serving selection and every owner/universe/policy
      mismatch still launch nothing.
- [x] 1.8 Reproduce the second post-deploy mismatch where serving status is healthy
      but a deterministic run-class binding from an earlier assignment makes every
      prompt run fail `provider_not_bound`; reuse an exact current child and refresh
      a stale child only through a fenced transactional rebind.

## 2. Evidence

- [x] 2.1 Ruff + the touched suites, including `tests/test_requester_owned_provider_execution.py`
      (its two "must hold without served authority" tests describe the OLD reachability; update them
      to assert the new lane holds for an UNAUTHORIZED context and admits an authorized run).
- [x] 2.2 Plugin mirror parity.
- [ ] 2.3 Live proof after deploy: the bound universe agent chooses and runs its
      own provider-backed prompt workflow through ordinary user authority. Retain
      only a sanitized receipt proving the selected provider ran exactly as
      expected and, when the owner has independently approved a safe effect,
      that the reviewed effect happened exactly once. Patches does not inspect,
      edit, run, or delete the live branch and retains no private identifiers or
      content.
- [ ] 2.4 Fresh opposite-family review, or the documented hard-provider-limit
      independent-review fallback, agrees that the follow-up preserves exact
      provider, owner, universe, policy, revocation, one-use carrier, budget,
      and settlement fences before landing.
