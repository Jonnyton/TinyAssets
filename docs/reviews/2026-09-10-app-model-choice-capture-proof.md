# App per-message model-choice capture

September10 2026. Local feature worktree afterab522e39. Internal wiring for the
already-reviewed canonical converse model_choice input; no picker or model-list
endpoint is enabled and no deployment is claimed.

The actual MCP.converse method now forwards a copied optional document; null or
omission leaves the argument absent, preserving server-owned saved/default
resolution. Sending typed or spoken text captures the choice once. Queue and
in-flight persistence retain it; restored historical records without the field
remain no-override even if the page now has a different current selection. Retry
reuses the same choice, not the mutable picker value. Sign-out clears the transient
current choice. Saving defaults and observed answer receipts are unaffected.

Queue identity includes scope, text, timestamp and captured model choice. Two
same-text/same-timestamp entries with different models are no longer erased
together when one is sent. Explicit fallback order, including an empty tail, is
copied and forwarded unchanged. This adds no inference or spending authority.

Verification runs the actual extracted app functions in Node, not rewritten
Python equivalents. Thirteen new cases cover typed/voice capture, queued object
mutation, retry, restored pending and queued choices/legacy absence, distinct
same-text records, actual MCP optional-argument omission and fallback forwarding.
The existing124 app tests and16 brand/mirror tests also pass.

```text
python -m pytest -q tests/test_app_model_choice.py tests/test_onboarding_app.py tests/test_brand_parity.py tests/test_mirror_parity_gate.py --tb=short --show-capture=no -rs
153 passed in 34.38s
```

Actual Docker Linux oracle, same four files/flags, Python3.11.16/git2.47.3/
bwrap0.12.0:153 passed22.66s, zero skips. Windows is Python3.14. Earlier132/136
app-only groups passed; final153 includes the later explicit fallback-order case.
Ruff/diff checks pass,418 runtime mirrors/import pass. Shared brand provenance
regenerated using its existing generator, preserving the mark version and assets;
only the app checksum changed. No visible site layout/assets were edited.

Review this wiring with the real picker/catalogue consumer before landing. The
cross-client public MCP and actual rendered app selection proofs remain open;
these local JavaScript checks are supporting evidence, not that final proof.
