The continuation hook lists dispatches in a different worktree that are outside this assignment. Per the assignment's constraints I am not acting on them. Here is the complete deliverable again, in full.

## Independent Fable 5.1 exact-code review, round three of three

Candidate 91409a36 against deployed base 005b01df, reviewed in this worktree by reading the two shape reviews, the disposition doc, the full diff of every authored file, and tests/test_model_access_requests.py. No edits, subprocesses, worktrees, or test runs were made.

### Verified in code

**Self-consent and request mutation (AGREE, no defect).**
- The action allowlist is closed: `validate_action` refuses any key outside the five asker fields, so `previous_membership`, `expected_assignment_digest`, `expected_assignment_generation` and `consent_version` can only be written server-side by `capture_action` (`tinyassets/api/model_access_requests.py:15-19`).
- The dedupe key is computed after capture (`tinyassets/api/pending_requests.py:734-741`), so the row the owner sees is the row that executes, and `answer_request` re-derives and compares it before dispatch.
- Fieldless is enforced twice: at creation in `_validated_fields`, and at answer where any stored field or submitted value refuses (`pending_requests.py:1440-1441`). `dont_ask_again` is forced off on allow, and storage nulls a standing ALLOW for action-bearing asks (`tinyassets/storage/pending_requests.py:163-182`). The served surface has no answer operation and a test proves it.
- The deny branch returns before any dispatch, so a declined answer never binds.

**Replay and custody change (AGREE).** `execute_action` re-resolves every source at answer time and refuses if the resolved root or membership differs from the stored proposal. A grant, alias, or held-provider change after the tab was shown cannot publish anything other than what was disclosed. Every publishing path publishes exactly `proposed`. Each classifier state requires either the original digest or an exact membership match.

**Sequence disposition (AGREE).** Enable-only requires ready state, exact membership, matching `provider_ref`, and either the untouched digest or R+1 with generation greater than G. Failed or pending retry requires R unchanged, exact membership, and generation greater than G. Bind pins the observed digest and current home before the lock and inside both transactions. `set_serving` checks the digest before discovery and again inside the write transaction. The shared admission taken in `_observe` is released before bind or enable, so there is no reentrant nesting. Tests cover two failed publications then a partial reconnect at generation 3, no rebind on retry, a foreign binding republishing, a home change, failed request resolution, and preserved caps and other sources.

**Stale request claiming success or stranding the agent (AGREE).** A superseded state returns `provider_authority_denied` and leaves the row pending. A state already completed by hand to the identical membership resolves without acting, which is truthful. The only strand is the disclosed one: after a successful bind and a failed reconnect the agent is off until the owner retries, and the grant sentence says exactly that.

**Non-authorizing writes and pinned reads (AGREE).** Preference save runs as the server-derived actor with `require_founder_home` plus `require_current_home=True` and touches no assignment. Both the served and universe-server routes call the same function. The served connection write accepts `model_discovery` only. Binding reads are SQL-scoped by universe id and binding id. `model_options` sits behind the admission ledger and the untrusted envelope, and the ticket pattern matches the existing served writes so there is no ledger leak.

**UI (AGREE).** Accept sends empty values for fieldless asks, the grant sentence renders in the rail, a `request_pending` error stays local with no relay line to an offline agent, buttons re-enable in `finally` so retry is possible, and a `suppressed: false` result removes the mute claim from the founder's thread line.

### Findings

1. **DISAGREE_CONCERN, low, no code fix required.** No test drives the served path end to end: `write_graph target=pending_request operation=ask` carrying a `bind_model_access` action under `_bind_founder_identity(("write",))`. `_scope` derives identity the same way `_extend_ask_verdict` does (`pending_requests.py:135-139`), so I expect it to work. Live acceptance should include the agent raising the ask, not only the owner answering it.

2. **DISAGREE_CONCERN, low, note only.** The bound state accepts `revision == R+1` without checking what advanced it. An owner who hand-rebinds this binding to exactly the proposed membership and then answers gets enable-only. That is the owner's own consented content, so it is not an authority defect.

3. **DISAGREE_CONCERN, low, note only.** A superseded request stays pending with no agent-side dismissal, as the prior review noted. The owner can clear it. A standing decline with `dont_ask_again` embeds digest and revision in the key, so it is effectively inert rather than harmful.

No DISAGREE_EVIDENCE findings. Linux CI and the live account catalogue proof remain ahead per the progress doc and are not claimed here.

VERDICT: APPROVE
