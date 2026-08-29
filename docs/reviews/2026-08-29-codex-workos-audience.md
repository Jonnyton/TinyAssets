# Codex cross-family read — production WorkOS `aud` rejection

Dispatched 2026-08-29 while the sign-in loop was live, as a fresh-eyes check rather than a
fourth grind on the same approach. Ranked #1 matched what I found and fixed in parallel
(missing Resource Indicator), and it independently agreed the daemon must NOT be loosened.
Its #2 — stale refresh chains keep the old `aud` — was the item I had not considered.

The production WorkOS environment is almost certainly missing the Resource Indicator. This is an environment configuration issue, not a reason to loosen daemon validation.

Ranked causes:

1. **No Resource Indicator in production — overwhelmingly likely.**  
   WorkOS explicitly says that without configured Resource Indicators, it ignores the RFC 8707 `resource` parameter and sets `aud` to the WorkOS **environment client ID** instead. Check the production environment under **Connect → Configuration → Resource Indicators** for the exact value `https://tinyassets.io/mcp`. [WorkOS MCP guide](https://workos.com/docs/authkit/mcp)

   Register that resource. Do not accept the client ID in the daemon. Doing so removes resource-server binding and permits replay of other same-environment tokens—a real security downgrade.

2. **Old authorization/refresh grant survived the configuration fix.**  
   WorkOS says existing refresh-token chains retain their original audience after adding/defaulting a Resource Indicator. After registering it, fully sign out/revoke the consent, clear the `ta_rt` refresh session, and perform a genuinely new authorization. Merely refreshing is insufficient. [WorkOS MCP guide](https://workos.com/docs/authkit/mcp)

3. **Confusing the two different client IDs or token types.**  
   Decode `aud` and compare it with:

   - **Developer → API Keys → environment client ID:** confirms missing Resource Indicator.
   - `client_01M15YZ...` Connect app ID: could suggest an ID-token/access-token mix-up.

   WorkOS normally gives ID tokens the OAuth application’s client ID as audience. However, TinyAssets explicitly extracts `access_token`, not `id_token`, so this is lower probability. [WorkOS token claims](https://workos.com/docs/reference/workos-connect/token)

4. **WorkOS configuration/issuance defect.**  
   Only consider this if the exact Resource Indicator exists in the correct production environment and a brand-new authorization still produces the wrong `aud`. Capture the WorkOS request ID and claims—not the token—and escalate to WorkOS.

`aud` being the AuthKit issuer is not expected; `iss` and `aud` are separate claims.

A JWKS/issuer mismatch is effectively ruled out. TinyAssets maps only PyJWT’s `InvalidAudienceError` to `category=audience`; key lookup, signature, and issuer failures have distinct categories. Signature and issuer validation happen before audience validation. See [workos_provider.py](/C:/Users/Jonathan/Projects/TinyAssets/tinyassets/auth/workos_provider.py:69). With the deployed code matching this checkout, the token’s signature and issuer passed, but its present `aud` did not match.

Fastest safe claims check: copy the rejected `access_token` from DevTools Network locally—never paste it into jwt.io—then run:

```python
import getpass, jwt

t = getpass.getpass("JWT: ")
h = jwt.get_unverified_header(t)
c = jwt.decode(t, options={
    "verify_signature": False,
    "verify_exp": False,
    "verify_aud": False,
    "verify_iss": False,
})
print(
    {"alg": h.get("alg"), "kid": h.get("kid")},
    {k: c.get(k) for k in ("iss", "aud", "iat", "exp")},
)
```

That decoding is diagnostic only; the daemon remains the verifier. I also rechecked the live protected-resource metadata: it correctly advertises the production issuer and `https://tinyassets.io/mcp`, further concentrating suspicion on WorkOS’s production Resource Indicator configuration.