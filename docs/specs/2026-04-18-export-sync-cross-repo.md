---
status: active
---

# Cross-Repo Export Sync — `TinyAssets/` + `TinyAssets-catalog/` (Track G)

**Date:** 2026-04-18
**Author:** dev (task #32 pre-draft; unblocks track G when dispatched)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` — §4 GitHub export sink, §14.6 scale audit (diff-only ≤12 commits/h), §16.4 scope resolution, §17 per-piece privacy.
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` — `artifact_field_visibility`, `training_excluded`, `nodes.concept_visibility`, `strip_private_fields` function.
- Memory: `project_license_fully_open_commons.md` (CC0 / CC-BY-SA / MIT-style all OPEN; lead's dispatch uses CC0 as working assumption).
- Memory: `project_collab_model_split.md` — wiki-open for content, fork-and-PR for platform code.

Track G is the bridge between Postgres-canonical live content and the two GitHub repos. Gets wrong → either clone-and-run breaks, or private data leaks into public commits. Both failure modes are unrecoverable at scale.

---

## 1. Two repos — scope + responsibilities

### 1.1 `TinyAssets/` (platform code)

Repo root:
```
Workflow/
├── tinyassets/                  # engine package
├── domains/                   # domain-specific workflow shells
├── fantasy_daemon/            # reference domain
├── tests/
├── docs/                      # this repo's design notes + specs
├── packaging/                 # tray installers, MCP plugin mirror
├── scripts/
├── AGENTS.md
├── PLAN.md
├── STATUS.md
├── CLAUDE.md
├── CONTRIBUTING.md
├── LICENSE                    # platform-code license (MIT-style per license memory)
└── pyproject.toml
```

**Never touched by export sync.** Postgres content never lands here. Pure OSS fork-and-PR per §16.3. Bot has zero write access.

### 1.2 `TinyAssets-catalog/` (workflow content)

Repo root:
```
TinyAssets-catalog/
├── catalog/
│   ├── nodes/
│   │   ├── {node_id}.yaml
│   │   └── ...
│   ├── goals/
│   │   ├── {goal_id}.yaml
│   │   └── ...
│   ├── branches/
│   │   ├── {branch_def_id}.yaml
│   │   └── ...
│   └── status.json            # export manifest: head_version, last_batch_id, counts
├── README.md                  # "this is an export of the Postgres-canonical catalog; see TinyAssets/ for the platform"
├── LICENSE                    # content license (CC0 working assumption — OPEN Q1)
├── CONTRIBUTING.md            # PR-ingest flow + validation rules
└── .github/
    └── workflows/
        ├── validate-pr.yml    # bot runs on every incoming PR
        └── ingest-on-merge.yml  # bot runs when merged
```

**Bot-owned repo.** `tinyassets-catalog-bot[bot]` is the sole writer on the main branch (branch protection). Humans PR; bot validates + merges after review.

### 1.3 Division rules

| What | `TinyAssets/` | `TinyAssets-catalog/` |
|---|---|---|
| Engine Python code | ✓ | — |
| Infra (tray, MCP gateway) | ✓ | — |
| Node YAML artifacts (concept layer) | — | ✓ |
| Goal/branch YAML artifacts | — | ✓ |
| Design docs (this repo) | ✓ | — |
| Instance-data blobs | — | — (never leave owner's host) |
| License file | MIT-style | CC0 / CC-BY-SA (OPEN Q1) |
| Issue tracker | ✓ | content-bug issues only |

**Invariant:** no double-homing. A file in one repo is authoritative only for that repo. Engine-code contributions flow `TinyAssets/` → Postgres via config-reload-on-deploy, not via catalog. Content contributions flow `TinyAssets-catalog/` → Postgres via PR-ingest (§3).

---

## 2. Postgres → `TinyAssets-catalog/` export pipeline

### 2.1 Overall flow

```
┌────────────────────────────────────────────────┐
│ Postgres write (INSERT/UPDATE on nodes/goals/  │
│ branches WHERE concept_visibility='public'     │
│ AND training_excluded=false)                   │
└──────────────┬─────────────────────────────────┘
               │  trigger
               ▼
┌────────────────────────────────────────────────┐
│ public.pending_export(artifact_id, kind,       │
│   operation, row_version, queued_at)           │
│ — queue table, dedupes on latest version       │
└──────────────┬─────────────────────────────────┘
               │
               │  pg_cron every 5 min OR Realtime-triggered Edge Function
               ▼
┌────────────────────────────────────────────────┐
│ export_batcher Edge Function                   │
│  1. SELECT ... FROM pending_export             │
│     WHERE queued_at < now() - 30s              │
│     ORDER BY queued_at LIMIT 500               │
│  2. For each artifact: render YAML via         │
│     public.render_public_concept(id, kind)     │
│     which already strips via strip_private_    │
│     fields + excludes training_excluded rows   │
│  3. Stage per-file diffs in memory             │
│  4. If >0 diffs: commit batch via GitHub API   │
│     as tinyassets-catalog-bot[bot]               │
│  5. On success: DELETE processed rows,         │
│     advance status.json head_version           │
└──────────────┬─────────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────┐
│ GitHub TinyAssets-catalog/ main                   │
│  commit: "sync: <batch_id> (N artifacts)"       │
│  author: tinyassets-catalog-bot[bot]              │
└────────────────────────────────────────────────┘
```

### 2.2 Trigger strategy — decided

**Option picked: Postgres trigger → `pending_export` queue table + pg_cron 5-min batch job.**

Rationale vs the alternatives:
- Realtime subscription would work (control-plane Edge Function subscribes to `nodes` CDC + does the export). But Realtime isn't durable on its own — if the Edge Function drops, events are missed. A queue table is the durable backstop.
- Pure polling (cron scans `nodes.updated_at > last_exported_at`) works but adds a scan per run; queue table is O(changes) not O(total).
- Trigger + queue + cron gives us: durable (row-level), O(changes), squash-batchable, ≤12 commits/h bound honored mechanically.

### 2.3 `pending_export` queue table

```sql
CREATE TABLE public.pending_export (
  queue_id     bigserial PRIMARY KEY,
  artifact_id  uuid NOT NULL,
  artifact_kind text NOT NULL CHECK (artifact_kind IN ('node','goal','branch')),
  operation    text NOT NULL CHECK (operation IN ('upsert','delete')),
  row_version  bigint NOT NULL,
  queued_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (artifact_id, artifact_kind)  -- dedupe on (id, kind); latest row_version wins
);

CREATE INDEX pending_export_queued ON public.pending_export (queued_at);
```

**Dedupe behavior:** second write to the same artifact upserts the row — `row_version` moves forward, `queued_at` resets. Exporter processes the latest version only. If 100 edits land in 30s, only one YAML diff commits.

### 2.4 Postgres triggers

```sql
CREATE FUNCTION public.enqueue_export() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  kind text;
BEGIN
  kind := TG_ARGV[0];   -- 'node' / 'goal' / 'branch'
  IF TG_OP = 'DELETE' THEN
    INSERT INTO public.pending_export (artifact_id, artifact_kind, operation, row_version)
    VALUES (OLD.node_id, kind, 'delete', OLD.version)
    ON CONFLICT (artifact_id, artifact_kind)
    DO UPDATE SET operation = 'delete', row_version = EXCLUDED.row_version, queued_at = now();
    RETURN OLD;
  END IF;

  -- Only enqueue PUBLIC rows. Private-to-public visibility flip also enqueues.
  IF NEW.concept_visibility = 'public' AND NEW.training_excluded = false THEN
    INSERT INTO public.pending_export (artifact_id, artifact_kind, operation, row_version)
    VALUES (NEW.node_id, kind, 'upsert', NEW.version)
    ON CONFLICT (artifact_id, artifact_kind)
    DO UPDATE SET operation = 'upsert', row_version = EXCLUDED.row_version, queued_at = now();
  ELSIF OLD.concept_visibility = 'public' AND NEW.concept_visibility != 'public' THEN
    -- public→private flip: export deletion
    INSERT INTO public.pending_export (artifact_id, artifact_kind, operation, row_version)
    VALUES (NEW.node_id, kind, 'delete', NEW.version)
    ON CONFLICT (artifact_id, artifact_kind)
    DO UPDATE SET operation = 'delete', row_version = EXCLUDED.row_version, queued_at = now();
  END IF;

  RETURN NEW;
END;
$$;

CREATE TRIGGER nodes_enqueue_export
  AFTER INSERT OR UPDATE OR DELETE ON public.nodes
  FOR EACH ROW EXECUTE FUNCTION public.enqueue_export('node');

-- Analogous triggers on goals, branches.
```

Note the **public→private flip emits a delete** — keeps the catalog in sync when a user privatizes a previously-public node. Ensures the catalog can never lag behind in the direction that leaks data.

### 2.5 Rendering YAML (privacy allowlist pattern)

Per task requirement: **allowlist, not blocklist.** Easier to reason about; a new field added to `nodes` defaults to NOT-exported until explicitly added to the allowlist.

```sql
CREATE FUNCTION public.render_public_concept(p_id uuid, p_kind text)
RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_row    record;
  v_yaml   text;
  v_concept jsonb;
BEGIN
  IF p_kind = 'node' THEN
    SELECT n.node_id, n.slug, n.name, n.domain, n.status, n.structural_hash,
           n.input_schema, n.output_schema, n.tags, n.parents,
           n.version, n.created_at, n.updated_at,
           n.concept
      INTO v_row
      FROM public.nodes n
      WHERE n.node_id = p_id
        AND n.concept_visibility = 'public'
        AND n.training_excluded = false;

    IF NOT FOUND THEN RETURN NULL; END IF;

    -- Strip private fields (even inside public nodes, individual fields
    -- may be marked private per §17 artifact_field_visibility).
    v_concept := public.strip_private_fields(v_row.concept, v_row.node_id, 'node');

    -- Build YAML via allowlist of known fields.
    v_yaml := format(
      E'# Auto-exported from Workflow Postgres. Do not hand-edit in this repo;\n' ||
      E'# submit changes via PR — they round-trip back into Postgres on merge.\n' ||
      E'license: %s\n' ||
      E'schema_version: 1\n' ||
      E'node_id: %s\n' ||
      E'slug: %s\n' ||
      E'name: %s\n' ||
      E'domain: %s\n' ||
      E'status: %s\n' ||
      E'structural_hash: %s\n' ||
      E'version: %s\n' ||
      E'tags: %s\n' ||
      E'parents: %s\n' ||
      E'input_schema: |\n  %s\n' ||
      E'output_schema: |\n  %s\n' ||
      E'concept: |\n  %s\n',
      (SELECT default_content_license FROM public.catalog_config LIMIT 1),
      v_row.node_id, v_row.slug, v_row.name, v_row.domain, v_row.status,
      v_row.structural_hash, v_row.version,
      to_json(v_row.tags), to_json(v_row.parents),
      v_row.input_schema::text, v_row.output_schema::text,
      v_concept::text
    );

    RETURN v_yaml;
  END IF;

  -- (analogous branches for 'goal' and 'branch' kinds, each with its own allowlist)
  RETURN NULL;
END;
$$;
```

**License injected at export time** from a config row — not hardcoded. Migration from CC0 → CC-BY-SA (or whatever host pins in Q1) is `UPDATE catalog_config SET default_content_license = 'CC-BY-SA-4.0';` — no code redeploy. Then a one-time re-export refreshes every YAML header.

### 2.6 Batcher Edge Function

```python
# pseudocode — Supabase Edge Function, cron every 5 min
async def export_batcher():
    # 1. Drain pending queue (up to 500 artifacts per batch).
    rows = await pg.fetch("""
        SELECT queue_id, artifact_id, artifact_kind, operation, row_version
        FROM public.pending_export
        WHERE queued_at < now() - interval '30 seconds'
        ORDER BY queued_at
        LIMIT 500
        FOR UPDATE SKIP LOCKED
    """)
    if not rows:
        return  # nothing to do

    # 2. Render YAML for each upsert / compute delete paths.
    diffs = []
    for row in rows:
        path = f"catalog/{row['artifact_kind']}s/{row['artifact_id']}.yaml"
        if row["operation"] == "upsert":
            yaml = await pg.fetchval(
                "SELECT public.render_public_concept($1, $2)",
                row["artifact_id"], row["artifact_kind"],
            )
            if yaml is None:
                # Row became non-public between trigger and batch; treat as delete.
                diffs.append(("delete", path, None))
            else:
                diffs.append(("upsert", path, yaml))
        else:
            diffs.append(("delete", path, None))

    # 3. Open a batch commit against GitHub API.
    batch_id = str(uuid.uuid4())
    message = f"sync: {batch_id[:8]} ({len(diffs)} artifacts)"
    try:
        commit_sha = await github_batch_commit(
            repo="TinyAssets-catalog",
            branch="main",
            diffs=diffs,
            message=message,
            author=TINYASSETS_CATALOG_BOT,
        )
    except GithubRateLimitError as e:
        # Leave rows in pending_export; next cron retries. Log + alert.
        await alert_admin(f"catalog export rate-limited: retry at {e.reset_at}")
        return
    except GithubTransientError:
        return  # retry next tick

    # 4. Update catalog/status.json with head_version + batch_id + timestamp.
    await github_update_file(
        repo="TinyAssets-catalog",
        branch="main",
        path="catalog/status.json",
        content=json.dumps({
            "head_version": max(r["row_version"] for r in rows),
            "last_batch_id": batch_id,
            "last_batch_at": datetime.now(timezone.utc).isoformat(),
            "artifact_count": await pg.fetchval("SELECT count(*) FROM public.nodes WHERE concept_visibility='public'"),
        }, indent=2),
        message=f"status: {batch_id[:8]}",
    )

    # 5. Delete processed rows. pending_export is now drained for this batch.
    await pg.execute(
        "DELETE FROM public.pending_export WHERE queue_id = ANY($1)",
        [r["queue_id"] for r in rows],
    )
```

### 2.7 ≤12 commits/h guarantee

5-min cron → max 12 runs/h. Each run = at most ONE commit (plus one status.json commit per run = up to 24/h if both fire). **Squash on status.json:** only write it if `head_version` actually advanced. Net ≤12 commits/h always.

For bulk import events (>500 diffs in one batch), batcher processes 500, leaves the rest, next cron tick gets the next 500. Burst-protected.

### 2.8 Idempotency

Same batch re-run is safe because:
- `pending_export` rows are deleted after successful commit. Re-run would see an empty queue.
- Commit author + message include `batch_id`. GitHub API call with the same tree-hash is a no-op in practice.
- Crash between commit success + queue delete: next batch re-stages the same YAML (identical content → GitHub returns no-op), then deletes queue rows. Worst case: ONE redundant status.json commit.

---

## 3. `TinyAssets-catalog/` → Postgres ingest pipeline (PR-based)

### 3.1 Contributor flow

```
OSS contributor                   TinyAssets-catalog/
      │
      ├─ forks TinyAssets-catalog/
      ├─ edits catalog/nodes/<id>.yaml
      ├─ opens PR against main ──────→
      │                                 │
      │                                 ▼
      │                         ┌──────────────────┐
      │                         │ validate-pr.yml  │
      │                         │ GitHub Action    │
      │                         └──┬───────────────┘
      │                            │
      │                            ▼
      │                     (6 validation checks — §3.2)
      │                            │
      │                   all pass │   fail
      │                            ▼
      │                     ┌──────────────┐
      │                     │ PR labeled   │  or ┌─────────────────────┐
      │                     │ "ready"      │     │ PR comment w/ error │
      │                     └──────┬───────┘     │ + blocking label    │
      │                            │             └─────────────────────┘
      │                            ▼
      │                     ┌──────────────┐
      │                     │ Human review │ (tier-3 contributor w/ merge rights)
      │                     └──────┬───────┘
      │                            │ approved
      │                            ▼
      │                     ┌──────────────┐
      │                     │ PR merged    │ (squash to bot-attributed commit)
      │                     └──────┬───────┘
      │                            │
      │                            ▼
      │                     ┌──────────────────┐
      │                     │ ingest-on-merge  │
      │                     │ GitHub Action    │
      │                     └──────┬───────────┘
      │                            │
      │                            ▼
      │                     Reads diff, calls control-plane RPC
      │                     `ingest_catalog_merge(payload, pr_meta)`
      │                            │
      │                            ▼
      │                     Control plane validates + applies via RLS
      │                     (NOT direct DB write — goes through RPC)
      ▼                            │
   contributor sees      ┌─────────┴─────────┐
   PR merged, web app    │ success            failure
   live within ~30s      ▼                    ▼
                  ledger + node        ingest row
                  updated,              added to admin
                  export trigger        queue, PR
                  fires back to         auto-reverted
                  catalog (idempotent)  via revert-PR bot
```

### 3.2 Bot validation checks

`validate-pr.yml` runs the following on every PR push:

1. **Schema valid** — YAML parses; `schema_version: 1` present; all allowlist fields present; no fields outside the allowlist.
2. **License compatible** — `license` field exactly matches `catalog_config.default_content_license` (or is a listed compatible). CC0 is compatible with CC0; CC-BY-SA blocks CC0 ingest (etc.).
3. **No private-instance fields** — PR must NOT introduce any field in the private-blocklist (`instance_ref`, credentials-shaped patterns, file paths, known instance examples). Regex-driven pass.
4. **Hash matches** — for an `upsert`, the PR must reference the current `structural_hash` as its `base_structural_hash` in PR body. Catches stale forks.
5. **Author identity OK** — PR author's GitHub OAuth identity must be linkable to a `users.user_id`. Ingest credits the change to that user's provenance chain.
6. **Version check** — PR's declared `version` must be exactly `Postgres_current_version + 1` for upserts. Stale (e.g. version==current) → reject with "rebase against HEAD." Newer (e.g. version>current+1) → reject as "invalid version jump." Forces linear history.

Failure-mode: bot comments with actionable error, applies `blocked` label. PR author rebases, pushes, re-triggers.

### 3.3 Ingest-on-merge RPC

```sql
CREATE FUNCTION public.ingest_catalog_merge(
  p_payload    jsonb,           -- the merged YAML, parsed
  p_pr_meta    jsonb            -- {pr_number, author_github_handle, merged_at, sha}
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER  -- runs as elevated role, but attributes to author_user_id
AS $$
DECLARE
  v_author_id uuid;
BEGIN
  -- Resolve PR author → user_id via github_handle.
  SELECT user_id INTO v_author_id
  FROM public.users
  WHERE github_handle = p_pr_meta->>'author_github_handle';

  IF v_author_id IS NULL THEN
    RAISE EXCEPTION 'pr_author_not_registered: %', p_pr_meta->>'author_github_handle';
  END IF;

  -- Final race-check: Postgres version must STILL match what the PR expected.
  PERFORM 1 FROM public.nodes
   WHERE node_id = (p_payload->>'node_id')::uuid
     AND version = (p_payload->>'version')::bigint - 1;
  IF NOT FOUND THEN
    -- Race lost: someone else merged between PR bot validation and now.
    INSERT INTO public.ingest_reject_log (...) VALUES (...);
    RETURN jsonb_build_object('status', 'rejected', 'reason', 'race_conflict');
  END IF;

  -- Apply the write. This acts as author_user_id via the attribution column;
  -- RLS still enforces column-level privacy (payload can't set private fields).
  UPDATE public.nodes
     SET concept = p_payload->'concept',
         name = p_payload->>'name',
         tags = array(select jsonb_array_elements_text(p_payload->'tags')),
         parents = array(select jsonb_array_elements_text(p_payload->'parents'))::uuid[],
         version = (p_payload->>'version')::bigint,
         last_edited_at = now()
   WHERE node_id = (p_payload->>'node_id')::uuid;

  INSERT INTO public.node_activity (node_id, actor_user_id, event_kind, payload)
  VALUES ((p_payload->>'node_id')::uuid, v_author_id, 'edited',
          jsonb_build_object('source', 'catalog_pr', 'pr_meta', p_pr_meta));

  RETURN jsonb_build_object('status', 'applied', 'new_version', (p_payload->>'version')::bigint);
END;
$$;
```

**Why RPC, not direct DB write from the Action:** RPC runs with SECURITY DEFINER so it can perform the write, but the attribution + validation happen in-DB. Prevents the ingest Action from becoming a super-user that bypasses RLS. Auditable, revocable.

### 3.4 Conflict behavior

PR version ≠ current version+1 at merge time:
- If current advanced (version > expected base): `race_conflict` rejection. Auto-revert-bot opens a new PR reverting the merge, comments "race with newer write in Postgres; rebase and resubmit." Contributor re-forks from now-current state.
- If current regressed (public→private flip happened): `target_private` rejection. PR is revert-merged; contributor informed "this node went private while your PR was open."

---

## 4. Rate-limit defense

### 4.1 GitHub API budgets

- **Unauthenticated:** 60/h. Unusable for a bot.
- **GitHub App (recommended):** 5,000/h per installation × (number of installations). Our bot is ONE installation → 5,000/h.
- **Per-repo:** no hard per-repo cap, but secondary rate limits kick in on "excessive contribution creation" (sustained >80 contributions/min).

### 4.2 Our usage at scale

| DAU | Write rate → catalog | Commits/h | API calls/h | Headroom |
|---|---|---|---|---|
| 1k | ~50 artifact writes/h | 12 (squashed) | ~60 | 80× |
| 10k | ~500 artifact writes/h | 12 (squashed) | ~80 | 60× |
| 100k | ~5,000 artifact writes/h | 12 (squashed) | ~150 (larger trees per commit) | 30× |

Batched commits keep headroom huge. 100k DAU still 30× under the ceiling.

### 4.3 Backpressure

If the 5-min cron's queue drain hits the 500-artifact batch limit for 3 consecutive runs, alert host-admin. Usually means a bulk import event; bot keeps draining, catalog catches up within ~30 min on a typical pool.

If the bot gets rate-limited (shouldn't happen at our scale, but defensively):
- Queue rows stay in `pending_export`. No data loss.
- Next cron retries. GitHub's rate-limit reset header tells us exactly when.
- `status.json` stamps `last_batch_at`; web app shows "catalog sync behind by X min" banner if >10 min stale.

---

## 5. License metadata propagation

### 5.1 Per-node YAML frontmatter

Every exported node YAML carries `license: <id>` (§2.5 render function). Pulls from `catalog_config.default_content_license` at render time.

### 5.2 Repo-level

- `LICENSE` file in `TinyAssets-catalog/` root — full text of whichever license host pins in Q1.
- `README.md` top section: "All content in this repo is licensed under `<LICENSE>`. See individual YAML `license:` fields for per-artifact overrides (none at MVP)."
- `CONTRIBUTING.md`: "By opening a PR, you agree your contribution is licensed under the repo LICENSE. DCO-style (Developer Certificate of Origin) — no CLA. Sign-off on each commit via `git commit --signoff`."

### 5.3 Per-artifact override (post-MVP)

Schema already supports per-node license via a future `nodes.license` column (OPEN Q2). Not in MVP. If added: render function prefers per-node over default.

### 5.4 License migration path

Host switches `default_content_license` config value → next batch run re-renders affected YAMLs with the new license. Over time, every artifact's YAML carries the new license. No historical-artifact rewrite; the YAML at that time is self-describing.

---

## 6. Private-instance guarantee (allowlist enforcement)

### 6.1 Test scenarios

Every code change to the export path MUST re-run these three tests:

**T1: Public node with private field.**
- Create a node with `concept = {"purpose": "x", "example_company": "AcmeCorp"}`.
- Mark `concept.example_company` path as `visibility='private'` in `artifact_field_visibility`.
- Trigger export.
- **Assert:** exported YAML does NOT contain "AcmeCorp" or "example_company" anywhere in the diff.

**T2: Training-excluded row.**
- Create a node with `training_excluded = true`.
- Trigger export.
- **Assert:** no `pending_export` row inserted (§2.4 trigger filters this).

**T3: Visibility flip.**
- Create a public node, export it.
- Flip `concept_visibility = 'private'`.
- Trigger export again.
- **Assert:** next batch produces a `delete` diff; YAML vanishes from the repo.

### 6.2 Allowlist in `render_public_concept`

The YAML render function explicitly names every field it emits. Adding a new column to `nodes` does NOT automatically export it. Dev must modify the render function to expose the column, and then schema review confirms "this field is safe to public." Safer than a blocklist where a forgotten blocklist entry = leak.

### 6.3 Paranoid layer: post-render scan

Belt-and-suspenders: after render, the Edge Function scans the rendered YAML for a blocklist of known-sensitive patterns:
- Email addresses.
- Absolute file paths (`C:\`, `/home/`, `/Users/`).
- Credential-shaped regexes (`sk-...`, API-key-looking strings).
- Known private-field names (`instance_ref`, `instance_data`, `credentials`).

If any match: abort the batch, alert admin, keep queue intact. Manual review required before retry. Explicit failure > silent leak.

---

## 7. Bot account setup

### 7.1 GitHub App (preferred)

Create `tinyassets-catalog-bot` as a GitHub App (not a personal access token or service account). Why:
- Scoped permissions (write to `TinyAssets-catalog` only; zero permission on `TinyAssets/`).
- Installation-level rate limits (5k/h).
- Auditable action history.
- Rotatable private key.

Permissions requested:
- Repository: Contents (read+write), Pull Requests (read+write on catalog only), Actions (read), Metadata (read).
- User: none.

### 7.2 Token storage

GitHub App private key → Supabase Vault (encrypted at rest, per-project KMS key). Edge Function fetches via Supabase service-role at batch start; never logs the key.

Fallback for self-hosted deploys: environment variable with restrictive permissions; flag as OPEN Q3 for which path is primary.

### 7.3 Rotation plan

- GitHub App private key rotated every 6 months (calendar reminder).
- Rotation: generate new key in GitHub App settings → update Supabase Vault → invalidate old key. Zero-downtime because Edge Function picks up new key on next batch.

---

## 8. Failure modes

| Mode | Detection | Behavior |
|---|---|---|
| Export lag (pending_export backlog > 500 artifacts) | Batcher sees queue > 500 at batch start | Log + alert host-admin. Continue draining; catalog catches up within ~30 min. `status.json.last_batch_at` ages visibly. |
| GitHub API outage | Commit throws 5xx | Exporter returns early; queue preserved; retries on next cron. Web app shows "catalog sync delayed" after 10 min. |
| Rate-limited | 403 + X-RateLimit-Remaining=0 | Back off until `X-RateLimit-Reset`. Log reset time. |
| Bot token revoked | 401 on commit | Immediate admin alert (email + web-app admin banner). All writes stall until token rotated. |
| Malformed YAML from ingest PR | validate-pr.yml catches | Bot comments with actionable error, applies `blocked` label. PR author fixes + re-pushes. |
| Race at ingest merge | `ingest_catalog_merge` RPC returns rejected | `ingest_reject_log` row logged. Revert-bot opens counter-PR. Contributor sees automated comment with rebase instructions. |
| Post-render scan detects sensitive pattern | Paranoid scan §6.3 | Abort entire batch. Queue intact. Alert admin with the rendered output + artifact_id. Manual review before retry. |
| Pending queue corrupt (bad artifact_id) | Exporter throws on lookup | Isolate the bad row: move to `pending_export_quarantine`, continue processing rest of batch. Alert admin. |

---

## 9. Scale primitives

Cross-refs to §14 scale audit:

| §14 concern | Track G primitive |
|---|---|
| §14.6 diff-only batched ≤12 commits/h | `pending_export` queue + 5-min cron; `status.json` skips commit when head unchanged. Mechanically bounded. |
| §14.7 moderation at scale | PR validation fires automated checks pre-human-review; tier-3 reviewers triage. Rate-limit handled by GitHub. |
| §14.9 GitHub OAuth rate limits | Bot uses App installation token (not user OAuth). Separate quota; no contention with user-side OAuth. |

**New primitive: `pending_export` queue table** — durable, O(changes), dedupes on (artifact_id, kind). Processed in bulk by a single Edge Function with `FOR UPDATE SKIP LOCKED` to prevent double-processing if cron runs overlap.

---

## 10. Honest dev-day estimate

Navigator's §10 estimate: **1 dev-day** for track G (including +0.25d from §14.6 batched diff revision).

My build-out:

| Work item | Estimate |
|---|---|
| `pending_export` queue table + 3 triggers (node/goal/branch) + tests | 0.25 d |
| `render_public_concept` PL/pgSQL for node/goal/branch (allowlist-based, 3 kinds) | 0.4 d |
| `catalog_config` table + license-at-export wiring | 0.1 d |
| Edge Function `export_batcher` — queue drain, YAML render, GitHub commit, status.json update, transactional queue delete | 0.6 d |
| GitHub App creation + permissions + Supabase Vault key storage | 0.2 d |
| `TinyAssets-catalog/` repo initial scaffold (README, LICENSE, CONTRIBUTING, empty `catalog/`, `.github/` workflows) | 0.15 d |
| `validate-pr.yml` with 6 checks (§3.2) | 0.5 d |
| `ingest-on-merge.yml` Action + `ingest_catalog_merge` RPC | 0.5 d |
| Post-render paranoid scan (§6.3) + T1/T2/T3 test scenarios | 0.3 d |
| Failure-mode handling (rate-limit retry, token-revoke alert, quarantine queue) | 0.3 d |
| Revert-bot for ingest race conflicts | 0.2 d |
| Integration smoke — full round-trip: Postgres edit → catalog commit → PR edit → merged → back to Postgres | 0.4 d |
| Docs (`CONTRIBUTING.md` in catalog repo, admin runbook for rotation + backfill, schema-comment annotations) | 0.2 d |
| **Total** | **~4.1 d** |

**Revision: 1 d → ~4 d.** Navigator's 1d is severely under-scoped (same pattern as #26, #29, #30). The under-count: PR-ingest reverse path is half the work (3.3+3.4+ingest Action = ~1.2d alone), and isn't in navigator's "diff-only sync" framing.

**Defer paths:**
- **Ship forward-only first (Postgres → catalog, no PR ingest)** = ~1.8d. OSS contributors can't contribute content via PR at launch; they can fork-and-remix, just can't round-trip back. Low-severity defer — forward sync is the load-bearing "clone and run" forever-rule; ingest is a growth lever.
- **Skip revert-bot** = drop 0.2d. Race-conflicted PRs stay merged; manual admin cleanup. Tolerable at launch volume.
- **Skip paranoid post-render scan** = drop 0.3d. Rely on allowlist guarantee alone. Risk: single render-function bug leaks private data; scan is cheap insurance.

**Recommend full ~4d.** Pattern consistent with prior specs. Pushes §10 total by another +3d. Session-tally of my spec revisions: **+11.5d over navigator's estimates** (25:+0, 26:+2, 27:+1, 29:+3, 30:+2.5, 32:+3). Still fits weeks-not-months with two devs.

---

## 11. OPEN flags

| # | Question |
|---|---|
| Q1 | **License specifier** — host's `project_license_fully_open_commons.md` memory explicitly does NOT pin CC0 vs CC-BY-SA vs MIT-style. Task description assumes CC0. Needs host confirm. Affects both repo LICENSE files + `catalog_config.default_content_license` + the "license compatibility" check in validate-pr.yml. |
| Q2 | Per-node license override column (`nodes.license text DEFAULT NULL`) — post-MVP or bundled? Recommend post-MVP; config-level default covers launch. |
| Q3 | Bot-key storage path — Supabase Vault (hosted ecosystem match) vs env var (self-host friendly). Recommend Supabase Vault as primary, env var fallback. |
| Q4 | Human-review bottleneck on catalog PRs — at 100 PRs/day, tier-3 reviewer triage isn't free. Minimum reviewer count? Recruitment plan? Punt to §14.7 moderation backstop for now. |
| Q5 | Two-repo vs single-repo-with-branches — alternative: one `TinyAssets/` repo with `main` branch for code + `catalog` branch for content. Simpler, but GitHub Actions + permissions model gets tangled. Recommend two repos per task description. |
| Q6 | Structural-hash in PR body — how does a contributor easily read their base-version hash? Recommend: each YAML includes `base_structural_hash` in the file itself; validator compares against latest Postgres. Contributor edits + bumps version; validator catches drift. |
| Q7 | Bulk-import collision — user-sim or migration tool imports 10k nodes at once. Does the 500-per-batch cap hold? Cron takes ~30 min to drain. Acceptable as one-off; flag if it becomes a steady state. |
| Q8 | DCO vs CLA — DCO is lighter for contributors; CLA gives the project clearer relicense rights later. Recommend DCO for launch; revisit if relicense need arises. |
| Q9 | `TinyAssets-catalog/` repo owner — same GitHub org as `TinyAssets/`, or separate? Separate org isolates permissions + reduces blast radius on token leak. Recommend same org for discoverability, protect via branch protection. |
| Q10 | Search-engine indexing — should `TinyAssets-catalog/` be indexed by Google? Yes for commons-adoption per license memory; set robots.txt accordingly. |

---

## 12. Acceptance criteria

Track G is done when:

1. `TinyAssets-catalog/` repo exists with scaffold (README, LICENSE, CONTRIBUTING, empty `catalog/`, GitHub Actions).
2. `tinyassets-catalog-bot` GitHub App installed with scoped permissions. Key in Supabase Vault.
3. `pending_export` table + triggers installed on `nodes`, `goals`, `branches`.
4. End-to-end forward sync: edit a public node in the web app → within 10 min the commit appears in `TinyAssets-catalog/` by `tinyassets-catalog-bot[bot]`.
5. T1/T2/T3 privacy tests green (§6.1). In particular, a private field inside a public node does NOT appear in any commit.
6. End-to-end PR ingest: fork the catalog repo → edit a node YAML → open a PR → validator green → human merges → within 30s the Postgres `nodes` row reflects the edit + `node_activity` shows the PR author as `actor_user_id`.
7. Race test: open two PRs against the same node simultaneously; one merges first; the second's ingest-on-merge returns `race_conflict`; revert-bot opens counter-PR.
8. Rate-limit test (simulated): force 429 from GitHub API → batcher backs off, queue survives, next cron retries cleanly.
9. All 10 OPEN flags in §11 resolved or explicitly deferred. At minimum Q1 (license pick) MUST be resolved before track G ships.
10. Docs updated: `AGENTS.md` points to the two-repo split + the PR-ingest flow.

If any of the above fails, track G is not shippable; the "clone-and-run preserved + OSS contributions round-trip" part of the forever rule is not real without it.
