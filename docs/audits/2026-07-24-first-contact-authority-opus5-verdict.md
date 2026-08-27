# Claude Opus 5 first-contact resource-authority verdict

- Reviewer: Claude Opus 5, high effort, opposite provider to Codex
- Reviewed: 2026-07-24 PT
- Review target: draft PR #1660 plus current code/spec ownership and PRs
  #1592, #1606, #1617, and #1691
- Main reviewed by Opus: `588bae7c`
- Review method: read-only local source and git inspection plus unauthenticated
  primary-source retrieval; editing and sub-agent delegation disabled
- Verdict: `ADAPT`
- Post-review freshness: main advanced to `65cab564` through lifecycle-only PR
  #1728 while the review ran. That landing explicitly leaves
  `universe-creation` execution-authority tasks 2.0-4.7 blocked and unchecked;
  it does not discharge or contradict the verdict below.

The remainder of this file is the Opus 5 output verbatim.

---

I have enough verified evidence. Here is the review.

---

# Verdict: `ADAPT`

The **direction and core invariant are sound** and I am not asking for a redesign. But §2 (Authoritative current state), §4 (ownership table) and §8 (slices) are materially stale against `origin/main`, and two prerequisites the packet declares unowned already have owners. Folding this packet as-written would re-specify a landed primitive, re-open a closed question, and leave a live shipped secret-custody surface unowned.

---

## Question 0 — Reconciliation against current `origin/main`

Packet freshness (lines 6–11) pins `origin/main` = `0a82dbec`. Actual `origin/main` = **`588bae7c`**, **30 commits ahead**, 145 changed paths.

| PR | Commit | Landed | Packet |
|---|---|---|---|
| #1699 distributed-execution redesign | `978649fe` | rebuilt from current main + `design.md` | absent |
| #1701 dark D0 authority spine | `aa328495` | **10,445 lines** of runtime + tests | absent; §2.11 asserts the opposite |
| #1713 personification disposition | `24788949` | Section 6 dispositioned, `implementation-notes.md` | absent |
| #1715 provider-receipt premise audit | `8a3ec9a5` | **all 15 tasks gated** | absent |
| #1719 credential-vault as-built sync/archive | `1cf891c1` | change **archived**, canonical spec synced | §4 still calls it "active" |
| (+ #1723 build-forward umbrella) | `588bae7c` | new `outbound-boundary-layer` change | absent |

**Does #1660's bundle map onto D0 `Verified`/domain-record ownership, or duplicate it?** It **duplicates it** as currently written. #1660 §5 proposes designing an authority carrier that D0 already ships.

---

## Blockers

### P0-1 — §2.11 (line 108) is factually false on current main
> "B2 signed owner/daemon/job/capsule/lease/fence authority is not landed"

`tinyassets/execution_authority/` ships today:
- `records.py:179` `ExecutionGrantV1` — `owner_id`, `daemon_id`, `job_id`, `capsule_id`, `capsule_digest`, `lease_id`, `generation`, `fence`, `expires_at`, `capability_ceiling`, `idempotency_key`
- `records.py:127` `ExecutionCapsuleV1`, `records.py:221` `ExecutionCandidateV1`, `records.py:271` `ExecutionTerminalV1`, `records.py:324` `SignedExecutionRecord` (Ed25519, domain-separated), `records.py:578` `canonical_payload_bytes`
- `verified.py:79` sealed `Verified[T]`: `__init__` raises (`verified.py:90`), no subclassing (`:92`), no copy/deepcopy/pickle (`:95–105`), closure-held weak identity registry, deep-immutability enforcement (`:33–58`), issuer + mechanism binding at the sink (`verified.py:148–153`)
- `__init__.py:11–32` — one-shot bootstrap; **no raw mint callable survives import**
- 6 test modules, ~3,200 test lines

`openspec/changes/archive/2026-08-26-distributed-execution/tasks.md`: **17 checked / 91 unchecked**; tasks 1.1–1.16 (the whole D0 spine) are `[x]`.

**Replacement wording for §2.11 final sentence:**
> ~~"B2 signed owner/daemon/job/capsule/lease/fence authority is not landed; the usable remote-execution slice remains blocked on it."~~
> "PR #1699 (`978649fe`) rebuilt `distributed-execution` from current main and PR #1701 (`aa328495`) landed the **dark D0 authority spine**: sealed `Verified[T]`, the four signed `execution-{capsule,grant,candidate,terminal}/v1` records, Ed25519 domain-separated signing, canonical payload bytes, and a bootstrap that leaves no reachable mint capability. D0 has **no production composition root**; tasks 1.1–1.16 are complete and 2.1–2.9 (extraction from #1472/#1477/#1479/#1481/#1487/#1491) plus 3.x/4.x remain. This lane MUST bind the accepted authority to `ExecutionGrantV1` and MUST NOT define a second grant, lease, fence, or evidence carrier."

### P0-2 — §8 Slice B's stated blocker is discharged
Lines 394–398 claim `distributed-execution` has "1 checked, 1 partial, and 21 unchecked task rows, while its B2 identity/job/capsule/claim/lease/fence spine remains on stale open draft PRs." Both halves are wrong (17/91 checked; spine landed on main). Do not approve these counts.

**Replacement for §8 Slice B's final paragraph:**
> "Slice B is now blocked on `distributed-execution` **task 3.1 (V1)** — persist one real job, authenticate the owner daemon, mint the grant — and on tasks 2.1–2.9 extraction, not on the D0 spine. The dark package has no production composition root (`execution_authority/__init__.py`), so Slice B's first prerequisite is a reviewed composition root under task 3.1, not a new authority contract."

### P0-3 — Slice A's prerequisite is declared unowned but has a live owner
§2.6 / §4 (line 168) name residual branch `codex/fail-closed-provider-auth-overlay` @ `dd71fc1c` (PR #1609 closed) and conclude *"Residual owner unresolved… do not consume a hypothetical repair."*

The repair is **not hypothetical**. Branch `codex/credential-fail-closed-truth` @ **`bb90ee01`** (PR #1592, worktree `wf-credential-fail-closed-truth`) carries OpenSpec change **`close-universe-host-subscription-fallback`** and rewrites `tinyassets/providers/base.py:157–197` to:
- pop `*API_KEY_PROVIDER_ENV_VARS, *HOST_SUBSCRIPTION_ENV_VARS` **unconditionally** when a universe is bound (closes the all-or-nothing partial-overlay hole → abuse case 2)
- pin `CLAUDE_CONFIG_DIR`/`CODEX_HOME` to `<universe>/.credentials/{claude,codex}` (closes `$HOME/.codex` rediscovery → abuse case 4)
- raise `ProviderUnavailableError` instead of `except Exception: pass` (closes the swallowed-error hole → abuse case 3)

and ships the exact three tests: `test_partial_vault_overlay_cannot_retain_alternate_host_auth`, `test_credential_resolution_failure_is_explicit`, `test_default_cli_homes_cannot_recover_host_auth` (`tests/test_credential_fail_closed.py:104,127,195`). Main has only 4 tests, none of them these.

**Replacement §4 row:**
> `| Ambient credential isolation | PR #1546 (`92dd60c5`) landed the host-credential half; the residual is owned by OpenSpec change `close-universe-host-subscription-fallback` on branch `codex/credential-fail-closed-truth` @ `bb90ee01` (PR #1592), which implements default-deny and carries the abuse-case 2/3/4 tests | Consume that change as Slice A's prerequisite; do not re-specify the environment boundary. Branch `codex/fail-closed-provider-auth-overlay` @ `dd71fc1c` / PR #1609 is superseded and MUST NOT be cited as the owner. |`

**Verified as still-live on main** (so the packet's underlying concern is right, only its ownership is wrong): `base.py:181–183` strips host vars only when **all three** are unchanged, and `base.py:192–196` swallows every non-`ValueError`. `#1719` now records both as normative as-built limitations at `openspec/specs/credential-vault/spec.md:79` with scenarios at `:98–104`.

### P0-4 — Server-side BYOC secret custody is **shipped**, not deferred
§6 (lines 332–339) states *"The chatbot, `converse`, MCP arguments … never receive the secret"* and *"Server-side secret enrollment remains deferred."* §4 (line 176) files encrypted custody as *"no accepted owner → DEFER."*

On current main, `universe action=set_engine` — reachable through registered MCP tool `_mcp_universe` (`universe_server.py:1201` → `api/universe.py:6001` → `:5600`) — **already accepts a raw provider secret as an MCP argument and stores it server-side**:

- `api/universe.py:5673` `api_key = str(data.get("api_key", "")).strip()`
- `api/universe.py:5689–5696` `write_credential_vault(...)` with `base64.b64encode(api_key…)`, comment: *"Envelope encryption is the deferred hardening"*
- `api/universe.py:5607` docstring: *"**Deposits** a BYO LLM API key into the universe's credential vault"*

So the packet's own §6 invariant is already violated by shipped code, and the shipped vocabulary already uses **"deposit"** for a provider secret — directly colliding with the constraint that "deposit" mean market funding/escrow only. `DEFER` on this row leaves a **live** surface unowned rather than unbuilt.

**Replacement §4 row:**
> `| Server-side secret custody | **Shipped unencrypted**: `universe action=set_engine` (`api/universe.py:5600,5673,5689`) takes `api_key` via MCP `inputs_json` and stores base64-at-rest. No encrypted-custody owner exists. | Name a **retire-or-harden** owner before Slice C. Until then §6 MUST read "server-side secret enrollment is shipped in an unencrypted, MCP-argument form that this contract deprecates," not "deferred." Rename the shipped affordance away from "deposit" so the term is reserved for market funding/escrow. |`

---

## P1 findings

**P1-1 — #1691's APPROVE is not evidenced authority.** The packet calls it "the independently approved planning successor" (lines 9, 69, 165). `constrain-set-engine-provider-authority/review.md` says "The independent reviewer" / "The verifier" and **never names a model or family**; `AGENTS.md:171` requires a named opposite-provider reviewer. Its named bases are `129a68f7` then `0a82dbec` — both behind `588bae7c`. Its own line 145 concedes *"Earlier APPROVE/SHIP verdicts remain historical evidence for their named bases."*
Compounding this: **the gate is circular** — `constrain-set-engine-provider-authority/tasks.md:25` is *"Obtain the required opposite-provider verdict on #1660"*, while packet §4 (line 165) says #1660 "consumes" #1691. Replace "the independently approved planning successor" everywhere with *"the proposed planning successor in draft PR #1691 @ `2954e4cb` (base `0a82dbec`); its review artifact names no reviewer family, so it is historical input, and its task 1.4 gates on this verdict — #1660 therefore MUST NOT describe itself as consuming an accepted #1691 result."*

**P1-2 — Stale owner label.** §4 line 175 lists `backfill-credential-vault-shipped-contracts` as **active**. #1719 (`1cf891c1`) archived it to `openspec/changes/archive/2026-07-25-…`. The as-built owner is now the canonical `openspec/specs/credential-vault/spec.md`.

**P1-3 — Delta-collision on the credential-vault spec.** `close-universe-host-subscription-fallback/specs/credential-vault/spec.md` contains **only `## ADDED Requirements`** and is based at `de64fe57` (pre-#1719). Post-#1719 the canonical spec **normatively asserts the opposite** at `:79` and `:98–104`. Adding without `## MODIFIED Requirements` leaves the canonical spec self-contradictory on archive. #1723 set the precedent for handling exactly this (deliberate time-ordered contradiction recorded as a sync-lane obligation). Add a §5 sub-item requiring the fail-closed change to MODIFY those two scenarios.

**P1-4 — §3's invariant has no slot for two shipped §20 paths.** I verified `docs/design-notes/2026-04-18-full-platform-architecture.md:1530–1570`. §20.2 defines **four peer paths**. The packet's §3 admits only "requester-owned BYOC/self-host" or "accepted market grant," which excludes:
- **path 1 dry-run** — the chatbot simulates on the *user's own* client subscription; zero platform compute, zero authority needed;
- **path 2 free public request queue** — "first qualifying daemon picks it up whenever," free to user. The executing operator volunteers **its own** resources. This is safe under the core invariant but is neither requester-owned nor an accepted market grant.

Path 2's admission half is already shipped (#1694/#1696) and `storage/request_admissions.py` correctly carries no price/funding field. Add a third authority class to §3: *`volunteered_public_capacity` — the executing operator's own recorded consent to spend its own resources on a public commons request; never maintainer, never platform, and never a fallback from a failed BYOC or market route.*

**P1-5 — Slice B's receipt dependency is blocked by construction.** §8 Slice B says "Extend the accepted `provider-attempt-receipts` result seam." Per #1715, `provider-attempt-receipts/tasks.md:1.1` is **LIVE — BLOCKED** on "#1606 / R2-1a has landed or an explicitly named successor has settled fail-closed universe credential isolation, selected-engine `allowed_providers`, and call-local credential/authority evidence" — and it records that **#1691 explicitly excludes result-local receipt implementation**. All 15 receipt tasks are unchecked. Either name the successor that discharges 1.1, or move the receipt extension out of Slice B into Slice B′.

**P1-6 — Missing owner row: the live vault-clobber P1.** `STATUS.md:7` — *"BYO deposit clobbers vault: `write_credential_vault` replaces whole payload; `set_engine` destroys stored tokens (Opus5 review, confirmed)."* Owner exists: `credential-vault-single-record-upsert` on `codex/osx-vault-clobber-fix`. §2.7 describes `set_engine` as simply persisting configuration and never notes it is lossy — which breaks BYOC enrollment for Slices B/C. Add the row.

**P1-7 — `outbound-boundary-layer` omitted.** #1723 (`588bae7c`) landed two requirements that state the packet's own invariant for the sibling surface: *"Outbound authority comes only from a current user grant"* (no host/maintainer/ambient fallback, fail-closed on absent/revoked/ambiguous) and *"Value-moving boundary effects settle through the single market transport"* (no boundary-local ledger, no boundary-computed price). Add it to §4 as a **peer, non-duplicate** boundary and align §5.2/§5.4 wording to it rather than restating it.

---

## P2 findings

- **§5.2 partially re-specifies an owned shape.** `paid-market-track-e-wave-2-transport/specs/paid-market-economy/spec.md` already requires *"Bids and match decisions are versioned, authorized, and reproducible"* (`:164`), *"Paid-market claims are narrow, exact, and atomic"* (`:194`), *"Paid delivery is fence-bound, replay-safe, and dispute-aware"* (`:212`), *"One authenticated transaction transport owns all logical market accounting transitions"* (`:257`). §5.2's nine-bullet list should **cite these requirement names** and state only the residual delta, or it becomes a second market spec — the exact thing §5.2 forbids.
- **Missing citation:** the MCP authorization spec now requires **RFC 9728 Protected Resource Metadata** alongside RFC 8707; §9 omits it.
- **Terminology:** `host_daemon` (`api/universe.py:5773–5779`) means *the founder hosts a daemon* (§20 path 4), not platform compute. §5.1's "host-daemon" route reads ambiguously against "maintainer host." Rename to `founder_hosted_daemon`.
- **`Verified` scope honesty:** `verified.py:13–15` states these are *"misuse prevention rather than an in-process sandbox."* §5's "unforgeable" language must inherit that qualifier.

---

## Direct answers

**Q1 — Correct shipped behavior / actual P0?** Mostly yes, and I verified each claim independently:
- §2.2 ✅ birth is provider-free — `api/first_contact.py:27–57`, zero `call_provider`
- §2.3 ✅ — `universe_server.py:981–1005`: resolves home, calls `_converse_impl`, no authority resolution, no structured hold; `:1001–1004` collapses every failure into `"Your universe couldn't be reached right now: {exc}"` (confirms abuse case 12 is live)
- §2.4 ✅ — `universe_intelligence.py:432` reply and `:440` `extract_learning` are separate `call_provider` calls off one ordinary `UniverseContext`, no shared lineage
- §2.5 ✅ — `providers/router.py:214–216, 237–239`: `allowlist is None` returns the chain unchanged; corroborated externally by OpenRouter's `only`/`ignore` semantics
- §2.6 ✅ residuals live (see P0-3), ownership wrong
- §2.11 ✅ on admission artifacts (`storage/request_admissions.py` carries `tenant_id`/`actor_id`/`accepted_priority_weight`/`grant_generation` and **no** price/funding field), ❌ on B2 (P0-1)
- §2.1 ✅ `universe-creation` is 6 checked / 27 unchecked = 6/33, task 2.0 is the hard gate
- **Missed P0s:** the shipped MCP secret-deposit path (P0-4) and the vault clobber (P1-6).

**Q2 — Minimal, typed, immutable, unforgeable, request-scoped?** The *properties* are right, but the packet designs them in prose while D0 ships them in code. Bind to `ExecutionGrantV1` + `Verified[T]`. Nothing in §5 widens persistent provider authority: §3's "may narrow… never add to it or cross route classes" is correct and matches `_apply_allowlist`.

**Q3 — Route separation?** §5.1 separates the four venues correctly, and §5.1's *"The central server must not import a seller credential"* is the right rule; `ExecutionGrantV1.audience_daemon_id`/`daemon_id` + `fence` already enforce execution-on-the-accepted-host structurally. Two fixes: rename `host_daemon` (P2), and add the volunteered-capacity class (P1-4).

**Q4 — Budget/atomicity/replay/receipts/redaction?** §5.5 and §5.7 are well-formed and I found no logical gap for concurrent users; `idempotency_key` + monotonic `generation`/`fence` exist on all four D0 records to hang them on. §5.5(5) `unknown` quarantine is externally corroborated — Golem docs confirm either party "may terminate the agreement at will." Gap: **no budget/reservation primitive exists in any owner.** `paid-market-economy` owns settlement, not pre-invocation worst-case reservation. §5.5 must name an owner or `universe-creation` must claim it explicitly.

**Q5 — Ownership preserved / duplicates / circularity?** Ownership discipline is the packet's strongest feature — §4 and §5.2 correctly refuse to build a second router, receipt system, vault, market, or lease protocol. Defects: the #1660↔#1691 circular gate (P1-1); the unbuildable receipt dependency (P1-5); the ADDED-vs-MODIFIED spec collision (P1-3); three missing owners (`outbound-boundary-layer`, vault-clobber, `close-universe-host-subscription-fallback`).

**Q6 — Server-side custody deferred while allowing tray/endpoint BYOC first?** The *structure* is right and Slice B correctly keeps credentials on the requester-controlled executor. But the deferral is **factually wrong** — an unencrypted server-side path ships today (P0-4). Reclassify to retire-or-harden.

**Q7 — Avoids platform-as-compute / founder limits?** ✅ Yes, and this is the packet's best-grounded section. §3's *"The platform provides a control plane, not compute or hidden subsidy"* matches §20.1's removal of the reference-host pool verbatim. It also correctly preserves the legitimate host-local case, which `PLAN.md:256–257` (shared `CODEX_HOME=/data/.codex` fleet) requires.

**Q8 — Hold + chatbot UX sufficient?** §6's descriptor list is sound and correctly grounded — I confirmed the MCP authorization spec states servers **"MUST NOT pass through the token it received from the MCP client"** and requires PKCE + RFC 8707 + RFC 9728, which is exactly §6's basis. Two changes: reconcile "deposit" against the shipped `set_engine` docstring (P0-4), and add §20 path-1 dry-run as a legitimate zero-authority first-contact affordance the hold should offer.

**Q9 — Missing requirements?** §5.4's deferral of organizations/cross-principal delegation is correct and I would not widen it. `tenant_id` already exists in the admission store, so §5.5's tenant-scoped identity is buildable. Genuinely missing: **revocation propagation across the D0 `generation`/`fence` monotonic floor** (D0 owns the floor; the packet's §5.6 inter-phase recheck must bind to it, not invent a second revocation clock), and the volunteered-capacity class (P1-4).

**Q10 — Owner mapping.** No parallel lane is needed; every finding has an existing owner:

| Finding | Absorbing owner task |
|---|---|
| P0-1, P0-2 | `distributed-execution` tasks **0.2** (rebase assumptions), **2.1–2.9** (extraction), **3.1 (V1)** |
| P0-3 | `close-universe-host-subscription-fallback` (all tasks) — cite as Slice A prerequisite |
| P0-4 | **new task under `universe-creation` §2**, or a named retire-or-harden change; do **not** file under `credential-vault` as-built |
| P1-1 | `constrain-set-engine-provider-authority` task **1.4** |
| P1-2 | §4 edit only (archived) |
| P1-3 | `close-universe-host-subscription-fallback` — add `## MODIFIED Requirements` |
| P1-4 | `universe-creation` §2 (semantic authority owner) |
| P1-5 | `provider-attempt-receipts` task **1.1** |
| P1-6 | `credential-vault-single-record-upsert` |
| P1-7 | `outbound-boundary-layer` — §4 reference only, no new work |
| Q4 budget owner | `universe-creation` task **4.2**, or explicitly `paid-market-track-e-wave-2-transport` |

---

## Disposition of #1617 and #1606

- **#1617 (`codex/first-contact-authority-handshake` @ `7a568e47`) — close; retain as source-only.** The packet's §9 treatment is right. Retain **exactly one** artifact: `docs/audits/2026-07-22-request-authority-and-openspec-gaps.md` @ `7a568e47` as an immutable citation index. Do not merge it as a second requester-authority owner. Its authority contract is superseded by D0 `ExecutionGrantV1` + `universe-creation`.
- **#1606 (`codex/founder-provider-allowlist` @ `88c249d4`, 21 commits) — do not merge as an authority owner; keep open until its successor discharges receipts task 1.1.** Closing it now would strand `provider-attempt-receipts` task 1.1, which names **#1606 or an explicitly named successor** as the only unblocking condition, and #1691 explicitly excludes receipts. Retain exactly: the fail-closed request/assignment intersection at routing time and the `set_engine` persistent-destination semantics — both already claimed by `constrain-set-engine-provider-authority`. Once that change lands and receipts 1.1 names it, close #1606.

---

## Next smallest buildable slice

**Not** Slice A as written. Build:

> **Slice A0 — land the default-deny provider environment.** Rebase `codex/credential-fail-closed-truth` (`bb90ee01`) onto `588bae7c`; convert `close-universe-host-subscription-fallback/specs/credential-vault/spec.md` from `ADDED`-only to `ADDED` + `MODIFIED` (superseding `openspec/specs/credential-vault/spec.md:98–104`); confirm its three tests go red on main and green on the branch; merge.

It is self-contained, closes abuse cases 2/3/4 with tests that already exist, requires no authority contract, no D0 composition root, no receipt seam, and no custody decision — and it is the declared prerequisite of every later slice. Slice A (typed hold) follows immediately after.

---

## Primary sources retrieved (all read-only, unauthenticated, 2026-07-24)

| URL | Result |
|---|---|
| `https://www.rfc-editor.org/rfc/rfc9700.txt` | ✅ BCP — *Best Current Practice for OAuth 2.0 Security* |
| `https://www.rfc-editor.org/rfc/rfc8707.txt` | ✅ Standards Track — *Resource Indicators for OAuth 2.0* |
| `https://www.rfc-editor.org/rfc/rfc8693.txt` | ✅ Standards Track — *OAuth 2.0 Token Exchange* |
| `https://www.rfc-editor.org/rfc/rfc8785.txt` | ✅ **Informational** (not Standards Track) — *JSON Canonicalization Scheme (JCS)* |
| `https://www.rfc-editor.org/rfc/rfc9449.txt` | ✅ Standards Track — *OAuth 2.0 DPoP* |
| `https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization` | ✅ Confirms RFC 8707 + **RFC 9728** + PKCE; *"MUST NOT pass through the token it received from the MCP client"* |
| `https://openrouter.ai/docs/features/provider-routing` | ✅ `only` / `ignore` / `allow_fallbacks`; *"Only allowing some providers may significantly reduce fallback options"* — corroborates ceiling-not-authority |
| `https://docs.golem.network/docs/golem/payments` | ✅ agreements, debit notes, mid-agreement payments, either side *"may terminate the agreement at will"* |
| `https://akash.network/docs/architecture/akash-network/` + `/docs/deployments/akash-cli/overview/` | ❌ **Not independently verifiable** — JS-rendered; no extractable lease/bid/escrow text. §9's Akash lease claim remains uncorroborated. |

## Verified fact vs. design inference

- **Verified shipped fact:** every `file:line` citation above; all task counts; all commit SHAs; the D0 package contents; the `set_engine` secret path; the `base.py` residuals.
- **Design inference (mine):** the volunteered-capacity class (P1-4) and the budget-owner gap (Q4) are readings of §20 and of the owner set, not defects observable in code.
- **Not verified:** PR open/closed/draft state and PR↔branch mapping — I used no authenticated `gh` calls, so #1592/#1606/#1617/#1691 numbering rests on the prompt's mapping plus branch evidence. Per repo convention, PR state expires quickly on a saturated fleet; re-check before acting on the disposition section.

ADAPT
