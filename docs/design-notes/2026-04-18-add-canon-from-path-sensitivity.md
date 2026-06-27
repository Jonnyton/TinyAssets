---
status: active
---

# `add_canon_from_path` — MCP Sensitivity Metadata Research

**Date:** 2026-04-18
**Author:** navigator
**Status:** Research + recommendation. Awaits host/lead decision.
**Relates to:** STATUS.md Concern 2026-04-16 (`add_canon_from_path` "exclude from always-allow", option b).

---

## 1. Question

Can the server mark `add_canon_from_path` — which reads arbitrary server-filesystem paths — as "never auto-approve" such that an MCP client (Claude Desktop etc.) refuses to include it in always-allow, even when the rest of the tool is approved?

## 2. What MCP + FastMCP expose today

The current MCP spec (2025-11-25) defines exactly five `ToolAnnotations` fields — `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` — all treated as *untrusted hints*, and the Trust-and-Safety text is explicit: **"clients MUST NOT rely solely on annotations for security decisions"** ([MCP spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25), [MCP blog — tool annotations as risk vocabulary](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)).

There is **no `sensitiveHint`, `privateHint`, `secretHint`, or `neverAutoApproveHint` in the normative spec.** Five proposals exist (SEP #1487, #1560, #1561, #1913, #1984) adding `secretHint`, `unsafeOutputHint`, `trustedHint`, and broader trust annotations, but none have shipped.

FastMCP's `ToolAnnotations` wraps only the five shipped fields. Setting `destructiveHint=True` is the closest signal today, and even that is advisory — Claude Desktop currently ignores annotations when deciding whether to prompt.

## 3. The load-bearing architectural fact

`add_canon_from_path` is **not a tool**. It is an `action` parameter value on the coarse-grained `universe` tool in `tinyassets/universe_server.py:1075` (`_action_add_canon_from_path` at line 3071, dispatched at line 1165). MCP clients approve *tools*, not *actions*. Claude Desktop's "always allow" toggle binds to the tool's name — once `universe` is allowed, *every* action on it is allowed, including `add_canon_from_path`.

Per Anthropic [issue #24433](https://github.com/anthropics/claude-code/issues/24433), approval granularity is tool-level and arguments are not inspected. There is no protocol- or client-level mechanism to carve out a single action from a tool's always-allow scope.

## 4. Option space

- **(a) Server-side annotation only.** Add `destructiveHint=True` to the `universe` tool (or a future `sensitiveHint`). Cost: ~0. Effect: zero today — Claude Desktop doesn't honor it for approval. Forward-compatible if a `neverAutoApprove` annotation lands.
- **(b) Extract `add_canon_from_path` to its own tool.** Split off `canon_upload` (or similar) as a dedicated `@mcp.tool` with its own annotations. This is the *only* way to make always-allow carve-out work with existing clients. Cost: ~0.5 dev-day + one extra "allow" click in the UX. Plays well with the #11 MCP-split direction: this tool would live in the mounted `fantasy` server, giving domain-owned sensitive ops their own approval scope.
- **(c) Purely client-side config.** Document a `claude_desktop_config.json` pattern with an `alwaysAllow: ["universe:*"]` exclusion, once clients support it. Today no such field exists — this is a request for a future client feature, not a design we can ship.
- **(d) Keep current defense (whitelist).** `TINYASSETS_UPLOAD_WHITELIST` (tinyassets/universe_server.py:141) already rejects out-of-whitelist paths server-side, independent of MCP approval. This is the real guard and remains load-bearing.

## 5. Recommendation

**(b) + (a) + keep (d).** Extract `add_canon_from_path` into its own `@mcp.tool` as part of the #11 MCP domain-split phase M1. Set `destructiveHint=True` and `openWorldHint=True` on it for forward-compat. Keep the whitelist as the actual security boundary — annotations are hints, the whitelist is enforcement.

**Trade-off:** one extra approval click on first-use per universe. Net user-visible cost is small; users who routinely upload canon already expect a distinct confirmation step for "server reads arbitrary path."

**Do not ship (c)-only.** The client config pattern does not exist today in any shipping MCP host. Relying on it is vapor.

## 6. Sources

- [MCP spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [MCP blog — tool annotations as risk vocabulary](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)
- [anthropics/claude-code #24433 — "Always allow" does not persist](https://github.com/anthropics/claude-code/issues/24433)
- [modelcontextprotocol/modelcontextprotocol #711 — Annotations for security/privacy](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/711)
- Codebase: `tinyassets/universe_server.py:1075` (universe tool), `:3071` (`_action_add_canon_from_path`), `:141` (`_upload_whitelist_prefixes`).

---

## 7. 2026-04-19 follow-up — is option-b viable standalone, or only as part of #11 M1?

**Task #13 re-checked the landscape with these specific questions:**

1. **Has MCP shipped `sensitiveHint` / `secretHint` / `neverAutoApprove`?** No. Re-verified against [MCP spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) and the 2026-03-16 tool-annotations blog post. The five fields (`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) remain the entire shipped vocabulary. SEPs #1487, #1560, #1561, #1913, #1984 still pending. Every annotation is explicitly "untrusted hint — clients MUST NOT rely solely on annotations for security decisions."

2. **Can FastMCP annotate a tool "per-call confirm" without extracting it?** No. FastMCP's `ToolAnnotations` wraps only the five shipped MCP fields and carries no server-imposable "always require approval" flag. The approval UX is 100% client-owned. There is no FastMCP primitive we can set to force Claude Desktop / Claude.ai to re-prompt on every call.

3. **What does Claude.ai / Claude Desktop honor today?** Claude Desktop's "Always allow" toggle binds to the tool's *name*, not to specific action arguments ([#24433](https://github.com/anthropics/claude-code/issues/24433)). Persistence across sessions is still buggy (mid-April 2026). A `claude_desktop_config.json` `alwaysAllow` pattern is proposed in the ecosystem but **not shipped** — citing it as a design assumption is vapor. Claude.ai webchat's MCP connector grants tool-level approval at connector-attach time; there is no per-tool or per-action re-prompt UX beyond the generic approval dialog.

4. **Does the conclusion change?** No. Extraction as a standalone `@mcp.tool` remains the only lever that makes always-allow carve-out actually happen in the client.

### 7.1 Is option-b viable standalone (without #11 M1)?

**Yes.** Extraction can ship as a self-contained change independent of the engine/domain MCP split.

**What standalone extraction looks like:**
- Register `add_canon_from_path` (or rename to `canon_upload_local` for clarity) as its own `@mcp.tool` in `tinyassets/universe_server.py` alongside the existing `universe` tool. ~0.5 dev-day, same effort estimate as the original note.
- Remove `add_canon_from_path` from the `universe` tool's action dispatch (`tinyassets/universe_server.py:1166`).
- Keep the server-side path whitelist (`_upload_whitelist_prefixes`, line 142) as the actual security boundary — unchanged and still load-bearing.
- Set `destructiveHint=True` and `openWorldHint=True` on the new tool for forward-compat if a `sensitiveHint` lands later.
- Clients see two tools on the TinyAssets Server surface: `universe` (coarse actions) + `canon_upload_local` (separate approval scope).

**What #11 M1 would add on top:** when the mount-split lands, the extracted tool moves into the mounted `fantasy` server. The carve-out value is unchanged — it only changes which namespace owns the tool. Until M1, the tool simply lives on the root server alongside `universe`.

### 7.2 Why ship now vs wait for M1

Arguments for **ship now**:
- Decoupled work item. 0.5 dev-day. No blocker.
- Security benefit is real and immediate — every user running the current `universe`-with-always-allow is one toggle away from granting arbitrary-path reads. Extracting the tool forces a distinct approval click.
- Forward-compatible with M1. When M1 lands, the tool relocates into `fantasy` with a trivial move — no user-facing breakage beyond the approval re-prompt that naturally follows any tool-namespace change.
- Pre-#3 (Author→Daemon rename) is fine. This touches `tinyassets/universe_server.py`, not files under the rename scope.

Arguments for **wait for M1**:
- Tool-namespace churn. Shipping extraction now + M1 later creates two approval re-prompts for users over the course of weeks. One is annoying; two is worse.
- Cleaner final shape if done together — domain-scoped sensitive tool born inside the domain namespace from day one.

### 7.3 Recommendation

**Ship option-b standalone, before #11 M1.** The two-re-prompt concern is real but small: users approving an uploader tool for the first time will see *one* dialog, then *one more* when M1 relocates it into `fantasy/canon_upload_local`. That's a week of minor UX noise against months of closed security gap. The gap is not theoretical — a user who has "always allow" set on `universe` today has implicitly granted arbitrary-path reads, and the whitelist alone (while load-bearing) does nothing to reduce the LLM's ability to *try* paths it shouldn't.

**What to flag for host approval before the dev work starts:**
- Tool name — recommend `canon_upload_local` (clear intent, daemon vocabulary friendly) over keeping `add_canon_from_path` (LLM-internal name leaking into user UX).
- Whether to keep both `canon_upload_local` *and* the existing `add_canon` action — yes, they serve different input patterns (inline content vs server path) and the split is what makes separate approval meaningful.
- Annotations — `destructiveHint=True`, `openWorldHint=True` on the new tool. No behavior change in Claude Desktop today, forward-compat for when a `sensitiveHint` ships.

**Status change proposal for STATUS.md Concerns line:** the 2026-04-16 "option b research" concern can be closed once this recommendation is accepted. The follow-up is a dev task (standalone extraction) that fits in #11's pre-M1 window but does not depend on M1.
