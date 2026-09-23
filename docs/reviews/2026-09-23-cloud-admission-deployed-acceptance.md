# Cloud admission — deployed slice and acceptance

Verified September 23, 2026 UTC. This is partial closeout of application guards,
not completion of the cloud-only boundary or free-user onboarding.

## Reviewed, tested and deployed

- PR [3919](https://github.com/Jonnyton/TinyAssets/pull/3919) merged as
  `042cdce86774676d5674f8e4bd67b4337c12a792` at 01:18:43 UTC.
  Its tree equals reviewed head `650f486f180163d3842a3c945df2899f29ec9786`
  (`git diff --stat 650f486f origin/main`, empty immediately after fetch).
- Independent Claude Opus approved that exact head; public review artifact
  [5786972437](https://github.com/Jonnyton/TinyAssets/pull/3919#issuecomment-5786972437).
- Hosted Linux [35804412934](https://github.com/Jonnyton/TinyAssets/actions/runs/35804412934)
  passed: 20,364 passed, five known failures and two known errors, 100 skipped,
  10 deselected; aggregator zero new failures / zero stale quarantine.
  The superseded ready-transition run was cancelled, not a regression result.
- Docker [35803560212](https://github.com/Jonnyton/TinyAssets/actions/runs/35803560212)
  proved default unadmitted image exit78/no listener and full protocol through an
  explicitly simulated-admission fixture. That fixture is not cloud evidence.
  Packaging, desktop builds/install, slow tests, lint and invariants also passed.
- Hosted image build [35805770946](https://github.com/Jonnyton/TinyAssets/actions/runs/35805770946)
  and deploy [35805988252](https://github.com/Jonnyton/TinyAssets/actions/runs/35805988252)
  passed. Deployment installed expected identity before startup at 01:22:25 UTC.
  Public `mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  passed at 01:23:12 UTC. Protected `deployed_sha.py --report-provenance
  --assert-contains 042cdce86774676d5674f8e4bd67b4337c12a792` passed at 01:23:19.
  Answering process: cloud / instance_match / observed=true / enforced=true.
- Earlier record-only PR3917 deployment [35704475424](https://github.com/Jonnyton/TinyAssets/actions/runs/35704475424)
  had proved cached CLOUD at 08:23 UTC September 22 before refusal was enabled.
  Expected state survives receipt replacement/redeployment; rollback compatibility
  has structural tests in `tests/test_expected_instance_state_preparation.py`,
  not an actual production rollback drill.

## Rendered ordinary-app acceptance

After verified deployment, the owner Chrome app received exactly
`Retest your workflow checklist` once at 18:24 PDT September 22.
Original response completed 18:29 PDT (01:29 UTC), without refresh or replay:

- App reported five controls PASS: inplace edit/output
  `b922d500122c490d`, discard `e08dee2d64ae48ae`, and matching live status /
  cancellation `04f87ff3f8dc4dad`.
- The single-node 171-character reply was a clarifying question, NOT a literal
  RETEST11 echo. Do not infer exact output-content success from its PASS label.
- Sequential `ba65cb04628d4d83` completed 49.9s, three fields; parallel
  `f6bf659f1173432a` completed 44.0s, five fields.
- App explicitly left both historical intermittent failures OPEN; this clean run
  does not establish their cause or resolution.
- Answered by claude-code / claude-sonnet-4-6. No operator private-workflow edits,
  no free-account actions, no duplicate dispatch. No newer organic owner use
  visible at this verification; this is test-request acceptance.

## Scope and remaining work

Main specs now describe the deployed process cache, mandatory assigned claims,
worker provisioning/exact-worker eligibility, startup/provider gates, cached
origin backstop and assigned-consumer startup/polling. Existing tray subprocess
controls and REST discovery remain, but are not execution authority.

This does NOT prove exclusive cloud credential custody, hardware attestation,
binary freshness from a mutable receipt, every worker, or complete named recovery
path coverage. Connector API access still returned 401 in hosted preflight;
custody and SSH host trust remain unknown. Non-assigned lease acquisition and an
unreferenced provider cloud literal remain coverage findings, not proved bypasses.
Free-only OAuth, product disconnect/reset and the user's first tool-capable
answer remain untested under the agreed general-flow readiness requirement.
The overall change stays open; partial spec sync is not archive/completion.
