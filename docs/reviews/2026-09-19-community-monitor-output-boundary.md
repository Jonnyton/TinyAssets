# Community watcher output boundary — verified hosted release

September 19, 2026. Isolated branch `codex/monitor-unavailable-signal`, based on
main `4cbb3f5b`. Candidate evidence below is followed by the exact hosted release
receipt. This is not an all-uptime claim. No live crash, account or provider call
was induced for this verification.

## Independent pre-build review

Claude Fable review26240, frozen `f4eb36e2`, exited0 in264s, **APPROVE**.
Root read its complete output/monitor-unavailable-shape-review.md. Reviewer
independently reproduced16red tests in1.23s and confirmed actual shell semantics:
parser failure under set-e prevents outputs; continue-on-error hides it; the
old red-only gate skips. Empty dict manufactures red and incomplete green can
recover. Approved minimal inline validation plus distinct always-run job failure,
with unknown still authorizing zero REST calls. This approval gates shape, not
the later implementation head or full uptime acceptance.

Accepted minor follow-ups: explicit matching red/exit1 rejection test, exact
heredoc delimiter extraction, and proof the existing Node alarm tests actually
execute rather than skip. Keep existing stderr merge fail-loud for this slice;
split only if real normal-path output demonstrates a need. No new notifications,
stale-source ordering, scheduler or endpoint authority is bundled.

## Candidate implementation and local proof

The existing inline parser validates version2 dictionary/overall/stages and
integer exit_code matching actual process exit. Only red2/3 and non-red0 are
recognized. Invalid output emits unknown/unavailable. A separate always-run gate
fails missing/unavailable output, including parser/output-write/setup failure;
valid unknown is classification success. Sink code is unchanged. No new module,
API, runtime table or secret. Delta and canonical specs describe this boundary.

Windows Python3.14 command:
`python -m pytest -q -rs tests/test_community_watch_result_boundary.py
tests/test_community_loop_typed_observation.py tests/test_community_loop_watch.py
--tb=short`: **61 passed in2.35s, zero skips**. This executes the actual inline
parser and existing alarm JavaScript under Node, including unknown/yellow no
mutation and real-red/literal-green controls. New tests were16red before code;
three additional rejection cases pin red1, non-integer version and non-list stages.

Existing workflow-structure suite separately reports3passed/1failure: the exact
pre-existing `createTinyAssetsDispatch` assertion already in the unchanged
known-failing ledger at line41. The alarm script is untouched by this patch.
Ruff and whitespace checks pass after import ordering correction. Local actionlint
is unavailable (same known environment); hosted actionlint remains mandatory.

Same three files on Linux Python3.11: **61 passed in11.22s, zero skips**.
Used WSL Ubuntu Docker, existing image tinyassets-workspace-browser-probe:e2d3edcc
verified as sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a;
read-only /src mount of this worktree, network none, TMPDIR=/tmp,
TINYASSETS_DATA_DIR=/tmp/tinyassets-test-data, PYTHONDONTWRITEBYTECODE=1 and
`python -m pytest -q -rs -p no:cacheprovider` plus the same three file names.
Node alarm tests executed without skips on both platforms.

## Verified hosted release — September19,10:12UTC

Fable final review18623 exited0/224s, **APPROVE**, exact head
`ccbf074a52c60c0efced30054d4d3219725259c2`; complete review is retained in
[PR3885 comment5740809614](https://github.com/Jonnyton/TinyAssets/pull/3885#issuecomment-5740809614).
Required Tests35435267457 succeeded: required-tests30m38s, slow-tests1m29s.
Hosted actionlint35435242518, invariants and corrected scope gate35435305004
passed. No required gate or known-failure ledger was weakened.

PR3885 merged10:09:48UTC as `3a2257f221bd1faa543f15a0590896232dd42d93`.
GitHub contents API at that revision and local reviewed-head git both return
workflow blob `33d97bca4232ecab5905b613a3867b3d12dabb40`.
Actual automatic push-triggered [hosted run35436644441](https://github.com/Jonnyton/TinyAssets/actions/runs/35436644441)
checked out that merge SHA. Summary reported **monitor available**; the new
unavailable gate skipped, while the existing red gate failed with exit2 because
the separate incident stage retained existing incident2824. The observation
stage stayed unknown. Alarm sink succeeded and made its ordinary retained-red
[comment5740953838](https://github.com/Jonnyton/TinyAssets/issues/3646#issuecomment-5740953838).
The workflow's overall failure is that preserved incident behavior, not a
watcher/parser regression. Normal structured output was not polluted by stderr.

Downloaded actual hosted junit artifact10582635771 (`junit-required-tests`)
from the required run. XML inspection verifies all61focused cases executed:
19 output-boundary,38typed-observation,4existing-watch; **zero skips, zero
failures/errors**, including the actual Node alarm-script controls.
Commands: `gh run view 35435267457 --json status,conclusion,jobs`;
`gh run view 35436644441 --json jobs,event,headSha,conclusion,url` and `--log`;
`gh run download 35435267457 --name junit-required-tests`; contents API for the
exact merged workflow and `git rev-parse ccbf074a:.github/workflows/community-loop-watch.yml`.

Failure injection remains isolated test evidence, not a production crash
experiment. Natural schedule classification is separately verified in
[the09:42receipt](2026-09-19-natural-scheduled-classification-proof.md).
Real measured-green receipt, schedule cadence, execution-quality and rendered
coverage remain open. Actions-only source/run proof requires no daemon restart;
no new ordinary user-chat acceptance or all-uptime completion is claimed.

## Rollback

If hosted normal-path behavior regresses, revert this workflow/test/spec patch
through the normal reviewed release path. There is no data/schema migration to
undo. Never restore missing evidence by granting private tenant authority or
closing an incident from incomplete output.
