## 1. Reviewed foundation

- [ ] 1.1 Resolve the design's exact storage/authority and discovery seams; obtain one cross-family shape review before implementing public/storage/authority changes.
- [x] 1.2 Ship truthful HTTP answering-model receipts, preserving requested selection and unknown metadata behavior, with tests and independent review.
- [ ] 1.3 Implement normalized account-scoped discovery with source/freshness/capability/cost evidence; prove refresh adds a new model and cannot widen endpoint grants.

  September11 remaining public/storage correction is specified in
  discovery-contract-v1.md. Bounded connection-authored extraction/price/capacity
  data replace a closed service profile. Pre-build ADAPT122s corrections are
  incorporated: configuration is not proof/extra approval, accounting stays
  dimensionally closed, legacy parsing preserved, capacity scope conservative.
  Catalogue/price/benchmark interpreter now built internally and consumed by
  existing legacy decoding. Review ADAPT113s required strict custom completeness;
  corrected with legacy behavior preserved.552Windows/552actualLinux pass, zero skips; see
  docs/reviews/2026-09-11-shared-discovery-decoder-proof.md. Full source-contract
  publication, provenance, cost/capacity enforcement and unfamiliar-source
  actual execution remain unbuilt. No public payload/permission extension;
  independent exact-commit review pending.

  Exact numeric-money parsing/encoding and array-root transport are now built
  behind an internal explicit mode, retaining legacy object/float decoding.
  Real scoped-broker -> compiled catalogue tests plus expanded group pass
  646Windows/646actualLinux, zero skips after initial ADAPT corrected malformed
  string decimals without changing legacy presets; see
  docs/reviews/2026-09-11-exact-discovery-numbers-proof.md. Exact28714628 correction
  independently APPROVE92s. The source-contract publisher/consumer and enforced accounting/capacity
  remain unbuilt; no live activation or complete source-support claim.

  Mixed-source ranking now preserves each accepted source's own Interaction and
  caps through the advisory plan and picker, removing same-Interaction rejection
  and the union of maximum caps.252Windows/252actualLinux pass, zero skips; see
  docs/reviews/2026-09-11-per-source-model-policy-proof.md. Exacta8408b66 review
  APPROVE85s,18cases independently passed; no required correction.
  This is not full custom source publication/enforcement or live acceptance.

  Pure usage/capacity/request-ceiling execution shapes are now built, including
  exact observed-cost rounding and existing token/request reservation arithmetic.
  538Windows/538actualLinux pass, zero skips; see
  docs/reviews/2026-09-11-discovery-execution-proof.md. Exact review pending.
  No production consumer yet. Whole-source price/constant-effect closure,
  publication/capture and per-attempt enforcement remain required before activation.

## 2. Owner policy and execution

- [ ] 2.1 Add versioned universe-local policy and current-choice input through authenticated app ingress; test generation conflicts, isolation and legacy-pin preservation.

  September10 partial: saved preferences/CAS and authenticated unpowered GET/POST
  implemented;352 Windows and352 actual Docker Linux checks pass, zero skips.
  See saved-preferences.md and docs/reviews/2026-09-10-model-preferences-proof.md.
  Current-choice ingress and runtime consumption are still pending; do not mark
  this task complete or expose enabled UI before those pieces work.

  September10 further partial: native-default authority and policy provenance
  e8adb973 pass317 Windows/319 actual Linux (3/1skips); exact review APPROVE363s.
  Pure saved/current whole-order conversion additionally passes108 Windows/
  108 Linux,0skips, awaiting review with the actual consumer. Real ingress,
  catalogue production and serving readiness remain unconnected and not live.

  September10 integration now connects canonical current-choice ingress, real
  preference capture/catalogue production, public model-access opt-in and serving
  readiness.765 Windows/767 actual Linux passes (3/1skips), including a real
  worker-claimed MCP -> writer -> tool-loop composition with synthetic wires.
  Independent review and both-client rendered proof are pending; UI and non-home
  controls remain incomplete. See preference-consumption-proof.md in docs/reviews.

  September10 review ADAPT454s required saved-automatic compatibility with legacy
  subscription binds. Corrected without changing saved generation or explicit
  choices; final793 Windows/795 Linux passes (3/1skips). Structured discovery-expiry
  refusals and internal picker projection are also built. Independent correction
  review APPROVE208s at5167596c; public catalogue, clickable controls and live proof
  still open. Proposed shared connector read/picker contract: model-picker-surface.md.

- [ ] 2.2 Implement deterministic automatic ranking and ordered explicit fallback within fresh authority, required capabilities and permitted cost; test unscored/stale catalogues and no-paid-fallback.
- [ ] 2.3 Integrate typed capacity scopes and safe continuation into the existing router; prove account exhaustion skips siblings and completed/ambiguous tools are not replayed.

  September10 2026: implemented after capacity-shape ADAPT341s;515 Windows/
  515 actual Linux tests pass, zero skips. Real composition preserves known tool
  results across model-only fallback and holds shared/unknown outcomes safely.
  Exact964c58f2 implementation independently APPROVE417s,25 composition cases
  reproduced. See model-capacity-proof.md and model-capacity-review.md in
  docs/reviews. Public current/saved plan consumption remains unfinished.
- [ ] 2.4 Resolve the shared HTTP engine-tool-loop prerequisite and prove actual authorized tools work before enabling HTTP full-agent selection.

  September11 further internal correction: inference encoding/decoding and
  discovery executor-tool support use the installed protocol capability;
  usage semantics are declared by the discovery contract.444Windows/444actualLinux
  passes, zero skips; see docs/reviews/2026-09-11-agent-protocol-capability-proof.md.
  Six channel-ratchet loci remain and public extensible discovery is not built.
  Exact-head review and deployment pending for this correction.

  September11 internal provider-boundary correction: version-one journal replies
  now validate their canonical record directly, without a synthetic vendor HTTP
  response. Frozen parent decoder/loader differential tests and the expanded
  inference/continuation group pass259Windows/259actualLinux, zero skips.
  See docs/reviews/2026-09-11-agent-reply-record-proof.md. Exact-head review and
  the remaining discovery/executor coupling corrections are pending; not deployed.

  September10 integration shape a5689312 independently ADAPT294s; seven mandatory
  corrections incorporated in interactive-agent-runtime.md. Portable completed
  history, guarded journal retry/unused abandon, and constrained tool-shaped HTTP
  bodies now implemented locally.373 Windows/373 actual Linux checks pass,0skips.
  See docs/reviews/2026-09-10-agent-runtime-adaptations-proof.md. Actual
  runner, per-inference observer/sealing/accounting and tools-capable selection
  were subsequently implemented in the integration below. No new deployment claimed.

  September10 05:49UTC: actual writer bridge -> HTTP agent -> router -> adapter ->
  journal -> owner-bound engine client composition now implemented locally.
  Every inference seals/checks current authority, accounts the full encoded
  request and tool-shaped response, commits intent after launch admission, then
  commits exact known tool results before continuing. Unknown transport/effect
  outcomes hold without replay.409 Windows/409 actual Linux checks pass,0skips.
  See docs/reviews/2026-09-10-interactive-http-agent-proof.md. Independent exact
  implementation review ADAPT567s found one required settled-frontier close fix;
  applied and now418 Windows/418 Linux tests pass,0skips. Known results remain
  preserved and incomplete/ambiguous tools remain held; exact correction review
  APPROVE341s. Typed candidate fallback is now built locally (see2.3); saved/current policy
  ingress and clickable UI remain unfinished; no full-agent live proof yet.

  September10 partial: synchronous HTTP lookup/request/cleanup now runs in one
  owned executor Future. Cancellation drains it before router settlement; actual
  asyncio.run teardown and selected-authority slot/budget retention are tested.
  Claude implementation APPROVE224s. Legacy-only extraction PR3718 is deployed
  asb9d642646c8d with authenticated SHA/canary and five fresh app checklist passes;
  this feature branch remains unshipped. HTTP tool calls/results, canonical MCP
  execution and durable safe continuation remain required. See
  http-inference-lifecycle.md. Do not mark full-agent selection complete.

  Shared owner-bound route now implemented644d6d74, tests strengthened2b3a6a9f;
  feature implementation independently APPROVE250s. Isolated PR3728 at
  ddb343b1 passes182 Windows/185 actual Docker Linux checks (3/0symlink skips).
  Exact release APPROVE270s reproduced56 tests; deployed3b541c116e7c03:07UTC
  with protected SHA/canary evidence. App20:12PDT reports five fresh passes;
  repeatable webhook receiver needs owner scope. See engine-tool-route.md.
  Private HTTP client5406c3e4 now built and exact-head APPROVE339s;227 Windows/
  230 Linux checks pass (3/0symlink skips). See engine-tool-client.md. No live
  caller, inference loop, per-inference accounting or continuation journal yet.

  Pure agent-chat codec now implemented after shape ADAPT300s;224 Windows and
  224 actual Linux checks pass,0skips. Immutable whole-batch tool requests and
  exact same-source result continuation are fixtures only, not live dispatch.
  See docs/reviews/2026-09-10-agent-chat-codec-proof.md. Exact e6bc197b review
  APPROVE330s independently reproduced91cases; no required changes.
  All existing HTTP full-agent holds remain in place.

  September10 journal6ce30ad0 built after shape ADAPT352s applied7470b3d4.
  Windows261passes; actual Linux258passes/3existing reset failures,zero skips.
  Exact7470b3d4 baseline in identical image reproduces the same3failures.
  Independent implementation APPROVE432s,48cases reproduced; full review and
  follow-ups recovered from its exact transcript (stop-hook recap issue).
  See docs/reviews/2026-09-10-agent-turn-journal-proof.md. Private storage only;
  actual per-inference admission/tool-loop/picker integration remains pending.

## 3. User proof and delivery

- [ ] 3.1 Build the clickable active-provider/model control with switch, saved default and fallback ordering; test keyboard access, actual-versus-preferred labels and unpowered use.

  September10 partial: reply-owned provider/model footers now render for typed
  and spoken replies;206 Windows/206 actual Linux checks pass, zero skips.
  Exact6f0e6273 independently APPROVE284s,124 app tests reproduced. See
  answer-model-display.md. This is observation only, not a clickable picker;
  current-attempt state, persisted history receipts and working selection controls
  remain pending. No runtime policy or provider authority is changed.
  Observation-only release now isolated in PR3734 atc4850362;352 Windows/352
  actual Docker Linux passes,0 skips. Exact final APPROVE162s follows runtime
  APPROVE249s; corrected generated app checksum and CI brand/preview pass.
  Required CI passed with zero new baseline failures; merged2d12f846 at03:50UTC.
  Deploy34435113016 passed protected SHA containment03:55:41UTC and public
  canary--assert-handles. Fresh exact checklist prompt sent in the owned app
  tab04:00UTC. App21:03PDT reports five passes; its new footer visibly says
  Answered by codex · Model not reported. AX and screenshot verified. Webhook
  deleted receiver404 still needs owner scope, prior200/204 remains valid.
  Fresh owner21:35PDT approvals subsequently activated reusable receiver scope:
  agent reports creation201/delivery200/cleanup204, runac12a245fe114351, checklist
  complete. Duplicate approvals acknowledged without rerun. This closes that
  checklist blocker, not the separate duplicate-request or model-picker gaps.
  Controlled typed-owner continuation only, not organic/first-contact proof.
  Clickable picker still open.

  September10 current-choice send wiring now built: typed/voice/queue/retry and
  restore preserve the exact captured choice; old records remain no-override.
  153 Windows/153 actual Linux app/brand/mirror checks pass, zero skips. No enabled
  picker yet. Shared catalogue/picker shape ADAPT383s; nine required corrections
  incorporated in model-picker-surface.md before API implementation. Review this
  client wiring with that consumer; see app-model-choice-capture-proof.md in docs/reviews.

  September10 further partial: reviewed catalogue prerequisites7/9 now implemented.
  Shared serving lookup filters before its ambiguity bound; legacy home readiness
  refuses explicit/corrupt saved choices and deleted-home authority while preserving
  absent/automatic and non-home behavior.203 Windows/205 Linux passes (3/1skips).
  See model-picker-prerequisites-proof.md in docs/reviews; exact8653ae50 review
  APPROVE335s,7cases independently reproduced. Public catalogue, enabled controls
  and live proof still pending.

  September10 collection partial: typed source failures, retained incompatible
  catalogues and per-source display demotion now built;875 Windows/877 actualLinux
  pass (3/1skips). Runtime still requires an eligible candidate; no authority or
  workflow mutation. See model-catalogue-collection-proof.md. Independent review,
  registered/unaccepted/native inventory, public ingress and controls still open
  at6edbf66c; exact collection independently APPROVE341s,9cases reproduced.

  September10 public catalogue now built: shared read_graph model_options,
  current-home/admin fences, owner-registered HTTP inventory, legacy native default,
  exact bind keys/accepted constraints and full structured choices. Source failures
  are distinct from model rows; display-only results cannot activate serving.
  893Windows/895Linux pass (3/1skips). See model-options-api-proof.md in docs/reviews.
  Exact e8d69c3b API independently APPROVE428s,17cases reproduced. Actual controls,
  native explicit catalogue and live both-client proof remain; no deployment or
  workflow edits.

  September10 picker consumer now built locally: native keyboard-modal control,
  last-reported answer separate from next-message override, saved defaults and
  move/remove fallback order. Existing send/queue/voice/retry capture remains.
  Stale/expired lists and save conflicts disable new changes without rewriting
  existing choices. The save supplies an explicit current-home target so an old
  dialog cannot write to a newly rebound home. No authority is granted by choice.
  Access-confirmation UI for unaccepted sources, native explicit discovery,
  rendered preview, independent consumer review and deployment remain open.

  Legacy source read correction now identifies native/default or registered HTTP
  fixed configuration after final authority checks;106Windows/106Linux pass with
  zero skips. See legacy-model-inventory-proof.md in docs/reviews. The next exact
  access setup composition is in model-access-confirmation.md. Shape ADAPT331s
  required explicit re-enable, positive eligibility count with guarded legacy
  recovery, and server-derived access_method; all applied before implementation.
  Access controls now built locally, preserving complete accepted constraints
  and requiring separate confirmation. Actual picker36 cases and public API21
  cases pass; final37-file group1074Windows/1076Linux (3/1skips). Network-disabled
  rendered confirmation/select/order/focus checks pass at390/1280px. See
  docs/reviews/2026-09-10-model-access-ui-proof.md. No live account changed;
  exact release integration/review, deployment and app acceptance remain open.
- [ ] 3.2 Run focused cross-platform tests, independent exact-head review and CI; deploy and verify authenticated SHA/canary evidence, then ordinary rendered app use without operator workflow edits.

  September11 assignment projection now consumes resolved candidate records,
  retaining legacy behavior and current admission authority.119Windows/119Linux
  pass, zero skips; see docs/reviews/2026-09-11-assignment-projection-proof.md.
  Config's two provider-name regressions removed; four gate loci remain.
  Independent exact-commit review and complete release validation still required.
- [ ] 3.3 Sync only shipped behavior into main specs and archive this change after completion; update the goal's stage and record any remaining capability gap honestly.
