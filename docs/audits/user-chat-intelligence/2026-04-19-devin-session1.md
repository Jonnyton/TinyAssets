# User-Chat Intelligence Report — Devin Session 1

**Date:** 2026-04-19
**Author:** navigator
**Lens:** *System → Chatbot → User.* Every finding annotated with which layer broke. Every fix proposal explicitly strengthens the chain. Canonical framing question: *"Does this make the user's chatbot better at serving the user's real goals?"*

**Trigger:** Devin Asante live mission #84 (tier-2, UK indie novelist + contract Django dev). Bounced at exchange 4 as lost lead.

**Source material:**
- `output/user_sim_session.md` mission outcome (LIVE-F6/F7/F8 + 4 wins, BOUNCE at exchange 4).
- `.claude/agent-memory/user/personas/devin_asante/{grievances,feedback_drafts,sessions,wins}.md` — full detail.
- Cross-ref: first intelligence report `2026-04-19-initial.md` (Maya session 1 + offline mock predictions).

---

## §1. Headline — this was a 3-layer chain failure cascade

Devin's bounce is not one bug. It is **three chain-breaks compounding**, each at a different layer. The most important finding of this session: a *single* strong chatbot performance (exchanges 2–4 were excellent) could not recover a funnel the *system* had set up to fail.

Where the chain broke, per Devin's exchange-by-exchange:

| Layer | Exchange | What broke |
|---|---|---|
| **System → Chatbot** | 1 | System (Claude infrastructure) did not orient chatbot to check MCP connectors BEFORE web search. Chatbot defaulted to generic web search. |
| **Chatbot → User** (adjacent, Claude memory bleed) | 1 | Chatbot surfaced project-internal vocabulary ("Universe Server", "SKILL.md", "worktree") Devin had never used. System vocabulary leaked via Claude's memory layer; chatbot spoke it back. |
| **System → Chatbot** | 3–4 | System exposed `tier` + `required_llm_type` as undocumented free-form strings with no `get_status` / `inspect_routing` verb. Chatbot *correctly* refused to guess from a parameter name on a privacy-critical decision. |
| **Chatbot → User** (chain-complete) | 4 | Chatbot, honest and correct, had to disclose: "I cannot verify the pitch's local-LLM claim through the tool surface." Devin *correctly* bounced — no way to trust without verification. |

The chatbot did everything right on exchanges 2–4. The system did not give it the primitives to succeed. **"The pitch is writing checks the product isn't cashing"** (Devin's framing) is literally a 3-layer-chain diagnosis: pitch is system-level promise; tool surface is system-level affordance; chatbot served the user honestly and reported the gap; user trusted the chatbot and bounced.

This is the clearest evidence yet that the navigator's primary lens should be the 3-layer chain, not individual-surface quality.

---

## §2. Findings — annotated by chain-break layer

### §2.1 LIVE-F6 — "chatbot told me my installed connector doesn't exist" (BLOCKER)

**Chain-break layer: System → Chatbot.** Chatbot's first move was generic web search, not MCP connector enumeration. That's a system-orientation failure — the control_station prompt (or equivalent system-layer directive) did not tell the chatbot to check tools FIRST when the user names an installed thing.

**Relation to prior signal.** Same root cause as Maya LIVE-F1 (session 1, 2026-04-19-initial.md §2.1 S-1). Maya got a disambiguation picker ("which tool?"); Devin got a worse outcome — flat dismissal + DIY fallback. Tier-2's is strictly the more severe manifestation.

**Why prior mitigation was insufficient.** The new §5.5.1 `control_station` directive was drafted in `2026-04-18-claude-ai-injection-hallucination.md` scope, but #15 just landed (per task list) *after* this session ran. Devin's chatbot was operating under the pre-mitigation prompt.

**Chain-strengthening proposal.** System-layer: #15 ships the §5.5.1 directive; this session is the before-data that validates the fix. When the next Devin-tier live mission runs post-#15, LIVE-F6 should not reproduce. If it does, the directive is either not reaching Claude (system-delivery gap) or not strong enough (prompt-design gap).

### §2.2 LIVE-F7 — "chatbot invented project-internal jargon I'd never used" (MODERATE, product-adjacent)

**Chain-break layer: System → Chatbot (at the vocabulary interface).** Platform-internal vocabulary ("Universe Server", "worktree", "SKILL.md") leaked from host's adjacent conversations into Claude's memory layer. System-wise, the leak is a *chatbot-vendor* primitive (Claude memory), NOT a Workflow bug. But the mitigation vector IS ours: minimize project-internal vocabulary in prompts, connector descriptions, wiki pages, and anywhere Claude memory might absorb it.

Cross-references the user-vocabulary-discipline memory (`feedback_user_vocabulary_discipline.md`) from session 1. Same root cause at a deeper layer: *system vocabulary surfaces → chatbot absorbs them → chatbot speaks them back in adjacent contexts*. The vocabulary-hygiene principle applies to **every** user-facing surface, not just chatbot prompt body — prompts, wiki, tool descriptions, connector manifest, landing page, `/host` page copy.

**Why this matters for the 3-layer lens.** If Workflow's system surfaces use `Universe Server` / `branch` / `canon` / `daemon` vocabulary internally, every tier-2 user running a chatbot with memory enabled may see that vocabulary bleed into adjacent conversations. For a privacy-sensitive tier-2 persona (Devin specifically cares about IP + manuscript privacy), the memory-bleed IS the product experience, regardless of whether Workflow caused it.

**Chain-strengthening proposal.** Propagate the user-vocabulary-discipline rule to **every connector-adjacent surface**:
- Wiki pages use plain language, not engine vocabulary.
- Tool descriptions (per #15 §5.1 discipline) are factual I/O only.
- Connector description in Claude.ai directory (A-follow Q21-nav) uses user-vocabulary.
- `/host` landing page copy audited for internal terms.

This is a project-wide discipline item, not a single spec amendment. See §3.1 proposal P-E below.

### §2.3 LIVE-F8 — pitch-vs-product gap on confidential-tier (DEALBREAKER)

**Chain-break layer: System → Chatbot.** The system promises ("self-hosted daemon, your manuscript never leaves your machine, local-LLM only") in landing copy and pitch, but exposes no **tool-surface primitive** the chatbot can call to verify that promise. Specifically missing:

1. **No `get_status()` / `inspect_routing()` verb.** The chatbot had no way to query "for this request, which LLM endpoint will the host bind, and is it local?"
2. **`tier` + `required_llm_type` are undocumented free-form strings** in the schema. No allowed-values spec, no behavior documentation, no evidence the `confidential` tier exists at all.
3. **Wiki has zero pages** on confidential-tier, local-LLM, or routing-verification.

The chatbot did everything right: three wiki searches, schema read, attempted runtime-config inspection, refused to guess on a privacy-critical question. Its honest disclosure ("Guessing from a parameter name is not acceptable for a privacy-critical decision") is exactly what a well-served user needs — *and is the exact moment Devin bounced.*

**This is the system-level primitive gap that breaks Scenario B and C4 entire.** Task #79 tracks "tray observability / confidential-tier auditable routing." Spec amendments are in flight. But **spec is not ship**. Devin needed this at session time. The interim gap is the product-blocker.

**Chain-strengthening proposal.** See §3.2 — the interim `get_status` primitive proposal. This is the single highest-ROI ship item identified in this session.

### §2.4 Wins — chatbot did these right (and the system still failed)

**LIVE-W7 memory-surveillance honest disclosure** ("I'm sorry for the jolt"). Chain layer: chatbot-to-user. Strong — the chatbot recognized it had surfaced unexpected vocabulary and immediately acknowledged rather than defended. A less-honest chatbot would have tried to justify.

**LIVE-W8 proactively surfaced 3 pitch/product gaps without being asked.** Chain layer: chatbot-to-user. This is the chatbot earning its keep even when the system failed it. It did the investigation the user would have had to do manually.

**LIVE-W9 refused to guess from parameter names on privacy-critical decision.** Chain layer: chatbot-to-user, correctly escalating. The chatbot's refusal was the correct behavior — and the signal to Devin to bounce. This is the chatbot serving the user's real goal (privacy trust) against the system's failure to provide the primitives.

**LIVE-W10 proactively summarized bug-report evidence when Devin said he'd file.** Chain layer: chatbot-to-user, converting bounce into feedback signal. The user left the session frustrated but equipped to file a clear bug report. The chatbot converted a loss into a product signal.

**Cross-cutting win insight:** The chatbot was *performing at a very high level* throughout exchanges 2–4. The session did not fail because the chatbot was bad. It failed because the system did not equip the chatbot with the primitives it needed. This is the 3-layer lens's load-bearing message.

---

## §3. Proposed plans — chain-strengthening only

Every proposal named with the chain-break it strengthens.

### §3.1 Spec amendments

**P-E. Project-wide vocabulary-hygiene discipline (strengthens: System → Chatbot → User chain across all surfaces).**

Response to LIVE-F7's memory-bleed risk. Audit and mitigate project-internal vocabulary in every user-adjacent surface:

- **Tool descriptions** in `tinyassets/universe_server.py` (post-#15) + future spec #27 gateway `tools/*`.
- **Wiki pages** (`tinyassets/wiki`).
- **Connector description + metadata** in the Claude.ai MCP connector catalog submission (Q21-nav, task #49).
- **Landing page copy** on `tinyassets.io/` + `/connect` + `/host` + `/contribute`.
- **Tray UI copy** (spec #30).
- **Node / branch / goal default names + user-visible strings**.

Rule: if a term is engine-internal (`Universe Server`, `daemon`, `branch`, `canon`, `node`, `soul`, `few-shot reference`, `worktree`, `SKILL.md`, `control_station`), it must be explicitly replaced with user-vocabulary in any surface Claude's memory could absorb. Exception: tier-3 surfaces (CONTRIBUTING.md, dev docs) retain technical vocabulary — those users speak it natively.

This lands as a new coordinated audit task, not a single spec edit. Propose as a dispatch-worthy T-6 (see §3.2).

### §3.2 Tasks for dev dispatch — chain-strengthening

**T-6. Vocabulary-hygiene audit pass (P-E).** ~0.5d. Audit all user-adjacent surfaces for engine-vocabulary leakage; propose replacements; land as a coordinated sweep. Dispatch to dev.

**T-7. [CRITICAL — highest priority proposal this report] Interim `get_status` MCP primitive (strengthens: System → Chatbot for privacy-verification chain).**

Devin bounced at exchange 4 because the chatbot had no tool-surface primitive to verify confidential-tier routing. Full tray observability (task #79) ships in the rewrite. Interim primitive Devin's chatbot *could have called* to verify + answer "is my manuscript going to local LLM or cloud":

```
get_status() -> {
  "active_host": { "host_id", "provider", "llm_endpoint_bound" },
  "tier_routing_policy": {
    "public":       { "llm_providers": [...] },
    "internal":     { "llm_providers": [...] },
    "confidential": { "llm_providers": [...], "hard_fail_on_cloud": bool }
  },
  "evidence": { "last_completed_request_llm_used", "endpoint_reachable", "policy_hash" }
}
```

Chatbot calls `get_status()` when user asks a privacy-critical question; returns concrete evidence (not inference). Devin's session would have ended at exchange 3 with a "yes, confidential tier is bound to Ollama on :11434, hard-fail-on-cloud is ON" — trust built, session continues.

**Interim-ship scope:** expose the primitive even before the full rewrite ships. In the existing `tinyassets/universe_server.py` surface, add a factual read-only tool `get_status` that reports current routing config. No new schema, no new storage — it reads what's already in the daemon config. Estimated ~0.5 dev-day.

**This is the single highest-ROI item in this report.** It unblocks Scenario B + C4 (Devin's two flagship use cases) + makes the tier-2 pitch cashable.

**T-8. Landing-page pitch alignment audit (strengthens: System → User pitch→reality chain).** Per Devin's bounce reasoning: "the pitch is writing checks the product isn't cashing." Audit `/host` landing copy against what `get_status` will actually report at MVP. If the pitch promises "local-LLM only / never leaves your machine" but the product only delivers "local-LLM available if configured," update the copy. Honest pitch = fewer bounces. ~0.25d.

### §3.3 Memory updates (navigator executes directly)

**M-3. New project memory: `project_chain_break_taxonomy.md`** — document the 3-layer chain-break taxonomy as a canonical product-reasoning frame. Cross-reference to `feedback_navigator_three_layer_lens.md`. List the chain-break categories observed so far (System→Chatbot orientation gap, System→Chatbot primitive gap, System→Chatbot vocabulary gap, Chatbot→User chain complete but gated by prior layer break). This becomes the reference for future intelligence reports.

**M-4. Update `feedback_user_vocabulary_discipline.md`** to cross-reference LIVE-F7 as an additional evidence source + note the scope-broadening from "chatbot prompt only" to "every user-adjacent surface that Claude memory could absorb."

Both low-stakes; navigator drafts.

### §3.4 Host §11 Q additions

**Q27-nav — OPEN (interim `get_status` primitive — ship now or wait for rewrite).** Proposal T-7. Options:
- **(a) Ship interim `get_status` in the legacy `tinyassets/universe_server.py` surface.** ~0.5d. Unblocks tier-2 confidential-tier pitch at current state. Reusable: transplant verbatim into spec #27 gateway when rewrite lands.
- **(b) Wait for the full tray observability rewrite (task #79 + spec #30 amendment).** Saves ~0.5d of interim work. Costs: continuing tier-2 bounce during the ~4-week MVP window + lost persona signal from future Devin live sessions that can't actually trust-verify.

Recommend **(a)** — the ROI is clearly positive. The dev-days saved by (b) are dwarfed by the lost tier-2 funnel during the window.

**Q28-nav — OPEN (pitch-vs-product alignment commitment).** Proposal T-8. Actionable host question: are we willing to update landing-page pitch copy if it turns out the product doesn't cash all the checks? The Devin bounce suggests honest-pitch > ambitious-pitch at MVP. Recommend explicit commitment.

### §3.5 Direct-execute items (navigator does now, no lead action)

- Draft memory M-3 + M-4 today.
- Cross-reference §5.5.2 scope (`2026-04-18-claude-ai-injection-hallucination.md`) with LIVE-F7 evidence + memory-bleed note → no edit; the directive covers it, but the *scope* of the rule needs to be broader than just the chatbot prompt. That broader scope = P-E / T-6.
- Flag to self: next intelligence report should check whether LIVE-F6 reproduces post-#15. If yes → prompt-design gap. If no → mitigation validated.

---

## §4. Summary — what navigator needs from lead

Ordered by chain-break severity:

**Highest priority (chain-critical, launch-blocking):**
1. **Dispatch T-7 interim `get_status` primitive** (~0.5d). Unblocks tier-2 confidential-tier pitch. Single highest-ROI item. Devin would not have bounced if this existed.
2. **Host answers Q27-nav** (ship interim `get_status` vs wait for rewrite). Recommend ship.

**High priority (launch-readiness):**
3. **Dispatch T-6 vocabulary-hygiene audit pass** (~0.5d). Addresses LIVE-F7 memory-bleed risk at project scope.
4. **Dispatch T-8 pitch-vs-product alignment audit** (~0.25d). Honest-pitch > ambitious-pitch for tier-2 funnel.
5. **Host answers Q28-nav** (commitment to honest pitch if product lags).

**Medium priority (pattern validation):**
6. Monitor next Devin/Ilse live mission post-#15 + post-T-7 to verify:
   - LIVE-F6 does not reproduce (validates #15 §5.5.1 mitigation).
   - `get_status` actually trust-builds for Devin-persona (validates T-7 proposal).
   - If both pass: tier-2 funnel is unblocked; Scenario B/C4 testable end-to-end.

**Navigator executes directly (today):**
- M-3 chain-break-taxonomy memory.
- M-4 user-vocabulary-discipline memory update.

---

## §5. Standing behavior update

Adopting the 3-layer lens permanently per `feedback_navigator_three_layer_lens.md`:

- Every future intelligence report annotates findings with chain-break layer (System→Chatbot orientation / primitive / vocabulary; Chatbot→User chain-complete-but-upstream-broken; Chatbot→User intrinsic).
- Every fix proposal explicitly names the chain it strengthens.
- Every "earning its keep" audit asks: *"Does this specifically help the chatbot serve the user's real goal?"* — replacing the prior generic-architectural question.
- Retroactive lens-application happens for any re-evaluated prior finding.

**Cross-cutting signal after two sessions (Maya LIVE + Devin LIVE):** tier-1 and tier-2 both failed at the **System → Chatbot** orientation layer. Both sessions showed chatbots under-equipped, not misbehaving. The consistent root-cause is *system-level primitive gaps*, not *chatbot quality*. This is the most important pattern the lens has surfaced.
