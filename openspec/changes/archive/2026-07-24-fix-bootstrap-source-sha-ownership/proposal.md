## Why

Exact-landed production DR run `30062890166` selected Debian 13 and installed
Docker successfully, then bootstrap changed `/opt/tinyassets` to the service
user before root resolved the checkout SHA. Git's dubious-ownership protection
rejected that read, leaving `TINYASSETS_SOURCE_SHA` empty and stopping the drill
before restore; the cleanup path still deleted Droplet `587154181`.

## What Changes

- Keep fresh-clone Git operations under root ownership, and run repeat
  bootstrap Git operations as the service account that owns the checkout.
- Resolve and validate the immutable checkout SHA before invoking the shared
  uptime installer, without creating any Git safe-directory exception.
- Cover both fresh-clone and already-owned rerun paths with focused regression
  tests.
- Rerun the production DR drill only from the exact landed commit.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: fresh-host bootstrap and repeat bootstrap must resolve
  the exact source SHA while every Git process runs as the checkout owner.

## Impact

- `deploy/hetzner-bootstrap.sh`
- `tests/test_bootstrap_script.py`
- `openspec/specs/uptime-and-alarms/spec.md`
- production DR workflow evidence
