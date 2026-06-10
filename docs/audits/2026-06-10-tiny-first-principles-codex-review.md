# Codex review - Tiny first-principles companions

Review date: 2026-06-10  
Reviewer: codex-gpt5-desktop  
Reviewed commit: `origin/main` `3ed9fa58` (`TINY first-principles spec + research companions`)  
Reviewed docs:

- `docs/specs/2026-06-10-tiny-first-principles-spec.md`
- `docs/specs/2026-06-10-brain-v2-research-implications.md`
- `docs/specs/2026-06-10-primitive-basis-audit.md`

## Verdict

**ADAPT - direction approved, production lock gated.**

The Brain v2 and primitive-basis companions are directionally sound and fit the
host-ratified Tiny spec: they push platform code toward substrate only, keep
ops behavior composable as branches, and make the context engine measurable
instead of another memory pile. This is enough to unblock bounded design stubs
and a read-only Brain v2 prototype over existing wiki/docs.

Do not treat this as a final vocabulary freeze or permission to ship public
multi-writer Brain v2 writes. The review leaves specific pre-build gates below.

## Required adaptations before build beyond stubs

1. **Freeze evidence snapshots for the external research claims.** The research
   companion depends on fast-moving 2026 repos and product pages. Before using
   those claims as architecture authority, record URL, retrieved timestamp,
   commit/release where available, license, and the exact claim being imported.
   Current spot-checks confirm the named projects mostly exist, but also show
   volatile metadata and some mismatches: `openclaw/openclaw` and
   `NateBJones-Projects/OB1` report `licenseInfo: other` through GitHub, while
   the spec uses more precise or permissive labels. Study-only is fine; vendoring
   or policy authority requires a source snapshot.

2. **Keep the first Brain v2 slice read-only.** The proposed first slice
   (entries schema + `assemble(lens)` read path over existing wiki content) is
   the correct blast-radius limit. Candidate writes, promotion, supersession,
   redaction, and cross-mind default views must wait until the candidate gate is
   implemented as a security boundary before consolidation.

3. **Make the eval harness a merge gate, not a later dashboard.** The spec names
   view hit-rate, tokens/query, assembly latency, fresh-session onboarding cost,
   and lens-query NDCG/MRR. The first implementation PR should include the fixed
   query set and baseline measurements before changing retrieval weights.

4. **Lock six primitive names, not every contract detail.** I approve
   Node/Edge/State/Scope/Run/Trigger as the working substrate vocabulary. Final
   contract lock still needs decisions from the audit's own open questions:
   branch values/staging, encoding-overhead budget K, live-edit versioning for
   suspended runs, message delivery laws, seal authority, and soundness-gate
   placement.

5. **Turn state-law L4 into a concrete bug before depending on merge reducers.**
   The audit correctly identifies the current right-biased merge reducer, but
   the line reference is stale: `workflow/graph_compiler.py` currently defines
   `_dict_merge` around lines 351-355, mirrored in the plugin runtime. File this
   as a targeted reducer-law task before any cross-run merge semantics depend on
   CRDT-lawful behavior.

6. **Authz and redaction must precede public accepted writes.** The companion
   correctly names multi-tenant identity/Sybil/authz and redaction as unsolved
   field gaps. For this project, those are not optional hardening items: public
   accepted entries, proposed supersessions, and commons promotion need T0/T1/T2
   authority checks, candidate quotas, PII/secret scanning, tombstone/index-purge
   behavior, and audit receipts before exposure outside a private prototype.

## Source spot-checks

These checks were freshness-stamped on 2026-06-10 while reviewing the landed
spec. They are not a full reproduction of the Fable research sweep.

- Karpathy LLM Wiki exists as a GitHub gist and presents itself as an idea file
  for LLM-built personal knowledge bases: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- MemPalace exists at `MemPalace/mempalace`; GitHub reported MIT license,
  created 2026-04-05, and 55,259 stars during review:
  https://github.com/MemPalace/mempalace
- Cloudflare Agent Memory documents keyed facts/instructions and supersession
  version chains:
  https://blog.cloudflare.com/introducing-agent-memory/
- Anthropic Contextual Retrieval documents the 67% top-20 retrieval-failure
  reduction for reranked contextual embedding + contextual BM25:
  https://www.anthropic.com/engineering/contextual-retrieval
- Hermes Agent memory docs confirm the 2,200-character `MEMORY.md` limit and
  the 80% consolidation practice:
  https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- OpenAI Apps SDK docs confirm MCP server instructions, structured tool
  results, and `structuredContent` as model-readable/widget-readable output:
  https://developers.openai.com/apps-sdk/concepts/mcp-server
  https://developers.openai.com/apps-sdk/reference

## Unblocked work

- Brain v2 design stubs.
- Read-only `assemble(lens)` prototype over existing wiki/docs.
- Schema sketches for entries, lifecycle states, recall traces, and source
  snapshots.
- Primitive vocabulary use in docs and implementation planning, provided open
  contract questions are carried as explicit TODO gates.

## Still blocked

- Public accepted Brain v2 writes.
- Cross-mind default-view promotion from chatbot-originated candidates.
- Final vocabulary/contract freeze.
- Any migration making Brain v2 canonical over STATUS/wiki/agent memories.
- Production use of merge reducers for cross-run convergence until L4 is fixed
  or restricted.

## Evidence

- `git fetch --all --prune --tags`
- `gh pr view 1303 --json number,state,mergedAt,mergeCommit,title,url,headRefName,baseRefName,latestReviews,comments`
- `mcp__workflow_live.wiki action=since changed_since=2026-06-10T06:53:12Z`
- `mcp__workflow_live.community_change_context filter_text=queue`
- `python scripts/docview.py stat docs/specs/2026-06-10-tiny-first-principles-spec.md`
- `python scripts/docview.py stat docs/specs/2026-06-10-brain-v2-research-implications.md`
- `python scripts/docview.py stat docs/specs/2026-06-10-primitive-basis-audit.md`
- `python scripts/docview.py lines --start 345 --end 365 workflow/graph_compiler.py`
- GitHub API spot checks with `gh repo view` for `MemPalace/mempalace`,
  `NousResearch/hermes-agent`, `openclaw/openclaw`, and
  `NateBJones-Projects/OB1`.
