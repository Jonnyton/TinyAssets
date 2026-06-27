---
status: active
---

# Shared-Account UX for Tier-2 Hosts

**Date:** 2026-04-19 (promoted to ACTIVE 2026-04-19 post-P0 probe — second evidence point acquired)
**Author:** navigator
**Lens:** *Does this give the chatbot more leverage to serve the user's manifested will?* — every recommendation passes through this question.
**Status:** **ACTIVE DESIGN NOTE** (promoted from "future candidate"). Two live evidence points within 24 hours justify promotion; see §1a. One §11 follow-up Q surfaced in §6 for host call.

**Evidence points:**

1. **Devin Asante LIVE Session 2** (`docs/audits/user-chat-intelligence/2026-04-19-devin-session-2.md` §6) — chatbot truthfully said "this account is Jonathan's, not Devin's." Handled gracefully via in-conversation reset. First clear live signal that tier-2 households share accounts.
2. **P0 Uptime Canary Probe** (`docs/audits/user-chat-intelligence/2026-04-19-p0-uptime-canary-probe.md` §2.2 #P2) — bare-curious-user persona in a **fresh chat**, no persona framing, no history invoked. Chatbot claimed: *"Found the thread — you started the deep-space-population remix earlier today but the server was down and you only got as far as a draft spec... pick up from the scope_framer node you began speccing."* This is pure fabrication — there was no thread, no earlier work, no remix. Claude's memory layer cross-wired context from another session (host workflow or prior user-sim run) into the bare-user chat. **Failure mode: the chatbot offered vocabulary the user never used (`remix`, `scope_framer node`) and claimed history the user never lived.** Same shape as Devin Session 2 — shared-account context bleed — but this time the mismatch was NOT gracefully disclosed; it was asserted as fact.

**Why this promotes to active (not just "second signal logged"):**

- Two incidents in 24 hours is a rate signal, not a noise signal. The probability of cross-session context bleed across independent sessions is higher than a one-off.
- The second incident is *strictly worse behavior* than the first. Devin Session 2 disclosed the mismatch honestly. The P0 probe asserted fabricated history as fact — a Hard Rule 8 violation ("fail loudly, never silently"). The problem is getting worse, not converging.
- The second incident entangles shared-account hallucination with **degraded-mode fabrication** (see companion note: `docs/design-notes/2026-04-19-degraded-mode-fabrication.md`). When the MCP tool is down, the chatbot compensates by fabricating from cross-session memory — two separate gaps reinforcing each other.

---

## §1. The shape of the problem

Three concrete shapes the chatbot encounters at tier-2:

1. **Spouse/partner share.** One Claude.ai account, two users. Person A (the account holder) has been using TinyAssets for a fantasy novel; Person B (the partner) wants to draft a recipe-tracker. Person B asks the chatbot "summon a daemon for my recipe tracker" — chatbot has memory of Person A's fantasy work but no signal yet that Person B is a different person with a different goal.

2. **Collaboration share.** Indie-dev contractor sets up TinyAssets on a client's account. Contractor and client both use it. The persona switching is task-shaped, not identity-shaped: same person, two hats.

3. **Editor/co-author share.** A novelist uses TinyAssets for their manuscript; their human editor occasionally drives the same account to leave editorial notes. Two people with overlapping but distinct goals.

What makes these *tier-2-specific* (vs tier-1): tier-2 hosts have installed the daemon, have local file access, often have privacy-critical expectations (manuscript IP, recipe-tracker private data, editorial drafts not yet public). The cost of the chatbot getting persona/account context wrong is materially higher than tier-1's "type the prompt again."

What makes it *not solvable by Claude memory alone*: Claude memory is one-account-scoped by Claude.ai's design. There is no signal at the memory layer that distinguishes "what Person A did yesterday" from "what Person B did yesterday." The only signal that exists is the chat content itself — what the user just typed, in this conversation.

---

## §2. Through the chatbot-leverage lens

The lens question: *does this give the chatbot more leverage to serve the user's manifested will?*

Three failure modes, each a different layer of leverage failure:

| Failure mode | What broke | Why the chatbot couldn't recover |
|---|---|---|
| **Cross-persona context bleed** (Person B's recipe-tracker request gets fantasy-novel context surfaced) | The chatbot had no signal that the persona changed. It served Person A's manifested will, not Person B's. | No primitive existed to ask "is this the same person as last time?" The chatbot guessed, and guessed wrong. |
| **Defensive over-disclosure** (chatbot asks "are you really {persona name}?" before every prompt) | Chatbot defaults to safety; user experiences interrogation. The user's manifested will (do the work) is buried under "verify identity first." | No primitive distinguishes "ambiguous mismatch" from "load-bearing mismatch." Everything is treated as load-bearing. |
| **Silent wrong-persona action** (chatbot does what Person A would have wanted, not what Person B asked for) | Chatbot serves *historical* manifested will instead of *current* manifested will. | The signal that this prompt diverges from prior context exists in the prompt itself, but the chatbot has no way to surface that divergence as a checkable hypothesis. |

The Devin Session 2 outcome avoided all three by *honestly disclosing the mismatch and offering a reset path*. That's the right shape for a one-off; it's not the right shape for a household using TinyAssets weekly. We need primitives that let the chatbot handle this gracefully without re-prompting the household every session.

**Lens-applied implication.** Every recommendation in §3-§5 should be a primitive that *increases the chatbot's leverage to interpret which user's will is currently being manifested* — not a primitive that *forces the user to declare themselves*. Declaration is friction; inference from signal is leverage.

---

## §3. The friction curve — what we should and should not ask

Three response shapes the chatbot can take when it detects a possible shared-account signal:

| Shape | Description | When it's right |
|---|---|---|
| **Silent do-what-I-said** | Chatbot just acts on the new prompt; ignores prior context if it doesn't fit. | When the prompt is self-contained and the prior context isn't load-bearing for the new task. (Devin's "recipe tracker" prompt has zero connection to Person A's fantasy novel — silent action is correct.) |
| **Narrate-and-act** | Chatbot acts but explicitly says "I'm starting fresh on this — your prior work on X is still there if you want me to switch." | When prior context *might* be relevant but the current prompt suggests it isn't. Surfaces the prior context as recoverable without forcing a choice. |
| **Ask-before-act** | Chatbot asks "Did you mean to continue Alex's manuscript work, or start something new?" | When the current prompt is genuinely ambiguous — references "the manuscript" without specifying which one, mentions something that could be either Person A's or Person B's project. |

**Friction increases left-to-right.** Silent action is zero friction; narrate-and-act adds one sentence; ask-before-act blocks the user.

**The shape currently dominant** (per Devin Session 2 evidence) is closer to ask-before-act-when-uncertain. That's the safe default for a one-off live mission. **For a household using TinyAssets weekly, the safe default should be narrate-and-act**, falling back to ask-before-act only when ambiguity is genuine.

**Lens-applied recommendation.** The chatbot needs a primitive that surfaces *which prior context is relevant to the current prompt* as structured evidence — same shape as the self-auditing-tools pattern (`docs/design-notes/2026-04-19-self-auditing-tools.md`). Then the chatbot can decide which response shape to use:

- High overlap with prior persona's context → consider ask-before-act.
- Low overlap → narrate-and-act, surface the prior context as "still here if you want it."
- Zero overlap (recipe vs fantasy) → silent do-what-I-said.

The decision is the chatbot's; the primitive just gives it the evidence to decide well.

---

## §4. The chatbot's job when it detects a shared-account signal

Three things the chatbot's job *is*:

1. **Notice the divergence without making it the conversation.** The signal that "this might be a different person" comes from the prompt itself — vocabulary mismatch, project-domain mismatch, framing-style mismatch. The chatbot's job is to *register* the divergence and *route* its response shape accordingly, not to *interrogate* the user about it.

2. **Preserve recoverability.** Whatever the chatbot does next, the prior persona's context must remain accessible. If Person B starts a recipe tracker, Person A's fantasy work must still be one prompt away ("can I see what Alex was working on?"). Recoverability removes the "did the chatbot just delete my novel?" anxiety.

3. **Surface its inference, gracefully.** Per the self-auditing-tools pattern, the chatbot should *narrate* what it inferred and *what would change its inference*. "I'm assuming this is a fresh project — say 'continue the manuscript' if you meant to pick up where Alex left off." One sentence; user can correct or proceed.

Three things the chatbot's job *is not*:

1. **It is not identity verification.** TinyAssets is not authenticating users. Whether Person A or Person B is at the keyboard is the chatbot's *contextual inference*, not the platform's *security check*. (Privacy at write-time is the per-piece chatbot-judged primitive — see `project_privacy_per_piece_chatbot_judged.md` — it doesn't depend on persona attribution being right.)
2. **It is not session management.** The chatbot doesn't run multi-user sessions. There's one Claude.ai session; the chatbot adapts to whoever is typing at any given moment.
3. **It is not invitation/onboarding orchestration.** If Person B is going to be a regular user, eventually they'll want their own context surface — but that's tier-1 onboarding for Person B (their own Claude.ai account, their own daemon), not a tier-2 multi-user feature.

**Lens-applied summary.** The chatbot's job is *interpretation*, not *enforcement*. The primitives needed are *evidence surfaces* (what does the prompt tell me about who's typing?), not *gatekeeping mechanics* (block until verified).

---

## §5. Reset/invite flows — the friction curve

When persona signals diverge enough that the chatbot decides ask-before-act is warranted, what are the flows?

### 5.1 In-conversation reset (zero-friction, zero-platform)

Chatbot says: "I'm noticing this prompt looks different from your prior work — want me to start fresh, or pick up where Alex left off?" User picks; chatbot proceeds. **No platform involvement.** No session, no account, no profile.

This is the shape Devin Session 2 used. It works for one-off persona mismatches. It does NOT scale to "Person B uses TinyAssets weekly" because Person B re-encounters the question every session.

### 5.2 Persistent persona-tag (low-friction, light platform involvement)

Chatbot maintains a per-Claude.ai-session tag like `current_persona_hint: "Person B"` that *the chatbot itself sets* based on conversational signal. TinyAssets' API exposes a `set_session_persona_hint(name)` tool the chatbot can call when it has high confidence. Subsequent prompts in the same session route through the persona tag.

**Platform's role:** expose the tool. Persistence is per-Claude.ai-session, not cross-session. No identity claim — just a hint the chatbot is using to organize its own context.

**Cost:** ~0.5 dev-day to add the MCP tool. Low. Zero schema impact (the hint lives in chatbot-side memory, not in `daemon_definitions` or any user-identity table).

### 5.3 Cross-session collaborator surface (higher-friction, requires schema)

If Person B becomes a regular user, eventually they'll want their own TinyAssets context — separate canon, separate daemon preferences, separate node-bid history. The right answer is **Person B opens their own Claude.ai account**. That's a tier-1 onboarding event for them.

If Person B *can't* (shared-household account, can't justify a second seat), the platform does NOT need to invent a multi-user-per-account primitive today. The cost (schema for "sub-personas under a single Claude.ai account") is high; the benefit is narrow (households who can't get a second account *and* care enough to need separate context); and it conflicts with the "platform doesn't know who you are" privacy posture.

**Recommendation: don't build this today.** When a household hits the friction of "I want my own context but can't get my own account," that's a signal to re-evaluate — but it's not in MVP scope and forcing it earlier creates a multi-user-account architecture before we've validated single-user works at scale.

### 5.4 The friction curve, summary

| Tier of intervention | Friction | Platform cost | When to use |
|---|---|---|---|
| In-conversation reset (5.1) | Zero | Zero | Default. Always available. Works for one-off persona mismatches. |
| Persistent persona-hint (5.2) | Low | ~0.5 dev-day | When the chatbot detects the mismatch is repeating across prompts in a session and would benefit from caching its inference. |
| Cross-session collaborator surface (5.3) | High | High (schema + auth changes) | **Not for MVP.** Build only when shared-household friction surfaces empirically. |

---

## §6. The §11 architectural follow-up question

Surfacing one host-call ambiguity for the next §11 host-Q digest update.

### Q-shared-1 — Per-Claude.ai-session persona-hint tool: ship in MVP or defer?

**Framing.** §5.2 proposes a `set_session_persona_hint(name)` MCP tool — a low-cost way for the chatbot to organize its own context across prompts within a session. The cost is ~0.5 dev-day and zero schema impact. The question is whether shared-account UX is load-bearing enough to justify shipping this primitive in MVP, or whether the in-conversation reset (§5.1) is sufficient for MVP and the persona-hint tool waits for empirical signal.

**Choices:**
- **(a) Ship in MVP.** Tier-2 hosts get cleaner repeat-session UX from day one. Cost: ~0.5 dev-day. Cleanly maps to the chatbot-leverage lens — the tool is *evidence-surface*, not *identity-enforcement*.
- **(b) Defer until empirical signal.** In-conversation reset (§5.1) handles one-off persona mismatches with zero platform cost. If shared-household friction emerges in tier-2 user-sim missions or live tier-2 traffic, ship then. Saves ~0.5 dev-day pre-MVP; risks one persistent friction point in early tier-2 retention.

**Recommendation (REVISED post-P0 probe): (a) ship in MVP.** Recommendation flipped from "defer" after second evidence point. Two reasons:

1. **Empirical signal is now two-instance, not single-instance.** The P0 probe showed the pattern recurring in a *fresh chat with a bare-user persona* — conditions that are strictly lower-signal than Devin Session 2 yet still produced a hallucinated-history assertion. That's a stronger signal than two matched-persona incidents would have been. The "wait for second signal" gate documented in the original recommendation has cleared.

2. **The P0 probe showed the failure mode is not self-healing.** Devin Session 2's graceful disclosure was the chatbot's good behavior; the P0 probe's asserted-fabrication was strictly worse. The in-conversation reset (§5.1) depends on the chatbot *choosing* to disclose the mismatch. When it doesn't (P0 probe), there is no recovery surface. A persistent persona-hint tool gives the chatbot an evidence surface it can reach for when conversational signal is ambiguous — converting a 50/50 disclosure gamble into structured inference.

**Revised cost/benefit:**
- Ship cost: ~0.5 dev-day (unchanged).
- Not-ship cost: one persistent friction point + at least one load-bearing trust-erosion mode where fabrication gets asserted as fact. Worse than documented.

Recommendation surfaces to host via next §11 host-Q digest update as HIGH confidence (was previously MEDIUM-defer).

---

## §7. What this note does NOT decide

- **Whether to add a `current_persona_hint` field to any platform-side schema** — explicitly out of scope; per §4-§5, the chatbot's contextual inference is not platform identity state.
- **Whether Person B's data should be visibility-isolated from Person A's** — that's the per-piece chatbot-judged privacy primitive (`project_privacy_per_piece_chatbot_judged.md`), unchanged by anything here.
- **What the TinyAssets platform does about sharing/family-account economics** (one paid host slot serving multiple users, etc.) — pure product question, not UX.
- **The exact wording of the chatbot's narrate-and-act sentences** — that's a copy iteration job for the next user-sim live test, not a design-note call.

These would each become real questions if we shipped §5.2 (the persona-hint tool) — listing them so future-us doesn't think they're forgotten.

---

## §8. Summary

- Tier-2 households share accounts. Devin Session 2 surfaced this empirically and the chatbot handled it well via in-conversation reset.
- The chatbot's job is *interpretation*, not *enforcement*. Primitives needed are *evidence surfaces*, not *gatekeeping mechanics*.
- Three response shapes (silent / narrate-and-act / ask-before-act) map to a friction curve. Default for households using TinyAssets weekly should be narrate-and-act, with ask-before-act reserved for genuine ambiguity.
- Three intervention tiers (in-conversation reset / persona-hint tool / cross-session collaborator surface). MVP uses tier 1; tier 2 is a small follow-up if signal supports it; tier 3 is post-MVP and probably not needed.
- One §11 host-call surfaced (Q-shared-1): ship persona-hint MVP or defer? Recommend defer until empirical signal beyond Devin Session 2.
- Cost for MVP: zero. Cost for the optional persona-hint follow-up: ~0.5 dev-day, zero schema impact, ship-anytime.

The load-bearing claim: **we don't need a multi-user feature; we need a chatbot-leverage primitive for repeat-session persona inference, and only if/when empirical signal calls for it.**
