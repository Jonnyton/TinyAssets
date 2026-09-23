# Independent lead review: served node edit parity

September23,2026 UTC. Claude Opus implementation, independently reviewed by
Codex lead at exact head **051d902d24a9cf3a36609fff55e39d3b46239c87** against
origin/main baee7c79. No runtime edit by lead; lead corrected two inaccurate
NaN explanatory comments and synchronized the already-reviewed requirement.

**AGREE / APPROVE for the MVP shape and basic safety**, gated on normal required
CI and actual deployment/live acceptance. Explicit seven-field allowlist,
unchanged authority exclusions, canonical validation and staged persistence are
appropriate. Timeout now rejects invalid numeric values and invalid resulting
workspace pairs before saving. Text fields are checked before set membership or
storage. Error guidance derives the accepted field list. No additional execution
path, grant, credential, tenant crossing or desktop dependency is added.

Read entire runtime diff, new397-line test module and altered denial tests.
Preserved mixed valid/invalid denial assertions; positive persisted readback covers
all seven fields. New tests cover malformed values/atomicity, foreign author,
unchanged version snapshot/hash, no effect dispatch/consent creation. Version
store preservation is not an unpinned-queue immutability proof. Inert enabled/
retry remain denied and are separately tracked, not falsely implemented.

Independent Windows verification: six focused modules171passed/0skips/21.25s,
including64 new cases; original3 reproduction assertions were red on unchanged
runtime. Plugin import succeeds;499 canonical mirrors match. Ruff has only the
same3 pre-existing E501s proven against origin/main; no new lint finding.
Diff whitespace, strict change/spec validation, precommit import and resolver
checks pass. Required hosted cases and live behavior remain unproven.

Claude shape reviewer ADAPT was resolved before implementation; builder timeout
is not an approval. This is the independent other-family implementation review,
not a relabeled Claude self-review. No further review round needed unless the
code materially changes or a concrete release question arises.

Release: https://github.com/Jonnyton/TinyAssets/pull/3924, attached to task.
Opened draft and transitioned ready12seconds later while checks were queued;
ready-event Tests35930192423 is the intended final run. Auto-merge enabled only
at the reviewed head. No build/deploy yet. After merge, inspect image/deploy
triggers instead of assuming GITHUB_TOKEN merges started them; require protected
SHA/public handle checks and exact ordinary checklist prompt. Composite-branch
canonical tests are heavy-only; obtain their post-merge Linux artifact alongside
the64new normal-required cases. Do not claim aggregate green covers exclusions.

Supplementary Linux baseline: scheduled Tests35915770316 at exact basebaee7c79
has a failed overall heavy job, but its junit-heavy-tests artifact10775532425
contains53 test_composite_branch_actions cases, all passed/0errors/0skips.
Downloaded September23 via `gh run download 35915770316 --name
junit-heavy-tests` outside the repository; parsed testcase/classname/file and
failure/error/skipped XML nodes with PowerShell. Compare candidate cases with
this baseline, not the unrelated aggregate red badge. Candidate proof is pending.

## Merge and required Linux proof — September23 23:08UTC

PR3924 merged as1f1217198c9edbc12cb043139df868637afc1df7 at23:08:12UTC.
`git fetch origin main` and `git rev-parse <reviewed>^{tree} <merge>^{tree}`
both yield7878d406c510802da71182cf4cbf47fea06e19ce: exact reviewed tree.
Required35930192423 passed19m54s:20,467passed,5known failures,2known errors,
100skipped/10deselected,0new failures and0stale quarantine. The separate slow
job passed1m28s. No gates or quarantine changed.

Downloaded junit-required-tests with `gh run download` outside the repository;
PowerShell XML inspection proves118 relevant cases, all passed with0skips:
new served-node-edit parity64, engine patch20, effects parity16, reasoning12,
input admissions6. Canonical composite-branch53 cases still require candidate
heavy evidence. Automatic post-merge Tests35932045895 includes that job; use it,
not a duplicate dispatch. Build35932045934 started automatically at23:08:15UTC.
Deployment and ordinary app acceptance are not yet claimed.

## Deployed — September23 23:13UTC

Automatic image35932045934 passed3m36s; deploy35932366205 SUCCESS.
Authenticated public MCP canary with --assert-handles passed23:13UTC; protected
`deployed_sha.py --assert-contains 1f1217198c9edbc12cb043139df868637afc1df7`
reported SHIPPED23:13:06UTC. Exact original app checklist request sent once at
16:16PDT/23:16UTC in newly verified owner tab; response pending. No operator
workflow edits or free-account actions. Candidate heavy53 cases remain pending.

## Accepted — September23 23:31UTC

Candidate heavy job107420623237 finished23:26UTC. Its overall red status is not
a scoped regression: artifact10782480813 downloaded with `gh run download
35932045895 -n junit-heavy-tests` contains all53 composite-branch tests PASS,
0failures/errors/skips, matching the baseline's53. With required118 this covers
all171 relevant Linux cases, none skipped.

Original16:22PDT checklist reply passed its five controls but did not test the
new fields. One natural follow-up at16:25 asked the app agent to fix its reported
output-name/time-limit issues itself. Original16:31PDT response reports BOTH
FIXED: on its probe branche66e28cb3916 it renamed old_name to new_name with the
matching schema, ran it and read PROBE-OK under new_name; it changed an existing
node timeout300→600 and read back600. No operator workflow edit, refresh or
request replay. This proves ordinary editing and successful renamed output,
not actual600-second enforcement or closure of intermittent provider failures.
The agent's assertion that larger timeouts make that failure mode go away is
not adopted as a platform reliability conclusion. Its latency/idle items remain
open. Existing authenticated owner conversation, not first-contact proof.

Runtime/specification already landed together in3924. Archive housekeeping
follows without a runtime change or another acceptance replay. No independent
post-fix customer use visible yet; retain a separate organic-use watch.
