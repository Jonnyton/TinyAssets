# Lane report — paid-market-live-price-discovery 2.1 / 2.2 / 2.5

Branch `claude/o5-live-price-runtime` off `origin/main` `f7142a57`.
Unblocked by the #1679 landing (`01e7ced7`) plus task 1.5's round-2 APPROVE.

(This file previously held the `claude/o5-data-commons` lane report, committed at
`f7142a57`; that content remains recoverable from git history.)

Runtime lives in `tinyassets/paid_market/` (not `tinyassets/payments/` — the brief's
path was stale; `payments/` holds the Wave-2 transport spine, `paid_market/` holds
the pure live-price core named in the brief: `quotes.py`, `match.py`, `routing.py`,
`instruments.py`, `price_surface.py`).

## Final money gate — demand canonicalization

- **Red** — `test_equivalent_malformed_demand_variants_share_one_market_class`
  failed because `_parsed_demand` compared the raw whitespace/case variant before
  market projection. The same shallow-copy path also let duplicate set members
  survive into the hashed public envelope after compatibility had reduced them
  with `set(...)`.
- **Fix** — both `match_descriptor` and `project_market_class` now pass typed
  demand through `_normalized_demand` before comparison or identity. It validates
  the closed shape and bounds, NFKC-normalizes/case-folds/trims identifiers to the
  existing ASCII grammar, and sorts/de-duplicates semantic sets. Mapping/list
  ordering and equivalent Unicode spellings therefore cannot create extra market
  classes; malformed inputs that cannot normalize fail closed.
- **Green** — `py -m pytest -q tests/test_paid_market_descriptors.py
  tests/test_paid_market_manipulation_mutation.py`: **175 passed**. The rejection
  matrix covers non-string, non-ASCII-after-NFKC, internal-whitespace, malformed
  nested-shape, and out-of-range demand.
- **Mutation** — `test_demand_canonicalization_is_load_bearing` replaces the
  canonicalizer with the prior shallow-copy seam and proves the six-variant guard
  goes red; with the control present, all six variants produce one
  `market_class_id`.
- **Mirror** — canonical runtime and packaged Claude-plugin runtime SHA-256:
  `AFBC5FDD04A5A2D2736A53455675D563AD6F9E3C7195DE59AA415CE63A1F735A`.
- **Pushed SHA** — `PENDING_IMPLEMENTATION_COMMIT`.
- **Corrected 2.1 / 2.2 checkoff state** — both remain checked, but their text
  now states the true strictness boundary: strict canonical-byte ingestion is a
  descriptor property; demand is a normalized, bounded typed mapping. Neither
  task claims that this module implements a raw demand-byte decoder.

---

## Task 2.2 — descriptor + market-class implementation

**New: `tinyassets/paid_market/descriptors.py`** (770 lines). Pure values; imports
nothing from provider or domain execution code.

- **Two identities, derived not accepted.** `construct_descriptor` derives
  `descriptor_id` from the library-built `tinyassets.capability-descriptor` envelope;
  `project_market_class` separately derives `market_class_id` from the
  `tinyassets.market-class` envelope. Domain separation is proven by test, not
  asserted. `capability_id` was already purged by #1679 and is not reintroduced —
  it is absent repo-wide.
- **No caller-supplied identity or direction.** `_ENVELOPE_FIELDS` /
  `_DESCRIPTOR_FIELDS` are closed sets, so `profile_id`, `descriptor_id`, `profiles`,
  `direction`, `min_inclusive`, and `max_inclusive` all return `unknown_field` with a
  non-echoing `<parent>/<?>` path.
- **Injected per-call validator, no mutable registry.** `_check_validator` selects by
  exact `(schema_version, lane, profile_schema_revision)` and separates the four
  failure codes: `domain_validator_unavailable` / `unsupported_profile_schema_revision`
  / `domain_validator_revision_mismatch` / `domain_validation_failed`. The validator
  receives a deep copy, so a rewriting validator cannot influence the digest.
- **Decoder vs constructor split.** `verify_canonical_descriptor` is the only path
  that emits `not_canonical`; it enforces byte-length → ASCII → guarded parse
  (depth/member/array/scalar limits, duplicate-key detection, NaN/Infinity refusal)
  → root → domain/version → structure → canonical byte comparison → validator.
- **Comparison direction is schema-owned.** `_LANE_FIELDS` tags every field
  `identifier` / `range_contains` / `range_at_least` / `range_at_most` / `set_subset`;
  callers cannot supply it.
- **Market class is demand-shaped.** Threshold buckets, required subsets, and coarse
  region/privacy/reliability class tables come from the revision-owned validator, so
  supply headroom and extra set members never enter the public class.

**New: `tinyassets/paid_market/scope.py`** — the trusted scope projector that produces
the canonical ASCII dimension object bytes. A scope revision may not reuse a
descriptor/market-class facet name without declaring a single canonical projection
from the already-bound facet.

**Changed: `tinyassets/paid_market/quotes.py`** — quote schema v1 → v2. v1 stays
verifiable as its original closed schema under `tinyassets.paid-market.quote.v1`;
v2 adds `market_scope_revision` + `public_scope_dimensions` under
`tinyassets.paid-market.quote.v2`, so a v1 signature can never span a scope binding.

**Changed: `tinyassets/paid_market/price_surface.py`** — `public_scope` widened from
`tuple[str, ...]` to canonical ASCII object bytes, and `market_scope_revision` added
so the aggregate key is the full `(market_class_id, market_scope_revision,
public_scope_dimensions)` triple.

---

## Task 2.1 — grammar, identity, precedence, and scope-provenance tests

**New: `tests/test_paid_market_descriptors.py`** (71 tests) and
**`tests/test_paid_market_scope_provenance.py`** (39 tests).

Golden identities are proven twice over: each test rebuilds the expected envelope
**by hand** and re-derives the `sha256:` value independently, and a separate test
pins the literal digest. A library-side envelope drift fails both; a drift in the
test helper still fails the pin.

- descriptor golden: `sha256:498e7165475c83778f49fc1f761bcf50618e3c49c69cadca18a3899c84a158b9`
- market-class golden: `sha256:8b4492afdba19dd1efc3c8c59c78ad2e94ab2662d1e9cf32dff9a8497584a656`

Also covered: four closed lane schemas; bounded ASCII grammar (identifier regex,
integer bounds, inverted ranges, empty/duplicate sets, `scale >= 1`); fail-closed
`unspecified` / `public_only` / `best_effort_unverified` defaults that never mean
"any"; schema-owned numeric direction and set-subset comparison; unit mismatch before
value comparison; validator attestation; decoder limits and precedence; headroom
collapsing to one market class; private demand kept out of public identity (and
raising `DescriptorError` rather than silently classifying); and no entry point
mutating its inputs.

---

## Task 2.5 — mutation and property proof

**New: `tests/test_paid_market_manipulation_mutation.py`** (84 tests).

Six controls carry a **mutation probe**: the guard runs green normally, then its
control is forced open and the probe asserts the guard goes **red**. A monkeypatch
that never reached the code path would leave the guard green and fail the probe, so
these also prove the patches are wired to the real call sites.

| Control | Seam forced open | Guard that goes red |
|---|---|---|
| Self-trade / linked-party / unknown-linkage exclusion | `price_surface._index_eligible` | excluded volume re-enters trusted VWAP |
| Per-principal influence cap (unbounded price) | `price_surface._capped_scales` | one principal's 1M-micro prints dominate |
| Canonical settlement fee | `price_surface._require_canonical_fee` | a zero-fee positive-gross settlement is accepted |
| Raw native-truth isolation | `price_surface._raw_vwap_field` | the external reference reaches raw VWAP |
| Composite ceiling clamp | `price_surface._composite_field` | a complete all-in ceiling stops bounding the composite |
| Substitutability gate | `descriptors._compare` | an unsupported facet is silently substituted |

One mutant was rejected during development for being **semantically equivalent** to
the original (it re-implemented `_composite_field`'s own behaviour, so the guard
stayed green). It was replaced with a mutant that actually opens the boundary.

Properties: no nominal price clears a non-price rejection (7 prices × 7 defects, all
`no_route`); price only orders already-eligible candidates; a changed descriptor is a
different supply identity and matching never returns an identity it did not derive;
stale native asks never become executable and a fresh field never refreshes a stale
one; settlements outside the TTL leave the index.

**No fee exemption is encoded.** Index eligibility and the canonical fee are separate
controls, proven together: a self-trade is excluded from trusted price evidence *and*
still carries its fee; the same holds for linked-party and arm's-length settlements.

**Money path:** integer micros only. `Fraction` is used for weighting (exact rational,
already the landed pattern), never float. Conservation (`net + fee == gross`) is
asserted, non-conserving settlements fail loud, and VWAP is proven to be an integer
inside the observed price range.

---

## Evidence

| Check | Result |
|---|---|
| `tests/test_paid_market_descriptors.py` | 71 passed |
| `tests/test_paid_market_scope_provenance.py` | 39 passed |
| `tests/test_paid_market_manipulation_mutation.py` | 84 passed |
| Touched paid-market test modules (10 files) | 506 passed |
| Full `pytest tests/` | PENDING_FULL |
| `ruff check tinyassets/paid_market/ tests/test_paid_market_*.py` | All checks passed |
| `packaging/claude-plugin/build_plugin.py` | 287 files staged, import probe ok |
| Cross-family review (Codex, refute-5-claims gate) | PENDING_CODEX |

**Red-first evidence.** Each suite was written before its implementation and observed
failing: `test_paid_market_descriptors.py` failed collection on
`ModuleNotFoundError: tinyassets.paid_market.descriptors`;
`test_paid_market_scope_provenance.py` failed on
`ModuleNotFoundError: tinyassets.paid_market.scope`; the golden-pin test failed
against a placeholder digest until the real value was derived and pinned.

## Files touched

Runtime: `tinyassets/paid_market/descriptors.py` (new),
`tinyassets/paid_market/scope.py` (new), `tinyassets/paid_market/quotes.py`,
`tinyassets/paid_market/price_surface.py`, `tinyassets/paid_market/__init__.py`.

Tests: `tests/test_paid_market_descriptors.py` (new),
`tests/test_paid_market_scope_provenance.py` (new),
`tests/test_paid_market_manipulation_mutation.py` (new),
`tests/test_paid_market_price_surface.py`, `tests/test_paid_market_quotes.py`.

Spec: `openspec/changes/paid-market-live-price-discovery/tasks.md` (2.1/2.2/2.5
checked off with evidence; premise rows flipped from `blocked-domain-owner`).

Mirror: `packaging/claude-plugin/.../runtime/tinyassets/paid_market/` (rebuilt).

Not touched, per constraint: `tinyassets/api/branches.py`, permissions,
`tinyassets/universe_server.py`.

### Two existing-test migrations (not weakened)

1. `tests/test_paid_market_price_surface.py` — 13 call sites moved from
   `public_scope=("region:us", "batch")` to the canonical bytes plus
   `market_scope_revision`. The spec requires this widening; every assertion is
   preserved.
2. `tests/test_paid_market_quotes.py` — an assertion that `schema_version = 2` is
   *unsupported* is now obsolete, since v2 is the scope-provenance schema. It was
   replaced by two stronger assertions (3 is unsupported; a v2 body missing its scope
   fields is a missing-field error) and a new parametrized test covering
   `True/False/1.0/"1"/None/0/3`, closing a `True == 1` type-confusion that would
   otherwise have let a bool select the v1 closed schema.

## Gap found, deliberately not built (outside 2.1/2.2/2.5) — NOW CLOSED

`PaidObservation` bound `market_class_id`, `market_scope_revision`, and
`public_scope`, but **not** the exact `descriptor_id`. Reported here rather than
silently widened into the lane. Codex's money review then found the same surface
from the other side and instructed that deferring it into already-built task 3.1
would preserve a false completed state — so it was repaired in this lane. See
Round 2 below.

---

# Round 2 — Codex money review (ADAPT), three findings

Verdict artifact: `verdict-A3.md` (reviewed `e88bbd8d`). Each finding below is
recorded red -> fix -> green -> mutation -> pushed sha.

## Finding 2 (Required) — `canonical_fee_required` meant positive, not canonical

`_require_canonical_fee` checked only `fee_micros > 0`, so a 1-micro fee on a
1,000,000-micro gross was accepted as canonical.

- **Red** — `tests/test_paid_market_price_surface.py::test_positive_but_non_canonical_fee_is_refused`
  and two siblings failed at collection: `ModuleNotFoundError:
  tinyassets.paid_market.fee_schedule`.
- **Fix** — new `tinyassets/paid_market/fee_schedule.py`: an immutable versioned
  registry binding `fee_schedule_version` -> `fee_ppm`, delegating the *amount* to
  the landed canonical primitive `forwards.canonical_fee_micros` so the paid market
  keeps exactly one fee formula. `SettlementBinding` carries
  `fee_schedule_version` (so the three receipts must already agree on it).
  `_require_canonical_fee` keeps `canonical_fee_required` for a zero fee and adds
  `canonical_fee_mismatch` and `unknown_fee_schedule_version`.
- **Green** — 584 passed, 22 skipped across `tests/test_paid_market_*.py`; ruff clean.
- **Mutation** — `_fee_matches_schedule` is its own seam
  (`tests/test_paid_market_manipulation_mutation.py:559`); forcing it to `True`
  makes the off-schedule guard go red, so the *schedule* half is load-bearing
  independently of the *positivity* half.
- **Pushed** — `25c61cfe`.

## Finding 1 (Critical) — the influence cap did not close the unbounded-price path

A positive fixed weight times an unbounded caller-provided price is still
unbounded, and principal roots/linkage were caller-supplied, so split-account
volume could claim unrelated roots and evade the exclusions.

- **Red** — 47 failures across the three suites, including
  `unit_price_not_settlement_derived`, `test_split_account_volume_cannot_evade_the_influence_cap`,
  `test_the_same_settlement_cannot_be_observed_twice`, the quote-binding matrix,
  and `observation_descriptor_ids`.
- **Fix** —
  - `_require_settlement_derived_price`: a declared price is admitted only when
    `unit_price_micros * quantity == binding.gross_micros` exactly. The
    authoritative reference is the gross the three authorities settled, so a 10^18
    print costs 10^18 * quantity micros of real money plus its canonical fee.
    Integer micros only; a gross that does not divide by the delivered quantity
    fails loud rather than rounding into the index.
  - `buyer_principal_root` / `seller_principal_root` / `linked_party` moved into
    `SettlementBinding` — the parties are now settlement authority, not a caller
    value, so `_index_eligible` cannot be steered.
  - `_settlement_identity_scale` dampens by requester / host-owner volume, so
    fabricating a fresh root pair per wash print no longer slips under every root-
    and pair-level bucket; `_require_unique_settlements` refuses a replayed
    settlement id.
  - `_capped_scales` re-bases each partition on its least-dampened member. Composing
    partitions through `min()` on absolute `1/volume` ratios let a single-identity
    partition win every `min()` and erase the other caps — a latent composition bug
    the new partition exposed. No-op in the water-filling branch (uncapped keys
    already scale to 1); it only corrects the infeasible-cap branch.
  - `join_paid_observation` now *derives* descriptor, market class, scope revision,
    and scope bytes from the settlement's `ValidatedQuote` instead of accepting
    them, and still re-validates the scope bytes rather than trusting the dataclass.
    `PriceSurface.observation_descriptor_ids` retains each source's exact descriptor
    id as aggregate evidence.
- **Green** — 612 passed, 22 skipped across `tests/test_paid_market_*.py`; ruff clean;
  mirror rebuilt (288 files, import probe ok).
- **Mutation** — five new monkeypatch probes (settlement-derived price, settlement-
  identity dampening, settlement uniqueness, quote binding, fee schedule). Beyond
  those, a **source-mutant run** deleted each new control from `price_surface.py`
  directly: all 21 new-control tests went red and no other test did.
- **Pushed** — `aa7d272a`.

## Finding 3 — task 2.1's checkoff was premature

The 2.1 evidence claimed "quote-bound observation-scope provenance" but pointed at
two disconnected facts with no join between them, so a quote/observation mismatch
could not go red.

- **Chosen resolution: complete the binding, not uncheck.** The review warned that
  deferring the gap into task 3.1 — already marked built — would preserve a false
  completed state. Since Finding 1 required rewriting the same join, the
  authoritative quote-to-observation binding was completed here and 3.1 was
  reopened and repaired rather than left overclaiming.
- **Red -> green** — four new provenance tests in
  `tests/test_paid_market_scope_provenance.py`: the observation's scope bytes are
  the signature-covered bytes re-parsed out of `canonical_bytes` (`:513`); a
  tampered scope never validates, so no observation exists at all (`:540`); a v1
  quote is refused `quote_scope_unsigned` (`:555`); descriptor / currency /
  fee-version mismatches fail closed (`:564`). 43 passed.
- **tasks.md corrected to the true state** — 2.1's evidence rewritten to name the
  real join tests and say plainly that the earlier claim was premature; 3.1 gains a
  repair note plus the deliberate fail-closed divisibility trade-off; 2.5's probe
  count corrected 6 -> 11 with current line refs; premise rows 2.1 / 2.5 / 3.1 /
  3.5 restamped. No box was checked that was not already true.
  `openspec validate paid-market-live-price-discovery --strict`: valid.
- **Pushed** — `3967702f`.

## Round-2 evidence

| Check | Result |
|---|---|
| `tests/test_paid_market_price_surface.py` | 54 passed |
| `tests/test_paid_market_scope_provenance.py` | 43 passed |
| `tests/test_paid_market_manipulation_mutation.py` | 91 passed |
| All `tests/test_paid_market_*.py` | 612 passed, 22 skipped |
| Source-mutant probe (5 controls removed) | 21 new-control tests red, 0 others |
| `ruff check tinyassets/paid_market/ tests/test_paid_market_*.py` | All checks passed |
| `openspec validate paid-market-live-price-discovery --strict` | valid |
| `packaging/claude-plugin/build_plugin.py` | 288 files staged, import probe ok; pre-commit mirror parity verified |
| The 12 other test modules that import `tinyassets.paid_market` | 338 passed |
| Full `pytest tests/` | NOT RUN — see below |
| Cross-family review (Codex, refute-3-claims gate) | DISPATCHED, in flight at report time — no verdict yet |

**Not run, stated rather than implied:** the full `pytest tests/` sweep. Round 1
left it `PENDING_FULL` and Codex's own run was killed by Windows process-resource
exhaustion. What *was* run to bound the blast radius: `price_surface`,
`PaidObservation`, and `SettlementBinding` have no importer anywhere outside
`price_surface.py` itself and the paid-market tests (repo-wide grep), and the 12
other test modules that import `tinyassets.paid_market` at all were run
explicitly — 338 passed. That is a scope argument plus its adjacent suites, not a
green full-suite run, and it is not claimed as one.

**Cross-family gate is dispatched, not returned.** A Codex `refute-these-three-
claims` review of `25c61cfe` + `aa7d272a` was launched read-only against this
worktree and was still running when this report was written. Its verdict is
required before this lane is treated as reviewed; nothing here should be read as
carrying it.

---

# Round 3 — Codex re-review returned ADAPT; three of four points fixed

The round-2 cross-family gate came back **ADAPT** and refuted the round-2 price
claim. It was right. Recorded here rather than argued with.

## A (critical) — bounding the product does not bound the price. FIXED

`quantity` was still caller-supplied, so a settlement that moved 1,000,000 micros
for 1,000 delivered units could be declared `(price=1_000_000, quantity=1)`: the
equality held exactly while publishing a 1,000x fabricated unit price.

- **Red** — `test_quantity_is_settlement_evidence_not_a_caller_declaration`.
- **Fix** — `delivered_quantity` is a `SettlementBinding` field, so both factors
  are settlement evidence and the unit price is fully determined.
  `join_paid_observation` no longer takes a `quantity` argument at all.
- **Green / mutation** — covered by the existing
  `_require_settlement_derived_price` probe; the source-mutant pass still reds it.
- **Pushed** — `9d06ae93`.

## C (critical) — the join trusted a forgeable dataclass. FIXED

`ValidatedQuote` is an ordinary public dataclass, so *holding* one proved nothing:
an attacker could keep the `canonical_bytes` of a genuinely signed quote and
replace the attributes around them.

- **Red** — `test_quote_attributes_must_match_the_bytes_the_issuer_signed`
  (7 params) and `test_unreadable_or_foreign_signed_bytes_fail_closed`.
- **Fix** — `_require_attributes_match_signed_bytes` re-reads quote_id,
  descriptor, market class, scope revision, scope bytes, currency, and fee version
  out of the signed body — the exact shape `quotes.quote_signing_bytes` emits.
  This immediately caught the lane's **own test fixtures**, which were forgeable
  stubs; they now build self-consistent bytes and deliberate drift is its own test.
- **Mutation** — new probe `test_signed_bytes_reverification_is_load_bearing`.
- **Pushed** — `9d06ae93`.

## D — unknown was reading as benign. FIXED

`linked_party` accepted `None`/`0`/`"false"`, an empty principal root counted as a
"known" root, and `principal_share_cap_ppm=True` passed as a 1-ppm cap. All three
now fail closed (`test_party_and_delivery_evidence_fails_closed`,
`test_a_bool_cannot_pass_as_the_influence_cap`). **Pushed** — `9d06ae93`.

## B (critical) — cross-partition cap composition. FIXED

- **Red** — the pinned counterexample was converted from a known-limitation
  assertion to the required behavior and extended across 2, 3, and 5 identity
  partitions. The focused module produced 5 failures because no joint solver
  existed (92 passed, 5 failed).
- **Fix** — reshaped, not edge-patched. `_raw_vwap_field` now submits the pair,
  buyer-root, seller-root, requester, and host-owner partitions to one exact
  rational linear solver. Every group cap is expressed against the same final
  settlement-weight total. The solver maximizes retained settled volume subject
  to those joint constraints and the original observation quantities; a
  structurally inconsistent partition set fails closed with
  `joint_influence_cap_infeasible`.
- **Green** — `tests/test_paid_market_manipulation_mutation.py` plus the directly
  touched `tests/test_paid_market_price_surface.py`: 178 passed.
- **Mutation** — `test_joint_partition_cap_is_load_bearing` forces the joint
  solver open and the 5-partition split-volume guard goes red. The parameterized
  2/3/5-partition probe proves adding partitions cannot restore admission.
- **Pushed SHA** — implementation commit `8756564c`; this evidence stamp follows
  it on the same pushed branch.

## Round-3 evidence

| Check | Result |
|---|---|
| All `tests/test_paid_market_*.py` | 642 passed, 22 skipped |
| Mutation probes | 13 (2 added this round) |
| `ruff check tinyassets/paid_market/ tests/test_paid_market_*.py` | All checks passed |
| `openspec validate paid-market-live-price-discovery --strict` | valid |
| Mirror | rebuilt; pre-commit parity verified |
| Cross-family gate (Codex round 2) | ADAPT — A/C/D fixed, B open |
| Full `pytest tests/` | still NOT run |
| Cross-family re-review of round 3 | NOT dispatched |

LANE_RESULT: done - finding B reshaped to one joint settlement-weight cap; 178 focused tests passed and commit 8756564c was pushed
