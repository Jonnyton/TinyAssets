# Native model picker snapshot composition repair

Scope: capability3 follow-up to deployed PR3865/adfdddf3057d. Its process
cleanup fix passed41hosted native tests but live picker acceptance exposed a
separate existing composition defect: native snapshots were passed to HTTP-only
validation and warning serialization. No usable-picker closure was claimed.

September17,2026, Chrome original-owner app at21:58UTC: Refresh models returned
"Could not refresh models"; service traceback identified model_options.py:248,
AttributeError NativeDiscoverySnapshot.models. The succeeding serializer also
assumed a warnings field absent on native snapshots. No credential, preference,
authority or private workflow was changed during diagnosis.

## Shape and regression

Fable shape review via peer_agent.py, claude-fable-5-1, read-only, terminal exit0
in267s: ADAPT. Reuse existing _assert_plan_snapshot; native freshness plus
same-transaction custody comparison rather than nested credential-store reads.
HTTP validation is unchanged; warnings explicitly dispatch by snapshot type.
The review's note about an already-untracked regression refers to the author's
tests written concurrently with the review, not an unrelated user's file.

Windows/Python3.14 command before fix:
`python -m pytest -q tests/test_native_model_options_api.py tests/test_model_options_api.py --tb=line`
Result3failed/26passed; all failures reproduce the live AttributeError. Expanded
green cohort (native picker, HTTP picker, native integration, HTTP publication):
73passed in12.29s before two additional mixed-source cases. Final results in PR.

Tests use real ownership/custody/serving stores and public read_graph dispatch,
synthetic provider metadata only. They cover native default plus discovered
choice, a newly appearing model, unknown/failed enumeration preserving default,
expiry and custody revocation, private-field exclusion, no inference, and mixed
native/HTTP source isolation. Canonical/delta specs synchronized; plugin mirror
rebuilt, import probe/ruff/diff checks pass. Hosted Linux gate remains required.

## Release acceptance

Not yet deployed. Required: exact-head independent review, hosted checks,
protected deployed-SHA/public canary, then refreshed ordinary app model picker,
explicit accepted nonempty model greeting without retry/fallback, restore saved
Automatic, and exact "Retest your workflow checklist". Preserve all user work.
Rollback: revert this isolated snapshot-composition patch through reviewed
release; no migration, persisted preferences or user data require reversal.
Full capability3 remains open for Codex answer identity/default/fallback proof.
