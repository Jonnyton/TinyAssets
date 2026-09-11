# Frozen discovery compatibility baseline

September 11, 2026 UTC. Local Windows feature worktree; no runtime edit,
activation or deployment. The new tests prepare the reviewed shared-contract
rewrite, not prove unfamiliar-source execution is already implemented.

`tests/_discovery_legacy_oracle.py` freezes the entire catalogue decoder module
from 8b9ba65ce0551b3f59afa5a7d79d1dfef849dd34, including helper behavior.
AST comparison against `git show 8b9ba65c:tinyassets/providers/catalog_decoders.py`
passed. It imports only shared domain values, not production decoder helpers.
An independence test disables the current decoder's price/row/scaling helpers
and verifies the frozen decoder remains functional.

Command: `python -m pytest -q tests/test_discovery_contract_compatibility.py tests/test_catalog_decoders.py --tb=short --show-capture=no -rs`.
Windows: 224 passed in 0.84s, zero skips. Actual Linux through Ubuntu WSL
`python3 scripts/linux_oracle.py --` with the same arguments: 224 passed in
0.47s, zero skips; Python 3.11.16, git 2.47.3, bubblewrap 0.12.0. Ruff on both
new files passes. Formatting-only line wrapping followed the Windows run.

Coverage includes identity refusal without normalization, missing/unknown and
unrepresentable prices, override maxima/invalidity, capability unknowns, minimum
contexts, incomplete envelopes, exact benchmark joins, source/scale and age.
Results are compared with both value and exception-class/message outcomes.

These comparisons currently run against the still-unchanged production decoder.
The new compiler must consume them later. Inference constraint and usage/capacity
oracles still need to accompany that implementation; this file does not claim
they have been frozen or that the four-locus neutrality gate passes.
