# Provider auth failures are classified by substring, not by the provider

**Filed:** 2026-09-01, after three Codex review rounds on #2758 each found a
new hole in the same heuristic.
**Severity:** P2 — the owner-facing notice can only be as honest as this
classification, and it is a guess.

## The finding

`tinyassets/providers/diagnostics.py` `classify_unavailable` decides
`auth_invalid` versus `endpoint_unreachable` by substring: "token", "auth",
"401", "403", "expired"... A context-length failure ("input exceeds the
model's maximum token limit") classifies as an auth failure; a message with
no tell classifies as a network failure. #2758 stopped promoting that guess
into the owner's notice unless the attempt's text carries narrow evidence,
and three rounds of review each found a realistic message on the wrong side
of whatever list was current (V1: "401" inside `140123 tokens`; V2: Codex
0.146's "Your access token could not be refreshed. Please log out and sign in
again." was not on it). A list of strings is the wrong shape for this fact.

**And the Claude quick-exit path throws the evidence away.**
`tinyassets/providers/claude_provider.py` (the `returned exit code 1 quickly`
branch) stores only its own sentence, not the CLI's stderr, so Claude's
"Not logged in · Please run /login" never reaches any classifier at all.

## The fix

The provider knows why it failed; it should say so in a typed field, not in
prose to be re-parsed. Each subprocess provider emits a structured failure
class from what it actually observed — exit code, a recognised CLI error
line, an HTTP status it saw — and `ProviderAttemptDiagnostic` carries that as
provenance (`evidence: "cli_not_logged_in" | "http_401" | ...`). The notice
layer promotes only provenance, never a substring match. The Claude
quick-exit branch keeps the CLI's stderr so there is something to classify.

Until then the tell list in `universe_server.py` (`_AUTH_EVIDENCE_TELLS`,
`_HTTP_401`) is the honest floor: narrow, and an honest unknown when it
misses.
