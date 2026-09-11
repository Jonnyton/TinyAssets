## 1. Permission contract

- [x] 1.1 Add validated GET-only redirect policy with omitted/none compatibility; prove parse, projection, canonical equality and old-reader/writer fail-closed behavior.
- [x] 1.2 Carry exact redirect permission through connection extension, owner-generated preview and approval; prove full-mode preservation, consent deduplication and incarnation/mode/policy snapshot fencing.

## 2. Broker execution

- [ ] 2.1 Add bounded child-only redirect metadata and shared DNS/transport deadline plumbing without changing no-follow behavior; differential-test the legacy path.
- [ ] 2.2 Implement approved redirect chains, per-hop authority/network rechecks, anonymous cross-origin behavior and sensitive-material declassification; prove all design refusal and budget cases.
- [ ] 2.3 Verify the real broker/effect/code-node composition returns usable bounded text with no redirect-capability leaks, duplicate effects or private-workflow changes.

## 3. Delivery and acceptance

- [ ] 3.1 Run focused Windows and actual Linux tests plus independent exact-head implementation review; address concrete findings and pass CI without weakening gates.
- [ ] 3.2 Deploy, verify protected SHA/canary evidence, and obtain rendered app proof of owner-approved redirected download capability through ordinary conversation; keep both-client compatibility and owner approval boundaries.
- [ ] 3.3 Sync only shipped requirements, archive this delivery and update the broader goal without declaring unrelated channel migration complete.

The source design received independent ADAPT150s; all six required corrections
were incorporated before this delivery extraction. This is the approved-download
capability's first implementation lane, not a fourth model-selection review.
The model review exception remains pending. The broader parent28-task inventory
is preserved rather than mechanically split or relabelled complete.

## Local evidence — September 11, 2026 20:53 UTC

Windows working tree: `python -m pytest -q tests/test_http_redirect_policy.py
tests/test_pending_requests.py tests/test_http_connection_provisioning.py
tests/test_full_channel_access.py tests/test_outbound_http_connection.py
tests/test_outbound_ssrf_driver.py --tb=short` passed313 tests in25.47s,
no skips. Focused ruff checks passed. Plugin mirror build passed its import
probe; strict OpenSpec validation and delivery admission passed.

The30 new policy/request tests cover strict GET-only parsing, omitted/none
identity, explicit permission projection, request normalization/generated
disclosure and rollback loss without changing exact/full mode. The frozen
class, parser and SQL writer match deployed cd28c3806c44ff63612adb8fcc709b622f89a6fd
by AST comparison; five shared leaf validators are unchanged. This is frozen
policy-reader/writer evidence, not old-binary network execution proof.

Task1.2 was incomplete at this checkpoint; the newer evidence below supersedes
that local implementation status. No live capability was established here.

## Approval evidence — September 11, 2026 21:04 UTC

The same Windows command plus `tests/test_http_redirect_approval.py` and
`tests/test_workspace_authority.py` passed409 tests in31.60s, no skips.
The34 new real temporary owner/request/ledger tests began with13 failing cases,
then prove full/exact approval, preserved scopes/mode/credential reference,
changed owner-time policy, changes immediately before SQL write, connection and
grant revocation, missing/partial snapshots, old unversioned requests, equivalent
reordered requests, non-reuse of old no-follow approval and new-key setup.

Redirect approval takes one resource/policy row snapshot and writes under
endpoint/scope/mode/incarnation checks plus active grant and unrevoked connection
checks. Generated request disclosure has a server-owned version marker in the
existing consent identity. A legacy row cannot authorize it after upgrade.
The tool description now explains how users can request this permission;
the existing app renders the server's grant_sentence as text.

Focused ruff, strict spec validation, mirror build/import and diff checks pass.
Task1.2's local approval implementation is complete, not live acceptance.
Transport remains unimplemented. Actual Linux, independent implementation review,
CI, deployment and rendered owner-approved downloads are still required. Do not
ship the permission-only foundation or claim its tests prove network behavior.
