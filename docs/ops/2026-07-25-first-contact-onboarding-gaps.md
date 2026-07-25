# First-contact branch/wiki onboarding evidence and correction manifest

**Freshness:** 2026-07-25, rebased `origin/main` source at `8ec01ab3` plus direct reads from `https://tinyassets.io/mcp`.
**Mode:** read-only audit. No live wiki, runtime, deployment, or canonical-spec mutation was performed.
**Scope:** current first-contact branch journey, registered MCP prompts, user-facing hints, repository handoff copy, and an exact-path but lower-bound public wiki planning inventory. It is not exhaustive until a privileged `scope=all` inventory or volume export is reconciled.

## Outcome

The defect is both instructional and structural:

1. The public connector advertises exactly seven handles, but registered prompts and returned hints teach hidden legacy tools.
2. `read_graph(target="branch")` and `run_graph` require a pre-known branch identifier.
3. `write_graph(target="branch")` patches only; the exact-seven surface has no branch catalog or complete-definition create path.
4. The exact-seven surface has no deliberate branch publication path; ordinary patching currently mints snapshots that listing can mistake for publication.
5. The internal list/build/publication seams are reusable only after authority, privacy, pagination, idempotency, explicit-publication, and error-projection hardening.

Prompt cleanup alone cannot repair onboarding. The OpenSpec change therefore specifies a bounded `read_graph(target="branches")` catalog and closed, transactionally idempotent create/publish modes under `write_graph(target="branch")` without adding a tool. Hosted catalog authority is Postgres-canonical; legacy SQLite state is only one-way import input or a downstream execution projection. Catalog/create/publish remain unavailable until every exact Branch projection filters restricted related-wiki metadata and non-visible Goal data.

## Source-owned first-contact gaps

| Source | Current problem | Correction owner |
|---|---|---|
| `tinyassets/api/prompts.py` | Calls the surface “5 tools”; teaches `universe`, `extensions`, `goals`, `wiki`, `community_change_context`; assumes raw branch IDs | Canonical prompt owner |
| `tinyassets/universe_server.py` | `meet_universe` docstring says load through `get_status`; extension/branch prompt wrappers promise hidden `extensions`; hidden rejection says “five canonical handles”; birth card names hidden soul edit | MCP router/prompt owner |
| `tinyassets/api/branches.py` | Branch guide and warnings teach hidden search/build/patch/get/approve actions and opaque IDs | Branch-authoring owner |
| `tinyassets/api/wiki.py` | `read_page` results recommend hidden `wiki action=search/since/read/list` | Wiki API owner |
| `tinyassets/api/universe.py` | Cross-surface hints recommend hidden extensions/goals/wiki/universe actions | Universe owner |
| `tinyassets/api/market.py` | Goal/gate errors recommend hidden goals/extensions/gates calls; some lack canonical equivalents | Goals/gates owner; remove unsupported advice |
| `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md` | Describes `get_status` plus six hidden tools as seven live tools and routes normal work through them | Documentation owner; correct or mark historical |

Canonical sources and packaged plugin mirrors were byte-identical when inspected. Future correction must edit canonical sources and regenerate with `python packaging/claude-plugin/build_plugin.py`, never hand-edit one mirror.

## Runtime seam evidence

- `tinyassets/universe_server.py:426-493`: `read_graph` supports exact `target="branch"` only; no `branches` catalog target.
- `tinyassets/universe_server.py:511-641`: `write_graph(target="branch")` always delegates to patch and cannot create.
- Freshness check on 2026-07-25 found no `UNIVERSE_SERVER_USER` configuration in `deploy/` or `.github/workflows/`; the environment fallback resolves to anonymous in the inspected deployment configuration and cannot supply verified authority.
- `tinyassets/api/branches.py:548-619`: internal list is visibility-filtered but unbounded, lacks stable pagination, and exposes ambiguous internal scopes.
- `tinyassets/api/branches.py:2080-2329`: internal full-definition build validates then saves atomically at the branch level, but accepts caller-influenceable author fields, defaults public visibility, lacks body-bound idempotency, and can echo attempted definitions on error.
- `tinyassets/api/branches.py:2687,2702`, `tinyassets/api/evaluation.py:863`, and `tinyassets/api/selector_dispatch.py:331` write branch versions; ordinary patch snapshots can appear published because the store has no deliberate catalog-publication bit.
- The hidden `publish_version` action is the only deliberate user publication path, while `set_published` changes only the non-authoritative definition boolean. Replacement must precede retirement.
- The legacy publication action accepts caller-supplied `publisher`, checks write scope but not branch ownership, and can mint an operational version for another actor's branch under a spoofed label. V1 catalog publication must require the verified branch owner and must never treat `branch_versions.publisher` as authorship or catalog authority. Service publication needs a later scoped-capability review.
- A private `fork_from` version can be loaded before a safe source-visibility decision in the legacy build seam. V1 rejects fork/remix input instead of publishing that unsafe behavior.
- Exact branch reads currently derive `related_wiki_pages`; the open STATUS concern records restricted path/title/summary leakage. The new catalog must not reuse that projection.
- Existing branch patch batches are transactional across their operations, but the public router exposes no expected hash/version. They are not compare-and-swap and must not be described as CAS.

## Live wiki direct correction set

These full hashes came from current `read_page` source proofs. They are pre-images for planning only and must be refreshed immediately before any write.

| Exact page | Audience | 2026-07-25 pre-image SHA-256 | Classification | Exact replacement | Dry-run | Guarded write | Post-image SHA-256 |
|---|---|---|---|---|---|---|---|
| `pages/plans/chatbot-builder-behaviors.md` | Pending privileged audience read | `d7abd7b775b8ceb034d6b44db29d437c52b4944a0a3589130a37877fa283ccc3` | Direct, highest priority | Pending exact text after canonical branch/page/goal compositions deploy | Pending | Blocked: no serialized writer | Pending |
| `pages/concepts/before-filing-a-patch-request-user-buildable-check.md` | Pending privileged audience read | `998b7eaeab1b9f6b367e967d6ee63d5c5ed2b439301d963c2aba0d7dd905438a` | Direct | Pending exact text; remove dotted/hidden calls and do not claim excluded fork behavior | Pending | Blocked: no serialized writer | Pending |
| `pages/concepts/pages-concepts-workflow-substrate-canonical-vocabulary-6-primitives-5-mcp-handles.md` | Pending privileged audience read | `55dc3c3f8d9bfe37e4b0a1d2a1dddd42ad9c17d4df54edd933c6fe8182faaab4` | Direct | Pending exact text distinguishing substrate operations from canonical wire handles | Pending | Blocked: no serialized writer | Pending |
| `pages/projects/meet-tiny.md` | Pending privileged audience read | `ca1f1378d96b5610f4ec959a0de399d1343a16aaaab7946668d2ddce5da3df1b` | Direct | Pending exact text replacing hidden universe/gates and opaque-ID instructions | Pending | Blocked: no serialized writer | Pending |
| `pages/projects/workflow-voice-twitter-daemon.md` | Pending privileged audience read | `adce1b720564e7d89faf1ce39c1d2044860cc0391a5b48a5c097e79677524417` | Direct/project state | Pending until a supported schedule/get composition exists | Pending | Blocked: no serialized writer | Pending |
| `pages/concepts/auto-hydrate-then-invoke-v1.md` | Pending privileged audience read | `3cd4048a17ee715641db254bcc5f8faf470cff9328cd50fbcbe5e29919143963` | Historical concept | Pending concise current-surface/superseded banner; preserve provenance | Pending | Blocked: no serialized writer | Pending |

## Lower-bound historical/current-surface banner set

Public search also returned the following promoted exact-hit pages. Most are historical concept/research material and should receive a current-surface or superseded banner instead of rewritten history:

- `pages/concepts/anticipation-gap-and-permission-ladder-jones-2026-05-07.md`
- `pages/concepts/brain-architecture-deep-dive-synthesis-2026-05-03.md`
- `pages/concepts/brain-update-003-completeness-cursor-enumeration-fallback.md`
- `pages/concepts/brain-update-005-merge-authorization-state-routing-anomalies-derived-views.md`
- `pages/concepts/capability-provisioning-via-brain-pages.md`
- `pages/concepts/factory-branch-games-directory-substrate-contract-2026-05-24.md`
- `pages/concepts/factory-branch-remix-proof-stellar-front-2026-05-24.md`
- `pages/concepts/pages-concepts-cowork-unfinished-central-ambition-audit-and-refactored-direction-2026-05-06.md`
- `pages/concepts/phase-4-multi-user-consensus-design-layer-v2.md`
- `pages/concepts/semantic-queue-reconciler-v1.md`
- `pages/concepts/website-as-live-project-observability.md`
- `pages/concepts/work-primitive-industry-framing-jones-2026-05-06.md`
- `pages/research/track-c-validator-checkpoint-log.md`

Every public search for `community_change_context`, `extensions action`, `gates action`, `wiki action`, `branch_def_id`, and `read.graph` reported `search_complete:false`. This inventory is therefore a lower bound. Exhaustiveness requires privileged/in-process `scope=all` or a volume export.

## Safe live-page apply procedure

For each page independently:

1. `read_page(page=<exact path>)` and capture the fresh `source_read_proof.sha256`.
2. Prepare an exact, minimal `old_text` → `new_text` patch.
3. Call `write_page` with the exact page, `expected_sha256`, and `dry_run=true`.
4. Require exactly one match, inspect the preview and proposed new hash.
5. Only after repository/runtime review gates, the owned explicit commons route, and a separately reviewed serialized/locked single-writer boundary are active, call authenticated `write_page(scope="commons", ..., dry_run=false)` for that one page.
6. Re-read and record the post-image SHA-256.
7. Stop on any SHA mismatch, zero/multiple match, unexpected audience/authority result, or content drift.

The current wiki patch owner conflicts on SHA mismatch or when `old_text` does not match exactly once, but its read/check/write sequence is not locked and therefore is not atomic compare-and-swap. Full-page writes and filings are not safe previews. This lane permits targeted dry-runs now but blocks live mutation until a separately reviewed serialized/locked single-writer boundary exists.

## Gates before any runtime or live write

- Claude Opus 5 opposite-provider APPROVE or accepted ADAPT on the exact spec/evidence head.
- Explicit landed SHAs or file-specific handoffs from universe-creation, universe-visibility/shared-Goals, and `control_station`; accepted production Postgres migration/role/RLS/recovery baseline with an allocated exact migration filename; and the owned `scope=commons` wiki route. Preserve newborn-BYOC behavior from #1759 but omit executable run guidance until the full requester-authority/isolation gates land. Retire-legacy caller inventory v4 landed in #1772; retire tasks 2.3a/2.3b/4.0 preserve publish, approval, and remix/lineage until canonical replacements and rendered proofs exist.
- Rotation-catalogued `TINYASSETS_BRANCH_CRYPTO_KEYRING` provisioned with no ephemeral/default-key fallback.
- V1 remains public-commons-only and selects no private-data custody mode; private authoring needs a separate PLAN-approved change naming its chosen custody mode, trust boundaries, storage, and routing.
- Failing tests precede implementation.
- Exact-seven canary, 500-client load proof, packaged mirror parity, and real browser-rendered chatbot acceptance are required.
- No founder/maintainer provider quota or compute is used by created/published branches; guidance stops at rediscovery until requester BYOC/accepted-market authority and isolation gates land, then permits only the resolved requester authority.
