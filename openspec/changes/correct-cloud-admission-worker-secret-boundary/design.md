## Context

The production deploy for PR #2178 installed `TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY` and then started the legacy graph-worker fleet with `/etc/tinyassets/request-idempotency.env` in the shared worker `env_file` list. `tinyassets.cloud_worker` copies its environment to the in-process fantasy runtime, and approved source nodes execute Python with full builtins. A source node can therefore construct blocked import names dynamically and read the daemon's admission-minting key.

The key crossed a hostile execution boundary and must be treated as exposed even without evidence of exfiltration. The currently deployed custom-agent runtime remains dark, so the correction does not activate agent execution or change public MCP behavior.

The same deploy slice also writes protected stdin to a plaintext temporary file without signal cleanup, archives only the daemon and tunnel rather than the four workers, and documents stale pre-rename log identities.

## Goals / Non-Goals

**Goals:**

- Restrict request/admission minting authority to the daemon service after the fully resolved Compose merge.
- Provide a deliberate, manual-only path for rotating the exposed production key during the corrective cutover while preserving immutable `set-once` behavior on ordinary deploys.
- Avoid secret-only value staging, protect the full target candidate at mode 0600, atomically replace the live file, and preserve it on every pre-rename failure without revealing the value.
- Retain offsite logs for the complete deployed daemon, tunnel, and four-worker fleet and make the runbook match current identities.
- Gate redeployment on focused tests and exact-head independent security/deploy review.

**Non-Goals:**

- Sandboxing or replacing the legacy in-process graph executor.
- Activating custom-agent invocations, app ingress, provider routing, or workflow iteration.
- Introducing a multi-key verification ring for pre-rotation admission witnesses. The runtime is dark and the exposed key is newly provisioned, so invalidating its witnesses is the safer recovery choice.
- Changing the separate daemon-only agent-interchange signing key.

## Decisions

### Keep all minting-key sources only on the daemon

`daemon.env_file` retains `/etc/tinyassets/request-idempotency.env`; the shared worker anchor drops it, which also removes it from all inherited worker services. While the deploy fleet is fenced, the correction also deletes any stale duplicate from `/etc/tinyassets/env`, fails closed if the shared file is unreadable or still contains the key, and checks each running worker's actual environment without printing it. Regressions load the actual YAML and inspect the deploy script. This is preferred over subprocess environment scrubbing because source nodes execute in-process before a subprocess boundary and workers have no current request-admission responsibility.

### Rotate through an explicit manual deploy input

Ordinary automatic and manual deploys continue using `set-once`. A boolean workflow-dispatch input permits `set` only for an intentional rotation run, and the script rejects rotation mode for non-manual events. Before transmitting the replacement key, rotation compares the deployed `/opt/tinyassets/compose.yml` hash with the reviewed source file, requires the shared env to lack the key, and proves all four running workers lack it. This forces a two-phase recovery: first deploy and verify the corrected boundary with the old key, then replace the repository secret and rotate using the same correction image. Any failure after replacement can recover only through the already-corrected host Compose file.

Alternatives considered were deleting the host file by hand and adding a permanent multi-key ring. Manual deletion creates an untracked mutation window, while a verification ring expands runtime/security scope and preserves trust in witnesses minted under an exposed key.

### Parse Docker Compose env declarations once and fail closed

One Bash helper recognizes the production Compose grammar relevant to key identity: optional leading whitespace, optional `export` plus whitespace, optional whitespace before the delimiter, and either `=` or `:`. `set`, `set-once`, `delete`, and the read-only `assert-absent` command all use that helper. `set-once` counts matching assignments and exits with the immutable-refusal code on the second match, without writing or printing either value. `delete` removes every recognized shape, and both scrub and rotation invoke `assert-absent` before any worker recreation or key transmission. A single empty assignment remains the documented bootstrap case.

### Use a protected sibling transaction and atomic rename

The installer reads and reconstructs the small environment file entirely in the current Bash process. The protected value is never placed in child argv/environment or a secret-only staging file. Before changing the live target, the helper creates a mode-0600 sibling transaction in the same directory, writes the complete candidate from the Bash buffer, applies final ownership/mode, syncs it, and atomically renames it over the target.

EXIT/HUP/INT/TERM cleanup removes an incomplete transaction, and signal handling re-raises the original signal. Any write, metadata, sync, or rename failure occurs before replacement and leaves the live file byte-for-byte unchanged. This full-file transaction is necessary for atomic replacement and is distinct from the rejected prior design, which persisted the protected value alone in a broadly reusable temporary file before editing the live target.

### Archive explicit production container identities

`ship-logs.sh` defaults to the daemon, tunnel, and four fixed worker container names. The runbook uses the current `tinyassets` systemd/project, `tinyassets-logs-*` archive prefix, and `tinyassets-logs` Vector container. Explicit names keep missing members visible in dry-run output and tests.

## Risks / Trade-offs

- **[Rotation invalidates witnesses signed by the exposed key]** -> Accept fail-closed invalidation because the runtime is dark and trusting an exposed issuer is worse; verify daemon health and canonical canaries after cutover.
- **[Compose env grammar grows beyond the recognized key forms]** -> Keep one parser helper, exercise every currently accepted Compose assignment shape against the installed Compose version, and fail closed through actual running-worker environment proof after deploy.
- **[Transaction contains the complete environment briefly]** -> Create it beside the target under mode 0600, never stage the value alone, never pass it through child argv/environment, clean it on exits/signals, and rename only after the complete candidate is synced.
- **[Compose inheritance changes later]** -> Parse the actual compose document in regression tests and assert the secret file is absent from every non-daemon service, not only the base worker.
- **[Automatic deploy races the secret update]** -> Merge only after exact-head review, complete and verify the ordinary corrected-boundary deploy first, replace the repository secret immediately before the second manual rotation deploy, and use the production mutation concurrency group.
- **[Log collection names drift with fleet topology]** -> Keep the expected identities in one default string and assert the complete current fleet in tests.

## Migration Plan

1. Merge the correction only after focused tests and independent exact-head security/deploy review pass.
2. Confirm no production mutation workflow is in progress.
3. Build and ordinarily deploy the reviewed correction with the existing key; verify the exact corrected Compose hash, shared-env absence, and running-worker absence proof.
4. Replace the repository request-idempotency HMAC secret with a newly generated canonical-base64 value without printing or persisting it locally.
5. Manually dispatch the same correction image with the rotation input enabled. The deploy re-proves the already-live boundary before transmitting and replacing the host key.
6. Verify daemon health, exact public MCP handles, worker environments, and the production release receipt after rotation.
7. Preserve custom-agent execution as dark; resume the V1 app/workflow lane only after the security gate closes.

Rollback uses the prior image only after fencing workers. Because the prior image reintroduces worker access, it MUST NOT be restored with the rotated key mounted; an emergency rollback must keep workers stopped or use a corrected Compose override until a safe image is available.

## Open Questions

None for implementation. Production rotation and redeploy remain gated on exact-head review.
