# Finite source quantity arithmetic — inactive prerequisite

September11 2026 UTC, feature4d38b964a400ebd7a6d3912a04f12b20c9ce6118
against600c729c46b46e3cdbc6bdeb550875a5a91d2e3a. Not deployed or activated.

QuantityModel compiles closed nonnegative integer affine bounds for aggregate
input tokens, output tokens and requests. Coefficients<=10^6, facts<=10^18;
requests cannot depend on token facts. Nested tuples detach caller data.
Exact arithmetic rounds each token charge upward, rejects reservations beyond
signed64 micros, and searches affordability inside an explicit finite output
limit. Free output remains finite. Zero output is a refusal sentinel, never
authority to dispatch when fixed costs exceed budget.

Eight internal samples of1000 output tokens at$10/million reserve80,000micros
($0.08), not10,000micros. Tests include aggregate overhead and request
multiplicity, exhaustive bounded affordability comparisons, malformed values,
dimension conflicts, overflow and safe smaller reservations.

Author command: python -m pytest -q tests/test_discovery_quantities.py
tests/test_discovery_execution_shapes.py tests/test_discovery_exact_numbers.py
tests/test_discovery_catalogue_shapes.py tests/test_discovery_contract_compatibility.py
tests/test_model_capacity.py tests/test_model_capacity_transport.py
tests/test_selected_model_authority.py tests/test_interactive_http_agent.py
--tb=short --show-capture=no -rs.
618Windows23.76s /618actualLinux17.66s, zero skips. Linux via Ubuntu WSL and
scripts/linux_oracle.py using Python3.11.16/git2.47.3/bubblewrap0.12.0.
Ruff on both new canonical files,422-file plugin build/import and diff checks pass.

Independent exact-commit review APPROVE73s, terminal exit0. Reviewer ran
python -B -m pytest tests/test_discovery_quantities.py -q -p no:cacheprovider
-o addopts= --tb=short:80passed0.50s, zero skips, local Windows September11UTC.
Exact whitespace/scoped working-tree equality and canonical/plugin blob equality
passed. Broader group not independently rerun. No required corrections.
Hard-limit available-family fallback under recorded quality-gates policy;
not cross-family evidence. Full output is in the primary worktree's
output/discovery-quantities-review.md.

No public/storage payload, accepted caps, permission or production consumer changes.
The corrected design separates local structure/arithmetic from owner-configured
remote promises. Complete price/extension coverage, publication/provenance and
same-digest selection/request/reservation/settlement remain activation gates.
Tariff-only source authority remains a separate unimplemented reviewed-design
prerequisite. The neutrality gate still fails at four existing loci; no exception,
renaming workaround, push, deployment or live acceptance claim.
