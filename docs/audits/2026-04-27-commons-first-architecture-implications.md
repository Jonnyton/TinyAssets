---
title: Commons-first architecture — project-wide implications sweep
date: 2026-04-27
author: navigator
status: read-only strategic discovery sweep — host curates response
companion:
  - project_commons_first_architecture (memory — host directive 2026-04-27, the principle this sweep applies)
  - project_minimal_primitives_principle (interacts: discover/remix become high-leverage primitives)
  - project_user_capability_axis (interacts: T1 browser-only users have no host)
  - project_privacy_via_community_composition (refined: privacy = host-resident, not platform-flag)
  - project_designer_royalties_and_bounties (the engine that makes remix work)
  - project_convergent_design_commons (this principle is the architectural realization)
  - docs/design-notes/2026-04-27-host-resident-private-data-design.md (sibling — data architecture)
  - docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md (sibling — community-evolves-features mechanism)
load-bearing-question: Where does the current architecture diverge from commons-first (private on hosts, public on platform, community remix as feature engine), and what's the migration path?
audience: lead, host
---

# Commons-first architecture — implications sweep

## Executive Summary

**21 findings across 6 axes.** The principle reshapes the platform's identity from "multi-tenant SaaS with privacy controls" to **"public OSS commons + host-resident private overlay."** Three structural changes at the top of the impact stack:

1. **Today's `visibility: "public" | "private"` field on `BranchDefinition` (and parallel on Goal) IS the soft-private anti-pattern the principle explicitly forbids.** Per the memory's anti-pattern list: "Soft-private branches. A 'private' flag on a platform record breaks the architecture. Either it's commons (public) or it's host-resident (truly private)." Today's code has private rows in the platform catalog with a viewer-side filter. Direct conflict — needs retire arc.

2. **The Phase 6 .author_server.db rename's framing changes.** The DB on each host IS the host-resident private store. It's not "platform DB renamed" — it's "host's private universe store, file-renamed for clarity." Phase 6's design note has the right migration but the wrong framing.

3. **T1 browser-only users (~95% of users) have no host. Two paths:** (A) all their content is commons, (B) community-hosted-on-your-behalf via a willing T2. Without one of these explicitly designed, browser-only users are LOCKED OUT of private workflows — a regression vs current behavior (where they can mark a branch private and trust the platform).

**Top 5 highest-leverage findings (ranked by user-impact × current-treatment-gap):**

| # | Finding | Action | Urgency |
|---|---|---|---|
| 1 | `visibility: 'public'\|'private'` on Branch + Goal IS soft-private anti-pattern; retire | Multi-arc data + code retirement: catalog records become public-only, private-tagged data emigrates to host. | **P0** — direct principle conflict |
| 2 | T1 browser-only users without a host can't have private content under strict commons-first | Design + ship community-hosted-on-your-behalf path (paid + free-friend variants). Browser-only users' privacy = a willing T2 hosts their universe. | **P0** — covers ~95% of users |
| 3 | Today's `output/<universe>/` per-universe data directory model is the right shape — it's already host-resident; just need to clarify which fields are public-vs-private | Per-universe DB stays as host-resident store; per-universe metadata WHICH IS PUBLISHED gets pushed to a separate "commons" layer (git catalog already exists for this — `tinyassets/catalog/`) | **P1** |
| 4 | Discover/similarity/remix substrate IS the load-bearing infrastructure — currently weak | New 6th MCP primitive `discover` (see sibling design note). Today: weak text search via `goals.search`, no similarity, no remix-with-credit chain. | **P1** |
| 5 | Privacy-modes design note (parked, 3 host Qs) becomes RETIRE-CANDIDATE — answer is "data is host-resident, no platform privacy policy needed" | Mark design-note as superseded; retire the 3 host Qs. | **P2** — already parked; just need closure |

**Findings that shifted the in-flight queue: 8.** Concrete reframes for Phase 6, A.1 unpack, paid-market design, privacy-modes note, primitive-set proposal, and PLAN.md.

**Findings that ratified existing direction: 7.** Wiki is already commons-shaped; git catalog (`tinyassets/catalog/`) already supports public commons; attribution model already designed (`project_designer_royalties_and_bounties`); A.1 unpack ratified; minimal-primitives ratified; convergent-commons memory ratified.

**Findings flagged for backlog: 6.** Federated-discovery research, multi-host availability UX, content moderation reframe, license-policy hardening.

---

## §1 — Where current architecture diverges from commons-first

### F1 — `BranchDefinition.visibility = "public" | "private"` field IS the soft-private anti-pattern

**Location:**
- `tinyassets/branches.py:729-734` — `visibility: str = "public"` on `BranchDefinition`
- `tinyassets/api/branches.py` — viewer-side filtering: `if visibility == "private" and branch.get("author", "") != _current_actor()` skip in listings, leaderboards, gate claims
- `tinyassets/catalog/serializer.py:125,291,312` — visibility persists into YAML catalog
- `tinyassets/api/engine_helpers.py` — `_filter_claims_by_branch_visibility()` and parallel `_filter_leaderboard_by_branch_visibility()` (Phase 6.2.2)
- `workflow.author_server.save_branch_definition` (now `daemon_server`) — normalizes to 'public'/'private' at SQLite layer

**What the principle says:** Per `project_commons_first_architecture` §"Anti-patterns":
> "Soft-private branches. A 'private' flag on a platform record breaks the architecture. There's no soft-private — either it's commons (public) or it's host-resident (truly private)."

Today's code is exactly this anti-pattern. Private branches sit in the same catalog as public, gated only by viewer-side filtering. The platform sees them, stores them, indexes them, ships them in backups. That's "stored on platform with access control" — the principle's other named anti-pattern: "Storing private data with platform-side encryption. That's still platform-resident."

**Recommended action — multi-arc retirement:**
- **Arc 1 (data architecture):** Define what's commons-bound vs host-bound. Catalog (branch defs, goal defs, public registrations) → commons (git-backed, public). Per-instance state (canon, runs, ledger entries) → host-resident only.
- **Arc 2 (code retirement):** delete `visibility` field from `BranchDefinition` and `Goal`. Delete `_filter_*_by_branch_visibility` helpers. Delete viewer-side filtering. Anything in the catalog IS public; anything not in the catalog IS host-resident.
- **Arc 3 (data migration):** existing `private` branches in catalogs → either (a) user publishes (becomes public; runs through commons license), or (b) user keeps host-resident (extracted from catalog, lives only in `<host>/output/<universe>/.workflow.db`).

**Sequencing:** Arc 1 design first (this audit + the sibling `host-resident-private-data-design` note), Arc 2 + Arc 3 follow. Multi-week.

**Urgency: P0 — direct principle conflict.**

### F2 — Universe metadata storage assumes platform-stored content

**Location:** `tinyassets/storage/__init__.py` data directory resolver. Per `output/<universe>/` per-universe layout, data CURRENTLY lives in `<TINYASSETS_DATA_DIR>/<universe>/.author_server.db` + `notes.json` + per-universe knowledge graph + LanceDB indexes.

**What the principle says:** This is actually FINE — `<TINYASSETS_DATA_DIR>` is the host's local data root, not platform-stored. The model is host-resident, just needs clearer naming.

**Recommended action — naming + framing:**
- Rename "platform DB" mental model to "host-resident workflow DB." Update Phase 6 design note framing accordingly.
- The cloud daemon (DO Droplet) IS itself a host. Whatever it stores IS host-resident from the platform's perspective. Just need to name what's commons-published.
- The PLATFORM (the abstract shared service) doesn't have a DB. It has:
  - The git-backed commons catalog (already exists at `tinyassets/catalog/`)
  - The wiki (host-published commons content)
  - The MCP-tool surface (stateless dispatch to whichever host has the data)

**Urgency: P1 — framing/docs work, not data movement.**

### F3 — `tinyassets/catalog/` (git-native YAML catalog) IS the public commons substrate — RATIFIED

**Location:** `tinyassets/catalog/{__init__.py, backend.py, layout.py, serializer.py}` — Phase 7 design.

**What the principle says:** Git-backed YAML catalog of branch defs, goal defs, node registrations, bid posts is EXACTLY the public commons. Public-by-construction (committed to git, fork-friendly, attribution-friendly). Already designed.

**Recommended action:** RATIFY. The Phase 7 storage-package split (host-decision-pending close-out per STATUS R7) closes this loop. After R7 confirms, this catalog IS the commons; no other "commons store" needs designing.

**Urgency: P1 — gates on R7 close.**

### F4 — Wiki at `tinyassets/api/wiki.py` IS the public commons knowledge layer — RATIFIED

**Location:** `tinyassets/api/wiki.py`, `pages/`, `drafts/` directory model, `wiki action=*` MCP verbs.

**What the principle says:** Per `project_wiki_is_uptime_surface` + `project_convergent_design_commons` + this principle: wiki is user-writable, public, collaborative. Already commons-shaped.

**Recommended action:** RATIFY. The 5+2 primitive-set proposal already folds wiki into `commons` (or splits into `discover` + `commons` per Q3). No reshape needed.

**Urgency:** N/A — ratification.

### F5 — Goal `visibility` field same anti-pattern as F1

**Location:** `tinyassets/catalog/serializer.py:291,312` — Goal also has `visibility` field.

**Recommended action:** Same arc as F1. Goals are commons or host-resident; same migration path.

**Urgency: P0** (folds into F1).

### F6 — Attribution graph data — public commons by construction

**Location:** `tinyassets/contribution_events.py`, `tinyassets/attribution/`, `CONTRIBUTORS.md`.

**What the principle says:** Per `project_designer_royalties_and_bounties` + commons-first: attribution data is INHERENTLY public (it's the commons-credit chain). Already public-by-design.

**Recommended action:** RATIFY. Attribution chain is commons-resident.

**Urgency:** N/A — ratification.

### F7 — Dispatcher queue (`tinyassets/dispatcher.py`) — request routing assumes data location is platform-trackable

**Location:** `tinyassets/dispatcher.py`, `tinyassets/scheduler.py`, `tinyassets/branch_tasks.py`, `tinyassets/bid/*`.

**What the principle says:** When a paid/free request needs to run against a PRIVATE branch, the dispatcher must route to a host that HAS THE BRANCH DATA, not just any willing claimer. New constraint: data-locality-aware routing.

For PUBLIC commons branches, any host that has the (cheaply-clonable) public catalog can fulfill — no locality constraint.

For PRIVATE host-resident branches, only the user's hosts (or hosts with explicit access) can fulfill.

**Recommended action:** Sibling design note (`discovery-similarity-remix-substrate`) §"Paid market against private data" addresses this. Net: dispatcher gains a `data_locality` filter on requests; private requests only route to hosts in the user's host-pool.

**Urgency: P1** — affects paid market design.

### F8 — Privacy-modes design note (parked, 3 host Qs) becomes RETIRE-CANDIDATE

**Location:** `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` (per STATUS Concern 2026-04-17).

**What the principle says:** The whole design is now obsolete. Private = host-resident; there are no privacy modes to design at the platform layer. The 3 host Qs evaporate.

**Recommended action:** Mark design note as SUPERSEDED by `project_commons_first_architecture` + the sibling `host-resident-private-data-design` note. Add archive header. Resolve the STATUS Concern.

**Urgency: P2** — closes a parked Concern.

### F9 — `add_canon_from_path` sensitivity note (3 host asks) — same outcome as F8

**Location:** `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md` (STATUS 2026-04-18).

**What the principle says:** `add_canon_from_path` is a LOCAL-APP primitive for host-resident data. The sensitivity question becomes "does the host trust the path?" — pure host-side concern. Platform doesn't see the data.

**Recommended action:** REFRAME the design note: "this is a local-app primitive operating on host-resident data; sensitivity is host-side, not platform-side." Reframe doesn't retire the 3 Qs but they shrink in scope (host-side path-whitelist, not platform-side encryption).

**Urgency: P2.**

### F10 — Claude.ai injection-mitigation design note — capability-axis sibling needed (covered in capability-axis sweep F4)

Already in the queue. Commons-first doesn't change the answer; flagging consistency.

**Urgency: P2.**

### F11 — Daemon roster + soul/ledger/attribution/royalty/bounty (STATUS deferred spec)

**Location:** STATUS Approved Specs row "[deferred] Daemon roster + node soul/ledger/attribution/royalty/outcome/bounty/fair-distribution items".

**What the principle says:** All of these are commons-shaped (souls, attribution, ledger, royalties, bounties) — they live in the public commons by definition. The deferral was waiting for scope clarity. Commons-first IS that clarity.

**Recommended action:** Activate the spec. Souls = public commons (registered + remixable). Attribution + royalty + bounty = ledger-tracked, public. Outcome = community-evaluated.

**Urgency: P1** — ready to scope; commons-first unblocks.

---

## §2 — Where current code is principle-aligned (RATIFIED)

| Component | Why aligned | Status |
|---|---|---|
| `tinyassets/catalog/` (git-native YAML) | Public commons by construction | F3 |
| `tinyassets/api/wiki.py` + `pages/` | Already commons-shaped | F4 |
| `tinyassets/attribution/` + `CONTRIBUTORS.md` | Attribution chain is public | F6 |
| `tinyassets/api/extensions.py` (`extensions list`, `describe_branch`) | Public-discovery surface | RATIFIED |
| MCP `goals search` | Discovery primitive seed | RATIFIED but weak (F12 below) |
| `tinyassets/registry.py` (node registry) | Public node catalog | RATIFIED |
| `tinyassets/payments/` (escrow, settlements) | Ledger is commons | RATIFIED |
| Per-universe directory model (`output/<universe>/`) | Already host-resident | RATIFIED with naming clarification (F2) |

---

## §3 — Discovery / similarity / remix substrate gaps

### F12 — Today's discovery surface is weak vs commons-first leverage

**Current discovery primitives:**
- `goals.search(query, limit, ...)` — text search across goal definitions. Good for "find a goal."
- `extensions.list_branches(domain_id, ...)` — list branches with optional filtering.
- `extensions.describe_branch(branch_id)` — read a specific branch.
- Wiki search via `wiki.search(query)`.

**Missing primitives** that commons-first needs:
- **Semantic similarity** ("find branches similar to my current one" / "find designs that solved a similar problem")
- **Battle-tested ranking** ("which branches in this domain produced verified outcomes")
- **Remix-with-credit** ("fork this branch + generate attribution event + publish remix")
- **Cross-domain transfer** ("this fantasy-author technique adapts to scientific computing — surface the analogy")
- **"What's hot"** (recently-active or recently-remixed designs)

**Recommended action:** Sibling design note (`discovery-similarity-remix-substrate`) builds these out. The 6th primitive `discover` houses all of them.

**Urgency: P1.**

### F13 — Multi-generation attribution chain — partially designed

**Location:** `project_designer_royalties_and_bounties` memory, `tinyassets/contribution_events.py`.

**What the principle says:** When User C remixes User B's design who remixed User A's design, attribution flows back through generations. Already memory-designed; needs implementation arc.

**Recommended action:** Cross-ref to sibling `discovery-similarity-remix-substrate` §"Multi-generation attribution."

**Urgency: P1.**

### F14 — License posture for the commons (parked decision)

**Per `project_license_fully_open_commons` memory:** "Goal is global commons adoption, content spreads beyond platform. Specific license (CC0 vs CC-BY-SA) still to pin."

**What the principle says:** Commons-first sharpens the urgency. Without a license, the catalog is technically "all rights reserved" by default — chilling effect on remix.

**Recommended action:** Pin the license decision. Recommend CC-BY-SA 4.0 for content, MIT or Apache-2.0 for code. Wikipedia-shape (`commons.wikimedia.org/wiki/Commons:Licensing`) is the canonical reference for content-commons license picking.

**Urgency: P1** — host-decision unblocking remix at scale.

---

## §4 — PLAN.md changes

### F15 — PLAN.md needs §"Commons-first architecture" section

**Current state:** PLAN.md doesn't name the commons-first principle as architectural. Memory does, but `AGENTS.md` says "Architecture truth lives in PLAN.md."

**Recommended action:** Lead surfaces to host: add a §"Commons-first architecture" section to PLAN.md cross-referencing the memory + this audit. Not a doc-edit task for navigator — host owns PLAN.md changes per AGENTS.md.

**Recommended PLAN.md text (suggestion only):**
> **Commons-first architecture (host directive 2026-04-27).** The platform's data space is the open-source community commons. Anything platform-stored is public-by-definition. Private content lives on host machines; platform never stores private data. Community designs become the tool surface for next users via discover + similarity + remix primitives. The platform doesn't ship features; the community evolves them. Engineering implications: §X cross-refs `project_commons_first_architecture` + `docs/design-notes/2026-04-27-host-resident-private-data-design.md` + `docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md`.

**Urgency: P1** — anchors the whole arc.

### F16 — PLAN.md §"Multiplayer Daemon Platform" needs reframing

**Current state:** Mentions "users, daemons, paid market" but doesn't make commons vs host-resident distinction explicit.

**Recommended action:** Reframe to make the data-locality model explicit. "Daemons execute on host machines; commons data is platform-shared; private data is host-resident-only."

**Urgency: P2** — bundles with F15 PLAN.md edit batch.

### F17 — PLAN.md §"Distribution And Discoverability" — discover primitive impact

Likely needs revision once `discover` primitive design lands (sibling note).

**Urgency: P2.**

---

## §5 — Cross-cuts to in-flight + queued work

### F18 — A.1 fantasy_daemon/ unpack arc — RATIFIED (commons-first sharpens the seam)

**Location:** `docs/design-notes/2026-04-26-fantasy-daemon-unpack-arc.md`.

**What the principle says:** A.1's split (engine to `tinyassets/`, domain to `domains/fantasy_daemon/`) maps EXACTLY to commons-first's split (engine substrate is commons-shared; domain skill definitions are commons; per-domain runtime state is host-resident). The unpack arc closes the rename arc; commons-first closes the data-locality arc. Same direction.

**Recommended action:** No A.1 scope change. Add a §"Commons-first ratification" note to the A.1 design note in §6 (sequencing dependencies) once host approves both.

**Urgency:** N/A — ratification.

### F19 — Phase 6 .author_server.db rename — REFRAMED, not rescoped

**Location:** `docs/design-notes/2026-04-27-author-server-db-filename-migration.md`.

**What the principle says:** The DB renamed in Phase 6 IS the host-resident private store. Phase 6's mechanics are correct; the FRAMING ("data DB rename") slightly misleads. Should read "host-resident workflow DB rename — closes the rename arc at the data layer for host-resident state."

**Recommended action:** When host approves Phase 6, add a 1-line framing clarification at top of the design note: "This DB lives on hosts (per commons-first architecture). Public commons data is in `tinyassets/catalog/` git-backed catalog, NOT this DB."

**Urgency: P2** — small framing edit.

### F20 — Paid market design — REFRAMED (data-locality-aware routing)

**Location:** Multiple design notes (`2026-04-19-daemon-economy-first-draft.md`, paid-market memories).

**What the principle says:** Paid jobs against private data require dispatcher to route to hosts with that data, not cheapest free claimer. Per F7. Also: the user's chatbot might say "find me a willing host to host my private universe overnight" — that's a paid-hosting market, distinct from paid-execution market.

**Recommended action:** Sibling design note `discovery-similarity-remix-substrate` §"Paid market under commons-first" addresses this with the data-locality dimension.

**Urgency: P1** — significant scope addition to paid market.

### F21 — 5+2 primitive-set proposal — UPDATED to 6+2 (split `discover` from `commons`)

**Location:** `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md`.

**What the principle says:** Discover/similarity/remix are LOAD-BEARING infrastructure. Strong claim for splitting `discover` from `commons`. Per Q3 in my pre-research note, recommend 6+2 over 5+2.

**Recommended action:** Sibling design note proposes the `discover` primitive shape; navigator updates the primitive-set proposal with a §"REFRAME 2026-04-27 — 5+2 becomes 6+2 under commons-first" addendum.

**Urgency: P1** — strategic primitive count.

---

## §6 — Browser-only user reality check

### F22 — Browser-only users (~95%) without host access have NO PRIVATE PATH under strict commons-first

**The problem:** Maya, Tomás, Priya — all T1 browser-only — have no host. Per principle, private data needs a host. So they have no private workflow option.

**Three architectural answers (recap from Q1 in pre-research note):**

- **(A) Hard tier gate:** browser-only users have NO private path. If you want privacy, install the tray (T2). Hard gate. Principle-pure but excludes 95% of users from privacy.
- **(B) Platform-as-hosting-provider:** platform offers a "host on your behalf" service. ANTI-PATTERN per the memory.
- **(C) Community-hosted-on-your-behalf:** a willing T2 host (paid or free-friend) hosts user's private universe. Compensation via paid market. Principle-pure: platform stores nothing; the data lives on a community member's host. User trusts that specific host, not the platform.

**Recommended action — design (A) primary + (C) extension:**
- T1 browser-only default: all your work is commons.
- T1 user wants private: chatbot offers community-hosting flow. User picks a willing T2 host (via reputation + price/free + capabilities); their private universe lives on that host. Platform routes execution requests there.
- This becomes a primary use case for the paid market: "Host my private universe for $5/month" or "host for free if I publicly attribute you as my collaborator."

The sibling design note `host-resident-private-data-design` builds out the shape.

**Urgency: P0** — without this, commons-first locks 95% of users out of privacy.

---

## §7 — Decision asks for the lead → host

1. **Confirm the principle's three parts** as architectural intent (private on hosts / public on platform / community remix as feature engine)?
2. **Approve the multi-arc retirement of `visibility: 'public' | 'private'`** field on Branch + Goal? Per F1, F5.
3. **Approve the community-hosted-on-your-behalf design** for browser-only users' private path? Per F22.
4. **Approve PLAN.md addition** of §"Commons-first architecture" section? Per F15.
5. **Approve commons license decision** (CC-BY-SA 4.0 for content, MIT/Apache-2.0 for code)? Per F14.
6. **Approve sibling design notes** as input for the multi-arc commons-first migration?
7. **Approve sequencing of commons-first arcs** post Arc B/C/Phase 6 + A.1 unpack? Multi-week structural arc; sequence after current rename arcs close.

---

## §8 — Cross-references

- `project_commons_first_architecture` (memory — host directive 2026-04-27) — the principle this audit applies
- `project_minimal_primitives_principle` — interacts with F21 (split `discover`)
- `project_user_capability_axis` — F22 (browser-only users + private path)
- `project_privacy_via_community_composition` — refined by this principle (privacy = host-resident)
- `project_designer_royalties_and_bounties` — F6, F13 (attribution chain)
- `project_convergent_design_commons` — this principle is the architectural realization
- `project_license_fully_open_commons` — F14 (license decision)
- `docs/design-notes/2026-04-27-host-resident-private-data-design.md` — sibling, data architecture
- `docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md` — sibling, community-evolves-features mechanism
- `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md` — F21 (5+2 → 6+2 reframe)
- `docs/design-notes/2026-04-26-engine-primitive-substrate.md` — F12 (E5 retrieval substrate is the seed for `discover`)
- `docs/design-notes/2026-04-26-fantasy-daemon-unpack-arc.md` — F18 (A.1 ratified)
- `docs/design-notes/2026-04-27-author-server-db-filename-migration.md` — F19 (Phase 6 reframe)
- `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` — F8 (RETIRE-CANDIDATE)
- `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md` — F9 (REFRAME)
- `docs/audits/2026-04-26-user-capability-axis-implications.md` — F10, F22 (capability-axis sibling)
- STATUS.md "Approved Specs: Daemon roster + node soul/ledger/attribution/royalty/outcome/bounty" — F11 (unblock)

### Web research citations

- [Distributed Hash Tables (DHT) | IPFS Docs](https://docs.ipfs.tech/concepts/dht/) — F-research: federated discovery patterns
- [Official MCP Registry | modelcontextprotocol.io](https://registry.modelcontextprotocol.io/) — federation infrastructure
- [Commons:Licensing | Wikimedia Commons](https://commons.wikimedia.org/wiki/Commons:Licensing) — F14 license-posture model
- [Civitai community model](https://civitai.com/) — community-remix evidence
- [Hugging Face Hub Licenses](https://huggingface.co/docs/hub/repositories-licenses) — license + discovery patterns
