# Lane report — paid-market-live-price-discovery 2.1 / 2.2 / 2.5

Branch `claude/o5-live-price-runtime` off `origin/main` `f7142a57`.
Unblocked by the #1679 landing (`01e7ced7`) plus task 1.5's round-2 APPROVE.

(This file previously held the `claude/o5-data-commons` lane report, committed at
`f7142a57`; that content remains recoverable from git history.)

Runtime lives in `tinyassets/paid_market/` (not `tinyassets/payments/` — the brief's
path was stale; `payments/` holds the Wave-2 transport spine, `paid_market/` holds
the pure live-price core named in the brief: `quotes.py`, `match.py`, `routing.py`,
`instruments.py`, `price_surface.py`).

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

## Gap found, deliberately not built (outside 2.1/2.2/2.5)

`PaidObservation` binds `market_class_id`, `market_scope_revision`, and
`public_scope`, but **not** the exact `descriptor_id`. The spec's "Settlement records
normalized delivery evidence" requirement and the scenario *"compatible supply
headroom shares one demand class — AND the aggregate still retains each source's
exact descriptor id as evidence"* both call for it. That belongs to task 3.1's
observation-join surface (`tinyassets/paid_market/price_surface.py:55-75`), already
marked built, so it is reported here rather than silently widened into this lane.

LANE_RESULT: PENDING
