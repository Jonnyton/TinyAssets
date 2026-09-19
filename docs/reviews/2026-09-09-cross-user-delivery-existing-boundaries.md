# Cross-user deliverables: existing boundaries and independent fit review

September 9, 2026, Windows/Python 3.14 local source; no production mutation.
Actual owner direction is quoted in
`docs/concerns/2026-09-09-cross-user-deliverable-connections.md`.
Fresh dedicated Chrome extension app tab was reloaded at this continuation and
still ended with the 00:50 PDT collaboration-gap answer; no message was sent.

## Verified fit, not a completed design

| Required behavior | Existing boundary | Reuse / missing distinction |
|---|---|---|
| Receiver-owned execution | `api/runs.py:enqueue_universe_branch_run`; webhook passes persisted receiver principal | Reuse execution/provider binding. Current call takes a whole branch, not an independently exposed selected node. |
| Receiver registration/revoke | `api/webhook_ops.py` through canonical `run_graph` | Exists for bearer webhook URLs; app agent cannot manage it. Not selected-sender identity or a native cross-user link. |
| Sender-known delivery | `webhook_inbound.py:_handle_hook_inner` | Successful response is queued only, no delivery/run ID; token authenticates receiver capability, not a sending user. |
| Safe replay | Existing inbound token/body claim and outbound effect receipt boundary | Reuse machinery appropriately, but a body-equality window is not a general occurrence/link identity. Two intentional identical deliverables need distinct occurrences; retries of one occurrence must not duplicate it. |
| Two-sided receipts | `handoffs/service.py`, `handoffs/store.py` | Existing handoff records are sender-owned real-world outcomes; not a receiver inbox. Do not relabel acceptance as receiver processing. |
| Files/artifacts | `authoring/io.py:read_handle_bytes`, `authoring/store.py:get_file_handle` | Existing handles require the exact owner AND session; passing a handle string is not transfer authority. Reuse byte integrity/manifest primitives with an actual cross-owner transfer boundary. |

`handoffs/adapters.py` starts empty; `rg -n 'register_adapter\(' tinyassets`
found no production registrations. Its store has one `owner_id`, not two-party
access. `handoffs/authority.py:resolve_source` requires completed runs and a
published declaration. Its metadata/credential-key blacklist is NOT itself a
general arbitrary-deliverable contract: a benign object can legitimately contain
a field called `key`. Keep transport credentials out of payloads without claiming
that field-name filtering supports all user deliverables.

## Local boundary experiment

Command: `python -m output.probe-cross-user-inbound-boundary`.
The ignored diagnostic creates only a temporary fixture token/store outside the
repo and records the enqueue arguments; it does not execute a workflow or call
an LLM/external service. September 9 at about 08:18 UTC: exit 0.

- Valid receiver token without sender authentication: HTTP 202, queued.
- Same body replay: HTTP 202, deduped, one recorded enqueue total.
- After receiver revocation: HTTP 404.
- Enqueue principal comes from receiver ownership; a sender claim is only payload.
- No delivery/run/receipt identifier in the success response.

This confirms token intake and revocation, not a defect in their stated bearer
contract. It proves why enabling it alone cannot satisfy selected-user collaboration.

## Focused test evidence and caveat

All runtime files, focused tests and conftest are identical to current origin/main
(verified `git diff origin/main -- tinyassets tests/test_webhook_ops.py
tests/test_webhook_inbound_hardened.py tests/test_handoff_authority.py tests/conftest.py`).

- `python -m pytest -q tests/test_authoring_file_io.py --tb=short`: 21 passed.
- Hardened webhook file alone: 16 passed, 10 deprecation warnings, 7.71 seconds.
- Webhook ops + hardened webhook + handoff authority together: 41 passed / 12 failed.
  Failures start at owner mint returning universe_access_denied.
- Minimal ordering reproduction, webhook ops file followed by only the owner-mint
  test: 5 passed / 1 failed. Owner-mint alone: 1 passed.

The ordering dependence was a test isolation defect, not a live ACL defect.
After reproducing the six-test failure in-process, inspection of loaded module
resolvers found `api.branches._base_path` and `api.permissions._base_path` still
pointing at `tests.test_webhook_ops._wire.<locals>.<lambda>` after fixture cleanup.
The lazy imports captured the monkeypatched helper; restoring the original in
`helpers` did not restore those aliases. Replacing that patch with the canonical
`TINYASSETS_DATA_DIR` environment setting keeps imported resolver functions real.
No runtime ACL or source code changed.

Candidate September 9, Windows/Python 3.14:

- Original combined group: 53 passed, 10 deprecation warnings, 11.42 seconds.
- `python -m pytest -q tests/test_handoff_authority.py
  tests/test_webhook_inbound_hardened.py tests/test_webhook_ops.py
  tests/test_authoring_file_io.py --tb=short`: 74 passed, 10 warnings, 11.75 seconds.
- `python -m ruff check tests/test_webhook_ops.py`: passed.
- `python -m pytest -q tests/test_concerns_index_matches_the_directory.py`:
  79 passed. `git diff --check`: passed.

The fixture fix is local, not a deployed platform capability or Linux evidence.

## Independent Claude review

Dispatched once via `peer_agent.py claude --timeout 360` with a no-nesting,
read-only source-fit brief. Exit 0 after 317 seconds. The wrapper's final output
was a stop-hook closing note; substantive review recovered from the SAME session
`57403540-e185-4af0-82cb-8b95eef8081f`, not a replacement reviewer.
Verdict: **REUSE_PARTS**. This is source-fit review, NOT implementation approval.

- AGREE: the complete owner-to-owner node delivery is absent.
- DISAGREE_EVIDENCE: receiver execution and revoke controls already exist in the
  webhook path; they must be distinguished from missing served access and identity.
- DISAGREE_CONCERN: public bearer webhooks lose sender identity; widening the old
  handoff table imports real-world outcome side effects and sender-only constraints.
- Direction: native authenticated delivery through the existing external-effect
  receipt boundary; receiver contract/allow-list, two-party delivery record,
  receiver execution and explicit artifact access. No new provider-specific path.

Main disposition: retain these reuse boundaries, explicitly include selected-node
entry and arbitrary deliverables rather than treating whole-branch JSON submission
as completion. Verify actual APIs/storage/authority in a reviewed design before
implementation. Do not auto-adopt the peer's suggested schema or credential filter.
