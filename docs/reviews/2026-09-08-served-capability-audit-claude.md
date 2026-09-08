# Served capability audit — independent Claude review

Date: 2026-09-08. Source runtime c97208f5, dirty audit documents.
Read-only peer exited 0 in 353 seconds. The wrapper output contains a stop-hook
closing note only; the substantive assistant review was recovered from local
session `e204ad6f-7531-468d-8588-4d7198aa7f16`, selecting assistant text containing
`VERDICT:`. No subagents or live calls; no test run by this reviewer.

Verdict: **ADAPT**. All nine original capability rows and the live heartbeat
blocker were confirmed, with framing corrections:

- Cancellation and old schedule/subscription controls are missing from both
  canonical surfaces, not only the served wrapper.
- Automation storage and old scheduler bindings already coexist; do not add
  another scheduler.
- Empty branch ID already clears a loop in `api/universe.py:6618`.
- Private agent binding reads meet the basic universe-pin criterion, but old
  IDOR deferral notes still require current implementation verification.
- Policy-set semantics were not reviewed; leave the self-grant concern qualified.

The audit was corrected accordingly. The tenth, in-place workflow editing row
was added during the review and was not independently assessed by it.

## Next implementation shape

Reuse `api.automations.automations` directly, not broad connector `write_graph`,
under the bound actor and graph. Existing reads are universe-scoped and controls
re-check ownership/admin and revision CAS. Creation retains existing preflight.
List/get/pause/delete/resume/create can be direct-agent operations, consistent
with the existing direct run and outbound approval surfaces. Create must use
fail-closed admission and the existing per-universe automation ceiling. No new
secret or grant is needed; no generic rail answer should claim to grant tools.
If a future product policy requires confirmation for recurring spend, implement
an explicit executable rail action rather than a second management surface.

Control receipts must distinguish stopping future triggers from stopping an
already-running job. Live bound-actor/ACL and revision readback remain unproven
until the app exercises the shipped route. This is shape guidance, not approval
of an implementation that has not been written.

## Drift coverage

The reviewer recommends a small typed availability/alternative map and a
relational test covering target+operation pairs in descriptions and refusal
text. The existing tests mainly cover standalone verbs such as `*_http` and
`*_compute`; they miss instructions to delete dependents via a hidden target.
Keep this bounded: no speculative registry framework or per-provider handles.
