# Recovery-To-Normal Deploy Handoff — 2026-07-30

## Outcome

The public MCP surface is recovered on the previously configured immutable
image. The handoff and partial-target recovery repairs are landed, but current
`main` still fails startup against production-shaped state. Normal deployment
is paused until the PR #1991 diagnostic is hardened after independent review;
the next single controlled deploy will use only allowlisted, deadline-bounded
evidence to identify the startup regression.

Update at `2026-07-30T21:01Z`: repaired normal deploy `30581439569`
successfully handed off the recovered generation and installed the target, but
health convergence failed with only stopped `tinyassets-daemon` remaining.
Cleanup fenced that `restart=no` strict subset. Recovery `30582599465` then
failed closed because recovery admitted only empty or exact-five volume
inventories. A fresh public canary returned HTTP 502.

Update at `2026-07-31T05:21Z`: isolated recovery workflow run `30605922404`
restored the public MCP surface after normal deploy `30605692331` failed
current-main startup and its ordinary rollback. Fresh-volume Docker build smoke
run `30606140782` passed on `ba87b1dd`, narrowing the fault to
production-shaped state or environment. The failed candidate's logs were lost
to rollback, so the next repair preserves bounded private startup evidence
before any rollback mutation.

Update at `2026-07-31T05:35Z`: delayed deploy `30606095699` failed the same
health gate and ordinary rollback, returning public `/mcp` to HTTP 502. Guarded
recovery `30606863154` passed immutable-image admission, host pull, canonical
canary, exact-seven assertion, fence finalization, and proof upload. Independent
review of PR #1991 exact head `ca85479e` returned ADAPT: the public-repository
artifact could expose a tunnel token through Compose command status or arbitrary
daemon logs, collection had no hard deadlines before rollback, the manifest
used the workflow rather than candidate revision, and the upload action was
unpinned. No instrumented deployment is permitted until all four findings are
closed and independently re-reviewed.

## Production Evidence

- Diagnostic normal deploy run `30578541098` completed its stop-writer
  preflight and target installation but failed health convergence.
- Host evidence showed the exact five stopped containers retained
  `com.docker.compose.project=tinyassets-recovery-691142eb4348935e`.
- `tinyassets-daemon.service` starts the canonical default Compose project
  `tinyassets`. Because the service was inactive, restart did not execute a
  canonical-project teardown before start.
- Docker then refused creation of `/tinyassets-daemon` because the stopped
  recovery-project container still owned that fixed name.
- The workflow failed closed and returned production to `unsafe_fenced`.
- Provenance-bound recovery run
  [30578968815](https://github.com/Jonnyton/TinyAssets/actions/runs/30578968815)
  succeeded at `2026-07-30T20:26:23Z`, including the canonical MCP canary,
  exact-seven surface assertion, and fence finalization.
- Fresh local public-canary verification on 2026-07-30 (Windows host):
  `py scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
  --assert-name TinyAssets --assert-handles` exited `0`.
- Normal deployment
  [30605692331](https://github.com/Jonnyton/TinyAssets/actions/runs/30605692331)
  installed immutable current-main digest
  `38441153394980b49774d1a2469599173e01850b2ee51c958f64eaffc00f953b`
  at revision `098fdd963e73069a98c15c312231dbc84688a75b`, but the daemon did
  not become healthy within 90 seconds. Ordinary rollback then failed and the
  workflow fenced the remaining partial fleet.
- Provenance-bound recovery
  [30605922404](https://github.com/Jonnyton/TinyAssets/actions/runs/30605922404)
  succeeded and restored the previously admitted immutable image.
- Fresh-volume Docker smoke
  [30606140782](https://github.com/Jonnyton/TinyAssets/actions/runs/30606140782)
  passed for current `main` revision `ba87b1dd`, including the local MCP
  canary. This contradicts a universal image/import failure and points to
  production-shaped startup inputs.
- Fresh local public-canary verification at `2026-07-31T05:21Z` (Windows
  host): `python scripts/mcp_public_canary.py --url
  https://tinyassets.io/mcp --assert-name TinyAssets --assert-handles
  --verbose` exited `0`.

## Root Cause

Emergency recovery correctly creates a restart-fenced generation under a
unique Compose project and preserves its exact IDs in durable state.
Finalization restores service boot posture but intentionally does not recreate
those containers under the canonical project. The next normal preflight stops
the recovered generation and overwrites canonical fence state with the new
run's exact old IDs. Before this repair it discarded the prior recovery
project/ID provenance, and `prepare_deploy` only unmasked the service. The
stopped recovery containers therefore survived into canonical Compose start.

## Repair

`preflight` now recognizes recovery provenance only from a prior `restored`
state. Before any host mutation it requires:

- the recorded recovery run to derive the exact recorded project name;
- the recorded IDs to cover exactly the daemon plus four workers;
- current inspected IDs to equal those durable IDs; and
- every current Compose project label to equal that exact recorded project.

It carries the bounded handoff into the new run's write-ahead state.
`prepare_deploy`, after its existing queue, receipt, and stopped-old-ID checks,
requires the same exact five IDs, labels, stopped states, and `restart=no`
policies. It writes removal intent, runs `docker rm` on only those exact IDs
without `-v`, proves the production-volume container inventory empty, records
completion, and only then unmasks the canonical service. After durable intent,
a strict remaining subset is replayable only when every survivor retains its
recorded identity and safety posture, every missing recorded ID is proved
absent, and there are no extra writers. Before intent, partial absence fails.
Substituted, running, restart-enabled, and foreign-project survivors fail.

Ordinary canonical predecessors have no recovery handoff record and keep the
existing systemd lifecycle.

The follow-up recovery repair recognizes only a strict subset of expected
canonical target names whose exact image/revision equals the durable target,
whose Compose project is exactly `tinyassets`, and whose containers are
stopped with `restart=no`. Every missing expected name must be absent across
all container states. It writes observed IDs before `docker rm`, removes
without `-v`, and replays only the remaining recorded subset after an
interruption. Extra, foreign, running, restart-enabled, substituted, and
same-name off-volume states fail before removal.

## Verification

TDD red evidence on 2026-07-30:

```text
5 failed, 2 passed, 90 deselected
```

The failures covered the reproduced no-removal behavior, discarded recovery
provenance, partial/foreign drift, and absent removal-intent replay state.

Green evidence on 2026-07-30 (Windows host):

```text
py -m pytest -q tests/test_retire_cheat_loop_deploy_fence.py
100 passed in 2.71s

py -m ruff check scripts/retire_cheat_loop_deploy_fence.py tests/test_retire_cheat_loop_deploy_fence.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict
Change 'repair-recovery-deploy-handoff' is valid
```

The suite includes a full unsafe-recovery → finalization → next normal
preflight → exact removal path, ordinary canonical preservation, mismatch
before first mutation, partial/foreign/running/restart-policy refusal, and
crash-after-removal replay, including injected strict-subset removal followed
by successful exact-survivor replay.

Independent review of head `01724e33` returned ADAPT: multi-ID `docker rm` is
not transactional, so strict-subset success had no replay path, and the change
needed an explicit sync/archive closeout task. Both findings are addressed in
head `65a12e1c`. Independent exact-head re-review returned APPROVE after fresh
evidence of 100 focused tests, clean Ruff and diff checks, and strict OpenSpec
validation.

Follow-up P0 verification on 2026-07-30 (Windows host):

```text
py -m pytest tests/test_retire_cheat_loop_deploy_fence.py -q
112 passed in 3.81s

py -m ruff check scripts/retire_cheat_loop_deploy_fence.py tests/test_retire_cheat_loop_deploy_fence.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict
Change 'repair-recovery-deploy-handoff' is valid
```

Two independent reviews of head `8486ca53` returned ADAPT because an
empty-inventory replay did not rebind the write-ahead record's
image/revision/project and did not prove every expected container name
globally absent. An existing plan could also encounter a full or substituted
volume fleet and fall through to a different remover. The follow-up binds plan
metadata before inventory branching, requires the observed volume names to
remain a subset of the write-ahead names, and proves all expected names absent
both on empty replay and after exact-ID removal. Five additional regression
cases cover off-volume name substitution, a full replacement fleet, and each
plan-metadata substitution. Exact-head independent re-review is pending.

Twelve new tests cover production-shaped partial-target recovery, write-ahead
replay after interrupted subset removal, and refusal of foreign-project,
running, restart-enabled, foreign-image, and same-name off-volume states.

Failed-candidate diagnostic verification at `2026-07-31T05:21Z` (Windows
host):

```text
python -m pytest tests/test_deploy_prod_workflow.py \
  tests/test_build_image_workflow.py tests/test_release_reconcile_workflow.py -q
127 passed in 22.55s

python -m ruff check tests/test_deploy_prod_workflow.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict
Change 'repair-recovery-deploy-handoff' is valid
```

This first diagnostic implementation is not approved for deployment.
Independent exact-head review of `ca85479e` returned ADAPT because artifacts in
this public repository are not an operator-only confidentiality boundary;
Compose status can serialize a token-bearing tunnel command, raw logs are not
secret-free, three SSH operations could consume the remaining job deadline
before rollback, the manifest could name the wrong revision, and
`actions/upload-artifact` was not pinned. The hardening successor retains only
allowlisted daemon state and structural traceback signals, bounds local SSH and
remote Docker calls, binds the manifest to the fence-proved target revision,
pins the upload action, and moves artifact publication after rollback and
restart-racer cleanup.

Hardening verification at `2026-07-31T05:44Z` (Windows host):

```text
python -m pytest tests/test_deploy_prod_workflow.py \
  tests/test_build_image_workflow.py tests/test_release_reconcile_workflow.py \
  tests/test_sanitize_startup_diagnostics.py -q
130 passed in 23.18s

python -m ruff check scripts/sanitize_startup_diagnostics.py \
  tests/test_sanitize_startup_diagnostics.py tests/test_deploy_prod_workflow.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict
Change 'repair-recovery-deploy-handoff' is valid
```

Secret fixtures cover token-bearing Compose command text, bearer credentials,
arbitrary source lines, unapproved `/data` and traversal paths, and
attacker-named exception types. None survive the fixed-schema sanitizer.

Exact-head re-review of PR #1992 at `250fc995` returned ADAPT: a forged
traceback could still place token text in a syntactically valid `/app` path or
function/line field, the target revision was not independently bound to the
inspected container, and cancellation was distinct from `failure()`. The
successor maps frames only to source paths proved present in the public
checkout, emits neither function nor line, collects raw logs only after both
the container's immutable image ref and OCI revision equal the fence-proved
target, and routes cancellation through the same bounded capture and
post-rollback/cleanup upload conditions. Adversarial fixtures now cover
valid-looking forged frames and identity mismatch; workflow structure tests
pin cancellation semantics.

The next exact-head review at `809cdb7a` returned ADAPT on three final safety
edges: a post-mutation deploy/assertion failure could skip the named health step
and therefore skip capture; upload ordering did not prove cleanup had restored
or authoritatively fenced the fleet and published terminal truth; and
syntactically valid mismatched image/revision values were still copied into the
public artifact. Capture now keys on any `failure() || cancelled()` after the
durable image-mutation marker. Upload requires diagnostic success, explicit
restored-or-safely-fenced cleanup output, and a published terminal receipt.
Mismatched observed identities are emitted only as `unavailable`.

Live instrumented deploy `30610115079` at revision `0eec432c` proved capture,
cleanup fencing, terminal publication, and artifact upload, but the artifact
reported `candidate_identity_match=false` with no state or signals. The Docker
format string emitted literal `\t` text while the validator split on actual tab
characters. Guarded recovery `30610348776` restored the public MCP canary and
exact-seven surface. The framing repair uses literal `|` between eight fields;
all accepted field grammars exclude that separator, and focused tests reproduce
the failed pipe input before proving exact image/revision acceptance.

Independent review of PR #1995 head `a5730730` returned ADAPT because the
workflow test proved only one separator occurrence, so a mutation of any other
boundary could survive. The successor locks the complete eight-field template,
asserts exactly seven identical separators, and passes a production-shaped
rendered record through `sanitize_candidate_state`. Fresh Windows-host evidence
at `2026-07-31T17:56Z` is 133 focused tests passed, clean Ruff and diff checks,
and strict OpenSpec validation. Independent exact-head re-review of
`c6bccf05a29cb5a58fe987fde9682deb0dabdb61` returned APPROVE with no findings
after additionally mutation-checking all seven delimiter boundaries and pipe
injection into every accepted field.

Controlled deploy `30653950641` then proved the repaired identity join in live
production: the artifact bound digest `18b97e...d60a` and revision `0eec432c`,
with Docker state `created`, `running=false`, `restarting=false`, `exit_code=0`,
no health state, no OOM, and zero log bytes. The candidate process therefore did
not start; this contradicts the earlier application-startup hypothesis and
moves investigation to Docker/systemd/Compose start orchestration. Ordinary
rollback could not prove a safe fleet, so exact-source guarded recovery
`30654162258` restored the canonical MCP canary and exact-seven assertion and
completed successfully. The next evidence slice must classify Docker's
identity-bound pre-start error without publishing raw host error text.

## Release And Rollback

Land only after independent exact-head fail-closed/security review. Build an
immutable image, then run one normal deploy from the currently finalized
recovery generation. Acceptance requires canonical exact-five proof, restored
fence state, and a fresh public MCP canary. On failure, use only the existing
provenance-bound unsafe recovery workflow with the prior admitted stop-writer
image; do not delete containers directly or bypass the fence.
