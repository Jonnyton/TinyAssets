## 1. Permission contract

- [x] 1.1 Add validated GET-only redirect policy with omitted/none compatibility; prove parse, projection, canonical equality and old-reader/writer fail-closed behavior.
- [ ] 1.2 Carry exact redirect permission through connection extension, owner-generated preview and approval; prove full-mode preservation, consent deduplication and incarnation/mode/policy snapshot fencing.

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

Task1.2 remains open: full-mode extension still short-circuits and exact-mode
approval still needs owner-time whole-policy/incarnation fencing. The request
normalizer and sentence now carry the permission, but that is not end-to-end
approval proof. No redirect transport, Linux execution, independent implementation
review, CI, deployment or new owner grant is claimed. Do not ship this foundation
alone or infer capability success from its green tests.
