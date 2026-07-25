## Context

The manual DR workflow crosses four trust boundaries: workflow input to the
primary host, DigitalOcean's API, a streamed primary-to-drill transfer, and the
restored Docker volume. Today those boundaries are coupled by an unchecked path
and implicit success: `curl -sf` hides API diagnostics, the transfer pipeline
does not propagate its first SSH failure, restore re-discovers a file instead
of naming the streamed artifact, and the final probe proves only daemon/MCP
liveness. Run `30060401009` reproduced the first failure class on landed main:
DigitalOcean provisioning returned curl exit 22 with no Droplet ID and no
actionable HTTP evidence.

## Goals / Non-Goals

**Goals:**

- Reject invalid or unsafe archive selections before paying to provision a
  Droplet.
- Make DigitalOcean failures actionable without logging credentials.
- Bind source preflight, transfer, restore, and restored-state proof to one
  exact archive.
- Preserve evidence and cleanup behavior on every terminal path.

**Non-Goals:**

- Changing `deploy/backup-restore.sh` or its atomic volume-swap contract.
- Adding a new DigitalOcean SDK or runtime dependency.
- Treating one drill as proof of future backup freshness.
- Dispatching the live drill before this change lands.

## Decisions

### Preflight on the primary with Python's standard library

The runner sends the selected path as a shell-escaped positional argument to a
small remote Python program. It resolves the path, confines it to
`/var/backups/tinyassets`, rejects symlinks/non-files/unreadable files and
unexpected names, validates every tar member against the restore safety shape,
and returns the archive SHA-256 plus the smallest regular member's relative
path and SHA-256. Paths cross GitHub outputs as base64 and remain encoded in
rendered workflow/log evidence; digests remain lowercase hex. The confined
remote verifier alone decodes the representative member path.

This duplicates only cheap pre-provision safety and evidence selection. The
restore script remains the authoritative pre-mutation validator on the drill
host, so defense in depth does not weaken its contract.

### Preserve only bounded, sanitized DigitalOcean error details

A small standard-library helper, `scripts/do_api_request.py`, owns every
DigitalOcean request. It accepts only `https://api.digitalocean.com/v2/` URLs,
reads the bearer token from the environment, captures at most 4096 response
bytes on failure, extracts only JSON `id`/`message` when available, replaces
the exact token and bearer-like strings, normalizes control characters, and
emits at most 300 diagnostic characters with HTTP status or transport class.
It never writes a failed raw body to stdout or a GitHub output.

The key-list request must succeed before an empty match can mean “key absent.”
This is preferred over curl's `--fail-with-body`, which can write an unbounded
provider response directly to Actions logs. The helper uses no third-party SDK.

### Checksum-bind the streamed artifact

The transfer step enables `set -euo pipefail`, passes the validated source path
as a quoted remote argument, writes only the validated basename, and compares
the drill-host SHA-256 with the preflight digest. Restore receives that exact
absolute file through `BACKUP_FILE`; it does not list or select another
artifact.

### Prove representative restored state before MCP liveness

After restore, a remote Python verifier decodes the preflight sample path,
confines it to Docker's inspected `tinyassets-data` mountpoint, rejects a
symlink/non-file, and compares its streamed SHA-256 with the archive sample.
Only then may compose start and the MCP probe run.

This proves that at least one exact archive payload reached the live restored
volume while keeping the existing MCP probe as the service-level proof.

### Cleanup is independent of evidence publication and deletion is a state

One `always()` destruction step handles green success, explicit
`destroy_on_failure`, and every pre-probe failure after a Droplet ID exists.
Probe-red with the default input still deliberately leaves the host for
inspection. The destruction step captures the bounded helper diagnostic,
continues only far enough to create/update a `dr-failed` escalation containing
the Droplet ID and run URL, and a final step makes the job red. A failed DELETE
can therefore never coexist with a PASS-only durable record.

The workflow publishes an unqualified PASS log only after the successful-drill
DELETE is confirmed. Successful log and step-summary evidence include archive
and representative-member digests. Log commit/push failure therefore cannot
skip destruction; probe-red and pre-probe failures retain the run URL and
whatever Droplet/artifact metadata exists.

## Risks / Trade-offs

- **[Primary preflight hashes the archive before transfer]** → This adds one
  full sequential read, but avoids provisioning or streaming a corrupt input
  and is bounded by the selected recovery artifact.
- **[The representative member may not be semantically important]** → Its
  purpose is exact restored-byte proof; MCP status separately proves runnable
  service state.
- **[DigitalOcean bodies could contain unexpected text]** → The helper reads at
  most 4096 failure bytes, emits at most 300 normalized/redacted characters,
  and never prints a raw body.
- **[Git push for the durable log can race another main update]** → The workflow
  reports failure instead of claiming a durable log, while `always()` cleanup
  still destroys a successful drill host.
- **[DigitalOcean DELETE can fail after a green probe]** → The job becomes red
  and a `dr-failed` issue retains Droplet ID, run URL, and bounded diagnostic;
  operators can delete it manually without guessing which host leaked.

## Migration Plan

1. Land the spec, workflow, tests, and archived change on `main`.
2. Dispatch drill #3 from the exact landed SHA.
3. If provisioning returns an HTTP error, record its safe diagnostic and
   repair the credential/permission/quota outside this code lane.
4. On success, confirm the committed log contains checksum and representative
   state evidence and the disposable Droplet was destroyed.

Rollback is a normal git revert. No persistent data shape changes.

## Open Questions

None.
