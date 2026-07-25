> **Target-only change — sync/archive guard.** Every requirement in this change
> describes *intended future behavior*. **Nothing in sections 2-6 is built on
> `origin/main`.** `openspec archive` syncs a change's delta specs into
> `openspec/specs/` as a side effect, and `openspec/specs/` is as-built truth —
> so archiving this change while its capabilities are unbuilt would write five
> fictional capabilities into canonical truth. **No delta here may be synced and
> this change may not be archived until the corresponding implementation and its
> named acceptance evidence have landed.** Sections 1 and 7 are this lane's own
> authoring and foldback work and are the only sections it may check.
>
> **Count as of 2026-07-25: 54 tasks, 9 complete** (all eight of section 1, plus
> 7.1). The 42 tasks in sections 2-6 and the three remaining in section 7 are
> open and may not be checked by annotation, delegation, or host-gating — only by
> landed code plus its named acceptance evidence.

## 1. Author the change against the landed PLAN positions

- [x] 1.1 Verify the four blocking PLAN positions actually landed before authoring against them.
  - Verified 2026-07-25 against `origin/main` `PLAN.md`: **1A** — *Design Decisions* "Canonical store is per-domain, not one store for everything (host-approved 2026-07-25)" plus "A user's brain organization is theirs to design (host-approved 2026-07-25)"; **1B** — Scoping Rule 4 "Private-data custody is an OPEN RESEARCH QUESTION (host-approved 2026-07-25 — reopened, previously stated here as settled)" plus the matching *Open Tensions* entry; **1C** — Scoping Rule 1 "Irreducibility finding — the only door a new top-level primitive comes through (host-approved 2026-07-25)"; **1D** — Scoping Rule 3 "Guidance is community-built; the platform owns enforcement boundaries only (host-approved 2026-07-25)". *Reference: Full-Platform Architecture* carries the three matching carve-outs.
- [x] 1.2 Scope the change to the target groups with no active owner and fence it against the two sibling target changes.
  - `docs/audits/2026-07-22-openspec-full-coverage-audit.md` § *Full-platform target ownership* names three unowned PLAN-gated groups. `complete-independent-full-platform-targets` owns moderation, tray packaging, node authoring/autoresearch, and real-world handoffs; `build-forward-platform-capabilities` and its successors own boundary, data, demand, hardware, training, pooled-ownership, and token. Neither claims catalog/collaboration, discovery/remix, presence, or portability/deletion/succession/feedback. No file overlap: this lane writes only `openspec/changes/complete-plan-gated-platform-targets/`.
- [x] 1.3 Apply 1A: specify Postgres-canonical catalog rows and the index-not-copy seam against OKF-canonical commons knowledge, with bundle-wins divergence resolution.
- [x] 1.4 Apply 1C: record an irreducibility call for all eleven standalone RPCs named across architecture §§15, 16, 21, 22, and 23 (`design.md` § D2). **Result: zero new top-level primitives, zero new advertised handles.**
  - The strongest candidate, remix-from-N, fails the test on verifiable grounds rather than judgment: `tinyassets/attribution/schema.py` keys `attribution_edge` on `UNIQUE (parent_id, child_id)`, so one child already carries N parent edges. Set-valued parentage is shipped substrate; the real gap is atomicity of the N-edge write plus the existing per-artifact `credit_share ≤ 1.0` invariant holding across all parents at once. That became a requirement, not a primitive.
- [x] 1.5 Apply 1B: write portability, deletion, and succession custody-agnostic across all four modes, with custody recorded per item and the platform claiming only what it holds.
  - Includes the succession corollary (`design.md` § D7): gaining an operator role grants no access to user content in any custody mode. Under the platform-held assumption §22's SPOF inventory would have made operator succession a backdoor into vault- and host-custody content.
- [x] 1.6 Apply 1D: split enforcement from guidance in every group — visibility filtering on projections, discovery candidates and derived blocks, presence, streams, exports, and filings is platform code; selection/redaction/weighting/quorum guidance is seeded remixable commons content.
- [x] 1.7 Reuse the shipped user-buildable selector contract for discovery ranking instead of inventing a parallel one, including its purity rejection and default-selector fallback.
  - `openspec/specs/shared-goals-and-convergence/spec.md:75` (DESIGN-008) and `evaluation-outcomes-and-attribution` § *quality leaderboard*.
- [x] 1.8 Record what the four positions do **not** settle as open questions rather than inventing positions (`design.md` § *Open Questions*, six entries).

## 2. Collaborative catalog and editing

- [ ] 2.1 Implement the Postgres-canonical catalog with commons entries as rebuildable index rows, bundle-wins divergence resolution, and brain organizations as catalog subjects rather than catalog schema.
- [ ] 2.2 Implement compare-and-swap versioned writes with monotonic per-artifact versions and refusals that return current version plus a change description.
- [ ] 2.3 Implement immutable revision append, arbitrary-revision restore recorded forward as a new revision, and refusal of any attempt to edit or remove a revision record.
- [ ] 2.4 Implement content-class-bound collaboration models, refusing commons-path writes to platform code with the fork-and-PR path named.
- [ ] 2.5 Implement derived one-way external export plus a round-trip import that re-enters the ordinary authenticated write path with no version, authority, visibility, or moderation bypass and no resurrection of withheld content.
- [ ] 2.6 Implement visibility enforcement across every catalog projection including derived fields and counts, with authority resolved from the authenticated subject and no environment fallback.
- [ ] 2.7 Route every behavior as an action under an existing canonical handle and add an invariant test asserting the advertised handle set is unchanged.
- [ ] 2.8 Prove catalog behavior under the §14 concurrency/load matrix: concurrent same-artifact writers, revision-append contention, import/direct-write races, and visibility enforcement under load.

## 3. Node discovery and remix

- [ ] 3.1 Implement the single-call composite signal contract with absent-not-defaulted signals and a stable query identifier.
- [ ] 3.2 Implement selector-delegated ranking with the seeded default selector, bind-time purity rejection, and unbind fallback.
- [ ] 3.3 Implement visibility filtering across candidates and every derived block, with negative tests per block for identifier, path, title, summary, snippet, count, rank-gap, and pagination leakage.
  - This is the same defect class as the live `_related_wiki_pages` branch-describe leak on the STATUS board — a derived block escaping the predicate the direct read honors — on a much larger surface. The negative tests are the requirement, not follow-up hardening.
- [ ] 3.4 Implement commons-equal ranking with no platform-origin weighting outside the selector, and labelled cross-domain matches.
- [ ] 3.5 Implement atomic remix-from-N over the existing `attribution_edge` substrate: all-or-nothing edge and credit writes, the per-artifact `credit_share ≤ 1.0` invariant across all parents, cycle rejection, and idempotent retry on a derivation identity.
- [ ] 3.6 Implement propose-then-ratify convergence with authenticated append-only ratifications, proposer recusal, supersede-not-delete, walkable superseded lineage, and seeded remixable policy values that cannot configure away the enforcement properties.
- [ ] 3.7 Implement standing similarity interest as a durable owner-bound stored query read back through the ordinary read path, with owner-visibility-scoped matching, revocation, expiry, and cost scaling in outstanding queries rather than queries×changes.
- [ ] 3.8 Prove discovery under the §14 matrix: read-dominant load at the stated multiple, concurrent remix on shared parents, concurrent ratification of one proposal, and stored-query fan-out.

## 4. Realtime collaboration and presence

- [ ] 4.1 Implement presence as an advisory expiring per-artifact signal that never grants, denies, delays, or reserves a write.
- [ ] 4.2 Implement heartbeat expiry with a bounded margin and no requirement for explicit release, with no presence inheritance across artifacts, sessions, or principals.
- [ ] 4.3 Implement versioned-row broadcast carrying artifact and resulting version, introducing no convergent-replication substrate.
- [ ] 4.4 Implement delivery-time visibility evaluation, existence-non-disclosure on unauthorized subscription, delivery stop on authority revocation, and collaborator-identity filtering.
- [ ] 4.5 Prove full collaborative function with the realtime transport entirely down, and loss-free duplicate-free recovery on reconnection.
- [ ] 4.6 Implement subscription-bounded fan-out with documented per-connection subscription and rate bounds, explicit bounded refusals, and shed/coalesce that never degrades commit latency or success.
- [ ] 4.7 Prove realtime under the §14 matrix at the stated multiple of projected load, including hot-artifact fan-out and mass reconnection.

## 5. Data portability and deletion

- [ ] 5.1 Implement per-item custody-mode recording with unknown-fails-safe handling, and verify no portability or deletion path assumes either the platform-held or the never-store position.
- [ ] 5.2 Implement export enumeration across all owned categories with enclose-or-descriptor per item, an explicit completeness statement, partial labelling, and no silent omission.
- [ ] 5.3 Implement per-custody-mode export conformance reporting, and refuse to offer any mode that cannot satisfy enumeration and retrieval by its owner.
- [ ] 5.4 Implement graceful resumable deferral for unreachable holders, distinguishable from permanent unavailability, delivering the remainder rather than withholding it.
- [ ] 5.5 Implement cross-principal export privacy across whole items, derived material, manifests, and counts, with no elevated-role reach.
- [ ] 5.6 Implement deletion as direct bounded erasure of platform-held content with per-item erasure records, plus issued deletion obligations to other holders with confirmed/unconfirmed reporting that never counts an issued obligation as deletion.
- [ ] 5.7 Implement wiki-orphan survival: contributions remain readable and anonymous, lineage resolves to an anonymous ancestor, and no derivative is cascaded.
  - Composes over the shipped `wiki-commons` dry-run-first hash-guarded page deletion path; do not add a second deletion mechanism.
- [ ] 5.8 Implement identity detachment as an authoritative marker consulted at resolution time over append-only ledgers, honored by every resolving surface including regenerated external mirrors, with non-honoring surfaces withholding the identifier rather than leaking it.
- [ ] 5.9 Implement initiator-bound expiring confirmation, refusal of third-party initiation and of replay, and pre-confirmation disclosure of irreversibility, export-first, and possible unconfirmed items.
- [ ] 5.10 Prove portability and deletion under the §14 matrix: concurrent export and deletion for one principal, holder-offline and holder-recovery paths, deletion racing an in-flight write, and detachment consistency across concurrent resolutions.

## 6. Platform succession and feedback

- [ ] 6.1 Implement the machine-readable successor roster and its automated completeness/staleness check, reporting without blocking unrelated work.
- [ ] 6.2 Implement and verify the operator-authority boundary: succession grants no content access in any custody mode, and out-of-reach custody stays out of reach even to a successor holding every operator role.
- [ ] 6.3 Implement phase-split executable bus-factor gates reporting per-condition results, with real-value conditions unsatisfiable by an automated or simulated participant and not evaluated as launch blockers.
- [ ] 6.4 **Host/founder action — no provider can complete this.** Record the named succession principals: the operator roster holders, the real-value-cutover human co-signer(s), and the registrar successor. Recorded here the same way the umbrella records its counsel gates; 6.3's real-value gate stays unmet until this lands.
- [ ] 6.5 Author the succession runbook covering all seven required areas, including redeploy-from-nothing without any operator's personal machine, and implement the role/secret/roster staleness divergence check.
- [ ] 6.6 Implement typed authenticated feedback filings through the existing page-write path with per-invocation attribution presentation, retained authenticated binding for abuse control, per-kind dedup, and an invariant test asserting no feedback handle is advertised.
- [ ] 6.7 Implement publish-authorization enforcement over filing body, attached context, and derived summaries with explicit named refusal rather than silent stripping; seed the feedback guidance as replaceable commons content, not platform policy code.
- [ ] 6.8 Implement external mirroring as an idempotent receipted outbound effect under the existing effect-authority and receipt contract, with the commons filing canonical, retry without duplication, and lower-trust admission for unauthenticated external inbound.
- [ ] 6.9 Prove the feedback path under the §14 matrix: concurrent duplicate submissions, mirror retry under uncertain outcomes, and burst intake.

## 7. Foldback

- [x] 7.1 Validate the change strictly and obtain an opposite-provider review before pushing.
  - `openspec validate complete-plan-gated-platform-targets --strict` passes; full-tree `openspec validate --all --strict` result and the Codex cross-family verdict are recorded in this lane's `LANE_REPORT.md`.
- [ ] 7.2 Split each capability into a narrower successor change before its implementation begins, per the umbrella's D1 rule, carrying forward the irreducibility ledger (D2), the custody model (D3), the enforcement/guidance split (D4), and the selector contract reuse (D5).
- [ ] 7.3 Complete live connector canaries, a rendered chatbot conversation, and freshness-stamped post-fix clean-use evidence for every public surface before treating it as implemented.
- [ ] 7.4 **Terminal task.** Sync each capability's delta into `openspec/specs/` only in the lane where its implementation and acceptance evidence land, then archive. As of 2026-07-25 zero of the five capabilities has any implementation on `origin/main`, so nothing may be synced and this change stays active. Archiving now would write five unbuilt capabilities into canonical as-built truth.
