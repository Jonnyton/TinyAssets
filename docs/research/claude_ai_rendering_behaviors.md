# Claude.ai native rendering behaviors — MCP tool-return reference

Dated 2026-04-12. Scope: what structural shapes of tool output Claude.ai chat will auto-render richly, and what the TinyAssets MCP server should therefore return.

Evidence tiers: **[spec]** MCP spec, **[anthropic]** Anthropic docs, **[observed]** our live testing, **[unconfirmed]** plausible but unsourced. Unconfirmed items are live-test candidates, not design commitments.

## Confirmed behaviors

| Feature | Trigger | Evidence |
|---|---|---|
| MCP tool result passes text content through to the assistant turn | Return `{"type":"text","text":...}` content item | [spec] modelcontextprotocol.io/specification/2025-06-18/server/tools |
| MCP tool result may also return image, audio, resource_link, embedded_resource, plus a separate `structuredContent` JSON object | Same spec. `structuredContent` is separate from unstructured `content`; the spec recommends also mirroring it as a text block for back-compat | [spec] same URL |
| Anthropic API surfaces MCP tool output as `mcp_tool_result` blocks with inner `content` array; text and image content types are passed through | [anthropic] docs.anthropic.com/en/docs/agents-and-tools/mcp-connector, Response content types section |
| `annotations.audience=["user"]` vs `["assistant"]` and `priority` are part of the standard tool-result schema | Lets servers label which content is meant for the user's eye and which is only for the model. Honored at client discretion | [spec] tools spec, Unstructured content note |
| MCP tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`, `title`, `tags`) advertise tool behavior for client UI | [spec] tools spec, Tool annotations; already wired through FastMCP in our `universe_server.py` | [anthropic][observed] |
| Mermaid code fences in assistant prose render inline in Claude.ai chat | Triple-backtick `mermaid` block; used in Anthropic's own MCP docs (e.g. sequenceDiagram blocks render when the page is viewed in Claude.ai) | [observed] task #32 landed; [anthropic] MCP spec pages ship mermaid blocks natively |
| Claude.ai creates Artifacts for sufficiently long / self-contained deliverables (HTML, React, SVG, long Markdown, long code) | Anthropic Help Center — "What are Artifacts and how do I use them" | [anthropic] support.anthropic.com article 9945119 (HTML; access requires browser, not direct markdown fetch) |

## Tool-result implications for the TinyAssets MCP server

1. **Text is the reliable channel.** Every MCP client renders `text` content items. Fancier rendering (mermaid, tables, code) depends on whether the client treats the assistant-message body as Markdown. Claude.ai does; other MCP clients may not. Ship mermaid/markdown inside `text`, never inside a nonstandard field.
2. **Use `structuredContent` in parallel.** For workflow graphs, node lists, etc., return both a human-readable text block (mermaid + markdown summary) and canonical `structuredContent` JSON. Text drives the UI; JSON preserves fidelity for scripted clients. Matches spec back-compat guidance.
3. **Label audience.** Scaffolding responses not meant for the user should carry `annotations.audience=["assistant"]` so clients can suppress them from the transcript.
4. **Keep tool descriptions legible.** `ToolAnnotations` + `title` + `tags` already flow through our FastMCP servers; these feed registries, marketplaces, and Claude.ai's tool picker. Treat every description as phone-screen-sized.
5. **Fence code for diagrams.** A fenced mermaid block inside `text` is the only portable visualization trigger today. Do not rely on clients auto-rendering raw JSON.

## Open questions (flag for live test)

- **Artifact from tool result** — can a tool return content that Claude.ai auto-hoists into the Artifact panel without prose re-emission? Live-test with long React / HTML.
- **Artifact size threshold** — unofficial chatter cites ~20 lines / "standalone, reusable" but no authoritative number.
- **Interactive widgets** — checkboxes, forms, buttons. Markdown checklists render visually but appear non-clickable. Unconfirmed via MCP channel.
- **Citation cards from URLs** — Claude.ai renders preview cards for web-search citations; whether a bare URL in a tool-result text block triggers the same is unknown.
- **Auto-visualization of JSON** — almost certainly prose-prompt-dependent, not structural. A mermaid fence remains the reliable path.
- **KaTeX / LaTeX in tool results** — probably renders (Markdown layer), not end-to-end confirmed.

## Pitfalls

- Oversized text content gets truncated by client and by the model's own context window. Keep tool returns scoped; pre-summarize.
- Malformed JSON inside a text block will render as literal text, not as a visualization — use `structuredContent` instead.
- Wrong code-fence language (e.g. ```` ```graph ```` vs ```` ```mermaid ````) defeats inline diagram rendering. Mermaid requires exactly the `mermaid` fence.
- Returning base64 images inflates transcript size fast. Prefer `resource_link` URIs when the client can fetch them.
- `type: "resource_link"` is spec-legal but not every client fetches or displays the target. Always include a minimal `text` summary alongside.
- Annotation fields are optional; clients MAY ignore them. Do not rely on `audience` to keep secrets — it's a display hint, not an access control.
