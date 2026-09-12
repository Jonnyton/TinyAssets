# Model release fixture corrections

September11,2026 around04:46–04:52UTC. Feature head before edits:
bd93e239618f35f711ae8993941daf8137154b78, draft PR3832, not deployed.

Required-tests34525329157 attempt2 failed with nine new failures. Six status
cases patched provider_serving_binding.list_bindings, an import removed by the
correct owner/status-filtered serving query. Their fixture now publishes real
agent definitions/bindings and uses the transaction-required serving setter.
It still proves exactly one owned serving binding, rejects two/foreign bindings,
and preserves absent/unready/disabled behavior. Runtime was not reverted to a
bounded pre-filter list.

The seventh obsolete case expected the unfinished-feature hold after that path
was integrated. It now creates the real current home, retains its discovery-less
manifest and expects no eligible model, proving both assignment and binding
unchanged after refusal. It does not bypass readiness or invent successful
discovery.

Verification on the edited tree:
- Windows: python -m pytest -q tests/test_status_says_what_is_true.py
  tests/test_serving_manifest_publication.py --tb=short --show-capture=no
  —41passed9.72s, zero skips.
- Actual Docker Linux via WSL Ubuntu and scripts/linux_oracle.py, same two files
  with --tb=short --show-capture=no -rs:41passed4.57s, zero skips;
  Python3.11.16, git2.47.3, bwrap0.12.0.
- Ruff corrected import formatting only; recheck required before commit.

Two channel-agnostic ratchet failures remain. No baseline, exclusion, gate,
provider runtime or private workflow was changed in these fixture corrections.
This is not a green release claim. A changed release head needs fresh independent
review and CI before deployment, then rendered user acceptance.
