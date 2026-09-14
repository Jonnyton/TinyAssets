# Independent model-capacity implementation review

September10 2026. Claude reviewed exact964c58f25feecc28e7b62b2be280d025a2e5c951
against e5d93e84, read-only. Session72062 ended exit0 in417s, APPROVE with no
required changes. Reproduced25 composition tests on Windows13.8s; checked nine
canonical runtime files against their generated mirrors. Broader515/515 evidence
is the author's separate proof, not independently reproduced.

Substantive review recovered from exact transcript
5585d2d7-bc89-4d91-b53b-451edc7940de after the known stop-hook final recap.

AGREE: per-attempt serving authority and launch allowance; zero settlement for
confirmed pre-generation refusals; scope-aware cooldown; unknown-to-account fold;
shared-account sibling exclusion; fresh grants and price bounds on replacement;
empty explicit fallback tails; unknown outcome holds; exact known tool results
without replay or foreign reasoning; unchanged legacy text and CLI paths.

Non-gating follow-ups, retained for integration:

- OpenRouter503 currently classifies by status alone. A gateway HTML503 can
  cycle siblings within the finite allowance. Require documented JSON evidence
  for model-local classification or conservatively fold an opaque503 to unknown.
- Aggregation independently selects scope, failure kind and retry delay. The
  current served chain has one attempt, but a future wider chain should carry
  one complete CapacitySignal rather than recombining fields.
- Public ingress must make the plan the single source of model selection and
  reject a contradictory plan/selection pair; the private runner currently
  replaces an incoming selection with its first planned candidate.
- Retry-After transport was not verified by the reviewer. Author source check
  after review: outbound_connections.py _execute_pinned_https_request includes
  lowercased response headers; _SsrfHardenedHttpDriver._request returns the
  declassified result; broker success serializes that whole result and
  _ProxyChannel.request returns it. The header is not intentionally dropped.
  This is source evidence, not a live retry-hint wire test. Duplicate response
  header names are collapsed by the existing driver before the decoder sees them.
- Dedicated capacity catch retains diagnostics but does not emit the warning
  sibling handlers do. Observability follow-up, not a blocking correctness defect.

Review does not approve public activation, current/saved ingress, native model
selection, UI, reset-inventory changes or deployment. No owner workflows or
permission requests were edited. Runtime remains exact964c58f2; subsequent d5949b13
only corrected evidence dates and recorded supplemental regression results.
