---
status: active
---

# Handoffs — Real-World Pipeline (§30 Exec Spec)

**Date:** 2026-04-19
**Author:** dev (task #69 pre-draft; navigator drift-audit #64 flagged this as missing spec)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` — §30 handoff pipeline, §24 product soul / real-world-effect engine, §15.1 `discover_nodes` response, §14 scale audit.
- `docs/specs/2026-04-19-connectors-two-way-tool-integration.md` — `ConnectorProtocol`, consent model, audit log. Handoffs are a connector subtype.
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` — `nodes` table + `real_world_outcomes` jsonb column.
- Memory `project_real_world_effect_engine.md` — "fail state: gimmicky or like a toy."

**Framing (host 2026-04-19 Scenario C3):** Platform actively routes outputs to real external validators — not "here's the output, take it from here." The external handoff is a first-class fulfillment step.

---

## 1. Responsibilities boundary

### Owns

- **Handoff-kind declaration** — the `declare_handoff: true` flag on a `connector-push` output (§2.1); routing of flagged pushes through this track.
- **Outcome-claim creation** — on successful handoff, auto-write to `public.real_world_outcomes` + update `nodes.real_world_outcomes_summary`.
- **`public.handoffs` tracking table** — lifecycle states (submitted → accepted → verified → orphaned or rejected).
- **Verification pipeline** — background workers that poll external APIs (CrossRef, semantic-scholar, arXiv, LoC) and webhook-receive where supported (GitHub Releases).
- **Auto-badge logic** — verified handoffs materialize as badges on the source node; `discover_nodes` ranking reads these.
- **User attestation path** — `attest_outcome(node_id, kind, evidence_url?)` for when auto-verification isn't available.
- **Scale controls** — poll scheduler with per-provider rate-limit budgets; queue with backoff; deduplication across nodes submitting the same external artifact.

### Delegates

- **The push itself** to the connector (spec #68). Handoffs invoke `connector_invoke(name, action, payload)` — same code path as any other push; the `declare_handoff` flag is the only differentiator.
- **OAuth / API-key storage** to connectors spec #68 §4 (vault-backed).
- **Badge rendering** to web app (spec #35) + `discover_nodes` response shaping (spec #25 §3.1).
- **User attestation UI** to web app + chatbot narration.

### Not-track-concerns (explicit non-goals)

- **No re-submission of failed handoffs.** If arXiv rejects a preprint, the node operator resubmits via a new invocation. The track does not attempt auto-retry with edits.
- **No citation graph construction.** Counting citations is semantic-scholar's job. The track fetches the count; it does not build the graph.
- **No notification system for status changes.** Badge updates, verification events, rejection events flow into the standard `notifications` surface (a separate track / post-MVP). Handoffs just write ground truth.
- **No proof-of-ownership at registration.** If two users both register the same ISBN, both claims sit in the table; moderation (#36) resolves disputes. Track doesn't judge.

---

## 2. Handoff = connector push + auto-outcome-claim

### 2.1 Declaration shape

A node declares a handoff-kind output:

```yaml
outputs:
  - name: paper_submission
    kind: connector-push
    connector: arxiv
    action: submit_preprint
    target: "cs.AI"                # connector-specific; arXiv category in this case
    declare_handoff: true          # marks this as real-world-outcome-generating
    outcome_kind: paper_submission # enum — see §2.3
```

At invocation time, the runtime routes to `connector_invoke` as usual. On `PushResult.status == "ok"`, the runtime ALSO:
1. Extracts `target_ref` from `PushResult` (URL / stable ID at the external system).
2. Inserts a `handoffs` row (§5) with status `submitted`.
3. Inserts a pre-verified `real_world_outcomes` event (§4).
4. Triggers the verification worker for this handoff's `outcome_kind`.

### 2.2 Rationale for pre-verified

Per §30.2 design note: third-party acceptance of the artifact IS the verification. arXiv returning a preprint URL means arXiv accepted the submission. CrossRef returning a DOI means DOI was registered. GitHub Releases returning a release URL means the release exists.

We do NOT wait for further evidence (citations, downloads, peer-review outcomes) before marking the outcome verified. Those are **secondary** signals that get folded in by the verification worker over time — they enrich the claim, they don't gate the initial verification.

### 2.3 Outcome kinds (enum)

```
paper_submission   (arXiv, bioRxiv, SSRN, preprint venues)
doi_issuance       (CrossRef, DataCite, mEDRA)
isbn_registration  (Library of Congress PCIP, Bowker, others)
code_release       (GitHub Releases, GitLab Releases)
journal_submission (venue-specific, e.g., Nature submission portal)
patent_filing      (USPTO, EPO — post-MVP)
regulatory_filing  (FDA, EMA — post-MVP)
dataset_publish    (Zenodo, Figshare — post-MVP)
other              (fallback for community connectors — user-attested only)
```

New kinds added via connector MANIFEST extension (per spec #68 §9.2 add `outcome_kind` field).

---

## 3. Launch catalog

### 3.1 MVP handoff connectors

| Connector | Outcome kind | Auth | Action | Verification strategy |
|---|---|---|---|---|
| `arxiv` | `paper_submission` | ORCID-linked API key | `submit_preprint` | Poll arXiv API for abstract; fold in semantic-scholar citation count |
| `crossref_doi` | `doi_issuance` | CrossRef deposit API key | `register_doi` | Poll CrossRef for DOI metadata; fold in citation count |
| `github_releases` | `code_release` | OAuth2 (github connector) | `create_release` | Webhook + polling fallback (star count, fork count, release downloads via GitHub API) |
| `isbn_loc` | `isbn_registration` | Library of Congress PCIP — application-based, slow | `submit_pcip` | Poll LoC catalog API; slow feedback loop (~weeks), user-attested until verified |

These four ship at MVP per navigator's §30 recommendation (~1.5d estimate).

### 3.2 Post-MVP / community-contributed

- `biorxiv` — life-sciences preprint sibling to arXiv.
- `datacite` — alternative DOI registrar (Zenodo uses DataCite).
- `zenodo` — dataset publication + DOI.
- `figshare` — dataset publication.
- `uspto` — patent filing.
- `fda_regulatory` — regulatory-filing APIs.
- `nature_submission` + venue-specific journal portals.
- `ssrn` — social-science preprint.

Same protocol; community contributes via PR to `TinyAssets/connectors/<name>/` with `outcome_kind` declared in MANIFEST.

### 3.3 ISBN-US selection rationale

Launching with Library of Congress PCIP (Preassigned Control Number) rather than Bowker because:
- LoC PCIP is free for qualifying publishers; Bowker ISBNs cost ~$125 each for US users.
- PCIP metadata is public-API-queryable (LoC online catalog).
- Bowker requires per-user merchant accounts; friction too high for a launch connector.

Bowker ships as a post-MVP community connector once a real publisher persona needs it.

---

## 4. Verification pipeline

### 4.1 Verification states

```
handoff submitted → verified (pre-verified per §2.2)
         ↓
         enrich_loop:
           - poll external API every N hours (per §4.3 cadence)
           - fold in: citation_count, star_count, fork_count, download_count,
                      peer_review_outcome, journal_acceptance_status
           - if external record disappears (retracted / taken down):
                transition to 'orphaned'; downgrade badge; narrate to owner
           - if publisher signals rejection (journal-specific):
                transition to 'rejected'
```

### 4.2 Per-outcome-kind enrichment

| Outcome kind | Primary enrich | Secondary enrich |
|---|---|---|
| `paper_submission` | arXiv API (abstract, version count) | semantic-scholar API (citation_count, influential_citation_count) |
| `doi_issuance` | CrossRef API (registration + metadata correctness) | semantic-scholar (citation_count if DOI is on a published paper) |
| `isbn_registration` | LoC catalog API (PCIP confirmation) | (no free citation-count for books at MVP; post-MVP check Google Books / OpenLibrary) |
| `code_release` | GitHub Releases API (release metadata) | GitHub repo API (star_count, fork_count, download_count) |

### 4.3 Polling cadence

Per-handoff age-based backoff:
- Handoffs <7 days old: poll every 6h (capture early traction).
- Handoffs 7–30 days old: poll every 24h.
- Handoffs 30–180 days old: poll every 7d.
- Handoffs >180 days old: poll every 30d.
- Handoffs >2 years old: poll every 180d (essentially frozen state but not retired; enables long-tail citation tracking).

This gives ~100× load reduction for the long tail while keeping recent handoffs responsive.

### 4.4 Webhook support

Where supported:
- **GitHub:** subscribe to `release`, `watch`, `fork` webhooks on the owning repo. Webhook event → enrich synchronously → update `real_world_outcomes`. Polling fallback still runs (webhooks miss events under rare network conditions).
- **arXiv / CrossRef / LoC:** no webhook support. Polling only.
- **Semantic-scholar:** no webhook; polling.

Webhook endpoint lives at the MCP gateway (spec #27 routes `/webhook/<provider>` to the handoff worker). HMAC signature verification per provider spec.

### 4.5 Dedup

Same external artifact (same DOI, same arXiv ID, same ISBN, same GitHub release URL) submitted by multiple nodes is dedup'd at the verification-worker layer:
- A `real_world_outcomes.external_id` unique-per-outcome-kind constraint prevents double-counting.
- Second+ submissions reference the existing outcome claim but attribute the submission to each originating node.
- Disputed attribution → moderation queue (spec #36).

---

## 5. `handoffs` tracking table

```sql
CREATE TABLE public.handoffs (
  handoff_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id uuid NOT NULL REFERENCES public.nodes(node_id),
  invocation_id uuid NULL REFERENCES public.invocations(invocation_id),
  user_id uuid NOT NULL REFERENCES auth.users(id),
  connector_name text NOT NULL,
  outcome_kind text NOT NULL
    CHECK (outcome_kind IN (
      'paper_submission', 'doi_issuance', 'isbn_registration', 'code_release',
      'journal_submission', 'patent_filing', 'regulatory_filing',
      'dataset_publish', 'other'
    )),
  target_ref text NOT NULL,              -- URL or stable external ID
  external_id text NOT NULL,             -- normalized (e.g., arxiv:2404.01234, doi:10.1234/foo)
  status text NOT NULL DEFAULT 'submitted'
    CHECK (status IN ('submitted', 'accepted', 'verified', 'rejected', 'orphaned')),
  outcome_claim_id uuid NULL REFERENCES public.real_world_outcomes(outcome_id),
  submitted_at timestamptz NOT NULL DEFAULT now(),
  verified_at timestamptz NULL,
  last_polled_at timestamptz NULL,
  poll_interval_hours int NOT NULL DEFAULT 6,
  enrichment_cache jsonb NOT NULL DEFAULT '{}'::jsonb,
  attestation_source text NOT NULL DEFAULT 'auto'
    CHECK (attestation_source IN ('auto', 'user', 'admin'))
);

CREATE UNIQUE INDEX handoffs_external_dedup
  ON public.handoffs (outcome_kind, external_id);

CREATE INDEX handoffs_poll_schedule
  ON public.handoffs (last_polled_at)
  WHERE status IN ('submitted', 'accepted', 'verified');

CREATE INDEX handoffs_node_summary
  ON public.handoffs (node_id, status, submitted_at DESC);

ALTER TABLE public.handoffs ENABLE ROW LEVEL SECURITY;
CREATE POLICY handoffs_owner_read
  ON public.handoffs FOR SELECT USING (user_id = auth.uid());
CREATE POLICY handoffs_public_summary
  ON public.handoffs FOR SELECT USING (status IN ('verified', 'accepted'));
-- Public read of verified handoffs (feeds discover_nodes badges).
-- Owner-only read of submitted/rejected/orphaned (protects in-flight + failed attempts from public).
```

**Why owner-only for submitted/rejected/orphaned:** a failed arXiv submission or an orphaned DOI is often private business (researcher pulled a paper; publisher withdrew a DOI). Only verified + accepted are public.

---

## 6. Handoff initiation

### 6.1 Chatbot-initiated

```
handoff_node_output(
  node_id: uuid,
  invocation_id: uuid,         # which specific run produced this output
  output_name: str,             # matches the node's declared output
  override_target: str?,        # optional — overrides node's declared target
) -> { handoff_id, outcome_claim_id, status, target_ref, next_verify_at }
```

**Flow:**
1. Gateway routes to track N handoff RPC.
2. Validates node's output declares `declare_handoff: true` for `output_name`.
3. Pulls connector name + action + destination from node declaration.
4. Invokes `connector_check_consent(connector, destination_key)` per spec #68 §6; if no consent, returns `consent_required` so chatbot can prompt.
5. Invokes `connector_invoke(connector, action, payload)` — payload is the node's output artifact.
6. On push success, inserts `handoffs` row + pre-verified `real_world_outcomes` event (atomic; transaction).
7. Schedules verification worker pickup.
8. Returns to chatbot.

### 6.2 Node-autonomous (post-publish execution)

When a node runs end-to-end on a daemon host and produces a handoff-declared output, the daemon invokes the same `handoff_node_output` RPC on behalf of the originating user. Consent must be pre-granted (per §6.1 step 4); if not, daemon pauses + surfaces to user via notification. Daemon does NOT auto-grant consent.

### 6.3 Irreversible action gating

Per spec #68 §5.2, most handoff kinds are **irreversible** (arXiv submit, DOI issue, ISBN register, GitHub release). Chatbot MUST confirm per invocation — consent gate alone is insufficient. Flow:

1. Chatbot: "I'm about to submit this paper to arXiv cs.AI. Proceed?"
2. User: "yes"
3. Chatbot invokes `handoff_node_output`.

For daemon-autonomous handoffs, the per-invocation confirm requirement is encoded in the node's declaration — nodes with `side_effect_class: irreversible` outputs MUST declare `requires_user_confirm: true`, which the daemon respects by pausing + asking.

### 6.4 Dry-run support

Test-runs within a `node_authoring.test_run(dry=true)` from track N (spec #67 §2.4) DO NOT invoke real handoffs. Instead, `simulated_effects` captures "would have submitted to arXiv cs.AI with payload X; external_id would be generated on real submit." Dry-run never creates a `handoffs` row.

---

## 7. User attestation path

### 7.1 When to use

Auto-verification isn't always available. Scenarios:
- Connector doesn't exist yet ("I just submitted my paper to Nature via their web portal, which we haven't built a connector for").
- Connector exists but outcome is long-delayed ("my preprint was just peer-reviewed and accepted by Cell"; verification is a journal-internal signal with no public API).
- Manual real-world outcome ("my book got picked up by Penguin Random House").

### 7.2 RPC

```
attest_outcome(
  node_id: uuid,
  outcome_kind: enum,
  target_ref: str,              # URL to the evidence (published paper, article, press release)
  narrative: str,               # user's description
  external_id: str? = null,     # optional — normalized ID if available
) -> { attestation_id, outcome_claim_id, badge_variant: 'user_attested' }
```

### 7.3 Badge distinction

Two variants:
- `verified` — auto-verification succeeded (third-party system confirmed).
- `user_attested` — user claimed; verification unavailable or pending.

Distinct in UI (different color / icon). Ranking in `discover_nodes` weights `verified` ~3× higher than `user_attested` (per §24.5 product-soul directive — real outcomes matter more than self-reports).

### 7.4 Moderation

User-attested claims that look wrong ("I cured cancer" with no evidence URL, or a known-fraudulent URL) flow through standard moderation (spec #36). Admins can downgrade `user_attested` to `disputed`, which removes the badge + flags the node.

### 7.5 Schema additions (minimal)

```sql
ALTER TABLE public.real_world_outcomes
  ADD COLUMN attestation_source text NOT NULL DEFAULT 'auto'
    CHECK (attestation_source IN ('auto', 'user', 'admin', 'disputed')),
  ADD COLUMN attestation_narrative text NULL,
  ADD COLUMN evidence_url text NULL;
```

Existing verified outcomes keep `attestation_source = 'auto'` by default.

---

## 8. Scale concerns

### 8.1 Polling load

At steady state (post-launch), estimate:
- 100 active nodes with handoffs initially.
- Average 2 handoffs per node.
- 50% in <7-day window (6h polls), 30% in 7-30d (24h polls), 20% older (≥7d polls).

Per-day poll volume:
- Hot (100 × 4 polls/day): 400
- Warm (60 × 1 poll/day): 60
- Cold (40 × 0.15 polls/day): 6
- **Total: ~466 polls/day at MVP.** Well within all providers' rate limits.

At 10× growth (1000 nodes, 2000 handoffs):
- Hot (1000 × 4): 4000 polls/day
- Warm (600 × 1): 600
- Cold (400 × 0.15): 60
- **Total: ~4,660 polls/day.** Still under rate limits for all launch providers:
  - arXiv: polite-pull guidance ~1 req/3s → 28,800/day ceiling.
  - CrossRef: 50 req/s polite pool → 4.3M/day ceiling; public pool lower.
  - semantic-scholar: 1 req/s anonymous → 86,400/day ceiling.
  - GitHub: 5000 req/hour authenticated → 120,000/day ceiling.
  - LoC: no documented rate limit but polite-pull expectation.

At 100× growth (10K nodes, 20K handoffs), poll volume is ~50K/day — still under ceilings but approaches semantic-scholar limit. Mitigation: cache citation counts with 7d TTL instead of polling on every verify cycle. Not MVP.

### 8.2 Rate-limit budgets

Per-provider token bucket in Postgres (or Redis — evaluate at track-K scale):

```sql
CREATE TABLE public.handoff_rate_budget (
  provider text PRIMARY KEY,
  tokens_available int NOT NULL,
  refill_tokens_per_sec float NOT NULL,
  max_tokens int NOT NULL,
  last_refill_at timestamptz NOT NULL DEFAULT now()
);

-- Worker acquires before polling. On 429 from provider, halve tokens_available + extend
-- refill-pause by 10×.
```

### 8.3 Worker architecture

Single-writer verification worker (Supabase Edge Function scheduled every 10min):
1. Queries `handoffs WHERE last_polled_at IS NULL OR last_polled_at < (now() - poll_interval_hours * interval '1 hour')`, limited to N per cycle (N=100 at MVP).
2. Per row: acquires rate-limit token → poll external API → update `enrichment_cache` → update `real_world_outcomes` → set `last_polled_at`.
3. On 429 / 5xx: backoff token budget + requeue for next cycle.

Single-writer avoids coordination overhead; if it saturates, add a second worker partitioned by `outcome_kind`.

### 8.4 Dedup + coalescing

If 50 users all submit papers citing the same prior arXiv paper (as a reference), we're not counting that prior paper 50 times — `handoffs.external_id` unique index catches it. Each submission gets its own `handoffs` row (the node's submission) but joins to one `real_world_outcomes` row per external_id.

### 8.5 Cold-start verification

On first verify of a submitted handoff, external_id might not yet be live in the destination service (arXiv indexing takes up to 24h; CrossRef takes minutes to hours). Expected. Worker treats "not yet found" as "keep polling per schedule" — does NOT mark orphaned until 30 days elapsed with no confirmation.

---

## 9. Dev-day estimate

Navigator's §30.5 was ~1.5d. Revising:

| Component | Dev-days |
|---|---|
| `declare_handoff` runtime routing + handoff RPC entry point | 0.2 |
| `handoffs` table + indexes + RLS + dedup unique index | 0.15 |
| Outcome-claim auto-write transaction | 0.1 |
| arXiv connector + enrichment (abstract + semantic-scholar citation) | 0.3 |
| CrossRef DOI connector + enrichment | 0.25 |
| GitHub Releases connector + webhook receive + polling fallback | 0.3 |
| ISBN-LoC connector + PCIP submit + catalog polling | 0.25 |
| Verification worker + scheduler + rate-limit budget | 0.3 |
| `attest_outcome` + user-attestation RPC + schema additions | 0.15 |
| Badge-variant + `discover_nodes` signal integration | 0.1 |
| Tests (unit per connector + integration per verification loop) | 0.3 |
| **MVP subtotal** | **~2.4** |
| Deferral: ISBN-LoC to v1.1 (slow feedback; often user-attested anyway) | −0.25 |
| **MVP-narrowed subtotal (3 launch connectors)** | **~2.15** |

**Revision rationale:** navigator's 1.5d assumed connector code existed. With connectors spec #68 landing separately, handoffs need the orchestration layer + verification pipeline + worker infrastructure on top of raw connectors. Actual spec scope is ~2.4d full MVP / ~2.15d narrowed.

**Recommend MVP-narrowed (~2.15d)** — 3 launch handoff connectors (arXiv + CrossRef + GitHub Releases) covers Scenario C3 launch story. ISBN-LoC ships v1.1 after real publisher persona validates the flow.

---

## 10. Acceptance criteria

**Gate 1 — Scenario C3 end-to-end:**
- User-sim research persona drafts a paper via a vibe-coded node (spec #67).
- Invokes `handoff_node_output(..., output_name="preprint_submission")`.
- Chatbot confirms irreversible action + consents.
- Connector submits to arXiv test-endpoint; receives URL back.
- `handoffs` row created with `status='verified'`; `real_world_outcomes` claim auto-created.
- Badge appears in `discover_nodes` response for the source node.
- 6h later, verification worker polls semantic-scholar; citation count (0 initially) cached.

**Gate 2 — webhook + polling fallback:**
- GitHub release webhook fires → `real_world_outcomes` updates within 5s.
- Simulated missed webhook → next poll picks up the event within 6h.

**Gate 3 — user attestation:**
- User invokes `attest_outcome(kind='journal_submission', evidence_url=..., narrative='Accepted by Cell 2026-07')`.
- `real_world_outcomes` row created with `attestation_source='user'`, `verified_*_count` fields update with `user_attested` variant.
- `discover_nodes` ranks this node below a node with equivalent `auto` verification (§7.3 weighting).

**Gate 4 — rate-limit respect:**
- Simulated arXiv 429 → worker halves tokens → retries next cycle, no immediate re-hit.
- 4,660 polls/day (10× launch scale) — no 429s from any launch provider.

**Gate 5 — dedup:**
- Two different nodes submit to the same arXiv preprint (e.g., one is forking + re-submitting) → second hits unique-constraint; handoff rejects with `duplicate_external_id`. Narration explains.

**Gate 6 — orphan detection:**
- External record disappears after 30d (preprint withdrawn) → status transitions `verified → orphaned`; badge downgrades; owner notified via standard notification channel.

---

## 11. OPEN flags

| # | Question |
|---|---|
| Q1 | **arXiv submission account ownership.** arXiv requires endorsement from an established researcher for new submitters. Platform-mediated endorsement? Use user's own ORCID-linked submission identity? Recommend user's own ORCID (preserves authorship attribution); platform acts as intermediary but submission is the user's. |
| Q2 | **CrossRef deposit account ownership.** CrossRef requires a paid membership for DOI issuance. Platform holds a single CrossRef membership + sub-accounts per user? Or per-user direct memberships? Recommend platform-owned membership at MVP (user pays a platform fee to cover), direct memberships as post-MVP option for publishers. |
| Q3 | **ISBN costs.** LoC PCIP is free but slow; Bowker is fast but $125/ISBN. At MVP ship PCIP-only; user pays Bowker directly if wanted. Confirm posture. |
| Q4 | **Retraction handling.** If an arXiv paper is retracted by the author post-verification, our orphan-detection (§10 Gate 6) catches it. But what about outcome-claims that the author doesn't want downgraded (disputed retraction)? Recommend: moderation queue entry, 30d hold before auto-orphaning post-retraction signal. |
| Q5 | **Journal submission connector trust.** Nature/Science/Cell submission APIs often require institutional credentials + manuscript-review processes before the journal APIs even accept submissions. Unlike arXiv (preprint), journal submission is a multi-step process. MVP: keep journal-submission-via-connector out of MVP; use `user_attested` path for journal acceptances at launch. Confirm. |
| Q6 | **Semantic-scholar citation freshness.** Their API is public + free but rate-limited; post-MVP do we negotiate an API partner-level agreement for higher QPS? Recommend yes if >10K handoffs with paper kind; not MVP. |
| Q7 | **Claim dispute UX.** Two nodes claim the same ISBN; moderator rules one wins. How is the loser narrated? Recommend: narrated as "this work is attributed to node X elsewhere" with a link to the moderation-resolution record; loser's badge downgrades to `disputed`. |
| Q8 | **External_id normalization.** Different services use different IDs for the same artifact (DOI vs arXiv ID vs journal citation). At MVP, normalize per `outcome_kind`; post-MVP, cross-link (this arXiv paper has this DOI after publication). Recommend MVP per-kind; add cross-link table v1.1. |
| Q9 | **Daemon-initiated handoffs + user absence.** Daemon running autonomously produces a preprint; user is asleep; paper must be submitted by deadline. Default policy: daemon SHOULD NOT auto-submit irreversible-kind handoffs if user hasn't pre-granted per-invocation consent for this specific submission. Recommend: daemon pauses + notifies; user approves on next check-in. |
| Q10 | **External-ID privacy.** If user's arXiv submission URL is public (arXiv is public-by-default), no privacy issue. But DOIs and ISBNs can be pre-registered before the work is publicly announced — public listing in `real_world_outcomes` may tip off a researcher's competitor. Recommend: add `public_at` field to `handoffs` with default-NULL (private until explicitly set); chatbot narrates + confirms before setting public on DOI/ISBN kinds. |

---

## 12. Cross-references

- Design note §30 — the source directive.
- Design note §24 — product soul + real-world-effect engine.
- Spec #25 full-platform-schema-sketch — `real_world_outcomes` table structure + `discover_nodes` signal block.
- Spec #27 MCP-gateway-skeleton — `/handoff_node_output` + `/attest_outcome` routes + `/webhook/<provider>` for push-events.
- Spec #67 track N (vibe-coding) — `node_authoring.test_run(dry=true)` skips real handoffs.
- Spec #68 connectors — `ConnectorProtocol`, consent gate, audit log. Handoffs = connector subtype with verified-outcome side effect.
- Spec #36 moderation — disputes + disputed-badge states.
- Spec #35 web app — badge rendering + user-attestation UI.
- Memory `project_real_world_effect_engine.md` — north-star framing.

---

**Status on dispatch:** ready to implement. Spec is executable without further research. Estimated MVP: **~2.15 dev-days** (3 launch handoff connectors: arXiv + CrossRef + GitHub Releases). Full (4 connectors incl. ISBN-LoC): ~2.4 dev-days.
