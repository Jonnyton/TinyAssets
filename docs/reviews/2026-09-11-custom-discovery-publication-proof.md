# Owned source publication and exact discovery capture

September11 2026 UTC, featureca73f353d4b0fa0c8937f7ab57748b7db2309cfa
against1736c9e3. Not deployed. Independent exact review APPROVE79s, terminal exit0,
no required corrections. Reviewer ran26new tests in6.14s on Windows September11UTC:
with bytecode writing disabled, python -m pytest -p no:cacheprovider -q
tests/test_custom_discovery_publication.py. Four canonical/plugin commit pairs
and exact-range whitespace match. Broader group not independently rerun.
Available-family fallback follows the documented hard provider limit/quality-gates
policy; not cross-family evidence. Full output in primary
output/custom-discovery-publication-review.md. The follow-up compiler docstring
only corrects its obsolete "not yet published" wording; runtime code is unchanged.

Existing configure_provider_capability action now accepts the reviewed closed
versioned source descriptor in the existing metadata table. Legacy shape/bytes
remain unchanged. Optional preview checks the same current owner/admin/verified
definition/grant/resource/auth/GET/endpoints and returns before metadata INSERT.
It cannot revoke or replace an existing row. Digest is whole-descriptor identity,
not authority. New response explicitly states that source semantics are not
independently verified and configuration grants neither inference nor spending.

Real discovery chooses exact numeric parsing for the new source, captures the
compiled immutable contract, and retains the existing whole context digest/final
recheck. Custom provider scope is server-derived custom-http; source_kind stays
http, account identity absent, owner_filtered false. Additive availability_basis
records owner_configured_contract without changing admission. Missing or changed
configuration/grants invalidate snapshots; no remote field supplies trust.
No selection or actual inference consumer is enabled by this commit.

Author final11-file command: python -m pytest -q
tests/test_custom_discovery_publication.py tests/test_model_discovery_capability.py
tests/test_discovery_snapshot.py tests/test_discovery_http.py
tests/test_discovery_exact_numbers.py tests/test_discovery_contract.py
tests/test_model_policy.py tests/test_agent_protocol_capability.py
tests/test_selected_model_authority.py tests/test_model_options_api.py
tests/test_provider_capability_api.py --tb=short --show-capture=no -rs.
440Windows28.65s/440actualLinux16.34s, zero skips. One Windows FastMCP Python3.14
deprecation warning, not a test failure. Linux via Ubuntu WSL linux_oracle.py,
Python3.11.16/git2.47.3/bubblewrap0.12.0. Ruff,423-file plugin build/import,
canonical mirrors and whitespace checks pass.

New tests cover existing graph action, authenticated API, real ledger/resolver/
credential-blind broker and synthetic network. They verify exact prices/benchmarks,
preview non-mutation, unchanged grants/definitions, mixed versions and forged
trust refusal, endpoint/auth rejection, revocation before metadata transaction,
contract change during fetch, and stale snapshot rejection. Initial fixture errors
used an invalid proxy access_mode and wrong expected existing auth-error class;
corrected to actual ledger values/legacy not_found behavior, no runtime relaxation.

Still required: same-contract selection/request/reservation/settlement/usage/capacity,
source-semantic admission and visible caveats, discoverable authoring schema/help,
legacy full-price migration to shared code, native/all-universe controls and live
acceptance. Four neutrality gate loci remain red; no exemption/push/deployment.
