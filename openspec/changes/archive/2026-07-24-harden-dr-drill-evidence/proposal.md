## Why

DR drill run `30060401009` failed before Droplet creation with only curl exit
22 because the workflow suppresses DigitalOcean's HTTP status/body and treats
a failed key-list request like an absent key. The same drill also trusts an
unvalidated primary-host path, streams it without end-to-end checksum proof,
and considers MCP liveness sufficient without proving representative restored
state.

## What Changes

- Fail before provisioning unless the selected primary-host artifact is an
  absolute, readable, non-symlink `tinyassets-data-*.tar.gz` file under the
  canonical backup directory and contains a safe `_data` archive with at least
  one regular-file sample.
- Preserve fixed-cap, credential-redacted DigitalOcean HTTP/transport
  diagnostics through one standard-library helper; never reinterpret a failed
  key-list request as “key absent.”
- Stream with pipeline failure propagation and prove the source/destination
  SHA-256 values match before restore.
- Restore the exact transferred local file and verify one representative
  archive member's path and SHA-256 in the restored Docker volume before the
  MCP probe can be green.
- Record artifact checksum and representative-state proof in the successful
  drill log and failure/summary evidence; make any failed Droplet deletion red
  with durable ID/run/diagnostic escalation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: strengthen the manual fresh-host DR drill's input,
  provisioning-diagnostic, transfer-integrity, restored-state, and durable
  evidence requirements.

## Impact

The change affects `.github/workflows/dr-drill.yml`, a standard-library
DigitalOcean request helper and its tests, the focused workflow tests, the
canonical uptime specification, and the DR drill log. It adds no third-party
runtime dependency and performs no live dispatch until the hardened workflow
lands.
