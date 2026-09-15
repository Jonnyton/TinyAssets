# Privacy-safe evidence for unsuccessful native terminals

Intent: retain a typed diagnostic clue for the observed Claude terminal failure
without treating failure as success, widening fallback or retaining private output.

Production46647117, original subscription user: Automatic fails in Claude with
subtype success; explicit Codex succeeds. Cause remains unknown. No evidence
yet attributes this to credentials, billing, model choice or a provider update.

Pre-build Fable shape review77014 (308s, exit0, ADAPT_SHAPE) identified the
assistant.error enum dropped by the parser. It rejected logging scrubbed result
snippets: redaction does not remove arbitrary private request content. Primary
schema evidence, checked September15,2026 via official documentation search and
published Anthropic type declarations:

- https://code.claude.com/docs/en/agent-sdk/typescript — SDKAssistantMessage.error.
- https://app.unpkg.com/@anthropic-ai/claude-agent-sdk@0.3.211/files/sdk.d.ts —
  SDKAssistantMessageError, including overloaded. Peer also inspected installed
  Claude2.1.261. Unknown future values must remain unrecognized, not raw strings.

This implementation captures only the last allowlisted assistant error category
and a closed is_error value (true/false/absent/non_boolean) in existing internal
attempt telemetry. For the observed unsuccessful-terminal branch, the existing
exception/log detail includes those facts and success/non_success subtype.
No result, errors array, content, stderr, arbitrary subtype or model identifier
is added to diagnostics. Last observed category is a clue, not a proven final
cause. A later successful terminal still succeeds.

Deliberate boundaries: keep exception classes, failure_class, quotas, routing,
retry and incomplete-native-effects evidence unchanged. No API field or storage
schema is added. The review's broader owner-visible native_terminal projection
and durable failed-turn history require their own surface/storage design and
remain OPEN. This narrow evidence repair does not substitute for those goals or
claim the underlying Claude issue is solved. Its purpose is to establish the
cause through a fresh authorized live attempt, then repair the actual blocker.

Tests:12 new cases failed at unchanged runtime; all14 new cases now pass.
Full stream file69passed/1skipped on Windows; unchanged runtime/test file at
46647117-equivalent tree55passed/1skipped. Identical skip is bwrap Linux-only;
Linux CI is still authoritative. Existing success, retry, timeout and protocol
tests remain green. New cases preserve native capacity-boundary refusal and
exclude arbitrary private values from messages. Plugin443-file import passes.

Exact-head Fable review, CI and deployment remain required. After deploy, use
ordinary app conversation to reproduce the failure; inspect only safe typed
diagnostics. Do not run a provider as the operator or edit private workflows.
Rollback uses the existing release workflow, with no schema/data migration.
