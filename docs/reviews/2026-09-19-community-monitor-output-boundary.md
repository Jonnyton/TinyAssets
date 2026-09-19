# Community watcher output boundary — candidate evidence

September 19, 2026. Isolated branch `codex/monitor-unavailable-signal`, based on
main `4cbb3f5b`. This is candidate evidence, not a deployed or all-uptime claim.
No live workflow failure, incident mutation, account or provider call induced.

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

Final exact-head independent review, required CI, merged-source verification
and actual hosted normal-path result remain pending.
Failure injection is isolated test evidence, not a production crash experiment.
Natural cron, real measured-green receipt, execution-quality and rendered-user
coverage remain open under the existing change and concerns.

## Rollback

If hosted normal-path behavior regresses, revert this workflow/test/spec patch
through the normal reviewed release path. There is no data/schema migration to
undo. Never restore missing evidence by granting private tenant authority or
closing an incident from incomplete output.
