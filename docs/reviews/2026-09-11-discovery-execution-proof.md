# Data-shaped execution prerequisites

September11 2026 UTC, local feature tree against632e6beb; not deployed.
discovery_execution.py implements pure closed UsageShape, CapacityShape and
RequestCeilings. No production consumer or new public descriptor is activated.

Usage reads original JSON numeric tokens as Decimal, enforces declared scalar
encoding and rounds positive fractional micros up. Malformed/absent/duplicate,
nonfinite, oversized and out-of-range values remain unknown. Capacity maps at
most32 HTTP statuses to existing scopes/reasons, with optional standard Retry-After;
it supplies no account identity or independent-capacity proof.

Request ceilings are exact decimal strings at declared powers-of-ten output
scales. Paths create object fields only, cannot overlap each other or installed
request fields, and preserve model/message/tool/token-limit fields. Model
exclusions are literal prefix/suffix/substring data. Constants are captured as
detached JSON with declared charge references. A local installed body validator
is required by the applying caller and cannot come from descriptor data.
Reservation/affordability use the existing bounded token and per-request units.

IMPORTANT: this inner compiler does not certify complete price coverage or that
constant effects are within actual executor quantity bounds. The whole-source
compiler must cross-check those before publication/selection. Nor does writing
a ceiling prove a remote service honors it. Existing legacy decoders/callers
are unchanged; no gate exemption or provider-specific preset was added.

python -m pytest -q tests/test_discovery_execution_shapes.py
tests/test_discovery_exact_numbers.py tests/test_discovery_catalogue_shapes.py
tests/test_discovery_contract_compatibility.py tests/test_model_capacity.py
tests/test_model_capacity_transport.py tests/test_selected_model_authority.py
tests/test_interactive_http_agent.py --tb=short --show-capture=no -rs
passes538Windows30.54s/538actualLinux16.72s, zero skips. Linux via Ubuntu WSL
scripts/linux_oracle.py with Python3.11.16/git2.47.3/bubblewrap0.12.0.
66 new cases include differential reservation checks against the unchanged
SelectedModel implementation, malformed shapes, exact caps and usage rounding.
Ruff clean,421-file plugin build/import probe and diff check pass.
Independent exact-head review required; no push/deployment or live proof.
