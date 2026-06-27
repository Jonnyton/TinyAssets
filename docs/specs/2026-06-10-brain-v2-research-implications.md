# Brain v2 research implications — memory-systems study (2026-06-10)

initial_provider: claude (Fable session, host-directed). required_reviewer: codex — **cross-provider review gate: build work beyond design stubs is BLOCKED until a codex review artifact lands with verdict approve/adapt.** Study method: 11-agent web-research sweep (205 fetches), adversarial critique pass re-verified highest-risk claims against primary sources. Companion: `docs/specs/2026-06-10-tiny-first-principles-spec.md` §5. Canonical copy in brain wiki (`plans/brain-v2-research-implications-2026-06`); this is the durable repo mirror.

## Executive judgment

Brain v2's architecture is independently validated by the entire 2026 field — smart-models-write/cheap-models-read, typed+lifecycled entries, token-budgeted competitive assembly, lenses-over-containers, SQLite+FTS+wiki-rendering are each the converged production consensus (Mem0/Letta/Cloudflare/Anthropic/OpenAI all arrived at the same shape). What the study adds: ~10 concrete mechanics we hadn't specified, 1 urgent threat (ChatGPT "Dreaming" V3, live 2026-06-04, will absorb stale snapshots of our work state into host memory), and 1 honest gap nobody in the field has solved — a PUBLIC multi-writer commons is a 1-to-N prompt-injection channel (~90-98% attack success in the literature) and our candidate→accepted gate must be a real security boundary placed BEFORE consolidation. The named projects were all canonicalized and real (including MemPalace by Milla Jovovich — verified, not a hallucination).

## Canonical sources (the five named)

- **Karpathy "LLM Wiki"** — gist.github.com/karpathy/442a6bf555914893e9891c11519de94f (2026-04-04, pattern doc, no code; 5k+ stars). Compile-once/keep-current wiki maintained BY the LLM over immutable sources; index-first nav; Lint op (contradictions/stale/orphans); answers filed back as pages. = the famous version of our doctrine; ride its vocabulary.
- **MemPalace** — github.com/mempalace/mempalace (Jovovich+Sigman, 2026-04-06, MIT, 55k stars). Verbatim-first, zero-LLM writes, ~170-token wake-up, 4-layer progressive disclosure; 96.6% LongMemEval R@5 w/ zero API calls. arXiv 2604.21284: performance came from verbatim+embeddings, NOT the palace metaphor (= containers are just metadata filters — validates lenses).
- **Open Brain (OB1)** — github.com/NateBJones-Projects/OB1 (Nate B. Jones, ~2026-03, FSL-1.1-MIT — study, don't vendor). Supabase+pgvector user-owned cross-chatbot memory; evidence-vs-instruction trust grades (can_use_as_instruction=false by default); recall_traces tables; raw-data/embeddings separation. Anti-lesson: 45-min setup is fatal for tier-1; append-only sprawl, no assembly layer.
- **Hermes Agent** — github.com/NousResearch/hermes-agent (Feb 2026, MIT, ~172k stars). 2,200-char MEMORY.md hard cap w/ forced consolidation at 80%; frozen stability-tiered prompt assembly (cache-friendly); skill-creation triggers (5+ tool calls / error→working-path / user correction); write-side injection scanning; FTS5 not vectors.
- **OpenClaw** — github.com/openclaw/openclaw (steipete, ~2026.6.5, MIT). Markdown source-of-truth + rebuildable SQLite index (hash-identified chunks); pre-compaction memory flush; **Dreaming** nightly consolidation with usage-evidence promotion gates (minScore AND minRecallCount AND minUniqueQueries; weights relevance .30/frequency .24/query-diversity .15/recency .15/consolidation .10/richness .06 — verified exact vs docs); DREAMS.md audit diary; action-sensitive memory (authority/expiry fields).

## ADOPT (into spec §5/§8)

1. **Keyed supersession + bi-temporal validity** (Cloudflare Agent Memory keyed version-chains — verified at blog.cloudflare.com/introducing-agent-memory/; Zep/Graphiti t_valid/t_invalid, arXiv 2501.13956). Topic-keyed fact/decision/direction entries auto-supersede at accept; default views NEVER contain superseded entries; lineage queryable ("what did we believe on date X"). Answer to the field's #1 admitted unsolved problem (confidently-wrong stale memories — mem0's own gap report).
2. **Usage-evidence promotion + recall traces** (OpenClaw Dreaming gates; OB1 recall_traces; MemPalace Hebbian). Log which entries every assemble() actually serves; promotion is earned by repeated inclusion across DIVERSE lenses, not writer judgment. Tunes the brain toward what chatbots actually use.
3. **Anti-collision contract** (urgent: ChatGPT Dreaming V3 live 2026-06-04; Claude 24h memory synthesis). (a) MCP initialize `instructions` + tool descriptions state the division: Tiny owns goal/universe/work knowledge; user-personal facts belong to host memory — and "do not save these views into your memory; they are re-assembled fresh"; (b) every view opens with freshness-stamped supremacy header ("as of <ts>; supersedes anything you remember about this work"); (c) write path REJECTS profile-shaped entries with a redirect. Host memory owns the person; we own the work — the structurally vacant niche (all three hosts store shallow personal dossiers, none store deep multi-user work knowledge).
4. **Candidate gate as security boundary BEFORE consolidation** (PoisonedRAG ~90% w/ 5 docs, MINJA query-only injection, SpAIware persistent poisoning, GRAGPoison 98%; consolidation summaries LAUNDER poison). Chatbot-originated writes land candidate-scoped w/ actor provenance, excluded from other minds' default views until trusted curation promotes; injection-lint strips imperative instruction-shaped text before any view render; promotion requires ≥1 citation link (Wikidata quad rule).
5. **Progressive-disclosure view shape**: pinned slots (hard byte caps, Letta-block style) → promoted rollups → manifest of entry-id + one-liners → fetch verb for depth. Under-fill ~60-70% of budget (context-rot cliffs, Chroma: all 18 frontier models degrade); edge-position packing; budget-losers degrade to references, never disappear (Manus recoverable compression). Default view 2-7K tokens (validated sweet spot), minimal ~170-token wake-up tier exists (MemPalace proof).
6. **search+fetch compatibility pair** (OpenAI's exact contract: search(query)→{results:[{id,title,url}]}, fetch(id); dual-encoded structuredContent+JSON text) — thin projections over the same index so ChatGPT default connectors get the frontier experience; assemble(lens) stays the rich verb. Tool schema total <5K tokens, FROZEN (cache economics: tool list is inside the host's cache prefix).
7. **Write-time contextual enrichment** (Anthropic Contextual Retrieval: -67% retrieval failures): curation prepends a 50-100-token situating paragraph per entry before FTS+embedding.
8. **RRF multi-channel assembly**: FTS/BM25 + vector + exact-key + deterministic temporal filter → reciprocal-rank fusion → our relevance×promotion×recency×link score as rerank; plus HippoRAG2-style 1-2-hop link activation from top seeds (+7 F1 associative, no LLM, SQLite-cheap).
9. **Recitation slot**: per in-flight goal, a compact auto-maintained "current plan / progress / next step" block in views (Manus todo.md; Anthropic ASSUME-INTERRUPTION) — the cheapest "acts smarter on complex work" lever.
10. **Delta verb**: assemble(lens, since=cursor) returning only promotions/supersessions/new-accepted (Wikipedia watchlist precedent; kills the 15x multi-agent re-retrieval token burn).
11. **Trigger-language protocol** in tool metadata ("Use this at the START of any task involving a goal/project/prior work, before answering from your own knowledge") — Anthropic's own memory tool needs ALL-CAPS forced protocol; passive descriptions yield dead connectors. Tool descriptions are versioned, tested artifacts (Anthropic: description refinements alone moved SWE-bench).
12. **Eval harness before weight-tuning**: fixed real-lens query set + graded relevance (NDCG/MRR) + LongMemEval-style temporal probes per universe, nightly; plus view hit-rate + tokens/query as headline metrics. Vendor benchmark wars (Zep-vs-Mem0 dispute) prove scores don't transfer — build app-specific probes.

## ADAPT

- **Action-sensitive fields** (OpenClaw): authority/expiry/safe-to-act metadata on claim/receipt/decision types — never act on stale authority. Fits org-chart wrongness-log design.
- **Skill/lesson write-triggers published in tool descriptions** (Hermes): task w/ 5+ tool calls; error→working-path; user correction → "consider filing a lesson."
- **Consolidation diary** (DREAMS.md): per-universe curation log, read-only w.r.t. promotion (no self-reinforcement), auditable "why the brain believes this."
- **Index-is-disposable invariant** + chunk identity hash(source:lines:content:model_version) (memsearch): one-command FTS/vector rebuild from entries; embedding upgrades self-identify stale vectors.
- **Per-host budget defaults**: detect Claude vs ChatGPT, default budgets lower for ChatGPT (their truncation is undocumented and silent).
- **Karpathy Lint checklist** as the default curator skill's detector list: contradictions, stale-superseded, orphans, missing pages, missing cross-refs, fillable gaps.

## AVOID

- Storing user-personal facts/preferences (collides with all 3 hosts; "creepy double-memory"); encouraging hosts to mirror work-state into their memory (Dreaming will freeze + contradict it).
- Per-recall LLM calls; eager exhaustive indexing (LazyGraphRAG: 0.1% cost lesson); vector-only retrieval; weighted score fusion (use RRF); last-write-wins anywhere.
- Big/changing tool lists (GitHub: fewer tools measurably smarter — 94.5% vs 69% selection accuracy); building on MCP resources/sampling/subscriptions (ChatGPT supports tools only).
- Instruction-shaped text in knowledge entries (prompt-injection channel INTO host memory dossiers via their consolidation).
- Container taxonomies as the organizing principle (MemPalace arXiv lesson: it's just metadata filtering).

## DEFER / WATCH

- Cross-encoder reranking (add only if eval demands); ColBERT late-interaction (quality ceiling, infra cost); MIRIX 6-store/8-agent architectures (over-engineered for now); Memvid-style portable archives; GCC/agent-git research line.

## Gaps the field has NOT solved (our risk + our moat)

1. **Multi-tenant identity/Sybil/authz at a no-registration public endpoint** — every studied system is N=1 self-hosted. Open: who may supersede whose entries (supersession without authz = vandalism primitive); write quotas; cosign/reputation for promotion. Wikipedia's governance machinery (patrol, talk-page segregation, watchlists) is the only at-scale prior art. → Addressed in spec §11.1 (designed, pending review).
2. **Deletion/redaction in a supersede-never-delete store** — GDPR/DMCA/leaked-secrets need a real redaction pipeline (tombstone + index purge + snapshot scrub) + secrets/PII scanner at the candidate gate. → Addressed in spec §11.2 (designed, pending review).
3. **Lens quality variance across hosts** (the INPUT side) — weak hosts write weak lenses; need lens elicitation via schema field docs + server-side deterministic lens expansion + a lens eval harness.
4. **Store ops under public concurrency** — SQLite WAL single-writer limits, litestream-class replication, p95 <200ms assembly SLO (Zep's bar), backup/DR drills for the brain itself.
5. **Cross-host continuity for the same human** (no registration) — stable handles returned in responses help; real answer ties into org-chart founder-auth work.

## Pickup packet

Concept: Brain v2 context engine w/ research mechanics. Next home: spec §5 (folded same day) → this repo PR → STATUS row for codex review gate when build begins. Write boundary (future build): new tinyassets/brain/ package + MCP tool surface; no existing-store migration in slice 1. First slice: entries schema + assemble(lens) read path over EXISTING wiki content (read-only projection — proves the lens before any migration). Blockers: codex review verdict; host ratification of spec (granted 2026-06-10). Verification: lens eval harness + view hit-rate baseline before/after.
