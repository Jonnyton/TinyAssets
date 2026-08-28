Review target: PR head `dfbd15d2`.

1. **DISAGREE_EVIDENCE** — Credential material reaches the resolver through multiple accepted fields.

   - A Slack webhook such as `https://hooks.slack.com/services/T000/B000/SECRET123` is itself a credential. The browser captures the entire secret-bearing path as a hint and sends it to the model: [app.html:1165](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1165), [app.html:1182](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1182), [connection_inference.py:422](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:422).
   - `label` has only a length check. `{"label":"sk_live_51ABCDEFSECRET","prefix":"","length":32}` is accepted: [connection_inference.py:174](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:174).
   - `prefix="AbCdEfGhIjK_"` passes, carrying eleven attacker-selected characters—roughly 65 bits—plus a delimiter: [connection_inference.py:78](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:78).
   - `intent` accepts arbitrary text and forwards its first 300 characters without secret screening: [connection_inference.py:314](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:314).

2. **DISAGREE_EVIDENCE** — `_ground_host` is bypassable by substring collision.

   Reproduction:

   ```text
   hint:     https://not-evil.com/setup
   proposal: host=evil.com, path=/steal, confidence=high
   result:   resolved=true
   deposit:  status=provisioned, host=evil.com
   ```

   The direct `if host in haystack` test treats `evil.com` inside `not-evil.com` as grounding: [connection_inference.py:230](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:230). The fallback is also not a registrable-label check; it accepts any ≥3-character label outside a six-word denylist: [connection_inference.py:233](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:233). The app then deposits immediately: [app.html:1236](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1236).

3. **AGREE** — No grant shape unavailable to the manual deposit was found. Inference and `connect_http` invoke the same endpoint parser: [connection_inference.py:351](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:351), [http_connection.py:338](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/http_connection.py:338).

   Caveat: this proves syntactic/SSRF parity, not least privilege. The parser will accept all five permitted methods if the model proposes them; only the prompt asks for narrowness.

4. **AGREE** — The owner gate matches `connect_http`: authenticated principal, `_request_universe`, same base, and an exact `(actor_id, permission="admin")` ACL row. Compare [connection_inference.py:272](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/connection_inference.py:272) with [http_connection.py:242](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/api/http_connection.py:242). The resolver’s universe-directory check is additionally restrictive, not permissive.

5. **DISAGREE_EVIDENCE** — Real credential pages are mishandled.

   - Slack webhook URLs are excluded from `values` but forwarded as hints. The credential is disclosed to inference, then `pickSecret` has nothing to deposit: [app.html:1172](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1172), [app.html:1182](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1182).
   - Given a typical Stripe page ordered as `Publishable key: pk_live_…` then `Secret key: sk_live_…`, bearer selection chooses `pk_live_…`: the first `\bkey\b` match wins. Exact-JS reproduction returned `pk_live_PUBLISHABLE`: [app.html:1206](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1206).
   - `Username: bob` is silently discarded because values under eight characters are rejected; basic auth then cannot assemble `username:password`: [app.html:1176](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1176), [app.html:1202](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1202).
   - The paste textarea is cleared correctly before awaiting. However, the optional intent remains in the DOM until successful deposit, so a credential accidentally pasted there persists through inference failures: [app.html:1217](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1217), [app.html:1244](/C:/Users/Jonathan/Projects/wf-fix-http-deposit-error-detail/tinyassets/onboarding/app.html:1244).

Focused verification on 2026-08-27, Windows/Python 3.14: `python -m pytest -q tests/test_connection_inference.py tests/test_onboarding_app.py` → 46 passed. The hostile cases above are absent from those tests.

**Overall verdict: REJECT.** Claims 1 and 2 are broken safety boundaries: the feature can disclose a credential during inference and automatically bind it to an exact host the user never named.