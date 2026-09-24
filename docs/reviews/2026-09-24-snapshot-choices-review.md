# Immutable execution-choice preservation — independent review

2026-09-24 UTC. Codex root reviewed Claude-authored runtime/test commit82ad5a91
in wf-resume-surface-design. Full serializer and new regression diff inspected;
root corrected inaccurate comments (no runtime behavior change), rebuilt the
plugin mirror and synced the delta into the main capability spec.

AGREE / APPROVE: conditional non-None preservation fixes the demonstrated field
loss and content-identity collision. Existing stored rows are not rewritten;
unset snapshots keep a literal checked digest. Existing policy validation,
provider access, visibility and immutable-row reads are unchanged. No new public
resume operation or claim of safe uncertain-effect replay is approved here.

Root independent Windows Python3.14 check:
`python -m pytest tests/test_branch_version_snapshot_execution_fields.py
tests/test_publish_version.py tests/test_run_branch_version.py -q --basetemp
C:/Users/Jonathan/AppData/Local/Temp/ta-snapshot-root-20260924`
returned65passed0skipped8.37s,8deprecation warnings. Ruff on both touched Python
files passed. Plugin build staged499files and import-probe passed.

Test scope: serializer/store/reconstruction, compiler dry inspection, policy-key
resolution and existing version execution tests. The new policy test copies the
admission precedence expression; it is not an actual provider call and does not
prove model availability. Final CI/deployment/ordinary app acceptance are still
required. Unrelated legacy resume regression and uncommitted concern preserved.
