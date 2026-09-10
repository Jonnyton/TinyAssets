# HTTP agent-loop prerequisite: source constraints

September9, checkout939931a9ff0516e28b7d64ad340cafd023f57401. Investigation,
not an implemented tool loop or approved storage migration.

## Existing boundaries to reuse

`ApiKeyHttpProvider.complete` validates the universe's connection grant and sends
one request through the credential-blind outbound proxy. It does not consume
ModelConfig.engine_mcp_enabled. Both protocol encoders currently handle text
requests/replies, not model tool calls. A provider accepting a tools parameter
therefore does not establish an executor that can run those tools.

`engine_mcp_http` already supervises one bearer-protected loopback MCP server per
allowed serving universe. The server pins owner and graph in process environment.
Use that existing authenticated dispatch boundary; do not duplicate the tool
implementations, synthesize an actor, expose its bearer to a remote LLM, or accept
a URL supplied by model output. Its explicit universe allowlist is a current
authority restriction, not something this feature may silently remove.

At the original inspection the route map recorded graph->URL/secret but not the owner identity. An
HTTP tool client will need a trustworthy owner/graph match and exact loopback
destination validation, including during supervisor owner changes. Adding route
identity metadata must be designed/tested at the shared publisher/consumer seam.
Missing or mismatched tool authority must hold the agent request, not silently
run a text-only substitute while claiming full-agent readiness.

## Continuation is not ordinary conversation memory

`conversation_store` is deliberately best-effort text memory: storage errors
degrade to no memory, and `converse` records an exchange only after its reply.
That is not safe durable ownership for started/completed tool calls. Neither
missing memory nor an exception can justify replaying an ambiguous effect.

The HTTP loop needs an authoritative turn/attempt journal and explicit tool-call
states before automatic fallback is enabled: record intent before dispatch,
persist exact completed results, hold unknown outcomes, and continue inference
using those records. Preserve owner/universe/turn lineage, request/policy
generation, accumulated usage and cancellation. Choose the existing runtime's
appropriate durable transaction seam before introducing any table; do not bolt
effect receipts onto the best-effort conversation store.

`_call_writer` already refuses whole-turn retries after an actual attempt,
specifically because CLI agents may have performed effects. Retain that rule
until checkpoint-aware continuation can prove the next action is inference only.
Walking the advisory fallback list after a tool failure would violate it.

## Observation and accounting

At the original source inspection, `providers.call._call_router_with_retry`
reduced ProviderResponse to text and updated a process-global last-provider
label. Feature commit215aacf2 now adds an optional reply-owned response observer
and WriterExecutionReceipt, propagated into converse's optional execution field.
The first completed conversational response wins; subsequent learning cannot
overwrite it. This bridge is built and independently reviewed, not deployed.
Reply-owned app display is now built in6f0e6273, not deployed; clickable selection
remains pending. Never use the global label across users.
See docs/reviews/2026-09-10-interactive-model-receipt-proof.md.

The newer agent-runtime outcome path requires complete usage/cost before success;
current HTTP responses do not provide cost there. Missing cost is unknown, not
zero. An HTTP tool loop must aggregate complete per-inference accounting or hold
unknown settlement honestly. It must not reuse one spent invocation carrier for
another model request or manufacture usage to obtain a successful outcome.

These are concrete integration requirements within tasks2.3/2.4/3.1. They do not
establish that the owner's paused background-self workflow has hit a new wall,
and they do not authorize editing that workflow or changing live credentials.

## Reverified receipt path, September9 23:52 UTC

At feature base558b94a3, the app calls MCP.converse in onboarding/app.html:1065
and renders its returned payload at2138. universe_server.converse returns only
reply/universe_id at2365. universe_intelligence._call_writer returns
call_provider's string; _call_router_with_retry in providers/call.py stores a
process-global last-provider label and discards ProviderResponse beyond text.
After the writer reply, learning extraction can make additional provider calls.
Therefore a global last-call label (even made thread-local) can describe the
extractor instead of the answering writer. Capture the actual writer result
at its call boundary and propagate request-local metadata explicitly, with
tests for interleaved universes and post-reply learning calls. Empty resolved
model remains unknown; the requested default/alias is not an actual receipt.
No receipt bridge/UI was implemented by that historical source check. The bridge
was subsequently implemented in215aacf2 as described above; reply-owned display
is now scoped in answer-model-display.md. Neither is a full-agent picker proof.

## Next integration inspection, September10

The pre-build route lookup was duplicated in claude_provider._engine_mcp_flags and
codex_provider._codex_engine_mcp_args. Both read graph-keyed URL/secret only and
fall back to Path(data_dir or "."); neither consumes an owner field because
engine_mcp_http._write_routes does not publish one. The supervisor already holds
the pinned server owner, retires changed owners and atomically publishes routes.
_desired_owners currently collapses serving rows to a graph->owner dictionary.

Before adding a third HTTP consumer, resolve one shared, CWD-independent route
reader and owner/graph identity contract for these existing consumers. Determine
fresh authority and ambiguous-owner handling at the publisher/consumer seam;
do not infer owner authority from possession of a graph-keyed URL. This is a
source-grounded next dependency, not a new public handle, approved authority
change. Existing allowlists stay in force.

Subsequent feature644d6d74 implements the shared owner/graph route contract,
reviewed APPROVE250s; see engine-tool-route.md for applied shape adaptations.
Private transport repair PR3728 is deployed3b541c116e7c03:07UTC with protected
SHA/canary and20:12PDT five-pass app retest. HTTP tool client5406c3e4 separately
is built and exact-head APPROVE339s with227 Windows/230 Linux passes, not yet a
live caller. Fresh per-inference admission and durable tool continuation remain
unbuilt. Reply-owned display is isolated in draft PR3734 atc4850362;352 Windows/
352 Linux passes, exact final review and CI pending. No model selection activated.
Next pure inference/tool transcript boundary is proposed in agent-chat-protocol.md;
legacy text codecs and price guards remain unchanged until reviewed integration.

## Per-inference integration source check, September10 03:38UTC

Feature7e125b4a source read via rg/docview: provider_assignment.py still sets
_SERVED_REQUEST_MAX_INVOCATIONS=2 and supplies it in both served-authority forms.
auth/middleware.py has a set-once seal_provider_request_launch_allowance helper,
but rg over canonical tinyassets finds no caller. Do not describe a longer sealed
candidate/HTTP-loop plan as activated. router.py reserves budget, acquires its
provider slot, revalidates before launch, consumes the request invocation, then
calls provider.complete once. An internal HTTP loop cannot hide several network
inferences under that one accounted launch. Move each inference through trusted
admission/settlement with a finite reviewed turn plan; never refill a spent carrier.

storage/agent_runtime_invocations.py is a read-only authority source with roots
and events restricted to admitted/invalidated, not a tool-execution journal.
storage/agent_runtime_invocation.py provides canonical transactional admission
through SQLiteProviderWorkAuthorityStore and external authority fences. Reuse
the existing database/transaction ownership where appropriate, but do not append
tool-start/result states to the authority chain or silently change its schema.
Any durable tool-intent/result/unknown state table needs its own explicit reviewed
storage contract under this existing change before integration code. Best-effort
conversation text and the pure codec are not alternatives to that journal.
