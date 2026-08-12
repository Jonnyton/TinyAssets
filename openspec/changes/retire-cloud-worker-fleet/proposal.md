## Why

Production no longer has a fixed provider-shaped cloud worker fleet, but deployment, queue execution, and provider routing still assume four pinned workers and ambient host credentials. The repository must match the worker-free runtime and use the already-landed per-universe serving binding as the sole LLM execution authority.

## What Changes

- **BREAKING** remove the four cloud-worker services, worker deployment/recovery inputs, host-pool client package, cloud-worker supervisor/healthcheck, and their fleet-only tests.
- Run queued branch-task and automation turns from the daemon by resolving the task universe's assigned serving credential.
- Hold work with typed reason `no_requester_owned_executor` when no assigned credential is available; never borrow host credentials or switch providers.
- **BREAKING** remove provider fallback chains, free-provider chaining, writer pins, and ambient host-credential fallback from universe-scoped execution.
- Preserve the queue and non-LLM daemon machinery: ingress, memory, canaries, status, scheduling, and transactional authority state.
- Make production deployment assert the worker-free service set: daemon, tunnel, logs, and profile-gated Slack agent.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `provider-routing`: replace fallback-chain and pin behavior with exact assigned-serving-credential routing and fail-closed holds.
- `daemon-runtime-and-dispatch`: replace cloud-worker queue consumption with credential-driven daemon consumption and worker-free deployment ownership.
- `daemon-identity-and-host-pool`: remove the retired host-pool REST client/runtime surface.
- `credential-vault`: require universe-scoped execution to use only the credential selected by its serving binding, without ambient fallback.
- `desktop-host-runtime`: the source tray spawns a credential-neutral daemon (no `--provider`/`TINYASSETS_PIN_WRITER`; ambient provider/credential env stripped) that resolves each universe's assigned serving credential at runtime, instead of provider-pinned per-provider daemons.

## Impact

Deployment compose/workflows and fences lose worker services and secrets. The cloud-worker, healthcheck, automation fleet runtime, host-pool package, and provider fallback code are deleted or reduced to credential-driven daemon paths. Queue/automation/provider tests are rewritten around exact serving bindings and typed holds; fleet-only tests are deleted. The Claude plugin mirror is rebuilt from canonical `tinyassets/` sources.
