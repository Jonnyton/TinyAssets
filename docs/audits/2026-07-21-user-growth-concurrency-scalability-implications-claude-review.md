I completed the opposite-provider review and wrote it to `docs/audits/2026-07-21-user-growth-concurrency-scalability-implications-claude-review.md`.

**Verdict: ADAPT.** The Codex research is solid — the executive-answer table honestly separates target architecture from current single-host reality, every current-code claim I checked held up (deploy/compose.yml sharing, scheduler singleton with no production caller, 1800s lease default, unpaginated wiki scans, retry_policy declared-but-unapplied, manual-only DR drill), and I re-fetched two of its highest-leverage external citations directly (MCP draft changelog's session removal, Cloudflare Durable Objects' single-threaded-per-object guidance) — both checked out exactly.

The one required correction: direct code inspection found the compute-isolation gap is more concrete and partly live than the report states —
- `allowed_providers` has **zero write sites anywhere in the codebase** (not just missing from `set_engine` as the report says, quoting commit 92dd60c5 — no code path anywhere sets it, so the allowlist enforcement the router correctly implements is 100% dormant in production).
- `engine_endpoint` (the `self_hosted_endpoint` BYOC route) is **write-only dead code** — `set_engine` persists it but nothing in the router ever reads it, so that "BYOC" API is a no-op today.
- `ollama-local`'s hardcoded fallback is **inert in the current single-container deploy** (no Ollama installed there, so it fails loud) but **live and armed for Tier-2/Tier-3 self-hosted deployments** the product's own tier model targets.

This sharpens rather than undermines the report's thesis — I flagged it as the one item that should be promoted from "truth conflict to resolve" to a named, file:line-cited, immediate-priority item. I explicitly noted I skipped re-routing this through Codex, since this review itself is the required opposite-provider check.

Per the task's explicit instruction, I only wrote the review file — I did not touch STATUS.md, though that row (claimed by codex-gpt5-desktop) lists "Claude reviews" as a dependency and may want updating separately now that this review exists.
