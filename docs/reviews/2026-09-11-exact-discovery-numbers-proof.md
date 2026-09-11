# Exact numeric discovery and array-root transport

September 11, 2026 UTC, feature worktree; parent46138e7f. Not deployed.

The existing credential-blind discovery reader has an internal explicit exact
JSON mode: original numeric tokens become Decimal, object/array roots are
accepted, duplicate keys/nonfinite constants/invalid roots still refuse, and
the same grant/owner/endpoint/proxy-close checks run. Default legacy mode keeps
its object-root/float behavior and existing error message. Remote data cannot
choose the mode; no public descriptor or permission surface is widened yet.

Compiled price fields now declare string/number/either encoding, default string.
Exact numeric fields accept integer/Decimal values, never binary floats or bools;
all prices retain exact scaling, unknown-component handling and override maxima.
New benchmark shapes likewise consume exact scalars; legacy presets retain their
old numeric interpretation. The existing unfamiliar benchmark fixture now uses
Decimal as the real exact parser returns, with unchanged expected scores.

New test file test_discovery_exact_numbers.py uses the real test ledger, scoped
resolver and credential-blind broker with synthetic wires. It proves array-root
transport -> compiled catalogue/prices, untouched grants/model pin/authority
flags, exact submicro values staying unknown rather than free, numeric overrides,
unknown fees, invalid encoding/mode, rejected documents and revoked/foreign scope.
This is supporting integration evidence, not live inference or app acceptance.

Command: `python -m pytest -q` plus the following ten files and
`--tb=short --show-capture=no -rs`:

- tests/test_discovery_exact_numbers.py
- tests/test_discovery_catalogue_shapes.py
- tests/test_discovery_contract_compatibility.py
- tests/test_catalog_decoders.py
- tests/test_model_price_applicability.py
- tests/test_discovery_snapshot.py
- tests/test_model_discovery_capability.py
- tests/test_discovery_http.py
- tests/test_selected_model_authority.py
- tests/test_interactive_http_agent.py

Windows599passed40.38s; actual Linux via Ubuntu WSL
`python3 scripts/linux_oracle.py --` with the same arguments599passed20.75s;
zero skips. Python3.11.16/git2.47.3/bubblewrap0.12.0 on Linux. Ruff clean on both
canonical files and affected tests; plugin build420files/import probe OK;
diff whitespace clean. Unchanged channel-neutrality gate remains red at4loci.

Full source-contract publication/provenance, dimensionally closed reservation,
request ceilings, usage/capacity and unfamiliar-source actual execution remain
unbuilt. Nothing configures a live account, edits workflows or widens grants.
Initial exact99ffc777 review returned ADAPT: Decimal accepts malformed string
syntax such as 0__0 as zero. New-contract string/either scalars now require a
complete ASCII JSON decimal token before exact conversion. Legacy price presets
explicitly retain their original Decimal interpretation; benchmarks preserve
the same legacy split.47 additional regressions cover malformed and valid tokens,
legacy prices and benchmark strings. Same ten-file command now passes
646Windows28.97s/646actualLinux20.87s, zero skips; ruff/plugin/import/mirrors
and diff checks pass. Independent correction review of exact
28714628abd1359cc43c20d8e7aa7591c39bcfb2 completed92s, terminal exit0,
VERDICT APPROVE.71 focused cases independently passed in memory plus bounds,
benchmark and immutability probes (python -B -, Windows September11 UTC);
not an independent reproduction of the full646-case group. Canonical/mirror blob
791cdce2cfe14c0219a24d899c830a8ee8757468 matched. No further required correction;
no whole-PR or live acceptance approval. No push/deployment.
