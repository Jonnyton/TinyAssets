# Serving lookup/readiness: independent implementation review

September10 2026. Claude58597 reviewed exact8653ae50 against03041ce8, read-only,
exit0,335s. VERDICT: APPROVE. Seven focused legacy-readiness cases independently
reproduced on Windows,7passed1.75s. No sub-agents or source edits.

AGREE: predicate filtering precedes LIMIT2 in both resolvers;105 newer inactive
bindings cannot conceal the active one and ambiguity still refuses. Legacy home
preferences are read in the same BEGIN IMMEDIATE as activation; absent/automatic
remain usable, explicit/corrupt/deleted hold without mutation. Non-home and
pre-onboarding standalone behavior matches the turn path. Exception handlers,
mirrors and delta spec agree. No required corrections.

Non-gating findings retained for subsequent work:

1. onboarding/serving.py:_quiesce_other_serving still enumerates list_bindings100.
   It can leave an old serving row during app connect; both fixed resolvers then
   correctly refuse ambiguity. Needs an all-owner-serving read for this mutation,
   not reuse of the deliberately bounded LIMIT2 ambiguity helper.
2. Removing the founder_home row skips the home-preferences gate in both existing
   readiness and turn paths. Remaining deletion protection then depends on
   assignment/custody invalidation. Track with the scoped-reset inventory concern;
   do not infer a vulnerability or silently classify/delete provider state.
3. The helper is not in custom_agents.__all__; explicit imports work.
4. Unlike list_bindings, the new helper does not strip ids. Current resolver
   callers already pass normalized values; no current regression identified.
5. Existing universe index does not cover the complete predicate; an owner/status
   composite index may matter for large agent inventories. No measured need yet.

This approval does not cover the subsequent collection/typed-failure changes,
public catalogue endpoint, clickable controls, live provider calls or deployment.
