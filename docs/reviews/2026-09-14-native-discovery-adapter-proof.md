# Native discovery adapter checkpoint — September14 2026

Local feature worktree codex/select-agent-models based on419a3a6a. This continues
the owner-approved Fable shape review, not an additional review round. No remote
push, deployment, actual connected-account discovery, inference or workflow edit.

## Built

- NativeCatalogue/NativeModel normalize opaque execution IDs, exact known input
  modalities, hidden status, recommended default and observation time. Missing
  modality metadata remains unknown. No compiled model releases or HTTP prices.
- BaseProvider has an optional enumerate_models hook. Codex registers a bounded
  app-server stdio metadata adapter, sending only initialize, initialized and
  paginated model/list with includeHidden. It never starts a thread or turn.
- Direct subprocess only; owned snapshot environment and snapshot cwd are
  required by the adapter. Unsupported shell-wrapper executables refuse rather
  than fall back to the maintainer's account. Stderr/upstream errors are not
  exposed. Resource limits refuse, never truncate the list into apparent success.
- Duplicate IDs, conflicting defaults, malformed required fields, repeated
  cursors, oversized results, EOF and timeout refuse. Unknown optional fields and
  notifications are tolerated. Cancellation kills and reaps the metadata child.
- Separate owned discovery lifecycle compares expected custody with current
  owner/universe/service/generation before copying credentials; rechecks after
  enumeration; checks freshness; cleans the snapshot in finally. It carries no
  launch authority and requires callers to fence the accepted assignment/member.
- Claude's unproven enumeration hook returns None. Its accepted explicit IDs and
  provider-default behavior continue; unknown enumeration is not completion.

Official source reverified September14:
[model/list](https://learn.chatgpt.com/docs/app-server#list-models-modellist) and
[initialize lifecycle](https://learn.chatgpt.com/docs/app-server#getting-started).
Installed `codex app-server --help` confirms stdio. Only documentation/help was
queried on the real CLI, not account state. The adapter retains primary writing
through codex exec.

## Verification

Initial adapter group on Windows Python3.14 and actual Linux Python3.11.16:
136 passed, zero skips on both. Linux git2.47.3/bwrap0.12.0. Tests use real Python
child processes as protocol peers, not a real provider account. They prove
multi-page/hidden/new-ID handling, failure sanitization and process cleanup.

The final group adds seven owned-lifecycle cases: success, unknown, provider
error, cancellation, rotation, foreign owner and stale metadata. Current-custody
storage and snapshot copying are mocked in those seven cases; do not claim
end-to-end live vault custody from them. Final group September14 around06:36–
06:38UTC: **143 passed, zero skips on Windows (9.01s); 143 passed, zero skips
on Linux (4.09s)**. Ruff is clean, strict OpenSpec validation passes, and the
rebuilt plugin runtime/import probe passes (439 runtime files). No CI result
for this checkpoint is claimed here.

Command: `python -m pytest -q tests/test_native_model_discovery.py tests/test_native_model_execution.py tests/test_native_model_authority.py tests/test_providers.py --tb=short --disable-warnings -rs`.
Linux runs the same arguments through `python3 scripts/linux_oracle.py --` from
WSL Ubuntu with GIT_DIR/GIT_WORK_TREE pointed at this feature worktree.

## Not complete / next wiring

This is a tested internal seam, not live account enumeration. The existing
served_model_plan._native_models still displays only provider default/accepted
declarations. Connect this owned snapshot into advisory display with assignment
rechecks; require fresh membership at selection/launch for discovered scope; add
strict native enumeration evidence to workflow selection. Do not turn metadata
into authority or silently change owner-declared semantics. Test rotation and
cancellation across the actual store/member boundary before launch integration.

Windows .cmd adapter resolution and the direct Claude initialization seam remain
unproven. HTTP workflow tools/round allowance, final release review, CI, installer
timeout, deploy containment/canary and ordinary rendered app proof remain open.
