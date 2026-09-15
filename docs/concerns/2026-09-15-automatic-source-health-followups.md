# Automatic source health — post-live follow-ups

Filed 2026-09-15. Fable5.1 review of d2b77b84a7a6654a1cf32925bff2a0f776720e26
approved the MVP with these non-blocking observations, not demonstrated outages:

- Success hint clearing sits inside the router's provider try; a future exception
  in this advisory operation could turn a successful response into a failure.
  Required authority fields currently exist. Isolate advisory failures when
  extending this mechanism; retain actual response/effect evidence.
- Legacy api/runs.py classification still reports provider_unavailable for this
  message. The old native authentication message also missed its auth tells;
  the served chat path now carries typed auth_invalid. Separate legacy follow-up.
- Process-local five-minute hints are intentionally advisory and disappear on
  restart; multiple workers do not share them. This is not durable availability
  tracking. Any persistence expansion needs a reviewed storage/authority design.
- Current tests cover adapter normalization and real router/plan composition in
  separate tests. A whole fake-stream-through-served-router regression would
  improve coverage; actual live Automatic recovery remains the shipping proof.

No credential renewal, saved default change, workflow edit or unsafe replay is
authorized by these findings. Canonical review: ../reviews/2026-09-15-automatic-source-recovery.md.
