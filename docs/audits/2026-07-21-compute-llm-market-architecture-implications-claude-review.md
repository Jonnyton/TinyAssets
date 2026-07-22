# Claude Opposite-Provider Review: Compute/LLM Market Implications

**Reviewer:** Claude Sonnet via `scripts/peer_agent.py`, 2026-07-21.
**Scope:** independent source, TinyAssets design, OpenSpec, and code review.

The review is complete. Summary of what I did and found:

**Verification performed:** Read the relevant `PLAN.md` sections (Scoping Rules, Cross-Cutting Principles, Providers module, Design Decisions), all 7 cited OpenSpec capability specs in full, the actual pure-core code (`match.py`, `ceiling.py`), and the in-flight Wave 2 transport PR (#1542, unmerged). Independently re-fetched/re-searched the highest-risk external citations: 3MF's ISO/IEC 25422:2025 status, A2A 1.0's Agent Card signing, OpenRouter's curated provider-approval process, BIS's May 2025 AI training policy statement, and Vast.ai/Akash mechanics — all checked out accurate.

**Verdict: ADAPT** (not a rejection — the architecture, domain model, and market mechanisms are sound and well-grounded in actual code, not just prose). Five required fixes, all minor:
1. Run the ~12 new typed objects (`DemandIntent`, `CapabilityRequirement`, etc.) through PLAN.md's own Scoping Rules 1–2 before freezing them in OpenSpec — the report skips straight to definition.
2. State `DemandIntent`/private-payload residency in stricter Commons-first terms (host-resident by construction), not the vaguer "outside public price discovery."
3. Name the CFTC forward-contract-exclusion test explicitly (the report's whole physical-settlement design leans on it) and sharpen the BIS citation to its actual narrower trigger.
4. Fix a citation typo: `demand-side-paid-market` should be `demand-side` (that's the real capability directory).
5. Cross-reference the in-flight R2-1 identity-fail-closed work, since it and Wave 2's actor-authority hardening fix the same failure class in different files.

I skipped the standing Codex-dispatch reflex here since this task *was* the opposite-provider review — routing it to Codex would have been self-review. The default Fable peer dispatch was blocked by its spend cap; the review was rerun on Claude Sonnet and captured by the peer wrapper. The lead reconciled the review's `STATUS.md` edits and folded the five required adaptations into the initial report before publication.
