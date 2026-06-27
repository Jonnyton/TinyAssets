---
status: active
---

# TinyAssets MCP — Tool Return Shape Guidelines

**Status:** standing checklist for all MCP tool returns.
**Source:** `docs/research/claude_ai_rendering_behaviors.md` (2026-04-12).
**Audience:** dev, dev-2, any future contributor adding a TinyAssets MCP action.

## Default return shape

Every tool return is two parallel channels:

1. `text` content item — human-readable Markdown, phone-sized, the primary rendering surface. Claude.ai renders this as Markdown; other MCP clients may render plain. Never rely on non-`text` channels alone.
2. `structuredContent` — canonical JSON. Preserves full fidelity for scripted clients and for our own test harness. Per MCP spec, mirror key fields in the text block for back-compat.

Add `annotations.audience=["user"]` to content the user should see; `["assistant"]` to scaffolding the client can suppress from the transcript. Audience is a display hint — never an access control. `ToolAnnotations` (read/destructive/idempotent/openWorld) stay on the tool itself, already wired through FastMCP.

## Unifying principle: shape the data to match the question

Claude.ai's visualization choice IS the UX. Live evidence (2026-04-12): the same research-paper workflow rendered two different ways in the same chat — a flowchart when the user asked "how do they connect," a card grid when the user asked "show me all my nodes." Same underlying data, different conceptual posture, different rendering. See screenshots in `output/claude_chat_screenshots/`.

The lesson is not "include mermaid everywhere." It is **let the structure advertise its own shape**. Pick the return schema that matches the shape of the question the user just asked. When Claude.ai can see the shape clearly, it picks the right visualization on its own.

## Conceptual-shape hints

Choose the return pattern that matches the question. If a single tool can answer questions with different shapes (e.g. `get_branch` answers both "how do they connect?" and "show me all my nodes"), branch inside the tool on the calling context — or split into two actions whose returns each commit to one shape.

- **Ordered steps with directed connections** ("how do they connect?" "what runs first?"). Return a mermaid flowchart in `text` + an `edges: [{from, to}]` array in `structuredContent`. Claude.ai renders the diagram; the edges array carries fidelity. Current `describe_branch` is the reference implementation.
- **Unordered catalog of related items with metadata** ("show me all my nodes" "list my runs"). Return an array of consistent per-item objects in `structuredContent` under a named field (`nodes`, `items`, `runs`, `entries`). Each item carries the same keys. Text summary lists item names + 1–2 key fields. Claude.ai naturally renders these as card grids or tables.
- **State over time** ("what's happening?" "show me progress"). Return an ordered event list with `{status, ts, node_id, summary}` per event. Claude.ai renders as timeline, progress, or status ticks. Critical for Phase 3 `stream_run` — do not flatten the time axis.
- **Comparison between two things** ("did my edit help?" "show me before and after"). Return `{subject_a, subject_b, differences: [{field, a_value, b_value}]}`. Claude.ai renders as side-by-side or diff. Reference implementation will be `compare_runs` in Phase 4.
- **Single composite artifact with versions** ("show me this node's history" "what did I change?"). Return `{current, history: [{version, ts, diff_summary}]}`. Claude.ai renders as versioned doc with collapsible history.
- **Single scalar or status** ("is it done?" "what's my run status?"). Return a tight one-liner in `text` + the full state object in `structuredContent`. Do not over-render; a status badge does not need a diagram.

If a return does not fit any of these, either the question is unclear or the action is doing two things — reshape before shipping.

## Per-surface guidance

**Read actions (`describe_branch`, `get_run`, `list_runs`, `query_world`, `read_premise`).** Lead with a 1–2 sentence plain-English summary. Pick the conceptual-shape pattern that matches the question being answered (see above). Follow with a compact structured block in the matching idiom — mermaid for flows, a `nodes`/`items` array for catalogs, an event list for state-over-time, a diff block for comparisons. Long JSON belongs in `structuredContent`, not `text`. If text exceeds ~40 lines, summarize and tell the user how to drill in.

**Write actions (`create_branch`, `run_branch`, `update_node`, `judge_run`).** Acknowledge the action in one line (what changed, new identifiers). If the action produces a durable artifact (branch, run, judgment), show the current shape in the same idiom the corresponding read action uses — so the user sees immediately what they just built. Never return only `{"ok": true}`. Always include the new ID and a one-line mental model update.

**Long-running actions (`run_branch`, `stream_run`).** Return a small event object per step, not the accumulated transcript. Per-event format: node_id, status, started_at, one-line output summary, optional structured payload. Phone users poll; keep each response tight.

## Mermaid / code-block / LaTeX rules

- Mermaid: exactly the `mermaid` fence. `graph`, `flowchart` as fences do not render. One diagram per tool return — multiple diagrams slow the renderer and scatter focus.
- Diagram size: ≤ 12 nodes for a phone-legible graph. For larger graphs, summarize and offer a drill-down.
- Code blocks: fence with the real language (`python`, `json`, `bash`). Not `text` or unfenced.
- LaTeX: probably renders through Claude.ai's Markdown layer; unconfirmed. Use only where the content is genuinely math — do not decorate.
- Do not embed mermaid/LaTeX in fields other than `text`. Clients do not scan `structuredContent` for fenced content.

## Deferred pending live test

**Artifact hoisting from tool returns.** Unknown whether long HTML/React/SVG in a `text` block auto-opens Claude.ai's Artifact side panel, or whether it requires the assistant to re-emit in prose. Do not invest in React/HTML tool returns until Mission 4 live-tests this. Current guidance: return Markdown + mermaid; let the assistant build artifacts when the user asks.

Also unconfirmed: citation cards from bare URLs, interactive widgets, artifact size threshold. Flag in return comments; do not design around them.

## Anti-patterns

- **Walls of JSON in `text`.** If it would not fit one phone screen, summarize in `text` and put the rest in `structuredContent`.
- **Stale examples in docstrings.** When an action's return shape changes, update its docstring example the same commit. Drift erodes trust faster than missing docs.
- **Mixed domains in one description.** Every description must speak in the domain the user is in (workflow-building, not fiction-writing) and never list examples from a different domain. Related to #28.
- **Fiction-framing as default.** Workflow is a general workflow platform. Fantasy is one branch. New actions default to workflow language; fiction examples only inside the fantasy domain's own skill surface.
- **Raw JSON when markdown would render.** Tables, lists, checklists — use Markdown, not JSON objects.
- **Returning only `{"ok": true}`.** Every successful write surfaces what changed + what the user should do next.
- **Relying on annotations to hide sensitive data.** `audience=["assistant"]` is a hint; clients may ignore it.
