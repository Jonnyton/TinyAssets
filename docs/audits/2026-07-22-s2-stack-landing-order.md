<!--
Provenance: carried verbatim from an untracked file in the primary checkout at
`docs/audits/2026-07-22-s2-stack-landing-order.md` (written 2026-07-21 19:01).
The lane wrote the audit straight into `docs/audits/` but never committed it, so
it existed on no local or remote ref. Body below is that file unmodified; only
this comment was added.
-->

# S2 stack: actual dependency graph and landing order

**Freshness:** observed 2026-07-21 PDT / 2026-07-22 UTC against
`origin/main` `220a1fc8c69d3ae07b7673494e30d1267a220f69`, the fetched remote branch
heads listed below, and GitHub PR/Actions metadata. The local primary checkout
was 14 commits behind and dirty, so no conclusion in this audit uses its working
tree as branch truth.

## Verdict

The five advertised S2 PRs are not rooted at `main`. Their shared, unmerged
lineage is:

```text
#1464/#1465/#1466/#1467/#1468/#1469
                  |
                  v
                #1471  feat/patch-loop-integration
                  |
                  v
                #1472  feat/patch-loop-runner
                  |
                  v
                #1477  feat/patch-loop-leasestore-fix2
                 /   \
       old @8d9a7791  \
              |        v
            #1478     #1479
                       |
                       v
                     #1481
                       |
              old @cbb50e08
                       |
                       v
                     #1487
```

The two side branches are not clean descendants of their advertised current
bases:

- #1478 contains the #1477 tree only through `8d9a7791`; the current #1477 head
  is `4e0a22e2`. The branches have multiple merge bases and GitHub shows 40 files
  instead of the intended two.
- #1487 contains #1481 only through `cbb50e08`; the current #1481 head is
  `d4bf1364`. The current base has three commits not in #1487, while #1487 has
  eight commits not in the base.

The hidden upstream matters to landing: #1472 itself changes 13
release-critical files, above the current hard cap of 8. The requested S2 chain
cannot reach `main` until #1472 is split or its release-critical changes are
landed through smaller declared PRs.

## Scope-guard fact check

At `origin/main` the guard sets `MAX_SENSITIVE=8`; more than 8
release-critical files is a hard failure. `LARGE_TOTAL=150` is currently an
advisory threshold, not an unconditional hard failure: a large PR with 1-8
release-critical files may proceed when labeled `infra-change`. This differs
from the older "8 or 150" summary, but it does not change the result here:
#1477 and #1491 each expose 16 release-critical files and are hard-blocked.

Release-critical means `.github/workflows/**`, `deploy/**`, `Dockerfile`, or
`.dockerignore`.

## PR state by actual branch

| PR | Actual branch relationship | Diff against configured current base | GitHub state / checks | Smallest landable repair |
|---|---|---:|---|---|
| **#1477** `4e0a22e2` | Descends from #1472 `c11b145b`, but targets `main`. It therefore carries all of #1471 and #1472 plus the S2 work. Its body is stale: `04491a69` implements the V1.4 transport it still calls "in flight". | **400 files, 16 critical, +105196/-11034; 223 branch-only commits, 14 main-only.** | Draft, `mergeable=false`. Red: actionlint run `29871352325` sees the inherited `p0-outage-triage.yml` undefined need; packaging run `29871352319` lacks `nacl`; Docker run `29871352380` lacks `typing_extensions`. | **First:** retarget to `feat/patch-loop-runner` without rewriting history. This removes the false root diff. After #1471/#1472 land, reconcile current `main`, add PyNaCl to the packaging install contract at the lowest owning branch, refresh the stale PR body, and rerun all checks. |
| **#1478** `befd9421` | Forked from #1477 at `8d9a7791`, adds `4e50face`, then merges `e2a30f21`; it does **not** contain current #1477. | **40 files, 1 critical, +4207/-22** although the owned change is exactly **2 files, +311**. | Draft, `mergeable=true`; actionlint and all three authority jobs were green at run `29871389684`. Not currently red, but the diff is not the stated scope. | After #1477 is final, create a replacement from that exact head and cherry-pick only `4e50face`. Add `infra-change` for the one workflow file. Do not merge or rebase the current multi-base branch. |
| **#1479** `9389c1fb` | Current #1477 `4e0a22e2` is an ancestor. The advertised dependency is real. | **10 files, 0 critical, +1763/-621; 5 branch-only commits.** | Draft, `mergeable=true`. Red only on shared-lineage CI: packaging run `29871600052` lacks `nacl`; Docker run `29871600201` lacks `typing_extensions`. | Freeze it until #1477 and the packaging dependency fix are green. Then retarget to the landed parent and rerun; do not change B05/B06 code merely to mask an upstream environment failure. |
| **#1481** `d4bf1364` | Current #1479 `9389c1fb` is an ancestor. The advertised dependency is real. | **3 files, 0 critical, +266/-72; 6 branch-only commits.** | Draft, `mergeable=true`. Red only on shared-lineage CI: packaging run `29871657907` lacks `nacl`; Docker run `29871657766` lacks `typing_extensions`. | Freeze until #1479 lands, retarget to the landed parent, and rerun. Its product diff is already appropriately small. |
| **#1487** `f6bee436` | Built from the #1481 core commit `cc3a9a7b`, later merged the older #1481 snapshot `cbb50e08`; current #1481 `d4bf1364` is **not** an ancestor. | **9 files, 0 critical, +1716/-923; base/head divergence 3/8 commits.** | Draft, `mergeable=false`; no workflow run exists for the current head. Local evidence reported in the PR thread is 275 focused tests green after three test-only corrections, but that is not GitHub CI proof. | After #1481 is final, create a replacement from that head; replay production commit `38936d60` plus test fixes `73a823ea`, `a4374eb7`, `f6bee436`, then regenerate the plugin mirror once. Do not replay merge commits or the two superseded mirror commits. |

### Shared CI causes are upstream, not five separate bugs

1. `tinyassets/credentials/crypto.py` imports PyNaCl, but
   `.github/workflows/build-bundle.yml` installs a hand-curated packaging set
   without PyNaCl. This produces seven `ModuleNotFoundError: No module named
   'nacl'` setup errors.
2. The Docker smoke imports `typing_extensions`, while these heads predate the
   dependency declaration landed on current `main` as #1488 (`170c85b2`).
3. #1477/#1491 actionlint scans inherited workflow changes and catches
   `repair_provider_exhaustion_gate` referenced but not defined in
   `p0-outage-triage.yml`. Correcting the base removes unrelated workflow files
   from the S2 diff; current-main reconciliation supplies the later workflow
   repairs.
4. #1491 additionally failed plugin parity: its generated mirror was stale in
   three files. Its **386 files / 16 critical** diff is the same unmerged-lineage
   failure shape, not the scope of its daemon-key fix.

## Landing order

The dependency-valid landing order is:

1. **Repair the graph metadata now:** retarget #1477 to
   `feat/patch-loop-runner` (#1472). Acceptance: configured base is #1472,
   #1472 head is an ancestor of #1477, and the PR file list no longer exposes
   the 400-file/16-critical `main` diff.
2. **Land #1471**, after reconciling current `main` and declaring its seven
   release-critical files. Its 311-file total is large but not a hard failure
   under the current guard.
3. **Split and land #1472.** Its 13 release-critical files exceed the hard cap;
   separate the runtime/security substrate from release/deploy retirement work,
   with no resulting PR over eight critical files. Then retarget the remaining
   #1472 slice(s) to `main`.
4. **Finish and land #1477.** Bring in the now-landed upstream and current-main
   dependency fixes, fix the packaging dependency contract at its owning layer,
   refresh the V1.4 description, and verify the focused authority suite,
   packaging build, Docker smoke, actionlint, scope guard, and full required
   gate.
5. **Replace and land #1478** from the final #1477 head using only `4e50face`.
   This lands the authority gates before the remaining authority mutations.
6. **Land #1479**, then **#1481**, preserving their already-correct ancestry and
   small diffs.
7. **Replace and land #1487** from final #1481 using the production commit and
   three test corrections listed above, with one fresh mirror regeneration.

No later branch should be rebased, merged, or force-pushed until its immediate
parent is final. New replacement branches are preferred for #1478 and #1487 so
their current evidence remains inspectable.

## First-step execution record

Attempted 2026-07-21 PDT / 2026-07-22 UTC through the connected GitHub writer.
The write was canceled before mutation. A fresh PR read confirmed #1477 remains
unchanged: base `main`, head `4e0a22e2`, 400 changed files, 223 commits,
`mergeable=false`, draft. No later landing-order step was attempted.

## Evidence commands

```text
python scripts/session_sync_gate.py
git merge-base --is-ancestor <parent> <child>
git rev-list --left-right --count <base>...<head>
git diff --name-only <base>...<head>
git diff --shortstat <base>...<head>
git log --oneline --reverse <range>
```

GitHub metadata came from the PR records for #1464-#1472, #1477, #1478,
#1479, #1481, #1487, and #1491; failing job steps and logs came from the run IDs
cited above.
