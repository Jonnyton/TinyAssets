# Test identity and reset mutation proof

Freshness: 2026-07-21, Windows 11, Python 3.14, branch
`feature/test-identity-and-reset-impl` from `origin/main` at
`144eaba7467613c1aab37fe5d485bff02475500f`.

Each mutation below was applied alone to production code, its focused test was observed RED, and the
mutation was reverted. The restored implementation finished with 18/18 focused security tests green.

| Security boundary | Deliberate mutation | Required RED evidence |
|---|---|---|
| Delegated admin cannot confer deletion ownership | Removed `granted_by = principal` from ownership resolution | Scoped-reset test failed because founder B's directory was deleted |
| Only allowlisted test identities can reset | Removed allowlist membership enforcement | Allowlist test failed because a production founder was accepted |
| Exact deletion set is reviewed before apply | Replaced the supplied plan hash with the current plan hash | Plan-confirmation test failed because an incorrect hash did not raise |
| Index values cannot target operational data | Removed the operational-directory denylist | Hostile-index test failed with `universe_dirs == ["wiki"]` |
| Restore cannot overwrite post-reset state | Removed the existing-directory conflict guard | Restore-conflict test reached `FileExistsError` instead of failing closed |
| Identity evidence never contains a bearer | Stored the raw bearer in `bearer_present` | Token-safety test exposed the sentinel and failed |
| Unresolved identity never inherits host identity | Added `UNIVERSE_SERVER_USER` fallback for anonymous | Fail-closed identity test resolved to `host-founder` and failed |
| Presence/config/cache/inconclusive probes are never authenticated | Marked every `status=ok` provider authenticated and labeled an inconclusive probe as successful | Config-presence and inconclusive-probe tests observed dishonest evidence and failed |

Supporting clean command:

```text
python -m pytest tests/test_scoped_identity_reset.py tests/test_identity_observability.py tests/test_provider_auth_evidence.py -q
18 passed
```
