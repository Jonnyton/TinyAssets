---
status: active
---

# Private Universes: Payload-Redacted Enforcement Under Claude.ai Chat

**Date:** 2026-04-18
**Author:** navigator
**Status:** Decision-oriented design note. Becomes STATUS.md concern on land.
**Relates to:** Allied Residential AP workflows (HUD/LIHTC, vendor invoices). Strategic posture for any non-fiction domain.

**Constraint:** The chat interface is Claude.ai webchat. Not optional. Local-chatbot alternatives are out of scope for this design.

---

## 1. The data flow — what actually transits Anthropic

A single MCP tool call through Claude.ai:

```
user browser
   ├──▶ Claude.ai (Anthropic servers)               [typed prompt: transits]
   │       ├──▶ Claude model (Anthropic infra)      [prompt + tool schemas: observed]
   │       │       │
   │       │       ▼
   │       │     decides: call universe.inspect(uid="allied-ap")
   │       │
   │       ├──▶ MCP call relayed to local server    [call args: transit Anthropic]
   │       ▼
   │  local universe-server (host machine)          [executes, reads local files]
   │       │
   │       ▼
   │  tool response                                  ← THE CHOKEPOINT
   │       ▲
   │       │
   │       ├──◀ response relayed back via Anthropic [response body: transits Anthropic]
   │       │
   │       ▼
   │     Claude model reads tool response           [content in model context]
   │
   └──◀ Claude.ai (Anthropic servers)               [final answer: transits]
```

**Every byte that flows through the chatbot transits Anthropic.** The "local server" label is misleading — the server is local, but the *traffic* isn't.

**What we control:** only the response body. That is this design's entire enforcement surface. Everything below is about shaping what the server is willing to *say* when Claude.ai asks.

## 2. Anthropic retention posture (context, not enforcement)

- **Claude.ai Free/Pro/Max:** default post-2025-09-28 is 5-year retention + used for training unless user opted out. Opt-out reduces to 30-day retention and excludes training ([Anthropic consumer terms 2025-08-28](https://www.anthropic.com/news/updates-to-our-consumer-terms), [TechCrunch](https://techcrunch.com/2025/08/28/anthropic-users-face-a-new-choice-opt-out-or-share-your-data-for-ai-training/)).
- **Claude for Work / Enterprise / Gov / API:** never used for training; 7-day API log default, extendable via DPA, ZDR available enterprise-only ([Anthropic privacy center](https://privacy.claude.com/en/articles/10023548-how-long-do-you-store-my-data)).

**Implication for this design:** the host MUST have training opt-out set on their Claude.ai account as a hygiene baseline. That bounds the retention damage envelope to 30 days. Payload redaction (§7–8) ensures there is little to retain.

## 3. Daemon-side commitment — non-negotiable

Private universes pin the daemon to local providers. `tinyassets/preferences.py:31` already declares `LOCAL_PROVIDERS = ["ollama-local"]` and defaults to it. The gap is enforcement: `tinyassets/providers/router.py` does not consult a per-universe allowlist today. A silent fallback to Groq / OpenAI / Anthropic would leak everything the daemon's system prompt touched.

**Required:** per-universe `allowed_providers` list, enforced at router level. Hard-fail when the allowlist is violated, matching the "fail loudly, never silently" hard rule. For private universes, `allowed_providers = ["ollama-local"]`. No ambient fallback permitted.

## 4. Metadata leakage — accepted residual risk

Even with §7–8 redaction, some signal leaks through Claude.ai:

- **Universe ID** transits in every tool call (`universe_id: "allied-ap"` gives away the domain).
- **Tool names + call frequency** — a pattern of `run_branch` + `get_run` + `read_output` bursts reveals workflow shape.
- **Timestamps** — when the host works AP.
- **Counts and statuses** — "42 invoices processed" reveals volume.

**Mitigation available:** universe-name aliasing (§7.5). Everything else is accepted residual — if the host judges metadata itself sensitive, the only fix is not using Claude.ai at all, which is out of bounds per constraint. The open question (§6 #2) surfaces this explicitly.

## 5. Host's near-term Allied AP path — 1-week plan

1. **Today.** Confirm training opt-out is set on Claude.ai account. Verify `preferences.py` defaults are `ollama-local` only for Allied. No hygiene substitute for the §7 work, but caps the damage envelope at 30 days.
2. **This week — land the MVP §7.6 slice.** Tag `allied-ap` universe as `sensitivity_tier: confidential`; move its filesystem to `private_output/allied-ap/`; wire the response redactor per §8. Claude.ai chat continues as the user interface.
3. **Operational pattern.** User prompts Claude.ai like "code today's invoices" or "process batch for HOM509-94536497" (identifiers referenced, content never pasted). MCP call returns `{"run_id": "...", "status": "accepted", "count": 42}` — no amounts, no vendor names. Daemon runs on `ollama-local`, outputs land in `private_output/allied-ap/output/`. Host opens the resulting CSV locally (filesystem, tray panel, `code` editor) for Voyager import.
4. **Outcome.** Zero sensitive content transits Anthropic. Universe IDs, call counts, and timestamps still leak (accepted residual). Daemon LLM provider pinned to local; no third-party fallback path exists for this universe.

The pattern is: **Claude.ai orchestrates, the daemon processes, the filesystem holds the truth, the host views locally.**

## 6. Open questions for host

1. **Threat model scope.** Are we defending against (a) Anthropic as honest operator that might subpoena / be breached, (b) Anthropic as potential adversary, or (c) arbitrary observers of chat logs? Answer bounds what "acceptable metadata leakage" means in §4.
2. **Metadata acceptable?** Is "host runs an Allied AP workflow" itself sensitive, or only the content? If yes, §7.5 universe-aliasing becomes mandatory, not optional.
3. **Third-party providers in daemon fallback.** Ever? If no, hard-remove the fallback path from `providers/router.py` for any universe in the `confidential` tier. If yes, under what conditions? "Local provider unavailable for >5min" is not a justification — the daemon should pause, not reach out.

---

## 7. The private-universe flag — the enforcement primitive

Sections 1–5 describe the intent. §7 is the mechanism. Without a per-universe flag with teeth, private mode is host discipline, not a feature.

### 7.1 Shape

Per-universe config:

```yaml
# private_output/<universe_id>/config.yaml  (or output/ for public universes)
universe_id: allied-ap
sensitivity_tier: confidential         # public | internal | confidential
privacy: private                       # convenience alias; set when tier=confidential
private_since: "2026-04-18T12:00:00Z"  # when flag was enabled
universe_alias: "uni_7b2a3c"           # optional opaque wire-name (§7.5)
allowed_providers: ["ollama-local"]    # enforced by router (§3)
```

Default is `public`. Setting `confidential` means the universe:

1. **Payload-redacted at the tool layer** (§8). Every action has a minimum-information response shape. Content (text, values, names) never returns to Claude.ai.
2. **Daemon pinned to local providers** (§3). Router rejects any attempt to use a non-allowlisted provider.
3. **Lives outside the default `output/` tree.** `private_output/<universe_id>/` is canonical. Backups, exports, `git` snapshots, share-to-github helpers all scope to `output/` by default. Including private data requires explicit `--include-private` per operation, unsupported from remote MCP.
4. **Surfaced in local tray UX.** Lock glyph on the universe list. Warning on tier transition: "Confidential: past transcripts are not scrubbed. Consider wiping + reingesting if historical record is sensitive." Optional universe-name alias for the wire (§7.5).

### 7.2 Private-tier vs memory-scope tiers

The `sensitivity_tier` flag sits **above** the four-tier memory-scope hierarchy (node/branch/goal/user/universe). It is a universe-level *admission-and-redaction* envelope:

```
sensitivity_tier: confidential  →  tool-layer redaction envelope
    └── universe scope (ACL members who MAY inspect locally)
         └── user scope (per-user visibility)
              └── goal/branch/node scope (contextual narrowing)
```

A confidential universe can still have tiered ACL members, per-user slices, per-goal branches. Those operate inside the redaction envelope — they narrow what the *daemon* sees internally; §8 narrows what *Claude.ai* sees externally.

### 7.3 Client fingerprinting at MCP `initialize`

Promoted from long-term list — this is the audit mechanism that makes redaction auditable.

Every MCP connection begins with an `initialize` request ([MCP spec 2025-03-26 lifecycle](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle)) carrying:

```json
{
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "claude-ai", "version": "..."}
  }
}
```

TinyAssets Server should:

- **Parse and log `clientInfo.name` + `Origin` header** on every session. Claude.ai connects from `https://claude.ai`; Claude Desktop reports differently; direct API calls identify themselves.
- **Stamp every tool response with `client_id`** — the resolved client identity for the session. Host auditing ("did anything confidential go out through Claude.ai?") becomes a query against an audit log, not a trust question.
- **Advisory-only today** — clients can lie about `clientInfo.name`. The real enforcement is response redaction (§8): even if a malicious client masquerades, the redactor gives it nothing useful.

This is the Q1-amendment answer: client fingerprinting is how we *know* a request came from Claude.ai; the redactor (§8) is why it doesn't matter if a request lies.

### 7.4 "Does marking a universe confidential retroactively scrub leaks?"

**No.** Any prompt/response that already transited Claude.ai before the flag was set is in Anthropic's retention window. The flag changes *future* behavior only.

Implications:
- Pre-flag content is publicly-tainted. Host decides wipe+reingest (analogous to Q2 echoes decision) or accept.
- `private_since: <ISO-timestamp>` lets tooling audit which content pre-dates the flag.
- Tray UX must show a warning on flag transition.

### 7.5 Metadata-leakage mitigation — universe-name aliasing

Universe IDs transit every tool call. `universe_id: "allied-ap"` alone reveals the domain. When §6 question #2 answer is "metadata matters," the universe's on-wire name can be aliased:

```yaml
universe_id: allied-ap            # local-only; tray UX uses this
universe_alias: "uni_7b2a3c"      # wire name Claude.ai sees
```

All MCP responses substitute `universe_alias` for `universe_id` before serialization. Logs, status displays, and tray still use the friendly name; Anthropic only ever sees the opaque hash. Aliasing applies only when `sensitivity_tier == confidential`; otherwise no-op. Small change to the response serializer, no client-side impact.

### 7.6 Minimum viable slice — phased

~3–4 dev-days. Standalone exec plan; does not block #11.

1. **`sensitivity_tier` field + `private_output/` tree.** ~0.5 day. Additive config field; filesystem layout split honored in all write paths.
2. **Client fingerprinting + audit log.** ~0.5 day. Parse `clientInfo.name` + `Origin`, log per session, stamp on responses.
3. **Response redactor dispatch (§8).** ~1 day. Every action checks target universe's tier, routes response through redactor when confidential.
4. **Router per-universe allowlist (§3).** ~0.5 day. `preferences.py:LOCAL_PROVIDERS` is the starting allowlist for confidential universes.
5. **Universe-name aliasing (§7.5).** ~0.5 day. Additive field + serializer substitution.
6. **Tray UX: lock glyph, tier-transition warning, "mark private" affordance.** ~0.5 day.
7. **Docs: threat model page + non-retroactivity warning.** ~0.5 day.

### 7.7 What the flag does NOT solve

- **Metadata leakage:** mitigated via universe-aliasing (§7.5) but not eliminated. Tool names, timestamps, call counts still visible to Anthropic.
- **Pre-flag content:** already transited, already tainted. See §7.4.
- **User typing sensitive text into chat:** §9 tool-description nudges reduce likelihood; cannot eliminate.
- **Within-ACL leaks:** governed by memory-scope tiers, not this flag.

### 7.8 Why this is load-bearing

Without §7 the rest of the note is a pep talk about user discipline. The flag, plus §8 redaction, converts private-mode from a posture into a feature. The host can point at it in sales: "this universe is flagged confidential; no byte of its content has left my machine since 2026-04-18 because the server *refuses to return it* to Claude.ai."

---

## 8. Per-action response-redaction table

For every MCP action callable on a `confidential` universe, the server returns **only** the fields listed. Content fields are either replaced with counts/IDs/statuses or omitted entirely. This is the practical enforcement point.

| Action | Public-universe response (today) | Confidential-universe response |
|---|---|---|
| `universe action=list` | array of `{universe_id, name, ...}` | array of `{universe_alias, tier: "confidential"}` — friendly name omitted; no content previews |
| `universe action=inspect` | premise text, recent notes, work targets, output file tree, activity tail | `{universe_alias, tier, has_premise: bool, note_count, active_target_count, output_file_count, last_activity_bucket}` — zero content strings |
| `universe action=read_premise` | full PROGRAM.md | **REJECT** — `{"error": "read_premise is local-only for confidential universes.", "hint": "Open private_output/<alias>/PROGRAM.md on the host machine."}` |
| `universe action=read_output` / `read_canon` | file content | **REJECT** — same shape as above |
| `universe action=list_canon` | array of `{filename, size, provenance, source}` | `{count, doc_ids: [opaque], tier_counts: {sources: N, synthesized: M}}` — no filenames, no provenance |
| `universe action=get_activity` | last N log lines | `{line_count, last_activity_bucket: "fresh\|idle\|dormant"}` — no log text |
| `universe action=get_ledger` | action list with payloads | `{entry_count, last_entry_at}` |
| `universe action=query_world` | facts / characters / timeline text | **REJECT** (content-bearing) |
| `universe action=set_premise` | confirmation + first 200 chars echo | `{"accepted": true, "bytes": N, "hash": "<sha256>"}` — no echo |
| `universe action=add_canon` / `add_canon_from_path` | routed_to, byte count, **first-200-byte preview** | `{"accepted": true, "routed_to": "sources", "bytes": N, "hash": "<sha256>"}` — **no preview** (this is where the `add_canon_from_path` "exclude from always-allow" design-note dovetails) |
| `universe action=give_direction` (note) | note-id + category + summary | `{"note_id": "<opaque>", "accepted": true}` |
| `universe action=control_daemon status` | phase, word_count, accept_rate, unreconciled_writes | `{"phase_human": "...", "staleness": "fresh\|idle\|dormant", "unreconciled_writes_count": N}` — no raw phase string, no word count (reveals progress volume) |
| `universe action=submit_request` | request-id + preview | `{"request_id": "<opaque>", "accepted": true}` |
| `extensions action=run_branch` | run-id + outputs preview | `{"run_id": "<opaque>", "status": "accepted", "duration_seconds": N}` — no outputs |
| `extensions action=get_run` | status + full outputs + errors | `{"status", "duration_seconds", "error_type": "..."}` (error *class*, not message) |
| `extensions action=stream_run` | live log events | `{"events_emitted": N, "status"}` — no log text |
| `extensions action=get_node_output` | output payload | **REJECT** |
| `goals action=list` / `get` | goal text, discussion | `{count, goal_ids: [opaque]}` / REJECT |
| `gates action=list_claims` | claim evidence URLs | `{count, statuses: {...}}` |
| `wiki action=read` / `search` / `list` | wiki content | **REJECT** — wiki is detail-bearing by nature; confidential universes view locally |

**Design principles for the table:**
- **Counts are safe, content is not.** "42 invoices" leaks less than "HOM509-94536497 at $X for vendor Y."
- **Opaque IDs are safe, natural keys are not by default.** Private universes mint `run_id`, `note_id`, `request_id`, etc. as opaque tokens. Natural-key identifiers the host already shares (invoice numbers, unit IDs) are passed through — the host's workflow uses them operationally; redacting them would break the user pattern. Revisit if post-V1 audit shows natural-key patterning is a real leak source.
- **Status strings are bucketed.** `staleness: "fresh|idle|dormant"` buckets leak less than raw timestamps.
- **Errors return class, not message.** `error_type: "file_not_found"` is safe; the error message itself may contain a filesystem path with a vendor name.
- **Every rejected action names the local-only remediation.** The user should know where to look locally (tray panel, `private_output/<alias>/` on disk) when a confidential read is refused.

### 8.1 Redactor implementation shape

A single dispatcher in `tinyassets/universe_server.py` near `_dispatch_with_ledger` (~line 712):

```python
def _apply_redaction(action: str, result: str, universe_id: str) -> str:
    tier = _resolve_tier(universe_id)
    if tier != "confidential":
        return result
    return _REDACTORS.get(action, _default_reject)(result)
```

`_REDACTORS` is a per-action dict implementing the table above. Missing entries default to reject — **fail closed** for any action not yet explicitly classified. This is the principle that matters: adding new actions requires a redactor decision, not a silent pass-through.

---

## 9. Tool-description nudges — teaching the Claude.ai agent to behave

The Claude.ai-hosted agent is helpful by default. It will try to be useful with whatever it sees. On a confidential universe it *will* attempt to infer content from metadata if not told not to. Prevention is via MCP tool description strings — the agent reads them as part of the tool schema and conditions its behavior.

Proposed additions to the `universe` tool's `instructions`/docstring in `tinyassets/universe_server.py:57-103`:

```
"\n\nHARD RULE — CONFIDENTIAL UNIVERSE BEHAVIOR: When a universe response "
"includes `\"tier\": \"confidential\"` or the response shape is explicitly "
"redacted (counts and IDs only, no content strings):\n"
"  (1) DO NOT attempt to infer, reconstruct, summarize, or describe the "
"redacted content from the metadata. The metadata you see is ALL the user "
"wanted you to see.\n"
"  (2) DO NOT ask the user to paste the content into chat as a workaround. "
"The content is confidential; pasting it defeats the design.\n"
"  (3) If the user asks to see details, tell them: 'That universe is "
"confidential. Open private_output/<alias>/ on your machine or use the tray "
"panel to view locally.' Do not transit the content through this chat.\n"
"  (4) If the user pastes likely-sensitive content (dollar amounts, PII, "
"vendor names, HUD/LIHTC identifiers) in a message directed at a confidential "
"universe, decline: 'That looks like content you meant to keep local. Drop "
"the file at a path and I can reference it with `add_canon_from_path`; or "
"open the tray and add it there.' Then STOP — do not proceed with the "
"reference the user intended.\n"
```

Additionally: the response envelope for any confidential-universe action should carry a one-line instruction-to-agent, redundant with the above but delivered at point-of-use:

```json
{
  "tier": "confidential",
  "_agent_hint": "Metadata-only response. Do not infer content. Refer the user to local view.",
  ...
}
```

**Why both?** The tool-description nudge runs at schema registration (every session start) and conditions baseline behavior. The per-response `_agent_hint` is a reinforcement reminder so context-bleed from long chat histories doesn't erode the rule. Tool-description instructions are hints the agent can ignore; redundancy is the mitigation.

---

## 10. Long-term shipping list

All hang off §7–8. Tightened from prior draft:

1. **`sensitivity_tier` field + `private_output/` tree** — §7.1. Load-bearing.
2. **Client fingerprinting at MCP `initialize`** — §7.3. Promoted from long-term to V1; advisory-but-auditable.
3. **Per-universe provider allowlist in `providers/router.py`** — §3. Enforcement of "daemon never leaves the machine."
4. **Per-action response redactor with fail-closed default** — §8. The practical enforcement point.
5. **Universe-name aliasing** — §7.5. Metadata mitigation when host judges universe IDs sensitive.
6. **Tray UX: lock glyph, tier-transition warning, "mark private" affordance** — §7.6 step 6.
7. **Viral framing and threat-model docs** — "the daemon that never tells on you." Private-mode is real differentiator for LIHTC, legal, medical, HR. Ship with explicit threat model covering §7.4 non-retroactivity.

Not on this list: local-chatbot launchers, LM Studio integration, llama.cpp webui bridging. Out of scope per constraint.

---

## 11. Sources

- [Anthropic — Updates to Consumer Terms 2025-08-28](https://www.anthropic.com/news/updates-to-our-consumer-terms)
- [TechCrunch — Anthropic opt-out deadline](https://techcrunch.com/2025/08/28/anthropic-users-face-a-new-choice-opt-out-or-share-your-data-for-ai-training/)
- [Anthropic Privacy Center — data retention](https://privacy.claude.com/en/articles/10023548-how-long-do-you-store-my-data)
- [Anthropic Privacy Center — training opt-out](https://privacy.claude.com/en/articles/10023580-is-my-data-used-for-model-training)
- [MCP spec 2025-03-26 — lifecycle / initialize / clientInfo](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle)
- [MCPJam — MCP auth checklist (November 2025 spec)](https://www.mcpjam.com/blog/mcp-oauth-guide) — Origin header validation.
- Codebase: `tinyassets/preferences.py:24-34` (LOCAL_PROVIDERS vs SUBSCRIPTION_PROVIDERS), `tinyassets/providers/router.py` (router target for allowlist enforcement), `tinyassets/universe_server.py:57-105` (MCP instructions — §9 nudges land here), `:712` (`_dispatch_with_ledger` — redactor hook point), `:1075-1180` (universe tool dispatch map — §8 enforcement surface), `:3450+` (`_action_create_universe` — add `sensitivity_tier` param).
