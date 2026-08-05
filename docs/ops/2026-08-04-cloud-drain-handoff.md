# Cloud drain handoff — 2026-08-04 (revision 2)

Revision 1's resume procedure was executed. It did **not** complete: the create
path exposed a fourth and a fifth issue beyond the three revision 1 documented.
Two are fixed and deployed; the fifth is fixed-but-blocked.

## Current truth

- **No cloud automation exists yet.** `read_graph target=automations` returns
  `count: 0` with `prerequisites.ready: true`.
- Local tray/drain is stopped, and every restart vector is disabled — not just
  the process. Scheduled tasks `TinyAssets OpenSpec Drain` **and**
  `TinyAssets OpenSpec Drain Guard` are both `Disabled`; no Run keys; no
  services; the startup folder holds only a `disabled-by-codex-live-loop`
  marker. Record this explicitly — the Guard is the layer that defeated three
  previous rollbacks.
- Destination grant `pipes_grant_26eb1ab80dd8ecf0202a3b4f69a17081` stores its
  destination **bare** as `jonnyton/tinyassets` (no `github.com/` prefix), cap
  `one_pull_request` maximum 1.
- Provider binding `pwb_fbddd0e8b76b837a266488a23403f0b3` is ACTIVE at
  **generation 5** (rebound 2026-08-04 against the post-#2286 image),
  `max_invocations=64`, `max_cost_microunits=64`, expires 2026-09-03.
- Branch `745e637dd8fb@99cb5a8f` is private, authored by
  `user_01KWGB2NV5PV4PWHT5RYKJPB8X`, which **is** the authenticated founder
  actor — proved, not assumed: branch read authority returns private branches
  only to their author, and the connector read returns it in full.
- Production deployed `cae007e8` (build `30956393163`, deploy `30956628591`,
  canary passed 22:33:49Z) and then `868153bd`.

## Landed

- **PR #2286** — normalize GitHub destination comparison. Merged `cae007e8`.
- **PR #2291** — admit the universe id prefix production actually mints.
  Merged `868153bd`, built `30958096611`, deployed `30958294095`.

## Blocked

- **PR #2292** — admit the branch identity shapes production actually mints.
  The diagnosis is right; the **fix as written is not safe to land**. Left as a
  draft with auto-merge disabled; see the blocker comments on the PR.

  The required gate reports exactly one new failure,
  `test_cloud_automation_api.py::test_phone_rebinds_and_rolls_back_to_published_branch_versions`,
  deterministically across four runs. A bisect (#2295, closed) carrying the
  source change **without** the added tests still fails it, which attributes the
  regression to the `_reference` change itself and rules out suite
  ordering/state perturbation from the new test functions.

  This contradicts the natural prediction — the change is strictly more
  permissive, and that test's fixture ids are `branch_`-prefixed so they
  short-circuit before the new patterns ever run. Mechanism therefore unknown.
  Leading hypothesis: more-permissive deserialization lets a record that
  previously failed to load now load, sending rollback down a "reuse existing
  binding" path that then fails a CAS/generation check and returns an error
  dict — consistent with the observed `KeyError: 'status'`.

  The test cannot be attributed locally on Windows: it fails there with **and**
  without the change for an unrelated reason, masking the signal. A Linux repro
  is required.

## The two new issues

Both are the same class: **an allowlist encoding fixture spellings rather than
the shapes production actually mints**, so it rejected 100% of real inputs while
the suite stayed green.

### 4. `universe_id` (fixed, deployed — #2291)

    automation_setup_invalid: universe_id must be a nominal non-bearer reference

`_NOMINAL_REFERENCE_PREFIXES` listed `universe_`, but production mints universe
ids as `u-` + a lowercase Crockford ULID (`tinyassets/ids.py:23`).

### 5. `branch_def_id` (fixed, NOT landed — #2292)

    automation_setup_invalid: branch_def_id must be a nominal non-bearer reference

Branch identities carry **no** domain prefix at all:

| identity | mint | source |
|---|---|---|
| branch def id | `uuid4().hex[:12]` | `branches.py:677` |
| branch version id | `<def_id>@<content_hash[:8]>` | `branch_versions.py:277` |
| widened on collision | `<def_id>@<content_hash[:16]>` | `branch_versions.py:284` |

`pinned_branch_version_id` carries the same shape and would fail next.

**Why the suite never caught either:** every fixture spells these
`universe_alice` / `branch_spec_drain`, and the existing coverage only asserted
that bearer-shaped values are **rejected**. Nothing asserted that a **real**
identifier is **accepted**. A one-directional allowlist test is half a gate: it
pins the closed direction and lets the open direction drift to zero.

## Corrections to revision 1's procedure

1. `max_cost_microunits` is **not** a create-payload field. It is derived from
   the provider binding by `_derive_phone_work_definition`. The live binding
   already carries 64.
2. `operator.soul_text` is **required** and revision 1 omitted it.
   `prepare_cloud_automation` demands non-empty soul text when no project-loop
   daemon exists, and `get_status` reports `open_brain.daemon_count = 0`.
3. `accepted_spec_ref` may be a directory. It is only validated as a safe
   repository-relative POSIX path; the accepted spec is resolved by **content
   digest** (`load_accepted_spec` -> `_artifact_path(base, expected_digest)`),
   never read from that repository path.
4. A PR sitting at `BEHIND` under branch protection `strict: true` needs
   `gh pr update-branch` before auto-merge can fire.
5. `resume` fences on `expected_revision`; pass the control's current
   `revision`, not the default `0`.

## Resume procedure

1. **First, fix #5 without regressing rollback.** #2292's diagnosis is correct
   but its fix regresses
   `test_phone_rebinds_and_rolls_back_to_published_branch_versions`; see the
   blocker comments on #2292. Reproduce on Linux, find the mechanism, then land
   and deploy. Confirm with `get_status` that `release_state.git_sha` contains
   it — merged is not deployed.
2. Create exactly one **stopped** automation via
   `write_graph target=automation operation=create`:
   - `definition.repository` = `jonnyton/tinyassets`
   - `definition.accepted_spec_ref` =
     `openspec/changes/activate-main-universe-spec-drain`
   - `definition.branch_version_id` = `745e637dd8fb@99cb5a8f`
   - `accepted_spec_content` = the accepted spec text (required, non-empty)
   - `cadence_seconds` = 300
   - `operator.display_name` / `operator.soul_text` (both required)
3. Verify `automation_id` and `desired_state=stopped`, then resume once with
   `operation=resume` and the control's current `expected_revision`.
4. Verify `read_graph target=automations` shows one active automation, then
   watch health for one bounded slice and PR attempt.

**Efficiency note for whoever continues:** each merge/build/deploy cycle costs
~20 minutes, so do not discover the next id-shape blocker one cycle at a time.
Substituting production-shaped identifiers through the existing suite reproduces
the whole create path in ~10 seconds:

```
sed -i 's/"universe_alice"/"u-01kxm1vszd8hwp7em418asq8h9"/g; \
        s/"acct_alice"/"user_01KWGB2NV5PV4PWHT5RYKJPB8X"/g' \
    tests/test_cloud_automation_api.py
```

That sweep is how issue 5 was found before deploying, and it currently shows no
sixth id-shape blocker.

## Open risks

Cross-family review (Codex gpt-5.6-sol) returned **reject** on the activation
plan. Triaged:

- **Confirmed safe.** No repo-A -> repo-B bypass in #2286's normalizer across
  credential, lookalike-domain, `.git`, extra-segment, and case variants.
  Payload shape, directory-valued spec ref, and `cadence_seconds=300` are all
  correct.
- **R1 (cosmetic).** The normalizer accepts `https://http://github.com/...` and
  `github.com//...`; both still resolve to the *correct* repository. Strict
  parse + canonical reconstruction is a worthwhile follow-up, not a blocker.
- **R2 (latent, not active).** Grant/binding hydration requires exactly one
  candidate and strips caller-supplied ids before selecting, so supplied ids
  cannot disambiguate. Harmless today (exactly one of each); it breaks the day a
  second grant is connected.
- **R3 (open, likely benign).** `max_cost_microunits=64` is the minimum
  schema-valid value for 64 invocations. No decrement site was found — the value
  is carried as a conserved ceiling, and with subscription auth nothing meters
  spend against it — so a mid-flight budget kill looks unlikely. Confirm on the
  first slice rather than treating a grep miss as proof.
- **R4 (open).** Setup authority is bounded to 2 attempts, 0 child delegation
  and a 24h expiry. That prevents an infinite run but does **not** establish
  perpetual 24/7 renewal. The 24h PC-off proof must show renewal, not liveness.
- **R5 (needs conscious acceptance; raised here, outside Codex's file scope).**
  `.github/workflows/auto-enroll-merge.yml` enrols every non-draft same-repo PR
  into `main` for auto-merge, delegating safety wholly to branch protection. A
  PR this automation opens will **merge and auto-deploy to production with no
  human review**. That matches existing host-designed drain behaviour, but it
  should be a decision rather than a surprise.

## Cautions

- Do not claim 24/7 cloud operation until an active automation and a
  post-resume cloud slice are observable with the computer off.
- Keep the local drain stopped; do not re-enable either scheduled task.
- Do not quarantine `test_phone_rebinds_and_rolls_back_to_published_branch_versions`
  to unblock #2292. Turning a gate green by listing the test is the failure mode
  the project prohibits.
