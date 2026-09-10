# Private HTTP engine-tool client: next bounded slice

September10,2026. Proposed task2.4 implementation boundary, not an activated HTTP
agent loop. Reuse the shared owner-bound route from644d6d74 and installed FastMCP
3.2/MCP transport. Do not import engine_mcp_server and mutate its global identity.

## Contract

One async client context belongs to one verified caller actor/graph and one route
generation (the route includes the supervisor's per-server secret). Capture the
canonical root once, read through read_engine_mcp_route, and never take a URL or
bearer from model output, tool arguments or caller-supplied transport settings.
Re-read the captured root before every list/call and refuse if flag, allowlist,
owner, graph, port or secret differs. Do not reconnect and replay an operation on
a replacement route. This is consistency, not fresh inference permission: the
existing pinned server still enforces each tool's real authority.

Use the existing FastMCP Client with StreamableHttpTransport and a fixed internal
HTTP-client factory. Disable redirects and environment proxies (trust_env=False),
provide only this route's fixed Authorization header, and never forward outer
request headers/auth even though FastMCP's default transport collects them.
No OAuth, sampling, elicitation, model-initiated roots, task execution or new
background tool jobs. Use call_tool_mcp to preserve MCP content, structuredContent
and isError without schema coercion or a second inferred tool call.

List the actual server's schemas and intersect with SERVED_ENGINE_MCP_TOOLS and
the caller's explicitly supplied enabled_tools subset. A missing requested tool,
duplicate tool name, malformed schema or incomplete/looping pagination refuses
readiness; do not claim full parity from a partial list. No tool name outside that
exact validated discovered subset may dispatch. Server descriptions/results are
untrusted content, never connection or permission instructions. Keep opaque
argument values intact; do not reinterpret actor/graph fields as routing.

Transport errors carry a fixed secret-free code, not raw exceptions/URLs/headers.
Errors before sending tools/call are not_sent; after invoking it, unavailable
results are unknown, never permission to replay. An MCP isError response remains
an actual received tool result, not a transport exception or automatic retry.
No wrapper retries. Installed MCP's SSE reconnection is GET response resumption,
not another tools/call POST; cover this transport claim in the boundary tests.
Cancellation propagates without replacement; the future caller MUST durably
record tool intent before invoking this client and preserve unknown outcomes.
The client does not own or invent that journal, launch allowance or cost receipt.

Client/session/HTTP resources close on exit; cleanup errors must not erase a
result already received and persisted by the caller. No global client pool, no
secret-bearing repr, no shared mutable state across universes. Runtime selector
must still hold HTTP full-agent eligibility until tool loop, per-inference
admission/accounting and durable continuation are integrated and proven live.

## Source evidence and proof boundary

September10 installed-library signature/source inspection: FastMCP3.2.0
StreamableHttpTransport.connect_session merges outer Authorization with explicit
headers and passes follow_redirects=True to a custom factory. Override both at
our factory instead of relying on defaults. Client.call_tool_mcp returns the raw
MCP CallToolResult; call_tool does extra result/schema handling. The MCP transport
has GET/SSE resumption paths; verify no effectful POST reissue under failure.
These local sources are exact dependency evidence, not future-version guarantees.

Tests use synthetic route records and in-process fake MCP/HTTP endpoints only,
never the owner's live engine route, secret or workflows. Cover exact transport
construction, redirects/proxies/outer-header isolation, intersected discovery,
cross-owner/stale-route refusal, preserved structured/content/error results,
one dispatch on failure/cancellation and cleanup. Include a real protocol fixture
to avoid proving only a fake Client, and run Windows plus actual Docker Linux.
One cross-family shape/basic-safety review precedes code. No public handle,
permission/storage change or live provider/model selection in this slice.
