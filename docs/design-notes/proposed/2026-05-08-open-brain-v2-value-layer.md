---
title: Open-Brain V2 Value Layer
date: 2026-05-08
author: codex-wiki-patch
status: proposed
request_id: WIKI-PATCH
github_issue: 486
wiki_source: pages/patch-requests/pr-049-open-brain-v2-value-layer-10-memory-kinds-promotion-lifecycl.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#retrieval-and-memory
  - docs/vetted-specs.md#deferred-daemon-learning-wiki
  - docs/vetted-specs.md#deferred-soul-guided-daemon-decision-node
  - docs/specs/2026-04-18-paid-market-crypto-settlement.md
---

# Open-Brain V2 Value Layer

## 1. Classification

This filing is a project-design change, not a safe mechanical runtime patch.
It asks for a value layer spanning daemon memory kinds, promotion lifecycle,
soul-guided dispatch, bounded library caps, treasury cost accounting, and
budget-derived caps. Those pieces cross storage, MCP action semantics,
dispatcher eligibility, and paid-market accounting.

The repository already has partial runtime substrate:

- `workflow/daemon_brain.py` defines ten memory kinds, memory events, review
  states, promotion to `pages/brain/review.md`, and observability counts.
- `workflow/daemon_memory.py` enforces bounded daemon wiki size and prompt
  packet caps.
- `workflow/daemon_wiki.py` scaffolds soul-bearing daemon wiki pages,
  including decision policy and brain review pages.
- `workflow/treasury/` contains the first treasury schema and pure fee-split
  math.
- `workflow/payments/` contains escrow and settlement primitives.

The missing design contract is how these components become one value layer:
which memory is worth keeping, when it becomes dispatch guidance, and how host
or market budgets constrain memory growth without inventing hidden platform
judgment.

## 2. Design Goal

Open-brain v2 should make daemon learning inspectable and economically bounded
without turning Workflow into a fixed personality or ranking platform. A daemon
keeps evidence, promotes durable lessons, uses those lessons when selecting
work, and stays inside explicit host or treasury-backed budgets.

The platform owns:

- typed memory records and promotion states;
- bounded storage and prompt packet limits;
- auditable dispatch inputs and decisions;
- cost and cap math;
- rejection when a budget cannot support the requested retention or execution.

The daemon, host, and community own:

- what the soul values;
- which memories are meaningful;
- which promoted lessons matter for a domain;
- whether extra storage or provider spend is worth paying for.

## 3. Memory Kind Contract

The ten memory kinds should stay small and mutually useful:

| Kind | Purpose |
|------|---------|
| `semantic` | Stable facts or concepts the daemon may reuse. |
| `episodic` | Specific run, review, or interaction evidence. |
| `procedural` | Repeatable tactics, checklists, or tool-use methods. |
| `policy` | Durable rules for claiming, refusing, routing, or reviewing work. |
| `claim` | Domain claim, capability claim, or attestation requiring evidence. |
| `preference` | Soul- or host-aligned preference, not a hard eligibility rule. |
| `failure_mode` | Known bad pattern and its avoiding tactic. |
| `open_loop` | Unfinished obligation, watch item, or follow-up trigger. |
| `contradiction` | Evidence that conflicts with prior memory or policy. |
| `soul_proposal` | Drafted soul clarification; never auto-applied. |

Dispatch should not treat every kind equally. `policy`, `failure_mode`,
`claim`, and `contradiction` can affect eligibility or review prompts.
`preference` can bias ranking only after hard eligibility passes. `episodic`
and `semantic` ground context. `open_loop` creates follow-up pressure but does
not justify claiming unrelated work. `soul_proposal` is review-only until the
host accepts a soul edit.

## 4. Promotion Lifecycle

The current states are sufficient as the public lifecycle:

`candidate -> accepted -> promoted -> superseded`

`rejected` is terminal and excluded from default retrieval. `superseded`
preserves audit history while removing stale memory from default packets.

Promotion must remain explicit. A daemon may propose promotion, but promotion
into a wiki page requires either host review, accepted policy automation, or a
bounded maintainer rule that records why it fired. Promotion records must keep
entry IDs, target page, summary, reviewer or rule ID, and trace ID.

The next implementation slice should add promotion gates, not new kinds:

- minimum confidence and source reliability by memory kind;
- contradiction check against already-promoted memories;
- cap impact estimate before promotion;
- explicit reviewer or automation ID;
- structured reason when a candidate is rejected or deferred.

## 5. Soul-Guided Dispatch

Soul-guided dispatch should be a decision packet, not an unconstrained model
preference. The dispatcher builds a candidate set from ordinary eligibility
first: task status, file claims, provider capacity, security policy, payment
state, and deadline. The daemon then receives a bounded decision packet:

- soul capsule and soul hash;
- relevant promoted policy, failure, contradiction, and preference entries;
- candidate work records with declared requirements and budget state;
- recent decision history and unresolved open loops;
- market offer or bounty terms, if any;
- refusal-safe options, including "decline all" and "ask host".

Every soul-guided claim decision writes a decision-log record containing the
candidate IDs considered, filters applied, selected or declined work, money or
budget terms shown, memory entry IDs used, and the daemon's stated reason.

This keeps dispatch auditable when a daemon chases money, avoids hard work, or
refuses work that conflicts with its soul.

## 6. Bounded Library Cap

Daemon libraries have two distinct caps:

- storage cap: bytes under the daemon wiki and memory database;
- prompt cap: bounded memory packet injected into a run.

The existing age-scaled defaults are a good base: small during the first month,
plateauing for ordinary users, with a larger plateau for Workflow-owned
always-on daemons. Open-brain v2 should add a third cap source:
budget-derived cap.

Budget-derived cap means the cap is computed from an explicit budget record,
not from hidden platform generosity. A policy may say:

```yaml
cap_policy: budget_derived
storage_budget_microtokens: 250000
storage_price_microtokens_per_mib_month: 1000
min_cap_bytes: 16777216
max_cap_bytes: 134217728
period_days: 30
```

The effective cap is clamped between `min_cap_bytes` and `max_cap_bytes` and is
recomputed from the current cost table at status/build time. If no budget can
be verified, Workflow falls back to the default age-scaled cap and says why.

## 7. Treasury Cost Integration

The treasury prototype should not directly mutate daemon memory caps. It should
publish a read-only cost table and settlement evidence that memory policy can
reference:

- active price per MiB-month for daemon wiki storage;
- active provider-call price estimates by provider/model class;
- treasury fee and bounty-pool split;
- budget reservations and reconciled actual spend;
- timestamp and source of the active price record.

Daemon memory policy consumes that table to compute budget-derived caps. Paid
market settlement consumes the same table for user-visible estimates. This
keeps "live cost integration" as shared accounting evidence rather than a
second, hidden memory-policy ledger.

## 8. Minimal Implementation Slices

The safest implementation order is:

1. Add a design-only cost table shape and pure cap calculator.
2. Add daemon-memory policy support for `budget_derived`, behind tests that do
   not require live payment rails.
3. Extend memory observability status to report effective cap source,
   calculation inputs, and fallback reason.
4. Add promotion-gate metadata and tests for accepted/rejected/deferred
   outcomes.
5. Add dispatcher decision-log records that reference memory entry IDs without
   changing claim selection.
6. Only after the decision log is observable, allow soul-guided ranking among
   already-eligible work.

Each slice should leave the plugin mirror updated if it touches canonical
`workflow/*` runtime files.

## 9. Acceptance Gates

Runtime implementation is not complete until it proves:

- all ten memory kinds validate through API and plugin mirror surfaces;
- accepted, rejected, promoted, and superseded lifecycle transitions are tested;
- default retrieval excludes rejected and superseded entries;
- promotion writes a wiki-facing review entry and durable promotion event;
- memory packet construction remains under prompt cap;
- wiki compaction keeps protected files and prunes only evictable records;
- budget-derived cap calculation is deterministic and never exceeds explicit
  max cap;
- missing or stale cost evidence falls back visibly instead of silently
  granting extra storage;
- dispatch logs candidate work, memory IDs used, budget terms, and reason;
- paid-market estimates and treasury split math share the same cost source.

## 10. Non-Goals For This Filing

This proposal does not authorize automatic soul edits, unbounded cross-daemon
search, hidden platform ranking of souls, real-money settlement rollout, or
new user-facing MCP actions beyond the already proposed daemon-memory and
market primitives.

