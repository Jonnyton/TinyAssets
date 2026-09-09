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

The current route map records graph->URL/secret but not the owner identity. An
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

`providers.call._call_router_with_retry` currently reduces ProviderResponse to
text and updates a process-global last-provider label. `universe_intelligence`
returns that text, and the public converse reply has no per-turn model receipt.
The picker must receive request-local execution metadata; never use that global
label across users. The already deployed HTTP receipt fix preserves the actual
model at the provider boundary but does not bridge this remaining frontend path.

The newer agent-runtime outcome path requires complete usage/cost before success;
current HTTP responses do not provide cost there. Missing cost is unknown, not
zero. An HTTP tool loop must aggregate complete per-inference accounting or hold
unknown settlement honestly. It must not reuse one spent invocation carrier for
another model request or manufacture usage to obtain a successful outcome.

These are concrete integration requirements within tasks2.3/2.4/3.1. They do not
establish that the owner's paused background-self workflow has hit a new wall,
and they do not authorize editing that workflow or changing live credentials.
