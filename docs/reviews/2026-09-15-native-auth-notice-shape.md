# Native sign-in clue: pre-build shape and evidence

Original subscription user's September14 19:04PDT Automatic turn failed with
closed native evidence is_error=true and authentication_failed on deployed
0d09c564. This is not evidence of a CLI-update cause or credential expiry.
The separate free-only user has no paid subscriptions/OpenRouter account and
is not part of this auth incident. No credentials were changed or borrowed.

Fable5.1 shape round1 (process2342,358s,ADAPT) localized the lost diagnostics
and misleading notice wording. Its proposed init/launch phase gate was rejected
by the lead with code evidence: error-message text itself sets streaming phase.
Fable round2 (process4017,337s,ADAPT) independently reproduced this and withdrew
the gate. It proposed the implemented shape below. Review was read-only on
116c090c plus local draft tests/copy. Exact-head landing review still required.

## Implemented internal correction

- Assistant-error text is liveness, not model output. It cannot become the
  successful answer when a later empty terminal falls back to assembled text.
- Subsequent useful text/tool progress clears the prior assistant-error clue;
  heartbeat/opaque events do not. Successful terminal behavior remains first.
- A terminal result outranks the quick exit=1 guess. The existing generic error
  cooldown applies instead of unavailable cooldown; no new exception class.
- Router retains existing provider_error, failure_class=None and incomplete
  native proof. Side-effect state is preserved, not converted to safe-to-retry.
- The last failed attempt's closed diagnostic rendering can produce a clue-only
  notice. No new public field/class, credential mutation or fallback widening.
  Matcher uses a bounded transport label, not a vendor-name branch. This is a
  provider-reported clue, not an unforgeable authorization token.
- Existing auth/unknown notices no longer invent expiry/revocation, promise
  reconnect success or categorically rule out billing without evidence.

The review's broad case table said api_retry never supersedes the auth notice;
the implementation intentionally preserves existing typed capacity-retry
precedence. No change to real rate-limit/overload handling is intended here.

## Verification so far (September15 UTC, Windows)

Base runtime116c090c equals existing7c647138 for all changed/tested files,
verified using git diff --exit-code. Base five-file suite159 pass/4skip; current
suite178 pass/4skip before the final malformed-attempt test. First revised
regressions failed13/passed4 before runtime changes. Earlier wording baseline
46pass became48pass after two red-first notice tests.

Command: python -m pytest -q tests/test_provider_served_router.py
tests/test_provider_stream_and_classify.py tests/test_served_failure_notice.py
tests/test_a_failed_turn_says_what_actually_happened.py
tests/test_provider_router_diagnostics.py --tb=short

Skips are unchanged: Windows shared-lock overlap, two Linux/bubblewrap checks,
and opt-in real Codex credential integration. No actual-provider integration
or Linux pass is claimed by the Windows run. CI remains authoritative.
Ruff and plugin mirror/import pass. No filesystem/sandbox/process-limit helper
changes, no provider credentials or universe workflows edited.

## Remaining proof and scope

Land only after exact-head cross-family shape/basic-safety approval and CI.
Then protected deployed SHA/public canary and ordinary rendered conversation.
Owner-visible durable failed history and the underlying provider sign-in
rejection remain separate open capabilities; this notice does not close them.
Rollback is the ordinary image/commit rollback, with no migration/data cleanup.
