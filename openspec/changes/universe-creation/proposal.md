## Why

Universe creation is currently split across two user-reachable paths: MCP
`universe action=create_universe` and HTTP `POST /v1/universes`. They create
different filesystem shapes and encode conflicting identity semantics. This
must become one long-term creation contract so future changes extend a single
route instead of adding another fork.

## What Changes

- **BREAKING:** Remove HTTP universe creation as a user-facing
  creation path.
- Make `universe action=create_universe` the single creation route end to end.
- Use WorkOS AuthKit bearer tokens as the production founder identity source;
  token `sub` is the immutable `founder_id` used for creation, home-universe
  binding, and first-contact persona entry.
- Generate exactly one immutable lowercase ULID serial during creation; that
  serial is the `universe_id`.
- Use that serial as the universe directory name and operation key.
- Maintain a root universe index keyed by immutable `universe_id`. It shows the
  current learned name from each universe's own identity file when one exists.
- Stop accepting creation-time names as universe identity. A client display
  label, if needed later, is metadata only.
- Define first MCP contact as entering the authenticated founder's home
  universe persona. If the founder has no home universe yet, create the blank
  seed universe, bind it to that founder, load its soul, and speak as that
  newly aware universe.
- Seed one blank learned OKF soul bundle at creation; the universe's self-name is
  learned later through the linked soul files rooted at `soul.md`.
- Make `soul.edit` the real soul edit policy concept. It lives as
  `soul.edit.md`, lays out how soul changes are learned, and governs edits to
  `soul.md`, `identity.md`, `founder.md`, `body.md`, `origin.md`, and version
  snapshots. `orgchart.md`, `projects.md`, and `goals.md` are not governed by
  `soul.edit`.
- Stop creating separate `self/`, `soul/`, `notes.json`, or `activity.log`
  baseline files for new universes. Duplicate `self/`, `soul/`, and brain
  archive folders are removed during baseline reset, not retained as artifacts.
  Empty `notes.json` / `activity.log` starter files are removed; non-empty
  historical notes/logs remain runtime data until they have an explicit typed
  runtime target.
- Make new `soul.md` files OKF concept documents that track the latest
  `okf/SPEC.md` on GitHub.
- Add `projects.md` as a one-line founder-project index with pointers as needed,
  and keep `goals.md` scoped to platform runtime goals plus the branch uses/runs
  attached to those goals.
- Make `body.md` the learned embodiment file: live platforms/applications are
  body surfaces, real-world text is voice, running Branches are hands, and
  real-world feedback is sensory input.
- Add `orgchart.md` as the learned organization map. The oath-confirmed founder
  is always the top anchor; roles, teams, daemons, collaborators, delegations,
  and reporting lines below the founder are learned organically.
- Remove host-global active-universe routing from the creation/default-entry
  contract. Any current universe selection is per authenticated founder or
  per client session, never one root marker shared by all users.
- Enforce the MCP write boundary: authenticated founders write only to their own
  bound/home universe brain. Public cross-universe interactions are proposal or
  request surfaces, not direct writes.
- Enforce anonymous access as public-read-only. Anonymous callers cannot write,
  create, run, mutate ledgers/state, or perform costly/admin actions.
- Keep owner/admin grants separate from public/private visibility. `public_read`
  controls whether public reads are allowed, and changing it in either direction
  requires explicit user confirmation.
- Treat Branch runs as universe actions. A human user can ask their own universe
  to run, adopt, or remix a Branch; users can also submit patch requests,
  Branch edit proposals, alternative Branch proposals, and Goal proposals to the
  commons surfaces.
- Preserve branch commons when universe brains are cleared. Branch definitions,
  goals, run metrics, and outcome records are outside the universe brain unless
  the user explicitly asks to reset branch commons.
- Prepare for future iOS/Android clients and phone-hosted or phone-synced
  universes without adding mobile-only creation, identity, or brain formats.

## Capabilities

### New Capabilities

- `universe-creation`: The long-term contract for creating Workflow universes,
  including route ownership, generated ids, seeded baseline files, founder
  binding, first-connect persona entry, linked OKF bundle shape, real
  `soul.edit.md` policy, anonymous read-only access, explicit universe
  visibility, mobile-client compatibility, and the boundary between technical
  ids, display metadata, and learned soul identity.

### Modified Capabilities

- None.

## Impact

- Affected public surface: MCP `universe action=create_universe`.
- Removed or rejected public surface: HTTP `POST /v1/universes`.
- Affected code: `tinyassets/auth/*`, `tinyassets/api/helpers.py`,
  `tinyassets/api/universe.py`, `tinyassets/api/status.py`, `fantasy_daemon/api.py`,
  `tinyassets/universe_soul.py`, `tinyassets/universe_self_model.py`, tests covering
  auth, universe creation, first-contact persona entry, and persona/soul-model
  initialization.
- Related design: `docs/design-notes/2026-06-26-founder-and-universe-identity.md`.
- External standard: `https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`
  tracked as latest-main for new `soul.md` shape.
