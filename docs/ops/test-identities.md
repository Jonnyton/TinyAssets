# Test identities and scoped first-contact reset

This runbook creates repeatable first-contact and multi-user proof without an auth bypass or a global
production wipe. Test identities use the same WorkOS authorization and TinyAssets connector path as
every real founder.

## Security boundary

- Give each alias its own real WorkOS user and chatbot account/connector grant.
- Configure aliases to resolved WorkOS subjects only. Never store bearer tokens, OAuth credentials,
  passwords, or API keys in the roster.
- Never pass a subject directly to the command. The operator selects an allowlisted alias.
- Verify the live request through `get_status.request_identity`: `bearer_present` must be true and
  `subject` must exactly match the selected alias. The token is never returned.
- Stop on an unknown/anonymous subject. Never substitute host environment identity or credentials.

Configure at least two unique identities in the operator environment:

```powershell
$env:TINYASSETS_TEST_IDENTITIES='{"alice":"user_01...","bob":"user_02..."}'
```

The roster is private operator configuration. Session logs may name an alias and the observed subject,
but must never contain credentials or the full roster.

## Plan before applying

Run this against the live data volume from an authenticated operator shell, not through MCP:

```powershell
python -m tinyassets.reset plan --data-dir C:\data --identity alice
```

The JSON plan is read-only. Review its exact primary-key objects under `rows`, every entry under
`universe_dirs`, the resolved `principal`, and `preserved`. It includes the identity's home and
self-owned universes plus that actor's ACL grants. It preserves other identities, reusable branch
commons, run history, and wiki data.

Apply only the unchanged plan hash you reviewed:

```powershell
python -m tinyassets.reset apply --data-dir C:\data --identity alice --plan-id sha256:...
```

The command locks and recalculates scope before deletion. A mismatch fails closed. On success it emits
a `reset_id` and stores a private backup under `<data-dir>/.resets/<reset-id>`. Re-running an empty
identity reset is a no-op.

## Restore

Enumerate the restore before changing state:

```powershell
python -m tinyassets.reset restore --data-dir C:\data --identity alice --reset-id r-...
```

Then restore after review:

```powershell
python -m tinyassets.reset restore --data-dir C:\data --identity alice --reset-id r-... --confirm
```

Restore refuses to overwrite any new row or universe directory created after reset. Resolve that
conflict manually; never widen or force the restore.

## Live first-contact and isolation proof

1. Authenticate the dedicated chatbot account through the normal connector OAuth flow.
2. Call the connector normally and record `get_status.request_identity` (never a token). Stop unless it
   matches the selected alias.
3. Plan, review, and apply that alias's reset; retain the `reset_id`.
4. Open a new temporary/incognito chat and exercise first contact. Incognito clears chat context, not
   identity; the resolved status subject remains the proof.
5. Repeat through a second real account. Verify each founder sees only their permitted private
   universes and cannot enumerate or write the other's state.
6. Restore if the mission requires the prior state. Retain mutation-test, rendered-chat, and post-fix
   clean-use evidence under the normal `ui-test` process.

The legacy `reset(data_dir, confirm=True)` operation is global and is not part of this workflow.
