> **Implementation status (2026-06-30, branch `claude/founder-identity-allslices`).**
> Foundational + non-breaking creation slices landed on the branch: WorkOS RS
> auth (slice 1, PR #1435), the single ACL/write-boundary path (slices 2–3), and
> the non-breaking creation contract — generated `u-`+ULID id, optional
> `universe_id`, the seeded 13-file OKF bundle, and dropping notes.json/
> activity.log for new universes (slice 4). Checked boxes below reflect that.
> **Held for host live-proof gates** (canary + chatbot `ui-test`, AGENTS.md Rule
> 11/12): the breaking removals and existing-universe migration — 2.7–2.8, 2.10,
> 3.1–3.2, 2.12, and the *existing-universe* half of 2.9. Contract-test boxes are
> left unchecked unless a landed test covers them exactly.

## 1. Contract Tests

- [x] 1.0 Get opposite-provider source review of the OKF latest-main soul baseline before implementation uses the external standard. (Codex found → Claude reviewed; `docs/audits/2026-06-30-okf-soul-baseline-review.md`.)
- [ ] 1.0a Add WorkOS resource-server auth tests proving a valid AuthKit bearer token resolves token `sub` to `founder_id`, invalid tokens do not create a principal, and anonymous callers cannot create universes.
- [~] 1.0b Add first-contact auth tests proving a founder home universe is resolved from authenticated founder identity, not from env, first directory, or root `.active_universe`. (Identity resolution + no-marker-write + no cross-founder serial leak covered by `test_first_contact::test_first_contact_births_and_binds_home`, `test_founder_create_does_not_write_active_universe_marker`, `test_readonly_founder_omitted_scope_does_not_leak_other_home`; explicit env/first-dir precedence assertions still to add.)
- [ ] 1.0c Add MCP write-boundary tests proving authenticated founders can write only to their own bound/home universe brain and cannot edit another universe's soul, identity, canon, wiki, runtime goals, body, org chart, files, or state.
- [ ] 1.0c.1 Add anonymous-permission tests proving anonymous callers can read public surfaces only and cannot perform any write, create, run, costly, admin, ledger, sync, or state-changing action.
- [ ] 1.0c.2 Add universe-visibility tests proving ownership/admin grants do not change public/private readability, `public_read=false` blocks anonymous/non-granted reads, and public/private flips require explicit confirmation.
- [ ] 1.0d Add Branch interaction tests proving users can submit patch requests, Branch edit proposals, alternative Branch proposals, and Goal proposals without gaining write access to another universe brain.
- [ ] 1.0e Add Branch-run tests proving Branches are run only by universes, every run is attached to that universe's runtime Goal, multiple universes can use the same Branch as separate instances, and a universe can remix a Branch into its own variant.
- [~] 1.1 Add MCP creation tests proving blank create generates exactly one opaque lowercase-ULID `universe_id` and does not accept a creation-time persona name. (ULID format/uniqueness covered by `test_ids`; create takes no name. A create-route "generates when absent" assertion is still to add.)
- [x] 1.2 Add baseline tests proving creation writes `index.md`, `log.md`, `soul.md`, `soul.edit.md`, `identity.md`, `founder.md`, `orgchart.md`, `projects.md`, `goals.md`, `body.md`, `origin.md`, `soul_versions/index.md`, and `soul_versions/0001.md`, and does not create `self/`, `soul/`, `notes.json`, or `activity.log`. (`test_universe_bundle`, `test_universe_soul`.)
- [ ] 1.3 Add tests proving `get_status` is idempotent for a newly created universe and does not first-create the soul bundle.
- [ ] 1.4 Add tests proving existing descriptive-id universes are reset to
  serial-id roots and write/run/status operations use the serial `universe_id`.
- [ ] 1.4a Add universe-index tests proving creation inserts one row keyed by
  immutable `universe_id` and name learning updates that row from `identity.md`.
- [ ] 1.5 Replace HTTP create tests with assertions that `POST /v1/universes` does not create a universe.
- [x] 1.6 Add OKF-shape tests proving `soul.md` has parseable YAML frontmatter, `type: Universe Soul`, OKF latest-main source metadata, and local markdown links that resolve to generated files. (`test_universe_bundle`.)
- [x] 1.7 Add link-closure tests proving every baseline file is pointed to by `index.md`, `log.md`, `soul.md`, or `soul_versions/index.md`. (`test_universe_bundle::test_link_closure_every_file_pointed_to`.)
- [~] 1.8 Add `soul.edit` tests proving `soul.edit.md` exists as `type: Soul Edit Policy`, the execution path reads/follows it, changes are treated as learned updates, accepted edits update only governed soul files (`soul.md`, `identity.md`, `founder.md`, `body.md`, `origin.md`), `orgchart.md`/`projects.md`/`goals.md` are not listed as governed files, accepted edits append `log.md`, and a new `soul_versions/` snapshot is written. (Policy FILE + governed-list covered by `test_universe_bundle::test_soul_edit_policy`; the `universe action=soul.edit` execution path is held/future.)
- [x] 1.9 Add projects/goals boundary tests proving `projects.md` is a one-line founder-project index with pointers as needed, and `goals.md` is runtime goals plus goal-attached Branch uses/runs. (`test_universe_bundle`.)
- [x] 1.10 Add body contract tests proving `body.md` starts not-learned, describes body as learned embodiment/personification, and does not claim live platforms, applications, voice, hands, or senses before those are built or observed. (`test_universe_bundle`.)
- [x] 1.11 Add orgchart contract tests proving `soul.md` links `orgchart.md` with the open questions, `orgchart.md` starts not-learned, states that the oath-confirmed founder is always the top anchor, and does not invent roles, teams, daemons, collaborators, delegations, or reporting lines. (`test_universe_bundle`.)
- [ ] 1.12 Add first-connect tests proving an authenticated founder with no home universe gets a blank seed universe created and bound, the chatbot loads that seed soul/persona, and the first response speaks in first person as the universe rather than returning platform status as the main experience.
- [ ] 1.13 Add first-connect tests proving an authenticated founder with an existing home universe loads that learned universe soul/persona and speaks as that universe.
- [x] 1.14 Add scope tests proving omitted universe scope resolves through authenticated founder home-universe context and never through root `.active_universe`. (`test_first_contact::test_founder_create_does_not_write_active_universe_marker`, `test_readonly_founder_omitted_scope_does_not_leak_other_home`.)
- [ ] 1.15 Add existing-universe reset tests proving universe roots are serial-id folders, data/canon files remain under the serial directory, and write/run/status operations use the serial `universe_id`.
- [ ] 1.16 Add universe-clearing tests proving serial universe directories and founder home bindings can be cleared while branch definitions, goals, run metrics, and outcome records remain intact unless branch commons are explicitly reset.
- [ ] 1.17 Add mobile-contract tests or fixtures proving an Android/iOS client path uses the same MCP auth/read/confirmed-write contract and cannot create a mobile-only universe id or brain shape.

## 2. Creation Implementation

- [ ] 2.0 Implement WorkOS AuthKit Resource Server validation: Protected Resource Metadata, AuthKit metadata/JWKS loading, issuer validation, audience validation, and token `sub` to `founder_id`.
- [ ] 2.0a Implement resolve-always auth mode: public reads can be anonymous, while create/write/costly/admin actions require authenticated founder scopes through the existing action-scope registry.
- [ ] 2.0b Enforce target-universe ownership for universe-brain writes through MCP.
- [ ] 2.0c Enforce anonymous public-read-only behavior for every MCP write surface, including ledger, auto-ship, wiki, run, and universe-brain writes.
- [ ] 2.0d Implement explicit public/private visibility state using `public_read`, separate from owner/admin grants.
- [ ] 2.0e Add a confirmation-gated visibility action for public -> private and private -> public transitions.
- [ ] 2.0f Route cross-universe branch/community interactions through request/proposal surfaces rather than direct universe-brain writes.
- [ ] 2.0g Enforce Branch-run authority so the runnable actor is a universe and each run is recorded as a goal-bound Branch-use instance.
- [x] 2.1 Add a small generated-id helper for new universe ids using `u-` plus lowercase ULID, keeping the serial generator isolated. (`tinyassets/ids.py`.)
- [x] 2.2 Update MCP `universe action=create_universe` so `universe_id` is optional on create and generated when absent.
- [x] 2.3 Ensure the MCP create route seeds one linked OKF soul bundle during creation. (`tinyassets/universe_bundle.py::seed_okf_bundle`.)
- [x] 2.4 Ensure the MCP create route writes the full baseline files required by the spec.
- [x] 2.5 Remove creation-time persona name handling; treat any display label as metadata only if still needed by a live reader. (Create takes no `name`; persona name is learned via `identity.md`.)
- [ ] 2.6 Implement `soul.edit.md` as the real soul edit policy file and make the execution path read/follow it, with versioning and log updates.
- [ ] 2.7 Implement founder home-universe resolution for MCP first contact: authenticated founder -> existing home universe or new blank seed universe -> loaded soul/persona -> first-person universe voice.
- [ ] 2.8 Remove root `.active_universe` from MCP default routing. Explicit universe choices are request/client/session scope, not shared host state.
- [~] 2.9 Remove duplicate `self/`/`soul/` directories, brain archive folders, and empty `notes.json` / `activity.log` starter files from active universe roots, and stop creating `self/`, `soul/`, `notes.json`, or `activity.log` for new universes. (NEW-universe half done: create no longer seeds notes.json/activity.log/self//soul/. The EXISTING-universe removal is the held live-data migration.)
- [ ] 2.10 Bring universe roots to generated serial-id folders matching `universe_id`.
- [ ] 2.11 Maintain the root universe index: add new serial ids at creation and update the learned-name column when `identity.md` learns or changes the universe's name.
- [ ] 2.12 Prepare a basic Android test app after auth/read/confirmed-write surfaces are stable; it must use the same MCP contract and platform-standard credential storage/integrity hooks.

## 3. Remove Duplicate Route

- [ ] 3.1 Remove or reject `POST /v1/universes` in `fantasy_daemon/api.py` so it cannot create universes.
- [ ] 3.2 Remove slug-name creation behavior and tests that treat slugified names as universe ids.
- [ ] 3.3 Preserve non-create HTTP read/list behavior only where current tests or live clients still require it.

## 4. Verification

- [ ] 4.1 Run focused universe creation, universe soul, persona/soul-model, and affected HTTP API tests.
- [ ] 4.2 Run an MCP-level create/status smoke test against a temporary data dir.
- [ ] 4.3 Update docs or prompt examples that still instruct users to create universes through HTTP or creation-time names.
