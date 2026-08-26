# External test identities

This runbook prepares repeatable identity acceptance without adding an
impersonation path or a public deletion surface. The operator-only scoped reset
landed in PR #1788 after the cross-store inventory, writer fence, mutation
proof, and crash-recovery gates passed. It remains unavailable to MCP/API
clients and accepts only identities from a private roster.

## Private host configuration

1. In WorkOS, provision two distinct test users through the ordinary
   authorization-server flow.
2. Give each user its own chatbot account and ordinary TinyAssets connector
   OAuth grant. Do not share cookies, connector grants, or bearer material.
3. Store only an alias-to-subject mapping in an access-controlled operator
   secret. Do not commit it, place it in shell history, or include it in test
   output. The roster schema is `revision`, `aliases`, and
   `allowlisted_subjects`; `python -m tinyassets.scoped_reset` rejects extra
   credential-bearing fields and a roster whose ownership or permissions are
   not private to the operator.
4. Configure a dedicated deployment secret named
   `TINYASSETS_IDENTITY_FINGERPRINT_KEY`. It must contain at least 32 bytes of
   high-entropy material and must not reuse an OAuth, provider, maintainer, or
   roster secret. Store it under that exact item name in the operator vault;
   `scripts/secrets_keys.txt` is the canonical loader catalog. Provision the
   same value into `/etc/tinyassets/env`, which `deploy/compose.yml` loads via
   `env_file`, then recreate the daemon. Keep
   `TINYASSETS_IDENTITY_FINGERPRINT_VERSION=v1`; change the version when
   rotating the key so acceptance evidence cannot silently cross rotations.
5. Verify provisioning through the public status read. A provisioned key
   returns `identity_evidence.status=available` and a non-null versioned
   `request_identity.principal_fingerprint`. Missing, short, wrong-type, or
   otherwise invalid configuration keeps the operational status response up
   but returns `principal_fingerprint=null`,
   `identity_evidence.status=unavailable`, a fixed non-secret `reason`, and an
   `evidence_caveats.request_identity` entry. That degraded marker fails
   identity acceptance; it never permits a weak/default-key fingerprint.

Never store tokens, refresh tokens, cookies, provider credentials, passwords,
or auth-home paths in the roster.

## Rendered connector proof

Run identity acceptance only after the fingerprint secret is deployed:

1. Sign in as the first test user through the ordinary connector OAuth flow.
2. In a rendered Claude.ai or ChatGPT conversation, ask the chatbot to check
   the workflow connector's status.
3. Require `request_identity.bearer_present=true` and a versioned
   `request_identity.principal_fingerprint`. Save only the alias and
   fingerprint.
4. Repeat with the second user. The fingerprints must be distinct.
5. Verify `get_status` and `read_graph target=status` report the same
   fingerprint for each request. An explicit unavailable marker or alias
   disagreement fails identity acceptance, but must not remove operational
   status fields such as `active_host` or `release_state`.
6. Follow `.agents/skills/ui-test/SKILL.md` for the public canary, rendered
   client matrix, concurrency proof, and post-fix clean-use evidence.

Do not infer identity from browser cookies, the absence of a login screen, an
incognito chat, or connector UI state. Do not call the MCP directly as final
acceptance evidence.

## Reset boundary

Do not use the confirm-gated global `tinyassets.reset.reset` to recycle one test
identity. Use the operator shell to create and review a read-only plan:

```powershell
python -m tinyassets.scoped_reset plan --data-dir <data-dir> --roster <private-roster-path> --identity <alias>
```

Apply only the unchanged reviewed plan ID:

```powershell
python -m tinyassets.scoped_reset apply --data-dir <data-dir> --roster <private-roster-path> --identity <alias> --plan-id <sha256-plan-id>
```

The command fails closed on an unknown/non-allowlisted alias, a changed plan,
shared or ambiguous state, credentials, active obligations, unsafe paths, or
unclassified stores. It returns an idempotent no-op for an allowlisted identity
with no state. There is still no scoped-reset MCP tool, API route, public
per-universe delete, or user deletion feature.
