# Consumer implementation review and final integration disposition

September 20, 2026 UTC. Fable peer 96731 exited 0 after 504 seconds and returned
APPROVE at exact consumer head `f9b91ed7f566dbce9a0d155c489efa94faafac99`, Q1–Q6
AGREE. The full returned artifact is `release-code-review.md`, preserved without
rewriting its historical findings or claiming it reviewed later commits.
Its own Windows model-bridge cohort passed 8 tests, no skips, in 15.08 seconds.

## Final authorized integration batch

No canonical runtime or plugin runtime changed from the approved head.

- Ordinary cherry-picks of foundation docs `520b40c0` and `bdbc429a` preserve
  held-guard-only expected-status wording in canonical and delta specs. Local
  resulting commits are `47025163` and `50774c81`; no reset/rebase/history rewrite.
- Preserve the actual nested maintenance closure in the existing delivery test
  rather than compile a function with nonlocal state at module scope. Parameterized
  admission/delivery failures across three ticks prove budget work is not starved
  and the admitted cursor survives a failed scan. The original isolated test
  was a real red regression (SyntaxError), not part of the earlier 606 cohort.
- Add actual `main` boot/periodic nomination regression against a real temporary
  canonical admission, intercepting submission and network/provider effects.
  Deployment uses Dockerfile CMD `python -m tinyassets.universe_server`, entrypoint
  `exec "$@"`, unchanged compose CMD, and module main. The alternate direct ASGI
  factory alone is not claimed to run the main-owned maintenance loop.
- Sync six bounded governed-consumer requirements and three canonical-turn
  requirements. Clarify visit-local rollback, selection/admission/projection
  check timing and visible-but-generic refusals. No phantom ancestry mechanism:
  v1 rejects nested executable references and does not expose converse as an
  engine/code-node tool. Built-in writer/learning clauses describe the default
  path; a selected consumer does not run that pipeline additionally.
- Preserve every unrelated canonical relay requirement and historical review.
  The canonical scope does not promise arbitrary UI, foreign harness loading,
  managed resume, complete setup migration, or unconditional installation repair
  when owner/eligibility/revision checks refuse it.

## Optional notes — post-MVP, not silently implemented

The reviewer reported no necessary basic-safety correction. These observations
remain explicit post-MVP follow-ups, not part of this release's completion claim:

1. Prompt fallback's termination relies on existing exhausted identity exclusion.
   A separate visited set could defensively reinforce it; current finite-order
   exhaustion and same-journal tests pass. No new fallback mechanism is added.
2. Any binding revision change holds/fails a queued consumer, even a layout-only
   edit. This is conservative current-authority behavior. Comparing only selected
   fields may improve recovery later but is not used to relax this release's CAS.
3. Invalid/serving/provider-bearing app_experience bindings can leave the app's
   disable control ineligible. Current owner-side binding APIs remain the existing
   repair path, but one-click restoration is not universally proven. Specs retain
   those eligibility checks rather than promising unconditional mutation access.
4. Terminal exact replay may submit an immediately no-op guarded task before read.
   Existing durable marker/CAS and terminal projection prevent repeated effects.
   Avoiding that submission is a later efficiency improvement, not a safety fix.
5. Plain connector callers with selected custom behavior receive
   consumer_request_required until they supply the explicit keyed request. This
   remains honest rather than silently defaulting; improved control-station
   onboarding guidance remains optional follow-up. The actual handle documents
   the versioned protocol and owner-scoped observation target.

## Fresh final-batch evidence

Matched six-file cohort on September 20 UTC: Windows Python 3.14 **58 passed,
zero skips, 23.26 seconds**; Linux Python 3.11 **58 passed, zero skips, 40.42
seconds**. Command `python -m pytest -q -rs --tb=short` with:

```
tests/test_delivery_account_deletion.py
tests/test_consumer_startup.py
tests/test_consumer_origins.py
tests/test_consumer_public_turn.py
tests/test_work_consumer_model_bridge.py
tests/test_assigned_queue_consumer.py
```

Linux used the same read-only working tree, disabled bytecode/cache writes and
no network under oracle image
`sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a`.
The previous 606/606 cohort remains evidence for unchanged runtime, not relabeled
as another full run. Scoped test lint passes; strict consumer/foundation changes
and canonical governed-consumer/relay/graph-execution specs validate.

The root owns a bounded follow-up for this new exact head, hosted CI, deployment
proof and ordinary two-owner rendered acceptance. Tasks 3.1–3.3 remain open; no
archive or live adoption claim is made here.
