# Paid-market Track E Wave 2 transport lane report

Date: 2026-07-24 PT
Branch: `codex/osx-paid-market-transport`
OpenSpec change: `paid-market-track-e-wave-2-transport`

## Outcome

The lane premise-verified all 37 tasks and completed every standalone
spec/transport/fixture-migration task that can proceed before the recorded host,
S14/B36, tenant, boundary, and domain-owner gates. The task file moved from
1 checked / 36 open to 15 checked / 22 explicitly blocked after independent
review. No live migration, workflow registration, chain effect, PR, or feature
enablement occurred.

The prior `codex/paid-market-track-e-wave2-spec` lane was inspected before
implementation. Its reconciled proposal/design/delta artifacts were already
present through the branch base/squash; salvage is credited in the relevant
commit messages.

## Completed

- 1.2: recorded the pre-change pure-core/matcher and strict OpenSpec baselines.
- 2.1–2.4: added a replay-safe fixture migration runner, exact-byte cached SQL,
  gap-free 001–009 numbering, schema history, bounded advisory locking, atomic
  failure/resume, fresh concurrent-runner proof, complete catalog fingerprint
  baselining, Compose migration gating, and real fixture-role RLS proof.
- 3.1–3.2: added/exported the pure spot-settlement adapter and drain tests.
- 3.3–3.4: hardened fixture 009 with exact canonical hashing, tenant-scoped
  replay/conflict, fixed search paths, non-login owners, least privilege,
  bounds/provenance checks, canonical structural validation, and 100-caller
  replay proof.
- 4.8: added the immutable, default-off settlement transport with an injected
  trusted authority verifier and sole `MarketLedgerRpc` mutation boundary.
- 6.1: rebuilt the generated Claude runtime mirror and passed parity/import
  probes.
- 6.3: completed independent Claude-family implementation review and follow-up;
  all Critical/Important findings were resolved and re-tested.
- 6.5: kept migrations unapplied outside the fixture, transport/workflow
  unregistered, chain effects absent, and the paid-market feature default-off.

## Skipped as already landed or premise-inverted

- 1.1 was already landed: the 2026-07-22 opposite-provider spec review exists.
- 4.9 was already landed in proposal/design/delta: exact
  `job_id:lease_fence:accepted_result_sha256`, S14/B36, and the separately
  reviewed §18.6 chain-settlement successor are recorded.
- The inherited `external pass-through` / `self_hosted_zero_fee` premise was
  stale. It was not implemented. The active change and stale routing references
  now state: cheapest adequate currently executable Internet route is the
  top-line reference; native/connected supply competes below it through supply
  and demand; every positive-gross TinyAssets settlement pays at least one
  canonical fee micro. A zero-gross full refund has no seller fee base and is
  not a route or actor exemption.
- Live price/quote read surfaces remain owned by
  `paid-market-live-price-discovery` and were referenced, not duplicated.

## Skipped as blocked

- 2.5–2.6: need host-provided live Supabase access, production baseline and
  migration-home approval, then separately reviewed production-native SQL.
- 3.5: business-state/version CAS and actor/account authorization depend on the
  gated workflow plus tenant/boundary/domain owners and S14/B36.
- 3.6–3.7: standalone differential/hash/grant-bound evidence is green, but
  residual business reservations, authoritative tenant/revocation rows, and
  global business lock order depend on 3.5.
- 4.1–4.7: runtime inbox, workflow, Realtime, bid, claim, and delivery work is
  blocked by canonical-absolute, R2-1, S14/B36, live-price, boundary, tenant,
  claim, and domain-owner dependencies. No speculative migration 010 or API/MCP
  surface was created.
- 5.1–5.7: workflow fault/race/load/zero-host proofs require those blocked
  runtime stores and, for 5.3/5.4, host-provided production-shaped Supabase
  environments. Local fixture evidence was not reported as production proof.
- 6.2: every available standalone gate is green, but the named
  workflow/Realtime/bid/claim/delivery suites cannot exist until 4.1–4.7.
- 6.4: rendered chatbot/tray acceptance is forbidden before a reviewed live
  surface, migrations, S14/B36, and cutover exist.
- 6.6: sync/archive and STATUS retirement wait for landing; doing them on an
  unreviewed builder branch would falsely claim completion.

## Verification evidence

Fresh 2026-07-24 PT, Windows + Docker PostgreSQL 15:

- `python -m pytest tests/test_paid_market_transport.py tests/test_paid_market_core.py tests/test_match_scale.py tests/test_paid_market_migrations.py tests/test_paid_market_postgres.py -q --noconftest`
  — 227 passed in 9.99s after the final review fixes.
- `python -m pytest prototype/full-platform-v0/tests -q`
  — 18 passed in 3.46s; RLS assertions ran as
  `tinyassets_fixture_app`, not the superuser.
- Fresh `tinyassets-wave2-test` Compose volume — migration exited 0,
  PostgreSQL/gateway healthy, migration replay exited 0; the disposable
  `tinyassets-wave2-test_pgdata` volume was then removed.
- `python -m ruff check <all changed Python from origin/main...HEAD>`
  — clean.
- `openspec validate paid-market-track-e-wave-2-transport --strict`
  — valid.
- `openspec validate --specs --strict`
  — 26 passed, 0 failed.
- Claude runtime build/parity/import probe — passed for 264 mirrored files.
- Independent reviews:
  `docs/audits/2026-07-24-paid-market-wave2-transport-implementation-review.md`
  and
  `docs/audits/2026-07-24-paid-market-wave2-transport-followup-review.md`;
  the final narrow APPROVE is
  `docs/audits/2026-07-24-paid-market-wave2-transport-final-rereview.md`.

## Commits

- `1c4cd8c5` — record transport baseline.
- `2ba2f33a` — canonical spot settlement postings.
- `58aa9577` — replay-safe fixture migrations.
- `98711be1` — dark settlement transport.
- `9b6d9c74` — hardened fixture ledger boundary.
- `bc18841a` — reconciled economics and gates.
- `39f2fe7f` — SQL bounds and hostile-search-path tests.
- `72ab2a75` — trusted authority verifier requirement.
- `a57ebecd` — end-to-end canonical settlement enforcement.
- `3759b2a9` — complete fixture baseline checks.
- `acce051b` — migration/RLS/security review fixes.
- `48033137` — unified positive-gross fee oracle.
- `a02d0a71` — final review hardening and dependency rationale.
- `bc732ab0` — closed the final NULL-invariant and runner-neutral ACL
  fingerprint review gaps.

Push target: `origin/codex/osx-paid-market-transport`; the final handoff push
includes all implementation, review evidence, task classifications, and this
report. No pull request was opened.
