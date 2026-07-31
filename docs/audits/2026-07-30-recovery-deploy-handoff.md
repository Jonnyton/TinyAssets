# Recovery-To-Normal Deploy Handoff — 2026-07-30

## Outcome

The public MCP surface is recovered on the previously configured immutable
image. The writer-fleet handoff and partial-target recovery repairs are landed.
Read-only diagnostic run `30664801072` has now reduced the remaining
production-shaped startup failure to exact fixed-name conflicts on both
`tinyassets-tunnel` and `tinyassets-logs`. A fail-safe sidecar handoff repair is
under local verification; no further production mutation is permitted until
its independent exact-head review approves.

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
- Read-only bounded journal run `30664801072` at revision `0df587ef` returned
  only the fixed schema and classified `conflict_containers` as exactly
  `tinyassets-tunnel` and `tinyassets-logs`; it published no raw journal text
  and performed no host mutation.

## Root Cause

Emergency recovery correctly creates a restart-fenced generation under a
unique Compose project and preserves its exact IDs in durable state.
Finalization restores service boot posture but intentionally does not recreate
those containers under the canonical project. The next normal preflight stops
the recovered generation and overwrites canonical fence state with the new
run's exact old IDs. Before this repair it discarded the prior recovery
project/ID provenance, and `prepare_deploy` only unmasked the service. The
stopped recovery containers therefore survived into canonical Compose start.

The remaining sidecar collision is the same ownership-boundary defect outside
the production data volume. Emergency recovery intentionally started only the
five receipt-capable writer containers, so the canonical-project tunnel and
log sidecars survived and continued serving ingress/logging. A later normal
preflight fenced only production-volume consumers. When systemd was already
inactive, canonical Compose could not tear down those surviving fixed-name
sidecars and failed while creating the new project.

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

The sidecar repair binds each present tunnel/log container by exact ID, exact
Compose project/service labels, non-writer mounts, and saved restart policy.
Preflight fences and stops them; target preparation records removal intent and
removes only exact surviving IDs without `-v`, including subset/empty replay.
If forward start and ordinary rollback both fail, unsafe recovery removes only
a newly proved canonical or recovery-owned sidecar generation, starts both
sidecars under the unique recovery project with `restart=no`, and durably binds
their IDs. A partial sidecar Compose start is captured, stopped, removed by
exact ID, and retried once within the same recovery invocation. A repeated
failure is durably captured and refenced. Finalization restores saved policies,
or canonical `unless-stopped` for a previously absent sidecar.

## Verification

Fixed-name sidecar repair verification at `2026-07-31T21:32Z` (Windows host):

```text
python -m pytest tests/test_retire_cheat_loop_deploy_fence.py \
  tests/test_deploy_prod_workflow.py \
  tests/test_diagnose_prod_startup_workflow.py \
  tests/test_sanitize_systemd_startup_diagnostics.py -q
248 passed in 8.19s

python -m ruff check scripts/retire_cheat_loop_deploy_fence.py \
  tests/test_retire_cheat_loop_deploy_fence.py \
  tests/test_deploy_prod_workflow.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict --no-interactive
Change 'repair-recovery-deploy-handoff' is valid

git diff --check
clean
```

The new cases cover canonical and recovery-project sidecar ownership, foreign
and substituted refusal, exact-ID subset replay, emergency recreation,
partial-start durable refencing and retry, restart-policy finalization, and the
next normal handoff. Empty/foreign Compose projects and sidecars mounting the
production data volume also fail before sidecar mutation. Independent
exact-head review is pending. A foreign fixed-name blocker remains untouched
while the proved recovery writers are still refenced; a recovery-owned sidecar
with an unexpected data mount is ID-bound and stopped but never removed.

Autonomous partial-start retry verification at `2026-07-31T21:40:40Z`
(Windows host):

```text
RED: python -m pytest \
  tests/test_retire_cheat_loop_deploy_fence.py::\
test_partial_recovery_sidecar_start_is_durably_refenced_and_retryable -q
1 failed: recovery failed and was re-fenced: partial sidecar compose failure

GREEN: python -m pytest tests/test_retire_cheat_loop_deploy_fence.py \
  -q -k "partial_recovery_sidecar_start"
2 passed, 128 deselected in 0.51s

python -m pytest tests/test_retire_cheat_loop_deploy_fence.py \
  tests/test_deploy_prod_workflow.py tests/test_build_image_workflow.py \
  tests/test_diagnose_prod_startup_workflow.py \
  tests/test_sanitize_startup_diagnostics.py \
  tests/test_sanitize_systemd_startup_diagnostics.py -q
264 passed in 9.27s
```

The bounded path retries only after durable exact-project/service/ID capture
and exact-ID removal of a non-writer partial fleet. A second transient failure
ends the loop at attempt two, leaves the new partial ID restart-fenced, and
returns the writers to `unsafe_fenced`. Independent exact-head review remains
required before publish or production mutation.

Independent review of `95cdeca6` returned ADAPT at `2026-07-31T21:48Z`:
post-capture fixed-name substitution could make cleanup and `quiesce_unsafe`
repeat the same identity rejection before the five-writer fence began. A
zero-exit Compose result with one missing sidecar also bypassed the retry. The
replacement adds a writer-first invariant: name drift is recorded, a captured
exact ID that still exists is restart-fenced and stopped by ID without removal,
the current fixed-name replacement is untouched, and the volume-writer fence
continues independently. Strict inventory capture now occurs inside the bounded
attempt so zero-exit incomplete creation follows the same exact-ID retry path.

Adaptation evidence at `2026-07-31T22:04:26Z` (Windows host):

```text
RED replacement-only substitution: 1 failed
recovery failed ... re-fence also failed: recovery sidecar identity changed

RED rename+replacement and zero-exit incomplete inventory: 2 failed

RED stubborn captured sidecar stop: 1 failed before writer fencing

Re-review of `47bd47a8` found one remaining eager outer-handler restart-fence
operation that could throw before `quiesce_unsafe`. Its exact regression failed
with all five writers still running. The duplicate eager sidecar mutation is
removed; outer recovery now only captures partial ownership evidence and always
delegates restart/stop handling to the single writer-first quiesce path.

GREEN focused replacement/rename/incomplete/stubborn/restart cases:
5 passed, 130 deselected in 0.63s

python -m pytest tests/test_retire_cheat_loop_deploy_fence.py \
  tests/test_deploy_prod_workflow.py tests/test_build_image_workflow.py \
  tests/test_diagnose_prod_startup_workflow.py \
  tests/test_sanitize_startup_diagnostics.py \
  tests/test_sanitize_systemd_startup_diagnostics.py -q
269 passed in 8.46s
```

The replacement-only case proves all five writers stop while the substituted
non-writer receives no update/stop/remove command. The rename-plus-replacement
case additionally proves the original captured ID is stopped under its new
name while the fixed-name replacement remains untouched. New exact-head review
is required before publish or production mutation. The stubborn-sidecar case
proves its recorded stop error survives as evidence while all five volume
writers still converge to `unsafe_fenced`.

Independent re-review APPROVED exact code head `a3335dfa`: the outer recovery
handler performs evidence capture only, every sidecar restart/stop operation is
centralized behind the writer-first quiesce boundary, all five adversarial
regressions passed, and the reviewer found no remaining blocking security or
correctness issue. PR #2010 carries the four-commit repair stack; production
remains unchanged until CI, merge, and the controlled deploy gate complete.

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

The successor capture appends only Docker's JSON-escaped `.State.Error` as the
final identity record field, caps the complete record at 16 KiB, and splits only
the eight preceding fixed boundaries so delimiter text inside the error cannot
change field identity. The sanitizer parses a JSON string and emits one fixed
class (`none`, port, mount, permission, network, runtime, or `other`) only after
the image/revision join succeeds; mismatch, malformed JSON, and oversize input
fail unavailable. Raw error text never enters the artifact. Windows-host
verification at `2026-07-31T18:24Z`: 136 focused tests passed, Ruff and diff
checks clean, and strict OpenSpec validation passed. Independent exact-head
review of `bf81cb284bd58775dd73eae7bb1e48f22b8e77c2` returned APPROVE
with no findings after hostile shell payloads, every trusted-field pipe
injection, malformed/non-string JSON, invalid UTF-8, oversize input, and
identity mismatch all failed without raw-text disclosure.

Controlled deploy `30655656939` reproduced the exact candidate at revision
`0eec432c` and returned `start_error_class=none`: Docker created the daemon
container but never attempted its start. This eliminates Docker runtime-start
failure as the current boundary and points to systemd/Compose orchestration
between create and start. Exact-source guarded recovery `30655881616` restored
the canonical canary, exact-seven surface, and finalized successfully. Because
the relevant unit journal persists, the next diagnostic is read-only: classify
the bounded `18:34Z`-`18:37Z` journal window on the host and return fixed signals
only, without another deployment or raw journal publication.

The diagnostic workflow accepts two strict UTC-second timestamps, rejects
future, reversed, or over-ten-minute windows, and performs only a bounded
`journalctl` read over SSH. At most 256 KiB flows directly into the runner-side
sanitizer; SSH stderr and all journal text are suppressed, and there is no host
write or artifact upload. Output is limited to fixed Compose stages, fixed
failure classes, a derived stage, and bounded counts. Windows-host verification
at `2026-07-31T18:48Z`: 142 focused tests passed, Ruff and diff checks clean,
and strict OpenSpec validation passed. Independent exact-head review remains
required before reading the preserved production window.

Independent review of PR #2002 head `173941b8` returned ADAPT: the byte cap ran
after SSH and allowed a 262,145-byte sentinel into the sanitizer; marker union
across retries could let an earlier `Started` hide a terminal `Created`; and
workflow tests recognized validation text without executing the validator or
fully locking publication/PIPESTATUS behavior. No production diagnostic ran.

The successor caps exactly 256 KiB on the production host before SSH, checks
both remaining pipeline statuses, and classifies only the suffix beginning at
the final daemon `Creating` marker. Timestamp validation moved into the
sanitizer module and is behavior-tested against shell payloads, malformed dates,
future, reversed, and over-ten-minute windows. Workflow tests lock the validator
invocation, both pipeline statuses, source-side cap, and absence of summary,
output, `tee`, artifact, GitHub, or host-mutation sinks. Fresh Windows-host
evidence at `2026-07-31T19:04Z`: 149 focused tests passed, Ruff and diff checks
clean, and strict OpenSpec validation passed. Exact-head re-review is pending.

Re-review of `fa542a47` remained ADAPT: a retry may begin at `Starting` without
another `Creating`; a container-name conflict disappeared behind the known
restart signal; the source-side cap could not report its own truncation; and the
OpenSpec delta did not state these decision-critical requirements. The next
successor frames one truncation byte plus a bounded payload within the same
256 KiB transport ceiling, anchors the terminal phase at the last daemon
`Creating` or `Starting`, preserves name-conflict and line-level unknown classes,
and specifies each invariant. No production diagnostic has run.

The successor now treats the later of the last daemon `Creating` or `Starting`
as the terminal phase boundary, adds an exact container-name-conflict class,
and detects unclassified failure lines independently of known classes. The
source stream uses a bounded five-chunk deque: a one-byte truncation flag plus
at most 262,143 payload bytes crosses SSH, so the complete transport never
exceeds 256 KiB and truncation remains truthful. The remote line cap was removed
so it cannot silently discard evidence. Fresh Windows-host evidence at
`2026-07-31T19:20Z`: 152 focused tests passed, Ruff and diff checks clean, and
strict OpenSpec validation passed. Exact-head re-review remains pending.

Third review of `2731dbac` closed every runtime/security finding and returned
ADAPT only because OpenSpec named the additive unknown enum `other` while code
and tests emit `other_failure`. The requirement now uses the exact implemented
enum; executable content is unchanged from the reviewed head.

Final exact-head review of `05a0c6719c8b528f3a592ed71b02ef489c65cc2c`
returned APPROVE with no findings after confirming the exact enum, unchanged
runtime/tests, strict OpenSpec validity, and that the production diagnostic
remains unrun.

Read-only diagnostic run `30659242692` validated its window and SSH setup, then
failed closed in the classification pipeline before printing any diagnosis.
Only the fixed error `bounded journal diagnosis failed` entered Actions logs;
no raw journal, artifact, output, summary, host mutation, or production outage
occurred. The run did not report which pipeline status failed, so changing the
remote shell would be speculative. The successor exposes only fixed numeric
`ssh_status` and `sanitizer_status`, reruns the same historical window, and then
changes only the proved boundary.

Rerun `30659887786` reported `ssh_status=1` and `sanitizer_status=0`, proving
the runner-side framed sanitizer succeeds and the remote command is the failing
boundary. No raw text or host mutation occurred. The successor sends a static
script over SSH stdin to explicit `bash -s` and assigns distinct fixed remote
exit codes to journal collection and framing, eliminating login-shell ambiguity
while preserving fail-closed localization.

The successor passes the static remote script through SSH stdin to `bash -s --`
with the already-validated timestamps as positional arguments. It captures the
remote two-command `PIPESTATUS`, exits 41 for journal failure and 42 for framing
failure, and retains the outer SSH/sanitizer fixed numeric report. Raw stderr and
journal text remain suppressed. Fresh Windows-host evidence at
`2026-07-31T19:47Z`: extracted Bash syntax passed, 152 focused tests passed,
Ruff and diff checks are clean, and strict OpenSpec validation passed.
Exact-head review approved the explicit Bash boundary before the read-only run.

Read-only run `30660879761` then returned `ssh_status=41` and
`sanitizer_status=0`, proving the explicit Bash transport and runner sanitizer
succeeded while `journalctl` itself returned nonzero. That code does not prove
why it failed. The leading compatibility hypothesis is the strict RFC-3339
`T...Z` input spelling: newer systemd accepts it, while older parsers document
and accept epoch syntax. The successor probes that hypothesis without mutation
by keeping the strict UTC input contract and converting locally to documented
`@<Unix-seconds>` arguments before SSH. This is timezone-unambiguous, compatible
with older systemd parsers, and does not broaden the workflow's read-only or
fixed-output surface. Exact-head review is required before another read-only
run.

Fresh Windows-host evidence at `2026-07-31T20:06Z`: 153 deployment-focused
tests passed, Ruff and diff checks are clean, the cross-provider drift guard is
clean, and strict OpenSpec validation passed. Local actionlint is unavailable;
the repository's pinned CI actionlint workflow remains the authoritative gate.

PR #2006 merged as `994d8f0e` after two exact-head independent APPROVE reviews
and all required CI checks. Read-only historical run `30662668227` then
succeeded on the preserved `18:34:00Z`-`18:36:36Z` window and emitted only the
fixed result: `created_without_start`, stages `container_create` and
`container_created`, with `container_name_conflict` plus downstream systemd
exit/restart and unclassified failure signals. No raw journal or production
mutation occurred. This proves a fixed-name collision but not which canonical
name collided; a sidecar explanation remains only a hypothesis until an
allowlisted-name classifier identifies the matching name.

The successor adds only `conflict_containers`, populated from the seven fixed
canonical names when they occur on a line already classified as a name
conflict. Token boundaries prevent a base worker name from matching a suffixed
worker. Arbitrary container IDs/names and all raw lines remain unavailable.
The first exact-head review returned ADAPT because line-wide case-folded token
matching could misidentify dot/underscore-embedded private names, Unicode or
case variants, or an unrelated allowlisted name elsewhere on a conflict line.
The replacement extracts only Docker's quoted conflicting-name operand from
the original terminal-attempt line, strips at most one leading slash, and uses
case-sensitive exact equality. Regressions cover every rejected form, multiple
conflicts, and terminal-attempt reset. Fresh Windows-host evidence at
`2026-07-31T20:54Z`: 165 deployment-focused tests passed, Ruff and diff checks
are clean, strict OpenSpec validation passed, and the cross-provider drift guard
is clean.

## Controlled deploy after sidecar handoff

PR #2010 merged as `85d40171`. Manual main build run `30669318410` successfully
published immutable image digest
`sha256:513efdf67cae52498c462bc3aa856adc47f31469ca0a1fb94a601f3fcd7fb753`.
The automatically triggered normal deploy `30669341874` then failed closed in
stop-writer preflight before file sync or candidate start. Rollback, restart
racer restoration, release-state publication, and proof upload all succeeded.
The bounded artifact reported only:

```json
{"error":"restored sidecar ownership is invalid: tinyassets-tunnel","safe":false,"stale_state_ignored":true}
```

Current state remained `restored` for recovery run `30655881616-1`; public MCP
stayed healthy. The refusal is now reduced to one fixed predicate class
(`identity missing`, `project invalid`, `service invalid`, `recorded identity
changed`, or `non-writer proof failed`) plus the fixed sidecar name. Tests prove
private label, ID, and mount fixture values never enter the error. Independent
review approved exact head `e746a12d`, and PR #2013 merged as `7fdf0cc5`.
Normal deploy run `30669933553` used that classifier and again failed closed
before runtime sync or candidate start: `tinyassets-tunnel` has an invalid
Compose project. The next read-before-write diagnostic may classify only fixed
historical categories; no raw label may enter the public artifact, and no
further deploy mutation is allowed before exact-head review.

The follow-up classifier recognizes only `current-canonical`,
`legacy-workflow`, `legacy-deploy`, `recorded-recovery`,
`unrecorded-recovery`, `missing`, or `other`. All categories run through the
real preflight before any Docker update, stop, or remove; arbitrary and
recovery-shaped fixture labels are absent from the error. Fresh verification
at `2026-07-31T22:34:26Z` on the Windows host: 279 deployment-focused tests
passed in 9.32 seconds, changed-file Ruff passed, strict OpenSpec validation
passed, and `git diff --check` was clean.

PR #2015 merged as `bd9522e3`. Its first dispatch, run `30670511483`, never
received a hosted runner and was canceled before setup. The clean replacement
run `30670743121` used the same immutable image and failed closed before runtime
sync or candidate start with fixed category `unrecorded-recovery` for
`tinyassets-tunnel`. State remained `restored`, no current-run cutover began,
and unsafe recovery was skipped.

Repository ancestry and GitHub job evidence identify exactly six public
`recover-unsafe` attempts whose revisions predate writer-only recovery PR
#1908: `30514843571-1`, `30514946746-1`, `30515026545-1`, `30515117371-1`,
`30517431860-1`, and `30518735998-1`. At successful run `30515117371`, the
recovery command invoked full Compose without a service allowlist; PR #1908
then added `RECOVERY_SERVICES` so later recovery could create only the five
writers. The migration allowlist is therefore the deterministic project set
derived from those six exact public attempt IDs, not the
`tinyassets-recovery-*` prefix. Tests cover all six through real preflight and
target preparation, exact-ID removal without volumes, mixed-project refusal,
and arbitrary recovery-shaped refusal.

Fresh migration verification at `2026-07-31T22:50:50Z` on the Windows host:
287 deployment-focused tests passed in 9.17 seconds, changed-file Ruff passed,
strict OpenSpec validation passed, and `git diff --check` was clean. Production
mutation remains blocked on independent exact-head security review.

Fresh diagnostic verification at `2026-07-31T22:21:08Z` (Windows host):

```text
python -m pytest tests/test_retire_cheat_loop_deploy_fence.py \
  tests/test_deploy_prod_workflow.py tests/test_build_image_workflow.py \
  tests/test_diagnose_prod_startup_workflow.py \
  tests/test_sanitize_startup_diagnostics.py \
  tests/test_sanitize_systemd_startup_diagnostics.py -q
273 passed in 8.32s

python -m ruff check scripts/retire_cheat_loop_deploy_fence.py \
  tests/test_retire_cheat_loop_deploy_fence.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict --no-interactive
Change 'repair-recovery-deploy-handoff' is valid

git diff --check
clean
```

## Strict successor after concurrent sidecar landings

PR #2010 and its #2013 fixed-schema diagnostic landed while a stricter
fail-closed review of the original sidecar lane was still running. The
successor preserves both landings and closes the remaining reviewed gaps: it
pins each sidecar image and exact read-only mount set, rejects production-volume
source aliases, stops inspected exact IDs rather than mutable names, and
records full stopped-fleet removal intent before `docker rm` so interruption
replays only the proved remaining subset.

Recovery-sidecar capture now binds each proved owned sibling independently.
Expiry, boot reconciliation, and the outer recovery failure path therefore
refence zero, one, or two created sidecars without touching a mixed foreign
fixed-name sibling. Finalization normalizes every sidecar restart policy to
canonical `unless-stopped`; boot reconciliation refences a generation left
partially restart-enabled by abrupt host loss. Unsafe writer cleanup also acts
on exact inspected IDs and records name substitution as unproved instead of
stopping the replacement.

Fresh successor verification at `2026-07-31T22:38:18Z` (Windows host):

```text
python -m pytest tests/test_retire_cheat_loop_deploy_fence.py \
  tests/test_deploy_prod_workflow.py tests/test_build_image_workflow.py \
  tests/test_diagnose_prod_startup_workflow.py \
  tests/test_sanitize_startup_diagnostics.py \
  tests/test_sanitize_systemd_startup_diagnostics.py -q
296 passed in 10.32s

python -m ruff check scripts/retire_cheat_loop_deploy_fence.py \
  tests/test_retire_cheat_loop_deploy_fence.py \
  tests/test_deploy_prod_workflow.py
All checks passed!

openspec validate repair-recovery-deploy-handoff --strict --no-interactive
Change 'repair-recovery-deploy-handoff' is valid

python scripts/check_cross_provider_drift.py
cross-provider drift check: clean

git diff --check
clean
```

Production remains unchanged. This exact successor still requires independent
exact-head fail-closed/security approval before publish or host mutation.

The first independent strict-successor review returned ADAPT after reproducing
three additional fail-closed gaps: a foreign named volume could spoof the mount
set; interrupted full-fleet and restored-handoff replay could remove survivors
before detecting a same-name off-volume replacement; and preflight accepted a
same-name sidecar replacement after stopping only the captured IDs. The repair
requires bind type plus no volume name and exact unique mappings, re-proves each
captured fixed name after stop, and proves every missing recorded name globally
absent before any replay `docker rm`. Replacements remain untouched and errors
contain only fixed canonical names/predicates.

Fresh adaptation evidence at `2026-07-31T22:55:42Z` (Windows host): the eight
new targeted cases first failed against the reviewed implementation, then all
passed after the repair; the complete fence file passed `173` tests. At
`2026-07-31T22:56:23Z`, the six-file deployment/recovery suite passed `307`
tests; Ruff, strict OpenSpec, cross-provider drift, and diff checks all passed.
Independent exact-head re-review remains required before publish or production
mutation.

After concurrent PR #2018 added the finite audited full-Compose recovery
project authority, the strict successor was restacked to preserve that exact
allowlist and its mixed/arbitrary-project refusals. Fresh combined evidence at
`2026-07-31T23:10:21Z` (Windows host): `315` deployment/recovery tests passed;
Ruff, strict OpenSpec, cross-provider drift, and diff checks passed. Production
remains unchanged pending combined exact-head review.

## Release And Rollback

### 2026-07-31 terminal cleanup incident and recovery

Normal deploy
[30671580199](https://github.com/Jonnyton/TinyAssets/actions/runs/30671580199)
installed immutable revision `85d40171331fa67ef649632012b505ddfde0f6c4`,
proved the exact five-container target, unchanged logical receipt, canonical
public MCP canary, and exact-seven handle surface. Its final cleanup could not
match the preflight daemon snapshot `active=activating, enabled=disabled` to
the healthy settled observation `active=active, enabled=disabled`. After the
120-second bounded comparison it safely stopped and restart-fenced all five
target writers. A fresh Windows-host canary returned HTTP 502; no receipt
change or data-loss signal was observed.

Provenance-bound recovery
[30671967082](https://github.com/Jonnyton/TinyAssets/actions/runs/30671967082)
used source identity `30671580199-1` and the already-proved target image. It
passed immutable admission, exact unsafe-source validation, canonical MCP
canary, exact-seven assertion, and authoritative finalization at
`2026-07-31T23:08:35Z`. A fresh Windows-host command immediately afterward,
`python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
--timeout 15 --assert-handles --assert-handles-retries 2 --verbose`, exited 0
with canonical handles and identity evidence available.

The follow-up repair is test-first and deliberately narrow: normalize only a
preflight daemon `activating` state to the intended terminal `active` state;
retain exact enablement and every other fail-closed comparison; preserve the
successful forward/not-needed rollback tuple; publish separate exact cleanup
markers; and never derive a running terminal identity from a stopped
container.

Independent exact-head review approved implementation commit `cb03d95e` on
2026-07-31: 355/355 focused tests passed, changed-file Ruff was clean, strict
OpenSpec validation and diff checks passed, and the reviewer confirmed all six
fail-closed invariants. The unscoped repository test sweep remained CPU-active
but exceeded its bounded 300-second run without a failure result; unscoped Ruff
reported only 110 pre-existing errors outside this change.

Land only after independent exact-head fail-closed/security review. Build an
immutable image, then run one normal deploy from the currently finalized
recovery generation. Acceptance requires canonical exact-five proof, restored
fence state, and a fresh public MCP canary. On failure, use only the existing
provenance-bound unsafe recovery workflow with the prior admitted stop-writer
image; do not delete containers directly or bypass the fence.
