## Context

The production deploy for PR #2178 installed `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY` and then started the legacy graph-worker fleet with `/etc/tinyassets/request-idempotency.env` in the shared worker `env_file` list. `tinyassets.cloud_worker` copies its environment to the in-process fantasy runtime, and approved source nodes execute Python with full builtins. A source node can therefore construct blocked import names dynamically and read the daemon's admission-minting key.

The key crossed a hostile execution boundary and must be treated as exposed even without evidence of exfiltration. The currently deployed custom-agent runtime remains dark, so the correction does not activate agent execution or change public MCP behavior.

The same deploy slice also writes protected stdin to a plaintext temporary file without signal cleanup, archives only the daemon and tunnel rather than the four workers, and documents stale pre-rename log identities.

## Goals / Non-Goals

**Goals:**

- Restrict request/admission minting authority to the daemon service after the fully resolved Compose merge.
- Provide a deliberate, manual-only path for rotating the exposed production key during the corrective cutover while preserving immutable `set-once` behavior on ordinary deploys.
- Remove the protected-stdin value file on success, command failure, and termination signals without revealing its value.
- Retain offsite logs for the complete deployed daemon, tunnel, and four-worker fleet and make the runbook match current identities.
- Gate redeployment on focused tests and exact-head independent security/deploy review.

**Non-Goals:**

- Sandboxing or replacing the legacy in-process graph executor.
- Activating custom-agent invocations, app ingress, provider routing, or workflow iteration.
- Introducing a multi-key verification ring for pre-rotation admission witnesses. The runtime is dark and the exposed key is newly provisioned, so invalidating its witnesses is the safer recovery choice.
- Changing the separate daemon-only agent-interchange signing key.

## Decisions

### Keep the minting file only on the daemon

`daemon.env_file` retains `/etc/tinyassets/request-idempotency.env`; the shared worker anchor drops it, which also removes it from all inherited worker services. A regression loads the actual YAML and checks every service after anchor resolution. This is preferred over subprocess environment scrubbing because source nodes execute in-process before a subprocess boundary and workers have no current request-admission responsibility.

### Rotate through an explicit manual deploy input

Ordinary automatic and manual deploys continue using `set-once`. A boolean workflow-dispatch input permits `set` only for an intentional rotation run, and the script rejects rotation mode for non-manual events. This makes the exceptional authority change visible in GitHub history and prevents routine deployments from silently rotating a trust root. The repository secret is replaced before the correction deploy; that exact manual run atomically replaces the host value before recreating the daemon and workers.

Alternatives considered were deleting the host file by hand and adding a permanent multi-key ring. Manual deletion creates an untracked mutation window, while a verification ring expands runtime/security scope and preserves trust in witnesses minted under an exposed key.

### Use one process-wide cleanup owner for the plaintext value file

The installer tracks the active value-file path outside `cmd_set`, registers an EXIT cleanup trap, and gives HUP/INT/TERM handlers cleanup ownership before re-raising the original signal. The normal and error paths clear the tracked file through the same helper. This preserves the existing no-secret-in-argv design while closing interruption residue.

Avoiding a temporary file entirely was considered, but the existing multiline-preserving awk path and deployment portability make a small auditable cleanup primitive lower risk for this emergency correction.

### Archive explicit production container identities

`ship-logs.sh` defaults to the daemon, tunnel, and four fixed worker container names. The runbook uses the current `tinyassets` systemd/project, `tinyassets-logs-*` archive prefix, and `tinyassets-logs` Vector container. Explicit names keep missing members visible in dry-run output and tests.

## Risks / Trade-offs

- **[Rotation invalidates witnesses signed by the exposed key]** -> Accept fail-closed invalidation because the runtime is dark and trusting an exposed issuer is worse; verify daemon health and canonical canaries after cutover.
- **[A signal arrives between temporary-file creation and path registration]** -> Assign the `mktemp` result directly to the tracked global and register traps before any value file can be created.
- **[Compose inheritance changes later]** -> Parse the actual compose document in regression tests and assert the secret file is absent from every non-daemon service, not only the base worker.
- **[Automatic deploy races the secret update]** -> Merge only after exact-head review, replace the repository secret immediately before a manual rotation deploy, and use the production mutation concurrency group.
- **[Log collection names drift with fleet topology]** -> Keep the expected identities in one default string and assert the complete current fleet in tests.

## Migration Plan

1. Merge the correction only after focused tests and independent exact-head security/deploy review pass.
2. Confirm no production mutation workflow is in progress.
3. Replace the repository request-idempotency HMAC secret with a newly generated canonical-base64 value without printing or persisting it locally.
4. Manually dispatch the correction image with the rotation input enabled. The deploy replaces the host key before syncing and recreating the corrected Compose fleet.
5. Verify daemon health, exact public MCP handles, resolved worker environments, and production release receipt. Confirm workers do not contain the key name or value.
6. Preserve custom-agent execution as dark; resume the V1 app/workflow lane only after the security gate closes.

Rollback uses the prior image only after fencing workers. Because the prior image reintroduces worker access, it MUST NOT be restored with the rotated key mounted; an emergency rollback must keep workers stopped or use a corrected Compose override until a safe image is available.

## Open Questions

None for implementation. Production rotation and redeploy remain gated on exact-head review.
