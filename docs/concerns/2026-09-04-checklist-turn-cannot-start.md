# Checklist acceptance is blocked before the app agent can answer

Observed 2026-09-04 at 22:57 and 22:59 UTC, production revision `0512f335`.
The founder's existing webapp conversation received exactly
`Retest your workflow checklist`. Both attempts rendered an unknown turn
failure, not a checklist result. No private workflow was changed.

Read-only operator evidence: bounded `docker logs --since ... --until ...`
over the existing deployment SSH connection recorded one failed Codex launch
per attempt, exit 1 in under five seconds. The diagnostic's default bucket is
`endpoint_unreachable`; it is not proven network failure. An unauthenticated
request from inside the container to the model catalogue reached the service
and received HTTP 401, establishing connectivity only, not user auth validity.

PR #2959 fixed router/recorder double truncation and deployed as `97da0ead`
at 23:32 UTC (deploy `33929823161`, protected SHA and canary both green).
The exact retest at 23:34 UTC still failed before a checklist reply. The retained
tail is a large model-catalogue response. An independent Claude diagnosis also
found that quick-exit handling discards JSON stdout error events, so catalogue
failure need not be the only terminal cause.

Read-only production metadata check at approximately 23:40 UTC: official model
catalogue GET using the existing bound credential returned HTTP 200, four
models, and `codex-auto-review` declared reasoning effort `max`. No credential
was printed or changed, and no inference was invoked. Production's
`codex --version` is 0.135.0; its official `ReasoningEffort` enum ends at XHigh
without an unknown-value fallback. This proves a catalogue parsing mismatch,
not that correcting it alone will complete a turn.

In-review generic repair: pin official CLI 0.153.4 (supports model-defined
reasoning values) and replace removed `--full-auto` with its explicit
`--sandbox workspace-write` equivalent. Both old and new `exec` default to
headless Never approvals. Shell and account-app tools remain disabled, own
universe credential mounting and the mandatory OS sandbox stay unchanged.
Independent shape review required same-lane keepalive flag compatibility,
runtime startup proof instead of help parsing, and scrubbed structured stdout
failure evidence. Those additions are implemented. Clean-home feature comparison
found remote plugins default-on in the new release; provider launches explicitly
disable plugins and remote plugins as well as account apps. Real CLI smoke
initializes a fake required MCP and reaches a loopback-only fake HTTP 401 with
no credentials. The app retest, still outstanding, gates recovery.

The configured default `gpt-5.4` is absent from the four-model catalogue.
Catalogue visibility alone does not prove responses-side model rejection;
do not change selected models without that evidence. Structured failure
messages are now retained so a second launch cause can be identified.

## Post-upgrade live result, 2026-09-05 00:51 UTC

PR #2964 deployed c30daa8f with protected containment and public canary passing
in deploy 33934197685. The exact app retest still failed before a checklist
reply. Bounded `docker logs --since 2026-09-05T00:50:40Z --until
2026-09-05T00:52:00Z tinyassets-daemon` now retains the terminal cause: HTTP 400,
the requested `gpt-5.4` model is unsupported for this ChatGPT account.
`_codex_model` imposes that model when no environment override is supplied.
Thus catalogue compatibility was real but not sufficient for recovery.

The next bounded repair under independent shape review removes the implicit
platform model pin, delegating unspecified selection to the same connected
CLI's catalogue-aware default while retaining explicit overrides. No new
hardcoded model list, credential substitution, private workflow edit, or
cross-provider fallback is authorized. Keep the full provider-agnostic finding
open independently of this outage repair.

Independent round-2 review (2026-09-05 01:14 UTC) traced the offline native-model
smoke failure to two test assumptions: Responses-lite carries tool specs in
`input[].additional_tools`, and MCP specs may be deferred to tool discovery
rather than enumerated on the initial request. Source: official CLI 0.153.4
`core/tests/suite/responses_lite.rs` and `core/src/tools/spec_plan.rs`. Corrected
the fixture to inspect both tool envelopes, require nonempty specs, retain the
recursive forbidden-name check, and report code-mode deferred engine visibility
as unobserved rather than claiming invocation. The real CLI smoke now passes.

The credential-free custom-provider smoke uses the bundled model default, not
the authenticated account catalogue. It proves startup/wire/config invariants,
not the account default's tool execution. Code mode's isolate can discover
deferred tools through ALL_TOOLS; the initial request cannot exhaustively expose
that registry. A stubbed discovery/execution probe would strengthen offline
coverage; the reviewer treated that as follow-up, not a landing blocker. The
unchanged OS sandbox and tool registry restrictions still apply. A rendered app
retest remains mandatory before declaring recovery or a checklist pass.

Do not substitute credentials, change provider bindings, or repair workflow
definitions to close this finding. The acceptance is a real rendered reply and
ultimately the agent's independent checklist passing.
