# Profile-bound discovery snapshot — locally tested, still advisory

September9,2026,22:15 UTC. Internal profile publication was independently
APPROVED atc8d0dbab (264s,40 reproduced tests). The full verdict is committed in
discovery-profile-publication-review.md. There is no active peer review process.

The new discovery_snapshot module joins the existing verified definition, live
grant/resource and typed profile. Grant/resource/profile are read in one SQLite
snapshot. Existing secret-free grant-identity hashing supplies credential-reference
lineage; no credential value is read, hashed or returned. Before/after source
checks reject profile, grant, endpoint, definition or credential-reference changes.
This is identity evidence, not proof of separate account capacity or a new grant.

Only the configured profile URLs are read through the independently reviewed
credential-blind transport. The protocol contract owns its model/benchmark
decoders; the generic refresh coordinator knows no vendor response shape or
model names. It alone supplies account-filtered provenance after a successful
profile-bound read. Remote flags cannot upgrade tool support or assert an account
identity. HTTP executor_tools remains false, authenticated_account_id remains unknown,
and no legacy model string becomes an automatic preference.

The policy's historical connection_id field is an opaque selector key. Snapshot
models use the exact provider reference; physical connection/grant ids stay
separate in provenance. Two definitions sharing a connection therefore remain
distinct accepted bindings, not a permission union or an ambiguous duplicate key.

Observed time is captured after the catalogue read; optional benchmark failure
keeps models visible and unranked with a fixed warning. Benchmark as_of controls
score freshness. Backwards clock or more than five minutes after observation
refuses a fresh result. There is no completed-result cache. An async wrapper
offloads blocking reads and coalesces in-flight calls per source/event loop;
cancelling one waiter leaves the actual read running, and failed/completed flights
do not poison later refreshes. Separate server processes have separate flights.
This is not a process-shared capacity or authority mechanism.

Three optional review follow-ups also now have tests: malformed non-string
benchmark URLs fail explicitly instead of being discarded (voice unchanged),
full-channel publication retains existing scope semantics, and a path grant
without query permission cannot publish the fixed all-modalities query.

Verification, September9, Windows Python3.14 and supplemental Ubuntu3.11.15:

`python -m pytest -q tests/test_discovery_snapshot.py
tests/test_model_discovery_capability.py tests/test_connection_capabilities.py
tests/test_provider_capability_api.py tests/test_realtime_voice.py
tests/test_discovery_http.py tests/test_catalog_decoders.py tests/test_model_policy.py
tests/test_api_key_http_provider.py tests/test_mirror_parity_gate.py`

- Windows:301 passed,14.67s; Ubuntu:301 passed,37.38s; no skips. Linux has one
  existing LangChain warning. Existing external-temp receiver-linux-proof.sh was
  used; this is not a Docker-oracle claim.
- Seventeen new snapshot tests plus45 profile cases. Real metadata/authority
  storage and injected network documents, not live account or rendered proof.
- Ruff check/format and diff checks passed; plugin mirror402files/import passed.

No app/API consumer invokes snapshot refresh yet. Per-attempt model/cost admission,
real HTTP tools, policy persistence/routing, actual response metadata and visible
controls remain unfinished. Snapshot output is advisory and must never be accepted
as inference authority. Independent integration review remains required before
landing. Actual account price-component coverage still needs live evidence; fixture
pricing cannot establish that automatic choices are usable on a real account.
