# Repair the dormant resolver's pip configuration contract

## Current implementation and verification, September15 2026 UTC

Fable5.1 shape review returned ADAPT; output/resolver-pip-shape-fable.md holds
the complete review and final recap. Lead verified the dispatch process ended
before consuming the result; no recovery redispatch. Accepted corrections:
literal os.devnull (not npm's Windows-uppercase NULL_DEVICE), explicit
--disable-pip-version-check and --no-input in both commands/allowlist because
isolated mode ignores those option environment variables, real parser and config
loader proofs. No permissions, registry scope, acquisition or jail change.

Local implementation removes --no-config, suppresses configuration through the
seven-key explicit child environment, retains old inert environment keys for
compatibility, and corrects the design's invalid command. npm behavior unchanged.
Canonical plugin rebuilt (443 files/import probe passed).

Windows Python3.14.3/pip25.3, September15 around07:22-07:24UTC:
- Real download/install parser tests each reproduced SystemExit2 for the old
  command. Config control confirmed global/site poison loads despite isolated;
  after correcting the test to use pip's get_value (items shape varies by pip
  version), the unfixed builder failed KeyError for missing PIP_CONFIG_FILE.
- Corrected code: `python -m pytest -q tests/test_workspace_resolver.py`
  48passed0.94s; `python -m pytest -q tests/test_workspace_resolver.py
  tests/test_workspace_provision.py --tb=short` 332passed1.60s, no skips.
- `python -m ruff check tinyassets/workspace_resolver.py
  tests/test_workspace_resolver.py` passed. No installs, downloads, host config
  writes or credentials used in these parser/temporary-config tests.
- Required `python scripts/linux_oracle.py -- -q tests/test_workspace_resolver.py
  tests/test_workspace_provision.py` could not reach a Linux engine, before
  collection. Its owned stalled docker-info child90280/parent60828 was verified
  then stopped; oracle33776 exited1. No Docker reset or Linux-pass claim.
  Hosted Linux CI is still required before landing.

Independent exact-head implementation review, CI, deployment containment and
canary remain. This dormant repair is not a browser/provisioning success and
cannot close the cloud-preview concern; app workflow definitions are untouched.
Rollback uses normal release rollback if needed; no storage migration/data loss.

## Original pre-build note (historical)

Scope: internal bug fix to workspace_resolver.py and its tests, not completion
of workspace provisioning and not a new browser-specific tool. Base production
bd8eaa957b191f5c540493d0a3a1d3eafc6c672d. No runtime edits yet.

Existing builders emit --no-config, which pip rejects. Both download and offline
install are affected; tests assert the invalid argv instead of invoking pip's
parser. The existing resolver_environment is an explicit six-key mapping and
does not suppress global/site pip configuration. No current caller wires these
builders into checkout, which still reports admission-only provisioning.

Proposed narrow repair: remove unsupported --no-config from both builders and
their fixed-flag allowlist; add PIP_CONFIG_FILE=os.devnull to the explicitly
constructed child environment. Preserve --isolated, exact index, hash-only
binary closure, offline no-index, Node behavior and no ambient environment.
This repairs the existing intended no-configuration contract, not permissions.

Primary sources verified September15,2026:
- [pip configuration](https://pip.pypa.io/en/stable/topics/configuration/#pip-config-file)
  documents the null-device value disabling all configuration files.
- [pip CLI](https://pip.pypa.io/en/stable/cli/pip/)
  documents isolated mode; it is not a replacement for disabling global/site
  configuration. No invented generic provider compatibility is claimed.

Required proof before landing: reproduce invalid builder argv with pip's real
parser; verify both corrected complete argv with --help (no network/install);
exercise actual pip configuration loading against temporary poisoned global,
user and site fixtures with/without the null-device setting. Never touch the
host's real config or print credentials. Keep exact-environment assertions and
show unrelated PIP_/proxy/index/credential variables are not inherited. Linux
oracle/CI and base comparison remain required; local Docker currently fails
startup, not a test failure. No checkout integration or browser success claim.

Fable5.1 pre-build review is requested before implementing this researched
configuration change. This is a bounded internal command bug, not another round
of the original workspace architecture review. Browser binary acquisition,
system libraries, resolver jail/offline installation and cloud-agent captures
remain separately unimplemented requirements.
