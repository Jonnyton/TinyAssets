# FEAT-005 staleness-mitigation: implementation ordering

Source: dev-partner chat (https://chatgpt.com/c/69f64b8d-fa04-83e8-b4d3-bb6e95b16475)
Captured: 2026-05-02

## Problem
ChatGPT and similar connector wrappers cache MCP tool catalog descriptions.
After PR #173 added `kind` and `tags` to `file_bug`, stale clients still
reject the new fields ("Additional properties are not allowed (kind, tags
were unexpected)"). User must trigger `refetch_tools=true`. Even then,
some clients re-cache and revert.

## Recommended ordering (chatbot, ranked)

### 1. `get_status.tool_schema_versions` — first
Cheapest learning signal, doesn't change write semantics. Ship a structured
status block:

```json
"tool_schema_versions": {
  "wiki": {
    "server_schema_version": "2026-05-02-pr173",
    "fields": ["action", "kind", "tags", "component", "severity", "..."],
    "last_changed_at": "2026-05-02T...",
    "supports": {
      "file_bug.kind": true,
      "file_bug.tags": true,
      "feature_request_routing": true
    }
  },
  "extensions": {
    "server_schema_version": "...",
    "last_changed_at": "..."
  }
}
```

Lets stale clients self-diagnose:
- "my local catalog says no kind/tags" + "server status says kind/tags exist" => stale connector catalog.
- Doesn't auto-fix — but creates immediate diagnosis + canary signal.

### 2. `get_tool_schema` action / live schema endpoint
Second. Machine-readable refresh target:
```json
{ "action": "get_tool_schema", "tool": "wiki" }
```
or dedicated MCP-level schema endpoint if that's house style.
Pairs with #1: status tells client it's stale; this lets client recover.

### 3. MCP `listChanged` notification + client refresh check
Third. Right protocol-ish fix but only useful for clients that listen
and refresh — i.e. not OpenAI's wrapper. Implement after #1/#2 because
adoption is gated on client behavior, not server.

### 4. `cache_inferred_kind` fallback — last, with audit fields
Don't lead with this. Tempting (heals stale clients transparently) but
semantically risky — can hide schema drift. If shipped:
```json
{
  "kind": "bug",
  "cache_inferred_kind": "feature",
  "cache_inference_reason": "title starts with Feature request:"
}
```
Explicit + observable so we can spot when it's papering over real problems.

### 5. `schema_version` in descriptions — cosmetic garnish
Cheap but weak. Helps humans, not automation.

## Acceptance test for #1
1. Call `get_status` from any chatbot.
2. Response contains `tool_schema_versions.wiki.supports.file_bug.kind = true`.
3. Documented: "if your local file_bug schema doesn't show `kind`/`tags`,
   your connector catalog is stale; trigger refetch."

## Why this matters for 24/7 loop uptime
Stale connector catalogs silently downgrade community filings (kind=feature
gets sent without kind, ends up routed to bug investigation chain).
Without #1, every catalog-staleness incident requires a human to notice
and run `refetch_tools=true`. With #1, the chatbot itself can detect +
report.
