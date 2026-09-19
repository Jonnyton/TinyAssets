## Context

The existing scheduled workflow is platform-owned infrastructure. Current
`get_status` already exposes a confined canary projection, current coordinator
liveness, and deploy identity. None is a receipt that arbitrary user work made
useful progress. The legacy REVERT reader expects private fantasy-scene logs;
the current unscoped canary does not have that authority. See the dated
diagnosis committed with this change for commands and exact run evidence.

Full PLAN was read. Its constraints apply: infrastructure never invokes an LLM
or acts as a universe; observability follows the platform; private user health
must not become a global authority signal. Existing `get_status` was checked
with `scripts/check_primitive_exists.py action get_status`. No primitive is
missing for the bounded result-classification repair.

## Goals / Non-Goals

**Goals:** distinguish measured outage, measured success, unavailable coverage;
preserve real outage paging; derive consecutive reds from the correct scheduled
observation; keep hostless execution-quality and rendered-proof gaps visible.

**Non-goals:** new public status fields/endpoints, tenant grants, runtime health
storage, synthetic workflows, provider calls, browser transport redesign,
restarting retired fleets, or claiming full checklist closure.

## Decisions

### 1. Classify at the evidence boundary, not by generic process failure

Keep existing exit codes/diagnostics. A small pure classifier can build
`overall`, reason, and per-monitor observations from explicit probe results.
Do not infer health from arbitrary nonzero/zero process exits or parse human
error text. Where the revert script conflates failed transport and absent
legacy evidence under exit 5, add an internal typed reason at that producer
boundary; transport/tool refusal still cannot be made unknown merely by its
shared numeric code. No wire/API change is required.

- Any observed handshake, tool, expected-coordinator, wiki, or legitimately
  observed revert-threshold failure keeps Layer-1 red.
- Missing legacy activity evidence is unknown; no fabricated empty list.
- An empty/unrecognized/missing required result is unknown unless another
  probe already establishes red. A skipped dependent probe does not hide the
  actual upstream red.
- All required probes must be positively observed green for overall green.
- Unknown names the missing capability and exact prerequisite in the job
  summary; it does not close an incident or satisfy full uptime acceptance.

Alternative rejected: merely remove revert from the bundle or interpret exit
5 as zero. Both manufacture coverage. Blanket exit-5 unknown also loses real
transport failures; structured reason is required before changing that case.

### 2. Reuse existing Actions run/attempt/step receipts for outage history

After the non-failing classification step, emit a uniquely named measured-red
sentinel step that exits nonzero only when `overall == red`. Existing Actions
step metadata is the durable receipt; no new stored content or API projection.
The alarm sink inspects the immediately preceding eligible completed run's
exact attempt and this sentinel's conclusion, not whole workflow conclusion.
Old runs without the sentinel, unavailable metadata, malformed/duplicate
receipts, cancelled/skipped sentinels, or another job's failure cannot prove
prior red. Do not search past unknown to stitch nonconsecutive reds together.
Only compare the same workflow/canonical target and same supported receipt
version; bind the read to run ID and attempt. Keep reads bounded and verify the
workflow source is the production branch, not an unrelated manual ref.

Current unknown returns through the existing no-REST-mutation guard. An
already-open incident still gets evidence for a current measured red, as now;
literal green remains the only recovery path. Missing history never fabricates
the threshold. History-read failure is a diagnostic, not a green observation.

Alternative rejected: new JSON artifacts or runtime tables solely for this
boolean receipt. Existing platform-owned Actions metadata is sufficient and
requires no content download, parser authority, or persistence migration.

### 3. Absent scheduled rendered capability is explicit, not a provider failure

The current hosted runner has no authorized rendered-user session. Record
Layer-2 unknown with that prerequisite before invoking `claude_chat.py`; do
not auto-launch a browser, attach an owner's session, install credentials, or
call an LLM. Preserve the separately usable user-directed harness and its
existing tests. This slice fixes the known scheduled execution contract, not
general browser error taxonomy or interactive transport.

Report Layer-1 and Layer-2 separately, plus full acceptance as incomplete when
either required coverage is unknown. A successful job process means only that
the observation was recorded; it is not a green uptime acceptance result.

## Acceptance Matrix

| Observation | Expected outcome |
| --- | --- |
| Handshake/tool/activity/wiki green; legacy private evidence absent | Layer-1 unknown; monitoring gap named; no page/recovery |
| Wiki red plus missing revert evidence | Layer-1 red; wiki diagnostic preserved |
| Expected coordinator stalled plus fresh last activity | Red; no healthy-peer override |
| Transport fails while reading revert evidence | Red; never blanket exit-5 unknown |
| All required Layer-1 observations positively green | Literal green; existing recovery behavior |
| Empty downstream result with otherwise green probes | Unknown, never skipped-to-green |
| Current red after prior workflow failure with no measured-red receipt | First measured red; no threshold page |
| Current red after prior Layer-2-only failure | First measured red; no threshold page |
| Current red after prior exact-attempt measured-red receipt | Existing two-red incident behavior |
| Prior unknown, then current red | First red, even if an older run was red |
| Prior receipt absent/ambiguous/API read fails/wrong ref or attempt | Unproven history; no fabricated threshold |
| Current unknown with existing incident | No REST mutation/page; incident stays open |
| Scheduled runner without authorized rendered session | Explicit Layer-2 unknown; no browser or LLM subprocess |
| Intentional user failure/provider exhaustion | Not read or aggregated into global platform health |

Executable coverage will extend the existing workflow JavaScript harness and
pure probe tests. Prove new cases red before implementing, run current monitor
regressions, actionlint, and a fresh scheduled run after merge. A scheduled
unknown receipt is successful classification acceptance, not completed item 9.

Red-first checkpoint, September 19, Windows Python 3.14:
`python -m pytest -q tests/test_revert_loop_canary.py
tests/test_current_executor_liveness.py tests/test_last_activity_canary.py
tests/test_uptime_canary_workflow.py tests/test_uptime_canary_layer2.py
tests/test_uptime_canary_concurrency.py --tb=short --show-capture=no`
reports **4 failed, 122 passed** before any runtime/workflow edit. Three failures
pin the missing producer distinction (refusal and transport are red; absent
private evidence unknown). One executes the real alarm JavaScript and proves
that a previous failed workflow without a measured Layer-1 receipt incorrectly
creates an outage issue. Ruff passes on both edited test files. Remaining
matrix cases are implementation-stage work, not claimed as executed.

## Risks / Trade-offs

- [Unknown persists] -> Keep the concern and exact execution-quality/rendered
  prerequisites open; no repeating settled probes or claiming full closure.
- [Actions metadata unavailable] -> Do not count prior red; surface diagnostic.
  Existing open incidents still receive actual current red evidence.
- [Historical failures miscounted] -> Old receiptless runs are unproven; require
  run/attempt/source checks and an explicit sentinel, not workflow failure.
- [Masked transport failure] -> Test structured reason and shared exit-code
cases before changing aggregation.

Reviewed producer mapping: only a response with absent `evidence`,
`first_contact.event=no_universe_yet`, a daemon worker-liveness object, and a
release-state key is recognized as the confined legacy-evidence gap. Empty,
malformed, denied, read-failed or transport-failed responses stay red. The
`--format gha` producer writes fixed `revert_observation` and `revert_reason`
enums directly to `GITHUB_OUTPUT`; the workflow passes them to the classifier
as environment values. Human diagnostics never choose the classification.

Reviewed history semantics: skipped-deploy and unknown observations break the
chain rather than being stepped over. Prior receipts older than 30 minutes,
from a different branch/path, or superseded by a new attempt are unproven.
The reader rechecks the run after retrieving exact-attempt jobs. The sentinel
has a versioned name, no `continue-on-error`, and only executes for measured
red. Only Actions read permission is added; no new service authority.

The current production shape supplies no legacy REVERT evidence, so literal
green and automatic incident recovery are currently unreachable. An incident
opened by an actual outage stays open after that measured outage recovers;
later reds follow existing incident escalation. Old false-era incidents also
cannot auto-close. The summary warns explicitly; coordinator/incident-owner
cleanup must reverify each incident before disposition, never bulk-close from
this partial proof. Full acceptance remains open. This limitation is accepted
for the truthful classification MVP, not a claim of recovered full monitoring.

Shape review and dispositions:
`docs/reviews/2026-09-19-scheduled-monitor-shape-fable.md`.

## Migration Plan

Fable shape review first, then failing tests, bounded implementation, focused
suite/actionlint, exact-head independent review, one PR. Verify the deployed
workflow's next result and retain the incomplete-coverage finding. No database
migration or account change. Revert the workflow/helper patch if classification
breaks; never roll back by granting access to tenant evidence.

## Open Questions

### Follow-through: community-watch consumes the same typed truth

September 19 source inventory found `community_loop_watch.workflow_stage`
mapping a fresh successful Uptime workflow to green without reading its typed
result. Its separate alarm sink also recovered on every non-red status,
including yellow. A classifier-success/unknown receipt could therefore erase
the distinction downstream. The bounded correction uses the existing Actions
run/attempt/job/step metadata contract, not logs, new JSON artifacts, public
endpoints or runtime storage. Add a unique positive-green sentinel alongside
the existing measured-red sentinel: green cannot be inferred from absence of
red. Exact attempt/job identity, production branch/path/repository, source SHA,
completion timestamps and the existing 90-minute consumer freshness policy
must match, with a final run re-read to reject superseded attempts. Missing,
malformed, duplicate or conflicting evidence remains unknown. Old explicit
measured-red receipts remain red; old receiptless success is not green.

The observation stage alone changes to typed semantics; ordinary deploy-stage
conclusions stay as before. Existing stale-monitor alarms remain red with a
diagnostic distinguishing cadence absence from endpoint measurement. Measured
red or another existing red stage outranks unknown. The community sink exits
before any label/issue/dispatch call unless overall is literal red or green;
this also fixes prior yellow-as-recovery behavior. Existing permissions and
red issue/update/stale-dispatch actions are unchanged. Only literal green can
recover, and neither green Layer-1 nor workflow success establishes rendered
Layer-2 acceptance or restores a scheduler cadence guarantee.

Red-first command: `python -m pytest -q
tests/test_community_loop_typed_observation.py --tb=no` yielded 27 failed,
2 passed before implementation. The real JavaScript red/green controls passed;
the unknown/yellow/empty recovery cases failed. After implementation the
expanded matrix additionally checks malformed fields and retained legacy red.
The existing quarantined `test_alarm_sink_dispatches_only_stale_uptime_canary_workflow`
asserts an obsolete dispatch helper; it is not weakened or newly quarantined.
Independent follow-through review and hosted CI remain required. Natural cron,
private-free execution-quality and rendered acceptance remain open.

The bounded review question: does explicit unknown plus exact-attempt measured
red metadata preserve actionable outage handling without inventing missing
coverage? Disagree with code evidence or a named safety concern.

Not a build dependency for this slice: which authoritative engine-owned signal
would prove sustained useful execution without treating intentional user
failures as platform faults? No existing public execution-quality receipt was
found; defining that source requires separate scope and shape review. Rendered
user acceptance also remains a distinct missing observation.
