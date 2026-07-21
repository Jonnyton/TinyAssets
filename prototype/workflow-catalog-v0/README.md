# Workflow-catalog/ v0 — Repo Skeleton

**Status:** Skeleton of the content-repo that will eventually live at a separate GitHub repo (`<org>/Workflow-catalog/`) per spec #32 §1.2. For this prototype, it lives as a subdirectory of the main repo.
**Purpose:** Demonstrate the repo layout + GitHub Actions export/ingest pipelines before track G dispatches.
**Out of scope for v0:** actual bot-signed commits, Supabase integration, per-PR validation Action running live.

## Contents

```
prototype/workflow-catalog-v0/
├── README.md              # this file
├── LICENSE                # CC0-1.0 per host Q7
├── CONTRIBUTING.md        # PR-ingest rules for OSS contributors
├── catalog/
│   ├── nodes/
│   │   └── example-node.yaml     # one sample showing the export shape
│   ├── goals/                     # empty dir — populated at export time
│   ├── branches/                  # empty dir — populated at export time
│   └── status.json                # export manifest
├── .github/
│   └── workflows/
│       ├── validate-pr.yml        # runs on every incoming PR
│       └── ingest-on-merge.yml    # runs when merged
└── scripts/
    └── export-from-postgres.py    # skeleton of the Edge-Function equivalent
```

## What this demonstrates

Per spec #32:
1. **Flat YAML shape** per exported artifact, with CC0-1.0 `license:` frontmatter.
2. **Allowlist-only render** — only fields explicitly named in the render function appear in exports.
3. **`catalog/status.json`** manifest tracks `head_version`, `last_batch_id`, `last_batch_at`.
4. **GitHub Actions** — validate-pr.yml (6 checks per #32 §3.2) + ingest-on-merge.yml (calls `ingest_catalog_merge` RPC).
5. **CONTRIBUTING.md** states DCO requirement (sign-off per commit), license compatibility rule, PR-ingest flow.

## What's missing (v0 scope)

- No real Postgres to export from — `scripts/export-from-postgres.py` is a skeleton reading from stdin/mock.
- No real `ingest_catalog_merge` RPC endpoint — ingest-on-merge posts to a configurable URL.
- Bot identity placeholder (`workflow-catalog-bot[bot]` doesn't exist yet).
- No branch-protection rules (that's a GitHub repo setting, not in-tree).

## OPEN flags

- License file: **CC0-1.0** locked per `project_license_fully_open_commons.md` update (confirmed in dispatch). Platform code stays MIT.
- Bot account creation: host task pre-launch.
- Per-PR validation Action's exact `N_auto_hide_threshold` and min-bid defaults: cross-ref spec #32 §3.2 + #36 §3.
