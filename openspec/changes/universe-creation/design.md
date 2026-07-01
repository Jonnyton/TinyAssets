## Context

Workflow currently has two universe creation paths that both write under the
same data root:

- MCP/chatbot: `universe action=create_universe` in `tinyassets/api/universe.py`.
- HTTP API: `POST /v1/universes` in `fantasy_daemon/api.py`.

They create different filesystem shapes and identity meanings. The MCP route
requires the caller to provide `universe_id`; the HTTP route slugifies a supplied
name into the directory/id and writes `universe.json`, `canon/`, and `output/`.
That conflicts with the founder/universe identity design: a universe has one
opaque immutable serial (`universe_id`), and its self-name is learned later in
the canonical soul document (`soul.md`).

## Goals / Non-Goals

**Goals:**

- Make `universe action=create_universe` the only creation route end to end.
- Use WorkOS AuthKit bearer token `sub` as the production `founder_id` for
  creation, first-contact routing, and home-universe binding.
- Generate exactly one immutable lowercase ULID serial at creation; that serial
  is `universe_id`.
- Use `universe_id` as the directory name for both new and existing universes;
  universe roots are serial-id folders.
- Maintain one readable root universe index keyed by immutable `universe_id`,
  with current learned names projected from each universe's own identity file.
- Define the default MCP entry path: authenticated founder -> home universe ->
  loaded universe soul/persona -> first-person universe voice.
- Enforce that MCP users can write only to their own bound/home universe brain.
- Enforce that anonymous MCP callers have public read access only and no write
  path at all.
- Separate universe ownership/write authority from public/private visibility,
  with confirmation required before making a universe private or public.
- Define Branch runs as universe actions, with public user interactions routed
  through patch requests, Branch edit proposals, alternative Branch proposals,
  and Goal proposals.
- Prepare the creation/auth contract for future iOS and Android clients and
  phone-hosted or phone-synced universes without adding a second creation path.
- Seed the same blank universe baseline every time.
- Seed the learned soul bundle at creation, not lazily only after status reads.
- Make `soul.edit` a real soul edit policy file whose OKF concept id is
  `soul.edit`.
- Remove HTTP creation instead of hiding or wrapping it.
- Remove duplicate `self/`, `soul/`, and brain archive folders during
  baseline reset; active persona/self-understanding reads come from the root OKF
  soul bundle, not a second folder model. Empty `notes.json` /
  `activity.log` starter files are also removed; non-empty historical notes/logs
  remain runtime data until they have an explicit typed runtime target.
- Use the latest OKF spec on GitHub as the soul document standard:
  `https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`.

**Non-Goals:**

- Multi-universe execution scheduling.
- Multi-org enterprise role modeling beyond the founder identity needed for
  universe creation and home-universe entry.
- Renaming non-universe infrastructure directories such as `daemon_wikis`,
  `wiki`, or `community-pool`.

## Decisions

**D0 - WorkOS `sub` is founder identity.**
Production MCP auth uses WorkOS AuthKit as the Authorization Server and
Workflow as the Resource Server. Workflow validates bearer JWTs against AuthKit
metadata/JWKS and uses token `sub` as the immutable `founder_id`. Anonymous
callers may read public surfaces but cannot create universes. The local
self-issued auth provider is not a production founder identity source.

**D0b - Anonymous is public-read only.**
An anonymous MCP caller has no write authority, including local/no-auth harness
requests. Anonymous can read public surfaces only. Any write, create, run,
costly, admin, ledger, sync, or state-changing action requires an authenticated
founder identity plus the required action scope and target-universe authority.

**D0a - MCP writes are scoped to the founder's own universe.**
An authenticated founder can write only to their own bound/home universe brain.
Public universe reads can cross universe boundaries, but writes to another
universe's soul, identity, canon, wiki, runtime goals, body, org chart, files,
or state are rejected. Branch/commons request surfaces are separate: users can
submit patch requests, propose Branch edits, propose alternative Branches, or
propose Goals without directly mutating another universe brain.

**D0c - Ownership is not visibility.**
Owner/admin grants prove who can write a universe. They do not by themselves
make that universe private. Public/private read visibility is an explicit
universe rule: `public_read=true` means anonymous/public reads are allowed;
`public_read=false` means only granted actors can read. The user-facing action
that changes `public_read` must be confirmation-gated in both directions:
public -> private and private -> public. Sync, creation, owner binding, branch
runs, and mobile connection must not silently flip visibility.

**D1 - One route, not shared duplicate routes.**
The canonical creation surface is MCP `universe action=create_universe`. The HTTP
create route is removed. If a UI needs universe creation, it must call the MCP
surface and receive the same contract, not a second server route.

**D2 - One generated serial equals `universe_id`.**
Creation generates one opaque immutable serial and stores/returns it as
`universe_id`. The generated format is `u-` plus a 26-character lowercase ULID
(Crockford base32, time-sortable timestamp prefix, random suffix). There is no
later second code serial. The serial is the storage directory name. Descriptive
text does not remain the universe folder name and does not become the universe's
learned name.

**D3 - Creation-time names are not identity.**
The create request does not set the universe's self-name. Display labels, if
needed by clients, are metadata and must not drive directory names, persona
identity, or `soul.md`.

**D3a - Universe index.**
The root data surface has a readable universe index keyed by immutable
`universe_id`. The index may display the current learned name from a universe's
own `identity.md`. When a universe learns or changes its name, the row for that
same immutable `universe_id` is updated. Runtime operations resolve by
immutable `universe_id`.

**D4 - Creation seeds a linked OKF soul bundle.**
New universes have one identity/intention model: an OKF bundle rooted in the
universe directory, with `soul.md` as the central soul entrypoint. This is not a
separate `soul/` directory and not a rendered summary. Governed soul files are
`identity.md`, `founder.md`, `body.md`, and `origin.md`; `soul.edit.md` is the
policy for editing those files and `soul.md`. `orgchart.md`, `projects.md`, and
`goals.md` are learned/runtime files linked from `index.md`, not
soul-edit-governed files.
OKF's optional reserved files, `index.md` and `log.md`, are precreated and
linked: `index.md` is the bundle map and `log.md` is the human-readable update
history.
`get_status` can remain idempotent, but status is not responsible for first
creating the soul bundle.

Source freshness: Codex verified
`https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`
on 2026-06-26. The latest commit for `okf/SPEC.md` on `main` was
`ee67a5ca27044ebe7c38385f5b6cffc2305a9c1a` dated 2026-06-12. Workflow tracks
the latest-main URL as the live standard, not that commit as a pinned runtime
contract.

**D5 - Baseline files are explicit linked surface.**
Creation writes the runtime files expected by the MCP universe loop:
`index.md`, `log.md`, `soul.md`, `soul.edit.md`, `identity.md`, `founder.md`,
`orgchart.md`, `projects.md`, `goals.md`, `body.md`, `origin.md`,
`soul_versions/index.md`, and `soul_versions/0001.md`. New creation does not
create `self/`, `soul/`, `notes.json`, or `activity.log`. Any additional file
or directory retained from the removed HTTP route must be justified by a live reader
and linked from the OKF bundle, not silently dropped into the universe root.
Empty `notes.json` / `activity.log` starter files are removed; non-empty
notes/logs remain data until they have a typed runtime target.

**D6 - `soul.edit` is the real soul edit policy file.**
`soul.edit` is the OKF concept id for `soul.edit.md`. That file lays out how
this universe learns high-authority changes to its own soul. The MCP
surface may expose `universe action=soul.edit` as the execution handle, but the
authority/rules live in `soul.edit.md`, not in a hidden hardcoded string.
A soul edit is a learning event: it may update `soul.md`, `identity.md`,
`founder.md`, `body.md`, or `origin.md` only through the rules in
`soul.edit.md`; accepted edits append `log.md` and write a `soul_versions/`
snapshot. `orgchart.md`, `projects.md`, and `goals.md` are outside this
authority.

**D7 - Projects are not runtime goals; branch use attaches to goals.**
`projects.md` is the index for founder projects, products, experiments, and
things the founder is building. It should contain one-line summaries and links
to project files when a project needs its own file. `goals.md` is the runtime
surface: goals this universe runs, plus the current/preferred/rejected Branch
uses attached to those goals. A commons Branch may be reusable across many Goals
and universes; a universe run/use of a Branch must belong to a Goal.
User-facing chatbots should prefer existing similar Goals before creating new
Goal names so the commons converges around shared objective vocabulary.

**D7a - Branches are run by universes, not directly by users.**
A human MCP user can ask their own universe to adopt, run, or remix a Branch.
The runnable actor is the universe, and the run is recorded as that universe's
own goal-bound Branch-use instance. Multiple universes can use the same commons
Branch because each universe has a separate runtime instance. A universe can
remix a Branch into its own variant without overwriting the shared Branch.

**D8 - `body.md` is learned embodiment.**
`body.md` is an analogy document that aids personification. The universe is the
brain; body is the learned record of live things people can interact with as the
founder and universe build: platforms, applications, interfaces, hosted
services, and other real surfaces. Text that lands in the real world is voice.
Branches the universe runs are hands taking actions. Real-world feedback is
eyes, ears, and other sensory input. Creation does not invent a body; the file
starts not-learned and changes only as actual surfaces, actions, and feedback
are built or observed.

**D9 - `orgchart.md` is learned organization with a fixed founder anchor.**
`orgchart.md` is an organic organization map, not a generated hierarchy. The
founder confirmed by the oath is always the top of the org chart. Everything
below that top anchor is learned from actual work: roles, teams, daemons,
collaborators, delegations, responsibilities, and reporting lines. Creation does
not invent departments, titles, or reporting structure; it seeds the fixed anchor
rule and leaves the organization not-learned until work or authority decisions
teach it.

**D10 - First MCP contact enters the universe persona.**
Default MCP entry is not a platform status report. When an authenticated founder
connects without requesting a specific universe, the system resolves that
founder's home universe. If none exists, it creates the blank seed universe,
binds it to the founder, loads the root OKF soul bundle, and the chatbot speaks
in first person as that newly aware universe. If the founder already has a home
universe, the chatbot loads that universe's learned soul/persona and speaks as
that universe. A current universe selection is per founder or per client
session. There is no root-global `.active_universe` in the live multi-user
contract.

**D11 - Mobile clients are first-class, not alternate contracts.**
Future iOS and Android clients use the same WorkOS founder identity, MCP write
boundary, generated `universe_id`, and OKF universe brain contract. A phone can
be a client, a private universe host, or one endpoint in a phone/computer sync
setup. Mobile apps do not get a second creation route or a different brain
shape. Mobile auth/storage/app-integrity prep follows platform primitives:
Apple Keychain for local secrets, Apple App Attest/DeviceCheck-family signals
for app integrity where needed, Android Credential Manager/passkeys for auth
UX, Android Keystore-backed storage through platform libraries, and Google Play
Integrity as an Android app/device integrity signal. These signals are
additional risk checks; they never replace WorkOS `sub` or universe ownership.

Sources for mobile prep:

- Apple App Attest / DeviceCheck documentation:
  `https://developer.apple.com/documentation/devicecheck`
- Apple Keychain Services documentation:
  `https://developer.apple.com/documentation/security/keychain_services`
- Android Credential Manager documentation:
  `https://developer.android.com/identity/sign-in/credential-manager`
- Google Play Integrity API documentation:
  `https://developer.android.com/google/play/integrity`

## Risks / Trade-offs

- **HTTP clients still call create** -> Remove or fail that route with a clear
  error and update tests/docs. Do not silently create through it.
- **Tests encode slug-name behavior** -> Replace with generated-id and
  learned-name assertions.
- **Universe folders can drift from storage identity** -> Universe roots are
  generated serial-id directories matching `universe_id`.
- **`soul.edit` changes more than blank creation** -> Implement it as a readable
  OKF policy file plus execution path. Remove direct soul-overwrite semantics
  from the user-facing route and update callers.
- **`self/`, `soul/`, and `soul.md` overlap** -> Active universes use a root OKF
  bundle with `soul.md` as entrypoint; duplicate `self/`, `soul/`, brain
  archive folders, and empty starter files are removed during baseline
  reset.
- **Unlinked files become invisible junk** -> Baseline files must be linked from
  `index.md`, `soul.md`, `log.md`, or `soul_versions/index.md`. Runtime JSON/log
  files are excluded unless a real reader justifies and links them.
- **Global active universe leaks across users** -> Remove `.active_universe`
  from MCP default routing. First-connect and omitted-scope behavior resolve
  through the authenticated founder's home universe, and explicit universe
  selections are session/client state.
- **Authenticated scope could be mistaken for cross-universe write access** ->
  Require target-universe ownership for universe-brain writes. Keep public
  cross-universe interactions on proposal/request surfaces.
- **Ownership grants could accidentally make a universe private** -> Use
  `public_read` as the explicit visibility rule. Admin grants only authorize
  writes; they do not alter public/private readability.
- **Privacy flips could leak or strand a universe** -> Require explicit
  confirmation before both public -> private and private -> public changes.
- **Branch commons could be mistaken for direct user execution** -> Branches are
  runnable only by universes, and each run belongs to that universe's goal-bound
  Branch-use instance.
- **Universe clearing could erase branch commons** -> Keep branch definitions,
  goal catalogs, completed-run records, and outcome metrics outside the
  universe-brain reset path unless the user explicitly asks to reset branch
  commons.
- **Mobile app work could fork the contract** -> Treat mobile as another MCP
  client/host using the same WorkOS identity and universe contract.

## Implementation Plan

1. Add WorkOS resource-server auth tests proving token `sub` resolves to
   `founder_id` and anonymous callers cannot create universes.
2. Add ownership tests proving authenticated founders can write only to their
   own bound/home universe brain.
3. Add anonymous-permission tests proving public reads work and every write,
   run, create, ledger, sync, costly, and admin action is denied without an
   authenticated founder.
4. Add visibility tests proving owner/admin grants do not change `public_read`
   and public/private flips require confirmation.
5. Add Branch authority tests proving users can submit patch requests and
   Branch/Goal proposals, but Branch runs are executed only by universes and
   recorded as goal-bound Branch-use instances.
6. Add generated lowercase-ULID creation tests against MCP
   `universe action=create_universe`.
7. Move any required baseline creation into the MCP route.
8. Seed one OKF-conformant linked soul bundle during creation using the readable
   learning style from the current self-model text.
9. Remove `POST /v1/universes` as a creation route and update tests that call it.
10. Implement `soul.edit.md` as the edit-policy concept and make the execution
   path read/follow it when learning soul changes and writing version snapshots.
11. Bring universe roots to generated serial-id directories matching
   `universe_id`.
12. Remove duplicate `self/`, `soul/`, brain archive folders, and empty
   `notes.json` / `activity.log` starter files from active universe
   roots, and read persona/self-understanding from the root OKF soul bundle.
13. Add first-connect resolution: authenticated founder -> home universe; create
   and bind a blank seed universe if none exists; load the root OKF soul/persona
   and speak as that universe.
14. Remove `.active_universe` from MCP default routing. Omitted `universe_id`
   resolves through authenticated founder home-universe context; explicit
   universe choices live in client/session state.
15. Preserve branch commons when clearing universe brains unless the user
   explicitly asks to reset branch commons.
16. Keep HTTP universe listing/reading behavior only if still needed; it must not
   create universes.
17. Prepare a minimal Android test app only after the MCP auth/read/confirmed
   write contract is stable; it must call the same MCP surfaces and not create
   mobile-specific universe identity.
18. Run MCP-level and affected HTTP tests.

## Open Questions

- None for creation identity. The serial format decision is `u-` plus lowercase
  ULID.
