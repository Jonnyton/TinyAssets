---
title: Per-User Intent History Substrate
date: 2026-05-07
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 585
wiki_source: pages/patch-requests/pr-074-pr-074-per-user-intent-history-substrate-hawaii-swimsuit-pro.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#retrieval-and-memory
  - PLAN.md#api-and-mcp-interface
  - PLAN.md#multi-user-evolutionary-design
  - docs/design-notes/2026-04-18-full-platform-architecture.md#20-chatbot-builder-behaviors
---

# Per-User Intent History Substrate

## 1. Recommendation Summary

Do not add a platform-owned per-user intent-history database or a new
user-facing MCP action for PR-074. The smallest useful design is a layered
intent-evidence substrate:

1. Chatbot-native memory remains the default place for per-user intent
   preferences.
2. Local-app users may optionally maintain a host-resident private intent
   journal for portability, audit, and explicit user inspection.
3. The public commons stores only generalizable intent-disambiguation rubrics,
   not individual users' histories.
4. Workflow runtime surfaces should later expose existing observable facts
   through existing context/status shapes, not through an `intent_history`
   primitive.

This handles the "Hawaii swimsuit problem": the same literal prompt can imply
different right actions for different people. One user asking about "Hawaii"
may mean "find swimwear I like"; another may mean "avoid swimwear because this
is a work trip"; a third may mean "book family-safe beach logistics." The
platform should help the chatbot ground that distinction without centralizing a
private behavioral profile.

## 2. Existing Decisions This Must Preserve

The full-platform architecture already resolved Q9 against platform-stored
per-user fulfillment preferences:

- Per-user preferences live in the chatbot provider's native memory layer.
- Workflow may expose observable facts, such as prior request decisions,
  registered hosts, and open bids.
- Workflow may hint that a signal is memory-worthy, but it cannot force a
  chatbot memory write.
- Cross-chatbot preference sync is not a launch requirement.

PR-074 should be treated as a refinement of that decision, not a reversal. The
new substrate can preserve intent evidence where the user explicitly controls
the storage boundary, but it must not quietly recreate `user_fulfillment_prefs`
under a different name.

## 3. Layered Shape

### Layer A: Chatbot-Native Intent Memory

This is the default path for browser-only users and the only path needed for
many cases. The chatbot records high-confidence, user-benefiting lessons in its
own memory system, using its provider-specific controls and deletion semantics.

Good entries are small behavioral facts, not transcripts:

```text
When this user asks for travel packing help, assume they want practical,
weather-aware packing, not shopping recommendations, unless they mention buying.
```

Bad entries are broad surveillance or sensitive inference:

```text
User searched Hawaii swimwear on 2026-05-07 and probably has body-image anxiety.
```

Workflow's role is prompt and rubric design: teach the chatbot to ask one
clarifying question when the same utterance maps to materially different
actions, and to remember only user-approved, useful generalizations.

### Layer B: Host-Resident Private Intent Journal

Local-app users can opt into a private journal stored on their machine. This is
not a platform database and not public commons content. It is host-resident data
with explicit export/delete controls, consistent with the commons-first rule.

Suggested record shape:

```yaml
id: intent_obs_01J...
created_at: "2026-05-07T00:00:00Z"
source:
  kind: user_confirmed | observed_choice | correction | imported_chatbot_memory
  evidence_ref: local://workflow/intent-evidence/...
scope:
  domain: travel
  task_class: packing_advice
statement: >
  For Hawaii travel, this user usually wants packing guidance before shopping.
confidence: 0.72
expires_at: "2026-11-07T00:00:00Z"
visibility: host_private
redaction:
  raw_transcript_stored: false
  sensitive_inference: false
```

The journal stores compact observations with provenance and expiry. It should
avoid raw chat logs by default. If the user wants to carry preferences between
Claude, ChatGPT, a local shell, and a tray daemon, the journal becomes an
explicit import/export artifact rather than a hidden cross-provider profile.

### Layer C: Public Commons Rubrics

The commons should learn reusable disambiguation patterns, not users' private
answers. A public page or node can say:

- "Travel packing requests often need a trip-purpose clarification."
- "Shopping suggestions require buying intent, budget, size/style constraints,
  and consent to browse products."
- "If the prompt is ambiguous between advice, purchase, itinerary, and private
  personal context, ask before acting."

This makes the community better at handling the Hawaii example without
centralizing anyone's history.

### Layer D: Runtime Observable Facts

Workflow can later expose facts it already owns, such as a user's prior
Workflow requests, registered hosts, pending bids, and completed run classes.
Those facts should appear through existing context/status surfaces when needed.
They should not become a new top-level `intent_history` action.

The distinction matters:

- "User previously selected `self_host_prompt` for private invoice workflows"
  is an observable Workflow fact.
- "User likes modest swimwear" is a private preference and belongs in chatbot
  memory or a host-resident journal only if the user chooses that.

## 4. Non-Goals

- No central platform profile table for individual intent history.
- No raw transcript ingestion into Workflow's public or cloud storage.
- No automatic cross-provider sync without an explicit user-owned export/import
  artifact.
- No new MCP action in v1. Chatbots should compose from memory, existing
  observable facts, and commons rubrics.
- No policy taxonomy for all sensitive intent classes. Community rubrics evolve
  that layer.

## 5. Privacy And Abuse Constraints

Intent history is high-risk because it can encode beliefs, health status,
financial posture, sexuality, family structure, and other sensitive facts even
when the original prompt looked mundane. Any future implementation must satisfy:

- User inspection: the user can see the compact observation before it is stored.
- User correction: a user correction should override older observations.
- Expiry: observations decay; stale intent guesses are worse than no memory.
- Minimum evidence: "model inferred this" is weaker than "user confirmed this."
- No dark personalization: intent history should help complete the user's task,
  not steer engagement, upsell, or ranking in ways the user cannot inspect.
- Provider separation: Claude memory, ChatGPT memory, local journals, and
  Workflow facts have different owners and deletion models. Do not blur them.

## 6. Suggested Future Implementation Slices

### Slice 1: Commons Rubric Only

Write a public wiki/page template for ambiguous-prompt handling. This is
community-buildable and requires no runtime code.

Acceptance:

- The rubric includes examples where the same prompt maps to different actions.
- The rubric tells the chatbot when to ask a clarifying question.
- The rubric says what is safe to remember and what is not.

### Slice 2: Local Intent Journal Spec

Specify a host-resident YAML/SQLite journal with export/delete controls. This
can be built only after the host-resident private data design is accepted for
the relevant local-app surface.

Acceptance:

- Records are compact observations, not transcripts.
- Every record has provenance, confidence, and expiry.
- The user can inspect, delete, and export records.
- No cloud/platform write path exists.

### Slice 3: Existing-Facts Context Snapshot

Extend an existing user/status/context response, if one exists at that point,
to include Workflow-owned observable facts relevant to a current decision. Do
not add this until a concrete chatbot flow proves that composing from existing
tools is fragile.

Acceptance:

- The response contains only facts Workflow already owns.
- It excludes inferred preferences.
- It is read-only.
- It is covered by auth/RLS or the host-private boundary appropriate to the
  facts being returned.

## 7. Open Questions

1. Should a host-resident journal be provider-neutral from day one, or should
   each chatbot provider import/export its own small memory summary?
2. What expiry defaults are acceptable by domain? Travel preferences may decay
   quickly; accessibility needs may need a different cadence and stronger user
   confirmation.
3. Should sensitive domains require an explicit "remember this" phrase, or is a
   provider-native memory confirmation enough?
4. Which existing context/status surface is the right place for Workflow-owned
   observable facts once a concrete flow needs them?

## 8. Gate Ladder

Design-only acceptance for PR-074:

- Proposed note exists under `docs/design-notes/proposed/`.
- The note preserves the prior Q9 no-platform-preferences decision.
- The note identifies the smallest useful change and avoids runtime code.
- The note names future slices and privacy constraints.

Implementation acceptance for any later runtime branch:

- Opposite-family review before build, because the design touches per-user
  memory and privacy boundaries.
- Focused tests for auth/RLS or host-private file boundaries.
- Rendered chatbot-surface verification for any public MCP behavior change.
- Post-fix clean-use evidence or a `STATUS.md` watch item if no real-user use is
  visible yet.

## 9. Classification

PR-074 is a project-design request. It is not a bug and should not make runtime
code changes in this branch.
