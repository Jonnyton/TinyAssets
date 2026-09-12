# Independent shared-authority implementation review

September 9, 2026. Claude reviewed exact fc617195, exit 0 after 184 seconds.
Scope: the shared-validator refactor only; not model-policy, candidate authority,
HTTP tools, fallback routing or UI approval. No blocking findings; nonblocking
service-map duplication remains part of the future provider-neutral integration.

Review is complete and the focused test file ran. Writing up the findings now.

**Review of fc617195 (diff b3bb8956..fc617195), shared serving-authority refactor only.** I read both changed modules, the baseline, the differential test, the proof doc, the router call site, and the helpers the shared validator calls. I ran the one new test file on this machine.

Test run on Windows, Python 3.14.3:

```
tests/test_served_authority_shared_chain.py  23 passed in 2.32s
```

That matches the proof doc's "twenty-three new checks" (2 providers × 10 conditions, plus 2 live-custody cases, plus 1 delegation check). I did not rerun the other three files or the Linux run, so the 70/3 and 72/1 figures are unverified but consistent.

**AGREE, with citations**

- **Permission and root isolation preserved.** Every lookup in the helper is keyed by the authenticated principal, and dispatch now passes `base_path=Path(base_path)` so the open-grant ledger reads use the same root as before (`tinyassets/provider_assignment.py:1224-1233`, `tinyassets/provider_serving_binding.py:635`). Readiness callers at lines 447, 745, 832, 902 are untouched and keep the universe-parent default. The sole production caller passes the universe parent as base anyway (`tinyassets/providers/router.py:504`), so the explicit root is a faithful preservation rather than a behavior change.
- **Carrier and exact-agent gates untouched.** Carrier universe match, trusted source set, converse/writer gate, and the status/creator/revision triple all remain at the execution boundary (`provider_assignment.py:1176-1218`). The helper's added `isinstance(provider_ref, str)` check is strictly tighter than the baseline.
- **Hard-coded converse/writer in the helper is equivalent.** Dispatch rejects any other role or operation before the store opens (`provider_assignment.py:1203`).
- **Custody tuple compare is equivalent** to the baseline `_exact_custody`. The binding digest is compared to the custody digest, which is already required to equal the assignment digest.
- **Revocation and rotation.** The same `verify_open_grant_custody` runs with the same arguments and root. Differential tests for revoked grant and rotated credential pass for both implementations.
- **Snapshot lifecycle and exception propagation unchanged.** The helper never snapshots. Snapshot creation and the `finally` cleanup stay in dispatch, body errors re-raise raw when authority was issued, and pre-yield failures wrap to the held error. The test asserts the snapshot directory is gone afterward.
- **Shared admission lock retained** at `provider_assignment.py:1179`. The helper takes no lock, so calling it under the readiness callers' exclusive lock and dispatch's shared lock is safe. Deferred `BEGIN` is unchanged.
- **Packaging mirror copies are byte-identical** to source for both modules.
- **No schema, candidate, fallback, or model activation** in the diff. The provider service map still has exactly two entries.

**DISAGREE_CONCERN, none blocking**

- **Check ordering changed on the HTTP path.** The baseline compared custody digests before the live grant verification; the helper does the live verification first. Outcome is identical because `verify_open_grant_custody` handles a missing custody row itself (`provider_serving_binding.py:287`), and the extra ledger read on the failure path is read-only. Only the chained cause text differs.
- **Internal error messages collapsed** to one string for assignment, binding, and custody failures. Outward held error is unchanged, so this affects logs only.
- **Dead branch in dispatch.** The `service is None` guard at `provider_assignment.py:1258` is now unreachable, because the helper's dictionary subscript raises first. This is the one spot where a future candidate-set change could diverge: adding a provider to the shared service map without updating dispatch's private two-entry map would hold a request that readiness accepted. That is future candidate-set design, not a defect here.
- **Differential coverage gaps.** The new file has no foreign-principal, stale-revision, provider_ref-mismatch, or credential-digest-tamper cases against the baseline. Those are likely exercised by the other three files in the proof run, but the baseline comparison itself does not cover them.

No real blocker found.

VERDICT: APPROVE


