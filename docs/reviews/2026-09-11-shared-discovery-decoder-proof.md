# Shared data-driven catalogue and benchmark decoding

September 11, 2026 UTC, local feature worktree, parent6f8e85f0. Not deployed.

`discovery_catalogue.py` compiles immutable bounded catalogue/price/benchmark
shapes from closed data documents. JSON Pointers, exact price scaling, context
minima, declared tool evidence, conservative overrides and exact benchmark joins
are shared operations, not a new brand registry. The legacy named functions in
`catalog_decoders.py` now call this same interpreter using their existing data
declarations. New-shape fixtures use different nesting, names and source/model
identifiers without registering a preset. Input dictionaries cannot mutate the
compiled objects. The new paths are internal, pure and non-authorizing.

The complete source contract is NOT implemented here: publication, source
provenance, price-cap/accounting closure, usage/capacity and actual unfamiliar
source execution still need the reviewed discovery-contract-v1 integration.
In particular, the price field compiler alone does not certify that a named
component is executable or enforceable. No public action or storage payload is
widened, and no remote metadata may change owner/executor/account/source flags.

Verification command: `python -m pytest -q` with these nine files followed by
`--tb=short --show-capture=no -rs`:

- tests/test_discovery_catalogue_shapes.py
- tests/test_discovery_contract_compatibility.py
- tests/test_catalog_decoders.py
- tests/test_model_price_applicability.py
- tests/test_discovery_snapshot.py
- tests/test_model_discovery_capability.py
- tests/test_discovery_http.py
- tests/test_selected_model_authority.py
- tests/test_interactive_http_agent.py

Final Windows: 522 passed in43.48s, zero skips. Final actual Linux through
Ubuntu WSL `python3 scripts/linux_oracle.py --` with the same arguments:
522 passed in20.12s, zero skips; Python3.11.16, git2.47.3, bubblewrap0.12.0.
Both final groups include the missing-versus-malformed nested override fix.

Frozen legacy catalogue decoder unchanged: differential values and exception
class/messages agree for price, identity, capability, completeness and ranking
cases. Independence test now disables the actual shared interpreter helpers,
not retired helper names; expected outputs/oracle were not loosened.
New46cases additionally cover unfamiliar layouts, immutability, pointer escapes
and array indices, invalid declarations, source-authority flags, unknown fees,
malformed/absent overrides and row/override bounds. No URL is followed.

Ruff clean on both canonical files and both affected tests.
`python packaging/claude-plugin/build_plugin.py`:420files, import probe OK.
`git diff --check` clean. `python scripts/check_channel_agnostic.py` still fails
at the same four loci; no gate/baseline change. Independent exact-head review
required. No workflow edit, push, deployment or live model-picker proof.
