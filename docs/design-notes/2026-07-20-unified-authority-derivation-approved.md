> **Status: APPROVED shape (host, 2026-07-20).** This is the design the host
> selected for unified authority derivation. Authored as the Claude-family half
> of a cross-family design pair; the alternative total-unification design is at
> [`2026-07-20-unified-authority-derivation-alternative-rejected.md`](2026-07-20-unified-authority-derivation-alternative-rejected.md).
> The decision it records is summarized in `PLAN.md` § Design Decisions
> ("Unified authority derivation — one principle, three verification mechanisms")
> and § Cross-Cutting Principles. Promoted from a local session artifact so the
> PLAN.md entry has a durable, checkable source.
>
> Claims marked UNVERIFIED in §7 remain unverified. Code line references are
> accurate as of 2026-07-20 and will drift.

---

# Independent design: Authority Derivation — the simplest correct shape

**Angle of this lane:** minimize the mechanism, and adversarially find where a single unified primitive *should not* reach. My central finding diverges from a "one signed-capsule primitive everywhere" instinct: **there are three distinct unforgeable-fact mechanisms, not one.** The unifying thing is a *principle* and a *return type*, not a *constructor*. Forcing WorkOS identity, filesystem blobs, and GitHub state into the ed25519-over-JSON shape is a false unification that is worse than an honest split.

## TL;DR — recommended shape

Build one small module (`tinyassets/runtime/signed_records.py`) that exposes a generic **`Verified[T]`** return type constructible only inside the module, plus the fix-8 verify routine generalized. Make it structural not by the type system (Python can't enforce that) but by **verify-key custody**: strip raw verify/signing keys out of every consumer, so the *only* way to obtain a `Verified[Grant]` is to route through the verifier. Gate regressions with the project's own **mutation-probe test pattern** (forge the row via DML, assert the decision still rejects) — never a semantic lint. Unify only the surfaces whose authority is a *platform-decided* fact (M1). Keep content-addressed (M2: blobs, git heads) and external-authority (M3: WorkOS, GitHub) surfaces as separate boundaries that share the `Verified[T]` *return type* but not its constructor.

The load-bearing prerequisite for all of it is a **platform trust root / key composition root** — which STATUS.md's 2026-07-20 concern and the fix-8 gate both confirm is currently *missing* (`LeaseGrantIssuer` accepts any duck-typed key object; no production issuer construction exists). Without that anchor every signature is theater. Build it first.

---

## 1. The reframe: three mechanisms, one principle

The systemic defect is real and uniform: authority read from mutable/insertable state (`status`, `approved`, `claimed_by`, `workflow_outcome`, `head_sha`, `accepted_result_id`, insertable `*_events`). But the *fix* is not uniform, because the "unforgeable fact" each surface must re-derive from is of three different kinds:

| Mechanism | Fact is unforgeable because… | Verification | Surfaces |
|---|---|---|---|
| **M1 — Platform signature** | the platform signed a canonical payload with a custody-held key | ed25519 over `hash_canonical_jcs`, domain-separated (`execution_capsule.py:609,616`) | lease grant, **completion attestation** (fix-9), enrollment *approval*, claim *ownership* |
| **M2 — Content-addressing** | the identifier *is* the content hash; changing bytes changes the id | re-hash / CAS-existence at decision point | S5 blob refs (`blob:sha256:…`), git `head_sha`, capsule digest, receipt id |
| **M3 — External re-confirmation** | an external trust root owns the fact and signs it their own way | verify against that source's crypto/API at decision point | WorkOS human identity (JWT/JWKS), GitHub approval + merge state |

The reference fix (fix-8) is pure M1: `_verified_lease_grant` (`lease_store.py:574`) parses the mutable JSON, verifies the signature (`:614-620`), then asserts every mutable row column equals the signed binding (`:630-643`); the row can only *narrow or reject*, never *authorize*. That three-step — **parse → verify signature → assert row-equals-signed** — is exactly what to generalize for M1. It is *not* what M2 and M3 need.

**The unifying abstraction is the principle** — *"authority derives from an unforgeable fact, re-verified at the decision point; mutable rows/events may reject but never authorize"* — plus a **shared `Verified[T]` return type** so every authority-consuming call site looks the same. The constructors underneath are three.

---

## 2. The mechanism: simplest correct shape (A vs B vs C)

### Option A — typed `Verified[T]`, constructible only via verification
Make authority-consumers take `Verified[Grant]`, not `dict`. The only blessed constructor is the verifier.
- **Win:** an unverified authority read becomes conspicuous — any `Verified(...)` built outside the crypto module is a grep/reviewer/type-checker red flag, and the consumer *signature* demands proof.
- **Fails alone:** Python has no access control. `Verified.__new__` is reachable; the type *discourages*, it does not *structurally forbid* (asserted from language semantics, not tested). And it says nothing about legacy rows, CAS, or external identity.

### Option B — convention + semantic lint/AST gate
Keep fix-8 as a convention; add a lint that flags authority sites reading known-mutable columns.
- **Fails:** a lint can't tell an *authority* read from a *display/reject-only* read — the audit itself spends its whole second half drawing that line (`market.py:811` outcome list = fine; `lease_store.py:1096` reject-only = fine). A column-name heuristic false-positives every projection and false-negatives every new column. This is precisely the "heuristic that leaks a new edge every review round" the project memory warns against (`never-infer-identity-from-adjacent-tables`). Reject.

### Option C — recommended: A's *type* + key-custody as the *structure* + B's *goal* delivered as a mutation-probe test

Three parts, each minimal:

1. **`Verified[T]`** (from A) for conspicuousness at every call site.
2. **Verify-key custody** for the actual structural guarantee. This is the real lever and it is *already proven* in fix-8: the issuer holds the signing key and retains no store, the store holds only the verify key and cannot mint (`lease_store.py:1791-1803` vs `:246`). Generalize it: **no consumer module holds a raw verify key.** A consumer that holds no key *cannot* verify, so it *must* call `RecordVerifier.verify(...)` to get a `Verified[T]` — and code that decides authority without one is now visibly reading raw rows, which #3 catches. Key custody is what turns "convention" into "structure" in a language with no private members.
3. **Mutation-probe gate** (B's goal, not B's method): for each authority site, a test that forges the mutable row/event via raw DML and asserts the decision still raises `StoredStateCorruptError`. This is the project's existing `mutation-test-fail-closed-default` pattern (the fix-8 "RED selector" tests). It is *semantic* (tests the real decision), *fail-closed* (a newly-added authority read that trusts a forged row flips a red probe green → the harness flags it), and needs no code understanding.

**Why C is the simplest that actually closes:** the mechanism is genuinely two things — a return type and key custody — both of which fix-8 already demonstrates in one module. It adds no framework. Pure-A leaks (unenforceable, no coverage of legacy/CAS/external); pure-B leaks (semantic heuristic). C's synthesis closes structurally where it can (M1 key custody) and honestly scopes where it can't.

### API sketch (M1 core)

```python
# tinyassets/runtime/signed_records.py
@final
class Verified(Generic[T]):          # frozen; __init__ raises unless _token matches a module-private sentinel
    payload: T
    # constructed ONLY by functions in this module

class PlatformSigner:                # holds a signing key resolved from the trust root; retains no store
    def sign(self, *, domain: bytes, payload: Mapping) -> tuple[str, str]: ...

class RecordVerifier:                # holds ONE verify key (from the trust root); the only M1 verify path
    def verify(self, *, domain, signed_json, signature,
               row_bindings: Mapping) -> Verified[Mapping]:
        # parse -> verify_domain_separated_ed25519 -> assert every row_binding == signed field
        # any mismatch/parse/sig failure -> StoredStateCorruptError
```

`LeaseStore._verified_lease_grant` becomes a caller of `RecordVerifier.verify`; the completion attestation fix-9 needs is a second caller with a different domain separator. Enrollment-approval and claim-ownership become the third and fourth callers. That is the entire "unification" — four call sites, one verifier, one type.

---

## 3. Scope: what IS unified vs. what stays a separate trust boundary

| Surface | Authority today | Mechanism | In unified M1? | Why / the leak |
|---|---|---|---|---|
| S2 lease completion + terminal-replay | insertable `completed`/`result_submitted` events, mutable `accepted_result_id` (`lease_store.py:1637,1722`) | **M1** | **Yes** — fix-9 signs a completion attestation | Platform *is* the decider; canonical fix. |
| S2/S4 lease grant | signed grant already (`lease_store.py:574`) | **M1** | **Yes (done)** | The reference. |
| S3 **enrollment approval** | mutable `daemon_enrollments.status`/`owner_user_id` (`daemon_enrollment.py:566`) | **M1** | **Yes** | Platform decides "owner X approved daemon D, key K". Sign that binding; today it's a raw row. |
| S3 **device proof** | device ed25519 sig over nonce (`daemon_enrollment.py:572-580`) | M1-ish | Already sound *for possession* | Proves key-holding; the *who-owns-it* half is the enrollment-approval row above — that's the part to sign. |
| S3 **WorkOS human identity** | WorkOS JWT (LIVE) | **M3** | **No — separate** | Signer is WorkOS (JWKS/`aud`/`iss`/`exp`/rotation), not a platform ed25519 key. Different verification entirely; already live and correct. Share the `Verified[Identity]` *return type*, not the constructor. |
| S3 bearer token → request auth | unsigned `daemon_access_tokens` row + mutable daemon key/epoch (`daemon_enrollment.py:872-912`) | **M1** | **Yes** (device-key resolution) — but see uptime | `resolve_device_key` trusts stored key/thumbprint/epoch/`revoked_at` without re-authenticating the row; bind it to the signed enrollment. |
| S5 **blob refs** | mutable JSON binding `status`/size (`blob_refs.py:585-597`) | **M2** | **No — separate** | Threat is filesystem, not DML; the `sha256` in the ref *is* the proof, and `referenced_at` is out-of-DML-reach because it's on disk. Signing adds a fact that proves *less* than the hash. Re-check CAS; return `Verified[BlobRef]`. |
| **GitHub review/merge** | mutable projection `workflow_outcome`, `head_sha` (`review_queue_actions.py:608,618`) | **M2 + M3** | **No — separate** | `head_sha` is content-addressed (git); approval is a **GitHub-owned** fact — re-confirm against GitHub API at decision (merge worker already does). The projection is a *cache*, never authority. |
| **Market claim ownership** | mutable `claimed_by` (`market.py:3475`) | **M1** | **Yes, partially** | Sign the claim-ownership binding so `claimed_by` derives from a signed claim artifact. |
| **Market settlement** | authenticated actor == `claimed_by`, money via ledger (`market.py:3487`) | M3 + ledger | **No — separate** | Settlement is *actor-identity (S3) + ledger conservation* (`apply_tx`/`assert_drained`), layered. A DML forge of `claimed_by` alone still fails the "authenticate *as* that actor" gate. Don't collapse ledger invariants into a signature. |

**The honest split:** unify M1 (lease/completion/enrollment-approval/claim-ownership) behind one verifier + `Verified[T]`. Give M2 (blob, git head) and M3 (WorkOS, GitHub, ledger-backed settlement) the same `Verified[T]` *return type* so consumers are uniform, but leave their verification in their own homes. A single M1 constructor forced onto M2/M3 would (a) make the platform sign facts the hash/external-source already proves, and (b) create a second, weaker source of truth alongside the real one.

---

## 4. Uptime / live-surface risk (Forever Rule)

| Surface | Live? | Risk & rollout |
|---|---|---|
| S2 lease completion (fix-9) | No (building) | Adopt fully now. No live path. |
| **S3 WorkOS token verify** | **LIVE** (main `b91a6b07`, prod on WorkOS) — *STATUS-confirmed* | Leave as-is; already correct M3. Do **not** route it through the M1 constructor. |
| **S3 enrollment-approval signing** | Enrollment path is live | **Staged + host sign-off.** Signing approvals changes the write path. Dual-verify window: sign all new approvals, keep fail-closed-legacy acceptance for in-flight enrollments during a bounded migration, then cut over. Ripping out the mutable-`status` read in one shot strands in-flight enrollments → self-inflicted outage. |
| **Market settlement** | Liveness **UNVERIFIED** by me | Claim-ownership signing is *additive* (low risk). But "fail-closed" on a *money* path has its own severity — a signing bug that freezes settlement is an outage of a different kind. Keep the ledger (`apply_tx`/`assert_drained`) as the primary control; signing is defense-in-depth. **Host sign-off required** specifically because fail-closed-on-funds ≠ fail-closed-on-a-lease. |
| **GitHub review** | Liveness **UNVERIFIED** by me | Low risk: the merge worker already re-confirms against GitHub, so stopping the pre-enqueue projection-as-authority read is defense-in-depth, not the sole gate. |
| S5 blob | Tied to fix-9 | The `referenced_at`/CAS re-check is already the fix-9 direction; no separate live path. |

**Flag for the orchestrator:** the *only* surfaces that can adopt with zero live-path change are S2/lease and the GitHub pre-enqueue tightening. S3 enrollment-signing and market claim-signing **must** be staged with host sign-off. WorkOS token verification must be left alone.

---

## 5. Migration reality — no flag day

Existing rows/tokens/claims have no signed artifact. The governing constraint is the project memory: **never infer an owning identity from correlated side-effect rows.** So a backfill that *synthesizes* a signature by reading the very mutable columns we don't trust is forbidden — it launders unforgeable-looking authority out of forgeable state.

Transition rule per mechanism:

- **M1, not-live (S2):** fail-closed for unbound state. A terminal/grant row without a valid signed artifact → `StoredStateCorruptError`. Clean, because there are few/no real production rows.
- **M1, live (S3 enrollment, market claim):** *bounded dual-verify window*, not backfill. Sign every new artifact; during the window accept legacy records via the old verification *explicitly marked legacy*; after the window, fail-closed → existing daemons re-enroll / claims re-sign. Host-gated because the cutover is user-visible.
- **M2 (blob, git head):** *no migration at all* — content hashes and git shas are already unforgeable; you just start re-deriving at the decision point. Historical rows need nothing.
- **M3 (WorkOS, GitHub):** *no migration* — re-confirm against the external source at decision time; there was never a stored artifact to backfill.

This is a concrete payoff of **not** over-unifying: M2 and M3 surfaces migrate for free precisely because they were never supposed to store a platform-minted artifact. A false unification would have manufactured a migration burden (and a `never-infer-identity` violation) where none needs to exist.

---

## 6. Build order — the trust root is the linchpin

The hardest and most load-bearing piece is **not** `Verified[T]`; it is the **platform trust root / key composition root** that decides which signing/verify keys are legitimate. The fix-8 gate found `LeaseGrantIssuer` accepts *any* duck-typed object with `signing_key_id`/`VerifyKey`/`active` and retains it directly (gate doc lines 73-84; UNVERIFIED beyond that doc by me), and STATUS.md's 2026-07-20 concern says outright: *"S2 has no production issuer composition root."* Every signature in the M1 model is worthless until keys resolve from a pinned trust anchor.

Recommended sequence:
1. **Trust-root / key registry** (composition root): pins signing keys, exposes verify keys to `RecordVerifier` only, owns rotation/revocation. This is a shared linchpin and it *composes with* the credential-vault linchpin already in flight (PR #1469) — the vault is a natural custody backend for the signing keys. Coordinate, don't duplicate.
2. **`signed_records.py`** (`Verified[T]`, `PlatformSigner`, `RecordVerifier`) — extract fix-8's routine.
3. **S2 completion attestation** (fix-9) as the first M1 consumer — already in motion, validates the shape.
4. **Mutation-probe gate** generalized across authority sites.
5. **Staged** S3 enrollment-approval + market claim signing behind host sign-off.
6. **Additive** GitHub pre-enqueue tightening; blob CAS `Verified[BlobRef]`.

---

## 7. Risks & UNVERIFIED

- I did **not** run the mutation probes (read-only lane); exploitability of every cited site is UNVERIFIED by me and inherited from the Codex audit's own UNVERIFIED stance.
- Market and GitHub **liveness** is UNVERIFIED by me; STATUS.md confirms only WorkOS/anon-write live.
- Production issuer composition root: confirmed *absent* per the fix-8 gate doc; I did not independently re-derive it beyond that doc.
- `Verified[T]` cannot be *structurally* un-constructable in Python (asserted from language semantics, not tested) — which is exactly why key-custody, not the type, is the structural lever.
- Whether any out-of-repo consumer keys on mint-time `accepted_result_id` uniqueness (relevant to deriving-vs-deleting it): UNVERIFIED (noted in my fix-9 pre-review, unchanged).

---

VERDICT: Unify M1 platform-signed authority (lease grant, completion attestation, enrollment *approval*, claim *ownership*) behind one `RecordVerifier` + custody-only verify keys + a `Verified[T]` return type, gated by mutation-probe tests and anchored to a platform trust root built first; do NOT unify WorkOS identity (M3 JWT), blob/git-head content-addressing (M2), or ledger-backed market settlement (M3+ledger) — they share the `Verified[T]` return type but keep their own verifiers, and forcing them into the signature constructor is a false unification that also manufactures a needless, memory-violating migration.
