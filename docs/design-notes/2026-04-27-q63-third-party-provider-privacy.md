---
status: active
title: Q6.3 — Third-party providers in fallback chain — privacy primitive scoping
date: 2026-04-27
author: dev-2
type: design-note
load-bearing-question: When a TinyAssets daemon's fallback chain reaches Gemini/Groq/Grok/etc, what data crosses the network, and what minimal platform primitive lets a chatbot/community privacy posture actually enforce a no-third-party policy?
relates-to:
  - docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md (parent privacy-modes note; §3 already named this gap)
  - docs/audits/2026-04-28-rows-6-7-8-community-build-obviation-addendum.md (commons-first audit; obviated Q6.1 + Q6.2; Q6.3 still-platform)
  - project_privacy_via_community_composition (memory; community-build except for enforcement primitives)
  - project_minimal_primitives_principle (memory; tool surface should shrink)
audience: lead, host
---

# Q6.3 — Third-party providers in fallback chain — privacy primitive scoping

## Summary

Q6.3 is the one privacy question that survives the commons-first reframe of the 2026-04-18 privacy-modes note. The platform CANNOT punt this to community-build, because the leak point is the router — a platform-owned dispatch surface — and the leak happens silently inside an `await provider.complete(prompt, system, cfg)` call before any chatbot/community redactor can intervene.

**Recommendation: the platform ships ONE primitive — a per-universe `allowed_providers: list[str]` allowlist enforced at router boundary — and nothing else.** Threat models, redaction policy, sensitivity classification, taxonomy, etc. all stay community-build per `project_privacy_via_community_composition`. The platform owns the enforcement choke point because nothing else can.

## 1. Current data flow per third-party provider

Each provider sends prompt + system + config raw over the network. No scrubbing today.

### 1.1 Router (`tinyassets/providers/router.py`)

- **Hard-coded chains (L51-56):**
  - `writer`: `claude-code → codex → gemini-free → groq-free → grok-free → ollama-local`
  - `judge`: `codex → gemini-free → groq-free → grok-free → ollama-local`
  - `extract`: `codex → gemini-free → groq-free → ollama-local`
  - `embed`: `ollama-local` (already local-only)
- **Judge ensemble (L61-63):** `_JUDGE_PROVIDERS = ["codex", "gemini-free", "groq-free", "grok-free", "ollama-local"]` — fans out to ALL available in parallel.
- **Per-universe steering today:** `ucfg.preferred_writer` / `preferred_judge` (L152-155) — only **REORDERS** the chain. Does NOT remove third-party links. A pinned-local universe with `preferred_writer="ollama-local"` still has `claude-code, codex, gemini-free, groq-free, grok-free` in the chain after it. If `ollama-local` raises `ProviderError`, fallback continues into the third-party providers.
- **`TINYASSETS_PIN_WRITER` env (L143-146):** narrows writer chain to the single pinned provider with no fallback. **This is the only existing hard-pin in the system.** Process-wide, not per-universe; kills fallback safety. Not an answer for Q6.3 because it's process-wide and writer-only.

### 1.2 Per-provider payload (verbatim wire content)

| Provider | File | Wire content | Endpoint | Token retention |
|---|---|---|---|---|
| `gemini-free` | `gemini_provider.py:51-59` | `model="gemini-2.5-flash"`, `contents=prompt`, `system_instruction=system`, `temperature`, `max_output_tokens` | `google-genai` SDK → Google Cloud (free tier) | Per Google free-tier ToS |
| `groq-free` | `groq_provider.py:48-58` | `model="llama-3.3-70b-versatile"`, `messages=[{"role":"system","content":system},{"role":"user","content":prompt}]`, `temperature`, `max_tokens` | `groq` SDK → Groq Cloud | Per Groq free-tier ToS |
| `grok-free` | `grok_provider.py:51-63` | `model="grok-4.1-fast"`, `messages=[{system, user}]`, `temperature`, `max_tokens` | `openai` SDK → `api.x.ai/v1` | Per xAI ToS |

**No tracing identifiers (universe_id, run_id, branch_id, node_id) are added by the provider — but the prompt/system content typically embeds them (e.g. node prompts often include universe canon, prior-step output, scene context). Scrubbing structured identifiers does not address content leakage; the prose IS the leak.**

### 1.3 What the router does NOT do today

- No per-universe `allowed_providers` allowlist (the gap §3 of `2026-04-18-privacy-modes-for-sensitive-workflows.md` named).
- No content-classification hook before `provider.complete()`.
- No metadata scrubber (timestamps, identifiers, structural shape).
- No structured "privacy-failed" exception path — silent fallback up the chain.

## 2. Minimal-redaction options

Five options ordered increasing-cost / increasing-coverage:

### Option A — Allowlist enforcement at router (THIS NOTE'S RECOMMENDATION)

**Shape:** add `allowed_providers: list[str] | None` field to `UniverseConfig` (`tinyassets/config.py`). Router consults at call time:

- Before `for provider_name in chain:` loop, filter chain to `[p for p in chain if p in allowed_providers]` when set.
- If filtered chain is empty → raise `AllProvidersExhaustedError` immediately (fail loudly, no implicit local fallback — caller gets explicit signal that policy blocked the call).
- Same filter applied to `_JUDGE_PROVIDERS` for `call_judge_ensemble`.
- `call_with_policy` honors the allowlist by intersecting the policy `attempt_order` with `allowed_providers` before attempting.

**Cost:** ~30 LOC change in `router.py` + ~5 LOC field add in `config.py` + 4-6 tests.

**Coverage:** complete for the Q6.3 question. A universe with `allowed_providers: ["ollama-local"]` cannot leak to any third-party provider; failure is loud.

**Why this is the platform's responsibility:** the router is the single chokepoint. There is no community-build path that catches a silent fallback to Groq inside `await provider.complete()` after the chatbot has handed off the request.

### Option B — Per-provider-call content classifier hook

**Shape:** allow per-universe `content_classifier: Callable[[str, str], ClassifierVerdict]` invoked before each `provider.complete()`. Verdict gates whether the call proceeds.

**Cost:** larger — requires a classifier-loading mechanism, a stable interface, sandbox guarantees on the classifier itself.

**Why we should NOT ship this primitive:** classification policy IS what `project_privacy_via_community_composition` says belongs to community. The chatbot can already classify before it issues an MCP call. Re-doing it inside the router duplicates work and forces the platform to take a position on classification taxonomy.

### Option C — Structured-redactor pipeline before send

**Shape:** chain of redactors (PII regex, named-entity, structural). Configured per-universe.

**Cost:** large; fragile (regex misses); ongoing maintenance burden.

**Why NO:** redaction taxonomy is exactly what the privacy-via-composition memory carves out as community-build. Different domains (legal, medical, AP, fiction) want different redactors. Platform shipping a redactor primitive == platform picking taxonomy == anti-pattern per `project_privacy_via_community_composition`.

### Option D — Metadata scrubbing (universe_id, timestamps, identifiers)

**Shape:** remove or alias structural identifiers in prompt + system before send.

**Why NO (for Q6.3 specifically):** §4 of the parent privacy note explicitly accepts metadata leak as residual. Q6.3 is about CONTENT (prompt body), not metadata.

### Option E — Hard-fail when third-party provider in chain reaches an `is_sensitive` request

**Shape:** request carries `sensitivity: "confidential"` flag; router rejects any non-local provider when flag is set.

**Why NO:** this is Option A by another name (allowlist of `[ollama-local]` for confidential), but worse — the flag-shape couples the request taxonomy ("confidential" vs others) into the platform. Allowlist by provider name is more general and doesn't embed taxonomy.

## 3. Recommended split — platform primitive vs community-build

Per `project_privacy_via_community_composition`: "Platform owns enforcement primitives only."

| Concern | Owner | Mechanism |
|---|---|---|
| **Fallback chain enforcement** (router refuses non-allowlisted providers) | **PLATFORM** | Option A — `allowed_providers` field on `UniverseConfig`; router-level filter. |
| Sensitivity classification (which workflows are private) | Community / chatbot | Chatbot reads workflow context, decides per-call whether to invoke Workflow on a sensitive universe; sets `allowed_providers` at universe-create time. |
| Threat-model definition (what counts as sensitive) | Community / chatbot | Per-domain rubrics (AP, medical, legal). Lives in user's chatbot memory or a community-published rubric. Chatbot reads rubric → decides allowlist. |
| Redaction taxonomy (what gets redacted, how) | Community / chatbot | Chatbot redacts at MCP-call time before tool-call body lands in Anthropic-side relay. Out of scope for the router. |
| Metadata scrubbing | Accepted residual | Per parent note §4. Platform doesn't enforce; chatbot can choose universe ID aliasing if metadata sensitivity is high. |
| Provider rotation / quota / billing | PLATFORM | Existing `QuotaTracker` — already platform. |

**The single platform primitive Q6.3 needs: `allowed_providers: list[str] | None` field on `UniverseConfig`, enforced at router boundary, hard-fail when filtered chain is empty.**

## 4. Open questions for host

1. **`allowed_providers` default.** When unset, current behavior (full chain including third-party) preserved? Recommend yes — backwards-compatible; opt-in for privacy. Pre-existing universes don't change behavior on upgrade.
2. **Audit-log when a request hits an allowlist-empty failure.** Log to `logger.warning` only, or surface to `get_status` / `get_progress`? Recommend `logger.warning` at router + structured exception that callers can render. No new persistent surface; the hard-fail is already loud.
3. **Allowlist scope — universe-only, or also per-branch / per-node?** Per-universe is sufficient for the parent privacy note's Allied-AP use case. Per-branch/per-node adds combinatorial config without obvious extra leverage. Recommend per-universe only for v1; if a real use case for finer scope emerges, add later.
4. **Process-wide `TINYASSETS_PIN_WRITER` interaction.** When both pin and allowlist are set, pin wins (existing behavior — narrows chain to single provider, then allowlist filter applies; if pin not in allowlist, hard-fail). Recommend keep current pin semantics, document the interaction.
5. **Judge ensemble (`call_judge_ensemble`) under allowlist.** Filter `_JUDGE_PROVIDERS` by allowlist — yes; if filtered to empty, return `[]` (caller already handles empty list per L484-486). Already the existing pattern.

## 5. Effort + dispatch shape

- **Code change:** ~30-40 LOC (router filter + config field + judge-ensemble filter).
- **Tests:** 4-6 unit tests in `tests/test_provider_router.py` (or new `test_provider_router_allowlist.py`):
  - `allowed_providers=["ollama-local"]` blocks `gemini-free` from running.
  - Empty allowlist filter → `AllProvidersExhaustedError`.
  - `call_judge_ensemble` skips disallowed providers.
  - `call_with_policy` policy chain intersects with allowlist correctly.
  - Backwards-compat: `allowed_providers=None` → full chain unchanged.
  - Pin + allowlist disjoint → hard-fail (pin wins, then allowlist rejects pin).
- **Doc updates:** AGENTS.md "Configuration — environment variables" → no env-var change (config field, not env-var). PLAN.md "Engine and Domains" privacy section → 1 paragraph cross-ref.
- **Dispatch:** single dev-2 task, ~1.5h end-to-end. Can run independently of #18 (router file is not in lock-set). NOT for THIS session — design-note delivery only per task brief.

## 6. Cross-references

- `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` §3 — "router does not consult a per-universe allowlist today" gap statement (this note converts that gap into a primitive proposal).
- `docs/audits/2026-04-28-rows-6-7-8-community-build-obviation-addendum.md` — commons-first audit; classified Q6.3 as still-platform.
- `tinyassets/providers/router.py` — implementation target.
- `tinyassets/config.py:29,33` — `preferred_writer/preferred_judge` (existing per-universe steering surface to extend).
- `tinyassets/preferences.py:33` — `LOCAL_PROVIDERS = ["ollama-local"]` (already the canonical "local-only" pin source).
- `project_privacy_via_community_composition` (memory) — "Platform owns enforcement primitives only" rule.
- `project_minimal_primitives_principle` (memory) — "fewest primitives" frame; allowlist-as-list is one field, not a taxonomy.

## 7. What this note does NOT cover

- Anthropic-side retention (parent note §2 owns).
- Metadata leak via tool-call envelope (parent note §4 owns).
- Filesystem-side privacy (`private_output/`, sensitivity_tier on disk) — REFRAMED as community-build per `project_privacy_via_community_composition`.
- Subprocess providers (`claude-code`, `codex`) — these run on the host machine; payload doesn't leave the host until the subprocess CLI sends it. Same allowlist works (allowlist names "claude-code" or omits it).
- Dispatch: design-note only per task brief #14. Implementation queued as a separate dev task post-#18.
