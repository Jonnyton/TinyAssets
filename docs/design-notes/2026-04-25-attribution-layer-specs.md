---
status: active
---

# Attribution Layer Specs

**Date:** 2026-04-25
**Author:** navigator
**Status:** Design spec — semantics on top of dev-2-2's contribution-ledger schema. Lead/host ratify; once stable feeds PLAN.md.
**Builds on:**
- `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (dev-2-2 — schema substrate, single-table model with 5 event_types + 4 indexes)
- `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` v1 §3 (five contribution surfaces framing)
- Memory `project_designer_royalties_and_bounties` (royalty distribution + navigator's fair-weighting role)
- Memory `project_paid_market_trust_model` (E18 override candidate — sybil resistance with monetization)
- `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` Phase B (items 8-12) + Phase D (items 19-22)
**Scope:** semantics — when events fire, how weights compute, how lineage decays, bounty distribution math, sybil resistance sketches, negative event handling, reputation queryability. NO schema changes. If a gap surfaces, raised as v2 of #47, not a counter-proposal.

---

## 1. Event-type catalog

For each event_type defined in #47 §1.1, this section pins: trigger condition, emit-site (line refs from #47 §3), required metadata fields, default weight. Storage shape is fixed by #47; this is how the runtime fills the rows.

### 1.1 `execute_step` — daemon-host contribution

**Trigger:** every successful step finalize on a run. One event per step, regardless of step duration or output volume.

**Emit-site:** `tinyassets/runs.py:331-377` (`update_run_status`'s step-finalize transaction). Inside the same `_connect()` block that writes node-completion to `run_events`, append one row to `contribution_events`. Same SQLite transaction = atomicity guarantee.

**Required metadata:**
| Field | Source | Notes |
|---|---|---|
| `actor_id` | `runs.daemon_actor_id` (Phase B item 10) | Captured at run claim time. **Required:** if `daemon_actor_id` is empty, emit no event (don't credit anonymous). |
| `source_run_id` | The current run | Always populated. |
| `source_artifact_id` | NULL | This event credits the daemon, not an artifact. |
| `weight` | 1.0 (default) | See §2.1. |
| `metadata_json` | `{"node_id": ..., "step_index": ..., "duration_ms": ..., "status": "success"}` | Useful for diagnostic / "who ran what" without scanning runs. |

**Skip conditions:**
- Step status is `failed`, `cancelled`, or `interrupted` (per #47 §6 Q4 — no event for unfinished work).
- Run was a dry-run / preview / validation (chatbot-side smoke against an unpublished branch). Detected via `runs.run_name` carrying a `dry_run:` prefix or a future `runs.is_dry_run` flag.

### 1.2 `design_used` — designer contribution

**Trigger:** every step that references a published artifact. One event per artifact reference. A single step can emit multiple events if it references multiple artifacts (e.g., a node from one branch_version + an evaluator soul from another).

**Emit-site:** same step-finalize transaction as `execute_step`. After the daemon-host event lands, walk the step's artifact references (`graph_node_ref.node_def_id`, branch_version_id of the running snapshot, soul_id if attached, evaluator_id if attached) and emit one event per published reference.

**Required metadata:**
| Field | Source | Notes |
|---|---|---|
| `actor_id` | The artifact's author at publish time | Read from `branch_versions.publisher` for branch_version refs; from `node_definitions.author` for node refs; analogous for soul/evaluator. |
| `source_artifact_id` | The artifact's id | branch_version_id, node_def_id, etc. |
| `source_artifact_kind` | `'branch_version'` / `'node_def'` / `'soul'` / `'evaluator'` | Per #47 §1.1 enum; extends as new artifact kinds land. |
| `source_run_id` | The current run | Tracks where this designer credit got earned. |
| `weight` | 1.0 default; per §2.2 may decay later | Lineage walk happens at calc-time, not emit-time, per #47 §1.3. |
| `metadata_json` | `{"node_id": ..., "artifact_version": ...}` | Optional — diagnostic. |

**Skip conditions:**
- Artifact reference is to an unpublished/draft (no row in `branch_versions`). Only published artifacts earn credit. Live `branch_def_id` references for in-progress work emit no `design_used` event.
- Self-reference: actor_id of the artifact's author == actor_id of the daemon-host running it. Don't double-credit a designer running their own primitive. (See §2.6 — open question: does host want to allow self-credit at lower weight?)

### 1.3 `code_committed` — direct repo PR

**Trigger:** GitHub webhook `pull_request.closed` with `merged=true` AND PR carries the `patch_request` label (or its alias). Future: include classifier-detected `docs-only` / `format-only` / `hot-fix` PRs even without explicit label, per canary→patch_request spec §6.

**Emit-site:** the GitHub webhook handler (Phase D item 17 / Task #55, currently pending). Per #47 §3 row 3, lives at `tinyassets/integrations/github_webhook.py` (new file). Emits one event per PR commit author + each `Co-Authored-By` actor in the commit chain.

**Required metadata:**
| Field | Source | Notes |
|---|---|---|
| `actor_id` | PR author's Workflow id (looked up via CONTRIBUTORS.md handle linkage) | If no linkage exists, emit with `actor_id` = synthetic `github:<handle>`; retroactive linkage primitive (per E17) backfills later. |
| `actor_handle` | GitHub handle | Stored verbatim. |
| `source_artifact_id` | PR URL | e.g. `https://github.com/jfarn/tinyassets/pull/142` |
| `source_artifact_kind` | `'github_pr'` | |
| `source_run_id` | NULL | PR is run-free until a downstream daemon run references it. |
| `weight` | 1.0 default; modified by PR-size/complexity heuristic in §2.3 | |
| `metadata_json` | `{"pr_number": ..., "merged_at": ..., "commit_shas": [...], "labels": [...], "lines_added": ..., "lines_removed": ...}` | Used by §2.3 heuristic. |

**One event per Co-Authored-By trailer:** if commit message has `Co-Authored-By: A` and `Co-Authored-By: B`, emit one event per coauthor. Weight per coauthor follows a split (see §2.3 — equal-split default; lead author gets a small bonus).

### 1.4 `feedback_provided` — helpful chatbot-action

**Trigger:** a gate-series evaluator returns a decision payload that **explicitly cites** a wiki page or chatbot artifact as evidence. **Anti-spam invariant:** no cite, no credit. The evaluator must include the cited artifact in its decision metadata for the event to fire.

**Emit-site:** the gate-series evaluator's decision-write path (Phase A item 7 — gate-series typed-output contract). When the evaluator returns its decision, the gate runner inspects the decision's `evidence_refs: [{kind, id}, ...]` field and emits one `feedback_provided` event per cited artifact whose author is identifiable.

**Required metadata:**
| Field | Source | Notes |
|---|---|---|
| `actor_id` | Author of the cited artifact | E.g. for a cited wiki bug page, the original `bug_filer_actor_id` from frontmatter. |
| `source_artifact_id` | Cited artifact id | BUG-NNN, drafts/foo, run_id of a prior run, etc. |
| `source_artifact_kind` | `'wiki_page'` / `'cosign'` / `'prior_run'` / etc. | Per #47 enum extensions. |
| `source_run_id` | The gate's run | The gate-series run that consumed the feedback. |
| `weight` | Per §2.4 formula — proportional to gate decision weight | |
| `metadata_json` | `{"gate_decision": ACCEPT/SEND_BACK/REJECT, "decision_confidence": 0..1, "cited_at_node": ..., "evidence_strength": "strong"/"weak"}` | Used by §2.4 weighting. |

**The "explicit cite" constraint is load-bearing.** A user filing 1000 wiki pages doesn't earn 1000 feedback credits. Only when a gate-series uses a page as decision input does that page's author earn. This makes feedback monetization spam-resistant by construction.

**Self-cite handling:** a user citing their own artifact in a gate they authored emits the event with `metadata.self_cite=true`. Bounty calc deweights or filters these (see §2.6 open question).

### 1.5 `caused_regression` — negative event

See §6 for full handling. Trigger summary: post-merge canary regression within watch-window AND the rollback chain attributes the regression to a specific artifact. Weight is **negative**, magnitude derived from severity (§6.1 table).

---

## 2. Weight formulas

All formulas produce a single REAL value per event, suitable for `contribution_events.weight`. Lineage decay applies at calc-time (§3), not emit-time.

### 2.1 `execute_step.weight`

```
weight = 1.0
```

Flat. One step = one unit of daemon-host credit. Rationale: complexity / runtime / token-count are already implicit in *which* nodes a daemon picks to claim — a daemon claiming long-running expensive nodes earns many step-credits naturally. Adding multipliers invites gaming (a daemon could artificially inflate step counts by inserting no-op nodes into branches it controls).

**Future refinement (Phase E or later):** if abuse appears, switch to `weight = log(1 + duration_seconds)` or similar bounded function. Don't preempt.

### 2.2 `design_used.weight`

```
weight = 1.0
```

Per artifact reference. Lineage decay is applied at calc-time, not here — the leaf event is the credit anchor; the decay walk derives ancestor shares. (Per #47 §1.3 architecture.)

**Multiplier per reference type** (optional v1.1 refinement):
- `branch_version` reference: weight = 1.0
- `node_def` reference inside a branch: weight = 0.5 (node is a sub-primitive; whole-branch designer earns full unit, node designer earns half)
- `soul` reference: weight = 0.3 (soul tunes behavior; doesn't define structure)
- `evaluator` reference: weight = 0.5 (similar to node)

These multipliers are **calibration parameters**, not load-bearing semantics. Pin defaults; let host adjust based on observed economic effects. Storage location: `tinyassets/economics/weights.py` (per #47 §6 Q3 recommendation).

### 2.3 `code_committed.weight`

```
weight = 1.0 * pr_size_factor * coauthor_split_factor
```

**`pr_size_factor`** — bounded, sublinear in lines changed:
```
pr_size_factor = clamp(0.5, 1.0 + log10(max(1, lines_changed) / 50), 3.0)
```
A 50-line PR earns 1.0×, 500-line earns ~2.0×, 5000-line earns capped at 3.0×. Sublinearity prevents giant-PR gaming; the floor (0.5) ensures docs-only fixes still earn meaningful credit.

**`coauthor_split_factor`** for N coauthors total (lead + N-1 trailing):
- Lead PR author: `(1.0 + 0.2) / N` (small lead-author bonus reflecting they did the orchestration).
- Each trailing coauthor: `(1.0 - 0.2 / (N - 1)) / N` if N > 1, else 1.0.

For solo PR (N=1), `coauthor_split_factor = 1.0`. For N=2, lead gets ~0.6, coauthor gets ~0.4. For N=4, lead gets ~0.3, each coauthor gets ~0.233.

**Lead detection** = first commit author OR PR opener (PR opener takes precedence on contested cases). Co-Authored-By trailers are always coauthors, never leads.

### 2.4 `feedback_provided.weight`

```
weight = base_feedback_weight * gate_decision_strength * evidence_strength_multiplier
```

**`base_feedback_weight`** = 0.1 (an order of magnitude below `design_used`). Feedback is signal; design is structure. Calibrates so a high-signal user feedbacker accumulates meaningful credit but never out-earns a comparable designer.

**`gate_decision_strength`** = decision-confidence as reported by the gate evaluator (0.0 to 1.0). A low-confidence cite earns less.

**`evidence_strength_multiplier`**:
- `"strong"` (gate cites artifact as primary basis): 1.0
- `"weak"` (gate cites as one-of-many corroborating signals): 0.5
- `"contradicting"` (gate cited but ultimately discounted): 0.2

Defaults if metadata absent: `gate_decision_strength = 0.5`, `evidence_strength_multiplier = 0.5`. Conservative — unannotated cites earn modestly.

**Self-cite (§1.4):** if `metadata.self_cite == true`, multiply final weight by 0.0 (no self-credit) OR 0.25 (small self-credit, since you're surfacing your own work). Pin **0.0** for v1 — no self-credit. Avoids the failure mode where a user files 1000 pages then authors a gate that cites all of them. Host can override if behavior surfaces real user need for self-citation.

### 2.5 Net per-event weight ranges (calibration sanity check)

| Event type | Min weight | Typical | Max (uncapped) |
|---|---|---|---|
| `execute_step` | 1.0 | 1.0 | 1.0 |
| `design_used` | 0.3 (soul) | 1.0 (branch_version) | 1.0 |
| `code_committed` | 0.25 (small docs PR, 4-coauthor) | 1.0-2.0 (typical PR) | 3.0 (massive solo PR) |
| `feedback_provided` | 0.0 (self-cite) | 0.025 (default cite) | 0.1 (strong primary cite) |
| `caused_regression` | -10 (P0) | -3 (P1) | -1 (P2) |

Two orders of magnitude span, top to bottom. Designer + committer credit dominate; daemon-host credit is steady-trickle; feedback is small but real; regression bites hard. Calibration is intuitive: ship something that breaks and you lose more than you'd earn from a typical PR.

### 2.6 Open weight-formula questions (deferred)

- Self-credit policy on `design_used` (§1.2 — designer running own primitive). Pin **no event** for v1; host override if real use case appears.
- Weight differentiation across `branch_version` vs. `node_def` vs. `soul` vs. `evaluator` (§2.2 multipliers). Pin defaults but call out: these are calibration knobs.
- Lead-author bonus magnitude in `coauthor_split_factor` (§2.3). Pin 0.2; host may tune up if PR orchestration cost is undervalued in practice.

---

## 3. Lineage decay coefficients

Per memory `project_designer_royalties_and_bounties`: N-generation attribution decays geometrically. The platform parameter pins the curve.

### 3.1 The curve

```
decay_coeff(depth) = α^depth
```

where `depth` is generation count from the leaf (0 = leaf itself, 1 = direct parent, 2 = grandparent, ...) and `α ∈ (0, 1)`.

### 3.2 Pinned default: α = 0.6

Reasoning:
- α = 0.5 (half each generation) is conventional but **too steep** for a creator-economy. By generation 4 (great-great-grandparent) credit is already 6.25%; many primitives have 5+ generation lineages and the original authors get vanishing credit.
- α = 0.7 is **too gentle**: at 4 generations you're still at 24%, and the head of the lineage chain captures more of the bounty pool than the leaf does for any artifact deeper than 2 generations.
- α = 0.6 lands at depth=4 → 12.96%, depth=8 → 1.68%, depth=12 → 0.22%. Original authors get meaningful but not dominant credit; new contributors aren't crowded out by ancient ancestry.

### 3.3 Truncation cap: max_lineage_depth = 12

Beyond 12 generations, decay coefficient is set to 0. Two reasons:
- Computational: SQL recursive CTE in #47 §4 has `WHERE bd.fork_from IS NOT NULL AND lineage.depth < :max_lineage_depth` — bounding the walk avoids pathological lineages.
- Economic: at depth 12 with α=0.6, share is 0.22%; below the noise floor of microtransaction fees per memory `project_q10_q11_q12_resolutions` ("batch settlements <$1").

Truncation MUST be visible in the audit trail. A merge's bounty calc result includes a `truncated_at_depth: 12` field if any lineage walk hit the cap, so the absence of credit beyond depth 12 isn't silent.

### 3.4 Storage location

`tinyassets/economics/decay.py` (matches #47 §6 Q3 recommendation). Constants pinned as module-level; bounty calc imports. Changing α is a config-as-code edit, requires PR and dispatch — not runtime-mutable. (Per memory: "platform parameter, not per-user choice.")

### 3.5 Cross-artifact lineage

A branch_version may reference multiple node_defs, each with its own lineage chain. Decay applies per chain independently:
- `branch_version` (depth 0) → `branch_def parent_branch_def_id` walks one chain.
- Each `node_def` referenced by the branch walks its own `node_def.fork_from` chain.

Per-chain decay sums into the merge's total share without normalization. A merge might credit one designer for `branch_version` ancestry AND another designer for `node_def` ancestry inside that branch. Both stand; both decay independently from their respective leaves.

---

## 4. Bounty distribution math

For merge M committed at time `t_M`, attribution window `[t_M - W, t_M]` (W typically 30 days, configurable per merge), produce ordered list of (actor_id, percent_share) tuples summing to 100%.

### 4.1 Algorithmic shape

Builds on #47 §4 recursive-CTE query. Three passes:

**Pass 1 — collect raw weighted contributions per actor:**

```sql
WITH RECURSIVE lineage(artifact_id, depth) AS (
    SELECT :merge_artifact_id, 0
    UNION ALL
    SELECT bd.fork_from, lineage.depth + 1
    FROM lineage
    JOIN branch_definitions bd ON bd.branch_def_id = lineage.artifact_id
    WHERE bd.fork_from IS NOT NULL AND lineage.depth < :max_lineage_depth
),
positive_contributions AS (
    SELECT
        ce.actor_id,
        SUM(ce.weight * decay_coeff(lineage.depth)) AS raw_share
    FROM contribution_events ce
    JOIN lineage ON lineage.artifact_id = ce.source_artifact_id
    WHERE ce.occurred_at BETWEEN :window_start AND :window_end
      AND ce.weight > 0
    GROUP BY ce.actor_id
),
negative_contributions AS (
    SELECT
        ce.actor_id,
        SUM(ce.weight) AS regression_penalty  -- already negative
    FROM contribution_events ce
    WHERE ce.occurred_at BETWEEN :window_start AND :window_end
      AND ce.weight < 0
      AND ce.actor_id IN (SELECT actor_id FROM positive_contributions)
    GROUP BY ce.actor_id
)
SELECT
    p.actor_id,
    p.raw_share + COALESCE(n.regression_penalty, 0) AS net_share
FROM positive_contributions p
LEFT JOIN negative_contributions n ON n.actor_id = p.actor_id
WHERE p.raw_share + COALESCE(n.regression_penalty, 0) > 0
ORDER BY net_share DESC;
```

**Pass 2 — apply sybil-aware scaling (when E18 lands):**

Each `actor_id` carries a `sybil_confidence_score ∈ [0, 1]` from the chosen sybil-resistance primitive (§5). Multiply each row's `net_share` by the actor's score before normalization. Unvouched / new actors with score 0.3 effectively get 30% of their raw earned share until they accumulate trust signals.

**Pass 3 — normalize to percentages summing to 100%:**

```
total = SUM(scaled_net_share)
percent_share[i] = scaled_net_share[i] / total * 100
```

### 4.2 Exclusion thresholds

- Actors whose `net_share <= 0` (regressions exceed positive contributions in window) are **dropped** from the distribution. They earned nothing this merge. The platform take + bounty pool replenishment captures their share.
- Actors whose `net_share > 0` but normalized percent_share < 0.5% are bucketed: their shares aggregate into a single `bounty_pool_remainder` line in the result. Reasoning: microshares below 0.5% of a typical merge payout are below transaction-cost floors. Bucketed shares accumulate in the bounty pool for redistribution.
- Hard floor: at most 50 actors get individual lines on a single merge's distribution. Beyond that, lowest-share actors bucket. Caps result-set size for UI rendering and on-chain emission.

### 4.3 Routing of distribution result

Two consumers of `(actor_id, percent_share)` tuples:
1. **Commit message generator** — emits `Co-Authored-By` trailers per actor with handle linkage (one trailer per actor; no percent_share rendering in commits — that's economic, not credit-attribution data).
2. **Bounty payout queue** — writes each tuple to the payment escrow's pending-payout table. Batch settlement per memory `project_q10_q11_q12_resolutions`.

Result ALSO writes to a `merge_distributions` audit table (one row per merge × actor) for transparency / dispute resolution. Schema is small; not in scope here but flag for v2.

### 4.4 Disputed merges

When the calc produces a result but at least one actor (or a quorum-eligible third party) flags the result within a 48h challenge window, navigator (or governance quorum, post-DAO) reviews:
- Verifies emit-site events fired correctly.
- Validates lineage walk against ground truth.
- Checks for emit-time bugs (e.g., wrong actor_id captured).
- Either ratifies the original calc or issues a corrective `caused_regression`-class adjustment event (see §6.4).

**Routine merges auto-distribute after 48h challenge window with no dispute.** Disputed = navigator-mediated.

---

## 5. Sybil resistance primitive sketches

E18 (host go/no-go: "sybil resistance must land with monetization, not after") is the explicit override of memory `project_paid_market_trust_model`. Below are three sketches host can choose from. **Not picking — sketching all three concretely so host has options.**

### 5.1 Sketch A — Web-of-trust via vouching

**Storage shape:** new table `actor_vouches`:

```sql
CREATE TABLE actor_vouches (
    voucher_actor_id    TEXT NOT NULL,
    vouchee_actor_id    TEXT NOT NULL,
    vouched_at          REAL NOT NULL,
    weight              REAL NOT NULL DEFAULT 1.0,
    revoked_at          REAL,           -- soft-revoke timestamp
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (voucher_actor_id, vouchee_actor_id)
);

CREATE INDEX idx_actor_vouches_vouchee ON actor_vouches(vouchee_actor_id);
```

**Authority model:** any actor with `sybil_confidence_score >= 0.5` can vouch (a kind of bootstrap; founding host actors seeded at score 1.0). Each actor has a vouch budget (e.g. 5 vouches per quarter) — prevents one trusted actor from vouching for unlimited sybils.

**Query primitive:**
```python
def sybil_confidence_score(actor_id, base_path, t_now) -> float:
    # Sum incoming vouches' weights, decay by voucher's own score, normalize.
    # Returns 0.0 (no signal) to 1.0 (heavily vouched).
```

**Pros:** community-driven, scales without centralized identity, naturally surfaces real humans. **Cons:** bootstrap problem (early system has few vouchers); vouch budgets need tuning to avoid both throttle and farming.

### 5.2 Sketch B — GitHub-handle as identity anchor

**Storage shape:** add columns to actor record (or use existing CONTRIBUTORS.md surface as authoritative):

```sql
ALTER TABLE actors ADD COLUMN github_handle TEXT;
ALTER TABLE actors ADD COLUMN github_account_age_days INTEGER;
ALTER TABLE actors ADD COLUMN github_public_contributions INTEGER;
ALTER TABLE actors ADD COLUMN github_verified_at REAL;
```

(Or a separate `actor_github_anchors` table — mirrors variant-canonicals split.)

**Authority model:** actor self-links a GitHub handle (one-time chatbot-mediated, per A5). Platform fetches public account stats via GitHub API; recomputes monthly.

**Query primitive:**
```python
def sybil_confidence_score(actor_id, base_path, t_now) -> float:
    # Function of GitHub account age + contribution count + verification.
    # Unlinked actors score 0.3 (default — earn but at deweighted rate).
    # Linked accounts < 30 days old score 0.4.
    # Linked accounts > 1y with > 50 public contribs score 0.95.
```

**Pros:** inherits GitHub's anti-sybil work for free; no community bootstrap problem; clear UX path for casual users (paste handle once). **Cons:** non-GitHub users (privacy-conscious, regional) get permanent deweight; tightly couples to one third-party identity provider.

### 5.3 Sketch C — Decay on bad vouches (compounds with A)

This is a *modifier* on sketch A, not standalone. Tracks vouching outcomes over time.

**Storage shape:** extend `actor_vouches` with outcome tracking:

```sql
ALTER TABLE actor_vouches ADD COLUMN outcome TEXT NOT NULL DEFAULT 'pending';
-- enum: 'pending', 'good', 'bad'
ALTER TABLE actor_vouches ADD COLUMN outcome_resolved_at REAL;
```

**Outcome attribution:** when a vouchee accumulates ≥ N `caused_regression` events with attributed authorship (e.g. N=3 within 90 days), all their vouchers get a `bad` mark on their vouch row. When a vouchee reaches a positive-contribution milestone with no negative events (e.g. 50+ positive events, 0 regressions), vouchers get a `good` mark.

**Query primitive enhancement:**
```python
def voucher_credibility(actor_id, base_path) -> float:
    # Ratio of good vouches to (good + bad), decayed over time.
    # Vouches from a high-credibility voucher carry more weight in
    # `sybil_confidence_score` of the vouchee.
    # New vouchers default 0.5 credibility.
```

**Pros:** self-policing — bad vouchers self-degrade; system surfaces honest brokers automatically. **Cons:** accountability lag (outcomes take time to resolve); cold-start ambiguity for new vouchers.

### 5.4 Composability matrix

| Combination | Effect |
|---|---|
| A only | Pure web-of-trust. Bootstrap-fragile but maximally decentralized. |
| B only | Centralized-anchor; works day one. Permanent deweight for non-GitHub users. |
| A + B | Default. GitHub anchor sets initial floor; vouching can lift score above floor for non-GitHub users. **My read: this is the recommended composition.** |
| A + B + C | Full — vouching with outcome tracking. C strengthens A over time as vouching outcomes compound. |
| Only C | Doesn't make sense — C has no standalone vouches to track. |

**Recommendation (sketch only — host decides E18):** ship A + B in v1; layer C in v2 once vouching outcomes accumulate enough data to compute credibility. C requires several months of vouching activity before its deweighting works meaningfully.

### 5.5 Where sybil scoring is applied

Per §4.1 Pass 2: bounty distribution multiplies each actor's raw earned share by their `sybil_confidence_score`. A new actor with score 0.3 effectively earns at 30% rate until they build trust. The earned credit is **recorded** in `contribution_events` at full weight (the events are facts); the **distribution** scales by sybil score. This separation matters: when an actor's score later improves (e.g. they verify GitHub or get vouched), retroactive distributions can be re-computed at the new score for future windows. Past distributions stay as-issued (audit trail integrity).

---

## 6. Negative event handling — `caused_regression`

### 6.1 Severity → weight mapping

| Severity | Weight magnitude | Rationale |
|---|---|---|
| P0 | -10.0 | Forever-Rule violation — outage, data-loss, auto-heal pipeline broken. Author should lose ~10 PRs worth of credit. |
| P1 | -3.0 | Degraded surface; recoverable. |
| P2 | -1.0 | Precursor / single-instance regression. Often false-positive; small penalty preserves signal-to-noise. |
| (false-positive correction) | Reverses prior `caused_regression` | When investigation determines the original attribution was wrong. See §6.4. |

### 6.2 Trigger condition

**Event fires when:**
1. A canary surface goes red.
2. The red triggers a rollback decision (Phase E item 23-24 — bisect-on-canary + atomic-rollback-set).
3. The rollback's attribution chain identifies a specific merge / artifact that introduced the regression.
4. The watch-window of that merge is still open (typically 7-30 days post-merge).

All four conditions must hold. **The system does NOT emit speculative regression events** — only when the attribution chain is concrete.

### 6.3 Emit-site

Phase E item 23 (`bisect-on-canary`). When bisect identifies the offending commit/artifact:

1. Read the merge's `merge_distributions` audit row (§4.3) to find which actors earned share for this merge.
2. Emit one `caused_regression` event per actor in the merge's distribution, weight proportional to the actor's positive share at merge-time:

```
caused_regression.weight[actor] = severity_magnitude * (actor_merge_share / sum_of_shares)
```

For a P0 regression on a merge where actor A had 40% share and actor B had 60% share:
- actor A: -10 * 0.4 = -4.0
- actor B: -10 * 0.6 = -6.0

This is the "credit-proportional liability" rule: you bore credit, you bear regression. **Daemon-host credits don't bear liability** — daemons just executed; designers and committers chose what to ship. So the regression-distribution skips events with `event_type = 'execute_step'`.

### 6.4 Reversal / correction

If subsequent investigation determines the regression attribution was wrong (the rollback was unnecessary, or attribution chain misidentified the root cause):

1. Navigator (or governance quorum) authors a `regression_reversal` decision.
2. Emit one positive event per affected actor with `weight = -1 * original_weight` (cancels the regression). `event_type` remains `caused_regression` (audit trail) but `metadata.is_reversal = true` and `metadata.reverses_event_id = <original>`.
3. Bounty calc treats reversed regressions as zero-net (positive cancels negative).

The event ledger is append-only; reversals don't delete prior events. Audit trail preserves the full history.

### 6.5 Aggregate per-actor reputation

```
reputation(actor_id, window) = SUM(weight) for all events in window
```

Naïve sum-of-weights. Positive events accumulate; negative events deduct. Reputation is **windowed** (default: trailing 90 days) to avoid permanent stigma for old mistakes. Per §7, reputation is queryable but not displayed by default — it's an input to discovery rank, not a public grade.

**One floor:** reputation cannot push an actor's `sybil_confidence_score` below 0.0 or their bounty share below 0.0 in any individual merge. Repeated regressions reduce earnings to zero; they don't claw back already-distributed bounties from prior merges. Distributions are final at challenge-window close.

---

## 7. Reputation surface

Per memory `project_user_builds_we_enable`: reputation is a primitive users compose, not a platform-imposed grade. Platform exposes the data; chatbots and user-built UIs decide how to surface it.

### 7.1 MCP read action sketch

```
contributions action=actor_reputation actor_id=... window_days=90
→ {
    "actor_id": ...,
    "actor_handle": ...,
    "window_start": ...,
    "window_end": ...,
    "net_reputation": <float>,
    "positive_events": <int>,
    "negative_events": <int>,
    "by_event_type": {
        "execute_step": {count: N, weight_sum: ...},
        "design_used": {count: N, weight_sum: ...},
        ...
    },
    "sybil_confidence_score": <float ∈ [0, 1]>,
    "github_handle": <str or null>,
    "vouch_count_in": <int>,         # vouches received
    "vouch_count_out": <int>          # vouches given
}
```

Read-only; no auth required for public actor profiles. Privacy-flagged actors (per `project_privacy_per_piece_chatbot_judged`) return aggregates only, not per-event details.

### 7.2 Discovery rank composition

A chatbot recommending "trusted gates for goal X" composes reputation as one input to discovery rank:

```
discovery_score(artifact) = base_relevance * f(reputation_of_author) * g(usage_count) * h(recency)
```

Reputation is one factor; usage and recency are co-equal. Memory `project_q17_q18_seed_moderation_feedback`: surface BOTH a "trusted" rank AND a "novelty" rank — don't let reputation alone crowd out new contributors.

### 7.3 What reputation is NOT

- Not a public grade. Per `project_user_builds_we_enable`, the platform doesn't impose ranking — it provides data.
- Not gating. Low-reputation actors can still contribute, file patch_requests, author primitives. Their work just earns at deweighted rates until reputation builds.
- Not portable across windows. An actor who recovers from a bad period builds reputation in the new window; old window's reputation doesn't follow them.
- Not a sybil signal directly. `sybil_confidence_score` (§5) is the sybil signal; reputation is the contribution signal. They compose but are distinct.

### 7.4 Privacy / opt-out

Actors can flag their reputation as private (per-actor flag — extends `actors` table or lives in CONTRIBUTORS.md). Private reputation:
- Still computed; still affects bounty distribution (math doesn't change).
- Not surfaced in `contributions action=actor_reputation` to other actors.
- Self-readable via authenticated query.

This preserves symmetric privacy (per v1 vision §7 ρ): actors choose their visibility; platform respects.

---

## 8. Open questions

1. **`max_lineage_depth = 12` calibration.** §3.3 picks 12 based on α=0.6 hitting 0.22% noise floor. If host sets α higher (e.g. 0.7), 12 is too deep (depth 12 would still be 1.4%). Spec should make max_lineage_depth a function of α and a noise floor, not a fixed integer. Pin computation: `max_depth = ceil(log(noise_floor) / log(α))` with `noise_floor = 0.005`. Worth explicit ratification.

2. **Self-cite weight (§2.4 — `metadata.self_cite=true`).** Spec pins 0.0 for v1 (no self-credit). But user-built gates that legitimately cite their own foundational pages (e.g. a primer the user wrote that gates use as reference) are a real case. Do we want a 0.25 fractional self-cite? Decision affects whether well-intentioned self-citers get punished alongside spammy ones. Recommend 0.0 ship, monitor, calibrate.

3. **Daemon-host credit on regression.** §6.3 states daemon-host credits don't bear regression liability. But what about a daemon-host that runs a *known-broken* version repeatedly after a regression is filed? Eventually we want to penalize unresponsive daemon-hosts. Mechanism unclear — separate event type? Reduced future weight? Out of scope for v1; flag for v2.

4. **Bootstrap distribution for no-event-yet artifacts.** A merge that uses a fresh primitive with no prior `design_used` events (it's the first use ever) — the lineage walk finds the artifact but the events table has no rows for the author yet. Bounty calc skips the author. Is that right (no use = no credit) or wrong (the author authored what got used; merge-time use is itself a credit signal)? Recommend: emit a synthetic `design_used` event at merge-time bounty calc whenever the merge's leaf artifacts have no prior events (synthetic event covers the gap). Open for ratification.

5. **Merge_distributions audit table schema.** §4.3 references this for transparency / dispute resolution but I haven't sketched it (out of scope per "no schema changes"). Flag for #47 v2: needs `(merge_id, actor_id, percent_share, raw_weight, decay_applied, sybil_score_applied, finalized_at)` shape minimum. Without it, distributions are computed-but-unrecorded — disputes have no ground truth.

---

## 9. References

- Substrate: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#47, dev-2-2 — schema + emit-site map).
- v1 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §3 (five surfaces) + §7 ρ (symmetric privacy).
- Roadmap: `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` Phase B items 8-12 (substrate landing) + Phase D items 19-22 (this spec's economic activation).
- Canary spec: `docs/design-notes/2026-04-25-canary-to-patch-request-spec.md` (canary→file_bug provides the trigger surface for `caused_regression` events post-rollback).
- Variant canonicals: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (per-(goal, scope) shape mirrored in §5.2 actor_github_anchors split option).
- Memory load-bearing:
  - `project_designer_royalties_and_bounties` — N-generation decay, navigator's adjudication role, 1% take + 50% to bounty pool.
  - `project_paid_market_trust_model` — E18 override candidate; sybil resistance "must land with monetization, not after" departs from this memory's "don't scope abuse infra until abuse appears."
  - `project_user_builds_we_enable` — reputation is a primitive users compose; platform exposes data.
  - `project_q10_q11_q12_resolutions` — batch settlements <$1; informs §4.2 bucketing threshold.
  - `project_privacy_per_piece_chatbot_judged` — symmetric privacy filter on reputation queries.
- Code refs: `tinyassets/runs.py:331-377` (execute_step emit-site), `tinyassets/runs.py:434-450` (design_used emit-site), `tinyassets/branch_definitions.fork_from` at `daemon_server.py:404-411` (lineage substrate), `tinyassets/branch_versions.py:109` (publish path).
