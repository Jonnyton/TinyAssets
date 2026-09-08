# Served automation lifecycle — exact-head Claude review

Date: 2026-09-08. Independent Claude subscription subprocess, read-only.
Reviewed SHA: `25d844ecfc99896785d24c10379cf28a86298ba9` against
`0e485ba0add1b852d712b4c5d349e542a4131268`. Wrapper exited 0 after 281 seconds.
Its final output includes APPROVE but is a stop-hook closing note; the full
substantive review was read from assistant text in local session
`403dbf72-2263-4305-8e7f-6bd38531d0f2`. This artifact summarizes that review.

**VERDICT: APPROVE. No material pre-live blockers.**

Reviewer read the complete committed diff, adapter, store CAS mutators,
permission helpers, OpenSpec artifacts and prior shape guidance. Independently
ran `python -m pytest -q tests/test_served_automation_lifecycle.py`: **19 passed**
on Windows. Runtime tree was clean; both generated mirrors were byte-identical.

## Structured findings

- **AGREE: actor/universe confinement.** The adapter receives the pinned graph;
  identity comes from the bound ContextVar. No graph/actor/owner selectors are
  advertised. Control payloads refuse; create ignores extra document selectors.
  Uniform foreign-row miss is tested even for an actor who administers both
  universes.
- **AGREE: existing ACL and CAS execute.** Owner/admin checks, creation preflight,
  authorship, serving assignment and ceiling remain; revision is rechecked in
  the store transaction. Stranger and write-collaborator tests prove no mutation.
- **AGREE: projections remain safe.** No raw owner principal, provider or secret;
  foreign/legacy text is untrusted data, and mixed lists split own and foreign.
- **AGREE: documented operations route.** Relational vocabulary and real-adapter
  tests cover create/pause/resume/delete; future adapter additions fail the
  equality test rather than becoming silently callable.
- **AGREE: stop semantics are explicit.** Trigger state, retirement, revision,
  last run and finish stamp remain visible; neither docstring claims job
  cancellation. Live last-run visibility needs verification (below).

## Nonblocking post-live follow-up

- **DISAGREE_CONCERN, design wording:** the identity's `("write",)` capability
  tuple is not itself inspected by this adapter. Existing authentication and
  resource ACL are the enforced authority boundary. Do not describe the tuple
  alone as an enforced permission control.
- Reviewer did not verify that served run reads can open consumer-created runs
  attributed to the universe principal. The suggested last-run readback needs
  this check; the projection's last-finished stamp is not full terminal proof.
- Refused creation consumes an admission ticket before preflight, as branch
  creation already does. Resume uses canonical behavior: a missing ready
  provider can cause subsequent consumer auto-pause with a recorded reason.
- Pause/resume have no execution-admission rate limit; each advances revision.
  Missing expected_revision defaults to zero and conflicts against a live row.

Required Linux CI remains mandatory; this is not live app acceptance. No private
workflow, automation, credential or destination was edited by the reviewer.
