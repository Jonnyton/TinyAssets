# Drop-first operational migration — coordinator disposition

September20,2026. Opus30526 terminal0/264s supplied the actual ta-op wrapper and
migration contract in output/claude-production-drop-path-result.md. Root read the
complete result, current Dockerfile/Compose/callsites, apply-daemon-env-remote.sh,
and deploy_fail_safe.sh:1118–1280 plus the runtime-bundle contract.

AGREE with real static root-owned wrapper plus migrated callers/tested gate,
not the rejected inventory-only ratchet. This independent operational slice
can be implemented without activating managed resource families or root-start.
Root authorizes D1 (production-image artifact/build preparation, no root/cap
flip) and D3 (existing keepalive argv migration only, no trigger/authority
change and no executing providers). These are normal implementation work under
the owner's coordinated platform mandate, not new host/account permissions.

DISAGREE_EVIDENCE with the proposed legacy entry predicate: fresh read-only
production command at~10:09UTC,
`python scripts/droplet.py ssh -- 'docker exec tinyassets-daemon cat /proc/self/status'`,
returned real/effective/saved/fs UID/GID1001, Groups:1001, ALL five caps0, NNP1.
Thus requiring getgroups()==0 on today's rootless Docker exec would refuse
healthy production. The earlier claim that production has no bounding caps is
correct; the claim that its group list is empty was unverified and is false.
No production setting, process or credential was changed by this read.

Proposed compatibility correction for cross-family pre-build review: on already
unprivileged entry, require every real/effective/saved/fs UID/GID exactly1001,
all five caps0 and NNP1; permit only supplementary entries equal to that SAME
primary gid1001 (including an empty list), refuse every other group. Label this
legacy-rootless verification, not a full managed bootstrap/drop receipt. This
does not widen existing authority. The future root+exact5cap branch MUST still
clear groups to empty and verify full zero-cap drop. No setuid helper, userns
workaround, Config.User change or permissive unknown-identity fallback.

D2: the normal deploy transaction DOES restore config before old image on both
internal failure and public-canary rollback, as verified in source. Healthcheck
migration can share the same reviewed image/runtime-bundle patch with explicit
regression of that ordering and active runbook correction. Image-only/manual
downgrades must not be described as preserving a compatible pair automatically;
existing docs explicitly allow image-only operation. Do not alter rollback
semantics merely to hide a missing binary. Before any environment mutation,
the apply helper must verify the fixed native version route is actually present
and acceptable in the running image; refuse without restart or bare fallback
if absent. This resolves merge-before-image-arrival safely.

The proposed mode inventory needs two source-grounded corrections: droplet.py's
env command prints a FILTERED summary, not one supplied key, and the preflight
needs a fixed native version mode which was not listed. Preserve the original
filtered output via a fixed post-drop summary route, never print all secrets.
Single-key printenv still accepts only a validated environment NAME after the
drop. The closed mode table must preserve actual existing argv; no arbitrary
root command, path, interpreter switch or shell input. Existing builder stage
already installs build-essential, so compile statically there rather than using
a local-only compiler image ID in the production Dockerfile.

The new helper can be isolated from all unlanded cloud runtime/fixture changes.
Prefer a clean production-base worktree for an independently deployable patch;
do not import the full experimental cloud ancestry to ship this helper.
New compatibility amendment must pass the bounded opposite-family shape check
before implementation. Exact-head code review, native positive/negative tests,
Linux/deploy regressions, normal CI/deploy and live proof still gate release.

## Compatibility review returned

Opus82402 terminal0/126s, complete result read by root September20,2026:
output/claude-drop-first-compat-review-result.md. APPROVE corrected shape with
two binding implementation conditions: native-version preflight BEFORE the
fail-open environment read at apply-daemon-env-remote.sh:88, and filtered summary
implemented as a fixed in-wrapper post-drop print, never a shell pipeline.
Reviewer agrees with same-primary-group legacy predicate, coupled bundle rollback
ordering, clean production-base isolation and unchanged keepalive schedules.
No implementation or production activation has occurred. Next bounded Claude
builder must inherit these conditions and the existing authority proposal.
Reviewer addendum calls the local fixture token-less; raw run5 receipt actually
contains a synthetic canary token. Its pulse failure is the missing git_sha,
not missing authorization; it is not evidence for production pulse readiness.
