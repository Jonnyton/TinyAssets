---
title: Host-resident private data — architecture proposal under commons-first
date: 2026-04-27
author: navigator
status: active
companion:
  - project_commons_first_architecture (memory — the principle)
  - docs/audits/2026-04-27-commons-first-architecture-implications.md (sibling — implications sweep)
  - docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md (sibling — discover/remix design)
  - docs/design-notes/2026-04-26-engine-primitive-substrate.md (E1-E8 substrate; this design extends host-resident interpretation)
  - docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md (5+2; this design adds the `host-of-record` notion)
  - docs/design-notes/2026-04-27-author-server-db-filename-migration.md (Phase 6 — host-resident DB rename)
load-bearing-question: When private data lives on hosts (not platform), what's the storage layout, sync model, multi-host availability story, and migration path from today's "private rows in platform catalog" state?
audience: lead, host (final scope + sequencing decision)
---

# Host-resident private data — architecture proposal

## §0 — Frame

Per `project_commons_first_architecture`: private data lives on hosts; platform stores nothing private. This note designs the **shape** of host-resident storage + multi-host availability + migration from today's soft-private state.

This is NOT a complete spec — it's a strategic design proposal. After host approval of the architecture, a detailed implementation arc gets a separate exec-plan.

**Key constraints inherited from the principle + sibling memories:**

- **Async availability is acceptable** (per principle): if no host with the data is online, the user-with-access waits. Best-effort.
- **Browser-only users (T1) have no host of their own** (per `project_user_capability_axis`): need a community-hosting path.
- **Privacy is composition, not flag** (per `project_privacy_via_community_composition`): chatbot decides per-piece what's private.
- **No platform-side encryption** (per principle's anti-patterns): host-resident or doesn't exist; not "encrypted-on-platform."

---

## §1 — Storage layout — what's host-resident vs commons-published

### §1.1 — The data inventory

| Data category | Today's location | Commons or host? | Rationale |
|---|---|---|---|
| **Workflow definitions (BranchDefinition, NodeRegistration, Goal)** | Catalog (git+SQLite) + per-host SQLite | **COMMONS by default**, host-resident by user intent | Designs are public unless user keeps them private. Today's catalog already supports git-publish. |
| **Run state (in-flight + checkpoints)** | Per-host `output/<universe>/.author_server.db` (post-rename `.workflow.db`) | **HOST-RESIDENT only** | A run includes the user's actual inputs (Maya's invoices, Priya's species data). Always host-resident. |
| **Run outputs (artifacts: CSVs, PDFs, methods paragraphs)** | Per-host `output/<universe>/<run_id>/...` | **Choice: host-resident or published commons** | Published with user intent → commons (e.g. exemplary repro-script). Default → host-resident. |
| **Canon / knowledge graph / LanceDB** | Per-host `output/<universe>/{lancedb, knowledge.db, ...}` | **HOST-RESIDENT** | User-uploaded source material. Always host-resident. (Public canon is a separate concept — published commons knowledge.) |
| **Attribution events (commits, ledger entries)** | `tinyassets/contribution_events.py` | **COMMONS** (publicly trackable), private actions also-host | Public-action events: commons. Private host-only actions: host. |
| **Soul files (per-daemon identity)** | `output/<universe>/<daemon_name>/soul.md` per `project_daemon_souls_and_summoning` | **Choice: published or host-resident** | Soul files publish to commons IF user wants — they're remix material. Default host. |
| **Bug reports + wiki pages** | Wiki | **COMMONS** | Already commons-shaped. |
| **Goals (shared workflow intent)** | Catalog | **COMMONS** | Public by definition; private goals are an oxymoron. |
| **Bids (paid-market posts)** | Catalog | **COMMONS** | Public auction surface. |
| **User accounts + sessions** | Per-host or auth provider | **HOST-RESIDENT** (no platform-side user table) | OAuth provider holds identity; host SQLite stores per-host session. |
| **Universe metadata (name, owner, daemon list, settings)** | `output/<universe>/notes.json` | **HOST-RESIDENT by default**, commons subset on publish | Universe IS the host-resident container. Publishing a workflow from a universe doesn't publish the universe. |

### §1.2 — Layout proposal

**Per host:**

```
$TINYASSETS_DATA_DIR/
├── universes/                              # HOST-RESIDENT
│   └── <universe_id>/
│       ├── .workflow.db                    # SQLite — branch/run/goal state for this universe
│       ├── notes.json                      # universe metadata (name, owner, settings)
│       ├── canon/                          # uploaded canon files (preserved per Hard Rule 9)
│       ├── lancedb/                        # vector embeddings
│       ├── knowledge.db                    # KG over this universe
│       └── runs/<run_id>/                  # per-run artifacts
├── commons-cache/                          # READ-ONLY local cache of commons catalog
│   ├── catalog/                            # YAML mirror of git commons catalog
│   ├── wiki/                               # local wiki replica
│   └── attribution/                        # public attribution graph cache
├── auth/                                   # HOST-RESIDENT
│   └── .auth.db                            # OAuth tokens, session state
└── ledger/                                 # HOST-RESIDENT host's own
    └── settlement.db                       # paid-market settlement ledger entries (host-side view)
```

**At the platform (commons):**

```
<commons-git-repo>/
├── catalog/
│   ├── branches/<branch_def_id>.yaml       # PUBLISHED branch defs (no private branches here)
│   ├── nodes/<node_id>.yaml                # public node registrations
│   ├── goals/<goal_id>.yaml                # public goal definitions
│   └── bids/<bid_id>.yaml                  # active paid-market bid posts
├── wiki/                                   # collaborative wiki (current implementation)
│   ├── pages/
│   └── drafts/
├── souls/<daemon_name>.md                  # PUBLISHED daemon souls (opt-in)
└── attribution/
    └── events.jsonl                        # public attribution events (commits, remix chains, ledger settlements)
```

**Key structural property:** the platform repo carries NOTHING that's per-user-private. Every YAML row is publishable, forkable, attributable. A user reading the platform catalog directly (git clone) sees ONLY commons content.

### §1.3 — Per-universe vs per-user data partitioning

**Per principle:** a universe IS a host-resident container. The user's private workflow state lives in `<host>/universes/<universe_id>/`. Multiple users' universes can coexist on one host (multi-tenant per `project_daemons_are_multi_tenant_by_design`); each is its own subdir.

**A user's "data" is the union of all universes they own across all hosts they have access to.** Discovery question: "where are my universes?" answers via the user's own host inventory + access-grant records (see §2 below).

---

## §2 — Multi-host availability + sync model

### §2.1 — The host inventory problem

If User A's private universe lives on Host H1, and User A grants access to User B, how does User B's chatbot find it?

**Three readings:**

**(A) Per-user host-list registry.** A platform-side (yes, ironic — but this is metadata, not data) registry of "User A has hosts H1, H2, H3" — public-by-construction, just IDs and capabilities, no content. Like DNS for hosts.

**(B) Discovery via DHT.** Distributed hash table over the user-host graph. IPFS-shaped (per research: `docs.ipfs.tech/concepts/dht/`). Self-publishing; no central registry. **Heavier.**

**(C) Out-of-band coordination.** User shares a host URL with collaborator manually. Like sharing a Google Drive link. Lowest friction; least scalable.

**Recommendation: (A) primary + (C) for unregistered hosts.**

**Why:** the host-list IS metadata, not user content. Publishing "User A has these hosts" doesn't violate commons-first (it's about routing, not content). DHT (B) is over-engineered for the single-host-MVP scale. Out-of-band (C) covers the long tail and pre-registration cases.

### §2.2 — Host registration + capability advertisement

Each host registers itself in the commons-side host registry (per principle: this is "metadata, not content"):

```yaml
# commons-git-repo/hosts/<host_id>.yaml
host_id: "host-abc123"
owner: "user-alice"  # or "anonymous-public-host"
endpoint: "https://alice-tray.example.com/mcp"
capabilities:
  - llm: ["claude-opus", "claude-sonnet", "ollama-local"]
  - software: ["python-3.13", "ASP-engine", "fantasy-author-domain"]
  - storage_offered: "200GB"
  - max_concurrent_runs: 4
visibility: "self" | "network" | "paid"  # who can dispatch to this host
hosted_universes:                         # ONLY public universes this host claims
  - universe_id: "<id>"                   # for routing public-content runs
    capabilities: [...]
# Note: PRIVATE universes do NOT appear here. The host knows them; nobody else does
# unless the user-with-access has been granted via §2.3.
```

**Visibility semantics:**
- `self` — host accepts work only from its own user
- `network` — host accepts work from a list of GitHub-handle / public-key collaborators
- `paid` — host accepts work from anyone willing to pay (paid-market bids)

### §2.3 — Per-universe access grants (host-side)

A private universe's access list is stored host-side (NOT in commons):

```sqlite
-- Per host: <host>/universes/<universe_id>/.workflow.db
-- table: universe_access
-- (universe access lives ON the host with the data, not in commons)
CREATE TABLE universe_access (
  granted_to_user_id TEXT NOT NULL,  -- the user-with-access
  capability TEXT NOT NULL,          -- "read" | "write" | "execute"
  granted_at INTEGER NOT NULL,
  granted_by_user_id TEXT NOT NULL,
  expires_at INTEGER                 -- NULL = no expiry
);
```

**When User B asks their chatbot "show me User A's private project":**
1. Chatbot looks up User A's host inventory (from commons host registry, §2.2)
2. For each of A's hosts, chatbot tries an authenticated request: "do you have a universe shared with User B?"
3. Online host with matching access record returns the universe metadata (or content via further requests)
4. If no host with that universe is online, chatbot says "User A's private universe isn't reachable right now — try later, or ask User A to bring a host online."

**This is the async-availability UX named in the principle.** It's by design.

### §2.4 — Sync between hosts (multi-host private universe)

User A may run their private universe on multiple hosts (laptop + cloud daemon + friend's machine). State sync between them:

**Option A — Single source of truth + replicas.** One host designated "primary"; others are read-only replicas. Sync via host-to-host pull (rsync-shape, or git-LFS-shape for binary state).

**Option B — Multi-master CRDT.** Each host can write; conflicts resolved via CRDTs. Heavier engineering.

**Option C — Manual sync (out of scope for v1).** User runs `workflow sync host-1 → host-2` periodically. Simplest to ship; offloads correctness to user.

**Recommendation: Option A primary, Option C as v1 fallback.** Single-master + read-replicas matches today's model (single host per universe). Multi-host is a v2 concern; design the v1 with a clean upgrade path to A.

### §2.5 — Browser-only users — community-hosting path

Per §F22 of sibling sweep: T1 browser-only users (Maya, Tomás) need someone else to host their private content. Three subpatterns:

1. **Friend hosting** — User A's friend Bob runs a tray. Bob agrees to host A's private universe for free or in exchange for collaborator-credit. The universe lives on Bob's host. Auth grants A access; Bob has admin.

2. **Paid hosting** — A pays a willing T2 host (via paid market) to host A's universe. Compensation per `project_designer_royalties_and_bounties` model. Standard rate-card surface.

3. **Anchor host** — A pays the platform's reference cloud daemon (the DO Droplet) to host. Same as (2) but via a known-good first-party host. **Note:** even this is host-resident, not platform-stored — the DO Droplet is JUST ANOTHER HOST per commons-first. The platform provides the connector + commons + dispatcher; the cloud daemon is a service on top.

**Per principle:** all three are valid; (1) and (2) are community-evolved, (3) is platform-as-host-of-resort. All preserve "platform never stores private."

**The chatbot's job:** when a browser-only user wants private work, the chatbot offers the three options + helps user pick. Maya might pick (1) — "your nephew's gaming PC could host this" — Tomás might pick (2) for $5/mo, Priya might pick (3) — "anchor with platform's reference host for reliability." Same architecture; user-chooses-the-trust-anchor.

---

## §3 — Migration path from today's "private rows in catalog" state

### §3.1 — Current state inventory

**Today, private branches/goals/etc. live in the platform catalog (per F1, F5 in sibling sweep). Migration shape:**

```
TODAY:
  catalog/
  ├── branches/
  │   ├── public-branch-1.yaml    visibility: public
  │   ├── public-branch-2.yaml    visibility: public
  │   ├── private-branch-1.yaml   visibility: private (anti-pattern)
  │   └── private-branch-2.yaml   visibility: private (anti-pattern)
  └── goals/...

MIGRATION TARGET:
  commons-catalog/                 # platform-side; only public
  ├── branches/
  │   ├── public-branch-1.yaml
  │   └── public-branch-2.yaml
  └── ...

  <each user's host>/universes/<universe>/
  ├── private-branch-1.yaml        # extracted from old platform catalog
  └── private-branch-2.yaml
```

### §3.2 — Migration sequencing (recommended: greenfield + grandfathering per Q2)

**Phase 1 — Future-proof (forward-compat):**
- Stop accepting `visibility: 'private'` for new branches/goals via MCP (gate at `tinyassets/api/branches.py`).
- Replace with one of: `publish=true` (commons publish) or `host_only=true` (host-resident, doesn't enter commons catalog).
- New private branches go straight to host-resident; never enter platform catalog.

**Phase 2 — Audit existing private rows:**
- Survey all rows with `visibility: private` in current catalog (per host's local SQLite + git-backed commons-catalog if Phase 7 has shipped).
- Per-row: notify owner via wiki message / chatbot prompt: "this branch is in the legacy private catalog; migrate to host-resident or publish to commons?"
- Default after grandfathering window (recommend 6 months): chatbot proactively prompts on next user-touch.

**Phase 3 — Code retirement:**
- Once all legacy-private rows are migrated, delete `visibility` field from `BranchDefinition` + `Goal`.
- Delete viewer-side filtering helpers (`_filter_*_by_branch_visibility`).
- Catalog becomes public-only; presence implies publication.

**Phase 4 — Post-cutover validation:**
- `TINYASSETS_LEGACY_PRIVATE_AUDIT=1` returns zero rows on every host.
- Pre-commit invariant: `visibility` field doesn't exist on any catalog row YAML.
- Wiki page documenting the migration's completion + how privacy works post-cutover.

**Total arc: ~6-9 months grandfathering + ~2 weeks code+migration work spread across.**

### §3.3 — Failure modes during migration

| Failure mode | Mitigation |
|---|---|
| User loses access to private branch during migration | Migration is COPY-then-flag-stale; original isn't deleted until user confirms host-resident copy works. |
| User abandons the platform mid-migration | Legacy private rows remain in old catalog as orphans; quarterly cleanup invites them to either publish or delete. |
| Two hosts both think they own a migrated private branch | Conflict resolution via "first-host-to-confirm wins"; second host's copy gets renamed `<name>.alternate.yaml` for user disambiguation. |
| Browser-only user has private branch but no host | Chatbot prompts community-hosting (per §2.5). If user can't find a host, the branch becomes commons-publish or sits in legacy-private orphan tier. |

---

## §4 — Async availability UX

Per principle: "Users with access who arrive when no host is online wait or get a graceful 'no host online with this content right now' signal."

### §4.1 — Concrete UX patterns

**User asks chatbot: "show me my private invoices project"**

Outcomes by host availability:

| Host state | Chatbot response |
|---|---|
| User's host online + reachable | Full content; works as today. |
| User's host briefly offline | "Looks like your invoice host isn't responding — could be a brief network blip. Want to retry in 30s?" |
| User's host offline > 5 min | "Your invoice work lives on your laptop, which appears to be offline. Bring it online, or share access with the cloud daemon if you want this work to be reachable when your laptop's off." |
| All hosts with universe offline (multi-host case) | "All hosts with this universe are offline right now. Last seen: H1 2 hours ago. Try later, or contact one of the hosters." |
| User-with-access (not owner) trying to reach | "User A's private universe isn't reachable right now — no host with access is online. Try later." |

### §4.2 — Indicators in the chat-rendered UI

- **Always show host status** when a request touches private data: "Reading from `alice-laptop` ✓" / "Trying `alice-laptop` ✗ → falling back to `alice-cloud` ✓"
- **"Bring my host online" link** when offline. Goes to a runbook for tray-restart on laptop, or paid-host purchase flow for browser-only users.
- **"Make this commons" link** as escape hatch — user can always promote private to public if they want guaranteed availability.

### §4.3 — Cache + fallback patterns

For READ-MOSTLY private data (e.g. canon docs that change rarely), the user's chatbot can cache locally. But:

- **No platform-side cache** — that violates commons-first. Platform NEVER touches private data.
- **Chatbot-client-side cache** (in Claude.ai's session memory) is acceptable but non-durable. When session ends, cache evaporates.
- **Cross-host replica** is the correct durable cache (per §2.4 Option A). User runs the universe on 2 hosts; one is the primary, the other a read-replica.

---

## §5 — Risk profile

### §5.1 — Low-risk

- **Catalog changes are mostly additive then subtractive.** Phase 1 stops accepting new `visibility: private`; nothing in production breaks. Phase 3 deletion happens after audit window.
- **Per-host data layout is already host-resident.** Today's `output/<universe>/.workflow.db` IS the host-resident store. The change is renaming + framing, not data movement.
- **Wiki + attribution graph + git-commons-catalog already work as designed.** No retire arc for those.

### §5.2 — Medium-risk

- **Browser-only user community-hosting flow is new.** First-time UX is critical (per Maya's grievances list); host-discovery + payment + access-grant flow needs to feel like 1-2 chat turns, not a 10-step wizard.
- **Multi-host sync semantics in v2.** Single-master + replicas is workable for v1 but needs CRDT or manual-sync upgrade story before users hit collisions at scale.
- **Auth + access-grant cross-host coordination.** OAuth-flow against provider, then per-host access-grant SQLite, then dispatcher routing — ensures no leak of private content but requires 3-layer testing.

### §5.3 — High-risk

- **User trust during migration.** If a user's private branch goes briefly inaccessible during Phase 2 migration, trust breaks. Migration MUST be copy-then-flag-stale, never move-then-delete.
- **Discovery surface false-negatives.** If chatbot can't find user's prior private work because the host with it is offline, user thinks the platform "lost" their data. Needs clear "host is offline, last seen X ago" UX (per §4).

---

## §6 — Sequencing dependencies

### §6.1 — Hard dependencies (must ship first)

- **A.1 fantasy_daemon/ unpack arc** — closes the rename's package layer; commons-first's data-layer changes operate on a clean tree.
- **Phase 6 .author_server.db rename** — host-resident DB filename matches its semantic role.
- **Arc C Phase 3** — legacy env-var aliases die before catalog migration. Arc B Phase 3 code-rename alias deletion has already shipped.

### §6.2 — Cannot block

- Methods-prose evaluator (REFRAMED community-build per host directive 2026-04-26) — orthogonal.
- Recency composition + `run_branch resume_from` (F2 accepted 2026-04-28) — orthogonal.
- Cloud daemon redeploy — orthogonal.

### §6.3 — Suggested sequencing

```
... current rename arcs ...
  → A.1 unpack arc (close package layer)
  → Phase 6 (rename data-layer file)
  → THIS WORK Phase 1 (forward-compat — stop accepting new private rows)
  → THIS WORK Phase 2 (audit + grandfather window opens)
  → discover/remix substrate ships (sibling note's work)
  → THIS WORK Phase 3 (code retirement)
  → THIS WORK Phase 4 (post-cutover validation)
```

---

## §7 — Decision asks for the lead → host

1. **Confirm the data inventory in §1.1** — which categories are commons vs host-resident? Especially: are `souls/<daemon_name>.md` published to commons by default or only on opt-in?
2. **Approve the per-user host-list registry pattern (§2.1 option A)?** Vs DHT (B) or out-of-band (C)? Recommend (A) primary + (C) for unregistered.
3. **Approve community-hosting path for browser-only users (§2.5)?** Three subpatterns (friend-host / paid-host / anchor-host). Any to drop or expand?
4. **Approve migration sequencing (Phase 1-4) + ~6mo grandfathering window (§3.2)?** Or aggressive cutover preferred?
5. **Approve single-master + replicas (Option A) for v1 multi-host sync (§2.4)?** Or skip multi-host entirely in v1, ship single-host-only?
6. **Approve the layout proposal (§1.2)?** Naming: `commons-catalog/` vs `public-catalog/` vs other? `host's view: universes/<id>/` vs `output/<universe>/` (today's name)?
7. **Approve PLAN.md addition** of host-resident-vs-commons data-layer model? (Cross-reference with sibling sweep F15.)

---

## §8 — Cross-references

- `project_commons_first_architecture` — the principle this design realizes
- `project_user_capability_axis` — F22 in sibling sweep (browser-only path)
- `project_daemons_are_multi_tenant_by_design` — multi-tenant per host
- `project_designer_royalties_and_bounties` — paid-hosting compensation
- `project_daemon_souls_and_summoning` — soul publication question §7.1
- `docs/audits/2026-04-27-commons-first-architecture-implications.md` — sibling sweep
- `docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md` — sibling, the discover side
- `docs/design-notes/2026-04-26-engine-primitive-substrate.md` — E3 (checkpoint) is the host-resident substrate
- `docs/design-notes/2026-04-27-author-server-db-filename-migration.md` — Phase 6 closes data-layer naming
- `tinyassets/storage/__init__.py` — `data_dir()` resolver (host-resident root)
- `tinyassets/catalog/` — git-native catalog (commons substrate)
- `tinyassets/branches.py:729` — `visibility` field that retires

### Web research citations

- [Distributed Hash Tables (DHT) | IPFS Docs](https://docs.ipfs.tech/concepts/dht/) — §2.1 option B reference
- [InterPlanetary File System | Wikipedia](https://en.wikipedia.org/wiki/InterPlanetary_File_System) — federation patterns
- [IPFS Kademlia DHT spec](https://specs.ipfs.tech/routing/kad-dht/) — DHT routing primitives
- [The Road to the New DHT | IPFS Blog](https://blog.ipfs.tech/2020-05-19-road-to-dht/) — host-availability tradeoffs at scale
