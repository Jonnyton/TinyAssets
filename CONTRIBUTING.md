# Contributing to TinyAssets

Thanks for looking at TinyAssets. This document tells you how to contribute code, content, connectors, and reviews — and what you can expect back from us in return. If anything here is unclear, open an issue.

---

## What lives where

- **`TinyAssets/`** (this repo, platform code) — MIT-licensed Python + prototypes. PRs land here for the MCP gateway, tray, connectors, node authoring surface, infra.
- **`TinyAssets-catalog/`** (content repo, CC0-1.0) — node YAMLs, branch definitions, catalogs (node-type / integration-pattern / domain-pattern / privacy / moderation). PRs land here for node + branch + taxonomy contributions.
- **`docs/design-notes/`, `docs/specs/`, `docs/catalogs/`** — design documentation. PRs welcome for amendments, counter-proposals, new specs.

**Pick the right repo for your contribution:** connector code → `TinyAssets/connectors/`. A new node definition → `TinyAssets-catalog/catalog/nodes/`. A design critique → `docs/design-notes/` in `TinyAssets/`.

---

## Our commitment to you — Review SLA

This section is the forever-rule answer to "is my PR going to rot?" Short answer: **no.**

### Response SLA (what you can expect)

| Event | Target | Commitment |
|---|---|---|
| **First-response to a PR** | ≤48 hours (weekday median) | A named maintainer acknowledges the PR + either reviews or tells you who will. No silent inbox. |
| **Full review** | ≤5 calendar days | A complete review pass with merge / change-request / decline decision. If the work is larger than maintainer bandwidth, we'll say so + propose a chunking plan. |
| **Re-review after changes** | ≤48 hours (weekday median) | Same clock re-starts on push-to-branch. |
| **Merge decision** | ≤10 calendar days from PR open (absent blocker) | If a decision takes longer, it's because of a genuine blocker (spec ambiguity, cross-PR coordination, host out sick) — maintainer posts the reason on the PR. |

### Holiday / out-of-office exceptions

If a named maintainer is OOO ≥72 hours, they either (a) hand off to another admin-pool member or (b) post an OOO note to the repo's pinned issue with expected return date. PRs opened during OOO windows get first-response when the reviewer returns + the clock is measured from OOO-end, not PR-open.

### Escalation path if SLA is breached

1. Comment on the PR tagging `@maintainers` after 72h of no first-response.
2. If still silent after 5 days, email `security@tinyassets.io` with the PR URL. Admin-pool members rotate this inbox.
3. If still silent after 10 days with no SLA-breach explanation, the PR is eligible for the `stale-maintainer` escalation — file an issue in `TinyAssets/` titled `SLA breach: PR #N`. Admin pool treats this as a P1 operational flag.

No single maintainer can make your PR invisible. If one is unresponsive, the admin-pool surface exists to catch it.

### Launch-window caveat (2026-04 → ~2026-07)

During the initial launch window, the admin pool is size 1-2 (host + first co-maintainer per `SUCCESSION.md` §2). The SLA above is our best-effort target; we expect to hit the 48h first-response median but occasional 3-5 day slips are realistic. **If you see a pattern of slips, flag it in the `stale-maintainer` path** — we'd rather hear about SLA breaches than have contributors quietly bounce.

Post-launch (admin pool ≥3), the SLA becomes a hard commitment. Breach-rate is tracked in the public maintainer-health dashboard.

---

## Who reviews

Current admin pool (see `SUCCESSION.md` §2 for canonical list):

| Role | Who | What they review |
|---|---|---|
| **Host / primary maintainer** | Jonathan Farnsworth | All PRs by default during launch window. |
| **Co-maintainer #1** (pre-launch seat — TBD) | — | Connectors, tray, node authoring surface. Backup reviewer for all other areas. |
| **Moderation admin** (may overlap with co-maintainer) | — | Content-catalog PRs + moderation-rubric changes. |
| **User-sim persona reviewer** | `user` agent (automated) | Catalog + onboarding copy — checks persona authenticity + real-world-effect framing. |

**Maintainer rotation:** the first review on each PR is auto-assigned round-robin across the admin pool. The assignee can re-route if another member is a better fit; re-routes must happen within the 48h first-response clock.

---

## How to contribute

### 1. Platform code (`TinyAssets/`)

- Fork + branch off `main`.
- Run `ruff check` + `pytest` locally before pushing — our pre-merge CI runs both.
- Follow the conventions in `AGENTS.md` (hard rules, TypedDict+Annotated-reducer state, no destructive operations without user approval).
- New modules need tests. Nodes must never crash — graceful fallback always.
- Sign commits with DCO (`Signed-off-by: Your Name <email>`). No CLA required.

### 2. Connectors (`TinyAssets/connectors/<name>/`)

See `docs/specs/2026-04-19-connectors-two-way-tool-integration.md` §9. Required files:
- `__init__.py` exporting a class matching `ConnectorProtocol`.
- `MANIFEST.yaml` declaring name/version/auth_kind/required_scopes/actions.
- `tests/test_connector.py` with mock-backed unit tests for each declared action.
- `README.md` covering setup + scope rationale + known limitations.

Review criteria: privacy compliance (no payload logging), auth via shared `OAuth2Handler`, error-taxonomy mapping, tests, documentation, maintainer contact.

### 3. Node + Branch content (`TinyAssets-catalog/`)

- Start with an existing node YAML as a template (see `catalog/nodes/example-node.yaml`).
- License: **CC0-1.0** for all catalog content. No exceptions at launch.
- Required fields per `docs/catalogs/node-type-taxonomy.md` + `docs/catalogs/integration-patterns.md`.
- Persona-authenticity test: can you describe this node's use-case in the voice of a real user with a real project? If the answer is "no" or "it's a toy example," rework it before submitting.

### 4. Design notes + specs (`TinyAssets/docs/`)

- Design-notes go in `docs/design-notes/YYYY-MM-DD-<slug>.md`.
- Specs (executable feature plans) go in `docs/specs/YYYY-MM-DD-<slug>.md` or the existing INDEX.
- Counter-proposals are welcome — open an issue linking to the existing doc + your alternative. We track dissent, not just consensus.

### 5. Reviews

You don't have to be an admin-pool member to review. Drive-by reviews are welcome + weighted in the maintainer-health dashboard. If you want to commit to regular review work, say so in an issue — it's the fastest path to admin-pool seating.

---

## What we won't merge

- Code without tests (nodes + platform both).
- Connectors that log payload content.
- Catalog content with a non-CC0 license.
- PRs that add backwards-compatibility shims for removed code (delete the dead code — we're not supporting legacy).
- Anything that breaks the "main is always downloadable" standing principle (see `STATUS.md`).
- PRs that change `AGENTS.md` hard rules without a corresponding design note + admin-pool sign-off.

---

## Getting help

- **General questions:** open a discussion in `TinyAssets/`.
- **Security reports:** email `security@tinyassets.io` (PGP key in `SUCCESSION.md`).
- **Stuck contributor:** ping `@maintainers` on your PR. If you've been stuck for >72h, use the escalation path above — we want to unblock you.

Thanks for showing up. The forever-rule is "TinyAssets is always up, always downloadable, always reviewable" — contributors make the third clause real. We owe you the review time you're giving us the code time for.

---

## Cross-references

- `SUCCESSION.md` — admin pool roster, rotation policy, recruitment criteria.
- `AGENTS.md` — behavioral norms, hard rules, testing requirements.
- `docs/specs/2026-04-19-connectors-two-way-tool-integration.md` §9 — connector plugin schema.
- `docs/catalogs/node-type-taxonomy.md` + sibling catalogs — content contribution shapes.
- `docs/moderation_rubric.md` — how reported content is evaluated.

---

## Open questions (pending host decisions)

This section lists commitments in this doc whose concrete values are still pending host decision. Contributors should know what's still being finalized.

**Q25-nav (maintainer rotation at launch):** This doc commits to a 48h first-response SLA. The admin-pool size at launch-day-zero is 1-2 (host + first co-maintainer per `SUCCESSION.md`). Host has three options for how to honor the SLA during the launch window:
- **(a)** Accept tier-3 bounce risk; honor SLA on best-effort only; post the "launch-window caveat" above as our actual posture.
- **(b)** Delay launch until admin pool ≥ 3 (hard SLA from day zero).
- **(c)** Launch + recruit co-maintainers mid-launch-window; SLA hardens as pool grows.

Current draft reflects (c). If host picks (a) or (b), the "Launch-window caveat" section changes.

Resolution target: before `tinyassets.io` launch-day-zero.
