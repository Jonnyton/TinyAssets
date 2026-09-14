# Native picker follow-up: local proof, not deployed acceptance

September14 2026, working tree based on deployed d895905e, branch
codex/native-model-picker. Owner-approved Fable5.1 shape review completed357s
ADAPT; see2026-09-14-native-model-list-fable.md. Reviewed dispositions and
unreviewed adjacent engine gap are in the change's native-picker-followup.md.

## Implemented

Native access UI now offers default, explicit named IDs, or discovered scope
when an installed metadata adapter is reported. Names are opaque, validated,
unverified account choices, not a release table. The existing bind/enable flow
and separate confirmation are retained; other source scopes, spending limits,
saved preferences and default execution are not silently widened or rewritten.
Input drafts survive catalogue refresh and clear when the home changes.

Missing enumeration has a visible source diagnostic without disabling an
independently admitted default. Inspection found the review's simple diagnostic
addition would otherwise poison the default row because model_options copied
all source reasons onto every row. The narrow display exclusion applies only
to admitted empty/default models and two native enumeration diagnostics; all
actual authorization/capability/source refusals still apply.

## Verification

Baseline WindowsPython3.14:60passes13.75s in app picker/model-options API.
Before runtime changes, new native setup/metadata regressions failed9cases:
missing allowNativeAccess and enumeration field. No fixture/quarantine bypass.

Final Windows:99passed,0skipped,15.62s. Command:

`python -m pytest -q tests/test_app_model_picker.py tests/test_model_options_api.py tests/test_native_discovery_integration.py tests/test_model_options.py --tb=short`

Final Linux:99passed,0skipped,13.22s; Python3.11.16/git2.47.3/bwrap0.12.0.
Docker Desktop socket was unavailable; the existing Ubuntu Docker29.1.3 engine
was verified with `wsl -d Ubuntu -- docker info --format '{{.ServerVersion}}'`.
No service was started or settings changed. Linux command uses the standard
working-tree oracle, overriding only its root discovery because the Windows
worktree .git path is not a Linux path:

`wsl -d Ubuntu --cd /mnt/c/Users/Jonathan/.codex/worktrees/native-model-picker/TinyAssets -- python3 -c "from pathlib import Path; import scripts.linux_oracle as oracle; oracle._repo_root=lambda: Path('/mnt/c/Users/Jonathan/.codex/worktrees/native-model-picker/TinyAssets'); oracle.main()" -- -q tests/test_app_model_picker.py tests/test_model_options_api.py tests/test_native_discovery_integration.py tests/test_model_options.py`

Ruff on all six changed Python/test modules and git diff --check pass.
`python packaging/claude-plugin/build_plugin.py` rebuilt441files; import probe-ok.
Strict validation passes agent-model-selection, provider-routing and
live-mcp-connector-surface. Main specifications now contain the shipped PR3832
deltas, preserving all previous requirements. The pre-existing connector spec
used MAY in a requirement (reproduced unchanged on4c65735b); replacing that
sentence with SHALL support an optional field preserves the optional contract
and satisfies strict validation. Change is not archived: remaining goals open.

## Browser evidence and limits

Own Chrome extension local127.0.0.1:8769 preview used synthetic transport with
connect-src none. Native three-way selector and named input render; two sample
IDs survive Refresh models. No consent submitted, no live grant/preference or
private workflow changed. Preview tab closed and only owned Python43844 stopped.
The continuing real app conversation is preserved in the separate mission tab.

No complete native-account catalogue, real selected-model turn, Claude metadata
protocol, or final new-head approval/deployment is proven here. Current live
release remains d895905e. The app's six workflow smoke passes are recorded in
the primary goal, not treated as model-selection acceptance. Keep the PR draft
until exact-code release review and CI. This shape review is not that receipt.

## CI manifest correction — September 14, 20:45 UTC

Both initial CI failures (invariants run34894197546 and preview contract
run34894197368) identify the same stale generated-assets app.html hash. Ran
`python WebSite/brand/render_marks.py`; the sole substantive generated change
is that manifest hash. No mark geometry or app behavior changed. All six
`python scripts/invariants_run.py --pre-commit` checks now pass locally.
`node --test WebSite/site-react/scripts/brand-parity.test.mjs`:2passed.

Initial local `npm test` lacked yaml in this new worktree. After the locked
`npm ci --ignore-scripts --no-audit --no-fund`, Windows `npm test` reports
233passed,4skipped,0failed (237tests). Linux CI remains authoritative for those
skips. No dependency versions changed. Install warned that existing Next14.2.15
is vulnerable; recorded separately for assessment, not fixed in this picker PR.
