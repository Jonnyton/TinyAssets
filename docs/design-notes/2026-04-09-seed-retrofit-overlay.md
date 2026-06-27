---
status: shipped
shipped_date: 2026-04-09
---

# 2026-04-09 Seed Retrofit Overlay

## Problem

TinyAssets grew substantial architecture and implementation before the newer seed
surfaces existed. As a result, the repo had strong core truth files but weak
navigation, weak idea intake, and a sparse Obsidian graph outside the largest
planning documents.

## Context

- `AGENTS.md`, `PLAN.md`, and `STATUS.md` already exist and should remain the
  authoritative core.
- The repo has many important planning documents at the root, but no top-level
  `README.md` or `INDEX.md` to connect them.
- The project now needs better handling for cross-provider user steering and
  stray ideas that should become shipped work instead of chat residue.
- Runtime code and storage surfaces should not be moved during this retrofit.

## Options

1. Leave the repo structure mostly unchanged and rely on the current core docs.
2. Move existing planning docs into a new directory tree.
3. Add the missing seed-era navigation and capture surfaces around the existing
   project without moving current technical artifacts.

## Decision

Choose option 3.

Additive overlay is the safest path:

- add `README.md` and `INDEX.md` as repo hubs
- add `ideas/` for intake, triage, and shipped traceability
- add `knowledge/` markdown as a human-readable companion to `knowledge.db`
- add `docs/exec-plans/`, `docs/specs/`, `docs/decisions/INDEX.md`, and
  `templates/`
- update operating docs so multiple concurrent provider sessions have a durable
  home for new user steering

## Follow-Up

- Start using `ideas/INBOX.md` immediately for new non-executed user ideas.
- Gradually link or migrate high-value knowledge into `knowledge/pages/` and
  `knowledge/syntheses/`.
- Prefer new multi-step delivery planning in `docs/exec-plans/` instead of
  creating more disconnected root plan documents.
