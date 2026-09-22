# Owned run activity: deployment and rendered acceptance

## Scope and release

PR [3909](https://github.com/Jonnyton/TinyAssets/pull/3909) exposes typed saved
per-node timing and returned-model evidence through existing authorized run reads.
It does not fix historical intermittent failures or prove provider admission,
first-byte timing, exact cancellation, or absence of a response.

Reviewed head: `82f12ec5eee0ee99d1836753ce6e2c369eb46683`.
Merged/deployed: `8f4ee4a84e23a3fb92cfeaa9ba2541ab22c73102`.
Fable shape review13185 recommended this approach. Exact review34490 requested
placing diagnostics after legacy text guidance; adapted head received independent
Fable81316 APPROVE (exit0,166s; eight surface tests independently passed).
[Exact-head approval receipt](https://github.com/Jonnyton/TinyAssets/pull/3909#issuecomment-5770107733).
Opus authored pure tests but timed out before reporting; no passing peer verdict
is inferred. Lead read and executed them.

## Verification, September22,2026 UTC

- Windows Python3.14 selected five test files:218passed,3unchanged skips;
  baseline cad07bd0 selected original three files:93passed,3skips.
- Linux oracle Python3.11.15:221passed,no skips; baseline96passed,no skips.
  Command: `python scripts/linux_oracle.py -- -q tests/test_run_activity.py
  tests/test_run_activity_surface.py tests/test_run_snapshot_phase.py
  tests/test_graph_answer_execution.py tests/test_engine_mcp_server.py`.
  Windows uses the same selection with `python -m pytest -q`.
- Ruff, strict change validation, seven invariants,497-file plugin mirror/import
  and diff check passed. No ledger or skip changes.
- Hosted [Tests35677381985](https://github.com/Jonnyton/TinyAssets/actions/runs/35677381985)
  passed:20056passed,100skipped,10deselected,5known failures and2known collection
  errors; aggregator0new failures/0stale quarantines. Slow10passed,1skip.
  Reviewed/tested/merged commits share tree22a13f560e11da9aa7658a3e00f49419f6f467a1.
- Build35678485980 and [deploy35678724170](https://github.com/Jonnyton/TinyAssets/actions/runs/35678724170)
  succeeded. Image `sha256:b3298c3c45bc6102914ebfd995e4cdb0f3454a5769bd3d57c7e013bd32c209ba`.
  Hosted `mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  passed. Protected `deployed_sha.py --assert-contains` reports production
  contains the merged SHA at02:15:37.2425425UTC. Evidence: completed job logs.

## Rendered app acceptance

Owner-authorized existing authenticated TinyAssets app conversation, Chrome
extension primary mission tab; not first-contact/onboarding proof. Free account
and unrelated owner tabs were preserved. No operator workflow edits or direct
MCP calls. Existing idle conversation refreshed before the first prompt.

At02:19UTC sent exactly `Retest your workflow checklist` once. Original19:24PDT
reply arrived without refresh/replay: singlef96f845cac8e4713 completed4.9s,
sequentialfdb5e0b3185d496a completed44.8s, parallelcd31faf1b9884bde completed157.3s
with all nodes and five outputs. Agent obtained per-node elapsed values and
retracted its claim that angle_a is always slower; intermittent causes stay open.

At02:24UTC asked naturally to inspect earlier failed parallelabc24482d97a4d8b,
including completed calls and unknowns, without starting or rerunning work.
Original19:25PDT answer retrieved:

- split: stored return, local6.3s, claude-code/claude-sonnet-4-6.
- angle_b: stored return at1790029407.29, local182.5s, same provider/model,
  model_status reported, despite later run failure and empty output catalog.
- angle_a: local300.015s, timeout, null returned-call time/execution receipt.
- synthesis: pending, no observed start; no invented provider receipt.

The initial explanation overclaimed null as "never returned", conflated a
completion record with acknowledgment, and inferred why the output catalog was
empty. At02:27UTC sent one read-only correction request. Original19:27PDT answer
corrected null and catalog claims but newly asserted that `model_status: reported`
means provider acknowledgment of receipt/admission. That is false: the normalizer
sets reported iff a model name exists. Data access is observed; interpretation
acceptance is not claimed. No further coaching prompt was sent. Bounded Fable
review50428 finished exit0/113s, CLARIFY_SURFACE: the caveat can be lost after
long node lists and the existing model-status values need explicit definitions.
The follow-up preserves legacy guidance priority, then places the clarified
caveat before node activity. Two test assertions fail before and pass after.
Windows selected218passed/same3skips; lint/spec/mirror pass. Exact-head review,
CI, redeployment and uncoached live interpretation acceptance remain pending.
No organic post-fix owner use is visible.

## Clarification release

Follow-up [PR3910](https://github.com/Jonnyton/TinyAssets/pull/3910), reviewed
headabfc4865635dc538d2c400a7fefe8eaaf172c5b9, received independent Fable9757
APPROVE (exit0,117s; no reviewer tests). [Exact receipt](https://github.com/Jonnyton/TinyAssets/pull/3910#issuecomment-5770429108).
The reviewer agrees on producer semantics, legacy guidance, unchanged scope,
mirror, exact spec sync and focused regressions. Nonblocking note: unknown can
also mean no usable recorded model label, not literal absence of any provider
label; no admission/acknowledgment is established either way.

Required CI35680224724 passed:20056passed/100skipped/10deselected/5known failures/
2known collection errors/70subtests;0new failures/0stale quarantines. Job19m31s;
slow1m18s. Prior draft run35680053632 was cancelled by ready-event concurrency,
not a test regression. Main's earlier heavy-test failures were set-compared to
previous deployment: same101 identifiers, no new failure (runs35678486011 and
35674112352). No whole-suite-green claim or ledger edit.

Merged02:59:53UTC as02b1e628d2da54b2222a684f0318b19969c68a86. Reviewed head,
CI checkout907af248220206835fbe9cb378b71c90ee94c6b9 and actual merge share tree
7232ad1bb4f5e5175665b8b9ff166fc5623bf56c, verified by completed checkout logs,
exact git fetch and tree comparison. Image build35681508241 passed3m26s.
Deployment35681740530 passed1m14s. Protected receipt03:04:41.1061197UTC confirms
production contains02b1e628d2da54b2222a684f0318b19969c68a86; public handles
canary passed. Image `sha256:28a68ce42723b7823e27e67d13b5a089f625d897eec2046f065f7a189dcb7a4a`.
Verified from completed hosted deployment job logs.

At03:06UTC exact checklist prompt sent once after idle refresh; original20:10PDT
retest6 completed without replay or mid-turn refresh. Editing/output0b0ce5ae48e34e40
returned RETEST6 then restored; workspaceacb2e2ad9c324452 create/discard1.4s;
cancelled6a39c8bd93274506 around7s into60s hold; parallelb2a0b2c0b8374ad8
all4nodes52.5s, sequential3e63e98d7d594acb43.5s. This does not prove exact
underlying subprocess stop or resolve intermittent causes, which the app retains.
At03:12UTC asked naturally what saved evidence now establishes for earlier
failedabc24482d97a4d8b and what remains unknown, without start/rerun. No field
definitions or desired interpretation supplied. Original20:13PDT response arrived
without refresh/replay. It retrieved the prior failed run's split6.299s and
angle_b182.463s returned-model receipt, angle_a300.016s timeout with null receipt,
and pending synthesis. It explicitly defines reported as a recorded model
identifier, not acknowledgment/admission/validated output, and leaves provider
state and empty-catalog mechanism unknown. This accepts the scoped clarification.
It is not proof of every inference: the answer calls local starts dispatch and
pending/no-start never dispatched; these are not independent transport evidence.
Historical reliability remains open. No newer organic owner use visible; keep
the watch open. The already-shipped canonical requirement was compared against
the delta and matches. This documentation-only closeout archives the change;
it changes no runtime behavior and does not close wider reliability work.
