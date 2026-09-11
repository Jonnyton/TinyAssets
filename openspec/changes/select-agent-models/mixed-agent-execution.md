# Mixed-source execution — release-blocking correction

## Required outcome and observed defect

The owner can order native/subscription/local and HTTP choices together. The
runtime must execute that order at safe capacity boundaries, retaining completed
work. Hiding mixed choices is not completion of the requested capability.
Current _call_writer chooses an execution style once; native exhaustion never
advances the plan, while the HTTP loop advances to native with an incompatible
structured agent request. Existing default/current/saved ordering stays intact.

## One coordinator, two installed execution capabilities

Use one in-process interactive-turn coordinator for any selected candidate with
an AgentModelPlan. A step capability is either engine-managed inference/tools or
native whole-agent execution. Select from installed executor capability, not
model names or service-specific fallback branches. Native providers keep their
CLI subprocesses; no primary-writer API SDK, fabricated native model or fake
HTTP SelectedModel. Selection still means the exact accepted member reference.

The coordinator owns original prompt/system, captured policy, current selection,
accumulated exhaustion, attempted references, one absolute deadline and progress.
Every candidate is freshly authorized through the existing router/assignment
entrypoint. No reused ServedProviderAuthority, no caller-provided prepared model,
no cost/token limit union and no credential copying. Current request/tool fences
remain before inference and effects. User's saved/current policies are not edited.

## Closed retry evidence

A shared pure classifier consumes exact typed per-attempt diagnostics. An all-
skipped capacity gate means nothing launched. An attempted capacity refusal is
retryable only with explicit locally observed side_effect_state=none. Missing,
possible, committed, malformed or contradictory effect evidence cannot be
upgraded to none. Unknown errors, timeout, auth, malformed protocol and uncertain
tool outcomes do not become capacity just because another model exists.

Require diagnostics for the current exact provider, no unaccounted attempted
provider. Preserve model-local vs account scope; missing scope is conservative
account scope and must not rotate keys on an unproven independent account.
Unknown account relationships use existing model-policy exclusion. No sleep on
the interactive worker. Retain retry hints as evidence, not an instruction to
retry an exhausted source immediately. Traversal is finite; never revisit a
candidate or fabricate an eligible replacement outside the captured plan.

Native CLI adapters may attest no effects only from a complete supported stream
or another execution-bound fact. Empty/malformed/unknown protocol is not proof.
Existing streamed tool observations remain sticky: a later tool-finished event
must not erase the fact that work happened. Do not broaden fallback from legacy
unselected writer calls, which keep their existing one-all-skipped retry rule.

## Durable progress and native delegation

Extend the private journal by explicit versioned native-step records, preserving
version-one HTTP bytes/readers. Native model="" truthfully means provider
default. Do not synthesize a native AgentReply as if it were a tool-free HTTP
inference. A native result is a whole-agent terminal response with its real
provider/optional reported model/accounting, and unknown internal tool detail.

The native step records intent after fresh reservation/claim and before launch,
using the existing claim observer with a clearly separate installed step kind.
Its terminal record distinguishes succeeded, known-no-effects capacity refusal
and indeterminate. Existing SQL tables may carry a version-two candidate/reply
payload; no destructive migration or alteration of old rows. Snapshot validation
must branch on the explicit version/kind and must never infer a retryable native
failure from the absence of HTTP tool rows. Incomplete/unknown native work holds.

Preserve all earlier fully completed engine-managed tool calls/results exactly
when the next step is native. Project the same validated history as portable
data, strip foreign private reasoning, and render a bounded structured history
block beside the unchanged original request. Treat tool content as untrusted
data, never system authority or instructions. Do not summarize/truncate user
content or manufacture missing results. If it cannot fit, fail visibly; no lossy
fallback. Native agent tools still use the current engine grant.

If native capacity refusal proves no effects, that step contributes no tool
history and the next HTTP/native candidate receives the same prior completed
history. Native success ends the turn; native uncertain effects cannot be
restarted on another source. No crash resurrection or background replay is added.
Final answering-model observer uses only the final genuine provider response.

## Verification and sequencing

Review this storage/observer boundary before implementing it. The pure closed
retry classifier may be built independently; it grants no authority and is not
activation of mixed fallback. Then connect one coordinator and versioned journal
with a genuine native/HTTP/native acceptance fixture through real request,
assignment, router and broker seams. Do not replace those seams with mock grants.

Cover automatic native-first exhaustion, explicit HTTP-first, native/native,
HTTP tools -> native continuation, native no-effects -> HTTP preserving earlier
results, uncertain native/tool effects held, account siblings skipped, empty
explicit tail, revoked fallback, no paid widening, once-only final receipt,
deadline/cancellation, legacy no-plan compatibility, v1 snapshot differential
decoding and version-two malformed/mismatched record refusal. Run Windows and
actual Linux, independent exact-head review, fresh CI, protected deployment proof
and rendered ordinary app retest. Neither the classifier nor a hidden UI option
closes this requirement on its own.
