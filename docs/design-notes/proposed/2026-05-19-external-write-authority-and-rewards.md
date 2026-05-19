# External-write authority, idempotency, and reward release

**Status:** DRAFT — needs host steering before implementation.
**Author:** claude-opus-4-7, 2026-05-19.
**Replaces:** PR #893's narrow framing of "external-write primitive for Loop 2."
**Touches:** Brain module, Goals, Gates, Attribution, Royalties, Treasury, Bounties.

---

## Problem

The platform increasingly needs to write *outside itself* — open a GitHub PR,
send an email, post a tweet, publish a paper draft, transfer crypto from
treasury, call a third-party API. PR #893 framed this narrowly as "Loop 2
needs to emit PRs." That framing is too small: external writes show up in
every user scenario the platform aims to serve, and the trust/authority
model must be designed across all of them at once, not bolted on per
connector.

This note lays out the scenarios, the authority model, the Brain's role,
how Goals + Gates wire in, and how real-world reward release composes on
top.

---

## Scenarios

### 1. Single-person creator (YouTube / Twitter / personal blog)

One user runs branches that emit content to surfaces *they* own. Their
YouTube channel, their X account, their Substack. There's no community
to vet the write. Authority is unambiguous: it's them.

**External-write authority:** delegated user identity. Their token, their
account, their reputation.
**Approval shape:** chatbot asks once per surface ("can I post to your X
account on your behalf?"), persists scope, re-asks only on scope change.
**Brain's role:** remembers their style preferences, prior posts, what
voice they want; conditions every external write on those memories.
**Goals + Gates:** lightweight — Goal = "5 videos / month"; Gates = "posted
+ got ≥X views." Reward = personal satisfaction; no treasury release needed.

### 2. Single user posting *for themselves* on Twitter / similar

Subset of (1) but worth calling out because the write surface is high-
frequency and the failure mode (double-tweet) is more visible. Same
authority model; the idempotency contract becomes critical here because
Twitter doesn't natively support idempotency keys on status posts.

**Implication:** the platform's idempotency contract (see §"Idempotency"
below) is what carries the load, not the upstream API.

### 3. Shared fantasy universe (or any shared creative commons)

A small set of founders, a moderation tier, many contributors. Many people
write to the same body of canon. External writes might be: publish a chapter
to the public site, accept a contributor's submission, post an announcement
to the community Discord, mint an artifact tied to canon, release royalty
payouts to credited contributors.

**External-write authority:** *layered.*
- Branch-bound authority for in-universe writes (publish-to-site,
  accept-submission) — the Branch declares which scopes it needs; the
  Goal's owner pre-approves scopes; the daemon running the branch
  executes under that delegated scope.
- Founder/moderator authority for trust-boundary writes (moderation
  actions, founder announcements) — requires explicit step-up: the
  acting principal must be a logged-in founder *and* the write must be
  inside an approved branch.
- Host identity for platform-side writes (treasury operations,
  cross-universe announcements) — never delegated.
**Approval shape:** per-Goal scope manifest. Goal = "publish chapter 1 of
Universe X." Manifest lists external surfaces the Goal may touch (site
write, Discord post, royalty escrow update). Founder approves manifest
once; per-branch writes operate inside it.
**Brain's role:** the universe's Brain holds the canon, the contributor
list, the per-contributor weights for attribution, and the moderation
state. Every external write reads the Brain *before* writing — e.g.,
publishing a chapter checks the Brain for the canonical character list
to prevent canon drift.
**Goals + Gates:** Goal = "Chapter 1 published"; Gates = "draft approved by
≥N moderators", "passes canon-consistency check", "site-publish succeeded."
Gates are the bridge to reward release.

### 4. Scientific domain / research-paper universe

Many researchers; the universe is an open scientific corpus (e.g.,
"protein folding consensus" or "open replication of paper X"). External
writes might be: submit a paper to arXiv, file a Zenodo deposit, push
to a public GitHub repo, post to OpenReview, claim co-authorship.

**External-write authority:** strongest constraint scenario.
- Every external write must carry author-level identity, because
  scientific publication carries reputation/legal weight.
- The platform CANNOT publish under "the daemon's name." Publication
  must run under named contributors with their orcid/handle.
- Authority is granted *per submission*: when a paper is about to land
  to arXiv, the contributors named in the attribution graph each must
  approve (multi-signature on the publish action).
**Approval shape:** N-of-M approval over the paper's named authors. Goal's
gate ladder includes an "all authors signed publish" rung.
**Brain's role:** corpus Brain holds the field's prior art, the
methodology constraints, the open-replication state. Every paper draft
reads the Brain to cite correctly and to know what's been replicated.
**Goals + Gates:** Goal = "publish paper Y on topic Z"; Gates = "draft
written", "methodology check passes", "all authors signed", "submitted",
"accepted." Reward release ties to "accepted" gate, not "submitted."

### 5. The project itself having a voice

The Workflow project is its own universe — branches can be bound to a
Goal like "Workflow ships v1.0" or "Workflow's public blog publishes a
weekly digest." The platform *is* the contributor base; founders + a wide
contributor pool drive PRs.

**External-write authority:** host identity for platform-affecting writes
(merging PRs, posting to project Twitter, deploying releases). Delegated
contributor identity for contributor-affecting writes (their PRs to their
own forks, their X posts about their contributions).
**Approval shape:** host explicit-key for high-impact writes (releases,
treasury, public statements); branch-scope-approved for low-impact writes
(filing an issue, opening a draft PR).
**Brain's role:** the project's Brain *is* the open-brain v2 substrate
that just landed — memory_kinds registry, promotion state machine,
soul-guided dispatch. Every external write is conditioned on it.
**Goals + Gates:** Goal = "ship v1.0"; Gates = the release readiness
ladder. External writes (release publish, blog post) only fire on the
right rung being claimed.

---

## Authority model — synthesized

Pull the scenarios together: **every external write runs under exactly one
authority, picked from a typed hierarchy.**

```
host                            (platform-side; treasury, release, deploy)
  └─ founder                    (per-universe; moderation, founder action)
       └─ branch-scope          (delegated by Goal owner; in-universe write)
            └─ contributor      (delegated by branch; personal-identity write)
                 └─ daemon      (acts under a contributor's delegation)
```

**Rules:**

1. **Every external write declares its authority level at definition time**
   (in the Goal scope manifest), not at run time. Run-time elevation is
   forbidden; if a branch needs a higher authority, the Goal owner must
   re-approve the manifest.
2. **A write's authority level is the MINIMUM that suffices.** A daemon
   posting a draft chapter to a private staging site is contributor-level;
   a daemon publishing to the public site is branch-scope-level; a daemon
   minting a royalty payout is host-level.
3. **The platform never assumes authority it wasn't given.** If a write
   needs host-level authority and the host isn't signing, the write is
   queued and visible in the host's review surface — it does NOT just
   execute.
4. **Brain conditions every authority decision.** The Brain (universe-
   specific for shared universes, personal for single creators) holds the
   memory of past authority decisions and informs the next one — "this
   contributor's last 5 writes were clean, raise their scope ceiling" /
   "this universe's moderation tier voted against this category last week,
   block analogous writes."

---

## Idempotency (locked by host 2026-05-19)

**Every external write must carry a deterministic idempotency key.**
The platform refuses to dispatch a write without one.

**Construction:** key = stable hash of `(authority_principal, write_surface,
write_payload, attempted_at_window)`. The `attempted_at_window` is coarse
(per-hour) so a retry within the window collapses; a retry after the
window is a new write.

**Storage:** platform-side replay buffer keyed on the idempotency key.
Before any external write returns, the buffer is updated with a "this key
was attempted" marker. Retries see the marker and short-circuit, even if
the external surface itself has no idempotency support (Twitter, email).

**Implication for external connectors:** the connector definition must
include an `idempotency_key_constructor` callable that hashes the
write's salient inputs. No constructor → connector cannot be registered.
This is a hard registration-time gate, not a runtime warning.

---

## Goals + Gates: when external writes actually fire

External writes are NOT bound to arbitrary branch progress. They're
bound to **gate rung claims.** This is what wires writes into the Goal
ladder, not into raw daemon activity.

- Goal owner defines the ladder, with "this rung gates this external
  write" annotations.
- Branch climbs the ladder by accumulating evidence (per the standard
  gate-evidence model).
- Claiming a rung that's marked "fires external write X" triggers
  dispatch of write X — under the authority declared in the rung
  annotation, with the idempotency key constructed from the rung claim
  + branch state.

Example (fantasy universe):
- Goal: "Chapter 1 published"
- Ladder rungs:
  - R1: "draft complete" (no external write)
  - R2: "≥N moderators approved" (no external write)
  - R3: "publish to site" → fires site-publish write under
    branch-scope authority
  - R4: "royalty escrow released" → fires treasury write under
    host authority

Example (scientific):
- Goal: "Paper Y submitted"
- Rungs:
  - R1..R4: drafting / methodology / co-author signatures
  - R5: "submit to arXiv" → fires arXiv-submit under N-of-M
    contributor authority (multi-signature)
  - R6: "accepted" → fires reward-release under host authority

---

## Real-world reward release (the punchline)

When someone offers a reward for a gate ("$500 escrowed for whoever
gets Paper Y accepted to NeurIPS"), the reward is held in the platform's
treasury until the relevant rung is claimed *and the external evidence
verifies*.

**Composition:**

1. **Reward deposit** = external write of type "treasury inbound"; runs
   under contributor-or-anonymous authority; idempotency key = donor +
   amount + Goal + time-window.
2. **Reward release condition** = a specific gate rung in the Goal's
   ladder is claimed AND the gate's evidence type is `external_event`
   (e.g., "arXiv ID exists" / "publication site reports article live" /
   "GitHub release is tagged").
3. **Verification** = an evidence-fetcher (oracle) reads the external
   surface and confirms the event. The fetcher itself is a registered
   external connector, subject to the same idempotency and authority
   rules.
4. **Payout** = external write of type "treasury outbound to attribution
   list"; runs under host authority; idempotency key = Goal + rung +
   payout-cycle.

**Brain's role in payout:** the Brain holds the attribution graph (who
contributed how much to which nodes). Payout reads attribution at the
moment of release, weights it by the Brain's contributor-weight policy,
and emits the per-contributor amounts. There is no "I deserved more"
adjudication after the fact — the Brain's snapshot at release is
authoritative.

**Why this composes cleanly:** every piece is already a primitive we're
building:
- treasury read/write (slice C of open-brain v2: read-only treasury
  status — write path still to come).
- gate ladder + rung claims (existing gates surface).
- evidence oracles (a special class of external connector).
- attribution graph (existing in the ledger / `author_id` surfaces).
- the Brain reading attribution (the open-brain substrate).

No new fundamental primitive is needed for reward release. It's a
composition of authority + idempotency + gates + connectors +
attribution + Brain.

---

## Open design questions for host steering

1. **Goal scope manifest format** — JSON schema or natural-language?
   (Recommendation: structured JSON for the connector-binding part,
   free-text annotation for the rung-to-write mapping.)

2. **N-of-M contributor signing on scientific publication** — built as a
   first-class gate evidence type, or as a generic "multi-actor
   approval" primitive that other surfaces can reuse?
   (Recommendation: generic multi-actor approval; scientific publication
   is the first consumer but moderation, founder-vote, and treasury
   multisig will all want the same thing.)

3. **Brain authority-condition policy** — how aggressively should the
   Brain *deny* writes based on past signal? Two ends:
   - Permissive: Brain logs and hints, doesn't block.
   - Strict: Brain can refuse to authorize a write that contradicts its
     state.
   (Recommendation: start permissive, advance to strict only with an
   explicit opt-in flag per Goal, so universes can decide.)

4. **Evidence-oracle trust** — when an oracle says "the paper is
   accepted at NeurIPS," who validates the oracle? Multi-oracle quorum?
   Host signature?
   (Recommendation: multi-oracle quorum for reward release ≥ $X
   threshold; single-oracle below. Threshold configurable per universe.)

5. **Idempotency-key window granularity** — per-hour is the default
   above; some surfaces (treasury operations) want per-day or never-
   collapse; some (chat posts) want per-minute.
   (Recommendation: window is per-connector, declared at connector
   registration time.)

6. **What does Loop 2 actually fire as its first external write?** PR
   #893's original framing was "Loop 2 emits PRs." Is "emit PR to
   project repo" the right first external write to ship, or is something
   smaller (e.g., "Loop 2 emits a draft wiki page that humans then
   promote") safer for the first slice?

---

## Relationship to other open work

- **PR #893** — supersede with this note. Close #893 once this is
  approved; cite this as the replacement.
- **#909/#910/#911/#912** — the effort-classifier follow-ups are
  unrelated to external-write authority; no edge.
- **Open-brain v2 slices A-D (landed)** — this design assumes slices A
  (memory_kinds), B (soul-guided dispatch), C (treasury status read),
  D (bounded spend) are in place. The write-path treasury work is
  net-new and follows from this note.
- **Brain module in PLAN.md (PR #873)** — this note assumes the Brain
  module exists in PLAN.md and references it. PR #873's restructure
  should leave room for Brain to host the authority-conditioning policy
  described here.

---

## Next steps

1. Host reviews this draft; answers the 6 open questions OR steers to
   different defaults.
2. Promote to `docs/design-notes/` (out of `/proposed/`) once approved.
3. Replace PR #893 — close it, open a sibling PR that points here as
   the spec.
4. Land Brain module in PLAN.md (PR #873 work) with a hook for this
   authority-conditioning policy.
5. First implementation slice: the idempotency contract + connector
   registration gate, since that's a hard prerequisite for any other
   external write to land safely.
